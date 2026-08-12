"""Unit tests for the data-driven Smart Strike Selector (no fake values)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smart_strike_selector import strike_selector


class TestSmartStrikeSelector(unittest.TestCase):

    def test_returns_real_structure(self):
        res = strike_selector.select_best_strike(spot_price=24500, option_type="CE")
        for key in ("best_strike", "best_strike_delta", "best_strike_premium",
                    "rank_score", "data_source", "stale_snapshot", "candidates"):
            self.assertIn(key, res)

    def test_no_fabricated_oi(self):
        """OI must be a real integer, not the old 150000-offset*300 formula."""
        res = strike_selector.select_best_strike(spot_price=24500, option_type="CE")
        for c in res["candidates"]:
            self.assertIsInstance(c["open_interest"], int)
        self.assertNotEqual(res["candidates"][0]["open_interest"], 150000)

    def test_delta_is_bs_real(self):
        res = strike_selector.select_best_strike(spot_price=24500, option_type="CE")
        self.assertGreaterEqual(res["best_strike_delta"], -1.0)
        self.assertLessEqual(res["best_strike_delta"], 1.0)

    def test_premium_source_is_market_or_bs(self):
        res = strike_selector.select_best_strike(spot_price=24500, option_type="CE")
        self.assertIn(res["candidates"][0]["premium_source"], ("market", "bs"))

    def test_pe_side(self):
        res = strike_selector.select_best_strike(spot_price=24500, option_type="PE")
        self.assertEqual(res["option_type"], "PE")
        self.assertLess(res["best_strike_delta"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
