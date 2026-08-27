# Phase H — Strategy Specifications (FROZEN BEFORE RESULTS)

Author: OpenCode
Date: 2026-08-14
Status: FROZEN — these specifications were written and hashed BEFORE any
candidate result was generated or inspected. No parameter was tuned after
results were seen. Any later change to a candidate spec invalidates the
comparison and requires a re-freeze + re-run.

Spec hash (authoritative, in code): `f814e452da62b2087fa050be692ba2e5ae4d33a6cf812bcaec859a10a5524f20`
Computed as sha256 of the JSON-serialized `CANDIDATE_SPECS` dict in
`multi_strategy_backtest.py` (sort_keys=True).

---

## Shared comparison contract (applies to every candidate)

| Item | Frozen value |
|---|---|
| Dataset | `data/nifty_history.csv`, `data/india_vix.csv`, `data/fii_dii_history.csv`, `data/ml_features.csv`, `data/oi_snapshots/NIFTY_<date>.csv` (247 snapshots), `data/historical/expiry_calendar.csv`. Snapshot frozen at run time in `/tmp/opencode/phaseH_frozen_data`. |
| Dataset composite hash | `018c182ef833c620d3b36ac22faadf956caabb42bf5264445e4ab7dac2a9d163` |
| nifty_history.csv sha256 | `691bf02d08d0a2ec58acac88751e695c44232ddaf886020be25057721466f49d` |
| Window | 2025-08-13 → 2026-08-13 (245 trading days) |
| Expiry model | `expiry_calendar.py` canonical historical weekly (Thursday thru 2025-08-28, Tuesday from 2025-09-02, holiday Monday shifts). Same single-owner module used by live exit engine. |
| Cost model | `cost_model.py`: COST_PER_TRADE = ₹40.00 per order, charged per order leg actually filled. |
| Slippage model | SLIPPAGE_PCT = 1.5% adverse per fill (BUY ref×(1+slip), SELL ref×(1−slip)). |
| Capital basis | ₹100,000 starting capital, 1 lot (75 qty) per position for all trading candidates. Max risk/trade is not hard-capped at 1% (control precedent: 1 lot); documented rather than hidden. |
| No-lookahead | For every decision at date t, only data timestamped ≤ t (VIX slice, nifty/indicator slice, OI snapshot = latest dated ≤ t, FII/DII slice ≤ t, ML trained walk-forward on rows ≤ t, expiry = calendar entry for t). No future information. |
| Data availability | Missing contract leg → CONTRACT_UNAVAILABLE, no trade, no substitute, no fabricated price. Missing price → BS(sigma=0.15) fallback at the contract's true TTM (same as control). |
| Outcome/P&L definitions | Net P&L = realized fills × lot − fees − slippage embedded in fills; positive = win, negative = loss, zero = breakeven. |

---

## Candidate A — Current Strategy / Control

Frozen reference: `backtest_frozen.py` (authoritative F2/F3 engine). Executed in
`multi_strategy_backtest.py` by directly calling `backtest_frozen.evaluate_day`
and `backtest_frozen.simulate_trade` — byte-identical to the F3 baseline.

| Field | Frozen rule |
|---|---|
| strategy_name | Current frozen 6-layer confluence + naked directional option |
| market_regimes | All, subject to l1 gate (RANGE_LV / NO_TRADE excluded) |
| entry_condition | 6-layer confluence funnel: l1 regime gate passed, l2 approved, l3 technical bias ≠ NEUTRAL, l4 OI/skew, l5 institutional, l6 ML; grade A+ (≥5/6) or A (≥4/6) |
| direction_logic | Frozen side selection: `'BUY_CALL' in action or 'BULLISH' in action → CE else PE`. Documented frozen defect: every F2/F3 trade is PE (all-PUT). Deliberately NOT changed (no-strategy-change mandate). |
| instrument | Naked long CE or PE, 1 lot (75) |
| expiry_rule | `expiry_calendar.get_expiry_for_trade_date(d)` |
| strike_rule | Wall strike (nearest resistance for CE / support for PE) else spot×(1.01 / 0.99), rounded to nearest 50 |
| position_size | 1 lot (75) |
| stop_rule | ATR = max(10, 0.25×entry); SL = max(2, entry − 1.5×ATR); trigger mark ≤ SL×1.001 |
| target_rule | target = entry + 2×(entry − SL); trigger mark ≥ target×0.999 |
| exit_rule | STOP_LOSS / TAKE_PROFIT / EXPIRY_SQUARE_OFF on the contract's real expiry |
| cost_model | ₹40 × 2 orders = ₹80 / trade |
| slippage_model | 1.5% adverse × 2 fills |
| data_requirements | full dataset |
| unsupported_conditions | contract not listed → CONTRACT_UNAVAILABLE (0 of 48 in F3) |

---

## Candidate B — Defined-Risk Directional Spread

Concept: eligible trend regime → Bullish → Bull Call Spread / Bearish → Bear Put
Spread. Defined risk (max loss = width − net debit), same expiry, deterministic
strike construction, same underlying/dataset/cost/slippage.

| Field | Frozen rule |
|---|---|
| strategy_name | Directional vertical spread |
| market_regimes | TREND_HV, TREND_LV only (eligible trend regime). RANGE_* excluded. |
| entry_condition | SAME 6-layer funnel as control (identical candidate days), then regime restriction to trend |
| direction_logic | Layer-3 technical bias: CALL → bull call spread (long CE, short higher CE); PUT → bear put spread (long PE, short lower PE). Correct directional mapping frozen for B (B is not the frozen control, so it is not bound by A's side-selection defect). |
| instrument | 2-leg vertical spread, 1 lot (75) |
| expiry_rule | `expiry_calendar.get_expiry_for_trade_date(d)` |
| strike_rule | Long leg = wall strike else spot×(1.01 CE / 0.99 PE) rounded to 50 (same formula as control, recomputed with B's correct side). Short leg = the listed strike nearest to long ± SPREAD_WIDTH. SPREAD_WIDTH = 500.0 index points (single integer constant, justified: NIFTY weekly strikes are 50 apart near ATM → 10 strikes wide; round fixed width, not tuned). |
| position_size | 1 lot (75) |
| entry_price | Net debit = long LTP − short LTP (day-d chain; BS(sigma=0.15) fallback per leg). Skip if net debit ≤ 0 (invalid construction) or either leg unlisted. |
| stop_rule | SAME formula as control applied to net debit: ATR = max(10, 0.25×net_debit); SL = max(2, net_debit − 1.5×ATR); trigger on net mark |
| target_rule | target = net_debit + 2×(net_debit − SL); trigger on net mark |
| exit_rule | STOP_LOSS / TAKE_PROFIT / EXPIRY_SQUARE_OFF (net intrinsic at real expiry); max loss bounded by width − net debit |
| cost_model | ₹40 × 4 orders = ₹160 / trade (2-leg instrument legitimately incurs 2× order count vs control) |
| slippage_model | 1.5% adverse × 4 fills |
| data_requirements | full dataset |
| unsupported_conditions | short leg unlisted or net debit ≤ 0 → CONTRACT_UNAVAILABLE, no trade |

Width selection was a single freeze decision made before results; no delta /
width / expiry optimization was performed.

---

## Candidate C — Defined-Risk RANGE_HV Strategy (iron condor)

Concept: existing `premium_seller.py` iron-condor structure, executed with the
shared execution model on the frozen dataset. Uses the deterministic
premium_seller constants; no new parameters invented to produce a result.

| Field | Frozen rule |
|---|---|
| strategy_name | RANGE_HV iron condor (premium_seller structure) |
| market_regimes | RANGE_HV only. Frozen choice that narrows `premium_seller.sell_ok` (which also allowed RANGE_LV / TREND_LV); matches the Phase-H candidate definition. |
| entry_condition | regime == RANGE_HV AND 16.0 ≤ VIX < 25.0 (premium_seller RICH/HIGH selling window; VIX_PANIC excluded at ≥25) |
| direction_logic | Market-neutral credit collection |
| instrument | Iron condor: short 2% OTM strangle + 150-pt wings, 1 lot (75) |
| expiry_rule | `expiry_calendar.get_expiry_for_trade_date(d)` |
| strike_rule | Short call Kc = round(S×1.02/50)×50; short put Kp = round(S×0.98/50)×50; wings = nearest listed strike to Kc+150 / Kp−150 |
| position_size | 1 lot (75). NOTE: premium_seller's original risk-based sizing (1% of capital per unit) is REPLACED by the shared 1-lot convention for comparability — documented difference, not hidden. |
| entry_price | Net credit = (Kc+Kp) − (KcW+KpW) from chain LTP else BS(sigma=0.15) per leg. Skip if credit ≤ 0 or any leg unlisted. |
| stop_rule | Cut when net credit ≥ 2.0 × entry credit (premium_seller STOP_MULT=2) |
| target_rule | Book when credit ≤ 0.5 × entry credit (premium_seller PROFIT_TARGET_PCT=0.50) |
| exit_rule | TARGET / STOP / TIME (close when days since entry ≥ entry-DTE − 2, i.e. ~2 calendar days before expiry, premium_seller DAYS_TO_CLOSE=2 applied to the true historical DTE) / EXPIRY / EOD (window-end force close) |
| cost_model | ₹40 × 8 orders = ₹320 / trade (4 legs × 2 sides) |
| slippage_model | 1.5% adverse × 8 fills |
| data_requirements | full dataset |
| unsupported_conditions | any leg unlisted or credit ≤ 0 → no trade |

No width/delta/premium/target/stop optimization. All constants are
premium_seller's frozen values.

---

## Candidate D — No-Trade Control

| Field | Frozen rule |
|---|---|
| strategy_name | No-trade control (permanent RANGE_LV-style abstention) |
| market_regimes | all → NO TRADE |
| entry_condition | never |
| instrument | none |
| cost/slippage | 0 |
| outcome | 0 trades, ₹0 P&L, ₹0 drawdown — the benchmark every strategy must beat net of costs to justify trading |

---

## Freeze discipline notes

1. All constants above (SPREAD_WIDTH, condor legs/wings/targets/stops, VIX
   gate, lot, costs) were fixed in `multi_strategy_backtest.py` before the
   first result-bearing run.
2. The control path calls the authoritative `backtest_frozen` functions so the
   F3 baseline is reproduced trade-for-trade (verified: 48 trades, win 33.3%,
   net ₹1,906.43, PF 1.011).
3. No candidate received different cost/slippage/expiry/data rules; the only
   per-candidate differences are (a) order-leg count (2/4/8 orders), which is
   an intrinsic property of the instrument, and (b) Candidate C's sizing
   convention, documented above.
4. The live/paper production strategy was NOT modified. Phase D live/paper
   observation is separate and untouched.
