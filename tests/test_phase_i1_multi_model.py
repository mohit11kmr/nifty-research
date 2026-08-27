"""Phase I.1 - Controlled Multi-Model Strategy Research tests.

covers: canonical prompt isolation + fairness (byte-identical expansion,
no-tool instruction, frozen prompt hash), exact/near-duplicate detection,
freeze discipline (never overwrite, never re-invoke), raw-output YAML
extraction, experiment constants, frozen artifact presence, evaluation
outcomes (VALIDATED+EXECUTION_UNSUPPORTED / MODEL_UNAVAILABLE),
deterministic evaluation reruns, transparent model aggregation, review
table discipline (PENDING_REVIEW only, no auto-promotion), and
no-production-writes / no-broker-call isolation.

Run: .venv/bin/python -m unittest tests.test_phase_i1_multi_model -v
"""
import hashlib
import json
import os
import tempfile
import unittest
from unittest import mock

import ai_multi_model_experiment as A

REPO = A.REPO


def _tree(base):
    out = []
    for root, _dirs, files in os.walk(base):
        for f in sorted(files):
            out.append(os.path.relpath(os.path.join(root, f), base))
    return out


class TestPromptIsolation(unittest.TestCase):
    def test_frozen_prompt_hash_stable(self):
        self.assertEqual(
            hashlib.sha256(A.canonical_prompt_text().encode()).hexdigest(),
            "6745b9d47f23f580ee29e003f8502c3fb0745a99d9f86cf882186efd966aec13")

    def test_canonical_prompt_has_slot_tokens(self):
        text = A.canonical_prompt_text()
        self.assertIn("<<SLOT>>", text)
        self.assertIn("<<CATEGORY>>", text)

    def test_expand_replaces_tokens(self):
        for i in range(len(A.SLOTS)):
            expanded = A.expand_prompt(i)
            self.assertNotIn("<<SLOT>>", expanded)
            self.assertNotIn("<<CATEGORY>>", expanded)

    def test_expansion_identical_across_calls(self):
        for i in range(len(A.SLOTS)):
            self.assertEqual(A.expand_prompt(i), A.expand_prompt(i))

    def test_prompt_forbids_tools(self):
        self.assertIn("Do not use any tools",
                      A.canonical_prompt_text())

    def test_prompt_used_copy_frozen(self):
        used = os.path.join(A.PHASE_I1_DIR, "canonical_prompt_v1_used.md")
        self.assertTrue(os.path.exists(used))
        with open(used) as fh:
            self.assertEqual(fh.read(), A.canonical_prompt_text())


class TestDuplicateDetection(unittest.TestCase):
    SPEC_A = {"entry": {"conditions": {"all": [
        {"id": "rsi", "field": "RSI", "operator": ">", "value": 60}]}}}
    SPEC_B = {"entry": {"conditions": {"all": [
        {"id": "rsi", "field": "RSI", "operator": ">=", "value": 60.0}]}}}
    SPEC_C = {"entry": {"conditions": {"all": [
        {"id": "rsi", "field": "RSI", "operator": "<", "value": 35}]}}}

    def test_exact_duplicate(self):
        known = [{
            "name": "x.yaml", "strategy_id": "s1",
            "fingerprint": A.PS.normalized_rule_fingerprint(self.SPEC_A),
            "canon_fingerprint": A.canonical_fingerprint(self.SPEC_A)}]
        cls, name = A.classify_duplicate(self.SPEC_A, known)
        self.assertEqual(cls, "EXACT_DUPLICATE")
        self.assertEqual(name, "s1")

    def test_near_duplicate_operator_and_float(self):
        known = [{
            "name": "x.yaml", "strategy_id": "s1",
            "fingerprint": A.PS.normalized_rule_fingerprint(self.SPEC_A),
            "canon_fingerprint": A.canonical_fingerprint(self.SPEC_A)}]
        cls, _ = A.classify_duplicate(self.SPEC_B, known)
        self.assertEqual(cls, "NEAR_DUPLICATE")

    def test_unique(self):
        known = [{
            "name": "x.yaml", "strategy_id": "s1",
            "fingerprint": A.PS.normalized_rule_fingerprint(self.SPEC_A),
            "canon_fingerprint": A.canonical_fingerprint(self.SPEC_A)}]
        cls, name = A.classify_duplicate(self.SPEC_C, known)
        self.assertEqual(cls, "UNIQUE")
        self.assertIsNone(name)


class TestFreezeDiscipline(unittest.TestCase):
    def test_freeze_write_creates_then_refuses_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "frozen.txt")
            self.assertTrue(A._freeze_write(path, "aaa"))
            self.assertFalse(A._freeze_write(path, "aaa"))
            with self.assertRaises(ValueError):
                A._freeze_write(path, "bbb")
            with open(path) as fh:
                self.assertEqual(fh.read(), "aaa")

    def test_generate_does_not_reinvoke_on_frozen_raw(self):
        rec = A.generate_proposal("big_pickle", 0)
        self.assertFalse(rec["generated_now"])
        self.assertTrue(os.path.exists(rec["raw_path"]))
        self.assertIn("yaml_path", rec)
        self.assertIn("proposal_hash", rec)


class TestExtraction(unittest.TestCase):
    def test_fenced_yaml(self):
        text = "```yaml\nproposal:\n  title: t\n```\n"
        out = A.extract_yaml_document(text)
        self.assertIn("proposal:", out)

    def test_bare_yaml_marker(self):
        text = "yaml\nproposal:\n  title: t\n"
        self.assertEqual(A.extract_yaml_document(text),
                         "proposal:\n  title: t")

    def test_leading_prose(self):
        text = "Here is my proposal.\n\nproposal:\n  title: t\n"
        out = A.extract_yaml_document(text)
        self.assertTrue(out.startswith("proposal:"))


class TestConstants(unittest.TestCase):
    def test_experiment_fixed_parameters(self):
        self.assertEqual(A.MANIFEST_HASH,
                         "ff068e6d54094f696ce02ea357503251fb0ce973b286fcaa4f357bedbd7fa57a")
        self.assertEqual(A.RESEARCH_WINDOW, ("2025-08-13", "2026-08-13"))
        self.assertEqual(A.DEV_OOS_CUT, "2026-03-01")
        self.assertEqual(A.MIN_REQUIRED_TRADES, 20)
        self.assertEqual(A.MAX_PROPOSALS, 9)
        self.assertEqual(A.MAX_PROPOSALS_PER_MODEL, 3)
        self.assertEqual(A.EXPERIMENT_ID, "phase_i1_controlled_multi_model_v1")

    def test_engine_registered_ids(self):
        self.assertEqual(A.ENGINE_REGISTERED_IDS,
                         ("current_control_v1", "directional_spread_v1",
                          "range_hv_iron_condor_v1"))

    def test_budget(self):
        recs = [{"proposal_id": f"p{i}", "model_id": "big_pickle"}
                for i in range(A.MAX_PROPOSALS)]
        self.assertTrue(A.budget_ok(recs))
        recs.append({"proposal_id": "pX", "model_id": "big_pickle"})
        self.assertFalse(A.budget_ok(recs))


class TestFrozenArtifacts(unittest.TestCase):
    def test_six_proposal_yamls_frozen(self):
        for model in ("big_pickle", "deepseek"):
            for slot in ("p1", "p2", "p3"):
                pid = f"phase_i1_{model}_{slot}"
                self.assertTrue(
                    os.path.exists(os.path.join(A.PROPOSAL_YAML_DIR, f"{pid}.yaml")),
                    f"{pid}.yaml missing")
                self.assertTrue(
                    os.path.exists(os.path.join(A.RAW_DIR, f"{model}_{slot}.txt")),
                    f"{model}_{slot}.txt missing")

    def test_qwen_unavailable_artifact_preserved(self):
        self.assertTrue(os.path.exists(
            os.path.join(A.RAW_DIR, "qwen_p1_openrouter_max_tokens_error.txt")))


class TestEvaluation(unittest.TestCase):
    def test_evaluation_outcomes(self):
        for model in ("big_pickle", "deepseek"):
            for slot in range(3):
                rec = A.evaluate_proposal(model, slot)
                self.assertEqual(rec["validation_status"], "VALIDATED")
                self.assertEqual(rec["failure_code"], "EXECUTION_UNSUPPORTED")
                self.assertEqual(rec["backtest_status"], "NOT_RUN")
                self.assertEqual(rec["classification"], "UNIQUE")
                self.assertEqual(rec["review_status"], "PENDING_REVIEW")
        for slot in range(3):
            rec = A.evaluate_proposal("qwen", slot)
            self.assertEqual(rec["failure_code"], "MODEL_UNAVAILABLE")
            self.assertEqual(rec["status"], "REJECTED")

    def test_evaluation_deterministic_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            with unittest.mock.patch.object(A, "RESULT_DIR", tmp):
                for model in A.MODEL_KEYS:
                    for slot in range(3):
                        A.evaluate_proposal(model, slot)
                A._save_experiment_json()
                first = {f: open(os.path.join(tmp, f)).read()
                         for f in os.listdir(tmp) if f.endswith(".json")}
                self.assertEqual(len(first), 10)
                for model in A.MODEL_KEYS:
                    for slot in range(3):
                        A.evaluate_proposal(model, slot)
                A._save_experiment_json()
                second = {f: open(os.path.join(tmp, f)).read()
                          for f in os.listdir(tmp) if f.endswith(".json")}
                self.assertEqual(first, second)

    def test_no_production_writes(self):
        before = _tree(A.PHASE_I1_DIR)
        with tempfile.TemporaryDirectory() as tmp:
            with unittest.mock.patch.object(A, "RESULT_DIR", tmp):
                for model in A.MODEL_KEYS:
                    for slot in range(3):
                        A.evaluate_proposal(model, slot)
                A._save_experiment_json()
                A._cmd_review(type("A", (), {}))
                written = set(os.listdir(tmp))
                self.assertEqual(written,
                                 {"experiment.json", "review_table.json"} |
                                 {f"phase_i1_{m}_p{i}.eval.json"
                                  for m in A.MODEL_KEYS for i in (1, 2, 3)})
        self.assertEqual(_tree(A.PHASE_I1_DIR), before)

    def test_no_broker_calls(self):
        src = open(os.path.join(A.REPO, "ai_multi_model_experiment.py")).read()
        for forbidden in ("paper_account", "ground_truth.db", "place_order",
                          "mcp_nifty"):
            self.assertNotIn(forbidden, src)


class TestAggregation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = A.load_eval_records()

    def test_all_slots_present(self):
        self.assertEqual(len(self.records), 9)

    def test_transparent_metrics_no_pl_ranking(self):
        m = A.aggregate_model_metrics(self.records)
        self.assertEqual(m["big_pickle"]["proposals_valid"], 3)
        self.assertEqual(m["big_pickle"]["validation_pass_rate"], 1.0)
        self.assertEqual(m["deepseek"]["validation_pass_rate"], 1.0)
        self.assertEqual(m["qwen"]["validation_pass_rate"], 0.0)
        self.assertEqual(m["qwen"]["backtest_completion_rate"], 0.0)
        self.assertEqual(m["big_pickle"]["average_net_pnl"], None)


class TestReviewTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = A.load_eval_records()
        cls.rows = A.build_review_table(cls.records)

    def test_all_pending_review_no_auto_promotion(self):
        for row in self.rows:
            self.assertEqual(row["review_status"], "PENDING_REVIEW")
            self.assertNotEqual(row["recommended_decision"],
                                "CONTROLLED PAPER CANDIDATE")

    def test_recommended_decisions(self):
        by_id = {row["proposal_id"]: row for row in self.rows}
        for m in ("big_pickle", "deepseek"):
            for slot in ("p1", "p2", "p3"):
                row = by_id[f"phase_i1_{m}_{slot}"]
                self.assertEqual(row["recommended_decision"],
                                 "REQUEST MORE DATA")
                self.assertEqual(row["failure_code"], "EXECUTION_UNSUPPORTED")
        for slot in ("p1", "p2", "p3"):
            self.assertEqual(by_id[f"phase_i1_qwen_{slot}"]["recommended_decision"],
                             "REJECT")


if __name__ == "__main__":
    unittest.main()
