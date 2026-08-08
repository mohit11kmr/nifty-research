"""Stock flow intelligence - which companies are being bought, since when.

Detects persistent institutional accumulation in Nifty 50 names:
1. Trend health: price vs SMA20/50, SMA50 slope (uptrend since when)
2. Buying period: when did the stock first break above SMA50 this leg
3. Momentum: 1m/3m/6m returns, RSI, ADX trend strength
4. Volume confirmation: volume rising with price (accumulation) vs falling
5. Results awareness: date of last price spike (event-adjusted view)
Uses Yahoo Finance daily data (free, reliable fallback when NSE is blocked).
"""
import os
import time
import datetime as dt

import numpy as np
import pandas as pd
import requests

import indicators

YH = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"}

# Nifty 50 constituents -> Yahoo tickers
NIFTY50 = {
    "RELIANCE": "RELIANCE.NS", "HDFCBANK": "HDFCBANK.NS", "ICICIBANK": "ICICIBANK.NS",
    "INFY": "INFY.NS", "TCS": "TCS.NS", "SBIN": "SBIN.NS", "BHARTIARTL": "BHARTIARTL.NS",
    "ITC": "ITC.NS", "LT": "LT.NS", "AXISBANK": "AXISBANK.NS", "KOTAKBANK": "KOTAKBANK.NS",
    "HINDUNILVR": "HINDUNILVR.NS", "BAJFINANCE": "BAJFINANCE.NS", "TITAN": "TITAN.NS",
    "MARUTI": "MARUTI.NS", "SUNPHARMA": "SUNPHARMA.NS", "TATAMOTORS": "TMCV.NS",
    "WIPRO": "WIPRO.NS", "HCLTECH": "HCLTECH.NS", "NTPC": "NTPC.NS",
    "ADANIENT": "ADANIENT.NS", "ADANIPORTS": "ADANIPORTS.NS", "BAJAJFINSV": "BAJAJFINSV.NS",
    "ASIANPAINT": "ASIANPAINT.NS", "ULTRACEMCO": "ULTRACEMCO.NS", "NESTLEIND": "NESTLEIND.NS",
    "TATASTEEL": "TATASTEEL.NS", "POWERGRID": "POWERGRID.NS", "JSWSTEEL": "JSWSTEEL.NS",
    "M&M": "M%26M.NS", "HDFCLIFE": "HDFCLIFE.NS", "SBILIFE": "SBILIFE.NS",
    "DRREDDY": "DRREDDY.NS", "CIPLA": "CIPLA.NS", "TECHM": "TECHM.NS", "ONGC": "ONGC.NS",
    "COALINDIA": "COALINDIA.NS", "BPCL": "BPCL.NS", "TATACONSUM": "TATACONSUM.NS",
    "BRITANNIA": "BRITANNIA.NS", "EICHERMOT": "EICHERMOT.NS", "HEROMOTOCO": "HEROMOTOCO.NS",
    "BAJAJ-AUTO": "BAJAJ-AUTO.NS", "INDUSINDBK": "INDUSINDBK.NS", "DIVISLAB": "DIVISLAB.NS",
    "APOLLOHOSP": "APOLLOHOSP.NS", "GRASIM": "GRASIM.NS", "HINDALCO": "HINDALCO.NS",
    "DLF": "DLF.NS", "TRENT": "TRENT.NS", "SIEMENS": "SIEMENS.NS", "BEL": "BEL.NS",
    "HAL": "HAL.NS", "BHEL": "BHEL.NS", "RECLTD": "RECLTD.NS", "PFC": "PFC.NS",
    "JIOFIN": "JIOFIN.NS",
}

NIFTY50_NAMES = {
    "RELIANCE": "Reliance", "HDFCBANK": "HDFC Bank", "ICICIBANK": "ICICI Bank",
    "INFY": "Infosys", "TCS": "TCS", "SBIN": "SBI", "BHARTIARTL": "Bharti Airtel",
    "ITC": "ITC", "LT": "L&T", "AXISBANK": "Axis Bank", "KOTAKBANK": "Kotak Bank",
    "HINDUNILVR": "HUL", "BAJFINANCE": "Bajaj Finance", "TITAN": "Titan",
    "MARUTI": "Maruti", "SUNPHARMA": "Sun Pharma", "TATAMOTORS": "Tata Motors",
    "WIPRO": "Wipro", "HCLTECH": "HCL Tech", "NTPC": "NTPC", "ADANIENT": "Adani Ent",
    "ADANIPORTS": "Adani Ports", "BAJAJFINSV": "Bajaj Finserv", "ASIANPAINT": "Asian Paints",
    "ULTRACEMCO": "UltraTech", "NESTLEIND": "Nestle", "TATASTEEL": "Tata Steel",
    "POWERGRID": "PowerGrid", "JSWSTEEL": "JSW Steel", "M&M": "M&M", "HDFCLIFE": "HDFC Life",
    "SBILIFE": "SBI Life", "DRREDDY": "Dr Reddy", "CIPLA": "Cipla", "TECHM": "Tech Mahindra",
    "ONGC": "ONGC", "COALINDIA": "Coal India", "BPCL": "BPCL", "TATACONSUM": "Tata Consumer",
    "BRITANNIA": "Britannia", "EICHERMOT": "Eicher Motors", "HEROMOTOCO": "Hero Motocorp",
    "BAJAJ-AUTO": "Bajaj Auto", "INDUSINDBK": "IndusInd", "DIVISLAB": "Divi's",
    "APOLLOHOSP": "Apollo Hospitals", "GRASIM": "Grasim", "HINDALCO": "Hindalco",
    "DLF": "DLF", "TRENT": "Trent", "SIEMENS": "Siemens", "BEL": "BEL", "HAL": "HAL",
    "BHEL": "BHEL", "RECLTD": "REC Ltd", "PFC": "PFC", "JIOFIN": "Jio Financial",
}


STOCK_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "stocks")


def _yahoo_daily(ticker, days=260, use_cache=True):
    """Daily OHLCV - read from data/stocks cache first, fetch only if missing."""
    if use_cache and STOCK_CACHE:
        # symbol = ticker minus .NS, URL-unescape M%26M -> M&M
        from urllib.parse import unquote
        sym = unquote(ticker.replace(".NS", ""))
        p = os.path.join(STOCK_CACHE, f"{sym}.csv")
        if os.path.exists(p):
            age_h = (dt.datetime.now().timestamp() - os.path.getmtime(p)) / 3600
            if age_h < 30:
                df = pd.read_csv(p, parse_dates=["date"])
                return df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    p2 = int(dt.datetime.now().timestamp())
    p1 = int((dt.datetime.now() - dt.timedelta(days=days)).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?period1={p1}&period2={p2}&interval=1d&events=history")
    r = requests.get(url, headers=YH, timeout=20)
    r.raise_for_status()
    d = r.json()["chart"]["result"][0]
    ts = d["timestamp"]
    q = d["indicators"]["quote"][0]
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
    df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    if use_cache and STOCK_CACHE:
        try:
            from urllib.parse import unquote
            sym = unquote(ticker.replace(".NS", ""))
            os.makedirs(STOCK_CACHE, exist_ok=True)
            df.to_csv(os.path.join(STOCK_CACHE, f"{sym}.csv"), index=False)
        except Exception:
            pass
    return df


def _buying_since(df, sma50):
    """First date of the current leg above SMA50 (i.e., 'buying started when')."""
    above = df["close"] > sma50
    if not above.iloc[-1]:
        return None
    # find last position where it was below SMA50
    below_pos = df.index[~above]
    last_below = below_pos[-1] if len(below_pos) else None
    if last_below is None:
        return df.index[0]
    after = df.index[df.index > last_below]
    return after[0]


def analyze_stock(symbol, min_days=80):
    """Full flow analysis for one stock. Returns dict or None on failure."""
    ticker = NIFTY50.get(symbol, symbol + ".NS")
    df = _yahoo_daily(ticker)
    if len(df) < min_days:
        return None
    df = df.set_index("date")
    ind = indicators.add_all_indicators(df)

    close = ind["close"]
    last = ind.iloc[-1]
    sma20, sma50 = ind["sma20"], ind["sma50"]
    sma200 = ind["sma200"]

    r1m = (close.iloc[-1] / close.iloc[-22] - 1) * 100 if len(close) > 22 else None
    r3m = (close.iloc[-1] / close.iloc[-66] - 1) * 100 if len(close) > 66 else None
    r6m = (close.iloc[-1] / close.iloc[-132] - 1) * 100 if len(close) > 132 else None

    # SMA50 slope = trend persistence
    slope50 = (sma50.iloc[-1] / sma50.iloc[-21] - 1) * 100 if len(sma50) > 21 else None
    # Volume trend (last 10d avg vs prior 20d)
    v10 = ind["volume"].iloc[-10:].mean()
    v20 = ind["volume"].iloc[-30:-10].mean()
    vol_ratio = v10 / v20 if v20 else 1.0

    # 52w context
    hi52 = close.iloc[-252:].max()
    lo52 = close.iloc[-252:].min()
    off_high = (close.iloc[-1] / hi52 - 1) * 100 if hi52 else 0
    off_low = (close.iloc[-1] / lo52 - 1) * 100 if lo52 else 0

    adx = last.get("adx", 0)
    rsi = last.get("rsi14", 50)
    atr = last.get("atr14", 0)
    atr_pct = (atr / close.iloc[-1] * 100) if close.iloc[-1] else 0

    since = _buying_since(ind, sma50)

    score = 0
    notes = []
    if close.iloc[-1] > sma20.iloc[-1] > sma50.iloc[-1]:
        score += 2
        notes.append("price>SMA20>SMA50 (stacked bullish)")
    elif close.iloc[-1] > sma50.iloc[-1]:
        score += 1
        notes.append("above SMA50")
    else:
        score -= 2
        notes.append("below SMA50")

    if slope50 and slope50 > 0.5:
        score += 1
        notes.append(f"SMA50 rising (+{slope50:.1f}%/mo)")
    elif slope50 and slope50 < -0.5:
        score -= 1
        notes.append(f"SMA50 falling ({slope50:+.1f}%/mo)")

    if vol_ratio and vol_ratio > 1.4:
        score += 1
        notes.append(f"volume {vol_ratio:.1f}x normal (accumulation)")
    if r1m and r1m > 3:
        score += 1
        notes.append(f"+{r1m:.1f}% in 1 month")
    if r3m and r3m > 8:
        score += 1
        notes.append(f"+{r3m:.1f}% in 3 months")
    if adx and adx >= 25:
        score += 1
        notes.append(f"ADX {adx:.0f} (strong trend)")
    if rsi and 55 <= rsi <= 70:
        score += 1
        notes.append(f"RSI {rsi:.0f} (bullish, not overbought)")

    # price near 52w high with strength = leadership
    if off_high and off_high > -8:
        score += 1
        notes.append(f"{off_high:.0f}% off 52w high")

    return {
        "symbol": symbol,
        "name": NIFTY50_NAMES.get(symbol, symbol),
        "close": round(float(close.iloc[-1]), 2),
        "score": score,
        "r1m_pct": round(r1m, 1) if r1m is not None else None,
        "r3m_pct": round(r3m, 1) if r3m is not None else None,
        "r6m_pct": round(r6m, 1) if r6m is not None else None,
        "rsi": round(rsi, 0) if rsi == rsi else None,
        "adx": round(adx, 0) if adx == adx else None,
        "sma50_slope_pct": round(slope50, 2) if slope50 is not None else None,
        "vol_ratio": round(vol_ratio, 2) if vol_ratio == vol_ratio else None,
        "buying_since": since.strftime("%d %b %Y") if since is not None else None,
        "off_52w_high_pct": round(off_high, 1) if off_high == off_high else None,
        "off_52w_low_pct": round(off_low, 1) if off_low == off_low else None,
        "atr_pct": round(atr_pct, 2) if atr_pct == atr_pct else None,
        "notes": notes,
    }


def scan_universe(symbols=None, top=15, throttle=0.25):
    """Scan all Nifty 50 names, return flow report sorted by score."""
    symbols = symbols or list(NIFTY50.keys())
    results = []
    for i, sym in enumerate(symbols):
        try:
            r = analyze_stock(sym)
            if r:
                results.append(r)
        except Exception:
            pass
        time.sleep(throttle)
        if (i + 1) % 15 == 0:
            time.sleep(1.0)
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top], results


def format_flow(results, top=None):
    """Trader-readable flow lines."""
    lines = []
    for r in results:
        badge = "BUY" if r["score"] >= 3 else ("WATCH" if r["score"] >= 1 else "AVOID")
        lines.append(
            f"{badge:5s} {r['symbol']:10s} {r['name']:<22s} score={r['score']:+d} "
            f"1m {r['r1m_pct']:+.1f}% 3m {r['r3m_pct']:+.1f}% "
            f"{'since ' + r['buying_since'] if r['buying_since'] else 'below SMA50'} "
            f"| {' '.join(r['notes'][:2])}")
    return lines


if __name__ == "__main__":
    top, all_ = scan_universe(top=12)
    for line in format_flow(top):
        print(line)
