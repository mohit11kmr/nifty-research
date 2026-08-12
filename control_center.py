"""Interactive Control Center Menu for NIFTY Research.

Provides a simple 1-key terminal menu for operating the entire platform.
"""
import os
import sys
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))


def display_menu():
    print("\n" + "="*66)
    print("🎯 NIFTY QUANT PLATFORM — SIMPLE INTERACTIVE CONTROL CENTER")
    print(f"Time: {dt.datetime.now().strftime('%d %b %Y | %H:%M:%S IST')}")
    print("="*66)
    print(" [1] 🚀 Start 5-Second Real-Time Live Market Ticker Stream")
    print(" [2] 🎯 Generate Today's High-Precision Trade Setup & Signal")
    print(" [3] 📝 Check Live Paper Trading Account & Open Positions")
    print(" [4] 🛡️ Run Prop-Desk Capital Guard Risk Safety Audit")
    print(" [5] 🔄 Run Autonomous Reinforcement Self-Enhancement Loop")
    print(" [6] 🌐 Open Live Visual Terminal (http://127.0.0.1:8766/)")
    print(" [7] 📜 View Historical Audit & Permanent Backtest Log Summary")
    print(" [8] ⚡ Run One-Click Master Orchestrator (All Engines)")
    print(" [9] ⚙️ PID Background Quant Daemon (Start / Status / Stop)")
    print(" [0] ❌ Exit Control Center")
    print("="*66)


def run_control_center():
    while True:
        display_menu()
        choice = input("Enter choice [0-9]: ").strip()

        if choice == "1":
            import live_ticker_service
            live_ticker_service.stream_live_market_ticks(interval_sec=2, max_ticks=5)

        elif choice == "2":
            import precision_signals
            sig = precision_signals.generate_precision_signal()
            print("\n" + json.dumps(sig, indent=2))

        elif choice == "3":
            import paper_trader
            summary = paper_trader.paper_engine.get_paper_account_summary()
            print("\n" + json.dumps(summary, indent=2))

        elif choice == "4":
            import capital_guard
            cg = capital_guard.CapitalGuard().full_capital_safety_audit()
            print("\n" + json.dumps(cg, indent=2))

        elif choice == "5":
            import auto_enhancer
            enh = auto_enhancer.run_auto_enhancement_cycle()
            print("\n" + json.dumps(enh, indent=2))

        elif choice == "6":
            print("\n🌐 Live Terminal Web Server URL: http://127.0.0.1:8766/")
            os.system("google-chrome http://127.0.0.1:8766/ 2>/dev/null &")

        elif choice == "7":
            import history_logger
            hist = history_logger.get_historical_audit_summary()
            print("\n" + json.dumps(hist, indent=2))

        elif choice == "8":
            import run_all
            run_all.run_complete_suite()

        elif choice == "9":
            import quant_daemon
            pid = quant_daemon.is_daemon_running()
            if pid:
                print(f"🟢 Daemon running on PID {pid}. Stopping...")
                quant_daemon.stop_daemon()
            else:
                print("🔴 Daemon stopped. Check status:")
                os.system("python3 quant_daemon.py --status")

        elif choice == "0":
            print("Goodbye Mohit bhai!")
            break
        else:
            print("Invalid selection. Try again.")


if __name__ == "__main__":
    run_control_center()
