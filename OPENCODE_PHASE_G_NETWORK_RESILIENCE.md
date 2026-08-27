# OpenCode — Phase G: Network Disconnect / Recovery Resilience Test

## Objective

Verify safe behavior during temporary network/data-source failure and automatic recovery.

This is a resilience test only.

DO NOT change strategy, thresholds, regime logic, confidence, confluence, capital guard, stop/target rules, expiry rules, ML, self-improvement, or live trading. Do not create real trades or fabricate data. Use isolated fixtures and simulated feed failures.

---

## 1. Read Current Implementation

Read:

```text
audit/MASTER-PROJECT-BLUEPRINT.md
audit/PHASE-C-ADOPT-04-AUTO-EXIT.md
audit/PHASE-F3-EXPIRY-CONSISTENCY-BACKTEST.md
audit/TRADING_DECISION_FLOW.md
audit/PHASE-D-FIRST-GENUINE-PAPER-OUTCOME.md
```

Inspect:

```text
quant_daemon.py
auto_paper_runner.py
live_market_fetch.py
data_fetcher.py
paper_mtm.py
exit_evaluator.py
paper_execution.py
paper_trader.py
truth.py
ground_truth.py
mcp_nifty.py
timing.py
```

Identify network/data dependencies for:

- NIFTY spot
- OPTIONS/OI
- VIX
- FII/DII
- broker/API
- research DB updates
- other external feeds

---

## 2. Baseline

Before testing, record:

```text
current time
daemon status
PID
last successful cycle
signal count
decision count
execution count
position count
outcome count
paper cash
open positions
reconciliation
chain health
```

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

## 3. Failure Scenarios

Test independently.

### A — NIFTY feed failure

Simulate NIFTY source unavailable.

Expected:

```text
REAL/FRESH
→ STALE or MISSING
```

No new directional trade from stale NIFTY data.

### B — OPTIONS/OI failure

Expected:

```text
OPTIONS = STALE / MISSING
```

No silent use of stale OI and no invented OI.

### C — VIX failure

Expected:

```text
VIX = STALE / MISSING
```

No fabricated VIX.

### D — All external feeds unavailable

Simulate:

```text
NIFTY unavailable
OPTIONS unavailable
VIX unavailable
FII/DII unavailable
```

Expected:

```text
NO new trade
```

System must fail closed.

---

## 4. Open-Position Failure Scenario

Use an isolated temporary paper-trading fixture.

With a test-only open position, simulate network/feed failure.

Verify:

```text
MTM = STALE / MISSING
```

Also verify:

- no fabricated quote
- no fabricated P&L
- no automatic close solely because quote disappeared
- Ground Truth unchanged
- position remains open unless an independent existing rule requires closure

---

## 5. Stop / Target During Network Failure

With the isolated fixture and current quote unavailable:

Verify:

```text
STOP_LOSS is NOT falsely triggered
TAKE_PROFIT is NOT falsely triggered
```

unless another trusted source independently supplies a valid trigger.

No fabricated exit price.

---

## 6. Expiry During Network Failure

Use an isolated fixture near square-off.

If no valid exit price exists:

```text
NO_EXIT_PRICE_SQUARE_OFF_PENDING
```

or the project's existing equivalent.

Do not fabricate a square-off price.
Do not auto-roll.

---

## 7. Recovery

After each simulated outage:

```text
network/data source available
↓
fresh data arrives
↓
REAL/FRESH
↓
normal evaluation resumes
```

Recovery must not require manual DB repair.

---

## 8. Missed-Cycle Recovery

Simulate failed cycles, then recovery.

Verify:

- failed cycles visible
- recovery cycle succeeds
- no duplicate signal
- no duplicate decision
- no duplicate execution
- no fabricated catch-up trade
- no retroactive trade at an earlier timestamp

Recovery at time T evaluates current state at T.

---

## 9. Duplicate Prevention

On recovery verify no:

```text
duplicate signal
duplicate execution
duplicate position
duplicate outcome
duplicate Ground Truth chain
```

Repeated recovery checks must remain idempotent.

---

## 10. Freshness Recovery

For each feed measure:

```text
last_good_timestamp
failure_timestamp
recovery_timestamp
first_fresh_timestamp
```

Report:

```text
stale_duration
recovery_time
status transition
```

Expected pattern:

```text
REAL/FRESH
→ STALE
→ MISSING
→ REAL/FRESH
```

as applicable.

---

## 11. Fallbacks

Inspect current fallback behavior.

Classify each fallback:

```text
REAL
CACHED_REAL
ESTIMATED
SIMULATED
UNSUPPORTED
```

A fallback must never be mislabeled REAL.

Flag any fallback that could create a trade using stale data.

Do not silently change the strategy.

---

## 12. Daemon Resilience

Test `quant_daemon.py` for:

- feed failure
- temporary timeout
- repeated timeout
- feed restoration
- exception recovery

Verify the daemon does not silently die unless fail-stop is intentional.

If it stops, the reason and restart behavior must be visible/documented.

---

## 13. Timeout / Retry Behavior

Determine current:

```text
network timeout
retry count
retry delay
backoff
```

Do not add aggressive retries solely for this phase.

Report missing resilience controls as gaps.

---

## 14. Paper Account Safety

During failure/recovery verify:

```text
cash
realized P&L
fees
slippage
positions
```

remain consistent.

No accidental position creation.

---

## 15. Ground Truth Safety

During failure/recovery:

- no fabricated observation marked REAL
- no duplicate signal
- no duplicate execution
- no duplicate outcome
- provenance remains honest
- append-only protections remain intact

Verify:

```text
MATCH
```

---

## 16. Production Data Safety

Use temporary fixtures for failure injection.

Do not corrupt:

```text
data/ground_truth.db
paper_account.json
data/research.db
```

unless legitimate daemon observation naturally writes production observations.

Verify hashes/mtimes as appropriate.

---

## 17. Test Matrix

Create:

```text
tests/test_phase_g_network_resilience.py
```

Cover:

```text
NIFTY feed failure
OPTIONS/OI failure
VIX failure
all-feed failure
open-position feed loss
stop during feed loss
target during feed loss
expiry during feed loss
recovery
missed-cycle recovery
duplicate prevention
freshness recovery
daemon exception recovery
production-data isolation
```

Use mocks/fixtures. Do not require a real internet outage for automated tests.

---

## 18. Manual / Staging Check

If safe and supported, provide a non-destructive procedure for:

```text
disable source
observe stale state
restore source
observe fresh state
```

Do not disconnect the user's actual internet or disable the production network stack.

---

## 19. Documentation

Create:

```text
audit/PHASE-G-NETWORK-RESILIENCE.md
```

Include:

- Current Network/Data Dependencies
- Failure Scenarios
- Expected Behavior
- Actual Behavior
- Recovery Behavior
- Timeout/Retry Behavior
- Position Safety
- Ground Truth Safety
- Data Freshness
- Duplicate Protection
- Daemon Resilience
- Known Gaps

---

## 20. Acceptance Criteria

```text
NIFTY Feed Failure             PASS/FAIL
OPTIONS/OI Failure             PASS/FAIL
VIX Failure                    PASS/FAIL
All-Feed Failure               PASS/FAIL
Fail-Closed Behavior           PASS/FAIL
Open Position Safety           PASS/FAIL
Stop-Loss Safety               PASS/FAIL
Take-Profit Safety             PASS/FAIL
Expiry Safety                  PASS/FAIL
Recovery                       PASS/FAIL
Missed Cycle Handling          PASS/FAIL
Duplicate Prevention           PASS/FAIL
Freshness Recovery             PASS/FAIL
Daemon Resilience              PASS/FAIL
Ground Truth Integrity         PASS/FAIL
Reconciliation                 PASS/FAIL
Production Isolation           PASS/FAIL
Tests                           PASS/FAIL
Strategy Unchanged             PASS/FAIL
No Fabricated Data             PASS/FAIL
```

All critical items must PASS.

---

## 21. Do Not Start Strategy Work

After Phase G, STOP.

Do not:

- change strategy
- tune thresholds
- optimize
- start experiments
- add ML
- add self-learning
- enable live trading

Goal:

**FAIL SAFELY → RECOVER CORRECTLY → CONTINUE HONESTLY**

---

# FINAL RESPONSE

Return exactly:

```text
PHASE G — NETWORK RESILIENCE

NIFTY Feed Failure:
PASS/FAIL

OPTIONS/OI Failure:
PASS/FAIL

VIX Failure:
PASS/FAIL

All-Feed Failure:
PASS/FAIL

Fail-Closed:
PASS/FAIL

Open Position Safety:
PASS/FAIL

Stop Safety:
PASS/FAIL

Target Safety:
PASS/FAIL

Expiry Safety:
PASS/FAIL

Recovery:
PASS/FAIL

Missed Cycle Handling:
PASS/FAIL

Duplicate Prevention:
PASS/FAIL

Freshness Recovery:
PASS/FAIL

Daemon Resilience:
PASS/FAIL

Ground Truth:
PASS/FAIL

Reconciliation:
PASS/FAIL

Production Data Untouched:
YES/NO

Strategy Changed:
YES/NO

Fabricated Data:
YES/NO

Tests:
PASS/FAIL

Main Resilience Gap:
<description>

Most Important Finding:
<description>

Next Safe Phase:
REVIEW / OBSERVE MORE / CONTROLLED EXPERIMENT / HOLD
```

## FINAL RULE

The project must never turn a temporary internet failure into:

- a fake quote
- a fake trade
- a fake outcome
- a stale-data entry
- a duplicate execution
- a false REAL provenance record

Target behavior:

```text
NETWORK ON
    ↓
NORMAL

NETWORK OFF
    ↓
STALE/MISSING
    ↓
NO FALSE TRADE

NETWORK ON
    ↓
FRESH DATA
    ↓
NORMAL RESUME
```
