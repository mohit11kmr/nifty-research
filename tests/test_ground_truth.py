"""Ground-truth ledger tests (Phase 4B): immutable chain recording, outcome
engine, prediction evaluation, reproducibility and legacy paper import.

unittest style (repo convention). All DB/history/research writes are
redirected to temp files - no production data is touched.
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

SIG = {
    "signal_action": "HIGH_CONVICTION_CALL",
    "signal_grade": "A+ GRADE (SUPER PRECISE)",
    "confluence_score": "5/6 (83%)",
    "nifty_spot": 24150.0,
    "vix": 13.5,
    "vix_zone": "NORMAL",
    "market_state": "TREND_HV",
    "confluence_checks": {
        "regime_layer": {"status": "PASSED"},
        "technical_layer": {"status": "PASSED", "bias": "CALL"},
    },
}


def _make_env(tmp):
    """Point history csv + research db + ground truth db at temp paths."""
    nifty_csv = os.path.join(tmp, "nifty_history.csv")
    with open(nifty_csv, "w") as f:
        f.write("Date,Open,High,Low,Close,Volume\n"
                "2026-08-10,24000,24100,23900,24050,100\n"
                "2026-08-12,24100,24200,24000,24150,100\n"
                "2026-08-13,24150,24200,24050,24100,100\n")
    gt.NIFTY_HISTORY_CSV = nifty_csv
    gt.RESEARCH_DB = os.path.join(tmp, "research.db")
    return gt.GroundTruthDB(os.path.join(tmp, "ground_truth.db"))


def _make_ticks(tmp):
    conn = sqlite3.connect(os.path.join(tmp, "research.db"))
    conn.execute("CREATE TABLE ticks (recv_ts TEXT, symbol TEXT, expiry TEXT,"
                 " strike REAL, side TEXT, ltp REAL)")
    rows = [("2026-08-13T09:30:00", "NIFTY", "18-Aug-2026", 24450.0, "CE", 130.0),
            ("2026-08-13T11:00:00", "NIFTY", "18-Aug-2026", 24450.0, "CE", 145.0),
            ("2026-08-13T13:00:00", "NIFTY", "18-Aug-2026", 24450.0, "CE", 120.0),
            ("2026-08-13T14:30:00", "NIFTY", "18-Aug-2026", 24450.0, "CE", 165.0)]
    conn.executemany("INSERT INTO ticks VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def _record_past_chain(db):
    """Record a chain dated 2026-08-12 so the next-session close exists."""
    obs = db.record_observation("2026-08-12 15:30:00 IST", "NIFTY", 24100.0, "test")
    sid = db.record_signal("2026-08-12 15:30:00 IST", "NIFTY", "UP", "precision_signal",
                           "5/6", None, "TREND_HV", obs, "v1", None, "v1",
                           {"_action": "HIGH_CONVICTION_CALL", "_grade": "A+ GRADE (SUPER PRECISE)"})
    db.record_feature_snapshot(sid, "2026-08-12 15:30:00 IST", "v1", 7200,
                               {"nifty_spot": 24100.0})
    pid = db.record_prediction(sid, "UP", 24100.0, horizon="next_trading_session_close",
                               horizon_end_ts="2026-08-13",
                               prediction_ts="2026-08-12 15:30:00 IST")
    db.record_decision("ENTER", signal_id=sid, prediction_id=pid,
                       decision_ts="2026-08-12 15:30:05 IST")
    return sid, pid


class TestChainRecording(unittest.TestCase):
    def test_full_chain_linked(self):
        tmp = tempfile.mkdtemp()
        db = _make_env(tmp)
        # past-dated "now" so the chain's horizon has a next session close
        with mock.patch.object(gt, "now_str",
                               return_value="2026-08-12 15:30:00 IST"):
            chain = db.record_signal_chain(SIG, capital_guard_audit={"safety_status": "APPROVED"})
        self.assertIsNotNone(chain["signal_id"])
        self.assertIsNotNone(chain["prediction_id"])
        self.assertIsNotNone(chain["decision_id"])
        sig = db.get_signal(chain["signal_id"])
        self.assertEqual(sig["direction"], "UP")
        self.assertEqual(sig["score"], "5/6 (83%)")
        self.assertEqual(sig["checks_json"]["_grade"], "A+ GRADE (SUPER PRECISE)")
        dec = db.get_decision(chain["decision_id"])
        self.assertEqual(dec["decision_type"], "ENTER")
        self.assertEqual(dec["signal_id"], chain["signal_id"])
        self.assertEqual(dec["prediction_id"], chain["prediction_id"])
        pred = db.get_prediction(chain["prediction_id"])
        self.assertEqual(pred["predicted_direction"], "UP")
        self.assertIsNotNone(pred["horizon_end_ts"])
        self.assertEqual(gt._parse_ts(pred["horizon_end_ts"]).date().isoformat(), "2026-08-13")

    def test_stay_out_records_skip_decision_no_prediction(self):
        tmp = tempfile.mkdtemp()
        db = _make_env(tmp)
        sig = dict(SIG)
        sig["signal_action"] = "STAY_OUT"
        sig["signal_grade"] = "NO_SIGNAL (FILTERED OUT NOISE)"
        chain = db.record_signal_chain(sig)
        self.assertIsNone(chain["prediction_id"])
        self.assertEqual(db.get_decision(chain["decision_id"])["decision_type"], "SKIP")


class TestAppendOnly(unittest.TestCase):
    def test_signal_update_blocked(self):
        tmp = tempfile.mkdtemp()
        db = _make_env(tmp)
        sid, _ = _record_past_chain(db)
        with self.assertRaises(sqlite3.IntegrityError):
            db._cur().execute("UPDATE signals SET score=? WHERE signal_id=?", ("99", sid))
            db._conn.commit()

    def test_signal_delete_blocked(self):
        tmp = tempfile.mkdtemp()
        db = _make_env(tmp)
        sid, _ = _record_past_chain(db)
        with self.assertRaises(sqlite3.IntegrityError):
            db._cur().execute("DELETE FROM signals WHERE signal_id=?", (sid,))
            db._conn.commit()

    def test_position_entry_price_immutable(self):
        tmp = tempfile.mkdtemp()
        db = _make_env(tmp)
        eid = db.record_execution(None, "NIFTY", "BUY", 75, 140.0, 140.0,
                                  "2026-08-13 10:00:00 IST", strike=24450, option_type="CE")
        pid = db.record_position(eid, "NIFTY", "BUY", 75, 140.0,
                                 "2026-08-13 10:00:00 IST", status="OPEN",
                                 strike=24450, option_type="CE")
        with self.assertRaises(sqlite3.IntegrityError):
            db._cur().execute("UPDATE positions SET entry_price=999 WHERE position_id=?", (pid,))
            db._conn.commit()

    def test_double_close_blocked(self):
        tmp = tempfile.mkdtemp()
        db = _make_env(tmp)
        eid = db.record_execution(None, "NIFTY", "BUY", 75, 140.0, 140.0,
                                  "2026-08-13 10:00:00 IST", strike=24450, option_type="CE")
        pid = db.record_position(eid, "NIFTY", "BUY", 75, 140.0,
                                 "2026-08-13 10:00:00 IST", status="OPEN",
                                 strike=24450, option_type="CE")
        db.close_position(pid, 180.0, "2026-08-13 15:00:00 IST", "TARGET")
        with self.assertRaises(ValueError):
            db.close_position(pid, 190.0, "2026-08-13 15:10:00 IST", "TARGET")


class TestOutcomeEngine(unittest.TestCase):
    def test_win_loss_breakeven_and_fees(self):
        tmp = tempfile.mkdtemp()
        db = _make_env(tmp)
        for exit_price, fees, slp, expect in [(180.0, 0, 0, "WIN"),
                                              (100.0, 0, 0, "LOSS"),
                                              (141.0, 50.0, 25.0, "BREAKEVEN")]:
            eid = db.record_execution(None, "NIFTY", "BUY", 75, 140.0, 140.0,
                                      "2026-08-13 10:00:00 IST", fees=fees, slippage=slp,
                                      strike=24450, option_type="CE")
            pid = db.record_position(eid, "NIFTY", "BUY", 75, 140.0,
                                     "2026-08-13 10:00:00 IST", status="OPEN",
                                     strike=24450, option_type="CE")
            db.close_position(pid, exit_price, "2026-08-13 15:00:00 IST", "TARGET",
                              fees=fees, slippage=slp)
            oc = db.get_outcome(pid)
            self.assertEqual(oc["outcome_class"], expect)
            self.assertEqual(oc["duration_s"], 18000.0)

    def test_mfe_mae_from_ticks(self):
        tmp = tempfile.mkdtemp()
        _make_ticks(tmp)
        db = _make_env(tmp)
        eid = db.record_execution(None, "NIFTY", "BUY", 75, 140.0, 140.0,
                                  "2026-08-13 09:30:00 IST", strike=24450, option_type="CE")
        pid = db.record_position(eid, "NIFTY", "BUY", 75, 140.0,
                                 "2026-08-13 09:30:00 IST", status="OPEN",
                                 strike=24450, option_type="CE")
        db.close_position(pid, 165.0, "2026-08-13 14:30:00 IST", "TARGET")
        oc = db.get_outcome(pid)
        self.assertEqual(oc["mfe"], 25.0)
        self.assertEqual(oc["mae"], 20.0)
        self.assertEqual(oc["mfe_source"], "FULL")

    def test_no_tick_data_mfe_none(self):
        tmp = tempfile.mkdtemp()
        db = _make_env(tmp)
        eid = db.record_execution(None, "NIFTY", "BUY", 75, 140.0, 140.0,
                                  "2026-08-13 10:00:00 IST", strike=24450, option_type="CE")
        pid = db.record_position(eid, "NIFTY", "BUY", 75, 140.0,
                                 "2026-08-13 10:00:00 IST", status="OPEN",
                                 strike=24450, option_type="CE")
        db.close_position(pid, 180.0, "2026-08-13 15:00:00 IST", "TARGET")
        oc = db.get_outcome(pid)
        self.assertIsNone(oc["mfe"])
        self.assertEqual(oc["mfe_source"], "NONE")


class TestPredictionEvaluation(unittest.TestCase):
    def test_evaluated_past_signal(self):
        tmp = tempfile.mkdtemp()
        db = _make_env(tmp)
        sid, pid = _record_past_chain(db)
        self.assertEqual(db.evaluate_pending_predictions(), 1)
        ev = db.get_evaluation(prediction_id=pid)
        self.assertEqual(ev["prediction_correct"], "NEUTRAL")
        self.assertEqual(ev["status"], "DONE")
        self.assertEqual(ev["actual_move"], 0.0)  # 24100 -> 24100 flat

    def test_today_signal_stays_pending(self):
        tmp = tempfile.mkdtemp()
        db = _make_env(tmp)
        chain = db.record_signal_chain(SIG)
        self.assertEqual(db.evaluate_pending_predictions(), 0)
        self.assertIsNone(db.get_evaluation(prediction_id=chain["prediction_id"]))


class TestReproducibility(unittest.TestCase):
    def test_verify_reproducible(self):
        tmp = tempfile.mkdtemp()
        db = _make_env(tmp)
        chain = db.record_signal_chain(SIG, capital_guard_audit={"safety_status": "APPROVED"})
        repro = db.verify_reproducibility(chain["signal_id"])
        self.assertTrue(repro["reproducible"])
        failed = [k for k, v in repro["checks"].items() if v is False]
        self.assertEqual(failed, [])

    def test_decision_after_signal_timestamp(self):
        tmp = tempfile.mkdtemp()
        db = _make_env(tmp)
        chain = db.record_signal_chain(SIG)
        sig = db.get_signal(chain["signal_id"])
        dec = db.get_decision(chain["decision_id"])
        self.assertGreaterEqual(gt._parse_ts(dec["decision_ts"]), gt._parse_ts(sig["signal_ts"]))


class TestLegacyImport(unittest.TestCase):
    def test_idempotent_import_with_legacy_provenance(self):
        tmp = tempfile.mkdtemp()
        db = _make_env(tmp)
        acct = os.path.join(tmp, "paper_account.json")
        with open(acct, "w") as f:
            json.dump({"open_positions": [{
                "position_id": "POS_LEG_1",
                "timestamp": "2026-08-12 10:15:02 IST",
                "symbol": "NIFTY", "side": "BUY", "option_type": "CE",
                "strike": 24450, "lots": 1, "quantity": 75,
                "entry_price": 140.0, "sl_price": 90.0, "target_price": 240.0,
                "status": "OPEN"}], "closed_trades": []}, f)
        self.assertEqual(db.import_legacy_paper_positions(account_file=acct), 1)
        self.assertEqual(db.import_legacy_paper_positions(account_file=acct), 0)
        pid = db.position_id_by_ref("POS_LEG_1")
        pos = db.get_position(pid)
        self.assertEqual(pos["status"], "OPEN")
        self.assertEqual(pos["provenance"]["status"], "LEGACY")
        exec_ = db.get_execution(pos["entry_execution_id"])
        self.assertEqual(exec_["execution_mode"], "PAPER")
        self.assertIsNone(exec_["decision_id"])


class TestIntegrityGate(unittest.TestCase):
    def test_integrity_ok_after_valid_flow(self):
        tmp = tempfile.mkdtemp()
        db = _make_env(tmp)
        chain = db.record_signal_chain(SIG)
        eid = db.record_execution(chain["decision_id"], "NIFTY", "BUY", 75, 140.0, 140.0,
                                  "2026-08-13 10:00:00 IST", strike=24450, option_type="CE")
        pid = db.record_position(eid, "NIFTY", "BUY", 75, 140.0,
                                 "2026-08-13 10:00:00 IST", status="OPEN",
                                 position_ref="POS_1", strike=24450, option_type="CE")
        db.close_position(pid, 180.0, "2026-08-13 15:00:00 IST", "TARGET")
        self.assertTrue(db.integrity_check()["ok"])


class TestLegacyApiCompatibility(unittest.TestCase):
    def test_row_to_dict_column_names(self):
        tmp = tempfile.mkdtemp()
        db = _make_env(tmp)
        sid, pid = _record_past_chain(db)
        sig = db.get_signal(sid)
        self.assertIn("signal_id", sig)
        self.assertIn("direction", sig)
        self.assertEqual(sig["score"], "5/6")
        self.assertEqual(sig["checks_json"]["_grade"], "A+ GRADE (SUPER PRECISE)")
        self.assertEqual(db.get_prediction(pid)["predicted_direction"], "UP")


if __name__ == "__main__":
    unittest.main()
