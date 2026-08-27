# OpenCode — Phase H2: RANGE-HV Iron Condor Research Validation

## Objective

Phase H1 v2 is complete and verified.

The Strategy Creator now provides:

```text
Strategy Specification
→ Validation
→ Compilation
→ Backtest Adapter
→ Paper Adapter Interface
→ Ground Truth / Evaluation compatibility
```

Current multi-strategy research found:

```text
CURRENT CONTROL
48 trades
33.3% win rate
PF 1.011
Net +₹1,906.43
Status: CONTROL / EDGE UNPROVEN

DIRECTIONAL SPREAD
24 trades
20.8% win rate
PF 0.473
Net -₹44,398.33
Status: WEAK

RANGE-HV IRON CONDOR
6 trades
66.7% win rate
PF 9.693
Net +₹6,248.25
Max DD -₹587
Status: PROMISING BUT INSUFFICIENT SAMPLE
```

H2 objective:

> Validate the existing frozen RANGE-HV Iron Condor candidate rigorously before any strategy change, optimization, paper promotion, or AI generation.

This is a **research validation phase only**.

---

# CRITICAL RULE

DO NOT:

- change the Range-HV strategy rules
- change strike width
- change delta
- change expiry selection
- change stop
- change target
- add filters
- remove filters
- tune VIX thresholds
- tune regime rules
- optimize position sizing
- optimize capital allocation
- run parameter sweeps
- run genetic search
- run Bayesian optimization
- retrain ML for optimization
- enable live trading
- promote the strategy to production paper trading
- create synthetic trades
- fabricate missing market data
- alter Ground Truth history
- modify the current control strategy

The purpose is:

**Determine whether the existing Range-HV candidate has enough independent evidence to justify further paper research.**

---

# 1. READ AUTHORITATIVE DOCUMENTS

Read:

```text
audit/MASTER-PROJECT-BLUEPRINT.md
audit/PHASE-H-MULTI-STRATEGY-BACKTEST.md
audit/PHASE-H1-V2-STRATEGY-LAB.md
audit/PHASE-F3-EXPIRY-CONSISTENCY-BACKTEST.md
audit/PHASE-G-NETWORK-RESILIENCE.md
audit/TRADING_DECISION_FLOW.md
```

Also inspect:

```text
strategies/range_hv_iron_condor_v1.yaml
strategy_schema.py
strategy_validator.py
strategy_compiler.py
strategy_registry.py
backtest_adapter.py
premium_seller.py
backtest_frozen.py
multi_strategy_backtest.py
historical_expiry.py
calendar_expiry.py
paper_execution.py
exit_evaluator.py
evaluation_engine.py
ground_truth.py
```

Current source code and frozen strategy specification are authoritative.

---

# 2. FREEZE THE CANDIDATE

The canonical candidate is:

```text
strategies/range_hv_iron_condor_v1.yaml
```

Record:

```text
strategy_id
version
spec_hash
git_commit
dataset_hash
expiry-calendar hash
cost-model version
slippage model
```

Verify the specification still has:

```text
classification = PROMISING_BUT_INSUFFICIENT
lifecycle = BACKTESTED
```

Do not modify the specification during H2.

---

# 3. VERIFY STRATEGY CONSISTENCY

Before any extended validation:

Run:

```bash
python strategy_lab.py validate range_hv_iron_condor_v1
python strategy_lab.py compile range_hv_iron_condor_v1
python strategy_lab.py equivalence range_hv_iron_condor_v1
```

Expected:

```text
VALID
COMPILED
spec-consistency = OK
```

If the frozen specification or engine has changed unexpectedly:

STOP and report.

---

# 4. CURRENT SAMPLE AUDIT

Reconstruct the original six trades exactly.

Produce a trade-by-trade table:

```text
trade_id
date
regime
VIX
entry time
expiry
strikes
premium received
max risk
exit time
exit reason
gross P&L
fees
slippage
net P&L
MFE
MAE
days held
```

Do not change the historical results.

This table is the baseline evidence.

---

# 5. PROFIT-CONCENTRATION ANALYSIS

Determine:

```text
profit contribution by trade
largest winner
largest loser
median trade
mean trade
profit contribution by month
profit contribution by regime
```

Calculate:

```text
% of total net P&L from best trade
% of total net P&L from top 2 trades
% of total net P&L from top 3 trades
```

If a small number of trades dominate returns:

```text
HIGH_CONCENTRATION
```

Do not call the strategy robust.

---

# 6. RANGE-HV ELIGIBILITY AUDIT

For every historical RANGE_HV day in the dataset:

Record:

```text
date
VIX
regime
data availability
options availability
strategy eligibility
trade generated?
reason if no trade
```

Separate:

```text
RANGE_HV observed
RANGE_HV eligible
RANGE_HV trade
RANGE_HV no-trade
```

This must answer:

> Why did only six trades occur?

Do not change the strategy to create more trades.

---

# 7. MONTHLY STABILITY

Break the full historical period into calendar months.

For each month report:

```text
RANGE_HV days
eligible days
trades
wins
losses
net P&L
PF
average trade
max drawdown where meaningful
```

Use:

```text
NO_TRADES
INSUFFICIENT_SAMPLE
```

where appropriate.

Do not aggregate sparse months into a misleading average.

---

# 8. REGIME / VOLATILITY BAND ANALYSIS

Within RANGE_HV, report performance across the observed VIX distribution.

Do NOT create optimized bins.

Use descriptive, pre-defined reporting only.

For example, if enough data naturally exists:

```text
VIX 16–18
VIX 18–20
VIX 20–22
VIX 22–25
```

If sample size is too small:

```text
INSUFFICIENT_SAMPLE
```

Do not select bins after viewing profitable outcomes.

---

# 9. DAY-OF-WEEK / EXPIRY CONTEXT

Report descriptive statistics by:

```text
entry weekday
days-to-expiry
expiry day
holding duration
```

Do NOT tune entry or expiry based on these observations.

Purpose:

**Understand behavior, not optimize it.**

---

# 10. EXIT ANALYSIS

Break down all historical trades by:

```text
STOP_LOSS
TAKE_PROFIT
EXPIRY_SQUARE_OFF
```

For each:

```text
count
win/loss
average P&L
MFE
MAE
average hold
```

Determine whether returns come mainly from one exit mechanism.

Do not change exits.

---

# 11. COST / SLIPPAGE SENSITIVITY — DESCRIPTIVE ONLY

Use the existing canonical cost model.

Do not optimize.

Report:

```text
gross P&L
fees
slippage
net P&L
```

If useful, show a simple descriptive comparison:

```text
gross vs after-cost
```

Do not create alternative cost assumptions to improve the strategy.

---

# 12. OUT-OF-SAMPLE DESIGN

Do NOT use the full historical period to make a promotion decision.

Use a clear chronological split, preferably:

```text
DEVELOPMENT
2025-08-13 → 2026-03-31

OUT-OF-SAMPLE
2026-04-01 → 2026-08-13
```

Do NOT tune using the OOS period.

If the candidate has too few OOS trades:

```text
OOS_INSUFFICIENT
```

Do not manufacture evidence.

---

# 13. WALK-FORWARD OBSERVATION

If the project already supports walk-forward evaluation, use its existing mechanism.

Do NOT introduce new optimization.

A valid walk-forward result may only mean:

```text
OBSERVED
```

not automatically:

```text
PROVEN
```

---

# 14. BOOTSTRAP / STATISTICAL UNCERTAINTY

With only six trades, ordinary point estimates are highly unstable.

Calculate uncertainty where defensible:

```text
confidence interval for win rate
bootstrap P&L range
trade-level variability
```

If the sample is too small for a meaningful method:

```text
NOT_RELIABLE
```

Do not imply statistical significance.

---

# 15. DRAWDOWN / RISK CHECK

Verify:

```text
max drawdown
max single-trade loss
largest consecutive losses
capital utilization
worst historical sequence
```

The previous result showed approximately:

```text
max DD ≈ -₹587
```

Verify against the current frozen replay rather than assuming the number.

Do not change position sizing.

---

# 16. EXPECTED-RISK CHECK

Verify that:

```text
defined risk
max loss per position
capital usage
```

are internally consistent with the existing project risk framework.

Do not invent a new risk framework.

If inconsistency exists:

```text
RISK_MODEL_MISMATCH
```

and STOP promotion.

---

# 17. DATA QUALITY

For every RANGE_HV trade verify:

```text
NIFTY
OPTIONS
OI
VIX
EXPIRY
STRIKES
QUOTES
```

were available at the correct decision time.

No future data.

No stale-as-fresh.

No fabricated quotes.

---

# 18. NO-LOOKAHEAD

Perform a specific audit for:

```text
entry decision
strike selection
expiry
premium
exit
```

Ensure every input was known at or before the relevant timestamp.

---

# 19. REPRODUCIBILITY

Run the Range-HV validation twice.

Require:

```text
same trade list
same metrics
same daily eligibility
same OOS split
```

Record:

```text
dataset hash
strategy spec hash
expiry hash
result hash
```

---

# 20. PRODUCTION ISOLATION

The validation must NOT modify:

```text
data/ground_truth.db
paper_account.json
production signal state
live broker state
```

Use the existing frozen research snapshot.

Verify production isolation.

---

# 21. RESEARCH REPORT

Create:

```text
audit/PHASE-H2-RANGE-HV-VALIDATION.md
```

Include:

## Candidate Identity

## Frozen Specification

## Original Six Trades

## RANGE_HV Eligibility Analysis

## Monthly Stability

## VIX/Volatility Analysis

## Day-of-Week / Expiry Analysis

## Exit Analysis

## Cost Analysis

## Development vs Out-of-Sample

## Uncertainty / Sample Size

## Drawdown / Risk

## Data Quality

## No-Lookahead

## Reproducibility

## Production Isolation

## Limitations

## Verdict

Use only:

```text
PROMISING_BUT_INSUFFICIENT
SUPPORTED
WEAK
UNPROVEN
NOT_TESTABLE
```

Do not use:

```text
PROFITABLE
BEST
PROVEN
READY_FOR_LIVE
```

unless evidence actually supports such a claim and project rules permit it.

---

# 22. PROMOTION GATE

The candidate is NOT promoted automatically.

H2 must end with one of:

```text
HOLD — insufficient sample
REJECT — evidence weak
CONTINUE PAPER RESEARCH
```

Do NOT automatically move to paper trading.

A future paper phase requires explicit approval after reviewing H2.

---

# 23. FUTURE SAMPLE-GROWTH PATH

If H2 remains promising but insufficient:

The next safe phase should be:

```text
PAPER OBSERVATION ONLY
```

using the exact frozen Range-HV specification.

Do not tune it first.

Target:

```text
20+ genuine outcomes
```

before making an initial empirical edge assessment.

---

# 24. DO NOT TOUCH AI GENERATION YET

The future AI loop is:

```text
AI proposes strategy
↓
Validator
↓
Compiler
↓
Backtest
↓
Evidence
↓
Human review
↓
Paper
```

H2 must NOT implement that loop.

---

# 25. TESTS

Add focused H2 tests where needed:

```text
tests/test_phase_h2_range_hv.py
```

Test:

- exact six-trade reconstruction
- eligibility classification
- no-lookahead
- OOS split
- deterministic output
- cost accounting
- exit classification
- production isolation
- spec consistency
- reproducibility

Run:

```bash
python test_all.py
python -m unittest discover -s tests -v
python tests/test_fix_verification.py
pip check
pip-audit
git diff --check
```

Report exact counts.

---

# 26. FINAL RESPONSE

Return exactly:

```text
PHASE H2 — RANGE-HV IRON CONDOR VALIDATION

Strategy:
range_hv_iron_condor_v1

Spec Hash:
<hash>

Dataset:
<hash>

Original Trades:
6

RANGE_HV Observed Days:
X

RANGE_HV Eligible Days:
X

Trades:
X

Wins:
X

Losses:
X

Win Rate:
<value / INSUFFICIENT>

Net P&L:
<value / INSUFFICIENT>

PF:
<value / INSUFFICIENT>

Max Drawdown:
<value / INSUFFICIENT>

Best Trade:
<value>

Worst Trade:
<value>

Profit Concentration:
<description>

Monthly Stability:
<description>

Best Descriptive VIX Band:
<description / INSUFFICIENT>

Exit Breakdown:
<description>

Development Results:
<summary>

Out-of-Sample Results:
<summary / OOS_INSUFFICIENT>

Statistical Uncertainty:
<summary>

Data Quality:
PASS/FAIL

No-Lookahead:
PASS/FAIL

Reproducibility:
PASS/FAIL

Production Data Untouched:
YES/NO

Strategy Changed:
NO

Optimization:
NO

AI Generation:
NO

VERDICT:
PROMISING_BUT_INSUFFICIENT / SUPPORTED / WEAK / UNPROVEN / NOT_TESTABLE

Most Important Finding:
<description>

Biggest Limitation:
<description>

Next Safe Phase:
HOLD / PAPER OBSERVATION / REJECT / REVIEW
```

## FINAL RULE

**Do not improve the Range-HV strategy during H2.**

We are answering one question:

> Is the existing Range-HV candidate strong enough to deserve more evidence?

If the answer is "not enough evidence", that is a successful research result.
