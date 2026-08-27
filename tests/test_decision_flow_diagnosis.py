"""Phase 6.6 - read-only diagnostic tests for the trading decision flow.

These tests PROVE the current decision-flow behavior without writing anything
to the production ledger and without calling generate_precision_signal()
(which records into data/ground_truth.db).

Covers:
1. Regime classification from the actual current cache (RANGE_LV -> NO_TRADE).
2. GroundTruthDB decision mapping: STAY_OUT -> SKIP (capital guard NOT the
   reason), ENTER + guard-APPROVED -> ENTER, ENTER + guard-REJECTED -> REJECT.
3. Candidate-generation invariant: the current REAL_FRESH ledger contains
   zero directional candidates (predictions/executions/positions = 0).
"""
import os
import sys
import sqlite3
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np

import regime_filter
import ground_truth


def _synthetic_df(adx=12.0, pdi=25.0, mdi=26.0, bb_pctile_high=False):
    """Build a minimal indicator frame with a controllable ADX/directional
    spread and Bollinger width percentile (high vs low vol)."""
    n = 120
    close = np.linspace(24400, 24395, n) + np.random.RandomState(0).normal(0, 5, n)
    df = pd.DataFrame({
        "date": pd.date_range("2026-04-01", periods=n, freq="B"),
        "close": close,
    })
    if bb_pctile_high:
        width = np.full(n, 10.0)
        width[-1] = 60.0
    else:
        width = np.full(n, 10.0)
    df["bb_upper"] = close + width
    df["bb_lower"] = close - width
    df["adx"] = adx
    df["pdi"] = pdi
    df["mdi"] = mdi
    return df


class TestRegimeClassification(unittest.TestCase):
    def test_low_adx_and_low_vol_is_range_lv(self):
        df = _synthetic_df(adx=12.7, pdi=25.1, mdi=26.1, bb_pctile_high=False)
        regime, _ = regime_filter.detect_regime(df.iloc[-1], df)
        self.assertEqual(regime, "RANGE_LV")
        self.assertEqual(regime_filter.REGIME_PROFILE[regime]["gate"], "NO_TRADE")

    def test_high_adx_and_spread_is_trend(self):
        df = _synthetic_df(adx=30.0, pdi=30.0, mdi=22.0, bb_pctile_high=False)
        regime, _ = regime_filter.detect_regime(df.iloc[-1], df)
        self.assertIn(regime, ("TREND_HV", "TREND_LV"))

    def test_high_vol_and_no_trend_is_range_hv(self):
        df = _synthetic_df(adx=12.7, pdi=25.1, mdi=26.1, bb_pctile_high=True)
        regime, _ = regime_filter.detect_regime(df.iloc[-1], df)
        self.assertEqual(regime, "RANGE_HV")

    def test_current_cached_data_classifies_range_lv(self):
        """Documents the CURRENT driver state (empirical, read-only).

        If NIFTY starts trending this test will fail - that failure is the
        signal that the regime gate is no longer the blocker."""
        df = regime_filter._load_nifty_cached()
        row = df.iloc[-1]
        regime, reasons = regime_filter.detect_regime(row, df)
        self.assertEqual(regime, "RANGE_LV", reasons)
        plan = regime_filter.trade_plan(df=df, row=row)
        self.assertEqual(plan["gate"], "NO_TRADE")


class TestDecisionMapping(unittest.TestCase):
    def setUp(self):
        self.db = ground_truth.GroundTruthDB()

    def test_stay_out_maps_to_skip_regardless_of_capital_guard(self):
        decision, reason = self.db._derive_decision("STAY_OUT", "NO_SIGNAL (FILTERED OUT NOISE)",
                                                    {"safety_status": "APPROVED"})
        self.assertEqual(decision, "SKIP")
        self.assertIn("no evaluable signal", reason)

    def test_stay_out_skips_even_if_guard_would_approve(self):
        """Capital Guard APPROVED must NOT be read as trade approval."""
        decision, reason = self.db._derive_decision("STAY_OUT", "NO_SIGNAL",
                                                    {"safety_status": "APPROVED"})
        self.assertEqual(decision, "SKIP")

    def test_enter_with_approved_guard_is_enter(self):
        decision, _ = self.db._derive_decision("HIGH_CONVICTION_CALL", "A+ GRADE",
                                               {"safety_status": "APPROVED"})
        self.assertEqual(decision, "ENTER")

    def test_enter_with_rejected_guard_is_reject(self):
        decision, reason = self.db._derive_decision("HIGH_CONVICTION_CALL", "A+ GRADE",
                                                    {"safety_status": "RESTRICTED"})
        self.assertEqual(decision, "REJECT")
        self.assertIn("capital guard", reason)


class TestCandidateInvariant(unittest.TestCase):
    def test_production_ledger_has_zero_directional_candidates(self):
        """Read-only SELECT on the production ledger."""
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "data", "ground_truth.db")
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            n_pred = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
            n_exec = conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
            n_pos = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual((n_pred, n_exec, n_pos), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
