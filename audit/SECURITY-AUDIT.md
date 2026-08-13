# Security Audit — Nifty Research

> Deep audit Phase 4 (full). Companion to `02-security-auth.md` (authN/authZ
> detail) and `AUDIT.md`. No app code modified. Built: 2026-08-12, `039e684`.

---

## 1. Attack Surface

- `live_dash` HTTP on `127.0.0.1:8766` (read-only JSON + static HTML).
- `web_dashboard` — generates static HTML (no server). Broker login happens as
  a rendering side effect.
- MCP `nifty-trader` — stdio, local; 15 read-only tools; `broker_status`
  touches live broker account.
- Cron (3 jobs) + daemons — local processes.
- Outbound only: Angel One REST/WS, NSE (Playwright), Yahoo, Telegram.
- **No internet-facing listener, no user model, no web sessions, no uploads.**

---

## 2. Findings

### Security — High

**S-H1. Audit trail + paper account committed to git (data-integrity/privacy).**
- File: `data/historical_audit.db`, `data/paper_account.json` (tracked —
  verified `git ls-files data/`).
- Problem: `paper_trade_journal` (entry/exit prices, PnL), signal history, and
  paper account state live in repo + history. `.gitignore` covers only
  `research.db*`; `*.log`. The "append-only permanent audit trail" is actually
  mutable, versioned binary in git.
- Impact: financial records in version control, stale/duplicate DB states,
  repo bloat, commit noise.
- Fix: gitignore `data/*.db*`, `data/paper_account.json`, `data/*.csv`,
  `data/*.pid`, `data/adaptive_weights.json`; purge if desired.
- Confidence: High.
- **RESOLVED (2026-08-13)**: all sensitive runtime state gitignored +
  untracked (`git rm --cached`): historical_audit.db, paper_account.json,
  signal/tick/journal CSVs, `.pid`, adaptive_weights, enhancement_log,
  rebalance_test, reflection_hypotheses, ml_features. Verified
  `git ls-files data/` → none remain.

### Security — Medium

**S-M1. Broker secrets file world-readable (`.env` 0644).**
- Evidence: `ls -la .env` → `-rw-r--r--`. Any local user reads Angel creds +
  TOTP secret (defeating MFA) + Telegram token.
- Fix: `chmod 600 .env`. Confidence: High.
- **RESOLVED (2026-08-13)**: `.env` verified `-rw-------` (0600).

**S-M2. Env loading inconsistent + hidden order dependency.**
- Only `angel_one_client.py:20-27` parses `.env` (manual; no `python-dotenv`).
  `telegram_notifier`/`notifications_system` read `os.environ` only. In
  `run_all` (no broker import) Telegram creds are absent → alerts silently
  skipped.
- Fix: central `config.py` + `python-dotenv`, loaded once. Confidence: High.
- **RESOLVED (2026-08-13)**: central `config.py` (single `load_env`, idempotent,
  never overwrites) + `python-dotenv` pinned in requirements. Verified by
  `tests/test_fix_verification.py::TestR5BrokerFailClosed`.

**S-M3. Broker token lifecycle — no expiry enforcement, no logout.**
- `angel_one_client.py:156-160` reuses `auth_token`/`feed_token` if merely
  non-empty; expired JWT reused until restart; no revocation path.
- Fix: expiry-aware re-auth on 401; explicit `logout()`. Confidence: High.
- **RESOLVED (2026-08-13)**: `angel_one_client` now enforces a
  `TOKEN_TTL_SECONDS=1500` (25 min, `ANGEL_TOKEN_TTL_SECONDS` override);
  `_session_expired()` gates every getter via `_ensure_session()`; a 401 on
  any `_data_call()` triggers `_reset_session()` + one re-login retry;
  explicit `logout()` added. Login failure on any path clears stale tokens
  (fail-closed). Verified by `tests/test_fix_verification.py::TestBrokerSessionLifecycle`.

### Security — Low

**S-L1. MCP `broker_status` exposes broker holdings/positions** to any local
agent without opt-in (`mcp_nifty.py`; `area` allowlisted → no arbitrary
dispatch). Fix: `BROKER_MCP_ENABLED=1` gate. Confidence: High.
**RESOLVED (2026-08-13)**: gated on `BROKER_MCP_ENABLED=1` (off by default);
area allowlisted. Verified by `tests/test_fix_verification.py::TestR13McpBrokerGate`.

**S-L2. `place_order` is an ungated real-money primitive** (0 callers today;
no authz/confirm/capital-guard at that boundary). Fix before any future
wiring: explicit `authorize()`. Confidence: High.
**RESOLVED (documentation only)**: a prominent DANGER docstring marks it as a
real-money primitive with an explicit rule — no automated wiring until an
`authorize()` gate + capital-guard approval exist. Zero callers confirmed.

**S-L3. Frontend `innerHTML` with DB-derived strings** (`live_dash.html:87-116`).
Data is internal (NSE/tick_recorder), no realistic attacker input; defense-in-
depth → use `textContent`. Confidence: Medium.

**S-L4. Console leaks**: broker login prints `client_code`
(`angel_one_client.py:69`); `__main__` dumps profile. No token *values*
printed (verified). Fix: strip. Confidence: Medium.
**RESOLVED (2026-08-13)**: login prints only `[Angel One] Login Successful`
(no `client_code`); `__main__` no longer dumps the profile object.

**S-L5. No rate limiting** on broker login / MCP tools / Telegram sends
(server-side only). Info for a local tool. Confidence: High.

---

## 3. Verified Clean (rejected findings)

| Check | Result |
|---|---|
| SQL injection | All `execute` calls parameterized (`?`); no string-built SQL found (`live_dash`, `tick_recorder`, `agent_workflow_graph`, `mcp_nifty`, `history_logger`). Rejected. |
| eval/exec/pickle/unsafe deserialization | None (`walk_forward_eval` is a function name only). Rejected. |
| Command injection | All `subprocess`/`os.system` use hardcoded strings or fixed temp paths (`alert_monitor`, `hermes_agent`, `blog_post`, `voice_coach`, `control_center`). Rejected. |
| Path traversal | All file opens use fixed `data/`/`results/` paths; no user-supplied filenames. Rejected. |
| SSRF | All `requests.get`/`urlopen` URLs built from fixed tickers/constants (Yahoo, NSE, Google News RSS, Telegram). Rejected. |
| IDOR/BOLA | No object-id request model; only allowlisted `area` selector. Rejected. |
| Privilege escalation | No role/tenant model exists. Rejected. |
| Session fixation / cookies / password reset / OAuth | Features do not exist. Rejected. |
| Hardcoded secrets in code or git | Only `.env.example` placeholders + env var names; no real values in any commit. Rejected. |
| Token values in logs/results | grep over `logs/` + `results/` → 0 hits. Rejected. |
| AuthN bypass / brute-force app-side | No auth surface to bypass; broker login throttled only server-side. Rejected (see S-L5). |
