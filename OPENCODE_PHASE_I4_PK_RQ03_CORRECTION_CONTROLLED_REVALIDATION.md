# OpenCode — Phase I.4: PK-RQ-03 Correction + Controlled Revalidation

Use this with **Big Pickle or DeepSeek**.

## Objective

Phase I.3 produced:

```text
PK-RQ-03 — GAP_BOUNCE
43 trades
Net ≈ +₹23,591
Development ≈ +₹101,458
OOS ≈ −₹77,867
```

Independent Claude Sonnet audit classified it:

```text
D — PROMISING BUT INSUFFICIENT
```

Important audit findings:

```text
F1 — stop_pct=0.5 declared but not simulated
F2 — LOT=75 applied to all dates; 2024 historical lot may be 50
F3 — entry uses bhavcopy settle/WAP, not a true executable fill
F4 — global k-means regimes are retrospective/non-PIT
F5 — ~₹1,000 aggregate accounting discrepancy
F6 — 2024 expiry-calendar limitation may exist
F7 — forward-5d boundary issue
```

Your job is to **correct the documented implementation/semantic defects and re-run the SAME frozen PK-RQ-03 hypothesis**.

This is NOT optimization and NOT new strategy research.

---

# 1. HARD RULES

DO NOT:

- change gap threshold
- change VIX threshold
- change DTE
- change 5-session horizon
- change option moneyness
- optimize stop-loss
- optimize slippage
- optimize fees
- change development/OOS boundary
- use OOS to tune anything
- generate new strategies
- paper trade
- live trade
- call broker APIs
- modify Ground Truth
- modify paper_account.json
- modify frozen historical data
- fabricate bid/ask/fills
- silently remove losing trades

A correction is allowed ONLY when it fixes a documented bug or semantic mismatch.

---

# 2. READ FIRST

Read:

```text
audit/CLAUDE_SONNET_4_6_PHASE_I3_PK_RQ03_AUDIT.md
audit/PHASE-I3-REGIME-AWARE-RESEARCH-DISCOVERY.md
audit/PHASE-I2-GENERIC-STRATEGY-EXECUTION.md
audit/PHASE-H3-RANGE-HV-RISK-CONTRACT-INTEGRITY.md
audit/PHASE-F3-EXPIRY-CONSISTENCY-BACKTEST.md
audit/DATA-ALIGNMENT-01-UNIFIED-CALENDAR.md
results/phase_i3/ai_proposals/PK-RQ-03.yaml
```

Preserve all Phase I.3 artifacts unchanged.

---

# 3. BASELINE FREEZE

Before modifying code capture:

```text
git status
HEAD
dataset hash
PK-RQ-03 spec hash
original result hash
original trade count
original metrics
```

Write baseline evidence under:

```text
results/phase_i4/baseline/
```

Never overwrite Phase I.3 results.

---

# 4. F2 — HISTORICAL LOT SIZE

This is the first priority.

Inspect the project's authoritative historical NIFTY lot-size evidence.

Implement a date-aware function/service such as:

```python
get_lot_size(trade_date)
```

Requirements:

- historical
- deterministic
- provenance-backed
- point-in-time safe
- tested
- no current-lot fallback

Do NOT guess.

If authoritative historical lot-size evidence cannot be established:

```text
STOP
LOT_SIZE_DATA_UNVERIFIED
```

Do not silently use 75 for all dates.

Add tests around the historical change boundary and representative 2024/2025/2026 dates.

---

# 5. F1 — DECLARED STOP-LOSS

Claude found:

```text
stop_pct = 0.5
```

in the PK-RQ-03 spec, but all original trades exited by horizon.

Implement the **declared** stop-loss semantics using the project's canonical execution semantics.

Do not reinterpret it for better P&L.

Because the dataset is EOD, do not invent intraday paths.

If stop evaluation can only be supported at EOD resolution, document that explicitly.

Verify exit precedence against existing project conventions:

```text
entry
→ stop check
→ horizon check
→ expiry
```

Add tests for:

- trigger
- no trigger
- exact boundary
- expiry before horizon
- missing option observation
- contract unavailable
- no lookahead
- idempotent exit

---

# 6. F3 — ENTRY PRICE / EXECUTION REALISM

Claude found that the original entry uses bhavcopy settle/WAP.

Do NOT replace it with a guessed bid/ask.

First determine what historical executable data actually exists.

Classify the corrected execution model as:

```text
HISTORICAL_SETTLEMENT
EOD_CLOSE
EOD_VWAP
BID
ASK
MID
OTHER
```

If realistic historical bid/ask does not exist:

```text
DO NOT FABRICATE IT
```

It is acceptable to retain the research price while explicitly documenting:

```text
EXECUTION_REALISM_LIMITED
```

Only change the entry price if the project has an authoritative historical executable price source.

Also document that the gap is observed at the open but the option entry occurs at EOD.

---

# 7. F4 — REGIME LABELS

Do NOT add a regime filter to PK-RQ-03.

Keep retrospective global k-means labels for descriptive analysis only.

If desired, build a separate PIT rolling/expanding regime service for future research, but do NOT use it to improve this candidate.

---

# 8. F5 — AGGREGATE ACCOUNTING

Make trade-level ledger authoritative.

Enforce:

```text
sum(trade.net_pnl) == aggregate.net_pnl
```

and:

```text
aggregate.net_pnl
= aggregate.gross
- aggregate.fees
- aggregate.slippage
```

Fix the reporting/accounting discrepancy without changing trade economics.

---

# 9. F6 — EXPIRY

Determine whether the 2024 expiry-calendar limitation actually changes PK-RQ-03 trades.

If it changes trades:

```text
correct canonical expiry
→ rerun
```

If it does not:

```text
NO_PK_RQ03_IMPACT
```

Do not expand unrelated infrastructure.

---

# 10. F7 — FORWARD-5D BOUNDARY

Ensure forward targets require all five future trading sessions.

If the future window is incomplete:

```text
EXCLUDE_FROM_TARGET
```

Never fabricate missing future observations.

---

# 11. PRESERVE THE EXACT HYPOTHESIS

These must remain unchanged:

```text
gap < -0.5%
vix_close < 25
dte > 1
long ATM CE
EOD entry
5-session horizon
expiry cap
dev <= 2026-02-28
OOS >= 2026-03-01
```

Any change requires a new strategy/spec ID and is OUT OF SCOPE.

---

# 12. CONTROLLED REPLAY

Run the corrected candidate on the SAME frozen dataset.

Write only to:

```text
results/phase_i4/
```

Do not overwrite:

```text
results/phase_i3/
```

---

# 13. BEFORE/AFTER COMPARISON

Produce:

| Metric | I.3 Original | I.4 Corrected | Delta |
|---|---:|---:|---:|
| Trades | | | |
| Net P&L | | | |
| Gross P&L | | | |
| Fees | | | |
| Slippage | | | |
| PF | | | |
| Win rate | | | |
| Max DD | | | |
| Best trade | | | |
| Top-3 concentration | | | |
| Development P&L | | | |
| OOS P&L | | | |
| Stop exits | | | |
| Horizon exits | | | |
| Expiry exits | | | |

Also create a trade-by-trade diff with a reason for every changed trade:

```text
LOT_SIZE_CORRECTION
STOP_LOSS_CORRECTION
EXPIRY_CORRECTION
REPORTING_ONLY
OTHER_VALIDATED_SEMANTIC_FIX
```

No unexplained changes.

---

# 14. OOS IS THE PRIMARY GATE

Keep:

```text
OOS cutoff = 2026-03-01
```

Do not change it after seeing the corrected result.

Report separately:

```text
development
OOS
```

Include:

```text
trades
net
PF
win rate
drawdown
concentration
```

---

# 15. REGIME-B DESCRIPTIVE ANALYSIS

Using the existing retrospective regime labels ONLY for explanation, calculate for down-gap sessions:

```text
sample
mean fwd5d
median
win rate
```

for:

```text
REGIME_A
REGIME_B
REGIME_C
```

Do not add a regime rule to PK-RQ-03.

Question:

> Does REGIME_B behave more like continuation than reversal?

Do not assume the answer.

---

# 16. PROFIT CONCENTRATION

Recalculate:

```text
best trade %
top 2 %
top 3 %
best month %
net without top 1
net without top 3
```

This is diagnostic only.

---

# 17. COST / SLIPPAGE

Keep the canonical existing cost model.

Do not optimize it.

Verify:

```text
net = gross - fees - slippage
```

at trade and aggregate levels.

---

# 18. RISK

Verify after correction:

```text
capital at risk
risk per trade
max theoretical loss
worst realized loss
max drawdown
```

Do not change strategy risk settings.

---

# 19. REPRODUCIBILITY

Run the corrected replay twice.

Require:

```text
same trades
same metrics
same normalized result
same result hash
```

Ignore only explicitly documented run IDs/timestamps.

---

# 20. PRODUCTION ISOLATION

Never write:

```text
data/ground_truth.db
paper_account.json
production signals
broker state
```

Research outputs only:

```text
results/phase_i4/
audit/
tests/
temporary fixtures
```

---

# 21. TESTS

Create/update:

```text
tests/test_phase_i4_pk_rq03_corrections.py
```

Cover:

- historical lot size
- lot-size boundary
- stop-loss semantics
- stop no-lookahead
- EOD execution semantics
- aggregate accounting invariant
- expiry impact
- forward target boundary
- unchanged PK-RQ-03 hypothesis
- deterministic replay
- production isolation

Run the normal project suite plus:

```bash
python -m unittest discover -s tests -v
pip check
git diff --check
```

---

# 22. AUDIT REPORT

Create:

```text
audit/PHASE-I4-PK-RQ03-CORRECTION-CONTROLLED-REVALIDATION.md
```

Include:

## Objective
## Claude Audit Findings
## Baseline Freeze
## F2 Historical Lot Size
## F1 Stop-Loss
## F3 Entry Semantics
## F4 Regime Labels
## F5 Accounting
## F6 Expiry
## F7 Forward Target Boundary
## Hypothesis Preservation
## Before vs After
## Trade-by-Trade Changes
## Development
## OOS
## Regime Analysis
## Concentration
## Costs
## Risk
## Reproducibility
## Production Isolation
## Tests
## Limitations
## Final Verdict

---

# 23. PROMOTION RULE

Do NOT call PK-RQ-03 a paper candidate merely because corrected P&L is positive.

Use:

```text
CONTROLLED_PAPER_CANDIDATE
```

only if:

```text
all known critical implementation defects fixed
no lookahead
correct historical lot sizes
stop semantics actually implemented
execution limitations explicitly documented
OOS is not contradicted by development
OOS evidence is adequate
risk semantics valid
concentration acceptable
reproducibility PASS
production isolation PASS
```

Otherwise:

```text
HOLD
```

---

# 24. IMPORTANT

The corrected result may become:

```text
better
worse
negative
approximately unchanged
```

All outcomes are valid.

Do not evaluate this phase by whether P&L improves.

The purpose is:

> Make the research truthful.

If corrected research becomes negative, that is a successful outcome.

---

# 25. STOP

After corrected replay, tests, comparison, and audit:

STOP.

Do NOT:

- optimize
- change thresholds
- test alternative horizons
- add regime filters
- change moneyness
- add trailing stops
- paper trade
- live trade
- generate new AI strategies

Wait for independent review.

---

# 26. FINAL RESPONSE

Return:

```text
PHASE I.4 — PK-RQ-03 CORRECTION + CONTROLLED REVALIDATION

Original:
43 trades
+₹23,591.49
OOS −₹77,867
Classification D

F2 Historical Lot:
PASS / FAIL / UNVERIFIED

F1 Stop-Loss:
IMPLEMENTED / NOT IMPLEMENTED

F3 Entry Semantics:
REALISTIC / LIMITED / INVALID

F4 Regime:
DESCRIPTIVE ONLY / PIT / PROBLEM

F5 Accounting:
PASS / FAIL

F6 Expiry:
NO IMPACT / CORRECTED / UNVERIFIED

F7 Forward Boundary:
PASS / FAIL

Hypothesis Changed:
NO / YES

Corrected Trades:
X

Changed Trades:
X

Net P&L:
₹X

PF:
X

Win Rate:
X

Max DD:
₹X

Development:
<metrics>

OOS:
<metrics>

Stop Exits:
X

Horizon Exits:
X

Expiry Exits:
X

Top-1 Concentration:
X%

Top-3 Concentration:
X%

OOS Verdict:
PASS / INSUFFICIENT / NEGATIVE

Reproducibility:
PASS / FAIL

Production Data Untouched:
YES / NO

Optimization:
NO

Paper Trading:
NO

Final Classification:
INVALID / STATISTICAL_OBSERVATION_ONLY / PROMISING_BUT_INSUFFICIENT / CONTROLLED_PAPER_CANDIDATE / HOLD

Most Important Finding:
<description>

Next Safe Phase:
REVIEW
```

## FINAL PRINCIPLE

**Do not fix the backtest so the strategy wins.**

Fix it so:

> **the reported result is as close to the truth as the available historical data permits.**

If the truthful corrected result is negative, that is a successful research outcome.
