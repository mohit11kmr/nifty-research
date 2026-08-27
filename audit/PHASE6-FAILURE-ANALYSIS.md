# Phase 6 — Failure Analysis

# Phase 6 — phase6-evaluation-v1

- Generated: 2026-08-13 13:36:13 IST (read-only, from a `mode=ro` facade - the ledger was never modified)
- Source: `data/ground_truth.db` (sha256 `1cc7cb60233b46f4…`)
- Report data is **OBSERVED** from the Ground Truth ledger. Derived aggregates are labeled DERIVED.
  Missing values stay missing (`null`); nothing is estimated or invented.
- Cohort rule: only `REAL_FRESH` records are eligible for empirical performance claims.


## Result (OBSERVED + DERIVED)

- classified failures: 0
- healthy / no-trade chains: 47
- most common category: None (no failures to classify)
- by_category: {}

All 47 recorded chains are healthy `STAY_OUT` chains (observation ->
snapshot -> signal -> decision=SKIP, timestamps monotonic, no leakage). There are
no `DATA_ERROR` / `FEATURE_ERROR` / `SIGNAL_ERROR` / `REGIME_ERROR` / `MODEL_ERROR` /
`RISK_ERROR` / `EXECUTION_ERROR` / `TIMING_ERROR` rows to report.

Evidence-based rule: nothing is classified UNKNOWN by default; rows with no
failure evidence are simply not counted as failures. As trades are recorded, this
report will populate without code changes (the taxonomy is already wired end to end).
