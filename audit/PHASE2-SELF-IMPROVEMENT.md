# PHASE 2 — Self-Improvement Levels, AI Boundaries & Governance

> Design deliverable. Built 2026-08-13. No application code modified.
> Covers master-prompt Phases 10, 16, 17, 18: ML reality check, maturity
> levels, what AI may/must not control, and governance.

---

## 1. Existing ML reality check (Phase 10) — verdicts on every ML-looking module

### 1.1 `ml_engine` — genuine ML, context-only
- Inputs: cached NIFTY features (`data/ml_features.csv`, **currently stale Aug-08**).
- Outputs: next-day direction + meta-blender agreement.
- Learning: genuine `walk_forward_eval` (train_days 150/180/200, step 20, no shuffle).
- Persistence: none. Versioning: none. Retraining: per call, in-memory.
- Limitations: stale feature cache; no persisted model; out-of-sample ~51% vs
  baseline ~52% (no edge) — correctly treated as context-only.
- **Verdict: KEEP as the honest benchmark; add cache-freshness guard + model persistence + versioning.**

### 1.2 `super_ai_ml` — genuine model fitting, fixed protocol, context-only
- Inputs: same cached features.
- Outputs: BULLISH_CALL / BEARISH_PUT / NEUTRAL_SIDEWAYS (+ avg prob).
- Learning: 80/20 fixed chronological split, **fixed hyperparams** (XGB/LGBM
  n_estimators=100, depth=4, lr=0.05, seed 42; RF depth 5). Docstring claims
  walk-forward; code does not.
- Persistence: none. Versioning: none.
- Limitations: no walk-forward, no calibration, stale cache, context-only by
  AGENTS.md; feeds precision_signals layer 6 + live_trader_brain dimension 4.
- **Verdict: KEEP context-only; either add real walk-forward + calibration or
  strip the misleading docstring.**

### 1.3 Everything else — NOT genuine ML

| Module | Real purpose | Why not ML | Recommendation |
|---|---|---|---|
| `trainer.py` | walk-forward **evaluator of the rule brain** (42.8%) | evaluates rules; no model; no feedback | KEEP as evaluator; wire to registry |
| `lstm_neural_engine.py` | deterministic formula (constant 0.60) | no network, no data, no fit | **REMOVE from run_all or tag SIMULATED/UNSUPPORTED** |
| `adaptive_weights.py` | Q-learning-style weight file | honest no-op (no outcomes, no consumer) | KEEP honest no-op; later feed real outcomes from Outcome Engine |
| `auto_enhancer.py` | scheduled audit + false success log | no adaptation occurs | **FIX claim** (report NOOP truthfully) |
| `reflection_engine.py` | template hypothesis generator | no learning, no validation consumers | KEEP as input to new hypothesis engine; add experiment links |
| `volatility_forecaster.py` | fixed GARCH formula | constants never estimated; fabricates <10 samples | REDESIGN with real estimation or archive |
| `portfolio_rebalance.py` | fixed-rule backtest | no learning; flat results | archive |
| `empirical_proof.py` | verification script | deterministic checks | KEEP as test helper |
| `equity_quant.py` | formula scans | no learning; never invoked | wire or archive |

## 2. Self-improvement levels (Phase 16)

```
LEVEL 0 — No learning               current: no feedback into any parameter
LEVEL 1 — Measurement               next: ground truth + outcomes + evaluation
LEVEL 2 — Adaptive parameters       after: params registry + drift-driven tuning
LEVEL 3 — Automated experiments     after: registry + isolated runner
LEVEL 4 — Controlled model selection  after: benchmark + promotion gate
LEVEL 5 — Continuous monitored improvement  only after 1-4 hold
```

### 2.1 Current level — evidence

**LEVEL 0** (with LEVEL-1 fragments). There is measurement (audit trail,
42.8% trainer report) but **no learning**: nothing ever feeds back into any
parameter. The "adaptive" surfaces (adaptive_weights, auto_enhancer,
reflection_engine) are inert or cosmetic. Frozen "trained" constants in
market_brain confirm zero feedback. A claim of LEVEL 1 requires the outcome
chain; it does not exist yet.

### 2.2 Safe next level — LEVEL 1

Build measurement only: ground-truth DB, outcome engine, baseline report,
failure records. No adaptive parameters, no automated experiments, no model
promotion until LEVEL 1 is provably running for ≥ 1 full evaluation window.

## 3. AI boundaries (Phase 17)

### 3.1 AI MAY (increasingly automated with level)

- summarize failures (read-only)
- generate structured hypotheses (via hypothesis engine)
- analyze patterns in ground truth + failure data
- suggest experiments (registry records, never self-executing production changes)
- compare candidate models on the frozen benchmark
- explain anomalies
- assist documentation
- assist code generation **in an experiment sandbox** (isolated workspace)

### 3.2 AI MUST NOT autonomously

- bypass risk limits or alter capital controls (1%/3%/7%, kill-switch)
- promote unvalidated models
- modify production logic without governance
- rewrite historical outcomes (append-only truth)
- disable safeguards
- hide poor results (no silent fallback/fabrication)
- redefine metrics to make itself look better (metrics live in the registry)

## 4. Governance (Phase 18)

### 4.1 Governance matrix

| Action | Level | Authority |
|---|---|---|
| Record outcomes/evaluations | L1 | AUTOMATIC (engine, append-only) |
| Write failure records | L1 | AUTOMATIC |
| Baseline freeze / refresh | L1+ | HUMAN ONLY |
| Hypothesis PROPOSED | L2 | AUTOMATIC (from failure analysis) |
| Experiment PROPOSED | L2 | APPROVAL REQUIRED (owner) |
| Experiment RUNNING | L2 | AUTOMATIC (isolated) |
| Experiment decision (PASS/REJECT/INCONCLUSIVE) | L3 | AUTOMATIC on gate, owner review of artifacts |
| Promotion to params registry | L3 | APPROVAL REQUIRED (owner) |
| Baseline re-anchor | L3+ | HUMAN ONLY |
| Rollback | any | AUTOMATIC on trigger + notification |
| Risk-parameter change | any | HUMAN ONLY (never AI) |
| Metric/registry definition change | any | HUMAN ONLY |

### 4.2 Audit trail

Every governance action writes an immutable row: who/what, action, versions
before/after, evidence hash, timestamp. `promotions`, `rollbacks`,
`experiment_registry` tables are append-only and WAL-protected.

### 4.3 Guardrails that can never be relaxed by automation

- 1% per-trade cap, 3% daily / 7% weekly stop, kill-switch (owner rules).
- RANGE_LV = NO TRADE for directional options.
- Honesty rules: no shuffling, no fabricated data, edge vs baseline reported.
- No automated real-money orders (broker primitive stays unwired and gated).
