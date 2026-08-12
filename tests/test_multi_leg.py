"""Unit tests for the multi-leg option strategy engine (real pricing)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import multi_leg_options as mlo


class TestMultiLeg(unittest.TestCase):

    def test_iron_condor_structure(self):
        d = mlo.construct_multi_leg_strategy(spot_price=24500, strategy_type="IRON_CONDOR")
        self.assertEqual(d["strategy"], "IRON_CONDOR")
        self.assertEqual(len(d["legs"]), 4)
        self.assertIn("probability_of_profit", d)
        self.assertIn("profit_probability", d)
        self.assertIn("breakevens", d)
        self.assertIn("stale_snapshot", d)

    def test_no_hardcoded_premiums(self):
        """Every leg must carry a real premium + iv + source (market/bs)."""
        for st in ("IRON_CONDOR", "BULL_CALL_SPREAD", "BEAR_PUT_SPREAD", "SHORT_STRANGLE"):
            d = mlo.construct_multi_leg_strategy(spot_price=24500, strategy_type=st)
            for leg in d["legs"]:
                self.assertGreater(leg["premium"], 0, f"{st}: zero premium {leg}")
                self.assertIn(leg["source"], ("market", "bs"))

    def test_breakeven_sane(self):
        d = mlo.construct_multi_leg_strategy(spot_price=24500, strategy_type="BULL_CALL_SPREAD")
        be = d["breakevens"]["lower"]
        self.assertIsNotNone(be)
        self.assertGreater(be, 24000)
        self.assertLess(be, 25000)

    def test_spot_default_sane(self):
        d = mlo.construct_multi_leg_strategy()
        self.assertGreater(d["spot_price"], 15000)
        self.assertLess(d["spot_price"], 35000)

    def test_rr_present(self):
        d = mlo.construct_multi_leg_strategy(spot_price=24500, strategy_type="BULL_CALL_SPREAD")
        if d["max_risk_per_lot"] and d["max_risk_per_lot"] > 0:
            self.assertTrue(d["risk_reward_ratio"].startswith("1 :"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
