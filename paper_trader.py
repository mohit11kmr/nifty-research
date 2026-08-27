"""Live Paper Trading Engine for NIFTY Research.

Enables simulated virtual trading without risking real capital.
Tracks virtual portfolio, open positions, MTM PnL, and performance metrics.

Phase A (paper execution integrity): new orders/closes are routed through the
order/position lifecycle FSM in paper_execution.py, which derives position
state from fills and mirrors every valid execution/close into the immutable
Ground Truth ledger with REAL provenance. Pre-Phase-A legacy positions in
`open_positions` are preserved untouched and managed through the legacy path
(LEGACY provenance). See audit/PHASE-A-PAPER-INTEGRITY.md.
"""
import os
import sys
import json
import datetime as dt
import pandas as pd

import paper_execution

ACCOUNT_FILE = os.path.join("data", "paper_account.json")


class PaperTrader:
    """Virtual Paper Trading Manager."""

    def __init__(self, initial_capital=100000.0):
        self.initial_capital = float(initial_capital)
        self.account = self._load_account()

    def _load_account(self):
        os.makedirs("data", exist_ok=True)
        if os.path.exists(ACCOUNT_FILE):
            try:
                with open(ACCOUNT_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass

        default_account = {
            "initial_capital": self.initial_capital,
            "cash_balance": self.initial_capital,
            "realized_pnl": 0.0,
            "open_positions": [],
            "closed_trades": [],
            "last_updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
        }
        self._save_account(default_account)
        return default_account

    def _save_account(self, account_data=None):
        if account_data is None:
            account_data = self.account
        account_data["last_updated"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
        with open(ACCOUNT_FILE, "w") as f:
            json.dump(account_data, f, indent=2)

    def execute_paper_order(self, symbol="NIFTY", side="BUY", option_type="CE", strike=24500, lots=1, lot_size=75, entry_price=150.0, sl_price=100.0, target_price=250.0):
        """Execute a simulated paper trade through the Phase A FSM.

        The order goes SUBMITTED -> ACCEPTED -> FILLED; fills mirror into the
        Ground Truth ledger with REAL provenance, and position state is
        derived from fills. Legacy semantics are preserved: REJECTED is
        returned for insufficient virtual margin, EXECUTED carries the
        position dict (position_id = position_ref).
        """
        quantity = lots * lot_size

        engine = paper_execution.PaperExecutionEngine(account_file=ACCOUNT_FILE)
        submit = engine.submit_order(
            symbol=symbol, side=side, option_type=option_type, strike=strike,
            lots=lots, lot_size=lot_size, entry_price=entry_price,
            sl_price=sl_price, target_price=target_price,
        )
        if submit["status"] == "REJECTED":
            return {"status": "REJECTED", "reason": submit.get("reason") or "Insufficient Virtual Margin"}

        order_id = submit["order_id"]
        engine.accept_order(order_id)
        # ADOPT-03: fill is slipped adversarially against the requested entry
        # price (BUY *1.015 / SELL *0.985) unless an exact fill is needed.
        fill = engine.fill_order(order_id, quantity, price=None,
                                 reference_price=float(entry_price))
        order = engine._find_order(order_id)
        fill_price = float(fill["fill"]["fill_price"])

        position = {
            "position_id": order.get("position_ref"),
            "order_id": order_id,
            "timestamp": order["fills"][0]["timestamp"],
            "symbol": symbol,
            "side": side,
            "option_type": option_type,
            "strike": strike,
            "lots": lots,
            "quantity": quantity,
            "entry_price": fill_price,
            "requested_price": float(entry_price),
            "slippage_amount": float(fill["fill"]["slippage_amount"]),
            "commission": float(fill["fill"]["commission"]),
            "sl_price": sl_price,
            "target_price": target_price,
            "invested_amount": fill_price * quantity,
            "status": "OPEN",
        }
        print(f"✅ [PAPER TRADE EXECUTED] {side} {symbol} {strike} {option_type} @ ₹{fill_price} "
              f"(ref ₹{entry_price}, slip ₹{fill['fill']['slippage_amount']}, "
              f"fee ₹{fill['fill']['commission']}) ({lots} Lot/75 Qty) | Order {order_id}")
        return {"status": "EXECUTED", "position": position}

    def close_paper_position(self, position_id, exit_price):
        """Close an open paper position and compute realized PnL.

        Phase A: positions created through the FSM (position_ref) are closed
        via the paper execution engine, which mirrors the exit execution and
        closes the Ground Truth position. Pre-Phase-A legacy positions remain
        on the legacy path (LEGACY provenance, never upgraded).
        """
        legacy_ids = [str(p["position_id"]) for p in self.account["open_positions"]]
        if str(position_id) not in legacy_ids:
            try:
                engine = paper_execution.PaperExecutionEngine(account_file=ACCOUNT_FILE)
                return engine.close_position(str(position_id), float(exit_price))
            except ValueError as exc:
                return {"status": "ERROR", "reason": str(exc)}

        open_positions = self.account["open_positions"]
        target_pos = None

        for pos in open_positions:
            if pos["position_id"] == position_id:
                target_pos = pos
                break

        if not target_pos:
            return {"status": "ERROR", "reason": "Position ID not found"}

        quantity = target_pos["quantity"]
        entry_price = target_pos["entry_price"]
        side = target_pos["side"]

        if side.upper() == "BUY":
            pnl = (exit_price - entry_price) * quantity
        else:
            pnl = (entry_price - exit_price) * quantity

        invested_amount = target_pos.get("invested_amount") or (entry_price * quantity)
        pnl_pct = (pnl / invested_amount) * 100.0

        target_pos["exit_price"] = exit_price
        target_pos["exit_timestamp"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
        target_pos["realized_pnl"] = round(pnl, 2)
        target_pos["pnl_pct"] = round(pnl_pct, 2)
        target_pos["status"] = "CLOSED"

        self.account["open_positions"].remove(target_pos)
        self.account["closed_trades"].append(target_pos)
        self.account["cash_balance"] += invested_amount + pnl
        self.account["realized_pnl"] += pnl
        self._save_account()

        # Mirror the close into the immutable ground-truth ledger with an
        # honest exit reason (TARGET / STOP_LOSS / MANUAL).
        try:
            import ground_truth
            ledger = ground_truth.GroundTruthDB()
            exit_ts = target_pos["exit_timestamp"]
            exit_price = float(target_pos["exit_price"])
            if target_pos.get("target_price") and exit_price >= float(target_pos["target_price"]) * 0.999:
                reason = "TARGET"
            elif target_pos.get("sl_price") and exit_price <= float(target_pos["sl_price"]) * 1.001:
                reason = "STOP_LOSS"
            else:
                reason = "MANUAL"
            ledger.close_position(
                position_id=ledger.position_id_by_ref(target_pos["position_id"]),
                exit_price=exit_price,
                exit_timestamp=exit_ts, exit_reason=reason,
                provenance={"source": "paper_trader", "status": "LEGACY"},
            )
        except Exception as _gt_err:
            print(f"⚠️ [GROUND TRUTH] close mirror skipped: {_gt_err}")

        print(f"🛑 [PAPER POSITION CLOSED] PnL: ₹{pnl:+,.2f} ({pnl_pct:+.2f}%)")
        return {"status": "CLOSED", "trade": target_pos}

    def get_paper_account_summary(self):
        """Get live virtual account summary (cost-aware since ADOPT-03).

        Realized P&L is NET of fees + slippage; unrealized P&L and marked
        equity come from the read-only mark-to-market report (open FSM
        positions vs trusted research.db quotes). Legacy positions stay
        display-only and are never valued.
        """
        closed = self.account["closed_trades"]
        wins = [t for t in closed if t.get("realized_pnl", 0) > 0]
        win_rate = (len(wins) / len(closed) * 100) if closed else 0.0

        fsm = {}
        mtm = None
        engine = None
        try:
            engine = paper_execution.PaperExecutionEngine(account_file=ACCOUNT_FILE)
            fsm = engine.summary()
            mtm = engine.mark_to_market_report()
        except Exception:
            fsm = {}

        cash = float(engine.account["cash_balance"]) if engine else float(self.account["cash_balance"])
        realized = float(engine.account["realized_pnl"]) if engine else float(self.account["realized_pnl"])
        fees = float(engine.account.get("total_fees", 0.0)) if engine else float(self.account.get("total_fees", 0.0))
        slip = float(engine.account.get("total_slippage", 0.0)) if engine else float(self.account.get("total_slippage", 0.0))

        return {
            "account_status": "PAPER_TRADING_ACTIVE",
            "initial_capital": self.account["initial_capital"],
            "cash_balance": round(cash, 2),
            "realized_pnl": round(realized, 2),
            "total_fees": round(fees, 2),
            "total_slippage": round(slip, 2),
            "current_equity": round(cash + realized, 2),
            "unrealized_pnl": round(mtm["unrealized_pnl"], 2) if mtm else 0.0,
            "equity_marked": round(mtm["equity"], 2) if mtm else None,
            "mtm_position_count": mtm["position_count"] if mtm else 0,
            "total_open_positions": len(self.account["open_positions"]) + fsm.get("fsm_open_positions", 0),
            "total_closed_trades": len(closed),
            "paper_win_rate_pct": round(win_rate, 2),
            "open_positions": self.account["open_positions"],
            "fsm_order_count": fsm.get("fsm_orders", 0),
            "fsm_open_positions": fsm.get("fsm_open_positions", 0),
        }


    def run_exit_checks(self, quote_source=None, now=None):
        """ADOPT-04: evaluate open paper positions and auto-close triggered
        exits (STOP_LOSS / TAKE_PROFIT / EXPIRY_SQUARE_OFF) via the FSM."""
        engine = paper_execution.PaperExecutionEngine(account_file=ACCOUNT_FILE)
        return engine.run_exit_checks(quote_source=quote_source, now=now)

    def paper_exit_status(self, quote_source=None, now=None):
        """ADOPT-04: read-only exit/health snapshot for open paper positions."""
        engine = paper_execution.PaperExecutionEngine(account_file=ACCOUNT_FILE)
        return engine.paper_exit_status(quote_source=quote_source, now=now)


# Singleton instance
paper_engine = PaperTrader()

if __name__ == "__main__":
    print("=== TESTING LIVE PAPER TRADING ENGINE ===")
    summary = paper_engine.get_paper_account_summary()
    print(json.dumps(summary, indent=2))
