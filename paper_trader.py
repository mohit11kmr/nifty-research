"""Live Paper Trading Engine for NIFTY Research.

Enables simulated virtual trading without risking real capital.
Tracks virtual portfolio, open positions, MTM PnL, and performance metrics.
"""
import os
import sys
import json
import datetime as dt
import pandas as pd

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
        """Execute a simulated paper trade."""
        quantity = lots * lot_size
        total_investment = entry_price * quantity

        if total_investment > self.account["cash_balance"]:
            return {"status": "REJECTED", "reason": "Insufficient Virtual Margin"}

        pos_id = f"POS_{len(self.account['closed_trades']) + len(self.account['open_positions']) + 1}_{dt.datetime.now().strftime('%H%M%S')}"

        position = {
            "position_id": pos_id,
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
            "symbol": symbol,
            "side": side,
            "option_type": option_type,
            "strike": strike,
            "lots": lots,
            "quantity": quantity,
            "entry_price": entry_price,
            "sl_price": sl_price,
            "target_price": target_price,
            "invested_amount": total_investment,
            "status": "OPEN"
        }

        self.account["cash_balance"] -= total_investment
        self.account["open_positions"].append(position)
        self._save_account()

        print(f"✅ [PAPER TRADE EXECUTED] {side} {symbol} {strike} {option_type} @ ₹{entry_price} ({lots} Lot/75 Qty)")
        return {"status": "EXECUTED", "position": position}

    def close_paper_position(self, position_id, exit_price):
        """Close an open paper position and compute realized PnL."""
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

        pnl_pct = (pnl / target_pos["invested_amount"]) * 100.0

        target_pos["exit_price"] = exit_price
        target_pos["exit_timestamp"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
        target_pos["realized_pnl"] = round(pnl, 2)
        target_pos["pnl_pct"] = round(pnl_pct, 2)
        target_pos["status"] = "CLOSED"

        self.account["open_positions"].remove(target_pos)
        self.account["closed_trades"].append(target_pos)
        self.account["cash_balance"] += target_pos["invested_amount"] + pnl
        self.account["realized_pnl"] += pnl
        self._save_account()

        print(f"🛑 [PAPER POSITION CLOSED] PnL: ₹{pnl:+,.2f} ({pnl_pct:+.2f}%)")
        return {"status": "CLOSED", "trade": target_pos}

    def get_paper_account_summary(self):
        """Get live virtual account summary."""
        closed = self.account["closed_trades"]
        wins = [t for t in closed if t.get("realized_pnl", 0) > 0]
        win_rate = (len(wins) / len(closed) * 100) if closed else 0.0

        return {
            "account_status": "PAPER_TRADING_ACTIVE",
            "initial_capital": self.account["initial_capital"],
            "cash_balance": round(self.account["cash_balance"], 2),
            "realized_pnl": round(self.account["realized_pnl"], 2),
            "current_equity": round(self.account["cash_balance"] + self.account["realized_pnl"], 2),
            "total_open_positions": len(self.account["open_positions"]),
            "total_closed_trades": len(closed),
            "paper_win_rate_pct": round(win_rate, 2),
            "open_positions": self.account["open_positions"],
        }


# Singleton instance
paper_engine = PaperTrader()

if __name__ == "__main__":
    print("=== TESTING LIVE PAPER TRADING ENGINE ===")
    summary = paper_engine.get_paper_account_summary()
    print(json.dumps(summary, indent=2))
