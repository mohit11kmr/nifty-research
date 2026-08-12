---
description: Generate a High-Conviction Trade Setup with Capital Guard Audit, Regime Gate, OI intel and precise strike levels.
agent: build
---

Generate a complete trade setup for $ARGUMENTS using the `nifty-trader` MCP server:

1. Call `market_snapshot` for the full picture (regime gate, VIX zone, chain intel, FII/DII, technicals).
2. Call `expiry_status` and `expected_move` to know expiry day + expected daily range.
3. Call `capital_guard_audit` to verify kill-switch / expiry trap / event risk / 1% sizing.
4. Call `precision_signal` for the 6-layer confluence signal.
5. If the user asked about the broker, call `broker_status` (positions/holdings).

Apply the trade-setup skill's conviction framework. Present:
- Conviction X/5 + regime gate verdict (RANGE_LV = NO TRADE)
- Exact strike levels, stop loss, target 1/2
- Position size in lots (1% capital rule, regime multiplier)
- Hard **STOP TRADING** warning if capital guard or regime blocks it
- ACTION: MANUAL ORDER — Angel One app/web se lagao
