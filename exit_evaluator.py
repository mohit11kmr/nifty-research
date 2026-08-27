"""ADOPT-04: deterministic paper exit evaluation (STOP_LOSS / TAKE_PROFIT /
EXPIRY_SQUARE_OFF).

This module ONLY DECIDES whether an existing paper position should exit. It
never executes a close and never mutates anything. `paper_execution.py`
remains the sole execution layer (FSM -> fill -> close -> Ground Truth).

Exit rules are the existing project rules verified from source
(no new rules invented):

* STOP_LOSS (long): entry setup stores `sl_price` = max(2.0, entry - 1.5*ATR)
  (auto_paper_runner.py:84, agent_workflow_graph.py:107). Trigger convention
  (paper_execution._derive_exit_reason): exit mark <= sl_price*1.001.
* TAKE_PROFIT (long): target = entry + 2*(entry - sl) (1:2 RRR). Trigger:
  exit mark >= target_price*0.999.
* EXPIRY_SQUARE_OFF: uses the canonical NIFTY weekly-expiry service
  (expiry_calendar.py - single owner shared with backtest_frozen.py and
  mcp_nifty.py). The option's actual contract expiry (position/quote
  envelope) is authoritative when known; the canonical calendar/weekday is
  the fallback when no contract expiry is available. Square off by 15:05 IST
  on the expiry date (canonical squareoff_hhmm(), source
  regime_filter.EXPIRY_SQUARE_OFF_HOUR documented "square off by 15:05").
  Past-expiry positions are squared off immediately (weekend/holiday-safe).
  No auto-roll, no max-hold rule exists.
* SELL positions: the project never creates SELL paper entries (both entry
  paths hardcode side="BUY"), so no SELL exit rule exists. Evaluator skips
  SELL with SELL_EXITS_UNSUPPORTED instead of inventing inverted behavior.

Quote freshness (ADOPT-03): only a REAL (fresh) quote may trigger price-based
exits. STALE -> skipped (no silent trigger). MISSING/INVALID -> no fabricated
price. Expiry square-off is time-based and mandatory: it uses the last
available quote price (REAL or STALE) when one exists; with no price at all
it is skipped and recorded (never fabricated).

Precedence (documented + tested): EXPIRY_SQUARE_OFF > STOP_LOSS > TAKE_PROFIT.
For a long position a single mark price cannot be <= stop AND >= target at
once, so same-interval stop/target ambiguity cannot arise; expiry vs
stop/target is resolved by the fixed precedence above (deterministic, no
look-ahead).
"""
import os
import datetime as dt

import paper_mtm
from paper_mtm import ResearchDBQuoteSource
import expiry_calendar

# ---------------------------------------------------------------------------
# exit reasons (stable vocabulary, never collapsed into generic CLOSE)
# ---------------------------------------------------------------------------
EXIT_NONE = "NONE"
STOP_LOSS = "STOP_LOSS"
TAKE_PROFIT = "TAKE_PROFIT"
EXPIRY_SQUARE_OFF = "EXPIRY_SQUARE_OFF"
MANUAL = "MANUAL"
EXIT_REASONS = (STOP_LOSS, TAKE_PROFIT, EXPIRY_SQUARE_OFF, MANUAL)

# ---------------------------------------------------------------------------
# project rule constants (source-verified, do not change)
# ---------------------------------------------------------------------------
# canonical square-off trigger, single owner: expiry_calendar.squareoff_hhmm()
# (regime_filter.EXPIRY_SQUARE_OFF_HOUR = 15.0 ; documented "square off by 15:05")
SQUARE_OFF_HHMM = expiry_calendar.squareoff_hhmm()
# trigger tolerance bands (paper_execution._derive_exit_reason convention)
_STOP_BAND = 1.001   # exit <= stop * 1.001
_TARGET_BAND = 0.999  # exit >= target * 0.999


def _parse_expiry(value):
    """Parse a contract expiry string to a date (canonical parser)."""
    return expiry_calendar.parse_expiry(value)


class ExitEvaluator:
    """Deterministic decision layer. Pure: never closes, never mutates."""

    def __init__(self, quote_source=None, square_off=SQUARE_OFF_HHMM):
        self.quote_source = quote_source or ResearchDBQuoteSource()
        self.square_off = square_off  # "HH:MM" IST, inclusive trigger

    # ------------------------------------------------------------------
    def _square_off_reached(self, now):
        now_t = now.time().replace(second=0, microsecond=0)
        hh, mm = (int(x) for x in str(self.square_off).split(":"))
        return now_t >= dt.time(hh, mm)

    # ------------------------------------------------------------------
    def evaluate_position(self, position, quote=None, now=None):
        """Evaluate ONE open paper position -> decision dict (read-only)."""
        now = now or paper_mtm.now_local()
        ref = position.get("position_ref")
        side = str(position.get("side", "BUY")).upper()
        entry = float(position.get("entry_price") or 0.0)
        sl = position.get("sl_price")
        tgt = position.get("target_price")
        base = {
            "position_ref": ref,
            "symbol": position.get("symbol"),
            "option_type": position.get("option_type"),
            "strike": position.get("strike"),
            "side": side,
            "entry_price": entry,
            "stop_price": sl,
            "target_price": tgt,
            "expiry": None,
            "expiry_date": None,
            "is_expiry_day": False,
            "is_expired": False,
            "canonical_expiry": None,
            "expiry_status": None,
            "quote_status": None,
            "mark_price": None,
            "distance_to_stop": None,
            "distance_to_target": None,
            "reason": EXIT_NONE,
            "triggered": False,
            "exit_reference_price": None,
            "skip_reason": None,
            "square_off_time": self.square_off,
        }

        if side != "BUY":
            base["skip_reason"] = "SELL_EXITS_UNSUPPORTED"
            base["reason"] = EXIT_NONE
            return base

        quote = quote if quote is not None else self.quote_source.get_quote(
            position.get("symbol"), position.get("strike"),
            position.get("option_type"), now=now)
        qstatus = quote.get("status") if quote else "MISSING"
        mark = float(quote["price"]) if quote and quote.get("price") is not None else None
        base["quote_status"] = qstatus
        base["mark_price"] = round(mark, 2) if mark is not None else None
        base["expiry"] = quote.get("expiry") if quote else None
        exp_date = _parse_expiry(base["expiry"]) if base["expiry"] else None
        base["expiry_date"] = exp_date.isoformat() if exp_date else None
        base["is_expired"] = bool(exp_date and exp_date < now.date())
        # Contract expiry from the position/quote is authoritative; the
        # canonical calendar/era rule is the fallback when none is known
        # (single owner: expiry_calendar).
        base["is_expiry_day"] = bool(
            exp_date == now.date()
            if exp_date
            else expiry_calendar.is_expiry_day(now.date()))
        # Read-only canonical status for the evaluation date: the SAME expiry
        # the historical replay and the contract selection use.
        base["canonical_expiry"] = expiry_calendar.get_expiry_for_trade_date(
            now.date()).isoformat()
        base["expiry_status"] = expiry_calendar.describe(now.date())
        if sl:
            base["distance_to_stop"] = round(entry - float(sl), 2)
        if tgt:
            base["distance_to_target"] = round(float(tgt) - entry, 2)

        square_off_due = (base["is_expiry_day"] and self._square_off_reached(now)) \
            or base["is_expired"]

        if square_off_due:
            # time-based mandatory close; needs only a real last price
            if mark is not None:
                base["reason"] = EXPIRY_SQUARE_OFF
                base["triggered"] = True
                base["exit_reference_price"] = round(mark, 2)
                return base
            base["skip_reason"] = "NO_EXIT_PRICE_SQUARE_OFF_PENDING"
            base["reason"] = EXIT_NONE
            return base

        # price-based exits require a FRESH (REAL) quote
        if qstatus != "REAL":
            base["skip_reason"] = {
                "STALE": "STALE_QUOTE_NO_TRIGGER",
                "MISSING": "MISSING_QUOTE",
                "INVALID": "INVALID_QUOTE",
            }.get(qstatus, "NO_TRUSTED_QUOTE")
            base["reason"] = EXIT_NONE
            return base

        if sl and mark <= float(sl) * _STOP_BAND:
            base["reason"] = STOP_LOSS
            base["triggered"] = True
            base["exit_reference_price"] = round(mark, 2)
            return base
        if tgt and mark >= float(tgt) * _TARGET_BAND:
            base["reason"] = TAKE_PROFIT
            base["triggered"] = True
            base["exit_reference_price"] = round(mark, 2)
            return base
        base["reason"] = EXIT_NONE
        return base

    # ------------------------------------------------------------------
    def evaluate_open_positions(self, positions, quote_source=None, now=None):
        """Evaluate a list of open positions (read-only). One dict per position."""
        quote_source = quote_source or self.quote_source
        out = []
        for pos in positions:
            quote = quote_source.get_quote(
                pos.get("symbol"), pos.get("strike"), pos.get("option_type"), now=now)
            out.append(self.evaluate_position(pos, quote=quote, now=now))
        return out


# keep module import cheap / safe
if __name__ == "__main__":
    import json as _json
    import paper_execution as _pe
    _e = _pe.PaperExecutionEngine()
    _st = _e.paper_exit_status()
    print(_json.dumps(_st, indent=2, default=str))
