"""Phase 4A tests: P-05 provenance persistence, P-06 ML freshness, P-15 cache recovery.

unittest style (matches the repo's test convention). All DB/cache writes are
redirected to temp files - no production data is modified by these tests.
"""
import os
import sys
import json
import shutil
import tempfile
import unittest
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import truth
import history_logger


# --------------------------------------------------------------------------
# P-05: Provenance persistence
# --------------------------------------------------------------------------
class TestCanonicalProvenance(unittest.TestCase):
    def test_canonical_provenance_filters_none(self):
        prov = truth.canonical_provenance(status=truth.REAL, source="x",
                                          fallback_reason=None, missing=None,
                                          fallback_used=True)
        self.assertNotIn("fallback_reason", prov)
        self.assertNotIn("missing", prov)
        self.assertEqual(prov["status"], truth.REAL)
        self.assertEqual(prov["source"], "x")
        self.assertIs(prov["fallback_used"], True)

    def test_canonical_provenance_defaults_unknown(self):
        prov = truth.canonical_provenance(source="y")
        self.assertEqual(prov["status"], truth.UNKNOWN)

    def test_canonical_provenance_empty_becomes_unknown(self):
        prov = truth.canonical_provenance()
        self.assertEqual(prov["status"], truth.UNKNOWN)

    def test_serialize_deserialize_roundtrip(self):
        prov = truth.canonical_provenance(status=truth.FALLBACK, source="db:spot",
                                          fallback_used=True, fallback_reason=truth.MISSING)
        back = truth.deserialize_provenance(truth.serialize_provenance(prov))
        self.assertEqual(back, prov)

    def test_legacy_row_reads_as_legacy_never_real(self):
        self.assertEqual(truth.deserialize_provenance(None)["status"], truth.LEGACY)
        self.assertNotEqual(truth.deserialize_provenance(None)["status"], truth.REAL)

    def test_corrupt_provenance_reads_as_unknown(self):
        prov = truth.deserialize_provenance("not-json{{{")
        self.assertEqual(prov["status"], truth.UNKNOWN)
        self.assertEqual(prov.get("reason"), "corrupt provenance")

    def test_provenance_fields_are_canonical(self):
        self.assertIn("status", truth.PROVENANCE_FIELDS)
        self.assertIn("model_version", truth.PROVENANCE_FIELDS)
        self.assertIn("evaluation_method", truth.PROVENANCE_FIELDS)
        self.assertIn("execution_mode", truth.PROVENANCE_FIELDS)


class TestProvenancePersistence(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = {}
        for attr in ("DB_FILE", "TICK_CSV", "SIGNAL_CSV", "JOURNAL_CSV"):
            self._old[attr] = getattr(history_logger, attr)
        history_logger.DB_FILE = os.path.join(self._tmp.name, "audit.db")
        history_logger.TICK_CSV = os.path.join(self._tmp.name, "ticks.csv")
        history_logger.SIGNAL_CSV = os.path.join(self._tmp.name, "signals.csv")
        history_logger.JOURNAL_CSV = os.path.join(self._tmp.name, "journal.csv")
        history_logger._conn = None

    def tearDown(self):
        history_logger._conn = None
        for attr, val in self._old.items():
            setattr(history_logger, attr, val)
        self._tmp.cleanup()

    def test_migration_adds_provenance_columns(self):
        conn = history_logger._init_sqlite_db()
        for table in ("tick_history", "signal_history", "paper_trade_journal"):
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            self.assertIn("provenance_json", cols, f"{table} missing provenance_json")

    def test_legacy_rows_stay_legacy(self):
        history_logger._init_sqlite_db()
        with history_logger._conn_lock:
            cur = history_logger._conn.cursor()
            cur.execute(
                "INSERT INTO tick_history (timestamp, spot_price, vix, pcr, max_pain) "
                "VALUES ('2020-01-01 00:00:00 IST', 10000.0, NULL, NULL, NULL)")
            history_logger._conn.commit()
            rid = cur.lastrowid
        prov = history_logger.get_record_provenance("tick_history", rid)
        self.assertEqual(prov["status"], truth.LEGACY)
        self.assertNotEqual(prov["status"], truth.REAL)

    def test_new_tick_receives_provenance(self):
        history_logger.log_market_tick(
            24400.0, vix=13.5, pcr=0.95, max_pain=24450,
            provenance={"status": truth.REAL, "source": "yahoo:^NSEI",
                        "evaluation_method": "live_fetch"})
        with history_logger._conn_lock:
            row = history_logger._conn.execute(
                "SELECT provenance_json FROM tick_history ORDER BY id DESC LIMIT 1").fetchone()
        prov = truth.deserialize_provenance(row[0])
        self.assertEqual(prov["status"], truth.REAL)
        self.assertEqual(prov["source"], "yahoo:^NSEI")
        self.assertEqual(prov["evaluation_method"], "live_fetch")

    def test_no_provenance_becomes_unknown_not_real(self):
        history_logger.log_market_tick(24400.0)
        with history_logger._conn_lock:
            row = history_logger._conn.execute(
                "SELECT provenance_json FROM tick_history ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(truth.deserialize_provenance(row[0])["status"], truth.UNKNOWN)

    def test_provenance_survives_read_write(self):
        history_logger.log_market_tick(
            24400.0, provenance={"status": truth.FALLBACK, "source": "research.db:spot",
                                 "fallback_used": True, "fallback_reason": truth.MISSING,
                                 "data_timestamp": "2026-08-12T15:30:00Z"})
        with history_logger._conn_lock:
            rid = history_logger._conn.execute(
                "SELECT id FROM tick_history ORDER BY id DESC LIMIT 1").fetchone()[0]
        prov = history_logger.get_record_provenance("tick_history", rid)
        self.assertEqual(prov["status"], truth.FALLBACK)
        self.assertIs(prov["fallback_used"], True)
        self.assertEqual(prov["fallback_reason"], truth.MISSING)
        self.assertEqual(prov["data_timestamp"], "2026-08-12T15:30:00Z")

    def test_corrupt_stored_provenance_is_unknown(self):
        history_logger._init_sqlite_db()
        with history_logger._conn_lock:
            cur = history_logger._conn.cursor()
            cur.execute(
                "INSERT INTO tick_history (timestamp, spot_price, provenance_json) "
                "VALUES ('2026-08-13 00:00:00 IST', 24400.0, 'not-json')")
            history_logger._conn.commit()
            rid = cur.lastrowid
        self.assertEqual(history_logger.get_record_provenance("tick_history", rid)["status"],
                         truth.UNKNOWN)

    def test_csv_mirror_contains_provenance(self):
        history_logger.log_market_tick(
            24400.0, provenance={"status": truth.REAL, "source": "yahoo:^NSEI"})
        with open(history_logger.TICK_CSV) as f:
            lines = f.read().strip().splitlines()
        self.assertEqual(lines[0], "timestamp,spot_price,vix,pcr,max_pain,provenance_json")
        self.assertIn("REAL", lines[1])
        self.assertIn("yahoo:^NSEI", lines[1])

    def test_signal_log_receives_provenance(self):
        history_logger.log_generated_signal(
            {"signal_action": "BUY_CE", "signal_grade": "A+", "nifty_spot": 24450.0,
             "precise_trade_levels": {"recommended_call_strike": 24500}},
            provenance={"status": truth.REAL, "source": "precision_signals",
                        "evaluation_method": "6_layer_confluence",
                        "signal_version": "abc123"})
        with history_logger._conn_lock:
            row = history_logger._conn.execute(
                "SELECT provenance_json, action FROM signal_history ORDER BY id DESC LIMIT 1").fetchone()
        prov = truth.deserialize_provenance(row[0])
        self.assertEqual(prov["status"], truth.REAL)
        self.assertEqual(prov["signal_version"], "abc123")
        self.assertEqual(row[1], "BUY_CE")

    def test_summary_reports_provenance_coverage(self):
        history_logger.log_market_tick(24400.0, provenance={"status": truth.REAL})
        history_logger.log_market_tick(24401.0)  # UNKNOWN but tagged
        with history_logger._conn_lock:
            history_logger._conn.execute(
                "INSERT INTO tick_history (timestamp, spot_price) VALUES ('2020-01-01 00:00:00 IST', 9000.0)")
            history_logger._conn.commit()
        summ = history_logger.get_historical_audit_summary()
        cov = summ["provenance_coverage"]["tick_history"]
        self.assertEqual(cov["records"], 3)
        self.assertEqual(cov["with_provenance"], 2)
        self.assertEqual(cov["legacy"], 1)

    def test_migration_is_idempotent(self):
        conn = history_logger._init_sqlite_db()
        before = [r[1] for r in conn.execute("PRAGMA table_info(tick_history)").fetchall()]
        history_logger._ensure_provenance_columns(conn)
        after = [r[1] for r in conn.execute("PRAGMA table_info(tick_history)").fetchall()]
        self.assertEqual(before, after)
        self.assertEqual(before.count("provenance_json"), 1)


# --------------------------------------------------------------------------
# P-06: ML freshness wiring
# --------------------------------------------------------------------------
class TestMlFreshness(unittest.TestCase):
    def setUp(self):
        import ml_engine
        self.ml_engine = ml_engine
        self._tmp = tempfile.TemporaryDirectory()
        self._old_cache = ml_engine.FEATURE_CACHE
        self._tmp_cache = os.path.join(self._tmp.name, "ml_features.csv")
        ml_engine.FEATURE_CACHE = self._tmp_cache

    def tearDown(self):
        self.ml_engine.FEATURE_CACHE = self._old_cache
        self._tmp.cleanup()

    def _write_fresh_cache(self, rows=250):
        import pandas as pd
        dates = pd.date_range("2025-01-01", periods=rows)
        df = pd.DataFrame({"date": dates, "close": [24400.0] * rows,
                           "ret_1": [0.0] * rows, "rsi14": [50.0] * rows,
                           "target_up": [1] * rows})
        df.to_csv(self._tmp_cache, index=False)

    def test_fresh_cache_read_without_rebuild(self):
        self._write_fresh_cache()
        df, meta = self.ml_engine.build_features()
        self.assertIs(meta["rebuilt"], False)
        self.assertEqual(meta["status"], truth.REAL)
        self.assertIsNotNone(df)

    def test_stale_cache_triggers_rebuild(self):
        self._write_fresh_cache()
        old = dt.datetime.now().timestamp() - 30 * 3600
        os.utime(self._tmp_cache, (old, old))
        df, meta = self.ml_engine.build_features()
        self.assertIs(meta["rebuilt"], True)
        self.assertEqual(meta["status"], truth.REAL)
        self.assertGreaterEqual(len(df), 100)
        mtime = os.path.getmtime(self._tmp_cache)
        self.assertGreater(mtime, dt.datetime.now().timestamp() - 60)

    def test_missing_cache_triggers_rebuild(self):
        df, meta = self.ml_engine.build_features()
        self.assertIs(meta["rebuilt"], True)
        self.assertIsNotNone(df)
        self.assertTrue(os.path.exists(self._tmp_cache))

    def test_rebuild_failure_returns_none_and_leaves_missing(self):
        orig = self.ml_engine._build_features_from_source
        self.ml_engine._build_features_from_source = lambda: (_ for _ in ()).throw(
            RuntimeError("source data unavailable"))
        try:
            df, meta = self.ml_engine.build_features()
        finally:
            self.ml_engine._build_features_from_source = orig
        self.assertIsNone(df)
        self.assertEqual(meta["status"], truth.MISSING)
        self.assertIn("source data unavailable", meta["error"])
        self.assertFalse(os.path.exists(self._tmp_cache))

    def test_invalid_cache_discarded_and_rebuilt(self):
        self._write_fresh_cache()
        future = dt.datetime.now().timestamp() + 24 * 3600
        os.utime(self._tmp_cache, (future, future))
        df, meta = self.ml_engine.build_features()
        self.assertIs(meta["discarded_corrupt"], True)
        self.assertIs(meta["rebuilt"], True)
        self.assertIsNotNone(df)

    def test_stale_source_marks_output_stale(self):
        orig = self.ml_engine._source_freshness
        self.ml_engine._source_freshness = lambda: {"nifty_history": truth.STALE,
                                                    "fii_dii_history": truth.REAL}
        try:
            df, meta = self.ml_engine.build_features(force=True)
        finally:
            self.ml_engine._source_freshness = orig
        self.assertIsNotNone(df)
        self.assertEqual(meta["status"], truth.STALE)  # rebuilt but from stale source

    def test_direction_forecast_emits_provenance(self):
        if not self.ml_engine.HAS_SKLEARN:
            self.skipTest("sklearn missing")
        res, err = self.ml_engine.direction_forecast()
        if err:
            self.fail(f"direction_forecast failed: {err}")
        self.assertEqual(res["status"], truth.REAL)
        self.assertIn("data_freshness", res)
        self.assertIn("feature_version", res)
        self.assertIn("evaluation_method", res)
        self.assertEqual(res["evaluation_method"], "walk_forward")

    def test_meta_blender_emits_freshness(self):
        if not self.ml_engine.HAS_SKLEARN:
            self.skipTest("sklearn missing")
        res, err = self.ml_engine.meta_blender()
        if err:
            self.fail(f"meta_blender failed: {err}")
        self.assertIn("status", res)
        self.assertIn("data_freshness", res)
        self.assertIn(truth.REAL, (res["status"], truth.STALE))


# --------------------------------------------------------------------------
# P-15: Cache recovery
# --------------------------------------------------------------------------
class TestCacheRecovery(unittest.TestCase):
    def setUp(self):
        import rebuild_cache
        self.rc = rebuild_cache
        self._tmp = tempfile.TemporaryDirectory()
        self._old = (rebuild_cache.ML_FEATURES, rebuild_cache.TF_SCAN,
                     self.rc._yahoo_probe)

    def tearDown(self):
        self.rc.ML_FEATURES, self.rc.TF_SCAN, self.rc._yahoo_probe = self._old
        self._tmp.cleanup()

    def _stale_file(self, name="cache.csv", text="name,params\nx,{}\n"):
        p = os.path.join(self._tmp.name, name)
        with open(p, "w") as f:
            f.write(text)
        old = dt.datetime.now().timestamp() - 30 * 3600
        os.utime(p, (old, old))
        return p

    def test_needs_rebuild_classification(self):
        fresh = os.path.join(self._tmp.name, "fresh.csv")
        with open(fresh, "w") as f:
            f.write("a\n1\n")
        self.assertFalse(self.rc.needs_rebuild(fresh, 20))
        stale = self._stale_file()
        self.assertTrue(self.rc.needs_rebuild(stale, 20))
        self.assertTrue(self.rc.needs_rebuild(os.path.join(self._tmp.name, "missing.csv"), 20))
        future = os.path.join(self._tmp.name, "future.csv")
        with open(future, "w") as f:
            f.write("a\n1\n")
        os.utime(future, (dt.datetime.now().timestamp() + 3600,) * 2)
        self.assertTrue(self.rc.needs_rebuild(future, 20))

    def test_validate_csv(self):
        good = os.path.join(self._tmp.name, "good.csv")
        with open(good, "w") as f:
            f.write("name,params\nrsi,{}\n")
        ok, note = self.rc.validate_csv(good, {"name", "params"})
        self.assertTrue(ok)
        self.assertIn("1 rows", note)
        bad = os.path.join(self._tmp.name, "bad.csv")
        with open(bad, "w") as f:
            f.write("this is not a csv {{{{")
        ok, note = self.rc.validate_csv(bad, {"name"})
        self.assertFalse(ok)

    def test_rebuild_ml_features_noop_when_fresh(self):
        import ml_engine
        self.rc.ML_FEATURES = self._tmp_cache = os.path.join(self._tmp.name, "ml.csv")
        ml_engine.FEATURE_CACHE = self._tmp_cache
        try:
            df, meta = ml_engine.build_features(force=True)  # create real fresh cache
            self.rc.ML_FEATURES = self._tmp_cache
            r = self.rc.rebuild_ml_features(force=False)
            self.assertEqual(r["status"], truth.REAL)
            self.assertIs(r["rebuilt"], False)
            self.assertEqual(r["note"], "already fresh")
        finally:
            ml_engine.FEATURE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   os.pardir, "data", "ml_features.csv")

    def test_rebuild_ml_features_repairs_stale(self):
        import ml_engine
        self.rc.ML_FEATURES = self._tmp_cache = os.path.join(self._tmp.name, "ml.csv")
        ml_engine.FEATURE_CACHE = self._tmp_cache
        old = dt.datetime.now().timestamp() - 30 * 3600
        with open(self._tmp_cache, "w") as f:
            f.write("date,close,target_up\n2020-01-01,10000,1\n")
        os.utime(self._tmp_cache, (old, old))
        try:
            r = self.rc.rebuild_ml_features(force=False)
            self.assertIs(r["rebuilt"], True)
            self.assertEqual(r["status"], truth.REAL)
            self.assertGreater(r["rows"], 1)
        finally:
            ml_engine.FEATURE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   os.pardir, "data", "ml_features.csv")

    def test_rebuild_tf_scan_success(self):
        import pandas as pd
        import multitf
        self.rc.TF_SCAN = os.path.join(self._tmp.name, "tf_scan.csv")
        self.rc._yahoo_probe = lambda attempts=2: (True, "mock net")
        orig_scan = multitf.tf_grid_scan
        multitf.tf_grid_scan = lambda *a, **k: pd.DataFrame(
            {"name": ["rsi_meanrev"], "params": ["{}"], "hold": [1]})
        try:
            r = self.rc.rebuild_tf_scan(days=5, attempts=1)
        finally:
            multitf.tf_grid_scan = orig_scan
        self.assertIs(r["rebuilt"], True)
        self.assertEqual(r["status"], truth.REAL)
        self.assertEqual(r["rows"], 1)

    def test_rebuild_tf_scan_network_failure_preserves_stale(self):
        self.rc.TF_SCAN = self._stale_file("tf_scan.csv", "name,params\nx,{}\n")
        before = open(self.rc.TF_SCAN, "rb").read()
        self.rc._yahoo_probe = lambda attempts=2: (False, "net down")
        r = self.rc.rebuild_tf_scan(attempts=1)
        self.assertIs(r["rebuilt"], False)
        self.assertEqual(r["status"], truth.STALE)
        self.assertIn("network unavailable", r["error"])
        after = open(self.rc.TF_SCAN, "rb").read()
        self.assertEqual(before, after, "failed rebuild must not touch the file")

    def test_no_fabricated_data_on_failure(self):
        self.rc.ML_FEATURES = os.path.join(self._tmp.name, "missing_ml.csv")
        import ml_engine
        ml_engine.FEATURE_CACHE = self.rc.ML_FEATURES
        orig = ml_engine._build_features_from_source
        ml_engine._build_features_from_source = lambda: (_ for _ in ()).throw(
            RuntimeError("no data"))
        try:
            r = self.rc.rebuild_ml_features()
        finally:
            ml_engine._build_features_from_source = orig
            ml_engine.FEATURE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   os.pardir, "data", "ml_features.csv")
        self.assertIs(r["rebuilt"], False)
        self.assertEqual(r["status"], truth.MISSING)
        self.assertFalse(os.path.exists(self.rc.ML_FEATURES))


if __name__ == "__main__":
    unittest.main()
