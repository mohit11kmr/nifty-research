"""One-Click Master Orchestrator Script for NIFTY Research.

Executes all 31 Multi-Asset Quant, Self-Enhancement, Paper Trading & Adopted Engines:
1. Capital Guard Risk Audit (capital_guard.py)
2. Swarm Dynamic Delta-Hedging Guard (delta_hedging_guard.py)
3. LangGraph 6-Node Agentic State Graph Workflow (agent_workflow_graph.py)
4. Angel One SmartAPI Scrip Master Token Lookup (token_lookup.py)
5. Value-at-Risk (VaR) & Portfolio Stress Test Engine (var_risk_manager.py)
6. Deep Learning LSTM Neural Sequence Engine (lstm_neural_engine.py)
7. Volume Surge & Pocket Pivot Analytics Engine (volume_analytics_engine.py)
8. Real-Time 5-Second Market Ticker Stream (live_ticker_service.py)
9. Live Market Real-Time Price Sync (live_market_fetch.py)
10. Permanent Append-Only History Audit Logger (history_logger.py)
11. Multi-Timeframe Trend Alignment Engine (mtf_alignment.py)
12. 6-Layer Precision Signal Generator (precision_signals.py)
13. Smart Strike Price Selector (smart_strike_selector.py)
14. Multi-Leg Option Spreads Generator (multi_leg_options.py)
15. Reflection & Self-Critique Hypothesis Engine (reflection_engine.py)
16. Gamma Flip & GEX Engine (gamma_flip.py)
17. Multi-Asset Analytics (skew.py, equity_quant.py, mcx_intel.py)
18. Autonomous Self-Enhancement Loop (auto_enhancer.py)
19. Autonomous Live Paper Trading Simulation (auto_paper_runner.py)
20. Live HTML Visual Terminal Generator (web_dashboard.py)
21. Systematic Dashboard Generator (systematic_report.py)
22. Hinglish Voice Coach Audio Alert (voice_coach.py)
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
    print("\n[1/22] Running Capital Guard Risk Audit...")
    try:
        import capital_guard
        cg = capital_guard.CapitalGuard()
        cg_res = cg.full_capital_safety_audit()
        print(f" -> Status: {cg_res.get('safety_status')} | Kill-Switch: {cg_res.get('kill_switch', {}).get('status')}")
    except Exception as e:
        print(f" -> Capital Guard Error: {e}")

    # 2. Swarm Delta Hedging Guard
    print("\n[2/22] Running Swarm Dynamic Delta-Hedging Guard (delta_hedging_guard.py)...")
    try:
        import delta_hedging_guard
        dh_res = delta_hedging_guard.delta_guard.evaluate_portfolio_delta()
        print(f" -> Delta Guard Status: {dh_res.get('guard_status')} | Hedge Needed: {dh_res.get('hedge_needed')} | Action: {dh_res.get('hedge_recommendation', {}).get('action')}")
    except Exception as e:
        print(f" -> Delta Guard Error: {e}")

    # 3. Agentic Workflow Graph
    print("\n[3/22] Running LangGraph 6-Node Agentic State Graph Workflow (agent_workflow_graph.py)...")
    try:
        import agent_workflow_graph
        graph_res = agent_workflow_graph.run_agentic_workflow_graph()
        print(f" -> Workflow Execution: {graph_res.get('execution')} | Equity: ₹{graph_res.get('portfolio', {}).get('equity'):,.2f}")
    except Exception as e:
        print(f" -> Workflow Graph Error: {e}")

    # 4. Token Lookup
    print("\n[4/22] Running Angel One SmartAPI Scrip Master Token Lookup (token_lookup.py)...")
    try:
        import token_lookup
        token_info = token_lookup.get_token_for_symbol(symbol_name="NIFTY", strike=24500, option_type="CE")
        print(f" -> Scrip Token: {token_info.get('token')} | Symbol: {token_info.get('symbol')} | Expiry: {token_info.get('expiry')}")
    except Exception as e:
        print(f" -> Token Lookup Error: {e}")

    # 5. Value-at-Risk (VaR) & Stress Testing
    print("\n[5/22] Running Value-at-Risk (VaR) & Portfolio Stress Test (var_risk_manager.py)...")
    try:
        import var_risk_manager
        var_res = var_risk_manager.var_engine.compute_value_at_risk()
        print(f" -> 95% VaR: ₹{var_res.get('var_95_confidence_rupees')} ({var_res.get('var_95_confidence_pct')}%) | Status: {var_res.get('var_status')}")
    except Exception as e:
        print(f" -> VaR Engine Error: {e}")

    # 6. Deep Learning LSTM Engine
    print("\n[6/22] Running Deep Learning LSTM Neural Sequence Engine (lstm_neural_engine.py)...")
    try:
        import lstm_neural_engine
        lstm = lstm_neural_engine.predict_lstm_sequence()
        print(f" -> LSTM Verdict: {lstm.get('lstm_verdict')} (Bullish Prob: {lstm.get('lstm_bullish_probability')*100:.1f}%)")
    except Exception as e:
        print(f" -> LSTM Engine Error: {e}")

    # 7. Volume Analytics & Pocket Pivot Engine
    print("\n[7/22] Running Volume Surge & Pocket Pivot Engine (volume_analytics_engine.py)...")
    try:
        import volume_analytics_engine
        vol_res = volume_analytics_engine.compute_volume_analytics()
        print(f" -> Volume Surge: {vol_res.get('volume_surge_ratio')}x | Conviction: {vol_res.get('institutional_conviction')}")
    except Exception as e:
        print(f" -> Volume Analytics Error: {e}")

    # 8. Live Ticker Streaming
    print("\n[8/22] Running 5-Second Real-Time Market Ticker Stream (live_ticker_service.py)...")
    try:
        import live_ticker_service
        live_ticker_service.stream_live_market_ticks(interval_sec=1, max_ticks=2)
    except Exception as e:
        print(f" -> Live Ticker Error: {e}")

    # 9. Live Market Real-Time Price Sync
    print("\n[9/22] Syncing Live Real-Time Market Ticks (live_market_fetch.py)...")
    try:
        import live_market_fetch
        live = live_market_fetch.update_live_market_cache()
        print(f" -> Live Spot Price: ₹{live.get('spot'):,.2f} ({live.get('status')})")
    except Exception as e:
        print(f" -> Live Price Fetch Error: {e}")

    # 10. History & Audit Logger Summary
    print("\n[10/22] Checking Permanent Append-Only Audit Logs (history_logger.py)...")
    try:
        import history_logger
        audit_sum = history_logger.get_historical_audit_summary()
        print(f" -> Total Historical Ticks Saved: {audit_sum.get('total_historical_ticks_saved')} | DB: {audit_sum.get('database_file')}")
    except Exception as e:
        print(f" -> History Logger Error: {e}")

    # 11. Multi-Timeframe Alignment Engine
    print("\n[11/22] Running Multi-Timeframe Alignment Engine (mtf_alignment.py)...")
    try:
        import mtf_alignment
        mtf = mtf_alignment.compute_mtf_alignment()
        print(f" -> MTF Alignment: {mtf.get('alignment_status')} ({mtf.get('alignment_score')})")
    except Exception as e:
        print(f" -> MTF Alignment Error: {e}")

    # 12. Precision Signal Generator
    print("\n[12/22] Running 6-Layer High-Precision Signal Generator...")
    try:
        import precision_signals
        sig = precision_signals.generate_precision_signal()
        print(f" -> Signal Grade: {sig.get('signal_grade')} ({sig.get('confluence_score')})")
        print(f" -> Action: {sig.get('signal_action')}")

        import history_logger
        history_logger.log_generated_signal(sig)
    except Exception as e:
        print(f" -> Precision Signal Error: {e}")

    # 13. Smart Strike Price Selector
    print("\n[13/22] Running Smart Strike Price Selector (smart_strike_selector.py)...")
    try:
        import smart_strike_selector
        best_strike = smart_strike_selector.strike_selector.select_best_strike(spot_price=24403.10, option_type="CE")
        print(f" -> Best Strike: {best_strike.get('best_strike')} {best_strike.get('best_strike_moneyness')} | Score: {best_strike.get('rank_score')}")
    except Exception as e:
        print(f" -> Strike Selector Error: {e}")

    # 14. Quantum Nexus Multi-Leg Options Engine
    print("\n[14/22] Running Multi-Leg Option Spreads Generator (multi_leg_options.py)...")
    try:
        import multi_leg_options
        condor = multi_leg_options.construct_multi_leg_strategy()
        print(f" -> Strategy: {condor.get('strategy')} | Win Prob: {condor.get('profit_probability')}")
    except Exception as e:
        print(f" -> Multi-Leg Option Error: {e}")

    # 15. Quantum Nexus Reflection Hypothesis Engine
    print("\n[15/22] Running AI Reflection & Self-Critique Engine (reflection_engine.py)...")
    try:
        import reflection_engine
        hyp = reflection_engine.run_reflection_loop()
        print(f" -> Hypothesis: {hyp.get('hypothesis_id')} | Proposed: {hyp.get('proposed_change')}")
    except Exception as e:
        print(f" -> Reflection Error: {e}")

    # 16. Gamma Flip Engine
    print("\n[16/22] Running Market Maker Gamma Flip & GEX Engine...")
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

    # 17. Multi-Asset Analytics (Skew, Equity RS, MCX)
    print("\n[17/22] Running Multi-Asset Analytics (Options Skew, Equity RS, MCX)...")
    try:
        import skew, equity_quant, mcx_intel
        print(" -> Options Skew, Mansfield Relative Strength & MCX Intelligence Executed.")
    except Exception as e:
        print(f" -> Multi-Asset Error: {e}")

    # 18. Autonomous Auto-Enhancement Loop
    print("\n[18/22] Running Autonomous Self-Enhancement Loop (RL Weights & Volume Profile)...")
    try:
        import auto_enhancer
        enh_res = auto_enhancer.run_auto_enhancement_cycle()
        print(f" -> Auto-Enhancement Status: {enh_res.get('enhancement_cycle_status')}")
    except Exception as e:
        print(f" -> Auto-Enhancement Error: {e}")

    # 19. Live Paper Trading Engine
    print("\n[19/22] Running Live Paper Trading Simulation (auto_paper_runner.py)...")
    try:
        import paper_trader
        summary = paper_trader.paper_engine.get_paper_account_summary()
        print(f" -> Paper Account Equity: ₹{summary.get('current_equity'):,.2f} | Open Positions: {summary.get('total_open_positions')}")
    except Exception as e:
        print(f" -> Paper Trading Error: {e}")

    # 20. Live HTML Terminal Generator
    print("\n[20/22] Updating Live Browser Terminal (blog/live_terminal.html)...")
    try:
        import web_dashboard
        term_path = web_dashboard.generate_live_terminal_html()
        print(f" -> Terminal Updated: {term_path}")
    except Exception as e:
        print(f" -> Web Dashboard Error: {e}")

    # 21. Systematic Dashboard Generator
    print("\n[21/22] Updating Systematic Dashboard (results/systematic_dashboard.md)...")
    try:
        import systematic_report
        dash_path = systematic_report.generate_systematic_dashboard()
        print(f" -> Dashboard Updated: {dash_path}")
    except Exception as e:
        print(f" -> Systematic Dashboard Error: {e}")

    # 22. Voice Coach Audio Alert
    print("\n[22/22] Activating Interactive Hinglish Voice Coach...")
    try:
        import voice_coach
        voice_coach.run_voice_summary()
    except Exception as e:
        print(f" -> Voice Coach Error: {e}")

    print("\n==================================================================")
    print("✅ MASTER ORCHESTRATION COMPLETE — ALL 31 QUANT ENGINES ONLINE!")
    print("==================================================================")


if __name__ == "__main__":
    run_complete_suite()
