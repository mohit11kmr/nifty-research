"""Backtesting engine with Black-Scholes option P&L estimation.

Logic: signal on close(T) -> enter at open(T+1) buying OTM option (ATM+~1% strike)
-> exit at close(T+hold). Premium priced via Black-Scholes using recent
historical volatility; carries vega + theta decay. Costs included (brokerage+SIP).
"""
import numpy as np
import pandas as pd
from math import log, sqrt, exp, erf

COST_PER_TRADE = 40.0          # brokerage + taxes per trade (approx)
SLIPPAGE_PCT = 0.015           # 1.5% realistic bid-ask spread slippage on option premium
DAYS_TO_EXPIRY = 20            # assume ~4 weeks to expiry
TRADING_DAYS = 252


def _cdf(x):
    return 0.5 * (1 + erf(x / sqrt(2)))


def bs_call(S, K, T, sigma, r=0.06):
    if sigma <= 0 or T <= 0:
        return max(S - K, 0.0)
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return S * _cdf(d1) - K * exp(-r * T) * _cdf(d2)


def bs_put(S, K, T, sigma, r=0.06):
    if sigma <= 0 or T <= 0:
        return max(K - S, 0.0)
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return K * exp(-r * T) * _cdf(-d2) - S * _cdf(-d1)


def _hist_vol(close, n=20):
    rets = np.log(close / close.shift(1))
    hv = rets.rolling(n, min_periods=n).std() * sqrt(TRADING_DAYS)
    return hv.fillna(0.25)


def run_backtest(df, signal, hold=1, strike_dist=0.01, capital=100000,
                 risk_pct=0.25, vol_window=20, days_per_bar=1.0, mode="option"):
    """Backtest option-buying strategy.

    df: OHLCV+indicators frame (index = dates)
    signal: Series aligned to df index (+1 CALL / -1 PUT / 0 none)
    hold: bars held per trade
    days_per_bar: trading days elapsed per bar (1.0 for daily, ~1/27 for 15m)
    mode: 'option' = Black-Scholes option premium P&L (daily use)
          'underlying' = index move captured, % of risked capital
    Returns trades DataFrame.
    """
    close = df["close"].to_numpy()
    open_ = df["open"].to_numpy()
    dates = df.index
    n = len(df)
    hv = _hist_vol(df["close"], vol_window).to_numpy()
    t = (DAYS_TO_EXPIRY - 0.5) / TRADING_DAYS

    trades = []
    i = 0
    while i < n:
        if signal.iloc[i] == 0:
            i += 1
            continue
        entry_idx = i + 1                      # enter next bar open
        exit_idx = min(entry_idx + hold, n - 1)
        if entry_idx >= n:
            break

        side = int(signal.iloc[i])
        S_in = open_[entry_idx]
        S_out = close[exit_idx]
        if S_in <= 0 or np.isnan(hv[entry_idx]):
            i += 1
            continue

        if mode == "underlying":
            ret = side * (S_out / S_in - 1.0)
            risk_cap = capital * risk_pct
            pnl = risk_cap * ret - 2 * COST_PER_TRADE
            trades.append({
                "entry_date": dates[entry_idx],
                "exit_date": dates[exit_idx],
                "side": "CALL" if side == 1 else "PUT",
                "entry_price": S_in,
                "exit_price": S_out,
                "strike": S_in,
                "premium_in": round(risk_cap, 2),
                "premium_out": round(risk_cap + pnl, 2),
                "lots": 1,
                "pnl": round(pnl, 2),
                "ret_pct": round(ret * 100, 2),
                "cost": round(2 * COST_PER_TRADE, 2),
            })
            i = exit_idx + 1
            continue

        K = round(S_in * (1 + strike_dist * side) / 50) * 50
        sigma_in = max(hv[entry_idx], 0.10)
        sigma_out = max(hv[exit_idx], 0.10)

        prem_in = bs_call(S_in, K, t, sigma_in) if side == 1 else bs_put(S_in, K, t, sigma_in)
        elapsed = hold * days_per_bar / TRADING_DAYS
        prem_out = bs_call(S_out, K, t - elapsed, sigma_out) if side == 1 else bs_put(S_out, K, t - elapsed, sigma_out)

        prem_in *= (1 + SLIPPAGE_PCT)
        prem_out *= (1 - SLIPPAGE_PCT)

        lots = max(int((capital * risk_pct) / max(prem_in, 50.0)), 1)
        cost = lots * (prem_in + prem_out) + 2 * COST_PER_TRADE
        pnl = lots * (prem_out - prem_in) - 2 * COST_PER_TRADE
        ret_pct = pnl / (lots * prem_in) * 100 if prem_in > 0 else 0.0

        trades.append({
            "entry_date": dates[entry_idx],
            "exit_date": dates[exit_idx],
            "side": "CALL" if side == 1 else "PUT",
            "entry_price": S_in,
            "exit_price": S_out,
            "strike": K,
            "premium_in": round(prem_in, 2),
            "premium_out": round(prem_out, 2),
            "lots": lots,
            "pnl": round(pnl, 2),
            "ret_pct": round(ret_pct, 2),
            "cost": round(cost, 2),
        })
        i = exit_idx + 1

    trades_df = pd.DataFrame(trades)
    return trades_df


def _sharpe(returns, rf=0.06):
    r = returns - rf / TRADING_DAYS
    std = r.std()
    return (r.mean() / std * sqrt(TRADING_DAYS)) if std and std > 0 else 0.0


def compute_metrics(trades, capital=100000):
    empty = {"trades": 0, "pnl": 0, "win_rate": 0, "profit_factor": 0,
             "avg_ret_pct": 0, "max_dd_pct": 0, "sharpe": 0, "cagr_pct": 0,
             "hit": 0, "miss": 0}
    if trades is None or trades.empty:
        return empty

    wins = trades[trades["pnl"] > 0]
    losses = trades[trades["pnl"] < 0]
    gross_win = wins["pnl"].sum()
    gross_loss = abs(losses["pnl"].sum())
    pf = gross_win / gross_loss if gross_loss else (np.inf if gross_win else 0)

    eq = (capital + trades["pnl"].cumsum()).to_numpy()
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = dd.min() if len(dd) else 0.0

    rets = trades["pnl"] / capital
    sharpe = _sharpe(rets)

    total_days = 0
    if len(trades) > 1:
        try:
            total_days = (trades["exit_date"].max() - trades["entry_date"].min()).days
        except (TypeError, AttributeError):
            total_days = len(trades)
    years = max(total_days / 365, 1 / 365)
    cagr = 0.0
    if capital > 0:
        base = (capital + trades["pnl"].sum()) / capital
        if base > 0:
            cagr = base ** (1 / years) - 1

    return {
        "trades": len(trades),
        "pnl": round(trades["pnl"].sum(), 2),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if len(trades) else 0.0,
        "profit_factor": round(pf, 2),
        "avg_ret_pct": round(trades["ret_pct"].mean(), 2),
        "max_dd_pct": round(max_dd * 100, 2),
        "sharpe": round(sharpe, 2),
        "cagr_pct": round(cagr * 100, 2),
        "hit": len(wins),
        "miss": len(losses),
    }


def evaluate(df, signal, hold=1, capital=100000):
    trades = run_backtest(df, signal, hold=hold, capital=capital)
    metrics = compute_metrics(trades, capital)
    return trades, metrics
