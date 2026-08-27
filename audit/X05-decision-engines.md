# X05 — Decision Engines Deep-Dive (X-Ray)

> X-Ray phase 5. Built 2026-08-13. The signal chain: what each decision engine
> actually computes, its exact thresholds, and where fabrication/bypass exists.

---

## 1. Signal chain (how a decision is produced)

```
regime_filter (gate) ─┬─> precision_signals (6-layer) ──> A+ / NO_SIGNAL
                      ├─> oi_intel (PCR/max-pain/walls/Murarkar)
                      ├─> sentiment / institutional (flow)
                      ├─> smart_strike_selector (Δ) + SL/TGT sizing
                      ├─> capital_guard (approval) + var_risk_manager
                      └─> market_brain / super_ai_ml (context/agreement)
                            └─> live_trader_brain (master synthesis, standalone)
```

## 2. `regime_filter.py` — the primary gate

- 4 regimes: **TRENDING / RANGE / VOLATILE / TRANSITION** (detect_regime:
  TRENDING `adx≥25 & |pdi−mdi|≥5`; RANGE `adx≤20`; VOLATILE BB-width pct ≥80%;
  else TRANSITION).
- **RANGE_LV (low-vol chop) = NO TRADE** for directional options (hard rule).
- VIX premium regime: CHEAP/NORMAL/RICH/HIGH/PANIC; VIX PANIC (≥22) + low
  confidence = hard no-trade; `STOP_LIMIT_VIX_PANIC_THRESHOLD=22`.
- Expected daily move = NIFTY × (VIX/100)/√252.
- Reads `market_brain` verdict as a confidence gate (consumes its frozen
  constants).

## 3. `precision_signals.py` — 6-layer confluence (the A+ gate)

Layer 1–6: regime → capital guard → technicals → OI/skew → institutional → ML.
Output: `A+` grade with confluence score, else `NO_SIGNAL`.

**Integrity findings (H1, M1, M2):**
- **Layer 3 passes a hardcoded 80% technical consensus** — not computed from
  market_brain. A+ can be produced from non-real inputs.
- **Capital layer always reports "100% Risk Compliant"** regardless of real pnl.
- On data failure, falls back to hardcoded `spot=24500.0` / `vix=12.0` reported
  as live (M1).
- SL = 0.8% arbitrary; RR label "1:2.0" hardcoded (L1).
- **M2**: options layer passes on `vix > 16.0` regardless of PCR alignment —
  the claimed PCR/skew confluence is bypassed.

## 4. `oi_intel.py` — OI intelligence

- **PCR**, **max pain** (argmin over ATM band spot ±8% — formula fixed in BOTH
  oi_intel and data_fetcher, keep in sync), **OI walls**, **Murarkar matrix**
  (CI/DD/FR accumulation-distribution), build-up/spike detection via **z-score
  vs own recent history** (genuinely adaptive baseline).
- `detect_build_up`: `chg_min_pct=8` declared, **never enforced** (LOW).
- Consumed by daily_report, mcp, gamma_flip, web_dashboard, alert_monitor.

## 5. `market_brain.py` — technical consensus (label vs reality)

- `make_verdict` → bias CALL/PUT/NEUTRAL, strength HIGH/MEDIUM/LOW, confidence
  (round, clamp **50–75**), reasons[], favored/avoid strategies, levels, IV-vs-HV notes.
- Calibration labelled **"TRAINED RULES"** but **hardcoded literals**:
  `call_thresh=0.45`, `put_thresh=0.30` (asymmetric — comments: puts 44.8% vs
  calls 27.8% hit); reliabilities RANGE 0.49 / TRENDING 0.46 / VOLATILE 0.55
  (comment claims "~70%" but code 0.55) / TRANSITION 0.46.
- `confidence = (reliability + |pct|·0.25 + bonus HIGH .10/MED .05/LOW 0) × 100`,
  clamped [50,75].
- `directional_consensus`: 6 votes (SMA50, SMA20, supertrend, RSI bull 45–65 /
  bear >70 or <30, MACD hist, PDI>MDI).
- **Trainer never writes back** — "looks adaptive, actually fixed."

## 6. `gamma_flip.py` — GEX / gamma regime

- MM net GEX + flip strike; returns `gamma_flip_strike` (None on no-data/error).
- ⚠ GEX uses **hardcoded T=15, σ=0.15** (not chain IV).
- Consumers read `gamma_flip_strike` key (documented gotcha).

## 7. `sentiment.py` — global/flow risk-on-off

Fixed thresholds: S&P ±0.5%, DXY ±0.3%, Gold >1% (−1), Crude >2% (−1), BTC >1%,
USDINR ±0.3%; FII/DII net ±1500 cr; PCR >1.5 / <0.7; max-pain pull >1.0%/1.5%.
Weights: global 1.0, fii 1.5, options 0.5. Total ≥2 → BULLISH, ≤−2 → BEARISH.

## 8. `mcx_intel.py` — commodities (dormant)

Gold/Silver ratio >85 → BULLISH_SILVER, <65 → BULLISH_GOLD; crude ±1.5%; metals
via DXY ±0.3%. Imported by run_all step 17 but **never called** (fixed print).

## 9. Master synthesis — `live_trader_brain.py` (standalone, not wired)

`evaluate_master_trader_brain()` merges 5 engines; requires ALL:
1. psychology `HEALTHY_MINDSET`
2. capital guard `APPROVED` (or kill-switch inactive)
3. `account_survival_rate_pct >= 95.0`
4. `super_ai_verdict != "NEUTRAL_SIDEWAYS"`
→ `RECOMMENDED_{ml_verdict}` / `STAND_BY_NO_TRADE`. **No caller in run_all/test_all.**

## 10. `agent_workflow_graph.py` — the one wired decision pipeline

6 nodes: (1) Market Data (spot+VIX from regime_filter, stand-down if no real
spot) → (2) Signal Detection (precision_signals) → (3) Strategy Decision
(directional buy via smart_strike OR defined-risk multi-leg) → (4) Risk
Validation (capital_guard APPROVED?) → (5) Execution (paper order) → (6)
Portfolio Update (paper summary equity). Run by run_all step 3.

## 11. Decision-integrity risk register

| # | Risk | Engine | Status |
|---|---|---|---|
| 1 | A+ signal from fabricated confluence (L3 hardcoded 80%, capital 100%) | precision_signals | **HIGH (H1), unfixed** |
| 2 | Options layer bypasses PCR/skew check when vix>16 | precision_signals | MED (M2) |
| 3 | Fake-live fallback spot/vix reported as live | precision_signals | MED (M1) |
| 4 | Sizer can exceed 1% cap (1-lot floor) | capital_guard | HIGH (H2) |
| 5 | "Trained" thresholds frozen; trainer never feeds back | market_brain / trainer | MED |
| 6 | GEX σ/T hardcoded not chain-derived | gamma_flip | LOW |
| 7 | `chg_min_pct=8` build-up gate never enforced | oi_intel | LOW |
| 8 | Master brain + swarm built but unwired | live_trader_brain, multi_agent_swarm | LOW |

## 12. What IS honest in the decision path

- regime_filter gate + VIX zones (real data, owner-mandated).
- oi_intel z-scores vs own history (adaptive baseline).
- smart_strike_selector Δ from live chain IV + BS.
- multi_leg_options from real LTP/BS greeks.
- institutional / stock_flow scans from real caches.
