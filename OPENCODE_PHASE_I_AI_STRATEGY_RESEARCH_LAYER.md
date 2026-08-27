# OpenCode — Phase I: AI Strategy Research Layer

## Objective

H3 is closed. The project now has:

```text
Unified 646-session historical dataset
Strategy Creator / Validator / Compiler
Backtest + Paper architecture
Ground Truth
Cost / Slippage / MTM
Auto-Exit
Expiry consistency
Network resilience
```

Current strategy evidence remains:

```text
Current Control        = EDGE UNPROVEN
Directional Spread     = WEAK
Range-HV Iron Condor   = PROMISING BUT UNPROVEN
```

The next long-term product goal is:

> Build an AI-assisted Strategy Research Layer where an AI model proposes a structured strategy hypothesis, while the deterministic platform validates, compiles, backtests, evaluates, and rejects unsafe or invalid proposals.

This is NOT an autonomous trading system.

AI is a research hypothesis generator.

The deterministic platform is the gatekeeper.

---

# CRITICAL RULES

DO NOT:

- enable live trading
- call broker order endpoints
- automatically create paper positions
- automatically promote strategies
- automatically select a winner
- optimize parameters
- run unrestricted parameter sweeps
- execute AI-generated Python
- let AI modify production strategy files
- let AI modify Ground Truth
- let AI modify paper_account.json
- let AI alter risk/expiry rules
- fabricate historical data
- use future information
- silently replace missing data
- train an autonomous self-learning loop

Goal:

```text
AI PROPOSAL
→ SAFE SPECIFICATION
→ VALIDATION
→ BACKTEST
→ EVIDENCE
```

---

# 1. READ THE AUTHORITATIVE PROJECT STATE

Read:

```text
audit/DATA-ALIGNMENT-01-UNIFIED-CALENDAR.md
audit/PHASE-H1-V2-STRATEGY-LAB.md
audit/PHASE-H2-RANGE-HV-VALIDATION.md
audit/PHASE-H3-RANGE-HV-RISK-CONTRACT-INTEGRITY.md
audit/PHASE-H-MULTI-STRATEGY-BACKTEST.md
audit/PHASE-F3-EXPIRY-CONSISTENCY-BACKTEST.md
audit/PHASE-G-NETWORK-RESILIENCE.md
```

Inspect:

```text
strategy_schema.py
strategy_validator.py
strategy_compiler.py
strategy_registry.py
strategy_lab.py
backtest_adapter.py
paper_adapter.py
evaluation_engine.py
ground_truth.py
capital_guard.py
paper_execution.py
exit_evaluator.py
data/historical/manifests/unified_research_dataset.json
```

Current source and frozen artifacts are authoritative.

---

# 2. TARGET ARCHITECTURE

```text
HUMAN / AI
     ↓
STRATEGY PROPOSAL
     ↓
PROPOSAL VALIDATOR
     ↓
EXISTING STRATEGY VALIDATOR
     ↓
RISK / DATA / EXPIRY GATES
     ↓
STRATEGY COMPILER
     ↓
BACKTEST
     ↓
EVALUATION
     ↓
HUMAN REVIEW
```

AI must never bypass deterministic gates.

---

# 3. MODEL INDEPENDENCE

The interface must work with:

```text
Big Pickle
DeepSeek
Qwen Coder
other LLMs
future local models
```

The platform accepts YAML/JSON and does not depend on a specific model.

---

# 4. PROPOSAL SCHEMA

Create:

```text
strategy_proposal_schema.py
```

A proposal should contain:

```text
proposal_id
title
author_type
author_model
created_at
parent_strategy_id
hypothesis
research_question
market
regimes
entry
direction
instrument
strike_selection
risk
exit
data_requirements
expected_failure_modes
```

Example:

```yaml
proposal:
  id: ai_proposal_0001
  author_type: AI
  author_model: <model>
  title: "Example Research Hypothesis"
  hypothesis: "..."
  research_question: "..."

strategy:
  ...
```

Do not invent missing strategy fields automatically.

---

# 5. PROPOSAL → EXISTING STRATEGY SPEC

Pipeline:

```text
AI proposal
↓
proposal parser
↓
proposal validator
↓
existing Strategy Specification
↓
strategy_validator.py
↓
strategy_compiler.py
```

Reuse the existing strategy system.

Do NOT create a parallel strategy engine.

---

# 6. ALLOWED BUILDING BLOCKS

AI may compose only registered platform primitives.

Use existing:

```text
FIELD_REGISTRY
PROJECT_RULE_ALLOWLIST
supported instruments
canonical expiry
existing exit/risk rules
```

Do not create arbitrary Python expressions.

---

# 7. ARBITRARY-CODE REJECTION

Reject proposals containing:

```text
eval
exec
import
os.system
subprocess
shell commands
arbitrary Python
```

Status:

```text
REJECTED_ARBITRARY_CODE
```

---

# 8. LOOKAHEAD GATE

Inherit existing no-lookahead rules.

Reject references such as:

```text
future_
tomorrow
next_close
future_vix
future_oi
future_high
future_low
outcome
realized_pnl
exit_price
```

Also validate semantic point-in-time safety.

---

# 9. RISK GATE

Before backtest verify:

```text
risk defined
capital basis defined
position size defined
maximum loss defined where applicable
instrument risk bounded
exit defined
expiry defined
```

For multi-leg option structures verify:

```text
leg relationships
same expiry
strike ordering
wing width
credit semantics
maximum loss
```

Use lessons from H3.

Invalid risk semantics must reject the proposal before performance testing.

---

# 10. DATA GATE

Every proposal declares:

```text
required datasets
required fields
required granularity
minimum history
```

Use:

```text
data/historical/manifests/unified_research_dataset.json
```

where possible.

If required data is unavailable:

```text
DATA_INSUFFICIENT
```

Do not silently substitute another source.

---

# 11. FIXED RESEARCH WINDOW

Every backtest must carry:

```text
dataset_manifest_hash
start_date
end_date
```

The AI must not choose a favorable window after seeing results.

---

# 12. DEVELOPMENT / OUT-OF-SAMPLE

Define the chronological split before evaluation.

Do not tune using OOS.

If insufficient:

```text
OOS_INSUFFICIENT
```

---

# 13. CANONICAL COST / EXECUTION

All proposals use the same project:

```text
commission
slippage
fill model
MTM
expiry
P&L
```

AI cannot change the cost model.

---

# 14. BACKTEST GATE

Only proposals passing:

```text
schema
lookahead
risk
data
instrument
expiry
execution
```

reach the deterministic backtest.

---

# 15. EVALUATION

Use the existing evaluator.

Report:

```text
trades
win rate
gross P&L
fees
slippage
net P&L
profit factor
expectancy
max drawdown
max single-trade loss
MFE
MAE
average hold
trade frequency
profit concentration
regime performance
OOS performance
```

Use:

```text
INSUFFICIENT_SAMPLE
NOT_RELIABLE
```

when appropriate.

---

# 16. NO SINGLE "AI SCORE"

Do not create one opaque score.

Return a research vector:

```text
edge quality
sample size
stability
drawdown
risk validity
data quality
regime robustness
OOS quality
trade frequency
profit concentration
execution realism
complexity
```

AI may summarize; it cannot override numerical evidence.

---

# 17. FAILURE REASONS

Use structured failure codes:

```text
SCHEMA_ERROR
LOOKAHEAD_ERROR
RISK_ERROR
EXPIRY_ERROR
DATA_INSUFFICIENT
UNSUPPORTED_INSTRUMENT
EXECUTION_UNSUPPORTED
OOS_INSUFFICIENT
SAMPLE_INSUFFICIENT
DUPLICATE_PROPOSAL
```

Never allow the model to bypass a rejection.

---

# 18. PROPOSAL REGISTRY

Create:

```text
strategy_proposals/
```

Store:

```text
proposal
model identity
prompt/template version
created timestamp
strategy spec hash
dataset manifest hash
result hash
status
```

Statuses:

```text
DRAFT
VALIDATED
BACKTESTED
REVIEW
REJECTED
PAPER_CANDIDATE
RETIRED
```

Promotion must remain explicit.

---

# 19. PROVENANCE

Every proposal must preserve:

```text
proposal_hash
strategy_spec_hash
dataset_hash
result_hash
model identity
creation timestamp
```

Once frozen, the research result must be deterministic.

---

# 20. DUPLICATE DETECTION

Compare:

```text
strategy spec hash
normalized rule fingerprint
```

Reject exact duplicates:

```text
DUPLICATE_PROPOSAL
```

Do not count cosmetic changes as new research.

---

# 21. COMPUTE BUDGET

Add conservative limits:

```text
max proposals per run
max backtests per session
max compute budget
```

Do not generate thousands of strategies automatically.

---

# 22. MODEL RESEARCH TEMPLATE

Create:

```text
prompts/AI_STRATEGY_RESEARCH_TEMPLATE.md
```

The template must tell the model:

- propose a structured strategy specification
- use only registered fields
- use only supported instruments/rules
- declare data requirements
- declare risk
- declare exit
- declare expiry
- state why it might work
- state why it might fail
- output no executable code
- claim no profitability before testing
- never bypass validation

---

# 23. CLI

Create:

```text
ai_strategy_lab.py
```

Minimum:

```bash
python ai_strategy_lab.py list
python ai_strategy_lab.py inspect <proposal.yaml>
python ai_strategy_lab.py validate <proposal.yaml>
python ai_strategy_lab.py compile <proposal.yaml>
python ai_strategy_lab.py research <proposal.yaml>
python ai_strategy_lab.py compare <proposal.yaml>
```

Do NOT implement autonomous generation loops yet.

---

# 24. BASELINE COMPARISON

Every AI proposal must be compared under the same dataset/cost model against:

```text
current_control_v1
```

Where appropriate also show:

```text
range_hv_iron_condor_v1
directional_spread_v1
```

Do not rank on net P&L alone.

---

# 25. NO SELF-LEARNING YET

Do NOT implement:

```text
automatic retraining
online learning
reinforcement learning
self-modifying prompts
automatic parameter evolution
automatic strategy mutation
```

This phase only builds the safe proposal/evaluation layer.

---

# 26. HUMAN REVIEW GATE

After research:

```text
AI proposal
↓
research evidence
↓
HUMAN REVIEW
```

Human choices:

```text
REJECT
REQUEST_MORE_DATA
RUN_CONTROLLED_PAPER_TEST
```

No automatic paper/live promotion.

---

# 27. SAMPLE PROPOSALS

Create at most two simple:

```text
EXAMPLE_ONLY
NOT_FOR_TRADING
```

proposals solely to prove the pipeline.

Do not claim profitability.

---

# 28. TESTS

Create:

```text
tests/test_ai_strategy_layer.py
```

Test:

- valid proposal
- invalid proposal
- proposal → spec conversion
- unknown field rejection
- arbitrary-code rejection
- lookahead rejection
- risk rejection
- unsupported instrument
- expiry rejection
- data requirement validation
- duplicate detection
- deterministic compilation
- deterministic backtest
- control comparison
- result hashing
- provenance
- proposal registry
- no production writes
- no broker calls
- human review gate

---

# 29. PRODUCTION SAFETY

The AI layer must not modify:

```text
data/ground_truth.db
paper_account.json
production signals
production outcomes
broker state
```

Phase I is research only.

---

# 30. DOCUMENTATION

Create:

```text
audit/PHASE-I-AI-STRATEGY-RESEARCH-LAYER.md
```

Include:

## Objective
## Architecture
## AI Role
## Model Independence
## Proposal Schema
## Validator
## Risk Gate
## Data Gate
## Backtest Gate
## Evaluation
## Registry
## Provenance
## Human Review
## Safety Boundaries
## Tests
## Known Limitations
## Future Work

---

# 31. FUTURE WORK — DOCUMENT ONLY

Do not implement yet:

```text
multi-model debate
AI strategy generator
strategy mutation
walk-forward optimizer
Bayesian optimization
genetic search
reinforcement learning
online model learning
automatic paper promotion
live deployment
```

Future target:

```text
AI
→ propose
→ validate
→ backtest
→ compare
→ learn only from VERIFIED outcomes
→ propose next hypothesis
```

Human approval remains required.

---

# 32. ACCEPTANCE CRITERIA

```text
Proposal schema                         PASS/FAIL
Proposal validator                      PASS/FAIL
Model independence                      PASS/FAIL
Arbitrary-code rejection                PASS/FAIL
Lookahead protection                    PASS/FAIL
Risk gate                              PASS/FAIL
Data gate                              PASS/FAIL
Expiry gate                            PASS/FAIL
Execution compatibility                PASS/FAIL
Backtest gate                          PASS/FAIL
Evaluation                             PASS/FAIL
Baseline comparison                    PASS/FAIL
Proposal registry                      PASS/FAIL
Version/hash provenance                PASS/FAIL
Duplicate detection                    PASS/FAIL
Deterministic research                 PASS/FAIL
Human review gate                      PASS/FAIL
No production writes                   PASS/FAIL
No broker calls                        PASS/FAIL
Tests                                  PASS/FAIL
No optimization                       PASS/FAIL
```

All critical items must PASS.

---

# 33. STOP AFTER PHASE I

After implementation/tests:

STOP.

Do NOT:

- generate hundreds of strategies
- run autonomous AI loops
- optimize
- paper trade automatically
- live trade
- modify current strategies
- change risk rules
- modify historical truth

Review Phase I first.

---

# FINAL RESPONSE

Return exactly:

```text
PHASE I — AI STRATEGY RESEARCH LAYER

Proposal Schema:
PASS/FAIL

Validator:
PASS/FAIL

Model Independence:
PASS/FAIL

Arbitrary-Code Rejection:
PASS/FAIL

Lookahead Protection:
PASS/FAIL

Risk Gate:
PASS/FAIL

Data Gate:
PASS/FAIL

Expiry Gate:
PASS/FAIL

Execution Compatibility:
PASS/FAIL

Backtest Gate:
PASS/FAIL

Evaluation:
PASS/FAIL

Baseline Comparison:
PASS/FAIL

Proposal Registry:
PASS/FAIL

Provenance / Hashing:
PASS/FAIL

Duplicate Detection:
PASS/FAIL

Deterministic Research:
PASS/FAIL

Human Review Gate:
PASS/FAIL

Production Data Untouched:
YES/NO

Broker Calls:
YES/NO

Optimization:
NO

Autonomous Strategy Generation:
NO

Tests:
PASS/FAIL

Most Important Finding:
<description>

Remaining Limitations:
<description>

Next Safe Phase:
REVIEW / CONTROLLED AI RESEARCH / PAPER VALIDATION / HOLD
```

## FINAL RULE

The AI is a **research scientist, not the trader**.

```text
AI PROPOSES
    ↓
PLATFORM VALIDATES
    ↓
BACKTEST MEASURES
    ↓
EVIDENCE DECIDES
    ↓
HUMAN APPROVES
```

No model gets a shortcut around research truth.
