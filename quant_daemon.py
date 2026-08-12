"""Persistent PID-Managed Background Trading Daemon for NIFTY Research.

Adopted from trading_bot architecture:
Runs continuous 30-second live market tick streaming, paper trading execution,
and reinforcement auto-enhancement in background with PID process tracking.

Usage:
    python3 quant_daemon.py --start    # Start background daemon
    python3 quant_daemon.py --status   # Check daemon status
    python3 quant_daemon.py --stop     # Stop background daemon
"""
import os
import sys
import time
import json
import signal
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))

PID_FILE = os.path.join("data", "quant_daemon.pid")
LOG_FILE = os.path.join("data", "quant_daemon.log")


def is_daemon_running():
    """Check if PID file exists and process is active."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return pid
        except (OSError, ValueError):
            os.remove(PID_FILE)
    return None


def stop_daemon():
    """Stop the running background daemon."""
    pid = is_daemon_running()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"🛑 [Quant Daemon] Stopped background process PID: {pid}")
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
        except Exception as e:
            print(f"Error stopping daemon: {e}")
    else:
        print("ℹ️ [Quant Daemon] No running daemon process found.")


def run_daemon_loop():
    """Main continuous background loop."""
    pid = os.getpid()
    os.makedirs("data", exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(pid))

    print(f"🚀 [Quant Daemon] Started Background Daemon Process PID: {pid}")

    tick_count = 0
    try:
        while True:
            tick_count += 1
            now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")

            # 1. Sync Live Market Tick
            import live_market_fetch
            live = live_market_fetch.update_live_market_cache()

            # 2. Run Auto Paper Trader
            import auto_paper_runner
            paper_sum = auto_paper_runner.run_auto_paper_trader()

            # 3. Every 5th cycle (2.5 mins), run Auto-Enhancer
            if tick_count % 5 == 0:
                import auto_enhancer
                auto_enhancer.run_auto_enhancement_cycle()

            msg = f"[{now_str}] Cycle #{tick_count} | Spot: ₹{live.get('spot', 0.0):,.2f} | Paper Equity: ₹{paper_sum.get('current_equity', 0.0):,.2f}\n"
            with open(LOG_FILE, "a") as f:
                f.write(msg)

            time.sleep(30)
    except KeyboardInterrupt:
        print("\n🛑 Daemon interrupted.")
    finally:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--status"

    if arg == "--start":
        pid = is_daemon_running()
        if pid:
            print(f"ℹ️ Daemon already running on PID {pid}")
        else:
            run_daemon_loop()
    elif arg == "--stop":
        stop_daemon()
    else:
        pid = is_daemon_running()
        if pid:
            print(f"🟢 [Quant Daemon Status] RUNNING (PID: {pid}) | Log: {LOG_FILE}")
        else:
            print("🔴 [Quant Daemon Status] STOPPED | Start with: python3 quant_daemon.py --start")
