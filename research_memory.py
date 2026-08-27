"""Phase I.3 - Research Memory + Negative Knowledge (spec sections 23, 24).

An append-only JSONL store under strategy_research_memory/ capturing every
observation, hypothesis, test result and piece of negative knowledge produced
by Phase I.3. Nothing here touches production data. Negative knowledge is
deliberately first-class: a hypothesis that failed validation is recorded with
its evidence so future discovery does not repeat it.
"""
import json
import os
import datetime as dt

REPO = os.path.dirname(os.path.abspath(__file__))
MEMORY_DIR = os.path.join(REPO, "strategy_research_memory")
MEMORY_FILE = os.path.join(MEMORY_DIR, "phase_i3_memory.jsonl")

KINDS = ("OBSERVATION", "HYPOTHESIS", "TEST", "NEGATIVE_KNOWLEDGE")


def _ensure():
    os.makedirs(MEMORY_DIR, exist_ok=True)


def add_record(kind, content, evidence=None, tags=None, ref=None):
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    _ensure()
    rec = {
        "id": f"mem_{len(read_all()) + 1:04d}",
        "kind": kind,
        "content": content,
        "evidence": evidence,
        "tags": tags or [],
        "ref": ref,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    with open(MEMORY_FILE, "a") as fh:
        fh.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
    return rec


def add_negative_knowledge(hypothesis, evidence, verdict="REJECTED"):
    return add_record(
        "NEGATIVE_KNOWLEDGE",
        content=f"hypothesis [{hypothesis}] -> {verdict}",
        evidence=evidence,
        tags=["negative", verdict.lower()],
    )


def read_all():
    if not os.path.exists(MEMORY_FILE):
        return []
    out = []
    with open(MEMORY_FILE) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def query(kind=None, tag=None):
    recs = read_all()
    if kind:
        recs = [r for r in recs if r["kind"] == kind]
    if tag:
        recs = [r for r in recs if tag in (r.get("tags") or [])]
    return recs


def summary():
    recs = read_all()
    out = {"total": len(recs), "by_kind": {}}
    for r in recs:
        out["by_kind"][r["kind"]] = out["by_kind"].get(r["kind"], 0) + 1
    return out
