"""Phase F - historical collector output integrity tests.

Verifies the NSE bhavcopy collector (collect_historical_data.py) produced a
complete, point-in-time, no-lookahead-safe dataset:

  * manifest covers every window trading day with a verified source hash
  * bhavcopy underlying spot matches nifty_history close (cross-source check)
  * generated snapshots match the frozen backtest schema exactly
  * existing live-capture snapshots were never overwritten
  * no stale/future data (snapshot dated > evaluation day impossible by dir)
"""
import glob
import json
import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import collect_historical_data as chd  # noqa: E402

ROOT = chd.ROOT
WINDOW = (pd.Timestamp("2025-08-13"), pd.Timestamp("2026-08-13"))
# trading days present in nifty_history within the window
CALENDAR = [d.isoformat() for d in chd.trading_days("2025-08-13", "2026-08-13")]


class TestManifestIntegrity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.m = chd.load_manifest()

    def test_all_window_days_present_and_ok(self):
        missing = [d for d in CALENDAR if d not in self.m]
        self.assertEqual(missing, [])
        bad = [k for k, r in self.m.items() if r.get("status") != "OK"]
        self.assertEqual(bad, [])

    def test_every_entry_has_source_and_sha(self):
        for k, r in self.m.items():
            self.assertTrue(r.get("source", "").startswith("https://nsearchives"),
                            f"{k}: source")
            self.assertEqual(len(r.get("zip_sha256", "")), 64, f"{k}: sha256")

    def test_nifty_rows_present_both_sides(self):
        for k, r in self.m.items():
            self.assertGreater(r["nifty_rows"], 0, k)
            self.assertGreater(r["ce_rows"], 0, k)
            self.assertGreater(r["pe_rows"], 0, k)
            self.assertEqual(r["ce_rows"] + r["pe_rows"], r["nifty_rows"], k)

    def test_spot_matches_nifty_close(self):
        n = pd.read_csv(os.path.join(ROOT, "data", "nifty_history.csv"))
        n["date"] = pd.to_datetime(n["date"])
        close = n.set_index("date")["close"]
        bad = []
        for k, r in self.m.items():
            d = pd.Timestamp(k)
            if d in close.index and r.get("spot"):
                diff = abs(r["spot"] - float(close[d])) / float(close[d]) * 100
                if diff > 0.1:
                    bad.append((k, round(diff, 4)))
        self.assertEqual(bad, [], f"bhavcopy spot vs nifty close > 0.1%: {bad}")

    def test_no_future_data(self):
        for k in self.m:
            self.assertLessEqual(pd.Timestamp(k), WINDOW[1])


class TestSnapshotSchema(unittest.TestCase):

    def test_generated_snapshots_have_frozen_schema(self):
        exp_cols = ["expiry", "strike", "ce_oi", "ce_oi_chg", "ce_pct_chg",
                    "ce_volume", "ce_iv", "ce_ltp", "ce_buy_qty", "ce_sell_qty",
                    "pe_oi", "pe_oi_chg", "pe_pct_chg", "pe_volume", "pe_iv",
                    "pe_ltp", "pe_buy_qty", "pe_sell_qty"]
        checked = 0
        for p in glob.glob(os.path.join(ROOT, "data", "oi_snapshots", "NIFTY_*.csv")):
            b = os.path.basename(p).replace("NIFTY_", "").replace(".csv", "")
            if b not in chd.load_manifest():  # live captures / non-window
                continue
            df = pd.read_csv(p)
            self.assertEqual(list(df.columns), exp_cols, p)
            self.assertTrue((df["strike"] > 0).all(), p)
            self.assertTrue((df["ce_oi"] >= 0).all(), p)
            self.assertTrue((df["pe_oi"] >= 0).all(), p)
            checked += 1
        self.assertGreaterEqual(checked, 240, "expected ~241 bhavcopy snapshots")

    def test_expiry_format_matches_existing(self):
        df = pd.read_csv(os.path.join(ROOT, "data", "oi_snapshots",
                                      "NIFTY_2025-08-13.csv"))
        exp = set(df["expiry"])
        self.assertIn("14-Aug-2025", exp)  # weekly Thursday early window

    def test_iv_and_order_depth_are_honestly_unavailable(self):
        df = pd.read_csv(os.path.join(ROOT, "data", "oi_snapshots",
                                      "NIFTY_2025-08-13.csv"))
        self.assertTrue(df["ce_iv"].isna().all())
        self.assertTrue(df["pe_iv"].isna().all())
        self.assertTrue(df["ce_buy_qty"].isna().all())


class TestLiveCapturesPreserved(unittest.TestCase):

    def test_live_snapshot_files_not_overwritten(self):
        m = chd.load_manifest()
        for d in ("2026-08-11", "2026-08-12", "2026-08-13"):
            self.assertTrue(m[d].get("snapshot_skipped_existing"),
                            f"{d}: live capture must be kept, not bhavcopy")
            self.assertIsNone(m[d].get("snapshot_written"), d)


class TestConsumersWork(unittest.TestCase):
    """The generated historical snapshots must feed the frozen options layer
    exactly like live snapshots do (PCR / max pain / OI walls)."""

    def test_pcr_and_pain_and_walls_run(self):
        import oi_intel
        df = pd.read_csv(os.path.join(ROOT, "data", "oi_snapshots",
                                      "NIFTY_2025-08-13.csv"))
        p = oi_intel.pcr_and_pain(df, spot=24619.35)
        self.assertIsNotNone(p["pcr"])
        self.assertIsNotNone(p["max_pain"])
        w = oi_intel.oi_walls(df, spot=24619.35)
        self.assertTrue(w["resistance_oi"] and w["support_oi"])

    def test_skew_is_honest_neutral(self):
        import skew
        df = pd.read_csv(os.path.join(ROOT, "data", "oi_snapshots",
                                      "NIFTY_2025-08-13.csv"))
        s = skew.compute_iv_skew(df, spot=24619.35)
        self.assertEqual(s.get("bias"), "NEUTRAL")  # no IV -> honest NEUTRAL


if __name__ == "__main__":
    unittest.main()
