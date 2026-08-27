"""Phase I - AI Strategy Research pipeline tests (unittest, repo convention).

covers: proposal schema determinism, validator gate matrix (lookahead /
arbitrary-code / data-gate / risk / execution), compiler contract, registry
provenance + duplicate detection, research output determinism (result_hash
stable across reruns), evaluation vector honesty (NOT_RELIABLE at n<20),
baseline comparison verdicts, and the frozen-equivalence proofs for the two
EXAMPLE_ONLY proposals.

Run: .venv/bin/python -m unittest tests.test_phase_i_research -v
"""
import json
import os
import tempfile
import unittest
from unittest import mock

import strategy_proposal_schema as PS
import strategy_proposal_validator as PV
import strategy_proposal_compiler as PC
import strategy_proposal_registry as SPR
import ai_strategy_research as AR

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROPOSALS = os.path.join(REPO, "strategy_proposals")

P1 = os.path.join(PROPOSALS, "example_ai_proposal_0001.yaml")
P2 = os.path.join(PROPOSALS, "example_ai_proposal_0002.yaml")

PROPOSAL_HASH_1 = "d5a060c59978ed4aaa1d84e081e89e6f682ee3915f6bab350377ac5cbec84e27"
SPEC_HASH_1 = "d8117eed20a7d17fbe32374f5623497ffc68283ae99b8b1a152f87d17b3c5da7"
RESULT_HASH_1 = "0f7665acc54683fc527e0f3f2f1c192e5a9f62fe8c28736e3fe244930a8a00d8"


def _compile(path):
    return PC.compile_file(path)


def _sample_run():
    """Deterministic fake engine run for unit-level tests."""
    rows = [
        {"exit_date": "2025-10-02", "net_pnl": 1462.0, "regime": "RANGE_HV",
         "option_type": "IRON_CONDOR"},
        {"exit_date": "2025-11-20", "net_pnl": -359.0, "regime": "RANGE_HV",
         "option_type": "IRON_CONDOR"},
        {"exit_date": "2026-01-08", "net_pnl": 1820.0, "regime": "RANGE_HV",
         "option_type": "IRON_CONDOR"},
        {"exit_date": "2026-03-12", "net_pnl": 1570.0, "regime": "RANGE_HV",
         "option_type": "IRON_CONDOR"},
    ]
    return {
        "metrics": {"trade_count": 4, "win_count": 3, "loss_count": 1,
                    "win_rate": 75.0, "gross_pnl": 6393.0, "net_pnl": 4493.0,
                    "fees": 1280.0, "slippage": 1620.0, "profit_factor": 8.0,
                    "expectancy": 1123.25, "max_drawdown": -359.0,
                    "max_drawdown_pct": -0.36, "status": "INSUFFICIENT_SAMPLE"},
        "by_regime": {"RANGE_HV": {"trades": 4, "net": 4493.0, "winrate": 75.0}},
        "monthly": {},
        "trades": rows,
        "fingerprints": {"dataset_composite_hash": "x"},
    }


class TestProposalSchemaDeterminism(unittest.TestCase):
    def test_hashes_deterministic_and_key_sensitive(self):
        c1 = _compile(P1)
        c2 = _compile(P1)
        self.assertEqual(c1.proposal_hash, c2.proposal_hash)
        self.assertEqual(c1.spec_hash, c2.spec_hash)
        self.assertEqual(c1.fingerprint, c2.fingerprint)
        self.assertEqual(c1.proposal_hash, PROPOSAL_HASH_1)
        self.assertEqual(c1.spec_hash, SPEC_HASH_1)


class TestValidatorGates(unittest.TestCase):
    def test_example_proposals_valid(self):
        for path in (P1, P2):
            vr = PV.validate_file(path)
            self.assertTrue(vr.valid, vr.report())
            self.assertTrue(vr.warnings)  # PARTIAL expiry coverage is expected

    def test_lookahead_gate_rejects_forbidden_fields(self):
        comp = _compile(P1)
        mut = json.loads(json.dumps(comp.proposal))
        mut["strategy"]["entry"]["conditions"]["all"][0]["next_close"] = 100
        vr = PV.validate_proposal(mut)
        self.assertFalse(vr.valid)
        self.assertIn("lookahead", vr.report().lower())

    def test_arbitrary_code_gate_rejects_dangerous_tokens(self):
        comp = _compile(P1)
        mut = json.loads(json.dumps(comp.proposal))
        mut["proposal"]["hypothesis"] = "run it with subprocess.call"
        vr = PV.validate_proposal(mut)
        self.assertFalse(vr.valid)
        self.assertIn("REJECTED_ARBITRARY_CODE", vr.report())

    def test_missing_required_section_rejected(self):
        comp = _compile(P1)
        mut = json.loads(json.dumps(comp.proposal))
        del mut["strategy"]["risk"]
        vr = PV.validate_proposal(mut)
        self.assertFalse(vr.valid)


class TestRegistry(unittest.TestCase):
    def test_register_persist_review_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = SPR.ProposalRegistry(base_dir=tmp)
            c = _compile(P1)
            rec = reg.register(c, status="DRAFT")
            self.assertEqual(rec["proposal_id"], "example_ai_proposal_0001")
            reg.update(rec["proposal_id"], human_decision="REQUEST_MORE_DATA",
                       status="REVIEW", evidence="BACKTESTED")
            rec = reg.get(rec["proposal_id"])
            self.assertEqual(rec["human_decision"], "REQUEST_MORE_DATA")
            self.assertEqual(rec["evidence"], "BACKTESTED")

    def test_provenance_immutable_on_hash_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = SPR.ProposalRegistry(base_dir=tmp)
            c = _compile(P1)
            reg.register(c)
            c2 = _compile(P1)
            c2.proposal_hash = "deadbeef"  # simulate re-submission drift
            with self.assertRaises(ValueError):
                reg.register(c2)


class TestResearchDeterminism(unittest.TestCase):
    @mock.patch.object(AR, "BacktestAdapter")
    def test_result_hash_stable_across_reruns(self, mock_adapter):
        mock_adapter.return_value.run.return_value = _sample_run()
        comp = _compile(P1)
        with mock.patch.object(AR, "_compiled_control",
                               side_effect=RuntimeError("skip control")):
            out1 = AR.run_research(comp, control=False)
            out2 = AR.run_research(comp, control=False)
        self.assertEqual(out1["result_hash"], out2["result_hash"])
        self.assertEqual(out1["metrics"]["net_pnl"],
                         out2["metrics"]["net_pnl"])


class TestEvaluationVectorHonesty(unittest.TestCase):
    @mock.patch.object(AR, "BacktestAdapter")
    def test_insufficient_sample_never_promoted(self, mock_adapter):
        mock_adapter.return_value.run.return_value = _sample_run()
        comp = _compile(P1)
        with mock.patch.object(AR, "_compiled_control",
                               side_effect=RuntimeError("skip control")):
            out = AR.run_research(comp, control=False)
        v = out["evaluation_vector"]
        self.assertLess(v["sample_size"], 20)
        self.assertEqual(v["stability"]["status"], "INSUFFICIENT_SAMPLE")
        self.assertFalse(v["stability"]["sufficient"])


class TestBaselineComparison(unittest.TestCase):
    def test_verdicts_and_dims(self):
        proposal_run = {
            "metrics": {"trade_count": 6, "net_pnl": 6248.25,
                        "win_rate": 66.7, "fees": 1920.0, "slippage": 2276.15,
                        "profit_factor": 9.693, "expectancy": 1041.38,
                        "max_drawdown": -587.0},
            "trades": [{"exit_date": "2025-10-02", "net_pnl": 1462.0},
                       {"exit_date": "2025-11-20", "net_pnl": -359.0},
                       {"exit_date": "2026-01-08", "net_pnl": 1820.0},
                       {"exit_date": "2026-02-12", "net_pnl": 1570.0},
                       {"exit_date": "2026-04-16", "net_pnl": 820.0},
                       {"exit_date": "2026-06-11", "net_pnl": 935.0}],
        }
        control_run = {
            "metrics": {"trade_count": 48, "net_pnl": 1906.43,
                        "win_rate": 33.3, "fees": 3840.0, "slippage": 10554.82,
                        "profit_factor": 1.011, "expectancy": 39.72,
                        "max_drawdown": -51746.8},
            "trades": [],
        }
        comp = AR.baseline_comparison(proposal_run, control_run)
        self.assertEqual(comp["verdict"], "NOT_RELIABLE")  # n=6 < 20
        self.assertEqual(comp["dimensions"]["net_pnl"]["proposal"], 6248.25)
        self.assertEqual(comp["dimensions"]["profit_factor"]["control"], 1.011)


class TestFrozenEquivalence(unittest.TestCase):
    """Slow guard: real engines, committed baselines (H2/H3 numbers).
    Runs both frozen engines once in setUpClass (repo convention)."""

    @classmethod
    def setUpClass(cls):
        cls.condor = AR.run_research(_compile(P1), control=False)
        cls.control = AR.run_research(_compile(P2), control=False)
        cls.baseline = AR.baseline_comparison(cls.condor, cls.control)

    def test_condor_reproduces_h2(self):
        self.assertEqual(self.condor["metrics"]["trade_count"], 6)
        self.assertEqual(self.condor["metrics"]["net_pnl"], 6248.25)
        self.assertEqual(self.condor["metrics"]["profit_factor"], 9.693)
        self.assertEqual(self.condor["result_hash"], RESULT_HASH_1)
        self.assertEqual(self.baseline["control"], "current_control_v1")

    def test_control_restatement_reproduces_control(self):
        self.assertEqual(self.control["metrics"]["trade_count"], 48)
        self.assertEqual(self.control["metrics"]["net_pnl"], 1906.43)
        self.assertEqual(self.control["metrics"]["profit_factor"], 1.011)

    def test_baseline_verdict_not_reliable_at_n6(self):
        self.assertEqual(self.baseline["verdict"], "NOT_RELIABLE")
        self.assertEqual(self.baseline["dimensions"]["sample_size"]["proposal"], 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
