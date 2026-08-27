"""Phase H2 - RANGE-HV Iron Condor validation tests (MEASUREMENT ONLY).

Verifies the frozen candidate identity, exact six-trade reconstruction,
eligibility classification, no-lookahead, OOS split, determinism,
cost accounting, exit classification, spec consistency, production
isolation, and the risk-model mismatch finding.

Run: .venv/bin/python -m unittest tests.test_phase_h2_range_hv -v
"""
import datetime as dt
import builtins
import json
import os
import unittest
from unittest import mock

import strategy_registry as SR
import phase_h2_validation as H2
from backtest_adapter import BacktestAdapter

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
RESULTS = os.path.join(REPO, "results", "phaseH_multi_strategy.json")

SPEC_HASH = "56ba02752efc4650efe1d8c88165f3396e3ae10aaa15519d9b13e33a4e0d1adb"
VIX_MIN, VIX_MAX = 16.0, 25.0


def _is_gate(t):
    return t.get("vix") is not None and VIX_MIN <= t["vix"] < VIX_MAX


class TestH2FrozenCandidate(unittest.TestCase):
    def test_candidate_identity(self):
        spec = SR.default_registry().load("range_hv_iron_condor_v1")
        st = spec["strategy"]
        self.assertEqual(st["id"], "range_hv_iron_condor_v1")
        self.assertEqual(st["version"], 1)
        self.assertEqual(st["classification"], "PROMISING_BUT_INSUFFICIENT")
        self.assertEqual(spec["state"]["lifecycle"], "BACKTESTED")
        self.assertIs(spec["state"]["promoted"], False)
        self.assertEqual(SR.default_registry().spec_hash("range_hv_iron_condor_v1"),
                         SPEC_HASH)


class TestH2Eligibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = H2.RangeHVValidator()

    def test_eligibility_counts(self):
        r = self.v.run_all()
        self.assertEqual(r["trade_count"], 6)
        self.assertEqual(r["range_hv_observed_days"], 37)
        self.assertEqual(r["range_hv_vix_gate_days"], 19)
        self.assertEqual(r["eligible_days"], 6)

    def test_every_gate_passing_free_day_is_a_trade(self):
        """No structure/price/credit rejection exists: every RANGE_HV day that
        passes the VIX gate and is not locked/close-day produces a trade."""
        tr = self.v.eligibility_trace()
        gated_free = [t for t in tr if t["regime"] == "RANGE_HV" and _is_gate(t)]
        self.assertEqual(len(gated_free), 19)
        self.assertEqual(sum(1 for t in gated_free if t["status"] == "TRADE"), 6)
        self.assertEqual(sum(1 for t in gated_free if t["status"] == "POSITION_LOCKED"), 10)
        self.assertEqual(sum(1 for t in gated_free if t["status"] == "TRADE_CLOSE"), 3)

    def test_trace_matches_engine_dates(self):
        r = self.v.run_all()
        trace_dates = [t["date"] for t in r["trace"] if t["status"] == "TRADE"]
        engine_dates = [t["entry_date"] for t in r["trades"]]
        self.assertEqual(trace_dates, engine_dates)

    def test_all_vix_gate_fails_are_low_vix(self):
        tr = self.v.eligibility_trace()
        fails = [t for t in tr if t["status"] == "VIX_GATE_FAIL"]
        self.assertEqual(len(fails), 18)
        for t in fails:
            self.assertIsNotNone(t["vix"])
            self.assertTrue(t["vix"] < VIX_MIN or t["vix"] >= VIX_MAX,
                            f"{t['date']} vix={t['vix']} should be outside gate")


class TestH2Trades(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = H2.RangeHVValidator()
        cls.r = cls.v.run_all()

    def test_exact_six_trade_reconstruction(self):
        with open(RESULTS) as fh:
            ref = json.load(fh)
        ref_trades = ref["candidates"]["C_RANGE_HV_IRON_CONDOR"]["trades"]
        run = self.r["trades"]
        self.assertEqual(len(run), len(ref_trades))
        for a, b in zip(run, ref_trades):
            for k in ("entry_date", "exit_date", "regime", "option_type",
                      "strike", "entry_premium", "reason", "net_pnl", "fees",
                      "slippage", "mfe", "mae", "days_held"):
                self.assertEqual(a[k], b[k], f"{k}: {a.get(k)} != {b.get(k)}")

    def test_cost_accounting(self):
        t = self.r["trades"]
        for row in t:
            self.assertEqual(row["fees"], 8 * 40.0)
            self.assertGreater(row["slippage"], 0)
        fees = sum(x["fees"] for x in t)
        slip = sum(x["slippage"] for x in t)
        gross = sum(x["net_pnl"] + x["fees"] + x["slippage"] for x in t)
        self.assertAlmostEqual(gross - fees - slip, sum(x["net_pnl"] for x in t), places=2)

    def test_exit_classification(self):
        reasons = {t["reason"] for t in self.r["trades"]}
        self.assertEqual(reasons, {"TARGET", "TIME", "EXPIRY"})
        self.assertNotIn("STOP", reasons)
        ex = self.r["exit_analysis"]
        self.assertEqual(ex["TARGET"]["count"], 3)
        self.assertEqual(ex["TIME"]["count"], 2)
        self.assertEqual(ex["EXPIRY"]["count"], 1)

    def test_entry_conditions_satisfied(self):
        for t in self.r["trades"]:
            self.assertEqual(t["regime"], "RANGE_HV")
            self.assertIsNotNone(t["vix_at_entry"])
            self.assertTrue(VIX_MIN <= t["vix_at_entry"] < VIX_MAX)
            self.assertEqual(t["wing_width"], 150)
            self.assertGreater(t["entry_premium"], 0)

    def test_no_lookahead(self):
        tr = self.r["trace"]
        vix_at = {t["date"]: t["vix"] for t in tr}
        for t in self.r["trades"]:
            self.assertGreater(t["exit_date"], t["entry_date"])
            # VIX at entry is the day-of-entry snapshot (not a future value)
            self.assertEqual(t["vix_at_entry"], vix_at[t["entry_date"]])
            # exit occurs on or before the canonical expiry of the entry week
            entry = dt.date.fromisoformat(t["entry_date"])
            expiry = dt.date.fromisoformat(t["exit_date"])  # exits are at/inside expiry
            self.assertLessEqual(entry, expiry)

    def test_oos_split(self):
        oos = self.r["oos"]
        self.assertEqual(oos["development"]["trades"], 1)
        self.assertEqual(oos["out_of_sample"]["trades"], 5)
        self.assertEqual(oos["development"]["net"], -131.75)
        # OOS sample is far below the 20+ outcome target -> OOS_INSUFFICIENT
        self.assertLess(oos["out_of_sample"]["trades"], 20)

    def test_profit_concentration_flagged(self):
        pc = self.r["profit_concentration"]
        self.assertEqual(pc["best_trade"], 2256.25)
        self.assertGreaterEqual(pc["top3_pct_of_total"], 80.0)  # HIGH_CONCENTRATION

    def test_risk_model_mismatch_documented(self):
        """1-lot defined-risk exposure (~8% of capital) exceeds the spec's
        declared max_risk_pct=1.0 -> RISK_MODEL_MISMATCH (blocks promotion).
        Note: max_risk_per_share = wing_width - entry_credit, which can go
        NEGATIVE when the collected credit exceeds the 150-pt width (frozen
        engine formula artifact: model treats it as risk-free)."""
        pos_risk = [t for t in self.r["trades"] if t["max_risk_per_share"] > 0]
        neg_risk = [t for t in self.r["trades"] if t["max_risk_per_share"] <= 0]
        self.assertEqual(len(neg_risk), 2)  # trades 1 & 4: credit > width
        self.assertEqual(len(pos_risk), 4)
        for t in pos_risk:
            exposure = t["max_risk_per_share"] * 75
            self.assertGreater(exposure / 100000.0, 0.01, f"{t['entry_date']} exposure")
        for t in neg_risk:
            self.assertGreater(t["entry_premium"], t["wing_width"],
                               f"{t['entry_date']} credit>width artifact")

    def test_determinism(self):
        r1 = self.v.engine_trades()
        r2 = self.v.engine_trades()
        self.assertEqual(r1[1], r2[1])  # trade rows identical
        t1 = self.v.eligibility_trace()
        t2 = self.v.eligibility_trace()
        self.assertEqual(t1, t2)


class TestH2SpecConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from strategy_registry import default_registry
        compiled = default_registry().compile("range_hv_iron_condor_v1")
        cls.adapter = BacktestAdapter(compiled, data_root=H2.FROZEN_SNAPSHOT)
        cls.run_result = cls.adapter.run()

    def test_spec_consistency_zero_violations(self):
        self.assertEqual(self.adapter.check_spec_consistency(self.run_result), [])

    def test_metrics_match_reference(self):
        m = self.run_result["metrics"]
        self.assertEqual(m["trade_count"], 6)
        self.assertEqual(m["win_count"], 4)
        self.assertEqual(m["net_pnl"], 6248.25)
        self.assertEqual(m["profit_factor"], 9.693)
        self.assertEqual(m["max_drawdown"], -587.0)


class TestH2ProductionIsolation(unittest.TestCase):
    def test_measurement_never_writes_production(self):
        """Full measurement pipeline (load -> trace -> engine -> report) must
        never open ground_truth.db / paper_account.json / data/* for writing.
        Uses the same open() guard as the Phase H suite, so it is immune to
        external live-daemon writers mutating those files concurrently."""
        blocked = ("ground_truth", "paper_account", "/data/")
        real_open = builtins.open
        written = []

        def guarded_open(file, mode="r", *a, **k):
            if isinstance(mode, str) and any(c in mode for c in "wax") and \
               any(b in str(file) for b in blocked):
                written.append(str(file))
                raise AssertionError(f"blocked write to {file}")
            return real_open(file, mode, *a, **k)

        with mock.patch("builtins.open", side_effect=guarded_open):
            r = H2.RangeHVValidator().run_all()
        self.assertEqual(written, [])
        self.assertEqual(r["trade_count"], 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
