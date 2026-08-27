"""Phase I.3 - Research Checkpointing (spec section 33).

Every compute stage writes a completed/failed record to
results/phase_i3/checkpoints/checkpoints.jsonl keyed by (task_id, run_hash).
A run resumes by skipping tasks already completed under the SAME run_hash
(which embeds the frozen dataset hash + resource profile + code version), so a
changed dataset or machine profile forces recomputation instead of a stale
resume. Record format is deliberately append-only JSONL - never rewritten.
"""
import json
import os
import datetime as dt

REPO = os.path.dirname(os.path.abspath(__file__))
CHECKPOINT_DIR = os.path.join(REPO, "results", "phase_i3", "checkpoints")
CHECKPOINT_FILE = os.path.join(CHECKPOINT_DIR, "checkpoints.jsonl")

FIELDS = ("task_id", "run_hash", "status", "payload", "generated_at")


def _ensure():
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)


def _record(task_id, run_hash, status, payload=None):
    _ensure()
    with open(CHECKPOINT_FILE, "a") as fh:
        fh.write(json.dumps({
            "task_id": task_id,
            "run_hash": run_hash,
            "status": status,
            "payload": payload or {},
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }, sort_keys=True, default=str) + "\n")


def read_all():
    if not os.path.exists(CHECKPOINT_FILE):
        return []
    out = []
    with open(CHECKPOINT_FILE) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def done(task_id, run_hash):
    """True when a COMPLETED record exists for (task_id, run_hash)."""
    return any(r["task_id"] == task_id and r["run_hash"] == run_hash
               and r["status"] == "COMPLETED" for r in read_all())


def failed(task_id, run_hash):
    return any(r["task_id"] == task_id and r["run_hash"] == run_hash
               and r["status"] == "FAILED" for r in read_all())


def mark_completed(task_id, run_hash, payload=None):
    _record(task_id, run_hash, "COMPLETED", payload)


def mark_failed(task_id, run_hash, reason=None):
    _record(task_id, run_hash, "FAILED", {"reason": reason})


def summary():
    recs = read_all()
    out = {"total_records": len(recs), "by_status": {}, "tasks": {}}
    for r in recs:
        out["by_status"][r["status"]] = out["by_status"].get(r["status"], 0) + 1
        out["tasks"].setdefault(r["task_id"], r["status"])
    return out
