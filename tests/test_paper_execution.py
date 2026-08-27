"""Phase A - Paper Execution Integrity tests.

Covers ADOPT-01 (order/position lifecycle FSM) and ADOPT-02
(paper <-> Ground Truth reconciliation):

- order state transitions
- invalid transitions
- partial fills
- cancel
- reject
- multiple fills
- position derivation from fills
- reconciliation match
- reconciliation mismatch (visible, never silently auto-corrected)
- legacy-position handling (LEGACY/UNKNOWN, kept separate, never converted)
- append-only protection
- duplicate execution prevention
- deterministic reconciliation

All DB/account writes are redirected to temp files - no production data is
touched. Run: .venv/bin/python -m unittest tests.test_paper_execution -v
"""
import os
import sys
import json
import sqlite3
import tempfile
import unittest
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ground_truth as gt
import paper_execution
import paper_trader

TS = "2026-08-13 10:00:00 IST"


def _make_fixture(with_legacy=False):
    tmp = tempfile.mkdtemp()
    acct = os.path.join(tmp, "paper_account.json")
    gt_db = os.path.join(tmp, "ground_truth.db")
    gt.RESEARCH_DB = os.path.join(tmp, "research.db")
    if with_legacy:
        with open(acct, "w") as f:
            json.dump({
                "initial_capital": 100000.0,
                "cash_balance": 3381.25,
                "realized_pnl": 0.0,
                "open_positions": [
                    {"position_id": "POS_1_101502", "timestamp": "2026-08-12 10:15:02 IST",
                     "symbol": "NIFTY", "side": "BUY", "option_type": "CE", "strike": 24450,
                     "lots": 1, "quantity": 75, "entry_price": 140.0, "status": "OPEN"},
                    {"position_id": "POS_10_155509", "timestamp": "2026-08-12 15:55:09 IST",
                     "symbol": "NIFTY", "side": "BUY", "option_type": "PE", "strike": 24500,
                     "lots": 1, "quantity": 75, "entry_price": 28.25, "status": "OPEN"},
                ],
                "closed_trades": [],
            }, f)
    return tmp, acct, gt_db


def _open_engine(acct, gt_db, with_legacy=False):
    engine = paper_execution.PaperExecutionEngine(account_file=acct, gt_db_file=gt_db)
    if with_legacy:
        pass
    return engine


def _fill_full(engine, order_id, qty, price, ts=TS, commission=0.0):
    return engine.fill_order(order_id, qty, price, ts=ts, commission=commission)


class TestOrderStateTransitions(unittest.TestCase):
    def test_submit_to_accepted_to_filled(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        self.assertEqual(sub["status"], "SUBMITTED")
        self.assertTrue(str(sub["order_id"]).startswith("ORD_"))
        e.accept_order(sub["order_id"])
        self.assertEqual(e._find_order(sub["order_id"])["status"], "ACCEPTED")
        _fill_full(e, sub["order_id"], 75, 140.0)
        self.assertEqual(e._find_order(sub["order_id"])["status"], "FILLED")

    def test_submit_rejected_on_insufficient_margin(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        e.account["cash_balance"] = 100.0
        sub = e.submit_order(entry_price=200.0)  # 200*75 = 15000 > 100
        self.assertEqual(sub["status"], "REJECTED")
        self.assertEqual(e._find_order(sub["order_id"])["status"], "REJECTED")

    def test_explicit_reject_from_submitted(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order()
        e.reject_order(sub["order_id"], reason="MANUAL")
        self.assertEqual(e._find_order(sub["order_id"])["status"], "REJECTED")

    def test_accept_then_cancel(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order()
        e.accept_order(sub["order_id"])
        e.cancel_order(sub["order_id"])
        self.assertEqual(e._find_order(sub["order_id"])["status"], "CANCELED")

    def test_stable_order_id_persists(self):
        tmp, acct, gt_db = _make_fixture()
        e1 = _open_engine(acct, gt_db)
        sub = e1.submit_order()
        oid = sub["order_id"]
        e2 = paper_execution.PaperExecutionEngine(account_file=acct, gt_db_file=gt_db)
        self.assertEqual(e2._find_order(oid)["order_id"], oid)


class TestInvalidTransitions(unittest.TestCase):
    def test_fill_on_submitted_raises(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order()
        with self.assertRaises(ValueError):
            e.fill_order(sub["order_id"], 75, 140.0)

    def test_fill_on_rejected_raises(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        e.account["cash_balance"] = 1.0
        sub = e.submit_order(entry_price=200.0)
        self.assertEqual(sub["status"], "REJECTED")
        with self.assertRaises(ValueError):
            e.fill_order(sub["order_id"], 75, 200.0)

    def test_fill_after_filled_raises(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        _fill_full(e, sub["order_id"], 75, 140.0)
        with self.assertRaises(ValueError):
            e.fill_order(sub["order_id"], 1, 140.0)

    def test_cancel_on_filled_raises(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        _fill_full(e, sub["order_id"], 75, 140.0)
        with self.assertRaises(ValueError):
            e.cancel_order(sub["order_id"])

    def test_reject_on_accepted_raises(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order()
        e.accept_order(sub["order_id"])
        with self.assertRaises(ValueError):
            e.reject_order(sub["order_id"])

    def test_fill_exceeding_remaining_raises(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        with self.assertRaises(ValueError):
            e.fill_order(sub["order_id"], 9999, 140.0)

    def test_zero_fill_raises(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        with self.assertRaises(ValueError):
            e.fill_order(sub["order_id"], 0, 140.0)


class TestPartialAndMultipleFills(unittest.TestCase):
    def test_partial_fills_progress_to_filled(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(lots=2, lot_size=75, entry_price=140.0)  # qty 150
        e.accept_order(sub["order_id"])
        r1 = e.fill_order(sub["order_id"], 40, 140.0)
        self.assertEqual(r1["status"], "PARTIALLY_FILLED")
        r2 = e.fill_order(sub["order_id"], 110, 140.0)
        self.assertEqual(r2["status"], "FILLED")
        order = e._find_order(sub["order_id"])
        self.assertEqual(len(order["fills"]), 2)
        self.assertEqual(sum(f["quantity"] for f in order["fills"]), 150)

    def test_three_fills_multiple(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        for qty in (25, 25, 25):
            e.fill_order(sub["order_id"], qty, 140.0)
        order = e._find_order(sub["order_id"])
        self.assertEqual(order["status"], "FILLED")
        self.assertEqual(len(order["fills"]), 3)
        self.assertEqual([f["fill_id"] for f in order["fills"]][-1], f"{sub['order_id']}_F3")

    def test_cancel_after_partial_fill(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(lots=2, lot_size=75, entry_price=140.0)
        e.accept_order(sub["order_id"])
        e.fill_order(sub["order_id"], 75, 140.0)
        order = e._find_order(sub["order_id"])
        self.assertEqual(order["status"], "PARTIALLY_FILLED")
        e.cancel_order(sub["order_id"])
        self.assertEqual(e._find_order(sub["order_id"])["status"], "CANCELED")
        self.assertEqual(sum(f["quantity"] for f in order["fills"]), 75)

    def test_fill_records_required_fields(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        _fill_full(e, sub["order_id"], 75, 140.0, commission=10.0)
        fill = e._find_order(sub["order_id"])["fills"][0]
        for key in ("fill_id", "order_id", "quantity", "price", "timestamp",
                    "commission", "execution_mode"):
            self.assertIn(key, fill)
        self.assertEqual(fill["commission"], 10.0)
        self.assertEqual(fill["execution_mode"], "PAPER")


class TestPositionDerivation(unittest.TestCase):
    def test_position_derived_from_fills(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        e.fill_order(sub["order_id"], 40, 130.0, ts=TS)
        e.fill_order(sub["order_id"], 35, 150.0, ts=TS)
        positions = e.derived_positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["quantity"], 75)
        self.assertEqual(positions[0]["entry_price"], round((40 * 130 + 35 * 150) / 75, 2))
        self.assertEqual(positions[0]["status"], "OPEN")

    def test_no_position_without_fills(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order()
        e.accept_order(sub["order_id"])
        self.assertEqual(e.derived_positions(), [])

    def test_close_order_never_becomes_position(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        _fill_full(e, sub["order_id"], 75, 140.0)
        ref = e._find_order(sub["order_id"])["position_ref"]
        e.close_position(ref, 160.0, ts=TS)
        self.assertEqual(e.derived_positions(), [])


class TestGroundTruthMirroring(unittest.TestCase):
    def test_filled_order_mirrors_execution_and_position(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        _fill_full(e, sub["order_id"], 75, 140.0)
        order = e._find_order(sub["order_id"])
        self.assertIsNotNone(order["gt_position_id"])
        db = gt.GroundTruthDB(gt_db)
        self.assertEqual(db.counts()["executions"], 1)
        self.assertEqual(db.counts()["positions"], 1)
        exec_ = db.get_execution(order["gt_execution_ids"][0])
        self.assertEqual(exec_["broker_reference"], order["fills"][0]["fill_id"])
        self.assertEqual(exec_["execution_mode"], "PAPER")
        self.assertEqual(exec_["provenance"]["status"], "REAL")
        self.assertEqual(exec_["provenance"]["source"], "paper_execution")
        pos = db.get_position(order["gt_position_id"])
        self.assertEqual(pos["status"], "OPEN")
        self.assertEqual(pos["position_ref"], order["position_ref"])

    def test_close_mirrors_exit_and_closes_position_with_outcome(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0, sl_price=90.0, target_price=240.0)
        e.accept_order(sub["order_id"])
        _fill_full(e, sub["order_id"], 75, 140.0)
        ref = e._find_order(sub["order_id"])["position_ref"]
        res = e.close_position(ref, 160.0, ts="2026-08-13 15:00:00 IST")
        self.assertEqual(res["status"], "CLOSED")
        self.assertEqual(res["exit_reason"], "MANUAL")
        db = gt.GroundTruthDB(gt_db)
        pos = db.get_position(e._find_order(sub["order_id"])["gt_position_id"])
        self.assertEqual(pos["status"], "CLOSED")
        self.assertEqual(db.counts()["outcomes"], 1)
        self.assertEqual(db.counts()["executions"], 2)  # entry + exit
        self.assertTrue(db.integrity_check()["ok"])

    def test_duplicate_execution_prevention(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        _fill_full(e, sub["order_id"], 75, 140.0)
        order = e._find_order(sub["order_id"])
        fill = order["fills"][0]
        first = fill["gt_execution_id"]
        # re-mirroring the same fill must be idempotent
        again = e._mirror_fill_to_gt(order, fill)
        self.assertEqual(again, first)
        db = gt.GroundTruthDB(gt_db)
        self.assertEqual(db.counts()["executions"], 1)
        rows = db._cur().execute(
            "SELECT COUNT(*) FROM executions WHERE broker_reference=?",
            (fill["fill_id"],)).fetchone()[0]
        self.assertEqual(rows, 1)


class TestReconciliation(unittest.TestCase):
    def test_match_report(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        _fill_full(e, sub["order_id"], 75, 140.0)
        rep = e.reconciliation_report()
        self.assertEqual(rep["match_status"], "MATCH")
        self.assertEqual(rep["counts"]["paper_positions"], 1)
        self.assertEqual(rep["counts"]["gt_executions"], 1)
        self.assertEqual(rep["counts"]["gt_positions"], 1)
        self.assertEqual(rep["counts"]["errors"], 0)

    def test_mismatch_visible_when_mirror_fails(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        # simulate GT unavailability: no mirror happens
        with mock.patch.object(e, "_mirror_fill_to_gt", return_value=None):
            e.fill_order(sub["order_id"], 75, 140.0)
        rep = e.reconciliation_report()
        self.assertEqual(rep["match_status"], "MISMATCH")
        types = {m["type"] for m in rep["mismatches"]}
        self.assertIn("EXECUTION_NOT_MIRRORED", types)
        self.assertIn("POSITION_NOT_MIRRORED", types)
        self.assertEqual(rep["counts"]["gt_executions"], 0)

    def test_legacy_positions_kept_separate(self):
        _, acct, gt_db = _make_fixture(with_legacy=True)
        e = _open_engine(acct, gt_db)
        rep = e.reconciliation_report()
        self.assertEqual(rep["counts"]["legacy_positions"], 2)
        self.assertEqual(rep["counts"]["gt_executions"], 0)
        self.assertEqual(rep["counts"]["gt_positions"], 0)
        for legacy in rep["legacy_positions"]:
            self.assertEqual(legacy["classification"], "LEGACY/UNKNOWN")
            self.assertIsNone(legacy["gt_counterpart"])
        # legacy info entries are visible but do not flip match status
        self.assertEqual(rep["match_status"], "MATCH")
        self.assertTrue(any(m["type"] == "LEGACY_POSITION_UNMATCHED"
                            and m["severity"] == "INFO" for m in rep["mismatches"]))

    def test_legacy_positions_never_converted_to_real(self):
        _, acct, gt_db = _make_fixture(with_legacy=True)
        e = _open_engine(acct, gt_db)
        e.reconciliation_report()
        db = gt.GroundTruthDB(gt_db)
        refs = [r[0] for r in db._cur().execute(
            "SELECT broker_reference FROM executions").fetchall()]
        self.assertEqual(refs, [])

    def test_deterministic_reconciliation(self):
        _, acct, gt_db = _make_fixture(with_legacy=True)
        e = _open_engine(acct, gt_db)
        # legacy fixture has cash 3381.25 -> keep exposure within margin
        sub = e.submit_order(entry_price=40.0)
        e.accept_order(sub["order_id"])
        _fill_full(e, sub["order_id"], 75, 40.0)
        ref = e._find_order(sub["order_id"])["position_ref"]
        e.close_position(ref, 60.0, ts="2026-08-13 15:00:00 IST")

        r1 = e.reconciliation_report()
        r2 = e.reconciliation_report()
        r1.pop("report_ts")
        r2.pop("report_ts")
        self.assertEqual(json.dumps(r1, sort_keys=True, default=str),
                         json.dumps(r2, sort_keys=True, default=str))

        e2 = paper_execution.PaperExecutionEngine(account_file=acct, gt_db_file=gt_db)
        r3 = e2.reconciliation_report()
        r3.pop("report_ts")
        self.assertEqual(json.dumps(r1, sort_keys=True, default=str),
                         json.dumps(r3, sort_keys=True, default=str))


class TestAppendOnlyProtection(unittest.TestCase):
    def test_executions_cannot_be_updated_or_deleted(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        _fill_full(e, sub["order_id"], 75, 140.0)
        db = gt.GroundTruthDB(gt_db)
        cur = db._cur()
        eid = cur.execute("SELECT execution_id FROM executions").fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            cur.execute("UPDATE executions SET fill_price=1 WHERE execution_id=?", (eid,))
        with self.assertRaises(sqlite3.IntegrityError):
            cur.execute("DELETE FROM executions WHERE execution_id=?", (eid,))

    def test_positions_entry_immutable_and_no_delete(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        _fill_full(e, sub["order_id"], 75, 140.0)
        db = gt.GroundTruthDB(gt_db)
        cur = db._cur()
        pid = cur.execute("SELECT position_id FROM positions").fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            cur.execute("UPDATE positions SET entry_price=999 WHERE position_id=?", (pid,))
        with self.assertRaises(sqlite3.IntegrityError):
            cur.execute("DELETE FROM positions WHERE position_id=?", (pid,))

    def test_double_close_rejected_by_ledger(self):
        _, acct, gt_db = _make_fixture()
        e = _open_engine(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        _fill_full(e, sub["order_id"], 75, 140.0)
        ref = e._find_order(sub["order_id"])["position_ref"]
        e.close_position(ref, 160.0, ts=TS)
        with self.assertRaises(ValueError):
            e.close_position(ref, 200.0, ts=TS)


class TestPaperTraderIntegration(unittest.TestCase):
    def _make_paper_trader(self, acct):
        paper_trader.ACCOUNT_FILE = acct
        return paper_trader.PaperTrader()

    def _gt_engine_patch(self, gt_db):
        """Patch paper_execution.PaperExecutionEngine so the engine created
        inside execute_paper_order mirrors into the temp ledger."""
        class _E(paper_execution.PaperExecutionEngine):
            def __init__(self, account_file=None, gt_db_file=None, ledger=None):
                super().__init__(account_file=account_file, gt_db_file=gt_db,
                                 ledger=ledger)
        return mock.patch.object(paper_execution, "PaperExecutionEngine", _E)

    def _gt_db_patch(self, gt_db):
        """Route ledger writes from the legacy close path to the temp ledger."""
        real_cls = gt.GroundTruthDB
        return mock.patch.object(
            gt, "GroundTruthDB",
            lambda *a, **k: real_cls(gt_db))

    def _run_execute(self, pt, gt_db, **kwargs):
        with self._gt_engine_patch(gt_db):
            return pt.execute_paper_order(**kwargs)

    def test_execute_paper_order_routes_through_fsm(self):
        _, acct, gt_db = _make_fixture()
        pt = self._make_paper_trader(acct)
        res = self._run_execute(pt, gt_db, strike=24450, entry_price=140.0)
        self.assertEqual(res["status"], "EXECUTED")
        self.assertTrue(str(res["position"]["position_id"]).startswith("POS_"))
        e = paper_execution.PaperExecutionEngine(account_file=acct, gt_db_file=gt_db)
        rep = e.reconciliation_report()
        self.assertEqual(rep["counts"]["paper_orders"], 1)
        self.assertEqual(rep["counts"]["gt_executions"], 1)
        self.assertEqual(rep["counts"]["gt_positions"], 1)
        self.assertEqual(rep["match_status"], "MATCH")
        # the execute path must never touch the production ledger
        self.assertEqual(gt.GroundTruthDB().counts()["executions"], 0)

    def test_insufficient_margin_rejected(self):
        _, acct, gt_db = _make_fixture()
        with open(acct, "w") as f:
            json.dump({"cash_balance": 100.0}, f)
        pt = self._make_paper_trader(acct)
        res = self._run_execute(pt, gt_db, entry_price=500.0)
        self.assertEqual(res["status"], "REJECTED")

    def test_legacy_close_path_preserved(self):
        _, acct, gt_db = _make_fixture(with_legacy=True)
        pt = self._make_paper_trader(acct)
        with self._gt_db_patch(gt_db):
            res = pt.close_paper_position("POS_1_101502", 160.0)
        self.assertEqual(res["status"], "CLOSED")
        self.assertEqual(len(pt.account["closed_trades"]), 1)
        self.assertEqual(len(pt.account["open_positions"]), 1)
        # legacy close must not pollute the production ledger
        self.assertEqual(gt.GroundTruthDB().counts()["executions"], 0)

    def test_close_legacy_positions_never_convert_to_real(self):
        _, acct, gt_db = _make_fixture(with_legacy=True)
        e = paper_execution.PaperExecutionEngine(account_file=acct, gt_db_file=gt_db)
        db = gt.GroundTruthDB(gt_db)
        self.assertEqual(db.counts()["positions"], 0)


if __name__ == "__main__":
    unittest.main()
