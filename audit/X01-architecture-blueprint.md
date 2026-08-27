# X01 — Architecture Blueprint (X-Ray)

> X-Ray phase 1. Built 2026-08-13. Evidence: 3 module x-ray sweeps (decision/risk,
> ML/learning, data/execution/infra) + `AUDIT.md` + `00-project-map.md`.
> No app code modified.

---

## 1. System in one paragraph

Nifty Research is a single-owner, local-only Python quant toolset (~90 .py files
in a flat root) that ingests NSE option-chain + Yahoo market data into cached
files/SQLite, runs a stack of rule-based quant engines (regime, OI intel,
premium signals, risk guards, ML context), and exposes the result through:
(1) an MCP server (`mcp_nifty.py`, 16 tools) consumed by opencode,
(2) a stdio/HTTP local dashboard (`live_dash.py` :8766), (3) static HTML
(blog + live terminal), (4) a paper-trading loop (`auto_paper_runner.py`).
There is no automated real-order path.

## 2. Layered model

```
 DATA ACQUISITION LAYER
   nse_live.py (Playwright, v3 encrypted API)      ─ live chain
   live_feed.py / tick_recorder.py (NSE WS)        ─ tick-by-tick → research.db
   data_fetcher.py (requests, fallback)            ─ chain + history
   yfinance (Yahoo ^NSEI/^INDIAVIX/stocks/intraday)
   institutional.fetch_fii_dii_history (free mirror)
              │
 CACHE LAYER  (data/*.csv, data/oi_snapshots/, data/stocks/, research.db)
   build_data.py (one-shot refresh, 20h freshness, 6h FII/DII)
              │
 QUANT ENGINE LAYER (stateless, read caches)
   regime_filter, oi_intel, indicators, precision_signals, gamma_flip,
   sentiment, mcx_intel, institutional, stock_flow, skew_analytics,
   timing, smart_strike_selector, volume_analytics_engine, volume_profile,
   pattern_recognition, lob_microstructure, anti_spoofing, strategies,
   backtester, multitf, mtf_alignment, equity_quant
              │
 RISK LAYER (guards, read caches + paper state)
   capital_guard, var_risk_manager, delta_hedging_guard, dynamic_trailing,
   monte_carlo, trader_psychology, expectancy_calculator, profit_engine
              │
 SYNTHESIS LAYER (merge engines into verdicts)
   market_brain (technical_consensus), super_ai_ml (ML context),
   live_trader_brain (master synthesis), agent_workflow_graph (6-node),
   multi_agent_swarm (4-agent, DEAD), reflection_engine
              │
 EXECUTION LAYER (paper only)
   paper_trader (ledger), auto_paper_runner (gated auto-trader)
              │
 PERSISTENCE OF TRUTH
   history_logger → historical_audit.db + CSV mirrors (audit trail)
              │
 PRESENTATION / INTERFACE LAYER
   mcp_nifty.py (MCP, 16 tools) │ live_dash.py (:8766) │ web_dashboard.py →
   blog/live_terminal.html │ daily_report.py → blog/posts │ systematic_report.py
   │ voice_coach (TTS) │ notifications_system (Telegram) │ alert_monitor (desktop)
```

Dependency direction is strictly downward; import graph is acyclic (verified in
first-pass audit). De-facto shared libs with highest fan-in: `regime_filter`,
`capital_guard`, `indicators`.

## 3. Entry points & orchestrators (4 parallel, drift independently)

| Entry point | Trigger | What it composes |
|---|---|---|
| `run_all.py` | CLI / control_center (8) / hermes pre-market | **23-step linear suite** (below) |
| `quant_daemon.py` | `--start` (PID file), loops 30s | live cache sync → auto_paper_runner → (every 5th) auto_enhancer |
| `hermes_agent.py` | Hermes cron (job `6005919dce97`) | pre-market run_all / intraday signal+TTS / post-market build_data + daily_report --blog |
| `control_center.py` | interactive menu | 9 one-key actions incl. daemon + run_all |
| `agent_workflow_graph.py` | run_all step 3 | 6-node sequential "LangGraph-style" (no LangGraph dep) |

### run_all.py exact 23 steps (docstring claims "32 engines"; code = 23)
1. CapitalGuard `full_capital_safety_audit()` → safety_status + kill-switch
2. `delta_hedging_guard.evaluate_portfolio_delta()` → guard_status/hedge
3. `agent_workflow_graph.run_agentic_workflow_graph()` → 6-node + equity
4. `token_lookup` scrip token for regime `trade_plan()` ATM strike
5. `var_risk_manager` 95% VaR
6. `lstm_neural_engine.predict_lstm_sequence()` (constant 0.60 output)
7. `volume_analytics_engine` surge ratio + conviction
8. `live_ticker_service.stream_live_market_ticks(1, 2)` (2 fast ticks)
9. `live_market_fetch.update_live_market_cache()` → spot sync + audit
10. `history_logger.get_historical_audit_summary()`
11. `mtf_alignment.compute_mtf_alignment()`
12. `precision_signals.generate_precision_signal()` + log_generated_signal
13. `smart_strike_selector.select_best_strike(spot=24403.10, "CE")` — **hardcoded spot**
14. `multi_leg_options.construct_multi_leg_strategy()`
15. `reflection_engine.run_reflection_loop()` (template hypotheses)
16. `gamma_flip.calculate_gamma_exposure()` on latest oi_snapshot CSV
17. `import skew, equity_quant, mcx_intel` — **prints fixed line, never calls them**
18. `auto_enhancer.run_auto_enhancement_cycle()` (no-op + boilerplate)
19. `paper_trader.paper_engine.get_paper_account_summary()` — **reads only, does NOT run auto_paper_runner**
20. `notifications_system.notify_trade_signal(...)` gated on precision signal
21. `web_dashboard.generate_live_terminal_html()` → blog/live_terminal.html
22. `systematic_report.generate_systematic_dashboard()` → results/systematic_dashboard.md
23. `voice_coach.run_voice_summary()` — Hinglish TTS

## 4. Storage map

| Store | Writer | Reader(s) | Notes |
|---|---|---|---|
| `data/nifty_history.csv` | build_data, live_market_fetch | ~20 modules | patched live intraday |
| `data/india_vix.csv` | build_data | regime_filter, sentiment | ~1yr |
| `data/fii_dii_history.csv` | build_data | institutional, sentiment | ~60 sessions |
| `data/oi_snapshots/oi_NIFTY_<date>.json/.csv` | oi_intel.save_history_json / oi_refresh | oi_intel, gamma_flip, mcp | dated; `oi_NIFTY_live.json` for dash |
| `data/research.db` (`ticks`, `spot`) | tick_recorder | live_dash, mcp recent_ticks, lob_microstructure | 191 MB / 1.21M rows; unbounded |
| `data/historical_audit.db` (`tick_history`, `signal_history`, `paper_trade_journal*`) | history_logger | control_center, run_all | `*paper_trade_journal` never INSERTed |
| `data/paper_account.json` | paper_trader | auto_paper_runner, reflection_engine, mcp | git-tracked |
| `data/adaptive_weights.json` | adaptive_weights | **nobody** | decorative state |
| `data/stocks/*.csv`, `data/sectors/*.csv` | build_data / equity_quant | stock_flow, equity_quant | Nifty-50 universe |

## 5. External services

| Service | Used by | Purpose |
|---|---|---|
| NSE streamer WS `streamer.nseindia.com/streams/fo/mbp` | live_feed, tick_recorder | free option tick stream (market hours) |
| NSE v3 encrypted API (browser) | nse_live, oi_refresh, daily_report | live chain snapshots |
| Yahoo (yfinance) | build_data, live_market_fetch, live_ticker_service, multitf, global_data, mcx_intel | spot/VIX/stocks/intraday |
| FII/DII mirror API | institutional | cash + F&O participant OI |
| Telegram Bot API | notifications_system | signal alerts |
| Angel One (margincalculator scrip master) | token_lookup, angel_one_client | token lookup; broker MCP opt-in |
| localhost :8766 | alert_monitor | desktop alerts |

## 6. Interface surface

- **MCP (16 tools, stdio, FastMCP, server `nifty-trader`)**: market_snapshot,
  regime_trade_plan, vix_intel, option_chain_intel, gamma_flip_intel,
  institutional_flow, technical_consensus, precision_signal,
  capital_guard_audit, stock_scan, super_ai_ml_context, expiry_status,
  expected_move, broker_status (env-gated `BROKER_MCP_ENABLED=1`),
  recent_ticks, full_daily_report. All tools read `data/` caches first, never re-download.
- **live_dash :8766 (stdlib HTTP)**: `/`, `/api/spot`, `/api/ticks?n=`,
  `/api/chain`, `/api/status`. Full-table scans per request (H3).
- **Static HTML**: blog/posts + index (blog_post, cap 60), live_terminal.html.
- **Desktop**: alert_monitor (notify-send + paplay).

## 7. Architecture risks carried forward

1. God orchestrator (run_all fan-out 26) — steps 13/17 are inert/hardcoded.
2. 4 parallel orchestrators drift independently (run_all / daemon / hermes / control_center).
3. No data-access layer; 15 modules re-implement "read latest OI snapshot";
   4+ "current spot" helpers; max-pain computed in 2 places (dual-bug history, both fixed).
4. `multi_agent_swarm`, `live_trader_brain` are built but not wired into run_all/test_all.
5. Production readiness 4/10 (no backups, no rotation, Docker = test runner only).
