"""Global market data - USDINR, US indices, DXY, commodities, FII/DII.

Sources: Yahoo Finance (free) for global prices, NSE API attempt for FII/DII.
"""
import datetime as dt
import json
import time
import requests
import pandas as pd

YAHOO_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

GLOBAL_TICKERS = {
    "S&P 500": "^GSPC",
    "Dow Jones": "^DJI",
    "Nasdaq": "^IXIC",
    "Dollar Index": "DX-Y.NYB",
    "Gold": "GC=F",
    "Silver": "SI=F",
    "Crude Oil": "CL=F",
    "Bitcoin": "BTC-USD",
    "USDINR": "INR=X",
    "Nikkei": "^N225",
    "SGX Nifty": "^NSEI",  # proxy for SGX-ish global Nifty read
}


def fetch_yahoo_series(ticker, days=90):
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    p1 = int(dt.datetime.combine(start, dt.time()).timestamp())
    p2 = int(dt.datetime.combine(end, dt.time()).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?period1={p1}&period2={p2}&interval=1d")
    r = requests.get(url, headers=YAHOO_HEADERS, timeout=25)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(ts):
        try:
            rows.append({
                "date": pd.to_datetime(t, unit="s").date(),
                "close": q["close"][i],
                "prev_close": q["close"][i - 1] if i > 0 else q["close"][i],
            })
        except (TypeError, IndexError):
            continue
    df = pd.DataFrame(rows).dropna(subset=["close"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_global_snapshot(days=90, cache_dir="data"):
    """Fetch daily closes for all global tickers. Returns {name: last_close, change_pct}."""
    import os
    os.makedirs(cache_dir, exist_ok=True)
    out = {}
    for name, ticker in GLOBAL_TICKERS.items():
        try:
            df = fetch_yahoo_series(ticker, days)
            if df.empty:
                continue
            last = df["close"].iloc[-1]
            prev = df["close"].iloc[-2] if len(df) > 1 else last
            chg = (last / prev - 1) * 100 if prev else 0.0
            out[name] = {"ticker": ticker, "close": round(float(last), 2),
                         "change_pct": round(float(chg), 2)}
        except Exception as e:  # noqa: BLE001
            out[name] = {"ticker": ticker, "close": None, "change_pct": None, "error": str(e)[:60]}
        time.sleep(0.4)
    return out


def fetch_fii_dii():
    """FII/DII net activity. NSE API first, degrade gracefully."""
    try:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
            "Referer": "https://www.nseindia.com/",
        })
        s.get("https://www.nseindia.com", timeout=20)
        time.sleep(0.8)
        r = s.post("https://www.nseindia.com/api/fiidii",
                   json={"name": "FIIDII", "fromDate": "01-Jan-2026",
                         "toDate": dt.date.today().strftime("%d-%b-%Y")}, timeout=25)
        if r.status_code == 200:
            data = r.json()
            rows = data.get("data", [])
            if rows:
                last = rows[-1]
                return {
                    "date": last.get("date"),
                    "fii_equity_cash": _to_float(last.get("FII Equity Cash")),
                    "dii_equity_cash": _to_float(last.get("DII Equity Cash")),
                    "fii_future_index": _to_float(last.get("FII Index Futures")),
                    "fii_stock_futures": _to_float(last.get("FII Stock Futures")),
                }
    except Exception as e:  # noqa: BLE001
        return {"error": f"NSE FII/DII blocked: {str(e)[:80]}"}
    return {"error": "FII/DII unavailable"}


def _to_float(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def format_global_snapshot(snap):
    lines = []
    for name, d in snap.items():
        if d.get("close") is None:
            lines.append(f"- {name}: N/A")
            continue
        lines.append(f"- {name}: {d['close']:,.2f} ({d['change_pct']:+.2f}%)")
    return "\n".join(lines)
