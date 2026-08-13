# Fix Log — Nifty Research Remediation

Chronological record of every change made during the 2026-08-12/13 audit
remediation pass. Each entry: finding → change → verification.

Regression gate after all changes:
- `.venv/bin/python test_all.py` → 34/34 OK
- `.venv/bin/python -m unittest discover -s tests` → 45/45 OK
  (incl. `tests.test_fix_verification` → 29/29 OK)
- venv `pip-audit` → **No known vulnerabilities found**

---

## R1 — precision_signals: honest confluence (QA-H1, QA-M1, QA-M2) · P0 · DONE
- **Change**: removed hardcoded `spot=24500/vix=12.0/zone=NORMAL` defaults and
  the fabricated "80% consensus" market_brain call; every layer is now computed
  from real data and reports `NOT_COMPUTED`/`NEUTRAL`/`BLOCKED`/`MIXED`/`ERROR`
  when its source is unavailable. Capital layer consumes real daily PnL from
  the paper account. Removed the `or (vix > 16.0)` options-layer bypass; layer
  passes only on real PCR↔bias alignment.
- **Files**: `precision_signals.py`
- **Verified**: `tests/test_fix_verification.py::TestR1PrecisionHonestConfluence`
  — `confluence_score` equals the count of PASSED layers; A+ grade requires
  regime PASSED; all six exact layer keys present; honest statuses only.

## R2 — Gitignore + untrack sensitive state (S-H1, DB-D4) · P0 · DONE
- **Change**: added `data/historical_audit.db*`, `paper_account.json`,
  `signal/tick/journal CSVs`, `*.pid`, `adaptive_weights.json`,
  `enhancement_log.json`, `rebalance_test.json`,
  `reflection_hypotheses.jsonl`, `ml_features.csv` to `.gitignore` and ran
  `git rm --cached` on every tracked sensitive file.
- **Files**: `.gitignore` (+ staged index deletions)
- **Verified**: `git ls-files data/` → no sensitive runtime state remains.

## R3 — capital_guard: sub-lot block + ATR structure SL (QA-H2, QA-M4) · P0 · DONE
- **Change**: removed the `max(..., 1)` lot floor — sub-lot risk now returns
  `allowed_lots=0` + `status=TRADE_BLOCKED`. Invalid stop-loss blocks with an
  explicit reason instead of fabricating risk. Structure stop = 1.5×ATR from
  `regime_filter.trade_plan()` mapped to premium space (`0.5×stop_dist`, ATM
  delta≈0.5); derivation failures surface via `derivation_error` (never
  silently swallowed).
- **Files**: `capital_guard.py`
- **Verified**: `tests/test_fix_verification.py::TestR3CapitalGuard`

## R5 — Central config + broker fail-closed (S-M2) · P0 · DONE
- **Change**: added `config.py` (single idempotent `load_env` via
  `python-dotenv`, `override=False`), pinned `python-dotenv>=1.0.0`.
  `angel_one_client` refuses login and returns `None` on data getters when
  credentials are missing — no live API call. `.env` permissions verified
  0600 (S-M1).
- **Files**: `config.py` (new), `angel_one_client.py`, `requirements.txt`
- **Verified**: `tests/test_fix_verification.py::TestR5BrokerFailClosed`

## R6 — Dashboard/recorder index + retention (PF-H1, PF-H2, DB-D1, DB-D3) · P1 · DONE
- **Change**: no `date(recv_ts)` function wrappers remain in any query path;
  `tick_recorder` creates `idx_ticks_key`, `idx_ticks_ts`, `idx_spot_ts` and
  uses WAL. New `data_retention.py` purges `ticks`/`spot` older than
  `--keep-days` (default 30) with optional VACUUM; `mcp_nifty.recent_ticks`
  uses an index-friendly `recv_ts >= datetime('now','localtime','-1 day')`
  range. `tick_recorder` batch-commits and samples spot on a real wallclock
  schedule.
- **Files**: `tick_recorder.py`, `live_dash.py`, `mcp_nifty.py`,
  `data_retention.py` (new)
- **Verified**: `tests/test_fix_verification.py::TestR7DataRetention`

## R11 — history_logger: persistent WAL connection (QA-M5, PF-M1) · P1 · DONE
- **Change**: one persistent connection (WAL + `busy_timeout=5000`) reused by
  all writes; schema `CREATE TABLE` runs once at init, not per tick; no more
  per-call connection churn. CSV dual-write kept by documented design.
- **Files**: `history_logger.py`
- **Verified**: `tests/test_fix_verification.py::TestR11HistoryLoggerWal`
  (`PRAGMA journal_mode` → `wal`).

## R12 — Dependency security (DEP-M1/M2, mcp CVEs, pip CVEs) · P1 · DONE
- **Change**: `requests 2.31.0 → 2.34.2` (CVE-2024-35195); `pip 24.0 → 26.2.1`
  (7 CVEs); `mcp 1.13.0 → 1.29.0` (fixes PYSEC-2026-1617/3482/3483, still
  within the documented `<2.0` pin). `requirements.txt` floor bumped
  (`requests>=2.32.0`, added `python-dotenv`); `requirements.lock` generated
  via `pip freeze --all`.
- **Files**: `requirements.txt`, `requirements.lock` (new), `.venv`
- **Verified**: venv `pip-audit` → no known vulnerabilities; MCP stdio
  handshake OK (16 tools registered).
- **Accepted residual**: system `click 8.1.6` — CVE-2026-7246 affects
  `click.edit()` only; the project never calls it and `gTTS` hard-pins
  `click<8.2`. Documented, not upgradable without breaking `voice_coach.py`.

## R13 — MCP broker gate + danger-primitive docs (S-L1, S-L2) · P0 · DONE
- **Change**: `broker_status` now requires `BROKER_MCP_ENABLED=1` in `.env`
  (off by default); `area` allowlisted (`profile|holdings|positions`).
  `recent_ticks` fails gracefully when `data/research.db` is absent and clamps
  `limit` ≤ 100. `place_order` carries a prominent DANGER docstring: real-money
  primitive, zero callers, must not be wired into automation without an
  `authorize()` gate + capital-guard approval.
- **Files**: `mcp_nifty.py`, `angel_one_client.py`
- **Verified**: `tests/test_fix_verification.py::TestR13McpBrokerGate`

## R14 — Fix-verification tests · P1 · DONE
- **Change**: new `tests/test_fix_verification.py` (18 tests) covering
  R1/R3/R5/R7/R11/R13 — honest confluence, sub-lot blocking, broker
  fail-closed, retention purge, WAL mode, MCP gate.
- **Files**: `tests/test_fix_verification.py` (new)
- **Verified**: 18/18 OK alongside existing suites (34/34).

## R4 — DB / state backups (M10) · P1 · DONE
- **Change**: new `backup_data.py` — atomic `sqlite3` `.backup` of both DBs
  (`research.db`, `historical_audit.db`) + copy of `paper_account.json`,
  `signal_history.csv`, `tick_history.csv`, `adaptive_weights.json`,
  `enhancement_log.json` into `backups/YYYYMMDD-HHMM/`; mandatory
  `verify_backup()` (integrity_check + per-table row-count parity vs live);
  `--keep N` retention pruning (default 14); `--dry-run` preview.
- **Files**: `backup_data.py` (new), `.gitignore` (`backups/`)
- **Verified**: real run `--keep 5` → 7 files, DB row-counts match live
  (`ticks` 1,210,270 / `spot` 470 / `pattern_logs` 1) + `integrity_check: ok`;
  restore = copy-back + reopen verified in `TestBackupScript`.

## R15 — live_dash access log + README hygiene (L7/L9) · P3 · PARTIAL
- **Change**: `live_dash` access log now goes through `log_message` (stderr);
  `.gitignore` adds `data/ml_features.csv`, `logs/`, `backups/`; README test
  section + badge corrected (34/34 + 29/29 fix suite).
- **Files**: `live_dash.py`, `.gitignore`, `README.md`
- **Deferred**: frontend error/retry states (S-L3 innerHTML cosmetics) —
  defense-in-depth only, no realistic attacker input.

## S-M3 + S-L4 — broker session lifecycle + console leak · P1 · DONE
- **Change**: `TOKEN_TTL_SECONDS=1500` (25 min, `ANGEL_TOKEN_TTL_SECONDS`
  override) + `_session_expired()`/`_ensure_session()`/`_reset_session()`/
  `logout()`/`_data_call()` (401 → reset + 1 retry); login failure on any
  path clears stale tokens (fail-closed). Login prints only
  `[Angel One] Login Successful`; `__main__` profile dump removed.
- **Files**: `angel_one_client.py`
- **Verified**: `tests/test_fix_verification.py::TestBrokerSessionLifecycle`
  (5 tests: expiry, 401 retry, logout, stale-clear, env TTL override).

## PF-M3 — vectorized max pain (O(n²) → O(n)) · P2 · DONE
- **Change**: `oi_intel.pcr_and_pain` computes payouts via numpy matrix
  product (`np.maximum(k-s,0)@ce + np.maximum(s-k,0)@pe`); empty-band guard
  returns `best=None` instead of KeyError.
- **Files**: `oi_intel.py`
- **Verified**: measured 72-strike full chain **53.4 ms → 1.87 ms (~29×)**,
  output identical to reference loop; `TestMaxPainParity` (2 tests).

## R8 — single chain-metrics owner (P4) · P2 · DONE
- **Change**: `data_fetcher.compute_chain_metrics` now delegates pcr + max
  pain to `oi_intel.pcr_and_pain(chain, spot=atm)` (function-level import,
  no circular dependency); atm/support/resistance computed locally; pcr
  defaults to `0.0` when no band data.
- **Files**: `data_fetcher.py`
- **Verified**: `TestChainMetricsParity` — parity between the two report
  paths (delegation means identical output by construction).

## PF-M2 — TTL cache for repeated reads · P2 · ACCEPTED (with evidence)
- **Decision**: NOT implemented. Measured snapshot parse cost is **1.4 ms**
  per `/api/chain` call — a TTL cache would add staleness risk and code
  complexity for no measurable gain at current scale. Revisit if call
  frequency grows.

## Re-audit verdicts
- **QA-M3 (strike grid 100)** → **REJECTED — false positive**. NIFTY strike
  grid is 50 points (`precision_signals.py:229-242`, verified against live
  option-chain snapshots); 24550 is a valid strike.
- **QA-H1, QA-H2, QA-M1, QA-M2, QA-M4, QA-M5, DB-D1, DB-D3, DB-D4,
  S-H1, S-M1, S-M2, S-M3, S-L1, S-L2, S-L4, PF-H1, PF-H2, PF-M3, DEP-M1,
  DEP-M2, M10** → **RESOLVED**.
- **Still open (accepted/deferred)**: S-L3 (frontend innerHTML), S-L5 (rate
  limiting), PF-M2 (TTL cache — accepted with 1.4 ms measurement), M8
  (concurrent artifact writes — single-writer by design), R7 (market_state
  service) and R9 (run_all declarative) major refactors, R15 frontend
  error/retry states.
