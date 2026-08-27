# DATA-ALIGNMENT-01 — Unified Trading Calendar + Cross-Dataset Alignment + Research Dataset Freeze

## Canonical Calendar

One authoritative historical session calendar now exists:

- Path: `data/historical/normalized/trading_calendar_expanded.csv`
- Coverage: `2024-01-01 → 2026-08-13` (956 calendar days)
- Calendar hash (SHA256 of sorted TRADING_SESSION rows): `54965462e130df5491c919bc53d9bac681f3f88b711a0abdfd7da8084a593dcf`

Status distribution:

| session_status    | count | meaning                                             |
|-------------------|-------|-----------------------------------------------------|
| TRADING_SESSION   | 646   | NSE FO bhavcopy exists (market open)                |
| MARKET_HOLIDAY    | 39    | on official NSE holiday list, no session            |
| NO_ARCHIVE        | 271   | weekend, scheduled closure (incl. non-special Sat)  |
| UNKNOWN           | 0     | unverifiable weekday                                |

Internal consistency: 684 weekdays in window = 645 weekday sessions + 39 holidays
(exact tiling, zero orphan weekdays). 646 = 645 weekdays + the special Saturday
`2025-02-01`.

## Source Priority

1. **NSE options EOD evidence** — `raw/bhavcopy/NIFTY_<date>.csv` proves a
   session existed (market open). Primary authority.
2. **NSE official holiday list** — 39 market holidays (2024: 16, 2025: 13,
   2026: 10) embedded as `NSE_HOLIDAYS` in `collect_historical_data_deep.py`,
   verified against NSE press releases. Used to classify weekday gaps.
3. **Weekday/weekend schedule** — only to classify `NO_ARCHIVE`; never to
   override evidence.

Yahoo/`nifty_history.csv` is NEVER authoritative. It was the root cause of both
mismatches (below).

## 2025-02-01 (Saturday — Budget Day)

- **Was the market open? YES.** Options EOD raw exists
  (`raw/bhavcopy/NIFTY_2025-02-01.csv`, 1,038 NIFTY option rows), and NSE
  archived `ind_close_all_01022025.csv` + `fao_participant_oi_01022025.csv`
  (both HTTP 200, sha256-verified).
- **Datasets containing it before this phase:** options EOD, `nifty_history`
  (Yahoo had the session).
- **Datasets lacking it before this phase:** VIX, participant OI. Reason: both
  collectors derived their day list from `trading_days()` which skips all
  Saturdays — the Saturday session was never even probed.
- **Action:** backfilled both from NSE archives (REAL, quality A).
  - VIX: open 16.2475 / high 16.58 / low 14.0125 / close 14.10
  - participant OI: 5 client buckets, 35.6M total contracts
  - NIFTY (from `ind_close_all`): close 23,482.15 — matches options
    `UndrlygPric` median exactly (0.0% dev)

## 2026-08-11 (Tuesday — Yahoo Gap)

- **Was the market open? YES.** Options EOD raw exists
  (`raw/bhavcopy/NIFTY_2026-08-11.csv`), NSE archived both `ind_close_all_11082026.csv`
  and `fao_participant_oi_11082026.csv`.
- **Datasets containing it before this phase:** options EOD, expiry calendar
  (`2026-08-11 → 2026-08-18` expiry).
- **Datasets lacking it before this phase:** `nifty_history` (Yahoo omitted the
  day), VIX, participant OI. Reason: a source-calendar hole in Yahoo — the day
  is absent from the production `nifty_history.csv`, so `trading_days()` never
  emitted it and the collectors never probed NSE.
- **Action:** backfilled VIX + participant OI from NSE archives; canonical
  NIFTY EOD built from `ind_close_all` (close 24,471.70 — 0.0% dev from options
  `UndrlygPric`). Production `data/nifty_history.csv` was NOT modified; its gap
  is documented in the unified manifest (`production_cache.nifty_history`).

## Dataset Alignment

Per-session status for all 646 canonical TRADING_SESSION dates:
`data/historical/normalized/alignment_matrix.csv` (956 rows incl. non-sessions).

| dataset                 | PRESENT | MISSING |
|-------------------------|---------|---------|
| NIFTY (`nifty_eod_expanded`) | 646 | 0 |
| OPTIONS EOD (`options_eod_expanded`) | 646 | 0 |
| VIX (`vix_expanded`)     | 646 | 0 |
| PARTICIPANT OI (`participant_oi_expanded`) | 646 | 0 |
| EXPIRY calendar (obs dates) | 246 | 400 (derivation window) |

After backfill every canonical session is present in all four market datasets.
The 400 "missing" expiry rows are NOT dataset gaps — `expiry_calendar.csv` was
scoped to the Phase F window `2025-08-13 → 2026-08-13`; sessions before that
window (including `2025-02-01`) legitimately have no expiry-calendar
observation record. `2026-08-11` IS present (expiry `2026-08-18`).

## Missing Data

- None in the four market datasets for canonical sessions (after backfill).
- `data/nifty_history.csv` (production Yahoo cache) is missing 150 canonical
  sessions (149 pre-2024-08-12 + `2026-08-11`). NOT modified — research should
  use `nifty_eod_expanded.csv`.
- Expiry-calendar observation rows for 400 pre-Phase-F sessions (documented
  above, not a data gap).
- No interpolation, forward-fill, or inference was used anywhere.

## Cross-Dataset Validation

- Date alignment: all four datasets cover exactly the 646 canonical sessions.
- Timezone: all calendar dates are naive (UTC-midnight style) `YYYY-MM-DD`,
  no tz-mixed values.
- Underlying validation: median options `UndrlygPric` vs official NSE Nifty 50
  close (`ind_close_all`), all 646 sessions checked.
  - max deviation: **0.00%**, median: **0.00%**, days > 0.5%: **0**
  - both special sessions match exactly.
- VIX and NIFTY date sets identical (646 = 646).

## Coverage

`coverage_matrix.csv` (regenerated from the canonical calendar) now reports
**FULL for all 646 sessions** — previously the matrix never showed FULL because
(1) it derived dates from the Yahoo day list, and (2) it used wrong filename
slices for VIX (`[16:26]` on `ind_close_all_<date>.csv`, correct `[14:24]`) and
participant OI (`[22:32]`, correct `[19:29]`), so those layers silently never
matched. The corrected slices live in `build_alignment_matrix()` and
`cmd_coverage()`.

## Dataset Hashes

Stable content hashes (deterministic, exclude volatile `retrieved_at`):

| dataset | stable hash |
|---------|-------------|
| options_eod_expanded | `1aab93e4ba55b0a1c7ee7080abd08d49ad7a79a45ddbd7b21de977b3b78621e6` |
| vix_expanded | `c688cedbb956682ae6c242ef08d3a5c10269d4be1bc3fc0013139238430736cd` |
| participant_oi_expanded | `c2683b64e963a229c5ac4f625fa52fc6416a64158cb98db2855df572e5a91106` |
| nifty_eod_expanded | `8abdeb7b3166635d9ff23517d0f7b7199d15000f761e1c2239905e8deec5acb7` |
| expiry_calendar | `3abbe4ccb003d9f9228d9bdfaf73041403dae5ed4a43f30e223bc9fc6b426ad2` |

File SHA256 of each normalized CSV and the production-cache SHA256 are recorded
in `unified_research_dataset.json` (`*_sha256` / `production_cache`).

## Reproducibility

`collect_historical_data_deep.py calendar` + `align` run twice produced:
- identical calendar hash (`5496...dcf`)
- identical stable content hashes
- identical alignment classifications
- identical `missing_dataset_days`
Only `created_at` differs (documented timestamp), per the phase spec.

## Idempotency

Second run: new downloads = 0 (all 646 raw files hashed OK), duplicate raw
files = 0, normalized stats identical, stable hashes identical. Backfilled
manifest entries were re-used by hash match (`collect_vix`/`collect_participant_oi`
skip `OK` days whose `raw_sha256` matches).

## Production Isolation

- `data/nifty_history.csv` — NOT modified (SHA256 unchanged, gap documented).
- `data/ground_truth.db`, `paper_account.json`, `oi_snapshots`, `research.db` —
  untouched; collector writes confined to `data/historical/`.
- No strategy, regime, risk, or backtest code touched (`tests` verify no
  forbidden write paths are referenced).

## Limitations

- `expiry_calendar.csv` covers only the Phase F window; pre-2025-08-13
  sessions have no expiry-observation record (options data itself carries
  expiries for every session).
- Production `nifty_history.csv` retains its Yahoo gap; consumers must switch
  to `nifty_eod_expanded.csv` for research.
- `trading_days()` (Yahoo-derived helper) is retained for legacy collectors;
  new/authoritative logic uses `canonical_calendar()`. A future phase may
  re-point legacy collectors at the canonical calendar.
- Weekend sessions other than `2025-02-01` would be classified `NO_ARCHIVE` by
  schedule; only options-EOD evidence can upgrade them (none exist).

## Frozen Manifest

- Path: `data/historical/manifests/unified_research_dataset.json`
- Schema version: `1.0`
- `trading_sessions = 646`, `market_holidays = 39`
- All dataset paths + hashes above; `missing_dataset_days` all empty
  (`nifty`, `options_eod`, `vix`, `participant_oi`).
- Future research should reference this manifest and its exact hashes rather
  than rediscovering files ad hoc.
