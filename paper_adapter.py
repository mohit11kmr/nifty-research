"""Phase H1 v2 - Paper Adapter (interface proof).

Proves a CompiledStrategy can drive the EXISTING paper execution engine
(paper_execution.PaperExecutionEngine) without any modification to it.

The interface test (test_strategy_lab.py) creates a THROWAWAY engine rooted in
a temp directory (temp account json + temp ground-truth db) so nothing touches
the production paper account or the production database.
"""
import copy

import paper_execution


class PaperAdapter:
    def __init__(self, compiled):
        self.compiled = compiled

    def validate_order_shape(self, order):
        """Check an order dict has every key PaperExecutionEngine.submit_order
        requires (a pure signature check - does not submit anything)."""
        required = ("symbol", "side", "option_type", "strike", "lots",
                    "lot_size", "entry_price", "sl_price", "target_price",
                    "requested_price", "order_kind")
        missing = [k for k in required if k not in order]
        return (not missing), missing

    def submit_candidate(self, engine, candidate):
        """Submit every leg of a candidate as an OPEN order. Returns list of
        (order, engine-order) pairs; engine-order carries the status."""
        legs = self.compiled.build_order(candidate, context={})
        submitted = []
        for leg in legs:
            validated, missing = self.validate_order_shape(leg)
            if not validated:
                raise ValueError(f"order leg missing keys {missing}: {leg}")
            order = copy.deepcopy(leg)
            placed = engine.submit_order(
                symbol=order["symbol"], side=order["side"],
                option_type=order["option_type"], strike=order["strike"],
                lots=order["lots"], lot_size=order["lot_size"],
                entry_price=order["entry_price"], sl_price=order["sl_price"],
                target_price=order["target_price"],
                requested_price=order["requested_price"],
                order_kind=order["order_kind"])
            submitted.append((leg, placed))
        return submitted

    def close_candidate(self, engine, open_order):
        """Submit a CLOSE order for an open order. Returns engine result."""
        qty = open_order.get("quantity") or (open_order["lots"] * open_order.get("lot_size", 75))
        lots = open_order["lots"]
        lot_size = int(qty / lots) if lots else 75
        return engine.submit_order(
            symbol=open_order["symbol"], side="SELL" if open_order["side"] == "BUY" else "BUY",
            option_type=open_order["option_type"], strike=open_order["strike"],
            lots=lots, lot_size=lot_size,
            entry_price=open_order["requested_price"],
            sl_price=open_order.get("sl_price"), target_price=open_order.get("target_price"),
            requested_price=open_order["requested_price"], order_kind="CLOSE")
