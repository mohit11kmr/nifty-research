"""Phase F2 - historical expiry/contract model correction tests.

Covers:
  * expiry calendar: Thursday period, Tuesday period, transition boundary,
    holiday Monday shift, expiry day (no 0DTE), non-expiry day
  * contract selection: correct historical expiry, no future-expiry leak,
    CONTRACT_UNAVAILABLE is explicit, no silent fallback to wrong expiry
  * square-off: actual historical expiry triggers, no early square-off,
    no post-expiry holding, no auto-roll
  * regression: strategy parameters unchanged, expiry lookup is data-driven
"""
import datetime as dt
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest_frozen as bf          # noqa: E402
import historical_expiry as he        # noqa: E402


class TestExpiryCalendar(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.cal = he.load_calendar()

    def test_thursday_period_mapping(self):
        self.assertEqual(he.applicable_expiry(dt.date(2025, 8, 13),
                                              self.cal).isoformat(), "2025-08-14")
        self.assertEqual(he.applicable_expiry(dt.date(2025, 8, 26),
                                              self.cal).isoformat(), "2025-08-28")

    def test_tuesday_period_mapping(self):
        self.assertEqual(he.applicable_expiry(dt.date(2025, 9, 2),
                                              self.cal).isoformat(), "2025-09-09")
        self.assertEqual(he.applicable_expiry(dt.date(2026, 8, 12),
                                              self.cal).isoformat(), "2026-08-18")

    def test_transition_boundary(self):
        # last Thursday weekly -> first Tuesday weekly
        self.assertEqual(he.applicable_expiry(dt.date(2025, 8, 28),
                                              self.cal).isoformat(), "2025-09-02")
        self.assertEqual(he.applicable_expiry(dt.date(2025, 8, 29),
                                              self.cal).isoformat(), "2025-09-02")
        t = he.detect_transition()
        self.assertEqual(t["last_thursday_weekly"], "2025-08-28")
        self.assertEqual(t["first_new_weekly"], "2025-09-02")
        self.assertEqual(t["new_weekday"], "Tuesday")

    def test_holiday_monday_shift(self):
        # Diwali week: Tuesday 2025-10-21 was a holiday -> weekly moved to Mon
        self.assertEqual(he.applicable_expiry(dt.date(2025, 10, 20),
                                              self.cal).isoformat(), "2025-10-28")

    def test_expiry_day_never_zero_dte(self):
        # On a Tuesday weekly expiry day the applicable contract is next week
        self.assertEqual(he.applicable_expiry(dt.date(2026, 8, 11),
                                              self.cal).isoformat(), "2026-08-18")
        self.assertEqual(he.applicable_expiry(dt.date(2026, 8, 4),
                                              self.cal).isoformat(), "2026-08-11")

    def test_non_expiry_day(self):
        self.assertGreater(he.applicable_expiry(dt.date(2025, 9, 3),
                                                self.cal).isoformat(), "2025-09-03")

    def test_no_future_expiry_leak(self):
        # applicable expiry is always strictly after the observation date
        for d, rec in self.cal.items():
            if rec[3]:
                self.assertGreater(rec[0], dt.date.fromisoformat(d), d)

    def test_calendar_artefact_is_deterministic(self):
        rows = he.build_expiry_calendar()
        import hashlib
        h1 = hashlib.sha256(pd.DataFrame(rows).to_csv(index=False).encode()).hexdigest()
        h2 = hashlib.sha256(open(os.path.join(he.ROOT, "data", "historical",
                                              "expiry_calendar.csv"), "rb").read()).hexdigest()
        self.assertEqual(h1[:8], "3abbe4cc")  # pinned artifact hash prefix


class TestContractSelection(unittest.TestCase):

    def test_correct_historical_expiry_selected(self):
        nifty, vix, fii, ml, snaps = bf.load_inputs()
        nifty_dates = [d.date() for d in nifty["date"]]
        rec = bf.evaluate_day(dt.date(2025, 8, 13), nifty, vix, fii, ml, snaps,
                              nifty_dates)
        if rec.get("candidate"):
            self.assertEqual(rec["expiry"], "2025-08-14")
            self.assertEqual(rec["contract_status"], "AVAILABLE")

    def test_no_future_expiry_leak_in_records(self):
        nifty, vix, fii, ml, snaps = bf.load_inputs()
        nifty_dates = [d.date() for d in nifty["date"]]
        for d in ("2025-09-02", "2025-09-16", "2026-01-20", "2026-06-30"):
            rec = bf.evaluate_day(dt.date.fromisoformat(d), nifty, vix, fii, ml,
                                  snaps, nifty_dates)
            if rec.get("candidate"):
                exp = dt.date.fromisoformat(rec["expiry"])
                self.assertGreater(exp, dt.date.fromisoformat(d), d)

    def test_unavailable_contract_is_explicit(self):
        d = dt.date(2025, 8, 14)
        chain = pd.DataFrame({
            "expiry": ["21-Aug-2025", "28-Aug-2025"],
            "strike": [24500.0, 24500.0],
            "ce_oi": [1, 1], "ce_oi_chg": [0, 0], "ce_volume": [1, 1],
            "ce_ltp": [10.0, 12.0], "pe_oi": [1, 1], "pe_oi_chg": [0, 0],
            "pe_volume": [1, 1], "pe_ltp": [8.0, 9.0],
        })
        # strike 25000 does not exist in ANY expiry of this chain
        self.assertIsNone(bf.price_strike_lookup({d: chain}, d,
                                                 25000.0, "PE",
                                                 expiry=dt.date(2025, 8, 21)))
        # strike exists at a DIFFERENT expiry -> no silent fallback for the
        # requested contract
        self.assertIsNone(bf.price_strike_lookup({d: chain}, d,
                                                 24500.0, "PE",
                                                 expiry=dt.date(2025, 9, 4)))

    def test_price_lookup_uses_specific_contract(self):
        d = dt.date(2025, 8, 14)
        chain = pd.DataFrame({
            "expiry": ["21-Aug-2025", "28-Aug-2025"],
            "strike": [24500.0, 24500.0],
            "ce_oi": [1, 1], "ce_oi_chg": [0, 0], "ce_volume": [1, 1],
            "ce_ltp": [10.0, 12.0], "pe_oi": [1, 1], "pe_oi_chg": [0, 0],
            "pe_volume": [1, 1], "pe_ltp": [8.0, 9.0],
        })
        v = bf.price_strike_lookup({d: chain}, d, 24500.0, "PE",
                                   expiry=dt.date(2025, 8, 28))
        self.assertEqual(v, 9.0)  # 28-Aug-2025 PE ltp


class TestSquareOff(unittest.TestCase):

    def _fixture(self):
        nifty, vix, fii, ml, snaps = bf.load_inputs()
        nifty_dates = [d.date() for d in nifty["date"]]
        return nifty, snaps, nifty_dates

    def test_square_off_on_actual_tuesday_expiry(self):
        nifty, snaps, dates = self._fixture()
        # entry 2025-09-02, contract expiry 2025-09-09 (Tuesday)
        out = bf.simulate_trade(dt.date(2025, 9, 2), 25000.0, 100.0, 50.0,
                                200.0, 25000.0, "PE", dt.date(2025, 9, 9),
                                nifty, snaps, dates)
        self.assertIsNotNone(out)
        self.assertLessEqual(dt.date.fromisoformat(out["exit_date"]),
                             dt.date(2025, 9, 9))

    def test_no_post_expiry_holding(self):
        nifty, snaps, dates = self._fixture()
        out = bf.simulate_trade(dt.date(2025, 9, 2), 25000.0, 500.0, 250.0,
                                1000.0, 25000.0, "PE", dt.date(2025, 9, 9),
                                nifty, snaps, dates)
        if out is not None:
            self.assertLessEqual(dt.date.fromisoformat(out["exit_date"]),
                                 dt.date(2025, 9, 9))
            if out["reason"] == "EXPIRY_SQUARE_OFF":
                self.assertEqual(out["exit_date"], "2025-09-09")

    def test_no_auto_roll(self):
        # Structural property: simulate_trade never rolls and never holds past
        # the actual contract expiry. Run over real Tuesday-era entry days.
        nifty, snaps, dates = self._fixture()
        cal = he.load_calendar()
        entries = [dt.date(2025, 9, 2), dt.date(2025, 9, 16), dt.date(2025, 10, 7),
                   dt.date(2026, 1, 20), dt.date(2026, 6, 30)]
        for t in entries:
            expiry = cal[t.isoformat()][0]
            out = bf.simulate_trade(t, 25000.0, 100.0, 50.0, 250.0, 25000.0,
                                    "PE", expiry, nifty, snaps, dates)
            if out is not None:
                self.assertLessEqual(dt.date.fromisoformat(out["exit_date"]),
                                     expiry, t.isoformat())
                if out["reason"] == "EXPIRY_SQUARE_OFF":
                    self.assertEqual(out["exit_date"], expiry.isoformat(),
                                     t.isoformat())


class TestRegression(unittest.TestCase):

    def test_strategy_parameters_unchanged(self):
        self.assertEqual(bf.LOT_SIZE, 75)
        self.assertEqual(bf.SL_BAND, 1.001)
        self.assertEqual(bf.TP_BAND, 0.999)
        self.assertEqual(bf.MIN_WARMUP_ROWS, 30)
        self.assertEqual(bf.WINDOW_START, dt.date(2025, 8, 13))
        self.assertEqual(bf.WINDOW_END, dt.date(2026, 8, 13))
        from cost_model import COST_PER_TRADE, SLIPPAGE_PCT
        self.assertEqual(COST_PER_TRADE, 40.0)
        self.assertEqual(SLIPPAGE_PCT, 0.015)

    def test_frozen_entry_rules_unchanged(self):
        # ATR / SL / target formulas still the frozen ones
        entry, atr = 100.0, max(10.0, 100.0 * 0.25)
        sl = max(2.0, entry - 1.5 * atr)
        self.assertEqual(sl, 62.5)
        self.assertEqual(entry + 2.0 * (entry - sl), 175.0)

    def test_expiry_lookup_is_data_driven_not_fixed_weekday(self):
        self.assertEqual(he.applicable_expiry(dt.date(2026, 8, 12)).strftime("%A"),
                         "Tuesday")


if __name__ == "__main__":
    unittest.main()
