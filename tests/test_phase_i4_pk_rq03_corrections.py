"""Phase I.4 - PK-RQ-03 correction + controlled revalidation tests.

Covers the documented Phase I.3 defect corrections (Claude Sonnet 4.6 audit
F1-F7) for the frozen PK-RQ-03 (GAP_BOUNCE) hypothesis:

  F2  historical market-lot service (point-in-time contract lot, no "75" fallback)
  F1  stop-loss now simulated (EOD stop, stop -> horizon -> expiry precedence)
  F5  accounting invariant: net == gross - fees - slippage, trade + aggregate
  F3/F4/F6/F7 documented classification / descriptive-only regimes / expiry
      and forward-window semantics asserted on the replayed output

Run: .venv/bin/python -m unittest tests.test_phase_i4_pk_rq03_corrections -v
"""
import json
import os
import unittest

import research_runner as RUN
import research_dataset as RD
import research_feature_engine as FE
import research_regime_discovery as RR
import lot_size as LS

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_PATH = os.path.join(REPO, "results", "phase_i3", "ai_proposals", "PK-RQ-03.yaml")
REPORT_PATH = os.path.join(REPO, "results", "phase_i4", "report.json")
DIFF_PATH = os.path.join(REPO, "results", "phase_i4", "trade_diff.csv")

# Regression pin for the corrected replay (frozen hypothesis + corrected runner).
CORRECTED_HASH = "ee3b44e8959dc38292b42342067dcafaf037f817e80fe255ea871a106d1b5587"
ORIGINAL_HASH = "f11b794e902e464374b99578ab53e1158b2e9eb972139d7f93ad74cfa17605e0"

_FIXTURES = None
_SPEC = None


def _spec():
    global _SPEC
    if _SPEC is None:
        import yaml
        with open(SPEC_PATH) as fh:
            doc = yaml.safe_load(fh)
        doc["proposal"]["proposal_id"] = "PK-RQ-03"
        doc["proposal"]["author_type"] = "AI"
        doc["proposal"]["author_model"] = "opencode/big-pickle"
        _SPEC = doc
    return _SPEC


def _fixtures():
    """Lazy singleton: context + panel + meta + retrospective regime labels."""
    global _FIXTURES
    if _FIXTURES is None:
        ctx = RD.load_context()
        panel, meta = FE.build_panel(ctx)
        regime_report, _ = RR.discover_regimes(panel, meta)
        _FIXTURES = (ctx, panel, regime_report["assignments"])
    return _FIXTURES


class LotSizeServiceTest(unittest.TestCase):
    """F2: point-in-time market lot from the frozen bhavcopy."""

    def test_no_current_lot_constant_anywhere(self):
        with open(os.path.join(REPO, "lot_size.py")) as fh:
            src = fh.read()
        self.assertNotIn("fallback", src.lower())
        for token in ("lot = 75", "lot_size = 75", "== 75", "return 75"):
            self.assertNotIn(token, src)

    def test_get_lot_size_boundaries_2024_first_half(self):
        self.assertEqual(LS.get_lot_size("2024-04-25"), 50)
        self.assertEqual(LS.get_lot_size("2024-04-26"), 25)

    def test_get_lot_size_boundaries_2024_second_half(self):
        # 2024-12-25 is a market holiday (no rows); last lot-25 session is
        # 2024-12-24, first lot-75 session is 2024-12-26.
        self.assertEqual(LS.get_lot_size("2024-12-24"), 25)
        self.assertEqual(LS.get_lot_size("2024-12-26"), 75)

    def test_get_lot_size_boundaries_2025_2026(self):
        self.assertEqual(LS.get_lot_size("2025-12-29"), 75)
        self.assertEqual(LS.get_lot_size("2025-12-30"), 65)

    def test_get_lot_size_point_in_time_outstanding_contract(self):
        # On 2025-01-27 the near-expiry (2025-01-30) contract carries lot 25;
        # newer 2025-02-06 expiry already carries 75. PIT = entry contract lot.
        self.assertEqual(LS.get_lot_size("2025-01-27"), 25)
        self.assertEqual(LS.contract_lot("2025-01-27", "2025-02-06", 23500, "CE"), 75)

    def test_contract_lot_exact_row_matches_frozen_data(self):
        import pandas as pd
        df = pd.read_csv(
            os.path.join(REPO, "data", "historical", "normalized",
                         "options_eod_expanded.csv"),
            usecols=["date", "expiry", "strike", "option_type", "lot_size"])
        for d in ("2024-04-25", "2024-06-24", "2025-01-27", "2026-03-04"):
            sub = df[(df["date"] == d) & (df["option_type"] == "CE")]
            if not len(sub):
                continue
            r = sub.iloc[0]
            self.assertEqual(
                LS.contract_lot(d, r["expiry"], r["strike"], "CE"), int(r["lot_size"]))

    def test_contract_lot_missing_row_returns_none(self):
        self.assertIsNone(LS.contract_lot("2025-01-27", "2025-01-30", 99999, "CE"))
        self.assertIsNone(LS.get_lot_size("1990-01-01"))


class AccountingInvariantTest(unittest.TestCase):
    """F5: the trade ledger is authoritative; net == gross - fees - slippage."""

    def _ledger(self, rows):
        trades = []
        for i, (g, f, s) in enumerate(rows):
            trades.append({"net_pnl": round(g - f - s, 2), "gross": round(g, 2),
                           "fees": round(f, 2), "slippage": round(s, 2),
                           "days_held": 3})
        return trades

    def test_compute_metrics_aggregate_identity(self):
        trades = self._ledger([(1000.0, 40.0, 15.0), (-500.0, 40.0, 7.5)])
        m = RUN.compute_metrics(trades, 600)
        self.assertEqual(m["net_pnl"], 1000 - 500 - 80 - 22.5)
        self.assertEqual(m["fees"], 80.0)
        self.assertEqual(m["slippage"], 22.5)
        self.assertEqual(m["gross"], 500.0)
        self.assertAlmostEqual(m["net_pnl"], m["gross"] - m["fees"] - m["slippage"], 2)

    def test_trade_level_identity_in_ledger(self):
        trades = self._ledger([(1234.56, 40.0, 18.9), (-321.1, 40.0, 5.0)])
        for t in trades:
            self.assertAlmostEqual(t["net_pnl"],
                                   round(t["gross"] - t["fees"] - t["slippage"], 2), 2)

    def test_corrected_ledger_identity_holds(self):
        if not os.path.exists(REPORT_PATH):
            self.skipTest("results/phase_i4/report.json not generated")
        with open(REPORT_PATH) as fh:
            r = json.load(fh)
        self.assertTrue(r["accounting"]["trade_level_net_equals_gross_fees_slippage"])
        self.assertTrue(r["accounting"]["aggregate_check"])
        self.assertEqual(r["accounting"]["aggregate"]["identity"],
                         "net == gross - fees - slippage")


class CorrectedReplayTest(unittest.TestCase):
    """Controlled replay of the frozen PK-RQ-03 hypothesis on the corrected
    runner (F1 stop simulated, F2 contract lot, F3/F4/F5/F6/F7 semantics)."""

    @classmethod
    def setUpClass(cls):
        ctx, panel, labels = _fixtures()
        doc = _spec()
        cls.panel = panel
        cls.run_a = RUN.research(doc, panel, ctx, labels)
        cls.run_b = RUN.research(doc, panel, ctx, labels)
    def test_hypothesis_preserved_verbatim(self):
        from ai_phase_i4_revalidation import verify_hypothesis
        self.assertEqual(verify_hypothesis(_spec()), [])

    def test_determinism_same_hash(self):
        self.assertEqual(self.run_a["result_hash"], self.run_b["result_hash"])
        self.assertEqual(self.run_a["trades"], self.run_b["trades"])
        self.assertEqual(self.run_a["metrics"], self.run_b["metrics"])

    def test_result_hash_matches_frozen_replay(self):
        self.assertEqual(self.run_a["result_hash"], CORRECTED_HASH)

    def test_different_from_original_buggy_result(self):
        self.assertNotEqual(self.run_a["result_hash"], ORIGINAL_HASH)

    def test_stop_loss_now_simulated(self):
        reasons = [t["reason"] for t in self.run_a["trades"]]
        self.assertIn("EXIT_STOP", reasons)
        for t in self.run_a["trades"]:
            if t["reason"] == "EXIT_STOP":
                self.assertEqual(t["stop_level"], round(0.5 * t["entry_mark"], 2))
                self.assertLessEqual(t["exit_mark"], t["stop_level"] + 0.01)
            else:
                self.assertEqual(t["reason"], "EXIT_EXPIRY")

    def test_lot_size_correction_applied(self):
        lots = sorted(set(t["lot"] for t in self.run_a["trades"]))
        self.assertNotEqual(lots, [75])
        self.assertTrue(set(lots).issubset({25, 50, 65, 75}))
        self.assertLessEqual(len(lots), 4)

    def test_entry_lot_is_point_in_time_contract_lot(self):
        for t in self.run_a["trades"]:
            near = self.panel.loc[t["entry_date"], "near_expiry"]
            expected = LS.contract_lot(t["entry_date"], near, t["strike"], "CE")
            self.assertEqual(t["lot"], expected)


class PhaseArtifactTest(unittest.TestCase):
    """Gates on the controlled-replay artifacts (results/phase_i4/)."""

    def test_report_exists(self):
        self.assertTrue(os.path.exists(REPORT_PATH), "run ai_phase_i4_revalidation.py")

    def test_report_reproducibility_and_isolation(self):
        with open(REPORT_PATH) as fh:
            r = json.load(fh)
        self.assertTrue(r["reproducibility"]["same_trades"])
        self.assertTrue(r["reproducibility"]["same_metrics"])
        self.assertTrue(r["reproducibility"]["same_hash"])
        self.assertTrue(r["production_isolation"]["protected_untouched"])
        self.assertTrue(r["hypothesis_preserved"])

    def test_trade_diff_classification_complete(self):
        import pandas as pd
        df = pd.read_csv(DIFF_PATH)
        self.assertEqual(len(df), 43)
        counts = df["reason_code"].value_counts().to_dict()
        self.assertEqual(counts.get("STOP_LOSS_CORRECTION"), 22)
        self.assertEqual(counts.get("LOT_SIZE_CORRECTION"), 13)
        self.assertEqual(counts.get("REASON_LABEL_ONLY"), 8)
        self.assertTrue((df["reason_code"] != "REPORTING_ONLY").all())


if __name__ == "__main__":
    unittest.main()
