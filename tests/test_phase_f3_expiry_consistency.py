"""Phase F3 - historical/live expiry consistency correction tests.

Verifies that the historical frozen replay and the live/paper auto-exit
engine share ONE canonical expiry source (expiry_calendar.py) and that no
hardcoded Thursday logic remains in the expiry path.

Covers:
  * historical transition (last Thursday 2025-08-28 -> first Tuesday
    2025-09-02), actual calendar evidence
  * holiday / moved expiries (Monday shifts) and invalid dates
  * contract selection (correct expiry/strike/CE/PE, unavailable contract)
  * paper exit: before expiry, on expiry before square-off, at/after
    square-off, wrong-weekday trap, expired positions, no auto-roll
  * shared source: backtest + paper + MCP return the same expiry per date
  * no lookahead, idempotency, square-off time single owner
  * production isolation (temp fixtures only)

Run: .venv/bin/python -m unittest tests.test_phase_f3_expiry_consistency -v
"""
import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import expiry_calendar as ec           # noqa: E402
import backtest_frozen as bf           # noqa: E402
import exit_evaluator                  # noqa: E402
import paper_execution                 # noqa: E402
import paper_mtm                       # noqa: E402
import ground_truth as gt              # noqa: E402


def _quote(status="MISSING", price=None, expiry=None):
    q = {"status": status, "price": price, "price_basis": "ltp",
         "quote_timestamp": "2026-08-13 15:29:00.000", "quote_age_s": 5.0,
         "expiry": expiry}
    return q


class TestHistoricalTransition(unittest.TestCase):
    def test_last_thursday_weekly_is_expiry_day(self):
        self.assertTrue(ec.is_expiry_day(dt.date(2025, 8, 28)))
        self.assertEqual(ec.get_expiry_for_trade_date(dt.date(2025, 8, 28)),
                         dt.date(2025, 9, 2))
        self.assertEqual(ec.expiry_era(dt.date(2025, 8, 28)), "thursday")

    def test_first_tuesday_weekly_is_expiry_day(self):
        self.assertTrue(ec.is_expiry_day(dt.date(2025, 9, 2)))
        self.assertEqual(ec.get_expiry_for_trade_date(dt.date(2025, 9, 2)),
                         dt.date(2025, 9, 9))
        self.assertEqual(ec.expiry_era(dt.date(2025, 9, 2)), "tuesday")

    def test_transition_actual_calendar_evidence(self):
        # Actual calendar evidence overrides a naive weekday rule: Monday
        # 2025-09-01 sits in the Thursday era, but the first Tuesday weekly
        # (2025-09-02) was ALREADY listed -> applicable contract is 09-02.
        d = dt.date(2025, 9, 1)
        self.assertEqual(ec.expiry_era(d), "thursday")
        self.assertEqual(ec.get_expiry_for_trade_date(d), dt.date(2025, 9, 2))
        self.assertFalse(ec.is_expiry_day(d))   # 09-01 is not an expiry day
        self.assertTrue(ec.is_expiry_day(dt.date(2025, 9, 2)))

    def test_thursday_never_applies_after_transition(self):
        # Thursday 2026-08-13 is NOT an expiry day (Tuesday era).
        self.assertEqual(ec.expiry_era(dt.date(2026, 8, 13)), "tuesday")
        self.assertFalse(ec.is_expiry_day(dt.date(2026, 8, 13)))
        self.assertEqual(ec.get_expiry_for_trade_date(dt.date(2026, 8, 13)),
                         dt.date(2026, 8, 18))


class TestHolidayAndInvalidDates(unittest.TestCase):
    def test_diwali_monday_shift(self):
        self.assertTrue(ec.is_expiry_day(dt.date(2025, 10, 20)))  # Monday
        self.assertEqual(ec.get_expiry_for_trade_date(dt.date(2025, 10, 20)),
                         dt.date(2025, 10, 28))

    def test_other_monday_shifts(self):
        for d in ("2026-03-02", "2026-03-30", "2026-04-13"):
            self.assertTrue(ec.is_expiry_day(dt.date.fromisoformat(d)), d)

    def test_weekday_never_asserts_expiry_without_calendar(self):
        # A Wednesday between Tuesday expiries is not an expiry day.
        self.assertFalse(ec.is_expiry_day(dt.date(2026, 8, 12)))
        self.assertGreater(ec.get_expiry_for_trade_date(dt.date(2026, 8, 12)),
                           dt.date(2026, 8, 12))

    def test_forward_rule_outside_window(self):
        # Beyond the observed window the era convention applies (Tuesday).
        self.assertTrue(ec.is_expiry_day(dt.date(2026, 8, 18)))
        self.assertFalse(ec.is_expiry_day(dt.date(2026, 8, 19)))
        self.assertEqual(ec.get_expiry_for_trade_date(dt.date(2026, 8, 18)),
                         dt.date(2026, 8, 25))
        self.assertEqual(ec.get_expiry_for_trade_date(dt.date(2026, 12, 31)),
                         dt.date(2027, 1, 5))

    def test_parse_expiry_invalid(self):
        self.assertIsNone(ec.parse_expiry(None))
        self.assertIsNone(ec.parse_expiry("garbage"))
        self.assertIsNone(ec.parse_expiry(""))
        self.assertEqual(ec.parse_expiry("18-Aug-2026"), dt.date(2026, 8, 18))
        self.assertEqual(ec.parse_expiry("2026-08-18"), dt.date(2026, 8, 18))

    def test_no_zero_dte(self):
        # On an expiry day the applicable contract is NEXT week.
        for d in ("2025-08-28", "2025-09-02", "2025-10-20", "2026-08-11"):
            exp = ec.get_expiry_for_trade_date(dt.date.fromisoformat(d))
            self.assertGreater((exp - dt.date.fromisoformat(d)).days, 0, d)


class TestSharedSourceIdentity(unittest.TestCase):
    def test_single_canonical_module_shared(self):
        # backtest and paper exit import the SAME singleton expiry service.
        self.assertIs(bf.exp_cal, ec)
        self.assertIs(exit_evaluator.expiry_calendar, ec)
        self.assertEqual(exit_evaluator.SQUARE_OFF_HHMM, ec.squareoff_hhmm())

    def test_square_off_time_single_owner(self):
        self.assertEqual(ec.squareoff_hhmm(), "15:05")   # current source trigger
        self.assertEqual(ec.last_entry_hhmm(), "14:30")
        self.assertEqual(exit_evaluator.SQUARE_OFF_HHMM, "15:05")

    def test_backtest_and_paper_agree_per_trade_date(self):
        nifty, vix, fii, ml, snaps = bf.load_inputs()
        nifty_dates = [d.date() for d in nifty["date"]]
        ev = exit_evaluator.ExitEvaluator()
        pos = {"position_ref": "P1", "symbol": "NIFTY", "option_type": "CE",
               "strike": 24450, "side": "BUY", "entry_price": 140.0,
               "sl_price": 90.0, "target_price": 240.0, "quantity": 75}
        for d in ("2025-08-13", "2025-09-02", "2025-09-16", "2026-01-20",
                  "2026-06-30", "2026-08-11"):
            dd = dt.date.fromisoformat(d)
            rec = bf.evaluate_day(dd, nifty, vix, fii, ml, snaps, nifty_dates)
            backtest_expiry = (dt.date.fromisoformat(rec["expiry"])
                               if rec.get("candidate") and rec.get("expiry")
                               else None)
            canonical = ec.get_expiry_for_trade_date(dd)
            decision = ev.evaluate_position(pos, quote=_quote(status="MISSING"),
                                            now=dt.datetime.combine(
                                                dd, dt.time(15, 0)))
            if backtest_expiry is not None:
                self.assertEqual(backtest_expiry, canonical, d)
            self.assertEqual(dt.date.fromisoformat(decision["canonical_expiry"]),
                             canonical, d)
            self.assertEqual(decision["expiry_status"]["next_expiry"],
                             canonical.isoformat(), d)


class TestContractSelection(unittest.TestCase):
    def test_unavailable_contract_still_explicit(self):
        # Regression: contract validation is data-driven and explicit.
        d = dt.date(2025, 8, 14)
        chain = pd.DataFrame({
            "expiry": ["21-Aug-2025", "28-Aug-2025"],
            "strike": [24500.0, 24500.0],
            "ce_oi": [1, 1], "ce_oi_chg": [0, 0], "ce_volume": [1, 1],
            "ce_ltp": [10.0, 12.0], "pe_oi": [1, 1], "pe_oi_chg": [0, 0],
            "pe_volume": [1, 1], "pe_ltp": [8.0, 9.0],
        })
        # strike 25000 does not exist in ANY expiry -> None (no substitution)
        self.assertIsNone(bf.price_strike_lookup({d: chain}, d, 25000.0, "PE",
                                                 expiry=dt.date(2025, 8, 21)))
        # strike exists at a DIFFERENT expiry -> no silent fallback
        self.assertIsNone(bf.price_strike_lookup({d: chain}, d, 24500.0, "CE",
                                                 expiry=dt.date(2025, 8, 14)))

    def test_correct_expiry_strike_side_ce(self):
        d = dt.date(2025, 9, 2)
        chain = pd.DataFrame({
            "expiry": ["09-Sep-2025", "16-Sep-2025"],
            "strike": [25150.0, 25150.0],
            "ce_ltp": [100.0, 120.0], "pe_ltp": [90.0, 110.0],
        })
        v = bf.price_strike_lookup({d: chain}, d, 25150.0, "CE",
                                   expiry=ec.get_expiry_for_trade_date(d))
        self.assertEqual(v, 100.0)
        vp = bf.price_strike_lookup({d: chain}, d, 25150.0, "PE",
                                    expiry=ec.get_expiry_for_trade_date(d))
        self.assertEqual(vp, 90.0)


class TestPaperExitConsistency(unittest.TestCase):
    def _pos(self):
        return {"position_ref": "P1", "symbol": "NIFTY", "option_type": "CE",
                "strike": 24450, "side": "BUY", "entry_price": 140.0,
                "sl_price": 90.0, "target_price": 240.0, "quantity": 75}

    def test_before_expiry_no_expiry_exit(self):
        ev = exit_evaluator.ExitEvaluator()
        q = _quote(status="REAL", price=150.0, expiry="18-Aug-2026")
        d = ev.evaluate_position(self._pos(), quote=q,
                                 now=dt.datetime(2026, 8, 11, 10, 0))
        self.assertEqual(d["reason"], exit_evaluator.EXIT_NONE)
        self.assertFalse(d["triggered"])

    def test_on_expiry_before_square_off_no_exit(self):
        ev = exit_evaluator.ExitEvaluator()
        q = _quote(status="REAL", price=150.0, expiry="11-Aug-2026")
        d = ev.evaluate_position(self._pos(), quote=q,
                                 now=dt.datetime(2026, 8, 11, 15, 0))
        self.assertTrue(d["is_expiry_day"])
        self.assertFalse(d["triggered"])
        self.assertEqual(d["reason"], exit_evaluator.EXIT_NONE)

    def test_at_square_off_exits(self):
        ev = exit_evaluator.ExitEvaluator()
        q = _quote(status="REAL", price=150.0, expiry="11-Aug-2026")
        d = ev.evaluate_position(self._pos(), quote=q,
                                 now=dt.datetime(2026, 8, 11, 15, 5))
        self.assertEqual(d["reason"], exit_evaluator.EXPIRY_SQUARE_OFF)
        self.assertTrue(d["triggered"])

    def test_after_square_off_exits(self):
        ev = exit_evaluator.ExitEvaluator()
        q = _quote(status="REAL", price=150.0, expiry="11-Aug-2026")
        d = ev.evaluate_position(self._pos(), quote=q,
                                 now=dt.datetime(2026, 8, 11, 15, 10))
        self.assertEqual(d["reason"], exit_evaluator.EXPIRY_SQUARE_OFF)

    def test_wrong_weekday_no_false_expiry(self):
        # Thursday 2026-08-13, Tuesday era: NOT an expiry day, so a position
        # with no contract expiry must not square off on it.
        ev = exit_evaluator.ExitEvaluator()
        d = ev.evaluate_position(self._pos(), quote=_quote(status="MISSING"),
                                 now=dt.datetime(2026, 8, 13, 15, 10))
        self.assertFalse(d["is_expiry_day"])
        self.assertEqual(d["reason"], exit_evaluator.EXIT_NONE)

    def test_expired_position_squares_off_immediately(self):
        ev = exit_evaluator.ExitEvaluator()
        q = _quote(status="REAL", price=150.0, expiry="11-Aug-2026")
        d = ev.evaluate_position(self._pos(), quote=q,
                                 now=dt.datetime(2026, 8, 12, 10, 0))
        self.assertTrue(d["is_expired"])
        self.assertEqual(d["reason"], exit_evaluator.EXPIRY_SQUARE_OFF)


class TestNoAutoRollAndIdempotency(unittest.TestCase):
    def _fixture(self):
        tmp = tempfile.mkdtemp()
        acct = os.path.join(tmp, "paper_account.json")
        gt_db = os.path.join(tmp, "ground_truth.db")
        gt.RESEARCH_DB = os.path.join(tmp, "research.db")
        with open(acct, "w") as f:
            json.dump({"initial_capital": 100000.0, "cash_balance": 100000.0,
                       "realized_pnl": 0.0, "total_fees": 0.0,
                       "total_slippage": 0.0, "open_positions": [],
                       "closed_trades": []}, f)
        return tmp, acct, gt_db

    def _open(self, acct, gt_db):
        e = paper_execution.PaperExecutionEngine(account_file=acct, gt_db_file=gt_db)
        sub = e.submit_order(entry_price=140.0, sl_price=90.0, target_price=240.0,
                             side="BUY", strike=24450)
        e.accept_order(sub["order_id"])
        e.fill_order(sub["order_id"], 75, price=None, reference_price=140.0,
                     ts="2026-08-11 10:00:00 IST")
        return e

    def test_expiry_close_creates_no_new_position(self):
        _, acct, gt_db = self._fixture()
        e = self._open(acct, gt_db)
        src = paper_mtm.FakeQuoteSource({
            ("NIFTY", 24450.0, "CE"): _quote(status="REAL", price=150.0,
                                             expiry="11-Aug-2026")})
        rep = e.run_exit_checks(quote_source=src, now=dt.datetime(2026, 8, 11, 15, 5))
        self.assertEqual(len(rep["closed"]), 1)
        self.assertEqual(rep["closed"][0]["reason"], "EXPIRY_SQUARE_OFF")
        # no auto-roll: no new open position, no new order beyond the close
        self.assertEqual(e.derived_positions(), [])
        open_orders = [o for o in e.orders()
                       if o.get("order_kind") == "OPEN" and o["status"] == "FILLED"]
        self.assertEqual(len(open_orders), 1)   # the original entry only
        db = gt.GroundTruthDB(gt_db)
        self.assertEqual(db.counts()["outcomes"], 1)

    def test_repeated_expiry_check_single_close(self):
        _, acct, gt_db = self._fixture()
        e = self._open(acct, gt_db)
        src = paper_mtm.FakeQuoteSource({
            ("NIFTY", 24450.0, "CE"): _quote(status="REAL", price=150.0,
                                             expiry="11-Aug-2026")})
        now = dt.datetime(2026, 8, 11, 15, 5)
        e.run_exit_checks(quote_source=src, now=now)
        r2 = e.run_exit_checks(quote_source=src, now=now)   # idempotent
        self.assertEqual(r2["closed"], [])
        db = gt.GroundTruthDB(gt_db)
        self.assertEqual(db.counts()["executions"], 2)       # entry + exit only
        self.assertEqual(db.counts()["outcomes"], 1)
        self.assertEqual(e.reconciliation_report()["match_status"], "MATCH")


class TestNoLookahead(unittest.TestCase):
    def test_expiry_always_strictly_after_trade_date(self):
        cal = ec._calendar()
        for d, rec in cal.items():
            if rec[3] and rec[0] is not None:
                self.assertGreater(rec[0], dt.date.fromisoformat(d), d)
        # forward rule is strictly after too
        for d in ("2026-08-18", "2026-08-25", "2026-12-31"):
            self.assertGreater(ec.get_expiry_for_trade_date(dt.date.fromisoformat(d)),
                               dt.date.fromisoformat(d), d)


class TestProductionIsolation(unittest.TestCase):
    def _sha(self, path):
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def test_read_only_validation_touches_no_production_state(self):
        acct = "data/paper_account.json"
        sha_acct = self._sha(acct)
        e = paper_execution.PaperExecutionEngine()
        st = e.paper_exit_status()
        self.assertEqual(st["open_count"], 0)
        rep = e.run_exit_checks()
        self.assertEqual(rep["closed"], [])
        db = gt.GroundTruthDB()
        self.assertEqual(db.counts()["executions"], 0)
        self.assertEqual(db.counts()["positions"], 0)
        self.assertEqual(db.counts()["outcomes"], 0)
        self.assertTrue(db.integrity_check()["ok"])
        self.assertEqual(self._sha(acct), sha_acct)
        self.assertEqual(e.reconciliation_report()["match_status"], "MATCH")


if __name__ == "__main__":
    unittest.main()
