"""Cache Rebuild / Recovery (Phase 4A P-15).

Rebuilds stale/missing/corrupt derived caches through the REAL existing data
pipelines - never by touching timestamps and never by fabricating data.

- data/ml_features.csv -> ml_engine.build_features(force=True)
  (reads fresh nifty_history.csv + fii_dii_history.csv, cache-only, no network)
- data/tf_scan.csv     -> multitf.tf_grid_scan(strategies.build_param_grid(), ...)
  (Yahoo intraday bars; network dependent, bounded retries, clear failure)

Cache recovery rules:
  VALID + FRESH  -> use (no-op)
  VALID + STALE  -> rebuild
  MISSING        -> rebuild
  CORRUPT        -> discard + rebuild
  REBUILD FAILED -> remain STALE/MISSING; never fabricate
"""
import os
import sys
import time
import datetime as dt

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

import truth

ML_FEATURES = os.path.join("data", "ml_features.csv")
TF_SCAN = os.path.join("data", "tf_scan.csv")

ML_FEATURES_COLUMNS = {"date", "close", "target_up"}
TF_SCAN_COLUMNS = {"name", "params"}


def needs_rebuild(path, budget_h):
    """True when the cache should be rebuilt (STALE / MISSING / INVALID)."""
    return truth.file_freshness(path, budget_h).get("status") in (
        truth.STALE, truth.MISSING, truth.INVALID)


def validate_csv(path, required_columns):
    """Integrity check: readable CSV with expected columns and >=1 row."""
    try:
        df = pd.read_csv(path)
    except Exception:
        return False, "unparseable CSV"
    if len(df) < 1:
        return False, "empty file"
    missing = required_columns - set(df.columns)
    if missing:
        return False, f"missing columns: {sorted(missing)}"
    return True, f"OK ({len(df)} rows)"


def rebuild_ml_features(force=True):
    """Rebuild data/ml_features.csv through ml_engine's real pipeline."""
    import ml_engine
    result = {
        "asset": "ml_features.csv",
        "rebuilt": False,
        "network": "none",
        "error": None,
    }
    prev = truth.file_freshness(ML_FEATURES, truth.DAILY_CACHE_FRESHNESS_H)
    result["previous_status"] = prev["status"]

    if not force and prev["status"] == truth.REAL:
        ok, note = validate_csv(ML_FEATURES, ML_FEATURES_COLUMNS)
        if ok:
            result.update(status=truth.REAL, rebuilt=False, note="already fresh")
            return result
        # fresh mtime but corrupt content -> treat as CORRUPT, rebuild

    df, meta = ml_engine.build_features(force=True)
    if df is None:
        result.update(status=meta.get("previous_status", truth.STALE),
                      rebuilt=False,
                      error=meta.get("error"))
        return result

    ok, note = validate_csv(ML_FEATURES, ML_FEATURES_COLUMNS)
    if not ok:
        result.update(status=truth.STALE, rebuilt=False, error=note)
        return result

    result.update(status=meta.get("status"), rebuilt=True,
                  rows=int(len(df)), note=note,
                  source_freshness=meta.get("source_freshness"))
    return result


def _yahoo_probe(attempts=2):
    """Bounded connectivity probe; no indefinite retries."""
    import multitf
    last_err = None
    for i in range(1, attempts + 1):
        try:
            df = multitf.fetch_intraday("15m", days=5)
            if len(df) > 0:
                return True, f"net OK ({len(df)} probe rows)"
        except Exception as e:
            last_err = str(e)[:120]
        if i < attempts:
            time.sleep(3)
    return False, f"net unavailable: {last_err}"


def rebuild_tf_scan(days=120, attempts=2):
    """Rebuild data/tf_scan.csv through multitf's real scan pipeline.

    Requires Yahoo network. On failure the existing file is left untouched
    and its STALE/MISSING status is preserved.
    """
    result = {
        "asset": "tf_scan.csv",
        "rebuilt": False,
        "network": "required",
        "error": None,
    }
    prev = truth.file_freshness(TF_SCAN, truth.DAILY_CACHE_FRESHNESS_H)
    result["previous_status"] = prev["status"]

    if prev["status"] == truth.REAL:
        ok, note = validate_csv(TF_SCAN, TF_SCAN_COLUMNS)
        if ok:
            result.update(status=truth.REAL, rebuilt=False, note="already fresh")
            return result

    ok, probe = _yahoo_probe(attempts=attempts)
    if not ok:
        result.update(status=prev["status"], rebuilt=False,
                      error=f"network unavailable - cache left {prev['status']}",
                      probe=probe)
        return result

    import multitf
    import strategies as S
    try:
        t0 = time.time()
        grid = S.build_param_grid()
        df = multitf.tf_grid_scan(grid, intervals=("15m", "60m", "1d"),
                                  days=days, progress=True)
        df.to_csv(TF_SCAN, index=False)
        elapsed = round(time.time() - t0, 1)
    except Exception as e:
        result.update(status=prev["status"], rebuilt=False,
                      error=f"scan failed - cache left {prev['status']}: {str(e)[:120]}")
        return result

    ok, note = validate_csv(TF_SCAN, TF_SCAN_COLUMNS)
    if not ok:
        result.update(status=truth.STALE, rebuilt=False, error=note)
        return result

    fresh = truth.file_freshness(TF_SCAN, truth.DAILY_CACHE_FRESHNESS_H)
    result.update(status=fresh["status"], rebuilt=True, rows=int(len(df)),
                  elapsed_s=elapsed, note=note, probe=probe)
    return result


def _print_result(r):
    print(f"\n[{r['asset']}]")
    print(f"  previous_status : {r.get('previous_status')}")
    print(f"  status          : {r.get('status')}")
    print(f"  rebuilt         : {r.get('rebuilt')}")
    if r.get("rows") is not None:
        print(f"  rows            : {r['rows']}")
    if r.get("elapsed_s"):
        print(f"  elapsed_s       : {r['elapsed_s']}")
    if r.get("note"):
        print(f"  integrity       : {r['note']}")
    if r.get("probe"):
        print(f"  network         : {r['probe']}")
    if r.get("error"):
        print(f"  error           : {r['error']}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Rebuild derived caches through real pipelines")
    ap.add_argument("--only", choices=("ml_features", "tf_scan"), default=None)
    ap.add_argument("--days", type=int, default=120, help="tf_scan lookback days")
    args = ap.parse_args()

    print("=== Cache Rebuild (P-15) ===")
    print(f"Time: {dt.datetime.now().strftime('%d %b %Y | %H:%M:%S IST')}")
    for entry in truth.asset_freshness_report():
        if entry["path"] in (ML_FEATURES, TF_SCAN):
            print(f"  {entry['path']}: {entry['status']} (age {entry['age_h']}h)")

    results = []
    if args.only in (None, "ml_features"):
        r = rebuild_ml_features()
        _print_result(r)
        results.append(r)
    if args.only in (None, "tf_scan"):
        r = rebuild_tf_scan(days=args.days)
        _print_result(r)
        results.append(r)

    final = truth.asset_freshness_report()
    print("\n--- post-rebuild freshness ---")
    for entry in final:
        if entry["path"] in (ML_FEATURES, TF_SCAN):
            print(f"  {entry['path']}: {entry['status']} (age {entry['age_h']}h)")

    bad = [r["asset"] for r in results if r.get("status") != truth.REAL]
    if bad:
        print(f"\nREBUILD INCOMPLETE for: {', '.join(bad)} (left stale/missing, not fabricated)")
        return 1
    print("\nALL TARGET CACHES FRESH")
    return 0


if __name__ == "__main__":
    sys.exit(main())
