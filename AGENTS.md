# Nifty Research — Agent Memory & Instructions

> **First read `OWNER_INSTRUCTIONS.md`** — it records the owner's text
> instructions (trading philosophy, risk rules, VIX regime matrix, ML
> honesty, live-tick source). It is the source of truth for *why* this code
> exists; this file is the operational memory for *how* to work here.

## Purpose
Options intelligence + backtesting toolset for NSE (Nifty 50 / Bank Nifty).
Built around Nitin Murarkar-style OI + institutional flow logic, with a
strategy research/backtest pipeline.

## How to work here (permanent rules)
1. **No repetitive work.** Always cache data to `data/` on first fetch and
   read from cache afterward. Never re-download the same data in a run.
2. Build data first, then run analysis. Use `python build_data.py` to fetch
   everything into cache once; analysis scripts read from cache.
3. Market data is fetched from NSE (blocked to plain requests -> use
   Playwright browser for live chain) and Yahoo Finance (stocks, intraday).
4. Keep scripts executable end-to-end (`python file.py` should work).
5. User communicates in Hinglish. Respond in Hinglish (Roman script).
6. Think like a 50-year veteran trader/dev: robust, cached, no wasted API
   calls, edge over flash.
7. **Loss control is the edge.** Always surface the regime gate (`regime_filter`)
   and hard risk rules (1% per trade, 3% daily stop, ATR stop, no averaging
   down). RANGE_LV regime = NO TRADE, never recommend a directional option then.

## Data cache (data/)
- `data/oi_snapshots/` — daily option-chain snapshots (JSON+CSV). Used for
  OI build-up/spike detection across days.
- `data/stocks/` — Yahoo daily OHLCV per Nifty 50 symbol (`<SYM>.csv`).
- `data/fii_dii_history.csv` — FII/DII cash + F&O participant OI history
  (from free mirror API, ~60 sessions).
- `data/tf_scan.csv` — multi-timeframe strategy grid scan results.
- `data/nifty_history.csv` — Nifty 50 daily history.
- `data/india_vix.csv` — India VIX daily history (Yahoo ^INDIAVIX, ~1yr).
  Feeds regime_filter premium side + expected move.
- `data/research.db` — SQLite research DB built by `tick_recorder.py` during
  market hours: tables `ticks` (per-strike CE/PE quotes: ltp/bid/ask/oi/iv/
  volume, every stream update) and `spot` (index sampled every 60s). Grows
  every market day -> intraday OI build-up + IV skew + spread research.

## Modules
- `data_fetcher.py`  — NSE/Yahoo data + option chain (plain requests).
- `nse_live.py`      — live NSE via Playwright (encrypted API workaround).
- `oi_intel.py`      — OI walls, build-up, PCR, max pain, Murarkar matrix.
- `stock_flow.py`    — Nifty 50 accumulation scan (trend + buying period +
  momentum + volume). `scan_universe()` / `analyze_stock()`.
- `institutional.py` — FII/DII cash + participant OI, margin-CE read.
- `indicators.py`    — indicator computation.
- `strategies.py`    — strategy library + param grids.
- `backtester.py`    — option/underlying backtest engine (BS premium).
- `multitf.py`       — multi-timeframe (15m/30m/60m/daily) backtesting.
- `daily_report.py`  — combined daily report (chain + institutional + stock
  flow + TF edge + ML context). `--blog` flag also auto-posts.
- `regime_filter.py` — 4-regime market gate (TREND/RANGE x HV/LV) + India VIX
  premium regime (CHEAP/NORMAL/RICH/HIGH/PANIC). RANGE_LV = NO_TRADE.
  VIX PANIC + low conf = hard no-trade. Expected daily move from VIX.
- `premium_seller.py` — defined-risk option SELLING backtest (iron condor),
  gated on VIX 16-25 + sane regime. Backtest: 72.5% win, PF 2.6 (matches
  research 60-75%). Research edge: sellers collect theta, buyers bleed.
- `blog_post.py`     — auto-generates dated HTML blog post from daily report +
  regime gate + AI-trading setup guide; regenerates `blog/index.html`.
- `build_data.py`    — fetch all data once into cache.
- `tick_recorder.py` — live research DB recorder: streams every NSE option
  quote (same `live_feed` WebSocket) into `data/research.db` table `ticks`
  + samples index spot (Yahoo ^NSEI 1m) into `spot` every 60s. Batch-commits
  every ~200 rows / 5s, auto-reconnects, stops at 15:30 IST. Run every market
  day to grow the research dataset.
- `live_feed.py`     — live tick-by-tick via NSE official streamer WebSocket
  (`wss://streamer.nseindia.com/streams/fo/mbp?symbol=<SYM>&expiry=<DATE>`).
  Same endpoint NSE's own option-chain page uses (optionchain-stream JS).
  Free, no broker account. Works only during market hours - outside 09:15-15:30
  the socket connects then NSE closes it (0 messages is normal). NOT a
  fallback for snapshots - use `nse_live.fetch_option_chain_live` for that.
  Old `wss://webstream.nseindia.com` is DEAD (DNS gone) - do not use.
- `capital_guard.py`  — SEBI loss-prevention: 3% daily kill-switch, 0DTE expiry
  trap (>13:30 IST = no naked buying), event-risk filter, drawdown de-risking,
  strict 1% position sizer.
- `precision_signals.py` — 6-layer confluence signal (regime + capital guard +
  technicals + OI/skew + institutional + ML). Only A+ grade signals; else NO_SIGNAL.
- `gamma_flip.py`     — market-maker net GEX + gamma flip strike (long gamma =
  stabilizing, short gamma = accelerating). NOTE: returns `gamma_flip_strike`
  (None on no-data/error) — consumers read that key.
- `live_trader_brain.py` — master synthesis: psychology + SMC + Monte Carlo +
  super-AI ML + capital guard -> RECOMMENDED_* or STAND_BY_NO_TRADE.
- `super_ai_ml.py`    — XGBoost/LightGBM/RF ensemble. CONTEXT ONLY (~51% vs 52%
  baseline, no standalone edge).
- `mcp_nifty.py`      — **trading MCP server** (stdio, FastMCP): exposes every
  engine as an MCP tool (`market_snapshot`, `regime_trade_plan`, `vix_intel`,
  `option_chain_intel`, `gamma_flip_intel`, `institutional_flow`,
  `technical_consensus`, `precision_signal`, `capital_guard_audit`,
  `stock_scan`, `super_ai_ml_context`, `expiry_status`, `expected_move`,
  `broker_status`, `recent_ticks`, `full_daily_report`). Run via
  `.venv/bin/python mcp_nifty.py`. Register in opencode.json under `nifty-trader`.
- `.opencode/`        — opencode agents (`quant-researcher`, `risk-officer`,
  `nifty-analyst`) + slash commands (`/trade-setup`, `/market-snapshot`,
  `/oi-intel`, `/regime-gate`, `/risk-audit`, `/broker`, `/stock-flow`,
  `/institutional`, `/deep-research`, `/auto-enhance`, `/backtest`).
- `.opencode/skills/` — project skills (`nifty-analysis`, `oi-intel`,
  `trade-setup`), registered via opencode.json `skills.paths`. Prefer
  `nifty-trader` MCP tools over `python -c` one-liners.

## Entry points
- `python build_data.py` — build/refresh full data cache.
- `python tick_recorder.py NIFTY` — record whole market day into data/research.db
  (background: PTY / `nohup`). `--seconds N` for a short test run.
- `python daily_report.py` — combined daily report (uses cache, refreshes
  what is stale).
- `python daily_report.py --blog` — same + auto-post to `blog/`.
- `python blog_post.py` — regenerate blog post + index from current report.
- Option chain live test: `python nse_live.py`
- Live ticks (market hours only): `python live_feed.py NIFTY 60`
- Open blog: `blog/index.html` (or `python -m http.server 8765 --directory blog`)

## OpenCode CLI (trading power-up)
Project `opencode.json` registers `nifty-trader` (runs `.venv/bin/python
mcp_nifty.py`, venv = system-site-packages + `mcp<2.0`) and `git-nifty`
(`uvx --with "mcp<2.0" mcp-server-git`). Global `~/.config/opencode/opencode.json`
registers `memory`, `sqlite-nifty`, `filesystem-nifty`, `fetch`, `playwright`.
Skills live in `.opencode/skills/` (moved from `~/.opencode/skills`, now
version-controlled). Agents in `.opencode/agent/`, commands in `.opencode/command/`.

- GOTCHA: reference MCP servers (`mcp-server-sqlite`, `mcp-server-fetch`,
  `mcp-server-git`) use the mcp 1.x API. `uvx` alone pulls mcp 2.x and they
  crash at boot (`list_resources` / `McpError` errors). ALWAYS run them as
  `uvx --with "mcp<2.0" mcp-server-<name>`. Fixed + verified 2026-08-12.
- Custom `nifty-trader` needs `mcp<2.0` too (same reason) - venv pins it.
- No trading-specific opencode plugin exists in the ecosystem; project "plugin"
  layer = skills + slash commands + agents (markdown, version-controlled).
- Config changes (opencode.json, agents, commands, skills) need an opencode
  restart to take effect.
- If `nifty-trader` MCP tools are unavailable, fall back to
  `python -c "import ..."` (same cached data).
- Rebuild the MCP venv if broken: `python3 -m venv --system-site-packages .venv
  && .venv/bin/pip install "mcp>=1.8,<2.0"`.

## Automated pipeline (Hermes cron)
- Job `6005919dce97` `nifty-daily-report`: weekdays 16:30 IST, runs
  `C:\Users\Mohit\AppData\Local\hermes\scripts\daily_report.py` (wrapper ->
  `blog_post.py`) -> generates report AND auto-posts to blog. Gateway service
  auto-starts on login.
- Hermes CLI: `...\hermes-agent\venv\Scripts\hermes.exe` (`cron status/list`,
  `cron run <id> --accept-hooks`, `cron runs`, `send`, `-z "prompt"`).

## Gotchas
- NSE option chain API is encrypted; live fetch must run in-browser
  (`nse_live.fetch_option_chain_live`). Plain `data_fetcher` is fallback.
- Yahoo intraday range caps: 15m/30m<=60d, 60m<=90d, daily<=730d.
- Max pain: compute on ATM band (spot ±8%), not full strike set. Formula:
  at settlement S calls pay `max(0, S - K)`, puts pay `max(0, K - S)`, and
  max pain = the strike with the LEAST total payout to buyers (argmin) -
  NOT argmax. NOTE: fixed in BOTH `oi_intel.pcr_and_pain` and
  `data_fetcher.compute_chain_metrics` (main.py report path) - both had the
  swapped-formula + argmax bug; keep them in sync.
- Blog post = one per day: `blog_post.main()` overwrites today's post
  (`blog/posts/<date>.html`), never appends timestamped duplicates.
- `backtester.run_backtest(mode="underlying")` for cross-TF comparison;
  `mode="option"` for daily option premium.

## ML findings (DONE - do not re-run as primary signal)
- `ml_engine.py` meta-blender (9-16 strategy signals via walk-forward):
  out-of-sample acc ~51% vs baseline ~52% => NO standalone edge. Use only as
  context/agreement counter, never as a buy/sell trigger.
- Direction classifier: ~49% vs baseline ~52% => coin flip. Do not retrain
  repeatedly looking for edge; it will overfit. If retrained, only with fresh
  walk-forward and report edge vs baseline.
- Keep ML honest: report accuracy AND baseline AND edge. No shuffling (ts).

## Risk rules (hard, never relax)
- Max 1% of capital per trade; stop = 1.5x ATR below entry (structure-based).
- 3% daily / 7% weekly loss limit -> stop trading. No averaging down, ever.
- Defined-risk only (spreads/iron condors); no naked short options advice.
- Expiry day: no new entries after 14:30, square off by 15:05.
- Regime RANGE_LV (low-vol chop) = NO TRADE for directional options.

## Research-backed strategy matrix (web research, verified sources)
- India VIX premium regime decides BUY vs SELL options (NiftyDesk/MarketsEasy):
  VIX<12 cheap->buy; 12-16 normal->directional spreads; 16-20 rich->start
  selling; 20-25 high->sell aggressively (smaller size); >25 panic->mean-rev
  or sit out.
- Expected daily move = NIFTY x (VIX/100)/sqrt(252).
- Option sellers win 60-75% with defined risk (iron condor/short strangle);
  buyers mostly lose to theta -> buy only ATM/ITM, never far OTM.
- Bought options: cut at 40-50% of premium. Sold options: exit if premium
  doubles from entry or short leg goes ITM. Hard stops, not mental.
- "No clear setup = no trade" is a rule, not a suggestion.
- GitHub refs: buzzsubash/algo_trading_strategies_india (short straddle/
  strangle/iron-fly, Zerodha), Aditya0049/NIFTY-OPTIONS-TRADING-AI (sell when
  daily move <1%, ~61% win), maddy1852005-DS regime-switch ML bot.

## IV Skew & Microstructure findings (deep-research 2026-08-12, from
research.db tick data 11-Aug-2026 expiry + web research; do not re-run daily)
- Expiry-day surface is a two-layer structure: DEEP OTM wings = permanent put
  smirk (put IV rich), but ATM/near-ATM = regime-sensitive and often
  CALL-SKEWED on expiry days (reconstructed RR ~ -3 to -4 vol pts, i.e. OTM
  call IV 3-4 pts ABOVE OTM put IV; skew ratio 0.93-0.97 all day). Retail
  call-lottery flow + call-heavy gamma is the driver. Treat as microstructure
  noise, NOT a reliable stand-alone edge.
- Butterfly convexity: 0 mid-price violations in ATM band on expiry day =>
  static no-arb holds; convexity arb dead after costs.
- Put-call parity: implied F consistent across strikes within 0.2-0.3 pts
  (std of F); NIFTY futures basis F-spot ~ +10 to +14 pts (positive carry) ->
  box/conversion arb dead net of costs.
- Spreads blow out as expiry approaches: avg rel spread 8% (10:00) -> 27%
  (13:00); OTM strikes (>2% OTM) trade at min-tick with rel spreads 10-59% =>
  only ATM +/-1.5% is economically tradeable. Execution cost hurdle for any
  multi-leg skew trade ~ 5-15 pts/lot.
- Expiry-day pinning worked: spot 24447 vs max pain 24450 (within 3 pts);
  24500 CE wall +379K OI (+615%, 440K total) capped the move; PCR 0.749 &
  falling (call heavy) + Murarkar "watch cap".
- VPIN/toxicity: use as flow descriptor only (Andersen-Bondarenko critique).
- Tradeable verdict on NIFTY weeklies (post-2025 SEBI cost regime, lot=75):
  VIX/IV-rank-gated premium selling > put-skew z-score credit spreads >
  calendar skew > risk-reversal carry (thin). NOT tradeable: box/parity,
  naked butterfly, dispersion, guaranteed 25d skew carry. Expiry-day
  call-skew academic proof is scarce - keep as noise.
- IV field in research.db `ticks` is always NULL (NSE streamer doesn't send
  it) -> reconstruct via BS Newton/bisection from mid (vectorized; expiry-day
  absolute IV unstable, RELATIVE skew structure is the signal).
