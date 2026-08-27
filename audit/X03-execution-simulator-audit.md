# X03 — Execution & Simulator Audit (X-Ray)

> X-Ray phase 3. Built 2026-08-13. Focus: paper-execution ledger, auto-trader
> gates, backtest cost model, risk-engine internals. No real-order path exists.

---

## 1. Paper trading ledger — `paper_trader.py`

Singleton `paper_engine`. Virtual account; APIs:
`execute_paper_order`, `close_paper_position`, `get_paper_account_summary`
(status dicts: EXECUTED / REJECTED / CLOSED / ERROR).

**Persisted** to `data/paper_account.json`: `initial_capital`, `cash_balance`,
`open_positions`, `closed_trades`. Setup (`capital_guard.__main__`) seeds
`SEED_CAPITAL`, `realized_pnl`, `history_day`, `current_pnl_duration`.

Consumers: `auto_paper_runner.py`, `agent_workflow_graph.py` (node 5),
`run_all.py` (step 19 — summary read only), `control_center.py` (menu 3),
`test_all.py`, `reflection_engine.py` (reads summary).

## 2. Auto paper trader — `auto_paper_runner.py` (the live loop)

One autonomous iteration with explicit stand-down gates, run every 30s by
`quant_daemon.py`. Exact sequence:

1. live spot sync (`live_market_fetch`)
2. CapitalGuard audit + VaR → `BLOCKED` → stand down
3. MTF alignment check
4. volume analytics
5. **6-layer precision signal** → `STAY_OUT`/`NO_SIGNAL` → stand down
6. smart strike (Δ 0.30–0.55)
7. entry / SL / target (1:2 RRR, **1.5×ATR SL**)
8. dynamic trailing (Chandelier ×2.5)
9. `paper_engine.execute_paper_order` (**1 lot × 75**)

This is the closest thing to an execution path; it is fully gated and paper-only.
⚠️ The gate relies on `precision_signals`, which fabricates Layer 3 consensus
(H1) — so a "green" gate can be built from non-real inputs.

## 3. Backtest cost model — `backtester.py`

`run_backtest(df, signal, hold, strike_dist, capital, risk_pct, vol_window,
days_per_bar, mode)`:
- Signal on close(T) → enter open(T+1) → exit close(T+hold).
- `mode="option"`: BS premium, ATM±1% strike, 20-day expiry, rolling HV,
  **slippage 1.5%**, **₹40 cost/trade**.
- `mode="underlying"`: moves a fraction of risked capital (cross-TF fairness).
- `compute_metrics()`/`evaluate()` → PF, Sharpe, CAGR, maxDD.

Consumers: `main.py`, `multitf.py`, `trade_journal.py` (`--from-backtest`),
`test_all.py`. No daemon. Cost model is reasonable; the multi-leg/spread paths
use live LTP + BS greeks instead.

## 4. Risk-engine internals — exact constants

### `capital_guard.py`
- `RISK_PER_TRADE_PCT=0.01`, `DAILY_LOSS_LIMIT_PCT=0.03`, `WEEKLY_LOSS_LIMIT_PCT=0.07`
- `FIXED_SL_MODE=True`, `SL_ATR_MULT=1.5`, `ATR_FALLBACK_PCT=0.008`
- `EXPIRY_LAST_ENTRY_HOUR=14.5`, `EXPIRY_SQUARE_OFF_HOUR=15.0`, `EXPIRY_WINDOW_RISK=1`
- `MIN_CONFIDENCE=55.0`
- `STOP_LIMIT_VIX_PANIC_THRESHOLD=22`, `MIN_CAPITAL_CUSHION=0.05`
- `TRAILING_STOP_MODE="COMPOUND"`, `SPLIT_AND_AVG=False`, `STOCK_SL_HIT_BTW_PANIC=2`, `S_PCT_HOLDING=20`
- **Position sizing**: `lots = max(1, floor(capital * 0.01 / (strike_price * 100 * SL_percentage)))`
  → **floors at 1 lot, violating its own 1% cap (H2)**.
- `check_event_risk` always `NO_EVENT_DATA` (no calendar wired in).
- Default SL = 50% of premium (owner rule is 1.5×ATR) (M4).

### `var_risk_manager.py`
- Parametric VaR: z95=1.645, z99=2.326, vol floor 0.2%, fallback 1.5% (30 sessions);
  approved iff VaR95 ≤ 3% capital.
- Stress tests −5/−10/−22% at **fixed 0.5 delta** → always "PASSED" (formulaic).

### `monte_carlo.py`
- 10,000 sims × 100 trades, WR 0.55, win/loss 1.8, risk 1%, ruin at 50% DD,
  **fixed seed 42**. Survival ≥99% → "PASSED"; downstream survival gate 95%.

### `delta_hedging_guard.py`
- Trigger `|net_delta| > 500`, target ±100, `lots = int(delta_to_hedge/37.5)`
  (~0.5Δ × 75). Default net_delta=650 → hedge BUY_PE.

### `dynamic_trailing.py`
- ATR Chandelier ×2.5. RRR≥2.0 → lock +1.5×initial_risk (TIER_3); RRR≥1.0 →
  lock +0.5×risk (TIER_2); else max(initial_sl, chandelier).

### `expectancy_calculator.py` / `profit_engine.py`
- `EV = WR*avg_win − (1−WR)*avg_loss`; defaults 55% / ₹2000 / ₹1000 → `POSITIVE_EDGE`.
- profit_engine: risk 1%, SL=1.2×ATR, T1=2×SL, T2=3×SL; **hardcodes 50% win-rate**.

## 5. Multi-leg & seller engines

### `multi_leg_options.py`
- Defined-risk spreads from real LTP/BS: bull call, bear put, short strangle
  (hedged), iron condor. `WING=200`, inner short legs 150 (width//4 if custom),
  lot 75, sigma 0.15 default, r=0.06, PoP via greeks. Uses chain IV where live.

### `premium_seller.py`
- Iron-condor seller backtest: gate **VIX 16–25** and not TREND_HV (BB width
  >5%); shorts ±2% OTM (`spot_dist=0.02`), wings +150; exit 50% of credit /
  2× credit stop / 2 days before expiry; 1% risk.
- ⚠️ **Uses `25` qty/lot here vs `75` everywhere else** — reported 72.5% win /
  PF 2.6 is computed on the wrong lot size for this platform.

## 6. Simulation integrity findings

| # | Finding | Severity |
|---|---|---|
| 1 | `capital_guard` sizer floors at 1 lot → can exceed 1% cap by construction (H2) | HIGH |
| 2 | `var_risk_manager` stress tests formulaic (`capital × drop × 0.5`), always PASSED | MED |
| 3 | `monte_carlo` fixed seed 42 + hardcoded WR 0.55 → deterministic, not evidence | MED |
| 4 | `premium_seller` lot size 25 vs 75 → headline backtest number misleading | MED |
| 5 | `long_term_backtest` hardcodes "ULTRA_ROBUST" verdict string | MED |
| 6 | `profit_engine` hardcodes 50% win-rate into expectancy | LOW |
| 7 | `paper_trade_journal` table never INSERTed → no persistent paper trade audit | LOW |
| 8 | `agent_workflow_graph` may place paper orders — no dedicated test | LOW |

## 7. Execution loop gaps

- `run_all` step 19 reads the paper summary but **never runs the auto-trader**;
  the actual loop only lives in `quant_daemon` — two "run everything" paths
  diverge in what they execute.
- No broker reconcile (`connection_resilience.reconcile_offline_state` is a stub).
- `place_order` in broker client is an ungated real-money primitive with 0 callers (L5).
