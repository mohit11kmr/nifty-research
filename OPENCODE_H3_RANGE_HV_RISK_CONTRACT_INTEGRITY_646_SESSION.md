# OpenCode — H3: RANGE-HV Risk / Contract Semantics Integrity + 646-Session Frozen Validation

## Objective

DATA-ALIGNMENT-01 is complete.

The project now has one aligned historical research calendar:

```text
2024-01-01 → 2026-08-13
646 genuine trading sessions
```

Unified data currently reports:

```text
NIFTY              FULL
OPTIONS EOD        FULL
VIX                 FULL
PARTICIPANT OI      FULL
EXPIRY              PARTIAL
```

The two previously missed genuine sessions are now present:

```text
2025-02-01
2026-08-11
```

Cross-dataset alignment, underlying validation, no-fabrication, reproducibility, idempotency, and production isolation all passed.

The existing RANGE-HV Iron Condor candidate from Phase H2 remains:

```text
6 trades
Win rate 66.7%
Net +₹6,248.25
PF 9.693
Max DD ≈ -₹587
```

But H2 found a serious promotion blocker:

```text
RISK_MODEL_MISMATCH
```

The specification declares:

```text
1% risk
```

while measured one-lot exposure was approximately:

```text
₹7.8k–₹8.5k
≈ 8% of current capital
```

H2 also identified a contract/accounting issue where some trades had:

```text
credit > wing width
```

causing a naive maximum-loss calculation to become negative.

Therefore the purpose of H3 is:

> Determine whether the Range-HV candidate is internally correct and economically interpretable before using the newly aligned 646-session dataset to evaluate it.

This is a **risk / contract semantics / measurement integrity phase**.

It is NOT an optimization phase.

---

# CRITICAL RULES

DO NOT:

- change Range-HV entry logic
- change RANGE_HV regime definition
- change VIX gates
- change strike-selection rules
- change spread width
- change delta
- change expiry selection
- change stop-loss
- change target
- change position sizing
- tune parameters
- run parameter sweeps
- optimize max risk
- optimize credit
- optimize wing width
- add filters
- remove filters
- change the current control strategy
- promote Range-HV
- start live trading
- automatically start paper trading
- add AI strategy generation
- fabricate missing data
- alter Ground Truth
- modify paper_account.json

The goal is:

```text
CORRECT SEMANTICS
+
CORRECT ACCOUNTING
+
CORRECT RISK MEASUREMENT
+
THEN FAIR RESEARCH
```

---

# 1. READ AUTHORITATIVE DOCUMENTS

Read:

```text
audit/DATA-ALIGNMENT-01-UNIFIED-CALENDAR.md
audit/PHASE-H2-RANGE-HV-VALIDATION.md
audit/PHASE-H1-V2-STRATEGY-LAB.md
audit/PHASE-H-MULTI-STRATEGY-BACKTEST.md
audit/PHASE-F3-EXPIRY-CONSISTENCY-BACKTEST.md
audit/PHASE-G-NETWORK-RESILIENCE.md
```

Inspect:

```text
strategies/range_hv_iron_condor_v1.yaml
strategy_schema.py
strategy_validator.py
strategy_compiler.py
strategy_registry.py
backtest_adapter.py
premium_seller.py
multi_strategy_backtest.py
backtest_frozen.py
paper_execution.py
exit_evaluator.py
capital_guard.py
evaluation_engine.py
data/historical/manifests/unified_research_dataset.json
```

Current source code and the frozen specification are authoritative.

---

# 2. FREEZE INPUT DATA

Use ONLY the frozen unified dataset referenced by:

```text
data/historical/manifests/unified_research_dataset.json
```

Record:

```text
calendar hash
dataset manifest hash
options hash
VIX hash
participant OI hash
NIFTY hash
expiry hash
strategy spec hash
git commit
```

Do NOT silently discover newer files.

If the manifest points to a missing file:

```text
STOP
DATASET_INTEGRITY_FAILURE
```

---

# 3. RECONSTRUCT ORIGINAL H2 RESULT

Before any measurement change:

Re-run the existing Range-HV candidate exactly as H2 did.

Expected reference:

```text
6 trades
net +₹6,248.25
PF 9.693
max DD approximately -₹587
```

Require:

```text
spec-consistency = 0 violations
```

If the H2 reference cannot be reproduced:

```text
STOP
BASELINE_REPRODUCTION_FAILURE
```

Do not "fix" the baseline by changing the strategy.

---

# 4. IDENTIFY THE RISK MODEL MISMATCH

Trace:

```text
strategy spec
→ strike selection
→ premiums
→ spread width
→ credit received
→ lot size
→ maximum loss
→ capital usage
→ risk percentage
```

Determine exactly why:

```text
spec = 1% risk
```

while actual one-lot exposure was approximately:

```text
8% of capital
```

Report the exact source of mismatch.

Do not change the 1% value or position size during diagnosis.

---

# 5. DISTINGUISH RISK CONCEPTS

Explicitly separate:

```text
margin required
cash deployed
premium received
defined maximum loss
net capital at risk
mark-to-market exposure
```

Determine which quantity the current implementation calls:

```text
risk
```

and whether that definition is mathematically appropriate.

If terminology is misleading:

```text
SEMANTIC_MISMATCH
```

Do not silently change behavior.

---

# 6. IRON CONDOR MAX-LOSS SEMANTICS

Inspect the current condor calculation.

Verify the mathematical relationship between:

```text
wing width
credit received
maximum loss
```

Investigate the H2 condition:

```text
credit > wing width
```

Possible causes:

```text
valid economic structure
incorrect input units
incorrect premium scaling
incorrect wing-width calculation
incorrect max-loss formula
data/quote mismatch
simulation artifact
```

Do NOT select a cause because it improves P&L.

---

# 7. CONTRACT-LEVEL AUDIT

For every historical Range-HV trade reconstruct:

```text
trade date
expiry
short put strike
long put strike
short call strike
long call strike
put wing width
call wing width
short-put premium
long-put premium
short-call premium
long-call premium
gross credit
net credit
lot size
fees
slippage
```

Verify:

```text
short/long relationships
same expiry
correct CE/PE
correct strike ordering
positive wing widths
credit arithmetic
```

---

# 8. PREMIUM / PRICE UNITS

Determine:

```text
per-unit premium
per-lot premium
total premium
credit per spread
```

Verify all multiplication/division involving:

```text
lot size
number of legs
quantity
```

Create explicit unit tests.

---

# 9. MAX-LOSS TEST MATRIX

Create deterministic cases for:

```text
credit < wing width
credit == wing width
credit > wing width
unequal call/put wings
different lot sizes
fees
slippage
```

Verify the calculation never produces an economically impossible negative maximum loss unless the project explicitly defines that value.

If the current engine permits a negative artifact, report the exact path.

Do not silently patch production strategy during diagnosis.

---

# 10. RISK-PERCENT SEMANTICS

Determine what:

```text
max_risk_pct = 1%
```

actually means.

Possible meanings:

```text
maximum theoretical loss / capital
cash allocated / capital
margin / capital
premium at risk / capital
notional / capital
```

Report the actual implementation meaning.

Do not redefine it merely to make the strategy pass.

---

# 11. CAPITAL BASELINE

Determine:

```text
starting capital
capital at each trade
risk denominator
position quantity
capital utilization
```

Do not inject live daemon state into frozen research.

---

# 12. COST / SLIPPAGE

Verify:

```text
commission
slippage
number of legs
entry costs
exit costs
net credit
net P&L
```

Keep the canonical cost/slippage model unchanged.

---

# 13. EXIT SEMANTICS

Do not change:

```text
STOP_LOSS
TAKE_PROFIT
EXPIRY_SQUARE_OFF
```

Verify each is applied to the correct spread/position value.

Report any impossible negative loss/profit artifacts.

---

# 14. 646-SESSION REPLAY

After semantics are understood, run the exact frozen Range-HV strategy across:

```text
2024-01-01 → 2026-08-13
646 trading sessions
```

Use the unified dataset.

No filters or thresholds may be changed.

---

# 15. EXPIRY LIMITATION

Unified market data is complete for 646 sessions, but the current explicit expiry observation calendar only covers:

```text
2025-08-13 → 2026-08-13
```

For pre-2025-08-13 Range-HV trades:

- determine whether actual historical expiry can be reconstructed from authoritative data
- if not, mark `EXPIRY_DATA_LIMITATION`
- do not guess

Classify each session:

```text
FULLY_RESEARCHABLE
PARTIALLY_RESEARCHABLE
EXPIRY_LIMITED
DATA_INSUFFICIENT
```

Do not silently exclude earlier sessions.

---

# 16. RANGE-HV ACTIVITY ANALYSIS

Across the valid research window calculate:

```text
RANGE_HV observed days
VIX-pass days
candidate days
trades
locked/no-trade days
close/no-trade days
```

Explain why each eligible day did/did not trade.

Do not change the strategy to increase trade count.

---

# 17. H2 VS H3

Compare:

```text
H2 245-session baseline
vs
H3 corrected 646-session measurement
```

Report:

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
risk per trade
capital utilization
```

Do not choose a winner based only on P&L.

---

# 18. RISK-NORMALIZED REPORT

For every trade report:

```text
theoretical max loss
capital at risk
risk %
actual net P&L
return on risk
```

Descriptive only. No optimization.

---

# 19. PROFIT CONCENTRATION

Calculate:

```text
% total P&L from best trade
% total P&L from top 2
% total P&L from top 3
```

Also report monthly/yearly/regime contribution.

---

# 20. OUT-OF-SAMPLE

Use a chronological split.

Do not tune against OOS.

Report:

```text
development
out-of-sample
```

If too few OOS trades:

```text
OOS_INSUFFICIENT
```

---

# 21. REPRODUCIBILITY

Run H3 measurement twice.

Require:

```text
same trades
same contract selections
same risk calculations
same metrics
same classification
```

Record result hashes.

---

# 22. PRODUCTION ISOLATION

Use:

```text
frozen research dataset
temporary fixtures
read-only production state
```

Do not write:

```text
data/ground_truth.db
paper_account.json
production signals
production outcomes
```

Verify isolation.

---

# 23. BUG REPORTING

If a genuine calculation bug is discovered, report:

```text
BUG_FOUND
file
function
line
input
calculation
observed result
expected behavior
```

H3 is first a diagnosis/integrity phase.

If a minimal measurement-only fix is necessary to make risk semantics mathematically valid, isolate it clearly and produce before/after evidence.

Do not change entry logic.

---

# 24. TESTS

Create:

```text
tests/test_h3_range_hv_risk_semantics.py
```

Test:

- credit/wing-width arithmetic
- positive wing width
- premium unit conversion
- lot size
- multi-leg fees
- slippage
- maximum-loss calculation
- risk-percent calculation
- capital denominator
- negative-loss detection
- contract ordering
- same-expiry validation
- no-lookahead
- 646-session calendar use
- pre-2025 expiry limitation
- deterministic output
- production isolation

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

# 25. AUDIT REPORT

Create:

```text
audit/PHASE-H3-RANGE-HV-RISK-CONTRACT-INTEGRITY.md
```

Include:

## Objective
## Frozen Inputs
## H2 Baseline
## Risk Definition
## Risk Denominator
## Capital Basis
## Iron Condor Contract Semantics
## Credit / Wing Width
## Premium Unit Analysis
## Maximum Loss Analysis
## Cost / Slippage
## Contract-Level Audit
## 646-Session Replay
## Expiry Limitation
## H2 vs H3
## Risk Normalization
## OOS
## Profit Concentration
## Reproducibility
## Production Isolation
## Bugs Found
## Fixes (if any)
## Remaining Limitations
## Verdict

---

# 26. VERDICT RULE

Use only:

```text
HOLD — RISK SEMANTICS INVALID
HOLD — EXPIRY DATA INSUFFICIENT
HOLD — SAMPLE INSUFFICIENT
REJECT — ECONOMICS WEAK
CONTINUE RESEARCH
```

Do not use:

```text
PROVEN
PROFITABLE
READY_FOR_LIVE
```

unless genuinely supported and separately approved.

---

# 27. NO PROMOTION

H3 must NOT automatically promote Range-HV to:

```text
PAPER
LIVE
PRODUCTION
```

Promotion is a separate decision after review.

---

# FINAL RESPONSE

Return exactly:

```text
PHASE H3 — RANGE-HV RISK / CONTRACT INTEGRITY

Strategy:
range_hv_iron_condor_v1

Spec Hash:
<hash>

Unified Dataset:
<manifest path>

Dataset Hash:
<hash>

H2 Baseline:
<summary>

H2 Risk Definition:
<description>

Actual Risk Definition:
<description>

Risk Mismatch:
YES/NO

Capital Base:
<value/description>

Measured Risk Per Trade:
<summary>

Wing Width Validation:
PASS/FAIL

Credit Validation:
PASS/FAIL

Premium Unit Validation:
PASS/FAIL

Max Loss Calculation:
PASS/FAIL

Negative Max-Loss Artifact:
FOUND/NOT_FOUND

Contract Ordering:
PASS/FAIL

Expiry Consistency:
PASS/FAIL/LIMITED

Cost Accounting:
PASS/FAIL

Slippage:
PASS/FAIL

646-Session Replay:
PASS/FAIL/LIMITED

Valid Research Sessions:
X

Expiry-Limited Sessions:
X

Trades:
X

Win Rate:
<value>

Net P&L:
<value>

PF:
<value>

Max Drawdown:
<value>

Risk-Normalized Results:
<summary>

OOS:
<summary>

Profit Concentration:
<summary>

Reproducibility:
PASS/FAIL

Production Data Untouched:
YES/NO

Bug Found:
YES/NO

Measurement Fix:
YES/NO

Strategy Entry Logic Changed:
NO

Optimization:
NO

AI Generation:
NO

VERDICT:
<allowed verdict>

Most Important Finding:
<description>

Biggest Remaining Limitation:
<description>

Next Safe Phase:
REVIEW / CORRECTION PHASE / FURTHER DATA / PAPER RESEARCH / HOLD
```

## FINAL RULE

H3 must answer:

> **Is the current Range-HV result mathematically, economically, and contractually trustworthy enough to research further?**

If not, that is a successful research result.

Do not hide a risk-model bug.
Do not hide an expiry limitation.
Do not optimize around the problem.

**Correct measurement truth first. Strategy decisions come afterward.**

Do not automatically commit or push changes after H3.

Do not start H4 without reviewing the H3 report.

