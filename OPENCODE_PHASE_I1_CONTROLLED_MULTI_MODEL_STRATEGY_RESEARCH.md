# OpenCode — Phase I.1: Controlled Multi-Model Strategy Research

## Objective

Phase I — AI Strategy Research Pipeline is complete and verified.

The project now has:

```text
AI / Human Proposal
        ↓
Proposal Schema
        ↓
Proposal Validator
        ↓
Risk / Data / Expiry / Lookahead Gates
        ↓
Existing Strategy Compiler
        ↓
Deterministic Backtest
        ↓
Evaluation Vector
        ↓
Baseline Comparison
        ↓
Human Review
```

Verified Phase I behavior:

- Range-HV example reproduces H2 exactly: 6 trades, +₹6,248.25, PF 9.693.
- Current control reproduction: 48 trades, +₹1,906.43, PF 1.011.
- Small-sample research is honestly classified as `NOT_RELIABLE` below 20 trades.
- Proposal provenance, immutable registration, deterministic result hashes, lookahead/risk/data gates, and human review are implemented.

The next objective is NOT to build an autonomous strategy generator.

The objective is:

> **Measure whether different AI models can produce genuinely useful, non-duplicate, researchable strategy hypotheses under the same deterministic research environment.**

This is a controlled experiment on the **research quality of AI-generated strategy proposals**.

---

# 1. CRITICAL RULES

DO NOT:

- enable live trading
- automatically paper trade
- automatically promote any proposal
- call broker order endpoints
- change the current control strategy
- modify Range-HV
- change risk rules
- change expiry rules
- change the unified historical dataset
- optimize parameters
- run unrestricted parameter sweeps
- allow AI-generated Python execution
- allow model output to bypass validation
- train or fine-tune models
- create an autonomous generation/retry loop
- generate hundreds/thousands of strategies
- select a winner based only on backtest P&L

This phase must remain:

```text
CONTROLLED
REPRODUCIBLE
MODEL-COMPARABLE
RESEARCH-ONLY
```

---

# 2. READ AUTHORITATIVE PHASE DOCUMENTS

Read:

```text
audit/PHASE-I-V2-AI-STRATEGY-RESEARCH-LAYER.md
audit/PHASE-H3-RANGE-HV-RISK-CONTRACT-INTEGRITY.md
audit/DATA-ALIGNMENT-01-UNIFIED-CALENDAR.md
audit/PHASE-H1-V2-STRATEGY-LAB.md
audit/PHASE-H2-RANGE-HV-VALIDATION.md
```

Inspect:

```text
strategy_proposal_schema.py
strategy_proposal_validator.py
strategy_proposal_compiler.py
strategy_proposal_registry.py
ai_strategy_research.py
ai_strategy_lab.py
strategy_schema.py
strategy_validator.py
strategy_compiler.py
backtest_adapter.py
evaluation_engine.py
```

Use the frozen research dataset:

```text
data/historical/manifests/unified_research_dataset.json
```

---

# 3. EXPERIMENT DESIGN

Compare a small number of AI models under the same research contract.

Target models:

```text
Big Pickle
DeepSeek
Qwen Coder / another approved coding-reasoning model
```

Do not assume a model is available.

If a target model is unavailable:

```text
MODEL_UNAVAILABLE
```

and continue with the available models.

Do not install paid services or purchase API access automatically.

---

# 4. FAIRNESS REQUIREMENTS

Every model must receive the same:

```text
research prompt
strategy schema
field registry
project-rule allowlist
dataset manifest
research window
development/OOS split
cost model
slippage model
expiry model
risk rules
proposal limits
```

Do NOT give one model extra historical information unavailable to the others.

Do NOT tell one model the performance of another model before its proposal is frozen.

---

# 5. RESEARCH PROMPT

Create a single canonical prompt:

```text
prompts/AI_MULTI_MODEL_RESEARCH_V1.md
```

The prompt should instruct each model:

```text
You are generating a research hypothesis, not a trading signal.

Use only the registered Strategy Specification language.

You must:
- propose one strategy hypothesis
- explain why it might work
- define its failure modes
- declare required data
- declare instrument
- declare regime
- declare entry conditions
- declare risk
- declare exits
- declare expiry behavior
- stay point-in-time safe
- avoid arbitrary code
- output a structured proposal

You must not:
- claim profitability before testing
- use future information
- modify the platform risk model
- change the historical dataset
- bypass validation
- place orders
- refer to another model's result
```

---

# 6. CONTROLLED PROPOSAL BUDGET

Start small.

Maximum:

```text
3 models
×
3 proposals per model
=
9 proposals total
```

No more than 9 proposals in this phase.

Do not automatically expand the budget if results are poor.

---

# 7. STRATEGY DIVERSITY REQUIREMENT

Each model should attempt three materially different research directions:

### Proposal A — Directional

Example concept:

```text
trend-following
```

### Proposal B — Mean Reversion / Range

Example concept:

```text
range/reversion
```

### Proposal C — Defined Risk Options Structure

Example concept:

```text
defined-risk multi-leg options
```

These are categories only.

The model must create its own compliant hypothesis.

Do NOT seed specific profitable rules.

---

# 8. NO DUPLICATE STRATEGIES

Before backtest:

calculate:

```text
strategy_spec_hash
normalized_rule_fingerprint
```

Reject:

```text
DUPLICATE_PROPOSAL
```

Also detect semantic near-duplicates where the only change is cosmetic wording.

Do not count:

```text
RSI > 60
```

and:

```text
RSI >= 60.0
```

as a new strategy if all meaningful behavior is equivalent.

Record:

```text
UNIQUE
NEAR_DUPLICATE
EXACT_DUPLICATE
```

---

# 9. PROPOSAL FREEZE

For every model:

1. Generate proposal.
2. Save exact raw model output.
3. Convert to structured proposal.
4. Calculate proposal hash.
5. Freeze proposal.
6. Only then run validation.

The model cannot revise a proposal after seeing validation/backtest results.

A revised proposal counts as a NEW proposal and consumes another slot.

---

# 10. BLIND MODEL EVALUATION

Do not let models see:

```text
other model names/results
other proposals
comparison leaderboard
backtest outcomes
```

until all proposals are frozen.

---

# 11. VALIDATION

Every proposal goes through the exact Phase I gates:

```text
schema
field registry
operator registry
lookahead
point-in-time
risk
capital
instrument
expiry
data requirements
project-rule allowlist
```

Any failure blocks the proposal from backtest.

Record:

```text
VALIDATED
or
REJECTED
```

with structured failure reasons.

---

# 12. BACKTEST

Only validated unique proposals proceed.

Use:

```text
same unified dataset manifest
same development/OOS split
same cost model
same slippage model
same expiry model
same evaluation engine
```

No strategy-specific backtest shortcuts.

---

# 13. SAMPLE-SIZE RULE

Keep the existing evaluation rule:

```text
<20 trades
→ NOT_RELIABLE
```

Do not relax it.

A model does not "win" because it finds a strategy with:

```text
3 trades
PF 20
```

That is insufficient evidence.

---

# 14. EVALUATION VECTOR

For each proposal report:

```text
trades
wins
losses
win rate
gross P&L
fees
slippage
net P&L
PF
expectancy
max DD
max single-trade loss
MFE
MAE
average hold
trade frequency
profit concentration
regime performance
development performance
OOS performance
risk validity
data completeness
complexity
```

Do not compress this into one proprietary "AI score."

---

# 15. MODEL-LEVEL METRICS

For each model calculate:

```text
proposals submitted
proposals valid
validation pass rate
duplicate rate
backtest completion rate
average trades
median trades
NOT_RELIABLE rate
average PF
median PF
average net P&L
OOS survival rate
risk-validity rate
data-validity rate
```

Do NOT rank models by average P&L alone.

---

# 16. RESEARCH QUALITY METRICS

Evaluate each model on:

```text
1. Validity
2. Novelty
3. Risk correctness
4. Data compatibility
5. OOS quality
6. Sample sufficiency
7. Stability
8. Interpretability
9. Complexity
10. Research usefulness
```

A proposal with lower P&L but strong validity and OOS behavior may be more valuable than a high-P&L small-sample proposal.

---

# 17. BASELINE COMPARISON

Every valid proposal must be compared to:

```text
current_control_v1
```

using identical research settings.

Do NOT compare using different windows or different costs.

Optionally show:

```text
range_hv_iron_condor_v1
directional_spread_v1
```

as contextual references.

---

# 18. OOS DISCIPLINE

The model must not be allowed to see OOS results before proposal freeze.

Research process:

```text
PROPOSAL
↓
FREEZE
↓
VALIDATE
↓
BACKTEST
↓
EVALUATE
```

No:

```text
result
↓
edit
↓
rerun
```

within the same proposal slot.

A revised strategy becomes a new proposal.

---

# 19. RESULT REGISTRY

Extend the proposal registry with:

```text
experiment_id
model_id
model_version
proposal_id
proposal_hash
strategy_spec_hash
dataset_manifest_hash
result_hash
status
validation_status
backtest_status
review_status
```

Store all model outputs immutably.

---

# 20. REPRODUCIBILITY

For every frozen proposal:

Run the deterministic research engine twice.

Require:

```text
same strategy spec
same trades
same metrics
same result_hash
```

apart from explicitly removed runtime timestamps.

AI generation itself may be nondeterministic, but once the proposal is frozen, the research result must be deterministic.

---

# 21. HUMAN REVIEW

After all 9 proposal results are available, create a review table.

Human decisions:

```text
REJECT
KEEP FOR FUTURE RESEARCH
REQUEST MORE DATA
CONTROLLED PAPER CANDIDATE
```

No proposal is automatically promoted.

---

# 22. NO PAPER TRADING IN THIS PHASE

Even if a proposal shows:

```text
PF > 1
positive P&L
good OOS
```

do NOT automatically start paper trading.

The goal is to evaluate the AI research process itself.

Paper promotion is a separate future decision.

---

# 23. DATA ARCHIVE AWARENESS

The research layer must continue using the frozen unified dataset.

Do not mix new Angel One live-archive data into this experiment.

Future archive data is a separate research asset.

---

# 24. TESTS

Create:

```text
tests/test_phase_i1_multi_model.py
```

Test:

- same canonical prompt enforcement
- proposal freezing
- proposal hashing
- duplicate detection
- near-duplicate detection
- model isolation
- validation
- fixed dataset manifest
- fixed development/OOS split
- sample-size rule
- result reproducibility
- model-level aggregation
- registry
- human review
- no production writes
- no broker calls
- compute budget

---

# 25. EXPERIMENT REPORT

Create:

```text
audit/PHASE-I1-CONTROLLED-MULTI-MODEL-RESEARCH.md
```

Include:

## Objective

## Models Tested

## Canonical Prompt

## Dataset

## Research Window

## Development / OOS Split

## Proposal Budget

## Proposal Inventory

## Validation Results

## Duplicate / Novelty Analysis

## Backtest Results

## Evaluation Vectors

## Model-Level Metrics

## OOS Results

## Risk Validity

## Data Quality

## Reproducibility

## Human Review

## Limitations

## Verdict

---

# 26. IMPORTANT: DO NOT DECLARE A "BEST MODEL"

Do not conclude:

```text
Big Pickle is best
DeepSeek is best
Qwen is best
```

based on 3 proposals.

The correct conclusion may be:

```text
INSUFFICIENT EXPERIMENT
NO CLEAR MODEL ADVANTAGE
```

That is acceptable.

---

# 27. STOP CONDITION

After the 9-proposal experiment:

STOP.

Do NOT:

- generate more proposals
- optimize the best proposal
- mutate strategies
- paper trade automatically
- live trade
- train models
- change the unified dataset
- change current strategy logic

Wait for human review.

---

# 28. FINAL RESPONSE

Return exactly:

```text
PHASE I.1 — CONTROLLED MULTI-MODEL STRATEGY RESEARCH

Models:
<list>

Total Proposal Budget:
9

Proposals Generated:
X

Validated:
X

Rejected:
X

Duplicates:
X

Near-Duplicates:
X

Backtests Completed:
X

NOT_RELIABLE:
X

OOS_INSUFFICIENT:
X

Control Baseline:
48 trades / PF 1.011 / net +₹1,906.43

Best Research Candidate:
<proposal_id / NONE>

Best Candidate Trades:
X

Best Candidate PF:
<value / NOT_RELIABLE>

Best Candidate OOS:
<summary>

Model Comparison:
<summary>

Most Novel Model:
<model / NONE>

Highest Validity:
<model / NONE>

Highest Research Utility:
<model / NONE>

Clear Model Advantage:
YES / NO / INSUFFICIENT_EXPERIMENT

Reproducibility:
PASS/FAIL

Production Data Untouched:
YES/NO

Broker Calls:
YES/NO

Optimization:
NO

Automatic Promotion:
NO

Tests:
PASS/FAIL

Most Important Finding:
<description>

Biggest Limitation:
<description>

Next Safe Phase:
REVIEW / CONTROLLED PAPER CANDIDATE / MORE RESEARCH / HOLD
```

## FINAL RULE

This phase is not about finding a profitable strategy.

It is about answering:

> **Can different AI models reliably produce valid, novel, testable strategy hypotheses inside our deterministic research framework?**

The correct system is:

```text
MODEL PROPOSES
      ↓
PLATFORM VALIDATES
      ↓
SAME DATA
      ↓
SAME BACKTEST
      ↓
SAME EVALUATION
      ↓
HUMAN REVIEWS
```

No model gets an advantage from hidden data, result-driven revisions, or shortcuts around the research gates.
