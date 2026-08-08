# Conversation Log — Nifty Research

> Auto-export of the working session with the AI agent. Timestamp: 2026-08-08 19:15 IST.
> Context: full project audit, bug fixes, instructions file, README update, git setup.

---

## Session summary (what happened)

The owner asked for a full project examination, then for a few follow-ups. The
following work was completed and committed as `9d8a412` (plus earlier commits
`2e686db`, `d314ec6`):

### 1. Blog index sort fix (earlier session, already committed)
- Blog index sorted with a datetime sort key (`stem[:10]T{stem[11:15] or '0000'}`).
- Verified newest-first in browser.

### 2. Max pain bug fix (earlier session, already committed)
- `oi_intel.py:pcr_and_pain` had two bugs:
  - CE/PE payoff formulas were swapped (calls must pay `max(0, K - s)`, puts `max(0, s - K)`).
  - Used `argmax` instead of `argmin` — max pain is the strike with the **least** payout.
- Result: max pain was 22650 (1900 pts off) → fixed to 24600 (near spot, aligns with CE wall).
- Verified in blog post + daily report.

### 3. Blog duplicate posts fix (earlier session, already committed)
- `blog_post.py` was creating timestamped duplicates each run.
- Fixed to one post per day — overwrites `blog/posts/<date>.html`.
- Cleaned 8 test posts → 1. Index shows 1 post.

### 4. Live tick source discovery (earlier session)
- Owner asked for tick-by-tick data without a broker account.
- Reverse-engineered NSE official streamer WebSocket from `option-chainstream.js`:
  - Endpoint: `wss://streamer.nseindia.com/streams/fo/mbp?symbol=<SYM>&expiry=<DATE>`
  - Old `webstream.nseindia.com` is DEAD (DNS doesn't resolve).
- Created `live_feed.py` — connection tested OK; market closed on Saturday so 0
  messages received (expected). `_current_expiry` resolves via contract-info API
  (11-Aug-2026 verified). Graceful handling of connection close.

### 5. Git setup + initial commits
- No repo existed. Ran `git init`. Identity already set:
  - `mohit11kmr` / `97218605+mohit11kmr@users.noreply.github.com`
- `.gitignore`: `__pycache__/`, `*.pyc`, `.playwright-mcp/`.
- Remote: `https://github.com/mohit11kmr/nifty-research` (created by owner).
- Branch is `master` (first push to `main` failed — branch is named `master`).
- Commits: `2e686db` (toolset, 102 files), `d314ec6` (README + requirements).

### 6. Full project examination (this session)
- All 21 modules import cleanly (tested with full Python path).
- `websearch` import in `web_research.py` is an injected agent tool, gracefully
  caught — NOT a missing dependency.
- `python` alias uses wrong interpreter — full path needed:
  `C:\Users\Mohit\AppData\Local\Programs\Python\Python312\python.exe`
- Verified functional:
  - `main.py research` + `report` work; `daily_report.py` works.
  - `regime_filter.trade_plan()` → RANGE_LV → NO_TRADE, VIX 12.16 NORMAL.
  - `stock_flow.scan_universe()` → returns `(top_results, results)` tuple.
  - `institutional.institutional_scan()` → dict with FII/DII + fut data.
  - `ml_engine.meta_blender()` → walk_forward acc 0.514 vs baseline 0.521, f1 0.556, n 280.
  - `premium_seller.premium_sell_backtest()` → IRON_CONDOR, P&L +225,622, win 72.5%, PF 2.6, maxDD −33.61%.
  - `global_data.fetch_global_snapshot()` → 11 markets.
  - `blog_post.py` standalone works.
- All referenced functions exist; `oi_intel.format_matrix` is unreferenced (dead code).

### 7. Bugs found and fixed (this session)
- `nse_live.py:58` — leftover `or True` condition → always reloaded page.
  Fixed to `if time.time() - _cache["last"] > 60:` (60s cache).
- `main.py` report — expected legacy `data/option_chain.json`, now loads latest
  `data/oi_snapshots/*.csv` with fallback. Added `import glob`. Verified runs.

### 8. OWNER_INSTRUCTIONS.md created
Recorded the owner's text instructions from conversation (10 sections):
1. Deep research philosophy ("tum kuch bhi research nahi kar rahe ho")
2. Powerful + profitable ("0 loss" honest stance)
3. 0-loss honesty — impossible, minimize losses
4. Hard risk rules (1% per trade, 3% daily / 7% weekly, 1.5×ATR stop)
5. VIX regime matrix (RANGE_LV = NO_TRADE, seller edge 60–75%)
6. Data pipeline rules (cache, no re-downloads)
7. Hinglish communication
8. ML honesty (no standalone edge, context only)
9. Blog/automation (one post per day, Hermes cron)
10. Live tick source (NSE official streamer WebSocket)

### 9. README updated
- Added CLI reference (`main.py` commands).
- Added owner-instructions pointer.
- Documented verified module status.

### 10. AGENTS.md updated
- Top pointer added: "First read `OWNER_INSTRUCTIONS.md`" — it is the source of
  truth for *why* this code exists; AGENTS.md is operational memory for *how* to work.

### 11. Final commit
- Commit `9d8a412`: "Full project audit: fix nse_live reload bug + main.py chain
  path, add OWNER_INSTRUCTIONS.md, update README + AGENTS.md"
- Pushed `origin master` (d314ec6..9d8a412).

---

## Key gotchas / lessons (don't re-learn these)

- **Max pain formula**: calls pay `max(0, K - s)`, puts pay `max(0, s - K)`,
  answer = argmin of total payout on ATM band (spot ±8%). Never use argmax.
- **Blog dedupe**: one post per day, overwrite `blog/posts/<date>.html`. Plain
  date = midnight sort key.
- **Live feed**: NSE streamer only works market hours 09:15–15:30 IST; outside
  hours it connects then NSE closes it (0 messages is normal). Old webstream is dead.
- **Python**: always use full path
  `C:\Users\Mohit\AppData\Local\Programs\Python\Python312\python.exe`
  — plain `python` has no pandas.
- **Git**: branch is `master`, not `main`. Push with `git push origin master`.
- **ML**: meta-blender has no standalone edge (~51% vs ~52% baseline). Context only.
- **requirements.txt**: uses `scikit-learn` (imported as `sklearn` — normal).

---

## Files created/modified this session

| File | Change |
|------|--------|
| `nse_live.py` | Removed `or True` reload bug; 60s page cache |
| `main.py` | Report loads latest `data/oi_snapshots/*.csv` (legacy fallback) |
| `OWNER_INSTRUCTIONS.md` | New — owner's text instructions (source of truth) |
| `README.md` | CLI reference + owner-instructions pointer |
| `AGENTS.md` | Link to OWNER_INSTRUCTIONS as source of truth |
| `conversation_log.md` | This file — session export |

---

## Next steps (suggested, from owner instructions)

1. **Deep research → edge**: Murarkar OI walls/build-up + institutional flow
   validated edge (owner's top priority).
2. **Live tick verify**: `live_feed.py` on next market day (Monday 2026-08-10
   09:15 IST) with real ticks.
3. **Any new feature/strategy** the owner requests.
