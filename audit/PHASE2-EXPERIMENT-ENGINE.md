# PHASE 2 — Hypothesis & Experiment Engine, Promotion/Rollback

> Design deliverable. Built 2026-08-13. No application code modified.
> Covers master-prompt Phases 13–15: hypothesis generation, a controlled
> experiment registry, and explicit promotion/rollback rules.

---

## 1. Hypothesis engine (Phase 13)

### 1.1 Principle

The hypothesis engine **never modifies production code**. It emits structured,
testable hypotheses that feed the experiment registry. Code change happens only
inside an experiment branch, evaluated against the frozen baseline, and promoted
by governance.

### 1.2 Hypothesis record

```
hypothesis_id
observation          evidence-backed (from failure analysis, not vibes)
expected_effect      measurable, single metric
reason               causal story + supporting data
affected_component   module / parameter / feature
experiment_definition  what will be built and how it will differ
success_criteria     pre-registered, multiple (not profit-only)
risk                 what could regress and how it is watched
created_at, status   PROPOSED / ACTIVE / REJECTED / CONCLUDED
```

### 1.3 Example (from current evidence)

```
Observation:      performance degrades in high-vol sideways markets
                  (X05: regime gate misclassifies; F5 frozen constants)
Hypothesis:       regime_filter VOLATILE/RANGE threshold tuning is stale
Expected Effect:  regime precision up, RANGE_LV false-positive down
Affected:         regime_filter params (via params registry, not literals)
Success Criteria: regime precision improves AND decision EV improves AND
                  no maxDD increase (baseline-relative)
Risk:             tightening gate raises NO_TRADE rate
```

### 1.4 Source of hypotheses

- Failure analysis aggregates (Phase 12) — the primary generator.
- Manual submissions by the owner.
- Never: arbitrary model "improvement" without a measured failure behind it.

## 2. Experiment registry (Phase 14)

### 2.1 Record

```
experiment_id
parent_baseline
hypothesis_id
change_description
dataset_version, feature_version, model_version, parameter_version
train_period, validation_period, test_period, regime filters
metrics (pre-registered set from the taxonomy)
result (edge vs baseline + fold CI)
decision
created_at, ran_at, concluded_at
artifacts_sha          hash of experiment code + config (reproducibility)
```

### 2.2 States

```
PROPOSED → RUNNING → PASSED / REJECTED / INCONCLUSIVE
                       └→ PROMOTED / ROLLED_BACK
```

### 2.3 Isolation

- Every experiment runs on a **frozen copy** of the baseline datasets +
  baseline params; it may only differ in the specific change under test.
- Experiment code lives in an experiment workspace/package, not in the
  production modules.
- The experiment produces its own `results/experiments/<id>/` output; it can
  never write to ground-truth or audit tables.
- Two experiments never share mutable state.

### 2.4 Reproducibility

- `artifacts_sha` pins code + data manifest + config; re-running the exact sha
  must reproduce results bit-for-bit (seeds recorded, single-threaded where
  needed). A run that cannot be reproduced is INCONCLUSIVE at best.

## 3. Promotion rules (Phase 15)

### 3.1 What is NOT sufficient

A candidate must NOT be promoted merely because:

- total profit increased
- one period improved
- in-sample accuracy improved
- one metric improved

### 3.2 Required multi-dimensional gate

```
1. PRIMARY metric improves vs baseline (beyond fold noise, e.g. >1σ)
2. AND risk not materially worse (maxDD / VaR / drawdown-duration ≤ baseline + tol)
3. AND out-of-sample remains positive (same direction in OOS fold)
4. AND walk-forward stable (sign + magnitude consistent across ≥ half the folds)
5. AND no major regime degradation (check worst regime cell vs baseline)
6. AND no data leakage (audit trail clean: no future timestamps, no reshuffle)
7. AND baseline comparison passed (same dataset/costs/metrics/period)
8. AND any listed risk did not materialize beyond threshold
```

### 3.3 Rollback triggers

Automatic suspicion when post-promotion, over a watch window:

- primary metric degrades vs baseline beyond the pre-registered tolerance, or
- regime worst-cell degrades, or
- drift alarm trips on any input the candidate depends on, or
- a previously-passed invariant (freshness, no-leakage) is violated.

Rollback = revert candidate, restore previous params from registry, log a
`ROLLED_BACK` decision + reason. Rollback is automatic-and-notified, never
silent.

### 3.4 Version hygiene

- Promotion always bumps the **parameter/feature/model version** and records it
  in the registry. The prior version stays retrievable (audit trail).
- Baseline is only re-anchored by an explicit "baseline promotion" governance
  event — never implicitly when an experiment wins.

---

## 4. Registry storage (SQLite, append-only)

`data/experiment_registry.db`:

```
hypotheses      hypothesis_id PK, observation, expected_effect, reason,
                affected_component, success_criteria_json, risk_json, status, ts
experiments     experiment_id PK, parent_baseline, hypothesis_id FK,
                versions_json, periods_json, metrics_json, edge_result_json,
                decision, artifacts_sha, created_at, ran_at, concluded_at
promotions      promotion_id PK, experiment_id FK, from_version, to_version,
                evidence_json, reviewer, decided_at
rollbacks       rollback_id PK, promotion_id FK, reason, trigger, ts
```

Append-only + WAL + busy_timeout (same pattern as history_logger). No UPDATE on
decisions — a new record supersedes.

## 5. Minimal build order

1. `experiment_registry.py` — schema + CRUD + state machine (pure, testable).
2. `hypothesis_engine.py` — wraps failure aggregates into hypothesis records.
3. `experiment_runner.py` — executes a registered experiment in isolation.
4. `promotion_check.py` — implements the §3.2 gate as a deterministic check.
5. Reports: `results/experiments/<id>/*.md` + registry query tools.
