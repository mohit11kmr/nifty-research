"""Phase I.2 - Generic Execution Replay (I.1 proposals).

Replays the six FROZEN Phase I.1 proposals through the Phase I.2 generic
execution layer: every proposal that Phase I.1 recorded as EXECUTION_UNSUPPORTED
(no engine-registered strategy id) is now resolved to a registered
deterministic execution family or fails with a structured EXECUTION_UNSUPPORTED
code + reason (the diagnosis Phase I.1's audit did not record per proposal).

Production isolation (spec section 1):
  - reads ONLY frozen artifacts: strategy_proposals/phase_i1/proposals/*.yaml
  - writes ONLY to results/phase_i2/ (new directory). It NEVER calls
    ai_strategy_research.persist_research (that would mutate the frozen
    phase_i1 proposal registry) and NEVER calls evaluate_proposal (that would
    write into results/phase_i1/).
  - no production writes, no broker calls, no optimization, no auto-promotion
  - engine-registered strategies (current_control_v1 / directional_spread_v1 /
    range_hv_iron_condor_v1) are never routed through the generic layer.

Determinism (spec section 20): every supported replay is run twice and must
reproduce the same result_hash. The shared engine-backed control run is
computed once and reused for every baseline comparison.
"""
import datetime as dt
import json
import os
import sys

import yaml

import strategy_proposal_schema as PS
import strategy_proposal_validator as PV
import strategy_proposal_compiler as PC
import ai_strategy_research as AR
import strategy_execution_capabilities as C
import strategy_execution_registry as R

REPO = os.path.dirname(os.path.abspath(__file__))

EXPERIMENT_ID = "phase_i2_generic_execution_v1"
PHASE_I1_DIR = os.path.join(REPO, "strategy_proposals", "phase_i1")
PROPOSAL_YAML_DIR = os.path.join(PHASE_I1_DIR, "proposals")
RESULT_DIR = os.path.join(REPO, "results", "phase_i2")

MIN_REQUIRED_TRADES = 20

# The six frozen I.1 proposals (phase_i1_<model>_p<slot>).
PROPOSAL_IDS = (
    "phase_i1_big_pickle_p1", "phase_i1_big_pickle_p2",
    "phase_i1_big_pickle_p3",
    "phase_i1_deepseek_p1", "phase_i1_deepseek_p2",
    "phase_i1_deepseek_p3",
)


# ---------------------------------------------------------------------------
# Failure-code extraction from structured ValueErrors
# ---------------------------------------------------------------------------
def _split_exception(exc):
    """Return (code, reason) for a structured EXECUTION_UNSUPPORTED error."""
    msg = str(exc)
    marker = "EXECUTION_UNSUPPORTED:"
    if marker in msg:
        rest = msg.split(marker, 1)[1].strip()
        if ": " in rest:
            code, reason = rest.split(": ", 1)
            return code.strip(), reason.strip()
        return rest.strip(), ""
    return "UNSUPPORTED", msg


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
# Replay
# ---------------------------------------------------------------------------
def _load_proposal(pid):
    path = os.path.join(PROPOSAL_YAML_DIR, f"{pid}.yaml")
    with open(path) as fh:
        return yaml.safe_load(fh)


def replay_proposal(proposal, control_run, data_root=None):
    """Replay one frozen proposal through the generic execution layer.

    Returns (record, research|None). Deterministic except generated_at.
    """
    pid = (proposal.get("proposal") or {}).get("proposal_id")
    spec_block = proposal.get("strategy") if isinstance(proposal, dict) else None

    rec = {
        "experiment_id": EXPERIMENT_ID,
        "proposal_id": pid,
        "strategy_id": ((spec_block or {}).get("strategy") or {}).get("id"),
        "title": ((proposal.get("proposal") or {}).get("title")),
        "validation_status": "VALIDATED",
        "backtest_status": "NOT_RUN",
        "review_status": "PENDING_REVIEW",
    }

    validation = PV.validate_proposal(proposal)
    rec["spec_hash"] = validation.hashes.get("spec_hash")
    rec["proposal_hash"] = validation.hashes.get("proposal_hash")
    rec["fingerprint"] = validation.hashes.get("fingerprint")
    rec["dataset_hash"] = ((proposal.get("research") or {}).get("dataset_manifest_hash"))

    if not validation.valid:
        rec.update(status="REJECTED", failure_code=validation.failure_code,
                   failure_reason="; ".join(validation.errors[:5]))
        return rec, None

    compilation = PC.compile_proposal(proposal)

    # Pre-resolve the family for the diagnosis table (never a silent fallback).
    family_id, failure = R.resolve_family(compilation.compiled.spec)
    rec["resolved_family"] = family_id
    if family_id is not None:
        rec["registered"] = R.default_registry().lookup(family_id) is not None

    try:
        research = AR.run_research(compilation, data_root=data_root,
                                   control=True, control_run=control_run)
        research2 = AR.run_research(compilation, data_root=data_root,
                                    control=True, control_run=control_run)
        reproducible = research["result_hash"] == research2["result_hash"]
    except ValueError as exc:
        code, reason = _split_exception(exc)
        rec.update(status="REJECTED", failure_code=code,
                   failure_reason=reason,
                   granularity_issue=code == C.GRANULARITY_UNSUPPORTED)
        return rec, None

    metrics = research["metrics"]
    oos = research["evaluation_vector"]["oos_quality"]
    oos_trades = (oos.get("out_of_sample_from_2026_03_01") or {}).get("trades", 0)
    rec.update(
        status="REVIEW", backtest_status="BACKTESTED", failure_code=None,
        execution_family=metrics.get("candidate"),
        result_hash=research["result_hash"], reproducible=reproducible,
        trades=metrics.get("trade_count"), net_pnl=metrics.get("net_pnl"),
        profit_factor=metrics.get("profit_factor"),
        win_rate=metrics.get("win_rate"),
        max_drawdown=metrics.get("max_drawdown"), oos_trades=oos_trades,
        reliable=metrics.get("trade_count", 0) >= MIN_REQUIRED_TRADES,
        oos_verdict=oos.get("verdict"), baseline=research.get("baseline"),
    )
    return rec, research


def main(argv=None):
    os.makedirs(RESULT_DIR, exist_ok=True)

    # Shared engine-backed control, computed exactly once.
    control_run = AR.BacktestAdapter(
        AR._compiled_control(), data_root=None).run()

    records, researches = [], []
    for pid in PROPOSAL_IDS:
        proposal = _load_proposal(pid)
        rec, research = replay_proposal(proposal, control_run, data_root=None)
        if research is not None:
            path = os.path.join(RESULT_DIR, f"{pid}.research.json")
            _freeze_write(path, json.dumps(research, indent=2, sort_keys=True,
                                           default=str))
            researches.append(research)
        _freeze_write(os.path.join(RESULT_DIR, f"{pid}.eval.json"),
                      json.dumps(rec, indent=2, sort_keys=True, default=str))
        records.append(rec)
        print(f"{pid:<34} {rec.get('backtest_status'):<9} "
              f"{rec.get('failure_code') or rec.get('execution_family')} "
              f"trades={rec.get('trades')}")

    payload = {
        "experiment_id": EXPERIMENT_ID,
        "phase": "I.2",
        "source": "frozen phase_i1 proposals (results/phase_i1 untouched)",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "control_strategy": "current_control_v1 (engine-backed, computed once)",
        "records": records,
    }
    _freeze_write(os.path.join(RESULT_DIR, "experiment.json"),
                  json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
