---
description: Nifty 50 institutional accumulation stock scan (trend + momentum + volume).
agent: build
---

Run the Nifty 50 accumulation scan:

1. Call `nifty-trader` MCP `stock_scan` (default top 8, or top=N for more names).
2. Call `market_snapshot` for market context (regime) so stock picks match the index state.

Output: top accumulation stocks with flow score, trend health, buying period, momentum. Hinglish me, with a note that RANGE_LV index regime = no aggressive stock bets.
