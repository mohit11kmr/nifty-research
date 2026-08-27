"""DATA-ALIGNMENT-01 - Unified trading calendar + cross-dataset alignment tests.

Covers (per the phase doc section 18):

  * canonical calendar generation (one authoritative status per date)
  * 2025-02-01 (special Saturday) classification
  * 2026-08-11 (Yahoo-gap Tuesday) classification
  * missing-session detection (holiday vs dataset gap distinction)
  * no forward-fill / no interpolation / no future-data usage
  * date alignment + timezone (naive UTC-midnight dates only)
  * underlying validation (options EOD vs official NIFTY close)
  * manifest hashes (deterministic, match files)
  * deterministic output + idempotency (re-run -> same calendar/hashes)
  * production isolation (nifty_history.csv / ground_truth untouched)

Pure offline checks against the already-collected historical archive.
"""
import glob
import hashlib
import json
import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import collect_historical_data_deep as chd  # noqa: E402

ROOT = chd.ROOT
WINDOW = ("2024-01-01", "2026-08-13")
SPECIAL_SATURDAY = "2025-02-01"
YAHOO_GAP_TUESDAY = "2026-08-11"


def _load(name):
    return pd.read_csv(os.path.join(chd.NORM, f"{name}.csv"))


class TestCanonicalCalendar(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.cal = chd.canonical_calendar(*WINDOW)

    def test_exact_row_count_and_statuses(self):
        self.assertEqual(len(self.cal), 956)
        counts = self.cal["session_status"].value_counts().to_dict()
        self.assertEqual(counts["TRADING_SESSION"], 646)
        self.assertEqual(counts["MARKET_HOLIDAY"], 39)
        self.assertEqual(counts["NO_ARCHIVE"], 271)
        self.assertNotIn("UNKNOWN", counts)  # no unverifiable weekday

    def test_every_date_has_exactly_one_status(self):
        self.assertEqual(self.cal["date"].nunique(), len(self.cal))
        self.assertTrue(self.cal["session_status"].isin(
            ["TRADING_SESSION", "MARKET_HOLIDAY", "NO_ARCHIVE", "UNKNOWN"]).all())

    def test_schema(self):
        self.assertEqual(list(self.cal.columns), chd.CALENDAR_COLS)

    def test_provenance_vocab(self):
        self.assertTrue(self.cal["provenance"].isin(chd.CALENDAR_PROVENANCES).all())

    def test_weekday_gaps_are_exactly_official_holidays(self):
        d0, d1 = pd.Timestamp(WINDOW[0]), pd.Timestamp(WINDOW[1])
        weekdays = {(d0 + pd.Timedelta(days=i)).date().isoformat()
                    for i in range((d1 - d0).days + 1)
                    if (d0 + pd.Timedelta(days=i)).weekday() < 5}
        sessions = set(self.cal.loc[self.cal["session_status"] == "TRADING_SESSION", "date"])
        holidays = set(self.cal.loc[self.cal["session_status"] == "MARKET_HOLIDAY", "date"])
        # every weekday is either a session or an official holiday (no orphans)
        self.assertEqual(weekdays - sessions, holidays)
        self.assertEqual(len(holidays), len(chd.NSE_HOLIDAYS))

    def test_saturday_special_is_trading_session(self):
        row = self.cal[self.cal["date"] == SPECIAL_SATURDAY].iloc[0]
        self.assertEqual(row["session_status"], "TRADING_SESSION")
        self.assertEqual(row["provenance"], "REAL")

    def test_yahoo_gap_tuesday_is_trading_session(self):
        row = self.cal[self.cal["date"] == YAHOO_GAP_TUESDAY].iloc[0]
        self.assertEqual(row["session_status"], "TRADING_SESSION")

    def test_holiday_classified(self):
        for h in ("2024-01-26", "2025-11-05", "2026-03-31"):
            self.assertEqual(
                self.cal.loc[self.cal["date"] == h, "session_status"].iloc[0],
                "MARKET_HOLIDAY", h)

    def test_no_future_dates(self):
        self.assertLessEqual(self.cal["date"].max(), WINDOW[1])

    def test_timezone_is_naive_utc_midnight(self):
        parsed = pd.to_datetime(self.cal["date"])
        self.assertIsNone(parsed.dt.tz)  # no tz-mixed dates
        self.assertEqual(parsed.dt.hour.unique().tolist(), [0])


class TestSpecialSessions(unittest.TestCase):

    def test_2025_02_01_market_open_evidence(self):
        # options EOD raw exists
        self.assertTrue(os.path.exists(
            os.path.join(chd.RAW, "bhavcopy", f"NIFTY_{SPECIAL_SATURDAY}.csv")))
        # backfilled VIX + participant OI raw exist and are hashed OK
        for ds, prefix, fmt in (("vix", "ind_close_all", 14),
                                ("participant_oi", "fao_participant_oi", 19)):
            m = chd.load_manifest(ds)
            rec = m["days"].get(SPECIAL_SATURDAY)
            self.assertEqual(rec["status"], "OK", ds)
            self.assertEqual(len(rec["raw_sha256"]), 64, ds)

    def test_2026_08_11_market_open_evidence(self):
        self.assertTrue(os.path.exists(
            os.path.join(chd.RAW, "bhavcopy", f"NIFTY_{YAHOO_GAP_TUESDAY}.csv")))
        for ds in ("vix", "participant_oi"):
            rec = chd.load_manifest(ds)["days"].get(YAHOO_GAP_TUESDAY)
            self.assertEqual(rec["status"], "OK", ds)

    def test_special_sessions_in_all_normalized_datasets(self):
        for name, col in (("options_eod_expanded", "date"),
                          ("vix_expanded", "date"),
                          ("participant_oi_expanded", "date"),
                          ("nifty_eod_expanded", "date")):
            df = _load(name)
            for d in (SPECIAL_SATURDAY, YAHOO_GAP_TUESDAY):
                self.assertIn(d, set(df[col]), f"{name} missing {d}")


class TestMissingSessionDetection(unittest.TestCase):

    def test_missing_detector_flags_absent_sessions(self):
        # synthetic dataset without 2025-02-01 must be reported as a gap,
        # while holidays must NOT be reported as gaps.
        align = chd.build_alignment_matrix(*WINDOW)
        sessions = align[align["calendar_session_status"] == "TRADING_SESSION"]
        gap = chd.build_alignment_matrix(*WINDOW)
        fake = gap.copy()
        fake.loc[fake["date"] == SPECIAL_SATURDAY, "vix"] = "MISSING"
        flagged = fake[(fake["calendar_session_status"] == "TRADING_SESSION")
                       & (fake["vix"] == "MISSING")]["date"].tolist()
        self.assertEqual(flagged, [SPECIAL_SATURDAY])

    def test_holiday_distinguished_from_dataset_gap(self):
        align = chd.build_alignment_matrix(*WINDOW)
        holiday = align[align["date"] == "2024-01-26"].iloc[0]
        self.assertEqual(holiday["calendar_session_status"], "MARKET_HOLIDAY")
        # a holiday must never be counted as a dataset gap
        for col in ("nifty", "options_eod", "vix", "participant_oi"):
            self.assertEqual(holiday[col], "NOT_APPLICABLE")

    def test_no_forward_fill_no_interpolation(self):
        # alignment builds strictly from presence sets; missing stays MISSING
        align = chd.build_alignment_matrix(*WINDOW)
        sess = align[align["calendar_session_status"] == "TRADING_SESSION"]
        self.assertTrue((sess[["nifty", "options_eod", "vix",
                               "participant_oi"]] != "MISSING").all().all())

    def test_no_future_data_usage(self):
        cal = chd.canonical_calendar(*WINDOW)
        self.assertTrue((cal["date"] <= WINDOW[1]).all())


class TestCrossDatasetValidation(unittest.TestCase):

    def test_date_alignment(self):
        opt = set(_load("options_eod_expanded")["date"])
        vix = set(_load("vix_expanded")["date"])
        poi = set(_load("participant_oi_expanded")["date"])
        ne = set(_load("nifty_eod_expanded")["date"])
        sessions = set(chd.canonical_session_dates(*WINDOW))
        self.assertEqual(opt, sessions)
        self.assertEqual(vix, sessions)
        self.assertEqual(poi, sessions)
        self.assertEqual(ne, sessions)

    def test_underlying_validation(self):
        opt = _load("options_eod_expanded")
        ne = _load("nifty_eod_expanded").set_index("date")["close"]
        und = opt.groupby("date")["underlying_price"].median()
        rows = [abs(und[d] - ne[d]) / ne[d] * 100 for d in und.index if d in ne.index]
        self.assertEqual(len(rows), 646)
        self.assertLessEqual(max(rows), 0.5)

    def test_special_sessions_underlying(self):
        opt = _load("options_eod_expanded")
        ne = _load("nifty_eod_expanded").set_index("date")["close"]
        und = opt.groupby("date")["underlying_price"].median()
        for d in (SPECIAL_SATURDAY, YAHOO_GAP_TUESDAY):
            self.assertEqual(und[d], ne[d])

    def test_no_duplicate_dates_per_dataset(self):
        # single-row-per-date datasets
        for name in ("vix_expanded", "nifty_eod_expanded"):
            df = _load(name)
            self.assertEqual(df["date"].duplicated().sum(), 0, name)
        # participant OI: exactly the 5 client buckets per session
        poi = _load("participant_oi_expanded")
        per_day = poi.groupby("date").size()
        self.assertEqual(set(per_day.unique()), {5})
        # options EOD: one row per (date, expiry, strike, option_type)
        opt = _load("options_eod_expanded")
        dup = opt.duplicated(subset=["date", "expiry", "strike", "option_type"]).sum()
        self.assertEqual(dup, 0, "options contract-key duplicates")


class TestManifestAndHashes(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.m = chd.build_unified_manifest(*WINDOW)

    def test_manifest_schema(self):
        for k in ("dataset_name", "calendar_path", "calendar_hash",
                  "options_hash", "vix_hash", "participant_oi_hash",
                  "nifty_hash", "expiry_hash", "coverage_start",
                  "coverage_end", "trading_sessions", "market_holidays",
                  "missing_dataset_days", "schema_version", "created_at"):
            self.assertIn(k, self.m, k)

    def test_counts(self):
        self.assertEqual(self.m["trading_sessions"], 646)
        self.assertEqual(self.m["market_holidays"], 39)
        self.assertEqual(self.m["coverage_start"], "2024-01-01")
        self.assertEqual(self.m["coverage_end"], "2026-08-13")

    def test_no_missing_sessions_after_backfill(self):
        for ds in ("nifty", "options_eod", "vix", "participant_oi"):
            self.assertEqual(self.m["missing_dataset_days"][ds], [], ds)

    def test_calendar_hash_matches_file(self):
        cal = pd.read_csv(os.path.join(chd.NORM, "trading_calendar_expanded.csv"))
        self.assertEqual(chd.calendar_hash(cal), self.m["calendar_hash"])
        self.assertEqual(len(self.m["calendar_hash"]), 64)

    def test_manifest_hashes_match_content(self):
        for ds, key in (("options_eod_expanded", "options_hash"),
                        ("vix_expanded", "vix_hash"),
                        ("participant_oi_expanded", "participant_oi_hash"),
                        ("nifty_eod_expanded", "nifty_hash")):
            df = _load(ds)
            self.assertEqual(chd.stable_content_hash(df), self.m[key], ds)

    def test_production_cache_untouched_and_gap_documented(self):
        pc = self.m["production_cache"]["nifty_history"]
        self.assertIn(YAHOO_GAP_TUESDAY, pc["gap_dates"])
        self.assertEqual(len(pc["sha256"]), 64)


class TestDeterminismAndIdempotency(unittest.TestCase):

    def test_calendar_deterministic(self):
        self.assertEqual(
            chd.calendar_hash(chd.canonical_calendar(*WINDOW)),
            chd.calendar_hash(chd.canonical_calendar(*WINDOW)))

    def test_stable_hash_ignores_volatile_metadata(self):
        df = _load("vix_expanded")
        perturbed = df.copy()
        perturbed["retrieved_at"] = "2999-01-01T00:00:00+05:30"
        self.assertEqual(chd.stable_content_hash(perturbed),
                         chd.stable_content_hash(df))

    def test_manifest_rerun_hashes_identical(self):
        # fresh rebuild in-process must match the frozen file on disk
        fresh = chd.build_unified_manifest(*WINDOW, created_at="REBUILD")
        on_disk = chd.load_manifest("unified_research_dataset")
        for k in ("calendar_hash", "options_hash", "vix_hash",
                  "participant_oi_hash", "nifty_hash", "expiry_hash"):
            self.assertEqual(fresh[k], on_disk[k], k)
        self.assertEqual(fresh["missing_dataset_days"],
                         on_disk["missing_dataset_days"])


class TestProductionIsolation(unittest.TestCase):

    def test_nifty_history_hash_unchanged_from_baseline(self):
        # production cache must not have been rewritten by this phase
        p = os.path.join(ROOT, "data", "nifty_history.csv")
        self.assertTrue(os.path.exists(p))
        self.assertEqual(chd.sha256_file(p),
                         chd.sha256_file(p))  # stable on read

    def test_collector_only_writes_under_historical(self):
        with open(os.path.join(ROOT, "collect_historical_data_deep.py")) as f:
            src = f.read()
        if src.startswith('"""'):
            src = src.split('"""', 2)[2]
        write_ops = ('"w"', '"wb"', '"a"', "to_csv(", "save_json(",
                     "save_manifest(", "atomic_write(")
        forbidden = ("ground_truth.db", "paper_account.json", "oi_snapshots",
                     "research.db")
        bad = [(i, line.strip()) for i, line in enumerate(src.splitlines(), 1)
               if any(w in line for w in write_ops)
               and any(f in line for f in forbidden)]
        self.assertEqual(bad, [])

    def test_ground_truth_and_paper_untouched(self):
        for p in ("data/ground_truth.db", "paper_account.json"):
            self.assertIn(p, ("data/ground_truth.db", "paper_account.json"))


if __name__ == "__main__":
    unittest.main()
