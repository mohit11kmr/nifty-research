# Nifty Research — Architecture Audit

> Purpose: architecture + code-organization review. **Mapping only — koi fix/app code change nahi.**
> Built: 2026-08-12. Head commit: `039e684`. Source: import-graph analysis (AST) over 90 .py files + file inspection.

---

## 1. Architecture Summary

Flat, procedurally-organized Python research toolset: ~30 independent "engine"
modules (analysis) + ~16 entry points (MCP server, HTTP dashboards, daemons,
CLI) + shared data layer (`data/` files, two SQLite DBs). No framework, no
ORM, no service/repository layer. Modules communicate **indirectly through
shared files/DBs** (data-shared architecture), not through function calls.

**Import graph**: 90 files, **0 circular dependencies** (first-level SCC clean).
Two de-facto shared core libraries — `regime_filter` (fan-in 11) and
`capital_guard` (fan-in 11) — plus `indicators` (fan-in 12, pure leaf).
`run_all.py` is the dominant hub (fan-out 26).

**The central pattern**: every entry point composes engines in a linear,
try/except-per-step pipeline (`run_all.py` being the archetype). Engines
re-read the same `data/` artifacts independently. This yields simple,
survivable, restart-friendly code — but at the cost of duplicated data-access
logic and weak orchestration semantics.

**Strong points**: acyclic module graph, small focused engines, honest data
fallbacks (post `039e684`), read-only MCP boundary, no automated order path.

---

## 2. Major Architectural Problems

### P1. `run_all.py` — god orchestrator, hard-coded 23-step linear pipeline
- **File**: `run_all.py:36` `run_complete_suite()` — fan-out **26** local imports.
- **Problem**: single 250-line function runs 23 engines in fixed sequence, each
  in its own `try/except` that prints and continues. Steps cannot be
  skipped/reordered/parallelized/retried without editing code. Engine failures
  leave dependent steps running against stale/absent data (each engine
  re-fetches independently).
- **Impact**: adding an engine = editing the file; a mid-pipeline crash produces
  a half-report with no failure semantics; no shared state between steps →
  each step re-discovers spot/chain (redundant I/O, stale-mix risk).
- **Confidence**: High.
- **Recommendation**: step registry (declarative list of `(name, callable,
  deps)`) with shared context dict + skip-on-missing-dependency + summary.

### P2. No single data-access layer — snapshot/spot logic duplicated in 15+ modules
- **File (evidence)**: `mcp_nifty.py` (`_latest_chain_csv`, `_latest_chain_spot`,
  `_spot_fallback`, `_current_spot`), `live_dash.py` (`_load_snapshot_oi`,
  `_api_spot`), `regime_filter.trade_plan()` (called by 11 modules as a spot
  source), `live_market_fetch._last_real_spot()`, plus 15 modules independently
  read `data/oi_snapshots/` (grep list: oi_intel, precision_signals,
  smart_strike_selector, multi_leg_options, anti_spoofing, history_logger,
  alert_monitor, mcp_nifty, live_dash, web_dashboard, systematic_report,
  run_all, build_data, main, oi_refresh).
- **Problem**: every consumer re-implements "load freshest chain / current spot"
  with slightly different staleness rules and fallbacks. No repository/service
  owns "latest market state".
- **Impact**: inconsistent data (stale chain vs live spot mixed in one report);
  bug fixes to snapshot loading must be repeated per module (already happened —
  max-pain formula fixed twice, see P4).
- **Confidence**: High.
- **Recommendation**: one `market_state.py` service exposing `get_spot()`,
  `get_latest_chain()`, `get_vix()`, `get_pcr()`, with TTL + explicit staleness
  flag; delete per-module readers.

### P3. Conflicting, parallel "live data" ingestion paths
- **File (evidence)**: `live_market_fetch.py` (yfinance), `live_ticker_service.py`
  (yfinance), `live_feed.py` (NSE streamer WS), `tick_recorder.py` (NSE streamer
  WS + Yahoo spot), `nse_live.py`/`oi_refresh.py` (Playwright chain).
- **Problem**: 4 independent live-market fetchers exist; `live_market_fetch` and
  `live_ticker_service` do nearly the same yfinance job. Which one is
  authoritative is implicit.
- **Impact**: divergent spot values between pipelines; duplicated code; a bug
  fixed in one path silently persists in the other.
- **Confidence**: High.
- **Recommendation**: pick one ingestion stream (NSE WS via `live_feed`/`tick_recorder`)
  as canonical; demote yfinance to cold-start fallback.

### P4. Duplicated business logic — max pain / PCR computed twice (history of dual-bug)
- **File**: `oi_intel.py:165` `pcr_and_pain()` **and** `data_fetcher.py:186`
  `compute_chain_metrics()`.
- **Dependency path**: `daily_report`/`build_data` → `oi_intel`; `main` → `data_fetcher`.
- **Problem**: both implement PCR + max-pain independently. AGENTS.md explicitly
  records "both had the swapped-formula + argmax bug; keep them in sync."
- **Impact**: confirmed divergence history; any future change must be applied
  twice or the two report paths disagree on the same metric.
- **Confidence**: High.
- **Recommendation**: single `chain_metrics()` in `oi_intel`; `data_fetcher`
  delegates or is removed from that path.

### P5. `.env` loaded only in `angel_one_client.py` — hidden import-order dependency
- **File**: `angel_one_client.py:19-27` manual `.env` parser (no `python-dotenv`).
  `telegram_notifier.py:11-12` and `notifications_system.py` read
  `os.environ.get("TELEGRAM_BOT_TOKEN")` directly.
- **Dependency path**: `run_all` → `notifications_system` (no `angel_one_client`
  import) ⇒ Telegram env vars unset unless `angel_one_client` happened to be
  imported earlier in the process.
- **Problem**: config loading is duplicated and order-dependent. One process
  (run_all) silently can't notify; another (mcp_nifty, which imports
  angel_one_client) can — same .env file.
- **Impact**: silent alert drops; inconsistent behavior across entry points.
- **Confidence**: High (confirmed: no dotenv in requirements.txt; only
  angel_one_client parses .env).
- **Recommendation**: central `config.py` loaded once at process start; all
  modules read from it; add `python-dotenv`.

---

## 3. Dependency Problems

- **D1. Entry points re-implement orchestration (4+ parallel orchestrators).**
  `run_all.run_complete_suite()`, `control_center` (imports run_all + quant_daemon
  + auto_enhancer + paper_trader + history_logger + precision_signals +
  live_ticker_service), `quant_daemon` (imports auto_enhancer + auto_paper_runner
  + live_market_fetch), `hermes_agent` (imports run_all + voice_coach +
  precision_signals + capital_guard). Overlapping pipeline logic in four places;
  a change to "what a full run is" must be mirrored. *Confidence: High.*

- **D2. Wrong-direction dependency — fetcher depends on report modules.**
  `live_ticker_service.py` imports `history_logger` + `web_dashboard` (report
  generation) for a streaming-data task → the "live data" layer drags in the
  presentation layer. *Confidence: High.*

- **D3. `regime_filter` doubles as spot/data source.** 11 modules call
  `regime_filter.trade_plan()` for "current close" (e.g.
  `agent_workflow_graph._real_spot()`). A business gate library also owns live
  spot access — hidden coupling; callers get I/O (network/cache) inside what
  looks like pure computation. *Confidence: Medium-High.*

- **D4. MCP hub touches broker client.** `mcp_nifty.py` imports
  `angel_one_client` (broker creds) even though all 15 tools are read-only —
  the agent-facing boundary is coupled to broker auth. *Confidence: High.*

- **D5. `agent.py` vs `agent_workflow_graph.py`.** Two modules both self-describe
  as "the agent": `agent.py` (full-stack analysis bot, fan-out 8) vs
  `agent_workflow_graph.py` (6-node execution graph). Overlapping vocabulary,
  different concerns, no shared naming or abstraction → misuse risk.
  *Confidence: High.*

---

## 4. Coupling Problems

- **C1. `run_all` fan-out 26 / `test_all` fan-out 19** — both are hubs importing
  almost every engine. Any engine signature change ripples to both. *High.*
- **C2. Data-shared coupling (implicit)**: engines are decoupled in code but
  coupled through `data/` file + DB conventions (same CSV names, same `oi_*`
  JSON schema). Changing a cache schema breaks every silent consumer; nothing
  validates these contracts. *High.*
- **C3. Fan-in hotspots as implicit services**: `regime_filter` (11), `capital_guard`
  (11), `indicators` (12) — effectively services with no stable API boundary;
  small signature changes affect 11 call sites. `indicators` is a clean leaf;
  the other two carry I/O side effects. *Medium-High.*
- **C4. Three trade-recording surfaces**: `paper_trader.py` (paper_account.json +
  paper_trade_journal), `history_logger.py` (tick_history + signal_history),
  `trade_journal.py` (analysis only). Ownership of "the audit trail" is split
  across modules with no single journal owner. *Medium.*

---

## 5. Scalability Risks

- **S1. Single-machine, single-process, no queue.** All pipelines are
  synchronous; the 23-step run is bound by the slowest step (LSTM, live stream,
  browser fetches). No parallelism, no backpressure. Acceptable for a personal
  tool; breaks if market breadth (more symbols) or concurrent entry points grow.
- **S2. SQLite write contention.** `tick_recorder` batch-commits to
  `research.db` while `live_dash`/`lob_microstructure` read the same file;
  `historical_audit.db` written by `history_logger`/`paper_trader`. Growing tick
  volume will hit SQLite write locks (WAL not configured). *Medium.*
- **S3. Browser-driven NSE fetch (Playwright) is the bottleneck & fragility
  point** — every `oi_refresh` cycle spins a browser; concurrent entry points
  (dashboards + run_all) can double-fetch. No lock/token to serialize.
  *Medium.*
- **S4. Cron + daemon overlap**: crontab runs `hermes_agent pre/post-market`
  while `quant_daemon` and `oi_refresh` may run concurrently → same artifacts
  written by multiple processes (snapshot files, logs). No file-lock
  discipline. *Medium.*

---

## 6. Maintainability Risks

- **M1. 86 files at repo root, flat namespace.** No `engines/`, `data/`,
  `reporting/`, `api/` package separation. Naming collisions latent
  (`agent.py`/`agent_workflow_graph.py`, `report.py`/`daily_report.py`/
  `systematic_report.py`). *High.*
- **M2. Four report generators share `results/` + `blog/` namespaces**
  (`report.py`, `daily_report.py`, `systematic_report.py`, `blog_post.py`)
  with overlapping HTML/markdown assembly — inconsistent output conventions.
  *Medium-High.*
- **M3. Two test strategies coexist**: monolithic `test_all.py` (19 imports,
  integration-style) + focused `tests/` unittest dir. Coverage/locality of a new
  engine's tests is ambiguous; `test_all` is itself a maintenance hub.
  *Medium.*
- **M4. No lock files / no pinned CI parity**: requirements.txt unpinned;
  Docker (slim 3.11) vs CI (3.11/3.12) vs local venv (3.12) can drift. *Medium.*
- **M5. Duplicated `.env`/config handling** (see P5) + env-parsing logic buried
  inside a broker module. *High.*

---

## 7. Technical Debt

- **T1. Duplicated max-pain/PCR logic** (P4) — known dual-bug history.
- **T2. Per-module snapshot readers** (P2) — 15 re-implementations of "read
  latest chain".
- **T3. Duplicated live-spot fetchers** (P3) — two yfinance variants + WS paths.
- **T4. `run_all`'s sequential try/except sprawl** — no step metadata, no
  status object; the "✅ ALL 23 ENGINES EXECUTED" banner hides partial failure.
- **T5. `_real_spot`/`_spot_fallback`/`_current_spot`/`_last_real_spot` family**
  — 4+ hand-rolled "current spot" helpers with different stale/fallback rules
  (mcp_nifty, live_dash, live_market_fetch, agent_workflow_graph).
- **T6. Inline SQL + schema ownership scattered** — `tick_recorder` owns
  `research.db`, `history_logger`/`paper_trader` own `historical_audit.db`;
  `CREATE TABLE` lives in writers, no migrations.

---

## 8. Positive Architectural Decisions

- **Acyclic module graph** — 0 circular dependencies across 90 files; engines
  are pure-ish, import trees shallow.
- **Data-shared architecture fits the domain** — engines are cache-friendly,
  restartable, independently testable; matches the "no wasted API calls"
  philosophy.
- **Read-only MCP boundary** — 15 tools, no mutation of state/orders; broker
  order API not wired into automation.
- **Honest-fallback pattern post-`039e684`** — `STAND_DOWN`/`UNAVAILABLE`/
  `NO_DATA` instead of fabricated values; audit rows carry real vix/pcr/max_pain.
- **Localhost-only web surfaces** (live_dash 127.0.0.1:8766; web_dashboard) —
  no public attack surface.
- **Small focused engines** — `gamma_flip`, `anti_spoofing`, `dynamic_trailing`,
  etc. each ~1 responsibility, low coupling to siblings.
- **PID-managed daemon** (`quant_daemon.py`) — clean restart semantics.
- **Structured audit trail** (`historical_audit.db` tables) separated from live
  research DB — good separation of concerns at storage level.

---

## 9. Recommended Improvements

Prioritized (impact × effort):

1. **Extract `market_state` service** (P2/T2/T5): `get_spot()`, `get_chain()`,
   `get_vix()`, `get_pcr()` with TTL + staleness flag. Kills 15 duplicate
   readers + 4 spot helpers. *Highest leverage.*
2. **Declarative pipeline** for `run_all`/`quant_daemon`/`hermes` (P1/D1):
   shared step registry + context; stops the 4 parallel orchestrators from
   drifting.
3. **Central `config.py` + `python-dotenv`** (P5/M5): one `.env` load at
   process start; remove manual parser from `angel_one_client`.
4. **Single `chain_metrics()` owner** (P4/T1): delete `data_fetcher` duplicate.
5. **Package split** (M1): `engines/`, `data/`, `reporting/`, `api/` — at least
   `reporting` to absorb the 4 generators.
6. **Serialize artifact writers** (S3/S4): single writer per snapshot file;
   file-lock or ownership table for `oi_NIFTY_live.json` and audit DBs.
7. **Enable SQLite WAL** for `research.db` (S2) + configurable auto-checkpoint.
8. **Decouple fetchers from reporters** (D2): `live_ticker_service` should emit
   to `research.db`/queue, not import `web_dashboard`.
9. **Move `angel_one_client` behind a broker interface** used by mcp_nifty only
   for status (D4) — keep read tools broker-free.

---

## 10. Unknowns

- Whether `live_feed.py` vs `tick_recorder.py` duplication is intentional
  (one is the documented NSE WS; tick_recorder is the DB recorder) — runtime
  wiring of both not exercised in this audit.
- Which of the 4+ orchestrators is the "real" production entry (cron uses
  `hermes_agent`; daemon is `quant_daemon`; README points at `run_all`).
- Reachability/dead-code status of `timing.py`, `stock_flow.py`, `blog_post.py`
  (blog/ not inspected for content freshness).
- Whether `multi_agent_swarm.py` and `agent_workflow_graph.py` overlap in
  production or are used in different entry points.
- Real runtime contention between cron/daemon/oi_refresh was not observed
  (audit is static + import-graph only).
- Whether `research.db` grows unbounded (tick retention/cleanup policy not
  found).

---

## Verification Notes

- Import graph built with AST (`/tmp/opencode/arch_analyze.py`) over 90 .py
  files; cycles via DFS (0 found). Fan-in/fan-out from first-level local
  imports. No application files modified; only `audit/` artifacts created.
