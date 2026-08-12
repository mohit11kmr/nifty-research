"""Historical Record & Trade Journal Logger for NIFTY Research.

Maintains permanent append-only audit trail for:
1. Live Market Price Ticks (data/tick_history.csv & data/historical_audit.db)
2. Historical Signal Log & Accuracy Tracker (data/signal_history.csv)
3. Paper Trade Journal & Equity Curve Log (data/paper_trade_journal.csv)
"""
import os
import sys
import sqlite3
import json
import datetime as dt
import pandas as pd

DB_FILE = os.path.join("data", "historical_audit.db")
TICK_CSV = os.path.join("data", "tick_history.csv")
SIGNAL_CSV = os.path.join("data", "signal_history.csv")
JOURNAL_CSV = os.path.join("data", "paper_trade_journal.csv")


def _init_sqlite_db():
    """Initialize SQLite database for append-only historical logging."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # Table 1: Ticks
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tick_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        spot_price REAL,
        vix REAL,
        pcr REAL,
        max_pain REAL
    )
    """)

    # Table 2: Signal History
    cur.execute("""
    CREATE TABLE IF NOT EXISTS signal_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        action TEXT,
        grade TEXT,
        confluence_score TEXT,
        spot_price REAL,
        recommended_strike REAL,
        sl_points REAL,
        target_points REAL
    )
    """)

    # Table 3: Paper Trade Journal
    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper_trade_journal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        position_id TEXT,
        side TEXT,
        option_type TEXT,
        strike REAL,
        entry_price REAL,
        exit_price REAL,
        pnl REAL,
        status TEXT
    )
    """)

    conn.commit()
    conn.close()


def _real_market_context(spot_price):
    """Derive real vix / pcr / max_pain when not supplied - never fabricated."""
    vix = None
    pcr = None
    max_pain = None
    try:
        import regime_filter
        vs = regime_filter.vix_snapshot(nifty_close=spot_price)
        if vs and vs.get("level") is not None:
            vix = float(vs["level"])
    except Exception:
        pass
    try:
        import glob
        import oi_intel
        snaps = sorted(glob.glob(os.path.join("data", "oi_snapshots", "NIFTY_*.csv")))
        if snaps:
            cdf = pd.read_csv(snaps[-1])
            pp = oi_intel.pcr_and_pain(cdf, spot=spot_price)
            pcr = float(pp["pcr"]) if pp.get("pcr") is not None else None
            max_pain = float(pp["max_pain"]) if pp.get("max_pain") is not None else None
    except Exception:
        pass
    return vix, pcr, max_pain


def log_market_tick(spot_price, vix=None, pcr=None, max_pain=None):
    """Permanently log every live market tick (Append-Only).

    vix/pcr/max_pain default to None and are derived from real market context
    when omitted - no fabricated values are ever written to the audit trail.
    """
    _init_sqlite_db()
    now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")

    if vix is None or pcr is None or max_pain is None:
        real_vix, real_pcr, real_pain = _real_market_context(spot_price)
        vix = vix if vix is not None else real_vix
        pcr = pcr if pcr is not None else real_pcr
        max_pain = max_pain if max_pain is not None else real_pain

    # 1. Save to SQLite
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tick_history (timestamp, spot_price, vix, pcr, max_pain) VALUES (?, ?, ?, ?, ?)",
        (now_str, spot_price, vix, pcr, max_pain)
    )
    conn.commit()
    conn.close()

    # 2. Append to CSV
    row = {
        "timestamp": now_str,
        "spot_price": spot_price,
        "vix": vix,
        "pcr": pcr,
        "max_pain": max_pain
    }
    df = pd.DataFrame([row])
    hdr = not os.path.exists(TICK_CSV)
    df.to_csv(TICK_CSV, mode="a", header=hdr, index=False)

    print(f"💾 [History Logger] Appended Live Tick: ₹{spot_price:,.2f} @ {now_str}")


def log_generated_signal(signal_data):
    """Permanently log every generated signal for accuracy verification."""
    _init_sqlite_db()
    now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
    action = signal_data.get("signal_action", "STAY_OUT")
    grade = signal_data.get("signal_grade", "NO_SIGNAL")
    conf = signal_data.get("confluence_score", "0/6")
    spot = signal_data.get("nifty_spot", 0.0)
    levels = signal_data.get("precise_trade_levels", {})

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO signal_history (timestamp, action, grade, confluence_score, spot_price, recommended_strike, sl_points, target_points) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (now_str, action, grade, conf, spot, levels.get("recommended_call_strike", 0.0), levels.get("stop_loss_points", 0.0), levels.get("target_1_points", 0.0))
    )
    conn.commit()
    conn.close()

    row = {
        "timestamp": now_str,
        "action": action,
        "grade": grade,
        "confluence_score": conf,
        "spot_price": spot,
        "recommended_strike": levels.get("recommended_call_strike", 0.0),
        "sl_points": levels.get("stop_loss_points", 0.0),
        "target_points": levels.get("target_1_points", 0.0)
    }
    df = pd.DataFrame([row])
    hdr = not os.path.exists(SIGNAL_CSV)
    df.to_csv(SIGNAL_CSV, mode="a", header=hdr, index=False)

    print(f"💾 [History Logger] Appended Signal: {action} ({grade})")


def get_historical_audit_summary():
    """Get summary of recorded historical data for backtesting & accuracy tracking."""
    _init_sqlite_db()
    conn = sqlite3.connect(DB_FILE)

    ticks_count = pd.read_sql_query("SELECT COUNT(*) as cnt FROM tick_history", conn)["cnt"].iloc[0]
    signals_count = pd.read_sql_query("SELECT COUNT(*) as cnt FROM signal_history", conn)["cnt"].iloc[0]
    journal_count = pd.read_sql_query("SELECT COUNT(*) as cnt FROM paper_trade_journal", conn)["cnt"].iloc[0]

    conn.close()

    return {
        "audit_logger_status": "APPEND_ONLY_PERMANENT_LOGGING_ACTIVE",
        "total_historical_ticks_saved": int(ticks_count),
        "total_signals_logged": int(signals_count),
        "total_paper_journal_records": int(journal_count),
        "database_file": DB_FILE,
        "tick_csv_file": TICK_CSV,
        "signal_csv_file": SIGNAL_CSV
    }


if __name__ == "__main__":
    print("=== TESTING HISTORICAL RECORD & TRADE JOURNAL LOGGER ===")
    log_market_tick(24400.0, vix=13.5, pcr=0.95, max_pain=24450)
    summary = get_historical_audit_summary()
    print(json.dumps(summary, indent=2))
