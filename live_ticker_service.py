"""Real-Time 5-Second Market Streaming Service for NIFTY Research.

Streams live Nifty 50 spot, Bank Nifty, and VIX ticks every 5 seconds,
automatically logging to history_logger and updating web_dashboard.

Truth-layer (Phase 3): never fabricates a spot/VIX value. When the live
feed fails the last real recorded spot is returned as a CACHED_TICK
explicitly tagged FALLBACK; if no real value exists the quote is
UNAVAILABLE (spot=None) and the stream stands down instead of logging
invented prices.
"""
import os
import sys
import time
import json
import datetime as dt
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(__file__))

import history_logger
import web_dashboard
import truth


def _last_recorded_spot():
    """Last real spot from research.db (never a hardcoded value)."""
    try:
        import sqlite3
        db = os.path.join("data", "research.db")
        if os.path.exists(db):
            con = sqlite3.connect(db)
            row = con.execute(
                "SELECT value, recv_ts FROM spot ORDER BY recv_ts DESC LIMIT 1").fetchone()
            con.close()
            if row and row[0]:
                return {"spot": float(row[0]), "recv_ts": row[1]}
    except Exception:
        pass
    return None


def fetch_live_quote():
    """Fetch live quote from yfinance; honest fallback chain, no literals."""
    live_spot = None
    live_vix = None
    try:
        nifty = yf.Ticker("^NSEI").history(period="1d", interval="1m")
        if not nifty.empty:
            live_spot = float(nifty["Close"].iloc[-1])
    except Exception as e:
        print(f"[Live Ticker Handled Gracefully] {e}")

    try:
        vix_ticker = yf.Ticker("^INDIAVIX")
        if vix_ticker is not None:
            vix_df = vix_ticker.history(period="1d", interval="1m")
            if not vix_df.empty:
                live_vix = float(vix_df["Close"].iloc[-1])
    except Exception as e:
        print(f"[Live VIX Handled Gracefully] {e}")

    if live_spot is not None:
        return truth.envelope(
            {
                "status": "LIVE_TICK_STREAMING",
                "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
                "spot": round(live_spot, 2),
                "vix": round(live_vix, 2) if live_vix is not None else None,
            },
            status=truth.REAL,
            source="yahoo:^NSEI,^INDIAVIX",
            evaluation_method="live_fetch",
        )

    cached = _last_recorded_spot()
    if cached is not None:
        return truth.envelope(
            {
                "status": "CACHED_TICK",
                "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
                "spot": round(cached["spot"], 2),
                "vix": None,
                "data_timestamp": cached["recv_ts"],
            },
            status=truth.FALLBACK,
            source="research.db:spot",
            fallback_used=True,
            fallback_reason=truth.MISSING,
            evaluation_method="last_recorded",
        )

    return truth.envelope(
        {
            "status": "UNAVAILABLE",
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
            "spot": None,
            "vix": None,
        },
        status=truth.MISSING,
        source=None,
        fallback_used=False,
        fallback_reason=truth.MISSING,
        evaluation_method="none",
    )


def stream_live_market_ticks(interval_sec=5, max_ticks=10):
    """Stream live market ticks every N seconds."""
    print("==================================================================")
    print("⚡ REAL-TIME 5-SECOND MARKET TICK STREAMING SERVICE")
    print(f"Time: {dt.datetime.now().strftime('%d %b %Y | %H:%M:%S IST')}")
    print("==================================================================")

    for i in range(1, max_ticks + 1):
        tick = fetch_live_quote()
        spot = tick["spot"]
        vix = tick["vix"]
        ts = tick["timestamp"]

        if spot is None:
            print(f" ⚠️ [Tick #{i}/{max_ticks}] No live or recorded spot available "
                  f"- standing down (no fabricated price).")
            if i < max_ticks:
                time.sleep(interval_sec)
            continue

        # 1. Log permanently to SQLite DB & CSV (with P-05 provenance)
        history_logger.log_market_tick(
            spot_price=spot,
            vix=vix,
            provenance={
                "status": tick.get("status"),
                "source": tick.get("source"),
                "data_timestamp": tick.get("data_timestamp"),
                "fallback_used": tick.get("fallback_used"),
                "fallback_reason": tick.get("fallback_reason"),
                "evaluation_method": tick.get("evaluation_method"),
            },
        )

        # 2. Update Live Web Terminal
        web_dashboard.generate_live_terminal_html()

        tag = f"({tick.get('status')})" if tick.get("status") in (truth.FALLBACK, truth.STALE) else ""
        print(f" 📡 [Tick #{i}/{max_ticks}] NIFTY SPOT: ₹{spot:,.2f} | VIX: {vix} {tag} @ {ts}")
        if i < max_ticks:
            time.sleep(interval_sec)

    print("==================================================================")
    print("✅ LIVE TICK STREAMING COMPLETED & SYNCED TO WEB TERMINAL!")
    print("==================================================================")


if __name__ == "__main__":
    stream_live_market_ticks(interval_sec=2, max_ticks=3)
