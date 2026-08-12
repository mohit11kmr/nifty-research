---
description: Capital Guard risk audit — 3% kill-switch, 0DTE expiry trap, event risk, 1% position sizing check.
agent: build
---

Run a Capital Guard risk audit using `nifty-trader` MCP tools:

1. Call `capital_guard_audit` — daily kill-switch, expiry 0DTE trap, event-risk, drawdown de-risking, 1% position sizer.
2. Call `expiry_status` — is today expiry day (13:30 cutoff active?).
3. Call `broker_status` with area=positions if the user wants live exposure check.

Output a RISK VERDICT:
- APPROVED → trading allowed, with 1% lot sizing
- RESTRICTED → which rule triggered (kill-switch / expiry trap / event risk)
- STOP TRADING → hard warning, no new setups
