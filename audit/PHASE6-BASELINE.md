# Phase 6 — Baseline (frozen reference point)

# Phase 6 — phase6-evaluation-v1

- Generated: 2026-08-13 13:36:13 IST (read-only, from a `mode=ro` facade - the ledger was never modified)
- Source: `data/ground_truth.db` (sha256 `1cc7cb60233b46f4…`)
- Report data is **OBSERVED** from the Ground Truth ledger. Derived aggregates are labeled DERIVED.
  Missing values stay missing (`null`); nothing is estimated or invented.
- Cohort rule: only `REAL_FRESH` records are eligible for empirical performance claims.


## Baseline definition (DERIVED)

| field | value |
|---|---|
| report version | `phase6-evaluation-v1` |
| evaluation window | all recorded chain records in `data/ground_truth.db` (append-only) |
| cohort | REAL_FRESH only (eligible_count=47) |
| signal family | `precision_signal` (6-layer confluence) |
| decision rule | capital_guard + SKIP on no-signal |
| execution mode | PAPER (when trades occur) |
| costs | none recorded yet (execution fees/slippage `null`) |
| db sha256 | `1cc7cb60233b46f4…` |

## Determinism / reproducibility

- `verify_reproducibility(engine)` -> same frozen inputs produce identical
  report JSON (SHA-256 equal). Covered by `test_reproducibility_identical_reports`.
- Any report regeneration against the same DB snapshot is byte-identical.

## This baseline is a MEASUREMENT REFERENCE, not a target.

The goal is a trustworthy point to compare future changes against. No parameter,
threshold, or strategy was tuned to produce it.
