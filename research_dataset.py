"""Phase I.3 - Unified Research Dataset Context (spec sections 4, 7, 8).

Single read-only gateway to the frozen 646-session unified research dataset
(DATA-ALIGNMENT-01). This module:

  * verifies EVERY component hash from unified_research_dataset.json against
    the actual files (calendar_hash, stable hashes, sha256, expiry_hash) and
    aborts with DatasetIntegrityFailure before any research runs,
  * loads only the columns each consumer needs (column pruning, section 8),
  * never mutates a production file,
  * derives a point-in-time expiry map for all 646 sessions from the option
    chain's own expiry column, cross-checked against expiry_calendar.csv where
    the calendar exists.

The research run is keyed on `manifest_self_hash` so any change to the frozen
dataset invalidates every downstream cache (section 11).
"""
import hashlib
import json
import os
import datetime as dt

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.abspath(__file__))
NORM = os.path.join(REPO, "data", "historical", "normalized")
HIST = os.path.join(REPO, "data", "historical")
MANIFEST_PATH = os.path.join(HIST, "manifests", "unified_research_dataset.json")
CALENDAR_CSV = os.path.join(NORM, "trading_calendar_expanded.csv")
EXPIRY_CALENDAR_CSV = os.path.join(HIST, "expiry_calendar.csv")

NIFTY_COLS = ["date", "open", "high", "low", "close", "quality"]
VIX_COLS = ["date", "open", "high", "low", "close"]
OI_COLS = ["date", "client_type", "option_type", "contracts", "value_cr"]
OPTIONS_COLS = ["date", "expiry", "strike", "option_type", "open", "high", "low",
                "close", "settle_price", "underlying_price", "volume", "oi", "oi_chg",
                "lot_size"]

UNIFIED_REQUIRED_HASHES = (
    "calendar_hash", "nifty_hash", "nifty_sha256", "options_hash",
    "options_sha256", "vix_hash", "vix_sha256", "participant_oi_hash",
    "participant_oi_sha256", "expiry_hash",
)


class DatasetIntegrityFailure(RuntimeError):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest():
    with open(MANIFEST_PATH) as fh:
        return json.load(fh)


def manifest_self_hash(manifest=None):
    manifest = manifest or load_manifest()
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def calendar_hash(cal=None):
    """Same convention as collect_historical_data_deep.calendar_hash:
    SHA256 of compact JSON of TRADING_SESSION rows sorted by date."""
    if cal is None:
        cal = pd.read_csv(CALENDAR_CSV, dtype={"date": str})
    sess = cal.loc[cal["session_status"] == "TRADING_SESSION"]
    payload = "\n".join(
        json.dumps(dict(row), sort_keys=True, separators=(",", ":"))
        for _, row in sess.sort_values("date").iterrows())
    return hashlib.sha256(payload.encode()).hexdigest()


def stable_content_hash(df, exclude=("retrieved_at",)):
    """Same convention as collect_historical_data_deep.stable_content_hash."""
    cols = [c for c in df.columns if c not in exclude]
    if not len(df):
        return hashlib.sha256(b"").hexdigest()
    sub = df[cols]
    row_hash = pd.util.hash_pandas_object(sub, index=False)
    return hashlib.sha256(row_hash.values.tobytes()).hexdigest()


def verify_integrity(manifest=None, raise_on_fail=True):
    """Verify every manifest hash against the on-disk files."""
    manifest = manifest or load_manifest()
    checks = {}

    def _check(name, expected, actual, note=""):
        ok = expected == actual
        checks[name] = {"expected": expected, "actual": actual, "pass": ok, "note": note}
        return ok

    cal = pd.read_csv(CALENDAR_CSV, dtype={"date": str})
    _check("calendar_hash", manifest["calendar_hash"], calendar_hash(cal))

    def _file_check(key, rel_path):
        path = os.path.join(REPO, rel_path)
        expected_sha = manifest.get(key)
        if not os.path.exists(path):
            _check(key, expected_sha, None, "file missing")
            return
        actual = sha256_file(path)
        _check(key, expected_sha, actual, f"sha256 of {rel_path}")

    _file_check("nifty_sha256", manifest["nifty_dataset"])
    _file_check("options_sha256", manifest["options_dataset"])
    _file_check("vix_sha256", manifest["vix_dataset"])
    _file_check("participant_oi_sha256", manifest["participant_oi_dataset"])
    _file_check("expiry_hash", manifest["expiry_calendar"])

    # stable content hashes (value-based, excludes retrieved_at)
    for key, rel in (("nifty_hash", "nifty_dataset"), ("options_hash", "options_dataset"),
                     ("vix_hash", "vix_dataset"), ("participant_oi_hash", "participant_oi_dataset")):
        path = os.path.join(REPO, manifest[rel])
        if os.path.exists(path):
            df = pd.read_csv(path)
            _check(key, manifest.get(key), stable_content_hash(df), f"stable hash of {rel}")

    passed = all(c["pass"] for c in checks.values())
    report = {
        "manifest_path": MANIFEST_PATH,
        "manifest_self_hash": manifest_self_hash(manifest),
        "trading_sessions": manifest.get("trading_sessions"),
        "coverage": [manifest.get("coverage_start"), manifest.get("coverage_end")],
        "missing_dataset_days": manifest.get("missing_dataset_days"),
        "expiry_calendar_missing_sessions": len(manifest.get("expiry_calendar_missing_sessions", [])),
        "checks": checks,
        "integrity": "PASS" if passed else "FAIL",
    }
    if not passed and raise_on_fail:
        failed = [k for k, c in checks.items() if not c["pass"]]
        raise DatasetIntegrityFailure(
            f"dataset integrity FAILED: {failed} "
            f"(manifest {manifest.get('dataset_name')})")
    return report


# ---------------------------------------------------------------------------
# read-only data context
# ---------------------------------------------------------------------------
class DataContext:
    """Frozen, pruned, read-only view over the unified research dataset."""

    def __init__(self, verify=True):
        self.manifest = load_manifest()
        if verify:
            self.integrity = verify_integrity(self.manifest)
        else:
            self.integrity = None
        self.sessions = None
        self.nifty = None
        self.vix = None
        self.oi = None
        self.options = None
        self._chain_by_date = None
        self._expiry_by_date = None
        self._expiry_source = None

    # -- loaders -----------------------------------------------------------
    def load(self):
        self.sessions = sorted(pd.read_csv(CALENDAR_CSV, dtype={"date": str})
                               .loc[lambda d: d["session_status"] == "TRADING_SESSION",
                                    "date"].tolist())
        self.nifty = pd.read_csv(os.path.join(REPO, self.manifest["nifty_dataset"]),
                                 usecols=[c for c in NIFTY_COLS if c in _header(self.manifest["nifty_dataset"])])
        self.nifty["date"] = self.nifty["date"].astype(str)
        self.vix = pd.read_csv(os.path.join(REPO, self.manifest["vix_dataset"]),
                               usecols=[c for c in VIX_COLS if c in _header(self.manifest["vix_dataset"])])
        self.vix["date"] = self.vix["date"].astype(str)
        self.oi = pd.read_csv(os.path.join(REPO, self.manifest["participant_oi_dataset"]),
                              usecols=[c for c in OI_COLS if c in _header(self.manifest["participant_oi_dataset"])])
        self.oi["date"] = self.oi["date"].astype(str)
        cols = [c for c in OPTIONS_COLS if c in _header(self.manifest["options_dataset"])]
        self.options = pd.read_csv(os.path.join(REPO, self.manifest["options_dataset"]),
                                   usecols=cols,
                                   dtype={"date": str, "expiry": str, "strike": "float64",
                                          "option_type": str})
        return self

    @property
    def chain_by_date(self):
        if self._chain_by_date is None:
            self._chain_by_date = {d: g for d, g in self.options.groupby("date", sort=True)}
        return self._chain_by_date

    # -- expiry resolution (point in time) ----------------------------------
    def build_expiry_map(self):
        """date -> nearest weekly expiry strictly after date, resolved from the
        option chain's own expiry column (covers all 646 sessions). Cross-checks
        expiry_calendar.csv where present; those rows are the authoritative
        source when both exist."""
        cal = {}
        if os.path.exists(EXPIRY_CALENDAR_CSV):
            ec = pd.read_csv(EXPIRY_CALENDAR_CSV, dtype={"date": str, "expiry": str})
            cal = dict(zip(ec["date"], ec["expiry"]))
        derived = {}
        by_expiry = {d: sorted(set(g["expiry"])) for d, g in self.chain_by_date.items()}
        sessions = self.sessions
        idx = {d: i for i, d in enumerate(sessions)}
        for d, exps in by_expiry.items():
            future = [e for e in exps if e > d]
            derived[d] = min(future) if future else None
        source = {}
        for d in sessions:
            if d in cal and cal[d] in by_expiry.get(d, []):
                source[d] = "expiry_calendar"
            elif derived.get(d):
                source[d] = "options_chain"
            else:
                source[d] = "UNRESOLVED"
        self._expiry_by_date = {
            d: {"expiry": cal.get(d, derived.get(d)), "source": source[d]} for d in sessions}
        self._expiry_source = source
        return self._expiry_by_date

    @property
    def expiry_by_date(self):
        if self._expiry_by_date is None:
            self.build_expiry_map()
        return self._expiry_by_date

    def expiry_for(self, date):
        return self.expiry_by_date.get(date, {}).get("expiry")


def _header(rel_path):
    with open(os.path.join(REPO, rel_path)) as fh:
        return fh.readline().rstrip("\n").split(",")


def load_context(verify=True):
    """Convenience factory: verify + load + expiry map."""
    ctx = DataContext(verify=verify)
    ctx.load()
    ctx.build_expiry_map()
    return ctx


if __name__ == "__main__":
    print(json.dumps(verify_integrity(), indent=2))
