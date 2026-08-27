# OpenCode — Phase H: Multi-Strategy Research & Fair Comparison

## Objective

The current NIFTY-RESEARCH strategy has a trustworthy measurement baseline, but its historical edge remains unproven.

Current control baseline:

- 48 trades
- 33.3% win rate
- PF ≈ 1.01
- Net P&L ≈ ₹1,906
- Edge = UNPROVEN

Goal:

> Compare a small number of clearly defined strategy candidates fairly, using the same historical data, expiry model, cost model, slippage model, no-lookahead rules, and evaluation framework.

This is a research/measurement phase only.

## CRITICAL RULE

DO NOT:

- change the current production strategy
- change its thresholds
- optimize parameters
- run parameter sweeps
- tune stops/targets/deltas
- retrain ML for performance improvement
- enable live trading
- create real-money trades
- fabricate missing data
- cherry-pick periods
- use future information
- give different costs/slippage assumptions to different strategies
- alter Ground Truth history
- promote a winner to production

---

# 1. READ AUTHORITATIVE DOCUMENTS

Read:

```text
audit/MASTER-PROJECT-BLUEPRINT.md
audit/PHASE-E-FROZEN-STRATEGY-BACKTEST.md
audit/PHASE-F2-HISTORICAL-EXPIRY-CORRECTION.md
audit/PHASE-F3-EXPIRY-CONSISTENCY-BACKTEST.md
audit/PHASE-G-NETWORK-RESILIENCE.md
audit/TRADING_DECISION_FLOW.md
audit/EXTERNAL-ARCHITECTURE-BENCHMARK.md
audit/EXTERNAL-ADOPTION-ROADMAP.md
```

Inspect current strategy/execution components:

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
```

Current source is authoritative.

---

# 2. STRATEGY A — CURRENT CONTROL

Treat the existing strategy as the frozen control.

Do not modify it.

Record:

```text
strategy_id
git_commit
configuration fingerprint
dataset hash
expiry-calendar hash
cost-model version
slippage version
```

---

# 3. CANDIDATE STRATEGIES

Start with only these:

## A — Current Strategy / Control

```text
REGIME GATE
→ 6-LAYER CONFLUENCE
→ CAPITAL GUARD
→ DIRECTIONAL OPTION
→ CURRENT SL/TP/EXPIRY
```

## B — Defined-Risk Directional Spread

Concept:

```text
Eligible trend regime
↓
Bullish → Bull Call Spread
Bearish → Bear Put Spread
```

Requirements:

- defined risk
- exact expiry
- deterministic strike construction
- same underlying
- same historical dataset
- same cost/slippage model

Do not optimize width/delta/expiry.

If exact deterministic rules are not already supported, document and freeze one justified rule rather than tuning.

## C — Defined-Risk RANGE_HV Strategy

Inspect existing `premium_seller.py` / iron-condor logic.

Use one already-defined deterministic structure if possible.

Do not invent parameters just to get a backtest result.

If impossible without new discretionary rules:

```text
CANDIDATE_C_NOT_SPECIFIABLE_WITHOUT_NEW_RULES
```

## D — No-Trade Control

```text
RANGE_LV → NO TRADE
```

This is a control condition, not a trading strategy.

---

# 4. FREEZE STRATEGY SPECIFICATIONS

Before coding candidates, create:

```text
audit/PHASE-H-STRATEGY-SPECIFICATIONS.md
```

For each candidate document:

```text
strategy_name
market_regimes
entry_condition
direction_logic
instrument
expiry_rule
strike_rule
position_size
stop_rule
target_rule
exit_rule
cost_model
slippage_model
data requirements
unsupported conditions
```

No hidden discretionary decisions.

---

# 5. FAIR DATASET

All candidates MUST use the same frozen historical dataset and corrected expiry calendar.

Use the best validated dataset from the F2/F3 pipeline.

Same:

- start/end dates
- sessions
- timestamps
- data availability rules
- no-lookahead rules

No candidate gets extra information.

---

# 6. NO-LOOKAHEAD

For every historical decision at time `t`, only data timestamped `<= t` is allowed.

Applies to:

- spot
- indicators
- OI
- PCR
- VIX
- FII/DII
- quotes
- expiry
- ML outputs
- option contracts

No future information.

---

# 7. SAME EXECUTION MODEL

Use the same:

```text
commission
slippage
fill assumptions
MTM
expiry handling
P&L definitions
outcome definitions
```

for all candidates wherever applicable.

Simulation assumptions must remain explicitly labeled as simulation assumptions.

---

# 8. SAME CAPITAL BASIS

Define and freeze:

```text
starting capital
maximum risk/trade
position sizing convention
cash treatment
margin treatment
```

If a strategy genuinely requires a different capital structure, document it explicitly rather than hiding the difference.

---

# 9. BACKTEST THE CONTROL

Run Candidate A exactly as the latest corrected F3 baseline.

Do not change it.

---

# 10. CANDIDATE B — SPREAD

Use a deterministic construction such as:

```text
Bullish:
BUY one call
SELL one higher-strike call

Bearish:
BUY one put
SELL one lower-strike put
```

The exact strike-selection rule must be frozen before results are seen.

Do not optimize delta, width, premium, expiry, target, or stop.

---

# 11. CANDIDATE C — RANGE STRATEGY

Inspect existing premium-selling/iron-condor code.

Use one deterministic existing construction if available.

Do not create parameters solely to produce a result.

If rules are insufficient, mark:

```text
NOT_SPECIFIABLE
```

---

# 12. PERFORMANCE METRICS

For every candidate report:

```text
trade_count
win_count
loss_count
breakeven_count
win_rate
gross_pnl
fees
slippage
net_pnl
profit_factor
expectancy
average_trade
median_trade
max_drawdown
average_win
average_loss
MFE
MAE
average_hold
trade_frequency
```

Use `INSUFFICIENT_SAMPLE` where appropriate.

Do not manufacture statistics.

---

# 13. RISK-ADJUSTED METRICS

Where sample size supports it:

```text
Sharpe
Sortino
Calmar
max drawdown %
```

Otherwise report:

```text
NOT_RELIABLE
```

---

# 14. REGIME COMPARISON

Compare by:

```text
TREND_HV
TREND_LV
RANGE_HV
RANGE_LV
```

Report:

```text
sample
trades
net P&L
PF
expectancy
drawdown
```

---

# 15. MONTHLY / OUT-OF-SAMPLE STABILITY

Report monthly results.

Separate the historical period into development and out-of-sample sections where the dataset supports a defensible split.

Do not optimize against the out-of-sample period.

---

# 16. PROFIT CONCENTRATION

Report:

```text
% profit from best month
% profit from best trade
% profit from top 5 trades
```

This identifies fragile results.

---

# 17. TRADE FREQUENCY

Report:

```text
trades/month
trades/year
average days between trades
```

---

# 18. MULTI-STRATEGY RUNNER

Create an isolated runner:

```text
multi_strategy_backtest.py
```

It must:

- load one frozen dataset
- load frozen strategy specifications
- run candidates independently
- produce comparable results
- never touch production Ground Truth
- never touch `paper_account.json`
- be deterministic

---

# 19. OUTPUT FILES

Create:

```text
audit/PHASE-H-STRATEGY-SPECIFICATIONS.md
audit/PHASE-H-MULTI-STRATEGY-BACKTEST.md
results/phaseH_multi_strategy.json
```

---

# 20. COMPARISON TABLE

Include:

| Metric | Current Strategy | Spread Strategy | Range Strategy | No-Trade Control |
|---|---:|---:|---:|---:|
| Trades | | | | |
| Win Rate | | | | |
| Net P&L | | | | |
| PF | | | | |
| Expectancy | | | | |
| Max DD | | | | |
| MFE | | | | |
| MAE | | | | |
| Trade Frequency | | | | |

Use:

```text
INSUFFICIENT_DATA
NOT_APPLICABLE
NOT_SPECIFIABLE
```

where appropriate.

---

# 21. STRATEGY ASSESSMENT

Do not rank only by net P&L.

Assess:

```text
edge quality
stability
drawdown
sample size
trade frequency
regime robustness
data requirements
execution realism
complexity
```

Classify:

```text
STRONG_CANDIDATE
PROMISING_BUT_INSUFFICIENT
BASELINE_ONLY
WEAK
NOT_TESTABLE
```

---

# 22. REQUIRED CONCLUSION

Answer:

- Which strategy produced the best historical result?
- Which had the best risk-adjusted profile?
- Which was most stable month-to-month?
- Which worked in which regime?
- Which had the smallest drawdown?
- Which required the least data?
- Which is easiest to paper trade safely?
- Which should not be pursued further?
- Did any candidate demonstrate a durable edge?

Do not call anything “best” if the sample is insufficient.

---

# 23. REPRODUCIBILITY

Run the comparison twice.

Require deterministic equality of:

```text
daily results
trade lists
metrics
```

except documented run timestamps.

Record:

```text
dataset hash
expiry-calendar hash
strategy-spec hash
result hash
```

---

# 24. PRODUCTION ISOLATION

Verify before/after:

```text
data/ground_truth.db
paper_account.json
production signals
production outcomes
```

remain unchanged.

---

# 25. TESTS

Create:

```text
tests/test_phase_h_multi_strategy.py
```

Test:

- frozen strategy specifications
- same dataset
- no-lookahead
- same costs/slippage
- candidate-specific execution
- missing-data behavior
- no production writes
- deterministic output
- no hidden optimization

Run:

```bash
python test_all.py
python -m unittest discover -s tests -v
python tests/test_fix_verification.py
pip check
pip-audit
git diff --check
```

---

# 26. CURRENT PAPER OBSERVATION

Keep Phase D live/paper observation separate.

Do not modify the live/paper control strategy while Phase H is running.

---

# 27. STOP AFTER PHASE H

After the comparison:

STOP.

Do not:

- select a winner for live trading
- change production strategy
- optimize the winner
- retrain ML
- self-improve
- enable live trading
- allocate capital

Output is **research evidence only**.

---

# ACCEPTANCE CRITERIA

```text
Current control preserved             PASS/FAIL
Specifications frozen                 PASS/FAIL
Same dataset                          PASS/FAIL
No-lookahead                          PASS/FAIL
Same cost model                       PASS/FAIL
Same slippage                         PASS/FAIL
Same expiry model                     PASS/FAIL
Candidate B                           PASS/FAIL/NOT_SPECIFIABLE
Candidate C                           PASS/FAIL/NOT_SPECIFIABLE
Candidate D                           PASS/FAIL
Monthly comparison                    PASS/FAIL
Regime comparison                     PASS/FAIL
Drawdown comparison                   PASS/FAIL
Concentration analysis                PASS/FAIL
Trade-frequency analysis              PASS/FAIL
Reproducibility                       PASS/FAIL
Production isolation                  PASS/FAIL
Tests                                 PASS/FAIL
No optimization                       PASS/FAIL
```

# FINAL RESPONSE

Return exactly:

```text
PHASE H — MULTI-STRATEGY RESEARCH

Dataset:
<name/hash>

Window:
<start → end>

CURRENT STRATEGY:
Trades: X
Win Rate: X
Net P&L: X
PF: X
Max DD: X

SPREAD STRATEGY:
Status: TESTED / NOT_SPECIFIABLE
Trades: X
Win Rate: X
Net P&L: X
PF: X
Max DD: X

RANGE STRATEGY:
Status: TESTED / NOT_SPECIFIABLE
Trades: X
Win Rate: X
Net P&L: X
PF: X
Max DD: X

NO-TRADE CONTROL:
<summary>

BEST HISTORICAL RESULT:
<strategy / INSUFFICIENT>

BEST RISK-ADJUSTED:
<strategy / INSUFFICIENT>

MOST STABLE:
<strategy / INSUFFICIENT>

BEST REGIME:
<strategy + regime>

LARGEST DRAWBACK:
<description>

MOST IMPORTANT FINDING:
<description>

DURABLE EDGE:
PROVEN / NOT_PROVEN / INSUFFICIENT_SAMPLE

PRODUCTION DATA TOUCHED:
YES/NO

STRATEGY CHANGED:
YES/NO

OPTIMIZATION:
NO

NEXT SAFE PHASE:
REVIEW / PAPER TEST / OBSERVE MORE / HOLD
```

## FINAL RULE

We are not looking for the strategy with the prettiest backtest.

We are looking for the strongest combination of:

```text
realism
stability
risk control
repeatability
sample size
regime robustness
```

Only after a candidate survives this research stage should it be considered for controlled paper experimentation.
