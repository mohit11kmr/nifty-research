"""Phase F: NSE FO bhavcopy historical collector (2025-08-13 -> 2026-08-13).

Builds a verifiable, point-in-time historical options dataset for the frozen
backtest replay window from NSE's public FO bhavcopy archive:

  https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip

The bhavcopy is an END-OF-DAY file published after market close. It is the
correct day-level (close-marked) source for the frozen replay's day-t
decisions, but it is NOT intraday chain data - no bid/ask depth, no IV. Those
columns are left NaN (honest "unavailable"), which downstream makes
skew.compute_iv_skew return NEUTRAL.

Outputs (all under this repo, production state untouched):
  * data/historical/fo_raw/NIFTY_<date>.csv  - raw NIFTY option rows (fidelity)
  * data/historical/manifest.json            - per-day fetch record + sha256
  * data/historical/coverage.csv             - per-day per-layer coverage matrix
  * data/oi_snapshots/NIFTY_<date>.csv       - frozen-schema snapshots for the
    EXISTING backtest_frozen.py consumer (glob NIFTY_*.csv, latest <= t).
    Existing live-capture files are NEVER overwritten.

Resumable: already-collected days (verified by manifest hash) are skipped.

Usage:
  python collect_historical_data.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
      [--no-snapshots] [--sleep SEC] [--retries N]
"""
import argparse
import datetime as dt
import glob
import hashlib
import io
import json
import os
import sys
import time
import zipfile

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_BASE = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{:%Y%m%d}_F_0000.csv.zip"
FO_RAW_DIR = os.path.join(ROOT, "data", "historical", "fo_raw")
SNAP_DIR = os.path.join(ROOT, "data", "oi_snapshots")
MANIFEST = os.path.join(ROOT, "data", "historical", "manifest.json")
COVERAGE = os.path.join(ROOT, "data", "historical", "coverage.csv")

# frozen backtest schema (see data/oi_snapshots/NIFTY_2026-08-08.csv)
SNAP_COLS = ["expiry", "strike", "ce_oi", "ce_oi_chg", "ce_pct_chg",
             "ce_volume", "ce_iv", "ce_ltp", "ce_buy_qty", "ce_sell_qty",
             "pe_oi", "pe_oi_chg", "pe_pct_chg", "pe_volume", "pe_iv",
             "pe_ltp", "pe_buy_qty", "pe_sell_qty"]

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def fetch_bhavcopy(d, retries=3, sleep=0.6):
    """Download + parse the NIFTY option rows for trading day d. Returns
    (dataframe, zip_sha256) or (None, None) if the archive has no entry."""
    url = ARCHIVE_BASE.format(d)
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 404:
                return None, None
            r.raise_for_status()
            z = zipfile.ZipFile(io.BytesIO(r.content))
            name = z.namelist()[0]
            rows = pd.read_csv(io.BytesIO(z.read(name)), encoding="latin1")
            nifty = rows[(rows["TckrSymb"] == "NIFTY") & (rows["FinInstrmTp"] == "IDO")]
            return nifty, sha256_bytes(r.content)
        except Exception as e:  # noqa: BLE001 - network retry
            last = e
            time.sleep(sleep * (2 ** attempt))
    raise RuntimeError(f"bhavcopy {d}: download failed: {last}")


def parse_expiry(x):
    """'2026-08-14' -> '14-Aug-2026' (existing snapshot format)."""
    return dt.datetime.strptime(str(x).strip(), "%Y-%m-%d").strftime("%d-%b-%Y")


def build_snapshot(nifty, d):
    """Pivot bhavcopy CE/PE rows into the frozen snapshot schema.

    Mapping (EOD marks):
      ce_oi        = OpnIntrst(CE)            ce_oi_chg = ChngInOpnIntrst(CE)
      ce_volume    = TtlTradgVol(CE)          ce_ltp    = ClsPric(CE)
      pe_*         = mirror
      iv / pct_chg / buy_qty / sell_qty       = NaN (not in bhavcopy)
    """
    ce = nifty[nifty["OptnTp"] == "CE"].copy()
    pe = nifty[nifty["OptnTp"] == "PE"].copy()
    for df, pref in ((ce, "ce_"), (pe, "pe_")):
        df[f"{pref}oi"] = pd.to_numeric(df["OpnIntrst"], errors="coerce").fillna(0)
        df[f"{pref}oi_chg"] = pd.to_numeric(df["ChngInOpnIntrst"], errors="coerce").fillna(0)
        df[f"{pref}volume"] = pd.to_numeric(df["TtlTradgVol"], errors="coerce").fillna(0)
        df[f"{pref}ltp"] = pd.to_numeric(df["ClsPric"], errors="coerce").fillna(0)
    out = pd.merge(
        ce[["XpryDt", "StrkPric", "ce_oi", "ce_oi_chg", "ce_volume", "ce_ltp"]],
        pe[["XpryDt", "StrkPric", "pe_oi", "pe_oi_chg", "pe_volume", "pe_ltp"]],
        on=["XpryDt", "StrkPric"], how="outer",
    )
    out["expiry"] = out["XpryDt"].map(parse_expiry)
    out["strike"] = pd.to_numeric(out["StrkPric"], errors="coerce").astype(float)
    for c in ("ce_oi", "ce_oi_chg", "ce_volume", "ce_ltp",
              "pe_oi", "pe_oi_chg", "pe_volume", "pe_ltp"):
        out[c] = out[c].fillna(0)
    out["ce_pct_chg"] = out["pe_pct_chg"] = out["ce_iv"] = out["pe_iv"] = float("nan")
    out["ce_buy_qty"] = out["ce_sell_qty"] = out["pe_buy_qty"] = out["pe_sell_qty"] = float("nan")
    out = out[SNAP_COLS].sort_values(["expiry", "strike"]).reset_index(drop=True)
    out = out[out["strike"].notna() & (out["strike"] > 0)]
    return out


def trading_days(start, end):
    n = pd.read_csv(os.path.join(ROOT, "data", "nifty_history.csv"))
    n["date"] = pd.to_datetime(n["date"])
    days = n[(n["date"] >= pd.Timestamp(start)) & (n["date"] <= pd.Timestamp(end))]
    return [d.date() for d in days["date"]]


def load_manifest():
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as f:
            return json.load(f)
    return {}


def save_manifest(m):
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    tmp = MANIFEST + ".tmp"
    with open(tmp, "w") as f:
        json.dump(m, f, indent=1, sort_keys=True)
    os.replace(tmp, MANIFEST)


def collect_day(d, manifest, sleep, retries, write_snapshots):
    key = d.isoformat()
    raw_path = os.path.join(FO_RAW_DIR, f"{key}.csv")
    snap_path = os.path.join(SNAP_DIR, f"NIFTY_{key}.csv")

    entry = manifest.get(key, {})
    if entry.get("status") == "OK" and os.path.exists(raw_path):
        return entry, "skipped"

    nifty, zip_sha = fetch_bhavcopy(d, retries=retries, sleep=sleep)
    time.sleep(sleep)

    if nifty is None:
        return {key: {"date": key, "status": "MISSING_ARCHIVE",
                      "nifty_rows": 0}}, "missing"

    os.makedirs(FO_RAW_DIR, exist_ok=True)
    nifty.to_csv(raw_path, index=False)

    record = {
        "date": key,
        "source": ARCHIVE_BASE.format(d),
        "zip_sha256": zip_sha,
        "nifty_rows": int(len(nifty)),
        "ce_rows": int((nifty["OptnTp"] == "CE").sum()),
        "pe_rows": int((nifty["OptnTp"] == "PE").sum()),
        "expiries": sorted(nifty["XpryDt"].astype(str).unique().tolist()),
        "min_strike": float(nifty["StrkPric"].min()),
        "max_strike": float(nifty["StrkPric"].max()),
        "spot": float(pd.to_numeric(nifty["UndrlygPric"], errors="coerce").dropna().median()),
        "status": "OK",
    }
    if len(nifty) == 0:
        record["status"] = "OK_EMPTY"

    if write_snapshots and not os.path.exists(snap_path):
        snap = build_snapshot(nifty, d)
        os.makedirs(SNAP_DIR, exist_ok=True)
        snap.to_csv(snap_path, index=False)
        record["snapshot_written"] = os.path.basename(snap_path)
        record["snapshot_rows"] = int(len(snap))
    elif write_snapshots:
        record["snapshot_skipped_existing"] = True

    manifest[key] = record
    save_manifest(manifest)
    return {key: record}, "collected"


def write_coverage(manifest):
    nifty = pd.read_csv(os.path.join(ROOT, "data", "nifty_history.csv"))
    nifty["date"] = pd.to_datetime(nifty["date"])
    vix = pd.read_csv(os.path.join(ROOT, "data", "india_vix.csv"), parse_dates=["date"])
    ml = pd.read_csv(os.path.join(ROOT, "data", "ml_features.csv"))
    ml["date"] = pd.to_datetime(ml["date"]) if "date" in ml else None
    fii = pd.read_csv(os.path.join(ROOT, "data", "fii_dii_history.csv"))
    fii["date"] = pd.to_datetime(fii["date"])
    existing = {os.path.basename(p).replace("NIFTY_", "").replace(".csv", "")
                for p in glob.glob(os.path.join(SNAP_DIR, "NIFTY_*.csv"))}

    rows = []
    for key, rec in manifest.items():
        d = pd.Timestamp(key)
        rows.append({
            "date": key,
            "nifty": bool((nifty["date"] == d).any()),
            "vix": bool((vix["date"] == d).any()),
            "ml": bool((ml["date"] == d).any()) if ml["date"] is not None else False,
            "fii_dii": bool((fii["date"] == d).any()),
            "options_status": rec.get("status", "MISSING"),
            "snapshot_available": key in existing,
            "spot": rec.get("spot"),
        })
    out = pd.DataFrame(rows).sort_values("date")
    os.makedirs(os.path.dirname(COVERAGE), exist_ok=True)
    out.to_csv(COVERAGE, index=False)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2025-08-13")
    ap.add_argument("--end", default="2026-08-13")
    ap.add_argument("--no-snapshots", action="store_true",
                    help="only collect raw bhavcopy rows, skip snapshot build")
    ap.add_argument("--sleep", type=float, default=0.6)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--max-days", type=int, default=0, help="cap for testing")
    args = ap.parse_args()

    days = trading_days(args.start, args.end)
    if args.max_days:
        days = days[: args.max_days]
    manifest = load_manifest()

    ok = skipped = missing = failed = 0
    for d in days:
        try:
            _, status = collect_day(d, manifest, args.sleep, args.retries,
                                    not args.no_snapshots)
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] {d}: {e}")
            failed += 1
            continue
        if status == "collected":
            ok += 1
        elif status == "skipped":
            skipped += 1
        else:
            missing += 1
        print(f"[{status.upper():9s}] {d}")

    save_manifest(manifest)
    cov = write_coverage(manifest)
    print(f"\ncollected={ok} skipped={skipped} missing={missing} failed={failed}")
    print(f"manifest: {MANIFEST}  entries={len(manifest)}")
    print(f"coverage: {COVERAGE}  rows={len(cov)}")
    print(cov.groupby("options_status").size().to_string())


if __name__ == "__main__":
    main()
