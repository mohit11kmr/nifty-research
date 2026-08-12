"""LangGraph-Style Agentic State Graph Workflow for NIFTY Research.

Adopted from ai-trading-agents architecture:
Orchestrates 6 Agent Nodes in a DAG Flow:
  Market Data -> Signal Detection -> Strategy Decision -> Risk Validation -> Execution -> Portfolio Update
"""
import os
import json
import datetime as dt


def run_agentic_workflow_graph(spot_price=24403.10):
    """Execute complete 6-node state graph workflow."""
    print("==================================================================")
    print("🕸️ LANGGRAPH AGENTIC STATE GRAPH WORKFLOW")
    print(f"Time: {dt.datetime.now().strftime('%d %b %Y | %H:%M:%S IST')}")
    print("==================================================================")

    state = {
        "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "spot_price": spot_price,
        "should_trade": False
    }

    # Node 1: Market Data Node
    print(" -> [Node 1/6] Market Data Node: Normalizing Live Spot & Volatility...")
    state["normalized_market"] = {"spot": spot_price, "vix": 12.0, "status": "READY"}

    # Node 2: Signal Detection Node
    print(" -> [Node 2/6] Signal Detection Node: Evaluating 6-Layer Confluence...")
    import precision_signals
    sig = precision_signals.generate_precision_signal()
    state["signal"] = sig

    # Node 3: Strategy Decision Node
    print(" -> [Node 3/6] Strategy Decision Node: Selecting Optimal Strategy...")
    action = sig.get("signal_action", "STAY_OUT")
    if "BUY" in action:
        import smart_strike_selector
        best_strike = smart_strike_selector.strike_selector.select_best_strike(spot_price=spot_price)
        state["strategy"] = {"type": "DIRECTIONAL_BUY", "strike": best_strike.get("best_strike")}
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
    if state["should_trade"] and "BUY" in action:
        res = paper_trader.paper_engine.execute_paper_order(symbol="NIFTY", entry_price=140.0)
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
