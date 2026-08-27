"""DATA EXPANSION v2 — Deep Historical Market Data Collector + Angel One SmartAPI.

MEASUREMENT / DATA-ACQUISITION ONLY. This module never:
  * modifies strategy, thresholds, or any strategies/*.yaml
  * writes to ground_truth.db / paper_account.json / data/oi_snapshots /
    research.db / any verified live dataset file
  * places orders or calls any Angel One trading endpoint
  * prints secrets (tokens, PIN, TOTP, API keys)
  * fabricates data (missing -> MISSING, never ESTIMATED-as-REAL)
  * purchases paid data

Canonical layout (new, isolated under data/historical/):
  raw/          immutable source-derived copies (verbatim extraction)
  normalized/   canonical project schema (provenance + quality tagged)
  quarantine/   uncertain / conflicting / unverified
  manifests/    per-dataset manifest + production fingerprint snapshots

CLI:
  python collect_historical_data_deep.py discover
  python collect_historical_data_deep.py audit
  python collect_historical_data_deep.py angelone-capabilities
  python collect_historical_data_deep.py collect --kind <dataset> [--start --end --max-days]
  python collect_historical_data_deep.py validate [--kind]
  python collect_historical_data_deep.py coverage
  python collect_historical_data_deep.py calendar [--start --end]
  python collect_historical_data_deep.py backfill-special [--days ...]
  python collect_historical_data_deep.py align [--start --end]
  python collect_historical_data_deep.py manifest
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
import time
import zipfile

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(ROOT, "data", "historical")
RAW = os.path.join(HIST, "raw")
NORM = os.path.join(HIST, "normalized")
QUAR = os.path.join(HIST, "quarantine")
MANI = os.path.join(HIST, "manifests")
os.makedirs(RAW, exist_ok=True)
os.makedirs(NORM, exist_ok=True)
os.makedirs(QUAR, exist_ok=True)
os.makedirs(MANI, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

# --------------------------------------------------------------------------
# Endpoints (verified 14-Aug-2026 via live HTTP probes; UNVERIFIED flagged)
# --------------------------------------------------------------------------
EP = {
    "udiff_bhavcopy": "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{YYYYMMDD}_F_0000.csv.zip",
    "participant_oi": "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{DDMMYYYY}.csv",
    "participant_vol": "https://nsearchives.nseindia.com/content/nsccl/fao_participant_vol_{DDMMYYYY}.csv",
    "fii_stats": "https://nsearchives.nseindia.com/content/fo/fii_stats_{DD-Mon-YYYY}.xls",
    "ind_close_all": "https://nsearchives.nseindia.com/content/indices/ind_close_all_{DDMMYYYY}.csv",
    "fiidii_trade": "https://www.nseindia.com/api/fiidiiTradeNse",
    "vix_history": "https://www.nseindia.com/api/historicalOR/vixhistory?from={from}&to={to}",
    "focpv": "https://www.nseindia.com/api/historicalOR/foCPV?symbol={sym}&instrument={inst}&expiry={expiry}&optionType={ot}&from={from}&to={to}",
    "indices_history": "https://www.nseindia.com/api/historicalOR/indicesHistory?indexType={index}&from={from}&to={to}",
    "angel_master": "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json",
}

# Provenance / quality vocab
PROVENANCES = ("REAL", "CACHED_REAL", "ESTIMATED", "SIMULATED", "UNKNOWN")
QUALITIES = ("A", "B", "C", "D", "E")

MANIFEST_FIELDS = ["dataset", "source", "source_url", "retrieved_at",
                   "coverage_start", "coverage_end", "granularity", "format",
                   "sha256", "provenance", "quality"]

INDEX_EOD_COLS = ["date", "symbol", "open", "high", "low", "close", "volume",
                  "source", "source_url", "retrieved_at", "raw_file_hash",
                  "availability_time", "provenance", "quality"]
VIX_COLS = ["date", "open", "high", "low", "close", "source", "source_url",
            "retrieved_at", "raw_file_hash", "provenance", "quality"]
OPTIONS_EOD_COLS = ["date", "underlying", "instrument_type", "expiry", "strike",
                    "option_type", "open", "high", "low", "close",
                    "settle_price", "underlying_price", "volume", "turnover",
                    "oi", "oi_chg", "lot_size",
                    "source", "source_url", "retrieved_at", "raw_file_hash",
                    "availability_time", "provenance", "quality"]
FII_DII_COLS = ["date", "category", "buy_value_cr", "sell_value_cr",
                "net_value_cr", "source", "source_url", "retrieved_at",
                "raw_file_hash", "provenance", "quality"]
PART_OI_COLS = ["date", "client_type", "instrument_type", "option_type",
                "contracts", "value_cr", "source", "source_url",
                "retrieved_at", "raw_file_hash", "provenance", "quality"]

SCHEMAS = {
    "index_eod": INDEX_EOD_COLS,
    "vix": VIX_COLS,
    "options_eod": OPTIONS_EOD_COLS,
    "fiidii": FII_DII_COLS,
    "participant_oi": PART_OI_COLS,
}


# --------------------------------------------------------------------------
# Primitive helpers
# --------------------------------------------------------------------------
def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def now_iso():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def http_get(url, timeout=30, retries=3, sleep=0.5, session=None, **kw):
    """GET with retry/backoff; returns requests.Response or raises."""
    s = session or requests
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = s.get(url, headers=dict(UA, **kw.pop("headers", {})),
                      timeout=timeout, **kw)
            if r.status_code in (200,):
                return r
            if r.status_code == 404:
                return r  # caller decides MISSING
            last = f"HTTP {r.status_code}"
            time.sleep(sleep * (2 ** attempt))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(sleep * (2 ** attempt))
    raise RuntimeError(f"GET {url} failed: {last}")


def atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def load_json(path, default=None):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, obj):
    atomic_write(path, json.dumps(obj, indent=1, sort_keys=True))


def manifest_path(dataset):
    return os.path.join(MANI, f"{dataset}.json")


def load_manifest(dataset):
    return load_json(manifest_path(dataset), {})


def save_manifest(dataset, m):
    save_json(manifest_path(dataset), m)


# NSE official market holidays 2024-2026 (verified against NSE press releases /
# market holiday lists; every date below is a weekday with NO NSE FO bhavcopy =
# market was closed). Used ONLY to classify weekday gaps in the canonical
# calendar; never to override options-EOD trading evidence.
NSE_HOLIDAYS = {
    "2024-01-22": "Ram Temple consecration (special holiday)",
    "2024-01-26": "Republic Day",
    "2024-03-08": "Mahashivratri",
    "2024-03-25": "Holi",
    "2024-03-29": "Good Friday",
    "2024-04-11": "Id-Ul-Fitr",
    "2024-04-17": "Shri Ram Navami",
    "2024-05-01": "Maharashtra Day",
    "2024-05-20": "General Election",
    "2024-06-17": "Bakri Id",
    "2024-07-17": "Muharram",
    "2024-08-15": "Independence Day",
    "2024-10-02": "Gandhi Jayanti",
    "2024-11-15": "Guru Nanak Jayanti",
    "2024-11-20": "Assembly Election",
    "2024-12-25": "Christmas",
    "2025-02-26": "Mahashivratri",
    "2025-03-14": "Holi",
    "2025-03-31": "Id-Ul-Fitr",
    "2025-04-10": "Mahavir Jayanti",
    "2025-04-14": "Dr. B.R. Ambedkar Jayanti",
    "2025-04-18": "Good Friday",
    "2025-05-01": "Maharashtra Day",
    "2025-08-15": "Independence Day",
    "2025-08-27": "Ganesh Chaturthi",
    "2025-10-02": "Gandhi Jayanti",
    "2025-10-22": "Dussehra",
    "2025-11-05": "Diwali (Laxmi Puja)",
    "2025-12-25": "Christmas",
    "2026-01-15": "Pongal",
    "2026-01-26": "Republic Day",
    "2026-03-03": "Mahashivratri",
    "2026-03-26": "Holi",
    "2026-03-31": "Id-Ul-Fitr",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. B.R. Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-28": "Bakri Id",
    "2026-06-26": "Muharram",
}

CALENDAR_COLS = ["date", "session_status", "source_evidence", "source_file",
                 "provenance"]
CALENDAR_PROVENANCES = ("REAL", "OFFICIAL", "SCHEDULE", "UNKNOWN")


def canonical_calendar(start="2024-01-01", end=None):
    """ONE authoritative historical session calendar.

    Source priority (Yahoo is NEVER authoritative):
      1. NSE options EOD evidence   -> raw/bhavcopy/NIFTY_<date>.csv
      2. NSE official holiday list  -> NSE_HOLIDAYS
      3. weekday/weekend schedule   -> only to classify NO_ARCHIVE

    Every date in [start, end] gets exactly one status:
      TRADING_SESSION  - options EOD raw exists (market was open)
      MARKET_HOLIDAY   - on official NSE holiday list, no session
      NO_ARCHIVE       - scheduled closure (weekend) with no session
      UNKNOWN          - weekday with no options evidence and no holiday record
    """
    import glob
    bhav = {os.path.basename(p)[6:16]
            for p in glob.glob(os.path.join(RAW, "bhavcopy", "NIFTY_*.csv"))}
    rows = []
    d = pd.Timestamp(start).date()
    last = pd.Timestamp(end or dt.date.today().isoformat()).date()
    while d <= last:
        iso = d.isoformat()
        if iso in bhav:
            rows.append({"date": iso, "session_status": "TRADING_SESSION",
                         "source_evidence": "NSE options EOD (UDiFF bhavcopy)",
                         "source_file": f"data/historical/raw/bhavcopy/NIFTY_{iso}.csv",
                         "provenance": "REAL"})
        elif iso in NSE_HOLIDAYS:
            rows.append({"date": iso, "session_status": "MARKET_HOLIDAY",
                         "source_evidence": f"NSE official holiday: {NSE_HOLIDAYS[iso]}",
                         "source_file": "NSE_OFFICIAL_HOLIDAY_LIST",
                         "provenance": "OFFICIAL"})
        elif d.weekday() >= 5:
            rows.append({"date": iso, "session_status": "NO_ARCHIVE",
                         "source_evidence": "weekend - scheduled market closure",
                         "source_file": "WEEKEND_SCHEDULE",
                         "provenance": "SCHEDULE"})
        else:
            rows.append({"date": iso, "session_status": "UNKNOWN",
                         "source_evidence": "weekday: no options EOD evidence and not on NSE holiday list",
                         "source_file": "NONE",
                         "provenance": "UNKNOWN"})
        d += dt.timedelta(days=1)
    return pd.DataFrame(rows, columns=CALENDAR_COLS)


def canonical_session_dates(start="2024-01-01", end=None):
    """Sorted list of TRADING_SESSION dates from the canonical calendar."""
    cal = canonical_calendar(start, end)
    return sorted(cal.loc[cal["session_status"] == "TRADING_SESSION", "date"])


def calendar_hash(cal):
    """Deterministic SHA256 of sorted canonical session rows.

    Only TRADING_SESSION rows participate (per DATA-ALIGNMENT-01 section 14);
    the rows are serialized as compact JSON so any change to evidence, status
    or ordering changes the hash. Same calendar -> same hash.
    """
    sess = cal.loc[cal["session_status"] == "TRADING_SESSION"]
    payload = "\n".join(
        json.dumps(dict(row), sort_keys=True, separators=(",", ":"))
        for _, row in sess.sort_values("date").iterrows())
    return hashlib.sha256(payload.encode()).hexdigest()


def stable_content_hash(df, exclude=("retrieved_at",)):
    """Deterministic hash over stable columns of a normalized dataset.

    Excludes volatile metadata (retrieved_at) so re-normalizing an unchanged
    raw archive produces the SAME hash (reproducibility / idempotency).
    pandas hash_pandas_object is value-based and stable across runs; row order
    is the pipeline's deterministic order (dates sorted ascending).
    """
    cols = [c for c in df.columns if c not in exclude]
    if not len(df):
        return hashlib.sha256(b"").hexdigest()
    sub = df[cols]
    row_hash = pd.util.hash_pandas_object(sub, index=False)
    return hashlib.sha256(row_hash.values.tobytes()).hexdigest()


def trading_days(start, end):
    """Trading days between start/end. Nifty-history dates are precise
    (holiday-aware) where they cover the span; outside that span weekdays are
    used (any holiday there surfaces as MISSING_ARCHIVE on 404, never guessed).

    NOTE: this Yahoo-derived helper is retained for the original collectors;
    the AUTHORITATIVE day list is canonical_calendar()."""
    start_t, end_t = pd.Timestamp(start), pd.Timestamp(end)
    p = os.path.join(ROOT, "data", "nifty_history.csv")
    n = pd.read_csv(p, parse_dates=["date"])
    n = n[(n["date"] >= start_t) & (n["date"] <= end_t)]
    nifty_dates = {d.date().isoformat() for d in n["date"]}
    span_start = min(nifty_dates) if nifty_dates else None
    span_end = max(nifty_dates) if nifty_dates else None
    out = []
    d = start_t.date()
    while d <= end_t.date():
        iso = d.isoformat()
        if d.weekday() >= 5:
            d += dt.timedelta(days=1)
            continue
        if span_start is not None and span_start <= iso <= span_end:
            if iso in nifty_dates:
                out.append(iso)
        else:
            out.append(iso)
        d += dt.timedelta(days=1)
    return out


# --------------------------------------------------------------------------
# Provenance / schema / point-in-time / conflict / staleness (pure, tested)
# --------------------------------------------------------------------------
def validate_schema(df, dataset, strict=True):
    cols = SCHEMAS[dataset]
    missing = [c for c in cols if c not in df.columns]
    if missing and strict:
        raise ValueError(f"{dataset}: missing columns {missing}")
    extra = [c for c in df.columns if c not in cols]
    if extra:
        df = df[cols]
    return df


def check_provenance(provenance, quality):
    if provenance not in PROVENANCES:
        raise ValueError(f"provenance {provenance!r} not in {PROVENANCES}")
    if quality not in QUALITIES:
        raise ValueError(f"quality {quality!r} not in {QUALITIES}")
    if provenance in ("ESTIMATED", "SIMULATED", "UNKNOWN") and quality not in ("C", "D", "E"):
        raise ValueError("ESTIMATED/SIMULATED/UNKNOWN cannot be graded A/B canonical")
    return True


def point_in_time_filter(df, t, time_col="availability_time"):
    """Only rows available at or before decision time t may be used."""
    if time_col not in df.columns:
        raise ValueError(f"{time_col} missing for point-in-time filtering")
    t = pd.Timestamp(t)
    ts = pd.to_datetime(df[time_col], errors="coerce")
    return df[ts <= t].reset_index(drop=True)


def detect_future_timestamps(df, max_ts, ts_cols=("availability_time", "retrieved_at")):
    """Flag rows whose recorded timestamps are in the future (lookahead).

    Normalizes timezone-awareness (naive == local wall clock) on both sides so
    ISO timestamps carrying an explicit offset (e.g. +05:30) compare cleanly.
    """
    issues = []
    max_d = pd.Timestamp(max_ts).date()
    for c in ts_cols:
        if c in df.columns:
            ts = pd.to_datetime(df[c], errors="coerce")
            if getattr(ts.dt, "tz", None) is not None:
                ts = ts.dt.tz_localize(None)
            bad = df[ts.dt.date > max_d]
            if len(bad):
                issues.append({"column": c, "count": int(len(bad)),
                               "example": bad[c].iloc[0]})
    return issues


def classify_conflict(a, b, fields=("close", "oi", "volume"), tol=0.0):
    """Compare two sources of the same (date, key). Returns MATCH /
    MINOR_DIFFERENCE / CONFLICT. Never silently picks a source."""
    comparable = False
    verdicts = []
    for f in fields:
        if f not in a or f not in b:
            continue
        comparable = True
        x, y = a.get(f), b.get(f)
        if x is None or y is None or (isinstance(x, float) and pd.isna(x)) \
                or (isinstance(y, float) and pd.isna(y)):
            continue
        if abs(float(x) - float(y)) <= tol:
            continue
        verdicts.append("CONFLICT" if tol == 0.0 else "MINOR_DIFFERENCE")
    if not comparable:
        return "INCOMPARABLE"
    if verdicts:
        return verdicts[0]
    return "MATCH"


def dedupe(df, keys, keep="last"):
    if not keys:
        return df
    return df.drop_duplicates(subset=keys, keep=keep).reset_index(drop=True)


def stale_status(cached_mtime, market_open=False, max_age_hours=24):
    """Cached value must expose age; never let stale cache masquerade as live."""
    if cached_mtime is None:
        return "MISSING"
    age = time.time() - cached_mtime
    hours = age / 3600.0
    if market_open and hours > 5 / 60.0:
        return "STALE"
    if not market_open and hours > max_age_hours:
        return "STALE"
    return "FRESH"


# --------------------------------------------------------------------------
# Angel One capability table (verified 14-Aug-2026 from official docs/forum)
# --------------------------------------------------------------------------
ANGELONE_CAPABILITIES = [
    {"capability": "Authentication (API key + client + PIN + TOTP)", "status": "SUPPORTED",
     "detail": "loginByPassword -> jwtToken/refreshToken/feedToken; JWT valid till midnight (FAQ Q7)"},
    {"capability": "Instrument / scrip master download", "status": "SUPPORTED",
     "detail": "OpenAPIScripMaster.json (~155K records, live contracts only, refreshed daily)"},
    {"capability": "Historical candles getCandleData (NSE/NFO/BSE/BFO/MCX)",
     "status": "SUPPORTED", "detail": "1m/3m/5m/10m/15m/30m/1h/1d; max days/req 1m=30, 1d=2000; NSE F&O daily back to 2000, intraday 2016 (community reports ~1 month actual intraday depth)"},
    {"capability": "Historical candles for EXPIRED F&O contracts", "status": "NOT_SUPPORTED",
     "detail": "official forum t/5220, t/5507, t/4012: no candles for expired contracts; tokens recycled after expiry"},
    {"capability": "Historical OI (getOIData)", "status": "SUPPORTED",
     "detail": "new endpoint, live F&O contracts only; no expired-contract OI"},
    {"capability": "Current OI via getQuote", "status": "SUPPORTED",
     "detail": "opnInterest field in FULL quote mode; up to 50 tokens/request"},
    {"capability": "Option chain API", "status": "UNKNOWN",
     "detail": "undocumented getOptionChain/getOptionExpiryDate (Nov-2025 forum); unstable during market hours; documented substitute optionGreek"},
    {"capability": "WebSocket SmartWebSocketV2", "status": "SUPPORTED",
     "detail": "live streaming only; 3 conns / 1000 tokens; exchange nse_fo; no historical via WS"},
    {"capability": "Rate limits", "status": "SUPPORTED",
     "detail": "getCandleData 3 r/s, 150/min, 5000/hr; quote 10 r/s"},
    {"capability": "Trading endpoints (placeOrder etc.)", "status": "SUPPORTED",
     "detail": "EXIST - deliberately NOT used by this phase (read-only)"},
]


# --------------------------------------------------------------------------
# Collectors (write ONLY under data/historical/raw + normalized + manifests)
# --------------------------------------------------------------------------
def _today_days(start, end, max_days):
    days = trading_days(start, end)
    if max_days:
        days = days[:max_days]
    return days


def collect_bhavcopy_backfill(start="2024-01-01", end="2025-08-12", sleep=0.3,
                              retries=3, max_days=0):
    """UDiFF FO bhavcopy backfill -> raw/bhavcopy/NIFTY_<date>.csv (NIFTY rows,
    verbatim from zip) + manifest + normalized options_eod CSV."""
    m = load_manifest("bhavcopy")
    m.setdefault("days", {})
    days = _today_days(start, end, max_days)
    ok = skipped = missing = failed = 0
    for d in days:
        rec = m["days"].get(d)
        raw_path = os.path.join(RAW, "bhavcopy", f"NIFTY_{d}.csv")
        if rec and rec.get("status") == "OK" and os.path.exists(raw_path) \
                and sha256_file(raw_path) == rec.get("raw_sha256"):
            skipped += 1
            continue
        url = EP["udiff_bhavcopy"].format(YYYYMMDD=d.replace("-", ""))
        try:
            r = http_get(url, timeout=30, retries=retries, sleep=sleep)
        except Exception:
            failed += 1
            continue
        time.sleep(sleep)
        if r.status_code == 404:
            m["days"][d] = {"date": d, "status": "MISSING_ARCHIVE", "url": url}
            missing += 1
            continue
        try:
            z = zipfile.ZipFile(io.BytesIO(r.content))
            name = z.namelist()[0]
            rows = pd.read_csv(io.BytesIO(z.read(name)), encoding="latin1")
            nifty = rows[(rows["TckrSymb"] == "NIFTY") & (rows["FinInstrmTp"] == "IDO")]
        except Exception as e:  # noqa: BLE001
            m["days"][d] = {"date": d, "status": "PARSE_ERROR", "error": str(e)[:120]}
            failed += 1
            continue
        nifty.to_csv(raw_path, index=False)
        m["days"][d] = {"date": d, "status": "OK" if len(nifty) else "OK_EMPTY",
                        "nifty_rows": int(len(nifty)),
                        "zip_sha256": sha256_bytes(r.content),
                        "raw_sha256": sha256_file(raw_path),
                        "url": url}
        ok += 1
    save_manifest("bhavcopy", m)
    out, report = normalize_bhavcopy()
    return {"collected": ok, "skipped": skipped, "missing": missing,
            "failed": failed, "normalized_rows": int(len(out)),
            "quality": {k: report[k] for k in
                        ("ce_rows", "pe_rows", "trading_days", "unique_expiries",
                         "duplicates_removed", "conflicts_quarantined")}}


def collect_frozen_reuse(verbose=False):
    """Reuse the Phase F UDiFF raw archive (data/historical/fo_raw/NIFTY_<d>.csv
    is actually <d>.csv) for the frozen 2025-08-13..2026-08-13 window: copy into
    raw/bhavcopy/NIFTY_<date>.csv WITHOUT re-downloading, hash each file, and
    record OK entries in the bhavcopy manifest. Idempotent: skips dates whose
    target already exists with a matching hash."""
    fo_dir = os.path.join(HIST, "fo_raw")
    if not os.path.isdir(fo_dir):
        return {"copied": 0, "skipped": 0, "error": "fo_raw missing"}
    m = load_manifest("bhavcopy")
    m.setdefault("days", {})
    copied = skipped = 0
    for f in sorted(os.listdir(fo_dir)):
        if not f.endswith(".csv"):
            continue
        d = f[:-4]
        src = os.path.join(fo_dir, f)
        dst = os.path.join(RAW, "bhavcopy", f"NIFTY_{d}.csv")
        if os.path.exists(dst) and sha256_file(dst) == sha256_file(src):
            skipped += 1
            continue
        with open(src, "rb") as fin, open(dst, "wb") as fout:
            fout.write(fin.read())
        rec = {"date": d, "status": "OK", "nifty_rows": 0,
               "zip_sha256": None,
               "raw_sha256": sha256_file(dst),
               "url": EP["udiff_bhavcopy"].format(YYYYMMDD=d.replace("-", "")),
               "reused_from": "phase_f_fo_raw"}
        m["days"][d] = rec
        copied += 1
        if verbose:
            print(f"[frozen-reuse] {d}")
    save_manifest("bhavcopy", m)
    return {"copied": copied, "skipped": skipped}


UDIFF_ALIASES = {
    "open": ("OpnPric",),
    "high": ("HghPric", "HighPric"),
    "low": ("LwPric", "LowPric"),
    "close": ("ClsPric",),
    "settle_price": ("SttlmPric", "SetlPric"),
    "volume": ("TtlTradgVol",),
    "turnover": ("TtlTrfVal",),
    "oi": ("OpnIntrst",),
    "oi_chg": ("ChngInOpnIntrst",),
    "underlying_price": ("UndrlygPric",),
    "lot_size": ("NewBrdLotQty",),
}

NUMERIC_OPTION_FIELDS = ["open", "high", "low", "close", "settle_price",
                         "underlying_price", "volume", "turnover", "oi",
                         "oi_chg", "lot_size"]

# oi_chg is the signed daily change in OI - legitimately negative, excluded
NONNEG_OPTION_FIELDS = [c for c in NUMERIC_OPTION_FIELDS if c != "oi_chg"]


def normalize_udiff_day(df, d, raw_hash=None, url="", source="NSE_UDiFF_BHAVCOPY"):
    """Map one day's raw UDiFF NIFTY IDO rows to the canonical options schema.

    Returns (norm, quarantine). Malformed rows are quarantined, never silently
    dropped. provenance/quality default to REAL/A for primary NSE data.
    """
    out = df.copy()
    out["date"] = d
    out["underlying"] = "NIFTY"
    out["instrument_type"] = "OPTIDX"
    out["expiry"] = pd.to_datetime(out["XpryDt"], errors="coerce").dt.date
    out["strike"] = pd.to_numeric(_col_or(out, "StrkPric"), errors="coerce")
    out["option_type"] = out.get("OptnTp")
    for dst, aliases in UDIFF_ALIASES.items():
        col = _col_or(out, *aliases)
        out[dst] = pd.to_numeric(col, errors="coerce") if col is not None else pd.NA
    out["source"] = source
    out["source_url"] = url
    out["retrieved_at"] = now_iso()
    out["raw_file_hash"] = raw_hash or ""
    out["availability_time"] = f"{d} 23:59:59"
    out["provenance"] = "REAL"
    out["quality"] = "A"
    valid = (
        out["expiry"].notna()
        & pd.to_numeric(out["strike"], errors="coerce").gt(0)
        & out["option_type"].isin(["CE", "PE"])
        & (out[NONNEG_OPTION_FIELDS].fillna(0) >= 0).all(axis=1)
    )
    norm = out[valid][OPTIONS_EOD_COLS]
    quar = out[~valid].copy()
    if len(quar):
        quar["quarantine_reason"] = _quarantine_reasons(quar)
        quar["quarantine_source"] = "normalize_udiff_day"
    return norm.reset_index(drop=True), quar.reset_index(drop=True)


def _quarantine_reasons(df):
    """Per-row human-readable reason strings for invalid UDiFF rows."""
    reasons = []
    for _, row in df.iterrows():
        parts = []
        if pd.isna(row["expiry"]):
            parts.append("expiry_na")
        if pd.isna(row["strike"]) or row["strike"] <= 0:
            parts.append("strike_invalid")
        if row["option_type"] not in ("CE", "PE"):
            parts.append("option_type_invalid")
        for c in NONNEG_OPTION_FIELDS:
            v = row[c]
            if pd.notna(v) and v < 0:
                parts.append(f"{c}_negative")
        reasons.append("|".join(parts) if parts else "invalid")
    return reasons


def detect_conflicts(df, key=("date", "expiry", "strike", "option_type")):
    """Rows sharing a key but disagreeing on any non-key field."""
    if df.empty:
        return pd.DataFrame(columns=df.columns)
    key = list(key)
    cols = [c for c in df.columns if c not in key]
    groups = [g for _, g in df.groupby(key, dropna=False)
              if len(g) > 1 and any(g[c].nunique(dropna=False) > 1 for c in cols)]
    return pd.concat(groups).reset_index(drop=True) if groups \
        else pd.DataFrame(columns=df.columns)


def normalize_bhavcopy(days=None):
    """Rebuild the full normalized options EOD dataset from every raw UDiFF
    file under raw/bhavcopy (idempotent - never depends on the requested
    window, so incremental runs cannot clobber earlier coverage)."""
    import glob
    if days is None:
        days = sorted(os.path.basename(p)[6:16]
                      for p in glob.glob(os.path.join(RAW, "bhavcopy", "NIFTY_*.csv")))
    frames = []
    quarantine = []
    day_status = {}
    for d in days:
        p = os.path.join(RAW, "bhavcopy", f"NIFTY_{d}.csv")
        if not os.path.exists(p):
            day_status[d] = "MISSING_RAW"
            continue
        df = pd.read_csv(p, encoding="latin1")
        url = EP["udiff_bhavcopy"].format(YYYYMMDD=d.replace("-", ""))
        norm, quar = normalize_udiff_day(df, d, sha256_file(p), url)
        frames.append(norm)
        quarantine.append(quar)
        day_status[d] = f"OK:{len(norm)}" if len(norm) else "OK_EMPTY"
    out = pd.concat(frames, ignore_index=True) if frames \
        else pd.DataFrame(columns=OPTIONS_EOD_COLS)
    out = out.sort_values(["date", "expiry", "strike"]).reset_index(drop=True)

    conflicts = detect_conflicts(out)
    conflict_rows = int(len(conflicts))
    if conflict_rows:
        conflict_ids = set(conflicts.index)
        out = out.drop(index=conflict_ids).reset_index(drop=True)
        conflicts = conflicts.assign(
            quarantine_reason="conflict_duplicate_key",
            quarantine_source="normalize_bhavcopy")
        quarantine.append(conflicts)
    exact_dups = int(out.duplicated(subset=["date", "expiry", "strike", "option_type"]).sum())
    out = out.drop_duplicates(subset=["date", "expiry", "strike", "option_type"],
                              keep="last").reset_index(drop=True)

    quar = pd.concat(quarantine, ignore_index=True) if quarantine \
        else pd.DataFrame()
    quar_path = os.path.join(QUAR, "options_eod_quarantine.csv")
    if len(quar):
        quar.to_csv(quar_path, index=False)
    elif os.path.exists(quar_path):
        os.remove(quar_path)
        quar_path = None

    path = os.path.join(NORM, "options_eod_expanded.csv")
    out.to_csv(path, index=False)
    write_dataset_manifest("options_eod_expanded", "NSE_UDiFF_BHAVCOPY",
                           EP["udiff_bhavcopy"], out)
    report = build_options_eod_quality_report(
        out, day_status, quarantine=quar, quar_path=quar_path,
        conflict_rows=conflict_rows, exact_dups=exact_dups)
    return out, report


def build_options_eod_quality_report(out, day_status, quarantine=None,
                                     quar_path=None, conflict_rows=0,
                                     exact_dups=0):
    """Data-quality report over the normalized options EOD dataset + coverage.

    Pure computation over already-built data; writes manifests/options_eod/
    reports only. Never touches production datasets.
    """
    os.makedirs(os.path.join(MANI, "options_eod"), exist_ok=True)
    date_cnt = out["date"].value_counts().to_dict() if len(out) else {}
    ce = int((out["option_type"] == "CE").sum()) if len(out) else 0
    pe = int((out["option_type"] == "PE").sum()) if len(out) else 0
    expiries = sorted({str(e) for e in out["expiry"].dropna().unique()}) if len(out) else []
    quar_rows = int(len(quarantine)) if quarantine is not None else 0
    invalid = {} if quarantine is None or not len(quarantine) else {
        "total": int(len(quarantine)),
        "path": os.path.relpath(quar_path, ROOT) if quar_path else None,
        "reasons": quarantine["quarantine_reason"].value_counts().to_dict(),
    }
    report = {
        "dataset": "options_eod_expanded",
        "generated_at": now_iso(),
        "rows": int(len(out)),
        "ce_rows": ce,
        "pe_rows": pe,
        "unique_expiries": len(expiries),
        "trading_days": len(date_cnt),
        "duplicates_removed": int(exact_dups),
        "conflicts_quarantined": int(conflict_rows),
        "quarantined": invalid,
        "oi_nonzero_rows": int((out["oi"] > 0).sum()) if len(out) else 0,
        "volume_nonzero_rows": int((out["volume"] > 0).sum()) if len(out) else 0,
        "underlying_check": _underlying_crosscheck(out),
    }
    save_json(os.path.join(MANI, "options_eod", "quality_report.json"), report)
    save_json(os.path.join(MANI, "options_eod", "coverage.json"),
              {"generated_at": now_iso(), "days": day_status})
    return report


def _underlying_crosscheck(out):
    """Compare each day's UDiFF underlying_price (median) vs official NSE
    reference closes. Primary reference = ind_close_all (full window overlap);
    nifty_history.csv used as fallback for any day ind_close_all lacks.
    Honest report: best/median/worst % deviation, worst dates listed."""
    if not len(out):
        return {"status": "NO_OPTIONS_DATA"}
    import glob
    ref = {}
    for p in glob.glob(os.path.join(RAW, "vix", "ind_close_all_*.csv")):
        try:
            d = pd.read_csv(p)
        except Exception:  # noqa: BLE001
            continue
        row = d[d["Index Name"].astype(str).str.lower() == "nifty 50"]
        if row.empty:
            continue
        ref[os.path.basename(p)[14:24]] = float(row.iloc[0].get("Closing Index Value", 0))
    if ref:
        try:
            n = pd.read_csv(os.path.join(ROOT, "data", "nifty_history.csv"),
                            parse_dates=["date"])
            n["date"] = n["date"].dt.date.astype(str)
            for d0, c in zip(n["date"], n["close"]):
                ref.setdefault(str(d0), float(c))
        except Exception:  # noqa: BLE001
            pass
    if not ref:
        return {"status": "NO_REFERENCE"}
    daily = out.groupby("date")["underlying_price"].median()
    rows = []
    for d, und in daily.items():
        if d in ref and pd.notna(und) and und > 0:
            rows.append({"date": d, "underlying_price": float(und),
                         "nifty_close": ref[d],
                         "dev_pct": abs(float(und) - ref[d]) / ref[d] * 100.0})
    if not rows:
        return {"status": "NO_OVERLAP"}
    devs = [r["dev_pct"] for r in rows]
    worst = sorted(rows, key=lambda r: -r["dev_pct"])[:5]
    return {"status": "PASS" if max(devs) <= 0.5 else "CHECK",
            "days_checked": len(rows),
            "max_dev_pct": round(max(devs), 6),
            "median_dev_pct": round(float(pd.Series(devs).median()), 6),
            "worst_days": worst}


def collect_vix(start="2024-01-01", end=None, sleep=0.2, retries=3, max_days=0,
                asof=None, days=None):
    """India VIX EOD per-day via ind_close_all (nsearchives, no cookies).

    Pass explicit days= to backfill specific sessions (e.g. the two
    DATA-ALIGNMENT-01 special sessions) instead of the Yahoo-derived list.
    """
    end = end or dt.date.today().isoformat()
    m = load_manifest("vix")
    m.setdefault("days", {})
    days = days if days is not None else _today_days(start, end, max_days)
    ok = skipped = missing = failed = 0
    rows = []
    for d in days:
        rec = m["days"].get(d)
        raw_path = os.path.join(RAW, "vix", f"ind_close_all_{d}.csv")
        if rec and rec.get("status") == "OK" and os.path.exists(raw_path) \
                and sha256_file(raw_path) == rec.get("raw_sha256"):
            skipped += 1
        else:
            url = EP["ind_close_all"].format(DDMMYYYY=d.replace("-", "")[6:8]
                                             + d.replace("-", "")[4:6]
                                             + d.replace("-", "")[0:4])
            try:
                r = http_get(url, timeout=30, retries=retries, sleep=sleep)
            except Exception:
                failed += 1
                continue
            time.sleep(sleep)
            if r.status_code == 404:
                m["days"][d] = {"date": d, "status": "MISSING", "url": url}
                missing += 1
                continue
            with open(raw_path, "wb") as f:
                f.write(r.content)
            m["days"][d] = {"date": d, "status": "OK",
                            "raw_sha256": sha256_file(raw_path), "url": url}
            ok += 1
    save_manifest("vix", m)
    import glob
    days = [os.path.basename(p)[14:24]
            for p in glob.glob(os.path.join(RAW, "vix", "ind_close_all_*.csv"))]
    rows = []
    for d in days:
        p = os.path.join(RAW, "vix", f"ind_close_all_{d}.csv")
        df = pd.read_csv(p)
        row = df[df["Index Name"] == "India VIX"]
        if row.empty:
            continue
        r = row.iloc[0]
        rows.append({"date": d, "open": float(r.get("Open Index Value", 0)),
                     "high": float(r.get("High Index Value", 0)),
                     "low": float(r.get("Low Index Value", 0)),
                     "close": float(r.get("Closing Index Value", 0)),
                     "source": "NSE_IND_CLOSE_ALL", "source_url": "",
                     "retrieved_at": now_iso(),
                     "raw_file_hash": sha256_file(p),
                     "provenance": "REAL", "quality": "A"})
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values("date").reset_index(drop=True)
    path = os.path.join(NORM, "vix_expanded.csv")
    out.to_csv(path, index=False)
    if len(out):
        write_dataset_manifest("vix_expanded", "NSE_IND_CLOSE_ALL",
                               EP["ind_close_all"], out)
    return {"collected": ok, "skipped": skipped, "missing": missing,
            "failed": failed, "normalized_rows": len(out)}


def parse_participant_oi_file(path):
    """Parse a fao_participant_oi_<date>.csv: 1 title line, 1 blank, then a
    header (mixed comma+tab) and rows (Client/DII/FII/Pro/TOTAL). Returns a
    DataFrame or empty on parse failure."""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = [l.rstrip("\n") for l in f]
    data = [l for l in lines if l.strip()][1:]  # drop title line
    if not data:
        return pd.DataFrame()
    header = [c.strip().replace("\t", " ").replace(" ", "_") for c in data[0].split(",")]
    rows = []
    for l in data[1:]:
        parts = l.replace("\t", ",").split(",")
        parts = [p.strip() for p in parts]
        if len(parts) < len(header):
            parts += [""] * (len(header) - len(parts))
        rows.append(parts[: len(header)])
    df = pd.DataFrame(rows, columns=header)
    return df


def _col_or(df, *names):
    for n in names:
        if n in df.columns:
            return df[n]
    return None


def collect_participant_oi(start="2024-01-01", end=None, sleep=0.2, retries=3,
                           max_days=0, days=None):
    """Participant-wise F&O OI per day (nsearchives, no cookies).

    Pass explicit days= to backfill specific sessions (e.g. the two
    DATA-ALIGNMENT-01 special sessions) instead of the Yahoo-derived list.
    """
    end = end or dt.date.today().isoformat()
    m = load_manifest("participant_oi")
    m.setdefault("days", {})
    days = days if days is not None else _today_days(start, end, max_days)
    ok = skipped = missing = failed = 0
    for d in days:
        rec = m["days"].get(d)
        raw_path = os.path.join(RAW, "participant_oi", f"fao_participant_oi_{d}.csv")
        if rec and rec.get("status") == "OK" and os.path.exists(raw_path) \
                and sha256_file(raw_path) == rec.get("raw_sha256"):
            skipped += 1
            continue
        dd = d.replace("-", "")[6:8] + d.replace("-", "")[4:6] + d.replace("-", "")[0:4]
        url = EP["participant_oi"].format(DDMMYYYY=dd)
        try:
            r = http_get(url, timeout=30, retries=retries, sleep=sleep)
        except Exception:
            failed += 1
            continue
        time.sleep(sleep)
        if r.status_code == 404:
            m["days"][d] = {"date": d, "status": "MISSING", "url": url}
            missing += 1
            continue
        with open(raw_path, "wb") as f:
            f.write(r.content)
        m["days"][d] = {"date": d, "status": "OK",
                        "raw_sha256": sha256_file(raw_path), "url": url}
        ok += 1
    save_manifest("participant_oi", m)
    import glob
    days = [os.path.basename(p)[19:29]
            for p in glob.glob(os.path.join(RAW, "participant_oi", "fao_participant_oi_*.csv"))]
    frames = []
    for d in days:
        p = os.path.join(RAW, "participant_oi", f"fao_participant_oi_{d}.csv")
        if not os.path.exists(p):
            continue
        df = parse_participant_oi_file(p)
        if df.empty or "Client_Type" not in df.columns:
            continue
        df["date"] = d
        df["client_type"] = df["Client_Type"]
        df["instrument_type"] = "EQ_DERIVATIVES"
        df["option_type"] = "ALL"
        tl = _col_or(df, "Total_Long_Contracts", "Total_Short_Contracts")
        df["contracts"] = pd.to_numeric(tl, errors="coerce") if tl is not None else pd.NA
        df["value_cr"] = pd.NA
        df["source"] = "NSE_PARTICIPANT_OI"
        df["source_url"] = EP["participant_oi"].format(
            DDMMYYYY=d.replace("-", "")[6:8] + d.replace("-", "")[4:6]
            + d.replace("-", "")[0:4])
        df["retrieved_at"] = now_iso()
        df["raw_file_hash"] = sha256_file(p)
        df["provenance"] = "REAL"
        df["quality"] = "A"
        frames.append(df[PART_OI_COLS])
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    path = os.path.join(NORM, "participant_oi_expanded.csv")
    out.to_csv(path, index=False)
    if len(out):
        write_dataset_manifest("participant_oi_expanded", "NSE_PARTICIPANT_OI",
                               EP["participant_oi"], out)
    return {"collected": ok, "skipped": skipped, "missing": missing,
            "failed": failed, "normalized_rows": len(out)}


def collect_fiidii_trade(max_days=1, sleep=1.0, retries=3):
    """NSE FII/DII cash activity (cookie-bootstrapped API, latest days only)."""
    m = load_manifest("fiidii")
    rows = []
    for i in range(max_days):
        url = EP["fiidii_trade"]
        try:
            r = http_get(url, timeout=30, retries=retries, sleep=sleep)
            payload = r.json()
        except Exception as e:  # noqa: BLE001
            print(f"[fiidii] fetch failed: {e}")
            break
        data = payload.get("data") or []
        if not data:
            break
        d = data[0].get("date", dt.date.today().isoformat())
        rec = m.get(d, {"date": d, "rows": []})
        for it in data:
            rec["rows"].append({"category": it.get("category"),
                                "buy_value_cr": it.get("buyValue"),
                                "sell_value_cr": it.get("sellValue"),
                                "net_value_cr": it.get("netValue")})
        m[d] = rec
        rows = data
        break  # latest day only unless requested
    save_manifest("fiidii", m)
    out = pd.DataFrame([{"date": d, **it} for it in rows])
    path = os.path.join(NORM, "fiidii_expanded.csv")
    out.to_csv(path, index=False) if len(out) else None
    return {"normalized_rows": len(out), "status": "OK" if len(out) else "UNAVAILABLE"}


def write_dataset_manifest(dataset, source, url, df):
    path = os.path.join(NORM, f"{dataset}.csv")
    m = {
        "dataset": dataset, "source": source, "source_url": url,
        "retrieved_at": now_iso(),
        "coverage_start": str(df["date"].min()) if len(df) else None,
        "coverage_end": str(df["date"].max()) if len(df) else None,
        "granularity": "EOD",
        "format": "csv",
        "sha256": sha256_file(path),
        "provenance": "REAL", "quality": "A",
    }
    save_json(manifest_path(f"normalized_{dataset}"), m)
    return m


# --------------------------------------------------------------------------
# DATA-ALIGNMENT-01: canonical NIFTY EOD, alignment, unified frozen manifest
# --------------------------------------------------------------------------
def build_nifty_eod_expanded():
    """Canonical NIFTY 50 EOD from NSE ind_close_all raw files (official).

    Covers every canonical session that has an ind_close_all raw file
    (VIX archive shares the same source). Full provenance preserved;
    production data/nifty_history.csv is never modified here.
    """
    import glob
    rows = []
    for p in sorted(glob.glob(os.path.join(RAW, "vix", "ind_close_all_*.csv"))):
        d = os.path.basename(p)[14:24]
        try:
            df = pd.read_csv(p)
        except Exception as e:  # noqa: BLE001
            rows.append({"date": d, "session_status": "PARSE_ERROR",
                         "error": str(e)[:120]})
            continue
        row = df[df["Index Name"].astype(str).str.lower() == "nifty 50"]
        if row.empty:
            continue
        r = row.iloc[0]
        rows.append({"date": d, "open": float(r.get("Open Index Value", 0)),
                     "high": float(r.get("High Index Value", 0)),
                     "low": float(r.get("Low Index Value", 0)),
                     "close": float(r.get("Closing Index Value", 0)),
                     "source": "NSE_IND_CLOSE_ALL",
                     "source_url": EP["ind_close_all"].format(
                         DDMMYYYY=d.replace("-", "")[6:8]
                         + d.replace("-", "")[4:6] + d.replace("-", "")[0:4]),
                     "retrieved_at": now_iso(),
                     "raw_file_hash": sha256_file(p),
                     "provenance": "REAL", "quality": "A"})
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values("date").reset_index(drop=True)
    path = os.path.join(NORM, "nifty_eod_expanded.csv")
    out.to_csv(path, index=False)
    if len(out):
        write_dataset_manifest("nifty_eod_expanded", "NSE_IND_CLOSE_ALL",
                               EP["ind_close_all"], out)
    return out


def _expiry_observation_dates():
    p = os.path.join(HIST, "expiry_calendar.csv")
    if not os.path.exists(p):
        return set()
    try:
        return set(pd.to_datetime(pd.read_csv(p)["date"]).dt.date.astype(str))
    except Exception:  # noqa: BLE001
        return set()


def build_alignment_matrix(start="2024-01-01", end=None):
    """Per-date x per-dataset alignment for every canonical calendar date.

    Columns: date, calendar_session_status, nifty, options_eod, vix,
    participant_oi, expiry, overall_status. Dataset statuses:
    PRESENT / MISSING / NOT_APPLICABLE. Holidays vs dataset gaps are
    distinguished by calendar_session_status.
    """
    end = end or dt.date.today().isoformat()
    import glob
    cal = canonical_calendar(start, end)
    opt = {os.path.basename(p)[6:16]
           for p in glob.glob(os.path.join(RAW, "bhavcopy", "NIFTY_*.csv"))}
    vix_raw = {os.path.basename(p)[14:24]
               for p in glob.glob(os.path.join(RAW, "vix", "ind_close_all_*.csv"))}
    poi_raw = {os.path.basename(p)[19:29]
               for p in glob.glob(os.path.join(RAW, "participant_oi", "fao_participant_oi_*.csv"))}
    nifty_raw = {os.path.basename(p)[14:24]
                 for p in glob.glob(os.path.join(RAW, "vix", "ind_close_all_*.csv"))}
    expiry = _expiry_observation_dates()
    rows = []
    for _, r in cal.iterrows():
        d, st = r["date"], r["session_status"]
        if st != "TRADING_SESSION":
            rows.append({"date": d, "calendar_session_status": st,
                         "nifty": "NOT_APPLICABLE", "options_eod": "NOT_APPLICABLE",
                         "vix": "NOT_APPLICABLE",
                         "participant_oi": "NOT_APPLICABLE",
                         "expiry": "NOT_APPLICABLE",
                         "overall_status": "NOT_APPLICABLE"})
            continue
        layers = {"nifty": d in nifty_raw, "options_eod": d in opt,
                  "vix": d in vix_raw, "participant_oi": d in poi_raw,
                  "expiry": d in expiry}
        status = {k: ("PRESENT" if v else "MISSING") for k, v in layers.items()}
        present = sum(layers.values())
        overall = "FULL" if present == len(layers) else (
            "PARTIAL" if present else "INSUFFICIENT")
        rows.append({"date": d, "calendar_session_status": st, **status,
                     "overall_status": overall})
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(NORM, "alignment_matrix.csv"), index=False)
    return out


def build_unified_manifest(start="2024-01-01", end=None, created_at=None):
    """Frozen unified research dataset manifest (DATA-ALIGNMENT-01 §12).

    Hashes are deterministic (stable_content_hash over stable columns for
    normalized CSVs; calendar_hash for the calendar). created_at is the only
    timestamp. No production file is touched.
    """
    import glob
    end = end or dt.date.today().isoformat()
    cal = canonical_calendar(start, end)
    cal.to_csv(os.path.join(NORM, "trading_calendar_expanded.csv"), index=False)
    cal_hash = calendar_hash(cal)
    sessions = int((cal["session_status"] == "TRADING_SESSION").sum())
    holidays = int((cal["session_status"] == "MARKET_HOLIDAY").sum())

    def norm_df(name):
        p = os.path.join(NORM, f"{name}.csv")
        if not os.path.exists(p):
            return None
        try:
            return pd.read_csv(p)
        except Exception:  # noqa: BLE001
            return None

    def file_sha(p):
        return sha256_file(p) if os.path.exists(p) else None

    datasets = {}
    for name in ("options_eod_expanded", "vix_expanded",
                 "participant_oi_expanded", "nifty_eod_expanded"):
        df = norm_df(name)
        datasets[name] = {
            "path": f"data/historical/normalized/{name}.csv",
            "sha256": file_sha(os.path.join(NORM, f"{name}.csv")),
            "stable_hash": stable_content_hash(df) if df is not None and len(df) else None,
            "rows": int(len(df)) if df is not None else 0,
            "coverage_start": str(df["date"].min()) if df is not None and len(df) else None,
            "coverage_end": str(df["date"].max()) if df is not None and len(df) else None,
        }
    expiry_p = os.path.join(HIST, "expiry_calendar.csv")
    missing = {}
    align = build_alignment_matrix(start, end)
    for ds in ("nifty", "options_eod", "vix", "participant_oi"):
        miss = sorted(align.loc[(align["calendar_session_status"] == "TRADING_SESSION")
                                & (align[ds] == "MISSING"), "date"])
        missing[ds] = miss
    expiry_missing = sorted(align.loc[(align["calendar_session_status"] == "TRADING_SESSION")
                                      & (align["expiry"] == "MISSING"), "date"])
    nh_path = os.path.join(ROOT, "data", "nifty_history.csv")
    nifty_gaps = []
    if os.path.exists(nh_path):
        nh_dates = set(pd.read_csv(nh_path, usecols=["date"])["date"].astype(str))
        nifty_gaps = sorted(set(canonical_session_dates(start, end)) - nh_dates)
    m = {
        "dataset_name": "unified_research_dataset",
        "calendar_path": "data/historical/normalized/trading_calendar_expanded.csv",
        "calendar_hash": cal_hash,
        "options_dataset": datasets["options_eod_expanded"]["path"],
        "options_hash": datasets["options_eod_expanded"]["stable_hash"],
        "options_sha256": datasets["options_eod_expanded"]["sha256"],
        "vix_dataset": datasets["vix_expanded"]["path"],
        "vix_hash": datasets["vix_expanded"]["stable_hash"],
        "vix_sha256": datasets["vix_expanded"]["sha256"],
        "participant_oi_dataset": datasets["participant_oi_expanded"]["path"],
        "participant_oi_hash": datasets["participant_oi_expanded"]["stable_hash"],
        "participant_oi_sha256": datasets["participant_oi_expanded"]["sha256"],
        "nifty_dataset": datasets["nifty_eod_expanded"]["path"],
        "nifty_hash": datasets["nifty_eod_expanded"]["stable_hash"],
        "nifty_sha256": datasets["nifty_eod_expanded"]["sha256"],
        "expiry_calendar": "data/historical/expiry_calendar.csv",
        "expiry_hash": file_sha(expiry_p),
        "coverage_start": start,
        "coverage_end": end,
        "trading_sessions": sessions,
        "market_holidays": holidays,
        "missing_dataset_days": missing,
        "expiry_calendar_missing_sessions": expiry_missing,
        "production_cache": {
            "nifty_history": {
                "path": "data/nifty_history.csv",
                "sha256": file_sha(nh_path),
                "gap_dates": nifty_gaps,
                "note": "NOT MODIFIED. Yahoo-driven production cache; may omit "
                        "official sessions (e.g. 2026-08-11). Use nifty_eod_expanded "
                        "for research.",
            },
        },
        "provenance_summary": {
            "options_eod": "REAL - NSE UDiFF FO bhavcopy (raw/bhavcopy)",
            "vix": "REAL - NSE ind_close_all (raw/vix)",
            "participant_oi": "REAL - NSE fao_participant_oi (raw/participant_oi)",
            "nifty": "REAL - NSE ind_close_all (canonical nifty_eod_expanded)",
            "calendar": "NSE options EOD > NSE official holiday list > schedule",
        },
        "schema_version": "1.0",
        "created_at": created_at or now_iso(),
    }
    out = os.path.join(MANI, "unified_research_dataset.json")
    save_json(out, m)
    return m


def backfill_special_sessions(days=("2025-02-01", "2026-08-11"), sleep=0.2,
                              retries=3):
    """Collect VIX + participant OI for explicitly given sessions, then
    rebuild every affected normalized dataset + canonical NIFTY EOD."""
    res = {}
    res["vix"] = collect_vix(days=list(days), sleep=sleep, retries=retries)
    res["participant_oi"] = collect_participant_oi(
        days=list(days), sleep=sleep, retries=retries)
    res["nifty_eod"] = {"normalized_rows": len(build_nifty_eod_expanded())}
    return res


# --------------------------------------------------------------------------
# Angel One (read-only) probes
# --------------------------------------------------------------------------
def angelone_configured():
    import config
    return bool(config.get("ANGEL_CLIENT_CODE") and config.get("ANGEL_PASSWORD")
                and config.get("ANGEL_TOTP_SECRET") and config.get("ANGEL_API_KEY"))


def angelone_master():
    """Download fresh instrument master to raw/angelone/. Returns parsed JSON."""
    path = os.path.join(RAW, "angelone", "OpenAPIScripMaster.json")
    r = http_get(EP["angel_master"], timeout=60, retries=2, sleep=0.5)
    with open(path, "wb") as f:
        f.write(r.content)
    m = load_json(path)
    return m, path


def angelone_probe(max_master_entries=500):
    """Isolated read-only Angel One test. NEVER calls trading endpoints.
    Prints NO secrets."""
    from angel_one_client import AngelOneManager
    if not angelone_configured():
        return {"configured": False, "auth": "NOT_CONFIGURED"}
    mgr = AngelOneManager()
    result = {"configured": True}
    result["auth"] = "PASS" if mgr.login() else "FAIL"
    if result["auth"] != "PASS":
        mgr._reset_session()
        return result
    try:
        master, path = angelone_master()
        if isinstance(master, list):
            df = pd.DataFrame(master[:max_master_entries])
        else:
            df = pd.DataFrame(master.get("results", [])[:max_master_entries])
        nifty = df[df["symbol"] == "NIFTY"]
        nfo_opts = df[(df["exch_seg"] == "NFO") & (df["instrumenttype"].astype(str).str.contains("OPTIDX"))]
        result["master"] = {
            "downloaded": True,
            "path": os.path.relpath(path, ROOT),
            "entries": len(master),
            "nifty_tokens": nifty[["symbol", "token"]].to_dict("records"),
            "sample_nfo_option_tokens": nfo_opts.head(3)[["symbol", "token", "expiry", "strike", "lotsize"]].to_dict("records"),
            "earliest_nfo_expiry": sorted(nfo_opts["expiry"].astype(str).tolist())[:2] if len(nfo_opts) else None,
        }
        tok = str(nifty["token"].iloc[0]) if len(nifty) else "26000"
        result["candles_nifty_1d"] = mgr.get_candles(
            "NSE", tok, "ONE_DAY",
            (dt.date.today() - dt.timedelta(days=7)).strftime("%Y-%m-%d 09:15"),
            dt.date.today().strftime("%Y-%m-%d 15:30"))
        result["candles_status"] = "AVAILABLE" if result["candles_nifty_1d"] else "NO_DATA"
        result["candles_rows"] = len(result["candles_nifty_1d"]) if result["candles_nifty_1d"] else 0
        result["candles_sample"] = (result["candles_nifty_1d"] or [None])[-1]
    except Exception as e:  # noqa: BLE001
        result["probe_error"] = f"{type(e).__name__}: {str(e)[:160]}"
    finally:
        mgr.logout()
    return result


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------
def cmd_discover(args):
    report = {}
    probe_map = {"{YYYYMMDD}": "20260731", "{DDMMYYYY}": "31072026",
                 "{DD-Mon-YYYY}": "31-Jul-2026"}
    for key, url in EP.items():
        if key in ("focpv", "vix_history", "indices_history", "fiidii_trade"):
            report[key] = "REQUIRES_COOKIE_BOOTSTRAP (nseindia.com blocks plain requests)"
            continue
        probe = url
        for ph, val in probe_map.items():
            probe = probe.replace(ph, val)
        probe = probe.replace("{from}", "31-07-2026").replace("{to}", "31-07-2026")
        probe = probe.replace("{sym}", "NIFTY").replace("{inst}", "OPTIDX")
        probe = probe.replace("{expiry}", "2026-07-30").replace("{ot}", "CE")
        probe = probe.replace("{index}", "NIFTY 50")
        try:
            r = http_get(probe, timeout=20, retries=1, sleep=0.2)
            report[key] = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            report[key] = f"ERROR {type(e).__name__}"
    save_json(os.path.join(MANI, "discover_report.json"),
              {"probed_at": now_iso(), "endpoints": report})
    return report


def cmd_audit(args):
    """Inventory current datasets + production fingerprint (after snapshot)."""
    inv = _inventory()
    save_json(os.path.join(MANI, "inventory.json"), inv)
    return inv


def _inventory():
    def rng(f, col):
        try:
            d = pd.read_csv(f)
            c = col or d.columns[0]
            s = pd.to_datetime(d[c], errors="coerce").dropna()
            return {"rows": int(len(d)), "start": str(s.min().date()) if len(s) else None,
                    "end": str(s.max().date()) if len(s) else None}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)[:80]}
    files = {
        "nifty_history": ("data/nifty_history.csv", "date"),
        "india_vix": ("data/india_vix.csv", "date"),
        "fii_dii_history": ("data/fii_dii_history.csv", "date"),
        "ml_features": ("data/ml_features.csv", "date"),
    }
    out = {}
    for k, (p, c) in files.items():
        out[k] = {"path": p, **rng(p, c),
                  "sha256": sha256_file(p) if os.path.exists(p) else None}
    out["oi_snapshots"] = {"files": len(os.listdir("data/oi_snapshots"))}
    out["research_db_mb"] = round(os.path.getsize("data/research.db") / 1e6, 1)
    return out


def cmd_coverage(args):
    """Per-day coverage matrix over the canonical session calendar."""
    import glob
    cal = canonical_calendar("2024-01-01", dt.date.today().isoformat())
    bhav = {os.path.basename(p)[6:16] for p in glob.glob(os.path.join(RAW, "bhavcopy", "NIFTY_*.csv"))}
    vix = {os.path.basename(p)[14:24] for p in glob.glob(os.path.join(RAW, "vix", "ind_close_all_*.csv"))}
    poi = {os.path.basename(p)[19:29] for p in glob.glob(os.path.join(RAW, "participant_oi", "fao_participant_oi_*.csv"))}
    nifty = set(pd.read_csv("data/nifty_history.csv", usecols=["date"])["date"].astype(str))
    vix_old = set(pd.read_csv("data/india_vix.csv", usecols=["date"])["date"].astype(str))
    rows = []
    for d in cal["date"]:
        if d not in canonical_session_dates("2024-01-01", dt.date.today().isoformat()):
            continue
        layers = []
        if d in nifty or d in vix:
            layers.append("NIFTY_EOD")
        if d in vix or d in vix_old:
            layers.append("VIX")
        if d in bhav:
            layers.append("OPTIONS_EOD")
        if d in poi:
            layers.append("PARTICIPANT_OI")
        status = "FULL" if layers else "INSUFFICIENT"
        if layers and len(layers) < 4:
            status = "PARTIAL"
        rows.append({"date": d, "layers": "|".join(layers), "status": status})
    out = pd.DataFrame(rows)
    path = os.path.join(NORM, "coverage_matrix.csv")
    out.to_csv(path, index=False)
    return out.groupby("status").size().to_dict()


def cmd_calendar(args):
    """Write the authoritative trading calendar + print status counts/hash."""
    cal = canonical_calendar(args.start, args.end)
    path = os.path.join(NORM, "trading_calendar_expanded.csv")
    cal.to_csv(path, index=False)
    return {"path": f"data/historical/normalized/trading_calendar_expanded.csv",
            "rows": int(len(cal)),
            "calendar_hash": calendar_hash(cal),
            "counts": cal["session_status"].value_counts().to_dict()}


def cmd_align(args):
    """Build alignment matrix + frozen unified manifest (idempotent)."""
    align = build_alignment_matrix(args.start, args.end)
    manifest = build_unified_manifest(args.start, args.end)
    return {"alignment_rows": int(len(align)),
            "overall": align["overall_status"].value_counts().to_dict(),
            "calendar_hash": manifest["calendar_hash"],
            "manifest_path": "data/historical/manifests/unified_research_dataset.json",
            "missing_dataset_days": manifest["missing_dataset_days"],
            "production_nifty_gap": manifest["production_cache"]["nifty_history"]["gap_dates"]}



def cmd_validate(args):
    """Validate normalized datasets: schema, provenance, duplicates, futures."""
    import glob
    report = {}
    for p in sorted(glob.glob(os.path.join(NORM, "*.csv"))):
        name = os.path.basename(p).replace(".csv", "")
        df = pd.read_csv(p)
        issues = []
        if df.empty:
            issues.append("EMPTY")
        prov_vocab = (CALENDAR_PROVENANCES if name == "trading_calendar_expanded"
                      else PROVENANCES)
        for col in ("provenance", "quality"):
            if col in df.columns and df[col].notna().any():
                vocab = prov_vocab if col == "provenance" else QUALITIES
                bad = df[df[col].astype(str).isin(list(vocab)) == False]  # noqa: E712
                if len(bad):
                    issues.append(f"bad_{col}")
        dup = df.duplicated().sum() if len(df) else 0
        if dup:
            issues.append(f"duplicates={int(dup)}")
        fut = detect_future_timestamps(df, dt.date.today().isoformat())
        if fut:
            issues.append(f"future_ts={fut[0]['count']}")
        report[name] = {"rows": int(len(df)), "status": "PASS" if not issues else "ISSUES",
                        "issues": issues}
    save_json(os.path.join(MANI, "validation_report.json"),
              {"validated_at": now_iso(), "datasets": report})
    return report


def cmd_manifest(args):
    """Print per-dataset manifests."""
    out = {}
    for name in os.listdir(MANI):
        if name.endswith(".json"):
            out[name] = load_json(os.path.join(MANI, name))
    save_json(os.path.join(MANI, "all_manifests.json"), out)
    return {k: v.get("dataset", k) for k, v in out.items()}


COLLECTORS = {
    "bhavcopy-backfill": collect_bhavcopy_backfill,
    "frozen-reuse": collect_frozen_reuse,
    "vix": collect_vix,
    "participant-oi": collect_participant_oi,
    "fiidii": collect_fiidii_trade,
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover")
    sub.add_parser("audit")
    sub.add_parser("angelone-capabilities")
    p = sub.add_parser("collect")
    p.add_argument("--kind", choices=list(COLLECTORS) + ["all"], default="all")
    p.add_argument("--start", default="2024-01-01")
    p.add_argument("--end", default="2025-08-12")
    p.add_argument("--max-days", type=int, default=0)
    sub.add_parser("validate")
    sub.add_parser("coverage")
    sub.add_parser("manifest")
    p = sub.add_parser("calendar")
    p.add_argument("--start", default="2024-01-01")
    p.add_argument("--end", default="2026-08-13")
    p = sub.add_parser("backfill-special")
    p.add_argument("--days", nargs="+", default=["2025-02-01", "2026-08-11"])
    p = sub.add_parser("align")
    p.add_argument("--start", default="2024-01-01")
    p.add_argument("--end", default="2026-08-13")
    args = ap.parse_args()

    if args.cmd == "discover":
        print(json.dumps(cmd_discover(args), indent=1))
    elif args.cmd == "audit":
        print(json.dumps(cmd_audit(args), indent=1))
    elif args.cmd == "angelone-capabilities":
        caps = ANGELONE_CAPABILITIES
        probe = {}
        if args.cmd == "angelone-capabilities":
            probe = angelone_probe()
        print(json.dumps({"capabilities": caps, "live_probe": probe}, indent=1))
    elif args.cmd == "collect":
        kinds = list(COLLECTORS) if args.kind == "all" else [args.kind]
        for k in kinds:
            fn = COLLECTORS[k]
            if k == "fiidii":
                res = fn(max_days=args.max_days or 1)
            elif k == "frozen-reuse":
                res = fn(verbose=True)
            else:
                res = fn(start=args.start, end=args.end,
                         max_days=args.max_days)
            print(f"[{k}] {json.dumps(res)}")
    elif args.cmd == "validate":
        print(json.dumps(cmd_validate(args), indent=1))
    elif args.cmd == "coverage":
        print(json.dumps(cmd_coverage(args), indent=1))
    elif args.cmd == "calendar":
        print(json.dumps(cmd_calendar(args), indent=1))
    elif args.cmd == "backfill-special":
        print(json.dumps(backfill_special_sessions(days=tuple(args.days)), indent=1))
    elif args.cmd == "align":
        print(json.dumps(cmd_align(args), indent=1))
    elif args.cmd == "manifest":
        print(json.dumps(cmd_manifest(args), indent=1))


if __name__ == "__main__":
    main()
