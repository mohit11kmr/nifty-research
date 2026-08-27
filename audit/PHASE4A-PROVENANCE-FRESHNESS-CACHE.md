# Phase 4A — Provenance Persistence, ML Freshness Wiring & Cache Recovery

> Date: 2026-08-13 | Base commit: `cf132ca` (same as Phase 3)
> Scope (STRICT): **P-05** provenance persistence, **P-06** ML freshness
> integration, **P-15** cache rebuild / freshness recovery.
> NOT implemented (per spec): Ground Truth, Outcome Engine, failure
> analysis, experiment engine, model registry, autonomous learning,
> model promotion, self-modifying code, major refactors.

Phase 3 prerequisites this phase closes:
1. **Provenance column/schema** (history_logger) → P-05
2. **ml_engine freshness wiring** → P-06
3. **ml_features / tf_scan cache rebuild** → P-15

---

## P-05 — Provenance persistence

### Schema changes

Canonical DB: `data/historical_audit.db` (permanent append-only audit trail).
Canonical tables: `tick_history`, `signal_history`, `paper_trade_journal`.

Added one nullable TEXT column to each audit table:

```sql
ALTER TABLE <table> ADD COLUMN provenance_json TEXT;
```

`research.db` (raw tick recorder output, 298 MB) is left untouched — it is a
research capture, not the audit trail; provenance is applied at the audit
boundary.

### Canonical provenance representation (`truth.py`)

- `PROVENANCE_FIELDS` — canonical field list:
  `status, source, timestamp, data_timestamp, data_freshness, fallback_used,
  fallback_reason, feature_version, model_version, parameter_version,
  signal_version, evaluation_method, environment, execution_mode`.
- `canonical_provenance(**kwargs)` — builds the dict, drops `None` fields,
  never emits empty provenance (degrades to `UNKNOWN`).
- `serialize_provenance()` / `deserialize_provenance()` — deterministic
  `json.dumps(sort_keys=True)` for the TEXT column; read path maps:
  - `NULL` → `{"status": "LEGACY"}` (record predates the schema) — **never REAL**
  - unparseable → `{"status": "UNKNOWN", "reason": "corrupt provenance"}`
- Vocabulary extended with `LEGACY` and `UNKNOWN`.

### Migration

- `history_logger._ensure_provenance_columns(conn)` runs inside
  `_init_sqlite_db()` after schema creation: checks `PRAGMA table_info`,
  adds the column only if missing. **Idempotent**, additive, nullable.
- Existing rows keep `NULL` → read back as `LEGACY`; no historical record is
  rewritten or upgraded.
- Rollback: column is additive + nullable — old code and old rows are
  unaffected; full rollback only requires ignoring the column.
- Verified on a **copy** of the real DB: all row counts preserved, columns
  added, first record reads `LEGACY`.

### Write paths

- `log_market_tick(..., provenance=None)` — inserts `provenance_json`;
  `provenance=None` → status `UNKNOWN` (never silently `REAL`). CSV mirror
  includes the column (best-effort).
- `log_generated_signal(signal_data, provenance=None)` — same treatment.
- `live_ticker_service.stream_live_market_ticks` now passes the tick's
  envelope (`status`, `source`, `data_timestamp`, `fallback_used`,
  `fallback_reason`, `evaluation_method`) so a **FALLBACK tick is persisted
  as FALLBACK**, not as a real quote.
- `run_all.py` step 12 passes signal provenance
  (`source=precision_signals`, `evaluation_method=6_layer_confluence`,
  `signal_version=hash(confluence_checks)`).

### Read path

- `get_record_provenance(table, record_id)` — returns the dict; legacy →
  `LEGACY`, corrupt → `UNKNOWN`.
- `get_historical_audit_summary()` now reports `provenance_coverage`
  per table: `records / with_provenance / legacy`.

### Evidence (real DB after run_all)

```
tick_history   : 26 records | 3 with_provenance | 23 legacy
signal_history : 10 records | 1 with_provenance | 9 legacy
latest tick 717: {"status":"UNKNOWN"}                     (caller sent none)
latest tick 716: {"evaluation_method":"live_fetch","source":"yahoo:^NSEI,^INDIAVIX","status":"REAL"}
latest signal 10: {"signal_version":"d571203c6549","source":"precision_signals","status":"UNKNOWN"}
```

---

## P-06 — ML engine freshness

`ml_engine.py` now distinguishes **REAL+FRESH / REAL+STALE / MISSING / FALLBACK /
SIMULATED / INVALID / UNKNOWN** via the truth layer.

### Feature cache lifecycle

- `build_features(force=False)` returns `(df, meta)`:
  - cache **REAL** → read as-is (`rebuilt=False`).
  - cache **STALE / MISSING** → rebuild through the real source pipeline
    (`nifty_history.csv` + `fii_dii_history.csv`).
  - cache **INVALID** (future mtime) → discard + rebuild (`discarded_corrupt`).
  - rebuild **FAILED** → returns `(None, meta)` with `error`; cache left
    STALE/MISSING. **No fabricated data, no timestamp touching.**
  - final status downgraded to `STALE` if the underlying `nifty_history.csv`
    is itself stale (rebuilt-but-stale is still STALE).
- `feature_cache_status()` → `truth.file_freshness(FEATURE_CACHE, 20h)`.
- `_source_freshness()` → per-source freshness snapshot.

### Output provenance

- `direction_forecast()` envelope:
  `status, source=cache:ml_features.csv, data_timestamp (cache mtime),
  data_freshness, evaluation_method=walk_forward,
  feature_version=hash(feature cols), feature_cache_age_h/budget_h, rebuilt`.
- `meta_blender()` envelope: `status, source=cache:nifty_history.csv,
  data_freshness, evaluation_method=walk_forward, cache age/budget`.
- `format_ml()` prints `Data freshness: REAL|STALE (age h / budget h)`.
- Stale behavior = **degrade gracefully + mark output stale**: ML is CONTEXT
  ONLY (AGENTS.md), never a trigger; it is never silently treated as fresh.
- `super_ai_ml.py` already surfaced `feature_freshness` (Phase 3) and is now
  backed by a fresh cache after P-15.
- `daily_report.report_tf_summary()` now prints a freshness warning and the
  correct rebuild command when `tf_scan.csv` is stale.

### Evidence

```
direction_forecast: status REAL | freshness REAL | feature_version a1e2f3587129
                    acc 0.467 | baseline 0.521 | edge -0.054 | n 240   (honest, no edge)
meta_blender:       edge -1% (51% vs 52%) n=280 | Data freshness: REAL (age 0.03h)
```

---

## P-15 — Cache rebuild / recovery

New executable trigger: **`python rebuild_cache.py`** (real pipelines only).

### Cache sources / generation

| Cache | Source | Pipeline | Network |
|---|---|---|---|
| `data/ml_features.csv` | nifty_history + fii_dii caches | `ml_engine.build_features(force=True)` | none |
| `data/tf_scan.csv` | Yahoo intraday (^NSEI 15m/60m/1d) | `multitf.tf_grid_scan(strategies.build_param_grid(), ("15m","60m","1d"), days)` → to_csv | required |

### Recovery rules implemented

```
VALID + FRESH  -> use (no-op, integrity check only)
VALID + STALE  -> rebuild
MISSING        -> rebuild
CORRUPT        -> discard + rebuild   (fresh mtime + unreadable/missing columns)
REBUILD FAILED -> remain STALE/MISSING; exit 1; file untouched
```

- `needs_rebuild(path, budget_h)` — STALE/MISSING/INVALID classification.
- `validate_csv(path, required_columns)` — integrity check (readable, ≥1 row,
  expected columns); freshness is verified by mtime **and** content.
- Network safety (`_yahoo_probe`): bounded probe (≤2 attempts, 3s sleep),
  `fetch_intraday` already timeouts at 25s; failure → clear error, file
  untouched, status preserved.

### Rebuild evidence

```
before: ml_features.csv STALE (age 114.27h)   tf_scan.csv STALE (age 114.46h)
after : ml_features.csv REAL (age 0.0h)       496 rows, integrity OK
        tf_scan.csv     REAL (age 0.0h)       232 rows, integrity OK, 14.9s,
                                               net OK (114 probe rows)
```

Row-count note: the stale `tf_scan.csv` had 1392 rows; the rebuilt file has
232 rows — the current `strategies.build_param_grid()` yields 232 configs and
the current `tf_grid_scan` emits one row per config. The rebuild output is
the honest output of the real pipeline.

`python rebuild_cache.py --only ml_features|tf_scan` selects one cache.

---

## Tests

New file: `tests/test_phase4a.py` — **32 tests**, unittest (repo convention).
All DB/cache writes redirected to temp files; no production data modified.

| Area | Tests |
|---|---|
| Canonical provenance | field list, None-filtering, UNKNOWN default, serialize/deserialize roundtrip, LEGACY never REAL, corrupt→UNKNOWN |
| Provenance persistence | migration adds columns, idempotent migration, legacy rows stay LEGACY, new tick provenance, no-provenance→UNKNOWN, survives read/write, corrupt stored→UNKNOWN, CSV mirror carries provenance, signal provenance, coverage summary |
| ML freshness | fresh cache read without rebuild, stale→rebuild, missing→rebuild, rebuild-failure→None+missing, invalid→discard+rebuild, stale-source→output STALE, direction_forecast provenance, meta_blender freshness |
| Cache recovery | needs_rebuild classification, validate_csv, fresh no-op, stale repair, tf_scan success (mocked scan), tf_scan network-failure preserves stale + file byte-identical, failed rebuild introduces no data |

### Results (base `cf132ca`, `.venv/bin/python`)

| Check | Baseline | After | Status |
|---|---|---|---|
| `test_all.py` | 34 OK | 34 OK | PASS |
| `python -m unittest discover -s tests` | 71 OK | **103 OK** (71 + 32 new) | PASS |
| `python tests/test_fix_verification.py` | 29 OK | 29 OK | PASS |
| `pip check` | clean | clean | PASS |
| `pytest -m pytest tests/ -q` | unavailable | unavailable | REPORTED (not installed) |
| `pip-audit` | unavailable | unavailable | REPORTED (not installed) |
| `git diff --check` | clean | clean | PASS |
| `run_all.py` end-to-end | exit 0 | exit 0, 0 STALE flags | PASS |
| `rebuild_cache.py` | — | both caches REAL, integrity OK | PASS |

---

## Truth audit (STEP 11)

| Check | Result |
|---|---|
| Stale cache treated as fresh | **FIXED** — `build_features` rebuilds on STALE; `super_ai_ml` tags freshness; `daily_report` warns on stale tf_scan |
| Fake ML labels | **FIXED** — every ML result carries `status`/`data_freshness`/`feature_version`; acc reported with baseline + edge |
| Hardcoded market fallbacks | **FIXED** (Phase 3) — grep-clean in live paths; only `experiments/strike_selector_upgrade_experiment.py:17` remains (experiment code, not live) |
| Provenance discarded downstream | **FIXED** — persisted in audit DB/CSV; FALLBACK/REAL/UNKNOWN statuses survive |
| Legacy data mislabeled as REAL | **FIXED** — NULL provenance → `LEGACY`; 23 ticks + 9 signals stay LEGACY |
| Failed cache rebuild silently accepted | **FIXED** — `rebuild_cache` returns non-REAL status + exit 1; file byte-identical on failure |
| Missing feature data silently replaced | **FIXED** — `(None, meta)` + error; nothing fabricated |

---

## Remaining blockers before Ground Truth + Outcome Engine

1. **Signal→outcome linkage** — the full `ground_truth.db` schema
   (`signals → predictions → decisions → executions → positions → outcomes →
   evaluations`) from `audit/PHASE2-GROUND-TRUTH.md` is the next phase's
   work; P-05 gives it a persisted, honest provenance column to build on.
2. **`paper_trade_journal` writes** — table exists, never written (X03 F13);
   the ledger wiring is P-06/P-07 roadmap work, still out of scope.
3. **Confidence calibration** — market_brain constants are flagged
   `FROZEN_PARAMETER_MODEL`; a real calibration basis must be re-derived
   before any confidence is used as evidence.
4. **`pip-audit` / `pytest`** — still not installed; regression relies on the
   unittest suite + `pip check` (do not install per spec).

Ground Truth ready: **YES** (inputs are honest, provenance persists, caches
fresh) — begin the Phase 5 `ground_truth.db` design + Outcome Engine only
after this report is accepted.
