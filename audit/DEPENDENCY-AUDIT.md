# Dependency Audit — Nifty Research

> Deep audit Phase 12. No app code modified; no packages installed.
> Built: 2026-08-12. Source: `.venv/bin/pip list` + `pip check` + static
> review of `requirements.txt`.

---

## 1. Verification Results

| Check | Result |
|---|---|
| `pip check` (venv) | ✅ "No broken requirements found" |
| `requirements.txt` integrity | Single file, no lock file |
| `pip-audit` run | Not installed; not run (would require installing into the venv — skipped per no-modify rule). **Action**: run `pip install pip-audit` in a disposable venv + `pip-audit` during remediation. |
| Python versions | Docker 3.11-slim · CI 3.11/3.12 · local venv 3.12.3 — drift risk |

---

## 2. Findings

### DEP-M1. `requests 2.31.0` — known CVE (fixed in 2.32.0)
- **Evidence**: `.venv` has `requests 2.31.0` (2023-era). CVE-2024-35195
  (information disclosure via proxy/redirect handling) affects `requests`
  < 2.32.0.
- **Impact**: Low for a local single-user tool, but trivially fixable and it
  is the highest-signal dependency issue found.
- **Severity**: Medium (dependency hygiene). **Confidence**: High.
- **Fix**: `pip install -U requests` (verify behavior, run test suite).
- **RESOLVED (2026-08-13)**: `requests 2.34.2` installed; floor bumped to
  `requests>=2.32.0` in `requirements.txt`.

### DEP-M2. No lock file → non-reproducible installs
- **Evidence**: `requirements.txt` is unpinned (no `==` pins visible in the
  file scan); no `requirements.lock`/`poetry.lock`/`uv.lock`.
- **Impact**: CI vs Docker vs local venv can resolve different versions;
  "works on my machine" drift; the Docker/CI divergence (3.11 vs 3.12) is a
  real example.
- **Severity**: Medium. **Confidence**: High.
- **Fix**: pin versions (or add `uv lock`) + keep Docker/CI/local on one
  Python.
- **RESOLVED (2026-08-13)**: `requirements.lock` generated via
  `pip freeze --all` (full venv snapshot incl. system-site-packages).

### DEP-M3. Latest-major runtime deps (watch items, not bugs)
- `pandas 3.0.0`, `numpy 2.4.2`, `scikit-learn 1.9.0`, `xgboost 3.4.0`,
  `lightgbm 4.7.0`, `optuna 4.9.0` — all current majors. No conflict found by
  `pip check`. Note: pandas 3.0 is a new major; verify engine compatibility
  after any upgrade path. Info.

### DEP-M4. `mcp 1.13.0` pinned intentionally
- `mcp<2.0` is deliberate (documented in AGENTS.md — 2.x breaks reference
  servers). Good decision; keep pin. Info/positive.
- **UPDATED (2026-08-13)**: within the `<2.0` pin, `mcp` upgraded
  `1.13.0 → 1.29.0`, which fixes PYSEC-2026-1617 (DNS rebinding),
  PYSEC-2026-3482 (session hijack) and PYSEC-2026-3483 (WebSocket origin).
  All three affect HTTP/WS transports we do not use; stdio server boot
  verified (16 tools registered, handshake OK).
- **ADDED (2026-08-13)**: `pip` upgraded `24.0 → 26.2.1` (fixes 7 CVEs);
  venv `pip-audit` now reports **no known vulnerabilities**. Residual:
  system `click 8.1.6` (CVE-2026-7246 in `click.edit()`) — accepted, the
  project never calls `click.edit()` and `gTTS` hard-pins `click<8.2`.

---

## 3. Dependency verdict

Healthy dependency set — no conflicts, no abandoned libs, nothing
duplicative in requirements. Single actionable item: `requests` upgrade +
adopt a lock file + run `pip-audit` formally during remediation.
