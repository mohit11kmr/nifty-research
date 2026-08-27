# HISTORICAL DATA COVERAGE — UNIFIED (DATA-ALIGNMENT-01)

Unified per-session coverage over the canonical calendar
`2024-01-01 → 2026-08-13`. Full machine-readable per-session table:
`data/historical/normalized/alignment_matrix.csv` (956 rows — every calendar
date incl. holidays/weekends; canonical sessions = 646 rows).

## Summary

| layer             | sessions PRESENT | sessions MISSING |
|-------------------|------------------|------------------|
| NIFTY (`nifty_eod_expanded`)    | 646 | 0 |
| OPTIONS_EOD (`options_eod_expanded`) | 646 | 0 |
| VIX (`vix_expanded`)            | 646 | 0 |
| PARTICIPANT_OI (`participant_oi_expanded`) | 646 | 0 |
| EXPIRY (expiry_calendar obs)    | 246 | 400 (derivation window) |

- Core data status (NIFTY + OPTIONS_EOD + VIX + PARTICIPANT_OI):
  **FULL = 646, PARTIAL = 0, INSUFFICIENT = 0**
- 5-layer overall status (includes expiry-calendar observation):
  **FULL = 246, PARTIAL = 400, INSUFFICIENT = 0**
- The 400 PARTIAL sessions have every market-data layer PRESENT; they lack only
  an `expiry_calendar.csv` observation row because that calendar was derived for
  the Phase F window `2025-08-13 → 2026-08-13` only. This is NOT a data gap
  (options EOD for those sessions carries full expiry data). Never hidden: the
  per-layer `expiry` column reports `MISSING` for them explicitly.

## Calendar Structure

- Canonical sessions: **646** (645 weekdays + special Saturday `2025-02-01`)
- Market holidays: **39** (2024: 16, 2025: 13, 2026: 10) — exactly tile the
  weekday gaps against options-EOD evidence (0 orphan weekdays)
- Weekend NO_ARCHIVE: 271 | UNKNOWN: 0

## Special Sessions

| date        | NIFTY | OPTIONS_EOD | VIX | PARTICIPANT_OI | EXPIRY | OVERALL |
|-------------|-------|-------------|-----|----------------|--------|---------|
| 2025-02-01  | P     | P           | P   | P              | — (pre-window) | PARTIAL (data FULL) |
| 2026-08-11  | P     | P           | P   | P              | P (→2026-08-18) | FULL |

Both were backfilled from NSE archives (`ind_close_all` / `fao_participant_oi`,
sha256-verified). Underlying validation for both: 0.00% deviation.

## Per-Layer Notes

- NIFTY / VIX: derived from NSE `ind_close_all` raw files (646/646 sessions).
- OPTIONS_EOD: NSE UDiFF FO bhavcopy, 1,060,622 normalized rows (646/646).
- PARTICIPANT_OI: NSE `fao_participant_oi` (646/646 × 5 client buckets = 3,230).
- EXPIRY: `expiry_calendar.csv` 246 observation dates (2025-08-13 → 2026-08-13);
  includes `2026-08-11`.

## Coverage Matrix (per-session status counts)

`data/historical/normalized/coverage_matrix.csv` — regenerated from the
canonical calendar; now **FULL for all 646 sessions** (previously never FULL:
Yahoo-derived day list + wrong raw-filename slices for VIX/participant OI
silently dropped those layers).
