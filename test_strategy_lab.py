"""Phase H1 v2 - Strategy Lab tests (unittest, matching repo convention).

covers: schema determinism, validator accept/reject, registry, compiler
interface, control equivalence vs committed Phase H results, paper adapter
interface (against a throwaway engine rooted in a temp directory), and
determinism of the whole pipeline.
"""
import datetime as dt
import json
import os
import tempfile
import unittest

import strategy_schema as S
import strategy_validator as SV
import strategy_registry as SR

REGISTRY = SR.default_registry()


def strat_ids():
    return [r["id"] for r in REGISTRY.list_strategies()]


class TestSchemaDeterminism(unittest.TestCase):
    def test_spec_hash_deterministic_and_key_sensitive(self):
        spec = REGISTRY.load("current_control_v1")
        h1 = S.spec_hash(spec)
        h2 = S.spec_hash(json.loads(json.dumps(spec)))
        self.assertEqual(h1, h2)
        import copy
        mutated = copy.deepcopy(spec)
        mutated["strategy"]["version"] = 999
        self.assertNotEqual(S.spec_hash(mutated), h1)


class TestValidator(unittest.TestCase):
    def test_all_strategies_valid_and_unique_ids(self):
        ids = []
        for sid in strat_ids():
            vr = REGISTRY.validate(sid)
            self.assertTrue(vr.valid, f"{sid}: {vr.report()}")
            ids.append(sid)
        self.assertEqual(len(ids), len(set(ids)))

    def test_rejects_forbidden_lookahead_note(self):
        spec = REGISTRY.load("current_control_v1")
        import copy
        spec["entry"]["conditions"]["all"][0]["note"] = "uses future_close to set entry"
        vr = SV.validate_spec(spec)
        self.assertFalse(vr.valid)
        self.assertTrue(any("lookahead" in e.lower() for e in vr.errors))

    def test_rejects_unknown_project_ref(self):
        spec = REGISTRY.load("current_control_v1")
        import copy
        spec["entry"]["conditions"]["all"].append({"rule": "EXISTING_PROJECT_RULE",
                                                   "project_ref": "backtest_frozen.definitely_not_real",
                                                   "note": "not allowlisted"})
        vr = SV.validate_spec(spec)
        self.assertFalse(vr.valid)


class TestRegistryCompiler(unittest.TestCase):
    def test_registry_compile_all(self):
        for sid in strat_ids():
            c = REGISTRY.compile(sid)
            self.assertEqual(c.strategy_id, sid)
            self.assertEqual(c.spec_hash, REGISTRY.spec_hash(sid))

    def test_compiled_evaluate_declarative(self):
        # condor spec has declarative (field/operator) conditions + one
        # project-rule (sell_ok) - context supplies both registered field keys
        # and the project-rule parameter names.
        c = REGISTRY.compile("range_hv_iron_condor_v1")
        ctx = {"REGIME": "RANGE_HV", "VIX": 20.0, "regime": "RANGE_HV", "vix_level": 20.0}
        self.assertTrue(c.evaluate(ctx)["entry_allowed"])
        ctx_bad = {"REGIME": "TREND_HV", "VIX": 20.0, "regime": "TREND_HV", "vix_level": 20.0}
        self.assertFalse(c.evaluate(ctx_bad)["entry_allowed"])
        ctx_low_vix = {"REGIME": "RANGE_HV", "VIX": 12.0, "regime": "RANGE_HV", "vix_level": 12.0}
        self.assertFalse(c.evaluate(ctx_low_vix)["entry_allowed"])
        # missing fields -> not evaluable, never a crash
        self.assertFalse(c.evaluate({})["entry_allowed"])

    def test_compiled_generate_candidate_and_build_order(self):
        c = REGISTRY.compile("current_control_v1")
        self.assertIsNone(c.generate_candidate({}))
        rec = {"date": "2025-09-04", "regime": "TREND_HV", "grade": "B",
               "option_type": "PE", "strike": 24500, "short_strike": None,
               "expiry": dt.date(2025, 9, 9), "entry_premium": 120.0,
               "sl_premium": 200.0, "target_premium": 60.0, "candidate": True}
        cand = c.generate_candidate({"candidate_rec": rec})
        self.assertIsNotNone(cand)
        orders = c.build_order(cand, {})
        self.assertEqual(len(orders), 1)
        o = orders[0]
        self.assertEqual(o["symbol"], "NIFTY")
        self.assertEqual(o["side"], "BUY")
        self.assertEqual(o["option_type"], "PE")
        self.assertEqual(o["strike"], 24500)
        self.assertEqual(o["order_kind"], "OPEN")
        self.assertEqual(o["lot_size"], 75)

    def test_compiled_condor_builds_four_legs(self):
        c = REGISTRY.compile("range_hv_iron_condor_v1")
        cand = {
            "entry_date": "2025-09-04", "side": "IRON_CONDOR",
            "option_type": "IRON_CONDOR", "entry_premium": 80.0,
            "sl_premium": 180.0, "target_premium": 30.0,
            "lots": 1, "lot_size": 75,
            "strikes": {"short_call": 25200, "short_put": 24200,
                        "long_call": 25300, "long_put": 24100},
        }
        orders = c.build_order(cand, {})
        self.assertEqual(len(orders), 4)
        self.assertEqual({o["side"] for o in orders}, {"BUY", "SELL"})


class TestControlEquivalence(unittest.TestCase):
    def test_control_equivalence(self):
        from backtest_adapter import BacktestAdapter
        c = REGISTRY.compile("current_control_v1")
        adapter = BacktestAdapter(c)
        run = adapter.run()
        self.assertGreater(run["metrics"]["trade_count"], 0)
        self.assertEqual(adapter.check_spec_consistency(run), [])
        eq = adapter.equivalence(run)
        self.assertTrue(eq["matched"], eq["differences"][:5])

    def test_condor_backtest_spec_consistency(self):
        from backtest_adapter import BacktestAdapter
        c = REGISTRY.compile("range_hv_iron_condor_v1")
        adapter = BacktestAdapter(c)
        run = adapter.run()
        self.assertGreater(run["metrics"]["trade_count"], 0)
        self.assertEqual(adapter.check_spec_consistency(run), [])

    def test_backtest_determinism(self):
        from backtest_adapter import BacktestAdapter
        c = REGISTRY.compile("current_control_v1")
        r1 = BacktestAdapter(c).run()
        r2 = BacktestAdapter(c).run()
        self.assertEqual(r1["metrics"], r2["metrics"])
        self.assertEqual(r1["trades"], r2["trades"])


class TestPaperAdapterInterface(unittest.TestCase):
    def test_paper_adapter_interface(self):
        from paper_adapter import PaperAdapter
        import paper_execution
        c = REGISTRY.compile("current_control_v1")
        adapter = PaperAdapter(c)
        with tempfile.TemporaryDirectory() as tmp:
            engine = paper_execution.PaperExecutionEngine(
                account_file=os.path.join(tmp, "account.json"),
                gt_db_file=os.path.join(tmp, "gt.db"))
            cand = c.generate_candidate({"candidate_rec": {
                "date": "2025-09-04", "regime": "TREND_HV", "grade": "B",
                "option_type": "PE", "strike": 24500, "expiry": dt.date(2025, 9, 9),
                "entry_premium": 120.0, "sl_premium": 200.0, "target_premium": 60.0,
                "candidate": True}})
            placed = adapter.submit_candidate(engine, cand)
            self.assertEqual(len(placed), 1)
            leg, result = placed[0]
            inner = result["order"]
            self.assertEqual(inner["order_kind"], "OPEN")
            self.assertEqual(inner["quantity"], 75)
            self.assertEqual(result["status"], "SUBMITTED")
            closed = adapter.close_candidate(engine, inner)
            self.assertEqual(closed["order"]["order_kind"], "CLOSE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
