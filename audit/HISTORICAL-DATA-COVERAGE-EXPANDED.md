# HISTORICAL DATA COVERAGE — EXPANDED (2024-01-01 → 2026-08-13)

**Status: COMPLETE for options EOD; VIX + participant OI aligned except 2 days
(see gaps). Nothing wired into strategy/backtest yet.**

This is the data-coverage picture across every dataset in the expanded
`data/historical/` deep archive, after the OPTIONS EOD DEEP ARCHIVE phase.

## Dataset-by-dataset coverage

| Dataset | File | Rows | Horizon | SHA-256 (manifest) | Source |
|---|---|---|---|---|---|
| NIFTY options EOD | `normalized/options_eod_expanded.csv` | **1,060,622** | 2024-01-01 → 2026-08-13 (646 days) | `a1183fd2…` | NSE UDiFF FO bhavcopy |
| India VIX EOD | `normalized/vix_expanded.csv` | 644 | 2024-01-01 → 2026-08-13 | `b8dceb27…` | NSE `ind_close_all` |
| Participant OI | `normalized/participant_oi_expanded.csv` | 3,220 (644 × 5 clients) | 2024-01-01 → 2026-08-13 | `c65c07f6…` | NSE `fao_participant_oi` |

Legacy (pre-expansion) caches that remain in use by production/backtests and
are **untouched**: `data/nifty_history.csv`, `data/india_vix.csv`,
`data/fii_dii_history.csv`, `data/oi_snapshots/`, `data/historical/fo_raw/`.

## Trading-day accounting (2024-01-01 → 2026-08-13)

| Layer | Days covered |
|---|---|
| Weekday sessions computed by `trading_days()` | 655 |
| Options EOD raw files (official NSE) | **646** |
| Market holidays, recorded `MISSING_ARCHIVE` | 11 |
| Genuine sessions **absent from the weekday calendar** | 2 (`2025-02-01` special Saturday; `2026-08-11` Yahoo hole) |

Per-day status is machine-readable:
- `manifests/options_eod/coverage.json` (646 days, `OK:n` per day)
- `manifests/bhavcopy.json` (per-day raw_sha256 / MISSING_ARCHIVE)
- `manifests/vix.json`, `manifests/participant_oi.json` (per-day raw_sha256 / MISSING)
- `normalized/coverage_matrix.csv` (per-day layer matrix)

## Data-quality summary

| Check | Options EOD | VIX | Participant OI |
|---|---|---|---|
| Underlying/price cross-check vs official NSE | PASS (±0.000002%) | — (VIX self-consistent, REAL) | — (client totals match row sums, 5 clients/day) |
| Duplicate contract keys | 0 | 0 | 0 |
| Conflicts | 0 | n/a | n/a |
| Quarantined rows | 0 | 0 | 0 |
| Missing days explicitly marked | 11 (holidays) | 11 (holidays) + 2 calendar-excluded | 11 (holidays) + 2 calendar-excluded |
| Provenance / quality | REAL / A | REAL / A | REAL / A |

## Gaps (honest)

1. **VIX + participant OI missing 2 genuine sessions** that options EOD has:
   `2025-02-01` (special budget Saturday) and `2026-08-11` (real session absent
   from `data/nifty_history.csv`, which drives `trading_days()`). Options EOD
   carries both because it reused the Phase F archive, which covered the frozen
   window directly.
2. **Options EOD horizon = UDiFF availability floor.** UDiFF archives begin at
   2024-01-01 (probed 2019–2023 → 404); no deeper history exists on the official
   free feed.
3. **No IV / bid-ask depth** in UDiFF (EOD settlement data only) — IV
   reconstruction and microstructure belong to later analytics phases, not this
   archive.

## Isolation

All expanded datasets live under `data/historical/` and are consumed by
nothing in production. `ground_truth.db`, `paper_account.json`, `research.db`,
`oi_snapshots/`, strategies, and live/paper trading were not written by any
collector (test-verified). Frozen raw files (`fo_raw/`) were read-only inputs.

## Next safe phase

**DATA ALIGNMENT / REVIEW** — backfill `2025-02-01` + `2026-08-11` into VIX and
participant OI (drive the day list from the options-EOD archive / NSE holiday
calendar instead of Yahoo-derived `trading_days()`), then read-only review.
No `regime_filter` / Strategy Creator / backtest wiring until frozen.
