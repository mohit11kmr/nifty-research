# PHASE 2 — Implementation Roadmap & Final Decision

> Design deliverable. Built 2026-08-13. No application code modified.
> Covers master-prompt Phases 19–23: future architecture, priority backlog,
> implementation phases, and the final decision answers.

---

## 1. Future architecture (Phase 19) — smallest sensible design

### 1.1 Principle

Do NOT create a microservices zoo. The current system is a flat Python root
with SQLite + JSON state; the right next step is **one new package
(`platform/`) of read-only/isolated libraries + 3 append-only SQLite DBs**,
leaving the existing engine modules untouched until promotion.

```
production root (unchanged until promoted)
  │
  └── platform/                     NEW — the Phase-2 layer
       ├── truth.py                 status vocabulary + provenance envelope + freshness
       ├── ground_truth.py          ground_truth.db writes (append-only guards)
       ├── outcome_engine.py        outcome + evaluation computation (observer)
       ├── baseline.py              baseline freeze + report + comparison
       ├── failure_analyzer.py      failure records + aggregates
       ├── hypothesis_engine.py     structured hypotheses
       ├── experiment_registry.py   experiment state machine + persistence
       ├── experiment_runner.py     isolated execution
       ├── promotion_check.py       multi-dimensional gate (§3)
       └── reports/                 markdown + JSON report writers

DBs (append-only, WAL):
  data/ground_truth.db        signals→predictions→decisions→executions→positions→outcomes→evaluations
  data/experiment_registry.db hypotheses + experiments + promotions + rollbacks
  data/baseline.db            frozen baseline snapshots + reports
```

### 1.2 Interfaces

- Engines expose `result + provenance` (envelope) — a thin wrapper, not a rewrite.
- MCP tools + dashboards render status badges from envelopes.
- A `params.json` registry replaces source-literal thresholds for anything that
  may ever be tuned (market_brain, regime thresholds, adaptive weights).
- CI: `platform/` has unit tests; a grep-guard blocks `seed(42)`,
  `TRAINED`, `ULTRA_ROBUST`, `PASSED_ALL`, hardcoded spot literals in new code.

### 1.3 What we explicitly do NOT build yet

- No auto-trading. No neural-network stack. No distributed compute.
- No autonomous param adaptation (that's LEVEL 2+, after LEVEL 1 is proven).
- No rewriting of existing engines until an experiment demands it.

---

## 2. Priority fix/build list (Phase 20)

| ID | Problem | Why it matters | Evidence | Proposed solution | Deps | Risk | Benefit | Testing | Prio |
|---|---|---|---|---|---|---|---|---|---|
| P-01 | Hardcoded 24403.10/12.0 fallbacks (run_all:162, live_ticker_service, smart_strike defaults) | fake-live values poison decisions | F1–F3 | Route through `live_market_fetch` honest UNAVAILABLE + FALLBACK tag | none | low | removes fake-live | unit: fallback path emits FALLBACK | **P0** |
| P-02 | auto_enhancer false "updated" claim | looks like learning, changes nothing | F11 | Report real diff; verdict NOOP when nothing changed | P-01 | low | honest claims | unit on verdict derivation | **P0** |
| P-03 | market_brain frozen "TRAINED" constants + overstated reliability | 42.8% measured vs 0.55 hardcoded | F5, trainer report | Move to params registry; surface measured calibration; tag UNKNOWN | params.json | med | honest confidence | compare registry vs literal | **P0** |
| P-04 | LSTM / ULTRA_ROBUST / PASSED_ALL theater | unsupported outputs presented as results | F4, F8, long_term | Tag SIMULATED/UNSUPPORTED or remove from run_all; replace with calibrated metrics | P-01 | low | no misleading numbers | grep-guard + unit | **P0** |
| P-05 | Ground truth DB + append-only guards | cannot answer "was signal right" | Phase5 doc | `platform/ground_truth.py` + schema | none | med | measurement basis | schema invariants + leak tests | **P0** |
| P-06 | Outcome engine + signal→outcome links | no realized/MFE/MAE/execution quality | Phase6 doc, F13 | outcome_engine + auto_paper_runner wiring | P-05 | med | the core metric source | e2e paper→outcome test | **P0** |
| P-07 | Baseline freeze + report | no comparison reference | Phase8 doc | baseline.py + datasets manifest | P-05/P-06 | med | fair comparisons | reproducibility test | **P1** |
| P-08 | Failure analyzer + taxonomy | failures invisible (swallowed excepts) | Phase12 doc | failure_analyzer + classification rules | P-05/P-06 | med | learn from errors | classification unit tests | **P1** |
| P-09 | Stale-cache guard (ml_features Aug-08, tf_scan Aug-08) | ML/tf silently train on stale data | F15 | freshness budget in truth.py; rebuild on breach | P-01 | low | valid ML inputs | freshness tests | **P1** |
| P-10 | premium_seller re-run at lot 75 | headline 72.5% wrong unit | F6 | recompute + publish both; tag unit | none | low | honest edge number | metric parity test | **P1** |
| P-11 | super_ai_ml walk-forward + calibration | 80/20 fixed, no walk-forward, docstring mismatch | X06 | real walk_forward_eval; strip false claim | P-09 | med | honest ML eval | walk-forward fold test | **P2** |
| P-12 | monte_carlo / var stress real distributions | seed-42 + formulaic PASSED | F7, F8 | parameterize from real outcome dist; report CI | P-06 | med | evidence-grade risk | distribution tests | **P2** |
| P-13 | Experiment registry + hypothesis engine | no controlled improvement path | Phase13/14 doc | experiment_registry + runner | P-07/P-08 | med | safe improvement | state-machine tests | **P2** |
| P-14 | Promotion gate + rollback | no governance for change | Phase15 doc | promotion_check + rollback triggers | P-13 | med | controlled evolution | gate unit tests | **P3** |
| P-15 | Schedule data_retention + backfill paper_journal | DB unbounded (258 MB), journal dormant | F13, F17 | cron data_retention; wire paper_trade_journal writes | P-05 | low | bounded growth, audit | retention test | P1 |
| P-16 | Dead code removal (multi_agent_swarm, telegram_notifier, long_term_backtest) | maintenance drag | X07 | move to archive/ | none | low | clarity | test_all still green | P3 |

---

## 3. Implementation phases (Phase 21)

### Phase 1 — Truth & Provenance (≈P-01…P-04, P-09)
**Goal**: eliminate unsupported/fabricated results.
- Files: `platform/truth.py`, edits to `live_market_fetch` consumers,
  `auto_enhancer.py`, `run_all.py:162/196`, market_brain param extraction.
- DB changes: sidecar `.meta.json` per dataset; no schema change.
- New components: truth.py, freshness guard, grep-guard CI job.
- Tests: fallback→FALLBACK tag; freshness breach; verdict derivation;
  market_brain measured-vs-constant.
- Risks: touching run_all display paths; low blast radius.
- Acceptance: no hardcoded spot/vix reaches MCP or reports; no
  FABRICATED/UNSUPPORTED output rendered as REAL; test_all + unittest green.

### Phase 2 — Ground Truth + Outcome Engine (P-05, P-06, P-15)
**Goal**: track prediction → decision → execution → outcome.
- Files: `platform/ground_truth.py`, `platform/outcome_engine.py`,
  `auto_paper_runner.py`, `paper_trader.py` (write journal).
- DB changes: `data/ground_truth.db` (append-only + triggers), journal writes.
- New components: ground truth + outcome engine.
- Tests: schema invariants (1:1 chain, no future ts), leak tests, e2e
  paper→outcome, MFE/MAE retention-aware.
- Risks: append-only trigger bugs could block writes → guarded.
- Acceptance: every auto_paper_runner signal yields a decision row; closed
  paper trades produce outcomes with MFE/MAE/R-multiple.

### Phase 3 — Baseline + Evaluation (P-07, P-10, P-11)
**Goal**: reproducible performance measurement.
- Files: `platform/baseline.py`, premium_seller at 75, super_ai_ml walk-forward.
- DB changes: `data/baseline.db` (frozen snapshots + reports).
- New components: baseline freeze + report + comparison.
- Tests: reproducibility (same sha ⇒ same numbers), fold-CI, lot-75 parity.
- Risks: dataset manifest drift; mitigated by hash checks.
- Acceptance: baseline B2026-08-13 reproducible; edge reported with CI;
  72.5% corrected.

### Phase 4 — Failure Analysis (P-08)
**Goal**: understand why the system fails.
- Files: `platform/failure_analyzer.py`.
- Tests: classification rules, aggregate queries, calibration table.
- Acceptance: failure records auto-created on evaluations; regime×error report.

### Phase 5 — Experiment Engine (P-13, P-14)
**Goal**: test controlled improvements.
- Files: `platform/experiment_registry.py`, `experiment_runner.py`,
  `promotion_check.py`, `hypothesis_engine.py`.
- Tests: state machine, isolation, promotion gate, rollback triggers.
- Acceptance: a full PROPOSED→RUNNING→PASSED→(PROMOTED/ROLLED_BACK) cycle works
  on a sandbox experiment with the frozen baseline.

### Phase 6 — Controlled Adaptation (P-12 + promotion wiring)
**Goal**: validated parameter/model improvement.
- Files: params registry consumers, adaptive_weights fed by real outcomes.
- Tests: parameter-change experiments vs baseline.
- Acceptance: at least one real parameter (e.g. regime threshold) exists in the
  registry and has undergone a registered experiment.

### Phase 7 — Self-Improvement (automation only within governance)
**Goal**: automate hypothesis → experiment → validation with safeguards.
- Files: drift_monitor → hypothesis trigger; notification hooks.
- Tests: drift alarm → hypothesis PROPOSED → no auto-promotion.
- Acceptance: system reaches **LEVEL 2**, never LEVEL 3+ without owner.

---

## 4. Final decision (Phase 23)

### 1. What is the system actually capable of today?
- **Honest, gated, rule-based options/equity analysis** on cached NSE/Yahoo
  data: regime gate, OI intel (walls/PCR/max pain/Murarkar), 6-layer A+ signal
  (core layers now real), strike selection from live chain IV, risk guards
  (1%/3%/7%, 0DTE trap), paper execution (1 lot × 75), audit trail for market
  ticks + signals, MCP access to all of it.
- **Verified clean**: signal-integrity fixes, risk sizer, DB index/retention
  tooling, secrets, deps, git hygiene; 34+45 tests green.
- **NOT capable**: linking signals to outcomes, measuring itself, learning,
  real-money trading.

### 2. Which current results are trustworthy?
- regime/VIX/OI/walls/skew intel and strike/Δ from live chain IV (real data).
- precision_signals **core** A+ gating (post-remediation).
- backtester mechanics (cost model explicit), ml_engine walk-forward (~51% vs
  52% baseline — honest no-edge), trainer 42.8% measured (below coin-flip).
- audit trail rows (real VIX/PCR/max-pain context).

### 3. Which current results must be considered invalid or misleading?
- hardcoded 24403.10 / vix 12.0 fallbacks (run_all:162, live_ticker_service,
  smart_strike defaults) — F1–F3.
- premium_seller 72.5% / PF 2.6 (lot 25 ≠ 75) — F6.
- Monte Carlo "PASSED" (seed 42) and VaR "PASSED_ALL_3" (formula) — F7/F8.
- market_brain "TRAINED/0.55 reliability" vs measured 42.8% — F5.
- LSTM 0.60 verdict, "ULTRA_ROBUST", auto_enhancer "updated" claim — F4/F11.
- fabricated volume (volume_profile) and fabricated returns
  (volatility_forecaster) — F9/F10.
- run_all step 17 "Executed" (nothing runs) — F16.

### 4. Single most important missing capability
**Signal→outcome measurement** (ground truth + outcome engine): without it,
nothing can be known to work, no baseline exists, and self-improvement is
impossible by definition.

### 5. What should be built first?
P-01 (kill hardcoded fallbacks) + P-05/P-06 (ground truth DB + outcome engine) —
honest inputs first, then measurement.

### 6. What should NOT be built yet?
- Any autonomous parameter adaptation or model self-promotion.
- Any neural/deep-learning stack or auto-trading.
- Any new strategy engine. NO level beyond measurement until Level 1 proves out.

### 7. Minimum architecture for genuine self-improvement
`truth.py` (provenance) → `ground_truth.db` (immutable chain) → `outcome_engine`
(observer) → `baseline.py` (frozen comparison) → `failure_analyzer` →
`experiment_registry` + isolated `experiment_runner` → `promotion_check` gate →
params registry with rollback. That is ~10 small modules + 3 append-only SQLite
DBs — not a service architecture.

### 8. Evidence required before calling the system "self-improving"
- ≥1 full evaluation window of complete signal→outcome coverage (no
  UNKNOWN where data existed).
- A frozen baseline with reproducible reports.
- ≥1 registered experiment that PASSED the full multi-dimensional gate and was
  PROMOTED with observable baseline-relative edge, and ≥1 ROLLED_BACK path
  exercised.
- Failure analysis reporting stable, attributable failure rates.
- All of it on an append-only, versioned, audited trail.

---

# FINAL EXECUTIVE SUMMARY

```
PROJECT:
Nifty Research — local Python quant toolset (~90 flat .py files): NSE/Nifty
option+equity+MCX analysis engines, paper trading, local dashboards, MCP
server, Hermes-scheduled daily reporting. No real-money order path.

CURRENT REAL CAPABILITY:
Honest, gated rule-based analysis on cached NSE/Yahoo data (regime gate, OI
intel, 6-layer A+ signal, live-chain-IV strike selection, 1%/3%/7% risk
guards, 0DTE trap, paper execution 1 lot x 75, market+signal audit trail, 16
MCP tools). 34+45 tests green. Signal-integrity, risk-sizer, DB, secrets and
dependency remediations VERIFIED present.

TRUSTWORTHY OUTPUTS:
regime/VIX/OI/walls/PCR/max-pain/skew intel; strike+delta from live chain IV;
precision_signals core A+ gating; backtester mechanics (explicit cost model);
ml_engine walk-forward (~51% vs 52% baseline, honest no-edge); trainer 42.8%
(measured, below coin-flip); audit trail rows.

INVALID / MISLEADING OUTPUTS:
hardcoded 24403.10/12.0 fallbacks (run_all:162, live_ticker_service,
smart_strike defaults); premium_seller 72.5%/PF2.6 (lot 25 vs 75); Monte
Carlo "PASSED" (seed 42); VaR stress "PASSED_ALL_3" (formula); market_brain
"TRAINED/0.55" vs measured 42.8%; LSTM constant 0.60; "ULTRA_ROBUST";
auto_enhancer false "updated" claim; volume_profile random volume;
volatility_forecaster fabricated returns; run_all step 17 fake "Executed".

CURRENT ML STATUS:
Two genuine ML modules (ml_engine, super_ai_ml), both stateless, cache-fed,
context-only by policy, no persistence/versioning; super_ai_ml lacks real
walk-forward. Everything else is rules, no-op, or theater (LSTM is a
deterministic formula).

CURRENT LEARNING STATUS:
No feedback loop exists. Nothing ever updates a parameter from outcomes.
adaptive_weights/auto_enhancer/reflection_engine are inert or cosmetic.

CURRENT SELF-IMPROVEMENT LEVEL:
LEVEL 0 / 5  (measurement fragments exist; no learning)

TRUTH LAYER: PARTIAL (honesty discipline + audit trail exist; no provenance
envelopes/status vocabulary/freshness enforcement)

GROUND TRUTH: MISSING (no signal→decision→execution→outcome chain)

OUTCOME ENGINE: MISSING (paper ledger unlinked; paper_trade_journal dormant)

BASELINE: MISSING (no frozen versioned reproducible reference)

FAILURE ANALYSIS: MISSING (exceptions swallowed; no failure taxonomy)

EXPERIMENT ENGINE: MISSING (no registry/isolation/promotion)

CONTROLLED ADAPTATION: MISSING (params frozen in source; nothing tunable)

TOP 10 IMPLEMENTATION PRIORITIES:
1.  Kill hardcoded spot/vix fallbacks (F1-F3) — route through honest UNAVAILABLE
2.  Fix auto_enhancer false "updated" claim (honest NOOP verdict)
3.  Move market_brain frozen constants to params registry + show measured 42.8%
4.  Tag/remove LSTM + "ULTRA_ROBUST" + "PASSED_ALL_3" theater
5.  Build ground_truth.db (append-only chain) 
6.  Build outcome engine (signal→execution→outcome, MFE/MAE, R-multiple)
7.  Freeze baseline version + reproducible report
8.  Build failure analyzer (taxonomy + regime/confidence aggregates)
9.  Stale-cache guard (ml_features/tf_scan Aug-08 breach) + schedule retention
10. premium_seller re-run at lot 75 (publish corrected edge)

FIRST IMPLEMENTATION PHASE:
Truth & Provenance (P-01..P-04, P-09): make every output honest + tagged,
then Ground Truth + Outcome Engine (P-05/P-06). Inputs first, measurement next.

WHAT MUST NOT BE IMPLEMENTED YET:
Autonomous adaptation or model self-promotion; neural/deep-learning stack;
auto-trading; any new strategy engine. Nothing beyond measurement (Level 1)
until Level 1 is proven for a full evaluation window.

SUCCESS CRITERIA FOR THE NEXT PHASE:
1.  No FALLBACK/FABRICATED value reaches MCP/reports without a status tag
2.  Every auto_paper_runner decision persists a ground-truth row
3.  Every closed paper trade yields an outcome (P/L, MFE, MAE, R-multiple)
4.  No future-timestamp or look-ahead row exists in ground_truth.db
5.  Baseline B2026-08-13 is frozen + bit-reproducible
6.  test_all.py (34) + unittest tests (45) stay green
```
