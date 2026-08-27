# Phase H — Multi-Strategy Backtest (Fair Comparison)

Author: OpenCode
Date: 2026-08-14
Result hash: `c1d3a044e5744343bfa5796a8ea2c9f978b890d32f041fe627c37040ab3f6146`
Spec hash: `f814e452da62b2087fa050be692ba2e5ae4d33a6cf812bcaec859a10a5524f20`
Dataset composite hash: `018c182ef833c620d3b36ac22faadf956caabb42bf5264445e4ab7dac2a9d163`
Window: 2025-08-13 → 2026-08-13 (245 trading days)
Machine: `multi_strategy_backtest.py` (isolated, MEASUREMENT ONLY). Output:
`results/phaseH_multi_strategy.json`.

---

## 1. Methodology

Four candidates were run against the SAME frozen dataset snapshot (nifty,
VIX, FII/DII, ML features, 247 OI snapshots, corrected expiry calendar), the
same expiry model (`expiry_calendar.py`), the same cost model (₹40/order),
the same slippage model (1.5% adverse/fill), the same no-lookahead rules, and
the same metric definitions. Specifications were frozen and hashed BEFORE any
result was inspected (`audit/PHASE-H-STRATEGY-SPECIFICATIONS.md`).

- A = current frozen control, executed by the authoritative `backtest_frozen`
  functions → reproduces the F3 baseline trade-for-trade.
- B = defined-risk directional vertical spread (500-pt width), control's entry
  funnel restricted to trend regimes, correct bias→spread mapping.
- C = RANGE_HV iron condor (premium_seller structure) with shared execution
  model, gated on RANGE_HV + VIX 16–25.
- D = no-trade control.

Control reproduction check (must equal F3): trades=48, win 33.3%,
net ₹1,906.43, PF 1.011 — PASS (byte-identical trade set).

NOTE: while Phase H ran, the live daemon appended 2026-08-14 to
`data/nifty_history.csv`, mutating the live cache between the first two runs.
The dataset was therefore frozen into a snapshot (`/tmp/opencode/phaseH_frozen_data`)
and both reproducibility runs were executed against that snapshot. This data
drift is an environmental observation, not a strategy change.

---

## 2. Comparison table

| Metric | Current (A) | Spread (B) | Range/Condor (C) | No-Trade (D) |
|---|---:|---:|---:|---:|
| Trades | 48 | 24 | 6 | 0 |
| Win Rate | 33.3% | 20.8% | 66.7% | n/a |
| Net P&L (₹) | +1,906.43 | −44,398.33 | +6,248.25 | 0 |
| PF | 1.011 | 0.473 | 9.693 | n/a |
| Expectancy (₹/trade) | +39.72 | −1,849.93 | +1,041.38 | 0 |
| Max DD (₹) | −51,746.80 | −52,179.12 | −587.00 | 0 |
| MFE (avg, ₹) | +6,358.22 | +2,127.97 | +1,853.12 | 0 |
| MAE (avg, ₹) | −4,182.41 | −3,317.81 | −770.00 | 0 |
| Avg hold (days) | 2.35 | 2.25 | 5.5 | n/a |
| Trade frequency | 4.0/mo, 48/yr | 2.0/mo, 24/yr | 0.5/mo, 6/yr | 0 |

Risk-adjusted (see §7):
- A: Sharpe 0.071, Sortino 0.149, Calmar 0.037 — positive but negligible.
- B: NOT_RELIABLE (distinct daily P&L < 20).
- C: NOT_RELIABLE (n = 6 < 20).

---

## 3. Trade outcomes & exits

| | A | B | C |
|---|---:|---:|---:|
| STOP_LOSS | 18 | 9 | 0 |
| TAKE_PROFIT | 12 | 5 | 3 |
| EXPIRY_SQUARE_OFF | 18 | 10 | 1 |
| TIME (2d before expiry) | 0 | 0 | 2 |
| CE / PE | 0 / 48 | 7 / 17 (SPREAD) | condor × 6 |

A is all-PUT (frozen side-selection defect, unchanged per mandate). B used
correct bias mapping (7 bull-call, 17 bear-put). C is market-neutral credit.

Avg win / avg loss: A +10,649.56 / −5,265.20 (RR ≈ 2.0, wins rare).
B +7,975.27 / −4,435.51 (RR ≈ 1.8, wins rarer). C +1,741.75 / −359.38
(RR ≈ 4.8, wins frequent — theta tail).

---

## 4. Regime comparison

| Regime | A (trades / net ₹) | B (trades / net ₹) | C (trades / net ₹) |
|---|---:|---:|---:|
| TREND_HV | 20 / +1,986.08 | 20 / −27,271.02 | — |
| TREND_LV | 4 / +2,210.61 | 4 / −17,127.31 | — |
| RANGE_HV | 24 / −2,290.26 | — (excluded by spec) | 6 / +6,248.25 |
| RANGE_LV | 0 (gate closed) | — | — |

Reading: the frozen funnel's edge (if any) is regime-concentrated; B lost in
every trend regime; C's only exposure (RANGE_HV, VIX-rich) was profitable.

---

## 5. Monthly / out-of-sample stability

Development = exits < 2026-03-01; out-of-sample = exits ≥ 2026-03-01.
No candidate was optimized against OOS.

| | Dev trades / net | OOS trades / net |
|---|---:|---:|
| A | 18 / −26,516.46 | 30 / +28,422.89 |
| B | 12 / −52,281.16 | 12 / +7,882.83 |
| C | 0 / 0 | 6 / +6,248.25 |

Monthly net (₹) — A: Aug −2,043 | Oct −3,060 | Nov +6,209 | Jan −11,028 |
Feb −16,593 | **Mar +35,782** | Apr −12,079 | May −4,980 | Jun +2,533 |
Jul +7,167. All of A's positive P&L and most of B's recovery come from a
single month (Mar-2026). C's 6 trades span Mar/May + Apr ×3 — all positive
months, all OOS.

---

## 6. Profit concentration (fragility check)

| | A | B | C |
|---|---:|---:|---:|
| % profit from best month | 1,876.9% | (negative total) | 52.3% |
| % profit from best trade | 1,500.4% | (negative total) | 36.1% |
| % profit from top-5 trades | 5,083.8% | (negative total) | 109.4% |

A's net (+₹1,906) is dwarfed by a single month (+₹35,782) and a single trade
(+₹28,604): the whole year's "profit" is two lucky trades. B's total is
negative so percentages are not meaningful (reported raw). C is the least
concentrated of the profitable candidates but its denominator is 6 trades.

---

## 7. Risk-adjusted (where supported)

A (n=48): Sharpe 0.071, Sortino 0.149, Calmar 0.037 — a barely-positive,
high-volatility profile; consistent with "no durable edge".
B and C: NOT_RELIABLE per the frozen rule (risk-adjusted metrics are only
reported where the sample supports them; both lack a sufficient distinct
daily-P&L sample). No manufactured statistics.

---

## 8. Strategy assessment

| Dimension | A | B | C |
|---|---|---|---|
| Edge quality | none (PF 1.01) | negative | promising (PF 9.7, n=6) |
| Stability | terrible (1 month = whole year) | losing in 5/6 months | positive in all 3 months, tiny n |
| Drawdown | −₹51.7k (27% of equity path) | −₹52.2k | −₹587 (−0.6%) |
| Sample size | 48 (adequate to see no edge) | 24 (adequate to see no edge) | 6 (insufficient) |
| Trade frequency | 4/mo | 2/mo | 0.5/mo |
| Regime robustness | thin, luck-driven | none | RANGE_HV only, untested elsewhere |
| Execution realism | BS-0.15 fallback + EOD marks | +2 fills (₹160/trade) | 8 fills (₹320/trade) |
| Complexity | low | low | moderate |
| **Classification** | **BASELINE_ONLY** | **WEAK** | **PROMISING_BUT_INSUFFICIENT** |
| D | not applicable (control condition) | | |

---

## 9. Required conclusions

- **Best historical result:** C net +₹6,248 > A +₹1,906 > D 0 > B −₹44,398.
  C's lead is real but rests on 6 trades → call it **INSUFFICIENT** as an edge.
- **Best risk-adjusted profile:** A (Sharpe 0.071) is the only measurable one,
  and it is negligible. C's profile (RR 4.8, maxDD −₹587) is the best in
  economic terms but **INSUFFICIENT_SAMPLE**.
- **Most stable month-to-month:** none qualifies. A's profit is one month;
  B is negative in 5 of 6 months; C is positive in all 3 but has 6 trades.
- **Which worked in which regime:** TREND_LV was A's only positive regime
  (n=4); RANGE_HV is C's winning regime; B lost in every trend regime.
- **Smallest drawdown:** C (−₹587). Both naked directional candidates peaked
  around −₹52k regardless of the (very different) net outcome.
- **Least data:** D (none). Among traders, A and B use the full funnel; C uses
  only regime+VIX — but the market data needed is identical.
- **Easiest to paper trade safely:** C (defined risk, tiny drawdown, no
  stop-hunting sensitivity) — if more data confirms it. B is also defined-risk
  but demonstrably negative.
- **Should not be pursued further:** B (PF 0.47, −₹44k, no regime positive).
- **Durable edge:** **NOT_PROVEN.** A shows no edge; C is
  PROMISING_BUT_INSUFFICIENT (6 trades, all OOS).

---

## 10. Reproducibility

Two independent runs against the frozen snapshot produced byte-identical
payloads (excluding documented run timestamps) and identical result hashes
`c1d3a044…`. Control trade set byte-identical to F3.

## 11. Production isolation

Verified: `multi_strategy_backtest.py` only READS `data/*` and writes to
`--out` and `results/phaseH_multi_strategy.json`. It never touches
`data/ground_truth.db`, `paper_account.json`, or production signals/outcomes.
The live daemon continued legitimate Ground-Truth writes throughout; Phase H
made none. Current strategy/paper observation unchanged.

## 12. Limitation

The comparison's weakest cell is C's sample: only 19 RANGE_HV days in the
frozen window satisfy the 16–25 VIX gate, yielding 6 condors clustered in
Mar–May-2026. This is a data-availability fact, not a design failure — it is
exactly why C is classified PROMISING_BUT_INSUFFICIENT rather than a winner.
