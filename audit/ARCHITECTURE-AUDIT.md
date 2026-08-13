# Architecture Audit — Nifty Research

> Deep audit Phase 2. Full detailed findings in `audit/01-architecture.md`
> (10 sections). This file = summary + data-flow diagram + top architecture
> findings, to avoid duplication. No app code modified. Built: 2026-08-12.

---

## 1. Data Flow Diagram (reconstructed)

```
                          ┌──────────────────────────────────────────────┐
                          │              ENTRY POINTS                    │
                          │  mcp_nifty (stdio)   live_dash (127.0.0.1)   │
                          │  run_all (23-step)   control_center (CLI)    │
                          │  quant_daemon (PID)  hermes_agent (cron)     │
                          │  main (CLI)          web_dashboard (HTML)    │
                          └───────────────┬──────────────────────────────┘
                                          │ import / invoke
                       ┌──────────────────▼───────────────────┐
                       │     ORCHESTRATION LAYER              │
                       │  run_all · quant_daemon · hermes     │
                       │  agent_workflow_graph · swarm        │
                       └──────────────────┬───────────────────┘
                                          │
              ┌───────────────────────────┼───────────────────────────┐
              │  DATA INGESTION           │  ANALYSIS ENGINES         │
   Yahoo ─────► data_fetcher, equity_quant│  regime_filter (11 fan-in)│
   NSE WS ────► live_feed, tick_recorder  │  capital_guard (11)       │
   NSE bwr ───► nse_live, oi_refresh      │  oi_intel · skew · greeks │
   Angel WS ──► angel_one_client, live_tic│  precision_signals · ML   │
              └──────────────┬────────────┘  gamma_flip · lob · smc   │
                             │               mtf · volume · sentiment  │
              ┌──────────────▼─────────────┐                           │
              │         DATA LAYER         │◄───────── read/write ─────┘
              │ data/*.csv · *.json        │
              │ research.db (WAL, 191MB)   │
              │ historical_audit.db (no WAL│
              │ paper_account.json         │
              └────────────────────────────┘
```

Key flow (paper trade): cron/daemon → `auto_paper_runner` → `regime_filter`
gate → `precision_signals` → `smart_strike_selector` → `paper_trader`
(paper_account.json + journal) → `history_logger` (audit DB+CSV).

---

## 2. Top Architecture Findings (details in `01-architecture.md`)

| # | Finding | Severity | Evidence |
|---|---|---|---|
| P1 | God orchestrator `run_all` — 23-step hardcoded linear pipeline, fan-out 26 | High | `run_all.py:36`, per-step `try/except` |
| P2 | No data-access layer — snapshot/spot logic in 15+ modules, 4+ "current spot" helpers | High | `mcp_nifty._current_spot`, `live_dash._load_snapshot_oi`, `live_market_fetch._last_real_spot` |
| P3 | 4 parallel live-data ingestion paths (2× yfinance + 2× NSE WS) | Medium | `live_market_fetch`, `live_ticker_service`, `live_feed`, `tick_recorder` |
| P4 | Max-pain/PCR computed twice (`oi_intel` + `data_fetcher`) — dual-bug history | Medium | AGENTS.md gotcha; `oi_intel.py:165`, `data_fetcher.py:186` |
| D2 | Fetcher depends on report modules (`live_ticker_service` → `web_dashboard`) | Medium | import graph |
| D3 | `regime_filter.trade_plan()` doubles as spot source for 11 callers | Medium | `agent_workflow_graph._real_spot` |
| M1 | 86 files at root, flat namespace; naming collisions (`agent.py` vs `agent_workflow_graph.py`) | Medium | repo layout |

**Positives**: 0 circular dependencies (AST-verified), focused engines,
read-only MCP boundary, honest fallbacks, localhost-only web, PID daemon,
storage separation (live vs audit DBs).

---

## 3. Architecture Diagram request

Above ASCII diagram reconstructs the runtime data flow
(DISCOVER→UNDERSTAND→ANALYZE per master prompt). Layer boundaries are
informal (data-shared architecture) — that informality is the root of P2/P3.
