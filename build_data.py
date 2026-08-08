"""Build/refresh the full data cache in one run.

Fetches once, writes to data/, so analysis scripts never re-download.
Runs sequentially and skips anything that's already fresh today.

Usage:
    python build_data.py            # full refresh
    python build_data.py --fresh    # ignore age, force re-fetch
"""
import os
import sys
import datetime as dt
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _fresh(path, max_age_h=20):
    """True if file exists and is newer than max_age_h."""
    if not os.path.exists(path):
        return False
    age_h = (dt.datetime.now().timestamp() - os.path.getmtime(path)) / 3600
    return age_h < max_age_h


def _write(df, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)
    print(f"  wrote {os.path.relpath(path)} ({len(df)} rows)")


def build_nifty(fresh):
    p = os.path.join(DATA, "nifty_history.csv")
    if _fresh(p) and not fresh:
        print("nifty_history: fresh, skip")
        return
    from data_fetcher import fetch_index_history
    df = fetch_index_history("NIFTY 50", out_csv=p)
    _write(df, p)


def build_fiidii(fresh):
    p = os.path.join(DATA, "fii_dii_history.csv")
    if _fresh(p, 6) and not fresh:
        print("fii_dii_history: fresh, skip")
        return
    from institutional import fetch_fii_dii_history
    df = fetch_fii_dii_history(cache=False)
    _write(df, p)


def build_stocks(fresh):
    """Cache daily Yahoo history for all Nifty 50 symbols (used by stock_flow)."""
    os.makedirs(os.path.join(DATA, "stocks"), exist_ok=True)
    from stock_flow import NIFTY50
    from ml_engine import indicators_add
    import requests
    count = 0
    for sym, ticker in NIFTY50.items():
        p = os.path.join(DATA, "stocks", f"{sym}.csv")
        if _fresh(p) and not fresh:
            continue
        try:
            df = _yahoo_daily(ticker, 260)
            _write(df, p)
            count += 1
        except Exception as e:
            print(f"  {sym}: {e}")
    print(f"stocks: refreshed {count}")


def _yahoo_daily(ticker, days=260):
    import requests
    import pandas as pd
    p2 = int(dt.datetime.now().timestamp())
    p1 = int((dt.datetime.now() - dt.timedelta(days=days)).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?period1={p1}&period2={p2}&interval=1d&events=history")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    ts, q = res["timestamp"], res["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(ts):
        try:
            rows.append({"date": pd.to_datetime(t, unit="s").date(),
                         "open": q["open"][i], "high": q["high"][i],
                         "low": q["low"][i], "close": q["close"][i],
                         "volume": q["volume"][i] or 0})
        except (TypeError, IndexError):
            continue
    df = pd.DataFrame(rows).dropna(subset=["open", "high", "low", "close"])
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").drop_duplicates("date")


def build_vix(fresh):
    """Cache India VIX history (Yahoo ^INDIAVIX). Critical for premium regime."""
    p = os.path.join(DATA, "india_vix.csv")
    if _fresh(p, 20) and not fresh:
        print("india_vix: fresh, skip")
        return
    import requests
    import pandas as pd
    p2 = int(dt.datetime.now().timestamp())
    p1 = int((dt.datetime.now() - dt.timedelta(days=365)).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX"
           f"?period1={p1}&period2={p2}&interval=1d&events=history")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    ts, q = res["timestamp"], res["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(ts):
        try:
            rows.append({"date": pd.to_datetime(t, unit="s").date(),
                         "open": q["open"][i], "high": q["high"][i],
                         "low": q["low"][i], "close": q["close"][i]})
        except (TypeError, IndexError):
            continue
    df = pd.DataFrame(rows).dropna(subset=["close"])
    df["date"] = pd.to_datetime(df["date"])
    _write(df.sort_values("date"), p)


def build_oi_snapshot(fresh):
    """Capture today's live option chain (best-effort; skip if already saved)."""
    today = dt.date.today().isoformat()
    p = os.path.join(DATA, "oi_snapshots", f"NIFTY_{today}.csv")
    if os.path.exists(p) and not fresh:
        print(f"oi snapshot {today}: exists, skip")
        return
    try:
        from nse_live import fetch_option_chain_live, close
        chain, meta = fetch_option_chain_live("NIFTY")
        if not chain.empty:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            chain.to_csv(p, index=False)
            import oi_intel
            oi_intel.save_history_json(chain, "NIFTY", extra={"spot": meta.get("underlying")})
            print(f"  wrote oi snapshot {today} ({len(chain)} strikes)")
        close()
    except Exception as e:
        print(f"  oi snapshot skipped: {str(e)[:80]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="force re-fetch")
    ap.add_argument("--skip-oi", action="store_true", help="skip live NSE chain")
    args = ap.parse_args()
    print("=== build_data ===")
    build_nifty(args.fresh)
    build_vix(args.fresh)
    build_fiidii(args.fresh)
    build_stocks(args.fresh)
    if not args.skip_oi:
        build_oi_snapshot(args.fresh)
    print("done.")


if __name__ == "__main__":
    main()
