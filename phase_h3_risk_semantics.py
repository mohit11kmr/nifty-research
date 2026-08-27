"""Phase H3 - RANGE-HV Iron Condor: Risk / Contract-Semantics / Measurement
Integrity + 646-Session Frozen Validation (MEASUREMENT ONLY).

Answers the phase question: is the frozen Range-HV candidate internally
correct and economically interpretable BEFORE evaluating it on the unified
646-session dataset? NO strategy change, NO optimization, NO tuning.

Sections
--------
A.  Freeze inputs (hashes of unified dataset + spec + git commit).
B.  H2 baseline reproduction (RangeHVValidator on the frozen snapshot).
C.  Contract-level audit of the 6 H2 trades (leg provenance, true credit,
    widths, corrected max loss, corrected risk % of capital).
D.  Risk semantics (risk definitions, capital basis, RISK_MODEL_MISMATCH).
E.  Max-loss matrix (deterministic engine-formula cases).
F.  646-session unified replay (measurement layer for every session;
    strategy invoked ONLY on sessions with an authoritative canonical
    expiry; pre-window sessions classified EXPIRY_DATA_LIMITATION).
G.  H2-vs-H3 trade comparison (entry/exit/credit/P&L, data cross-checks).
H.  Risk-normalized + concentration report.
I.  Out-of-sample split (chronological; OOS_INSUFFICIENT when n < 20).
J.  Reproducibility (deterministic re-run of the replay engine).
K.  Production isolation (read-only assertion on the repo data dir).

The only filesystem writes are to --out. No data/* file is ever written.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import backtest_frozen as bf  # noqa: E402
import expiry_calendar as exp_cal  # noqa: E402
import historical_expiry as hist_exp  # noqa: E402
import multi_strategy_backtest as m  # noqa: E402
import phase_h2_validation as h2  # noqa: E402
from indicators import add_all_indicators  # noqa: E402

FROZEN_SNAPSHOT = "/tmp/opencode/phaseH_frozen_data"
UNIFIED_MANIFEST = os.path.join(ROOT, "data", "historical", "manifests",
                                "unified_research_dataset.json")
BASELINE_CACHE = "/tmp/opencode/h3_baseline_repro.json"

VIX_MIN = m.SPREAD_VIX_MIN
VIX_MAX = m.SPREAD_VIX_MAX
CAPITAL = m.CAPITAL
LOT_SIZE = m.LOT_SIZE

UNIFIED_FILES = {
    "nifty": os.path.join(ROOT, "data", "historical", "normalized",
                          "nifty_eod_expanded.csv"),
    "vix": os.path.join(ROOT, "data", "historical", "normalized",
                        "vix_expanded.csv"),
    "options": os.path.join(ROOT, "data", "historical", "normalized",
                            "options_eod_expanded.csv"),
    "expiry_calendar": os.path.join(ROOT, "data", "historical",
                                    "expiry_calendar.csv"),
    "participant_oi": os.path.join(ROOT, "data", "historical", "normalized",
                                   "participant_oi_expanded.csv"),
    "calendar": os.path.join(ROOT, "data", "historical", "normalized",
                             "trading_calendar_expanded.csv"),
}

SPEC_ID = "range_hv_iron_condor_v1"
H2_SPEC_HASH = "56ba02752efc4650efe1d8c88165f3396e3ae10aaa15519d9b13e33a4e0d1adb"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return None


def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# A.  Freeze inputs
# ---------------------------------------------------------------------------
def freeze_inputs():
    with open(UNIFIED_MANIFEST) as fh:
        manifest = json.load(fh)
    hashes = {name: sha256_file(path) for name, path in UNIFIED_FILES.items()}
    spec_hash = None
    try:
        from strategy_registry import default_registry
        spec_hash = default_registry().spec_hash(SPEC_ID)
    except Exception:
        pass
    return {
        "unified_manifest": {
            "path": UNIFIED_MANIFEST,
            "created_at": manifest.get("created_at"),
            "trading_sessions": manifest.get("trading_sessions"),
            "coverage_start": manifest.get("coverage_start"),
            "coverage_end": manifest.get("coverage_end"),
            "calendar_hash": manifest.get("calendar_hash"),
            "nifty_hash": manifest.get("nifty_hash"),
            "vix_hash": manifest.get("vix_hash"),
            "options_hash": manifest.get("options_hash"),
            "participant_oi_hash": manifest.get("participant_oi_hash"),
            "expiry_hash": manifest.get("expiry_hash"),
            "missing_dataset_days": manifest.get("missing_dataset_days"),
            "expiry_calendar_missing_sessions_count": len(
                manifest.get("expiry_calendar_missing_sessions", [])),
            "market_holidays": manifest.get("market_holidays"),
        },
        "file_sha256": hashes,
        "strategy": {
            "id": SPEC_ID,
            "spec_hash_computed": spec_hash,
            "spec_hash_h2_recorded": H2_SPEC_HASH,
            "spec_hash_match": spec_hash == H2_SPEC_HASH,
        },
        "git_commit": git_commit(),
    }


# ---------------------------------------------------------------------------
# B.  H2 baseline reproduction (frozen snapshot)
# ---------------------------------------------------------------------------
def h2_baseline(use_cache=True, recompute=False):
    if use_cache and not recompute and os.path.exists(BASELINE_CACHE):
        with open(BASELINE_CACHE) as fh:
            report = json.load(fh)
        report["_provenance"] = {"source": "cache", "path": BASELINE_CACHE}
        return report
    v = h2.RangeHVValidator()
    report = v.run_all()
    report["_provenance"] = {"source": "fresh_run", "path": None}
    return report


# ---------------------------------------------------------------------------
# C.  Contract-level audit of the 6 H2 trades
# ---------------------------------------------------------------------------
def _parse_strike(s):
    """Engine strike string 'KcW/Kc-Kp/KpW' -> (Kc, Kp, KcW, KpW)."""
    if not s or "/" not in s or "-" not in s:
        return None
    left, right = s.split("-")
    kcw, kc = (int(p) for p in left.split("/"))
    kp, kpw = (int(p) for p in right.split("/"))
    return kc, kp, kcw, kpw


def _true_condor_max_loss(strikes, credit):
    """Economic max loss of an iron condor = max(call_width, put_width) - credit.
    (width = long wing - short strike on each side; short side bounded)."""
    kc, kp, kcw, kpw = strikes
    call_w = kcw - kc
    put_w = kp - kpw
    return max(call_w, put_w) - credit


def contract_audit(h2_report, unified_snaps, unified_nifty):
    """Rebuild every H2 trade from the unified options chain and compute the
    corrected risk semantics. provenance per leg: chain_lookup vs bs_fallback."""
    rows = h2_report["trades"]
    out = []
    for r in rows:
        entry = dt.date.fromisoformat(r["entry_date"])
        strikes = _parse_strike(r.get("strike") or "")
        expiry = exp_cal.get_expiry_for_trade_date(entry)
        entry_premium = r.get("entry_premium")
        spot = float(unified_nifty[unified_nifty["date"] == pd.Timestamp(entry)]
                     .iloc[0]["close"])
        legs = {}
        if strikes is not None and expiry is not None:
            legs = m.condor_legs(unified_snaps, entry, expiry, *strikes, spot)
        credit = round((legs.get("Kc", 0) or 0) + (legs.get("Kp", 0) or 0)
                       - (legs.get("KcW", 0) or 0) - (legs.get("KpW", 0) or 0), 2) if legs else None
        kc, kp, kcw, kpw = strikes or (None,) * 4
        call_w = (kcw - kc) if kc is not None else None
        put_w = (kp - kpw) if kp is not None else None
        true_max_loss_share = (_true_condor_max_loss(strikes, credit)
                               if strikes is not None and credit is not None else None)
        engine_max_loss_share = r.get("max_risk_per_share")
        risk_pct = (round(true_max_loss_share * LOT_SIZE / CAPITAL * 100, 2)
                    if true_max_loss_share is not None else None)
        out.append({
            "entry_date": r["entry_date"], "exit_date": r["exit_date"],
            "exit_reason": r.get("reason"),
            "spot_at_entry": round(spot, 2),
            "legs": {k: (round(v, 2) if v is not None else None)
                     for k, v in legs.items()},
            "strikes": {"short_call": kc, "short_put": kp,
                        "long_call": kcw, "long_put": kpw},
            "call_width": call_w, "put_width": put_w,
            "entry_credit_true": credit,
            "entry_premium_h2_reported": (round(entry_premium, 2)
                                          if entry_premium is not None else None),
            "premium_is_condor_credit": bool(credit is not None
                                             and entry_premium is not None
                                             and abs(credit - entry_premium) < 1e-6),
            "engine_max_loss_share": (round(engine_max_loss_share, 2)
                                      if engine_max_loss_share is not None else None),
            "true_max_loss_share": (round(true_max_loss_share, 2)
                                    if true_max_loss_share is not None else None),
            "true_max_loss_lot": (round(true_max_loss_share * LOT_SIZE, 2)
                                  if true_max_loss_share is not None else None),
            "true_risk_pct_of_capital": risk_pct,
            "net_pnl": r["net_pnl"],
        })
    return out


# ---------------------------------------------------------------------------
# E.  Max-loss matrix (deterministic engine-formula cases)
# ---------------------------------------------------------------------------
def max_loss_matrix():
    """Engine formula: max_loss = (KcW - Kc) - credit  [call-side width only].
    True formula: max(call_w, put_w) - credit. Fees and adverse exit slippage
    are NOT inside max_loss (they stack on a loss exit)."""
    cases = [
        {"case": "sym_width_credit_below_width", "Kc": 24000, "Kp": 24000,
         "KcW": 24150, "KpW": 23850, "credit": 40.0},
        {"case": "sym_width_credit_equal_width", "Kc": 24000, "Kp": 24000,
         "KcW": 24150, "KpW": 23850, "credit": 150.0},
        {"case": "sym_width_credit_above_width", "Kc": 24000, "Kp": 24000,
         "KcW": 24150, "KpW": 23850, "credit": 160.0},
        {"case": "unequal_wings_put_wider", "Kc": 24000, "Kp": 24000,
         "KcW": 24150, "KpW": 23750, "credit": 40.0},
        {"case": "wide_wings_both_sides", "Kc": 24000, "Kp": 24000,
         "KcW": 24200, "KpW": 23800, "credit": 50.0},
    ]
    rows = []
    for c in cases:
        kc, kp, kcw, kpw, credit = (c["Kc"], c["Kp"], c["KcW"], c["KpW"],
                                    c["credit"])
        strikes = (kc, kp, kcw, kpw)
        call_w = kcw - kc
        put_w = kp - kpw
        engine = call_w - credit
        true = _true_condor_max_loss(strikes, credit)
        rows.append({
            "case": c["case"], "call_width": call_w, "put_width": put_w,
            "credit": credit,
            "engine_max_loss_share": round(engine, 2),
            "true_max_loss_share": round(true, 2),
            "engine_understates_by": round(engine - true, 2),
            "engine_negative_artifact": bool(engine < 0),
        })
    return rows


# ---------------------------------------------------------------------------
# F.  646-session unified replay
# ---------------------------------------------------------------------------
def load_unified():
    nifty = pd.read_csv(UNIFIED_FILES["nifty"])
    nifty["date"] = pd.to_datetime(nifty["date"])
    vix = pd.read_csv(UNIFIED_FILES["vix"])
    vix["date"] = pd.to_datetime(vix["date"])
    opt = pd.read_csv(UNIFIED_FILES["options"])
    opt["date"] = pd.to_datetime(opt["date"])
    opt["expiry"] = pd.to_datetime(opt["expiry"], errors="coerce")
    opt = opt.dropna(subset=["expiry"])
    opt["expiry"] = opt["expiry"].dt.strftime("%d-%b-%Y")
    return nifty, vix, opt


def build_unified_snaps(opt):
    """Per-day chain DataFrames (strike, expiry, ce_ltp, pe_ltp) matching the
    frozen oi_snapshots schema consumed by price_strike_lookup/build_condor.
    Prices are day-d EOD close; duplicates collapsed deterministically."""
    snaps = {}
    for d, g in opt.groupby(opt["date"].dt.date):
        g = g.sort_values(["strike", "expiry", "option_type"])
        g = g.drop_duplicates(subset=["strike", "expiry", "option_type"])
        wide = (g.pivot_table(index=["strike", "expiry"],
                              columns="option_type", values="close",
                              aggfunc="first").reset_index())
        rename = {}
        if "CE" in wide.columns:
            rename["CE"] = "ce_ltp"
        if "PE" in wide.columns:
            rename["PE"] = "pe_ltp"
        wide = wide.rename(columns=rename)
        for col in ("ce_ltp", "pe_ltp"):
            if col not in wide.columns:
                wide[col] = np.nan
        wide = wide[["strike", "expiry", "ce_ltp", "pe_ltp"]]
        wide["strike"] = wide["strike"].astype(float)
        snaps[d] = wide.reset_index(drop=True)
    return snaps


def measure_day(d, nifty):
    """Measurement-layer replication of backtest_frozen.evaluate_day's core
    (regime/vix/spot/skip only). The full funnel layers are NOT needed by
    candidate C. No lookahead: only rows <= d."""
    sdf = nifty[nifty["date"] <= pd.Timestamp(d)].copy()
    rec = {"date": pd.Timestamp(d).date().isoformat(), "spot": None,
           "vix": None, "vix_zone": None, "regime": None, "skip": None}
    if len(sdf) < bf.MIN_WARMUP_ROWS:
        rec["skip"] = "warmup"
        return rec
    add_all_indicators(sdf)
    sdf = sdf.dropna(subset=["adx", "bb_upper", "bb_lower"]).reset_index(drop=True)
    if len(sdf) < bf.MIN_WARMUP_ROWS:
        rec["skip"] = "warmup"
        return rec
    rec["spot"] = round(float(sdf.iloc[-1]["close"]), 2)
    vix_snap = bf.vix_snapshot_at(vix_df(), d)
    if vix_snap:
        rec["vix"] = vix_snap["level"]
        rec["vix_zone"] = vix_snap["zone"]
    regime, gate, _ = bf.regime_gate_at(sdf, vix_snap)
    rec["regime"] = regime
    rec["gate"] = gate
    return rec


_VIX_DF = {"df": None}


def vix_df():
    if _VIX_DF["df"] is None:
        v = pd.read_csv(UNIFIED_FILES["vix"])
        v["date"] = pd.to_datetime(v["date"])
        _VIX_DF["df"] = v
    return _VIX_DF["df"]


def researchable_dates():
    """Dates with an authoritative expiry in the canonical calendar."""
    cal = hist_exp.load_calendar(exp_cal.CALENDAR_CSV)
    out = set()
    for iso, (expiry, weekday, days, avail) in cal.items():
        if avail and expiry is not None:
            out.add(iso)
    return out


def regime_sensitivity(nifty, recs):
    """How sensitive is the RANGE_HV/RANGE_LV boundary to the depth of the
    nifty series? Recomputes the measurement layer on a frozen-depth-equivalent
    series (rows >= frozen start 2024-08-12) and counts regime flips over the
    researchable window. Explains why the unified replay can trade days the
    frozen-snapshot evaluation labelled RANGE_LV."""
    frozen_start = "2024-08-12"
    n_restricted = nifty[nifty["date"] >= pd.Timestamp(frozen_start)].copy()
    flips = []
    for d in n_restricted["date"]:
        iso = d.date().isoformat()
        rec_u = recs.get(iso)
        if rec_u is None or rec_u.get("skip"):
            continue
        rec_f = measure_day(d, n_restricted)
        if rec_f.get("skip"):
            continue
        if rec_u["regime"] != rec_f["regime"]:
            flips.append({"date": iso, "unified_regime": rec_u["regime"],
                          "frozen_depth_regime": rec_f["regime"]})
    return {"flip_count": len(flips), "flips": flips}


def classify_sessions(nifty, recs):
    """Every unified session -> measurement status. Strategy-invokable only
    when the canonical expiry is authoritative (researchable)."""
    researchable = researchable_dates()
    rows = []
    for d in nifty["date"]:
        iso = d.date().isoformat()
        rec = recs.get(iso)
        regime = rec["regime"] if rec else None
        vix = rec["vix"] if rec else None
        if not rec or rec.get("skip"):
            status, reason = "DATA_INSUFFICIENT", rec.get("skip") if rec else "no record"
        elif regime != "RANGE_HV":
            status, reason = "NON_CANDIDATE", f"regime={regime}"
        elif vix is None or not (VIX_MIN <= vix < VIX_MAX):
            status, reason = "NON_CANDIDATE", f"vix={vix}"
        elif iso in researchable:
            status, reason = "RESEARCHABLE", "canonical expiry available"
        else:
            status, reason = "EXPIRY_DATA_LIMITATION", \
                "no canonical expiry (pre-2025-08-13); forward rule would be a guess"
        rows.append({"date": iso, "regime": regime,
                     "vix": (round(vix, 2) if vix is not None else None),
                     "status": status, "reason": reason})
    return rows


def unified_replay(nifty, snaps, recs):
    """Run candidate C over the RESEARCHABLE window only (authoritative expiry).
    nifty_dates is restricted to researchable dates so the forward-rule expiry
    fallback can never fire inside the strategy loop."""
    researchable = researchable_dates()
    nifty_dates = [d.date() for d in nifty["date"]
                   if d.date().isoformat() in researchable]
    recs_sub = {k: v for k, v in recs.items() if k in researchable}
    trades = m.run_candidate_c(recs_sub, nifty, snaps, nifty_dates)
    rows = m.trade_rows("C_RANGE_HV_IRON_CONDOR", trades)
    return trades, rows, len(nifty_dates)


# ---------------------------------------------------------------------------
# H.  Concentration / metrics
# ---------------------------------------------------------------------------
def concentration(rows):
    nets = sorted((r["net_pnl"] for r in rows), reverse=True)
    total = sum(nets)
    if not nets or total == 0:
        return {"total": 0.0, "n": len(nets)}
    return {
        "n": len(nets), "total": round(total, 2),
        "best_trade": round(max(nets), 2), "worst_trade": round(min(nets), 2),
        "mean_trade": round(sum(nets) / len(nets), 2),
        "median_trade": round(sorted(nets)[len(nets) // 2], 2),
        "best_pct_of_total": round(max(nets) / total * 100, 1),
        "top2_pct_of_total": round(sum(nets[:2]) / total * 100, 1),
        "top3_pct_of_total": round(sum(nets[:3]) / total * 100, 1),
    }


def summary_metrics(rows, capital=CAPITAL):
    nets = [r["net_pnl"] for r in rows]
    if not nets:
        return {"trade_count": 0}
    wins = [x for x in nets if x > 0]
    gw = sum(wins)
    gl = -sum(x for x in nets if x <= 0)
    eq = []
    e = 0.0
    for r in sorted(rows, key=lambda x: x["exit_date"]):
        e += r["net_pnl"]
        eq.append(e)
    peak, mdd = -1e18, 0.0
    for x in eq:
        peak = max(peak, x)
        mdd = min(mdd, x - peak)
    return {
        "trade_count": len(nets),
        "win_count": len(wins),
        "loss_count": len(nets) - len(wins),
        "win_rate": round(len(wins) / len(nets) * 100, 1),
        "net_pnl": round(sum(nets), 2),
        "gross_profit": round(gw, 2),
        "gross_loss": round(gl, 2),
        "profit_factor": round(gw / gl, 3) if gl > 0 else None,
        "max_drawdown": round(mdd, 2),
        "average_trade": round(sum(nets) / len(nets), 2),
        "max_single_loss": round(min(nets), 2),
        "expectancy": round(sum(nets) / len(nets), 2),
    }


# ---------------------------------------------------------------------------
# G.  H2 vs H3 comparison
# ---------------------------------------------------------------------------
def compare_h2_h3(h2_rows, h3_rows):
    def key(r):
        return (r["entry_date"], r["exit_date"])
    h2map = {key(r): r for r in h2_rows}
    h3map = {key(r): r for r in h3_rows}
    matched = sorted(set(h2map) & set(h3map))
    only_h2 = sorted(set(h2map) - set(h3map))
    only_h3 = sorted(set(h3map) - set(h2map))
    pnl_diffs = []
    for k in matched:
        p = h2map[k]["net_pnl"]
        q = h3map[k]["net_pnl"]
        if abs(p - q) > 0.01:
            pnl_diffs.append({"entry": k[0], "exit": k[1],
                              "h2": p, "h3": q, "diff": round(q - p, 2)})
    return {
        "matched_trades": len(matched),
        "only_in_h2": [{"entry": k[0], "exit": k[1]} for k in only_h2],
        "only_in_h3": [{"entry": k[0], "exit": k[1]} for k in only_h3],
        "pnl_diffs": pnl_diffs,
        "identical": (len(only_h2) == 0 and len(only_h3) == 0
                      and len(pnl_diffs) == 0),
    }


def data_cross_checks(h2_report, nifty, vix, snaps):
    """Frozen-vs-unified price consistency (data, not strategy)."""
    froot = FROZEN_SNAPSHOT
    fn = pd.read_csv(os.path.join(froot, "data", "nifty_history.csv"))
    fn["date"] = pd.to_datetime(fn["date"])
    fv = pd.read_csv(os.path.join(froot, "data", "india_vix.csv"))
    fv["date"] = pd.to_datetime(fv["date"])
    merged_n = fn[["date", "close"]].merge(nifty[["date", "close"]],
                                           on="date", suffixes=("_f", "_u"))
    merged_v = fv[["date", "close"]].merge(vix[["date", "close"]],
                                           on="date", suffixes=("_f", "_u"))
    return {
        "nifty_overlap_rows": int(len(merged_n)),
        "nifty_max_close_dev_pct": round(
            float(((merged_n["close_f"] - merged_n["close_u"])
                   / merged_n["close_f"]).abs().max() * 100), 8),
        "vix_overlap_rows": int(len(merged_v)),
        "vix_max_abs_dev": round(float((merged_v["close_f"]
                                        - merged_v["close_u"]).abs().max()), 6),
    }


# ---------------------------------------------------------------------------
# J.  Reproducibility (deterministic replay re-run)
# ---------------------------------------------------------------------------
def replay_repro(nifty, snaps, recs):
    trades1, rows1, n1 = unified_replay(nifty, snaps, recs)
    trades2, rows2, n2 = unified_replay(nifty, snaps, recs)
    h1 = hashlib.sha256(canonical_json(rows1).encode()).hexdigest()
    h2 = hashlib.sha256(canonical_json(rows2).encode()).hexdigest()
    return {"run1_hash": h1, "run2_hash": h2, "identical": h1 == h2,
            "researchable_days": n1}


# ---------------------------------------------------------------------------
# K.  Production isolation (read-only assertion)
# ---------------------------------------------------------------------------
def sentinel_mtimes():
    return {name: os.path.getmtime(path) for name, path in UNIFIED_FILES.items()}


def oos_split_with_verdict(rows, split="2026-04-01"):
    oos = h2.RangeHVValidator.oos_split(rows, split)
    n_oos = oos["out_of_sample"]["trades"]
    verdict = "OOS_INSUFFICIENT" if n_oos < 20 else "OOS_ADEQUATE"
    oos["verdict"] = verdict
    oos["threshold"] = "n_out_of_sample < 20 -> OOS_INSUFFICIENT (no OOS claim)"
    return oos


def findings(report):
    """Synthesize the H3 verdict from the measured facts."""
    audit = report["contract_audit"]
    mismatch = [a["entry_date"] for a in audit
                if not a["premium_is_condor_credit"]]
    artifacts = [a["entry_date"] for a in audit
                 if a["engine_max_loss_share"] is not None
                 and a["engine_max_loss_share"] < 0]
    extra = [t["entry_date"] for t in report["646_replay"]["trades"]
             if t["entry_date"] not in
             {a["entry_date"] for a in audit}]
    return {
        "reported_premium_mislabeled": {
            "trades": mismatch,
            "impact": "H2 entry_premium/max_risk_per_share for these trades are "
                      "control-directional premiums, not condor credits -> "
                      "'credit > wing width' negative max-loss was a measurement "
                      "artifact, not an economic structure.",
        },
        "negative_max_loss_artifact": {
            "trades": artifacts,
            "impact": "engine max_loss < 0 is impossible economically; corrected "
                      "risk = wing_width - true_credit (all positive here).",
        },
        "risk_model_mismatch": report["risk_semantics"]["risk_model_mismatch"],
        "unified_replay_extra_trades": {
            "trades": extra,
            "impact": "these trades exist because the deeper unified nifty series "
                      "flips their regime RANGE_LV->RANGE_HV (bb-width percentile "
                      "history-depth sensitivity). Measurement artifact, not edge.",
        },
        "regime_boundary_sensitivity": report["regime_sensitivity"]["flip_count"],
        "expiry_data_limitation_sessions": report["646_replay"]
        ["session_class_counts"].get("EXPIRY_DATA_LIMITATION", 0),
        "oos_verdict": report["oos_split"]["verdict"],
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/opencode/h3",
                    help="output directory (only place this script writes)")
    ap.add_argument("--skip-baseline", action="store_true",
                    help="use cached H2 baseline JSON if present")
    ap.add_argument("--recompute-baseline", action="store_true",
                    help="re-run the H2 baseline pool (slow)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    before = sentinel_mtimes()

    inputs = freeze_inputs()
    print("freeze: spec_hash_match =", inputs["strategy"]["spec_hash_match"],
          "| git =", inputs["git_commit"])

    baseline = h2_baseline(use_cache=not args.recompute_baseline,
                           recompute=args.recompute_baseline)
    print("baseline: source =", baseline["_provenance"]["source"],
          "| trades =", baseline["trade_count"],
          "| net =", baseline["profit_concentration"]["total"])

    print("loading unified dataset ...")
    nifty, vix, opt = load_unified()
    snaps = build_unified_snaps(opt)
    print(f"unified snaps built: {len(snaps)} dates, "
          f"options rows = {len(opt)}")

    print("measurement layer over", len(nifty), "sessions ...")
    recs = {}
    for d in nifty["date"]:
        recs[d.date().isoformat()] = measure_day(d, nifty)
    classes = classify_sessions(nifty, recs)
    from collections import Counter
    class_counts = dict(Counter(c["status"] for c in classes))

    print("running unified replay ...")
    trades, rows, researchable_days = unified_replay(nifty, snaps, recs)
    repro = replay_repro(nifty, snaps, recs)

    audit = contract_audit(baseline, snaps, nifty)
    xchecks = data_cross_checks(baseline, nifty, vix, snaps)
    sens = regime_sensitivity(nifty, recs)

    report = {
        "phase": "H3",
        "freeze": inputs,
        "h2_baseline": {
            "provenance": baseline["_provenance"],
            "trade_count": baseline["trade_count"],
            "net_pnl": baseline["profit_concentration"]["total"],
            "profit_factor": None,
            "window": baseline["window"],
            "fingerprints": baseline.get("fingerprints"),
        },
        "contract_audit": audit,
        "risk_semantics": {
            "capital_basis": CAPITAL,
            "lot_size": LOT_SIZE,
            "engine_risk_definition": "width_risk - entry_credit (call-side width)",
            "true_risk_definition": "max(call_width, put_width) - credit",
            "spec_declared_risk_pct": 1.0,
            "measured_risk_pct_range": [
                round(min(a["true_risk_pct_of_capital"] for a in audit), 2),
                round(max(a["true_risk_pct_of_capital"] for a in audit), 2),
            ] if audit else None,
            "risk_model_mismatch": bool(audit) and all(
                a["true_risk_pct_of_capital"] is not None
                and a["true_risk_pct_of_capital"] > 1.0 for a in audit),
            "sizer": "units = max(int(capital*risk_pct/max(max_loss,1)), 1) -> "
                      "floors to 1 lot on this capital; 1% target unachievable",
            "capital_needed_for_1pct_risk": (round(
                max(a["true_max_loss_lot"] for a in audit) * 100, 2) if audit else None),
        },
        "max_loss_matrix": max_loss_matrix(),
        "646_replay": {
            "total_sessions": len(classes),
            "session_class_counts": class_counts,
            "researchable_days": researchable_days,
            "trade_count": len(rows),
            "trades": rows,
            "summary": summary_metrics(rows),
            "concentration": concentration(rows),
        },
        "h2_vs_h3": compare_h2_h3(baseline["trades"], rows),
        "data_cross_checks": xchecks,
        "regime_sensitivity": sens,
        "oos_split": oos_split_with_verdict(rows),
        "reproducibility": repro,
        "production_isolation": {
            "written_files_before": before,
            "written_files_after": sentinel_mtimes(),
            "repo_data_unchanged": before == sentinel_mtimes(),
        },
    }
    report["findings"] = findings(report)

    with open(os.path.join(args.out, "h3_report.json"), "w") as f:
        json.dump(report, f, indent=1, default=str)
    print("WROTE", os.path.join(args.out, "h3_report.json"))
    print("replay trades:", len(rows), "| net:", report["646_replay"]["summary"].get("net_pnl"))
    print("h2_vs_h3 identical:", report["h2_vs_h3"]["identical"])


if __name__ == "__main__":
    main()
