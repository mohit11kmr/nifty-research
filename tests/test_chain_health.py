"""Phase 6.5 - chain health monitor, live observation state and wiring tests.

Tests run on temp DBs only - production ground_truth.db is never touched.
Covers: orphan detection, missing/duplicate outcomes, missing snapshots,
provenance loss, timestamp inconsistencies, invalid state transitions,
zero-trade health and deterministic health output.
"""
import os
import sys
import json
import tempfile
import sqlite3
import unittest
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import truth
import ground_truth as gt
import evaluation_engine as ee

from tests.test_evaluation_engine import _make_env, _record_trade


def _engine(db_path):
    return ee.EvaluationEngine(gt_db=db_path)


def _find(health, ftype):
    return [f for f in health["findings"] if f["type"] == ftype]


class TestChainHealthHealthy(unittest.TestCase):
    def test_full_chain_is_healthy(self):
        tmp = tempfile.mkdtemp()
        db, db_path = _make_env(tmp)
        _record_trade(db, 0.85)
        h = ee.chain_health_report(_engine(db_path), include_generated_at=False)
        self.assertEqual(h["summary"]["health"], "HEALTHY")
        self.assertEqual(h["summary"]["total_findings"], 0)

    def test_zero_trade_state_is_healthy(self):
        """STAY_OUT/SKIP-only ledger (like production) must be HEALTHY."""
        tmp = tempfile.mkdtemp()
        db, db_path = _make_env(tmp)
        ts = "2026-08-12 15:30:00 IST"
        for i in range(5):
            obs = db.record_observation(ts, "NIFTY", 24100.0, "test")
            sid = db.record_signal(ts, "NIFTY", None, "precision_signal", None, None,
                                   None, obs, "v1", None, "v1",
                                   {"_action": "STAY_OUT"},
                                   provenance={"status": truth.REAL, "source": "test"})
            db.record_feature_snapshot(sid, ts, "v1", 600, {}, provenance={"status": truth.REAL})
            db.record_decision("SKIP", signal_id=sid, decision_ts=ts,
                               capital_guard_state="APPROVED", execution_mode="PAPER",
                               provenance={"status": truth.REAL})
        eng = _engine(db_path)
        h = ee.chain_health_report(eng, include_generated_at=False)
        self.assertEqual(h["summary"]["health"], "HEALTHY")
        obs_state = ee.live_observation_report(eng, include_generated_at=False)
        self.assertEqual(obs_state["state"], "NO_DIRECTIONAL_TRADES_YET")
        self.assertTrue(obs_state["health"] == "HEALTHY")

    def test_deterministic_health_output(self):
        tmp = tempfile.mkdtemp()
        db, db_path = _make_env(tmp)
        _record_trade(db, 0.7)
        eng = _engine(db_path)
        a = ee.chain_health_report(eng, include_generated_at=False)
        b = ee.chain_health_report(eng, include_generated_at=False)
        self.assertEqual(json.dumps(a, sort_keys=True, default=str),
                         json.dumps(b, sort_keys=True, default=str))


class TestChainHealthDetection(unittest.TestCase):
    def test_orphan_signal_flagged(self):
        tmp = tempfile.mkdtemp()
        db, db_path = _make_env(tmp)
        ts = "2026-08-12 15:30:00 IST"
        obs = db.record_observation(ts, "NIFTY", 24100.0, "test")
        sid = db.record_signal(ts, "NIFTY", "UP", "precision_signal", "5/6", 0.8,
                               "TREND_HV", obs, "v1", None, "v1", {},
                               provenance={"status": truth.REAL})
        db.record_feature_snapshot(sid, ts, "v1", 600, {})
        # no decision recorded -> orphan signal
        h = ee.chain_health_report(_engine(db_path), include_generated_at=False)
        self.assertIn("ORPHAN_SIGNAL", [f["type"] for f in h["findings"]])
        self.assertEqual(_find(h, "ORPHAN_SIGNAL")[0]["severity"], "WARNING")

    def test_missing_feature_snapshot_flagged(self):
        tmp = tempfile.mkdtemp()
        db, db_path = _make_env(tmp)
        ts = "2026-08-12 15:30:00 IST"
        obs = db.record_observation(ts, "NIFTY", 24100.0, "test")
        db.record_signal(ts, "NIFTY", "UP", "precision_signal", "5/6", 0.8,
                         "TREND_HV", obs, "v1", None, "v1", {},
                         provenance={"status": truth.REAL})
        h = ee.chain_health_report(_engine(db_path), include_generated_at=False)
        self.assertIn("MISSING_FEATURE_SNAPSHOT", [f["type"] for f in h["findings"]])

    def test_legacy_orphan_execution_is_info(self):
        """Legacy executions (no decision) are expected - INFO, not WARNING."""
        tmp = tempfile.mkdtemp()
        db, db_path = _make_env(tmp)
        ts = "2026-08-12 15:30:00 IST"
        db.record_execution(None, "NIFTY", "BUY", 75, 140.0, 140.0, ts,
                            execution_mode="PAPER", estimated_fill=True,
                            provenance={"status": truth.LEGACY, "source": "test"})
        h = ee.chain_health_report(_engine(db_path), include_generated_at=False)
        f = _find(h, "ORPHAN_EXECUTION")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["severity"], "INFO")

    def test_closed_position_without_outcome_is_error(self):
        tmp = tempfile.mkdtemp()
        db, db_path = _make_env(tmp)
        ts = "2026-08-12 15:30:00 IST"
        eid = db.record_execution(None, "NIFTY", "BUY", 75, 140.0, 140.0, ts,
                                  execution_mode="PAPER", estimated_fill=True,
                                  provenance={"status": truth.LEGACY})
        cur = db._cur()
        cur.execute(
            "INSERT INTO positions (entry_execution_id, symbol, side, quantity,"
            " entry_price, entry_timestamp, status, provenance_json)"
            " VALUES (?, ?, ?, ?, ?, ?, 'CLOSED', ?)",
            (eid, "NIFTY", "BUY", 75, 140.0, ts,
             truth.serialize_provenance({"status": truth.LEGACY})))
        db._conn.commit()
        h = ee.chain_health_report(_engine(db_path), include_generated_at=False)
        f = _find(h, "MISSING_OUTCOME")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["severity"], "ERROR")
        self.assertEqual(h["summary"]["health"], "UNHEALTHY")

    def test_duplicate_outcome_is_critical(self):
        """Duplicate outcomes are schema-impossible in the real ledger
        (position_id UNIQUE) - detector is defense-in-depth over a bare DB."""
        tmp = tempfile.mkdtemp()
        db_path = os.path.join(tmp, "bare.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE outcomes (outcome_id INTEGER PRIMARY KEY,"
                     " position_id INTEGER NOT NULL, outcome_class TEXT, provenance_json TEXT)")
        conn.execute("INSERT INTO outcomes (position_id, outcome_class) VALUES (1, 'WIN')")
        conn.execute("INSERT INTO outcomes (position_id, outcome_class) VALUES (1, 'WIN')")
        conn.commit()
        conn.close()
        h = ee.chain_health_report(_engine(db_path), include_generated_at=False)
        f = _find(h, "DUPLICATE_OUTCOME")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["severity"], "CRITICAL")
        self.assertEqual(h["summary"]["health"], "UNHEALTHY")

    def test_orphan_decision_flagged(self):
        tmp = tempfile.mkdtemp()
        db_path = os.path.join(tmp, "bare.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE signals (signal_id INTEGER PRIMARY KEY, signal_ts TEXT)")
        conn.execute("CREATE TABLE decisions (decision_id INTEGER PRIMARY KEY,"
                     " signal_id INTEGER, decision_type TEXT, decision_ts TEXT)")
        conn.execute("INSERT INTO signals (signal_id, signal_ts) VALUES (1, '2026-08-12 15:30:00 IST')")
        conn.execute("INSERT INTO decisions (decision_id, signal_id, decision_type, decision_ts)"
                     " VALUES (1, 999, 'ENTER', '2026-08-12 15:30:00 IST')")
        conn.commit()
        conn.close()
        h = ee.chain_health_report(_engine(db_path), include_generated_at=False)
        f = _find(h, "ORPHAN_DECISION")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["severity"], "WARNING")

    def test_decision_before_signal_flagged(self):
        tmp = tempfile.mkdtemp()
        db, db_path = _make_env(tmp)
        ts = "2026-08-12 15:30:00 IST"
        obs = db.record_observation(ts, "NIFTY", 24100.0, "test")
        sid = db.record_signal(ts, "NIFTY", "UP", "precision_signal", "5/6", 0.8,
                               "TREND_HV", obs, "v1", None, "v1", {},
                               provenance={"status": truth.REAL})
        db.record_decision("ENTER", signal_id=sid,
                           decision_ts="2026-08-12 09:00:00 IST",
                           provenance={"status": truth.REAL})
        h = ee.chain_health_report(_engine(db_path), include_generated_at=False)
        f = _find(h, "TIMESTAMP_INCONSISTENCY")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["severity"], "ERROR")

    def test_provenance_loss_flagged(self):
        tmp = tempfile.mkdtemp()
        db, db_path = _make_env(tmp)
        cur = db._cur()
        cur.execute("INSERT INTO signals (signal_ts, symbol) VALUES ('2026-08-12 15:30:00 IST', 'NIFTY')")
        db._conn.commit()
        h = ee.chain_health_report(_engine(db_path), include_generated_at=False)
        f = _find(h, "PROVENANCE_LOSS")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["severity"], "INFO")

    def test_impossible_quantity_flagged(self):
        tmp = tempfile.mkdtemp()
        db, db_path = _make_env(tmp)
        cur = db._cur()
        cur.execute("INSERT INTO positions (symbol, side, quantity, status, provenance_json)"
                    " VALUES ('NIFTY', 'BUY', 0, 'OPEN', ?)",
                    (truth.serialize_provenance({"status": truth.REAL}),))
        db._conn.commit()
        h = ee.chain_health_report(_engine(db_path), include_generated_at=False)
        f = _find(h, "INVALID_STATE_TRANSITION")
        self.assertTrue(any("quantity" in x["evidence"] for x in f))
        self.assertEqual(h["summary"]["health"], "UNHEALTHY")


class TestObservationState(unittest.TestCase):
    def test_state_classification(self):
        self.assertEqual(ee.observation_state({"counts": {"predictions": 0, "executions": 0, "outcomes": 0}}),
                         "NO_DIRECTIONAL_TRADES_YET")
        self.assertEqual(ee.observation_state({"counts": {"predictions": 2, "executions": 1, "outcomes": 0}}),
                         "PENDING_OUTCOMES")
        self.assertEqual(ee.observation_state({"counts": {"predictions": 2, "executions": 2, "outcomes": 1}}),
                         "ACCUMULATING_OUTCOMES")


if __name__ == "__main__":
    unittest.main()
