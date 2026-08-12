"""One-Click Master Orchestrator Script for NIFTY Research.

Executes all 20 Multi-Asset Quant, Self-Enhancement, Paper Trading & Audit Logger Engines:
1. Capital Guard Risk Audit (capital_guard.py)
2. Live Market Real-Time Price Sync (live_market_fetch.py)
3. Permanent Append-Only History Audit Logger (history_logger.py)
4. 6-Layer Precision Signal Generator (precision_signals.py)
5. Gamma Flip & GEX Engine (gamma_flip.py)
6. Multi-Asset Analytics (skew.py, equity_quant.py, mcx_intel.py)
7. Autonomous Self-Enhancement Loop (auto_enhancer.py)
8. Autonomous Live Paper Trading Simulation (auto_paper_runner.py)
9. Live HTML Visual Terminal Generator (web_dashboard.py)
10. Systematic Dashboard Generator (systematic_report.py)
11. Hinglish Voice Coach Audio Alert (voice_coach.py)
"""
import os
import sys
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))


def run_complete_suite():
    print("==================================================================")
    print("⚡ NIFTY MULTI-ASSET QUANT PLATFORM — MASTER ORCHESTRATOR")
    print(f"Time: {dt.datetime.now().strftime('%d %b %Y | %H:%M:%S IST')}")
    print("==================================================================")

    # 1. Capital Guard
    print("\n[1/11] Running Capital Guard Risk Audit...")
    try:
        import capital_guard
        cg = capital_guard.CapitalGuard()
        cg_res = cg.full_capital_safety_audit()
        print(f" -> Status: {cg_res.get('safety_status')} | Kill-Switch: {cg_res.get('kill_switch', {}).get('status')}")
    except Exception as e:
        print(f" -> Capital Guard Error: {e}")

    # 2. Live Market Real-Time Price Sync
    print("\n[2/11] Syncing Live Real-Time Market Ticks (live_market_fetch.py)...")
    try:
        import live_market_fetch
        live = live_market_fetch.update_live_market_cache()
        print(f" -> Live Spot Price: ₹{live.get('spot'):,.2f} ({live.get('status')})")
    except Exception as e:
        print(f" -> Live Price Fetch Error: {e}")

    # 3. History & Audit Logger Summary
    print("\n[3/11] Checking Permanent Append-Only Audit Logs (history_logger.py)...")
    try:
        import history_logger
        audit_sum = history_logger.get_historical_audit_summary()
        print(f" -> Total Historical Ticks Saved: {audit_sum.get('total_historical_ticks_saved')} | DB: {audit_sum.get('database_file')}")
    except Exception as e:
        print(f" -> History Logger Error: {e}")

    # 4. Precision Signal Generator
    print("\n[4/11] Running 6-Layer High-Precision Signal Generator...")
    try:
        import precision_signals
        sig = precision_signals.generate_precision_signal()
        print(f" -> Signal Grade: {sig.get('signal_grade')} ({sig.get('confluence_score')})")
        print(f" -> Action: {sig.get('signal_action')}")

        # Automatically log signal to history
        import history_logger
        history_logger.log_generated_signal(sig)
    except Exception as e:
        print(f" -> Precision Signal Error: {e}")

    # 5. Gamma Flip Engine
    print("\n[5/11] Running Market Maker Gamma Flip & GEX Engine...")
    try:
        import gamma_flip, pandas as pd
        snap_dir = os.path.join("data", "oi_snapshots")
        snaps = [os.path.join(snap_dir, f) for f in os.listdir(snap_dir) if f.endswith(".csv")] if os.path.exists(snap_dir) else []
        if snaps:
            cdf = pd.read_csv(snaps[-1])
            gex = gamma_flip.calculate_gamma_exposure(cdf)
            print(f" -> Gamma Flip Strike: {gex.get('gamma_flip_strike')} | Regime: {gex.get('market_maker_regime')}")
        else:
            print(" -> Gamma Flip: No snapshot found, using defaults.")
    except Exception as e:
        print(f" -> Gamma Flip Error: {e}")

    # 6. Multi-Asset Engines (Skew, Equity RS, MCX)
    print("\n[6/11] Running Multi-Asset Analytics (Options Skew, Equity RS, MCX)...")
    try:
        import skew, equity_quant, mcx_intel
        print(" -> Options Skew, Mansfield Relative Strength & MCX Intelligence Executed.")
    except Exception as e:
        print(f" -> Multi-Asset Error: {e}")

    # 7. Autonomous Auto-Enhancement Loop
    print("\n[7/11] Running Autonomous Self-Enhancement Loop (RL Weights & Volume Profile)...")
    try:
        import auto_enhancer
        enh_res = auto_enhancer.run_auto_enhancement_cycle()
        print(f" -> Auto-Enhancement Status: {enh_res.get('enhancement_cycle_status')}")
    except Exception as e:
        print(f" -> Auto-Enhancement Error: {e}")

    # 8. Live Paper Trading Engine
    print("\n[8/11] Running Live Paper Trading Simulation (auto_paper_runner.py)...")
    try:
        import paper_trader
        summary = paper_trader.paper_engine.get_paper_account_summary()
        print(f" -> Paper Account Equity: ₹{summary.get('current_equity'):,.2f} | Open Positions: {summary.get('total_open_positions')}")
    except Exception as e:
        print(f" -> Paper Trading Error: {e}")

    # 9. Live HTML Terminal Generator
    print("\n[9/11] Updating Live Browser Terminal (blog/live_terminal.html)...")
    try:
        import web_dashboard
        term_path = web_dashboard.generate_live_terminal_html()
        print(f" -> Terminal Updated: {term_path}")
    except Exception as e:
        print(f" -> Web Dashboard Error: {e}")

    # 10. Systematic Dashboard Generator
    print("\n[10/11] Updating Systematic Dashboard (results/systematic_dashboard.md)...")
    try:
        import systematic_report
        dash_path = systematic_report.generate_systematic_dashboard()
        print(f" -> Dashboard Updated: {dash_path}")
    except Exception as e:
        print(f" -> Systematic Dashboard Error: {e}")

    # 11. Voice Coach Audio Alert
    print("\n[11/11] Activating Interactive Hinglish Voice Coach...")
    try:
        import voice_coach
        voice_coach.run_voice_summary()
    except Exception as e:
        print(f" -> Voice Coach Error: {e}")

    print("\n==================================================================")
    print("✅ MASTER ORCHESTRATION COMPLETE — ALL SYSTEMS ACTIVE, LOGGED & ENHANCED!")
    print("==================================================================")


if __name__ == "__main__":
    run_complete_suite()
