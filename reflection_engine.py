"""Reflection & Self-Critique Hypothesis Engine for NIFTY Research.

Adopted from Quantum Nexus architecture:
Implements "Think -> Act -> Observe -> Reflect" loop.
Scores trade history, generates single-variable improvement hypotheses,
and appends hypotheses to data/reflection_hypotheses.jsonl.
"""
import os
import sys
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))

HYPOTHESES_FILE = os.path.join("data", "reflection_hypotheses.jsonl")


def run_reflection_loop():
    """Analyze recent performance and generate a single-variable hypothesis."""
    os.makedirs("data", exist_ok=True)

    # 1. Read trade history
    import paper_trader
    summary = paper_trader.paper_engine.get_paper_account_summary()
    closed_trades = summary.get("total_closed_trades", 0)
    win_rate = summary.get("paper_win_rate_pct", 0.0)

    # 2. Formulate hypothesis
    if win_rate < 50.0:
        hypothesis = {
            "hypothesis_id": f"HYP_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
            "observation": f"Win Rate is {win_rate:.1f}% across {closed_trades} trades.",
            "variable_to_test": "stop_loss_multiplier",
            "proposed_change": "Increase ATR Stop-Loss Multiplier from 1.5x to 2.0x to avoid noise stop-outs.",
            "status": "HYPOTHESIS_PROPOSED"
        }
    else:
        hypothesis = {
            "hypothesis_id": f"HYP_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
            "observation": f"Win Rate is healthy at {win_rate:.1f}%.",
            "variable_to_test": "target_profit_ratio",
            "proposed_change": "Expand Target 2 Risk-Reward Ratio from 1:2.0 to 1:2.5 to trail winners further.",
            "status": "HYPOTHESIS_ACTIVE"
        }

    # 3. Append to JSONL ledger
    with open(HYPOTHESES_FILE, "a") as f:
        f.write(json.dumps(hypothesis) + "\n")

    print(f"💡 [Reflection Engine] Generated Hypothesis {hypothesis['hypothesis_id']}: {hypothesis['proposed_change']}")
    return hypothesis


if __name__ == "__main__":
    print("=== TESTING REFLECTION ENGINE ===")
    res = run_reflection_loop()
    print(json.dumps(res, indent=2))
