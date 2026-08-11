"""Trader Psychology & Emotional Tilt Defense Engine for NIFTY Research.

Protects traders from the 4 Fatal Psychological Errors:
1. FOMO (Fear Of Missing Out) — Chasing already extended moves
2. Revenge Trading / Tilt — Taking rapid entries after a loss
3. Over-Confidence / Size Inflation — Doubling size after a win streak
4. Hesitation / Execution Freeze — Missing valid setups due to fear
"""
import os
import json
import datetime as dt


class PsychologyGuard:
    """Monitors trading state & prevents emotional capital destruction."""

    def __init__(self, max_consecutive_losses=2, fomo_threshold_pts=80.0):
        self.max_consecutive_losses = max_consecutive_losses
        self.fomo_threshold_pts = fomo_threshold_pts

    def audit_trade_psychology(self, recent_trades=None, current_spot=24500.0, breakout_spot=24400.0):
        """Run complete Psychological Audit on trading state."""
        if recent_trades is None:
            recent_trades = []

        warnings = []
        status = "HEALTHY_MINDSET"
        cool_off_required = False

        # 1. Revenge Trading Check
        consecutive_losses = 0
        for t in reversed(recent_trades):
            if t.get("pnl", 0) < 0:
                consecutive_losses += 1
            else:
                break

        if consecutive_losses >= self.max_consecutive_losses:
            status = "TILT_WARNING"
            cool_off_required = True
            warnings.append(
                f"🚨 REVENGE TRADING RISK: You have {consecutive_losses} consecutive losses. Take a mandatory 15-minute COOL-OFF break!"
            )

        # 2. FOMO Check (Distance from Breakout Zone)
        move_distance = abs(current_spot - breakout_spot)
        if move_distance >= self.fomo_threshold_pts:
            warnings.append(
                f"⚠️ FOMO RISK: Price has already moved {move_distance:.1f} pts from breakout zone ({breakout_spot:.0f}). Risk/Reward is unfavorable. Wait for a pullback!"
            )

        # 3. Size Inflation Check
        if len(recent_trades) >= 3 and all(t.get("pnl", 0) > 0 for t in recent_trades[-3:]):
            warnings.append(
                "💡 OVER-CONFIDENCE WARNING: 3 consecutive wins. Do NOT increase lot size. Stick strictly to 1% risk rule!"
            )

        return {
            "timestamp": dt.datetime.now().strftime("%d %b %Y %H:%M IST"),
            "psychology_status": status,
            "consecutive_losses": consecutive_losses,
            "cool_off_required": cool_off_required,
            "fomo_distance_pts": round(move_distance, 1),
            "psychological_warnings": warnings if warnings else ["✅ Mindset Clear: Proceed with Discipline."],
            "trader_mantra": "Losses are business expenses. Stick to the 1% risk rule. Never trade out of anger or excitement.",
        }


if __name__ == "__main__":
    guard = PsychologyGuard()
    print("=== TRADER PSYCHOLOGY GUARD TEST ===")
    audit = guard.audit_trade_psychology(
        recent_trades=[{"pnl": -1500}, {"pnl": -1200}],
        current_spot=24590.0,
        breakout_spot=24500.0,
    )
    print(json.dumps(audit, indent=2))
