"""Data-expansion - OPTIONS EOD DEEP ARCHIVE integrity tests.

Covers the official NSE/UDiFF options EOD archive (2024-01-01..2026-08-13):

  * 2024 UDiFF format parsing (OpnPric/HghPric/LwPric/ClsPric/SttlmPric)
  * 2025+ format aliases (HighPric/LowPric/SetlPric)
  * CE/PE, expiry, strike, price/OI/volume fields, underlying price, lot size
  * malformed-row quarantine (never silently dropped)
  * duplicate + conflict detection on (date, expiry, strike, option_type)
  * raw file SHA256 vs manifest
  * idempotent re-normalization (data-stable; only retrieved_at metadata moves)
  * no production writes (collector output confined to data/historical/)
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import collect_historical_data_deep as chd  # noqa: E402

ROOT = chd.ROOT

UDIFF_2024 = pd.DataFrame([
    {"TckrSymb": "NIFTY", "FinInstrmTp": "IDO", "XpryDt": "2024-01-11",
     "StrkPric": "20500", "OptnTp": "CE", "OpnPric": "120.0", "HghPric": "135.5",
     "LwPric": "118.0", "ClsPric": "130.25", "SttlmPric": "130.25",
     "UndrlygPric": "21665.8", "TtlTradgVol": "15000", "TtlTrfVal": "1.5e9",
     "OpnIntrst": "120000", "ChngInOpnIntrst": "5000", "NewBrdLotQty": "75"},
    {"TckrSymb": "NIFTY", "FinInstrmTp": "IDO", "XpryDt": "2024-01-11",
     "StrkPric": "20400", "OptnTp": "PE", "OpnPric": "80.0", "HghPric": "90.0",
     "LwPric": "79.0", "ClsPric": "88.5", "SttlmPric": "88.5",
     "UndrlygPric": "21665.8", "TtlTradgVol": "9000", "TtlTrfVal": "8e8",
     "OpnIntrst": "80000", "ChngInOpnIntrst": "-2000", "NewBrdLotQty": "75"},
])

UDIFF_2025 = pd.DataFrame([
    {"TckrSymb": "NIFTY", "FinInstrmTp": "IDO", "XpryDt": "2025-09-30",
     "StrkPric": "24500", "OptnTp": "CE", "OpnPric": "90.0", "HighPric": "95.0",
     "LowPric": "85.0", "ClsPric": "92.0", "SetlPric": "92.0",
     "UndrlygPric": "24487.4", "TtlTradgVol": "420", "TtlTrfVal": "7.7e8",
     "OpnIntrst": "112425", "ChngInOpnIntrst": "-1575", "NewBrdLotQty": "75"},
])


class TestUdiffParsing2024(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.norm, cls.quar = chd.normalize_udiff_day(UDIFF_2024, "2024-01-02",
                                                     raw_hash="abc123")

    def test_schema_exact(self):
        self.assertEqual(list(self.norm.columns), chd.OPTIONS_EOD_COLS)

    def test_no_quarantine_for_valid_rows(self):
        self.assertEqual(len(self.quar), 0)
        self.assertEqual(len(self.norm), 2)

    def test_ce_pe_preserved(self):
        self.assertEqual(set(self.norm["option_type"]), {"CE", "PE"})

    def test_expiry_parsed(self):
        self.assertTrue((self.norm["expiry"].astype(str) == "2024-01-11").all())

    def test_strike_parsed(self):
        self.assertEqual(list(self.norm["strike"]), [20500.0, 20400.0])

    def test_price_fields(self):
        row = self.norm[self.norm["option_type"] == "CE"].iloc[0]
        self.assertEqual(row["open"], 120.0)
        self.assertEqual(row["high"], 135.5)
        self.assertEqual(row["low"], 118.0)
        self.assertEqual(row["close"], 130.25)
        self.assertEqual(row["settle_price"], 130.25)

    def test_oi_and_change(self):
        pe = self.norm[self.norm["option_type"] == "PE"].iloc[0]
        self.assertEqual(pe["oi"], 80000)
        self.assertEqual(pe["oi_chg"], -2000.0)  # signed, legitimately negative

    def test_volume_turnover(self):
        row = self.norm[self.norm["option_type"] == "CE"].iloc[0]
        self.assertEqual(row["volume"], 15000)
        self.assertEqual(row["turnover"], 1.5e9)

    def test_underlying_price_and_lot_size(self):
        self.assertTrue((self.norm["underlying_price"] == 21665.8).all())
        self.assertTrue((self.norm["lot_size"] == 75).all())

    def test_provenance_and_metadata(self):
        row = self.norm.iloc[0]
        self.assertEqual(row["underlying"], "NIFTY")
        self.assertEqual(row["instrument_type"], "OPTIDX")
        self.assertEqual(row["source"], "NSE_UDiFF_BHAVCOPY")
        self.assertEqual(row["provenance"], "REAL")
        self.assertEqual(row["quality"], "A")
        self.assertEqual(row["raw_file_hash"], "abc123")
        self.assertEqual(row["availability_time"], "2024-01-02 23:59:59")


class TestUdiffParsing2025Aliases(unittest.TestCase):
    """2025+ UDiFF uses HighPric/LowPric/SetlPric aliases."""

    def test_aliases_mapped(self):
        norm, quar = chd.normalize_udiff_day(UDIFF_2025, "2025-08-12")
        self.assertEqual(len(quar), 0)
        row = norm.iloc[0]
        self.assertEqual(row["high"], 95.0)
        self.assertEqual(row["low"], 85.0)
        self.assertEqual(row["settle_price"], 92.0)
        self.assertEqual(row["strike"], 24500.0)


class TestQuarantine(unittest.TestCase):
    """Malformed rows must be quarantined with reasons, never dropped."""

    def test_bad_option_type_and_negative_price_quarantined(self):
        bad = pd.DataFrame([
            {"XpryDt": "2024-01-11", "StrkPric": "20500", "OptnTp": "XX",
             "OpnPric": "1.0", "HghPric": "2.0", "LwPric": "0.5",
             "ClsPric": "1.5", "SttlmPric": "1.5", "UndrlygPric": "21665.8",
             "TtlTradgVol": "0", "TtlTrfVal": "0", "OpnIntrst": "0",
             "ChngInOpnIntrst": "0", "NewBrdLotQty": "75"},
            {"XpryDt": "2024-01-11", "StrkPric": "20400", "OptnTp": "PE",
             "OpnPric": "-5.0", "HghPric": "2.0", "LwPric": "0.5",
             "ClsPric": "1.5", "SttlmPric": "1.5", "UndrlygPric": "21665.8",
             "TtlTradgVol": "0", "TtlTrfVal": "0", "OpnIntrst": "0",
             "ChngInOpnIntrst": "0", "NewBrdLotQty": "75"},
        ])
        norm, quar = chd.normalize_udiff_day(bad, "2024-01-02")
        self.assertEqual(len(norm), 0)
        self.assertEqual(len(quar), 2)
        reasons = "|".join(quar["quarantine_reason"])
        self.assertIn("option_type_invalid", reasons)
        self.assertIn("open_negative", reasons)
        self.assertIn("quarantine_source", quar.columns)

    def test_missing_strike_quarantined(self):
        bad = UDIFF_2024.copy()
        bad.loc[0, "StrkPric"] = ""
        norm, quar = chd.normalize_udiff_day(bad, "2024-01-02")
        self.assertEqual(len(norm), 1)
        self.assertEqual(len(quar), 1)
        self.assertIn("strike_invalid", quar.iloc[0]["quarantine_reason"])


class TestDuplicateAndConflictDetection(unittest.TestCase):

    def test_exact_duplicate_detected(self):
        df = pd.concat([UDIFF_2024.iloc[[0]], UDIFF_2024.iloc[[0]]], ignore_index=True)
        norm, _ = chd.normalize_udiff_day(df, "2024-01-02")
        # normalized rows identical -> drop_duplicates collapses to 1
        key = ["date", "expiry", "strike", "option_type"]
        self.assertEqual(len(norm), 2)
        self.assertEqual(len(norm.drop_duplicates(subset=key)), 1)
        self.assertEqual(int(norm.duplicated(subset=key).sum()), 1)

    def test_conflict_detected(self):
        a = UDIFF_2024.iloc[[0]].copy()
        b = UDIFF_2024.iloc[[0]].copy()
        b.loc[0, "ClsPric"] = "999.0"  # disagree on close
        both = pd.concat([a, b], ignore_index=True)
        norm, _ = chd.normalize_udiff_day(both, "2024-01-02")
        conflicts = chd.detect_conflicts(norm)
        self.assertEqual(len(conflicts), 2)
        self.assertEqual(set(conflicts["close"]), {130.25, 999.0})

    def test_no_conflict_when_identical(self):
        both = pd.concat([UDIFF_2024.iloc[[0]], UDIFF_2024.iloc[[0]]],
                         ignore_index=True)
        norm, _ = chd.normalize_udiff_day(both, "2024-01-02")
        self.assertEqual(len(chd.detect_conflicts(norm)), 0)


class TestRawChecksums(unittest.TestCase):
    """Every archived raw file must match its manifest raw_sha256."""

    @classmethod
    def setUpClass(cls):
        cls.m = chd.load_manifest("bhavcopy").get("days", {})

    def test_sample_raw_files_hash_to_manifest(self):
        bad = []
        for d in ("2024-01-02", "2024-06-03", "2025-08-12", "2025-08-13",
                  "2026-08-13"):
            rec = self.m.get(d)
            if not rec or rec.get("status") != "OK":
                continue
            p = os.path.join(ROOT, "data", "historical", "raw", "bhavcopy",
                             f"NIFTY_{d}.csv")
            if os.path.exists(p) and chd.sha256_file(p) != rec.get("raw_sha256"):
                bad.append(d)
        self.assertEqual(bad, [])

    def test_manifest_has_raw_sha_for_all_ok_days(self):
        missing_sha = [d for d, r in self.m.items()
                       if r.get("status") == "OK" and not r.get("raw_sha256")]
        self.assertEqual(missing_sha, [])


class TestNormalizedDataset(unittest.TestCase):
    """End-to-end checks on the archived normalized dataset."""

    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv(os.path.join(
            ROOT, "data", "historical", "normalized", "options_eod_expanded.csv"))
        cls.mani = json.load(open(os.path.join(
            ROOT, "data", "historical", "manifests",
            "normalized_options_eod_expanded.json")))

    def test_coverage_horizon(self):
        self.assertEqual(self.mani["coverage_start"], "2024-01-01")
        self.assertEqual(self.mani["coverage_end"], "2026-08-13")

    def test_no_duplicate_contract_keys(self):
        key = ["date", "expiry", "strike", "option_type"]
        self.assertEqual(self.df.duplicated(subset=key).sum(), 0)

    def test_only_ce_pe(self):
        self.assertEqual(set(self.df["option_type"]), {"CE", "PE"})

    def test_no_negative_oi_volume_prices(self):
        for c in ("oi", "volume", "open", "high", "low", "close",
                  "settle_price"):
            self.assertGreaterEqual(self.df[c].min(), 0, c)

    def test_expiry_after_trade_date(self):
        d = pd.to_datetime(self.df["date"])
        e = pd.to_datetime(self.df["expiry"])
        self.assertEqual((e < d).sum(), 0)

    def test_underlying_present(self):
        self.assertTrue(self.df["underlying_price"].notna().any())
        self.assertEqual(set(self.df["underlying"]), {"NIFTY"})

    def test_manifest_sha_matches_file(self):
        self.assertEqual(self.mani["sha256"], chd.sha256_file(os.path.join(
            ROOT, "data", "historical", "normalized", "options_eod_expanded.csv")))

    def test_2024_and_2025_and_2026_all_present(self):
        years = {d[:4] for d in self.df["date"]}
        self.assertIn("2024", years)
        self.assertIn("2025", years)
        self.assertIn("2026", years)


class TestIdempotentRerun(unittest.TestCase):
    """Re-normalizing over the same raw files yields identical data; only the
    retrieved_at metadata stamp changes per run."""

    def test_rerun_data_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_raw, old_norm = chd.RAW, chd.NORM
            old_quar, old_mani = chd.QUAR, chd.MANI
            try:
                chd.RAW = os.path.join(tmp, "raw")
                chd.NORM = os.path.join(tmp, "normalized")
                chd.QUAR = os.path.join(tmp, "quarantine")
                chd.MANI = os.path.join(tmp, "manifests")
                os.makedirs(chd.RAW)
                os.makedirs(chd.NORM)
                os.makedirs(chd.QUAR)
                os.makedirs(chd.MANI)
                for d, df in (("2024-01-02", UDIFF_2024),
                              ("2025-08-12", UDIFF_2025)):
                    df.to_csv(os.path.join(chd.RAW, f"NIFTY_{d}.csv"),
                              index=False, encoding="latin1")
                out1, _ = chd.normalize_bhavcopy()
                out2, _ = chd.normalize_bhavcopy()
                drop = [c for c in ("retrieved_at", "source_url")
                        if c in out1.columns]
                pd.testing.assert_frame_equal(
                    out1.drop(columns=drop).reset_index(drop=True),
                    out2.drop(columns=drop).reset_index(drop=True))
            finally:
                chd.RAW, chd.NORM = old_raw, old_norm
                chd.QUAR, chd.MANI = old_quar, old_mani


class TestNoProductionWrites(unittest.TestCase):
    """The collector must confine writes to data/historical/ and never touch
    strategy / ground truth / paper account / live trading state."""

    def test_output_dirs_are_isolated(self):
        self.assertTrue(chd.RAW.startswith(os.path.join(chd.ROOT, "data", "historical")))
        self.assertTrue(chd.NORM.startswith(os.path.join(chd.ROOT, "data", "historical")))
        self.assertTrue(chd.QUAR.startswith(os.path.join(chd.ROOT, "data", "historical")))
        self.assertTrue(chd.MANI.startswith(os.path.join(chd.ROOT, "data", "historical")))

    def test_no_production_paths_referenced(self):
        src = open(os.path.join(chd.ROOT, "collect_historical_data_deep.py")).read()
        if src.startswith('"""'):
            src = src.split('"""', 2)[2]  # strip module docstring
        # read-only audit inventory may NAME these files; write operations must
        # never target them.
        write_ops = ('"w"', '"wb"', '"a"', "to_csv(", "save_json(",
                     "save_manifest(", "atomic_write(")
        forbidden = ("ground_truth.db", "paper_account.json", "oi_snapshots",
                     "research.db")
        bad = [(i, line.strip()) for i, line in enumerate(src.splitlines(), 1)
               if any(w in line for w in write_ops)
               and any(f in line for f in forbidden)]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
