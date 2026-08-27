# Phase 6.1 — Results Interpretation

> Empirical findings ONLY. Evidence-backed statements; nothing is invented.
> Companion to `audit/PHASE6-FROZEN-BASELINE.md` (baseline_id
> `phase6-baseline-2026-08-13-3678c7f0`).

## 1. Snapshot

- git: `cf132caeb7e8e17a2f316cd45a48f0c88e7cc703` (`master`)
- DB sha256: `3678c7f07cdaac032d282c5d27ec048e67fbff63e4e961a26164c9a341891d68`
- Evaluation window: 2026-08-13 12:45:59 -> 13:44:18 IST (intraday)
- Counts: signals 87, predictions 0, decisions 87, executions 0,
  positions 0, outcomes 0, evaluations 0
- Leakage: clean (0 issues); reproducibility: byte-identical (True)

## 2. REAL_FRESH cohort analysis

- Eligible: 87 / 87 signals (no LEGACY / SIMULATED / STALE / UNKNOWN).
- All 87 are `STAY_OUT` no-signal records: directional claims = 0,
  predictions = 0, trades = 0.
- Signal-level sample is ADEQUATE (87 >= 20) but there is **nothing
  directional to score** - hit rate, accuracy, win rate, MFE/MAE are all
  correctly `null`.
- Decision acceptance 0.0 / skip rate 1.0 with APPROVED capital-guard state:
  the guard accepted the no-trade posture for every record. No money was at
  risk and no risk was taken - correct behavior for a no-signal session.

## 3. Confidence calibration

- Status: **INSUFFICIENT_DATA** (0 bands populated).
- No prediction has a confidence value paired with an outcome, so no
  confidence-vs-observed-success comparison is possible. Confidence is NOT
  treated as a probability anywhere in this report.

## 4. Regime analysis

- All 87 signals carry `market_state = NULL` at record time (the 6-layer
  confluence did not persist a market state for STAY_OUT records).
- Regime panel groups everything under `UNKNOWN`. No regime claim is made.

## 5. Signal / strategy family analysis

- One family exists: `precision_signal` (version `d571203c6549`).
- Evidence per family: sample 87, directional 0, outcomes 0.
- Classification: **INSUFFICIENT DATA** for any win-rate/edge claim.
- There is no "best supported" family. Calling anything best would be fabrication.

## 6. Decision vs execution decomposition

- Prediction quality: unmeasurable (0 predictions).
- Decision quality: measurable only as posture - 87/87 correct SKIP given
  zero directional signals (signal-level discipline held: no trade when no
  setup). Decision evidence: ADEQUATE.
- Execution quality: unmeasurable (0 executions).
- Outcome quality: unmeasurable (0 outcomes).
- Loss origin classification: **unknown** - there are no losses to trace.

## 7. Failure analysis

- Classified failures: 0. Healthy / no-trade chains: 87.
- No DATA_ERROR / FEATURE_ERROR / SIGNAL_ERROR / REGIME_ERROR / MODEL_ERROR /
  RISK_ERROR / EXECUTION_ERROR / TIMING_ERROR evidence exists.
- Root-cause classification is not attempted where no evidence exists.

## 8. MFE / MAE interpretation

- MFE / MAE available: 0 rows -> no entry/exit timing observation is possible.
- No claim about early/late entries, cut winners, or adverse excursion.

## 9. Data sufficiency gate

| metric | evidence class |
|---|---|
| counts + decision posture | HIGH_CONFIDENCE_EVIDENCE (87) |
| signal directional accuracy | INSUFFICIENT_SAMPLE (0) |
| prediction accuracy | INSUFFICIENT_SAMPLE (0) |
| execution quality | INSUFFICIENT_SAMPLE (0) |
| outcome / win rate / MFE / MAE | INSUFFICIENT_SAMPLE (0) |
| confidence calibration | INSUFFICIENT_SAMPLE (0) |
| regime performance | INSUFFICIENT_SAMPLE (0) |

## 10. Executive findings

**What is working (evidence-backed)**
- Ledger integrity: 87/87 REAL_FRESH chains append-protected, leakage-clean,
  reproducibly re-readable.
- Discipline: 0 trades on 87 no-signal records - the system does not trade
  when there is no setup (a hard rule, now observable in the ledger).
- Measurement rigour: every empty panel reports `null` / INSUFFICIENT_SAMPLE
  instead of a fabricated number.

**What is failing**
- Nothing is failing at the ledger/data level. No performance failure can be
  attributed because no trade exists to fail.

**What is unknown**
- Prediction accuracy, signal hit rate, decision-to-trade conversion,
  execution quality, win rate, MFE/MAE, confidence calibration, regime
  performance - all empty until directional signals and PAPER trades are
  recorded.

**Most important failure pattern**
- None observed yet (0 trades). The system is measurement-ready, not yet
  data-rich.

**Most promising improvement areas (future experiments - NOT implemented)**
- Persist `market_state` for STAY_OUT records so the regime panel can be
  populated.
- Record predictions + PAPER executions for directional A+ signals as they
  occur, to grow the outcome dataset.

## 11. Scope guard

No strategy, signal, risk rule, confidence threshold, or model parameter was
changed to produce this interpretation. Phase 6.1 is measurement + freeze only.
