# Nifty Research — Project Map (Reconnaissance)

> Purpose: accurate, factual map of the codebase — kaunsa module kya karta hai.
> Note: sirf map hai — secure/insecure ka claim nahi. Built: 2026-08-12.
> Head commit: `039e684` (working tree clean).

---

## 1. Technology Inventory

| Layer | Stack |
|---|---|
| Language | Python 3.11/3.12 (CI matrix) |
| Data | pandas, numpy, scipy |
| ML | scikit-learn, xgboost, lightgbm, optuna, ta |
| Market data | yfinance, websocket-client, smartapi-python, pyotp (Angel One), Playwright (NSE chain via browser) |
| MCP | `mcp>=1.8.0,<2.0.0` |
| TTS | pyttsx3, gTTS |
| HTTP | stdlib `http.server`/`ThreadingHTTPServer` (no Flask/FastAPI) |
| DB | SQLite via stdlib `sqlite3` (no ORM — raw SQL) |
| Cache | no Redis/memcached — filesystem `data/` caches + in-memory pandas only |
| Queues | none (no Celery/RQ/RabbitMQ) |
| Workers | long-running daemon processes (`quant_daemon.py`, `oi_refresh.py`, `tick_recorder.py`, `live_ticker_service.py`) |
| Cron | system crontab (3 entries, see §4) — runs system python3.12, not `.venv` |
| Webhooks | none |
| Frontend | static `live_dash.html` + HTML served by `web_dashboard.py` (no SPA/framework/JS build) |
| Broker | Angel One SmartAPI |
| Infra | Dockerfile (`python:3.11-slim`), docker-compose, GitHub Actions CI, MIT License |

Deps: `requirements.txt` (single file, no lock file). Venv: `.venv/` (project-local).

---

## 2. Repository Structure

```
nifty-research/
├── *.py                     # 86 root-level Python files (91 total incl. tests/)
├── tests/                   # unittest suites: test_greeks.py, test_multi_leg.py, test_smart_strike.py
├── data/                    # caches, DBs, JSON state (gitignored)
├── results/                 # generated reports (markdown/csv/json)
├── logs/                    # dated log dirs (2026-08-11, 2026-08-12)
├── audit/                   # THIS directory (project maps, audit outputs)
├── live_dash.html           # static frontend for live_dash.py API
├── experiments/             # one-off experiments (e.g. strike_selector_upgrade_experiment.py)
├── .github/workflows/ci.yml # CI
├── README.md, USER_GUIDE.md, OWNER_INSTRUCTIONS.md, MASTER_PROMPT.md, option_trader_guide.md
├── AGENTS.md                # research-backed strategy matrix (owner-mandated)
├── opencode.json            # OpenCode config: skills + MCP servers (nifty-trader, git-nifty)
├── requirements.txt, Dockerfile, docker-compose.yml, .env.example, LICENSE
```

### data/ (runtime state)
- `research.db` — live ticks, spot, pattern logs
- `historical_audit.db` — tick_history (spot/vix/pcr/max_pain), signal_history, paper_trade_journal
- `oi_snapshots/` — NSE chain snapshots (`oi_NIFTY_live.json` overwritten each cycle)
- `nifty_history.csv`, `india_vix.csv`, `tick_history.csv`, `fii_dii_history.csv`, `ml_features.csv`, `tf_scan.csv`, `signal_history.csv`
- `stocks/`, `sectors/` — yfinance cache trees
- `longterm_BSESN.csv`, `longterm_GSPC.csv` — long-term index history
- JSON state: `adaptive_weights.json`, `angel_scrip_master.json`, `paper_account.json`, `rebalance_test.json`, `reflection_hypotheses.jsonl`, `enhancement_log.json`
- PID/log files: `quant_daemon.pid`, `*.log` (alert_monitor, cron, hermes, live_dash, oi_refresh, quant_daemon, tick_recorder)

---

## 3. Architecture Overview

- **Entry**: multiple standalone entry points (MCP server, HTTP dashboard, daemon, CLI, agent) — sab read/write common `data/`.
- **Data layer**: NSE chain via Playwright (`nse_live.py`), Angel One WebSocket ticks (`tick_recorder.py`), Yahoo cache (`data_fetcher.py`/`equity_quant.py`).
- **Analysis engines** (independent modules, ~30): regime filter, MTF alignment, volume analytics, OI intel, greeks/multi-leg pricing, precision signals, gamma flip, LOB microstructure, SMC, ML ensemble, sentiment, institutional flow, skew, VAR.
- **Orchestration**: `run_all.py` (23-step pipeline), `agent_workflow_graph.py` (LangGraph-style), `multi_agent_swarm.py` (voting), `quant_daemon.py` (PID daemon).
- **Protection**: `capital_guard.py` (kill-switch/event risk), `premium_seller.py` (defined-risk), `paper_trader.py` (paper journal).
- **Presentation**: `web_dashboard.py` (HTML), `live_dash.py` (JSON API), `report.py`/`daily_report.py` (markdown), `blog_post.py`.
- **Interface**: `mcp_nifty.py` — stdio MCP server (13 read-only tools) for the agent layer.

---

## 4. Entry Points

| File | Role |
|---|---|
| `mcp_nifty.py` | stdio MCP server, 13 read-only market/chain/OI tools — primary agent interface |
| `live_dash.py` | HTTP `127.0.0.1:8766`, endpoints `/api/spot`, `/api/ticks`, `/api/chain` |
| `web_dashboard.py` | HTML dashboard (browser UI, broker status) |
| `run_all.py` | 23-step full pipeline orchestrator |
| `main.py` | CLI: fetch-data / research / report / all |
| `control_center.py` | interactive CLI menu |
| `quant_daemon.py` | PID-managed background daemon |
| `hermes_agent.py` | scheduled research & execution agent (runs system commands) |
| `alert_monitor.py` | polling alert loop (OI walls/levels) |
| `oi_refresh.py` | periodic NSE chain refetch into `oi_NIFTY_live.json` |
| `tick_recorder.py` | records live ticks + spot into `research.db` |
| `live_ticker_service.py` | 5-second market streaming service |
| `auto_paper_runner.py` | automated paper-trade runner (stand-down gated) |
| `build_data.py` | fetch/cache data first, then analysis (owner rule) |
| `report.py`, `daily_report.py`, `systematic_report.py`, `blog_post.py` | report generators |
| `test_all.py`, `tests/` | test suites |

### Scheduled entry points (system crontab, user `mohit`)
- `30 16 * * 1-5` → `build_data.py` (logs to `data/cron.log`)
- `45 08 * * 1-5` → `hermes_agent.py pre-market` (logs to `data/hermes.log`)
- `30 16 * * 1-5` → `hermes_agent.py post-market` (logs to `data/hermes.log`)
- Note: crontab invokes `/usr/bin/python3` (system 3.12), NOT `.venv` (also 3.12.3).

### Other runtime surfaces
- **Daemons** (`quant_daemon.py` PID-managed; `oi_refresh.py` 120s loop; `tick_recorder.py`; `live_ticker_service.py` 5s stream) — start manually/background.
- **WebSockets**: outbound to Angel One (quotes). No inbound WS/HTTP server sockets beyond the two dashboards.

---

## 5. Auth Components

- **Broker**: Angel One SmartAPI — `smartapi-python` + `pyotp`. Credentials from env (`.env`, `ANGEL_API_KEY/CLIENT_CODE/PASSWORD/TOTP_SECRET`). Session tokens created at runtime, stored in module state. Scrip master cached (`angel_scrip_master.json`).
- **Telegram**: `TELEGRAM_BOT_TOKEN/CHAT_ID` from env — `notifications_system.py` sends alerts.
- **OpenCode**: `opencode.json` runs local MCP servers only (no remote/cloud auth).

---

## 6. Authorization Components

- No multi-user system — single-owner local tool.
- **Risk gates** (policy, not authz): `capital_guard.py` (3% daily kill-switch, 0DTE 13:30 cutoff, event-risk IV filter), 1% per-trade cap, `RANGE_LV = NO_TRADE`, defined-risk-only spreads, hard stops.
- MCP layer is read-only; order placement only exists in `angel_one_client.py` (`place_order`) and is not wired into any automated flow.

---

## 7. Database Components

**`data/research.db`** (live layer):
- `ticks` (recv_ts, exch_ts, symbol, expiry, strike, side, ltp, bid, bid_qty, ask, ask_qty, oi, oi_chg, iv, volume, pct_chg) + idx_ticks_key
- `spot` (recv_ts, value, pct_chg) + idx_spot_ts
- `pattern_logs` (id, timestamp, pattern_name, pattern_type, confidence, signal_action, latest_close)

**`data/historical_audit.db`** (audit layer):
- `tick_history` (id, timestamp, spot_price, vix, pcr, max_pain)
- `signal_history` (id, timestamp, action, grade, confluence_score, spot_price, recommended_strike, sl_points, target_points)
- `paper_trade_journal` (id, timestamp, position_id, side, option_type, strike, entry_price, exit_price, pnl, status)

**CSV caches**: `nifty_history.csv`, `india_vix.csv`, `tick_history.csv`, `ml_features.csv`, `tf_scan.csv`, `signal_history.csv`, `fii_dii_history.csv`.

**Migrations**: none — no migration framework; schemas are inline `CREATE TABLE` in the modules that own them (tick_recorder, history_logger, paper_trader).

---

## 8. External Services

| Service | Used by | Purpose |
|---|---|---|
| Angel One SmartAPI (WebSocket + REST) | `angel_one_client.py`, `tick_recorder.py`, `web_dashboard.py` | live quotes, orders (unused), login |
| NSE (encrypted chain) via Playwright | `nse_live.py`, `oi_refresh.py` | option chain OI snapshots |
| Yahoo Finance (yfinance, cached) | `data_fetcher.py`, `equity_quant.py` | index/stock/VIX history, sectors |
| Telegram Bot API | `notifications_system.py` | trade/alert notifications |

---

## 9. Critical Assets

- `.env` — real Angel One + Telegram credentials (gitignored, untracked).
- `data/historical_audit.db` — audit trail (paper trades, signals, tick history).
- `data/research.db` — live ticks/spot.
- `data/paper_account.json` — paper account state.
- `data/oi_snapshots/` — freshest option chain (re-fetchable via `oi_refresh.py`).
- Everything else in `data/` is regenerable cache (yfinance, long-term CSVs).

---

## 10. Critical Business Flows

1. **Signal → Paper trade**: `auto_paper_runner.py` → MTF/volume/strike-selector engines → entry gated by real spot + regime; `STAND_DOWN` if no signal/no data → `paper_trader.py` journal → `history_logger.py` writes audit row with real vix/pcr/max_pain.
2. **NSE chain refresh loop**: `oi_refresh.py` (default 120s) → `oi_NIFTY_live.json` → read by `live_dash`, `smart_strike_selector`, `oi_intel`, `alert_monitor`.
3. **Live tick pipeline**: Angel WebSocket → `tick_recorder.py` → `research.db.ticks/spot` → `live_dash` API / `lob_microstructure` / volume engine.
4. **23-step pipeline**: `run_all.py` → regime → skew → gamma → ML ensemble → swarm vote → dashboard report.
5. **Capital protection**: `capital_guard.py` checked at entry; daily loss kill-switch; defined-risk spreads (`multi_leg_options.py`, `premium_seller.py`).
6. **Reporting**: `report.py`/`daily_report.py`/`systematic_report.py` → `results/*.md`; `blog_post.py` → prose summary.

---

## 11. Trust Boundaries

- **Agent/MCP ↔ data layer**: MCP tools are read-only over `data/` + market fetch — primary interface boundary.
- **Web pages ↔ localhost**: `live_dash`/`web_dashboard` bind localhost only.
- **Broker boundary**: only `angel_one_client.py` touches Angel One; no automated order path wired from signals.
- **Env secrets**: never read from source files — loaded from `.env`/environment only.
- **External data**: Yahoo/NSE/Telegram outputs are untrusted inputs parsed into pandas/JSON.
- **Process boundaries**: `hermes_agent.py` executes system commands; `quant_daemon.py` manages its own PID.

---

## 12. High-Risk Modules

| Module | Risk surface |
|---|---|
| `angel_one_client.py` | broker creds, order API (inactive), session token lifetime |
| `mcp_nifty.py` | agent-facing read boundary; what data it exposes |
| `web_dashboard.py`, `live_dash.py` | localhost HTTP serving state + broker login |
| `hermes_agent.py` | executes system commands (scheduling surface) |
| `notifications_system.py` | outbound Telegram alerts |
| `capital_guard.py` | misstep = real capital exposure (business risk) |
| `smart_strike_selector.py`, `multi_leg_options.py` | pricing math drives paper entries |
| `auto_paper_runner.py`, `agent_workflow_graph.py` | auto-execution logic (stand-down gated) |
| `history_logger.py` | audit integrity of records written |

---

## 13. Audit Scope

- **Done (2026-08-12)**: repo-wide fake-data scan — all fabricated values (hardcoded premiums, fake OI, synthetic candles, invented RL outcomes, hardcoded 2025 levels) removed; honest `UNAVAILABLE`/`STAND_DOWN`/`NO_DATA` fallbacks; 691 fabricated audit rows purged from SQLite+CSV; tests green (34/34 + 16/16); committed `039e684`.
- **Mapped but not yet deep-audited**: `main.py`, `report.py`, `daily_report.py`, `systematic_report.py`, `blog_post.py`, `trade_journal.py`, `timing.py`, `stock_flow.py`, `ml_engine.py`, `trainer.py`, `portfolio_rebalance.py`, `long_term_backtest.py`, `backtester.py`, `strategies.py`, `paper_trader.py`, `premium_seller.py` internals.

---

## 14. Unknowns

- `experiments/` full contents (one-off scripts — may drift from current code).
- `logs/2026-08-11` vs `2026-08-12` contents (daemon/agent run history).
- Whether `.venv/` is fully reproducible from `requirements.txt` alone (no lock file).
- Which modules are actually reachable vs legacy/dead code (e.g. `timing.py`, `stock_flow.py` usage).
- Angel One order path status: confirmed not wired into automation, but trade-severity of any future wiring not assessed.
- Runtime availability of broker login in CI (CI runs tests only, no broker creds).
