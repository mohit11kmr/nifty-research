# X02 — Data Layer Audit (X-Ray)

> X-Ray phase 2. Built 2026-08-13. Focus: acquisition → cache → persistence,
> freshness, honesty discipline, governance.

---

## 1. Acquisition paths (4 live-data paths — flagged tech debt)

| Path | Technology | Writer | Cadence |
|---|---|---|---|
| NSE option tick stream | official WS `streamer.nseindia.com/streams/fo/mbp` | `live_feed.py`, `tick_recorder.py` | market hours only; auto-reconnect; stops 15:30 IST |
| NSE live chain | v3 encrypted API via Playwright browser | `nse_live.fetch_option_chain_live` | per call / snapshot refresh |
| Yahoo spot/VIX/stocks | yfinance | `live_market_fetch`, `live_ticker_service`, `build_data` | 30s / per tick / freshness-gated |
| FII/DII | free mirror API | `institutional.fetch_fii_dii_history` | freshness 6h |

Gotchas: NSE blocks plain `requests` → must run in-browser. Old
`wss://webstream.nseindia.com` is DEAD (DNS gone). Yahoo intraday caps:
15m/30m ≤60d, 60m ≤90d, 1d ≤730d.

## 2. research.db (live research DB, `data/research.db`)

Writer `tick_recorder.py` — WAL + `synchronous=NORMAL`, batch insert every 200
rows or 5s, daily retention purge (default keep 30 days), indexes on `recv_ts`.

| Table | Purpose | Volume |
|---|---|---|
| `ticks` | per-strike CE/PE quotes (ltp/bid/ask/oi/iv/volume) every stream update | 1.21M rows, 191 MB |
| `spot` | index spot sampled every 60s (Yahoo ^NSEI 1m) | small |

Critical facts:
- **IV column is always NULL** (NSE streamer doesn't send IV) → skew work must
  reconstruct IV via BS Newton/bisection from mid. Documented in AGENTS.md.
- **Unbounded growth + full-table scans**: `date(recv_ts)` defeats the index on
  `recv_ts`; `/api/ticks` and `/api/chain` scan the whole table per request (H3).
- No migrations; schema inline in writer.
- Staleness trap: `data/ml_features.csv` (Aug 8) predates `nifty_history.csv`
  (Aug 13) — `ml_engine` / `super_ai_ml` silently train on the stale cache.

## 3. historical_audit.db (audit trail, `data/historical_audit.db`)

Writer `history_logger.py` — append-only; WAL; single persistent thread-safe
connection (this was remediated from the first-pass M5/M7 double-connection issue).

| Table | Columns | Status |
|---|---|---|
| `tick_history` | id, timestamp, spot_price, vix, pcr, max_pain | **actively written** (live_market_fetch, live_ticker_service) |
| `signal_history` | id, timestamp, action, grade, confluence_score, spot_price, recommended_strike, sl_points, target_points | **actively written** (run_all step 12) |
| `paper_trade_journal` | id, timestamp, position_id, side, option_type, strike, entry_price, exit_price, pnl, status | **DORMANT — created, counted in summary, never INSERTed** |

CSV mirrors: `data/tick_history.csv`, `data/signal_history.csv` (best-effort).

`log_market_tick` derives VIX/PCR/max-pain from `regime_filter.vix_snapshot` +
`oi_intel.pcr_and_pain` — never fabricated (honesty discipline holds here).

## 4. Cache layer freshness rules

`build_data.py`: refresh any file older than 20h (FII/DII: 6h); `--fresh` forces;
`--skip-oi` skips chain snapshot.

| Cache | Source | Notes |
|---|---|---|
| `data/nifty_history.csv` | Yahoo ^NSEI daily | live-patched by `live_market_fetch.update_live_market_cache()` |
| `data/india_vix.csv` | Yahoo ^INDIAVIX | ~1yr, feeds regime premium side + expected move |
| `data/fii_dii_history.csv` | mirror API | ~60 sessions |
| `data/stocks/<SYM>.csv` | Yahoo | Nifty-50 universe |
| `data/oi_snapshots/oi_NIFTY_<date>.{json,csv}` | NSE v3 (browser) | dated; `oi_NIFTY_live.json` for live dash |
| `data/tf_scan.csv` | multitf | strategy grid per TF |
| `data/sectors/*.csv` | yfinance ETF else equal-weight basket | equity_quant |

`live_market_fetch.fetch_live_market_spot()` returns `LIVE_MARKET_TICK` or
`UNAVAILABLE` — **never fabricated**; falls back to last research.db spot row.

## 5. Honesty discipline — verified violations & clean spots

| Component | Behavior |
|---|---|
| `live_market_fetch` | Honest: `UNAVAILABLE` on failure, no fabrication |
| `history_logger` | Honest: real VIX/PCR/max-pain context, never fabricated |
| `precision_signals` Layer 3 | **FABRICATES**: hardcoded 80% consensus (H1) |
| `capital_guard` capital layer | **FABRICATES**: always "100% Risk Compliant" (H1) |
| `precision_signals` fallback | hardcoded `spot=24500.0`/`vix=12.0` reported as live (M1) |
| `live_ticker_service` | hardcoded fallback `spot=24403.10`/`vix=12.0` on exception (flaw) |
| `volume_profile` | if `volume` column missing → `np.random.randint(1000,5000)` fabricated volume |
| `volatility_forecaster` | <10 samples → `np.random.seed(42); normal(0,0.0025,50)` synthetic returns |
| `smart_strike_selector` (run_all step 13) | `spot_price=24403.10` hardcoded literal |

## 6. Data governance findings (carried from first-pass audit)

- **H4**: `historical_audit.db`, `paper_account.json`, runtime pid files are
  git-tracked; financial paper records live in repo history.
- **M10**: no backups of research.db / historical_audit.db / paper_account.json.
- **M9**: `requests 2.31.0` known CVE-2024-35195 (fixed 2.32.0).
- **Triple-storage**: overlapping data in SQLite + CSV + JSON with no single
  source of truth.
- `enhancement_log.json` and `adaptive_weights.json` are overwritten per run
  (not append) — state that nothing consumes.
- `backup_data.py` copies `adaptive_weights.json` / `enhancement_log.json` into
  backup dir — treats decorative state as if it mattered.

## 7. Data-risk register (priority order)

1. **Staleness-as-correctness** (M1/H1/M5): fabricated/fallback values look live.
2. **Unbounded DB** (H3): multi-GB growth, full-table-scan dashboard.
3. **No backups** (M10/H4): only copies of audit trail + paper account are live + git.
4. **Cache staleness** (`ml_features.csv` vs `nifty_history.csv` date gap).
5. **Concurrent writers**: cron + daemon + dash write same artifacts, no file locks
   (M8); SQLite single-writer contention (M7).
