"""Truth & Provenance Layer (Phase 3) — minimal shared contract.

Makes important system outputs distinguish real market results from
simulation, estimation, fallback, stale, missing, invalid and unsupported
values. This module only labels and validates; it never fabricates data and
never substitutes values.

Design basis: audit/PHASE2-TRUTH-MODEL.md section 3 (status vocabulary,
provenance envelope, freshness rules). Freshness budgets below come from the
existing architecture: build_data.py `_fresh(path, max_age_h=20)` for the
daily cache cycle, the 6h FII/DII rule, and the 60s spot sampling (120s budget)
from tick_recorder.py.
"""
import os
import json
import hashlib
import datetime as dt

# ----------------------------------------------------------------------
# Status vocabulary (exactly one status per result)
# ----------------------------------------------------------------------
REAL = "REAL"                          # computed from observed data, no substitution
SIMULATED = "SIMULATED"                # model/scenario output under explicit assumptions
ESTIMATED = "ESTIMATED"                # derived/implied value (reconstructed IV, formula)
FALLBACK = "FALLBACK"                  # substituted value because primary source unavailable
STALE = "STALE"                        # computed from data older than its freshness budget
MISSING = "MISSING"                    # not computable (no data, never set)
INVALID = "INVALID"                    # violates invariants (future timestamp, bad age)
UNSUPPORTED = "UNSUPPORTED"            # produced by hardcoded/synthetic substitution
LEGACY = "LEGACY"                      # pre-provenance record; status unknown, never upgraded
UNKNOWN = "UNKNOWN"                    # provenance not supplied / not determinable

# Canonical provenance fields (Phase 4A P-05). Only populated fields are
# persisted; no field is forced into a record that does not have it.
PROVENANCE_FIELDS = [
    "status", "source", "timestamp", "data_timestamp", "data_freshness",
    "fallback_used", "fallback_reason", "feature_version", "model_version",
    "parameter_version", "signal_version", "evaluation_method",
    "environment", "execution_mode",
]

# ----------------------------------------------------------------------
# Freshness budgets (existing project rules, not invented)
# ----------------------------------------------------------------------
DAILY_CACHE_FRESHNESS_H = 20           # build_data refresh cycle (_fresh max_age_h=20)
FII_DII_FRESHNESS_H = 6                # institutional cache rule
LIVE_SPOT_FRESHNESS_S = 120            # spot sampled every 60s -> 2x budget

ASSET_BUDGETS_H = {
    "data/nifty_history.csv": DAILY_CACHE_FRESHNESS_H,
    "data/india_vix.csv": DAILY_CACHE_FRESHNESS_H,
    "data/ml_features.csv": DAILY_CACHE_FRESHNESS_H,
    "data/tf_scan.csv": DAILY_CACHE_FRESHNESS_H,
    "data/fii_dii_history.csv": FII_DII_FRESHNESS_H,
}


def now_iso():
    """Current timestamp as UTC ISO string (metadata convention)."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def envelope(result, status, source=None, timestamp=None, data_timestamp=None,
             fallback_used=None, fallback_reason=None, evaluation_method=None,
             **extra):
    """Attach a provenance envelope to a result dict.

    Returns a new dict; does not mutate the input. Only keys that carry
    real information are added (no empty fields).
    """
    if not isinstance(result, dict):
        result = {"result": result}
    out = dict(result)
    out["status"] = status
    if source is not None:
        out["source"] = source
    if timestamp is not None:
        out["timestamp"] = timestamp
    elif "timestamp" not in out:
        out["timestamp"] = now_iso()
    if data_timestamp is not None:
        out["data_timestamp"] = data_timestamp
    if fallback_used is not None:
        out["fallback_used"] = fallback_used
    if fallback_reason is not None:
        out["fallback_reason"] = fallback_reason
    if evaluation_method is not None:
        out["evaluation_method"] = evaluation_method
    for key, value in extra.items():
        if value is not None:
            out[key] = value
    return out


def hash_version(payload):
    """Stable content hash for feature/parameter/signal versioning."""
    if isinstance(payload, str):
        raw = payload.encode("utf-8")
    else:
        raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


def canonical_provenance(**kwargs):
    """Build the canonical provenance dict (P-05) - only populated fields.

    An empty provenance degrades to UNKNOWN rather than pretending a status.
    """
    out = {}
    for key in PROVENANCE_FIELDS:
        val = kwargs.get(key)
        if val is not None:
            out[key] = val
    if "status" not in out:
        out["status"] = UNKNOWN
    return out


def serialize_provenance(prov):
    """Deterministic JSON for persistence (SQLite TEXT column / CSV)."""
    return json.dumps(prov, sort_keys=True)


def deserialize_provenance(raw):
    """Read persisted provenance; legacy/corrupt rows never become REAL.

    None -> LEGACY (record predates the provenance schema).
    Unparseable -> UNKNOWN + reason.
    """
    if raw is None:
        return {"status": LEGACY}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except (ValueError, TypeError):
        pass
    return {"status": UNKNOWN, "reason": "corrupt provenance"}


def freshness_status(age_seconds, budget_seconds):
    """Classify data freshness: REAL (fresh), STALE, INVALID, MISSING."""
    if age_seconds is None:
        return MISSING
    if age_seconds < 0:
        return INVALID
    if budget_seconds is None or budget_seconds <= 0:
        return INVALID
    return REAL if age_seconds <= budget_seconds else STALE


def file_freshness(path, budget_h):
    """Freshness of a cache file based on its modification time."""
    if not os.path.exists(path):
        return {"path": path, "status": MISSING, "age_h": None,
                "budget_h": budget_h, "note": "file not found"}
    age_s = dt.datetime.now().timestamp() - os.path.getmtime(path)
    if age_s < 0:
        return {"path": path, "status": INVALID, "age_h": round(age_s / 3600, 2),
                "budget_h": budget_h, "note": "file mtime in the future"}
    status = freshness_status(age_s, budget_h * 3600)
    return {"path": path, "status": status, "age_h": round(age_s / 3600, 2),
            "budget_h": budget_h,
            "note": f"{status}: age {age_s / 3600:.1f}h vs budget {budget_h}h"}


def asset_freshness_report():
    """Scan known datasets against their budgets.

    Used to surface stale caches instead of letting them feed analysis
    silently. Returns a list of {path, status, age_h, budget_h, note}.
    """
    report = []
    for path, budget_h in ASSET_BUDGETS_H.items():
        report.append(file_freshness(path, budget_h))
    snap_dir = os.path.join("data", "oi_snapshots")
    if os.path.isdir(snap_dir):
        snaps = sorted(f for f in os.listdir(snap_dir) if f.endswith(".csv"))
        if snaps:
            newest = os.path.join(snap_dir, snaps[-1])
            report.append(file_freshness(newest, DAILY_CACHE_FRESHNESS_H))
        else:
            report.append({"path": snap_dir, "status": MISSING, "age_h": None,
                           "budget_h": DAILY_CACHE_FRESHNESS_H,
                           "note": "no oi_snapshots present"})
    return report


if __name__ == "__main__":
    print(json.dumps(asset_freshness_report(), indent=2))
