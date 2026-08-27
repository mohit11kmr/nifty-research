# Phase 6 — Evaluation Report

# Phase 6 — phase6-evaluation-v1

- Generated: 2026-08-13 13:36:13 IST (read-only, from a `mode=ro` facade - the ledger was never modified)
- Source: `data/ground_truth.db` (sha256 `1cc7cb60233b46f4…`)
- Report data is **OBSERVED** from the Ground Truth ledger. Derived aggregates are labeled DERIVED.
  Missing values stay missing (`null`); nothing is estimated or invented.
- Cohort rule: only `REAL_FRESH` records are eligible for empirical performance claims.


## Ledger counts (OBSERVED)

| table | chain-linked count |
|---|---|
| market_observations | 47 |
| feature_snapshots | 47 |
| signals | 47 |
| predictions | 0 |
| decisions | 47 |
| executions | 0 |
| positions | 0 |
| outcomes | 0 |
| evaluations | 0 |

- open positions: 0
- closed positions: 0
- pending (unevaluated) predictions: 0
- unresolved outcomes: 0
- executions/positions/outcomes are counted only when part of a recorded signal
  chain (imported LEGACY ledger rows are tracked but excluded from evaluation).

## Provenance distribution (OBSERVED)

| table | status -> count |
|---|---|
| decisions | {'REAL': 47} |
| evaluations | - |
| executions | - |
| feature_snapshots | {'REAL': 47} |
| market_observations | {'REAL': 47} |
| outcomes | - |
| positions | - |
| predictions | - |
| signals | {'REAL': 47} |

## Evaluation cohort (DERIVED)

- preferred cohort: `REAL_FRESH`
- eligible (`REAL_FRESH`): 47
- excluded LEGACY: 0
- excluded SIMULATED: 0
- excluded REAL_STALE: 0
- excluded UNKNOWN: 0

## Signal evaluation (DERIVED, ADEQUATE)

- sample: 47 signals, all `precision_signal`
- directional claims: 0 (non-directional: 47)
- signals with an outcome: 0
- hit rate / FPR / FNR: `null` - no directional claim with an outcome exists yet.
- All 47 recorded signals are `STAY_OUT` (no direction, no trade) => correctly NOT
  counted as predictions.

## Prediction evaluation (DERIVED, INSUFFICIENT_SAMPLE)

- sample: 0 -> correct/incorrect/neutral/unknown all 0.
- accuracy: `null`. No prediction has been recorded/evaluated yet.

## Decision evaluation (DERIVED, ADEQUATE)

- by_type: {'SKIP': 47}
- skip rate: 1.0, acceptance: 0.0
- capital guard states: {'APPROVED': 47}

## Execution / Outcome / Risk-guard evaluation (DERIVED, INSUFFICIENT_SAMPLE)

- executions: 0 -> no slippage/fees/fill data.
- outcomes: 0 -> win_rate, avg P&L, MFE/MAE all `null`.
- rejected requests: 0.

## Regime analysis (DERIVED)

- market states seen: `['UNKNOWN']` (all 47 signals have
  market_state NULL => grouped under UNKNOWN; no regime claim is made).

## Leakage verification (OBSERVED invariant checks)

- clean: True, issues: 0

## Honest bottom line

The ledger has a clean, append-protected, REAL_FRESH signal history but **zero**
directional predictions, trades, or outcomes so far. Any accuracy/win-rate claim
from this data would be fabricated - therefore none is made.
