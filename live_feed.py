"""Live NSE tick-by-tick via official streamer WebSocket (free, no broker).

Endpoint (verified 2026-08): wss://streamer.nseindia.com/streams/fo/mbp
NSE's own option-chain page uses exactly this WebSocket
(dist/js/sections/option-chainstream.js). Payload per message is one
strike's CE/PE quote: lastPrice, buy/sell price + qty, change, OI.

Only runs during market hours - NSE pushes nothing when the market is
closed (socket connects, no messages). For a full-chain snapshot when the
market is closed use nse_live.fetch_option_chain_live (browser).
"""
import json
import time
import datetime as dt

import websocket

STREAM_BASE = "wss://streamer.nseindia.com/streams/fo/mbp"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

# value -> key maps used by NSE's own UI (drop-down orders)
_SYMBOL = "NIFTY"


def stream_quotes(symbol="NIFTY", expiry=None, on_tick=None, max_seconds=120):
    """Connect to NSE streamer and yield option quotes as dicts.

    symbol: NIFTY / BANKNIFTY / FINNIFTY / equity F&O symbol.
    expiry: expiry date string '11-Aug-2026'. None -> resolve current week.
    on_tick: callback(quote_dict). If None, prints compactly.
    Yields nothing itself; blocks until max_seconds or error.
    """
    if expiry is None:
        expiry = _current_expiry(symbol)
    url = f"{STREAM_BASE}?symbol={symbol}&expiry={expiry}"
    cookies = _cookies()
    conn = websocket.create_connection(
        url, timeout=10, origin="https://www.nseindia.com",
        cookie=cookies,
        header=[f"User-Agent: {UA}"])
    try:
        conn.settimeout(5)
        end = time.time() + max_seconds
        count = 0
        while time.time() < end:
            try:
                raw = conn.recv()
            except websocket.WebSocketTimeoutException:
                continue  # no tick this window (market closed / slow)
            except websocket.WebSocketConnectionClosedException:
                print("  (connection closed by NSE - market closed?)")
                break
            if not raw:
                continue
            try:
                q = json.loads(raw)
            except Exception:
                continue
            if on_tick:
                on_tick(q)
            else:
                _print_tick(q)
            count += 1
            if count % 500 == 0:
                print(f"  ...{count} ticks")
        return count
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _print_tick(q):
    sp = q.get("strikePrice")
    ts = q.get("timestamp", "")
    ce = q.get("CE") or {}
    pe = q.get("PE") or {}
    if not sp:
        return
    line = f"[{ts}] {sp} "
    if ce:
        line += f"CE ltp={ce.get('lastPrice')} b={ce.get('buyPrice1')} a={ce.get('sellPrice1')} oi={ce.get('openInterest')}"
    if pe:
        line += f" PE ltp={pe.get('lastPrice')} b={pe.get('buyPrice1')} a={pe.get('sellPrice1')} oi={pe.get('openInterest')}"
    print(line)


def _current_expiry(symbol="NIFTY"):
    """Resolve current week expiry from NSE contract-info API (cheap REST)."""
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = UA
    try:
        s.get("https://www.nseindia.com", timeout=15)
        r = s.get(
            f"https://www.nseindia.com/api/option-chain-contract-info?symbol={symbol}",
            timeout=20)
        data = r.json()
        exp = (data.get("expiryDates") or [None])[0]
        return exp
    except Exception:
        return None


def _cookies():
    """Get NSE cookies via a normal HTTP session (some deployments need them)."""
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = UA
    try:
        s.get("https://www.nseindia.com", timeout=15)
        return "; ".join(f"{c.name}={c.value}" for c in s.cookies)
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "NIFTY"
    secs = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    print(f"connecting streamer: {sym} for {secs}s ...")
    n = stream_quotes(symbol=sym, max_seconds=secs)
    print(f"done: {n} messages (market closed -> 0 is normal outside 09:15-15:30)")
