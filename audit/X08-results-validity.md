# X08 — Results Validity Audit (X-Ray)

> X-Ray phase 8. Built 2026-08-13. Which platform claims/artifacts are backed by
> real evidence vs fabricated/deterministic/stale. Every item traced to source.

---

## 1. Claimed vs actual — headline numbers

| Claim | Where | Reality | Verdict |
|---|---|---|---|
| Premium-seller **72.5% win / PF 2.6** | premium_seller.py backtest, daily_report | Computed with **25 qty/lot vs platform 75**; gate VIX 16–25 + not-TREND_HV | MISLEADING (unit mismatch) |
| market_brain reliabilities **"~70%"** / "TRAINED RULES" | market_brain.py:135,170-175 | Hardcoded literals (RANGE 0.49/TRENDING 0.46/VOLATILE 0.55/TRANSITION 0.46); trainer measured **42.8% hit-rate (n=194)** | OVERSTATED + FROZEN |
| **51% vs 52% baseline** (ML, no edge) | AGENTS.md, ml_engine, super_ai_ml | Consistent with walk-forward; genuinely reported edge-vs-baseline | HONEST (correctly demoted) |
| LSTM "recurrent network" 0.6 bullish prob | lstm_neural_engine | Deterministic `mean(linspace(0.8,1.2))·0.52+0.08` = 0.60 every call | FABRICATED (theater) |
| VaR stress tests "PASSED" | var_risk_manager | Formulaic `capital × drop × 0.5` at fixed 0.5Δ; never simulated | FORMULAIC (always passes) |
| Monte Carlo survival "PASSED" | monte_carlo | 10,000×100 sims, WR 0.55, win/loss 1.8, **fixed seed 42** → deterministic | DETERMINISTIC (no evidence value) |
| auto_enhancer "weights/limits updated for tomorrow" | auto_enhancer.py:42, enhancement_log.json | adaptive_weights no-op (no outcomes) + read-only audits; **nothing mutated** | FALSE SUCCESS CLAIM |
| "46-year ULTRA_ROBUST" | long_term_backtest | Verdict string hardcoded | FABRICATED |
| Rebalance lift | portfolio_rebalance → data/rebalance_test.json | Diversified-no-rebalance 0.9805, monthly/weekly 0.9986 — lift negligible, flat/negative | HONEST (no edge found) |
| reflection hypotheses | reflection_hypotheses.jsonl | **7 identical entries** generated from empty account ("WR 0.0% across 0 trades") | INVALID input (no data) |
| adaptive_weights state | data/adaptive_weights.json | rsi 0.2, supertrend/pcr/skew 3.0 — pinned at clamp bounds; **nothing reads it** | DECORATIVE |
| Training report | results/training_report.md | Real walk-forward score of rule brain: **42.8%**, n=194 | REAL but below coin-flip |

## 2. results/ artifacts inventory

| Artifact | Producer | Contents | Trust |
|---|---|---|---|
| `strategy_research.md`, `research_results.csv` | main.py (grid) | strategy grid + OOS (last 40%) metrics | Real backtests, fixed cost model |
| `market_report.md` | main.py | market snapshot report | Real data |
| `systematic_dashboard.md` | systematic_report (run_all 22) | regime/VIX/PCR/walls/global/headlines | Real data |
| `predictions_log.csv`, `training_report.md` | trainer.py | rule-brain walk-forward, 42.8% | Real (no live impact) |
| `live_predictions.csv` | ? | prediction snapshots | see below |
| `deep_research_iv_skew_2026-08-12.md` | deep-research (web + research.db) | skew/microstructure study | Real; dated, do-not-re-run |
| `web_cues.json` | web_research | news cues | Cached |

## 3. Data-cache staleness (affects validity of anything reading them)

- `data/ml_features.csv` **Aug 8** vs `data/nifty_history.csv` **Aug 13** →
  ml_engine / super_ai_ml silently train on a 5-day-stale feature file.
- `data/tf_scan.csv` cached — TF edge in daily_report reflects the cache date.
- `data/oi_snapshots/*.csv` dated — gamma_flip (run_all 16) reads the latest;
  on no-data returns None (honest).

## 4. Backtest validity profile

- **Cost model**: BS premium, slippage 1.5%, ₹40/trade — reasonable but never
  validated against live fills (no live order path to compare).
- **Walk-forward**: genuine only in `ml_engine.walk_forward_eval` + trainer;
  `strategies`/`main.py` grid is a brute-force sweep with a fixed 40% OOS
  hold-out (no walk-forward).
- **No shuffling** (time-series discipline held).
- **Multi-leg PoP** uses live LTP + BS greeks → the most evidence-grounded path.

## 5. Live-path validity (what actually reaches a "signal")

1. Regime gate: real data (VIX percentile, HV gauge) — honest.
2. Precision A+ grade: **depends on hardcoded 80% Layer-3 consensus and
   "100% Risk Compliant" capital layer** → the A+ confidence label is not fully
   evidence-derived (H1).
3. Strike/SL/TGT: Δ from live chain IV (honest) × rules 1.5×ATR SL, 1:2 RRR.
4. ML layer 6: real model, context-only by policy, stale feature cache.

## 6. Verdict on platform numbers

- **Tradeable evidence**: skew/microstructure deep-research; multi-leg PoP;
  regime/VIX gates; oi_intel z-scores — real and reproducible.
- **Do NOT quote as edge**: premium_seller 72.5%/PF2.6 (lot 25),
  market_brain ~70% (frozen constants vs 42.8% measurement), Monte Carlo
  "PASSED" (seed 42), VaR stress "PASSED" (formulaic), LSTM 0.60, "ULTRA_ROBUST".
- **Actively misleading runtime claims**: auto_enhancer "success", M1 fake-live
  spot/vix fallback in precision_signals, live_ticker_service hardcoded fallback.

## 7. Recommendation (unchanged, consolidated)

1. Fix H1/M1 so A+ confidence is derived from real inputs (kill hardcoded L3
   and capital-layer fabrication) — otherwise the paper-trade trail
   (`signal_history`) records fake-confidence entries and poisons future
   calibration.
2. Recompute premium_seller with **75 qty/lot** before quoting again.
3. Rebuild `ml_features.csv` before any ML run; add a freshness check.
4. Replace seed-42 Monte Carlo and formulaic VaR stress with parameter
   uncertainty / scenario sampling, or relabel as illustrative.
5. Delete or relabel the theater: lstm display, auto_enhancer verdict,
   "ULTRA_ROBUST", market_brain "TRAINED RULES" comments.
