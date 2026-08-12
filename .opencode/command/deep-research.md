---
description: Run an exhaustive Deep Quantitative Research Sweep on any market topic using all MCP servers.
agent: build
---

Perform an exhaustive quantitative research sweep on: $ARGUMENTS

1. Use `nifty-trader` MCP tools (`market_snapshot`, `option_chain_intel`,
   `gamma_flip_intel`, `technical_consensus`, `institutional_flow`,
   `super_ai_ml_context`) for project data.
2. Use `fetch` and `playwright` MCP servers to scrape live market data & headlines.
3. Query `data/research.db` via `sqlite-nifty` MCP for historical tick patterns.
4. Run `python3 live_trader_brain.py` for the master quantitative verdict.
5. Output a detailed research report with equations, risk rules and trade levels.

Honesty: report ML accuracy AND baseline AND edge (no standalone ML edge exists).
