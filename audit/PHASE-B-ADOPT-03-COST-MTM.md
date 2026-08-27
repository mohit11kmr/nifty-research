# PHASE B — ADOPT-03 Paper Cost Model + Mark-to-Market

**Status:** IMPLEMENTED · VERIFIED
**Date:** 2026-08-13
**Spec:** `OPENCODE_PHASE_B_ADOPT_03_COST_MTM.md`
**Baseline frozen at:** git `cf132ca` (`phase6-baseline-2026-08-13-3678c7f0`)

## 1. Scope

Deterministic paper cost model (commission + adverse slippage), MTM of open
positions against trusted `research.db` quotes, realized vs unrealized P&L,
cost-aware account/equity reporting, Ground Truth parity, and tests.

**Explicitly NOT implemented** (per spec): auto-exit/stops/targets/expiry
automation, strategy/threshold changes, ML/experiments, live broker
enablement, new database, message bus, external trading frameworks, backtest
refactor.

## 2. Simulation assumptions (labeled, never broker-fabricated)

Re-used from the existing backtester so paper P&L stays comparable to
backtest P&L (`backtester.py`):

| Parameter | Value | Source |
|---|---|---|
| commission per trade | ₹40.00 | `COST_PER_TRADE = 40.0` |
| adverse slippage | 1.5% | `SLIPPAGE_PCT = 0.015` |
| MTM freshness budget | 120 s | `truth.LIVE_SPOT_FRESHNESS_S` (2× the 60s tick sample) |

These are **PROJECT-LEVEL SIMULATION ASSUMPTIONS, not actual broker charges.**
No broker-specific fees are invented anywhere.

## 3. What changed

### New files
- `cost_model.py` — pure deterministic `CostModel`: `commission_for_fill`
  (₹40/order allocated across fills by quantity, sum exactly = ₹40),
  `slippage_price` (BUY ×1.015 / SELL ×0.985; `None` when no valid reference,
  so nothing is ever fabricated), `slippage_amount`, `slippage_pct_used`,
  `total_cost`.
- `paper_mtm.py` — `ResearchDBQuoteSource` (read-only `mode=ro` against
  `data/research.db` `ticks`, lookup via existing `idx_ticks_key` on
  `(symbol, strike, side, recv_ts)`, latest row wins) returning an explicit
  envelope: `REAL` / `STALE` (used + flagged) / `MISSING` / `INVALID`
  (future ts / unparseable ts / no ltp-and-no-bid-ask). Price = `ltp` if >0
  else mid(bid,ask); never fabricated. `FakeQuoteSource` for isolated tests.
- `tests/test_adopt03_cost_mtm.py` — 29 tests (see §5).

### paper_execution.py
- `fill_order(order_id, quantity, price=None, reference_price=None,
  apply_slippage=True, ts=None, commission=None, execution_mode=...)`:
  - `requested_price` = order's resting price (always recorded).
  - `reference_price` defaults to requested; slippage baseline.
  - `price=None` → adverse fill from reference via cost model;
    explicit `price` → taken as-is (slippage 0).
  - commission: explicit override wins, else ₹40 allocated across fills.
  - fill record now carries `fill_price` (+ `price` back-compat alias),
    `reference_price`, `requested_price`, `slippage_amount`, `slippage_pct`,
    `commission`, `fees`, `transaction_cost`, `total_cost`.
- `_apply_fill_cash` books cash at `fill_price` and accumulates
  `total_fees` / `total_slippage` on the account.
- `close_position`: exit order is slipped against the requested exit price;
  realized P&L booked is **NET** (`gross − round-trip fees`); returns
  `requested_exit_price` / `exit_price` / `slippage_amount` / `fees` /
  `realized_gross` / `realized_net`.
- `_mirror_close_to_gt`: ledger receives `fees = round-trip commissions`
  (entry + exit order totals) and `slippage = 0.0` — slippage is already
  embedded in the recorded fill prices, so the GT outcome nets exactly like
  the paper account.
- `derived_positions`: adds `entry_fees` / `entry_slippage` (cost basis).
- `mark_to_market_report(quote_source=None, now=None)` — read-only. Per open
  FSM position: contract quote → `REAL`/`STALE` marked at quote, else
  `NO_QUOTE` fallback to entry price (flagged, never guessed). BUY/SELL
  signed valuation; `unrealized_pnl` vs net cost basis (entry value + entry
  fees); `equity = cash + Σ sign·mark·qty`; tallies `stale_count`,
  `no_quote_count`. Never creates a GT outcome, never mutates account.
- `summary()`: adds `realized_pnl_net`, `total_fees`, `total_slippage`.

### paper_trader.py
- `execute_paper_order`: slips the fill (`price=None,
  reference_price=entry_price`); returned position records the slipped
  `entry_price`, `requested_price`, `slippage_amount`, `commission`.
- `get_paper_account_summary`: cost-aware — reads engine's fresh account for
  `total_fees` / `total_slippage`, and adds `unrealized_pnl`,
  `equity_marked`, `mtm_position_count` from the MTM report.
- Legacy close path **unchanged** (gross, no fabricated costs); legacy
  positions remain display-only, never converted/upgraded, never valued.

## 4. Accounting invariants (all test-asserted)

1. Slippage lives **inside** the recorded fill price (like a real broker).
2. `realized_pnl` (net) = gross − (entry fees + exit fees); slippage already
   in gross.
3. GT outcome `net_pnl == paper realized_pnl`, with GT `fees` = round-trip
   commissions and GT `slippage = 0.0`. Verified for slipped and explicit
   entries.
4. `equity = cash_balance + Σ sign·mark_price·quantity` (BUY +1 / SELL −1).
5. MTM is read-only: no account mutation, no GT execution/outcome created,
   open positions stay OPEN.

## 5. Verification evidence

| Check | Result |
|---|---|
| `tests/test_adopt03_cost_mtm.py` (new) | **29/29 OK** |
| `tests/test_paper_execution.py` (Phase A) | **34/34 OK** |
| `unittest discover -s tests` (full suite) | **235/235 OK** (baseline 206 + 29) |
| `test_all.py` | **34 OK** |
| `git diff --check` | clean |
| `pip check` | clean |

Cost model determinism: repeated `slippage_price` calls return identical
values; partial-fill commission allocation sums exactly to ₹40.00.

## 6. Production isolation (verified)

Read-only assertions after implementation against the real data:

- ledger: `executions 0, positions 0, outcomes 0` (unchanged);
  `signals 190, decisions 190` unchanged.
- reconciliation: `MATCH`, `legacy_positions 10`, `errors 0`.
- paper account: `cash 3381.25`, `realized_pnl 0.0`, `total_fees 0.0`,
  `total_slippage 0.0`; MTM report `position_count 0`, `equity 3381.25`.

`auto_paper_runner.py` and `agent_workflow_graph.py` (live paper entry paths)
were audited: both call `execute_paper_order`/`get_paper_account_summary` with
supported keyword args and read keys that remain present — compatible.

## 7. Out-of-scope confirmations

No auto-exit/stop/target/expiry automation was added (MTM only reports; the
engine has no scheduler). No strategy/backtest/ML/live-broker changes. No new
database, message bus, or external framework.
