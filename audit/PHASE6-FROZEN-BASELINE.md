# Phase 6.1 — Frozen Baseline

> **IMMUTABLE REFERENCE POINT.** This file is frozen on 2026-08-13. Do not edit.
> Future experiments MUST compare against this exact baseline (baseline_id).
> A new baseline is created only when the evaluation snapshot changes
> (new ledger records, new signal/prediction versions, or rule changes).

## Identity

| field | value |
|---|---|
| baseline_id | `phase6-baseline-2026-08-13-3678c7f0` |
| report_version | `phase6-evaluation-v1` |
| git_commit | `cf132caeb7e8e17a2f316cd45a48f0c88e7cc703` (branch `master`) |
| database_sha256 | `3678c7f07cdaac032d282c5d27ec048e67fbff63e4e961a26164c9a341891d68` |
| reproducibility_hash | `61767dc213d20cf10ac51002a3ac8c05a00d514167fcec3f6e5e9710e1780007` |
| frozen_at | 2026-08-13 13:51:37 IST |
| evaluation tool | `phase6_pipeline.py` / `EvaluationEngine.evaluation_report()` |

## Dataset definition

| field | value |
|---|---|
| evaluation cohort | `REAL_FRESH` ONLY (eligible_count=87) |
| excluded cohorts | LEGACY=0, SIMULATED=0, REAL_STALE=0, UNKNOWN=0 |
| date range | 2026-08-13 12:45:59 IST -> 2026-08-13 13:44:18 IST (intraday) |
| signal family | `precision_signal` (6-layer confluence, version `d571203c6549`) |
| feature version | `d571203c6549` |
| parameter version | `None` (not supplied at record time) |
| decision rule | capital guard + SKIP on no-signal |
| execution mode | `PAPER` |
| cost assumptions | none (no executions recorded; fees/slippage = null) |

## Frozen metrics (OBSERVED / DERIVED)

| layer | metric | value | sufficiency |
|---|---|---|---|
| counts | signals | 87 | ADEQUATE (n=87 >= 20) |
| counts | predictions | 0 | INSUFFICIENT_SAMPLE |
| counts | decisions | 87 | ADEQUATE (n=87 >= 20) |
| counts | executions | 0 | INSUFFICIENT_SAMPLE |
| counts | positions | 0 | INSUFFICIENT_SAMPLE |
| counts | outcomes | 0 | INSUFFICIENT_SAMPLE |
| counts | evaluations | 0 | INSUFFICIENT_SAMPLE |
| signal | directional claims | 0 (all 87 STAY_OUT) | n/a |
| signal | hit rate / FPR / FNR | null | no directional outcome |
| prediction | accuracy | null | INSUFFICIENT_SAMPLE |
| decision | skip rate | 1.0 (87/87) | ADEQUATE |
| decision | acceptance rate | 0.0 | ADEQUATE |
| decision | capital guard states | APPROVED: 87 | ADEQUATE |
| execution | slippage / fees / fills | null | INSUFFICIENT_SAMPLE |
| outcome | win rate / avg P&L / MFE / MAE | null | INSUFFICIENT_SAMPLE |
| confidence | calibration status | INSUFFICIENT_DATA | 0 bands populated |
| regime | market states seen | UNKNOWN (all NULL) | ADEQUATE n but no claim |
| failure | classified failures | 0 (87 healthy/no-trade) | n/a |
| leakage | clean | True (0 issues) | n/a |
| reproducibility | byte-identical on re-run | True | n/a |

## Interpretation rule applied

- Only metrics with ADEQUATE sample may support empirical performance claims.
- Every gated metric above is reported as `null` / INSUFFICIENT_SAMPLE and is
  **not** used for any performance conclusion.
- No confidence value is treated as a calibrated probability.

## Limitations

1. Zero directional predictions / trades / outcomes exist at freeze time. The
   baseline proves ledger integrity and measurement readiness, not edge.
2. All 87 signals are STAY_OUT no-signal records; market_state is NULL for all
   (no regime attribute was stored at record time) - regime analysis is empty.
3. Execution quality, outcome, MFE/MAE and calibration cannot be measured yet.
4. Costs are unknown until real PAPER executions are recorded.

## Freeze rule

- This baseline is a MEASUREMENT REFERENCE, not a target.
- No parameter, threshold, or strategy was tuned to produce it.
- Do not modify this file after freezing.
