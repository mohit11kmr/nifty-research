"""Live Real-Time Market Price Fetcher & DB Sync Engine for NIFTY Research.

Fetches live intraday 1-minute ticks from market and updates:
1. Live Spot Price & Intraday Candles
2. SQLite DB research.db
3. Capital Guard & Signal Pipelines
"""
import os
import sys
import json
import datetime as dt
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(__file__))


def fetch_live_market_spot():
    """Fetch live real-time Nifty 50 spot price.

    Returns spot=None with status UNAVAILABLE on any failure - never a
    fabricated price. Callers must treat None as no-live-data and stand down.
    """
    try:
        ticker = yf.Ticker("^NSEI")
        df = ticker.history(period="1d", interval="1m")
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            spot = float(latest["Close"])
            high = float(latest["High"])
            low = float(latest["Low"])
            open_p = float(latest["Open"])
            time_str = df.index[-1].strftime("%Y-%m-%d %H:%M:%S IST")
            return {
                "status": "LIVE_MARKET_TICK",
                "timestamp": time_str,
                "spot": round(spot, 2),
                "open": round(open_p, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "is_live": True
            }
    except Exception as e:
        print(f"[Live Fetch Handled Gracefully] {e}")

    return {
        "status": "UNAVAILABLE",
        "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "spot": None,
        "open": None,
        "high": None,
        "low": None,
        "is_live": False
    }


def _last_real_spot():
    """Last real spot from the live_dash DB (never a hardcoded value)."""
    try:
        import sqlite3
        db = os.path.join("data", "research.db")
        if os.path.exists(db):
            con = sqlite3.connect(db)
            row = con.execute(
                "SELECT value, recv_ts FROM spot ORDER BY recv_ts DESC LIMIT 1").fetchone()
            con.close()
            if row and row[0]:
                return {"spot": float(row[0]), "recv_ts": row[1], "is_live": False}
    except Exception:
        pass
    return None


def update_live_market_cache():
    """Sync live market spot price into nifty_history.csv cache.

    Only writes rows/logs when a real live (or last-recorded real) spot is
    available. Never fabricates a price.
    """
    live = fetch_live_market_spot()
    if not isinstance(live, dict) or not live.get("spot"):
        live = _last_real_spot() or {"status": "UNAVAILABLE", "spot": None,
                                     "open": None, "high": None, "low": None, "is_live": False}

    spot = live.get("spot")
    if spot is None:
        print("⚠️ [Live Market Fetch] No live or cached spot available - standing down (no fabricated price).")
        return live

    p = os.path.join("data", "nifty_history.csv")
    os.makedirs("data", exist_ok=True)

    if os.path.exists(p):
        try:
            df = pd.read_csv(p)
            today_str = dt.datetime.now().strftime("%Y-%m-%d")

            if not df.empty and df["date"].iloc[-1] == today_str:
                df.loc[df.index[-1], "close"] = spot
                df.loc[df.index[-1], "high"] = max(df.loc[df.index[-1], "high"], live.get("high", spot))
                df.loc[df.index[-1], "low"] = min(df.loc[df.index[-1], "low"], live.get("low", spot))
            else:
                new_row = {
                    "date": today_str,
                    "close": spot,
                    "open": live.get("open", spot),
                    "high": live.get("high", spot),
                    "low": live.get("low", spot),
                    "volume": 0
                }
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

            df.to_csv(p, index=False)
            print(f"✅ [Live Market Fetch] Updated {p} with LIVE SPOT: ₹{spot:,.2f}")
        except Exception as e:
            print(f"⚠️ [Live Market Fetch File Sync Warning] {e}")

        # Permanently log tick to historical audit database for backtesting
        try:
            import history_logger
            history_logger.log_market_tick(spot)
        except Exception as e:
            print(f"⚠️ [History Logger Sync Warning] {e}")

    return live


if __name__ == "__main__":
    print("=== LIVE REAL-TIME MARKET FETCH TEST ===")
    res = update_live_market_cache()
    print(json.dumps(res, indent=2))
