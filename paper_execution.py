"""Paper Execution Engine — order/position lifecycle FSM + reconciliation.

Phase A (ADOPT-01 + ADOPT-02) implementation. Read/append-only against the
immutable Ground Truth ledger: this engine NEVER mutates historical ledger
facts. It only ever:
  * INSERTs new executions (one per fill) and new positions (one per FILLED
    position-opening order) into the ledger with REAL provenance, and
  * calls the ledger's sanctioned `close_position` (the only allowed mutation,
    touching only exit/status fields).

Phase B (ADOPT-03): deterministic cost model (commission + adverse slippage)
applied at fill time, position cost basis derived from fills, and
mark-to-market of open positions against trusted research.db quotes
(REAL/STALE/MISSING/INVALID - never fabricated). Realized P&L is net of fees
and slippage; unrealized P&L is separated; equity = cash + marked position
value. Open MTM never creates a Ground Truth outcome.

FSM:
    SUBMITTED -> ACCEPTED | REJECTED
    ACCEPTED  -> PARTIALLY_FILLED | FILLED | CANCELED
    PARTIALLY_FILLED -> PARTIALLY_FILLED | FILLED | CANCELED

Every order gets a stable `order_id`. Every fill records
`fill_id, order_id, quantity, fill_price, reference_price, requested_price,
slippage_amount, slippage_pct, commission, fees, transaction_cost,
total_cost, timestamp, execution_mode`. Position state is DERIVED FROM FILLS,
never hand-set.

Legacy paper positions (the stale pre-Phase-A `open_positions`) are kept
separate: they are never invented into the ledger, never retroactively
converted to REAL executions, and are classified LEGACY/UNKNOWN by the
read-only reconciliation report. A mismatch is always visible; historical
truth is never silently auto-corrected.
"""
import os
import json
import datetime as dt

import ground_truth
import paper_mtm
import exit_evaluator
from cost_model import CostModel, COST_PER_TRADE

DEFAULT_ACCOUNT_FILE = os.path.join("data", "paper_account.json")

ORDER_STATES = {
    "SUBMITTED", "ACCEPTED", "PARTIALLY_FILLED", "FILLED",
    "CANCELED", "REJECTED",
}
# Legal transitions. Terminal states (FILLED/CANCELED/REJECTED) have no exits.
VALID_TRANSITIONS = {
    "SUBMITTED": {"ACCEPTED", "REJECTED"},
    "ACCEPTED": {"PARTIALLY_FILLED", "FILLED", "CANCELED"},
    "PARTIALLY_FILLED": {"PARTIALLY_FILLED", "FILLED", "CANCELED"},
}
FILLABLE_STATES = {"ACCEPTED", "PARTIALLY_FILLED"}

GT_SOURCE = "paper_execution"
GT_PROV = {"status": "REAL", "source": GT_SOURCE, "execution_mode": "PAPER"}
_LEGACY_STATUS = {"LEGACY", "UNKNOWN"}


def _ist_ts():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")


def _derive_exit_reason(entry, sl_price, target_price, exit_price):
    """Deterministic exit-reason classification (mirrors paper_trader)."""
    if target_price and exit_price >= float(target_price) * 0.999:
        return "TARGET"
    if sl_price and exit_price <= float(sl_price) * 1.001:
        return "STOP_LOSS"
    return "MANUAL"


class PaperExecutionEngine:
    """Order lifecycle FSM + fill-derived positions + GT reconciliation.

    Persists to a JSON account file (default data/paper_account.json). The
    pre-existing legacy `open_positions` / `closed_trades` keys are preserved
    untouched; FSM state lives under the new `orders` key.
    """

    def __init__(self, account_file=None, gt_db_file=None, ledger=None):
        self.account_file = account_file or DEFAULT_ACCOUNT_FILE
        self._gt_db_file = gt_db_file
        self._ledger = ledger
        self._order_seq = 0
        self.cost_model = CostModel()
        self.exit_evaluator = exit_evaluator.ExitEvaluator()
        self.account = self._load()
        self._order_seq = self._max_seq()

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def _load(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.account_file)) or ".", exist_ok=True)
        account = {}
        if os.path.exists(self.account_file):
            try:
                with open(self.account_file) as f:
                    account = json.load(f)
            except (ValueError, OSError):
                account = {}
        defaults = {
            "initial_capital": 100000.0,
            "cash_balance": 100000.0,
            "realized_pnl": 0.0,
            "total_fees": 0.0,        # ADOPT-03: commissions charged on fills
            "total_slippage": 0.0,    # ADOPT-03: adverse fill-price deltas
            "open_positions": [],   # legacy, untouched
            "closed_trades": [],    # legacy, untouched
            "orders": [],           # Phase A FSM orders
            "last_updated": _ist_ts(),
        }
        for key, value in defaults.items():
            account.setdefault(key, value)
        if not os.path.exists(self.account_file):
            self._save_locked(account)
        return account

    def _save_locked(self, account):
        account["last_updated"] = _ist_ts()
        with open(self.account_file, "w") as f:
            json.dump(account, f, indent=2)

    def _save(self):
        self._save_locked(self.account)

    def _max_seq(self):
        """Monotonic sequence used for order_id / position_ref stability."""
        best = 0
        for order in self.account.get("orders") or []:
            oid = str(order.get("order_id", ""))
            try:
                best = max(best, int(oid.split("_")[-1]))
            except (ValueError, IndexError):
                pass
        for pos in (self.account.get("open_positions") or []) + (self.account.get("closed_trades") or []):
            ref = str(pos.get("position_id", ""))
            try:
                best = max(best, int(ref.split("_")[1]))
            except (ValueError, IndexError):
                pass
        return best

    def _next_order_id(self):
        while True:
            self._order_seq += 1
            oid = f"ORD_{dt.datetime.now().strftime('%H%M%S')}_{self._order_seq}"
            if not any(str(o.get("order_id")) == oid for o in self.account.get("orders") or []):
                return oid

    def _find_order(self, order_id):
        for order in self.account.get("orders") or []:
            if str(order.get("order_id")) == str(order_id):
                return order
        return None

    def _ledger_instance(self):
        if self._ledger is not None:
            return self._ledger
        if self._gt_db_file is not None:
            return ground_truth.GroundTruthDB(self._gt_db_file)
        return ground_truth.GroundTruthDB()

    # ------------------------------------------------------------------
    # FSM operations
    # ------------------------------------------------------------------
    def submit_order(self, symbol="NIFTY", side="BUY", option_type="CE", strike=24500,
                     lots=1, lot_size=75, entry_price=150.0, sl_price=None,
                     target_price=None, requested_price=None, order_kind="OPEN"):
        """Create an order in SUBMITTED (or REJECTED on insufficient cash).

        order_kind: "OPEN" opens a position (mirrored as a ledger position on
        FILL); "CLOSE" is a closing order (mirrors an exit execution + closes
        the ledger position, never creates one)."""
        side = str(side).upper()
        quantity = int(lots) * int(lot_size)
        requested_price = float(requested_price if requested_price is not None else entry_price)
        entry_price = float(entry_price)
        order_id = self._next_order_id()
        order = {
            "order_id": order_id,
            "timestamp": _ist_ts(),
            "symbol": symbol,
            "side": side,
            "option_type": option_type,
            "strike": strike,
            "lots": int(lots),
            "quantity": quantity,
            "requested_price": requested_price,
            "sl_price": sl_price,
            "target_price": target_price,
            "order_kind": order_kind,
            "status": "SUBMITTED",
            "fills": [],
            "position_ref": None,
            "closed_quantity": 0,
            "closed_by": None,
            "gt_position_id": None,
            "gt_execution_ids": [],
            "mirror_error": None,
            "reject_reason": None,
        }
        if side == "BUY":
            exposure = entry_price * quantity
            if exposure > float(self.account.get("cash_balance", 0.0)):
                order["status"] = "REJECTED"
                order["reject_reason"] = "Insufficient Virtual Margin"
        self.account.setdefault("orders", []).append(order)
        self._save()
        return {
            "status": order["status"],
            "order_id": order_id,
            "reason": order.get("reject_reason"),
            "order": order,
        }

    def _transition(self, order, new_state):
        if order["status"] not in VALID_TRANSITIONS or new_state not in VALID_TRANSITIONS[order["status"]]:
            raise ValueError(
                f"invalid transition {order['order_id']}: {order['status']} -> {new_state}")
        order["status"] = new_state

    def accept_order(self, order_id):
        order = self._find_order(order_id)
        if order is None:
            raise ValueError(f"order {order_id} not found")
        self._transition(order, "ACCEPTED")
        self._save()
        return order

    def reject_order(self, order_id, reason="REJECTED"):
        order = self._find_order(order_id)
        if order is None:
            raise ValueError(f"order {order_id} not found")
        self._transition(order, "REJECTED")
        order["reject_reason"] = reason
        self._save()
        return order

    def cancel_order(self, order_id, reason="CANCELED"):
        """Cancel remaining quantity (allowed from ACCEPTED / PARTIALLY_FILLED)."""
        order = self._find_order(order_id)
        if order is None:
            raise ValueError(f"order {order_id} not found")
        self._transition(order, "CANCELED")
        order["cancel_reason"] = reason
        self._save()
        return order

    def fill_order(self, order_id, quantity, price=None, reference_price=None,
                   apply_slippage=True, ts=None, commission=None,
                   execution_mode="PAPER"):
        """Fill `quantity` of an accepted order (partial or full).

        ADOPT-03 cost rules (deterministic, simulation assumptions):
          * requested_price  = the order's resting price (always recorded)
          * reference_price  = price used as the slippage baseline. When not
            given it defaults to the order's requested_price.
          * price            = the exact fill price. When None the cost model
            computes an adverse fill: BUY at ref*(1+slip%), SELL at
            ref*(1-slip%). When a value IS given it is taken as-is
            (no slippage recomputed against it).
          * commission       = ₹cost_per_trade per order, allocated across
            fills by quantity. Explicit override wins.

        Mirrors to GT (execution + position). Slippage is embedded in the
        fill price; the ledger execution records it as slippage=0.0 so the GT
        outcome nets exactly like the paper account.
        """
        order = self._find_order(order_id)
        if order is None:
            raise ValueError(f"order {order_id} not found")
        if order["status"] not in FILLABLE_STATES:
            raise ValueError(f"cannot fill order {order_id} in state {order['status']}")
        quantity = int(quantity)
        remaining = self._remaining(order)
        if quantity <= 0:
            raise ValueError("fill quantity must be positive")
        if quantity > remaining:
            raise ValueError(
                f"fill {quantity} exceeds remaining {remaining} for {order_id}")
        ts = ts or _ist_ts()

        requested_price = float(order.get("requested_price") or 0.0)
        ref = float(reference_price) if reference_price is not None else requested_price
        if price is not None:
            fill_price = float(price)
            used_slip = False
        else:
            slipped = self.cost_model.slippage_price(order["side"], ref)
            if slipped is None:
                raise ValueError(
                    f"no fill price and no reference price for {order_id}")
            fill_price = slipped
            used_slip = True
        if fill_price <= 0:
            raise ValueError(f"invalid fill price {fill_price}")

        commission = (float(commission)
                      if commission is not None
                      else self.cost_model.commission_for_fill(order, quantity))
        slip_amt = (self.cost_model.slippage_amount(order["side"], fill_price, ref, quantity)
                    if used_slip else 0.0)
        slip_pct = (self.cost_model.slippage_pct_used(fill_price, ref)
                    if used_slip else 0.0)

        fill = {
            "fill_id": f"{order_id}_F{len(order['fills']) + 1}",
            "order_id": order_id,
            "quantity": quantity,
            "fill_price": round(fill_price, 2),
            "price": round(fill_price, 2),          # back-compat alias
            "reference_price": ref,
            "requested_price": requested_price,
            "slippage_amount": round(slip_amt, 2),
            "slippage_pct": round(slip_pct, 2),
            "commission": round(commission, 2),
            "fees": round(commission, 2),
            "transaction_cost": round(commission + slip_amt, 2),
            "total_cost": round(commission + slip_amt, 2),
            "timestamp": ts,
            "execution_mode": execution_mode,
            "gt_execution_id": None,
            "mirror_error": None,
        }
        order["fills"].append(fill)
        self._apply_fill_cash(order, fill)
        new_state = "FILLED" if self._remaining(order) == 0 else "PARTIALLY_FILLED"
        order["status"] = new_state

        is_close = order.get("order_kind") == "CLOSE"
        if new_state == "FILLED" and order.get("position_ref") is None and not is_close:
            self._order_seq += 1
            order["position_ref"] = f"POS_{self._order_seq}_{dt.datetime.now().strftime('%H%M%S')}"

        self._mirror_fill_to_gt(order, fill)
        if order["status"] == "FILLED" and not is_close:
            self._mirror_position_to_gt(order)
        self._save()
        return {"status": order["status"], "order_id": order_id, "fill": fill}

    def _remaining(self, order):
        filled = sum(f.get("quantity", 0) for f in order.get("fills") or [])
        return int(order["quantity"]) - filled

    def _apply_fill_cash(self, order, fill):
        """Debit/credit cash at fill time; positions are derived from fills."""
        amount = float(fill["fill_price"]) * int(fill["quantity"])
        if str(order["side"]).upper() == "BUY":
            self.account["cash_balance"] = float(self.account.get("cash_balance", 0.0)) - amount
        else:
            self.account["cash_balance"] = float(self.account.get("cash_balance", 0.0)) + amount
        # costs are booked on the paper account (net P&L), not on cash
        self.account["total_fees"] = float(self.account.get("total_fees", 0.0)) + float(fill["fees"])
        self.account["total_slippage"] = float(self.account.get("total_slippage", 0.0)) + float(fill["slippage_amount"])

    # ------------------------------------------------------------------
    # Ground Truth mirroring (append-only INSERTs only)
    # ------------------------------------------------------------------
    def _mirror_fill_to_gt(self, order, fill):
        """Mirror one fill as one ledger execution. Idempotent per fill."""
        if fill.get("gt_execution_id") is not None:
            return fill["gt_execution_id"]
        ledger = self._ledger_instance()
        try:
            exec_id = ledger.record_execution(
                decision_id=None,
                symbol=order["symbol"], side=str(order["side"]).upper(),
                quantity=int(fill["quantity"]),
                requested_price=float(order.get("requested_price") or fill["fill_price"]),
                fill_price=float(fill["fill_price"]),
                execution_ts=fill["timestamp"], execution_mode="PAPER",
                estimated_fill=True, slippage=0.0,
                fees=float(fill.get("commission", 0.0)),
                broker_reference=fill["fill_id"],
                strike=order.get("strike"), option_type=order.get("option_type"),
                provenance=dict(GT_PROV),
            )
            fill["gt_execution_id"] = exec_id
            order.setdefault("gt_execution_ids", []).append(exec_id)
        except Exception as exc:  # surface as mismatch; never fake a success
            fill["mirror_error"] = f"execution mirror failed: {exc}"
            order["mirror_error"] = fill["mirror_error"]
            return None
        return exec_id

    def _mirror_position_to_gt(self, order):
        """Mirror a FILLED position-opening order as one ledger position."""
        if order.get("gt_position_id") is not None or not order.get("fills"):
            return order.get("gt_position_id")
        entry_fill = order["fills"][0]
        if entry_fill.get("gt_execution_id") is None:
            return None
        ledger = self._ledger_instance()
        try:
            avg_price = self._avg_entry(order)
            pos_id = ledger.record_position(
                entry_execution_id=entry_fill["gt_execution_id"],
                symbol=order["symbol"], side=str(order["side"]).upper(),
                quantity=int(order["quantity"]), entry_price=avg_price,
                entry_timestamp=entry_fill["timestamp"], status="OPEN",
                current_sl=order.get("sl_price"), current_tgt=order.get("target_price"),
                position_ref=order["position_ref"],
                strike=order.get("strike"), option_type=order.get("option_type"),
                provenance=dict(GT_PROV),
            )
            order["gt_position_id"] = pos_id
        except Exception as exc:
            order["mirror_error"] = f"position mirror failed: {exc}"
            return None
        return pos_id

    def _avg_entry(self, order):
        qty = sum(f.get("quantity", 0) for f in order["fills"])
        if qty <= 0:
            return 0.0
        return round(sum(f["fill_price"] * f["quantity"] for f in order["fills"]) / qty, 2)

    # ------------------------------------------------------------------
    # closing
    # ------------------------------------------------------------------
    def close_position(self, position_ref, exit_price, exit_reason=None, ts=None,
                       commission=None):
        """Close a FILLED open position with a single SELL close order.

        The close order is submitted, accepted and fully filled; the exit
        execution mirrors to the ledger and the ledger position is closed via
        the sanctioned `close_position` mutation. Only full-position closes
        are supported so paper and ledger quantities stay in lockstep.

        ADOPT-03: the close fill is slipped against the requested exit price
        (BUY at exit*1.015 / SELL at exit*0.985) unless an exact `exit_price`
        fill is wanted. Realized P&L booked on the paper account is NET:
        gross - fees - slippage, matching the Ground Truth outcome.
        """
        order = self._find_open_order_by_ref(position_ref)
        if order is None:
            raise ValueError(f"open position {position_ref} not found")
        remaining = order["quantity"] - int(order.get("closed_quantity", 0))
        if remaining <= 0:
            raise ValueError(f"position {position_ref} already closed")
        exit_price = float(exit_price)
        ts = ts or _ist_ts()
        exit_reason = exit_reason or _derive_exit_reason(
            self._avg_entry(order), order.get("sl_price"), order.get("target_price"), exit_price)
        entry = self._avg_entry(order)

        close_side = "SELL" if str(order["side"]).upper() == "BUY" else "BUY"
        submit = self.submit_order(
            symbol=order["symbol"], side=close_side, option_type=order["option_type"],
            strike=order.get("strike"), lots=1,
            lot_size=int(remaining), entry_price=exit_price,
            requested_price=exit_price, order_kind="CLOSE",
        )
        if submit["status"] == "REJECTED":
            raise ValueError(f"close order rejected: {submit.get('reason')}")
        close_order = self.accept_order(submit["order_id"])
        fill_res = self.fill_order(submit["order_id"], remaining,
                                   price=None, reference_price=exit_price,
                                   apply_slippage=True, ts=ts, commission=commission)
        exit_fill = fill_res["fill"]
        close_order["close_of"] = position_ref
        close_order["exit_reason"] = exit_reason
        close_order["entry_reference"] = order["position_ref"]

        order["closed_quantity"] = int(order.get("closed_quantity", 0)) + remaining
        order["closed_by"] = close_order["order_id"]

        sign = 1 if str(order["side"]).upper() == "BUY" else -1
        exit_fill_price = float(exit_fill["fill_price"])
        gross = round(sign * (exit_fill_price - entry) * remaining, 2)
        # Slippage is embedded in the recorded fill prices (like a real
        # broker), so it is already inside `gross`; only the round-trip order
        # commissions are booked separately. Net P&L therefore equals the
        # Ground Truth outcome exactly (GT receives the same fees and
        # slippage=0.0 because it is already priced in).
        round_trip_fees = self._round_trip_fees(order, close_order)
        exit_slip = float(exit_fill["slippage_amount"])
        realized = round(gross - round_trip_fees, 2)
        self.account["realized_pnl"] = round(
            float(self.account.get("realized_pnl", 0.0)) + realized, 2)

        self._mirror_close_to_gt(order, close_order)
        self._save()
        return {
            "status": "CLOSED",
            "order_id": close_order["order_id"],
            "position_ref": position_ref,
            "requested_exit_price": exit_price,
            "exit_price": exit_fill_price,
            "slippage_amount": exit_slip,
            "fees": round_trip_fees,
            "realized_gross": gross,
            "realized_net": realized,
            "exit_reason": exit_reason,
        }

    def _mirror_close_to_gt(self, order, close_order):
        if close_order.get("gt_close_status") == "MIRRORED":
            return
        ledger = self._ledger_instance()
        exit_fill = close_order["fills"][0]
        try:
            # The exit fill was already mirrored as a ledger execution by the
            # generic fill mirror (fill_order -> _mirror_fill_to_gt). Reuse it:
            # a single real exit execution must not become two ledger facts.
            exit_exec_id = exit_fill.get("gt_execution_id")
            if exit_exec_id is None:
                exit_exec_id = ledger.record_execution(
                    decision_id=None, symbol=close_order["symbol"],
                    side=str(close_order["side"]).upper(),
                    quantity=int(exit_fill["quantity"]),
                    requested_price=float(exit_fill["reference_price"] or exit_fill["fill_price"]),
                    fill_price=float(exit_fill["fill_price"]),
                    execution_ts=exit_fill["timestamp"], execution_mode="PAPER",
                    estimated_fill=True, slippage=0.0,
                    fees=float(exit_fill.get("commission", 0.0)),
                    broker_reference=exit_fill["fill_id"],
                    strike=close_order.get("strike"), option_type=close_order.get("option_type"),
                    provenance=dict(GT_PROV),
                )
                exit_fill["gt_execution_id"] = exit_exec_id
            # GT outcome must net exactly like the paper account: slippage is
            # already embedded in the fill prices, so the ledger records the
            # total round-trip commissions as fees and slippage=0.0.
            round_trip_fees = self._round_trip_fees(order, close_order)
            ledger.close_position(
                position_id=order["gt_position_id"], exit_price=float(exit_fill["fill_price"]),
                exit_timestamp=exit_fill["timestamp"],
                exit_reason=close_order.get("exit_reason", "MANUAL"),
                exit_side=str(close_order["side"]).upper(), fees=round_trip_fees, slippage=0.0,
                exit_execution_id=exit_exec_id,
                provenance=dict(GT_PROV),
            )
            close_order["gt_close_status"] = "MIRRORED"
        except Exception as exc:
            close_order["gt_close_status"] = "MIRROR_ERROR"
            close_order["mirror_error"] = f"close mirror failed: {exc}"

    def _round_trip_fees(self, order, close_order):
        """Total commissions charged for this position's entry + exit orders."""
        entry_fees = sum(float(f.get("commission", 0.0)) for f in order.get("fills") or [])
        exit_fees = sum(float(f.get("commission", 0.0)) for f in close_order.get("fills") or [])
        return round(entry_fees + exit_fees, 2)

    def _find_open_order_by_ref(self, position_ref):
        for order in self.account.get("orders") or []:
            if (str(order.get("position_ref")) == str(position_ref)
                    and order["status"] == "FILLED"
                    and int(order.get("closed_quantity", 0)) < int(order["quantity"])):
                return order
        return None

    # ------------------------------------------------------------------
    # derived position state (from fills)
    # ------------------------------------------------------------------
    def derived_positions(self):
        """Open positions derived strictly from fills + close activity."""
        out = []
        for order in sorted(self.account.get("orders") or [], key=lambda o: o["order_id"]):
            if order["status"] != "FILLED" or order.get("order_kind") == "CLOSE":
                continue
            remaining = int(order["quantity"]) - int(order.get("closed_quantity", 0))
            if remaining <= 0:
                continue
            out.append({
                "position_ref": order["position_ref"],
                "order_id": order["order_id"],
                "symbol": order["symbol"],
                "side": order["side"],
                "option_type": order["option_type"],
                "strike": order.get("strike"),
                "quantity": remaining,
                "entry_price": self._avg_entry(order),
                "entry_fees": round(sum(float(f.get("fees", 0.0)) for f in order.get("fills") or []), 2),
                "entry_slippage": round(sum(float(f.get("slippage_amount", 0.0)) for f in order.get("fills") or []), 2),
                "sl_price": order.get("sl_price"),
                "target_price": order.get("target_price"),
                "status": "OPEN",
                "gt_position_id": order.get("gt_position_id"),
                "timestamp": order["fills"][0]["timestamp"] if order["fills"] else order["timestamp"],
            })
        return out

    def orders(self):
        return sorted((dict(o) for o in self.account.get("orders") or []),
                      key=lambda o: o["order_id"])

    # ------------------------------------------------------------------
    # mark-to-market (ADOPT-03) - open positions against trusted quotes
    # ------------------------------------------------------------------
    def mark_to_market_report(self, quote_source=None, now=None):
        """Mark every derived open position to its latest trusted quote.

        * A position is marked at its contract quote when available
          (REAL/STALE). A STALE quote is still used for valuation but flagged.
        * When no trusted quote exists (MISSING/INVALID) the position is
          valued at its entry price and flagged - never guessed.
        * Total MTM (equity) = cash + sum(sign * mark_price * quantity).
          Realized P&L is NET of fees+slippage; unrealized P&L is computed
          vs the net cost basis (entry + entry fees + entry slippage).
        * This is read-only: it never creates a Ground Truth outcome and
          never mutates account state.
        """
        quote_source = quote_source or paper_mtm.ResearchDBQuoteSource()
        positions = self.derived_positions()
        marks = []
        total_mtm = 0.0
        total_unrealized = 0.0
        cash = float(self.account.get("cash_balance", 0.0))
        for pos in positions:
            quote = quote_source.get_quote(
                pos["symbol"], pos["strike"], pos["option_type"], now=now)
            status = quote.get("status")
            if quote.get("price") is not None and status in ("REAL", "STALE"):
                mark_price = float(quote["price"])
                basis = quote.get("price_basis")
            else:
                mark_price = float(pos["entry_price"])
                status = "NO_QUOTE" if status != "STALE" else "STALE"
                basis = "entry_fallback"
            sign = 1 if str(pos["side"]).upper() == "BUY" else -1
            qty = int(pos["quantity"])
            value = round(sign * mark_price * qty, 2)
            entry_cost = float(pos["entry_price"]) * qty
            # slippage is already embedded in the recorded entry fill price;
            # unrealized is marked vs net cost (entry value + entry fees)
            unrealized = round(value - (sign * entry_cost + float(pos["entry_fees"])), 2)
            cost_basis = round(sign * entry_cost + float(pos["entry_fees"]), 2)
            marks.append({
                "position_ref": pos["position_ref"],
                "symbol": pos["symbol"], "strike": pos["strike"],
                "option_type": pos["option_type"], "side": pos["side"],
                "quantity": qty, "entry_price": pos["entry_price"],
                "entry_fees": pos["entry_fees"], "entry_slippage": pos["entry_slippage"],
                "cost_basis": cost_basis,
                "quote_status": status, "price_basis": basis,
                "mark_price": round(mark_price, 2),
                "unrealized_pnl": unrealized,
                "quote_timestamp": quote.get("quote_timestamp"),
                "quote_age_s": quote.get("quote_age_s"),
            })
            total_mtm += value
            total_unrealized += unrealized
        total_mtm = round(total_mtm, 2)
        total_unrealized = round(total_unrealized, 2)
        equity = round(cash + total_mtm, 2)
        stale_count = sum(1 for m in marks if m["quote_status"] == "STALE")
        no_quote_count = sum(1 for m in marks if m["quote_status"] == "NO_QUOTE")
        return {
            "report_ts": _ist_ts(),
            "cash_balance": round(cash, 2),
            "marked_positions": marks,
            "position_count": len(marks),
            "total_marked_value": total_mtm,
            "unrealized_pnl": total_unrealized,
            "equity": equity,
            "realized_pnl_net": round(float(self.account.get("realized_pnl", 0.0)), 2),
            "total_fees": round(float(self.account.get("total_fees", 0.0)), 2),
            "total_slippage": round(float(self.account.get("total_slippage", 0.0)), 2),
            "stale_count": stale_count,
            "no_quote_count": no_quote_count,
        }

    # ------------------------------------------------------------------
    # auto-exit management (ADOPT-04) - decision + execution
    # ------------------------------------------------------------------
    def _now_ist_ts(self, now):
        if now is None:
            return None
        if isinstance(now, dt.datetime):
            return now.strftime("%Y-%m-%d %H:%M:%S IST")
        return now

    def run_exit_checks(self, quote_source=None, now=None):
        """Evaluate every open paper position and CLOSE what is triggered.

        The ExitEvaluator decides (STOP_LOSS / TAKE_PROFIT /
        EXPIRY_SQUARE_OFF); this engine executes via the existing FSM
        `close_position` (order -> fill -> cost/slippage -> GT close ->
        canonical outcome). Read-only except for actual closes.

        Idempotent by construction: only positions still open (remaining>0)
        are evaluated, and `close_position` refuses already-closed positions.
        """
        quote_source = quote_source or self.exit_evaluator.quote_source
        positions = self.derived_positions()
        report = {
            "report_ts": self._now_ist_ts(now) or _ist_ts(),
            "evaluated": len(positions),
            "decisions": [],
            "closed": [],
            "skipped": [],
            "errors": [],
        }
        closed_refs = set()
        for pos in positions:
            decision = self.exit_evaluator.evaluate_position(
                pos, quote=quote_source.get_quote(
                    pos["symbol"], pos["strike"], pos["option_type"], now=now),
                now=now)
            report["decisions"].append(decision)
            if not decision["triggered"]:
                report["skipped"].append(decision)
                continue
            if pos["position_ref"] in closed_refs:
                continue  # safety: one close per position per run
            try:
                close_res = self.close_position(
                    pos["position_ref"],
                    decision["exit_reference_price"],
                    exit_reason=decision["reason"],
                    ts=self._now_ist_ts(now))
                closed_refs.add(pos["position_ref"])
                report["closed"].append({
                    "position_ref": pos["position_ref"],
                    "reason": decision["reason"],
                    "requested_exit_price": decision["exit_reference_price"],
                    "exit_price": close_res["exit_price"],
                    "fees": close_res["fees"],
                    "realized_net": close_res["realized_net"],
                    "exit_reason": close_res["exit_reason"],
                })
            except Exception as exc:
                report["errors"].append({
                    "position_ref": pos["position_ref"],
                    "reason": decision["reason"],
                    "error": str(exc),
                })
        return report

    def paper_exit_status(self, quote_source=None, now=None):
        """READ-ONLY exit/health snapshot for every open paper position.

        Shows stop/target/expiry, distances, quote status, and the
        deterministic `potential_exit_reason`. Never executes a close.
        """
        quote_source = quote_source or self.exit_evaluator.quote_source
        positions = self.derived_positions()
        rows = []
        for pos in positions:
            decision = self.exit_evaluator.evaluate_position(
                pos, quote=quote_source.get_quote(
                    pos["symbol"], pos["strike"], pos["option_type"], now=now),
                now=now)
            rows.append({
                "position_id": pos["position_ref"],
                "symbol": pos["symbol"],
                "option_type": pos["option_type"],
                "strike": pos["strike"],
                "side": pos["side"],
                "entry_price": pos["entry_price"],
                "current_price": decision["mark_price"],
                "stop_price": decision["stop_price"],
                "target_price": decision["target_price"],
                "expiry": decision["expiry"],
                "expiry_date": decision["expiry_date"],
                "is_expiry_day": decision["is_expiry_day"],
                "is_expired": decision["is_expired"],
                "canonical_expiry": decision["canonical_expiry"],
                "expiry_status": decision["expiry_status"],
                "distance_to_stop": decision["distance_to_stop"],
                "distance_to_target": decision["distance_to_target"],
                "status": pos["status"],
                "potential_exit_reason": decision["reason"],
                "triggered": decision["triggered"],
                "quote_status": decision["quote_status"],
                "skip_reason": decision["skip_reason"],
            })
        return {
            "report_ts": self._now_ist_ts(now) or _ist_ts(),
            "positions": rows,
            "open_count": len(rows),
            "square_off_time": self.exit_evaluator.square_off,
            "note": "read-only exit status; never executes a close",
        }

    # ------------------------------------------------------------------
    # read-only reconciliation report (never mutates anything)
    # ------------------------------------------------------------------
    def _gt_rows(self, table):
        ledger = self._ledger_instance()
        cur = ledger._cur()
        cols = [c[1] for c in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        rows = cur.execute(
            f"SELECT * FROM {table} WHERE provenance_json LIKE ? ORDER BY "
            f"{'position_id' if table == 'positions' else 'execution_id'}",
            (f"%{GT_SOURCE}%",)).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def reconciliation_report(self):
        """Deterministic read-only report: orders, positions, GT sides,
        legacy positions, and every visible mismatch. Historical truth is
        never auto-corrected."""
        legacy = []
        for pos in (self.account.get("open_positions") or []) + (self.account.get("closed_trades") or []):
            ref = pos.get("position_id")
            if any(str(o.get("position_ref")) == str(ref) for o in self.account.get("orders") or []):
                continue
            prov = pos.get("provenance") or {}
            status = prov.get("status")
            classification = status if status in _LEGACY_STATUS else "LEGACY/UNKNOWN"
            legacy.append({
                "position_ref": ref,
                "classification": classification,
                "symbol": pos.get("symbol"),
                "strike": pos.get("strike"),
                "option_type": pos.get("option_type"),
                "quantity": pos.get("quantity"),
                "status": pos.get("status"),
                "gt_counterpart": None,
                "note": "pre-Phase-A position: no order/fill trail, no REAL ledger "
                        "execution; kept separate, never auto-converted",
            })

        gt_execs = self._gt_rows("executions")
        gt_positions = self._gt_rows("positions")
        paper_orders = self.orders()
        paper_positions = self.derived_positions()

        mismatches = []
        fill_ids = {}
        for order in paper_orders:
            for fill in order.get("fills") or []:
                fill_ids[str(fill["fill_id"])] = order["order_id"]

        for order in paper_orders:
            if order["mirror_error"]:
                mismatches.append({
                    "type": "MIRROR_ERROR", "severity": "ERROR",
                    "detail": f"order {order['order_id']}: {order['mirror_error']}"})
            is_close = order.get("order_kind") == "CLOSE"
            if order["status"] == "FILLED" and not is_close:
                if order.get("gt_position_id") is None:
                    mismatches.append({
                        "type": "POSITION_NOT_MIRRORED", "severity": "ERROR",
                        "detail": f"order {order['order_id']} FILLED but no ledger position"})
                for fill in order.get("fills") or []:
                    if fill.get("gt_execution_id") is None:
                        mismatches.append({
                            "type": "EXECUTION_NOT_MIRRORED", "severity": "ERROR",
                            "detail": f"fill {fill['fill_id']} has no ledger execution"})
            elif order["status"] == "FILLED" and is_close:
                for fill in order.get("fills") or []:
                    if fill.get("gt_execution_id") is None:
                        mismatches.append({
                            "type": "EXECUTION_NOT_MIRRORED", "severity": "ERROR",
                            "detail": f"fill {fill['fill_id']} has no ledger execution"})
            if order["status"] == "FILLED" and order.get("closed_by"):
                if order.get("gt_position_id") is not None:
                    gt_pos = next((p for p in gt_positions
                                   if int(p.get("position_id")) == int(order["gt_position_id"])), None)
                    if gt_pos and gt_pos.get("status") == "OPEN":
                        mismatches.append({
                            "type": "CLOSE_NOT_MIRRORED", "severity": "ERROR",
                            "detail": f"position {order['position_ref']} closed in paper "
                                      "but still OPEN in ledger"})

        gt_by_ref = {}
        for p in gt_positions:
            ref = str(p.get("position_ref"))
            gt_by_ref.setdefault(ref, []).append(p)
        for order in paper_orders:
            ref = str(order.get("position_ref")) if order.get("position_ref") else None
            if ref is None or ref == "None" or order.get("order_kind") == "CLOSE":
                continue
            if order["status"] == "FILLED":
                gt_list = gt_by_ref.get(ref, [])
                if len(gt_list) == 0:
                    mismatches.append({
                        "type": "GT_POSITION_ORPHAN", "severity": "ERROR",
                        "detail": f"paper position {ref} has no ledger position"})
                elif len(gt_list) > 1:
                    mismatches.append({
                        "type": "DUPLICATE_POSITION", "severity": "ERROR",
                        "detail": f"paper position {ref} maps to {len(gt_list)} ledger positions"})
        for ref, gt_list in gt_by_ref.items():
            if not any(str(o.get("position_ref")) == ref for o in paper_orders
                       if o["status"] == "FILLED" and o.get("order_kind") != "CLOSE"):
                mismatches.append({
                    "type": "GT_POSITION_ORPHAN", "severity": "ERROR",
                    "detail": f"ledger position {ref} has no matching FILLED paper order"})

        known_fills = set()
        seen_fill_ids = {}
        for order in paper_orders:
            for fill in order.get("fills") or []:
                fid = str(fill["fill_id"])
                known_fills.add(fid)
                seen_fill_ids[fid] = seen_fill_ids.get(fid, 0) + 1
        for fid, count in sorted(seen_fill_ids.items()):
            if count > 1:
                mismatches.append({
                    "type": "DUPLICATE_FILL", "severity": "ERROR",
                    "detail": f"fill {fid} appears {count} times in paper orders"})
        gt_exec_dup = {}
        for e in gt_execs:
            ref = str(e.get("broker_reference")) if e.get("broker_reference") else None
            if ref:
                gt_exec_dup[ref] = gt_exec_dup.get(ref, 0) + 1
        for ref, count in sorted(gt_exec_dup.items()):
            if count > 1:
                mismatches.append({
                    "type": "DUPLICATE_EXECUTION", "severity": "ERROR",
                    "detail": f"ledger execution broker_reference {ref} appears {count} times"})
        for e in gt_execs:
            ref = str(e.get("broker_reference")) if e.get("broker_reference") else None
            if ref and ref not in known_fills:
                mismatches.append({
                    "type": "GT_EXECUTION_ORPHAN", "severity": "ERROR",
                    "detail": f"ledger execution {ref} has no matching paper fill"})

        legacy_mismatches = [
            {
                "type": "LEGACY_POSITION_UNMATCHED", "severity": "INFO",
                "detail": f"position {p['position_ref']} classified {p['classification']} "
                          "- kept separate, no REAL ledger execution",
            } for p in legacy
        ]

        error_mismatches = [m for m in mismatches if m["severity"] == "ERROR"]
        all_issues = sorted(mismatches + legacy_mismatches,
                            key=lambda m: (m["severity"], m["type"], m["detail"]))
        return {
            "report_ts": _ist_ts(),
            "match_status": "MISMATCH" if error_mismatches else "MATCH",
            "paper_orders": paper_orders,
            "paper_positions": paper_positions,
            "ground_truth_executions": gt_execs,
            "ground_truth_positions": gt_positions,
            "legacy_positions": legacy,
            "mismatches": all_issues,
            "counts": {
                "paper_orders": len(paper_orders),
                "paper_positions": len(paper_positions),
                "gt_executions": len(gt_execs),
                "gt_positions": len(gt_positions),
                "legacy_positions": len(legacy),
                "errors": len(error_mismatches),
                "info": len(legacy_mismatches),
            },
        }

    def summary(self):
        legacy_open = len(self.account.get("open_positions") or [])
        return {
            "cash_balance": round(float(self.account.get("cash_balance", 0.0)), 2),
            "realized_pnl": round(float(self.account.get("realized_pnl", 0.0)), 2),
            "realized_pnl_net": round(float(self.account.get("realized_pnl", 0.0)), 2),
            "total_fees": round(float(self.account.get("total_fees", 0.0)), 2),
            "total_slippage": round(float(self.account.get("total_slippage", 0.0)), 2),
            "fsm_orders": len(self.account.get("orders") or []),
            "fsm_open_positions": len(self.derived_positions()),
            "legacy_open_positions": legacy_open,
        }


if __name__ == "__main__":
    import json as _json
    engine = PaperExecutionEngine()
    print(_json.dumps(engine.reconciliation_report(), indent=2, default=str))
