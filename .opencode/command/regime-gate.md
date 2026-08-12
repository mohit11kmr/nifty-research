---
description: Regime gate + VIX zone + expected move — market state ka quick check (RANGE_LV = NO TRADE).
agent: build
---

Run the regime gate check using `nifty-trader` MCP tools:

1. Call `regime_trade_plan` — regime (TREND_HV/LV, RANGE_HV/LV), gate, size multiplier, allowed/avoided strategies.
2. Call `vix_intel` — VIX zone (CHEAP/NORMAL/RICH/HIGH/PANIC).
3. Call `expected_move` — expected daily move in points.

Verdict batao:
- RANGE_LV → **NO TRADE** (hard gate)
- Otherwise → allowed strategies + size multiplier, VIX-zone-matched approach
