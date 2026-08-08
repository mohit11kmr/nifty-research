# NIFTY Options Intelligence & Research Toolset

A free, local-first options intelligence platform for the Indian market
(Nifty 50 / Bank Nifty). It combines **institutional OI logic**, **market
regime detection**, **India VIX premium regime**, **multi-timeframe
backtesting**, and a **defined-risk option-selling edge** into one pipeline
that produces a daily report — and auto-posts it to a static blog.

Everything runs on **free data** (NSE public endpoints + Yahoo Finance). No
broker account required.

> Educational research tool. Not investment advice. Markets carry risk; you
> can lose money. Never risk money you cannot afford to lose.

---

## What it does

| Feature | Module | What you get |
|---|---|---|
| Daily report | `daily_report.py` | Regime gate + OI walls + FII/DII + stock scan + TF edge + ML context in one file |
| OI intelligence | `oi_intel.py` | OI walls, build-up, PCR, **max pain**, Murarkar 4-pattern matrix |
| Regime gate | `regime_filter.py` | TREND/RANGE × HV/LV classification + **India VIX premium regime** |
| Loss control | `regime_filter.py` | Hard rules: 1% per trade, 3% daily stop, ATR stop, RANGE_LV = NO TRADE |
| Premium selling edge | `premium_seller.py` | Iron condor backtest gated on VIX 16–25 (72.5% win, PF 2.6) |
| Stock accumulation scan | `stock_flow.py` | Nifty 50 stocks in institutional accumulation (price > SMA20 > SMA50) |
| Institutional flow | `institutional.py` | FII/DII cash, participant OI, FII call/put writing read |
| Multi-TF backtesting | `multitf.py` | 15m/30m/60m/daily strategy grid, best TF + params per strategy |
| ML context | `ml_engine.py` | Meta-blender agreement counter (kept honest — no standalone edge) |
| Live tick-by-tick | `live_feed.py` | NSE official streamer WebSocket, free, market hours only |
| Auto blog | `blog_post.py` | Dated HTML post + index from the daily report |

---

## Requirements

- Python 3.10+
- Dependencies: `pip install -r requirements.txt`
- **Chrome** installed (for live NSE option-chain via Playwright)

`requirements.txt`:

```
pandas
numpy
scikit-learn
requests
websocket-client
playwright
```

After installing, run `playwright install chrome` (uses your system Chrome).

---

## Quick start

```bash
git clone https://github.com/mohit11kmr/nifty-research
cd nifty-research
pip install -r requirements.txt
playwright install chrome

# 1. Build the data cache once (Nifty history, all Nifty-50 stocks, India VIX,
#    FII/DII). Takes a few minutes the first time, cached afterwards.
python build_data.py

# 2. Generate the full daily report (reads from cache, refreshes stale data).
python daily_report.py

# 3. Auto-post to the blog (writes blog/posts/<date>.html + index.html).
python blog_post.py

# 4. Open the blog.
python -m http.server 8765 --directory blog
# -> http://localhost:8765
```

That's it. On any trading day you can just run `python daily_report.py`.

---

## Report sections

The daily report is a single wall of text — every section is meant to be
*context*, not a trigger:

1. **Regime gate + VIX** — is the market trending or chopping? Is option
   premium cheap or rich? `RANGE_LV` + low VIX = **NO TRADE**.
2. **Option chain** — CE/PE OI walls, build-up, PCR, max pain, Murarkar matrix.
3. **Institutional flow** — FII/DII cash, FII option writing/buying read.
4. **Stock flow** — top accumulation stocks with score + trend confirmation.
5. **Multi-timeframe edge** — which TF/params were historically best per strategy.
6. **ML context** — strategy agreement counter (2/9 CALL, 7/9 PUT, etc.).
7. **Premium seller** — iron condor backtest state (win rate, PF, exits).

---

## The edge (how loss control works)

Research across public sources + our own backtests says the profit comes
from **risk control, not prediction**:

- **Regime filter** blocks directional options in low-vol chop (RANGE_LV).
  A trend strategy in a chop market loses money — the gate stops you entering.
- **India VIX premium regime** decides BUY vs SELL option premium:
  VIX < 12 cheap → buy; 12–16 normal → directional spreads; 16–20 rich →
  start selling; 20–25 high → sell aggressively (smaller size);
  > 25 panic → mean-revert or sit out.
- **Hard risk rules**: max 1% of capital per trade, stop at 1.5×ATR before
  entry, 3% daily / 7% weekly loss = stop trading, no averaging down.
- **Defined risk only**: spreads / iron condors. No naked short advice.
- **Option sellers win 60–75%** with defined risk; buyers bleed theta — buy
  only ATM/ITM, never far OTM. Cut bought options at 40–50% of premium;
  exit sold options if premium doubles or the short leg goes ITM.
- Expected daily move ≈ `NIFTY × (VIX/100) / √252`.

---

## Module map

```
data_fetcher.py    NSE/Yahoo fetch + cache (option chain, index history)
nse_live.py        Live NSE via Playwright browser (encrypted API workaround)
live_feed.py       Live tick-by-tick via NSE official streamer WebSocket
oi_intel.py        OI walls, build-up, PCR, max pain, Murarkar matrix
institutional.py   FII/DII cash + participant OI + margin-CE read
stock_flow.py      Nifty 50 accumulation scan
regime_filter.py   4-regime gate + India VIX premium regime + hard risk rules
premium_seller.py  Iron condor backtest (VIX + regime gated)
indicators.py      Indicator computation
strategies.py      Strategy library + parameter grids
backtester.py      Backtest engine (Black-Scholes premium / underlying)
multitf.py         Multi-timeframe backtesting grid
ml_engine.py       Meta-blender (context only — see ML findings)
sentiment.py       Global risk + domestic positioning scoring
market_brain.py    Trader-style reasoning/knowledge engine
timing.py          Trade timing, gap scenarios, session logic
web_research.py    Live market cues via web search
global_data.py     Global data (USDINR, US indices, commodities, FII/DII)
agent.py           Live market agent (integrates everything)
trainer.py         Walk-forward self-training loop
greeks.py          Black-Scholes Greeks + IV analytics
report.py          Markdown report generation
main.py            CLI entry (fetch-data / research / report / all)
build_data.py      One-shot data cache builder
daily_report.py    Combined daily report (+ --blog flag)
blog_post.py       Blog post + index generator
```

---

## CLI reference (`main.py`)

```
python main.py fetch-data    download NIFTY history + option chain
python main.py research      backtest strategy grid, write reports
python main.py report        market snapshot report (uses latest cached chain)
python main.py all           full pipeline
```

`main.py report` reads the most recent option-chain snapshot from
`data/oi_snapshots/` (fallback: legacy `data/option_chain.json`) so it works
out of the box after `python build_data.py`.

---

## Owner instructions

`OWNER_INSTRUCTIONS.md` records the project owner's requirements and trading
philosophy (risk rules, VIX regime matrix, ML honesty, data-pipeline rules,
live-tick source). Read it before making changes — it defines *why* the code
is the way it is.

---

## Data cache

Everything is cached in `data/` on first fetch — scripts **never re-download
the same data** in a run (this keeps it fast, free, and repeatable):

```
data/nifty_history.csv      Nifty 50 daily history
data/india_vix.csv          India VIX daily history (Yahoo ^INDIAVIX)
data/stocks/<SYM>.csv       Per-stock daily OHLCV (all Nifty 50)
data/fii_dii_history.csv    FII/DII cash + F&O participant OI history
data/oi_snapshots/          Daily option-chain snapshots (JSON + CSV)
data/tf_scan.csv            Multi-timeframe strategy grid results
```

To refresh everything: `python build_data.py`.

---

## Live data notes

- **Option chain (snapshot)**: `nse_live.fetch_option_chain_live()` uses
  headless Chrome because NSE encrypts its API payloads — the browser's own
  JS runs the decryption. Works for any index/equity.
- **Tick-by-tick**: `python live_feed.py NIFTY 60` streams live quotes from
  NSE's official WebSocket (`wss://streamer.nseindia.com/streams/fo/mbp`).
  Free, no broker. **Only during market hours** (09:15–15:30 IST) — NSE
  pushes nothing when the market is closed.
- The old `webstream.nseindia.com` endpoint is dead — don't use it.

---

## Auto-posting (Hermes cron)

The project can auto-generate and post the daily report on a schedule using
[Hermes](https://github.com/anomalyco/opencode) cron:

- Job runs weekdays 16:30 IST
- Wrapper: `scripts/daily_report.py` → runs `blog_post.py` → writes
  `blog/posts/<date>.html` + regenerates `blog/index.html`

You can wire any scheduler (Windows Task Scheduler, cron, etc.) the same way:

```
python blog_post.py   # one post per day, overwrites today's post
```

---

## Customising

- **Symbols**: `nse_live.SYMBOLS` — edit to change the stock scan universe.
- **Regime thresholds**: `regime_filter.py` — HV/ADX/BB-width cutoffs.
- **Risk rules**: constants in `regime_filter.py` (risk per trade, daily/weekly
  loss limits, ATR stop multiplier). These are intentionally hard.
- **Premium seller**: `premium_seller.py` — spread width, VIX window, exits.

---

## Known limits / honest notes

- **ML has no standalone edge.** The meta-blender runs ~51% vs ~52% baseline
  out-of-sample. It is used only as a context/agreement counter, never as a
  buy/sell trigger. Don't retrain repeatedly chasing edge — it overfits.
- NSE free APIs are unofficial; NSE can change/break them. Playwright is the
  resilient fallback for the option chain.
- Yahoo intraday range caps: 15m/30m ≤ 60 days, 60m ≤ 90 days, daily ≤ 730 days.
- Backtests use Black-Scholes model premium — slippage/impact not modelled.

---

## License

Educational use. Data © respective exchanges (NSE/Yahoo). Use of NSE data is
subject to NSE Terms of Use. No warranty, use at your own risk.
