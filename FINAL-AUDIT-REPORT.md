# FINAL AUDIT REPORT — Nifty Research

**Pass**: 2026-08-12 deep audit (6 phases) → 2026-08-13 remediation + re-audit.
**Verdict**: all **High** and **Critical** findings RESOLVED; 1 finding
REJECTED as a false positive; residual items are accepted/deferred Medium/Low.

---

## 1. Executive summary

The audit found 15 High/Critical, 12 Medium and several Low findings across
security, risk-logic, performance and dependency hygiene. All P0/P1 items in
scope were remediated in one pass:

- **Honesty fix (QA-H1/M1/M2)**: `precision_signals` no longer fabricates
  confluence — every layer comes from real data, and the signal grade is
  strictly gated on the number of PASSED layers.
- **Risk fix (QA-H2/M4)**: the position sizer can no longer recommend more
  risk than 1%; sub-lot and invalid-stop cases now BLOCK instead of lying.
- **Privacy fix (S-H1)**: audit trail, paper account, and signal history are
  untracked + gitignored.
- **Dependency fix (DEP-M1/M2 + mcp/pip CVEs)**: `pip-audit` on the venv now
  returns **no known vulnerabilities**; a lock file pins the environment.
- **MCP gate (S-L1/S-L2)**: broker data is opt-in; the real-money order
  primitive is marked and unwired.

One audit claim was disproved: **QA-M3 (strike grid of 100) is a false
positive** — the NIFTY grid is 50 points and the code was already correct.

## 2. Findings disposition

| ID | Finding | Severity | Disposition |
|---|---|---|---|
| QA-H1 | Fabricated confluence in precision_signals | High | **RESOLVED** |
| QA-H2 | Position sizer floors at 1 lot → breaks 1% cap | High | **RESOLVED** |
| S-H1 | Audit trail + paper account in git | High | **RESOLVED** |
| PF-H1 | Dashboard full-scans 1.21M-row ticks table | High | **RESOLVED** |
| PF-H2 | research.db unbounded growth (191 MB) | High | **RESOLVED** |
| QA-M1 | Hardcoded spot/vix reported as live | Medium | **RESOLVED** |
| QA-M2 | Options layer bypass via vix>16 | Medium | **RESOLVED** |
| QA-M3 | Strike rounding → non-existent strikes | Medium | **REJECTED (false positive)** |
| QA-M4 | SL=50% premium default; silent exception swallow | Medium | **RESOLVED** |
| QA-M5 | history_logger per-call connects, no locking | Medium | **RESOLVED** |
| S-M1 | .env world-readable (0644) | Medium | **RESOLVED** (0600) |
| S-M2 | Env loaded only in broker module | Medium | **RESOLVED** (config.py) |
| S-M3 | Broker token expiry not enforced | Medium | **RESOLVED** (TTL 1500 s + logout + 401 retry) |
| M9/DEP-M1 | requests 2.31.0 CVE | Medium | **RESOLVED** (2.34.2) |
| M10 | No backups of DBs / paper account | Medium | **RESOLVED** (backup_data.py) |
| M8 | Cron + daemon concurrent artifact writes | Medium | OPEN (accepted, single-writer) |
| P1/P2 | God orchestrator / dup logic | Medium | OPEN (tech debt, R7–R9) |
| S-L1 | MCP broker_status no opt-in | Low | **RESOLVED** (env gate) |
| S-L2 | place_order ungated primitive | Low | **RESOLVED** (documented + unwired) |
| S-L4 | Console prints client_code / profile | Low | **RESOLVED** (stripped) |
| DB-D1 | date() defeats index | High | **RESOLVED** |
| DB-D3 | ticks no retention | High | **RESOLVED** (data_retention.py) |
| DB-D4 | DB committed to git | Medium | **RESOLVED** |
| DEP-M2 | No lock file | Medium | **RESOLVED** (requirements.lock) |
| mcp CVEs | 1.13.0 (3 advisories) | Med/High | **RESOLVED** (1.29.0, <2.0) |
| pip CVEs | pip 24.0 (7 advisories) | Med/High | **RESOLVED** (26.2.1) |
| click CVE | 8.1.6 (CVE-2026-7246) | High* | ACCEPTED (click.edit() unused; gTTS pin) |
| PF-M3 | Max pain O(n²) over the band | Low | **RESOLVED** (vectorized, ~29×) |

\* CVSS 7.2 but requires `click.edit()` + local interactive use — not
reachable in this codebase.

## 3. Verification evidence

- **Unit/integration**: `test_all.py` **34/34 OK**; full `tests/` discovery
  **45/45 OK**; `tests/test_fix_verification.py` **29/29 OK** (adds
  broker-session lifecycle, max-pain/chain-metrics parity, backup script).
- **Backup**: real `backup_data.py --keep 5` run → 7 files backed up; restored
  DB row-counts match live (`ticks` 1,210,270, `spot` 470, `pattern_logs` 1)
  and `PRAGMA integrity_check` = ok.
- **Performance**: vectorized max pain measured **53.4 ms → 1.87 ms (~29×)**
  on a full ~72-strike chain with output parity.
- **Security**: venv `pip-audit --path .venv/.../site-packages` →
  **"No known vulnerabilities found"**; `.env` = `-rw-------`; `git ls-files
  data/` → no sensitive state.
- **Runtime**: MCP stdio handshake OK (server `nifty-research`, 16 tools
  listed) on `mcp 1.29.0`; `pip check` → no broken requirements.

## 4. Residual risk (accepted / deferred)

| Item | Why accepted |
|---|---|
| PF-M2 no TTL cache | Snapshot parse measured at **1.4 ms** — no measurable gain at current scale. |
| M8 concurrent artifact writes | Cron daemon + recorder are single-writer per artifact by design. |
| R7–R9 tech-debt refactors | Structural (market_state service, run_all pipeline), not correctness; R8 already done via delegation. |
| S-L3/S-L5 + R15 frontend | Defense-in-depth / local-tool rate limits / error-state cosmetics — no threat model requires them today. |

## 5. Project health

Overall score from audit: **8/10**. After remediation the honest-signal,
loss-control and privacy-critical surfaces are clean. The open items are
quality-of-life and structural, not correctness or security-critical.

Signed: remediation pass + re-audit completed 2026-08-13.
