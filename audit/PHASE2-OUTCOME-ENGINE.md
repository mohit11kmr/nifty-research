# PHASE 2 — Outcome Engine & Result Taxonomy

> Design deliverable. Built 2026-08-13. No application code modified.
> Covers master-prompt Phases 6–7: the canonical Outcome Engine and a strict
> vocabulary for Prediction/Signal/Decision/Execution/Outcome/Performance/
> Model-Evaluation/System-Health.

---

## 1. Outcome Engine (Phase 6)

### 1.1 Mandate

The Outcome Engine is **independent from the signal generator**. Signal code
never computes its own outcome; the Outcome Engine observes the ground-truth
chain and answers objectively:

- Did execution happen?
- At what price / after what delay?
- What was realized P/L? Unrealized P/L?
- MFE / MAE?
- How long was the decision active?
- Was the outcome positive/negative/neutral?
- Was the original prediction correct?
- Was execution poor even though the prediction was correct?

### 1.2 Ownership model

```
signal generator ────(emits signal_id only)───┐
                                               ▼
                 GROUND TRUTH DB  ──►  OUTCOME ENGINE (observer)
                                                    │
paper/backtest fills ──────────────────────────────┤
tick stream (MFE/MAE) ─────────────────────────────┤
calendar/horizon ──────────────────────────────────┤
                                                    ▼
                                    outcome rows + evaluations (append-only)
```

The generator must not be able to write outcomes. Only the engine owns
`outcomes` + `evaluations` tables.

### 1.3 Traceability tree

```
Signal
 └── Prediction (direction, horizon)
      └── Decision (action or NO_TRADE)
           └── Execution (fill price, latency, slippage)
                └── Position (open qty, SL/TGT events)
                     └── Outcome (realized P/L, MFE, MAE, duration)
                          └── Evaluation (prediction correct? exec quality?)
```

Every node carries: `id`, `timestamp`, `parent_id`, `version hash`, provenance.

### 1.4 Questions → queries

| Question | Query shape |
|---|---|
| Did execution happen? | `executions WHERE decision_id = ?` — empty + decision=TRADE ⇒ REJECTED/FAILED record must exist |
| At what price / delay? | fill_price, fill_ts−order_ts |
| Realized P/L | outcomes.realized_pnl |
| Unrealized P/L | current mark vs entry for OPEN positions (marked at eval time, stamped) |
| MFE/MAE | recomputed from tick window; `mfe_source` marks PURGED when unavailable |
| Duration active | exit_ts − open_ts |
| Outcome sign | sign(realized_pnl) with cost floor: outcome counts NEUTRAL if |pnl| < costs |
| Prediction correct? | evaluations.prediction_correct (direction vs realized move over horizon) |
| Execution quality | slippage = |fill − req|, fill latency, filled-vs-requested qty → GOOD/BAD/UNKNOWN |

### 1.5 Neutral-outcome rule

A trade that loses less than its estimated frictions (slippage + fees) is
NEUTRAL, not a win or loss — this prevents cost-blind self-congratulation and
mirrors the existing honesty discipline.

### 1.6 Horizon & evaluation lifecycle

- Prediction carries `horizon` (e.g. "intraday to expiry", "next bar", "1 day").
- Evaluator runs at `horizon_end_ts` + grace; until then `status=PENDING`.
- Expiry-pinned predictions evaluate at square-off (15:05) with exit_reason=EXPIRY.
- NO_TRADE decisions are evaluated too: was the stand-down correct (i.e. would a
  naive trade have lost)? This answers "is the gate adding value?"

---

## 2. Result taxonomy (Phase 7)

Never use one number for all of these. They are distinct concepts with distinct
metrics.

### 2.1 Prediction
*Claim about the future.*
- **Metrics**: directional accuracy (HIT rate at horizon), calibration
  (Brier score / reliability diagram vs confidence bands), horizon-averaged error.
- **Not**: profit. A correct direction can lose money; a wrong direction can win.

### 2.2 Signal
*The trigger object (grade, layers).*
- **Metrics**: signal quality (share of signals with all layers PASSED),
  hit rate (of signals that became trades), precision/recall vs baseline,
  false-signal rate (STAY_OUT stats).
- **Not**: the A+ label itself — grade is a claim, verified only via outcomes.

### 2.3 Decision
*The chosen action given a signal.*
- **Metrics**: EV per decision (from outcomes), rejection rate (NO_TRADE share),
  gate additivity (outcome of executed vs would-have-been no-trade), action mix.
- **Not**: prediction accuracy — decision quality includes risk filtering.

### 2.4 Execution
*The fill.*
- **Metrics**: slippage (pts + ₹), fill latency, fill quality (BAD when
  estimated_fill=true used), fill rate, spread paid (B/A mid vs fill).
- **Not**: P/L — a bad fill on a great call is an execution failure.

### 2.5 Outcome
*What happened.*
- **Metrics**: realized P/L, unrealized P/L (marked), MFE, MAE, duration,
  outcome sign with NEUTRAL band (see 1.5), R-multiple (P/L ÷ initial risk).
- **Not**: prediction correctness (measured separately).

### 2.6 Performance
*Aggregate across a portfolio/period.*
- **Metrics**: CAGR, Sharpe (daily, risk-free from INR T-bill proxy), maxDD,
  PF, win rate by R-multiple buckets, drawdown duration, regime-stratified
  returns. Baseline-relative edge (system vs frozen baseline) only.
- **Not**: a single "42.8%"/"72.5%" headline without its denominator + cost basis.

### 2.7 Model Evaluation
*Does the model improve on baseline?*
- **Metrics**: out-of-sample accuracy vs baseline (must quote both + edge),
  calibration (reliability), walk-forward stability (std of folds),
  feature stability (permutation importance variance).
- **Not**: in-sample accuracy; not "model exists" as evidence of skill.

### 2.8 System Health
*Is the machinery working?*
- **Metrics**: uptime (daemon/recorder/dash), error rate (exceptions per cycle),
  data completeness (ticks/day expected vs actual), freshness violations
  (STALE reads), provenance coverage (% of results with envelopes),
  retention success (DB size under budget).
- **Not**: trading P/L — a system can be healthy and losing, or unhealthy and
  (accidentally) winning.

### 2.9 Metric registration rule

Every metric used in any report must be defined in one registry with: formula,
inputs, cost assumptions, time window, version. Reports render the registry
link, not just the number. This kills the "one metric proves everything" failure
mode the current code exhibits (e.g. `ULTRA_ROBUST`, `PASSED_ALL_3`).

---

## 3. Current-state gap summary

| Concept | Current code | Gap |
|---|---|---|
| Prediction | ML verdicts + market_brain consensus | no horizon, no calibration basis persisted |
| Signal | signal_history rows | no prediction/decision link |
| Decision | auto_paper_runner gates + paper orders | STAND_DOWN/NO_SIGNAL not recorded as decisions |
| Execution | paper fills (mid/LTP estimate) | latency/slippage not captured; `estimated_fill` absent |
| Outcome | closed_trades in paper_account.json | no MFE/MAE, no fees, no R-multiple, no link to signal |
| Performance | backtester metrics + trainer report | baseline absent, cost basis varies (lot 25 vs 75) |
| Model eval | walk-forward in ml_engine only | super_ai_ml has no walk-forward; no persistence |
| System health | — | missing entirely |
