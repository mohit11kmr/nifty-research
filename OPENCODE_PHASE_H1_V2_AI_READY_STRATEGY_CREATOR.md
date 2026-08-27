# OpenCode — Phase H1 v2: AI-Ready Strategy Creator MVP

## Objective

Turn NIFTY-RESEARCH into a reusable, model-independent Strategy Research Platform.

Current Phase H research says:

- Current strategy: 48 trades, 33.3% win rate, PF 1.011, net +₹1,906.43 — CONTROL / edge unproven.
- Directional spread: 24 trades, 20.8% win rate, PF 0.473, net -₹44,398.33 — WEAK.
- RANGE-HV Iron Condor: 6 trades, 66.7% win rate, PF 9.693, net +₹6,248.25, max DD -₹587 — PROMISING BUT INSUFFICIENT SAMPLE.
- No-trade control: zero risk but no return.

The long-term architecture is:

```text
Human / AI
    ↓
Strategy Specification
    ↓
Validator
    ↓
Compiler
    ↓
Canonical Strategy API
    ↓
Backtest / Paper
    ↓
Ground Truth
    ↓
Evaluation
```

The platform must work regardless of whether a strategy specification was authored by a human, Big Pickle, DeepSeek, Qwen Coder, or another future model.

## CRITICAL RULE

Do NOT:

- change the current production strategy
- change frozen thresholds
- change RANGE_LV behavior
- change SL/TP/capital/expiry rules
- optimize parameters
- run parameter sweeps
- add AI optimization or self-learning
- enable live trading
- create real-money trades
- fabricate data
- rewrite Ground Truth
- replace the existing execution/outcome engines
- allow arbitrary Python inside strategy definitions

The purpose is to build a **safe, explicit, versioned, auditable strategy-definition layer** above the existing infrastructure.

---

# 1. READ CURRENT PROJECT

Read:

```text
audit/MASTER-PROJECT-BLUEPRINT.md
audit/PHASE-E-FROZEN-STRATEGY-BACKTEST.md
audit/PHASE-F3-EXPIRY-CONSISTENCY-BACKTEST.md
audit/PHASE-G-NETWORK-RESILIENCE.md
audit/EXTERNAL-ARCHITECTURE-BENCHMARK.md
audit/EXTERNAL-ADOPTION-ROADMAP.md
audit/TRADING_DECISION_FLOW.md
```

Inspect:

```text
precision_signals.py
regime_filter.py
market_brain.py
oi_intel.py
capital_guard.py
smart_strike_selector.py
paper_execution.py
paper_trader.py
exit_evaluator.py
paper_mtm.py
ground_truth.py
evaluation_engine.py
backtest_frozen.py
premium_seller.py
historical_expiry.py
calendar_expiry.py
```

Current source is authoritative.

---

# 2. TARGET ARCHITECTURE

Implement:

```text
STRATEGY CREATOR
      ↓
STRATEGY SPEC
      ↓
VALIDATOR
      ↓
COMPILER
      ↓
CANONICAL STRATEGY API
   ↙             ↘
BACKTEST        PAPER
   ↘             ↙
     GROUND TRUTH
          ↓
      EVALUATION
```

The Strategy Creator must not directly place orders or bypass risk, execution, MTM, exits, Ground Truth, or evaluation.

---

# 3. MODEL INDEPENDENCE

Any model can author the same strategy specification:

```text
Human
Big Pickle
DeepSeek
Qwen Coder
Future AI
```

All must target the same schema.

No model-specific strategy semantics.

No model gets direct broker/Ground Truth authority.

---

# 4. MVP STORAGE

Use YAML for MVP.

Create:

```text
strategies/
    current_control.yaml
    range_hv_iron_condor_v1.yaml
    directional_spread_v1.yaml
```

Do not invent rules merely to fill files. If a candidate cannot be represented safely:

```text
NOT_SPECIFIABLE
```

---

# 5. VERSIONED STRATEGY SCHEMA

At minimum support:

```text
strategy_id
name
version
schema_version
description
market
regime
entry
direction
instrument
strike_selection
risk
exit
execution
data_requirements
```

Conceptual example:

```yaml
schema_version: "1.0"

strategy:
  id: range_hv_iron_condor_v1
  name: Range-HV Iron Condor
  version: 1

market:
  underlying: NIFTY

regime:
  allowed:
    - RANGE_HV

entry:
  conditions:
    all:
      - field: REGIME
        operator: "=="
        value: RANGE_HV

direction:
  mode: NEUTRAL

instrument:
  type: DEFINED_RISK_RANGE

strike_selection:
  rule: EXISTING_PROJECT_RULE

risk:
  rule: EXISTING_PROJECT_RULE

exit:
  stop:
    rule: EXISTING_PROJECT_RULE
  target:
    rule: EXISTING_PROJECT_RULE
  expiry:
    rule: CANONICAL_EXPIRY

data_requirements:
  - NIFTY
  - OPTIONS
  - OI
```

First inspect existing capabilities and reduce/adjust the schema to fit the actual project.

---

# 6. CONTROLLED FIELD REGISTRY

Do NOT allow arbitrary Python expressions.

Create a registry containing only supported project fields, such as:

```text
REGIME
ADX
EMA20
EMA50
RSI
PCR
OI_WALL
SKEW
MAX_PAIN
VIX
FII_SENTIMENT
ML_VERDICT
SPOT
ATR
```

Safe operators:

```text
>
>=
<
<=
==
!=
AND
OR
NOT
```

Unknown field/operator = validation error.

---

# 7. LOOKAHEAD PROTECTION

Strategy-time fields must obey:

```text
timestamp <= decision_time
```

Reject concepts like:

```text
tomorrow_close
future_vix
future_oi
future_high
future_low
future_outcome
```

unless represented separately as post-trade evaluation labels.

---

# 8. STRATEGY VALIDATOR

Create:

```text
strategy_validator.py
```

Validate:

```text
schema
identity
underlying
regimes
conditions
direction
instrument
strike rule
risk
exit
expiry
data requirements
registered fields
operators
lookahead safety
supported combinations
```

Enforce:

```text
risk defined
exit defined
expiry defined when required
instrument supported
required data declared
```

Output must be deterministic.

---

# 9. STRATEGY COMPILER

Create:

```text
strategy_compiler.py
```

Concept:

```text
compile(strategy_spec) → CompiledStrategy
```

Provide stable methods such as:

```text
evaluate(context)
generate_candidate(context)
build_order(candidate, context)
build_exit_rules(position, context)
```

Reference existing:

```text
capital_guard
paper_execution
exit_evaluator
Ground Truth
```

Do not duplicate those engines.

---

# 10. STRATEGY REGISTRY

Create:

```text
strategy_registry.py
```

Support:

```text
list
load by id/version
validate
compile
spec hash
```

Filesystem registry is acceptable for MVP.

Do not create another database unnecessarily.

---

# 11. STRATEGY VERSIONING

Every strategy has:

```text
strategy_id
version
spec_hash
```

Changing rules creates a new version.

Never silently mutate an existing specification.

---

# 12. LIFECYCLE

Support:

```text
DRAFT
VALIDATED
BACKTESTED
REVIEW
PAPER
PROMOTED
REJECTED
RETIRED
```

Promotion must always be explicit; do not auto-promote.

---

# 13. CURRENT CONTROL SPEC

Create:

```text
strategies/current_control.yaml
```

Represent the exact current frozen strategy.

This is a formal representation, NOT a strategy change.

Run the compiled specification against the same frozen F3 dataset.

Compare:

```text
daily regime
signals
confluence
direction
candidates
entries
exits
trade list
P&L
```

Any unexplained difference is a BLOCKER.

---

# 14. RANGE-HV IRON CONDOR SPEC

Create:

```text
strategies/range_hv_iron_condor_v1.yaml
```

Use the exact frozen Phase H candidate rules already in the repository.

Do NOT:

- change strike width
- change delta
- change target
- change stop
- change expiry
- add new filters
- optimize

Current evidence:

```text
6 trades
66.7% win rate
PF 9.693
net +₹6,248.25
max DD -₹587
```

Classify it as:

```text
PROMISING_BUT_INSUFFICIENT
```

Do not promote it.

---

# 15. DIRECTIONAL SPREAD SPEC

Create:

```text
strategies/directional_spread_v1.yaml
```

only if it can be represented exactly from the frozen Phase H candidate.

Do not improve it.

If unsupported:

```text
NOT_SPECIFIABLE
```

---

# 16. BACKTEST ADAPTER

Create a thin adapter allowing:

```text
CompiledStrategy
```

to be used by the existing backtest framework.

Do not rewrite the entire backtester.

---

# 17. CONTROL EQUIVALENCE — MANDATORY

This is the primary H1 proof.

Compile:

```text
strategies/current_control.yaml
```

Run against the frozen F3 dataset.

Require matching:

```text
signals
candidates
directions
trades
entries
exits
P&L
```

within documented deterministic tolerance.

If mismatch:

```text
STOP
REPORT MISMATCH
DO NOT PROCEED
```

---

# 18. PAPER ADAPTER

Build an adapter/interface showing that a compiled strategy can feed the existing paper engine.

For H1:

- prove compatibility
- do not switch production paper runner automatically
- keep current control active

---

# 19. CLI

Create:

```text
strategy_lab.py
```

Minimum commands:

```bash
python strategy_lab.py list
python strategy_lab.py validate strategies/current_control.yaml
python strategy_lab.py validate strategies/range_hv_iron_condor_v1.yaml
python strategy_lab.py inspect strategies/current_control.yaml
python strategy_lab.py compile strategies/current_control.yaml
```

Do not build the web UI yet.

---

# 20. AI MODEL COMPATIBILITY

Document this future role split:

```text
Big Pickle / coding agent
→ repository implementation

Reasoning model
→ architecture review / second opinion

Qwen Coder or similar coding model
→ repository-heavy implementation/review

Deterministic Strategy Engine
→ actual strategy semantics
```

Model switching must not require changing the Strategy Engine.

---

# 21. FUTURE AI STRATEGY GENERATION — DOCUMENT ONLY

Do not implement yet.

Future path:

```text
AI
↓
Strategy Proposal
↓
Schema Validation
↓
Lookahead Validation
↓
Compiler
↓
Backtest
↓
Compare
↓
Human Review
↓
Paper
```

AI must never directly reach a broker.

---

# 22. PRODUCTION SAFETY

The Strategy Creator must not modify:

```text
data/ground_truth.db
paper_account.json
production signal state
live broker state
```

Validation/compilation tests use isolated fixtures.

---

# 23. TESTS

Create:

```text
tests/test_strategy_creator.py
tests/test_strategy_validator.py
tests/test_strategy_compiler.py
tests/test_strategy_registry.py
```

Test:

### Schema
- valid spec
- missing field
- unknown field
- invalid operator
- invalid instrument
- invalid risk
- invalid exit

### Validator
- lookahead rejection
- unknown field rejection
- unsupported instrument
- missing data requirement
- invalid regime
- invalid condition

### Compiler
- deterministic compilation
- stable interface
- spec hash

### Registry
- list
- load
- version
- hash

### Control equivalence
- same decisions
- same candidates
- same trades
- same exits
- same P&L

### Candidate compatibility
- Range-HV spec loads/validates/compiles
- Directional spread spec loads if supported

### Isolation
- no Ground Truth writes
- no paper account writes
- no production mutation

---

# 24. DOCUMENTATION

Create:

```text
audit/PHASE-H1-V2-STRATEGY-CREATOR-MVP.md
```

Include:

## Why Strategy Creator

## Architecture

## Schema

## Registered Fields

## Validator

## Compiler

## Registry

## CLI

## Current Control Specification

## Range-HV Candidate Specification

## Directional Spread Specification

## Control Equivalence

## AI Model Independence

## Tests

## Limitations

## Future AI Strategy Generation

---

# 25. DO NOT BUILD WEB UI YET

Do not spend H1 effort on:

```text
drag-and-drop editor
charts
dashboard
authentication
multi-user accounts
```

Engine first.

---

# 26. DO NOT BUILD AI GENERATOR YET

H1 only builds the safe specification contract that future AI generators will target.

---

# 27. NO OPTIMIZATION

Do NOT:

- tune parameters
- search best delta
- search best spread width
- search best target
- search best stop
- search best expiry
- run genetic algorithms
- run Bayesian optimization
- train an AI strategy search model

---

# 28. ACCEPTANCE CRITERIA

```text
Strategy schema                         PASS/FAIL
Validator                              PASS/FAIL
Lookahead protection                   PASS/FAIL
Field registry                         PASS/FAIL
Compiler                              PASS/FAIL
Registry                              PASS/FAIL
Versioning                             PASS/FAIL
Spec hashing                           PASS/FAIL

Current Control YAML                   PASS/FAIL
Range-HV Candidate YAML                PASS/FAIL
Directional Spread YAML                PASS/FAIL/NOT_SPECIFIABLE

Control Equivalence                    PASS/FAIL
Backtest Adapter                       PASS/FAIL
Paper Adapter Interface                PASS/FAIL
AI-Model Independence                 PASS/FAIL
Production Isolation                  PASS/FAIL
Reproducibility                        PASS/FAIL
Tests                                  PASS/FAIL
No Optimization                        PASS/FAIL
No Strategy Mutation                  PASS/FAIL
```

All critical items must PASS.

---

# 29. STOP AFTER H1 v2

After completion:

STOP.

Do NOT:

- build web UI
- build AI strategy generator
- optimize strategies
- run parameter searches
- change production strategy
- enable live trading
- promote Range-HV
- start paper testing automatically

Review H1 v2 first.

---

# FINAL RESPONSE

Return exactly:

```text
PHASE H1 v2 — AI-READY STRATEGY CREATOR MVP

Schema:
PASS/FAIL

Validator:
PASS/FAIL

Lookahead Protection:
PASS/FAIL

Field Registry:
PASS/FAIL

Compiler:
PASS/FAIL

Registry:
PASS/FAIL

Versioning:
PASS/FAIL

Spec Hashing:
PASS/FAIL

Current Control Spec:
PASS/FAIL

Range-HV Iron Condor Spec:
PASS/FAIL

Directional Spread Spec:
PASS/FAIL/NOT_SPECIFIABLE

Control Equivalence:
MATCH / MISMATCH

Backtest Adapter:
PASS/FAIL

Paper Adapter Interface:
PASS/FAIL

AI-Model Independence:
PASS/FAIL

Production Data Untouched:
YES/NO

Strategy Mutated:
YES/NO

Optimization Performed:
NO

Tests:
PASS/FAIL

Most Important Finding:
<description>

Remaining Limitations:
<list>

Next Safe Phase:
REVIEW / H2 RANGE-HV VALIDATION / H2 WEB UI / HOLD
```

## FINAL RULE

The Strategy Creator is not a profit generator.

It is the **contract between humans/AI models and the deterministic trading research engine**.

Its job is to make strategies:

```text
explicit
versioned
validated
point-in-time safe
reproducible
backtestable
paper-compatible
auditable
```

Only after this contract is proven should AI-assisted strategy generation be added.
