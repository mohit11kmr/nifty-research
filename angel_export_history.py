"""Export genuine daily/index history from Angel One SmartAPI to CSV.

Pulls ONE_DAY candles for NIFTY / BANKNIFTY (and optional option contracts)
using the Angel One account configured in .env, and writes clean CSVs under
data/exports/ for backtesting.

Usage:
    .venv/bin/python angel_export_history.py                  # NIFTY + BANKNIFTY daily
    .venv/bin/python angel_export_history.py --symbols NIFTY BANKNIFTY
    .venv/bin/python angel_export_history.py --interval ONE_DAY --days 2000
"""
import argparse
import datetime as dt
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from angel_one_client import AngelOneManager  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "exports")

# Angel One index tokens (stable)
INDEX_TOKENS = {
    "NIFTY": ("99926000", "NSE"),
    "BANKNIFTY": ("99926009", "NSE"),
}

CHUNK_DAYS = 300  # Angel One caps rows/request; paginate in chunks


def fetch_all(manager, exchange, token, interval, days):
    """Paginate getCandleData backwards in CHUNK_DAYS windows and merge."""
    end = dt.datetime.now()
    start = end - dt.timedelta(days=days)
    frames = []
    window_end = end
    while window_end > start:
        window_start = window_end - dt.timedelta(days=CHUNK_DAYS)
        res = manager.get_candles(
            exchange, token, interval,
            window_start.strftime("%Y-%m-%d %H:%M"),
            window_end.strftime("%Y-%m-%d %H:%M"),
        )
        if res:
            df = pd.DataFrame(res, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            frames.append(df)
        window_end = window_start
    if not frames:
        return None
    out = pd.concat(frames).drop_duplicates("timestamp").sort_values("timestamp")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", default=["NIFTY", "BANKNIFTY"])
    ap.add_argument("--interval", default="ONE_DAY")
    ap.add_argument("--days", type=int, default=2000, help="how far back to pull")
    args = ap.parse_args()

    os.makedirs(DATA, exist_ok=True)
    manager = AngelOneManager()
    if not manager.login():
        print("LOGIN FAILED - check .env ANGEL_* creds")
        return 1

    for sym in args.symbols:
        if sym not in INDEX_TOKENS:
            print(f"skip {sym}: no index token mapping")
            continue
        token, exchange = INDEX_TOKENS[sym]
        df = fetch_all(manager, exchange, token, args.interval, args.days)
        if df is None or df.empty:
            print(f"{sym}: no data")
            continue
        out = os.path.join(DATA, f"{sym}_{args.interval.lower()}.csv")
        df.to_csv(out, index=False)
        print(f"{sym}: {len(df)} rows  {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}  -> {out}")

    manager.logout()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())