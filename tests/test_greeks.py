"""Unit tests for the Black-Scholes Greeks / PoP / what-if engines."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from greeks import (bs_price_and_greeks, probability_of_profit,
                    what_if_greeks, classify_strike)


class TestGreeks(unittest.TestCase):

    def test_call_put_parity_price(self):
        """Call + PV(K) == Put + Spot must hold within tolerance."""
        spot, strike, t, sig, r = 24450.0, 24500.0, 7, 0.15, 0.06
        c = bs_price_and_greeks(spot, strike, t, sig, "CE", r)
        p = bs_price_and_greeks(spot, strike, t, sig, "PE", r)
        import math
        pv_k = strike * math.exp(-r * t / 252)
        self.assertAlmostEqual(c["price"] + pv_k, p["price"] + spot, delta=0.5)

    def test_greeks_signs(self):
        c = bs_price_and_greeks(24450, 24500, 7, 0.15, "CE")
        p = bs_price_and_greeks(24450, 24500, 7, 0.15, "PE")
        self.assertGreater(c["delta"], 0)
        self.assertLess(c["delta"], 1)
        self.assertLess(p["delta"], 0)
        self.assertGreater(c["gamma"], 0)
        self.assertLess(c["theta"], 0)
        self.assertGreater(c["vega"], 0)
        self.assertGreater(c["rho"], 0)
        self.assertLess(p["rho"], 0)

    def test_atm_delta_symmetric(self):
        c = bs_price_and_greeks(24450, 24450, 20, 0.15, "CE")
        p = bs_price_and_greeks(24450, 24450, 20, 0.15, "PE")
        self.assertAlmostEqual(c["delta"] - p["delta"], 1.0, delta=0.02)

    def test_pop_bounds(self):
        self.assertGreater(probability_of_profit(24450, lower=24000, sigma_ann=0.15, t_days=20), 0.5)
        self.assertGreater(probability_of_profit(24450, upper=25000, sigma_ann=0.15, t_days=20), 0.5)
        self.assertLess(probability_of_profit(24450, lower=25000, sigma_ann=0.15, t_days=20), 0.5)
        self.assertLess(probability_of_profit(24450, upper=24000, sigma_ann=0.15, t_days=20), 0.5)
        p_band = probability_of_profit(24450, lower=24000, upper=25000, sigma_ann=0.15, t_days=20)
        self.assertGreaterEqual(p_band, 0.0)
        self.assertLessEqual(p_band, 1.0)
        self.assertIsNone(probability_of_profit(24450))

    def test_what_if_grid_shape(self):
        w = what_if_greeks(24450, 24500, 7, 0.15, "CE",
                           spot_shifts_pct=(-1, 0, 1), vol_shifts_pts=(-1, 0, 1))
        self.assertEqual(len(w["grid"]), 3)
        self.assertIn("price_iv+0", w["grid"][1])
        self.assertGreater(w["grid"][2]["price_iv+0"], w["grid"][0]["price_iv+0"])

    def test_classify_strike(self):
        self.assertEqual(classify_strike(24450, 24450), "ATM")
        self.assertIn("OTM", classify_strike(24450, 24700))


if __name__ == "__main__":
    unittest.main(verbosity=2)
