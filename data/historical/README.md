# Historical research dataset (Phase F)

Point-in-time options data for the frozen backtest replay window
**2025-08-13 -> 2026-08-13**, collected from NSE's public FO bhavcopy archive.

## Files
- `fo_raw/NIFTY_<date>.csv` — raw NIFTY option rows from the daily bhavcopy
  (`BhavCopy_NSE_FO_0_0_0_<date>_F_0000.csv.zip`), full original schema.
- `manifest.json` — per-day fetch record: source URL, zip sha256, row counts,
  expiries, strike range, underlying spot, status.
- `coverage.csv` — per-day per-layer availability matrix (nifty/vix/ml/fii/
  options).

## Source & provenance
- URL pattern: `https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip`
- EOD file published by NSE after market close. Manifest stores the zip sha256
  for every day so each snapshot is verifiable against the source.
- The bhavcopy `UndrlygPric` matches `data/nifty_history.csv` close to
  <0.001% on all 246 days (cross-source validation, `tests/
  test_historical_collector.py`).

## Consumers
The frozen backtest (`backtest_frozen.py`) globs `data/oi_snapshots/NIFTY_*.csv`
and uses the latest dated `<= day t`. The collector writes frozen-schema
snapshots for every window trading day, so the replay now has real options data
for the whole window — no code change to the frozen strategy.

## Resolution & honest limitations
The bhavcopy is **EOD (close-marked)** data — the correct mark for the frozen
day-level replay, but NOT intraday chain data. It has **no bid/ask depth and no
IV**. In the generated snapshots:
- `ce_iv` / `pe_iv` → NaN (skew layer honestly returns NEUTRAL)
- `ce_buy_qty` / `ce_sell_qty` / `pe_buy_qty` / `pe_sell_qty` → NaN (no depth)
- `ce_ltp` / `pe_ltp` → official `ClsPric` (EOD mark)
- `ce_pct_chg` → NaN (not part of bhavcopy)

Existing live intraday captures (`NIFTY_2026-08-08/11/12/13.csv`) are **never
overwritten** — the collector skips dates that already have a snapshot file
(`snapshot_skipped_existing` in manifest).

## Known data characteristics
- **Weekly expiry weekday shifts over the window**: NIFTY weeklies were
  Thursday in Aug-2025 and became Tuesday later in the window (SEBI expiry
  move). The frozen replay squares off on `next_thursday` regardless — a model
  simplification, documented in `backtest_frozen.py`.
- **2026-08-11** is a genuine trading day whose bhavcopy exists, but it is
  missing from `data/nifty_history.csv` (pre-existing Phase-E noted gap). The
  bhavcopy entry is in the manifest for data completeness; the frozen replay
  iterates index dates only, so it does not evaluate this day.
- **2026-08-08** is a Saturday (not a trading day) — no bhavcopy exists.

## Coverage summary (246 rows)
- nifty: 245/246, vix: 245/246, ml: 245/246 (2026-08-11 absent from index caches)
- fii_dii: 60/246 — the free mirror hard-caps at the most recent 60 sessions;
  NSE stopped publishing daily FII/DII cash in 2018 and its participant-OI
  archive URLs are not public. This is a structural gap; the institutional
  layer returns NO_DATA/NEUTRAL for the rest of the window.
- options: 246/246 with snapshots available.
