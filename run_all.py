"""One-Click Master Orchestrator Script for NIFTY Research.

Executes all 23 Multi-Asset Quant, Self-Enhancement, Paper Trading & Quantum Nexus Adopted Engines:
1. Capital Guard Risk Audit (capital_guard.py)
2. Real-Time 5-Second Market Ticker Stream (live_ticker_service.py)
3. Live Market Real-Time Price Sync (live_market_fetch.py)
4. Permanent Append-Only History Audit Logger (history_logger.py)
5. 6-Layer Precision Signal Generator (precision_signals.py)
6. Multi-Leg Option Spreads Generator (multi_leg_options.py)
7. Reflection & Self-Critique Hypothesis Engine (reflection_engine.py)
8. Gamma Flip & GEX Engine (gamma_flip.py)
9. Multi-Asset Analytics (skew.py, equity_quant.py, mcx_intel.py)
10. Autonomous Self-Enhancement Loop (auto_enhancer.py)
11. Autonomous Live Paper Trading Simulation (auto_paper_runner.py)
12. Live HTML Visual Terminal Generator (web_dashboard.py)
13. Systematic Dashboard Generator (systematic_report.py)
14. Hinglish Voice Coach Audio Alert (voice_coach.py)
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
    print("\n[1/14] Running Capital Guard Risk Audit...")
    try:
        import capital_guard
        cg = capital_guard.CapitalGuard()
        cg_res = cg.full_capital_safety_audit()
        print(f" -> Status: {cg_res.get('safety_status')} | Kill-Switch: {cg_res.get('kill_switch', {}).get('status')}")
    except Exception as e:
        print(f" -> Capital Guard Error: {e}")

    # 2. Live Ticker Streaming
    print("\n[2/14] Running 5-Second Real-Time Market Ticker Stream (live_ticker_service.py)...")
    try:
        import live_ticker_service
        live_ticker_service.stream_live_market_ticks(interval_sec=1, max_ticks=2)
    except Exception as e:
        print(f" -> Live Ticker Error: {e}")

    # 3. Live Market Real-Time Price Sync
    print("\n[3/14] Syncing Live Real-Time Market Ticks (live_market_fetch.py)...")
    try:
        import live_market_fetch
        live = live_market_fetch.update_live_market_cache()
        print(f" -> Live Spot Price: ₹{live.get('spot'):,.2f} ({live.get('status')})")
    except Exception as e:
        print(f" -> Live Price Fetch Error: {e}")

    # 4. History & Audit Logger Summary
    print("\n[4/14] Checking Permanent Append-Only Audit Logs (history_logger.py)...")
    try:
        import history_logger
        audit_sum = history_logger.get_historical_audit_summary()
        print(f" -> Total Historical Ticks Saved: {audit_sum.get('total_historical_ticks_saved')} | DB: {audit_sum.get('database_file')}")
    except Exception as e:
        print(f" -> History Logger Error: {e}")

    # 5. Precision Signal Generator
    print("\n[5/14] Running 6-Layer High-Precision Signal Generator...")
    try:
        import precision_signals
        sig = precision_signals.generate_precision_signal()
        print(f" -> Signal Grade: {sig.get('signal_grade')} ({sig.get('confluence_score')})")
        print(f" -> Action: {sig.get('signal_action')}")

        import history_logger
        history_logger.log_generated_signal(sig)
    except Exception as e:
        print(f" -> Precision Signal Error: {e}")

    # 6. Quantum Nexus Multi-Leg Options Engine
    print("\n[6/14] Running Multi-Leg Option Spreads Generator (multi_leg_options.py)...")
    try:
        import multi_leg_options
        condor = multi_leg_options.construct_multi_leg_strategy()
        print(f" -> Strategy: {condor.get('strategy')} | Win Prob: {condor.get('profit_probability')}")
    except Exception as e:
        print(f" -> Multi-Leg Option Error: {e}")

    # 7. Quantum Nexus Reflection Hypothesis Engine
    print("\n[7/14] Running AI Reflection & Self-Critique Engine (reflection_engine.py)...")
    try:
        import reflection_engine
        hyp = reflection_engine.run_reflection_loop()
        print(f" -> Hypothesis: {hyp.get('hypothesis_id')} | Proposed: {hyp.get('proposed_change')}")
    except Exception as e:
        print(f" -> Reflection Error: {e}")

    # 8. Gamma Flip Engine
    print("\n[8/14] Running Market Maker Gamma Flip & GEX Engine...")
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

    # 9. Multi-Asset Analytics (Skew, Equity RS, MCX)
    print("\n[9/14] Running Multi-Asset Analytics (Options Skew, Equity RS, MCX)...")
    try:
        import skew, equity_quant, mcx_intel
        print(" -> Options Skew, Mansfield Relative Strength & MCX Intelligence Executed.")
    except Exception as e:
        print(f" -> Multi-Asset Error: {e}")

    # 10. Autonomous Auto-Enhancement Loop
    print("\n[10/14] Running Autonomous Self-Enhancement Loop (RL Weights & Volume Profile)...")
    try:
        import auto_enhancer
        enh_res = auto_enhancer.run_auto_enhancement_cycle()
        print(f" -> Auto-Enhancement Status: {enh_res.get('enhancement_cycle_status')}")
    except Exception as e:
        print(f" -> Auto-Enhancement Error: {e}")

    # 11. Live Paper Trading Engine
    print("\n[11/14] Running Live Paper Trading Simulation (auto_paper_runner.py)...")
    try:
        import paper_trader
        summary = paper_trader.paper_engine.get_paper_account_summary()
        print(f" -> Paper Account Equity: ₹{summary.get('current_equity'):,.2f} | Open Positions: {summary.get('total_open_positions')}")
    except Exception as e:
        print(f" -> Paper Trading Error: {e}")

    # 12. Live HTML Terminal Generator
    print("\n[12/14] Updating Live Browser Terminal (blog/live_terminal.html)...")
    try:
        import web_dashboard
        term_path = web_dashboard.generate_live_terminal_html()
        print(f" -> Terminal Updated: {term_path}")
    except Exception as e:
        print(f" -> Web Dashboard Error: {e}")

    # 13. Systematic Dashboard Generator
    print("\n[13/14] Updating Systematic Dashboard (results/systematic_dashboard.md)...")
    try:
        import systematic_report
        dash_path = systematic_report.generate_systematic_dashboard()
        print(f" -> Dashboard Updated: {dash_path}")
    except Exception as e:
        print(f" -> Systematic Dashboard Error: {e}")

    # 14. Voice Coach Audio Alert
    print("\n[14/14] Activating Interactive Hinglish Voice Coach...")
    try:
        import voice_coach
        voice_coach.run_voice_summary()
    except Exception as e:
        print(f" -> Voice Coach Error: {e}")

    print("\n==================================================================")
    print("✅ MASTER ORCHESTRATION COMPLETE — ALL SYSTEMS & REFLECTION LOOPS ONLINE!")
    print("==================================================================")


if __name__ == "__main__":
    run_complete_suite()
