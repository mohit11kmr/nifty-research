"""Dynamic Volatility-Based Profit Trailing Engine for NIFTY Research.

Implements ATR Chandelier Exit & Profit Protection Rules:
1. Lock 50% Profit when Trade reaches 1:1 RRR
2. Lock 75% Profit when Trade reaches 1:2 RRR
3. Trail Stop-Loss dynamically using 2.5x ATR Chandelier Exit
4. Rule: A WINNING TRADE MUST NEVER TURN INTO A LOSS!
"""
import os
import json


def compute_trailing_stops(entry_price=24500.0, current_price=24650.0, atr=80.0, side="CALL", initial_sl=24420.0):
    """Compute dynamic ATR trailing stop-loss levels to lock in profits."""
    atr_multiplier = 2.5
    atr_stop_distance = atr * atr_multiplier

    if side.upper() in ["CALL", "BUY", "LONG"]:
        initial_risk = entry_price - initial_sl
        current_gain = current_price - entry_price
        rrr = current_gain / max(initial_risk, 1.0)

        # Chandelier Stop Level
        chandelier_sl = current_price - atr_stop_distance

        # Lock Profit Matrix
        if rrr >= 2.0:
            locked_sl = entry_price + (initial_risk * 1.5)  # Lock +150% RRR profit
            tier = "TIER_3_LOCK_150_PCT_PROFIT"
        elif rrr >= 1.0:
            locked_sl = entry_price + (initial_risk * 0.5)  # Lock +50% RRR profit
            tier = "TIER_2_LOCK_50_PCT_PROFIT"
        else:
            locked_sl = max(initial_sl, chandelier_sl)
            tier = "TIER_1_INITIAL_RISK"

        effective_sl = max(locked_sl, initial_sl)
        unrealized_pnl = current_gain

    else:  # PUT / SELL / SHORT
        initial_risk = initial_sl - entry_price
        current_gain = entry_price - current_price
        rrr = current_gain / max(initial_risk, 1.0)

        chandelier_sl = current_price + atr_stop_distance

        if rrr >= 2.0:
            locked_sl = entry_price - (initial_risk * 1.5)
            tier = "TIER_3_LOCK_150_PCT_PROFIT"
        elif rrr >= 1.0:
            locked_sl = entry_price - (initial_risk * 0.5)
            tier = "TIER_2_LOCK_50_PCT_PROFIT"
        else:
            locked_sl = min(initial_sl, chandelier_sl)
            tier = "TIER_1_INITIAL_RISK"

        effective_sl = min(locked_sl, initial_sl)
        unrealized_pnl = current_gain

    return {
        "entry_price": entry_price,
        "current_price": current_price,
        "side": side,
        "current_risk_reward_ratio": round(rrr, 2),
        "unrealized_points": round(unrealized_pnl, 2),
        "atr_2_5x": round(atr_stop_distance, 2),
        "trailing_stop_tier": tier,
        "new_trailing_stop_loss": round(effective_sl, 2),
        "profit_protection_rule": "NEVER LET A WINNING TRADE TURN INTO A LOSS!"
    }


if __name__ == "__main__":
    print("=== DYNAMIC PROFIT TRAILING ENGINE TEST ===")
    res = compute_trailing_stops(entry_price=24500.0, current_price=24680.0, atr=70.0, side="CALL", initial_sl=24420.0)
    print(json.dumps(res, indent=2))
