# OpenCode — Phase I.3: Advanced Regime-Aware Research Discovery

## Objective

Phase I.2 is complete.

Current platform:

```text
Unified 646-session dataset
NIFTY + OPTIONS EOD + VIX + PARTICIPANT OI
Strategy Creator
Proposal Validator
Generic Strategy Execution
Deterministic Backtest
Evaluation
Ground Truth
Cost / Slippage
Canonical Expiry
Network Resilience
```

Phase I.1/I.2 showed:

- AI proposals can be structurally valid.
- Some AI proposals reach deterministic backtest.
- Several proposals have zero trades because their hypotheses are too restrictive.
- DeepSeek Iron Condor produced 12 trades, -₹1,027.50, PF 0.892 → NOT_RELIABLE.
- Some proposals remain unsupported because their semantics/data requirements are not supported.
- No durable edge has been proven.

The next problem is NOT:

> Generate more random strategies.

The next problem is:

> **Discover repeatable market behaviors first, convert those observations into research questions, then ask AI to build testable strategies around those questions.**

This phase is a **research-discovery engine**, not an autonomous trading engine.

Target pipeline:

```text
DATA
 ↓
MARKET / REGIME BEHAVIOR
 ↓
RESEARCH QUESTIONS
 ↓
AI HYPOTHESES
 ↓
SUPPORTED STRATEGY SPEC
 ↓
RISK / DATA / EXPIRY / LOOKAHEAD GATES
 ↓
DETERMINISTIC BACKTEST
 ↓
OOS / STABILITY / CONCENTRATION
 ↓
RESEARCH MEMORY
```

---

# 1. CRITICAL RULES

DO NOT:

- enable live trading
- place broker orders
- automatically paper trade
- automatically promote a strategy
- optimize a strategy for P&L
- run unrestricted parameter sweeps
- run genetic/Bayesian optimization
- execute AI-generated Python
- modify historical truth
- fabricate data
- forward-fill missing market observations as REAL
- modify Ground Truth
- modify paper_account.json
- modify current control
- modify Range-HV
- change canonical cost model
- change expiry semantics to improve results
- train/fine-tune AI models
- create an infinite self-learning loop
- generate hundreds/thousands of strategies blindly

This phase is:

```text
DISCOVERY
→ HYPOTHESIS
→ VALIDATION
→ EVIDENCE
```

---

# 2. READ AUTHORITATIVE PROJECT STATE

Read:

```text
audit/PHASE-I1-CONTROLLED-MULTI-MODEL-RESEARCH.md
audit/PHASE-I2-GENERIC-STRATEGY-EXECUTION.md
audit/PHASE-I-V2-AI-STRATEGY-RESEARCH-LAYER.md
audit/PHASE-H3-RANGE-HV-RISK-CONTRACT-INTEGRITY.md
audit/DATA-ALIGNMENT-01-UNIFIED-CALENDAR.md
audit/PHASE-H1-V2-STRATEGY-LAB.md
audit/PHASE-H2-RANGE-HV-VALIDATION.md
audit/PHASE-F3-EXPIRY-CONSISTENCY-BACKTEST.md
```

Inspect:

```text
strategy_proposal_schema.py
strategy_proposal_validator.py
strategy_proposal_compiler.py
strategy_proposal_registry.py
strategy_execution_capabilities.py
strategy_execution_registry.py
strategy_execution.py
ai_strategy_research.py
ai_strategy_lab.py
backtest_adapter.py
evaluation_engine.py
regime_filter.py
precision_signals.py
oi_intel.py
mcp_nifty.py
calendar_expiry.py
historical_expiry.py
```

Use ONLY:

```text
data/historical/manifests/unified_research_dataset.json
```

Do not silently use newer data.

---

# 3. RESEARCH QUESTION

Primary question:

> Which repeatable market behaviors exist in the unified dataset that could support a testable strategy hypothesis?

Research themes may include:

```text
volatility expansion after compression
volatility contraction persistence
trend persistence
trend exhaustion
mean reversion after extremes
OI concentration behavior
price/OI divergence
VIX-regime behavior
expiry-context behavior
range persistence
breakout failure
gap continuation/reversal
```

These are hypotheses, not assumed truths.

---

# 4. DATA AUDIT FIRST

Verify:

```text
calendar hash
dataset manifest hash
options hash
NIFTY hash
VIX hash
participant OI hash
expiry hash
```

Check:

```text
coverage
missing fields
date alignment
duplicate records
invalid values
```

If frozen input integrity fails:

```text
STOP
DATASET_INTEGRITY_FAILURE
```

---

# 5. USE THE LOCAL PC RESOURCES

The user explicitly wants the local PC used intelligently.

First inspect:

```bash
nproc
free -h
df -h
python --version
lscpu
```

Also inspect available Python/data-processing packages and BLAS/threading backend where practical.

Record:

```text
CPU cores
RAM
available disk
Python version
execution backend
```

Do not assume unlimited resources.

---

# 6. RESOURCE MANAGER

Create:

```text
research_resource_manager.py
```

Responsibilities:

```text
detect CPU
detect RAM
detect disk
choose worker count
control batch size
control cache size
detect memory pressure
reduce concurrency when needed
```

Safe default:

```text
CPU workers = max(1, physical_cores - 1)
RAM target <= 70% available RAM
keep >= 15% disk free
```

If the machine is under pressure:

```text
reduce workers
reduce batch size
flush cache
```

Do not allow uncontrolled OOM behavior.

Archive the resource configuration with the experiment.

---

# 7. DATA LOADING

Do NOT load the 1M+ option dataset separately for each task.

Prefer:

```text
shared read-only research context
column pruning
date filtering
symbol filtering
```

Load/normalize once where practical.

Use chunks if required.

Do not duplicate the full dataset per worker.

---

# 8. SQLITE SAFETY

If SQLite/research.db is accessed:

```text
read-only
```

Workers must never open writable production connections.

Prefer immutable/read-only connections or isolated read-only handles.

---

# 9. PARALLEL COMPUTATION

Parallelize only independent work:

```text
feature groups
research metrics
regime statistics
behavior tests
proposal evaluations
```

Do not parallelize writes to the same mutable file.

Use:

```text
worker → temporary result
main process → deterministic merge
```

---

# 10. REPRODUCIBLE PARALLELISM

Parallel execution must not change:

```text
sort order
grouping
aggregation
result hash
```

Before hashing, sort deterministically by explicit keys:

```text
date
timestamp
feature
regime
research_question
proposal_id
```

Run important analyses twice.

---

# 11. CACHE

Create:

```text
data/research_cache/
```

Cache immutable derived artifacts such as:

```text
daily features
regime labels
feature summaries
behavior statistics
transition matrices
```

Each cache item records:

```text
source dataset hash
code version
schema version
feature version
created_at
```

If source hash changes:

```text
CACHE_INVALID
```

and recompute.

Never silently reuse stale cache.

---

# 12. FEATURE ENGINE

Create:

```text
research_feature_engine.py
research_feature_registry.py
```

Generate deterministic features from available data.

Examples:

## Price

```text
daily return
multi-day return
range %
ATR-style volatility proxy
gap %
distance from rolling high/low
trend slope
mean distance
```

## Volatility

```text
VIX level
VIX change
VIX percentile
realized-volatility proxy
volatility expansion
volatility compression
```

## Options / OI

```text
OI concentration
OI change
OI concentration shift
put/call OI balance where valid
volume/OI ratio
strike concentration
underlying-vs-OI divergence
```

Only use fields genuinely present in the unified dataset.

---

# 13. FEATURE REGISTRY

Every feature must declare:

```text
feature_id
description
source_fields
lookback
point_in_time_safe
granularity
formula_version
```

Unknown/unregistered features cannot enter AI proposals.

---

# 14. NO LOOKAHEAD

Every feature at time/date `t` may use only:

```text
data <= t
```

Future labels may exist only as evaluation targets, never as entry features.

Explicitly test:

```text
future price
future VIX
future OI
future outcome
future expiry information
```

---

# 15. REGIME DISCOVERY

Do not rely only on existing hand-coded regime labels.

Investigate descriptive states for:

```text
trend
range
volatility
volatility transition
OI state
combined market state
```

Possible methods:

```text
rule-based descriptive regimes
quantile regimes
unsupervised clustering
```

Do NOT tune boundaries for P&L.

At discovery stage, call them:

```text
REGIME_A
REGIME_B
REGIME_C
```

until interpretation is supported.

---

# 16. REGIME STABILITY

For each discovered regime calculate:

```text
frequency
average duration
median duration
transition probability
monthly distribution
yearly distribution
VIX distribution
return distribution
```

Do not call a regime an “edge” yet.

---

# 17. REGIME TRANSITIONS

Analyze:

```text
REGIME_A → REGIME_B
REGIME_B → REGIME_C
```

and subsequent behavior.

Future returns are evaluation outcomes, not input features.

---

# 18. MARKET-BEHAVIOR ENGINE

Create:

```text
research_behavior_engine.py
```

Investigate deterministic descriptive relationships such as:

```text
volatility expansion after compression
trend continuation after strong move
mean reversion after extreme
OI expansion + price movement
OI contraction + price movement
range persistence
range breakout
breakout failure
VIX regime transition
expiry-context behavior
```

Output:

```text
observation
sample
frequency
conditional behavior
confidence/uncertainty
data limitations
```

Do not call it a profitable edge automatically.

---

# 19. MULTIPLE-TESTING CONTROL

This phase may test many relationships.

Record:

```text
hypotheses tested
hypotheses rejected
hypotheses interesting
```

Do not select the single highest result without accounting for the number of hypotheses examined.

If multiple-testing correction is appropriate, document the method.

---

# 20. RESEARCH-QUESTION ENGINE

Create:

```text
research_question_engine.py
```

Convert robust descriptive observations into:

```yaml
question_id:
observation:
market_context:
hypothesis:
required_data:
candidate_family:
expected_failure_modes:
```

Example:

```text
Observation:
A volatility transition persists for several sessions.

Question:
Can a defined-risk strategy exploit this transition
without using future information?
```

The question is NOT yet a strategy.

---

# 21. AI HYPOTHESIS PACKET

Only after deterministic discovery send a small research packet to AI models.

Packet may contain:

```text
research question
supporting statistics
regime description
available fields
supported execution families
data limitations
previous failures / negative knowledge
```

Do not send unnecessary raw proprietary data.

Separate:

```text
OBSERVED
INFERRED
HYPOTHESIS
```

clearly.

---

# 22. AI PROPOSAL GATES

Every AI proposal must:

```text
use registered features
use supported execution family
declare risk
declare expiry
declare data requirements
declare failure modes
remain point-in-time safe
```

Otherwise reject.

---

# 23. RESEARCH MEMORY

Create/extend:

```text
strategy_research_memory/
```

Store:

```text
observations
research_questions
AI_hypotheses
tested_strategies
failed_strategies
unsupported_strategies
reliability findings
```

Failed ideas are useful because they prevent repeated dead ends.

---

# 24. NEGATIVE KNOWLEDGE

Record explicit negative findings such as:

```text
DIRECTIONAL_SPREAD → weak PF
RANGE_HV → insufficient evidence / risk blocker
OPTION_BUY hypothesis → zero-trade under tested condition
OI/FII hypothesis → data limitation
```

Future AI receives these facts.

---

# 25. CONTROLLED RESEARCH BUDGET

Maximum for Phase I.3:

```text
12 research questions
2 AI hypotheses per question
24 AI proposals maximum
```

Do not automatically expand.

---

# 26. FAST SCREEN

Before full backtest:

```text
schema
risk
data
expiry
execution
sample-size sanity
```

Reject obvious dead ends:

```text
zero eligible days
risk invalid
unsupported execution
required data missing
```

Do not automatically reject valid low-frequency ideas; label them:

```text
LOW_FREQUENCY
```

---

# 27. FULL RESEARCH

Only screened proposals reach:

```text
full backtest
development/OOS
stability
concentration
risk normalization
```

Keep the evaluation vector.

No opaque score.

---

# 28. OOS / WALK-FORWARD

Where enough data exists:

```text
development
OOS
walk-forward observation
```

Do not tune on OOS.

If insufficient:

```text
OOS_INSUFFICIENT
```

---

# 29. SAMPLE-SIZE POLICY

Keep:

```text
<20 trades → NOT_RELIABLE
```

Also report:

```text
1–5
6–19
20–49
50+
```

Do not treat these groups equally.

---

# 30. PROFIT CONCENTRATION

Automatically calculate:

```text
best trade %
top 2 %
top 3 %
best month %
```

Flag:

```text
HIGH_CONCENTRATION
```

This is descriptive, not automatic rejection.

---

# 31. REGIME ROBUSTNESS

For any promising candidate evaluate:

```text
different regimes
different years
different months
OOS
```

A strategy working only in one narrow regime is:

```text
REGIME_SPECIFIC
```

not automatically robust.

---

# 32. COMPUTE-AWARE RESEARCH ORDER

Use the PC in stages:

### Stage 1 — cheap
```text
feature generation
descriptive statistics
regime discovery
correlations
transition matrices
```

### Stage 2 — moderate
```text
research-question evaluation
fast screens
candidate strategy construction
```

### Stage 3 — expensive
```text
full backtest
walk-forward
reproducibility
multi-model comparison
```

Do not waste expensive backtests on obviously invalid proposals.

---

# 33. CHECKPOINTING

Long jobs must checkpoint:

```text
results/phase_i3/checkpoints/
```

Save:

```text
completed tasks
failed tasks
dataset hash
resource config
run hash
```

Resume without repeating completed work.

---

# 34. PRODUCTION ISOLATION

Everything must write only to:

```text
results/phase_i3/
data/research_cache/
strategy_research_memory/
audit/
tests/
```

Never:

```text
data/ground_truth.db
paper_account.json
production signals
broker state
```

---

# 35. TESTS

Create:

```text
tests/test_phase_i3_research_discovery.py
```

Test:

- feature registry
- point-in-time safety
- deterministic feature generation
- regime discovery
- regime stability
- transition analysis
- behavior discovery
- multiple-testing accounting
- research-question generation
- research memory
- negative knowledge
- AI packet generation
- proposal constraints
- resource manager
- cache invalidation
- checkpoint/resume
- deterministic parallel results
- no production writes
- no broker calls

---

# 36. AUDIT REPORT

Create:

```text
audit/PHASE-I3-REGIME-AWARE-RESEARCH-DISCOVERY.md
```

Include:

## Objective
## Frozen Dataset
## PC Resource Profile
## Resource Configuration
## Feature Registry
## Regime Discovery
## Regime Stability
## Regime Transitions
## Behavior Discovery
## Multiple-Testing Accounting
## Research Questions
## AI Hypotheses
## Strategy Proposals
## Backtest Results
## OOS
## Negative Knowledge
## Compute Statistics
## Reproducibility
## Production Isolation
## Limitations
## Verdict

---

# 37. ACCEPTANCE CRITERIA

```text
Frozen dataset verified              PASS/FAIL
Resource manager                     PASS/FAIL
Feature registry                     PASS/FAIL
No-lookahead features                PASS/FAIL
Regime discovery                     PASS/FAIL
Regime stability                     PASS/FAIL
Transition analysis                  PASS/FAIL
Behavior discovery                   PASS/FAIL
Multiple-testing accounting          PASS/FAIL
Research-question generation         PASS/FAIL
AI research packet                   PASS/FAIL
Proposal validation                  PASS/FAIL
Generic execution                   PASS/FAIL
OOS / walk-forward                   PASS/FAIL
Research memory                      PASS/FAIL
Negative knowledge                   PASS/FAIL
Checkpoint/resume                    PASS/FAIL
Deterministic parallelism            PASS/FAIL
Production isolation                 PASS/FAIL
No broker calls                      PASS/FAIL
Tests                                PASS/FAIL
No optimization                      PASS/FAIL
```

All critical items must PASS.

---

# 38. STOP CONDITION

After the controlled discovery run:

STOP.

Do NOT:

- exceed 12 research questions
- exceed 24 AI proposals
- optimize winners
- mutate strategies
- paper trade
- live trade
- train models
- change historical truth
- automatically continue into another research cycle

Produce the audit report and stop.

---

# 39. FINAL RESPONSE

Return exactly:

```text
PHASE I.3 — REGIME-AWARE RESEARCH DISCOVERY

Dataset:
<manifest hash>

Sessions:
646

CPU Cores:
X

RAM:
X

Workers Used:
X

Peak RAM:
X

Research Questions:
X

AI Proposals:
X

Validated:
X

Rejected:
X

Execution Supported:
X

Backtests:
X

NOT_RELIABLE:
X

OOS_INSUFFICIENT:
X

Promising Candidates:
X

High-Concentration Candidates:
X

Regimes Discovered:
X

Research Behaviors:
X

Most Interesting Research Question:
<description / NONE>

Most Promising Candidate:
<proposal_id / NONE>

Evidence Quality:
<summary>

Negative Knowledge Added:
X

Reproducibility:
PASS/FAIL

Checkpoint/Resume:
PASS/FAIL

Production Data Untouched:
YES/NO

Broker Calls:
YES/NO

Optimization:
NO

Autonomous Loop:
NO

Tests:
PASS/FAIL

Most Important Finding:
<description>

Biggest Limitation:
<description>

Next Safe Phase:
REVIEW / CONTROLLED RESEARCH / PAPER VALIDATION / HOLD
```

## FINAL RULE

The objective is NOT to find the strategy with the highest historical P&L.

The objective is:

```text
MARKET BEHAVIOR
      ↓
RESEARCH QUESTION
      ↓
HYPOTHESIS
      ↓
TESTABLE STRATEGY
      ↓
EVIDENCE
```

Use local CPU/RAM/disk aggressively enough to make research practical, but conservatively enough to keep the desktop stable and results reproducible.

**Compute is for exploring the search space intelligently, not for hiding overfitting.**
