# PHASE 2 — Failure Analysis Engine

> Design deliverable. Built 2026-08-13. No application code modified.
> Covers master-prompt Phase 12: structured, aggregate-able failure analysis.

---

## 1. Motivation

Today failures are invisible: exceptions are swallowed (many `except Exception`
blocks print a line and continue), signals can fire on fabricated layers, and
there is no record of "this signal was wrong" beyond an unlinked paper ledger.
Failure analysis makes errors countable, attributable, and learnable.

## 2. Failure record (per poor prediction/decision/outcome)

```
signal_id            FK to ground truth
timestamp            signal_ts (UTC)
market_state         regime + VIX zone + volatility bucket at signal time
features             feature_snapshot_id (not copies — immutable by link)
prediction           direction + horizon
confidence           value + calibration basis (null if uncalibrated)
decision             action / NO_TRADE / reason_code
risk_state           capital_guard status, drawdown bucket, kill-switch state
execution            fill price, latency, slippage, estimated_fill flag
outcome              realized P/L (R-multiple), MFE/MAE, duration
error_type           see taxonomy below
probable_cause       human/auto-assigned, versioned, one per record
```

## 3. Failure taxonomy

```
DATA_ERROR        input missing/stale/fabricated (freshness breach, FABRICATED tag)
FEATURE_ERROR     feature set wrong/buggy (bad indicator math, version drift)
SIGNAL_ERROR      signal logic wrong (layer gating bug, wrong grade)
REGIME_ERROR      regime classification wrong (gate said TREND, market chopped)
MODEL_ERROR       model mispredicted (overfit, stale features, drift)
RISK_ERROR        risk layer blocked/incorrectly sized (killed good trade / under-sized)
EXECUTION_ERROR   fill slippage, latency, missed fill (paper vs intended)
TIMING_ERROR      entry/exit timing wrong though direction right
UNKNOWN           no attributable cause (default — never guess upward)
```

Rules:
- One record = one primary error_type; the record can carry secondary tags.
- UNKNOWN is a real value; forcing a guess reintroduces false confidence.
- Records are append-only and never edited post-mortem (corrected analysis =
  new record + `supersedes`).

## 4. Classification rules (deterministic first pass)

| Condition | error_type |
|---|---|
| Feature `data_freshness` > budget at signal time | DATA_ERROR / FEATURE_ERROR (staleness) |
| Signal had NOT_COMPUTED/NEUTRAL layers but fired a trade | SIGNAL_ERROR |
| Regime label ≠ realized regime (ex-post classification) | REGIME_ERROR |
| Direction correct but |slippage| > threshold | EXECUTION_ERROR |
| Prediction correct, decision avoided, realized outcome would have won | RISK_ERROR (gate too strict — measured via NO_TRADE evaluation) |
| Direction wrong, all inputs fresh/valid | MODEL_ERROR (then drill into feature family) |
| No signal fired but market moved strongly | TIMING_ERROR / SIGNAL_ERROR (coverage failure) |

## 5. Aggregate analysis (the deliverable reports)

The engine must support (as SQL/materialized views, not bespoke scripts):

- failure rate by **regime**
- failure rate by **signal type** (grade, layer mix)
- failure rate by **confidence band** (calibration check — do 70% bands hit 70%?)
- failure rate by **model** (ml_engine / super_ai_ml / rules / none)
- failure rate by **time of day** (open / lunch / expiry-day window)
- failure rate by **volatility** (VIX quartile)
- failure rate by **feature family** (technical vs OI vs institutional vs ML)

### 5.1 Report format

```
results/failure_reports/<date>_failures.md
  - totals by error_type (count, % of decisions)
  - 2x2: error_type × regime
  - confidence calibration table (predicted band vs observed hit rate)
  - top 10 probable_cause strings (with counts)
  - drift alarm: any metric moving >2σ vs baseline period
```

## 6. Interaction with other components

- **Hypothesis engine**: a spike in `REGIME_ERROR × VOLATILE` auto-proposes a
  hypothesis record (never a code change — see Experiment Engine doc).
- **Outcome engine**: failures are derived from outcomes; the analyzer never
  computes its own P/L.
- **Baseline**: failure rates are compared against the frozen baseline's
  failure distribution; an experiment that merely shifts error_type without
  improving net edge is rejected.

## 7. Current-code gap

- No failure records exist; exceptions are swallowed silently (e.g. gamma_flip
  returns defaults, many `except Exception: print(...)`).
- `signal_history` has no outcome link, so "was this A+ correct" cannot be
  answered today — the engine above is the prerequisite to knowing failure
  rates at all.

## 8. Minimal build

1. `failure_analyzer.py`: reads ground-truth DB → writes failure rows + views.
2. `classify_failure(row)`: the deterministic rule table (§4).
3. `failure_report(days)`: markdown + JSON aggregates.
4. Triggers on `evaluations` insert → auto-create the failure record.
