# PHASE 2 — Baseline, Evaluation Framework & Benchmark

> Design deliverable. Built 2026-08-13. No application code modified.
> Covers master-prompt Phases 8, 9 and 11: the frozen baseline, the evaluation
> protocol, and a fair cross-candidate benchmark.

---

## 1. Baseline (Phase 8)

### 1.1 Definition

The **Baseline Version** is the frozen, deterministic reference system every
future improvement is compared against. It is not "the best system" — it is the
*honest current state* with all provenance issues fixed but no trading-logic
changes. It is:

```
baseline_version         B2026-08-13  (git commit cf132ca + config pin)
dataset_version          hash of the frozen evaluation dataset manifest
feature_version          hash of the feature-set definition used by the baseline
model_version            NONE (rules) / ml_engine_<window> as context-only
parameter_set            the exact thresholds/constants in use (from a params
                         registry, not source literals)
evaluation_period        frozen date range (see §1.3)
market_regime            regime labels from regime_filter over the period
execution_assumptions    paper fills: mid/LTP, 1.5% slippage, ₹40/trade, lot 75
cost_assumptions         documented; premium_seller re-run at 75
random_seed_policy       seeds recorded; any random component rerun with
                         SEED_FIXED=42 only for reproducibility, results quoted
                         as "seed-specific" not general
```

### 1.2 Determinism & reproducibility

- Baseline must be bit-reproducible: pin git commit, data snapshots
  (freeze `data/` inputs into a read-only `baseline_datasets/` copy or a hash
  manifest), Python version, `requirements.lock`, and all parameter values.
- Any change to any of these = a **new baseline version**, never an edit.
- Baseline inputs are snapshot-copied at freeze time because live caches change
  (proven by the ml_features Aug-08 vs nifty_history Aug-13 drift).

### 1.3 Evaluation period

- Use a **rolling, walk-forward window** rather than a single fixed period so
  the baseline remains measurable as time advances without being re-tuned.
- Fixed anchor dataset: NIFTY daily + intraday research.db window for which
  ticks survive retention (note: 30-day purge means MFE/MAE history is bounded;
  the baseline records `mfe_source=PURGED` honestly).

### 1.4 Freeze discipline

- During any experiment, baseline tables are **read-only** (same append-only
  trigger pattern as ground truth).
- The baseline can only be refreshed by an explicit "baseline promotion" event,
  governed (see Self-Improvement doc) — never silently.

---

## 2. Evaluation framework (Phase 9)

### 2.1 Data partitions

| Partition | Purpose | Rules |
|---|---|---|
| Train | fit models | no look-ahead by construction (walk-forward) |
| Validation | tune params / select | strictly chronological, after train |
| Out-of-Sample Test | final honest score | used once; touching it = retest contamination |
| Walk-Forward | rolling train→test folds | train_days 180–200, step 20 (already the ml_engine pattern) |

### 2.2 Stratification

Report results within:
- **Market regimes** (TRENDING/RANGE/VOLATILE/TRANSITION from regime_filter)
- **Volatility conditions** (VIX quartiles / premium zones CHEAP→PANIC)
- **Trend/gap conditions** (gap up/down/flat from timing.py stats)
- **Time periods** (month, day-of-week, intraday buckets)

Because performance is regime-dependent, a headline number without regime
breakdown is not evidence (matches the observed real-world skew in skew research).

### 2.3 Anti-overfitting protocol

| Hazard | Countermeasure |
|---|---|
| Look-ahead bias | features snapshotted at signal time only; forward horizons enforced by DB CHECK |
| Leakage | train/test strictly chronological; no shuffling (already the house rule) |
| Survivorship bias | fixed stock universe snapshot (Nifty-50 list dated) in evaluation manifest |
| Overfitting | walk-forward folds; parameter-change penalty if gains are below fold variance |
| Cherry-picking | pre-registered evaluation windows; any new window is a new registered experiment |
| Repeated test-set tuning | OOS test consumed exactly once per metric; touching it invalidates the experiment (auto-halt) |

### 2.4 What is a valid experiment (minimum bar)

An experiment is **valid** only if it has: a registered hypothesis, a frozen
baseline version, a pre-registered outcome definition + metric, the exact
partition boundaries, the seed policy, and a decision state that is not
PROPOSED. Anything else is a notebook doodle, not an experiment.

---

## 3. Model / Rule benchmark (Phase 11)

### 3.1 Candidates

```
A. Existing deterministic rules   (regime + precision_signals rule chain)
B. Statistical baseline           (naive: always-follow-regime / buy&hold / mean-rev)
C. Simple ML baseline             (logistic on the same features — cheap ceiling)
D. Current ML                     (ml_engine meta-blender, super_ai_ml — context-only today)
E. Future models                  (any new candidate)
```

### 3.2 Fair-comparison contract

Every candidate is evaluated on the **same**:

- dataset version (frozen manifest)
- time windows (identical walk-forward folds)
- outcome definition (same horizon, same NEUTRAL band, same costs)
- cost assumptions (1.5% slippage, ₹40/trade, lot 75; premium_seller corrected)
- metrics (the taxonomy: prediction accuracy, decision EV, outcome R-multiple,
  performance Sharpe/PF/maxDD, regime-stratified)
- holdout procedure (walk-forward, no reshuffle)

### 3.3 Metric-manipulation defense

- Report **edge = candidate − baseline** on the same metric, with confidence
  interval from walk-forward folds; a candidate "wins" only if edge > fold
  noise (e.g. edge exceeds 1 SD of fold-variances).
- Penalize parameter count: report out-of-sample edge **and** number of tuned
  parameters (prefer the simpler model when edges are within noise).
- Every claim must state its cost basis + period; the registry makes it
  impossible to quietly change lot size or add a fee exemption.
- No metric is computed by the candidate itself — the evaluation framework
  owns all scoring (same independence rule as the Outcome Engine).

### 3.4 Baseline report format

```
baseline_report_id, baseline_version, dataset_version, feature_version,
eval_window, folds[], metrics{accuracy, ev, sharpe, pf, maxdd, mfe/mae,
regime_matrix}, cost_basis, seed_policy, produced_by, artifacts_sha
```

Output to `results/baseline_reports/` — one file per baseline version,
immutable, with a JSON sidecar for machine comparison.
