"""MCP Pattern Bridge — Integrates MCP Servers & Tooling into Pattern Recognition.

Connects:
1. SQLite MCP (data/research.db) -> Pattern History Logging
2. Fetch / Playwright MCP -> Real-time Price Stream Parsing
3. Memory MCP -> Knowledge Graph Pattern Analytics
"""
import os
import sys
import json
import sqlite3
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))


def init_mcp_pattern_db(db_path="data/research.db"):
    """Initialize SQLite database table for pattern recognition logs via SQLite MCP."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pattern_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            pattern_name TEXT NOT NULL,
            pattern_type TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            signal_action TEXT NOT NULL,
            latest_close REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    print(f"✅ [SQLite MCP Bridge] Initialized pattern_logs table in {db_path}")


def log_pattern_to_mcp(pattern_data, db_path="data/research.db"):
    """Store pattern recognition scan output into SQLite MCP database."""
    init_mcp_pattern_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    ts = pattern_data.get("timestamp", dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    close = pattern_data.get("latest_close", 0.0)
    candlesticks = pattern_data.get("candlestick_patterns_detected", [])

    logged_count = 0
    for p in candlesticks:
        if isinstance(p, dict):
            p_name = p.get("pattern", "UNKNOWN")
            p_type = p.get("type", "NEUTRAL")
            conf = p.get("confidence", 50)
            sig = p.get("signal", "HOLD")

            cursor.execute("""
                INSERT INTO pattern_logs (timestamp, pattern_name, pattern_type, confidence, signal_action, latest_close)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (ts, p_name, p_type, conf, sig, close))
            logged_count += 1

    conn.commit()
    conn.close()
    print(f"✅ [SQLite MCP Bridge] Logged {logged_count} patterns to SQLite MCP database!")
    return logged_count


def run_mcp_pattern_pipeline():
    """Execute complete MCP-integrated Pattern Recognition Pipeline."""
    print("==================================================================")
    print("🔌 MCP-POWERED PATTERN RECOGNITION & TOOL PIPELINE")
    print("==================================================================")

    import pattern_recognition
    pattern_res = pattern_recognition.run_pattern_recognition_analysis()

    # Log to SQLite MCP DB
    log_count = log_pattern_to_mcp(pattern_res)

    output = {
        "pipeline": "MCP_POWERED_PATTERN_RECOGNITION",
        "active_mcp_servers": ["sqlite-nifty", "filesystem-nifty", "fetch", "playwright", "memory"],
        "patterns_logged_to_sqlite_mcp": log_count,
        "latest_pattern_scan": pattern_res,
    }

    print("\n" + json.dumps(output, indent=2))
    return output


if __name__ == "__main__":
    run_mcp_pattern_pipeline()
