"""Unit tests for the Truth & Provenance Layer (Phase 3).

Covers: fresh/stale/missing/invalid classification, explicit fallback
tagging, simulation tagging, unsupported-claim correction, provenance
preservation, and grep-guards that keep hardcoded fallbacks and false
"trained" claims from coming back.
"""
import os
import sys
import tempfile
import datetime as dt
import unittest
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import truth
from smart_strike_selector import strike_selector
from lstm_neural_engine import predict_lstm_sequence
import monte_carlo
import var_risk_manager
import market_brain
import live_ticker_service

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_module(name):
    with open(os.path.join(ROOT, name), "r", encoding="utf-8") as f:
        return f.read()


class TestTruthContract(unittest.TestCase):

    def test_fresh_data_is_real(self):
        self.assertEqual(truth.freshness_status(age_seconds=5, budget_seconds=100), truth.REAL)

    def test_stale_data_is_stale(self):
        self.assertEqual(truth.freshness_status(age_seconds=200, budget_seconds=100), truth.STALE)

    def test_missing_data_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            res = truth.file_freshness(os.path.join(d, "nope.csv"), 20)
        self.assertEqual(res["status"], truth.MISSING)

    def test_invalid_age_is_invalid(self):
        self.assertEqual(truth.freshness_status(age_seconds=-1, budget_seconds=100), truth.INVALID)
        self.assertEqual(truth.freshness_status(age_seconds=None, budget_seconds=100), truth.MISSING)
        self.assertEqual(truth.freshness_status(age_seconds=10, budget_seconds=0), truth.INVALID)

    def test_future_mtime_is_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "future.csv")
            with open(p, "w") as f:
                f.write("x")
            future = dt.datetime.now().timestamp() + 3600
            os.utime(p, (future, future))
            res = truth.file_freshness(p, 20)
        self.assertEqual(res["status"], truth.INVALID)

    def test_fresh_file_is_real(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "now.csv")
            with open(p, "w") as f:
                f.write("x")
            res = truth.file_freshness(p, 20)
        self.assertEqual(res["status"], truth.REAL)

    def test_envelope_adds_provenance_without_mutation(self):
        result = {"bias": "CALL"}
        out = truth.envelope(result, truth.FALLBACK, source="cache",
                             fallback_used=True, fallback_reason=truth.MISSING,
                             evaluation_method="last_recorded")
        self.assertNotIn("status", result)  # original untouched
        self.assertEqual(out["status"], truth.FALLBACK)
        self.assertTrue(out["fallback_used"])
        self.assertEqual(out["fallback_reason"], truth.MISSING)
        self.assertEqual(out["bias"], "CALL")
        self.assertIn("timestamp", out)

    def test_hash_version_is_stable_and_distinct(self):
        a = {"x": 1, "y": [1, 2]}
        b = {"y": [1, 2], "x": 1}
        c = {"x": 1, "y": [1, 3]}
        self.assertEqual(truth.hash_version(a), truth.hash_version(b))
        self.assertNotEqual(truth.hash_version(a), truth.hash_version(c))

    def test_freshness_report_is_valid(self):
        for entry in truth.asset_freshness_report():
            self.assertIn(entry["status"], (truth.REAL, truth.STALE, truth.MISSING, truth.INVALID))
            self.assertIn("budget_h", entry)


class _FakeYfDown:
    """yfinance stub whose Ticker raises (simulates feed failure)."""

    def Ticker(self, symbol):
        raise Exception("feed down")


class TestFallbackHonesty(unittest.TestCase):

    def test_ticker_stands_down_when_nothing_available(self):
        with mock.patch.object(live_ticker_service, "yf", _FakeYfDown()), \
             mock.patch.object(live_ticker_service, "_last_recorded_spot", return_value=None):
            t = live_ticker_service.fetch_live_quote()
        self.assertEqual(t["status"], truth.MISSING)
        self.assertIsNone(t["spot"])
        self.assertIsNone(t["vix"])
        self.assertNotEqual(t["spot"], 24403.10)
        self.assertNotEqual(t["vix"], 12.0)

    def test_ticker_explicit_fallback_keeps_reason(self):
        with mock.patch.object(live_ticker_service, "yf", _FakeYfDown()):
            t = live_ticker_service.fetch_live_quote()
        self.assertIn(t["status"], (truth.FALLBACK, truth.MISSING))
        if t["status"] == truth.FALLBACK:
            self.assertTrue(t["fallback_used"])
            self.assertEqual(t["fallback_reason"], truth.MISSING)

    def test_ticker_live_path_is_real(self):
        import pandas as pd

        class FakeTicker:
            def __init__(self, sym):
                self.sym = sym

            def history(self, **kw):
                idx = pd.date_range("2026-08-13", periods=1, freq="1min")
                close = 24360.35 if self.sym == "^NSEI" else 13.5
                return pd.DataFrame({"Close": [close]}, index=idx)

        with mock.patch.object(live_ticker_service, "yf", Ticker=FakeTicker):
            t = live_ticker_service.fetch_live_quote()
        self.assertEqual(t["status"], truth.REAL)
        self.assertEqual(t["spot"], 24360.35)

    def test_smart_strike_missing_spot_stands_down(self):
        res = strike_selector.select_best_strike(spot_price=None, option_type="CE")
        self.assertEqual(res["selector_status"], "MISSING_SPOT")
        self.assertEqual(res["status"], truth.MISSING)
        self.assertIsNone(res["best_strike"])
        self.assertNotIn("24403", str(res["selection_rationale"]))


class TestSimulationTags(unittest.TestCase):

    def test_lstm_is_simulated(self):
        out = predict_lstm_sequence()
        self.assertIn("lstm_verdict", out)
        self.assertEqual(out["status"], truth.SIMULATED)
        self.assertEqual(out["evaluation_method"], "deterministic_simulation")

    def test_monte_carlo_is_simulated_seed42(self):
        out = monte_carlo.run_monte_carlo_simulation(num_simulations=100)
        self.assertEqual(out["status"], truth.SIMULATED)
        self.assertEqual(out["random_seed"], 42)
        self.assertGreater(out["account_survival_rate_pct"], 90)
        self.assertIn("SIMULATED", out["quant_survival_verdict"])

    def test_volatility_forecaster_tags_placeholder_returns(self):
        import volatility_forecaster
        sim = volatility_forecaster.quant_forecaster.forecast_intraday_volatility(
            historical_returns=None, current_spot=24000)
        self.assertEqual(sim["data_status"], truth.SIMULATED)
        self.assertEqual(sim["evaluation_method"], "deterministic_simulation_seed42")
        real = volatility_forecaster.quant_forecaster.forecast_intraday_volatility(
            historical_returns=[0.001] * 50, current_spot=24000)
        self.assertEqual(real["data_status"], truth.ESTIMATED)

    def test_var_is_parametric_and_stress_is_formulaic(self):
        v = var_risk_manager.var_engine.compute_value_at_risk()
        self.assertEqual(v["evaluation_method"], "parametric_var_zscore")
        st = var_risk_manager.var_engine.run_portfolio_stress_test()
        self.assertEqual(st["evaluation_method"], "formulaic_estimate")
        self.assertNotIn("PASSED_ALL_3_HISTORICAL_CRASH_SCENARIOS", st["stress_test_status"])
        for name, sc in st["scenarios_evaluated"].items():
            self.assertIn("ESTIMATED", sc["survival"])
            self.assertIn("loss_method", sc)

    def test_volume_profile_no_random_volume(self):
        import volume_profile
        vp = volume_profile.compute_volume_profile()
        self.assertIn(vp.get("data_status"), (truth.REAL, truth.ESTIMATED))
        self.assertNotIn("random", vp.get("volume_source", "").lower())


class TestUnsupportedClaims(unittest.TestCase):

    def test_market_brain_not_trained(self):
        row = {"rsi14": 50, "bb_lower": float("nan"), "bb_upper": float("nan"),
               "sma50": float("nan"), "sma200": float("nan")}
        out = market_brain.make_verdict(None, row, "TRENDING", 0, 6)
        self.assertEqual(out["calibration"], "FROZEN_PARAMETER_MODEL")
        self.assertEqual(out["measured_hit_rate_pct"], 42.8)
        joined = " ".join(out["reasons"])
        self.assertNotIn("Trained calibration", joined)

    def test_grep_guard_no_hardcoded_spot(self):
        for mod in ("run_all.py", "live_ticker_service.py", "smart_strike_selector.py",
                    "lstm_neural_engine.py", "volatility_forecaster.py",
                    "multi_leg_options.py"):
            self.assertNotIn("24403.10", _read_module(mod), mod)
            self.assertNotIn("24278.85", _read_module(mod), mod)

    def test_grep_guard_no_spot_strike_fallback(self):
        run_all_src = _read_module("run_all.py")
        self.assertNotIn("else 24500", run_all_src)
        self.assertNotIn("DEFAULT_SPOT", _read_module("multi_leg_options.py"))

    def test_grep_guard_no_fake_trained_labels(self):
        src = _read_module("market_brain.py")
        self.assertNotIn("TRAINED RULES", src)
        self.assertNotIn("TRAINED RELIABILITY", src)
        self.assertNotIn("Trained calibration", src)

    def test_grep_guard_no_false_enhancement_claim(self):
        self.assertNotIn("automatically updated weights", _read_module("auto_enhancer.py"))

    def test_grep_guard_no_default_spot_constant(self):
        self.assertNotIn("DEFAULT_SPOT", _read_module("smart_strike_selector.py"))


class TestProvenancePreservation(unittest.TestCase):

    def test_lstm_status_survives(self):
        out = predict_lstm_sequence()
        self.assertEqual(out["status"], truth.SIMULATED)

    def test_fallback_provenance_survives(self):
        with mock.patch.object(live_ticker_service, "yf", _FakeYfDown()):
            t = live_ticker_service.fetch_live_quote()
        if t["status"] == truth.FALLBACK:
            self.assertIn("fallback_used", t)
            self.assertIn("fallback_reason", t)
            self.assertIn("data_timestamp", t)
        elif t["status"] == truth.MISSING:
            self.assertIn("fallback_used", t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
