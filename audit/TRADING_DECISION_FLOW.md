# Trading Decision Flow — Why the System Produces STAY_OUT / SKIP

> Phase 6.6 diagnosis-only report. No source code, thresholds, filters, risk
> rules or strategy logic were modified. No trades/predictions/outcomes were
> created. All evidence below is read from `data/ground_truth.db` (124 REAL
> signals, window 2026-08-13 12:45:59 -> 14:09:18 IST), current source code,
> and current cached market data.

## 1. The question

The frozen baseline has `STAY_OUT / SKIP rate = 100%`. This report answers:
**which gate is turning every directional candidate into STAY_OUT/SKIP?**

## 2. TL;DR

The system generates **zero directional candidates**. It is not rejecting
candidates downstream — no directional action is ever *produced*. The single
candidate generator, `precision_signals.generate_precision_signal()`, hard-
gates every output on the regime layer. The current regime is `RANGE_LV`
(low-vol chop, ADX 12.7, |PDI−MDI| 1.0, BB-width 46th percentile) whose
documented gate is `NO_TRADE`. That is the first and only blocker.

Capital Guard is **NOT** the blocker. It APPROVED all 124 no-trade decisions
(REJECT = 0). Confidence is **NOT** the blocker (no top-level confidence is
even emitted). `market_state = NULL` in the ledger is a persistence gap, not
a rejection — the regime IS computed and stored inside `checks_json`.

## 3. Current observation (evidence)

```
signals 124 | decisions 124 | feature_snapshots 124
predictions 0 | executions 0 | positions 0 | outcomes 0 | evaluations 0
direction: None x124 | score "2/6 (33%)" x124 | market_state NULL x124
decision_type SKIP x124 | reason "no evaluable signal (STAY_OUT/NO_SIGNAL)" x124
capital_guard_state APPROVED x124 | risk_state RISK_AUDIT_PASSED x124
REAL provenance x124 | chain health HEALTHY | leakage CLEAN
```

Uniform `checks_json` across all 124 (regime_filter uses the daily cache, so
intraday runs repeat the same classification):

| Layer | Stored value | Status |
|---|---|---|
| 1 regime | RANGE_LV / NO_TRADE | **BLOCKED** |
| 2 capital guard | RISK_AUDIT_PASSED | PASSED |
| 3 technical | CALL, conf 66.0, consensus 4/6 | PASSED |
| 4 options | PCR 0.754, max pain 24400, walls 24500/24300 | MIXED |
| 5 institutional | FII sentiment NEUTRAL | NEUTRAL |
| 6 super-AI ML | NEUTRAL_SIDEWAYS (bullish prob 0.4793) | NEUTRAL |

`confluence_score = 2/6` (capital guard + technical pass; regime, options,
institutional, ML fail/neutral).

## 4. Current driver data (evidence)

- `data/nifty_history.csv` last row 2026-08-13, close 24395.25, age 1.76 h
  (REAL, budget 20 h).
- ADX = 12.7, PDI = 25.1, MDI = 26.1, |PDI−MDI| = 1.0 → **no trend**.
- Bollinger width at 46th percentile → **low vol**.
- `regime_filter.detect_regime` → `RANGE_LV`.
- `REGIME_PROFILE[RANGE_LV].gate = "NO_TRADE"` (documented: "Low-vol chop.
  NO TRADE. Directional options bleed here").
- VIX 11.69 (VIX_CHEAP, 30th pct) — does not override the regime block.
- `data/oi_snapshots/` latest = `NIFTY_2026-08-12.csv` (STALE, 21.6 h).
- `data/india_vix.csv` STALE (21.6 h) — informational only.

## 5. First blocking gate (exact chain)

```
Input: nifty_history.csv daily cache (REAL)
  ↓
Condition (regime_filter.detect_regime): ADX >= 25 AND |PDI-MDI| >= 5
Actual: ADX 12.7 (FAIL) | |PDI-MDI| 1.0 (FAIL)
  ↓
Vol gauge: BB-width percentile >= 60 ?
Actual: 46th percentile -> low vol
  ↓
Result: regime = RANGE_LV
  ↓
REGIME_PROFILE[RANGE_LV].gate = NO_TRADE (regime_filter.trade_plan)
  ↓
precision_signals.generate_precision_signal() Layer 1:
  regime_open = (gate != NO_TRADE) AND (regime != RANGE_LV)
  Actual: gate==NO_TRADE -> regime_open False -> BLOCKED
  ↓
Grade logic (precision_signals.py:215-223):
  directional grade requires checks["regime_layer"]["status"] == "PASSED"
  -> impossible while RANGE_LV
  ↓
signal_action = "STAY_OUT", signal_grade = "NO_SIGNAL (FILTERED OUT NOISE)"
  ↓
ground_truth.GroundTruthDB.record_signal_chain -> _derive_decision
  action STAY_OUT -> decision_type "SKIP", reason "no evaluable signal"
```

## 6. Pipeline trace (STEP 6)

| Stage | File/Function | Output | Blocks? |
|---|---|---|---|
| Market data | `regime_filter._load_nifty_cached` | daily close cache | no |
| Data validation | `truth.asset_freshness_report` | REAL/STALE | no |
| Feature gen | `indicators.add_all_indicators` | ADX/PDI/MDI/BB | no |
| Market state | `regime_filter.trade_plan` | RANGE_LV, gate NO_TRADE | **YES (hard)** |
| Signal engine | `precision_signals.generate_precision_signal` | STAY_OUT (no candidate) | — |
| Candidate gen | (inside signal engine) | **0 directional candidates** | — |
| Confidence | technical layer conf 66.0 (not top-level) | none consumed | no |
| Strategy filters | grade logic: >=4/6 AND regime PASSED | never satisfied | yes (secondary) |
| OI filters | `oi_intel.pcr_and_pain` | PCR 0.754 → MIXED | no (regime blocks first) |
| Regime filters | Layer 1 | BLOCKED | **YES** |
| Risk filters | `capital_guard.full_capital_safety_audit` | APPROVED | no |
| Capital guard | same audit | APPROVED (approves no-trade) | no |
| Final decision | `_derive_decision` | SKIP | — |

## 7. Candidate generation vs rejection (STEP 7)

```
Directional candidates generated:  0
Candidates rejected:               0   (none existed to reject)
Candidates reaching risk layer:    0
Candidates reaching capital guard: 0   (guard runs as a layer, but on a
                                        STAY_OUT posture - 124 APPROVED)
Candidates reaching execution:     0
```

**Case A: no candidate is ever generated.** Not Case B.

## 8. Engine classification (STEP 8)

| Engine | Status | Role |
|---|---|---|
| `precision_signals` | ACTIVE | only candidate generator; always STAY_OUT under RANGE_LV |
| `regime_filter` | ACTIVE | Layer 1 dependency; hard NO_TRADE gate |
| `capital_guard` | ACTIVE | Layer 2; APPROVED on all 124 |
| `market_brain` (technical) | ACTIVE | Layer 3 via `_technical_verdict`; PASSED CALL 4/6 |
| `oi_intel` + `skew` | ACTIVE | Layer 4; MIXED (stale snapshot 12-Aug) |
| `institutional` | ACTIVE | Layer 5; NEUTRAL |
| `super_ai_ml` | ACTIVE | Layer 6; NEUTRAL_SIDEWAYS |
| `smart_strike_selector` | ACTIVE but REACH-ONLY | runs only after a directional action (never) |
| `multi_leg_options` | ACTIVE but REACH-ONLY | defined-risk path only after non-STAY_OUT |
| `auto_paper_runner` / `agent_workflow_graph` / `paper_trader` | ACTIVE but GATED | all STAND_DOWN on STAY_OUT |
| `mtf_alignment`, `volume_analytics`, `var_risk`, `lstm`, `gamma_flip`, `delta_hedging_guard`, `reflection`, `auto_enhancer`, `voice_coach`, `notifications` | ACTIVE report-only | never produce or gate candidates |
| `live_trader_brain` | DORMANT on record path | not wired into the ledger flow |

## 9. Confidence (STEP 9)

- Top-level `confidence` in the signal row: **NULL** — `generate_precision_signal()`
  never emits one; `record_signal_chain` stores `signal_data.get("confidence")`.
- Technical-layer confidence: **66.0** (stored in `checks.technical_layer.confidence`).
- `regime_filter.MIN_CONFIDENCE = 55` sizes trades down — only reached AFTER
  the regime gate; never reached under RANGE_LV.
- No confidence threshold is involved in the STAY_OUT. Confidence is not the
  blocker. Confidence is not treated as a probability (no calibration).

## 10. Market state / regime (STEP 10)

1. Is regime detection running? **Yes** — `regime_filter.trade_plan()` runs as
   Layer 1 on every call; output persisted in `checks_json.regime_layer`.
2. Is it persisted? **Only inside `checks_json`**. The `signals.market_state`
   column is **always NULL** because the signal dict carries no top-level
   `market_state` key (`ground_truth.py` stores `signal_data.get("market_state")`).
3. Is the engine consuming it? **Yes** — `regime_open` is Layer 1.
4. Does a missing `market_state` cause STAY_OUT? **No.** The block comes from
   `regime_layer.status = BLOCKED` inside `checks_json`, not the NULL column.
5. Is it unused? It is used; the column is simply never populated
   (observability gap, not a logic bug).

## 11. OI / options filters (STEP 11)

- OI data available but **stale**: latest snapshot `NIFTY_2026-08-12.csv`
  (21.6 h > 20 h budget). PCR 0.754, max pain 24400, OI walls 24500/24300.
- Options pass rule (`precision_signals.py:172`): `(pcr>1.2 AND CALL) OR
  (pcr<0.8 AND PUT)`. Actual: pcr 0.754 with CALL bias → **MIXED**, no point.
- Liquidity/delta/premium checks of `smart_strike_selector` are never reached
  (no candidate).
- OI filtering is **not** the blocker (regime blocks first), but it keeps the
  confluence score at 2/6.

## 12. Capital guard (STEP 12)

- APPROVE: **124** | REJECT: **0**.
- Blocked by capital guard: **0** of 124.
- **APPROVED ≠ trade approved.** The guard approved the *absence* of a trade
  (STAY_OUT → SKIP is decided before the guard is consulted for REJECT; see
  `_derive_decision`: guard only converts ENTER→REJECT).

## 13. Risk filters (STEP 13)

- Rejections by capital limit / position size / drawdown / daily loss / delta
  guard / exposure / stop-target / missing execution: **0** (no candidate
  reached any of them). All 124 recorded `RISK_AUDIT_PASSED`.

## 14. run_all pipeline (STEP 14)

`run_all.run_complete_suite()` = 23 reporting steps. Produces candidates:
only step 12 (`generate_precision_signal`) — always STAY_OUT. Step 20 re-runs
it for notifications. Steps 13/14/16 (strikes, spreads, GEX) are report-only
and unreachable under STAY_OUT. Steps 8/9 refresh caches. No step places a
trade; execution happens only via `auto_paper_runner` / `agent_workflow_graph`,
both gated on the same STAY_OUT signal → STAND_DOWN.

## 15. Is zero trades expected? (STEP 15)

**EXPECTED.** The market state is genuine low-vol chop (ADX 12.7, |PDI−MDI|
1.0, BB 46th pct). The documented hard rule (AGENTS.md / REGIME_PROFILE) is
RANGE_LV = NO TRADE. The zero-trade outcome follows the documented design
with correct data and correct provenance. This is not a bug and not
suspicious — but see the observability gaps below.

## 16. Main blocker (STEP 16)

1. **REGIME_FILTER** (RANGE_LV → NO_TRADE) — hard, generator-level, first gate.
2. **Confluence threshold** (`>=4/6` AND regime PASSED) — secondary; even if
   the regime opened tomorrow, the current score would be ~3/6 (regime +
   capital guard + technical), still below threshold.
3. **Options layer MIXED** + stale snapshot, FII NEUTRAL, ML NEUTRAL — keep
   the score low.

## 17. What would need to change (STEP 17 — NOT executed)

### If the system is correctly conservative (evidence supports this now)
No change. The system is doing exactly what RANGE_LV mandates. Evidence that
would justify changing: regime flips to TREND_HV/TREND_LV (ADX ≥ 25 and
|PDI−MDI| ≥ 5) and/or RANGE_HV (BB width ≥ 60th pct). At that point real
candidates should flow by themselves.

### Observability fixes (safe, non-strategy)
1. Emit top-level `market_state` (regime) and `confidence` (technical-layer
   66.0) from `generate_precision_signal()` so the ledger columns are
   populated. Expected impact: evaluation/regime reporting works; risk: none
   (pure metadata); validation: existing chain-health + evaluation tests.
2. Refresh today's `oi_snapshots/NIFTY_<date>.csv` during market hours so
   Layer 4 uses a fresh chain. Expected impact: correct PCR/max-pain;
   risk: low; validation: freshness test in `truth.asset_freshness_report`.

### If a future controlled experiment is desired (Phase 6.7+ decision)
The safest candidate is *not* lowering thresholds (that would be loosening a
hard risk rule). It is: **allow RANGE_HV mean-reversion candidates** (gate
`SMALL`, 0.7x size) once the regime actually becomes RANGE_HV — the regime
change is evidence-driven, not threshold-driven. Expected impact: small-size
defined-risk candidates in a genuine high-vol range; risk: medium (mean-rev
in a range still fights theta); validation: paper-only, minimum 20 outcomes
before any evaluation claim, matching the Phase 6 baseline discipline.

## 18. Honesty notes

- Nothing was changed; no trades, predictions, outcomes or synthetic signals
  were created.
- `market_state = NULL` is a persistence gap, not proof of a missing regime.
- Capital Guard APPROVED = the guard approved not trading, not that a trade
  was approved.
- Confidence (66.0) is a rule-based technical consensus, not a calibrated
  probability; it is not the blocker.
- The `A+ GRADE BUY_CALL` text printed by `test_all.py` is a hardcoded
  notification-test fixture (`test_16_notifications_system`), not a real
  signal — the simultaneously recorded ledger signal 133 is STAY_OUT.

## 19. Evidence chain (verifiable)

- Ledger: `data/ground_truth.db` (signals 124, decisions 124, all SKIP).
- Code: `precision_signals.py:101-223` (regime gate + grade logic),
  `regime_filter.py:174-285` (RANGE_LV detection + NO_TRADE),
  `ground_truth.py:592-710` (`record_signal_chain` / `_derive_decision`),
  `capital_guard.py` (APPROVED), `run_all.py`, `auto_paper_runner.py:68-71`,
  `agent_workflow_graph.py:72-123`.
- Data: `data/nifty_history.csv` (ADX 12.7), `data/india_vix.csv` (11.69),
  `data/oi_snapshots/NIFTY_2026-08-12.csv` (PCR 0.754).
- Diagnostic tests: `tests/test_decision_flow_diagnosis.py` (9 tests, all pass).
