"""NSE data fetcher - index history + option chain (free, official NSE endpoints)."""
import json
import time
import datetime as dt
import requests
import pandas as pd

NSE_BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
    "Referer": "https://www.nseindia.com/",
}


def _new_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    # First hit homepage so NSE issues its cookies (needed for API access)
    s.get(NSE_BASE, timeout=20)
    time.sleep(0.6)
    return s


def _get_json(session, url, retries=4):
    for i in range(retries):
        try:
            r = session.get(url, timeout=25)
            if r.status_code == 200 and "json" in r.headers.get("Content-Type", ""):
                return r.json()
            time.sleep(1.2 * (i + 1))
        except requests.RequestException:
            time.sleep(1.5 * (i + 1))
    raise ConnectionError(f"Failed to fetch {url}")


def _fetch_yahoo(symbol, start, end):
    """Fallback: Yahoo Finance daily OHLCV (^NSEI / ^NSEBANK / etc)."""
    sym_map = {
        "NIFTY 50": "^NSEI",
        "NIFTY BANK": "^NSEBANK",
        "BANKNIFTY": "^NSEBANK",
        "NIFTY": "^NSEI",
    }
    ticker = sym_map.get(str(symbol).strip().upper(), str(symbol).strip().upper())
    p1 = int(dt.datetime.combine(start, dt.time()) .timestamp())
    p2 = int(dt.datetime.combine(end, dt.time()).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?period1={p1}&period2={p2}&interval=1d&events=history")
    h = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
        "Accept": "application/json",
    }
    r = requests.get(url, headers=h, timeout=25)
    r.raise_for_status()
    data = r.json()
    res = data.get("chart", {}).get("result")
    if not res:
        raise ConnectionError(f"Yahoo returned no data for {ticker}")
    res = res[0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(ts):
        try:
            rows.append({
                "date": pd.to_datetime(t, unit="s").date(),
                "open": q["open"][i], "high": q["high"][i],
                "low": q["low"][i], "close": q["close"][i],
                "volume": q["volume"][i] or 0,
            })
        except (TypeError, IndexError):
            continue
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    return df


def fetch_index_history(symbol="NIFTY 50", start=None, end=None, out_csv=None):
    """Fetch daily OHLCV history for an index from NSE.

    symbol examples: 'NIFTY 50', 'NIFTY BANK', 'NIFTY FIN SERVICE'
    """
    if start is None:
        start = dt.date.today() - dt.timedelta(days=730)
    if end is None:
        end = dt.date.today()

    idx_map = {
        "NIFTY 50": "NIFTY 50",
        "NIFTY BANK": "NIFTY BANK",
        "BANKNIFTY": "NIFTY BANK",
        "NIFTY FIN SERVICE": "NIFTY FIN SERVICE",
        "NIFTY IT": "NIFTY IT",
        "NIFTY MIDCAP 100": "NIFTY MIDCAP 100",
        "NIFTY SMLCAP 100": "NIFTY SMLCAP 100",
        "NIFTY AUTO": "NIFTY AUTO",
        "NIFTY PHARMA": "NIFTY PHARMA",
        "NIFTY METAL": "NIFTY METAL",
        "NIFTY ENERGY": "NIFTY ENERGY",
        "NIFTY FMCG": "NIFTY FMCG",
        "NIFTY REALTY": "NIFTY REALTY",
    }
    idx = idx_map.get(str(symbol).strip().upper(), str(symbol).strip().upper())

    try:
        s = _new_session()
        from urllib.parse import quote
        url = (f"{NSE_BASE}/api/historical/indicesHistory?indexType={quote(idx)}"
               f"&from={start:%d-%m-%Y}&to={end:%d-%m-%Y}")
        data = _get_json(s, url)
        records = []
        for row in data.get("data", []):
            rec = row.get("INDEX", {})
            records.append({
                "date": rec.get("TIMESTAMP"),
                "open": rec.get("OPEN"),
                "high": rec.get("HIGH"),
                "low": rec.get("LOW"),
                "close": rec.get("CLOSE"),
                "volume": rec.get("TOTAL_TRADED_QUANTITY"),
            })
        df = pd.DataFrame(records)
        if df.empty:
            raise ConnectionError("NSE returned empty payload")
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        print("DataSource: NSE official API")
    except Exception as e:  # noqa: BLE001
        print(f"NSE blocked ({e}). Falling back to Yahoo Finance...")
        df = _fetch_yahoo(symbol, start, end)
        print("DataSource: Yahoo Finance")
    if out_csv and not df.empty:
        df.to_csv(out_csv, index=False)
    return df


def fetch_option_chain(symbol="NIFTY", expiry=None, out_json=None):
    """Fetch live option chain for an index (CE/PE, OI, IV per strike)."""
    sym = str(symbol).strip().upper()
    s = _new_session()
    url = f"{NSE_BASE}/api/option-chain-indices?symbol={sym}"
    data = _get_json(s, url)

    records = []
    for item in data.get("records", {}).get("data", []):
        expiry_date = item.get("expiryDate")
        if expiry and expiry_date != expiry:
            continue
        strike = item.get("strikePrice")
        ce = item.get("CE") or {}
        pe = item.get("PE") or {}
        records.append({
            "expiry": expiry_date,
            "strike": strike,
            "ce_oi": ce.get("openInterest"),
            "ce_oi_chg": ce.get("changeinOpenInterest"),
            "ce_volume": ce.get("totalTradedVolume"),
            "ce_iv": ce.get("impliedVolatility"),
            "ce_ltp": ce.get("lastPrice"),
            "pe_oi": pe.get("openInterest"),
            "pe_oi_chg": pe.get("changeinOpenInterest"),
            "pe_volume": pe.get("totalTradedVolume"),
            "pe_iv": pe.get("impliedVolatility"),
            "pe_ltp": pe.get("lastPrice"),
        })
    df = pd.DataFrame(records)
    if df.empty:
        return df
    for c in df.columns:
        if c != "expiry":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values("strike").reset_index(drop=True)
    if out_json:
        df.to_json(out_json, orient="records", indent=2)
    return df


def compute_chain_metrics(chain):
    """Compute OI-concentration, PCR and max-pain from an option chain."""
    if chain.empty:
        return None
    atm = chain.loc[(chain["ce_oi"].fillna(0) + chain["pe_oi"].fillna(0)).idxmax(), "strike"]

    pe_oi_total = chain["pe_oi"].fillna(0).sum()
    ce_oi_total = chain["ce_oi"].fillna(0).sum()
    pcr = pe_oi_total / ce_oi_total if ce_oi_total else 0.0

    # Max pain on liquid ATM band (spot ±8%) to avoid far-OTM OI distortion
    band = chain[chain["strike"].between(atm * 0.92, atm * 1.08)]
    if band.empty:
        band = chain
    max_pain = None
    best = None
    for _, row in band.iterrows():
        payout = 0.0
        # Calls pay max(0, S - K), puts pay max(0, K - S); max pain = strike
        # with the LEAST total payout to buyers (argmin), not the most.
        for strike, oi in zip(band["strike"], band["ce_oi"].fillna(0)):
            payout += max(0.0, row["strike"] - strike) * oi
        for strike, oi in zip(band["strike"], band["pe_oi"].fillna(0)):
            payout += max(0.0, strike - row["strike"]) * oi
        if best is None or payout < best:
            best = payout
            max_pain = row["strike"]

    top_oi = chain.sort_values("ce_oi", ascending=False).head(5)
    resistance = top_oi["strike"].tolist()
    top_put_oi = chain.sort_values("pe_oi", ascending=False).head(5)
    support = top_put_oi["strike"].tolist()

    return {
        "atm": atm,
        "pcr": round(pcr, 3),
        "max_pain": max_pain,
        "support_oi": support,
        "resistance_oi": resistance,
    }
