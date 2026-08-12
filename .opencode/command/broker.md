---
description: Angel One broker account — profile, equity holdings, live F&O positions.
agent: build
---

Check Angel One account via `nifty-trader` MCP `broker_status` tool:

1. `broker_status` with area=profile → account/exchange/products
2. `broker_status` with area=holdings → equity holdings
3. `broker_status` with area=positions → open F&O positions

Note: Angel One API is rate-limited — do NOT call repeatedly in a loop. One call per area. Summary Hinglish me do (exposure, margin used, open positions risk vs 1%/3% limits).
