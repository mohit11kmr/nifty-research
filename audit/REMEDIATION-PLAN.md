# Remediation Plan — Nifty Research

> Deep audit Phases 15 (risk matrix) + 16 (remediation order). No app code
> modified yet — this is the plan. Built: 2026-08-12, `039e684`.
> EXECUTION STATUS (2026-08-13): R1, R2, R3, R4, R5, R6, R8, R10, R11, R12,
> R13 **DONE**; R14 **PARTIAL**; R15 **PARTIAL** (access log + README done,
> frontend error states deferred); R7, R9 **OPEN** (deferred major refactors).
> QA-M3 (inside R10) **REJECTED — false positive** (NIFTY strike grid is 50,
> verified against live snapshots). PF-M2 **ACCEPTED** (1.4 ms snapshot parse
> measured); PF-M3 **DONE** (vectorized, ~29×).
> Regression gate: `test_all.py` 34/34 OK + `tests/` discovery 45/45 OK
> (`test_fix_verification.py` 29/29) + venv `pip-audit` → no known
> vulnerabilities.

---

## 1. Risk Matrix

| ID | Finding | Severity | Likelihood | Impact | Priority |
|---|---|---|---|---|---|
| QA-H1 | Fabricated confluence in `precision_signals` (Layers 3 + capital) | High | High | High | P0 |
| QA-H2 | `capital_guard` sizer floors at 1 lot → breaks 1% cap | High | Medium | High | P0 |
| S-H1 | Audit trail + paper account committed to git | High | High | Medium | P0 |
| PF-H1 | Dashboard full-scans 1.21M-row ticks table | High | High | Medium | P0 |
| PF-H2 | `research.db` unbounded growth (191 MB) | High | High | Medium | P0 |
| QA-M1 | Hardcoded spot/vix reported as live on failure | Medium | Medium | Medium | P1 |
| QA-M2 | Options layer bypass via `vix > 16.0` | Medium | Medium | Medium | P1 |
| QA-M3 | Strike rounding → non-existent strikes | Medium | Medium | Medium | P1 |
| QA-M4 | SL = 50% premium default (not ATR); silent exception swallow | Medium | Medium | Medium | P1 |
| QA-M5 | `history_logger` per-call connects + no locking | Medium | Medium | Medium | P1 |
| S-M1 | `.env` 0644 world-readable | Medium | Low | High | P1 |
| S-M2 | Env loaded only in broker module | Medium | High | Medium | P1 |
| S-M3 | Broker token expiry not enforced | Medium | Low | Medium | P1 |
| M9 | `requests 2.31.0` CVE-2024-35195 | Medium | Low | Low | P1 |
| M10 | No backups of DBs / paper account | Medium | Low | High | P1 |
| M8 | Cron + daemon concurrent artifact writes | Medium | Medium | Medium | P2 |
| P1/P2 | God orchestrator / no data-access layer / dup logic | Medium | High | Medium | P2 |
| S-L1 | MCP `broker_status` no opt-in | Low | Low | Low | P2 |
| S-L2 | `place_order` ungated primitive | Low | Low | High | P2 (before wiring) |
| L-items | README stale, no access logs, log rotation | Low | High | Low | P3 |

Priority = Likelihood × Impact (practical interpretation). P0 = fix first.

---

## 2. Remediation Plan (Phase 16 order)

### 1. Critical data-integrity

**R1 — Fix `precision_signals` fabricated confluence (QA-H1)**
- **Fix**: real `market_brain.make_verdict(df, row, ...)` from real df/row
  (or honest `NOT_COMPUTED`); pass real `daily_pnl` into
  `full_capital_safety_audit`; drop hardcoded "100% Risk Compliant".
- **File**: `precision_signals.py:66-79`.
- **Dependency**: market_brain / capital_guard API; none external.
- **Regression risk**: signal outputs change shape → update `signal_history`
  consumers (history_logger) + tests.
- **Required tests**: precision_signals with NO data → `NO_SIGNAL`; with
  fabricated defaults absent; capital layer reflects real pnl.
- **DONE (2026-08-13)** — verified by `TestR1PrecisionHonestConfluence`
  (score == PASSED-layer count, honest statuses only, A+ requires regime).

**R2 — Gitignore + (optionally) purge tracked state (S-H1)**
- **Fix**: add to `.gitignore`: `data/*.db*`, `data/paper_account.json`,
  `data/*.csv`, `data/*.pid`, `data/adaptive_weights.json`,
  `data/enhancement_log.json`, `data/oi_snapshots/`. If desired,
  `git rm --cached` the state files.
- **File**: `.gitignore`.
- **Regression risk**: none (files still present locally).
- **Required tests**: `git status` clean for a fresh data build.
- **DONE (2026-08-13)** — sensitive state gitignored + `git rm --cached`;
  `git ls-files data/` shows none remaining.

### 2. Critical business-logic bugs

**R3 — Remove 1-lot floor in position sizer (QA-H2)**
- **Fix**: `allowed_lots = int(adjusted_risk_cap / risk_per_lot)` (no `max(,1)`)
  and add `status: BLOCKED` when `allowed_lots == 0` or not compliant.
- **File**: `capital_guard.py:105-118`.
- **Regression risk**: existing callers expecting ≥1 lot must handle 0.
- **Required tests**: cap < risk_per_lot → 0 lots + BLOCKED; cap ≥ risk → N
  compliant lots.
- **DONE (2026-08-13)** — floor removed; sub-lot/invalid-SL → `TRADE_BLOCKED`;
  ATR structure SL surfaces `derivation_error`. Verified by `TestR3CapitalGuard`.

### 3. Production reliability / security

**R4 — Backups + log hygiene (M10, L9, S-M3, S-M1)**
- **Fix**: small backup script (sqlite `.backup` of both DBs + copy of
  paper_account.json into `backups/YYYYMMDD/`); daily via existing cron;
  `chmod 600 .env`; expiry-aware broker re-auth.
- **Files**: new `backup_data.py`; `.env`; `angel_one_client.py:156-160`.
- **Required tests**: backup script smoke run; token re-login on 401.
- **DONE (2026-08-13)**: `.env` chmod 600 ✓ (`-rw-------`). New
  `backup_data.py` — `sqlite3 .backup` of both DBs + copy of paper account /
  CSV / JSON state into `backups/YYYYMMDD-HHMM/`, mandatory `verify_backup()`
  (integrity_check + row-count parity), `--keep N` pruning, `--dry-run`.
  Real run backed up 7 files; restored row-counts match live + integrity ok.
  S-M3 (token expiry) done separately — see below. Verified by
  `TestBackupScript`.

**R5 — Central config + env loading (S-M2)**
- **Fix**: `config.py` with `python-dotenv` load once; modules read from it.
- **Dependency**: add `python-dotenv` to requirements (pin).
- **Required tests**: run_all notifies with real creds (or honest SKIP).
- **DONE (2026-08-13)** — `config.py` (single idempotent `load_env`, never
  overwrites) + `python-dotenv>=1.0.0` pinned; broker manager is fail-closed
  without creds (verified by `TestR5BrokerFailClosed`).

### 4. Performance

**R6 — Fix dashboard index/query + retention (PF-H1, PF-H2, DB-D1)**
- **Fix**: add `day` column (or range index on `recv_ts`), query
  `recv_ts >= datetime('now','localtime','-1 day')`; retention job deleting
  ticks older than N days (rollup to CSV first if wanted).
- **Files**: `tick_recorder.py` (schema), `live_dash.py:76-137`.
- **Regression risk**: index size vs scan savings — measure.
- **Required tests**: explain plan shows index usage; endpoint latency
  regression check; retention job.
- **DONE (2026-08-13)** — zero `date(recv_ts)` wrappers remain; range
  `recv_ts >= datetime('now','localtime','-1 day')` on indexed column;
  `data_retention.py --keep-days 30` (verified by `TestR7DataRetention`).
- **PF-M3** (max pain O(n²)): **DONE (2026-08-13)** — vectorized via numpy
  matrix product + empty-band guard; measured **53.4 ms → 1.87 ms (~29×)**
  on a ~72-strike chain with output parity. Verified by `TestMaxPainParity`.
- **PF-M2** (TTL cache): **ACCEPTED (2026-08-13)** — snapshot parse cost
  measured at **1.4 ms**; caching adds staleness risk for no measurable gain.

### 5. High technical debt

**R7 — `market_state` service (P2/P3, QA-M3)**
- **Fix**: single `get_spot()/get_chain()/get_vix()/get_pcr()` with TTL +
  staleness flag; route the 15 snapshot readers + 4 spot helpers through it.
- **Files**: new `market_state.py`; then `mcp_nifty`, `live_dash`,
  `agent_workflow_graph`, `live_market_fetch`.
- **Required tests**: stale vs live behavior; unit for each helper.

**R8 — Single `chain_metrics()` owner (P4)**
- **Fix**: `data_fetcher.compute_chain_metrics` delegates to `oi_intel` or is
  removed from that path.
- **Required tests**: max-pain/PCR parity test between report paths.
- **DONE (2026-08-13)**: `compute_chain_metrics` delegates pcr + max pain to
  `oi_intel.pcr_and_pain(chain, spot=atm)` (function-level import, no
  circular dep). Verified by `TestChainMetricsParity`.

**R9 — `run_all` declarative pipeline (P1)**
- **Fix**: step registry `[(name, fn, deps)]` + shared context + summary.
  Optional; medium effort.

### 6. Medium / Low cleanup

- **R10** — precision_signals: honest defaults (M1), remove `vix>16` bypass
  (M2), 100-grid strike rounding (M3), ATR-based SL (M4).
  **DONE (2026-08-13)** — M1, M2, M4 fixed; **M3 REJECTED** (strike grid is
  50, not 100 — `precision_signals.py:229-242`, verified vs live snapshots).
- **R11** — `history_logger`: persistent connection + WAL + lock (M5).
  **DONE (2026-08-13)** — single persistent WAL conn + `busy_timeout`; schema
  runs once at init. Verified by `TestR11HistoryLoggerWal`.
- **R12** — `pip install -U requests` + add lock file + formal `pip-audit`
  in disposable venv (M9, DEP-M2).
  **DONE (2026-08-13)** — `requests 2.34.2`, `pip 26.2.1`, `mcp 1.29.0`
  (3 CVEs fixed within `<2.0` pin), `requirements.lock` committed; venv
  `pip-audit` → no known vulnerabilities.
- **R13** — MCP `broker_status` behind `BROKER_MCP_ENABLED=1`; document
  `place_order` as danger primitive (S-L1/S-L2).
  **DONE (2026-08-13)** — gate + allowlist verified by
  `TestR13McpBrokerGate`; `place_order` carries a DANGER docstring.
- **R14** — tests: `regime_filter`, `oi_intel`, `history_logger`,
  end-to-end paper flow, MCP tools, `live_dash` API.
  **PARTIAL (2026-08-13)** — added `tests/test_fix_verification.py`
  (29 tests) covering R1/R3/R4/R5/R7/R8/R11/R13/S-M3/PF-M3. Still missing:
  `regime_filter`, end-to-end paper flow, live-dash API.
- **R15** — access logging on live_dash; README test count fix; frontend
  error/retry states (L7, L9, frontend findings).
  **PARTIAL (2026-08-13)** — `live_dash` access log routed through
  `log_message`; README test section + badge corrected; `.gitignore` adds
  `data/ml_features.csv`, `logs/`, `backups/`. Frontend error/retry states
  deferred (defense-in-depth only).

---

## 3. Sequencing

- **P0 (now)**: R1 → R2 → R3.
- **P1 (this week)**: R4 → R5 → R6 → R10 → R12.
- **P2 (next)**: R7 → R8 → R11 → R13 → R14.
- **P3**: R9 → R15.

Every fix lands with its required test. Full regression gate:
`.venv/bin/python test_all.py` (34) + `python -m unittest discover -s tests` (16).
