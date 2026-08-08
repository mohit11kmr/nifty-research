# Full Session Export — Nifty Research

> Complete conversation/session export with the AI agent.
> Timestamp: 2026-08-08 19:20 IST. Repo: `C:\Users\Mohit\nifty-research`
> GitHub: `https://github.com/mohit11kmr/nifty-research` (branch `master`)

---

## 1. Project origin (beginning of session)

Owner's goal: a **Nifty options intelligence + research toolset** for NSE
(Nifty 50 / Bank Nifty), built around **Nitin Murarkar-style OI + institutional
flow logic**, plus a strategy research/backtest pipeline.

Key owner instructions captured along the way:
- "Project ko powerful aur profitable banao."
- "Tum kuch bhi research nahi kar rahe ho" → do deep research and apply it in code.
- "0 loss" honest stance — impossible to guarantee; minimize losses.
- Work in Hinglish.
- Honest reporting always (no fake edges).

---

## 2. Architecture built

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

## 3. Data pipeline rules (established)

1. **No repetitive work.** Cache data to `data/` on first fetch; read from cache
   afterward. Never re-download the same data in a run.
2. Build data first (`python build_data.py`), then analyze.
3. Option-chain snapshots saved as `data/oi_snapshots/<SYM>_<DATE>.csv`.
4. Full Python path required (plain `python` lacks pandas):
   `C:\Users\Mohit\AppData\Local\Programs\Python\Python312\python.exe`

---

## 4. Risk rules + VIX regime matrix (hard, non-negotiable)

- Risk per trade: 1% of capital.
- Daily loss limit: 3%. Weekly loss limit: 7%.
- Stop: 1.5× ATR.
- VIX premium regime matrix:
  - VIX LOW/NORMAL + trending = trade.
  - VIX LOW + RANGE_LV = **NO_TRADE**.
  - VIX HIGH = smaller size / defined-risk only.
  - VIX > 25 = wait for mean reversion.
- Premium seller edge only 60–75% of the time (when IV is rich); 0-loss isn't
  possible — losses are capped by hard rules.

---

## 5. Session work item by item

### 5.1 Blog index sort fix
- Problem: base post (plain date) sorted as newest.
- Fix: datetime sort key `stem[:10]T{stem[11:15] or '0000'}`.
- Verified newest-first in browser.

### 5.2 Max pain bug (important)
- `oi_intel.py:pcr_and_pain` had **two bugs**:
  - CE/PE payoff formulas swapped (calls pay `max(0, K - s)`, puts pay `max(0, s - K)`).
  - Used `argmax` instead of `argmin` (max pain = strike with LEAST total payout).
- Was 22650 (1900 pts off) → fixed to 24600 (near spot, aligns with CE wall).
- Verified in blog post + daily report.

### 5.3 Blog duplicate posts
- Problem: `blog_post.py` created timestamped duplicate posts every run.
- Fix: one post per day, overwrite `blog/posts/<date>.html`.
- Cleaned 8 test posts → 1.

### 5.4 Live tick data (no broker)
- Owner asked for tick-by-tick data without a broker account.
- Reverse-engineered NSE official streamer WebSocket from `option-chainstream.js`:
  - Endpoint: `wss://streamer.nseindia.com/streams/fo/mbp?symbol=<SYM>&expiry=<DATE>`
  - Old `webstream.nseindia.com` is DEAD (DNS doesn't resolve).
- Created `live_feed.py` — connection tested OK; Saturday market closed → 0
  messages (expected). `_current_expiry` resolves via contract-info API
  (11-Aug-2026 verified). Graceful connection-close handling.
- **Only works during market hours 09:15–15:30 IST.**

### 5.5 Git setup
- No repo existed → `git init`.
- Identity: `mohit11kmr` / `97218605+mohit11kmr@users.noreply.github.com`.
- `.gitignore`: `__pycache__/`, `*.pyc`, `.playwright-mcp/`.
- Remote added: `https://github.com/mohit11kmr/nifty-research`.
- Branch is `master` (first push to `main` failed).
- Commits: `2e686db` (toolset, 102 files), `d314ec6` (README + requirements).

### 5.6 Full project audit (most recent work)
- All 21 modules import cleanly.
- `websearch` import in `web_research.py` is an injected agent tool, gracefully
  caught — NOT a missing dependency.
- Verified functional: `main.py research/report`, `daily_report.py`, `blog_post.py`,
  `regime_filter.trade_plan()` (RANGE_LV → NO_TRADE, VIX 12.16 NORMAL),
  `stock_flow.scan_universe()`, `institutional.institutional_scan()`,
  `ml_engine.meta_blender()` (acc 0.514 vs baseline 0.521, f1 0.556, n 280),
  `premium_seller.premium_sell_backtest()` (P&L +225,622, win 72.5%, PF 2.6,
  maxDD −33.61%), `global_data.fetch_global_snapshot()` (11 markets).
- `oi_intel.format_matrix` is unreferenced (dead code).

### 5.7 Bugs found + fixed in audit
- `nse_live.py:58` — leftover `or True` → always reloaded page. Fixed to
  `if time.time() - _cache["last"] > 60:` (60s cache).
- `main.py` report — expected legacy `data/option_chain.json`; now loads latest
  `data/oi_snapshots/*.csv` with fallback. Added `import glob`. Verified runs.

### 5.8 OWNER_INSTRUCTIONS.md
Recorded the owner's text instructions (10 sections):
1. Deep research philosophy
2. Powerful + profitable
3. 0-loss honesty
4. Hard risk rules
5. VIX regime matrix
6. Data pipeline rules
7. Hinglish communication
8. ML honesty
9. Blog/automation
10. Live tick source

### 5.9 README.md update
- CLI reference (`main.py` commands), owner-instructions pointer, verified state.

### 5.10 AGENTS.md update
- Top pointer: "First read `OWNER_INSTRUCTIONS.md`" — source of truth for *why*
  the code exists; AGENTS.md is operational memory for *how* to work.

### 5.11 conversation_log.md (previous export)
- Covered only the audit session; now superseded by this full export.

---

## 6. Final commit + push

- Commit `9d8a412`: "Full project audit: fix nse_live reload bug + main.py chain
  path, add OWNER_INSTRUCTIONS.md, update README + AGENTS.md"
- Commit `ce567ae`: "Add conversation log (session export)"
- Pushed `origin master`.

---

## 7. Key gotchas / lessons (don't re-learn these)

- **Max pain**: calls pay `max(0, K - s)`, puts pay `max(0, s - K)`,
  answer = argmin of total payout on ATM band (spot ±8%). Never argmax.
- **Blog dedupe**: one post per day, overwrite `blog/posts/<date>.html`.
- **Live feed**: NSE streamer only market hours; outside hours connects then NSE
  closes it (0 messages is normal). Old webstream endpoint is dead.
- **Python**: always full path `C:\Users\Mohit\AppData\Local\Programs\Python\Python312\python.exe`.
- **Git**: branch is `master`, not `main`. Push: `git push origin master`.
- **ML**: meta-blender has no standalone edge (~51% vs ~52% baseline). Context only.
- **requirements.txt**: `scikit-learn` (imported as `sklearn` — normal naming).
- **Hermes cron** `6005919dce97`: weekdays 16:30 IST, wrapper
  `C:\Users\Mohit\AppData\Local\hermes\scripts\daily_report.py`, next run
  2026-08-10T16:30:00+05:30.

---

## 8. Next steps (suggested)

1. **Deep research → edge**: validate Murarkar OI walls/build-up + institutional
   flow edge (owner's top priority).
2. **Live tick verify**: `live_feed.py` on Monday 2026-08-10 09:15 IST with real ticks.
3. **Any new feature/strategy** the owner requests.
