"""Multi-timeframe backtesting - test option strategies on 15m/30m/60m/daily.

NSE tooling idea: the same strategy behaves differently per timeframe.
A good intraday options setup on 15m can be a bad daily one. We fetch
Yahoo intraday bars and run the full strategy grid on each timeframe,
then rank which TF gives the best edge per strategy.
"""
import datetime as dt
import time

import numpy as np
import pandas as pd
import requests

import indicators
import strategies
import backtester

YH = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"}
INTERVALS = {"15m": "15m", "30m": "30m", "60m": "60m"}
# Yahoo per-interval range limits (days of data served for index charts)
MAX_RANGE_DAYS = {"15m": 60, "30m": 60, "60m": 90, "1d": 730}


def fetch_intraday(interval="15m", days=180, ticker="%5ENSEI"):
    """Yahoo intraday bars (^NSEI). Returns OHLCV DataFrame with tz-aware index."""
    days = min(days, MAX_RANGE_DAYS.get(interval, 90))
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={interval}&range={days}d"
    r = requests.get(url, headers=YH, timeout=25)
    r.raise_for_status()
    d = r.json()["chart"]["result"][0]
    ts = d["timestamp"]
    q = d["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(ts):
        try:
            rows.append({
                "datetime": pd.to_datetime(t, unit="s", utc=True).tz_convert("Asia/Kolkata"),
                "open": q["open"][i], "high": q["high"][i],
                "low": q["low"][i], "close": q["close"][i],
                "volume": q["volume"][i] or 0,
            })
        except (TypeError, IndexError):
            continue
    df = pd.DataFrame(rows).dropna(subset=["open", "high", "low", "close"])
    return df.set_index("datetime").sort_index()


BARS_PER_DAY = {"15m": 27, "30m": 13.5, "60m": 6.75, "1d": 1.0}


def run_strategy_on_tf(df, cfg, tf="1d"):
    """Run one strategy config on a timeframe frame. Returns (trades, metrics)."""
    fn = strategies.ALL_STRATEGIES.get(cfg["name"])
    if fn is None:
        return None
    try:
        params = cfg.get("params", {})
        signal = fn(df, **params)
    except Exception:
        return None
    hold = cfg.get("hold", 1)
    # intraday: cap option time-to-expiry assumption in backtester
    trades = backtester.run_backtest(df, signal, hold=hold,
                                     days_per_bar=BARS_PER_DAY.get(tf, 1.0),
                                     mode="underlying")
    return trades, backtester.compute_metrics(trades)


def load_tf_frames(intervals=("15m", "60m", "1d"), days=120):
    """Fetch + indicator-enrich all timeframe frames once (for grid scans)."""
    frames = {}
    for iv in intervals:
        try:
            if iv == "1d":
                from data_fetcher import _fetch_yahoo
                df = _fetch_yahoo("^NSEI", dt.date.today() - dt.timedelta(days=days), dt.date.today())
                df = df.set_index("date")
            else:
                df = fetch_intraday(INTERVALS[iv], days=days)
            frames[iv] = indicators.add_all_indicators(df)
        except Exception as e:
            print(f"  skip {iv}: {e}")
    return frames


def backtest_all_timeframes(cfg, intervals=("15m", "60m", "1d"), days=180, frames=None):
    """Backtest one strategy config across multiple timeframes (cached frames ok)."""
    if frames is None:
        frames = load_tf_frames(intervals, days)
    out = {}
    for iv in intervals:
        df = frames.get(iv)
        if df is None:
            continue
        try:
            res = run_strategy_on_tf(df, cfg, tf=iv)
            if res and not res[0].empty:
                trades, metrics = res
                out[iv] = {"metrics": metrics, "n_trades": metrics["trades"]}
        except Exception as e:
            out[iv] = {"error": str(e)[:60]}
    return out


def tf_grid_scan(configs, intervals=("15m", "60m", "1d"), days=120, progress=True):
    """Scan a list of configs across timeframes, rank best TF per strategy."""
    frames = load_tf_frames(intervals, days)
    rows = []
    for i, cfg in enumerate(configs):
        res = backtest_all_timeframes(cfg, intervals, days, frames=frames)
        row = {"name": cfg["name"], "params": json_safe(cfg["params"]), "hold": cfg.get("hold", 1)}
        for iv, r in res.items():
            if "metrics" in r and r["metrics"]["trades"] >= 10:
                row[f"{iv}_pnl"] = r["metrics"]["pnl"]
                row[f"{iv}_win"] = r["metrics"]["win_rate"]
                row[f"{iv}_trades"] = r["metrics"]["trades"]
                row[f"{iv}_pf"] = r["metrics"]["profit_factor"]
        rows.append(row)
        if progress and (i + 1) % 25 == 0:
            print(f"  ...{i+1}/{len(configs)}")
    return pd.DataFrame(rows)


def json_safe(d):
    return {k: (str(v) if isinstance(v, (dict, list)) else v) for k, v in d.items()}


def best_tf_report(df):
    """Given a tf_grid_scan result, summarize which TF suits which strategy."""
    lines = []
    for name, grp in df.groupby("name"):
        best = None
        best_pnl = -1e9
        for iv in ("15m", "60m", "1d"):
            col = f"{iv}_pnl"
            if col not in grp.columns:
                continue
            sub = grp[grp[col].notna()]
            if sub.empty:
                continue
            best_in_iv = sub.loc[sub[col].idxmax()]
            if best_in_iv[col] > best_pnl and best_in_iv[f"{iv}_trades"] >= 10:
                best_pnl = best_in_iv[col]
                best = (iv, best_in_iv)
        if best:
            iv, r = best
            lines.append(
                f"{name:16s} best TF={iv:3s} pnl {r[f'{iv}_pnl']:>+10,.0f} "
                f"win {r[f'{iv}_win']:.0f}% n={int(r[f'{iv}_trades'])} params={r['params']}")
    return lines


if __name__ == "__main__":
    cfg = {"name": "rsi_meanrev", "params": {"low": 40, "high": 60}, "hold": 3}
    res = backtest_all_timeframes(cfg)
    for iv, r in res.items():
        if "metrics" in r:
            m = r["metrics"]
            print(f"{iv:4s} trades={m['trades']} pnl={m['pnl']:,.0f} win={m['win_rate']}% pf={m['profit_factor']}")
