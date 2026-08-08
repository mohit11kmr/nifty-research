# Nifty Research — Agent Memory & Instructions

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
- `live_feed.py`     — live tick-by-tick via NSE official streamer WebSocket
  (`wss://streamer.nseindia.com/streams/fo/mbp?symbol=<SYM>&expiry=<DATE>`).
  Same endpoint NSE's own option-chain page uses (optionchain-stream JS).
  Free, no broker account. Works only during market hours - outside 09:15-15:30
  the socket connects then NSE closes it (0 messages is normal). NOT a
  fallback for snapshots - use `nse_live.fetch_option_chain_live` for that.
  Old `wss://webstream.nseindia.com` is DEAD (DNS gone) - do not use.

## Entry points
- `python build_data.py` — build/refresh full data cache.
- `python daily_report.py` — combined daily report (uses cache, refreshes
  what is stale).
- `python daily_report.py --blog` — same + auto-post to `blog/`.
- `python blog_post.py` — regenerate blog post + index from current report.
- Option chain live test: `python nse_live.py`
- Live ticks (market hours only): `python live_feed.py NIFTY 60`
- Open blog: `blog/index.html` (or `python -m http.server 8765 --directory blog`)

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
  calls pay `max(0, K - s)`, puts pay `max(0, s - K)`, and max pain = the
  strike with the LEAST total payout (argmin) - NOT argmax.
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
