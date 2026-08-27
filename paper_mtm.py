"""ADOPT-03: paper mark-to-market quote source (read-only).

Open paper positions are marked to the last trusted contract quote from
``data/research.db`` ``ticks`` (recorded by tick_recorder.py during market
hours). Freshness follows the existing truth.py budget for the live streamer
(LIVE_SPOT_FRESHNESS_S = 120s -> 2x the 60s sampling).

This module NEVER fabricates a quote. Every lookup returns an explicit
status:
    REAL    - valid price, age within freshness budget
    STALE   - valid price, age beyond freshness budget (shown, flagged)
    MISSING - no matching contract tick
    INVALID - unusable row (future timestamp, unparseable ts, no price)
    UNKNOWN - any other indeterminate state
"""
import os
import sqlite3
import datetime as dt

import truth

QUOTE_FRESHNESS_S = truth.LIVE_SPOT_FRESHNESS_S   # 120s
DEFAULT_RESEARCH_DB = os.path.join("data", "research.db")


def now_local():
    """Local (IST) naive now - tick timestamps are recorded in local time."""
    return dt.datetime.now()


def _parse_ts(value):
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(str(value), fmt)
        except (ValueError, TypeError):
            continue
    return None


class ResearchDBQuoteSource:
    """Read-only contract-quote lookup against research.db ``ticks``."""

    def __init__(self, db_file=DEFAULT_RESEARCH_DB, freshness_s=QUOTE_FRESHNESS_S):
        self.db_file = db_file
        self.freshness_s = float(freshness_s)

    # ------------------------------------------------------------------
    def _missing(self, symbol, strike, option_type, reason="no matching contract tick"):
        return {
            "status": "MISSING", "source": "research.db:ticks",
            "symbol": symbol, "strike": strike, "option_type": option_type,
            "price": None, "price_basis": None, "bid": None, "ask": None,
            "expiry": None, "quote_timestamp": None, "quote_age_s": None,
            "freshness_budget_s": self.freshness_s, "reason": reason,
        }

    def get_quote(self, symbol, strike, option_type, now=None):
        """Return the most recent trusted quote envelope for a contract.

        Matching key: (symbol, strike, option_type) on the most recent tick.
        The quote's expiry is reported (never silently substituted).
        """
        now = now or now_local()
        ot = str(option_type).upper()
        if not os.path.exists(self.db_file):
            return self._missing(symbol, strike, ot, reason="research.db not found")
        try:
            conn = sqlite3.connect(f"file:{self.db_file}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            return self._missing(symbol, strike, ot, reason=f"cannot open research.db: {exc}")
        try:
            row = conn.execute(
                "SELECT recv_ts, expiry, strike, side, ltp, bid, ask"
                " FROM ticks WHERE symbol=? AND strike=? AND side=?"
                " ORDER BY recv_ts DESC LIMIT 1",
                (str(symbol), float(strike), ot),
            ).fetchone()
        except sqlite3.Error as exc:
            conn.close()
            return self._missing(symbol, strike, ot, reason=f"research.db read error: {exc}")
        conn.close()

        if row is None:
            return self._missing(symbol, strike, ot)

        recv_ts, expiry, stk, side, ltp, bid, ask = row
        qts = _parse_ts(recv_ts)
        if qts is None:
            return self._missing(symbol, strike, ot,
                                 reason=f"unparseable quote timestamp {recv_ts!r}")
        age_s = round((now - qts).total_seconds(), 1)
        if age_s < 0:
            return self._missing(symbol, strike, ot,
                                 reason=f"quote timestamp {recv_ts!r} is in the future")
        if age_s > self.freshness_s:
            status = "STALE"
        else:
            status = "REAL"

        price = None
        basis = None
        if ltp is not None and float(ltp) > 0:
            price, basis = float(ltp), "ltp"
        elif (bid or 0) > 0 and (ask or 0) > 0:
            price, basis = round((float(bid) + float(ask)) / 2.0, 2), "bid_ask_mid"
        if price is None:
            return self._missing(symbol, strike, ot,
                                 reason="no valid ltp or bid/ask pair in latest tick")

        return {
            "status": status, "source": "research.db:ticks",
            "symbol": str(symbol), "strike": float(stk), "option_type": side,
            "expiry": expiry, "price": round(price, 2), "price_basis": basis,
            "bid": bid, "ask": ask,
            "quote_timestamp": recv_ts, "quote_age_s": age_s,
            "freshness_budget_s": self.freshness_s, "reason": None,
        }


class FakeQuoteSource:
    """Deterministic in-memory quote source for isolated tests.

    ``quotes`` maps ``(symbol, strike, option_type)`` to an envelope dict
    (keys: status/price/quote_timestamp/quote_age_s/expiry...). Missing keys
    behave like MISSING.
    """

    def __init__(self, quotes=None, default_status="REAL"):
        self.quotes = dict(quotes or {})
        self.default_status = default_status

    def get_quote(self, symbol, strike, option_type, now=None):
        key = (str(symbol), float(strike), str(option_type).upper())
        q = self.quotes.get(key)
        if q is None:
            return {
                "status": "MISSING", "source": "fake",
                "symbol": str(symbol), "strike": float(strike),
                "option_type": str(option_type).upper(),
                "price": None, "price_basis": None, "bid": None, "ask": None,
                "expiry": None, "quote_timestamp": None, "quote_age_s": None,
                "freshness_budget_s": QUOTE_FRESHNESS_S, "reason": "no fake quote",
            }
        out = dict(q)
        out.setdefault("symbol", str(symbol))
        out.setdefault("strike", float(strike))
        out.setdefault("option_type", str(option_type).upper())
        out.setdefault("source", "fake")
        out.setdefault("freshness_budget_s", QUOTE_FRESHNESS_S)
        out.setdefault("status", self.default_status)
        return out
