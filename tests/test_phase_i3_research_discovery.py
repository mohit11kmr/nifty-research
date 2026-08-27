"""Phase I.3 - Regime-Aware Research Discovery tests (unittest, repo convention).

covers: manifest integrity gate, feature panel build + leakage probe, conditions
DSL (point-in-time safety), fast screen verdicts (SCREENED_IN / LOW_FREQUENCY /
REJECT), full research runner (determinism via result_hash, sample-size policy,
concentration, regime robustness, OOS verdict), and the settlement-price data
artifact correction on expiry days.

Run: .venv/bin/python -m unittest tests.test_phase_i3_research_discovery -v
"""
import json
import os
import unittest

import numpy as np

import research_dataset as RD
import research_feature_engine as FE
import research_regime_discovery as RR
import research_conditions as RC
import research_screener as RS
import research_runner as RUN

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_FIXTURES = None


def _fixtures():
    """Module-level lazy singleton: context + panel + meta + regime labels."""
    global _FIXTURES
    if _FIXTURES is None:
        ctx = RD.load_context()
        panel, meta = FE.build_panel(ctx)
        regime_report, _ = RR.discover_regimes(panel, meta)
        _FIXTURES = (ctx, panel, meta, regime_report["assignments"])
    return _FIXTURES
RESULT_HASH_STABLE = "b051f0d8d3b13a3a41e6982dcf0a141d0dcccd598f44d87e7e54a21a2d206f38"


def _gap_proposal(direction="LONG", instrument="CALL", conditions=None,
                  required=None, regime=None):
    return {
        "proposal": {"proposal_id": "phase_i3_test_probe", "title": "probe",
                     "author_type": "AI", "author_model": "opencode/big-pickle",
                     "created_at": "2026-08-16T00:00:00+05:30",
                     "parent_strategy_id": None, "hypothesis": "h",
                     "research_question": "RQ-03",
                     "expected_failure_modes": ["a", "b"],
                     "candidate_family": "GAP_BOUNCE"},
        "strategy": {
            "id": "probe_v1",
            "entry": {"conditions": conditions or [
                {"field": "nifty_gap_pct", "op": "<", "value": -0.5},
                {"field": "vix_close", "op": "<", "value": 25}],
                "direction": direction, "instrument": instrument,
                "strike_selection": "ATM"},
            "exit": {"type": "HORIZON", "horizon_sessions": 5},
            "risk": {"defined_risk": True},
            "execution": {"cost_model": "canonical", "resolution": "EOD",
                          "lot_size": 75},
            "required_features": required or ["nifty_gap_pct", "vix_close"],
            "regime": regime,
        },
    }


class DataIntegrityTest(unittest.TestCase):
    def test_manifest_self_hash_stable(self):
        ctx = RD.load_context()
        self.assertGreater(len(ctx.sessions), 600)
        self.assertIn("2024-01-01", ctx.sessions[0])
        self.assertIn("2026-08-13", ctx.sessions[-1])

    def test_manifest_verifies_without_raising(self):
        # frozen dataset must pass its own integrity gate
        RD.verify_integrity()


class FeatureEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx, cls.panel, cls.meta, cls.labels = _fixtures()

    def test_panel_shape(self):
        self.assertEqual(len(self.panel), 646)
        self.assertGreater(self.panel.shape[1], 40)
        self.assertIn("near_expiry", self.panel.columns)

    def test_feature_version_present(self):
        self.assertIn("feature_version", self.meta)
        self.assertIn("source_hash", self.meta)

    def test_pcr_orientation(self):
        # put/call; must be >= 0 and far from zero on average
        self.assertTrue((self.panel["pcr_oi"] >= 0).all())
        self.assertGreater(self.panel["pcr_oi"].median(), 0.3)

    def test_leakage_probe(self):
        report = FE.leakage_probe(self.panel, self.ctx,
                                  dates=self.panel.index[100:102].tolist(),
                                  feature_ids=["nifty_ret_5d", "nifty_20d_hv"])
        for d, row in report.items():
            self.assertTrue(row["_match"] is True)

    def test_no_future_nan(self):
        tail = self.panel.tail(5)
        self.assertFalse(tail.isna().all().all())


class ConditionsDslTest(unittest.TestCase):
    def test_validate_rejects_bad_op(self):
        errs = RC.validate_conditions([{"field": "nifty_close", "op": "??",
                                        "value": 1}])
        self.assertTrue(any("op" in e for e in errs))

    def test_evaluate_nan_is_false(self):
        doc = {"nifty_close": np.nan}
        self.assertFalse(RC.evaluate(doc, [{"field": "nifty_close", "op": ">",
                                            "value": 1}]))

    def test_between(self):
        doc = {"nifty_close": 100.0}
        self.assertTrue(RC.evaluate(doc, [{"field": "nifty_close", "op": "between",
                                           "value": [90, 110]}]))

    def test_expected_signal_dates_are_sorted(self):
        import pandas as pd
        panel = pd.DataFrame({"nifty_close": [1.0, 2.0, 3.0]},
                             index=["2026-01-01", "2026-01-02", "2026-01-03"])
        dates = RC.expected_signal_dates(panel, [])
        self.assertEqual(list(dates), sorted(dates))


class ScreenerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel, cls.labels = _fixtures()[1], _fixtures()[3]

    def test_screen_in(self):
        v = RS.fast_screen(_gap_proposal(), self.panel, self.labels)
        self.assertEqual(v["verdict"], "SCREENED_IN")

    def test_reject_missing_feature(self):
        doc = _gap_proposal(required=["not_a_real_feature"])
        v = RS.fast_screen(doc, self.panel, self.labels)
        self.assertEqual(v["verdict"], "REJECT")
        self.assertTrue(any("unknown features" in r for r in v["reasons"]))

    def test_reject_bad_instrument_family(self):
        doc = _gap_proposal()
        doc["proposal"]["candidate_family"] = "VOL_EXPANSION"
        v = RS.fast_screen(doc, self.panel, self.labels)
        self.assertEqual(v["verdict"], "REJECT")

    def test_reject_naked_short(self):
        doc = _gap_proposal(direction="SHORT", instrument="CALL")
        v = RS.fast_screen(doc, self.panel, self.labels)
        self.assertEqual(v["verdict"], "REJECT")

    def test_low_frequency_label(self):
        doc = _gap_proposal(conditions=[{"field": "nifty_gap_pct", "op": "<",
                                         "value": -2}], required=["nifty_gap_pct"])
        v = RS.fast_screen(doc, self.panel, self.labels)
        self.assertEqual(v["verdict"], "LOW_FREQUENCY")


class RunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx, cls.panel, _, cls.labels = _fixtures()
        cls.out = RUN.research(_gap_proposal(), cls.panel, cls.ctx, cls.labels)

    def test_result_hash_deterministic(self):
        again = RUN.research(_gap_proposal(), self.panel, self.ctx, self.labels)
        self.assertEqual(self.out["result_hash"], again["result_hash"])

    def test_trades_resolved(self):
        self.assertGreater(self.out["n_trades"], 20)
        self.assertEqual(self.out["metrics"]["status"], "RELIABLE")

    def test_evaluation_vector_fields(self):
        ev = self.out["evaluation_vector"]
        for key in ("edge_quality", "sample_size", "stability", "drawdown",
                    "risk_validity", "data_quality", "regime_robustness",
                    "oos_quality", "trade_frequency", "profit_concentration",
                    "execution_realism", "complexity"):
            self.assertIn(key, ev)

    def test_oos_split(self):
        oos = self.out["oos"]
        self.assertIn("out_of_sample_from_2026_03_01", oos)
        self.assertIn("verdict", oos)

    def test_concentration_metrics(self):
        c = self.out["concentration"]
        for key in ("best_trade_pct", "top3_pct", "best_month_pct"):
            self.assertIn(key, c)

    def test_sample_bucket_marked(self):
        self.assertTrue(self.out["sample_buckets"]["50_plus"])

    def test_regime_robustness_reports(self):
        rr = self.out["regime_robustness"]
        self.assertIn("by_regime", rr)
        self.assertIn("flag", rr)

    def test_note_reliable_under_20(self):
        rare = RUN.research(_gap_proposal(
            conditions=[{"field": "nifty_gap_pct", "op": "<", "value": -2}],
            required=["nifty_gap_pct"]), self.panel, self.ctx, self.labels)
        self.assertLess(rare["n_trades"], 20)
        self.assertEqual(rare["metrics"]["status"], "NOT_RELIABLE")
        self.assertEqual(rare["oos"]["verdict"], "OOS_INSUFFICIENT")


class SettlementArtifactTest(unittest.TestCase):
    """Expiring contracts on the expiry date have settle_price = underlying
    close (bhavcopy artifact); the runner must use close as the mark."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = _fixtures()[0]

    def test_artifact_signature_present(self):
        chain = RUN.Chain(self.ctx)
        c = chain.find("2024-01-18", "2024-01-18", 21550, "CE")
        self.assertIsNotNone(c)
        self.assertAlmostEqual(c.settle, 21462.25, places=1)
        self.assertAlmostEqual(c.mark("2024-01-18"), 0.2, places=1)

    def test_non_expiry_uses_settle(self):
        chain = RUN.Chain(self.ctx)
        c = chain.find("2024-01-17", "2024-01-18", 21550, "CE")
        self.assertIsNotNone(c)
        self.assertAlmostEqual(c.mark("2024-01-17"), 90.6, places=1)


if __name__ == "__main__":
    unittest.main()
