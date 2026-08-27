"""Phase 6 evaluation-engine tests: cohort selection, metrics, confidence
calibration, failure taxonomy, leakage and reproducibility.

unittest style (repo convention). All DB writes happen in temp files - the
production ground_truth.db is never opened writable by these tests.
"""
import os
import sys
import json
import tempfile
import unittest
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import truth
import evaluation_engine as ee
import ground_truth as gt


# ---------------------------------------------------------------------------
# cohort selection
# ---------------------------------------------------------------------------
class TestCohorts(unittest.TestCase):
    def test_real_fresh_label(self):
        self.assertEqual(ee.cohort_label(truth.REAL, 10), "REAL_FRESH")

    def test_real_stale_label(self):
        # 25h old vs 20h daily budget
        self.assertEqual(ee.cohort_label(truth.REAL, 25 * 3600), "REAL_STALE")

    def test_legacy_and_simulated_labels(self):
        self.assertEqual(ee.cohort_label(truth.LEGACY, None), "LEGACY")
        self.assertEqual(ee.cohort_label(truth.SIMULATED, None), "SIMULATED")
        self.assertEqual(ee.cohort_label(None, None), truth.UNKNOWN)

    def test_split_and_eligible(self):
        rows = [
            {"provenance_status": truth.REAL, "freshness_seconds": 10},
            {"provenance_status": truth.REAL, "freshness_seconds": 25 * 3600},
            {"provenance_status": truth.LEGACY, "freshness_seconds": None},
            {"provenance_status": truth.SIMULATED, "freshness_seconds": None},
        ]
        cohorts = ee.split_cohorts(rows)
        self.assertEqual(cohorts["REAL_FRESH"], [rows[0]])
        self.assertEqual(cohorts["REAL_STALE"], [rows[1]])
        self.assertEqual(cohorts["LEGACY"], [rows[2]])
        self.assertEqual(cohorts["SIMULATED"], [rows[3]])
        self.assertEqual(ee.select_eligible(cohorts), [rows[0]])

    def test_sufficiency(self):
        self.assertEqual(ee.sufficiency(10, ee.MIN_OUTCOME_SAMPLE), "INSUFFICIENT_SAMPLE")
        self.assertEqual(ee.sufficiency(40, ee.MIN_SIGNAL_SAMPLE), "ADEQUATE")


# ---------------------------------------------------------------------------
# signal / prediction / outcome metrics
# ---------------------------------------------------------------------------
def _signal_row(direction="UP", correct=None, pnl=None, cls=None, **kw):
    r = {"signal_id": kw.get("signal_id", 1), "signal_type": kw.get("signal_type", "precision_signal"),
         "market_state": kw.get("market_state", "TREND_HV"), "direction": direction,
         "provenance_status": truth.REAL, "freshness_seconds": 10,
         "prediction_correct": correct, "net_pnl": pnl, "outcome_class": cls}
    r.update(kw)
    return r


class TestSignalMetrics(unittest.TestCase):
    def test_empty(self):
        m = ee.signal_metrics([])
        self.assertEqual(m["sample_size"], 0)
        self.assertEqual(m["data_sufficiency"], "INSUFFICIENT_SAMPLE")
        self.assertIsNone(m["hit_rate"])

    def test_small_sample_insufficient(self):
        m = ee.signal_metrics([_signal_row()] * 5)
        self.assertEqual(m["data_sufficiency"], "INSUFFICIENT_SAMPLE")

    def test_hit_rate_non_directional_not_counted(self):
        rows = [_signal_row(direction="UP", correct="CORRECT", pnl=100) for _ in range(20)]
        rows += [_signal_row(direction=None, correct=None, pnl=None) for _ in range(20)]
        m = ee.signal_metrics(rows)
        self.assertEqual(m["sample_size"], 40)
        self.assertEqual(m["directional_claims"], 20)
        self.assertEqual(m["hit_rate"], 1.0)
        self.assertEqual(m["non_directional"], 20)

    def test_false_positive_and_averages(self):
        rows = [_signal_row(direction="UP", correct="CORRECT", pnl=100) for _ in range(10)]
        rows += [_signal_row(direction="UP", correct="INCORRECT", pnl=-50, cls="LOSS") for _ in range(10)]
        m = ee.signal_metrics(rows)
        self.assertEqual(m["correct"], 10)
        self.assertEqual(m["incorrect"], 10)
        self.assertEqual(m["false_positive_rate"], 0.5)
        self.assertEqual(m["average_net_pnl"], 25.0)
        self.assertEqual(m["median_net_pnl"], 25.0)


class TestPredictionMetrics(unittest.TestCase):
    def test_aggregation_by_model_and_band(self):
        rows = []
        for i in range(20):
            rows.append({"prediction_correct": "CORRECT", "model_type": "rule",
                         "model_version": "v1", "signal_type": "precision_signal",
                         "market_state": "TREND_HV", "confidence_band": "0.80-0.90",
                         "net_pnl": 50, "evaluation_status": "DONE"})
        m = ee.prediction_metrics(rows)
        self.assertEqual(m["correct"], 20)
        self.assertEqual(m["accuracy"], 1.0)
        self.assertEqual(m["by_model"]["rule"]["success_rate"], 1.0)
        self.assertEqual(m["by_confidence_band"]["0.80-0.90"]["sample_size"], 20)


class TestOutcomeMetrics(unittest.TestCase):
    def test_win_rate_mfe_mae(self):
        rows = []
        for i in range(20):
            rows.append({"outcome_class": "WIN", "net_pnl": 100, "return_pct": 5.0,
                         "duration_s": 3600, "mfe": 120, "mae": 10, "mfe_source": "FULL"})
        for i in range(10):
            rows.append({"outcome_class": "LOSS", "net_pnl": -50, "return_pct": -2.5,
                         "duration_s": 1800, "mfe": 60, "mae": 70, "mfe_source": "FULL"})
        m = ee.outcome_metrics(rows)
        self.assertEqual(m["sample_size"], 30)
        self.assertEqual(m["data_sufficiency"], "ADEQUATE")
        self.assertEqual(m["win_rate"], round(20 / 30, 4))
        self.assertEqual(m["average_net_pnl"], 50.0)
        self.assertEqual(m["mfe"]["average"], 100.0)
        self.assertEqual(m["mae"]["average"], 30.0)


# ---------------------------------------------------------------------------
# confidence calibration
# ---------------------------------------------------------------------------
def _pred_row(correct, conf, pnl=None):
    return {"prediction_correct": correct, "confidence": conf,
            "confidence_band": ee.confidence_band(conf), "net_pnl": pnl}


class TestConfidenceBands(unittest.TestCase):
    def test_band_edges(self):
        self.assertEqual(ee.confidence_band(0.55), "0.50-0.60")
        self.assertEqual(ee.confidence_band(0.85), "0.80-0.90")
        self.assertEqual(ee.confidence_band(0.99), "0.90-1.00")
        self.assertIsNone(ee.confidence_band(None))

    def test_insufficient_data(self):
        cal = ee.confidence_calibration([_pred_row("CORRECT", 0.85) for _ in range(3)])
        self.assertEqual(cal["calibration_status"], "INSUFFICIENT_DATA")

    def test_consistent_success_is_calibrated(self):
        rows = []
        for band_conf in (0.55, 0.75, 0.95):
            for _ in range(20):
                correct = "CORRECT"
                rows.append(_pred_row(correct, band_conf))
        cal = ee.confidence_calibration(rows)
        self.assertEqual(cal["calibration_status"], "CALIBRATED")
        self.assertEqual(cal["bands"]["0.50-0.60"]["sample_size"], 20)
        self.assertEqual(cal["bands"]["0.50-0.60"]["observed_success_rate"], 1.0)

    def test_divergent_success_is_uncalibrated(self):
        rows = []
        for _ in range(20):
            rows.append(_pred_row("CORRECT", 0.55))
        for _ in range(20):
            rows.append(_pred_row("INCORRECT", 0.95))
        for _ in range(20):
            rows.append(_pred_row("CORRECT", 0.75))
        cal = ee.confidence_calibration(rows)
        self.assertEqual(cal["calibration_status"], "UNCALIBRATED")


# ---------------------------------------------------------------------------
# failure taxonomy
# ---------------------------------------------------------------------------
class TestFailureTaxonomy(unittest.TestCase):
    def test_data_error_evidence(self):
        row = {"obs_valid": 0, "obs_price": None, "signal_id": 7,
               "snapshot_id": 1, "decision_type": None}
        cat, ev = ee.classify_failure(row)
        self.assertEqual(cat, "DATA_ERROR")
        self.assertIn("7", ev)

    def test_feature_error_missing_snapshot(self):
        row = {"obs_valid": 1, "obs_price": 100, "signal_id": 7,
               "snapshot_id": None, "decision_type": None}
        cat, _ = ee.classify_failure(row)
        self.assertEqual(cat, "FEATURE_ERROR")

    def test_risk_error_rejection(self):
        row = {"obs_valid": 1, "obs_price": 100, "signal_id": 7,
               "snapshot_id": 1, "decision_type": "REJECT",
               "capital_guard_state": "BLOCKED", "dec_reason": "kill switch"}
        cat, ev = ee.classify_failure(row)
        self.assertEqual(cat, "RISK_ERROR")
        self.assertIn("kill switch", ev)

    def test_model_error_wrong_prediction(self):
        row = {"obs_valid": 1, "obs_price": 100, "signal_id": 7, "snapshot_id": 1,
               "decision_type": "ENTER", "pred_id": 9,
               "prediction_correct": "INCORRECT", "actual_move": -120}
        cat, ev = ee.classify_failure(row)
        self.assertEqual(cat, "MODEL_ERROR")

    def test_timing_error(self):
        row = {"obs_valid": 1, "obs_price": 100, "signal_id": 7, "snapshot_id": 1,
               "signal_ts": "2026-08-13 10:00:00 IST",
               "decision_ts": "2026-08-13 09:00:00 IST"}
        cat, _ = ee.classify_failure(row)
        self.assertEqual(cat, "TIMING_ERROR")

    def test_healthy_no_trade_is_not_a_failure(self):
        row = {"obs_valid": 1, "obs_price": 100, "signal_id": 7, "snapshot_id": 1,
               "signal_ts": "2026-08-13 10:00:00 IST", "direction": None,
               "decision_type": "SKIP", "market_state": "TREND_HV"}
        cat, _ = ee.classify_failure(row)
        self.assertIsNone(cat)

    def test_aggregation_most_common(self):
        rows = [{"obs_valid": 0, "obs_price": None, "signal_id": i, "snapshot_id": 1}
                for i in range(10)]
        rows += [{"obs_valid": 1, "obs_price": 100, "signal_id": i, "snapshot_id": 1,
                  "decision_type": "REJECT", "capital_guard_state": "BLOCKED"}
                 for i in range(4)]
        s = ee.failure_summary(rows)
        self.assertEqual(s["classified_failures"], 14)
        self.assertEqual(s["most_common"], "DATA_ERROR")


# ---------------------------------------------------------------------------
# leakage
# ---------------------------------------------------------------------------
class TestLeakage(unittest.TestCase):
    def test_clean_chain_no_issues(self):
        rows = [{
            "signal_id": 1, "signal_ts": "2026-08-12 15:30:00 IST",
            "feature_ts": "2026-08-12 15:30:00 IST",
            "decision_ts": "2026-08-12 15:30:05 IST",
            "obs_id": 1, "obs_price": 24100.0,
            "pred_id": 1, "base_price": 24100.0,
            "horizon_end_ts": "2026-08-13",
            "eval_ts": "2026-08-13 15:30:00 IST",
        }]
        self.assertTrue(ee.verify_leakage(rows)["clean"])

    def test_feature_after_signal_flagged(self):
        rows = [{
            "signal_id": 1, "signal_ts": "2026-08-12 15:30:00 IST",
            "feature_ts": "2026-08-12 15:31:00 IST",
            "decision_ts": "2026-08-12 15:30:05 IST",
            "obs_id": 1, "obs_price": 24100.0,
            "pred_id": 1, "base_price": 24100.0,
            "horizon_end_ts": "2026-08-13",
            "eval_ts": "2026-08-13 15:30:00 IST",
        }]
        v = ee.verify_leakage(rows)
        self.assertFalse(v["clean"])
        self.assertEqual(v["leakage_issues"], 1)

    def test_eval_before_horizon_flagged(self):
        rows = [{
            "signal_id": 1, "signal_ts": "2026-08-12 15:30:00 IST",
            "feature_ts": "2026-08-12 15:30:00 IST",
            "decision_ts": "2026-08-12 15:30:05 IST",
            "obs_id": 1, "obs_price": 24100.0,
            "pred_id": 1, "base_price": 24100.0,
            "horizon_end_ts": "2026-08-13",
            "eval_ts": "2026-08-12 20:00:00 IST",
        }]
        v = ee.verify_leakage(rows)
        self.assertFalse(v["clean"])

    def test_base_price_mismatch_flagged(self):
        rows = [{
            "signal_id": 1, "signal_ts": "2026-08-12 15:30:00 IST",
            "feature_ts": "2026-08-12 15:30:00 IST",
            "decision_ts": "2026-08-12 15:30:05 IST",
            "obs_id": 1, "obs_price": 24100.0,
            "pred_id": 1, "base_price": 23999.0,
            "horizon_end_ts": "2026-08-13",
            "eval_ts": "2026-08-13 15:30:00 IST",
        }]
        v = ee.verify_leakage(rows)
        self.assertFalse(v["clean"])


# ---------------------------------------------------------------------------
# engine integration on a temp ground truth DB (read-only facade)
# ---------------------------------------------------------------------------
def _make_env(tmp):
    nifty_csv = os.path.join(tmp, "nifty_history.csv")
    with open(nifty_csv, "w") as f:
        f.write("Date,Open,High,Low,Close,Volume\n"
                "2026-08-10,24000,24100,23900,24050,100\n"
                "2026-08-12,24100,24200,24000,24150,100\n"
                "2026-08-13,24150,24200,24050,24200,100\n"
                "2026-08-14,24100,24300,24050,24200,100\n")
    gt.NIFTY_HISTORY_CSV = nifty_csv
    gt.RESEARCH_DB = os.path.join(tmp, "research.db")
    db_path = os.path.join(tmp, "ground_truth.db")
    db = gt.GroundTruthDB(db_path)
    return db, db_path


def _record_trade(db, conf, direction="UP", guard="APPROVED", exit_price=180.0):
    """Past-dated full chain with a closed trade + evaluated prediction."""
    ts = "2026-08-12 15:30:00 IST"
    obs = db.record_observation(ts, "NIFTY", 24100.0, "test")
    sid = db.record_signal(ts, "NIFTY", direction, "precision_signal", "5/6", conf,
                           "TREND_HV", obs, "v1", None, "v1",
                           {"_action": "HIGH_CONVICTION_CALL", "_grade": "A+"},
                           provenance={"status": "REAL", "source": "test_fixture"})
    db.record_feature_snapshot(sid, ts, "v1", 600, {"nifty_spot": 24100.0})
    pid = db.record_prediction(sid, direction, 24100.0,
                               horizon="next_trading_session_close",
                               horizon_end_ts="2026-08-13",
                               confidence=conf, calibration="UNKNOWN",
                               model_type="rule", model_version="v1",
                               prediction_ts=ts)
    db.record_decision("ENTER", signal_id=sid, prediction_id=pid,
                       decision_ts="2026-08-12 15:30:05 IST",
                       capital_guard_state=guard, execution_mode="PAPER")
    eid = db.record_execution(1, "NIFTY", "BUY", 75, 140.0, 140.0,
                              "2026-08-12 15:30:06 IST", strike=24450, option_type="CE")
    pos = db.record_position(eid, "NIFTY", "BUY", 75, 140.0,
                             "2026-08-12 15:30:06 IST", status="OPEN",
                             strike=24450, option_type="CE")
    db.close_position(pos, exit_price, "2026-08-13 15:00:00 IST", "TARGET")
    db.evaluate_pending_predictions()
    return sid, pid, pos


class TestEngineIntegration(unittest.TestCase):
    def test_read_only_never_writes_production(self):
        tmp = tempfile.mkdtemp()
        db, db_path = _make_env(tmp)
        _record_trade(db, 0.85)
        engine = ee.EvaluationEngine(gt_db=db_path)
        rep = engine.evaluation_report()
        # the facade opens read-only; it must never create or write tables
        self.assertEqual(rep["counts"]["signals"], 1)
        self.assertEqual(rep["counts"]["predictions"], 1)
        self.assertEqual(rep["counts"]["outcomes"], 1)
        self.assertEqual(rep["counts"]["evaluations"], 1)
        self.assertEqual(rep["prediction_evaluation"]["correct"], 1)

    def test_cohort_and_legacy_exclusion(self):
        tmp = tempfile.mkdtemp()
        db, db_path = _make_env(tmp)
        # legacy open paper position (no signal chain)
        acct = os.path.join(tmp, "paper_account.json")
        with open(acct, "w") as f:
            json.dump({"open_positions": [{
                "position_id": "POS_LEG_1", "timestamp": "2026-08-11 10:00:00 IST",
                "symbol": "NIFTY", "side": "BUY", "option_type": "CE", "strike": 24450,
                "lots": 1, "quantity": 75, "entry_price": 140.0, "status": "OPEN"}],
                "closed_trades": []}, f)
        db.import_legacy_paper_positions(account_file=acct)
        _record_trade(db, 0.8)
        engine = ee.EvaluationEngine(gt_db=db_path)
        cohorts = engine.cohorts()
        real_fresh_ids = [r.get("signal_id") for r in cohorts["REAL_FRESH"]]
        self.assertEqual(real_fresh_ids, [db._cur().execute(
            "SELECT signal_id FROM signals ORDER BY signal_id").fetchone()[0]])
        # legacy position is not in the REAL_FRESH signal cohort
        self.assertEqual(engine.evaluation_report()["counts"]["positions"], 1)

    def test_reproducibility_identical_reports(self):
        tmp = tempfile.mkdtemp()
        db, db_path = _make_env(tmp)
        _record_trade(db, 0.85)
        engine = ee.EvaluationEngine(gt_db=db_path)
        v = ee.verify_reproducibility(engine)
        self.assertTrue(v["reproducible"])
        self.assertEqual(v["hash_a"], v["hash_b"])

    def test_reproducibility_independent_of_generated_at(self):
        """The hash must not change when the wall-clock stamp differs between
        runs - generated_at is metadata, not an input."""
        tmp = tempfile.mkdtemp()
        db, db_path = _make_env(tmp)
        _record_trade(db, 0.85)
        engine = ee.EvaluationEngine(gt_db=db_path)
        real_now = ee._now
        calls = [0]

        def ticking_now():
            base = dt.datetime.strptime(real_now(), ee._TS_FMT)
            stamp = (base + dt.timedelta(seconds=1)) if calls[0] else base
            calls[0] += 1
            return stamp.strftime(ee._TS_FMT)

        ee._now = ticking_now
        try:
            v = ee.verify_reproducibility(engine)
        finally:
            ee._now = real_now
        self.assertTrue(v["reproducible"])
        self.assertEqual(v["hash_a"], v["hash_b"])

    def test_integrity_with_production_like_data(self):
        tmp = tempfile.mkdtemp()
        db, db_path = _make_env(tmp)
        _record_trade(db, 0.7)
        _record_trade(db, 0.6, exit_price=90.0)
        engine = ee.EvaluationEngine(gt_db=db_path)
        rep = engine.evaluation_report()
        self.assertEqual(rep["counts"]["outcomes"], 2)
        self.assertIn("WIN", rep["outcome_evaluation"]["by_class"])
        self.assertTrue(rep["leakage_verification"]["clean"])


if __name__ == "__main__":
    unittest.main()
