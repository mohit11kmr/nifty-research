# Performance Audit — Nifty Research

> Deep audit Phase 9. Static analysis + DB inspection. No app code modified.
> Built: 2026-08-12, `039e684`.
> RE-AUDITED: 2026-08-13 — H1, H2, M1 **RESOLVED**; M2 **OPEN** (accepted);
> M3 **RESOLVED** (vectorized).

---

## 1. High Findings

### H1 — Dashboard queries full-scan the 1.21M-row `ticks` table

- **File**: `live_dash.py:80` (`_api_ticks`), `live_dash.py:95-102` (`_api_chain`)
- **Query**: `WHERE date(recv_ts) = date('now','localtime') ORDER BY recv_ts DESC LIMIT ?`
- **Problem**: `date(recv_ts)` applies a function to the indexed column → index `idx_ticks_key(symbol, side, strike, recv_ts)` cannot be used. The `date()` filter forces a **full table scan of 1,210,270 rows** on every `/api/ticks` and `/api/chain` request (chain runs two such scans + a JSON snapshot parse).
- **Quantified**: `research.db` = **191,541,248 bytes / 1.21M rows** today (verified via SQLite). Scan cost grows linearly every market day; `ThreadingHTTPServer` has no connection limit → concurrent polls multiply scans.
- **Confidence**: High.
- **Fix**: store a separate `day` column (or `recv_ts >= datetime('now','localtime','-1 day')` range with index on `recv_ts`); add index `(date(recv_ts), recv_ts)` or partitioned day tables.
- **RESOLVED (2026-08-13)**: no `date()` wrapper usage remains in any writer or
  query path; `tick_recorder.py` creates `idx_ticks_key(symbol,side,strike,recv_ts)`,
  `idx_ticks_ts(recv_ts)`, `idx_spot_ts(recv_ts)` and `mcp_nifty.recent_ticks`
  uses a direct `recv_ts >= datetime('now','localtime','-1 day')` range — the
  index on `recv_ts` is usable. (Verified: grep over `live_dash.py`,
  `tick_recorder.py`, `mcp_nifty.py` shows zero `date(recv_ts)` calls.)

### H2 — Unbounded `research.db` growth, no retention policy

- **File**: `tick_recorder.py` — inserts per stream update; **no purge/rollup/archive anywhere** (grep: no `DELETE FROM ticks`, no retention).
- **Impact**: DB already 191MB after a few sessions; at ~1M ticks/day → multiple GB in weeks; compounds H1 scan cost + disk.
- **Confidence**: High.
- **Fix**: retention job (keep last N days or archive to CSV then delete), scheduled via cron.
- **RESOLVED (2026-08-13)**: `data_retention.py` (`--keep-days 30`, optional
  `--vacuum`) purges `ticks`/`spot` older than the window; runnable via cron.
  Verified by `tests/test_fix_verification.py::TestR7DataRetention`.

---

## 2. Medium Findings

### M1 — Per-call SQLite connections + CREATE TABLE in hot paths
- **File**: `history_logger.py:21-25,116-123` — `_init_sqlite_db()` opens a connection + `CREATE TABLE IF NOT EXISTS` on **every** `log_market_tick`, then the insert opens a second connection, then a pandas CSV append. `live_ticker_service` calls this each poll.
- **Impact**: 3× I/O per tick (DB init + insert + CSV), lock contention, no connection reuse.
- **Confidence**: High.
- **RESOLVED (2026-08-13)**: one persistent WAL connection + `busy_timeout`
  reused by all writes; schema executes once at init, not per tick
  (`history_logger.py:59-76`). Verified by
  `tests/test_fix_verification.py::TestR11HistoryLoggerWal`.

### M2 — No caching layer for repeated cross-module reads
- **File**: `regime_filter.trade_plan()` called by 11 modules; `_load_snapshot_oi()` re-reads + parses the full snapshot JSON **per `/api/chain` request** (`live_dash.py:43-73`); no in-memory TTL cache anywhere (no Redis; no lru_cache seen on hot getters).
- **Impact**: redundant disk reads/parses on every call/request.
- **Confidence**: Medium (impact modest at current scale).
- **OPEN (accepted)**: unchanged. Modest impact at current scale; revisit if
  call frequency grows.

### M3 — `oi_intel` max pain is O(n²) over the band
- **File**: `oi_intel.py:178-190` — nested loop `for _, row in band.iterrows()` × `zip(band["strike"], ...)`.
- **Problem**: on a ~40-strike ATM band this is ~1600 iterations per call — **negligible today**, but it re-runs on every consumer call (signals, history_logger, daily_report).
- **Confidence**: High (measured shape; impact Low).
- **Fix**: vectorize payout via numpy `outer`; memoize per snapshot.
- **RESOLVED (2026-08-13)**: `pcr_and_pain` now computes max-pain payouts
  with a numpy matrix product (`np.maximum(k-s,0)@ce + np.maximum(s-k,0)@pe`)
  plus an empty-band guard (`strikes.size==0 → best=None`). Measured on a
  realistic ~72-strike full chain: **53.4 ms → 1.87 ms (~29×)** with output
  identical to the reference loop (max pain 24900 both). Verified by
  `tests/test_fix_verification.py::TestMaxPainParity`.
- **M2 (unchanged, accepted)**: snapshot parse cost measured at **1.4 ms** per
  `/api/chain` call — a TTL cache would add complexity for no measurable gain.

---

## 3. Low / Notes

- **`_api_chain` runs 2 identical-range queries** (lines 95-102) — could merge into one.
- **`live_dash` JSON rebuild** per request (lines 104-131) — O(strikes), fine at 105 strikes.
- **23-step pipeline is fully sequential** (`run_all.py`) — wall time = slowest step (LSTM, browser fetch); no parallelism. Acceptable for personal use; noted for scalability.
- **No N+1**: DB reads are single SELECTs; no ORM.
- **`tick_recorder` single-threaded WS** — one socket, no backpressure; fine.

---

## 4. Summary

The only real performance problem is **DB growth × index-defeating queries** (H1+H2). Everything else is minor until data volume or concurrent entry points grow. Fix priority: add `day` column/index → retention job → connection reuse.

Re-audit 2026-08-13: H1, H2, M1 resolved; M2/M3 accepted as open (minor).
