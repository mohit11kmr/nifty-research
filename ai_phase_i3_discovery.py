"""Phase I.3 - Regime-Aware Research Discovery Orchestrator (spec 25/32/34).

Three-stage discovery pipeline over the frozen unified dataset:

  Stage 1  features -> regimes -> behaviors -> questions   (cached, deterministic)
  Stage 2  AI packets per question                          (cached)
  Stage 3  CONTROLLED AI run: bounded opencode subprocess generates <=N
           proposals across highest-conviction questions; every proposal is
           fast-screened (research_screener) then fully researched
           (research_runner). Rejected / low-frequency proposals stay on the
           record with structured reasons.

Budget (spec): MAX_QUESTIONS=12, MAX_HYPOTHESES_PER_QUESTION=2,
MAX_PROPOSALS=24. A "Controlled full run" uses --max-proposals (default 12)
across the top-conviction questions.

Every stage writes to results/phase_i3/ + data/research_cache/ +
strategy_research_memory/phase_i3_memory.jsonl only (spec hard rules).
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import yaml

import research_dataset as RD
import research_feature_engine as FE
import research_feature_registry as FREG
import research_regime_discovery as RR
import research_behavior_engine as BE
import research_question_engine as QE
import research_memory as MEMORY_MOD
import research_ai_packet as AP
import research_screener as RS
import research_runner as RUN
import research_checkpoint as CK

RESULTS = os.path.join("results", "phase_i3")
AI_PROPOSALS = os.path.join(RESULTS, "ai_proposals")
PROPOSAL_RESEARCH = os.path.join(RESULTS, "proposal_research")
MAX_PROPOSALS = 24


def _now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))
                           ).strftime("%Y-%m-%dT%H:%M:%S+05:30")


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)
    return path


def _mem(kind, content, evidence=None, tags=None):
    MEMORY_MOD.add_record(kind, content, evidence=evidence, tags=tags)


def _run_hash(meta):
    return meta["feature_version"]


def load_stage1():
    """Load context + panel + regimes + behaviors + questions (reused)."""
    ctx = RD.load_context()
    panel, meta = FE.build_panel(ctx)
    regime_report, _ = RR.discover_regimes(panel, meta)
    behavior_report, _ = BE.discover_behaviors(panel, meta)
    questions = QE.build_questions(behavior_report, regime_report)
    return (ctx, panel, meta, regime_report, behavior_report, questions)


# ---------------------------------------------------------------------------
# Stage 1
# ---------------------------------------------------------------------------
def run_stage1():
    _, panel, meta, regime_report, behavior_report, questions = load_stage1()
    out = {
        "stage": 1,
        "feature_version": meta["feature_version"],
        "n_sessions": len(panel),
        "regime_interpretation": regime_report["interpretation"],
        "regime_stability": regime_report["stability"],
        "regime_transitions": regime_report["transitions"],
        "n_behaviors": len(behavior_report["behaviors"]),
        "n_questions": len(questions),
        "questions": questions,
        "generated_at": _now(),
    }
    path = _write(os.path.join(RESULTS, "stage1_report.json"),
                  json.dumps(out, indent=2, sort_keys=True, default=str))
    CK.mark_completed("stage1", _run_hash(meta))
    _mem("TEST", f"stage1 complete: {len(panel)} sessions, {len(questions)} questions",
         evidence=f"features v{meta['feature_version']}", tags=["stage1"])
    return out, path


# ---------------------------------------------------------------------------
# Stage 2
# ---------------------------------------------------------------------------
def run_stage2():
    _, _, meta, _, behavior_report, questions = load_stage1()
    packets = AP.build_packets(questions, behavior_report)
    paths = []
    for p in packets:
        path = os.path.join(RESULTS, "ai_packets", p["packet_id"] + ".yaml")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            yaml.safe_dump(p, fh, sort_keys=False)
        paths.append(path)
    out = {"stage": 2, "n_packets": len(packets), "packets": paths,
           "generated_at": _now()}
    path = _write(os.path.join(RESULTS, "stage2_report.json"),
                  json.dumps(out, indent=2, sort_keys=True, default=str))
    CK.mark_completed("stage2", _run_hash(meta))
    _mem("TEST", f"stage2 complete: {len(packets)} AI packets", tags=["stage2"])
    return out, path


# ---------------------------------------------------------------------------
# Stage 3
# ---------------------------------------------------------------------------
def _extract_yaml(raw):
    raw = (raw or "").strip()
    if raw.startswith("```"):
        blocks = raw.split("```")
        for b in blocks[1::2]:
            b = b.strip()
            if b.lstrip().lower().startswith("yaml"):
                b = b.split("\n", 1)[1]
            if "proposal:" in b:
                return b
    return raw


PROMPT_TEMPLATE = """You are the research proposal generator for NIFTY options
research (Phase I.3). Read the packet file at {packet_path} (YAML). It contains
the OBSERVED evidence, INFERRED mechanics, the candidate HYPOTHESIS, the
research question, and generation instructions.

Read these schemas too:
  {repo}/research_conditions.py  -- the ONLY allowed condition DSL
    (field/op/value; ops: >,>=,<,<=,==,!=,between,in; values numeric literals).
  {repo}/research_feature_registry.py -- the ONLY allowed feature ids.

Requirements (hard):
1. Reply with exactly ONE proposal YAML document and nothing else.
2. proposal block: proposal_id exact string "{packet_id}", title,
   author_type: AI, author_model: opencode/big-pickle, created_at ISO with
   +05:30, parent_strategy_id: null, hypothesis (1-3 sentences),
   research_question = "{packet_id}", expected_failure_modes (2+ items),
   candidate_family exactly "{family}".
3. strategy block:
   - entry.conditions: valid DSL conditions using ONLY registered feature ids
     and numeric literals. Point-in-time safe (no percentiles, no future data).
   - entry.direction: LONG (for CALL/PUT/STRADDLE) or SHORT/NEUTRAL
     (IRON_CONDOR only).
   - entry.instrument: CALL, PUT, STRADDLE, or IRON_CONDOR.
   - entry.strike_selection: ATM, OTM_1, or ITM_1.
   - exit.type: HORIZON (horizon_sessions 1..20) or EXPIRY or CONDITION (one
     valid exit condition). Prefer HORIZON or EXPIRY.
   - risk.defined_risk: true (required for IRON_CONDOR); risk.stop_pct
     optional 0..1.
   - execution: cost_model canonical, resolution EOD, lot_size 75.
   - required_features: exact feature ids used in entry + exit conditions.
   - regime: {{"allowed": [...]}} subset of REGIME_A/REGIME_B/REGIME_C, or null.
     Restrict ONLY if the packet's evidence justifies it.
4. Never invent features, never write code, never mention backtests.

Reply with only the YAML document (```yaml fences are fine)."""


def _strip_ansi(text):
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _generate_proposal(packet_path, packet_id, family, opencode_bin, timeout=900):
    raw_path = os.path.join(AI_PROPOSALS, "raw", f"{packet_id}.txt")
    if os.path.exists(raw_path):
        with open(raw_path) as fh:
            raw = fh.read()
        generated = False
    else:
        prompt = PROMPT_TEMPLATE.format(
            packet_path=packet_path, repo=os.getcwd(), packet_id=packet_id,
            family=family)
        proc = subprocess.run(
            [opencode_bin, "run", "--model", "opencode/big-pickle",
             "--pure", "--format", "default", prompt],
            capture_output=True, text=True, timeout=timeout)
        raw = (proc.stdout or "") or (proc.stderr or "")
        if not raw or proc.returncode != 0:
            raw = raw or "<empty output>"
        generated = True
        _write(raw_path, raw)
    raw = _strip_ansi(raw)
    if "Error:" in raw and ("model" in raw.lower() or "available" in raw.lower()):
        return raw, None, "MODEL_UNAVAILABLE", generated
    try:
        doc = yaml.safe_load(_extract_yaml(raw))
    except Exception as e:
        return raw, None, f"yaml parse: {e}", generated
    if not isinstance(doc, dict) or "proposal" not in doc:
        return raw, None, "missing proposal block", generated
    return raw, doc, None, generated


def _run_one_packet(packet_path, panel, ctx, regime_labels, opencode_bin):
    packet = yaml.safe_load(open(packet_path))
    pid = packet["packet_id"]
    family = packet["candidate_family"]
    raw, doc, err, generated = _generate_proposal(packet_path, pid, family, opencode_bin)
    rec = {"packet_id": pid, "question_id": packet["question_id"],
           "candidate_family": family,
           "raw_path": os.path.join(AI_PROPOSALS, "raw", f"{pid}.txt"),
           "raw_chars": len(raw), "generated_now": generated}
    if err:
        rec.update(status="REJECTED", failure_code="SCHEMA_ERROR", evidence=err)
        _mem("NEGATIVE_KNOWLEDGE", f"proposal {pid} -> SCHEMA_ERROR",
             evidence=err, tags=["stage3", "rejected"])
        return rec
    doc["proposal"]["proposal_id"] = pid
    doc["proposal"]["author_type"] = "AI"
    doc["proposal"]["author_model"] = "opencode/big-pickle"
    doc["proposal"]["created_at"] = doc["proposal"].get("created_at") or _now()
    yaml_path = _write(os.path.join(AI_PROPOSALS, f"{pid}.yaml"),
                       yaml.safe_dump(doc, sort_keys=False))
    rec["yaml_path"] = yaml_path

    screen = RS.fast_screen(doc, panel, regime_labels)
    rec["screen_verdict"] = screen["verdict"]
    rec["screen_reasons"] = screen["reasons"]
    if screen["verdict"] == "REJECT":
        rec.update(status="REJECTED", failure_code="SCREEN",
                   evidence="; ".join(screen["reasons"]))
        _mem("NEGATIVE_KNOWLEDGE", f"proposal {pid} -> SCREEN reject",
             evidence=rec["evidence"], tags=["stage3", "rejected"])
        return rec

    research_path = os.path.join(PROPOSAL_RESEARCH, f"{pid}.json")
    if os.path.exists(research_path):
        # resume: research is deterministic (result_hash); reuse cached output
        research = json.load(open(research_path))
        research["reproducibility"] = RUN.reproducibility(research)
    else:
        research = RUN.research(doc, panel, ctx, regime_labels)
        research["reproducibility"] = RUN.reproducibility(research)
        _write(research_path,
               json.dumps(research, indent=2, sort_keys=True, default=str))
    out_path = research_path
    rec["status"] = "RESEARCHED"
    rec["backtest_status"] = "RAN"
    rec["n_trades"] = research["n_trades"]
    rec["metrics"] = research["metrics"]
    rec["oos_verdict"] = research["oos"]["verdict"]
    rec["concentration_flag"] = research["concentration"]["concentration_flag"]
    rec["regime_flag"] = research["regime_robustness"]["flag"]
    rec["result_hash"] = research["result_hash"]
    rec["research_path"] = out_path
    if research["n_trades"] < 20:
        rec["failure_code"] = "SAMPLE_TOO_SMALL"
        rec["evidence"] = f"n_trades={research['n_trades']} < 20 -> NOT_RELIABLE"
        _mem("NEGATIVE_KNOWLEDGE", f"proposal {pid} -> SAMPLE_TOO_SMALL",
             evidence=rec["evidence"], tags=["stage3", "not_reliable"])
    else:
        rec["failure_code"] = None
        rec["evidence"] = "research complete"
        _mem("TEST", f"proposal {pid} researched: n={research['n_trades']} "
             f"net={research['metrics']['net_pnl']} "
             f"oos={research['oos']['out_of_sample_from_2026_03_01']['net']}",
             evidence=f"result_hash={research['result_hash'][:16]}", tags=["stage3"])
    return rec


def run_packet_worker(packet_path, opencode_bin="opencode"):
    """Child-process worker: load dataset fresh, process ONE packet, emit the
    record JSON on stdout. Keeps memory per-packet (the 354MB options chain is
    reloaded for each child, avoiding cumulative RSS growth in one process)."""
    ctx, panel, meta, regime_report, _, _ = load_stage1()
    rec = _run_one_packet(packet_path, panel, ctx,
                          regime_report["assignments"], opencode_bin)
    rec["run_hash"] = _run_hash(meta)
    sys.stdout.write(json.dumps(rec, default=str) + "\n")
    sys.stdout.flush()


def run_stage3(max_proposals=12, opencode_bin="opencode", packets_dir=None):
    _, _, _, _, _, _ = load_stage1()
    packets_dir = packets_dir or os.path.join(RESULTS, "ai_packets")
    if not os.path.isdir(packets_dir):
        raise SystemExit("no packets dir; run stage 2 first")
    packet_paths = sorted(os.path.join(packets_dir, f) for f in os.listdir(packets_dir)
                          if f.endswith(".yaml"))
    if max_proposals > MAX_PROPOSALS:
        raise SystemExit(f"budget: max_proposals {max_proposals} > {MAX_PROPOSALS}")
    if max_proposals <= 0:
        raise SystemExit("max_proposals must be >= 1")
    packet_paths = packet_paths[:max_proposals]

    worker = os.path.abspath(__file__)
    records = []
    for path in packet_paths:
        pid = os.path.basename(path).replace(".yaml", "")
        log = os.path.join("/tmp", "opencode", f"phase_i3_{pid}.log")
        proc = subprocess.run(
            [sys.executable, worker, "--packet", path, "--opencode-bin", opencode_bin],
            capture_output=True, text=True, timeout=1800)
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "w") as fh:
            fh.write(proc.stdout + "\n--- stderr ---\n" + proc.stderr)
        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        if proc.returncode == 0 and lines:
            try:
                rec = json.loads(lines[-1])
            except Exception as e:
                rec = {"packet_id": pid, "status": "FAILED",
                       "failure_code": "WORKER_OUTPUT", "evidence": str(e)}
        else:
            rec = {"packet_id": pid, "status": "FAILED",
                   "failure_code": "WORKER_CRASH",
                   "evidence": (proc.stderr or proc.stdout or "")[-500:]}
        rec.setdefault("packet_id", pid)
        records.append(rec)
        CK.mark_completed(f"stage3/{pid}", rec.get("run_hash", "phase_i3"))
    summary = {
        "stage": 3,
        "budget": {"max_proposals": MAX_PROPOSALS, "used": len(records)},
        "status_counts": {
            k: sum(1 for r in records if r.get("status") == k)
            for k in ("REJECTED", "RESEARCHED", "FAILED")},
        "screen_counts": {
            k: sum(1 for r in records if r.get("screen_verdict") == k)
            for k in ("SCREENED_IN", "LOW_FREQUENCY", "REJECT")},
        "records": records,
        "generated_at": _now(),
    }
    path = _write(os.path.join(RESULTS, "discovery_report.json"),
                  json.dumps(summary, indent=2, sort_keys=True, default=str))
    _mem("TEST", f"stage3 complete: {len(records)} proposals "
         f"{summary['status_counts']}", tags=["stage3"])
    return summary, path


def run_all(max_proposals=12, opencode_bin="opencode"):
    s1, p1 = run_stage1()
    s2, p2 = run_stage2()
    s3, p3 = run_stage3(max_proposals=max_proposals, opencode_bin=opencode_bin)
    print("stage1:", p1)
    print("stage2:", p2)
    print("stage3:", p3)
    return s3, p3


def main():
    ap = argparse.ArgumentParser(description="Phase I.3 discovery orchestrator")
    ap.add_argument("--stage", type=int, default=0, choices=[0, 1, 2, 3])
    ap.add_argument("--packet", default=None, help="single-packet worker mode")
    ap.add_argument("--max-proposals", type=int, default=12)
    ap.add_argument("--opencode-bin", default="opencode")
    args = ap.parse_args()
    if args.packet:
        run_packet_worker(args.packet, args.opencode_bin)
    elif args.stage == 0:
        run_all(args.max_proposals, args.opencode_bin)
    elif args.stage == 1:
        run_stage1()
    elif args.stage == 2:
        run_stage2()
    else:
        run_stage3(args.max_proposals, args.opencode_bin)


if __name__ == "__main__":
    main()
