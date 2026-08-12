"""Portfolio rebalancing backtest - tests the 'diversify + rebalance' alpha
from the Pavel Kichev interview (Chart Fanatics).

Compares on cached NIFTY daily data:
  A) each strategy standalone
  B) equal-weight portfolio, weights drift (diversification only)
  C) equal-weight portfolio, periodic rebalance (monthly / weekly)

Run:  .venv/bin/python portfolio_rebalance.py
"""
import os
import sys
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
warnings.filterwarnings("ignore")

from backtester import run_backtest, compute_metrics
from indicators import add_all_indicators
import strategies

DATA = os.path.join(HERE, "data", "nifty_history.csv")
TRADING_DAYS = 252


def load_nifty_daily():
    df = pd.read_csv(DATA)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return add_all_indicators(df)


def strategy_trades(df, name, params=None, hold=5, risk_pct=0.25):
    """Run one strategy -> trades DF (underlying mode, % of risked capital)."""
    fn = strategies.ALL_STRATEGIES.get(name)
    if fn is None:
        return None
    signal = fn(df, **(params or {}))
    return run_backtest(df, signal, hold=hold, mode="underlying",
                        risk_pct=risk_pct)


def trades_to_returns(trades, index):
    """Map trade P&L (in % capital terms) onto a per-bar return series."""
    ret = pd.Series(0.0, index=index)
    if trades is None or trades.empty:
        return ret
    # risk_pct-scaled pnl: pnl is in currency, norm by risk_cap is embedded.
    # Convert pnl to % of full capital: run_backtest used risk_pct fraction.
    for _, t in trades.iterrows():
        d = pd.Timestamp(t["exit_date"])
        if d in index:
            ret.loc[d] += t["ret_pct"] / 100.0 * 0.25  # pnl % of risk_cap
    return ret


def portfolio_curve(returns, weights, rebal_period=None):
    """Rebalancing engine (sub-account method).

    Each strategy gets a separate sub-account compounding its own returns.
    rebal_period None  -> sub-accounts drift forever (diversification only)
    rebal_period 'M'/'W' -> at each period boundary, recombine all
                            sub-accounts into one pot and redistribute at
                            target weights (true rebalancing).
    Returns (equity_curve, drift_track) where drift_track logs weight drift.
    """
    frame = pd.DataFrame(returns).fillna(0.0)
    names = [w for w in weights if w in frame.columns]
    if not names:
        return pd.Series(dtype=float), {}
    w = np.array([weights[n] for n in names], dtype=float)
    w = w / w.sum()
    subs = w.copy()          # sub-account shares of the 1.0 pot
    value = 1.0
    curve = []
    drift_log = []
    cur_period = None
    for dt, row in frame.iterrows():
        r = row[names].to_numpy(dtype=float)
        period = dt.to_period(rebal_period) if rebal_period else None
        if rebal_period is not None and period != cur_period:
            if cur_period is not None:
                # rebalance: recombine pot, reset to target weights
                subs[:] = w
            cur_period = period
        # compound each sub-account with its own return
        subs = subs * (1.0 + r)
        value = float(subs.sum())
        curve.append(value)
        drift_log.append((dt, subs.copy() / max(value, 1e-12)))
    return pd.Series(curve, index=frame.index), drift_log


def metrics_from_curve(curve, rf=0.06):
    if curve.empty or len(curve) < 20:
        return {}
    rets = curve.pct_change().dropna()
    total = curve.iloc[-1] / curve.iloc[0] - 1
    years = len(curve) / TRADING_DAYS
    cagr = (curve.iloc[-1] / curve.iloc[0]) ** (1 / years) - 1 if years > 0 else 0
    std = rets.std()
    sharpe = (rets.mean() - rf / TRADING_DAYS) / std * np.sqrt(TRADING_DAYS) if std and std > 0 else 0
    dd = (curve / curve.cummax() - 1).min()
    return {
        "final_value": round(curve.iloc[-1], 4),
        "cagr_pct": round(cagr * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_dd_pct": round(dd * 100, 1),
    }


def fmt(m):
    if not m:
        return "no data"
    return (f"₹{m['final_value']*100000:.0f} | CAGR {m['cagr_pct']}% | "
            f"Sharpe {m['sharpe']} | MaxDD {m['max_dd_pct']}%")


def main():
    df = load_nifty_daily()
    print(f"NIFTY daily: {len(df)} bars  {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}")
    print()

    # Uncorrelated strategy streams (low correlation by construction)
    streams = {
        "trend":       {"name": "trend_sma", "params": {"fast": 20, "slow": 50, "adx_thresh": 25, "use_adx": True}, "hold": 10},
        "momentum":    {"name": "momentum_roc", "params": {"n": 10, "thresh": 2.0}, "hold": 5},
        "mean_rev":    {"name": "rsi_meanrev", "params": {"low": 30, "high": 70}, "hold": 3},
    }

    returns = {}
    for key, cfg in streams.items():
        trades = strategy_trades(df, cfg["name"], cfg["params"], hold=cfg["hold"])
        returns[key] = trades_to_returns(trades, df.index)
        n = len(trades) if trades is not None else 0
        print(f"  {key:<12} trades={n}")

    # correlation check
    frame = pd.DataFrame(returns).fillna(0.0)
    corr = frame.corr()
    print("\n  correlation matrix:")
    print(corr.round(2).to_string())

    print("\n" + "=" * 66)
    print("PORTFOLIO REBALANCING TEST  (equal-weight NIFTY daily)")
    print("=" * 66)

    weights = {k: 1.0 / len(returns) for k in returns}

    print("\n  [A] STRATEGIES STANDALONE")
    for k in returns:
        curve = returns[k].add(1).cumprod()
        print(f"    {k:<12} {fmt(metrics_from_curve(curve))}")

    print("\n  [B] DIVERSIFIED (equal weight, NO rebalance)")
    c_nr, drift_nr = portfolio_curve(returns, weights, rebal_period=None)
    print(f"    {'portfolio':<12} {fmt(metrics_from_curve(c_nr))}")
    if drift_nr:
        last = {k: round(float(v), 3) for k, v in zip(returns.keys(), drift_nr[-1][1])}
        print(f"    weights at end (drift): {last}  <-- momentum/trend overweighted")

    print("\n  [C] DIVERSIFIED + MONTHLY REBALANCE")
    c_r, drift_r = portfolio_curve(returns, weights, rebal_period="M")
    print(f"    {'portfolio':<12} {fmt(metrics_from_curve(c_r))}")

    print("\n  [D] DIVERSIFIED + WEEKLY REBALANCE")
    c_w, _ = portfolio_curve(returns, weights, rebal_period="W")
    print(f"    {'portfolio':<12} {fmt(metrics_from_curve(c_w))}")

    m_a = metrics_from_curve(c_nr)
    m_b = metrics_from_curve(c_r)
    if m_a and m_b and m_a.get("final_value"):
        lift = (m_b["final_value"] / m_a["final_value"] - 1) * 100
        print(f"\n  => Rebalance edge: +{lift:.1f}% terminal value (vs no-rebalance)")

    out = {
        "generated": datetime.now().isoformat(timespec="minutes"),
        "bars": len(df),
        "streams": {k: metrics_from_curve(returns[k].add(1).cumprod()) for k in returns},
        "diversified_no_rebal": m_a,
        "diversified_monthly": m_b,
        "diversified_weekly": metrics_from_curve(c_w),
        "correlation": corr.round(2).to_dict(),
    }
    import json
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    with open(os.path.join(HERE, "data", "rebalance_test.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"\n  saved -> data/rebalance_test.json")


if __name__ == "__main__":
    main()
