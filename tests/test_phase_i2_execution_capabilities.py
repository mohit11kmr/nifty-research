"""Phase I.2 - Generic Strategy Execution Layer tests (unittest, repo convention).

covers: capability matrix (spec section 7), granularity gate (14/15),
vacuous strike-typed data gate, execution-family resolution (credit/debit,
asymmetric condor), the six frozen I.1 proposals' classification + compile
gates, unregistered-family rejection, and slow regression proofs:
  - engine path unchanged (current_control_v1 still 48 trades / 1906.43 / 1.011)
  - generic replay determinism (result_hash stable across reruns)
  - frozen Phase I.1 artifacts remain untouched by the I.2 replay

Run: .venv/bin/python -m unittest tests.test_phase_i2_execution_capabilities -v
"""
import json
import os
import types
import unittest

import strategy_proposal_compiler as PC
import strategy_proposal_validator as PV
import strategy_schema as S
import ai_strategy_research as AR
import strategy_execution_capabilities as C
import strategy_execution_registry as R
import strategy_execution as SE

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I1_PROPOSAL_DIR = os.path.join(REPO, "strategy_proposals", "phase_i1", "proposals")
I1_RESULT_DIR = os.path.join(REPO, "results", "phase_i1")

SIX = ("phase_i1_big_pickle_p1", "phase_i1_big_pickle_p2", "phase_i1_big_pickle_p3",
       "phase_i1_deepseek_p1", "phase_i1_deepseek_p2", "phase_i1_deepseek_p3")

EXPECTED_FAMILIES = {
    "phase_i1_big_pickle_p1": ("OPTION_BUY", None),
    "phase_i1_big_pickle_p2": ("CALL_CREDIT_SPREAD", None),
    "phase_i1_big_pickle_p3": (None, C.POSITION_CONSTRUCTION_UNSUPPORTED),
    "phase_i1_deepseek_p1": ("OPTION_BUY", None),
    "phase_i1_deepseek_p2": ("IRON_CONDOR", None),
    "phase_i1_deepseek_p3": (None, C.POSITION_CONSTRUCTION_UNSUPPORTED),
}


def _compile(pid):
    import yaml
    with open(os.path.join(I1_PROPOSAL_DIR, f"{pid}.yaml")) as fh:
        return PC.compile_proposal(yaml.safe_load(fh))


def _spec(instrument_type, mode, sides, risk_note, side_params=None, sid="synth_v1"):
    spec = {
        "strategy": {"id": sid, "version": "v1", "name": "synth",
                     "classification": "DEFINED_RISK"},
        "description": "EOD daily strategy",
        "market": {"underlying": "NIFTY", "asset_class": "INDEX_OPTIONS",
                   "granularity": "EOD"},
        "instrument": {"type": instrument_type, "option_side": list(sides)},
        "direction": {"mode": mode},
        "entry": {"conditions": {"all": [], "any": []}},
        "exit": {"stop": "ATR", "target": "STRUCTURAL", "expiry": "WEEKLY",
                 "allowed_reasons": ["TARGET", "STOP", "EXPIRY"]},
        "risk": {"note": risk_note,
                 "position_size": {"lots": 1, "lot_size": 75},
                 "capital_per_trade_pct": 1.0, "max_loss_capital_pct": 3.0},
    }
    if side_params:
        spec["strike_selection"] = {"params": side_params}
    return spec


class _FakeCompilation:
    def __init__(self, spec):
        self.strategy_id = (spec.get("strategy") or {}).get("id")
        self.spec_hash = "fake"
        self.compiled = types.SimpleNamespace(spec=spec)


class TestCapabilityMatrix(unittest.TestCase):
    def test_only_three_registered_families(self):
        self.assertEqual(C.list_supported_families(),
                         ["CALL_CREDIT_SPREAD", "IRON_CONDOR", "OPTION_BUY"])

    def test_every_family_is_eod_and_defined_risk(self):
        for fam in C.CAPABILITY_TABLE.values():
            self.assertEqual(fam["min_granularity"], C.EOD)
            self.assertIn("DEFINED", fam["risk_semantics"])
            for key in ("entry_supported", "multi_leg", "risk_supported",
                        "expiry_supported", "stop_supported", "target_supported",
                        "MTM_supported", "cost_model_supported"):
                self.assertIsInstance(fam[key], bool)

    def test_no_claims_without_registered_families(self):
        for fam_id in ("PUT_CREDIT_SPREAD", "BULL_CALL_SPREAD",
                       "BEAR_PUT_SPREAD", "SHORT_STRANGLE", "IRON_BUTTERFLY"):
            self.assertNotIn(fam_id, C.CAPABILITY_TABLE)


class TestGranularityGate(unittest.TestCase):
    def test_intraday_tokens_rejected(self):
        for desc in ("exit on 5-min reversal", "uses 15min chart",
                     "intraday momentum", "tick-by-tick stops",
                     "roll at the 60 minute mark", "daily vs hourly frame"):
            self.assertEqual(C.granularity_gate(desc), C.GRANULARITY_UNSUPPORTED)

    def test_eod_descriptions_pass(self):
        for desc in ("EOD research window", "long-term trend following",
                     "expected move using VIX", "daily close signals",
                     "weekly expiry", None, ""):
            self.assertIsNone(C.granularity_gate(desc))


class TestVacuousStrikeGate(unittest.TestCase):
    def test_sub_1000_strike_typed_comparison_is_vacuous(self):
        cond = {"id": "x", "field": "OI_WALL", "operator": ">", "value": 0.5}
        self.assertEqual(C.vacuous_strike_threshold(cond), "x")
        cond2 = {"id": "y", "field": "MAX_PAIN", "operator": "<", "value": 300}
        self.assertEqual(C.vacuous_strike_threshold(cond2), "y")

    def test_real_strike_levels_pass(self):
        for cond in ({"id": "a", "field": "OI_WALL", "operator": ">",
                      "value": 24500.0},
                     {"id": "b", "field": "MAX_PAIN", "operator": "<",
                      "value": 25000},
                     {"id": "c", "field": "SPOT", "operator": ">", "value": 0.5},
                     {}):
            self.assertIsNone(C.vacuous_strike_threshold(cond))


class TestCoverageGate(unittest.TestCase):
    def test_below_50_pct_flagged(self):
        pct = C.coverage_failed(59, list(range(245)))
        self.assertIsNotNone(pct)
        self.assertLess(pct, C.COVERAGE_MIN_PCT)

    def test_full_coverage_passes(self):
        self.assertIsNone(C.coverage_failed(245, list(range(245))))


class TestFamilyResolution(unittest.TestCase):
    def test_credit_vs_debit_semantics(self):
        self.assertEqual(R._credit_or_debit(
            _spec("DEFINED_RISK_DIRECTIONAL", "DIRECTIONAL", ["CE"],
                  "net credit received on the spread"))[0], R.CREDIT)
        self.assertEqual(R._credit_or_debit(
            _spec("DEFINED_RISK_DIRECTIONAL", "DIRECTIONAL", ["PE"],
                  "net debit paid"))[0], R.DEBIT)
        self.assertEqual(R._credit_or_debit(
            _spec("DEFINED_RISK_DIRECTIONAL", "DIRECTIONAL", ["CE"], "")),
            (None, R.RISK_SEMANTIC_UNDEFINED))

    def test_asymmetric_condor_detection(self):
        self.assertTrue(R._asymmetric_condor(
            _spec("DEFINED_RISK_RANGE", "NEUTRAL", ["CE", "PE"],
                  "note", side_params={"wing_multiplier": 1.5})))
        self.assertTrue(R._asymmetric_condor(
            _spec("DEFINED_RISK_RANGE", "NEUTRAL", ["CE", "PE"],
                  "broken-wing structure")))
        self.assertFalse(R._asymmetric_condor(
            _spec("DEFINED_RISK_RANGE", "NEUTRAL", ["CE", "PE"], "note")))

    def test_resolve_family_for_three_families(self):
        self.assertEqual(
            R.resolve_family(_spec("NAKED_OPTION", "DIRECTIONAL", ["CE"], "note"))[0],
            "OPTION_BUY")
        self.assertEqual(
            R.resolve_family(_spec("DEFINED_RISK_DIRECTIONAL", "DIRECTIONAL",
                                   ["CE"], "net credit received"))[0],
            "CALL_CREDIT_SPREAD")
        self.assertEqual(
            R.resolve_family(_spec("DEFINED_RISK_RANGE", "NEUTRAL",
                                   ["CE", "PE"], "symmetric note"))[0],
            "IRON_CONDOR")

    def test_six_frozen_proposals_classify(self):
        for pid, (fam, code) in EXPECTED_FAMILIES.items():
            comp = _compile(pid)
            family, failure = R.resolve_family(comp.compiled.spec)
            self.assertEqual((family, failure[0] if failure else None),
                             (fam, code), pid)


class TestCompileGates(unittest.TestCase):
    def test_supported_proposals_compile_executor(self):
        for pid in ("phase_i1_big_pickle_p1", "phase_i1_big_pickle_p2",
                    "phase_i1_deepseek_p2"):
            comp = _compile(pid)
            ex = R.default_registry().compile_executor(comp)
            self.assertEqual(ex.family_id, EXPECTED_FAMILIES[pid][0])

    def test_unresolvable_proposals_rejected_with_code(self):
        for pid, code in (("phase_i1_big_pickle_p3", C.POSITION_CONSTRUCTION_UNSUPPORTED),
                          ("phase_i1_deepseek_p1", C.DATA_FIELD_UNSUPPORTED),
                          ("phase_i1_deepseek_p3", C.POSITION_CONSTRUCTION_UNSUPPORTED)):
            comp = _compile(pid)
            with self.assertRaisesRegex(ValueError, "EXECUTION_UNSUPPORTED"):
                try:
                    R.default_registry().compile_executor(comp)
                except ValueError as exc:
                    self.assertIn(code, str(exc), pid)
                    raise

    def test_unregistered_family_rejected(self):
        for sides, note in ((["PE"], "net credit received"),
                            (["CE"], "net debit paid")):
            comp = _FakeCompilation(
                _spec("DEFINED_RISK_DIRECTIONAL", "DIRECTIONAL", sides, note))
            with self.assertRaisesRegex(ValueError, C.FAMILY_NOT_REGISTERED):
                R.default_registry().compile_executor(comp)

    def test_granularity_gate_blocks_compile(self):
        spec = _spec("NAKED_OPTION", "DIRECTIONAL", ["CE"], "note")
        spec["description"] = "scalp on 5-min breakouts"
        with self.assertRaisesRegex(ValueError, C.GRANULARITY_UNSUPPORTED):
            R.default_registry().compile_executor(_FakeCompilation(spec))


class TestFieldResolution(unittest.TestCase):
    def test_condition_literals_evaluated_literally(self):
        """VIX_ZONE != 'RICH' compares rec value 'VIX_RICH' vs literal 'RICH':
        honest literal evaluation (True), documented spec bug, never fudged."""
        spec = _spec("NAKED_OPTION", "DIRECTIONAL", ["CE"], "note")
        spec["entry"] = {"conditions": {"all": [
            {"id": "x", "field": "VIX_ZONE", "operator": "!=", "value": "RICH"}]}}
        ctx = types.SimpleNamespace(ind_row=lambda d: {})
        rec = {"vix_zone": "VIX_RICH"}
        self.assertIs(SE.evaluate_conditions(ctx, spec, rec, None)["allowed"], True)

    def test_missing_field_blocks_entry(self):
        spec = _spec("NAKED_OPTION", "DIRECTIONAL", ["CE"], "note")
        spec["entry"] = {"conditions": {"all": [
            {"id": "x", "field": "FII_SENTIMENT", "operator": "==", "value": "BULLISH"}]}}
        ctx = types.SimpleNamespace(ind_row=lambda d: {})
        rec = {"vix_zone": "VIX_NORMAL"}
        self.assertIs(SE.evaluate_conditions(ctx, spec, rec, None)["allowed"], False)

    def test_unregistered_project_rule_blocks_entry(self):
        spec = _spec("NAKED_OPTION", "DIRECTIONAL", ["CE"], "note")
        spec["entry"] = {"conditions": {"all": [
            {"id": "x", "rule": S.PROJECT_RULE_TOKEN,
             "project_ref": "backtest_frozen.simulate_trade"}]}}
        ctx = types.SimpleNamespace(ind_row=lambda d: {})
        rec = {"spot": 25000.0}
        self.assertIs(SE.evaluate_conditions(ctx, spec, rec, None)["allowed"], False)


class TestFrozenI1ArtifactsUntouched(unittest.TestCase):
    def test_i1_results_never_written_by_i2(self):
        with open(os.path.join(I1_RESULT_DIR, "experiment.json")) as fh:
            payload = json.load(fh)
        records = {r["proposal_id"]: r for r in payload["records"]}
        for pid in SIX:
            self.assertEqual(records[pid]["failure_code"], "EXECUTION_UNSUPPORTED",
                             pid)
            self.assertEqual(records[pid]["backtest_status"], "NOT_RUN", pid)
        i1_files = set(os.listdir(I1_RESULT_DIR))
        self.assertFalse(any(f.endswith(".research.json") for f in i1_files))


class TestSlowFrozenEquivalence(unittest.TestCase):
    """Slow guard: real engines, committed baselines (Phase H numbers).
    Runs the engine control + one generic replay once in setUpClass."""

    @classmethod
    def setUpClass(cls):
        cls.control = AR.BacktestAdapter(
            AR._compiled_control(), data_root=None).run()
        cls.replay = AR.run_research(_compile("phase_i1_deepseek_p2"),
                                     control=False)
        cls.replay2 = AR.run_research(_compile("phase_i1_deepseek_p2"),
                                      control=False)

    def test_engine_path_unchanged_control_restatement(self):
        m = self.control["metrics"]
        self.assertEqual(m["trade_count"], 48)
        self.assertEqual(m["net_pnl"], 1906.43)
        self.assertEqual(m["profit_factor"], 1.011)

    def test_generic_replay_deterministic(self):
        self.assertEqual(self.replay["result_hash"], self.replay2["result_hash"])
        self.assertEqual(self.replay["metrics"]["candidate"], "IRON_CONDOR")
        self.assertEqual(self.replay["metrics"]["trade_count"],
                         self.replay2["metrics"]["trade_count"])
        for row in self.replay["trades"]:
            self.assertIn(row["reason"], ("TARGET", "STOP", "TIME", "EXPIRY", "EOD"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
