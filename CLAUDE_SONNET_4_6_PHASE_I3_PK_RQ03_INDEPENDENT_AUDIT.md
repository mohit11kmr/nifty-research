# Claude Sonnet 4.6 — Independent Audit
# Phase I.3 + PK-RQ-03 GAP_BOUNCE Candidate

## Role

You are an independent senior quantitative-research auditor reviewing the `nifty-research` project after Phase I.3.

Your primary objective is to determine whether:

1. the Phase I.3 research result is trustworthy,
2. the GAP_BOUNCE observation is real and independently reproducible,
3. PK-RQ-03 is economically and statistically credible,
4. the reported +₹23.6K result is a genuine research finding or a data-mining / implementation artifact,
5. the project should continue toward controlled paper validation.

Reported Phase I.3 state:

```text
646 sessions
12 research questions
12 AI proposals
7 validated
4 backtested
1 promising candidate

PK-RQ-03 — GAP_BOUNCE
Down-gap forward 5-day return ≈ +0.75%
Baseline ≈ +0.11%

Reported strategy result:
Net P&L ≈ +₹23.6K
HIGH_CONCENTRATION
OOS thin
```

The project itself does NOT consider this proven.

---

# 1. AUDIT ONLY

Do not:

- modify source code
- modify historical datasets
- modify strategy specs
- optimize parameters
- revise PK-RQ-03
- generate new strategies
- train models
- place broker orders
- paper trade
- change costs/slippage
- change expiry semantics
- change Ground Truth
- change `paper_account.json`
- commit or push changes

You may:

- inspect source
- run tests
- run read-only SQL
- run deterministic backtests
- independently reproduce calculations
- create temporary isolated analysis files
- create an audit report

If you find a defect, report it; do not fix it.

For every defect report:

```text
file
function
line
severity
problem
evidence
impact
recommended fix
```

---

# 2. READ AUTHORITATIVE DOCUMENTS

Read and compare documentation against actual code:

```text
audit/PHASE-I3-REGIME-AWARE-RESEARCH-DISCOVERY.md
audit/PHASE-I2-GENERIC-STRATEGY-EXECUTION.md
audit/PHASE-I1-CONTROLLED-MULTI-MODEL-RESEARCH.md
audit/PHASE-I-V2-AI-STRATEGY-RESEARCH-LAYER.md
audit/PHASE-H3-RANGE-HV-RISK-CONTRACT-INTEGRITY.md
audit/PHASE-H2-RANGE-HV-VALIDATION.md
audit/PHASE-H1-V2-STRATEGY-LAB.md
audit/DATA-ALIGNMENT-01-UNIFIED-CALENDAR.md
audit/PHASE-F3-EXPIRY-CONSISTENCY-BACKTEST.md
audit/PHASE-G-NETWORK-RESILIENCE.md
```

Locate actual Phase I.3 artifacts under:

```text
results/phase_i3/
strategy_research_memory/
audit/
```

If paths differ, report the actual path.

---

# 3. VERIFY PHASE I.3 NUMBERS

Independently verify:

```text
646 sessions
12 research questions
12 AI proposals
7 validated
4 full backtests
1 promising candidate
23 negative-knowledge findings
```

Confirm the reported manifest hash:

```text
3690ea52d2fe43ec67c98a4348cda32b99927f5f656a300680c76b7dc794828d
```

Do not accept summary claims without checking artifacts.

---

# 4. DATA INTEGRITY

Verify the frozen unified research dataset:

```text
NIFTY
OPTIONS_EOD
VIX
PARTICIPANT_OI
EXPIRY
```

Check:

- session calendar
- special sessions
- missing sessions
- duplicates
- conflicting rows
- timestamp/timezone semantics
- source provenance
- underlying alignment
- contract dates
- no silent mixing of newer data

If frozen-input integrity is not established:

```text
DATASET_INTEGRITY_CONCERN
```

---

# 5. PK-RQ-03 DEFINITION

Locate the exact:

```text
research question
AI proposal
strategy spec
trade ledger
result JSON
evaluation output
```

Document exactly:

```text
entry
instrument
contract construction
risk
exit
expiry
cost
slippage
research window
development/OOS split
```

Do not paraphrase in a way that changes the actual rule.

---

# 6. GAP-BOUNCE DEFINITION

Determine exactly how "down-gap" is calculated.

Check:

- previous close source
- current open source
- gap formula
- threshold
- units
- inclusive/exclusive comparison
- NIFTY/index source
- adjusted vs unadjusted data

Write the exact mathematical formula used by the project.

Do not assume a formula without verifying code.

---

# 7. INDEPENDENT GAP-BOUNCE REPRODUCTION

From the frozen raw dataset, independently calculate the down-gap cohort.

Reproduce:

```text
sample count
mean forward 5-day return
median
std
min
max
win rate
quartiles
```

Compare against:

```text
all sessions
non-gap sessions
up-gap sessions
```

Calculate where appropriate:

```text
mean difference
median difference
effect size
confidence interval
```

Do not rely only on average return.

Most importantly:

> The independent calculation must not call the same production function that created the original observation.

---

# 8. FORWARD-5-DAY TARGET AUDIT

Determine exactly how `forward 5-day return` is defined.

Check:

- 5 trading days vs calendar days
- entry price
- exit price
- holiday handling
- special sessions
- missing sessions
- off-by-one errors
- future information leakage

Confirm that the forward return is an evaluation label only and cannot reach the strategy entry decision.

---

# 9. LOOKAHEAD / DATA LEAKAGE AUDIT

Trace:

```text
raw data
→ feature
→ research behavior
→ research question
→ AI proposal
→ strategy spec
→ entry
→ execution
→ exit
```

For every entry input verify:

```text
availability_time <= decision_time
```

Check specifically:

- future prices
- forward returns
- centered rolling windows
- future VIX/OI
- future expiry information
- normalization
- cached features
- regime labels
- contract selection

Classify:

```text
CRITICAL
HIGH
MEDIUM
LOW
NONE_FOUND
```

---

# 10. MULTIPLE-TESTING / DATA-MINING AUDIT

This is a critical audit.

Phase I.3 reported:

```text
12 research questions
19 research behaviors
12 AI proposals
```

Determine the actual number of:

- behavior tests
- gap definitions
- thresholds
- horizons
- regime splits
- candidate strategy structures
- rejected hypotheses
- repeated tests

Explicitly investigate:

- Was the gap threshold selected after seeing outcomes?
- Was the 5-day horizon selected after comparing other horizons?
- Was PK-RQ-03 selected because it had the best result?
- Were alternative definitions tested?
- Was any failed candidate revised after seeing results?
- Was OOS ever used to choose a rule?

Record an estimate:

```text
TOTAL_HYPOTHESIS_TESTS
```

and assess selection bias.

---

# 11. SAMPLE SIZE

Report:

```text
gap events
strategy trades
development trades
OOS trades
trades by year
trades by month
trades by regime
```

Keep the existing rule:

```text
<20 trades = NOT_RELIABLE
```

Determine whether this rule is adequate for PK-RQ-03.

Provide uncertainty measures where appropriate.

---

# 12. PROFIT CONCENTRATION

Independently calculate:

```text
best trade contribution
top 2 contribution
top 3 contribution
best month contribution
worst month
median trade
median month
```

Determine whether the +₹23.6K result survives removal of its most influential trades.

This is diagnostic only, not optimization.

---

# 13. OOS AUDIT

Verify the exact development/OOS split.

Determine:

```text
OOS period
OOS trades
OOS net
OOS PF
OOS DD
OOS concentration
```

Check whether:

- OOS was defined before results
- OOS was reused for iteration
- thresholds were changed after viewing OOS
- the OOS sample is statistically meaningful

If insufficient:

```text
OOS_INSUFFICIENT
```

must remain.

---

# 14. TEMPORAL STABILITY

Using fixed PK-RQ-03 rules, report:

```text
year-by-year
quarter-by-quarter
month-by-month
regime-by-regime
```

Determine whether the candidate is:

```text
PERSISTENT
EPISODIC
ONE-PERIOD-DOMINATED
UNCLEAR
```

Do not optimize any thresholds during this analysis.

---

# 15. BASELINE CONTROLS

Compare PK-RQ-03 against:

```text
all sessions
no-trade control
current_control_v1
```

Use the same:

```text
dataset
cost model
slippage
expiry
evaluation
```

Do not change the comparison methodology to make the candidate look better.

---

# 16. ECONOMIC REALISM

Separate:

```text
statistical market effect
```

from:

```text
tradable strategy edge
```

Audit the conversion from gap behavior to actual strategy P&L.

Check:

- instrument choice
- option contract availability
- liquidity assumptions
- bid/ask assumptions
- fill timing
- overnight risk
- gamma/theta
- expiry
- lot size
- slippage
- commission

A real gap-bounce effect does NOT automatically imply an executable options edge.

---

# 17. DATA GRANULARITY

Check whether PK-RQ-03 requires intraday information while the research uses EOD data.

If the strategy needs unavailable information:

```text
DATA_GRANULARITY_INVALID
```

Do not accept false precision.

---

# 18. COST / SLIPPAGE RECOMPUTATION

Independently recalculate:

```text
gross P&L
commission
slippage
net P&L
```

Check for:

- wrong fee units
- wrong lot multiplier
- missing per-leg costs
- duplicated fees
- debit/credit sign errors
- slippage applied incorrectly

Determine whether the reported +₹23.6K is genuinely after the canonical cost model.

---

# 19. RISK AUDIT

Calculate:

```text
capital at risk
risk per trade
max theoretical loss
worst realized loss
drawdown
exposure concentration
```

Verify:

```text
declared risk == implemented risk
```

Look specifically for H3-style semantic mistakes:

```text
premium != credit
credit != max loss
notional != risk
```

---

# 20. OPTION CONTRACT AUDIT

If options are used, verify:

```text
underlying
expiry
strike
CE/PE
long/short
quantity
lot size
contract availability
canonical expiry
```

Check:

```text
no hardcoded Thursday
no future-week selection
no auto-roll
no lookahead
```

---

# 21. REPRODUCIBILITY

Run the existing PK-RQ-03 research twice where possible.

Require:

```text
same spec
same trades
same metrics
same normalized result hash
```

Investigate any nondeterminism.

---

# 22. REGIME AUDIT

Phase I.3 reported:

```text
3 regimes
A-heavy / calm mix
```

Verify:

- regime construction
- point-in-time safety
- stability
- PK-RQ-03 performance by regime
- whether regime labels depend on future data

Classify:

```text
REGIME_STABLE
REGIME_DEPENDENT
REGIME_UNCLEAR
```

---

# 23. AI HYPOTHESIS AUDIT

Inspect the original PK-RQ-03 AI proposal.

Separate:

```text
OBSERVED
INFERRED
HYPOTHESIS
```

Determine:

- Did the proposal use only information available before backtest?
- Was it revised after results?
- Does the final strategy spec match the proposal?
- Are there hidden assumptions?
- Did AI invent unsupported data?

---

# 24. RESEARCH MEMORY / NEGATIVE KNOWLEDGE

Inspect:

```text
strategy_research_memory/
```

Verify:

- failed hypotheses are recorded
- unsupported strategies are recorded
- reasons are preserved
- duplicates are prevented
- negative knowledge does not silently bias future research

---

# 25. RESOURCE AUDIT

Phase I.3 reports:

```text
CPU = 4 cores
RAM = 7.6 GiB
Workers = 3
Peak RAM ≈ 2.1 GB
```

Check actual behavior.

Assess:

- CPU utilization
- RAM
- swap
- disk
- multiprocessing safety
- cache behavior
- checkpointing
- subprocess overhead

Do not modify code.

---

# 26. PRODUCTION SAFETY

Verify:

```text
NO broker calls
NO live trading
NO paper-account writes
NO unintended Ground Truth writes
NO production historical-data mutation
```

Check research subprocesses and caches for unsafe write paths.

---

# 27. ARCHITECTURE AUDIT

Assess whether Phase I.3 added unnecessary complexity.

Inspect:

```text
feature engine
regime engine
behavior engine
question engine
AI packets
screening
runner
orchestrator
resource manager
cache
checkpointing
research memory
```

Rank architecture issues:

```text
CRITICAL
HIGH
MEDIUM
LOW
```

---

# 28. MAIN DECISION

Answer this directly:

> Is PK-RQ-03 an actual candidate for controlled paper validation, or is it currently only a statistical observation with an uncertain strategy transformation?

Use only these classifications:

```text
A — INVALID
B — DATA/IMPLEMENTATION BUG
C — STATISTICAL OBSERVATION ONLY
D — PROMISING BUT INSUFFICIENT
E — CONTROLLED PAPER CANDIDATE
```

Do not use `E` without strong evidence.

---

# 29. PROJECT DIRECTION

Evaluate:

```text
A. controlled validation of PK-RQ-03
B. deeper gap-behavior research
C. additional AI discovery
D. stronger OOS / walk-forward infrastructure
E. more execution families
F. better historical options data
G. pause strategy research
H. focus on research infrastructure
```

Rank by:

```text
scientific value
economic value
time cost
overfitting risk
```

Then give:

```text
STOP
START
CONTINUE
```

---

# 30. AUDIT REPORT

Create:

```text
audit/CLAUDE_SONNET_4_6_PHASE_I3_PK_RQ03_AUDIT.md
```

Required sections:

## Executive Verdict
## Phase I.3 Verification
## PK-RQ-03 Definition
## Independent GAP-Bounce Reproduction
## Lookahead / Leakage
## Multiple Testing
## Sample Size
## Profit Concentration
## OOS Audit
## Temporal Stability
## Baseline Comparison
## Economic Realism
## Data Granularity
## Cost / Slippage
## Risk
## Options Semantics
## Regime Audit
## AI Hypothesis Quality
## Research Memory
## Resource Usage
## Production Safety
## Architecture Quality
## Critical Findings
## STOP
## START
## CONTINUE
## Recommended Next 3 Actions
## Final Verdict

---

# 31. FINAL EXECUTIVE SUMMARY

Return exactly:

```text
CLAUDE SONNET 4.6 — INDEPENDENT AUDIT

Project Status:
<Healthy / Needs Correction / Major Concern>

Phase I.3 Integrity:
PASS / FAIL

PK-RQ-03 Reproduction:
PASS / FAIL

Independent GAP-Bounce Observation:
<summary>

Lookahead:
NONE_FOUND / CONCERN / LEAKAGE_FOUND

Multiple-Testing Risk:
LOW / MEDIUM / HIGH / CRITICAL

Sample Adequacy:
SUFFICIENT / INSUFFICIENT

OOS:
SUFFICIENT / INSUFFICIENT / INVALID

Profit Concentration:
LOW / MEDIUM / HIGH

Economic Realism:
PASS / CONCERN / FAIL

Risk Semantics:
PASS / CONCERN / FAIL

Execution Semantics:
PASS / CONCERN / FAIL

Reproducibility:
PASS / FAIL

Production Isolation:
PASS / FAIL

PK-RQ-03 Classification:
A / B / C / D / E

Platform Quality:
X/10

Research Quality:
X/10

Backtest Trust:
X/10

Biggest Problem:
<one sentence>

Biggest Strength:
<one sentence>

Most Important Next Action:
<one sentence>

Should We Paper-Test PK-RQ-03 Now?
YES / NO

Why:
<concise reason>
```

## FINAL INSTRUCTION

Be skeptical and independent.

Do not call +₹23.6K an edge merely because it is positive.

Do not reject the candidate merely because OOS is thin.

Determine whether:

```text
DATA
+
IMPLEMENTATION
+
STATISTICS
+
EXECUTION ECONOMICS
```

jointly justify continued controlled research.

Do not protect previous work.

Find what is wrong if something is wrong.
