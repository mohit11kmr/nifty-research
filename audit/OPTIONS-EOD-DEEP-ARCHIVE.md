# OPTIONS EOD DEEP ARCHIVE — official NSE/UDiFF

**Status: COMPLETE (frozen; not wired into strategy/backtest yet)**

Full-depth NIFTY index-option EOD archive from the official NSE archive feed
(UDiFF `BhavCopy_NSE_FO_*_F_0000.csv.zip`), extended to the full expanded
horizon. Data-acquisition only: nothing in this archive is consumed by
`regime_filter`, Strategy Creator, `backtest_frozen`, `multi_strategy_backtest`
or paper/live trading.

## Coverage

| Metric | Value |
|---|---|
| Horizon | **2024-01-01 → 2026-08-13** (target met; UDiFF begins at 2024-01-01 — probed 2019–2023, all 404) |
| Trading days with data | 646 |
| Raw files archived | 646 (400 downloaded 2024→2025-08-12 + **246 reused from Phase F `fo_raw/`, zero re-download**) |
| Market holidays (explicitly MISSING_ARCHIVE) | 11 |
| Normalized rows | **1,060,622** |
| CE rows | 525,133 |
| PE rows | 535,489 |
| Unique expiry dates | 167 (range 2024-01-04 … 2031-06-24) |
| OI > 0 rows | 739,986 |
| Volume > 0 rows | 608,554 |
| Lot sizes observed | 75 / 65 / 50 / 25 (SEBI lot-size timeline) |
| Quarantined rows | **0** |
| Conflicts (dup key, differing values) | **0** |
| Duplicate contract rows removed | **0** |

## Sources

- **Primary:** `https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{YYYYMMDD}_F_0000.csv.zip` (official NSE FO bhavcopy, UDiFF schema).
- No Angel One, no paid data, no simulated/estimated rows. Provenance `REAL`, quality `A` on every row.
- Underlying-price cross-check reference: official NSE `ind_close_all_<DDMMYYYY>.csv` (primary) + `data/nifty_history.csv` (fallback).

## Raw archive (immutable)

- Location: `data/historical/raw/bhavcopy/NIFTY_<date>.csv` — verbatim NIFTY/IDO
  rows extracted from the official zip, exactly as downloaded (frozen-window
  files reused from `data/historical/fo_raw/`, byte-copied, never modified in place).
- Per-day SHA-256: `data/historical/manifests/bhavcopy.json` →
  `days[<date>].raw_sha256` (zip hash recorded as `zip_sha256` for downloaded days;
  `reused_from: phase_f_fo_raw` marks the 246 reused days).
- Resumable/idempotent: a day is re-downloaded only when its raw file is missing
  or its hash no longer matches the manifest (`collect --kind bhavcopy-backfill`).
- Frozen window archived by `collect --kind frozen-reuse` (copies existing Phase F
  raw files — no network traffic).

## Normalized schema

`data/historical/normalized/options_eod_expanded.csv`
(canonical `OPTIONS_EOD_COLS`, extended with `underlying_price` + `lot_size`):

`date, underlying, instrument_type, expiry, strike, option_type, open, high,
low, close, settle_price, underlying_price, volume, turnover, oi, oi_chg,
lot_size, source, source_url, retrieved_at, raw_file_hash, availability_time,
provenance, quality`

- `oi_chg` is the **signed** daily change in OI (legitimately negative rows are
  normal — not quarantined).
- One row per contract per day: key `(date, expiry, strike, option_type)`.
- 2024-era and 2025+ UDiFF column aliases both handled
  (`OpnPric/HghPric/LwPric/ClsPric/SttlmPric` vs `HighPric/LowPric/SetlPric`).

## Data quality pipeline (`normalize_bhavcopy`)

1. Per-day parse → validate (`expiry`, `strike>0`, `option_type ∈ {CE,PE}`, all
   numeric fields ≥ 0 except signed `oi_chg`).
2. Invalid rows → **quarantined** with per-row reason
   (`data/historical/quarantine/options_eod_quarantine.csv`), never silently dropped.
3. Conflict detection on the full dataset: same key with differing values →
   quarantined as `conflict_duplicate_key` and counted.
4. Exact duplicate keys → collapsed (counted).
5. Per-day coverage manifest + quality report written to
   `data/historical/manifests/options_eod/`.

**Quality report** (`data/historical/manifests/options_eod/quality_report.json`):
rows, CE/PE, unique expiries, trading days, duplicates removed, conflicts
quarantined, quarantine breakdown, OI/volume coverage, underlying cross-check.

## Validation results

| Check | Result |
|---|---|
| Underlying price vs official NSE close (645/646 days, ±0.000002% max) | **PASS** |
| Expiry > trade date | PASS (0 violations) |
| No duplicate contract keys | PASS |
| Only CE/PE | PASS |
| No negative OI / volume / prices | PASS |
| Checksum (manifest sha256 == file sha256) | **PASS** `a1183fd2bd0ca892…` |
| Idempotent re-normalization (data-stable; only `retrieved_at` metadata moves) | **PASS** |
| Provenance / quality vocab | PASS (REAL/A only) |
| Production data untouched | **YES** (see isolation) |

## Missing days (explicit, never fabricated)

11 market holidays, all recorded `MISSING_ARCHIVE` in the manifest:
2024-01-22, 2024-01-26, 2024-03-08, 2024-03-25, 2024-03-29, 2024-04-11,
2024-04-17, 2024-05-01, 2024-05-20, 2024-06-17, 2024-07-17. The frozen window
(2025-08-13 → 2026-08-13) had **zero** missing days.

Two **genuine trading days** are archived that the weekday-only calendar omits:
- `2025-02-01` — special Saturday budget session (NSE bhavcopy exists).
- `2026-08-11` — real session (Phase F captured it) that `data/nifty_history.csv`
  (Yahoo) is missing, so `trading_days()` treats it as a holiday.

## Isolation (no production writes)

- Writes confined to `data/historical/raw|normalized|quarantine|manifests/`.
- Never touches: `ground_truth.db`, `paper_account.json`, `research.db`,
  `data/oi_snapshots/`, `strategies/*`, live trading, Angel One trading endpoints.
- `cmd_audit`/`cmd_validate`/`cmd_coverage` are read-only over those datasets.
- Verified by `tests/test_deep_options_archive.py::TestNoProductionWrites`.

## Tests

`tests/test_deep_options_archive.py` — 29 tests, all pass:

- 2024 UDiFF parsing (prices/OI/volume/expiry/strike/underlying/lot)
- 2025 format alias compatibility (`HighPric/LowPric/SetlPric`)
- CE/PE, expiry, strike, price, OI, signed OI-chg, volume, turnover
- malformed-row quarantine with reasons (negative price, bad option type, missing strike)
- duplicate detection + conflict detection on the contract key
- raw-file SHA256 vs manifest (sample days across 2024/2025/2026)
- normalized dataset invariants (schema, horizon, no dup keys, no negatives,
  expiry>date, manifest-hash match)
- idempotent re-run (data-stable)
- no production writes (write ops never reference production paths)

## Largest remaining gap

- The two genuine sessions absent from the **other** expanded datasets
  (VIX / participant OI): `2025-02-01` and `2026-08-11`, because
  `trading_days()` derives from `data/nifty_history.csv` (Yahoo), which omits
  the special Saturday and has a hole on 2026-08-11. Options EOD itself has no gap.
- Row-level IV is not present in UDiFF (honest `NEUTRAL` skew as in Phase F);
  IV reconstruction belongs to a later analytics phase.

## Next safe phase

**DATA ALIGNMENT / REVIEW** — align VIX + participant-OI to the full options-EOD
calendar (backfill 2025-02-01 + 2026-08-11 into those two datasets), then a
read-only sanity review. No strategy/backtest wiring until that is frozen.
