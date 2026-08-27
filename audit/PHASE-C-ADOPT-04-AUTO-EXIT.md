# PHASE C — ADOPT-04 Paper Auto-Exit / Stop / Target / Expiry Square-Off

**Status:** IMPLEMENTED · VERIFIED
**Date:** 2026-08-13
**Spec:** `OPENCODE_PHASE_C_ADOPT_04_AUTO_EXIT.md`
**Baseline frozen at:** git `cf132ca` (`phase6-baseline-2026-08-13-3678c7f0`)
**Previous phase:** ADOPT-03 (cost model + MTM), independently verified.

## 1. Scope

Manage the exit of **existing** paper positions per the already-defined
project rules: stop-loss, take-profit, expiry-day square-off, deterministic
evaluation/scheduling, Ground Truth outcome integration, legacy-position
safety, read-only exit/health reporting, and tests.

No strategy / entry / signal / threshold / regime / capital-guard / ML /
live-broker / backtest changes. No auto-re-entry, no auto-roll. ADOPT-05 not
started.

## 2. Exit rules verified from source (authoritative, not invented)

| Rule | Source evidence | Value |
|---|---|---|
| Stop-loss (long option) | `auto_paper_runner.py:84`, `agent_workflow_graph.py:107` | `sl = max(2.0, entry − 1.5·ATR)` where `ATR = max(10.0, entry·0.25)`; stored as `sl_price` |
| Trigger convention | `paper_execution._derive_exit_reason` | exit mark `<= sl × 1.001` → STOP_LOSS |
| Take-profit (1:2) | `auto_paper_runner.py:86`, `agent_workflow_graph.py:108` | `target = entry + 2·(entry − sl)`; stored as `target_price` |
| Trigger convention | `paper_execution._derive_exit_reason` | exit mark `>= target × 0.999` → TAKE_PROFIT |
| 0.8% index stop | `precision_signals.py:243` | index-level entry constraint (`spot × 0.008`), not a paper-position exit; paper exit uses the option-premium SL |
| Expiry day = Thursday | `mcp_nifty.NIFTY_EXPIRY_WEEKDAY = 3` | weekly expiry detection |
| Square-off | `regime_filter.py:33` `EXPIRY_SQUARE_OFF_HOUR = 15.0`, comment "square off by 15:05" | by **15:05 IST** on the expiry date |
| Timezone | `paper_execution._ist_ts()` uses local time; `regime_filter`/`mcp_nifty` use IST | IST (naive local) |
| Max-hold | **none exists** | N/A — no rule invented |
| SELL exits | **project never creates SELL paper entries** (both entry paths hardcode `side="BUY"`) | unsupported; evaluator returns `SELL_EXITS_UNSUPPORTED` rather than inventing inverted behavior |

## 3. Architecture

- `exit_evaluator.py` (new) — `ExitEvaluator`: **decision layer only**. Pure,
  read-only, deterministic. Returns one decision dict per open position:
  `NONE` / `STOP_LOSS` / `TAKE_PROFIT` / `EXPIRY_SQUARE_OFF` plus quote
  status, expiry, distances, exit reference price, and a `skip_reason`
  when evaluation could not be performed.
- `paper_execution.py` — remains the **sole execution layer**:
  - `run_exit_checks(quote_source=None, now=None)`: evaluates every open FSM
    position; for triggered decisions calls the existing `close_position`
    (order → fill → ADOPT-03 cost/slippage → cash/P&L → GT close → canonical
    outcome). Returns `decisions` + `closed` + `skipped` + `errors`.
  - `paper_exit_status(quote_source=None, now=None)`: **read-only** health
    snapshot (never closes) with position/stop/target/expiry/distances/
    potential exit reason/quote status.
- `paper_trader.py` — `run_exit_checks()` / `paper_exit_status()` passthrough
  on `PaperTrader` (`paper_engine` singleton used by the daemon/runner).
- `auto_paper_runner.py` — smallest internal trigger, per spec §9: exit
  checks run at the top of the existing 30s daemon loop (`quant_daemon` →
  `auto_paper_runner`), **before** the signal gate, so exits still happen on
  STAY_OUT days; failures never abort the loop (try/except + printed).

## 4. Determinism & precedence

Precedence (documented + tested): **EXPIRY_SQUARE_OFF > STOP_LOSS >
TAKE_PROFIT**.

- A single quote price cannot be `<= stop` AND `>= target` for a long
  position (stop < entry < target), so same-interval stop/target ambiguity
  is impossible by construction; expiry vs stop/target is resolved by the
  fixed precedence above. No look-ahead anywhere.
- Evaluation uses the ADOPT-03 quote envelope; the position's actual
  contract expiry (`research.db` ticks, e.g. `18-Aug-2026`) is authoritative
  when known; otherwise the Thursday NIFTY convention is used for
  `is_expiry_day`.

## 5. Quote freshness rules (ADOPT-03 infrastructure)

| Quote | Price-based exits (stop/target) | Expiry square-off (time-based, mandatory) |
|---|---|---|
| REAL (fresh) | may trigger | may trigger |
| STALE | skipped → `STALE_QUOTE_NO_TRIGGER` (no silent trigger) | may trigger on last known price (documented emergency rule: expiry square-off must happen) |
| MISSING / INVALID | skipped → `MISSING_QUOTE` / `INVALID_QUOTE` | skipped → `NO_EXIT_PRICE_SQUARE_OFF_PENDING` (never fabricate an exit price) |

An expired position (contract expiry in the past — missed square-off,
weekend/holiday) is squared off immediately on the next evaluation, still
price-safe.

## 6. Outcome integration & idempotency

- A final canonical outcome is created **only** after a real full close via
  the GT ledger `close_position` (append-only; already-closed positions
  raise). Exactly one execution pair + one outcome per position.
- Idempotency: `derived_positions()` exposes only remaining>0 positions;
  `close_position` refuses already-closed positions; `run_exit_checks`
  guards one close per position per run. Repeated scheduler calls produce
  one close → one outcome (tested).

## 7. Partial closes — N/A (documented limitation)

The existing architecture supports **full closes only**: `close_position`
always fills the full remaining quantity (order `closed_quantity` becomes
`quantity`) and the GT ledger closes a position once. Per spec §15 this
limitation is documented, not invented around. Test asserts a second close
raises.

## 8. Legacy positions

Legacy `open_positions` are never evaluated, never upgraded, never mirrored
to GT, and never produce an outcome. `run_exit_checks` evaluates only
FSM-derived positions; `paper_exit_status` reports only FSM positions. No
historical entry/stop/target/outcome is fabricated (tested: 0 GT rows after
run with a legacy fixture).

## 9. Verification evidence

| Check | Result |
|---|---|
| `tests/test_adopt04_auto_exit.py` (new) | **33/33 OK** |
| `tests/test_adopt03_cost_mtm.py` | **29/29 OK** |
| `tests/test_paper_execution.py` | **34/34 OK** |
| `unittest discover -s tests` (full) | **268/268 OK** (baseline 235 + 33) |
| `test_all.py` | **34 OK** |
| `tests/test_fix_verification.py` | exit 0 |
| `tests/test_chain_health` + `test_ground_truth` + `test_evaluation_engine` | **60/60 OK** |
| `git diff --check` | clean |
| `pip check` | clean |
| `pip-audit` (uvx) | no known vulnerabilities |

Test coverage per spec §19: stop exact/above/below + direction; target
exact/below/above; expiry before/at/after/non-expiry/expired/Thursday
convention; priority (expiry+stop, expiry+target); freshness
(fresh/stale/missing/invalid + stale-on-expiry + missing-on-expiry); FSM
execution (slippage/fees/cash/P&L); GT (execution mirrored, position closed,
exactly one outcome, reason preserved STOP_LOSS/TAKE_PROFIT/EXPIRY_SQUARE_OFF);
partial-close limitation; legacy safety; idempotency; read-only status;
runner integration; production isolation.

## 10. Production data safety (verified)

SHA-256 fingerprints of `data/paper_account.json` and `data/ground_truth.db`
captured before/after the read-only production checks — **unchanged**.
Production run results: `paper_exit_status open_count 0`, `run_exit_checks
closed []`, ledger `executions 0 / positions 0 / outcomes 0`,
reconciliation `MATCH`, account cash `3381.25` / realized `0.0`.

## 11. Reconciliation

Paper account ↔ FSM ↔ GT execution ↔ GT position ↔ GT outcome: **0
mismatches** (asserted `MATCH` in execution/idempotency tests after auto
closes).

## 12. Limitations

- Partial closes unsupported (full-close architecture; documented, tested).
- SELL-position exits unsupported (project creates none; no rule exists).
- Square-off requires a last-known price to close; with no quote at all the
  close is deferred and recorded (`NO_EXIT_PRICE_SQUARE_OFF_PENDING`).
- Exit scheduling is driven by the existing daemon loop (`quant_daemon` /
  `auto_paper_runner`, 30s cadence) plus direct `run_exit_checks()` calls;
  no separate scheduler/message bus was added.
- `regime_filter.EXPIRY_SQUARE_OFF_HOUR = 15.0` comment says "by 15:05"; the
  evaluator triggers at 15:05 (the documented by-time), consistent with the
  constant's intent.

## 13. Strategy preservation

`RANGE_LV → NO_TRADE`, 6-layer confluence, confidence thresholds, capital
guard, position sizing, entry rules, and signal generation are **unchanged**
(git diff on those modules: none by this phase). This phase governs only
positions that already exist.
