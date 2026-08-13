# Nifty Research — Full Deep Audit Report

> Deep audit per `OPENCODE_DEEP_AUDIT_MASTER_PROMPT.md`. No app code modified.
> Built: 2026-08-12. Head commit: `039e684`.
> Companion reports: `SECURITY-AUDIT.md`, `ARCHITECTURE-AUDIT.md`,
> `PERFORMANCE-AUDIT.md`, `QA-AUDIT.md`, `DEPENDENCY-AUDIT.md`,
> `REMEDIATION-PLAN.md` (all in `audit/`). Detailed evidence lives there.

---

## 1. Executive Summary

Nifty Research is a single-owner, local-only Python quant toolset (90 .py
files): option/equity/MCX analysis engines + dashboards + a stdio MCP server +
paper-trading automation. It is **well above typical hobby-code health**:
acyclic module graph, parameterized SQL throughout, no eval/exec, no
automated real-order path, honest-data discipline post-`039e684`, 50 tests
green (34 integration + 16 unit).

The material problems are **business-integrity and operational**, not classic
exploits:

1. **Fabricated confluence survives in the signal core** (`precision_signals`
   Layer 3 passes a hardcoded 80% consensus; capital layer always "100% Risk
   Compliant"). A+ signals can be produced from non-real inputs.
2. **The risk sizer guarantees ≥1 lot even when it violates the 1% cap**
   (`capital_guard.compute_position_size`) — the guard defeats its own rule.
3. **Unbounded live DB + full-table-scan dashboard queries** — `research.db`
   is 191 MB / 1.21M tick rows; `/api/ticks` & `/api/chain` scan the whole
   table each request because `date(recv_ts)` defeats the index.
4. **Audit trail + paper account committed to git** — `historical_audit.db`,
   `paper_account.json`, runtime pid files are tracked; financial paper
   records live in repo history.
5. **No backups, no log rotation, Docker is a test-runner only, `.env` is
   world-readable (0644)**, and secrets load only inside the broker module.

Nothing here is a remotely-exploitable critical (no internet-facing
surface, no auth to bypass), so there are **no CRITICAL** findings — the
highest are **HIGH** business-integrity/operational issues.

---

## 2. Project Architecture

See `ARCHITECTURE-AUDIT.md` and `00-project-map.md`. In short: flat 86-file
root; engines read/write shared `data/` (file + SQLite); entry points
compose engines in linear try/except pipelines; `run_all.py` is the god
orchestrator (fan-out 26); 0 circular dependencies; de-facto shared libs are
`regime_filter`/`capital_guard`/`indicators`.

---

## 3. Critical Findings

None.

Rationale: no internet-facing attack surface (localhost/stdio only), no user
model to bypass, no automated real-money path, no injection/SSRF/deserialization
vulnerabilities found (verified, see SECURITY-AUDIT rejected section).

---

## 4. High Findings

| ID | Title | Category |
|---|---|---|
| H1 | `precision_signals` Layer 3 + capital layer fabricate confluence → A+ signals on fake inputs | Business Logic / QA |
| H2 | `capital_guard` position sizer floors at 1 lot, violating its own 1% cap | Business Logic |
| H3 | Dashboard queries full-scan 1.21M-row ticks table; `research.db` unbounded (191 MB) | Performance / DB |
| H4 | Audit trail DB + paper account + runtime pid committed to git | DevOps / Data-integrity |

Details in `QA-AUDIT.md` (H1, H2), `PERFORMANCE-AUDIT.md` (H3),
`SECURITY-AUDIT.md` + `REMEDIATION-PLAN.md` (H4).

---

## 5. Medium Findings

| ID | Title | Category |
|---|---|---|
| M1 | `precision_signals` hardcoded `spot=24500.0`/`vix=12.0` reported as live on data failure | Business Logic |
| M2 | Options layer passes on `vix > 16.0` regardless of PCR alignment (claimed PCR/skew confluence is bypassed) | Business Logic |
| M3 | Strike rounding to nearest 50 can select non-existent NIFTY strikes (24550) | Business Logic |
| M4 | Capital guard SL = 50% of premium default (owner rule is 1.5×ATR); silent exception swallow | Business Logic |
| M5 | `history_logger` opens 2 connections + CREATE TABLE per tick; dual-write SQLite+CSV; no locking; no WAL on audit DB | DB / Concurrency |
| M6 | `.env` 0644; env loaded only in broker module (Telegram creds invisible elsewhere) | Security |
| M7 | Audit DB has no WAL/busy_timeout; concurrent writers risk lock contention | DB |
| M8 | Cron + daemons write same artifacts concurrently, no file locks | DevOps |
| M9 | `requests 2.31.0` — known CVE-2024-35195 (fixed in 2.32.0) | Dependency |
| M10 | No backups of `research.db` / `historical_audit.db` / `paper_account.json` | DevOps |

---

## 6. Low Findings

| ID | Title | Category |
|---|---|---|
| L1 | `precision_signals` SL = 0.8% arbitrary; RR "1:2.0" hardcoded label | Business Logic |
| L2 | `check_expiry_0dte_trap` uses local time, assumes IST TZ | Business Logic |
| L3 | `live_dash._api_status` reads `/tmp/opencode/recorder.pid` unguarded; request logging silenced | API |
| L4 | MCP `broker_status` exposes broker holdings/positions (allowlisted, but no opt-in) | Security |
| L5 | `place_order` ungated real-money primitive (0 callers today) | Security |
| L6 | Frontend renders DB values via `innerHTML` (internal data; defense-in-depth only) | Security |
| L7 | README stale "29/29 tests" (actual 34) | Documentation |
| L8 | Docker `CMD` runs tests only; compose `env_file` = `.env.example` placeholders | DevOps |
| L9 | No health checks, no log rotation, empty logs | DevOps |
| L10 | Client code printed to console on broker login | Security |

---

## 7. Major Risks

1. **Signal-integrity risk (H1)**: paper trades can trigger off fabricated
   confluence → the accuracy-tracking trail (`signal_history`) then records
   fake-confidence entries as if real, poisoning future calibration.
2. **Risk-overrun risk (H2)**: sizing recommendation can exceed 1% cap by
   construction; if ever wired to real orders, over-sizing executes.
3. **Data-loss risk (M10/H4)**: only copies of audit trail + paper account are
   the live DB/JSON + git; no backup/restore procedure.
4. **Degradation risk (H3)**: dashboard latency grows daily; `research.db`
   will hit multi-GB with no retention.
5. **Silent-failure risk (M1/M4/M6)**: engines default to hardcoded values and
   swallow exceptions — bad data looks like good data.

---

## 8. Technical Debt

- 4+ parallel orchestrators (`run_all`, `quant_daemon`, `hermes_agent`,
  `control_center`) drift independently.
- 15 modules each re-implement "read latest OI snapshot"; 4+ "current spot"
  helpers.
- Max-pain/PCR computed twice (`oi_intel` + `data_fetcher`) — dual-bug history.
- 4 live-data ingestion paths (2× yfinance + 2× NSE WS).
- `research.db` binary + CSV + JSON triple-storage of overlapping data.
- No migrations; schemas inline in writers.

---

## 9. Missing Tests (critical flows)

Covered today: 18 engine smoke tests (`test_all`) + greeks/strike/multi-leg
units (`tests/`).

**No tests for**: `regime_filter` (the primary gate — fan-in 11),
`oi_intel` max-pain/PCR, `history_logger` audit writes,
`auto_paper_runner`→`paper_trader` end-to-end flow, all 15 MCP tools,
`live_dash` API endpoints, `institutional`, `mtf_alignment`, `run_all`
orchestration, `data_fetcher`/`backtester`. H1 and H2 are untested.

---

## 10. Scalability Concerns

- `research.db` unbounded tick growth (H3) — the dominant constraint.
- SQLite single-writer; concurrent entry points (cron/daemon/dash) contend.
- Browser-driven NSE fetch per cycle; no serialization lock.
- Sequential 23-step pipeline = slowest-step bound; no parallelism.

---

## 11. Overall Project Health

**8/10.** Strong honesty discipline, clean import graph, safe SQL, real
tests that pass, sensible single-owner boundaries. Dragged down by
business-logic fabrications in the signal core, the risk-sizer floor, data
governance (git-tracked audit DB, no backups), and unbounded live DB.

---

## 12. Recommended Next Steps

1. Fix H1 (real market_brain input + real pnl into capital layer).
2. Fix H2 (remove 1-lot floor; return 0 lots + BLOCKED when cap not met).
3. Fix H3 (date-range index / ISO date prefix + retention policy).
4. Fix H4 (gitignore audit DB + paper account + pid; purge from history if desired).
5. Central `config.py` + `python-dotenv`; `chmod 600 .env`.
6. Add `regime_filter` + `oi_intel` + end-to-end paper-flow tests.
7. Add backups + log rotation; Docker entrypoint to real service.
8. Run `pip install -U requests` (+ full `pip-audit` in a disposable venv).
9. Gate `broker_status` MCP tool behind env opt-in; document `place_order` as
   a danger primitive.
10. Apply `REMEDIATION-PLAN.md` in dependency order.

---

## Security / Architecture / Code / Performance / Testing / Production scores

| Area | Score | Justification |
|---|---|---|
| Security | 8/10 | No exploitable findings; local-only; clean SQL/exec/SSRF. Penalties: `.env` 0644, env-load inconsistency, broker-status exposure, no rate limits, git-tracked financial records. |
| Architecture | 7/10 | Acyclic, focused engines, good boundaries. Penalties: god orchestrator, no data-access layer, 4 parallel orchestrators, fetcher→reporter dependency. |
| Code Quality | 7/10 | Honest-data discipline, parameterized SQL, readable modules. Penalties: hardcoded fallbacks presented as live, risk-sizer floor bug, duplicated logic. |
| Performance | 6/10 | Live DB unbounded + full-table scans per dashboard request; per-call DB connects; browser-per-cycle. No obvious O(n²) in hot paths otherwise. |
| Testing | 6/10 | 50 tests green and meaningful, but primary gate (`regime_filter`), max-pain, audit trail, MCP/API, and end-to-end paper flow untested. |
| Production Readiness | 4/10 | No backups, no log rotation, no health checks, Docker runs tests only, cron uses system python (works), env loading fragile, no monitoring. |
| **Overall** | **6.5/10** | Solid research tool, not production-deployable yet. Highest-value work: signal integrity (H1), risk sizer (H2), DB governance (H3/H4). |
