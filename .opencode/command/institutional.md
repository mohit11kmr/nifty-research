---
description: FII/DII institutional flow — cash + F&O positioning aur sentiment read.
agent: build
---

Analyze institutional flows:

1. Call `nifty-trader` MCP `institutional_flow` — FII/DII cash + futures/options positioning.
2. Call `market_snapshot` for the regime context.
3. If available, read `results/web_cues.json` for manual FII/news cues.

Output: FII/DII net direction, institutional bias vs regime, and what it means for the setup (confirms or conflicts). Hinglish me.
