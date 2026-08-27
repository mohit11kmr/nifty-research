"""Phase I.3 - Research Cache (spec section 11).

Derived research artifacts (feature panels, regime labels, behaviour reports)
are expensive to recompute and live in data/research_cache/. Every artifact is
keyed by:

    source dataset hash (manifest self-hash) + code version + schema version
    + feature version

so any change to the frozen dataset or the code that produced the artifact
invalidates it (CACHE_INVALID). Reads and writes are JSON, deterministic, and
never touch production data.
"""
import hashlib
import json
import os
import datetime as dt

REPO = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(REPO, "data", "research_cache")

SCHEMA_VERSION = "phase_i3_v1"
CODE_VERSION = "2026-08-16.1"


def _key(source_hash, code_version=CODE_VERSION, schema_version=SCHEMA_VERSION,
         feature_version=""):
    payload = "|".join([source_hash, code_version, schema_version, feature_version])
    return hashlib.sha256(payload.encode()).hexdigest()


def _cache_path(name, key):
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{name}__{key}.json")


def get(name, source_hash, feature_version="", code_version=CODE_VERSION):
    """Return cached payload if its source+code+schema+feature versions match,
    else None (CACHE_INVALID)."""
    key = _key(source_hash, code_version, SCHEMA_VERSION, feature_version)
    path = _cache_path(name, key)
    if not os.path.exists(path):
        return None, "CACHE_MISS"
    try:
        with open(path) as fh:
            blob = json.load(fh)
    except (ValueError, OSError):
        return None, "CACHE_INVALID"
    if blob.get("source_hash") != source_hash:
        return None, "CACHE_INVALID"
    if blob.get("code_version") != code_version:
        return None, "CACHE_INVALID"
    if blob.get("schema_version") != SCHEMA_VERSION:
        return None, "CACHE_INVALID"
    if blob.get("feature_version") != feature_version:
        return None, "CACHE_INVALID"
    return blob.get("payload"), "CACHE_HIT"


def put(name, source_hash, payload, feature_version="", code_version=CODE_VERSION):
    """Persist a payload under its version key. Overwrites a stale entry."""
    key = _key(source_hash, code_version, SCHEMA_VERSION, feature_version)
    blob = {
        "name": name,
        "source_hash": source_hash,
        "code_version": code_version,
        "schema_version": SCHEMA_VERSION,
        "feature_version": feature_version,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "payload": payload,
    }
    path = _cache_path(name, key)
    with open(path, "w") as fh:
        json.dump(blob, fh, indent=2, sort_keys=True, default=str)


def status(name, source_hash, feature_version="", code_version=CODE_VERSION):
    payload, state = get(name, source_hash, feature_version, code_version)
    return {"state": state, "cached": payload is not None}
