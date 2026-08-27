# X04 — Module Inventory (X-Ray)

> X-Ray phase 4. Built 2026-08-13. Full inventory of the ~90-file flat root,
> grouped by layer. Caller truth verified by x-ray sweeps.

---

## 1. Decision / Risk engines (x-ray sweep #1)

| Module | One-liner | Live path | Status |
|---|---|---|---|
| `regime_filter.py` | 4-regime gate (TREND/RANGE × HV/LV) + VIX premium zone; RANGE_LV=NO_TRADE; expected move | fan-in 11 — primary gate | ACTIVE, untested |
| `capital_guard.py` | SEBI guards: 3% kill-switch, 0DTE trap, 1% sizer | run_all(1), auto_paper_runner, mcp | ACTIVE (H2 sizing bug) |
| `precision_signals.py` | 6-layer confluence; only A+ else NO_SIGNAL | auto_paper_runner, agent_workflow, mcp | ACTIVE (H1 fabricates L3) |
| `oi_intel.py` | OI walls, build-up, PCR, max pain, Murarkar matrix | daily_report, mcp, gamma_flip | ACTIVE, untested |
| `smart_strike_selector.py` | strike from Δ 0.30–0.55 (BS, chain IV) | auto_paper_runner, agent_workflow, mcp | ACTIVE |
| `skew_analytics.py` | IV/RV skew, put-skew z-score | daily_report | ACTIVE |
| `market_brain.py` | `analyze_market` multi-indicator consensus → verdict/strength/confidence (clamped 50–75) | technical_consensus mcp, daily_report, timing | ACTIVE (hardcoded "trained" constants) |
| `gamma_flip.py` | MM net GEX + flip strike; `gamma_flip_strike` may be None | run_all(16), mcp, web_dashboard | ACTIVE |
| `delta_hedging_guard.py` | hedge when \|net_delta\|>500, target ±100 | run_all(2) | ACTIVE |
| `var_risk_manager.py` | parametric VaR95/99 + formulaic stress | run_all(5), auto_paper_runner | ACTIVE (stress always PASSED) |
| `sentiment.py` | risk-on/off: S&P/DXY/Gold/Crude/BTC/USDINR/FII/PCR/max-pain; weights global 1.0, fii 1.5, options 0.5 | agent.py (agent_workflow) | ACTIVE |
| `mcx_intel.py` | Gold/Silver ratio, crude ±1.5%, DXY metals ±0.3% | run_all(17, **not called**) | DORMANT |
| `smc_intelligence.py` | FVG/OB/CHoCH on 60 daily bars | live_trader_brain | BUILT, not wired |
| `mtf_alignment.py` | "5m/15m/1h/daily" from 5/10/20/50 daily bars | run_all(11), auto_paper_runner | ACTIVE (label inflation) |
| `timing.py` | gap/ORB/DOW stats + `timing_votes()` (data-driven per run) | market_brain family | ACTIVE |
| `stock_flow.py` | Nifty-50 accumulation scan | daily_report, stock_scan mcp | ACTIVE |
| `institutional.py` | FII/DII cash + participant OI, margin-CE read | daily_report, mcp | ACTIVE |
| `volume_analytics_engine.py` | surge vs 20-SMA, CMF20, OBV, pocket pivot | run_all(7), auto_paper_runner | ACTIVE |
| `volume_profile.py` | POC (bins=20), 70% value area | auto_enhancer | ACTIVE (random-vol fallback) |
| `pattern_recognition.py` | candlesticks (conf 85/80/70) + double top/bottom (conf 88) | mcp_pattern_bridge, test_all | ACTIVE |
| `lob_microstructure.py` | LOB imbalance (level counts), VPIN>0.40 toxic | multi_agent_swarm (**dead**) | DORMANT |
| `anti_spoofing.py` | wall-strike OI change < −20% → spoof; `price_volatility_pct=0.2` unused | multi_agent_swarm (**dead**) | DORMANT |
| `multi_leg_options.py` | bull call / bear put / short strangle / IC from live LTP | run_all(14), agent_workflow, mcp | ACTIVE |
| `premium_seller.py` | IC seller backtest, VIX 16–25 gate | daily_report | ACTIVE (lot 25 bug) |
| `strategies.py` | 16 registered signal generators + 223-config grid (×6 holds = 1,338 runs) | main, multitf, ml_engine, trade_journal | ACTIVE |
| `backtester.py` | BS option / underlying backtest; slippage 1.5%, ₹40 cost | main, multitf, trade_journal | ACTIVE |
| `multitf.py` | 15m/30m/60m/1d grid ranking (Yahoo caps) | daily_report (cached tf_scan) | ACTIVE |
| `long_term_backtest.py` | "46-year" S&P/Sensex RSI+SMA200 audit | standalone | DEAD-ish, "ULTRA_ROBUST" fabricated |
| `lob_microstructure.py` (contd.) | reads research.db ticks/spot | — | — |

## 2. ML / learning modules (x-ray sweep #2)

| Module | Actual ML? | Adaptive? | Live path | Class |
|---|---|---|---|---|
| `ml_engine.py` | Yes (sklearn, walk-forward) | re-fits each run; no persistence | context only (daily_report:126) | (a)+(c) |
| `super_ai_ml.py` | Yes (XGB/LGBM/RF) | re-fits each run; no persistence | signal layer 6 + master brain (doc'd context-only) | (a)+(c) |
| `trainer.py` | No (evaluates rule brain) | no feedback; constants frozen in market_brain | no caller (manual) | (b)/(c) |
| `lstm_neural_engine.py` | No (deterministic ramp, always 0.60) | No | run_all(6) display only | (d) |
| `adaptive_weights.py` | No (clamped ±lr) | code can; no outcomes supplied, no consumer | not used | (b)/(c) |
| `auto_enhancer.py` | No | no-op + boilerplate log | daemon every 2.5 min, changes nothing | (b)/(d) |
| `reflection_engine.py` | No | template hypotheses, never validated | run_all(15) | (b)/(c) |
| `volatility_forecaster.py` | No (fixed GARCH consts ω2e-6 α0.08 β0.90) | No; fabricates <10 samples | smoke test only | (b)/(c)/(d) |
| `portfolio_rebalance.py` | No | fixed equal-weight backtest | manual | (b)/(c) |
| `empirical_proof.py` | No | fixed verification | no caller | (b)/(c)/(d) |
| `equity_quant.py` | No (formula scans) | fixed formulas | imported, never invoked | (b)/(c) |

## 3. Data / execution / infra (x-ray sweep #3)

| Module | One-liner | Invoked by | Notes |
|---|---|---|---|
| `data_fetcher.py` | NSE/Yahoo chain + history (requests) | main.py | plain-requests fallback |
| `nse_live.py` | Playwright v3 encrypted chain fetch | oi_refresh, daily_report | primary live chain |
| `live_feed.py` | NSE WS streamer (market hours) | CLI, tick_recorder | 0 msgs outside hours is normal |
| `tick_recorder.py` | research.db builder (ticks/spot), batch 200/5s, 15:30 stop | standalone daemon | main research DB |
| `live_market_fetch.py` | honest live spot (never fabricates) + cache sync | auto_paper_runner, run_all(9), quant_daemon | audit log |
| `live_ticker_service.py` | 5s spot+VIX stream → audit + terminal HTML | control_center, run_all(8) | ⚠ hardcoded fallback |
| `build_data.py` | one-shot cache builder (20h / FII 6h freshness) | CLI, hermes post-market | `--fresh`, `--skip-oi` |
| `paper_trader.py` | virtual ledger, singleton `paper_engine` | auto_paper_runner, agent_workflow, run_all(19) | paper_account.json |
| `auto_paper_runner.py` | gated auto-trader iteration | quant_daemon (30s) | full gate chain |
| `quant_daemon.py` | PID daemon, 30s loop + auto_enhance every 5th | CLI | daemon log |
| `run_all.py` | 23-step master suite | CLI, control_center, hermes pre-market | god orchestrator |
| `main.py` | legacy CLI (fetch-data/research/report/all) | CLI only | LEGACY |
| `control_center.py` | 9-key interactive menu | CLI only | launcher |
| `hermes_agent.py` | pre/intra/post market scheduled agent | Hermes cron | builds + report |
| `alert_monitor.py` | desktop alerts via live_dash :8766 | standalone daemon | notify-send |
| `history_logger.py` | append-only audit trail (3 tables) | many | paper_trade_journal dormant |
| `oi_refresh.py` | OI snapshot refresher | standalone | — |
| `daily_report.py` | combined report + `--blog` | CLI, mcp full_daily_report, hermes | — |
| `report.py` | markdown renderers (market/backtest + research_results.csv) | main.py | — |
| `systematic_report.py` | beautiful-markdown dashboard | run_all(22) | — |
| `blog_post.py` | dated HTML post + index (cap 60) | CLI, daily_report --blog | one post/day |
| `web_dashboard.py` | live terminal HTML generator | live_ticker, run_all(21) | — |
| `live_dash.py` | stdlib HTTP :8766 (5 endpoints) | standalone daemon | full-table scans (H3) |
| `mcp_nifty.py` | MCP server, 16 tools | opencode (server nifty-trader) | reads cache first |
| `agent_workflow_graph.py` | 6-node sequential workflow | run_all(3), test_all | paper order node |
| `multi_agent_swarm.py` | 4-agent swarm → HIGH_CONVICTION_* | standalone only | DEAD (0 importers) |
| `config.py` | .env loader (manual parse) | 2 modules | — |
| `global_data.py` | 11 global tickers + FII/DII attempt | swarm, systematic_report | no cache writes |
| `token_lookup.py` | Angel scrip-master token lookup | run_all(4) | hardcoded fallbacks |
| `notifications_system.py` | Telegram notifier (env-gated) | run_all(20), test_all | — |
| `telegram_notifier.py` | thin standalone | — | DEAD (superseded) |
| `voice_coach.py` | gTTS Hinglish TTS | run_all(23), hermes | — |
| `web_research.py` | news cues (websearch → RSS fallback) | systematic_report | — |
| `connection_resilience.py` | DNS ping + reconnect; reconcile stub | test_all only | DORMANT |
| `trade_journal.py` | journal analyzer CLI (FIFO pairing) | standalone | functional tool |
| `backup_data.py` | copies state JSONs | CLI | decorative-state backup |
| `trader_psychology.py` | tilt/FOMO/over-confidence triggers | live_trader_brain | — |
| `live_trader_brain.py` | master synthesis (5 engines → RECOMMENDED_*) | standalone | not in run_all |
| `expectancy_calculator.py` | EV-per-rupee-risk | profit_engine, test_all | — |
| `profit_engine.py` | plan builder (1%, 1.2×ATR, 2×/3×) | self | no consumers |
| `dynamic_trailing.py` | Chandelier ×2.5, 3 tiers | profit_engine, auto_paper_runner, test_all | — |

## 4. Infra

- `opencode.json` — MCP `nifty-trader` (`.venv/bin/python mcp_nifty.py`) +
  `git-nifty` (uvx mcp<2.0); skills path `.opencode/skills`; bash+external dir allowed.
- `.github/workflows/ci.yml` — matrix 3.11/3.12 → `pip install -r requirements.txt`
  → `python test_all.py` (34-module suite) → `unittest discover -s tests`.
- `Dockerfile` — python:3.11-slim, playwright chromium, CMD test_all.
- `docker-compose.yml` — single service, mounts data/logs/results, env .env.example.
- `.opencode/` — 9 agents, 11 commands, 12 skills.

## 5. Missing test coverage (from first pass)

No tests for: `regime_filter` (fan-in 11), `oi_intel` max-pain/PCR,
`history_logger` audit writes, `auto_paper_runner`→`paper_trader` E2E,
all 15 MCP tools (excluding full_daily_report), `live_dash` endpoints,
`institutional`, `mtf_alignment`, `run_all` orchestration, H1/H2.
