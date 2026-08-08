# Owner Instructions — Nifty Research Toolset

Ye file aapke (project owner) ke saare text instructions aur requirements ki
record hai, jo conversation ke through diye gaye the. Har agent/developer ko
ye READ karna chahiye taaki project ki direction samjhe.

---

## 1. Core philosophy ("Tum kuch bhi research nahi kar rahe ho why")
- **Deep, real research karo** — don't just say "research karenge". Actually
  search the web, verify sources, aur findings ko CODE mein lagao.
- Research findings ko project mein implement karo — warna research bekaar hai.
- Har research conclusion ko `AGENTS.md` mein record karo (research-backed
  strategy matrix) taaki dobara search na karna pade.

## 2. The project must be POWERFUL + PROFITABLE
- Ye sirf toy tool nahi hai — real edge wala research toolset ban raha hai.
- Har module ka objective: ya to profit edge dena, ya loss kam karna.
- Keep everything DATA-BACKED (backtests, statistics) — no vibes-based logic.

## 3. "0 loss technique" — honest stance
- 0 loss **impossible** hai. Ye batao honestly.
- Asli goal: **loss chhota karna** + win rate high karna.
- Research-proven (recorded in AGENTS.md):
  - Option sellers win 60-75% with defined risk (iron condor / short strangle).
  - Option buyers mostly lose to theta — buy only ATM/ITM, never far OTM.
  - Bought options: cut at 40-50% of premium.
  - Sold options: exit if premium doubles from entry or short leg goes ITM.
  - Hard stops, not mental stops.
- Rule: "No clear setup = no trade" — not a suggestion.

## 4. Risk rules (hard, never relax)
- Max 1% of capital per trade.
- Stop = 1.5x ATR below entry (structure-based, not a guess).
- 3% daily loss limit / 7% weekly -> stop trading.
- No averaging down, ever.
- Defined-risk only (spreads/iron condors) — no naked short options advice.
- Expiry day: no new entries after 14:30, square off by 15:05.
- Regime RANGE_LV (low-vol chop) = NO TRADE for directional options.

## 5. India VIX premium regime (research-backed)
- VIX < 12 -> premium cheap -> BUY options.
- VIX 12-16 -> normal -> directional spreads.
- VIX 16-20 -> rich -> START SELLING.
- VIX 20-25 -> high -> sell aggressively (smaller size).
- VIX > 25 -> panic -> mean-revert or sit out.
- Expected daily move = NIFTY x (VIX/100)/sqrt(252).

## 6. Data pipeline rules
- **No repetitive work.** Cache everything to `data/` on first fetch, read
  from cache afterward. Never re-download same data in a run.
- Build data first (`python build_data.py`), then analysis.
- Scripts must be executable end-to-end (`python file.py` should work).
- NSE option chain is encrypted -> use Playwright browser (nse_live.py).
- Yahoo for stocks/intraday/VIX.

## 7. Communication rules
- User communicates in Hinglish (Roman script). Respond in Hinglish.
- Think like a 50-year veteran trader/dev: robust, cached, no wasted API
  calls, edge over flash.
- Loss control is the edge — always surface regime gate + hard risk rules.

## 8. ML honesty
- Meta-blender is ~51% vs ~52% baseline => NO standalone edge.
- Use ML only as context/agreement counter, never as buy/sell trigger.
- Do not retrain repeatedly chasing edge — it overfits.
- Always report accuracy AND baseline AND edge.

## 9. Blog + automation
- Blog auto-posts daily report (blog_post.py) — one post per day.
- Hermes cron job `nifty-daily-report` runs weekdays 16:30 IST.
- Wrapper: `C:\Users\Mohit\AppData\Local\hermes\scripts\daily_report.py`
- Hermes gateway auto-starts on login (Startup folder).

## 10. Live tick data (asked: "data live tick by tick kaha se loge")
- No broker account -> NSE official streamer WebSocket:
  `wss://streamer.nseindia.com/streams/fo/mbp?symbol=<SYM>&expiry=<DATE>`
- Free, no broker, works only during market hours (09:15-15:30 IST).
- Old `webstream.nseindia.com` is DEAD — do not use.
- For full-chain snapshot use nse_live.fetch_option_chain_live (browser).

---

*Last updated: 2026-08-08.* Ye file har code change ke saath current rakhni
chahiye — agar naye instructions milte hain, yahan update karo.
