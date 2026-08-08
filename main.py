"""NSE Trading Research Platform - CLI entry.

Commands:
  python main.py fetch-data            -> download NIFTY history + option chain
  python main.py research [--grid]     -> backtest strategy grid, write reports
  python main.py report                -> market snapshot report from last data
  python main.py all                   -> full pipeline
"""
import argparse
import datetime as dt
import os
import sys
import time

import pandas as pd

import data_fetcher
import indicators
import strategies
import backtester
import report as report_mod

DATA_DIR = "data"
RESULT_DIR = "results"
SYMBOL = "NIFTY 50"
CHAIN_SYMBOL = "NIFTY"


def ensure_dirs():
    for d in (DATA_DIR, RESULT_DIR):
        os.makedirs(d, exist_ok=True)


def fetch_data(days=730):
    ensure_dirs()
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    hist = data_fetcher.fetch_index_history(SYMBOL, start=start, end=end,
                                            out_csv=os.path.join(DATA_DIR, "nifty_history.csv"))
    print(f"Index history: {len(hist)} rows ({hist['date'].min():%d-%m-%Y} to {hist['date'].max():%d-%m-%Y})")

    chain = None
    for attempt in range(3):
        try:
            chain = data_fetcher.fetch_option_chain(CHAIN_SYMBOL,
                                                    out_json=os.path.join(DATA_DIR, "option_chain.json"))
            if not chain.empty:
                break
        except Exception as e:  # noqa: BLE001
            print(f"Chain fetch attempt {attempt+1} failed: {e}")
            time.sleep(2)
    if chain is not None and not chain.empty:
        print(f"Option chain: {len(chain)} strikes, expiry {chain['expiry'].iloc[0]}")
    else:
        print("Option chain: unavailable (market closed / blocked)")
    return hist, chain


def research():
    ensure_dirs()
    path = os.path.join(DATA_DIR, "nifty_history.csv")
    if not os.path.exists(path):
        print("No data. Run: python main.py fetch-data")
        sys.exit(1)
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = indicators.add_all_indicators(df)
    df = df.dropna(subset=["sma50", "adx", "vwap20"]).copy()

    grid = strategies.build_grid_with_holds()
    print(f"Testing {len(grid)} strategy configs...")
    results = []
    for cfg in grid:
        fn = strategies.ALL_STRATEGIES[cfg["name"]]
        sig = fn(df, **cfg["params"])
        trades, metrics = backtester.evaluate(df, sig, hold=cfg["hold"])
        results.append({"name": cfg["name"], "params": cfg["params"],
                        "hold": cfg["hold"], "metrics": metrics, "trades": trades})

    # Out-of-sample check on top candidates: backtest on last 40% of data only
    good = [r for r in results if r["metrics"]["trades"] >= 20]
    good.sort(key=lambda r: r["metrics"]["pnl"], reverse=True)
    split = int(len(df) * 0.6)
    oos = []
    for r in good[:5]:
        fn = strategies.ALL_STRATEGIES[r["name"]]
        sig = fn(df.iloc[split:], **r["params"])
        _, m = backtester.evaluate(df.iloc[split:], sig, hold=r["hold"])
        oos.append({"name": r["name"], "params": r["params"], "hold": r["hold"], "metrics": m})

    txt = report_mod.generate_backtest_report(results, os.path.join(RESULT_DIR, "strategy_research.md"), oos=oos)
    print(txt)
    print(f"\nReport: {RESULT_DIR}/strategy_research.md")


def market_report():
    ensure_dirs()
    path = os.path.join(DATA_DIR, "nifty_history.csv")
    if not os.path.exists(path):
        print("No data. Run: python main.py fetch-data")
        sys.exit(1)
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = indicators.add_all_indicators(df)

    chain = None
    if os.path.exists(os.path.join(DATA_DIR, "option_chain.json")):
        try:
            chain = pd.read_json(os.path.join(DATA_DIR, "option_chain.json"))
            chain = data_fetcher.compute_chain_metrics(chain)
        except Exception:  # noqa: BLE001
            chain = None

    txt = report_mod.generate_market_report(df, chain, os.path.join(RESULT_DIR, "market_report.md"))
    print(txt)
    print(f"\nReport: {RESULT_DIR}/market_report.md")


def main():
    ap = argparse.ArgumentParser(description="NSE Trading Research Platform")
    ap.add_argument("cmd", nargs="?", default="all",
                    choices=["fetch-data", "research", "report", "all"])
    args = ap.parse_args()

    if args.cmd in ("fetch-data", "all"):
        hist, chain = fetch_data()
        if args.cmd == "fetch-data":
            return
    if args.cmd in ("research", "all"):
        research()
    if args.cmd in ("report", "all"):
        market_report()


if __name__ == "__main__":
    main()
