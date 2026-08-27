# Phase 6.5 — Live Observation / Chain Health

> Empirical findings ONLY. Evidence-backed statements; nothing is invented.
> Companion to `audit/PHASE6-FROZEN-BASELINE.md` (baseline_id
> `phase6-baseline-2026-08-13-3678c7f0`). Phase 6.5 adds a read-only,
> non-mutating observation layer: `chain_health_report`,
> `live_observation_report`, `observation_state` and read-only MCP health
> tools. Nothing in Phase 6.5 writes to the ledger.

## 1. Snapshot

- git: `cf132caeb7e8e17a2f316cd45a48f0c88e7cc703` (`master`, clean)
- DB sha256: `3678c7f07cdaac032d282c5d27ec048e67fbff63e4e961a26164c9a341891d68`
- Observation window: 2026-08-13 12:45:59 -> 13:53:08 IST (intraday)
- Counts: signals 103, predictions 0, decisions 103, executions 0,
  positions 0, outcomes 0, evaluations 0, feature_snapshots 103
- Directional signals: 0; STAY_OUT/SKIP rate: 1.0
- Chain health: **HEALTHY**, 0 findings, 0 error/critical
- Observation state: **NO_DIRECTIONAL_TRADES_YET**

## 2. Chain health monitor (`evaluation_engine.chain_health_report`)

Checks every table in the ground-truth chain for structural integrity.
Severity ladder: INFO / WARNING / ERROR / CRITICAL. Any finding above
severity=0 marks the chain UNHEALTHY. Detectors:

| Finding | Rule | Severity |
|---|---|---|
| ORPHAN_SIGNAL | signal has no decision (directional or no-trade) | WARNING |
| ORPHAN_DECISION | decision references missing signal | WARNING |
| ORPHAN_EXECUTION | execution without decision (LEGACY provenance expected) | INFO |
| ORPHAN_POSITION | position without entry execution | ERROR |
| MISSING_FEATURE_SNAPSHOT | signal without a feature snapshot | WARNING |
| MISSING_OUTCOME | CLOSED position with no outcome | ERROR |
| DUPLICATE_OUTCOME | >1 outcome per position (defense-in-depth; real schema blocks) | CRITICAL |
| PROVENANCE_LOSS | NULL provenance on a non-legacy row | INFO |
| TIMESTAMP_INCONSISTENCY | feature_ts > signal_ts, decision before signal (ERROR); exit before entry (CRITICAL) | ERROR/CRITICAL |
| INVALID_STATE_TRANSITION | quantity <= 0 or position without entry execution (ERROR); entry execution reused (CRITICAL) | ERROR/CRITICAL |

Detectors are schema-guarded (PRAGMA table_info) so bare/minimal DBs do not
crash the monitor. Output is deterministic: identical DB -> identical
findings (test `test_deterministic_health_output`).

## 3. Live observation report (`live_observation_report`)

One-shot snapshot: counts per table, directional-signal count,
STAY_OUT/SKIP rate, open/closed positions, pending predictions, unresolved
outcomes, REAL_FRESH cohort eligibility, leakage status, chain findings and
the observation state. Classification
(`evaluation_engine.observation_state`):

- **NO_DIRECTIONAL_TRADES_YET** — 0 predictions & 0 executions (production
  today).
- **PENDING_OUTCOMES** — predictions/executions exist, 0 resolved outcomes.
- **ACCUMULATING_OUTCOMES** — >= 1 resolved outcome available for scoring.

## 4. Production observation (2026-08-13)

- 103/103 signals are `STAY_OUT` no-signal records with APPROVED
  capital-guard state; decision skip rate 1.0. Discipline held: no setup,
  no trade.
- Chain healthy (0 findings) -> the whole 103-record chain is structurally
  complete with provenance on every row.
- Nothing is scoreable yet (0 predictions, 0 outcomes). Hit rate, win rate,
  MFE/MAE, confidence calibration remain correctly `null`. Any claim of edge
  here would be fabrication.

## 5. Read-only MCP health tools (mcp_nifty.py)

Added, all verified in prod:

- `live_observation_status` — Phase 6.5 observation snapshot.
- `ground_truth_chain_health` — full chain-health monitor.
- `pending_evaluations` — predictions with unknown outcomes.
- `open_positions` — OPEN status positions (never orders).
- `outcome_status` — by_class WIN/LOSS/BREAKEVEN + net P&L + MFE/MAE.
- Existing `baseline_status` unchanged (frozen-baseline read).

All open a read-only connection (`_connect_ro`), catch errors via `_safe`,
and never write. Verified: `ok=True` for all six tools in production.

## 6. Tests (tests/test_chain_health.py, 13 cases)

- Healthy full chain -> HEALTHY, 0 findings.
- Zero-trade STAY_OUT/SKIP-only ledger (production shape) -> HEALTHY +
  NO_DIRECTIONAL_TRADES_YET.
- Deterministic output (JSON-identical across runs).
- Detectors: ORPHAN_SIGNAL(WARNING), MISSING_FEATURE_SNAPSHOT(WARNING),
  legacy ORPHAN_EXECUTION(INFO), MISSING_OUTCOME(ERROR) + UNHEALTHY,
  DUPLICATE_OUTCOME(CRITICAL) over bare DB, ORPHAN_DECISION(WARNING),
  decision-before-signal TIMESTAMP_INCONSISTENCY(ERROR),
  PROVENANCE_LOSS(INFO), INVALID_STATE_TRANSITION quantity=0(ERROR).
- observation_state classification matrix.

## 7. Regression

- `python -m unittest discover -s tests`: **163 tests OK** (18.3s).
- Production ledger untouched by Phase 6.5: sha256
  `3678c7f0...` unchanged from baseline; all writes still go through
  GroundTruthDB append-only/trigger-guarded path.

## 8. Honesty guard

- 103 signals = ADEQUATE signal sample, but 0 directional claims.
- No win rate / hit rate / MFE/MAE / confidence number is reported where
  data is absent - all remain `null`, matching PHASE6-FROZEN-BASELINE.
- Observation state names the situation precisely: we are observing a
  no-trade posture, not evaluating edge.
