"""Live research DB recorder - accumulates NIFTY ticks + spot into data/research.db.

Runs during market hours (09:15-15:30 IST). Appends every streamer quote to a
SQLite table and samples the index spot every 60s (Yahoo ^NSEI - NSE quote API
is blocked to plain requests). Run it every market day so the research dataset
grows over time: OI build-up, IV skew, bid-ask spread, intraday volume.

Usage:
    python tick_recorder.py [NIFTY] [--seconds N]     # run N seconds (test)
    python tick_recorder.py [NIFTY]                   # until market close / Ctrl+C
"""
import argparse
import datetime as dt
import json
import os
import sqlite3
import time

import requests
import websocket

from live_feed import _current_expiry, _cookies, STREAM_BASE, UA

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "research.db")
SPOT_SAMPLE_SEC = 60
BATCH_SIZE = 200

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ticks (
    recv_ts TEXT, exch_ts TEXT, symbol TEXT, expiry TEXT, strike REAL,
    side TEXT, ltp REAL, bid REAL, bid_qty REAL, ask REAL, ask_qty REAL,
    oi REAL, oi_chg REAL, iv REAL, volume REAL, pct_chg REAL
);
CREATE INDEX IF NOT EXISTS idx_ticks_key ON ticks(symbol, side, strike, recv_ts);
CREATE TABLE IF NOT EXISTS spot (
    recv_ts TEXT, value REAL, pct_chg REAL
);
CREATE INDEX IF NOT EXISTS idx_spot_ts ON spot(recv_ts);
"""


def _connect(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(_SCHEMA)
    con.commit()
    return con


def _prev_close():
    """Last cached NIFTY daily close (for spot % change)."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nifty_history.csv")
    try:
        import pandas as pd
        df = pd.read_csv(p)
        return float(df["close"].iloc[-1])
    except Exception:
        return None


def _fetch_spot(prev_close):
    """Live index value from Yahoo ^NSEI 1m (near real-time, works without browser)."""
    p2 = int(time.time())
    p1 = p2 - 7200
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI"
           f"?period1={p1}&period2={p2}&interval=1m")
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
    if not closes:
        return None, None
    val = float(closes[-1])
    pct = ((val / prev_close) - 1) * 100 if prev_close else None
    return val, pct


def _parse_tick(q, symbol, expiry):
    """One streamer message -> 1-2 DB rows (CE and/or PE present in message)."""
    strike = q.get("strikePrice")
    ts = q.get("timestamp", "")
    if strike is None:
        return []
    rows = []
    for side in ("CE", "PE"):
        d = q.get(side) or {}
        if not d:
            continue
        rows.append((
            dt.datetime.now().isoformat(timespec="seconds"), ts, symbol,
            expiry, strike, side,
            d.get("lastPrice"), d.get("buyPrice1"), d.get("buyQty1"),
            d.get("sellPrice1"), d.get("sellQty1"), d.get("openInterest"),
            d.get("changeinOpenInterest"), d.get("impliedVolatility"),
            d.get("totalTradedVolume"), d.get("pchangeinOpenInterest"),
        ))
    return rows


def _market_close_delay():
    """Seconds until 15:30 IST (daily square-off). Negative/zero -> market closed."""
    now = dt.datetime.now()
    close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    if now >= close:
        return 0
    return int((close - now).total_seconds())


def run(symbol="NIFTY", max_seconds=None):
    expiry = _current_expiry(symbol)
    if not expiry:
        expiry = "expiry"
    print(f"recorder: {symbol} ({expiry}) -> {DB_PATH}")
    con = _connect(DB_PATH)
    prev_close = _prev_close()
    batch = []
    total = 0
    last_spot = 0.0
    last_commit = 0.0
    start = time.time()
    deadline = None
    if max_seconds:
        deadline = time.time() + max_seconds
    elif _market_close_delay() > 0:
        deadline = time.time() + _market_close_delay()

    if deadline:
        left = int(deadline - time.time())
        print(f"  recording until {dt.datetime.fromtimestamp(deadline):%H:%M:%S} IST"
              f" ({left // 60}min {left % 60}s left)")
    else:
        print("  outside market window - will record until stream stops or Ctrl+C")

    conn = None
    while True:
        if deadline and time.time() >= deadline:
            print("  deadline reached - stopping")
            break
        try:
            conn = websocket.create_connection(
                f"{STREAM_BASE}?symbol={symbol}&expiry={expiry}", timeout=10,
                origin="https://www.nseindia.com", cookie=_cookies(),
                header=[f"User-Agent: {UA}"])
            conn.settimeout(5)
        except Exception as e:
            print(f"  connect fail: {e}; retry in 5s")
            time.sleep(5)
            continue

        while True:
            if deadline and time.time() >= deadline:
                break
            now = time.time()
            # spot sampling
            if now - last_spot >= SPOT_SAMPLE_SEC:
                try:
                    val, pct = _fetch_spot(prev_close)
                    if val is not None:
                        con.execute("INSERT INTO spot (recv_ts, value, pct_chg) VALUES (?,?,?)",
                                    (dt.datetime.now().isoformat(timespec="seconds"), val, pct))
                        print(f"  spot {val:,.1f} ({pct:+.2f}%)")
                        last_spot = now
                except Exception as e:
                    print(f"  spot fail: {str(e)[:50]}")
                last_spot = now

            try:
                raw = conn.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except websocket.WebSocketConnectionClosedException:
                print("  connection closed by NSE - reconnecting")
                break
            except Exception as e:
                print(f"  recv error: {str(e)[:50]} - reconnecting")
                break
            if not raw:
                continue
            try:
                q = json.loads(raw)
            except Exception:
                continue
            rows = _parse_tick(q, symbol, expiry)
            if rows:
                batch.extend(rows)
                total += len(rows)
            if len(batch) >= BATCH_SIZE or now - last_commit >= 5:
                if batch:
                    con.executemany(
                        "INSERT INTO ticks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                    con.commit()
                    batch = []
                    last_commit = now
                if total and now - last_spot < SPOT_SAMPLE_SEC:
                    elapsed = int(now - start)
                    print(f"  ...{total} tick-rows in {elapsed}s")
        try:
            conn.close()
        except Exception:
            pass
        if deadline and time.time() >= deadline:
            break
        time.sleep(2)

    if batch:
        con.executemany("INSERT INTO ticks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
        con.commit()
    t = con.execute("SELECT COUNT(*) FROM ticks").fetchone()[0]
    s = con.execute("SELECT COUNT(*) FROM spot").fetchone()[0]
    print(f"done. ticks={t:,} spot={s:,} | this run +{total:,}")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="NIFTY")
    ap.add_argument("--seconds", type=int, default=0)
    args = ap.parse_args()
    run(symbol=args.symbol, max_seconds=args.seconds or None)
