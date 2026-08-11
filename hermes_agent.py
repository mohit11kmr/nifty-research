"""Hermes Autonomous Trading Agent — Scheduled Market Research & Execution Runner.

Executes autonomous 3-phase trading lifecycle:
1. Pre-Market Phase (08:45 IST): Master orchestration & Risk Audit
2. Intraday Phase (Every 30 min during 09:15-15:30 IST): 6-Layer Signal Scan & Voice Alerts
3. Post-Market Phase (16:30 IST): EOD data cache build & Blog post generation
"""
import os
import sys
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))


def run_hermes_pre_market():
    """Phase 1: Pre-Market Autonomous Run (08:45 IST)."""
    print("🤖 [HERMES AGENT] Running Pre-Market Autonomous Phase...")
    import run_all
    run_all.run_complete_suite()


def run_hermes_intraday_scan():
    """Phase 2: Intraday Autonomous Signal Scan (Market Hours)."""
    print("🤖 [HERMES AGENT] Running Intraday Precision Signal Scan...")
    import precision_signals, capital_guard, voice_coach

    # 1. Capital Guard Audit
    cg = capital_guard.CapitalGuard().full_capital_safety_audit()
    if cg.get("kill_switch", {}).get("is_kill_switch_active"):
        print(" -> Kill-Switch Active! Halting Intraday Scan.")
        return

    # 2. Precision Signal Check
    sig = precision_signals.generate_precision_signal()
    grade = sig.get("signal_grade", "NO_SIGNAL")

    if "A+ GRADE" in grade or "A GRADE" in grade:
        msg = f"Hermes Agent Alert! High Conviction Setup Detected: {sig.get('signal_action')}. Check terminal!"
        print(f" -> {msg}")
        voice_coach.speak_hinglish(msg)
    else:
        print(f" -> Intraday Scan: {grade}. No high-confluence trade.")


def run_hermes_post_market():
    """Phase 3: Post-Market Autonomous EOD Summary (16:30 IST)."""
    print("🤖 [HERMES AGENT] Running Post-Market EOD Summary & Blog Generation...")
    os.system("python3 build_data.py")
    os.system("python3 daily_report.py --blog")
    print(" -> Hermes Post-Market Run Completed Successfully!")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "pre-market"
    print(f"==================================================================")
    print(f"🤖 HERMES AUTONOMOUS TRADING AGENT — MODE: {mode.upper()}")
    print(f"Time: {dt.datetime.now().strftime('%d %b %Y | %H:%M:%S IST')}")
    print(f"==================================================================")

    if mode == "intraday":
        run_hermes_intraday_scan()
    elif mode == "post-market":
        run_hermes_post_market()
    else:
        run_hermes_pre_market()
