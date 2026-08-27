# Phase F3 — Expiry Consistency Backtest

**Date:** 2026-08-14
**Window:** 2025-08-13 .. 2026-08-13 (245 trading days)
**Strategy:** Frozen (precision_signals 6-layer confluence + auto_paper_runner
execution model). **No optimization, no strategy change, no threshold change.**
**Measurement only** — reads `data/*` caches, writes only to `--out`.

## 1. What F3 changed (integration)

One canonical expiry source, `expiry_calendar.py`, is now the single owner of
the NIFTY weekly expiry for **all** consumers:

| Module | Integration |
|---|---|
| `exit_evaluator.py` | `canonical_expiry`, `expiry_status`, contract-expiry-authoritative rule, wrong-weekday trap; `SQUARE_OFF_HHMM`/`LAST_ENTRY_HHMM` re-read from `expiry_calendar` |
| `timing.py` | expiry-day flag via `expiry_calendar.is_expiry_day` (Thursday no longer hardcoded) |
| `mcp_nifty.py` | `expiry_status` tool from canonical calendar |
| paper auto-exit path (`auto_paper_runner.py` → `paper_trader.py` → `paper_execution.run_exit_checks` → `exit_evaluator`) | same canonical service |
| `backtest_frozen.py` | `exp_cal.get_expiry_for_trade_date(d)` for contract expiry AND square-off date; module-identity with the paper path |

Shared-source proof (test): `bf.exp_cal is exit_evaluator.expiry_calendar is expiry_calendar`.

## 2. Verification results

| Item | Evidence |
|---|---|
| Thursday → Tuesday transition | `is_expiry_day(2025-08-28)` True, next `2025-09-02`; `is_expiry_day(2025-09-02)` True, next `2025-09-09`. Actual calendar: 2025-08-14, 08-21, 08-28 last Thursday weeklies; Tue from 09-02. Trade expiries confirm: 3 Thursday expiries (early window), then 42 Tuesday + 3 Monday (holiday shifts). No Thursday expiry after 2025-09-02. |
| Holiday shifts | Diwali Mon 2025-10-20, Mon 2026-03-02 / 03-30 / 04-13 are expiry days; trades square off on 2025-10-28 / 2026-03-30 / 2026-04-13 Monday expiries. |
| Correct contract matching | (expiry, strike, side) validated in the day-t chain; 48/48 contracts AVAILABLE, 0 CONTRACT_UNAVAILABLE; marks only from exact contract LTP else BS(sigma=0.15) at true TTM. |
| No 0DTE | `get_expiry_for_trade_date(d) > d` always; min DTE across 48 trades = 1; entry day never equals expiry day. |
| No auto-roll | expiry close creates no new position/order (paper path, tested). |
| No lookahead | calendar `expiry` strictly after trade date for all 246 observed rows; all replay layers slice `<= t`. |
| Paper/backtest expiry identity | per-trade-date equality: backtest expiry == canonical == `exit_evaluator.canonical_expiry` for 6 sampled dates across the window. |
| Idempotent expiry exit | repeated `run_exit_checks` yields a single close; executions ledger = entry+exit only. |
| Production isolation | `ground_truth.db` / `paper_account.json` untouched by replay and by validation tests (byte-hash unchanged). |

## 3. F3 frozen backtest — determinism (run TWICE)

- Run 1: `/tmp/opencode/phaseF3/results_20260814_085703.json`
- Run 2: `/tmp/opencode/phaseF3/results_20260814_085835.json`
- **Byte-identical** except the single embedded `run_id` timestamp:
  `diff <(run1 with run_id masked) <(run2 with run_id masked)` → **0 differences**.
- JSON bodies equal under normalization (`run_id`/`git_head` stripped): **True**.

## 4. F2 vs F3 comparison

Same frozen strategy, same actual-expiry data. F3 only unified the source of
truth — results are **trade-for-trade identical** (48/48 trades identical, all
entry/SL/TP/strike/exit/net fields equal).

| Metric | F2 | F3 |
|---|---|---|
| Trades | 48 | 48 |
| CALL | 0 | 0 |
| PUT | 48 | 48 |
| Win rate | 33.3% (16W / 32L) | 33.3% (16W / 32L) |
| Net P&L | ₹1,906.43 | ₹1,906.43 |
| Profit factor | 1.01 | 1.01 |
| Max drawdown | ₹−51,746.80 | ₹−51,746.80 |
| Average hold | 2.35 days | 2.35 days |
| STOP_LOSS | 18 | 18 |
| TAKE_PROFIT | 12 | 12 |
| EXPIRY_SQUARE_OFF | 18 | 18 |
| CONTRACT_UNAVAILABLE | 0 | 0 |

Notes:
- CALL/PUT are all-PUT because the **frozen** side-selection check
  (`"BUY_CALL"/"BULLISH" in action`) never matches the frozen action strings
  (`MODERATE_*` / `HIGH_CONVICTION_*`). This is pre-existing frozen behavior,
  **identical in F2 and F3**, and is deliberately NOT changed (frozen replay +
  no-strategy-change mandate).
- The only F2↔F3 artifact delta is 6 daily rows (`2026-05-19`, `2026-05-20`,
  `2026-05-21`, `2026-05-22`, `2026-05-25`, `2026-08-13`) differing solely in
  FII-layer fields (`fii_5d`, `fii_net`, `fii_sentiment`, `l5_status`,
  `confluence_*`). Cause: `data/fii_dii_history.csv` was refreshed at
  2026-08-14 08:53 (after the F2 run, before F3) — **input-data drift, not an
  expiry change**. No expiry key differs anywhere; no trade affected.

## 5. Trade table (F3)

48 trades, all PUT, entry at OI-wall/support strike, SL = entry − 1.5·ATR,
TP = entry + 2·(entry−SL), exit on actual weekly expiry.

| entry | expiry | ewd | strike | entry | exit | reason | net ₹ |
|---|---|---|---|---|---|---|---|
| 2025-08-13 | 2025-08-14 | Thu | 24600 | 40.40 | 2025-08-14 | EXPIRY_SQUARE_OFF | −3,103.74 |
| 2025-08-14 | 2025-08-21 | Thu | 24600 | 113.50 | 2025-08-18 | STOP_LOSS | −7,235.30 |
| 2025-08-21 | 2025-08-28 | Thu | 25050 | 87.85 | 2025-08-22 | TAKE_PROFIT | 8,295.53 |
| 2025-10-21 | 2025-10-28 | Tue | 25500 | 26.70 | 2025-10-27 | STOP_LOSS | −1,721.00 |
| 2025-10-23 | 2025-10-28 | Tue | 25500 | 14.40 | 2025-10-28 | EXPIRY_SQUARE_OFF | −1,165.12 |
| 2025-10-24 | 2025-10-28 | Tue | 25700 | 49.85 | 2025-10-27 | STOP_LOSS | −3,209.96 |
| 2025-10-27 | 2025-10-28 | Tue | 25900 | 32.70 | 2025-10-28 | EXPIRY_SQUARE_OFF | −2,314.42 |
| 2025-10-28 | 2025-11-04 | Tue | 25900 | 120.70 | 2025-10-29 | STOP_LOSS | −4,643.71 |
| 2025-10-29 | 2025-11-04 | Tue | 26000 | 91.55 | 2025-10-31 | TAKE_PROFIT | 9,993.72 |
| 2025-10-30 | 2025-11-04 | Tue | 25500 | 14.10 | 2025-11-04 | EXPIRY_SQUARE_OFF | −1,138.59 |
| 2025-10-31 | 2025-11-04 | Tue | 25700 | 54.05 | 2025-11-04 | EXPIRY_SQUARE_OFF | 3,093.21 |
| 2025-11-03 | 2025-11-04 | Tue | 25700 | 38.80 | 2025-11-04 | EXPIRY_SQUARE_OFF | 4,254.12 |
| 2026-01-22 | 2026-01-27 | Tue | 25000 | 27.10 | 2026-01-23 | TAKE_PROFIT | 3,397.64 |
| 2026-01-23 | 2026-01-27 | Tue | 25000 | 75.00 | 2026-01-27 | EXPIRY_SQUARE_OFF | −5,737.66 |
| 2026-01-27 | 2026-02-03 | Tue | 25150 | 192.85 | 2026-01-29 | STOP_LOSS | −8,688.18 |
| 2026-01-28 | 2026-02-03 | Tue | 25000 | 84.75 | 2026-02-03 | EXPIRY_SQUARE_OFF | −6,516.82 |
| 2026-01-29 | 2026-02-03 | Tue | 25000 | 53.95 | 2026-02-03 | EXPIRY_SQUARE_OFF | −4,172.17 |
| 2026-01-30 | 2026-02-03 | Tue | 25000 | 76.70 | 2026-02-03 | EXPIRY_SQUARE_OFF | −5,904.01 |
| 2026-03-04 | 2026-03-10 | Tue | 24000 | 167.30 | 2026-03-05 | STOP_LOSS | −9,236.47 |
| 2026-03-05 | 2026-03-10 | Tue | 24000 | 48.45 | 2026-03-06 | TAKE_PROFIT | 2,969.14 |
| 2026-03-06 | 2026-03-10 | Tue | 24000 | 91.20 | 2026-03-09 | TAKE_PROFIT | 5,499.21 |
| 2026-03-09 | 2026-03-10 | Tue | 23500 | 50.75 | 2026-03-10 | EXPIRY_SQUARE_OFF | −3,935.96 |
| 2026-03-10 | 2026-03-17 | Tue | 24250 | 234.90 | 2026-03-11 | TAKE_PROFIT | 18,377.35 |
| 2026-03-11 | 2026-03-17 | Tue | 23000 | 69.00 | 2026-03-13 | TAKE_PROFIT | 8,131.09 |
| 2026-03-12 | 2026-03-17 | Tue | 23000 | 69.70 | 2026-03-13 | TAKE_PROFIT | 8,077.81 |
| 2026-03-13 | 2026-03-17 | Tue | 22000 | 21.60 | 2026-03-16 | STOP_LOSS | −1,358.62 |
| 2026-03-16 | 2026-03-17 | Tue | 23000 | 46.95 | 2026-03-17 | EXPIRY_SQUARE_OFF | −3,642.99 |
| 2026-03-17 | 2026-03-24 | Tue | 23550 | 237.20 | 2026-03-18 | STOP_LOSS | −7,964.26 |
| 2026-03-18 | 2026-03-24 | Tue | 23000 | 49.85 | 2026-03-19 | TAKE_PROFIT | 14,896.81 |
| 2026-03-19 | 2026-03-24 | Tue | 23000 | 254.10 | 2026-03-23 | TAKE_PROFIT | 19,752.55 |
| 2026-03-24 | 2026-03-30 | Mon | 22900 | 311.80 | 2026-03-25 | STOP_LOSS | −13,366.16 |
| 2026-03-25 | 2026-03-30 | Mon | 22000 | 30.90 | 2026-03-30 | EXPIRY_SQUARE_OFF | −2,417.49 |
| 2026-04-07 | 2026-04-13 | Mon | 23100 | 329.30 | 2026-04-08 | STOP_LOSS | −22,961.26 |
| 2026-04-16 | 2026-04-21 | Tue | 23500 | 23.85 | 2026-04-20 | STOP_LOSS | −1,570.53 |
| 2026-04-20 | 2026-04-21 | Tue | 24000 | 36.30 | 2026-04-21 | EXPIRY_SQUARE_OFF | −2,835.95 |
| 2026-04-21 | 2026-04-28 | Tue | 24550 | 223.55 | 2026-04-23 | TAKE_PROFIT | 15,289.06 |
| 2026-04-29 | 2026-05-05 | Tue | 24000 | 111.10 | 2026-05-04 | STOP_LOSS | −4,980.41 |
| 2026-06-19 | 2026-06-23 | Tue | 24000 | 85.95 | 2026-06-22 | STOP_LOSS | −4,783.46 |
| 2026-06-22 | 2026-06-23 | Tue | 24100 | 55.50 | 2026-06-23 | EXPIRY_SQUARE_OFF | 14,536.88 |
| 2026-06-23 | 2026-06-30 | Tue | 23800 | 138.60 | 2026-06-24 | STOP_LOSS | −6,538.25 |
| 2026-06-24 | 2026-06-30 | Tue | 24000 | 118.15 | 2026-06-25 | STOP_LOSS | −4,120.85 |
| 2026-06-25 | 2026-06-30 | Tue | 24000 | 67.05 | 2026-06-30 | EXPIRY_SQUARE_OFF | 5,224.81 |
| 2026-06-29 | 2026-06-30 | Tue | 23800 | 24.25 | 2026-06-30 | EXPIRY_SQUARE_OFF | −1,785.67 |
| 2026-06-30 | 2026-07-07 | Tue | 23850 | 120.10 | 2026-07-02 | STOP_LOSS | −7,608.44 |
| 2026-07-01 | 2026-07-07 | Tue | 24000 | 131.70 | 2026-07-02 | STOP_LOSS | −6,744.35 |
| 2026-07-02 | 2026-07-07 | Tue | 24100 | 73.65 | 2026-07-03 | STOP_LOSS | −3,389.09 |
| 2026-07-06 | 2026-07-07 | Tue | 24400 | 50.65 | 2026-07-07 | EXPIRY_SQUARE_OFF | −3,695.64 |
| 2026-07-07 | 2026-07-14 | Tue | 24350 | 114.00 | 2026-07-08 | TAKE_PROFIT | 28,604.03 |

## 6. Test status

- F3 suite `tests/test_phase_f3_expiry_consistency.py`: **25/25 OK**.
- Full regression `unittest discover tests -p "test_*.py"`: **322/322 OK**.
- F2 suite (`test_phase_f2_expiry.py`) and adopt suites included in the 322.

## 7. Constraints honored

No optimization, no strategy change, no threshold change, no live trading, no
controlled experiments. Replay and validation are measurement-only and
production-isolated.
