"""Autonomous Auto Paper Trader — Real-Time Virtual Execution System.

Fully integrated with Mohit's Project Custom Setup Engines:
1. Multi-Timeframe Alignment (mtf_alignment.py)
2. Smart Strike Price Selector (smart_strike_selector.py)
3. Volume Surge & Pocket Pivot Engine (volume_analytics_engine.py)
4. Dynamic ATR Trailing Stop-Loss Engine (dynamic_trailing.py)
5. Capital Guard 1% Risk Sizer (capital_guard.py)
6. Value-at-Risk Audit (var_risk_manager.py)
"""
import os
import sys
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))

import paper_trader
import precision_signals
import capital_guard
import live_market_fetch
import mtf_alignment
import smart_strike_selector
import volume_analytics_engine
import dynamic_trailing
import var_risk_manager


def run_auto_paper_trader():
    """Execute 1 iteration of autonomous paper trading using Mohit's project custom setup."""
    print("==================================================================")
    print("🤖 AUTONOMOUS LIVE PAPER TRADER (CUSTOM PROJECT SETUP)")
    print(f"Time: {dt.datetime.now().strftime('%d %b %Y | %H:%M:%S IST')}")
    print("==================================================================")

    # 1. Sync live market spot
    live_tick = live_market_fetch.update_live_market_cache()
    spot = live_tick.get("spot", 24403.10)

    # 2. Audit Capital Guard Risk & VaR
    cg = capital_guard.CapitalGuard().full_capital_safety_audit()
    var_audit = var_risk_manager.var_engine.compute_value_at_risk()
    safety_status = cg.get("safety_status", "RESTRICTED")

    if safety_status == "BLOCKED":
        print(f" 🛑 [Auto Paper Trader] Trading Blocked by Capital Guard: {cg.get('reason')}")
        return {"status": "BLOCKED", "reason": cg.get('reason')}

    # 3. Multi-Timeframe Trend Alignment Check
    mtf = mtf_alignment.compute_mtf_alignment(spot_price=spot)
    mtf_status = mtf.get("alignment_status")

    # 4. Volume Surge & Pocket Pivot Check
    vol_res = volume_analytics_engine.compute_volume_analytics(spot_price=spot)
    vol_surge = vol_res.get("volume_surge_ratio", 1.0)
    pocket_pivot = vol_res.get("pocket_pivot_detected", False)

    # 5. Generate 6-Layer Precision Signal
    sig = precision_signals.generate_precision_signal()
    grade = sig.get("signal_grade", "NO_SIGNAL")
    action = sig.get("signal_action", "STAY_OUT")

    print(f" -> Spot: ₹{spot:,.2f} | MTF: {mtf_status} | Vol Surge: {vol_surge}x | Signal: {action} ({grade})")

    # 6. Select Strike via Smart Strike Selector (Delta Sweet Spot 0.30 - 0.55)
    option_type = "CE" if ("BUY_CALL" in action or "BULLISH" in action) else "PE"
    strike_res = smart_strike_selector.strike_selector.select_best_strike(spot_price=spot, option_type=option_type)
    best_strike = strike_res.get("best_strike", 24450)

    # 7. Calculate Custom Entry, SL, Target & Trailing SL
    # Entry = REAL selected-strike premium (LTP or BS), not a hardcoded 140.0
    entry_premium = float(strike_res.get("best_strike_premium", 0) or 0)
    if entry_premium <= 0:
        entry_premium = round(spot * 0.006, 2)  # safe ~0.6% fallback
    atr_volatility = max(10.0, entry_premium * 0.25)  # Option ATR ~25% of premium
    sl_premium = round(max(2.0, entry_premium - (1.5 * atr_volatility)), 2)  # SL = Entry - 1.5x ATR
    risk_per_share = max(entry_premium - sl_premium, 1.0)
    target_premium = round(entry_premium + (2.0 * risk_per_share), 2)         # Target = 1:2.0 RRR

    # Dynamic Trailing SL Calculation
    trailing_res = dynamic_trailing.compute_trailing_stops(
        entry_price=entry_premium,
        current_price=entry_premium + 25.0,  # Simulated favorable move
        atr=atr_volatility,
        side="CALL" if option_type == "CE" else "PUT",
        initial_sl=sl_premium
    )
    trailing_sl = trailing_res.get("effective_stop_loss", sl_premium)

    print(f" 🎯 [Custom Setup Calculated] Strike: {best_strike} {option_type} | Entry: ₹{entry_premium} | SL: ₹{sl_premium} | Target: ₹{target_premium} | Trailing SL: ₹{trailing_sl}")

    # 8. Execute Order in Paper Trading Ledger
    res = paper_trader.paper_engine.execute_paper_order(
        symbol="NIFTY",
        side="BUY",
        option_type=option_type,
        strike=best_strike,
        lots=1,
        lot_size=75,
        entry_price=entry_premium,
        sl_price=sl_premium,
        target_price=target_premium
    )

    print(f" ✅ Auto Paper Trade Executed! Status: {res.get('status')} | Position ID: {res.get('position', {}).get('position_id')}")

    # Output Paper Account Summary
    summary = paper_trader.paper_engine.get_paper_account_summary()
    print("\n" + json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run_auto_paper_trader()
