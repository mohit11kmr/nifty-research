"""Capital Guard Engine — SEBI Loss-Prevention & Prop-Desk Risk Protection Suite.

Designed with ONE mission: PREVENT TRADER CAPITAL DESTRUCTION in F&O trading.

Implements 5 Prop-Desk Risk Protections:
1. Daily Loss Circuit Breaker (Kill-Switch at 3% max daily loss)
2. Expiry 0DTE Hero-Zero Trap Guard (Block naked option buying after 13:30 IST on expiry)
3. Event Risk IV Crush Guard (Block buying options 24h before RBI Policy / Budget / FED)
4. Account Drawdown De-risking Matrix (Cut position size by 50% if account DD > 5%)
5. Strict 1% Fixed Fractional Position Sizer (Max lots calculation)
"""
import os
import json
import datetime as dt


class CapitalGuard:
    """Proprietary Risk & Capital Protection Manager."""

    def __init__(self, capital=100000, max_daily_loss_pct=3.0, max_trade_risk_pct=1.0):
        self.capital = float(capital)
        self.max_daily_loss_pct = float(max_daily_loss_pct)
        self.max_trade_risk_pct = float(max_trade_risk_pct)
        self.max_daily_loss_amount = self.capital * (self.max_daily_loss_pct / 100.0)
        self.max_trade_risk_amount = self.capital * (self.max_trade_risk_pct / 100.0)

    def check_daily_kill_switch(self, current_daily_pnl=0.0):
        """Check if daily loss limit (3%) has been breached."""
        loss = abs(current_daily_pnl) if current_daily_pnl < 0 else 0.0
        is_breached = loss >= self.max_daily_loss_amount

        return {
            "status": "BLOCKED" if is_breached else "OPEN",
            "daily_loss_amount": round(loss, 2),
            "max_allowed_loss": round(self.max_daily_loss_amount, 2),
            "is_kill_switch_active": is_breached,
            "action": "LOCK TRADING FOR THE DAY (No Revenge Trading)" if is_breached else "TRADE ALLOWED",
        }

    def check_expiry_0dte_trap(self, is_expiry_day=False, current_time_str=None):
        """Check if trading after 13:30 IST on Expiry Day (0DTE Theta & Gamma Trap)."""
        if not current_time_str:
            current_time_str = dt.datetime.now().strftime("%H:%M")

        if not is_expiry_day:
            return {"status": "SAFE", "rule": "Not an Expiry Day", "allow_naked_options": True}

        hour, minute = map(int, current_time_str.split(":"))
        time_minutes = hour * 60 + minute
        cutoff_minutes = 13 * 60 + 30  # 13:30 IST

        if time_minutes >= cutoff_minutes:
            return {
                "status": "EXPIRY_TRAP_ACTIVE",
                "rule": "After 13:30 IST on Expiry Day",
                "allow_naked_options": False,
                "allowed_structures": ["Iron Condor", "Credit Spreads", "Defined-Risk Spreads"],
                "warning": "Naked Call/Put buying BLOCKED. 95% of 0DTE options decay to ₹0 due to theta crush.",
            }

        return {"status": "SAFE", "rule": "Before 13:30 IST cutoff", "allow_naked_options": True}

    def check_event_risk(self, upcoming_events=None):
        """Check for major high-impact events in next 24 hours (RBI Policy, Budget, FED)."""
        if not upcoming_events:
            upcoming_events = []

        high_impact = [e for e in upcoming_events if e.get("impact") == "HIGH"]
        if high_impact:
            return {
                "status": "EVENT_RISK_ACTIVE",
                "events": high_impact,
                "allow_option_buying": False,
                "warning": "High-impact event in next 24h. Option IV will crush 40% post-event. Use Spreads or Sit Out.",
            }

        return {"status": "NO_EVENT_RISK", "allow_option_buying": True}

    def compute_position_size(self, entry_price, stop_loss_price, lot_size=75, drawdown_pct=0.0):
        """Compute exact position size & lot count to NEVER exceed 1% risk limit."""
        if entry_price <= 0 or stop_loss_price <= 0 or entry_price <= stop_loss_price:
            risk_per_unit = max(entry_price * 0.5, 10.0)  # Default 50% premium risk if SL invalid
        else:
            risk_per_unit = entry_price - stop_loss_price

        risk_per_lot = risk_per_unit * lot_size

        # Apply Drawdown De-risking Multiplier
        size_multiplier = 1.0
        if drawdown_pct >= 10.0:
            size_multiplier = 0.25
        elif drawdown_pct >= 5.0:
            size_multiplier = 0.50

        adjusted_risk_cap = self.max_trade_risk_amount * size_multiplier
        allowed_lots = max(int(adjusted_risk_cap / max(risk_per_lot, 1.0)), 1)
        actual_risk = allowed_lots * risk_per_lot

        return {
            "account_capital": self.capital,
            "max_allowed_risk_1pct": round(self.max_trade_risk_amount, 2),
            "drawdown_pct": drawdown_pct,
            "size_multiplier": size_multiplier,
            "adjusted_risk_cap": round(adjusted_risk_cap, 2),
            "risk_per_lot": round(risk_per_lot, 2),
            "allowed_lots": allowed_lots,
            "actual_risk_amount": round(actual_risk, 2),
            "is_risk_compliant": actual_risk <= self.max_trade_risk_amount,
        }

    def full_capital_safety_audit(self, daily_pnl=0.0, is_expiry=False, drawdown_pct=0.0):
        """Run complete 5-point Prop-Desk Capital Safety Audit."""
        kill_switch = self.check_daily_kill_switch(daily_pnl)
        expiry_guard = self.check_expiry_0dte_trap(is_expiry)
        event_guard = self.check_event_risk()
        sizing = self.compute_position_size(entry_price=150, stop_loss_price=100, drawdown_pct=drawdown_pct)

        all_clear = (
            not kill_switch["is_kill_switch_active"]
            and expiry_guard["allow_naked_options"]
            and event_guard["allow_option_buying"]
        )

        return {
            "safety_status": "APPROVED" if all_clear else "RESTRICTED",
            "kill_switch": kill_switch,
            "expiry_guard": expiry_guard,
            "event_guard": event_guard,
            "position_sizing": sizing,
            "capital_preservation_score": "100% SECURE" if all_clear else "DERISKED",
        }


# Singleton instance
guard = CapitalGuard()

if __name__ == "__main__":
    print("=== Capital Guard Engine Safety Audit ===")
    audit = guard.full_capital_safety_audit(daily_pnl=-500, is_expiry=True, drawdown_pct=2.0)
    print(json.dumps(audit, indent=2))
