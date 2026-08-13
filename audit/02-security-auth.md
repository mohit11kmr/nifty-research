# Nifty Research — Authentication & Authorization Security Audit

> Scope: authN + authZ only. No app code modified. Built: 2026-08-12.
> Head commit: `039e684`. Method: source trace of every auth path + grep for
> credential exposure across code, git history, logs, results.

---

## 1. Authentication Architecture

This is a **single-owner, local, no-user-account** system. There is no
registration, login page, password reset, email verification, OAuth, or web
session. The application never issues its own credentials. Authentication is
limited to two outbound/integration credentials + one TOTP-MFA broker login:

| Surface | Credential | Mechanism | Where |
|---|---|---|---|
| Angel One broker | `ANGEL_API_KEY`, `ANGEL_CLIENT_CODE`, `ANGEL_PASSWORD`, `ANGEL_TOTP_SECRET` | SmartAPI `generateSession` (password + **TOTP MFA** via pyotp) → in-memory JWT `auth_token` + `refresh_token` + `feed_token` | `angel_one_client.py:29-77` |
| Telegram alerts | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Bot API token in HTTPS URL path (`/bot{token}/sendMessage`) | `telegram_notifier.py:11-28`, `notifications_system.py:18-28` |
| OpenCode MCP | none (local stdio) | two local servers (`nifty-trader` = `.venv mcp_nifty.py`, `git-nifty` = uvx) | `opencode.json` |

**MFA status**: broker login uses TOTP (`pyotp.TOTP(secret).now()` at
`angel_one_client.py:61`) — proper 2nd factor. Positive.

**Secrets storage**: `.env` file, gitignored + untracked, parsed manually by
`angel_one_client.py:20-27` (`os.environ.setdefault`). No secret is written to
any `data/` file, log, report, or commit (verified below). Broker tokens live
only in the process-memory singleton `manager` (`angel_one_client.py:179`).

---

## 2. Authentication Findings

### F1 — Broker secrets file is world-readable
- **File**: `.env` — mode `-rw-r--r--` (0644), 259 bytes.
- **Path**: any local user/process can read Angel One creds + Telegram token.
- **Problem**: standard credential hygiene violated; on a multi-user box or any
  process running as another user, secrets are exposed at rest.
- **Impact**: credential theft → full broker account takeover (TOTP secret also
  readable, defeating MFA).
- **Severity**: Medium. **Confidence**: High.
- **Fix**: `chmod 600 .env` (0400 better). Add `.env` perms note to setup docs.

### F2 — Broker token lifecycle: no expiry enforcement, no logout/revocation
- **File**: `angel_one_client.py` — `auth_token`/`refresh_token`/`feed_token`
  stored on singleton (lines 48-50); `create_websocket` (line 156) reuses tokens
  if merely non-empty (line 158-160) — **expired JWT is reused until process
  restart**; no `logout()` method; refresh token never rotated or revoked.
- **Problem**: daemons (`quant_daemon`, `oi_refresh`+broker calls, `web_dashboard`
  HTML gen) hold a long-lived live-session in memory with no re-auth-on-401 and
  no revocation path. Token reuse risk in long-running processes.
- **Impact**: silent auth failures + a broker session that outlives its useful
  window with no way to invalidate it app-side.
- **Severity**: Medium. **Confidence**: High.
- **Fix**: track token age / on-401 re-login; add explicit `logout()`; treat
  refresh_token as sensitive memory (already not logged).

### F3 — Broker login/console output reveals account identifier
- **File**: `angel_one_client.py:69` prints `Client: {client_code}`; `__main__`
  (line 185) prints `manager.get_profile()` result to stdout.
- **Dependency path**: `python angel_one_client.py` (or cron/daemon stdout
  capture) → console/logs.
- **Problem**: client code (account identifier) and full profile dict can land in
  shell logs. No password/token *values* printed (verified), but profile may
  include account details.
- **Severity**: Low. **Confidence**: Medium (profile response shape is
  broker-defined; treated as containing account data).
- **Fix**: strip account fields from console output; drop the `__main__` dump.

### F4 — Hidden env-loading dependency affects alert auth
- **File**: `angel_one_client.py:20-27` is the **only** `.env` loader
  (`notifications_system.py:19`, `telegram_notifier.py:11` read raw
  `os.environ`; no `python-dotenv` in requirements).
- **Dependency path**: `run_all.py` → `notifications_system.py` — process never
  imports `angel_one_client` ⇒ Telegram creds absent ⇒ alerts **silently
  skipped** (auth not available but failure is invisible).
- **Problem**: same `.env` behaves differently per entry point (architecture
  finding P5, auth consequence here).
- **Impact**: missing notifications with no error surfaced.
- **Severity**: Low. **Confidence**: High.
- **Fix**: central `config.py` + `python-dotenv` loaded once at startup.

### F5 — No app-side brute-force throttling on broker login
- **File**: `angel_one_client.py:53-77` — no sleep/backoff/attempt cap on
  `generateSession`.
- **Problem**: repeated failed logins are not throttled by the app.
- **Impact**: mitigation rests entirely on Angel One server-side rate limits.
- **Severity**: Info. **Confidence**: High.
- **Fix**: (optional) local backoff/jitter between login attempts.

---

## 3. Authorization Architecture

**No RBAC/ABAC/ownership model exists** — authorization is OS/process-level:
whoever can execute code as the owner can do anything. Enforced boundaries:

1. **MCP layer**: 15 read-only tools (`mcp_nifty.py`), stdio only; `_safe`
   wrapper returns `{ok, data|error}`; tool params are limited/validated.
2. **Web layer**: `live_dash.py` binds `127.0.0.1:8766` explicitly
   (`live_dash.py:195`); `web_dashboard.py` writes static HTML (no server).
3. **Order boundary**: `place_order` (`angel_one_client.py:132`) exists but has
   **zero callers** anywhere in the repo (grep-verified) — no automated
   execution path; `auto_paper_runner`/`agent_workflow_graph` write paper
   journals only.
4. **Risk gates** (`capital_guard.py`) are business policy, not authorization —
   applied to paper logic, not to the broker boundary.

### Resource matrix (WHO → CAN DO WHAT → ON WHICH RESOURCE)

| Resource | WHO | CAN DO | Enforcement point |
|---|---|---|---|
| Broker profile/holdings/positions | any local agent/process that imports `angel_one_client` or calls MCP `broker_status` | read | none beyond local process access |
| Broker orders | any local process importing the singleton | place real orders | **none** (method is plain passthrough) — mitigated only by 0 callers |
| Market/chain/regime data | MCP clients, local scripts | read | read-only tool design |
| Telegram channel | any local process importing notifiers | send messages | none (single-owner assumption) |
| SQLite/CSV research data | any local process (same user) | read/write | OS filesystem perms (default 0644/0666) |
| `.env` secrets | any local user | read | OS filesystem perms — **currently 0644** (see F1) |

---

## 4. Authorization Findings

### Z1 — MCP `broker_status` exposes broker account data to any local agent
- **File**: `mcp_nifty.py` `broker_status(area)` → `getattr(manager, "get_"+area)`
  (validated against allowlist `("profile","holdings","positions")`).
- **Dependency path**: OpenCode agent → MCP stdio tool → `angel_one_client.manager`
  → live `login()` if not connected → broker account read.
- **Problem**: the agent-facing read boundary silently includes **live broker
  portfolio/positions** with no explicit opt-in, no per-call confirmation, and
  no separate auth. Any subagent code executed on this machine can pull
  holdings/positions. The `getattr` itself is safe (allowlisted) — the issue is
  data exposure scope, not the dispatch.
- **Impact**: sensitive financial data exposed to the agent layer; repeated
  calls also re-trigger broker logins (rate/availability).
- **Severity**: Low-Medium (single-user local; would become High if MCP were
  ever exposed remotely). **Confidence**: High.
- **Fix**: gate broker tools behind an env opt-in (e.g. `BROKER_MCP_ENABLED=1`);
  keep the allowlist; add explicit wording that this is live broker data.

### Z2 — `place_order` has no authorization layer (latent)
- **File**: `angel_one_client.py:132-154` — direct passthrough to
  `smart_api.placeOrder`; only precondition is an in-memory session.
- **Dependency path**: (none today) — grep shows **0 callers**. If future
  automation imports the singleton and calls it, there is no allow/deny,
  no confirm, no capital-guard gate at this boundary.
- **Problem**: authorization for the highest-privilege primitive is *absent by
  design*; safety currently relies on "nobody calls it".
- **Impact**: if wired later, an accidental/agent-issued order executes with no
  checks (real-money risk).
- **Severity**: Low (latent). **Confidence**: High.
- **Fix**: before any future wiring, add an explicit `authorize()` gate (env
  flag + manual confirm) + `capital_guard` check at this boundary.

### Z3 — Broker login triggered as HTML-rendering side effect
- **File**: `web_dashboard.py:66` `angel_one_client.manager.get_profile()`
  during `generate_live_terminal_html()`.
- **Dependency path**: HTML gen → login() (if no session) → broker API.
- **Problem**: reading/rendering a page causes an auth round-trip; failures are
  swallowed into "Not Connected ⚠️". Not a security hole; availability +
  repeated-login churn.
- **Severity**: Info. **Confidence**: High.
- **Fix**: compute broker status lazily/once per run with TTL.

---

## 5. IDOR / BOLA Findings

**None found.**

- The only user-controllable resource selector in the codebase is
  `broker_status(area=...)` → `getattr(manager, "get_"+area)`; `area` is
  validated against a hard allowlist **before** the `getattr`
  (`mcp_nifty.py`), so no arbitrary method/ObjectID access is possible.
- No request carries object identifiers (ids/uuids) into any data query. MCP
  tools use only scalar limits (`top=`, `limit=`, `symbol=`, `capital=`) with
  no ownership dimension — there are no other users' objects to reach.
- No file-upload handlers, no export endpoints with user-scoped ids.

**Rejected**: BOLA/IDOR — no object reference model exists. Confidence: High.

---

## 6. Privilege Escalation Findings

**None found.**

- No role hierarchy, no admin endpoints, no tenant model → horizontal/vertical
  escalation is not representable in this system.
- Highest-privilege primitive is `place_order` (uncalled). No code path elevates
  a caller's capabilities. `getattr` dispatch (Z1) is allowlisted, not an
  escalation vector.

**Rejected**: privilege escalation — no role system exists. Confidence: High.

---

## 7. Session/Token Findings

- **No cookies, no web sessions** — no session fixation surface.
  Rejected: session fixation (no sessions). Confidence: High.
- **No JWT issued by the app** — JWT is broker-issued, held in-memory only
  (`angel_one_client.py:48-50`), never persisted to disk, never logged.
  Verified: grep of `logs/` + `results/` for `jwt|refreshToken|auth_token` →
  0 hits; git history contains only `.env.example` placeholders + env var
  **names** in source, no real values.
- **Token reuse**: `create_websocket` reuses auth/feed tokens without expiry
  check (F2) — Medium.
- **Token leakage**: no credential values found in console/logs/reports/git
  (except `client_code`/profile print, F3 — Low).
- **Insecure cookies**: N/A.

---

## 8. Rate Limiting Findings

- **No app-level rate limiting anywhere**: broker login (F5), MCP tools,
  Telegram sends, and the two localhost HTTP endpoints have no throttling.
- **Context**: `live_dash` has no auth, so an unauthenticated-rate-limit is not
  applicable; broker/Telegram limits are server-side only.
- **Severity**: Info (local single-user tool; becomes relevant only if any
  surface is exposed beyond localhost).

---

## 9. Confirmed Issues

| # | Issue | Severity | Confidence |
|---|---|---|---|
| F1 | `.env` mode 0644 — broker + Telegram secrets readable by any local user | Medium | High |
| F2 | Broker token lifecycle: expired-token reuse, no logout/revocation | Medium | High |
| Z1 | MCP `broker_status` exposes live broker holdings/positions to agent layer with no opt-in | Low-Medium | High |
| Z2 | `place_order` is an ungated real-money primitive (latent, 0 callers today) | Low | High |
| F3 | Broker login/profile printed to console (`client_code`, profile) | Low | Medium |
| F4 | Telegram creds silently unavailable in `run_all` path (env loaded only in broker module) | Low | High |

---

## 10. Suspected Issues

- **S1**: `web_dashboard` generated HTML (`blog/live_terminal.html`) may embed
  account-identifying fields if Angel profile returns more than the
  Connected/Not-Connected string — static grep of the generator shows only the
  badge, but the produced artifact should be spot-checked. Severity: Info.
- **S2**: Console/cron stdout capture of broker `__main__`/daemon output may
  accumulate account identifiers in `data/*.log` over time — current logs clean
  (verified), but no log-redaction exists. Severity: Low.

---

## 11. Rejected Findings

| Claim | Why rejected | Confidence |
|---|---|---|
| IDOR / BOLA | no object-id request model; only allowlisted `area` selector | High |
| Privilege escalation (horizontal/vertical) | no role/tenant model exists | High |
| Session fixation / insecure cookies | no cookies or web sessions | High |
| Registration / password reset / email verification / OAuth | features do not exist | High |
| Hardcoded secrets in git | only `.env.example` placeholders + env var names; no real values in any commit | High |
| Token values leaked to logs/results | grep across `logs/` + `results/` → 0 credential hits | High |
| `requests.Session` = auth session | these are HTTP client sessions for scraping (data_fetcher, global_data, live_feed), not user auth | High |

---

## 12. Recommended Fixes

1. **F1**: `chmod 600 .env` (0400 recommended); document in setup.
2. **F2**: expiry-aware session handling — check token age, re-login on 401,
   add explicit `logout()`; keep tokens memory-only.
3. **Z1**: gate broker MCP tools behind `BROKER_MCP_ENABLED=1` env opt-in;
   keep the `area` allowlist; never expose broker tools by default.
4. **Z2 (before any future order wiring)**: add `authorize()` gate (env flag +
   manual confirm) + `capital_guard` at the order boundary; treat `place_order`
   as a danger primitive with 0 callers as the invariant.
5. **F3**: remove `__main__` profile dump; do not print `client_code`.
6. **F4**: central `config.py` + `python-dotenv`, loaded once per process.
7. **S1/S2**: log-redaction pass (client_code, tokens) or silent-stderr on
   broker calls; spot-check `blog/live_terminal.html`.

---

AUTH SECURITY AUDIT COMPLETE
