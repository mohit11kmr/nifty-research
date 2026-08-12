---
description: Full market snapshot — regime, VIX, OI intel, gamma, FII/DII, technicals ek hi call me.
agent: build
---

Generate the complete market snapshot:

1. Call `nifty-trader` MCP `market_snapshot` — regime gate, VIX zone, chain intel (PCR/max pain/walls/Murarkar), gamma flip, FII/DII, technicals.
2. Call `expected_move` and `expiry_status` for range + expiry context.
3. Call `precision_signal` for the confluence verdict.

Summarize in the trade-setup output format with a conviction score. If regime is RANGE_LV, verdict is NO TRADE.
