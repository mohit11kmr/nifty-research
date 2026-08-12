"""LangGraph-Style Agentic State Graph Workflow for NIFTY Research.

Adopted from ai-trading-agents architecture:
Orchestrates 6 Agent Nodes in a DAG Flow:
  Market Data -> Signal Detection -> Strategy Decision -> Risk Validation -> Execution -> Portfolio Update
"""
import os
import json
import datetime as dt


def _real_spot():
    """Real current spot from regime_filter cache or live_dash DB."""
    try:
        import regime_filter
        plan = regime_filter.trade_plan()
        if plan.get("close"):
            return float(plan["close"])
    except Exception:
        pass
    try:
        import sqlite3
        db = os.path.join("data", "research.db")
        if os.path.exists(db):
            con = sqlite3.connect(db)
            row = con.execute("SELECT value FROM spot ORDER BY recv_ts DESC LIMIT 1").fetchone()
            con.close()
            if row and row[0]:
                return float(row[0])
    except Exception:
        pass
    return None


def run_agentic_workflow_graph(spot_price=None):
    """Execute complete 6-node state graph workflow."""
    print("==================================================================")
    print("🕸️ LANGGRAPH AGENTIC STATE GRAPH WORKFLOW")
    print(f"Time: {dt.datetime.now().strftime('%d %b %Y | %H:%M:%S IST')}")
    print("==================================================================")

    if spot_price is None:
        spot_price = _real_spot()
    if not spot_price:
        print(" 🛑 [Workflow] No real spot available - standing down (no fabricated workflow).")
        return {"execution": "STAND_DOWN_NO_DATA", "reason": "no real spot price"}

    state = {
        "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "spot_price": spot_price,
        "should_trade": False
    }

    # Node 1: Market Data Node
    print(" -> [Node 1/6] Market Data Node: Normalizing Live Spot & Volatility...")
    try:
        import regime_filter
        vix_snap = regime_filter.vix_snapshot(nifty_close=spot_price)
        vix = vix_snap.get("level") if vix_snap else None
    except Exception:
        vix = None
    state["normalized_market"] = {"spot": spot_price, "vix": vix, "status": "READY"}

    # Node 2: Signal Detection Node
    print(" -> [Node 2/6] Signal Detection Node: Evaluating 6-Layer Confluence...")
    import precision_signals
    sig = precision_signals.generate_precision_signal()
    state["signal"] = sig

    # Node 3: Strategy Decision Node
    print(" -> [Node 3/6] Strategy Decision Node: Selecting Optimal Strategy...")
    action = sig.get("signal_action", "STAY_OUT")
    entry_premium = None
    best_strike = None
    if action in ("STAY_OUT", "NO_SIGNAL") or "STAY_OUT" in str(sig.get("signal_grade", "")):
        print(f" -> [Workflow] Signal is {action} - no strategy selected, standing down.")
        state["strategy"] = {"type": "NO_TRADE", "reason": f"signal {action}"}
    elif "BUY" in action:
        import smart_strike_selector
        best_strike = smart_strike_selector.strike_selector.select_best_strike(spot_price=spot_price)
        state["strategy"] = {"type": "DIRECTIONAL_BUY", "strike": best_strike.get("best_strike")}
        entry_premium = best_strike.get("best_strike_premium")
    else:
        import multi_leg_options
        condor = multi_leg_options.construct_multi_leg_strategy(spot_price=spot_price)
        state["strategy"] = {"type": "DEFINED_RISK_SPREAD", "details": condor.get("strategy")}

    # Node 4: Risk Validation Node
    print(" -> [Node 4/6] Risk Validation Node: Auditing Capital Guard & VaR...")
    import capital_guard
    cg = capital_guard.CapitalGuard().full_capital_safety_audit()
    state["risk_result"] = cg.get("safety_status")
    state["should_trade"] = (cg.get("safety_status") == "APPROVED")

    # Node 5: Execution Node
    print(" -> [Node 5/6] Execution Node: Dispatching to Paper Trading Engine...")
    import paper_trader
    exec_ok = (
        state["should_trade"]
        and "BUY" in action
        and entry_premium and float(entry_premium) > 0
        and best_strike and best_strike.get("best_strike")
    )
    if exec_ok:
        premium = float(entry_premium)
        atr_v = max(10.0, premium * 0.25)
        sl_p = round(max(2.0, premium - 1.5 * atr_v), 2)
        target_p = round(premium + 2.0 * (premium - sl_p), 2)
        option_type = "CE" if ("BUY_CALL" in action or "BULLISH" in action) else "PE"
        res = paper_trader.paper_engine.execute_paper_order(
            symbol="NIFTY",
            side="BUY",
            option_type=option_type,
            strike=int(best_strike.get("best_strike")),
            lots=1,
            lot_size=75,
            entry_price=premium,
            sl_price=sl_p,
            target_price=target_p,
        )
        state["execution"] = res.get("status")
    else:
        state["execution"] = "STAND_DOWN_NO_TRADE"

    # Node 6: Portfolio Update Node
    print(" -> [Node 6/6] Portfolio Node: Updating Equity Curve & Audit DB...")
    summary = paper_trader.paper_engine.get_paper_account_summary()
    state["portfolio"] = {"equity": summary.get("current_equity"), "open_positions": summary.get("total_open_positions")}

    print("==================================================================")
    print(f"✅ WORKFLOW COMPLETED — Final Execution: {state['execution']} | Equity: ₹{summary.get('current_equity'):,.2f}")
    print("==================================================================")
    return state


if __name__ == "__main__":
    run_agentic_workflow_graph()
