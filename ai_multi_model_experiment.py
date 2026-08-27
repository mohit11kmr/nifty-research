"""Phase I.1 - Controlled Multi-Model Strategy Research Experiment.

Runs 3 AI models x 3 proposal slots = 9 FROZEN strategy proposals through the
existing deterministic research environment:

    freeze raw output -> convert -> hash -> validate -> dedupe
      -> backtest (engine-registered only) x2 -> baseline -> model metrics
      -> human review table

This is a RESEARCH-ONLY experiment on the RESEARCH QUALITY of AI-generated
strategy hypotheses (Phase I.1 spec sections 4-21). It is not a strategy
generator and it is not a trading system.

Safety (spec section 1):
  - raw model output is frozen BEFORE any evaluation; revisions are new slots
  - models never see other models' outputs or any backtest result
  - every proposal goes through the EXISTING Phase I gates (no bypass)
  - only validated unique proposals reach a backtest, and only when the
    proposal's strategy id maps to an engine-registered frozen structure
  - backtests are run TWICE and must reproduce the same result_hash
  - writes ONLY to strategy_proposals/phase_i1/ and results/phase_i1/
  - no production writes, no broker calls, no optimization, no auto-promotion
"""
import copy
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys

import yaml

import strategy_proposal_schema as PS
import strategy_proposal_validator as PV
import strategy_proposal_compiler as PC
import strategy_proposal_registry as SPR
import ai_strategy_research as AR
import strategy_schema as S

REPO = os.path.dirname(os.path.abspath(__file__))

EXPERIMENT_ID = "phase_i1_controlled_multi_model_v1"
CANONICAL_PROMPT_FILE = os.path.join(REPO, "prompts",
                                     "AI_MULTI_MODEL_RESEARCH_V1.md")

PHASE_I1_DIR = os.path.join(REPO, "strategy_proposals", "phase_i1")
RAW_DIR = os.path.join(PHASE_I1_DIR, "raw")
PROPOSAL_YAML_DIR = os.path.join(PHASE_I1_DIR, "proposals")
RESULT_DIR = os.path.join(REPO, "results", "phase_i1")
MAIN_REGISTRY_DIR = os.path.join(REPO, "strategy_proposals")

FROZEN_STRATEGIES_DIR = os.path.join(REPO, "strategies")

MANIFEST_HASH = "ff068e6d54094f696ce02ea357503251fb0ce973b286fcaa4f357bedbd7fa57a"
RESEARCH_WINDOW = ("2025-08-13", "2026-08-13")
DEV_OOS_CUT = "2026-03-01"
MIN_REQUIRED_TRADES = 20
MAX_PROPOSALS = 9
MAX_PROPOSALS_PER_MODEL = 3

# The three registered/engine-backed frozen structures (platform reality).
ENGINE_REGISTERED_IDS = ("current_control_v1", "directional_spread_v1",
                         "range_hv_iron_condor_v1")

# model key -> (provider/model id used for generation, model_version)
MODELS = (
    {"key": "big_pickle", "model_id": "opencode/big-pickle",
     "model_version": "opencode/big-pickle"},
    {"key": "deepseek", "model_id": "openrouter/deepseek/deepseek-chat",
     "model_version": "deepseek-chat"},
    {"key": "qwen", "model_id": "openrouter/qwen/qwen3-coder",
     "model_version": "qwen3-coder"},
)
MODEL_KEYS = tuple(m["key"] for m in MODELS)

SLOTS = (
    {"slot": "p1", "label": "1", "category": "A - DIRECTIONAL"},
    {"slot": "p2", "label": "2", "category": "B - MEAN REVERSION / RANGE"},
    {"slot": "p3", "label": "3", "category": "C - DEFINED RISK OPTIONS STRUCTURE"},
)
SLOT_KEYS = tuple(s["slot"] for s in SLOTS)


# ---------------------------------------------------------------------------
# Canonical prompt
# ---------------------------------------------------------------------------
def canonical_prompt_text():
    with open(CANONICAL_PROMPT_FILE) as fh:
        return fh.read()


def expand_prompt(slot_index=0):
    """Expand the canonical prompt for a slot. Deterministic; byte-identical
    across models for the same slot (fairness requirement, spec section 4)."""
    slot = SLOTS[slot_index]
    text = canonical_prompt_text()
    return (text.replace("<<SLOT>>", slot["label"])
                .replace("<<CATEGORY>>", slot["category"]))


# ---------------------------------------------------------------------------
# Identifiers + paths
# ---------------------------------------------------------------------------
def proposal_id(model_key, slot_index):
    return f"phase_i1_{model_key}_{SLOTS[slot_index]['slot']}"


def _frozen_strategy_fingerprints():
    """fingerprint + canonical-fingerprint of the 3 frozen strategies."""
    out = []
    for f in sorted(os.listdir(FROZEN_STRATEGIES_DIR)):
        if not f.endswith(".yaml"):
            continue
        with open(os.path.join(FROZEN_STRATEGIES_DIR, f)) as fh:
            spec = yaml.safe_load(fh)
        if not isinstance(spec, dict) or not isinstance(spec.get("strategy"), dict):
            continue
        out.append({
            "name": f,
            "strategy_id": (spec.get("strategy") or {}).get("id"),
            "fingerprint": PS.normalized_rule_fingerprint(spec),
            "canon_fingerprint": canonical_fingerprint(spec),
        })
    return out


# ---------------------------------------------------------------------------
# Near-duplicate detection (spec section 8)
# ---------------------------------------------------------------------------
def _canonicalize_value(node, in_operator=False):
    """Normalize numbers (60 == 60.0) and boundary operators
    (> x  ==  >= x.0) for semantic near-duplicate detection."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            is_op = (k == "operator")
            out[k] = _canonicalize_value(v, in_operator=is_op)
        return out
    if isinstance(node, list):
        return [_canonicalize_value(v, in_operator=in_operator) for v in node]
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return float(node)
    if isinstance(node, str) and in_operator:
        if node == ">":
            return ">="
        if node == "<":
            return "<="
    return node


def canonical_fingerprint(spec):
    """Fingerprint of the numerically/operator-canonicalized spec. Two specs
    with equal canonical fingerprints but different raw fingerprints are
    semantic near-duplicates (e.g. RSI > 60 vs RSI >= 60.0)."""
    canon = _canonicalize_value(copy.deepcopy(spec))
    return PS.normalized_rule_fingerprint(canon)


def classify_duplicate(spec, known):
    """known: list of {'fingerprint', 'canon_fingerprint', 'name', ...}.

    Returns ('EXACT_DUPLICATE'|'NEAR_DUPLICATE'|'UNIQUE', matched_name|None).
    """
    fp = PS.normalized_rule_fingerprint(spec)
    canon = canonical_fingerprint(spec)
    for rec in known:
        if rec.get("fingerprint") == fp:
            return "EXACT_DUPLICATE", rec.get("strategy_id") or rec.get("name")
    for rec in known:
        if rec.get("canon_fingerprint") == canon:
            return "NEAR_DUPLICATE", rec.get("strategy_id") or rec.get("name")
    return "UNIQUE", None


# ---------------------------------------------------------------------------
# Raw output extraction
# ---------------------------------------------------------------------------
def extract_yaml_document(raw_text):
    """Pull the YAML document out of a model response.

    Handles, deterministically, in order:
      1. ```yaml ... ``` (or any ``` ... ```) fenced block(s)
      2. a bare `yaml` marker line followed by the document
      3. leading prose ending at the first line that starts the `proposal:`
         block
      4. the raw text itself
    """
    lines = raw_text.splitlines()

    fences = [i for i, ln in enumerate(lines) if ln.strip().startswith("```")]
    if len(fences) >= 2:
        return "\n".join(lines[fences[0] + 1:fences[-1]])
    if len(fences) == 1:
        return "\n".join(lines[:fences[0]] + lines[fences[0] + 1:])

    start = None
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if stripped == "yaml" and start is None:
            start = i + 1
            continue
        if stripped.startswith("proposal:") or stripped.startswith("proposal :"):
            start = i
            break
    if start is not None:
        return "\n".join(lines[start:])
    return raw_text


# ---------------------------------------------------------------------------
# Conversion: raw output -> structured proposal (spec section 9)
# ---------------------------------------------------------------------------
def convert_raw_to_proposal(raw_text, model_key, slot_index):
    """Parse the model's raw output into a structured proposal document.

    The structured document is what gets hashed and frozen. proposal_id and
    author_model are normalized by the platform (identity fields are platform
    provenance, not model-authored content).

    Returns (proposal, error) where error is None on success.
    """
    body = extract_yaml_document(raw_text)
    try:
        doc = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        return None, f"YAML parse error: {exc}"
    if not isinstance(doc, dict):
        return None, "top-level YAML is not a mapping"
    for key in ("proposal", "strategy", "research"):
        if key not in doc:
            return None, f"missing required block {key!r}"
    pid = proposal_id(model_key, slot_index)
    meta = dict(doc["proposal"])
    meta["proposal_id"] = pid
    meta["author_model"] = model_key
    if not meta.get("author_type"):
        meta["author_type"] = "AI"
    doc["proposal"] = meta
    return doc, None


def convert_to_yaml(proposal):
    return yaml.safe_dump(proposal, sort_keys=False, default_flow_style=False)


# ---------------------------------------------------------------------------
# Freeze discipline (spec section 9): never overwrite a frozen artifact
# ---------------------------------------------------------------------------
def _freeze_write(path, content):
    if os.path.exists(path):
        with open(path) as fh:
            existing = fh.read()
        if existing != content:
            raise ValueError(f"refusing to overwrite frozen artifact {path}")
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(content)
    return True


# ---------------------------------------------------------------------------
# Generation (isolated subprocess per model/slot)
# ---------------------------------------------------------------------------
def generate_proposal(model_key, slot_index, timeout=600, opencode_bin="opencode"):
    """Run ONE blind, isolated model invocation. Saves the exact raw output
    to the freeze dir. Returns a dict describing the frozen artifact."""
    if model_key not in MODEL_KEYS:
        raise ValueError(f"unknown model {model_key!r} (models: {MODEL_KEYS})")
    model = next(m for m in MODELS if m["key"] == model_key)
    pid = proposal_id(model_key, slot_index)
    raw_path = os.path.join(RAW_DIR, f"{model_key}_{SLOTS[slot_index]['slot']}.txt")
    if os.path.exists(raw_path):
        with open(raw_path) as fh:
            raw = fh.read()
        generated = False
    else:
        prompt = expand_prompt(slot_index)
        proc = subprocess.run(
            [opencode_bin, "run", "--model", model["model_id"], "--pure",
             "--format", "default", prompt],
            capture_output=True, text=True, timeout=timeout,
        )
        raw = proc.stdout
        if not raw or proc.returncode != 0:
            raw = raw or (proc.stderr or "")
        generated = True

    proposal, error = convert_raw_to_proposal(raw, model_key, slot_index)

    _freeze_write(raw_path, raw)
    rec = {
        "experiment_id": EXPERIMENT_ID,
        "model_id": model_key,
        "model_version": model["model_version"],
        "proposal_id": pid,
        "slot": SLOTS[slot_index]["slot"],
        "category": SLOTS[slot_index]["category"],
        "raw_path": raw_path,
        "raw_chars": len(raw),
        "generated_now": generated,
        "parse_error": error,
    }
    if proposal is not None:
        rec["proposal_hash"] = PS.proposal_hash(proposal)
        yaml_path = os.path.join(PROPOSAL_YAML_DIR, f"{pid}.yaml")
        _freeze_write(yaml_path, convert_to_yaml(proposal))
        rec["yaml_path"] = yaml_path
        rec["strategy_id"] = ((proposal.get("strategy") or {}).get("strategy") or {}).get("id")
    return rec


# ---------------------------------------------------------------------------
# Lightweight compilation record for rejected/uncompilable proposals
# ---------------------------------------------------------------------------
class _ProposalCompilation:
    def __init__(self, proposal, proposal_hash, spec_hash, fingerprint,
                 strategy_id):
        self.proposal = proposal
        self.proposal_hash = proposal_hash
        self.spec_hash = spec_hash
        self.fingerprint = fingerprint
        self.strategy_id = strategy_id


def _empty_proposal(pid, model_key, slot_index):
    return {
        "proposal": {
            "proposal_id": pid,
            "title": "(raw output did not parse)",
            "author_type": "AI",
            "author_model": model_key,
            "created_at": "2026-08-16T00:00:00+05:30",
            "parent_strategy_id": None,
            "hypothesis": "",
            "research_question": "",
            "expected_failure_modes": ["raw output did not parse"],
        },
    }


# ---------------------------------------------------------------------------
# Evaluation: validate -> dedupe -> backtest (x2) -> baseline
# ---------------------------------------------------------------------------
def _registry():
    return SPR.ProposalRegistry(base_dir=PHASE_I1_DIR)


def _known_duplicate_records(exclude_pid=None):
    """fingerprint + canonical fingerprint of every existing strategy spec:
    the 3 frozen strategies/ and every proposal YAML (main + phase_i1).

    ``exclude_pid`` skips the proposal's own YAML so it never matches itself.
    """
    known = _frozen_strategy_fingerprints()
    for base in (MAIN_REGISTRY_DIR, PROPOSAL_YAML_DIR):
        if not os.path.isdir(base):
            continue
        for f in sorted(os.listdir(base)):
            if not f.endswith(".yaml"):
                continue
            if exclude_pid is not None and f == f"{exclude_pid}.yaml":
                continue
            try:
                with open(os.path.join(base, f)) as fh:
                    doc = yaml.safe_load(fh)
            except Exception:
                continue
            spec = doc.get("strategy") if isinstance(doc, dict) else None
            if not isinstance(spec, dict):
                continue
            known.append({
                "name": f,
                "strategy_id": (spec.get("strategy") or {}).get("id"),
                "fingerprint": PS.normalized_rule_fingerprint(spec),
                "canon_fingerprint": canonical_fingerprint(spec),
            })
    return known


def evaluate_proposal(model_key, slot_index):
    """Validate, dedupe and (if eligible) backtest one frozen proposal.

    Returns the evaluation record dict. Deterministic except for the
    generated_at timestamp written into research outputs.
    """
    pid = proposal_id(model_key, slot_index)
    yaml_path = os.path.join(PROPOSAL_YAML_DIR, f"{pid}.yaml")
    model = next(m for m in MODELS if m["key"] == model_key)

    if not os.path.exists(yaml_path):
        raw_path = os.path.join(RAW_DIR, f"{model_key}_{SLOTS[slot_index]['slot']}.txt")
        unavailable = not os.path.exists(raw_path)
        rec = {
            "experiment_id": EXPERIMENT_ID, "model_id": model_key,
            "model_version": model["model_version"], "proposal_id": pid,
            "status": "REJECTED", "validation_status": "REJECTED",
            "backtest_status": "NOT_RUN", "review_status": "PENDING_REVIEW",
            "failure_code": "MODEL_UNAVAILABLE" if unavailable else "SCHEMA_ERROR",
            "evidence": ("model could not be reached within the research budget"
                         if unavailable else "raw output did not parse"),
            "classification": "N/A",
        }
        _persist_eval(rec)
        return rec

    with open(yaml_path) as fh:
        proposal = yaml.safe_load(fh)

    validation = PV.validate_proposal(proposal)
    spec_block = proposal.get("strategy") if isinstance(proposal, dict) else None

    rec = {
        "experiment_id": EXPERIMENT_ID, "model_id": model_key,
        "model_version": model["model_version"], "proposal_id": pid,
        "title": ((proposal.get("proposal") or {}).get("title")),
        "hypothesis": ((proposal.get("proposal") or {}).get("hypothesis")),
        "research_question": ((proposal.get("proposal") or {}).get("research_question")),
        "expected_failure_modes": ((proposal.get("proposal") or {}).get("expected_failure_modes")),
        "strategy_id": ((spec_block or {}).get("strategy") or {}).get("id"),
        "spec_hash": validation.hashes.get("spec_hash"),
        "proposal_hash": validation.hashes.get("proposal_hash"),
        "fingerprint": validation.hashes.get("fingerprint"),
        "dataset_hash": ((proposal.get("research") or {}).get("dataset_manifest_hash")),
        "window_start": ((proposal.get("research") or {}).get("start_date")),
        "window_end": ((proposal.get("research") or {}).get("end_date")),
        "dev_oos_cut": ((proposal.get("research") or {}).get("dev_oos_cut")),
    }

    if not validation.valid:
        rec.update(status="REJECTED", validation_status="REJECTED",
                   backtest_status="NOT_RUN", review_status="PENDING_REVIEW",
                   failure_code=validation.failure_code,
                   evidence="; ".join(validation.errors[:5]),
                   classification="N/A")
        _persist_eval(rec)
        return rec

    # duplicate / near-duplicate classification
    known = _known_duplicate_records(exclude_pid=pid)
    classification, matched = classify_duplicate(spec_block, known)
    rec["classification"] = classification
    rec["duplicate_of"] = matched
    if classification != "UNIQUE":
        rec.update(status="REJECTED", validation_status="VALIDATED",
                   backtest_status="NOT_RUN", review_status="PENDING_REVIEW",
                   failure_code="DUPLICATE_PROPOSAL",
                   evidence=f"{classification} against {matched}",
                   failure_reason=f"{classification} of existing strategy/proposal {matched}")
        _persist_eval(rec)
        return rec

    compilation = PC.compile_proposal(proposal)
    rec["validation_status"] = "VALIDATED"

    if compilation.strategy_id not in ENGINES_REGISTERED():
        rec.update(status="REVIEW", backtest_status="NOT_RUN",
                   review_status="PENDING_REVIEW",
                   failure_code="EXECUTION_UNSUPPORTED",
                   evidence=f"no deterministic engine for strategy_id "
                            f"{compilation.strategy_id!r} "
                            f"(engine-registered: {', '.join(ENGINE_REGISTERED_IDS)})")
        _persist_eval(rec)
        return rec

    # deterministic backtest x2 (reproducibility, spec section 20)
    research = AR.run_research(compilation, registry=_registry(), control=True)
    research2 = AR.run_research(compilation, registry=_registry(), control=True)
    reproducible = research["result_hash"] == research2["result_hash"]

    metrics = research["metrics"]
    trades = research.get("trades") or []
    oos = research["evaluation_vector"]["oos_quality"]
    oos_trades = (oos.get("out_of_sample_from_2026_03_01") or {}).get("trades", 0)

    rec.update(status="REVIEW", backtest_status="BACKTESTED",
               review_status="PENDING_REVIEW",
               failure_code=None,
               result_hash=research["result_hash"],
               reproducible=reproducible,
               trades=metrics.get("trade_count"),
               net_pnl=metrics.get("net_pnl"),
               profit_factor=metrics.get("profit_factor"),
               win_rate=metrics.get("win_rate"),
               max_drawdown=metrics.get("max_drawdown"),
               oos_trades=oos_trades,
               reliable=metrics.get("trade_count", 0) >= MIN_REQUIRED_TRADES,
               oos_verdict=oos.get("verdict"),
               baseline=research.get("baseline"))

    AR.persist_research(research, registry=_registry(), out_dir=RESULT_DIR,
                        status="REVIEW")
    _persist_eval(rec)
    return rec


def ENGINES_REGISTERED():
    try:
        from backtest_adapter import ENGINES
        return tuple(sorted(ENGINES))
    except Exception:
        return tuple(sorted(ENGINE_REGISTERED_IDS))


def _persist_eval(rec):
    os.makedirs(RESULT_DIR, exist_ok=True)
    path = os.path.join(RESULT_DIR, f"{rec['proposal_id']}.eval.json")
    _freeze_write(path, json.dumps(rec, indent=2, sort_keys=True, default=str))


# ---------------------------------------------------------------------------
# Model-level aggregation (spec section 15)
# ---------------------------------------------------------------------------
def load_eval_records():
    out = []
    for model_key in MODEL_KEYS:
        for slot_index in range(len(SLOTS)):
            pid = proposal_id(model_key, slot_index)
            path = os.path.join(RESULT_DIR, f"{pid}.eval.json")
            if os.path.exists(path):
                with open(path) as fh:
                    rec = json.load(fh)
            else:
                rec = {"proposal_id": pid, "model_id": model_key,
                       "status": "MISSING", "validation_status": "MISSING",
                       "backtest_status": "NOT_RUN",
                       "review_status": "PENDING_REVIEW"}
            out.append(rec)
    return out


def _frac(recs, pred):
    if not recs:
        return 0.0
    return round(sum(1 for r in recs if pred(r)) / len(recs), 3)


def aggregate_model_metrics(records):
    """Transparent model-level metrics (no P&L-only ranking)."""
    out = {}
    for model_key in MODEL_KEYS:
        recs = [r for r in records if r.get("model_id") == model_key]
        valid = [r for r in recs if r.get("validation_status") == "VALIDATED"]
        backtested = [r for r in recs if r.get("backtest_status") == "BACKTESTED"]
        trades = [r.get("trades") for r in backtested if r.get("trades") is not None]
        pfs = [r.get("profit_factor") for r in backtested
               if r.get("profit_factor") is not None]
        nets = [r.get("net_pnl") for r in backtested if r.get("net_pnl") is not None]
        out[model_key] = {
            "proposals_submitted": len(recs),
            "proposals_valid": len(valid),
            "validation_pass_rate": _frac(recs, lambda r: r.get("validation_status") == "VALIDATED"),
            "duplicate_rate": _frac(recs, lambda r: r.get("classification") not in (None, "UNIQUE")),
            "backtest_completion_rate": _frac(recs, lambda r: r.get("backtest_status") == "BACKTESTED"),
            "average_trades": round(sum(trades) / len(trades), 1) if trades else None,
            "median_trades": sorted(trades)[len(trades) // 2] if trades else None,
            "not_reliable_rate": _frac(backtested, lambda r: not r.get("reliable")),
            "average_pf": round(sum(pfs) / len(pfs), 3) if pfs else None,
            "median_pf": sorted(pfs)[len(pfs) // 2] if pfs else None,
            "average_net_pnl": round(sum(nets) / len(nets), 2) if nets else None,
            "oos_survival_rate": _frac(backtested, lambda r: (r.get("oos_trades") or 0) >= MIN_REQUIRED_TRADES),
            "risk_validity_rate": _frac(valid, _risk_valid),
            "data_validity_rate": _frac(valid, _data_valid),
            "unique_rate": _frac(recs, lambda r: r.get("classification") == "UNIQUE"),
            "near_duplicate_rate": _frac(recs, lambda r: r.get("classification") == "NEAR_DUPLICATE"),
            "exact_duplicate_rate": _frac(recs, lambda r: r.get("classification") == "EXACT_DUPLICATE"),
        }
    return out


def _risk_valid(r):
    return r.get("validation_status") == "VALIDATED"


def _data_valid(r):
    return r.get("validation_status") == "VALIDATED"


# ---------------------------------------------------------------------------
# Human review table (spec section 21) - machine draft, human confirms
# ---------------------------------------------------------------------------
def review_recommendation(rec):
    if rec.get("status") == "REJECTED":
        code = rec.get("failure_code")
        if code == "DUPLICATE_PROPOSAL":
            return "KEEP FOR FUTURE RESEARCH"
        return "REJECT"
    if rec.get("backtest_status") != "BACKTESTED":
        if rec.get("failure_code") == "EXECUTION_UNSUPPORTED":
            return "REQUEST MORE DATA"
        return "REJECT"
    if not rec.get("reliable"):
        return "REQUEST MORE DATA"
    if (rec.get("oos_trades") or 0) < MIN_REQUIRED_TRADES:
        return "REQUEST MORE DATA"
    verdict = ((rec.get("baseline") or {}).get("verdict"))
    if verdict in ("OUTPERFORMS_CONTROL", "COMPARABLE_TO_CONTROL"):
        return "CONTROLLED PAPER CANDIDATE"
    return "KEEP FOR FUTURE RESEARCH"


def build_review_table(records):
    rows = []
    for rec in sorted(records, key=lambda r: (r.get("model_id", ""), r.get("proposal_id", ""))):
        rows.append({
            "proposal_id": rec.get("proposal_id"),
            "model_id": rec.get("model_id"),
            "strategy_id": rec.get("strategy_id"),
            "status": rec.get("status"),
            "validation_status": rec.get("validation_status"),
            "backtest_status": rec.get("backtest_status"),
            "failure_code": rec.get("failure_code"),
            "classification": rec.get("classification"),
            "trades": rec.get("trades"),
            "net_pnl": rec.get("net_pnl"),
            "profit_factor": rec.get("profit_factor"),
            "reliable": rec.get("reliable"),
            "oos_trades": rec.get("oos_trades"),
            "review_status": "PENDING_REVIEW",
            "recommended_decision": review_recommendation(rec),
        })
    return rows


# ---------------------------------------------------------------------------
# Experiment run bookkeeping
# ---------------------------------------------------------------------------
def budget_ok(records):
    return len(records) <= MAX_PROPOSALS and \
        all(r.get("model_id") in MODEL_KEYS for r in records)


def _save_experiment_json():
    records = load_eval_records()
    os.makedirs(RESULT_DIR, exist_ok=True)
    payload = {
        "experiment_id": EXPERIMENT_ID,
        "canonical_prompt_sha256": hashlib.sha256(
            canonical_prompt_text().encode()).hexdigest(),
        "manifest_hash": MANIFEST_HASH,
        "window": RESEARCH_WINDOW,
        "dev_oos_cut": DEV_OOS_CUT,
        "min_required_trades": MIN_REQUIRED_TRADES,
        "max_proposals": MAX_PROPOSALS,
        "models": [{"key": m["key"], "model_id": m["model_id"],
                    "model_version": m["model_version"]} for m in MODELS],
        "records": records,
    }
    _freeze_write(os.path.join(RESULT_DIR, "experiment.json"),
                  json.dumps(payload, indent=2, sort_keys=True, default=str))


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="Phase I.1 multi-model research")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate")
    g.add_argument("--model", choices=MODEL_KEYS, default=None)
    g.add_argument("--slot", choices=SLOT_KEYS, default=None)
    g.set_defaults(fn=_cmd_generate)

    e = sub.add_parser("evaluate")
    e.set_defaults(fn=_cmd_evaluate)

    a = sub.add_parser("aggregate")
    a.set_defaults(fn=_cmd_aggregate)

    r = sub.add_parser("review")
    r.set_defaults(fn=_cmd_review)

    args = p.parse_args(argv)
    return args.fn(args)


def _cmd_generate(args):
    keys = [args.model] if args.model else list(MODEL_KEYS)
    slots = [SLOT_KEYS.index(args.slot)] if args.slot else list(range(len(SLOTS)))
    for model_key in keys:
        for slot_index in slots:
            rec = generate_proposal(model_key, slot_index)
            print(f"{rec['proposal_id']:<34} raw={rec['raw_chars']} "
                  f"generated_now={rec['generated_now']} "
                  f"parse_error={rec.get('parse_error')}")
    return 0


def _cmd_evaluate(args):
    for model_key in MODEL_KEYS:
        for slot_index in range(len(SLOTS)):
            rec = evaluate_proposal(model_key, slot_index)
            print(f"{rec['proposal_id']:<34} {rec.get('validation_status'):<9} "
                  f"{rec.get('failure_code') or rec.get('backtest_status')} "
                  f"trades={rec.get('trades')}")
    _save_experiment_json()
    return 0


def _cmd_aggregate(args):
    records = load_eval_records()
    print(json.dumps(aggregate_model_metrics(records), indent=2, sort_keys=True))
    return 0


def _cmd_review(args):
    records = load_eval_records()
    rows = build_review_table(records)
    _freeze_write(os.path.join(RESULT_DIR, "review_table.json"),
                  json.dumps(rows, indent=2, sort_keys=True, default=str))
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
