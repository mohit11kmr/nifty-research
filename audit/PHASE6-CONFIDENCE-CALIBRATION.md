# Phase 6 — Confidence Calibration

# Phase 6 — phase6-evaluation-v1

- Generated: 2026-08-13 13:36:13 IST (read-only, from a `mode=ro` facade - the ledger was never modified)
- Source: `data/ground_truth.db` (sha256 `1cc7cb60233b46f4…`)
- Report data is **OBSERVED** from the Ground Truth ledger. Derived aggregates are labeled DERIVED.
  Missing values stay missing (`null`); nothing is estimated or invented.
- Cohort rule: only `REAL_FRESH` records are eligible for empirical performance claims.


## Status: INSUFFICIENT_DATA

- Bands populated: 0
- No prediction rows exist yet, so no confidence-vs-outcome comparison is possible.

Per-band metrics (sample size, observed success rate, average/median outcome,
failure rate) will be computed automatically once evaluated predictions exist.
No confidence value is currently treated as a calibrated probability - the
report labels this state honestly as `INSUFFICIENT_DATA`.
