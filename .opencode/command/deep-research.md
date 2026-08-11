---
description: Run an exhaustive 2026 Deep Quantitative Research Sweep on any market topic using all MCP servers.
agent: build
---

Perform an exhaustive quantitative research sweep on: $ARGUMENTS

1. Use the `fetch` and `playwright` MCP servers to scrape latest live market options data & headlines.
2. Query `data/research.db` via `sqlite-nifty` MCP to analyze historical tick patterns.
3. Run `python3 /home/mohit/Desktop/nifty-research/live_trader_brain.py` to obtain master quantitative verdict.
4. Output a detailed 500-line Deep Research Report with mathematical equations, risk rules, and trade levels.
