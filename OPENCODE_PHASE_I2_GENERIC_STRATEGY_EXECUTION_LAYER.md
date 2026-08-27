# OpenCode — Phase I.2: Generic Strategy Execution Layer
## Expand Deterministic Execution Coverage for AI-Generated Strategy Specifications

## 0. OBJECTIVE

Phase I.1 exposed the current bottleneck.

Results:

```text
Big Pickle    3/3 proposals validated
DeepSeek      3/3 proposals validated
Qwen          MODEL_UNAVAILABLE
Unique        6/6
Duplicates    0
Backtests     0
```

The six valid proposals all reached:

```text
EXECUTION_UNSUPPORTED
```

Therefore:

> The immediate bottleneck is not AI proposal quality. It is execution coverage of the deterministic backtest engine.

The project now needs a **Generic Strategy Execution Layer** that can execute any strategy specification composed from registered, supported strategy primitives.

This phase must NOT become an unrestricted trading-code interpreter.

The goal is:

```text
VALID STRATEGY SPEC
        ↓
CAPABILITY CHECK
        ↓
GENERIC EXECUTION FAMILY
        ↓
DETERMINISTIC BACKTEST
        ↓
EVALUATION
```

---

# 1. CRITICAL RULES

DO NOT:

- enable live trading
- automatically paper trade
- call broker order endpoints
- modify current control strategy behavior
- change Range-HV strategy rules
- change risk semantics to make a strategy executable
- introduce arbitrary Python execution
- allow AI-generated code to execute
- create an unrestricted strategy DSL
- silently fall back to fake execution
- fabricate fills
- fabricate option quotes
- fabricate OI
- fabricate expiry
- use future information
- optimize parameters
- run parameter sweeps
- mutate strategies after seeing results
- modify Ground Truth
- modify paper_account.json
- modify canonical historical data
- auto-promote a strategy

This phase is:

```text
EXECUTION CAPABILITY EXPANSION
```

not:

```text
STRATEGY OPTIMIZATION
```

---

# 2. READ AUTHORITATIVE DOCUMENTS

Read:

```text
audit/PHASE-I1-CONTROLLED-MULTI-MODEL-RESEARCH.md
audit/PHASE-I-V2-AI-STRATEGY-RESEARCH-LAYER.md
audit/PHASE-H3-RANGE-HV-RISK-CONTRACT-INTEGRITY.md
audit/PHASE-H1-V2-STRATEGY-LAB.md
audit/PHASE-H2-RANGE-HV-VALIDATION.md
audit/PHASE-F3-EXPIRY-CONSISTENCY-BACKTEST.md
audit/DATA-ALIGNMENT-01-UNIFIED-CALENDAR.md
```

Inspect:

```text
strategy_schema.py
strategy_validator.py
strategy_compiler.py
strategy_proposal_schema.py
strategy_proposal_validator.py
strategy_proposal_compiler.py
ai_strategy_research.py
strategy_proposal_registry.py
backtest_adapter.py
premium_seller.py
backtest_frozen.py
multi_strategy_backtest.py
paper_execution.py
exit_evaluator.py
capital_guard.py
evaluation_engine.py
```

Also inspect the actual six I.1 proposals and their validation/execution failure reasons.

---

# 3. FIRST TASK — DIAGNOSE EXECUTION_UNSUPPORTED

Before writing new execution code:

For all six Phase I.1 proposals:

```text
identify exact unsupported reason
group failures by capability
```

Create a table:

| Proposal | Family | Valid | Unsupported Reason | Existing Primitive Missing |
|---|---|---|---|---|

Do not assume all six failures have the same cause.

Possible categories:

```text
ENTRY_UNSUPPORTED
INSTRUMENT_UNSUPPORTED
POSITION_CONSTRUCTION_UNSUPPORTED
RISK_UNSUPPORTED
EXIT_UNSUPPORTED
DATA_FIELD_UNSUPPORTED
EXPIRY_UNSUPPORTED
P&L_UNSUPPORTED
COST_MODEL_UNSUPPORTED
MULTI_LEG_UNSUPPORTED
```

This diagnosis is mandatory before implementation.

---

# 4. EXECUTION FAMILY ARCHITECTURE

Create a registry of deterministic execution families.

Suggested initial families:

```text
OPTION_BUY
OPTION_SELL
BULL_CALL_SPREAD
BEAR_PUT_SPREAD
CALL_CREDIT_SPREAD
PUT_CREDIT_SPREAD
IRON_CONDOR
DEFINED_RISK_RANGE
DIRECTIONAL_SPOT
DIRECTIONAL_FUTURE
MEAN_REVERSION_SPOT
```

Only include a family when the current project has enough deterministic information to implement it correctly.

If a family is not supported:

```text
EXECUTION_UNSUPPORTED
```

Do not fake support.

---

# 5. GENERIC EXECUTION INTERFACE

Create:

```text
strategy_execution.py
```

with a stable interface conceptually similar to:

```python
class StrategyExecutor:
    family_id
    validate_capability(spec)
    construct_position(context)
    generate_entry(context)
    simulate_fill(order, context)
    calculate_risk(position, context)
    evaluate_exit(position, context)
    calculate_pnl(position, market_context)
```

Do not duplicate the existing execution engine unnecessarily.

Reuse:

```text
paper_execution
exit_evaluator
cost model
MTM
expiry service
capital_guard
```

where appropriate.

---

# 6. EXECUTION FAMILY REGISTRY

Create:

```text
strategy_execution_registry.py
```

Support:

```text
register family
lookup family
capability check
compile executor
list supported families
```

The compiler should resolve:

```text
strategy_spec.instrument
```

to a registered execution family.

---

# 7. CAPABILITY MATRIX

Create:

```text
strategy_execution_capabilities.py
```

Each family declares:

```text
family_id
entry_supported
multi_leg
risk_supported
expiry_supported
stop_supported
target_supported
MTM_supported
cost_model_supported
required_data
supported_market_types
```

Example:

```yaml
family_id: IRON_CONDOR

entry_supported: true
multi_leg: true
risk_supported: true
expiry_supported: true
stop_supported: true
target_supported: true
MTM_supported: true
cost_model_supported: true

required_data:
  - NIFTY
  - OPTIONS_EOD
```

Do not claim a capability until it has tests.

---

# 8. NO ARBITRARY CODE

The execution layer must never execute:

```text
aI-generated Python
eval
exec
shell
imports
dynamic code strings
```

AI output remains declarative.

---

# 9. OPTION CONTRACT CONSTRUCTION

For option-based strategies, deterministic construction must validate:

```text
underlying
expiry
strike
CE/PE
lot size
quantity
leg relationships
```

For spreads:

```text
same expiry
correct side relationship
positive wing width
valid strike ordering
```

For iron condor:

```text
long put < short put
short call < long call
all four legs same expiry
positive put wing
positive call wing
```

Do not silently repair invalid legs.

---

# 10. PREMIUM AND UNIT SEMANTICS

Use explicit units:

```text
premium per unit
premium per contract
premium per leg
net credit/debit
lot size
quantity
```

The H3 lesson is mandatory:

```text
control premium ≠ condor credit
```

The execution layer must not reuse the wrong premium field between strategy families.

Every family must define its own unit semantics.

---

# 11. RISK SEMANTICS

Every execution family must define:

```text
risk basis
maximum theoretical loss
capital requirement
capital-at-risk
risk percentage
```

Risk must never be inferred from a generic field without a family-specific definition.

Reject:

```text
RISK_SEMANTIC_UNDEFINED
```

if a family cannot determine risk correctly.

---

# 12. MULTI-LEG P&L

Create deterministic per-leg accounting:

```text
entry premium
exit premium
quantity
lot size
direction
fees
slippage
```

Aggregate:

```text
gross P&L
fees
slippage
net P&L
```

Do not duplicate the canonical cost engine.

---

# 13. EXPIRY

Use the canonical expiry service.

Never use:

```text
hardcoded Thursday
next Thursday
weekday guess
```

The executor must call the project expiry service.

If expiry cannot be resolved:

```text
EXPIRY_UNRESOLVED
```

and no trade is simulated.

---

# 14. HISTORICAL DATA CAPABILITY

The executor must know what data it is allowed to use.

Current unified research assets include:

```text
NIFTY
OPTIONS_EOD
VIX
PARTICIPANT_OI
```

But historical intraday option ticks are not complete.

Therefore each execution family must declare:

```text
minimum required granularity
```

Example:

```text
EOD strategy
→ OPTIONS_EOD acceptable

intraday stop/target strategy
→ OPTIONS_INTRADAY required
```

Do not simulate intraday behavior from EOD data unless the strategy explicitly operates at EOD.

---

# 15. NO FALSE FILL PRECISION

If only EOD data exists:

Do not pretend:

```text
09:17:31 fill
```

exists.

Use explicit execution resolution:

```text
EOD
INTRADAY
TICK
```

and reject a strategy requiring finer resolution than available.

---

# 16. EXISTING STRATEGY COMPATIBILITY

Current existing strategies must continue to work:

```text
current_control_v1
range_hv_iron_condor_v1
directional_spread_v1
```

Their behavior must remain unchanged.

This phase expands capability.

It must not alter existing results.

---

# 17. CONTROL EQUIVALENCE

Re-run:

```text
current_control_v1
```

and require the existing reference to remain equivalent.

Acceptance:

```text
same trades
same direction
same entries
same exits
same P&L
```

within existing deterministic tolerance.

If not:

```text
STOP
CONTROL_REGRESSION
```

---

# 18. RANGE-HV REGRESSION

Re-run:

```text
range_hv_iron_condor_v1
```

and require the existing H2 frozen reference to remain equivalent where the H2 dataset is used:

```text
6 trades
+₹6,248.25
PF 9.693
```

Do NOT use this as proof of profitability.

This is an execution-regression check.

---

# 19. PHASE I.1 REPLAY

Once execution families are implemented:

Re-run the six frozen Phase I.1 proposals.

For each report:

```text
VALID
EXECUTION_SUPPORTED
BACKTEST_COMPLETED
```

or:

```text
EXECUTION_UNSUPPORTED
```

If supported, produce deterministic results.

Do not modify the proposals after freeze.

---

# 20. NO RESULT-DRIVEN STRATEGY CHANGES

Do not allow:

```text
proposal
→ backtest fails
→ AI changes proposal
→ same proposal ID
```

If the strategy changes:

```text
new proposal ID
new hash
new experiment slot
```

---

# 21. EXECUTION DIFFERENCE FROM OPTIMIZATION

This phase may add support for:

```text
new execution family
```

It may NOT change:

```text
entry thresholds
exit thresholds
risk values
strategy parameters
```

Adding a generic execution capability is infrastructure work.

Changing strategy behavior is not allowed.

---

# 22. TEST MATRIX

Create:

```text
tests/test_phase_i2_execution_capabilities.py
```

Test at minimum:

## Capability
- supported family detection
- unsupported family detection
- capability matrix

## Option Buy
- contract selection
- premium units
- lot size
- cost
- P&L

## Spreads
- leg ordering
- same expiry
- wing widths
- net credit/debit
- P&L
- risk

## Iron Condor
- four-leg construction
- same expiry
- call wing
- put wing
- credit semantics
- maximum loss
- fees
- slippage

## Expiry
- canonical expiry
- unresolved expiry rejection

## Data resolution
- EOD strategy
- intraday-required rejection
- tick-required rejection

## Regression
- current control equivalence
- Range-HV equivalence

## Phase I.1
- replay each frozen proposal
- remove `EXECUTION_UNSUPPORTED` only when genuinely supported

## Safety
- arbitrary code rejected
- no broker calls
- no Ground Truth writes
- no paper-account writes

---

# 23. PERFORMANCE

Do not optimize prematurely.

Avoid re-loading full datasets separately for every proposal where safe.

Use a shared read-only research context where appropriate.

Cache only immutable dataset artifacts.

Do not cache mutable/live state.

---

# 24. AUDIT REPORT

Create:

```text
audit/PHASE-I2-GENERIC-STRATEGY-EXECUTION.md
```

Include:

## I.1 Execution Failure Diagnosis
## Execution Families Added
## Capability Matrix
## Generic Executor API
## Option Contract Construction
## Risk Semantics
## Premium Units
## Multi-Leg P&L
## Expiry Integration
## Data Granularity Gates
## Control Regression
## Range-HV Regression
## I.1 Proposal Replay
## Test Results
## Production Isolation
## Remaining Unsupported Families
## Limitations
## Verdict

---

# 25. ACCEPTANCE CRITERIA

```text
I.1 failure diagnosis                    PASS/FAIL
Execution family registry                PASS/FAIL
Capability matrix                       PASS/FAIL
Generic executor interface              PASS/FAIL
Option contract construction             PASS/FAIL
Premium unit semantics                   PASS/FAIL
Risk semantics                           PASS/FAIL
Multi-leg accounting                    PASS/FAIL
Canonical expiry integration             PASS/FAIL
Data-resolution gate                    PASS/FAIL
Current control equivalence             PASS/FAIL
Range-HV regression                     PASS/FAIL
I.1 proposal replay                     PASS/FAIL
Production isolation                    PASS/FAIL
No broker calls                         PASS/FAIL
No arbitrary code execution             PASS/FAIL
Tests                                   PASS/FAIL
No optimization                         PASS/FAIL
```

---

# 26. STOP CONDITION

After implementation and regression tests:

STOP.

Do NOT:

- generate additional AI proposals
- optimize any strategy
- run parameter sweeps
- automatically paper trade
- live trade
- add autonomous AI loops
- change historical truth

First review Phase I.2.

---

# 27. FINAL RESPONSE

Return exactly:

```text
PHASE I.2 — GENERIC STRATEGY EXECUTION LAYER

I.1 Execution Failure Diagnosis:
<summary>

Execution Families Supported:
<list>

Execution Families Added:
<list>

Capability Matrix:
PASS/FAIL

Generic Executor:
PASS/FAIL

Option Contract Construction:
PASS/FAIL

Premium Unit Semantics:
PASS/FAIL

Risk Semantics:
PASS/FAIL

Multi-Leg Accounting:
PASS/FAIL

Canonical Expiry:
PASS/FAIL

Data Resolution Gates:
PASS/FAIL

Current Control Equivalence:
MATCH / MISMATCH

Range-HV Regression:
MATCH / MISMATCH

I.1 Proposals:
X

I.1 Backtests Now Supported:
X

Still EXECUTION_UNSUPPORTED:
X

Tests:
PASS/FAIL

Production Data Untouched:
YES/NO

Broker Calls:
YES/NO

Optimization:
NO

Most Important Finding:
<description>

Remaining Unsupported Families:
<description>

Next Safe Phase:
REVIEW / I1 REPLAY / MORE EXECUTION COVERAGE / HOLD
```

## FINAL RULE

The objective is NOT to make every possible strategy executable.

The objective is:

> **Make every strategy that can be expressed using a defined, safe, deterministic execution family genuinely backtestable.**

If a strategy remains unsupported, report exactly why.

Never replace missing execution semantics with guesses.
