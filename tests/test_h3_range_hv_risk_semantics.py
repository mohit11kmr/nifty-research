"""Phase H3 - RANGE-HV Iron Condor risk/contract-semantics/measurement
integrity + 646-session unified replay tests (MEASUREMENT ONLY).

Verifies the corrected contract semantics (entry_premium mislabel bug,
negative max-loss artifact), the risk-model mismatch (1% declared vs
6.09-8.45% measured), the max-loss matrix, the 646-session unified replay
(6 H2 trades reproduce identically; 2 regime-flip trades are measurement
artifacts), regime-boundary sensitivity, OOS verdict, determinism and
production isolation.

Run: .venv/bin/python -m unittest tests.test_h3_range_hv_risk_semantics -v
"""
import datetime as dt
import builtins
import json
import os
import unittest
from unittest import mock

import phase_h3_risk_semantics as H3
import strategy_registry as SR

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_HASH = "56ba02752efc4650efe1d8c88165f3396e3ae10aaa15519d9b13e33a4e0d1adb"

TRUE_CREDITS = [68.8, 37.3, 45.5, 51.7, 39.55, 42.45]
TRUE_RISK_PCT = [6.09, 8.45, 7.84, 7.37, 8.28, 8.07]
MISLABELED_DATES = ["2026-03-04", "2026-04-21"]

_CACHE = {}


def _pipeline():
    """One shared heavy computation for the whole suite (unified dataset load,
    snaps build, measurement layer, replay, classification, sensitivity)."""
    if _CACHE:
        return _CACHE
    baseline = H3.h2_baseline(use_cache=True, recompute=False)
    nifty, vix, opt = H3.load_unified()
    snaps = H3.build_unified_snaps(opt)
    recs = {d.date().isoformat(): H3.measure_day(d, nifty)
            for d in nifty["date"]}
    trades, rows, res_days = H3.unified_replay(nifty, snaps, recs)
    classes = H3.classify_sessions(nifty, recs)
    cmp = H3.compare_h2_h3(baseline["trades"], rows)
    audit = H3.contract_audit(baseline, snaps, nifty)
    sens = H3.regime_sensitivity(nifty, recs)
    repro = H3.replay_repro(nifty, snaps, recs)
    oos = H3.oos_split_with_verdict(rows)
    _CACHE.update({
        "baseline": baseline, "nifty": nifty, "vix": vix, "snaps": snaps,
        "recs": recs, "rows": rows, "classes": classes, "cmp": cmp,
        "audit": audit, "sens": sens, "repro": repro, "oos": oos,
    })
    return _CACHE


class TestH3FreezeAndIdentity(unittest.TestCase):
    def test_spec_hash_matches_h2(self):
        self.assertEqual(SR.default_registry().spec_hash(H3.SPEC_ID), SPEC_HASH)

    def test_unified_manifest_integrity(self):
        with open(H3.UNIFIED_MANIFEST) as fh:
            m = json.load(fh)
        self.assertEqual(m["trading_sessions"], 646)
        self.assertEqual(m["calendar_hash"],
                         "54965462e130df5491c919bc53d9bac681f3f88b711a0abdfd7da8084a593dcf")
        self.assertEqual(m["missing_dataset_days"],
                         {"nifty": [], "options_eod": [], "participant_oi": [],
                          "vix": []})

    def test_freeze_inputs(self):
        f = H3.freeze_inputs()
        self.assertTrue(f["strategy"]["spec_hash_match"])
        self.assertIsNotNone(f["git_commit"])


class TestH3ContractAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = _pipeline()
        cls.audit = p["audit"]
        cls.baseline = p["baseline"]

    def test_six_trades(self):
        self.assertEqual(len(self.audit), 6)

    def test_true_credits_are_all_below_wing_width(self):
        for a in self.audit:
            self.assertLess(a["entry_credit_true"], 150.0,
                            f"{a['entry_date']} credit must stay below 150-pt wing")
        self.assertEqual([a["entry_credit_true"] for a in self.audit], TRUE_CREDITS)

    def test_entry_premium_mislabel_on_grade_a_days(self):
        mislabeled = [a["entry_date"] for a in self.audit
                      if not a["premium_is_condor_credit"]]
        self.assertEqual(mislabeled, MISLABELED_DATES)
        for a in self.audit:
            if a["entry_date"] in MISLABELED_DATES:
                self.assertGreater(a["entry_premium_h2_reported"],
                                   a["entry_credit_true"])

    def test_negative_max_loss_is_measurement_artifact(self):
        neg = [a["entry_date"] for a in self.audit
               if a["engine_max_loss_share"] is not None
               and a["engine_max_loss_share"] < 0]
        self.assertEqual(neg, MISLABELED_DATES)
        for a in self.audit:
            self.assertGreater(a["true_max_loss_share"], 0,
                               f"{a['entry_date']} corrected max loss must be positive")

    def test_risk_model_mismatch(self):
        pcts = [a["true_risk_pct_of_capital"] for a in self.audit]
        self.assertEqual(pcts, TRUE_RISK_PCT)
        for p in pcts:
            self.assertGreater(p, 1.0)
        self.assertEqual(min(pcts), 6.09)
        self.assertEqual(max(pcts), 8.45)

    def test_baseline_net_still_6248(self):
        self.assertEqual(self.baseline["trade_count"], 6)
        self.assertEqual(self.baseline["profit_concentration"]["total"], 6248.25)


class TestH3MaxLossMatrix(unittest.TestCase):
    def test_negative_artifact_when_credit_gt_width(self):
        m_ = {r["case"]: r for r in H3.max_loss_matrix()}
        self.assertTrue(m_["sym_width_credit_above_width"]["engine_negative_artifact"])
        self.assertEqual(m_["sym_width_credit_above_width"]["engine_max_loss_share"], -10.0)

    def test_unequal_wings_understate_risk(self):
        m_ = {r["case"]: r for r in H3.max_loss_matrix()}
        row = m_["unequal_wings_put_wider"]
        self.assertEqual(row["true_max_loss_share"], 210.0)
        self.assertEqual(row["engine_max_loss_share"], 110.0)
        self.assertEqual(row["engine_understates_by"], -100.0)

    def test_symmetric_cases_agree(self):
        m_ = {r["case"]: r for r in H3.max_loss_matrix()}
        for case in ("sym_width_credit_below_width", "wide_wings_both_sides"):
            self.assertEqual(m_[case]["engine_understates_by"], 0.0)


class TestH3UnifiedReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = _pipeline()
        cls.nifty = p["nifty"]
        cls.snaps = p["snaps"]
        cls.recs = p["recs"]
        cls.rows = p["rows"]
        cls.classes = p["classes"]
        cls.cmp = p["cmp"]
        cls.sens = p["sens"]
        cls.repro = p["repro"]

    def test_646_sessions_classified(self):
        self.assertEqual(len(self.classes), 646)
        from collections import Counter
        counts = dict(Counter(c["status"] for c in self.classes))
        self.assertEqual(counts["EXPIRY_DATA_LIMITATION"], 37)
        self.assertEqual(counts["RESEARCHABLE"], 22)

    def test_extra_trades_are_regime_flip_artifacts(self):
        entries = [t["entry_date"] for t in self.rows]
        self.assertEqual(len(entries), 8)
        self.assertEqual(entries[-2:], ["2026-05-15", "2026-05-19"])
        flips = {f["date"]: f for f in self.sens["flips"]}
        self.assertEqual(self.sens["flip_count"], 39)
        for extra in ("2026-05-15", "2026-05-19"):
            self.assertIn(extra, flips)
            self.assertEqual(flips[extra]["unified_regime"], "RANGE_HV")
            self.assertEqual(flips[extra]["frozen_depth_regime"], "RANGE_LV")

    def test_h2_six_trades_reproduce_identically(self):
        self.assertEqual(self.cmp["matched_trades"], 6)
        self.assertEqual(self.cmp["pnl_diffs"], [])
        self.assertEqual([t["entry"] for t in self.cmp["only_in_h3"]],
                         ["2026-05-15", "2026-05-19"])

    def test_replay_pnl_matches_h2_for_overlap(self):
        h2map = {t["entry_date"]: t["net_pnl"]
                 for t in _pipeline()["baseline"]["trades"]}
        for row in self.rows:
            if row["entry_date"] in h2map:
                self.assertEqual(row["net_pnl"], h2map[row["entry_date"]])

    def test_reproducibility(self):
        self.assertTrue(self.repro["identical"])
        self.assertEqual(self.repro["researchable_days"], 246)

    def test_oos_insufficient(self):
        oos = _pipeline()["oos"]
        self.assertEqual(oos["verdict"], "OOS_INSUFFICIENT")
        self.assertLess(oos["out_of_sample"]["trades"], 20)


class TestH3ProductionIsolation(unittest.TestCase):
    def test_measurement_never_writes_production(self):
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
            f = H3.freeze_inputs()
        self.assertEqual(written, [])
        self.assertTrue(f["strategy"]["spec_hash_match"])

    def test_sentinel_files_unchanged_by_full_module(self):
        before = H3.sentinel_mtimes()
        nifty, vix, opt = H3.load_unified()
        snaps = H3.build_unified_snaps(opt)
        recs = {d.date().isoformat(): H3.measure_day(d, nifty)
                for d in nifty["date"]}
        H3.unified_replay(nifty, snaps, recs)
        self.assertEqual(before, H3.sentinel_mtimes())
if __name__ == "__main__":
    unittest.main(verbosity=2)
