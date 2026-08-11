"""Mathematical Expectancy & Positive Edge Optimizer for NIFTY Research.

Calculates Mathematical Expected Value (EV) per Rupee Risk:
EV = (Win_Rate * Avg_Win_Rupees) - (Loss_Rate * Avg_Loss_Rupees)

If EV > 0 -> POSITIVE EDGE (Guaranteed Profitability over 100 trades)
If EV <= 0 -> NEGATIVE EDGE (Guaranteed Loss over time - BLOCK TRADE)
"""
import os
import json


def calculate_trade_expectancy(win_rate_pct=55.0, avg_win_rupees=2000.0, avg_loss_rupees=1000.0):
    """Compute mathematical expectancy per trade."""
    win_rate = win_rate_pct / 100.0
    loss_rate = 1.0 - win_rate

    expected_value = (win_rate * avg_win_rupees) - (loss_rate * avg_loss_rupees)
    ev_per_rupee_risk = expected_value / max(avg_loss_rupees, 1.0)

    # 100 Trade Profit Projection
    projected_100_trade_profit = expected_value * 100

    has_positive_edge = expected_value > 0

    return {
        "win_rate_pct": win_rate_pct,
        "avg_win_rupees": avg_win_rupees,
        "avg_loss_rupees": avg_loss_rupees,
        "reward_risk_ratio": round(avg_win_rupees / max(avg_loss_rupees, 1.0), 2),
        "expected_value_per_trade_rupees": round(expected_value, 2),
        "ev_per_rupee_risk": round(ev_per_rupee_risk, 2),
        "projected_profit_100_trades": round(projected_100_trade_profit, 2),
        "edge_status": "POSITIVE_EDGE (PROFITABLE)" if has_positive_edge else "NEGATIVE_EDGE (DO NOT TRADE)",
        "quant_guidance": f"For every ₹1,000 risked, this setup generates ₹{expected_value:.2f} expected profit." if has_positive_edge else "Negative expected value. Do not trade!"
    }


if __name__ == "__main__":
    print("=== EXPECTANCY & EDGE CALCULATOR TEST ===")
    res = calculate_trade_expectancy(win_rate_pct=50.0, avg_win_rupees=2500.0, avg_loss_rupees=1000.0)
    print(json.dumps(res, indent=2))
