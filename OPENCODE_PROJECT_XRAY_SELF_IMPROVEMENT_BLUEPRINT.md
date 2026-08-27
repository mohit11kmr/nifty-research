# OpenCode — Project X-Ray, System Understanding & Self-Improvement Blueprint

The project has already completed:

- Deep audit
- Remediation
- Re-audit
- Security hardening
- Dependency hardening
- Backup verification
- Regression testing
- Final diff review
- Git commit preparation

Now the project must move to the **next development phase**.

Your task is NOT to fix old audit findings.

Your task is to deeply understand the existing system and produce a complete technical and operational blueprint explaining:

1. What this project actually is
2. What problem it solves
3. What it does
4. How it works
5. How data flows through it
6. How decisions are produced
7. What outputs/results it generates
8. How those results should be evaluated
9. Where the system currently learns/adapts
10. Where it does NOT learn/adapt
11. How the system can safely improve itself in the future

# CRITICAL RULE

## DO NOT MODIFY SOURCE CODE

During this entire task:

- Do not edit source code
- Do not refactor
- Do not change algorithms
- Do not change configuration
- Do not modify database schema
- Do not change trading/risk logic
- Do not install unnecessary dependencies

You may run safe read-only commands, inspect code, run existing tests where useful, and generate documentation.

The goal is:

**UNDERSTAND FIRST → DESIGN SECOND → IMPLEMENT LATER**

---

# PHASE 1 — Complete Repository X-Ray

Inspect the complete repository.

Identify:

- application entry points
- modules
- services
- utilities
- configuration
- data files
- database
- APIs
- broker integrations
- scheduled jobs
- background processes
- dashboards
- logging
- testing
- ML/statistical components
- signal-generation components
- risk-management components

Build a complete component inventory.

For every important file/module determine:

```text
File
Purpose
Inputs
Outputs
Dependencies
Side Effects
Called By
Calls
Persistent State
External Services
```

Do not describe files merely from their names.

Infer their real function from the implementation.

---

# PHASE 2 — Identify the Actual Purpose of the Project

Determine the project's actual purpose from the code.

Answer:

## What is this project?

Describe it in one precise paragraph.

## What problem does it solve?

Describe the actual problem the system attempts to solve.

## Who/what consumes its output?

Identify:

- human users
- dashboards
- trading processes
- broker APIs
- other services
- files/databases
- automated pipelines

Do not infer product claims that are not supported by the code.

Clearly distinguish:

```text
FACT
INFERENCE
UNKNOWN
```

---

# PHASE 3 — End-to-End Data Flow

Reconstruct the complete data pipeline.

For example, if applicable:

```text
Market Data
↓
Data Fetching
↓
Cleaning
↓
Normalization
↓
Feature Generation
↓
Indicators
↓
Market State
↓
Signal Generation
↓
Signal Scoring
↓
Risk Management
↓
Decision
↓
Paper/Live Execution
↓
Result Logging
↓
Evaluation
```

Use the actual project architecture.

Do not invent missing components.

Create a detailed data-flow diagram.

---

# PHASE 4 — Module Dependency Graph

Create a dependency graph showing:

```text
Module A
  ↓
Module B
  ↓
Module C
```

Identify:

- central modules
- bottlenecks
- single owners
- duplicated logic
- circular dependencies
- tightly coupled components
- critical paths

Explain which modules are critical to final output.

---

# PHASE 5 — Explain Every Major Decision

For every major decision made by the system, determine:

```text
INPUT
↓
TRANSFORMATION
↓
RULE / MODEL / FORMULA
↓
DECISION
↓
OUTPUT
```

For each decision explain:

- what data it uses
- what calculations it performs
- what thresholds exist
- what weights exist
- what assumptions exist
- what conditions cause rejection
- what conditions cause approval
- whether the logic is deterministic or adaptive

If mathematical formulas exist, document them.

If weights exist, document:

```text
Parameter
Current Value
Source
Purpose
Effect
Adaptive or Fixed
```

---

# PHASE 6 — Signal / Prediction / Decision Analysis

If the project generates signals, predictions, scores, recommendations, or decisions:

Identify:

- signal types
- signal sources
- feature sets
- scoring mechanisms
- confidence calculations
- thresholds
- filters
- market-state conditions
- risk controls
- final decision rules

Create a clear hierarchy:

```text
RAW DATA
→ FEATURES
→ SIGNALS
→ SCORE
→ FILTERS
→ RISK CHECK
→ FINAL DECISION
```

Explain exactly where false positives and false negatives can originate.

---

# PHASE 7 — Result Analysis

Determine what the project considers a “result”.

Examples may include:

- prediction
- signal
- trade
- profit/loss
- accuracy
- confidence
- risk-adjusted return
- execution quality
- system health

For every result determine:

```text
Expected Result
Actual Result
Measurement Method
Time Horizon
Success Criteria
Failure Criteria
```

Important:

Do not assume that a generated signal equals a successful result.

Separate:

```text
Prediction
Decision
Execution
Outcome
Evaluation
```

---

# PHASE 8 — Historical Evaluation

Inspect the existing historical data and logs.

Determine whether the system can answer questions such as:

- Which signals worked?
- Which signals failed?
- Under which market conditions?
- At what time?
- Which features contributed?
- Which model/rule produced them?
- What was the confidence?
- What was the actual outcome?
- How long until the outcome?
- What was the maximum favorable excursion?
- What was the maximum adverse excursion?

Identify exactly what data is already available and what data is missing.

---

# PHASE 9 — Current Learning / Adaptation

Audit all adaptive behavior.

Search specifically for:

- adaptive weights
- feedback loops
- parameter updates
- calibration
- model retraining
- rolling statistics
- historical performance adjustments
- reinforcement-like behavior
- self-tuning
- threshold adaptation
- regime detection
- signal scoring adaptation

For every adaptive mechanism document:

```text
What changes?
Why does it change?
What data causes the change?
How often does it change?
What prevents bad adaptation?
Can it revert?
Is it versioned?
Is it tested?
```

---

# PHASE 10 — Identify What Does NOT Learn

This is very important.

Explicitly list:

```text
Currently Adaptive
Currently Fixed
Currently Manual
Currently Missing
```

Do not call a fixed rule “AI” or “learning”.

---

# PHASE 11 — Self-Improvement Capability Audit

Determine whether the current project has the following:

```text
Observation
Evaluation
Failure Detection
Root Cause Analysis
Hypothesis Generation
Experimentation
Backtesting
Validation
Scoring
Versioning
Promotion
Rollback
```

Create a matrix:

| Capability | Exists | Partial | Missing | Evidence |
|---|---:|---:|---:|---|

---

# PHASE 12 — Safe Self-Improvement Architecture

Design a future architecture for controlled self-improvement.

The system should conceptually follow:

```text
OBSERVE
↓
COLLECT OUTCOMES
↓
MEASURE PERFORMANCE
↓
IDENTIFY WEAKNESS
↓
GENERATE HYPOTHESIS
↓
CREATE EXPERIMENT
↓
BACKTEST / SIMULATE
↓
COMPARE WITH BASELINE
↓
VALIDATE
↓
APPROVE / REJECT
↓
VERSION
↓
PROMOTE
↓
MONITOR
↓
ROLLBACK IF NECESSARY
```

Do NOT implement this yet.

Explain exactly how it should work.

---

# PHASE 13 — Self-Improvement Safety Rules

Design safeguards.

The future system must NOT be allowed to:

- modify production trading logic blindly
- promote untested models
- alter risk limits without authorization
- change capital protection logic automatically
- overfit historical data
- learn from corrupted data
- learn from future information / data leakage
- promote a model based on a single successful period
- replace the baseline without comparison
- delete historical evidence

Require:

- experiments
- baselines
- versioning
- statistical validation
- rollback
- monitoring
- audit logs
- promotion criteria

---

# PHASE 14 — Measure Whether an Improvement Is Real

Design a framework for determining whether a change is actually better.

Possible metrics may include:

```text
Accuracy
Precision
Recall
Expected Value
Profit Factor
Sharpe Ratio
Sortino Ratio
Maximum Drawdown
Win Rate
Average Win
Average Loss
Risk-adjusted return
Signal stability
False positive rate
False negative rate
Latency
Execution quality
```

Only use metrics that actually make sense for this project.

Explain:

- baseline
- comparison period
- out-of-sample testing
- walk-forward testing
- regime separation
- statistical significance where appropriate
- overfitting controls

---

# PHASE 15 — Market Regime / Environment Analysis

If applicable, determine whether the system understands different environments such as:

- trending
- sideways
- high volatility
- low volatility
- gap conditions
- event-driven periods
- abnormal liquidity

Determine whether current logic behaves differently across regimes.

If not, identify this as a possible future improvement.

---

# PHASE 16 — Failure Analysis Engine

Design how the system should learn from failures.

For every failed decision, future architecture should ideally record:

```text
Timestamp
Market State
Input Features
Signal
Confidence
Decision
Risk State
Execution
Outcome
Error
Probable Cause
```

Then classify failures into categories such as:

```text
Data Error
Feature Error
Signal Error
Regime Error
Risk Error
Execution Error
Timing Error
Model Error
Unknown
```

Do not implement this yet.

---

# PHASE 17 — Knowledge / Memory Architecture

Design what the system should remember.

Separate:

```text
Raw Data
Historical Outcomes
Experiments
Models
Parameters
Market Regimes
Failures
Successful Patterns
Rejected Hypotheses
System Decisions
```

Define what should be persisted and what should not.

Avoid allowing uncontrolled memory growth.

---

# PHASE 18 — What Should Become AI?

Do NOT recommend AI simply because it sounds advanced.

Determine which parts should remain:

- deterministic rules
- statistical methods
- optimization
- ML
- LLM/AI-assisted analysis
- human approval

For each candidate component explain:

```text
Why AI?
Expected benefit
Risk
Data requirement
Validation requirement
Complexity
```

---

# PHASE 19 — Current Project Strengths

Identify the strongest parts of the existing architecture.

Especially mention:

- reliable components
- good risk controls
- useful datasets
- reusable modules
- strong testing
- good logging
- valuable feedback signals
- existing adaptive systems

---

# PHASE 20 — Current Weaknesses

Identify the most important weaknesses preventing the system from becoming substantially more advanced.

Prioritize them:

```text
CRITICAL
HIGH
MEDIUM
LOW
```

Focus on real architectural limitations rather than cosmetic issues.

---

# PHASE 21 — Roadmap

Create a roadmap with phases.

## Phase A — Understanding

Already being performed now.

## Phase B — Observability

Improve:

- event logging
- outcome tracking
- metrics
- experiment records

## Phase C — Evaluation

Add:

- baseline evaluation
- backtesting
- walk-forward testing
- regime analysis

## Phase D — Controlled Adaptation

Add:

- parameter optimization
- adaptive weights
- model comparison
- hypothesis engine

## Phase E — Self-Improvement

Add:

- failure analysis
- experiment generation
- automated validation
- model promotion
- rollback

## Phase F — Production Intelligence

Add:

- monitoring
- drift detection
- anomaly detection
- continuous evaluation
- controlled retraining

For every phase provide:

```text
Goal
Required Components
Dependencies
Risk
Expected Benefit
Success Criteria
```

---

# PHASE 22 — Produce Documentation

Create the following documentation WITHOUT modifying source code:

```text
PROJECT-XRAY.md
SYSTEM-ARCHITECTURE.md
DATA-FLOW.md
DECISION-ENGINE.md
RESULT-EVALUATION.md
CURRENT-LEARNING.md
SELF-IMPROVEMENT-BLUEPRINT.md
ADVANCEMENT-ROADMAP.md
```

If equivalent documents already exist, update them rather than creating duplicates.

---

# PROJECT-XRAY.md

Must answer in plain language:

1. What is this project?
2. What does it do?
3. Why does it exist?
4. What enters the system?
5. What happens internally?
6. What comes out?
7. Who consumes the output?
8. What are the most important modules?
9. What are the biggest risks?
10. What is the current maturity level?

---

# FINAL EXECUTIVE SUMMARY

At the end, provide this:

```text
PROJECT:
<precise description>

PRIMARY PURPOSE:
<description>

INPUTS:
<list>

CORE PROCESS:
<description>

OUTPUTS:
<list>

CURRENT ADAPTIVE COMPONENTS:
<list>

CURRENT NON-ADAPTIVE COMPONENTS:
<list>

CURRENT SELF-IMPROVEMENT LEVEL:
__/10

OBSERVABILITY:
__/10

EVALUATION:
__/10

ADAPTATION:
__/10

AUTOMATION:
__/10

PRODUCTION MATURITY:
__/10

TOP 10 ADVANCEMENT OPPORTUNITIES:
1.
2.
3.
4.
5.
6.
7.
8.
9.
10.

TOP 5 RISKS OF FUTURE SELF-IMPROVEMENT:
1.
2.
3.
4.
5.
```

---

# FINAL RULE

Do not modify application code during this task.

Do not install an AI/ML system merely for appearance.

Do not claim that the project “learns” unless the code actually demonstrates adaptive behavior.

Clearly separate:

**WHAT EXISTS**

from

**WHAT SHOULD BE BUILT**

and from

**WHAT IS UNKNOWN**

The final output must give a technically accurate mental model of the entire project so that the next phase can safely transform it into a measurable, controlled, self-improving system.
