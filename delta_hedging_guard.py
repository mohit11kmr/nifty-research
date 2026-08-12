"""Swarm Dynamic Delta-Hedging Guard for NIFTY Research.

Adopted from updated trading/trading_bot architecture:
Monitors portfolio net delta exposure and triggers automatic delta-neutral hedging
when net delta exceeds risk threshold limits (|Net Delta| > 500).
"""
import os
import json
import datetime as dt


class SwarmDeltaHedgingGuard:
    """Dynamic Delta-Hedging & Risk Neutralization Guard."""

    def __init__(self, delta_threshold=500.0):
        self.delta_threshold = delta_threshold

    def evaluate_portfolio_delta(self, net_delta=650.0, net_gamma=0.04, net_theta=-45.0, net_vega=120.0):
        """Evaluate net portfolio greeks and generate hedge recommendations."""
        greeks_state = {
            "net_delta": net_delta,
            "net_gamma": net_gamma,
            "net_theta": net_theta,
            "net_vega": net_vega
        }

        if abs(net_delta) > self.delta_threshold:
            hedge_needed = True
            hedge_side = "BUY_PE" if net_delta > 0 else "BUY_CE"
            delta_to_hedge = abs(net_delta) - 100.0  # Bring back within +/- 100
            lots_needed = max(1, int(delta_to_hedge / 37.5))  # Approx 0.5 delta per option lot (75 qty)

            recommendation = {
                "action": "AUTO_HEDGE",
                "reason": f"Net Delta exposure ({net_delta:+.1f}) exceeded safety threshold (+/-{self.delta_threshold:.0f}).",
                "recommended_side": hedge_side,
                "suggested_lots": lots_needed,
                "target_delta_reduction": round(delta_to_hedge, 1),
                "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
            }
        else:
            hedge_needed = False
            recommendation = {
                "action": "NO_HEDGE_REQUIRED",
                "reason": f"Net Delta exposure ({net_delta:+.1f}) is within safe bounds (+/-{self.delta_threshold:.0f}).",
                "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
            }

        return {
            "guard_status": "DELTA_GUARD_EVALUATED",
            "hedge_needed": hedge_needed,
            "greeks_state": greeks_state,
            "hedge_recommendation": recommendation
        }


# Singleton instance
delta_guard = SwarmDeltaHedgingGuard()

if __name__ == "__main__":
    print("=== TESTING SWARM DYNAMIC DELTA-HEDGING GUARD ===")
    res = delta_guard.evaluate_portfolio_delta(net_delta=650.5)
    print(json.dumps(res, indent=2))
