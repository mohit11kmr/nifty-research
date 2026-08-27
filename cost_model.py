"""ADOPT-03: deterministic paper cost model.

Parameters are re-used from the existing backtester (backtester.py:
``COST_PER_TRADE = 40.0`` = brokerage + taxes approx per trade, and
``SLIPPAGE_PCT = 0.015`` = adverse bid-ask slippage on option premium).

These are PROJECT-LEVEL SIMULATION ASSUMPTIONS, NOT actual broker charges.
No broker-specific fees are invented. Every function is pure and
deterministic: identical inputs always produce identical outputs.

Accounting convention (paper report):
    realized_net_pnl = realized_gross_pnl - realized_fees - realized_slippage
where:
    realized_gross_pnl = (exit_reference - entry_reference) * qty  (signed)
    realized_fees      = commissions (₹ cost_per_trade per order)
    realized_slippage  = adverse fill-price deltas vs reference prices
Slippage is booked inside the recorded fill price (like a real broker); the
Ground Truth outcome therefore nets exactly like the paper account.
"""
import os

# Simulation assumptions (sourced from backtester.py, NOT broker charges).
COST_PER_TRADE = 40.0          # brokerage + taxes per trade (approx)
SLIPPAGE_PCT = 0.015           # 1.5% adverse bid-ask slippage on option premium

DEFAULT_ACCOUNT_FILE = os.path.join("data", "paper_account.json")


class CostModel:
    """Pure, deterministic cost math for paper fills and positions."""

    def __init__(self, cost_per_trade=COST_PER_TRADE, slippage_pct=SLIPPAGE_PCT):
        self.cost_per_trade = float(cost_per_trade)
        self.slippage_pct = float(slippage_pct)

    # ------------------------------------------------------------------
    # commission
    # ------------------------------------------------------------------
    def commission_for_fill(self, order, fill_quantity):
        """Fixed ₹cost_per_trade per order, allocated across fills by qty.

        Multiple fills of one order never pay the fixed charge more than once
        (sum of per-fill allocations == cost_per_trade exactly).
        """
        qty = int(order.get("quantity") or 0)
        if qty <= 0:
            return round(self.cost_per_trade, 2)
        return round(self.cost_per_trade * int(fill_quantity) / qty, 2)

    # ------------------------------------------------------------------
    # slippage
    # ------------------------------------------------------------------
    def slippage_price(self, side, reference_price):
        """Adverse deterministic fill price from a reference price.

        BUY fills at/above reference; SELL fills at/below reference.
        Returns None if no valid reference (nothing can be fabricated).
        """
        if reference_price is None or float(reference_price) <= 0:
            return None
        ref = float(reference_price)
        if str(side).upper() == "SELL":
            return round(ref * (1 - self.slippage_pct), 2)
        return round(ref * (1 + self.slippage_pct), 2)

    def slippage_amount(self, side, fill_price, reference_price, quantity):
        """Adverse slippage in ₹ for a fill (always non-negative)."""
        if fill_price is None or reference_price is None:
            return 0.0
        return round(abs(float(fill_price) - float(reference_price))
                     * int(quantity), 2)

    def slippage_pct_used(self, fill_price, reference_price):
        """Slippage as % of the reference price (0 if no reference)."""
        if fill_price is None or not reference_price:
            return 0.0
        ref = float(reference_price)
        if ref <= 0:
            return 0.0
        return round(abs(float(fill_price) - ref) / ref * 100.0, 2)

    # ------------------------------------------------------------------
    # aggregates
    # ------------------------------------------------------------------
    def total_cost(self, commission, slippage_amount):
        """Direct cost attributable to a fill (₹)."""
        return round(float(commission) + float(slippage_amount), 2)
