"""Phase C (ADOPT-04) - Paper Auto-Exit / Stop / Target / Expiry Square-Off.

Covers:
- STOP_LOSS exact/above/below + correct side handling
- TAKE_PROFIT exact/below/above
- EXPIRY_SQUARE_OFF before/at/after square-off, non-expiry day,
  holiday/weekend (expired) handling, no auto-roll
- deterministic precedence (expiry > stop > target)
- quote freshness (REAL/STALE/MISSING/INVALID -> no silent/fabricated exit)
- execution via the existing FSM (slippage/fees/cash/P&L)
- Ground Truth (execution mirrored, position closed, exactly one outcome,
  exit reason preserved)
- partial-close limitation (documented N/A, always full close)
- legacy positions never upgraded, no fabricated outcome
- idempotency (repeated evaluation/run produces one close, one outcome)
- read-only paper_exit_status (never closes)
- production isolation (temp fixtures only; real data only read)

Run: .venv/bin/python -m unittest tests.test_adopt04_auto_exit -v
"""
import os
import sys
import json
import sqlite3
import tempfile
import unittest
import unittest.mock as mock
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ground_truth as gt
import paper_execution
import paper_trader
import paper_mtm
import exit_evaluator
from exit_evaluator import ExitEvaluator, STOP_LOSS, TAKE_PROFIT, EXPIRY_SQUARE_OFF, EXIT_NONE

# 2026-08-13 15:05 IST (a Thursday in the TUESDAY era - NOT an expiry day).
# Quotes below explicitly carry their own contract expiry (authoritative);
# the canonical-calendar fallback is covered by
# test_weekday_convention_when_no_contract_expiry.
NOW_EXPIRY = dt.datetime(2026, 8, 13, 15, 5, 0)
NOW_BEFORE = dt.datetime(2026, 8, 13, 15, 0, 0)
NOW_NON_EXPIRY = dt.datetime(2026, 8, 12, 16, 0, 0)   # Wednesday
NOW_AFTER = dt.datetime(2026, 8, 13, 15, 10, 0)


def _make_fixture(with_legacy=False):
    tmp = tempfile.mkdtemp()
    acct = os.path.join(tmp, "paper_account.json")
    gt_db = os.path.join(tmp, "ground_truth.db")
    gt.RESEARCH_DB = os.path.join(tmp, "research.db")
    acct_data = {
        "initial_capital": 100000.0,
        "cash_balance": 100000.0,
        "realized_pnl": 0.0,
        "total_fees": 0.0,
        "total_slippage": 0.0,
        "open_positions": [],
        "closed_trades": [],
    }
    if with_legacy:
        acct_data["cash_balance"] = 3381.25
        acct_data["open_positions"] = [
            {"position_id": "POS_1_101502", "timestamp": "2026-08-12 10:15:02 IST",
             "symbol": "NIFTY", "side": "BUY", "option_type": "CE", "strike": 24450,
             "lots": 1, "quantity": 75, "entry_price": 140.0, "status": "OPEN"},
        ]
    with open(acct, "w") as f:
        json.dump(acct_data, f)
    return tmp, acct, gt_db


def _open_engine(acct, gt_db):
    return paper_execution.PaperExecutionEngine(account_file=acct, gt_db_file=gt_db)


def _open_position(e, entry=140.0, sl=90.0, tgt=240.0, side="BUY", strike=24450,
                   ts="2026-08-12 10:00:00 IST"):
    sub = e.submit_order(entry_price=entry, sl_price=sl, target_price=tgt,
                         side=side, strike=strike)
    e.accept_order(sub["order_id"])
    e.fill_order(sub["order_id"], 75, price=None, reference_price=entry, ts=ts)
    return e._find_order(sub["order_id"])["position_ref"]


def _quote(status="REAL", price=150.0, expiry="18-Aug-2026", **kw):
    q = {"status": status, "price": price, "price_basis": "ltp",
         "quote_timestamp": "2026-08-13 15:29:00.000", "quote_age_s": 5.0,
         "expiry": expiry}
    q.update(kw)
    return q


class TestStopLoss(unittest.TestCase):
    def _dec(self, mark, sl=90.0, status="REAL", side="BUY", expiry="18-Aug-2026"):
        ev = ExitEvaluator()
        pos = {"position_ref": "P1", "symbol": "NIFTY", "option_type": "CE",
               "strike": 24450, "side": side, "entry_price": 140.0,
               "sl_price": sl, "target_price": 240.0, "quantity": 75}
        q = _quote(status=status, price=mark, expiry=expiry)
        return ev.evaluate_position(pos, quote=q, now=NOW_NON_EXPIRY)

    def test_exact_trigger_at_band(self):
        d = self._dec(mark=90.0 * 1.001)          # <= stop*1.001
        self.assertEqual(d["reason"], STOP_LOSS)
        self.assertTrue(d["triggered"])
        self.assertEqual(d["exit_reference_price"], round(90.0 * 1.001, 2))

    def test_above_stop_no_trigger(self):
        d = self._dec(mark=91.0)
        self.assertEqual(d["reason"], EXIT_NONE)
        self.assertFalse(d["triggered"])

    def test_below_stop_trigger(self):
        d = self._dec(mark=80.0)
        self.assertEqual(d["reason"], STOP_LOSS)

    def test_correct_direction_sell_unsupported(self):
        d = self._dec(mark=80.0, side="SELL")
        self.assertEqual(d["reason"], EXIT_NONE)
        self.assertFalse(d["triggered"])
        self.assertEqual(d["skip_reason"], "SELL_EXITS_UNSUPPORTED")


class TestTakeProfit(unittest.TestCase):
    def _dec(self, mark, tgt=240.0, status="REAL", expiry="18-Aug-2026"):
        ev = ExitEvaluator()
        pos = {"position_ref": "P1", "symbol": "NIFTY", "option_type": "CE",
               "strike": 24450, "side": "BUY", "entry_price": 140.0,
               "sl_price": 90.0, "target_price": tgt, "quantity": 75}
        q = _quote(status=status, price=mark, expiry=expiry)
        return ev.evaluate_position(pos, quote=q, now=NOW_NON_EXPIRY)

    def test_exact_trigger_at_band(self):
        d = self._dec(mark=240.0 * 0.999)         # >= target*0.999
        self.assertEqual(d["reason"], TAKE_PROFIT)
        self.assertEqual(d["exit_reference_price"], round(240.0 * 0.999, 2))

    def test_below_target_no_trigger(self):
        d = self._dec(mark=200.0)
        self.assertEqual(d["reason"], EXIT_NONE)

    def test_above_target_trigger(self):
        d = self._dec(mark=260.0)
        self.assertEqual(d["reason"], TAKE_PROFIT)


class TestExpirySquareOff(unittest.TestCase):
    def _dec(self, now, status="REAL", mark=150.0, expiry="13-Aug-2026"):
        ev = ExitEvaluator()
        pos = {"position_ref": "P1", "symbol": "NIFTY", "option_type": "CE",
               "strike": 24450, "side": "BUY", "entry_price": 140.0,
               "sl_price": 90.0, "target_price": 240.0, "quantity": 75}
        q = _quote(status=status, price=mark, expiry=expiry)
        return ev.evaluate_position(pos, quote=q, now=now)

    def test_before_square_off(self):
        d = self._dec(NOW_BEFORE)
        self.assertEqual(d["reason"], EXIT_NONE)
        self.assertTrue(d["is_expiry_day"])
        self.assertFalse(d["triggered"])

    def test_at_square_off(self):
        d = self._dec(NOW_EXPIRY)
        self.assertEqual(d["reason"], EXPIRY_SQUARE_OFF)
        self.assertEqual(d["exit_reference_price"], 150.0)

    def test_after_square_off(self):
        d = self._dec(NOW_AFTER)
        self.assertEqual(d["reason"], EXPIRY_SQUARE_OFF)

    def test_non_expiry_day(self):
        d = self._dec(NOW_NON_EXPIRY, expiry="18-Aug-2026")
        self.assertEqual(d["reason"], EXIT_NONE)
        self.assertFalse(d["is_expiry_day"])

    def test_expired_position_squared_off_immediately(self):
        # expiry in the past (e.g. missed square-off / weekend/holiday)
        d = self._dec(NOW_NON_EXPIRY, expiry="11-Aug-2026")
        self.assertTrue(d["is_expired"])
        self.assertEqual(d["reason"], EXPIRY_SQUARE_OFF)

    def test_expiry_square_off_uses_stale_price(self):
        # mandatory time-based close may use last available (stale) price
        d = self._dec(NOW_EXPIRY, status="STALE", mark=150.0)
        self.assertEqual(d["reason"], EXPIRY_SQUARE_OFF)
        self.assertEqual(d["quote_status"], "STALE")

    def test_expiry_no_price_pending(self):
        d = self._dec(NOW_EXPIRY, status="MISSING", mark=None)
        self.assertEqual(d["reason"], EXIT_NONE)
        self.assertEqual(d["skip_reason"], "NO_EXIT_PRICE_SQUARE_OFF_PENDING")

    def test_weekday_convention_when_no_contract_expiry(self):
        # Phase F3 canonical model: with NO contract expiry the canonical
        # calendar decides. 2026-08-13 is a THURSDAY in the TUESDAY era and is
        # NOT an expiry day (weekly expires Tue 2026-08-11 / 2026-08-18).
        # Wrong-weekday trap: a Thursday must never produce a false expiry.
        ev = ExitEvaluator()
        pos = {"position_ref": "P1", "symbol": "NIFTY", "option_type": "CE",
               "strike": 24450, "side": "BUY", "entry_price": 140.0,
               "sl_price": 90.0, "target_price": 240.0, "quantity": 75}
        q = _quote(status="MISSING", price=None, expiry=None)
        d = ev.evaluate_position(pos, quote=q, now=NOW_EXPIRY)
        self.assertFalse(d["is_expiry_day"])       # Thursday is not an expiry day
        self.assertEqual(d["canonical_expiry"], "2026-08-18")
        self.assertEqual(d["skip_reason"], "MISSING_QUOTE")
        # True expiry day in the Tuesday era: Tue 2026-08-11 IS an expiry day.
        d2 = ev.evaluate_position(pos, quote=q,
                                  now=dt.datetime(2026, 8, 11, 15, 5, 0))
        self.assertTrue(d2["is_expiry_day"])
        self.assertEqual(d2["canonical_expiry"], "2026-08-18")
        self.assertEqual(d2["skip_reason"], "NO_EXIT_PRICE_SQUARE_OFF_PENDING")


class TestPriority(unittest.TestCase):
    def _dec(self, now, mark, status="REAL", expiry="13-Aug-2026"):
        ev = ExitEvaluator()
        pos = {"position_ref": "P1", "symbol": "NIFTY", "option_type": "CE",
               "strike": 24450, "side": "BUY", "entry_price": 140.0,
               "sl_price": 90.0, "target_price": 240.0, "quantity": 75}
        q = _quote(status=status, price=mark, expiry=expiry)
        return ev.evaluate_position(pos, quote=q, now=now)

    def test_expiry_over_stop(self):
        d = self._dec(NOW_EXPIRY, mark=80.0)      # also below stop
        self.assertEqual(d["reason"], EXPIRY_SQUARE_OFF)

    def test_expiry_over_target(self):
        d = self._dec(NOW_EXPIRY, mark=260.0)     # also above target
        self.assertEqual(d["reason"], EXPIRY_SQUARE_OFF)

    def test_stop_over_target_impossible_single_price(self):
        # for a long position a single mark cannot be <= stop and >= target
        d = self._dec(NOW_NON_EXPIRY, mark=200.0)
        self.assertEqual(d["reason"], EXIT_NONE)


class TestQuoteFreshness(unittest.TestCase):
    def _dec(self, status, mark=80.0, expiry="18-Aug-2026"):
        ev = ExitEvaluator()
        pos = {"position_ref": "P1", "symbol": "NIFTY", "option_type": "CE",
               "strike": 24450, "side": "BUY", "entry_price": 140.0,
               "sl_price": 90.0, "target_price": 240.0, "quantity": 75}
        q = _quote(status=status, price=mark, expiry=expiry)
        return ev.evaluate_position(pos, quote=q, now=NOW_NON_EXPIRY)

    def test_fresh_can_trigger(self):
        d = self._dec("REAL", mark=80.0)
        self.assertEqual(d["reason"], STOP_LOSS)

    def test_stale_never_silently_triggers_price_exit(self):
        d = self._dec("STALE", mark=80.0)         # would be a stop hit
        self.assertEqual(d["reason"], EXIT_NONE)
        self.assertEqual(d["skip_reason"], "STALE_QUOTE_NO_TRIGGER")

    def test_missing_no_fabrication(self):
        d = self._dec("MISSING", mark=None)
        self.assertEqual(d["skip_reason"], "MISSING_QUOTE")
        self.assertIsNone(d["mark_price"])

    def test_invalid_no_fabrication(self):
        d = self._dec("INVALID", mark=None)
        self.assertEqual(d["skip_reason"], "INVALID_QUOTE")


class TestExecutionViaFsm(unittest.TestCase):
    def _engine_with_position(self, gt_db, acct, **kw):
        e = _open_engine(acct, gt_db)
        ref = _open_position(e, **kw)
        return e, ref

    def _source(self, status="REAL", price=80.0, expiry="18-Aug-2026"):
        return paper_mtm.FakeQuoteSource({
            ("NIFTY", 24450.0, "CE"): _quote(status=status, price=price, expiry=expiry)})

    def test_stop_loss_full_close_via_fsm(self):
        _, acct, gt_db = _make_fixture()
        e, ref = self._engine_with_position(gt_db, acct)
        rep = e.run_exit_checks(quote_source=self._source(price=80.0), now=NOW_NON_EXPIRY)
        self.assertEqual(len(rep["closed"]), 1)
        c = rep["closed"][0]
        self.assertEqual(c["reason"], "STOP_LOSS")
        self.assertEqual(c["exit_reason"], "STOP_LOSS")
        # SELL close slipped: 80*0.985=78.8; gross=(78.8-142.1)*75; fees=80
        expected_net = round((78.8 - 142.1) * 75 - 80.0, 2)
        self.assertEqual(c["realized_net"], expected_net)
        self.assertEqual(e.account["realized_pnl"], expected_net)
        self.assertEqual(e.account["total_fees"], 80.0)
        self.assertEqual(e.derived_positions(), [])

    def test_ground_truth_one_outcome_reason_preserved(self):
        _, acct, gt_db = _make_fixture()
        e, ref = self._engine_with_position(gt_db, acct)
        e.run_exit_checks(quote_source=self._source(price=80.0), now=NOW_NON_EXPIRY)
        db = gt.GroundTruthDB(gt_db)
        counts = db.counts()
        self.assertEqual(counts["executions"], 2)   # entry + exit
        self.assertEqual(counts["positions"], 1)
        self.assertEqual(counts["outcomes"], 1)     # exactly one canonical outcome
        out = db._cur().execute("SELECT exit_reason FROM outcomes").fetchone()
        self.assertEqual(out[0], "STOP_LOSS")
        pos = db._cur().execute("SELECT status FROM positions").fetchone()
        self.assertEqual(pos[0], "CLOSED")
        self.assertTrue(db.integrity_check()["ok"])

    def test_take_profit_reason_preserved(self):
        _, acct, gt_db = _make_fixture()
        e, ref = self._engine_with_position(gt_db, acct)
        e.run_exit_checks(quote_source=self._source(price=260.0), now=NOW_NON_EXPIRY)
        self.assertEqual(e.reconciliation_report()["match_status"], "MATCH")
        db = gt.GroundTruthDB(gt_db)
        self.assertEqual(db._cur().execute("SELECT exit_reason FROM outcomes").fetchone()[0],
                         "TAKE_PROFIT")

    def test_expiry_square_off_reason_preserved(self):
        _, acct, gt_db = _make_fixture()
        e, ref = self._engine_with_position(gt_db, acct)
        e.run_exit_checks(quote_source=self._source(price=150.0, expiry="13-Aug-2026"),
                          now=NOW_EXPIRY)
        self.assertEqual(e.account["realized_pnl"] != 0.0, True)
        db = gt.GroundTruthDB(gt_db)
        self.assertEqual(db._cur().execute("SELECT exit_reason FROM outcomes").fetchone()[0],
                         "EXPIRY_SQUARE_OFF")
        self.assertEqual(db.counts()["outcomes"], 1)

    def test_stale_quote_no_close(self):
        _, acct, gt_db = _make_fixture()
        e, ref = self._engine_with_position(gt_db, acct)
        rep = e.run_exit_checks(quote_source=self._source(status="STALE", price=80.0),
                                now=NOW_NON_EXPIRY)
        self.assertEqual(rep["closed"], [])
        self.assertTrue(any(s["skip_reason"] == "STALE_QUOTE_NO_TRIGGER"
                            for s in rep["skipped"]))
        self.assertEqual(e.derived_positions()[0]["position_ref"], ref)

    def test_idempotent_repeated_runs(self):
        _, acct, gt_db = _make_fixture()
        e, ref = self._engine_with_position(gt_db, acct)
        src = self._source(price=80.0)
        e.run_exit_checks(quote_source=src, now=NOW_NON_EXPIRY)
        r2 = e.run_exit_checks(quote_source=src, now=NOW_NON_EXPIRY)
        self.assertEqual(r2["closed"], [])
        db = gt.GroundTruthDB(gt_db)
        self.assertEqual(db.counts()["executions"], 2)
        self.assertEqual(db.counts()["outcomes"], 1)
        self.assertEqual(e.reconciliation_report()["match_status"], "MATCH")

    def test_partial_close_limitation_documented(self):
        _, acct, gt_db = _make_fixture()
        e, ref = self._engine_with_position(gt_db, acct)
        # close_position always closes the FULL remaining quantity
        e.close_position(ref, 160.0, exit_reason="MANUAL")
        self.assertEqual(e.derived_positions(), [])
        with self.assertRaises(ValueError):
            e.close_position(ref, 200.0, exit_reason="MANUAL")


class TestLegacySafety(unittest.TestCase):
    def test_legacy_never_upgraded_no_fabricated_outcome(self):
        _, acct, gt_db = _make_fixture(with_legacy=True)
        e = _open_engine(acct, gt_db)
        rep = e.run_exit_checks(now=NOW_EXPIRY)
        self.assertEqual(rep["evaluated"], 0)      # only FSM positions evaluated
        self.assertEqual(rep["closed"], [])
        db = gt.GroundTruthDB(gt_db)
        self.assertEqual(db.counts()["executions"], 0)
        self.assertEqual(db.counts()["positions"], 0)
        self.assertEqual(db.counts()["outcomes"], 0)
        self.assertEqual(len(e.account["open_positions"]), 1)
        self.assertEqual(e.account["open_positions"][0]["status"], "OPEN")


class TestReadOnlyExitStatus(unittest.TestCase):
    def test_paper_exit_status_never_closes(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        _open_position(e)
        src = paper_mtm.FakeQuoteSource({
            ("NIFTY", 24450.0, "CE"): _quote(price=80.0)})
        st = e.paper_exit_status(quote_source=src, now=NOW_NON_EXPIRY)
        self.assertEqual(st["open_count"], 1)
        row = st["positions"][0]
        self.assertEqual(row["potential_exit_reason"], "STOP_LOSS")
        self.assertEqual(row["quote_status"], "REAL")
        self.assertEqual(row["stop_price"], 90.0)
        self.assertEqual(row["target_price"], 240.0)
        self.assertEqual(row["distance_to_stop"], 52.1)      # 142.1 - 90
        self.assertEqual(row["distance_to_target"], 97.9)    # 240 - 142.1
        self.assertEqual(row["status"], "OPEN")
        self.assertEqual(st["note"], "read-only exit status; never executes a close")
        # nothing closed, no outcomes
        db = gt.GroundTruthDB(gt_db)
        self.assertEqual(db.counts()["outcomes"], 0)
        self.assertEqual(len(e.derived_positions()), 1)


class TestRunnerIntegration(unittest.TestCase):
    def test_auto_paper_runner_calls_exit_checks_before_gate(self):
        import auto_paper_runner
        calls = []
        def _fake_exit():
            calls.append(1)
            return {"closed": [], "errors": []}
        with mock.patch.object(auto_paper_runner.live_market_fetch,
                               "update_live_market_cache", return_value={}):
            with mock.patch.object(auto_paper_runner.paper_trader.paper_engine,
                                   "run_exit_checks", side_effect=_fake_exit):
                res = auto_paper_runner.run_auto_paper_trader()
        self.assertEqual(res["status"], "STAND_DOWN")   # no spot -> stand down
        self.assertEqual(len(calls), 1)                 # but exits were checked


class TestProductionIsolation(unittest.TestCase):
    def _sha(self, path):
        import hashlib
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def test_production_account_and_ledger_untouched(self):
        acct = "data/paper_account.json"
        gt_db = "data/ground_truth.db"
        sha_acct = self._sha(acct)
        sha_db = self._sha(gt_db)
        e = paper_execution.PaperExecutionEngine()
        # read-only exit status + exit checks (no FSM positions -> no closes)
        st = e.paper_exit_status()
        self.assertEqual(st["open_count"], 0)
        rep = e.run_exit_checks()
        self.assertEqual(rep["closed"], [])
        db = gt.GroundTruthDB()
        self.assertEqual(db.counts()["executions"], 0)
        self.assertEqual(db.counts()["positions"], 0)
        self.assertEqual(db.counts()["outcomes"], 0)
        self.assertEqual(self._sha(acct), sha_acct)
        self.assertEqual(self._sha(gt_db), sha_db)
        self.assertEqual(e.account["cash_balance"], 3381.25)
        self.assertEqual(e.reconciliation_report()["match_status"], "MATCH")


if __name__ == "__main__":
    unittest.main()
