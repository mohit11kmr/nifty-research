"""Phase E: frozen-strategy historical replay (MEASUREMENT ONLY).

Replays the exact frozen decision logic (precision_signals 6-layer
confluence + auto_paper_runner execution model) day-by-day over the
evaluable window with STRICT no-lookahead data windowing:

  * indicators recomputed on rows <= t
  * regime gate resolved with VIX as of t (slice), NOT the global latest row
  * options layer uses only OI snapshots dated <= t (latest of those)
  * contract expiry = ACTUAL historical weekly expiry per day (Phase F3:
    canonical single-owner service expiry_calendar.py -> historical calendar
    data/historical/expiry_calendar.csv - Thursday thru 2025-08-28, Tuesday
    from 2025-09-02, holiday Monday shifts; the SAME source the paper exit
    engine uses). Entry uses the actual contract; square-off happens on the
    contract's real expiry date.
  * institutional layer uses only FII/DII rows dated <= t
  * ML ensemble trained walk-forward on ml_features rows <= t
    (frozen train_super_ai_ensemble trains on the FULL file and predicts
    the last bar = lookahead in replay; the SAME hyperparams/80-20 split
    are reproduced per-day here - documented deviation, not a strategy change)

Production isolation: this script ONLY reads data/* caches and writes to
an output dir passed via --out. It never touches ground_truth.db,
paper_account.json, or any data/* file.

Exit/sizing/cost model (frozen, source-verified):
  * entry gate = precision_signals grade/action only (auto_paper_runner.py)
  * lots=1 (75 qty); entry premium = chain LTP else BS fallback (sigma 0.15)
  * ATR = max(10.0, entry*0.25); SL = max(2.0, entry-1.5*ATR)
  * target = entry + 2*(entry-SL); trigger mark<=SL*1.001 / mark>=TP*0.999
  * expiry square-off on the actual historical weekly expiry (Phase F3
    canonical service; Thursday through 2025-08-28, Tuesday from 2025-09-02)
  * commission COST_PER_TRADE=40.0/order; slippage SLIPPAGE_PCT=0.015
    adverse (BUY ref*(1+slip), SELL ref*(1-slip))
"""
import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import indicators            # noqa: E402
import market_brain          # noqa: E402
import oi_intel              # noqa: E402
import skew                  # noqa: E402
import institutional         # noqa: E402
import greeks                # noqa: E402
import expiry_calendar as exp_cal  # noqa: E402  (canonical expiry service, Phase F3)
from cost_model import COST_PER_TRADE, SLIPPAGE_PCT  # noqa: E402

LOT_SIZE = 75
BS_SIGMA = 0.15
R = 0.06
WINDOW_START = dt.date(2025, 8, 13)
WINDOW_END = dt.date(2026, 8, 13)
MIN_WARMUP_ROWS = 30

# frozen constants
SL_BAND = 1.001
TP_BAND = 0.999


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 16), b""):
            h.update(c)
    return h.hexdigest()


def load_inputs():
    nifty = pd.read_csv(os.path.join(ROOT, "data", "nifty_history.csv"))
    nifty["date"] = pd.to_datetime(nifty["date"])
    nifty = nifty.sort_values("date").reset_index(drop=True)

    vix = pd.read_csv(os.path.join(ROOT, "data", "india_vix.csv"),
                      parse_dates=["date"]).sort_values("date").reset_index(drop=True)

    fii = pd.read_csv(os.path.join(ROOT, "data", "fii_dii_history.csv"))
    fii["date"] = pd.to_datetime(fii["date"])
    fii = fii.sort_values("date").reset_index(drop=True)

    ml = pd.read_csv(os.path.join(ROOT, "data", "ml_features.csv"))
    if "date" in ml.columns:
        ml["date"] = pd.to_datetime(ml["date"])
    ml = ml.sort_values("date").reset_index(drop=True)

    snaps = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "oi_snapshots", "NIFTY_*.csv"))):
        b = os.path.basename(p).replace("NIFTY_", "").replace(".csv", "")
        try:
            d = pd.to_datetime(b).date()
        except Exception:
            continue
        snaps[d] = pd.read_csv(p)
    return nifty, vix, fii, ml, snaps


def bs_premium(spot, strike, t_days, sigma=BS_SIGMA, side="CE"):
    try:
        g = greeks.bs_price_and_greeks(spot, strike, max(int(t_days), 1), sigma, side=side, r=R)
        return round(float(g["price"]), 2)
    except Exception:
        return None


def vix_snapshot_at(vix, d):
    sub = vix[vix["date"] <= pd.Timestamp(d)]
    if sub.empty:
        return None
    last = sub.iloc[-1]
    level = float(last["close"])
    hist = sub["close"].dropna()
    pctile = float((hist < level).mean() * 100)
    zone = ("VIX_CHEAP" if level < 12 else "VIX_NORMAL" if level < 16
            else "VIX_RICH" if level < 20 else "VIX_HIGH" if level < 25 else "VIX_PANIC")
    return {"level": round(level, 2), "zone": zone, "percentile": round(pctile, 0)}


def regime_gate_at(nifty_slice, vix_snapshot):
    """Replicates regime_filter.trade_plan() gate resolution with NO lookahead
    (confidence fixed at 50 / bias NEUTRAL: precision_signals calls trade_plan()
    without a verdict)."""
    row = nifty_slice.iloc[-1]
    regime, _ = regime_filter_detect(row, nifty_slice)
    profile_gate = {"TREND_HV": "TRADE", "TREND_LV": "TRADE",
                    "RANGE_HV": "SMALL", "RANGE_LV": "NO_TRADE"}[regime]
    confidence, bias = 50.0, "NEUTRAL"
    hard_block = vix_snapshot is not None and vix_snapshot["zone"] == "VIX_PANIC" and confidence < 60
    if hard_block:
        gate, action = "NO_TRADE", "STAY OUT - VIX PANIC"
    elif profile_gate == "NO_TRADE":
        gate, action = "NO_TRADE", "STAY OUT"
    elif profile_gate == "SMALL":
        gate, action = "TRADE_SMALL", "FADE EXTREMES ONLY, TIGHT STOPS"
    else:
        gate, action = "TRADE_REDUCED", "LOW CONFIDENCE - HALF SIZE"
    return regime, gate, action


def regime_filter_detect(row, df):
    """Copy of regime_filter.detect_regime(row, df) 4-regime classifier."""
    adx = row.get("adx", 0) or 0
    pdi = row.get("pdi", 0) or 0
    mdi = row.get("mdi", 0) or 0
    bb_upper = row.get("bb_upper", np.nan)
    bb_lower = row.get("bb_lower", np.nan)
    close = row.get("close", np.nan)
    trending = adx >= 25 and abs(pdi - mdi) >= 5
    high_vol = False
    try:
        hist_width = ((df["bb_upper"] - df["bb_lower"]) / df["close"]).dropna()
        cur_width = (bb_upper - bb_lower) / max(close, 1e-9)
        pctile = float((hist_width.values < cur_width).mean() * 100)
        high_vol = pctile >= 60
    except Exception:
        pass
    if trending:
        return ("TREND_HV" if high_vol else "TREND_LV"), None
    return ("RANGE_HV" if high_vol else "RANGE_LV"), None


def technical_verdict_at(nifty_slice):
    mb_regime, _ = market_brain.detect_regime(nifty_slice, nifty_slice.iloc[-1])
    votes, score, total = market_brain.directional_consensus(nifty_slice, nifty_slice.iloc[-1])
    verdict = market_brain.make_verdict(nifty_slice, nifty_slice.iloc[-1], mb_regime, score, total)
    return (verdict.get("bias", "NEUTRAL"), verdict.get("strength", "LOW"),
            verdict, score, total)


def options_layer_at(snaps, d, spot, tech_bias):
    """Uses only snapshots dated <= d (latest of those) - no lookahead."""
    avail = [sd for sd in snaps if sd <= d]
    if not avail:
        return {"status": "NO_SNAPSHOT", "pcr": None, "max_pain": None, "walls": {}}
    cdf = snaps[max(avail)]
    try:
        pcr_data = oi_intel.pcr_and_pain(cdf, spot=spot)
        walls = oi_intel.oi_walls(cdf, spot=spot) or {}
        skew_data = skew.compute_iv_skew(cdf, spot=spot)
        pcr = pcr_data.get("pcr")
        max_pain = pcr_data.get("max_pain")
        if pcr is None:
            return {"status": "MIXED", "pcr": None, "max_pain": max_pain, "walls": walls}
        oi_passed = (pcr > 1.2 and tech_bias == "CALL") or (pcr < 0.8 and tech_bias == "PUT")
        return {"status": "PASSED" if oi_passed else "MIXED", "pcr": round(float(pcr), 3),
                "max_pain": max_pain, "walls": walls, "skew_bias": skew_data.get("bias"),
                "snapshot": str(max(avail))}
    except Exception as e:
        return {"status": "ERROR", "pcr": None, "max_pain": None, "walls": {}, "error": str(e)[:80]}


def institutional_layer_at(fii, d):
    sub = fii[fii["date"] <= pd.Timestamp(d)]
    if sub.empty:
        return {"status": "NO_DATA", "fii_sentiment": None}
    try:
        s = institutional.institutional_scan(sub)
        sent = s.get("fii_sentiment", "NEUTRAL") if s else "NEUTRAL"
        return {"status": "PASSED" if sent != "NEUTRAL" else "NEUTRAL",
                "fii_sentiment": sent,
                "fii_net": s.get("fii_net") if s else None,
                "fii_5d": s.get("fii_5d") if s else None}
    except Exception as e:
        return {"status": "ERROR", "fii_sentiment": None, "error": str(e)[:80]}


def ml_predict_at(ml, d):
    """Walk-forward replica of super_ai_ml.train_super_ai_ensemble on rows <= d."""
    sub = ml[ml["date"] <= pd.Timestamp(d)]
    if len(sub) < 100:
        return {"status": "NO_DATA", "verdict": None, "prob": None, "accs": {}}
    df = sub.copy()
    if "target_up" not in df.columns:
        df["target_up"] = (df["close"].shift(-1) > df["close"]).astype(int)
    df = df.bfill().ffill().fillna(0)
    features = [c for c in df.columns if c not in
                ["date", "target", "target_up", "close", "high", "low", "open"]]
    X = df[features].astype(np.float64)
    y = df["target_up"].astype(int)
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    models, scores, votes = {}, {}, []
    try:
        import xgboost as xgb
        m = xgb.XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.05,
                              random_state=42, n_jobs=1)
        m.fit(X_train, y_train)
        models["xgboost"] = m
        scores["xgboost"] = round(m.score(X_test, y_test) * 100, 2)
    except Exception as e:
        scores["xgboost"] = f"Error: {str(e)[:40]}"
    try:
        import lightgbm as lgb
        m = lgb.LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.05,
                               random_state=42, verbose=-1, num_threads=1)
        m.fit(X_train, y_train)
        models["lightgbm"] = m
        scores["lightgbm"] = round(m.score(X_test, y_test) * 100, 2)
    except Exception as e:
        scores["lightgbm"] = f"Error: {str(e)[:40]}"
    try:
        from sklearn.ensemble import RandomForestClassifier
        m = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42, n_jobs=1)
        m.fit(X_train, y_train)
        models["random_forest"] = m
        scores["random_forest"] = round(m.score(X_test, y_test) * 100, 2)
    except Exception as e:
        scores["random_forest"] = f"Error: {str(e)[:40]}"

    latest = X.iloc[[-1]]
    for name, m in models.items():
        votes.append({"model": name, "prediction": int(m.predict(latest)[0]),
                      "bullish_probability": round(float(m.predict_proba(latest)[0][1]), 4)})
    if not votes:
        return {"status": "ERROR", "verdict": None, "prob": None, "accs": scores}
    avg = float(np.mean([v["bullish_probability"] for v in votes]))
    verdict = ("BULLISH_CALL" if avg > 0.55 else "BEARISH_PUT" if avg < 0.45
               else "NEUTRAL_SIDEWAYS")
    return {"status": "PASSED" if verdict != "NEUTRAL_SIDEWAYS" else "NEUTRAL",
            "verdict": verdict, "prob": round(avg, 4), "accs": scores,
            "bars": len(df)}


def price_strike_lookup(snaps, d, strike, side, expiry=None):
    """Chain LTP for strike on snapshot dated d (if exists), else None.

    Phase F2: when expiry is given, the mark comes from that specific contract
    (expiry + strike); otherwise the shortest-dated listed expiry at the strike
    (pre-F2 behavior).
    """
    cdf = snaps.get(d)
    if cdf is None or "strike" not in cdf.columns:
        return None
    row = cdf[cdf["strike"] == strike]
    if expiry is not None and "expiry" in cdf.columns:
        row = row[row["expiry"] == expiry.strftime("%d-%b-%Y")]
    if row.empty:
        return None
    r = row.iloc[0]
    col = "ce_ltp" if side == "CE" else "pe_ltp"
    v = r.get(col)
    try:
        v = float(v)
        return v if v > 0 else None
    except Exception:
        return None


def simulate_trade(t, spot, entry, sl, target, strike, side, expiry,
                   nifty, snaps, nifty_dates):
    """Day-level premium path. Returns close dict or None if still open."""
    idx = nifty_dates.index(t)
    fill_in = entry * (1 + SLIPPAGE_PCT)
    log = []
    for j in nifty_dates[idx + 1:]:
        row = nifty[nifty["date"] == pd.Timestamp(j)].iloc[0]
        spot_j = float(row["close"])
        ttm = max((expiry - j).days, 1)
        ltp = price_strike_lookup(snaps, j, strike, side, expiry=expiry)
        mark = ltp if ltp is not None else bs_premium(spot_j, strike, ttm, BS_SIGMA, side)
        if mark is None:
            continue
        square_off_due = j == expiry
        if square_off_due:
            fill_out = mark * (1 - SLIPPAGE_PCT)
            pnl = (fill_out - fill_in) * LOT_SIZE - 2 * COST_PER_TRADE
            return {"exit_date": str(j), "reason": "EXPIRY_SQUARE_OFF",
                    "exit_mark": mark, "fill_out": fill_out, "net_pnl": round(pnl, 2),
                    "days_held": (j - t).days, "log": log}
        if mark <= sl * SL_BAND:
            fill_out = mark * (1 - SLIPPAGE_PCT)
            pnl = (fill_out - fill_in) * LOT_SIZE - 2 * COST_PER_TRADE
            return {"exit_date": str(j), "reason": "STOP_LOSS", "exit_mark": mark,
                    "fill_out": fill_out, "net_pnl": round(pnl, 2), "days_held": (j - t).days,
                    "log": log}
        if target and mark >= target * TP_BAND:
            fill_out = mark * (1 - SLIPPAGE_PCT)
            pnl = (fill_out - fill_in) * LOT_SIZE - 2 * COST_PER_TRADE
            return {"exit_date": str(j), "reason": "TAKE_PROFIT", "exit_mark": mark,
                    "fill_out": fill_out, "net_pnl": round(pnl, 2), "days_held": (j - t).days,
                    "log": log}
        log.append({"date": str(j), "spot": spot_j, "mark": mark})
    return None


def evaluate_day(d, nifty, vix, fii, ml, snaps, nifty_dates):
    sdf = nifty[nifty["date"] <= pd.Timestamp(d)].copy()
    rec = {"date": str(d), "spot": None, "vix": None, "vix_zone": None,
           "regime": None, "gate": None}
    if len(sdf) < MIN_WARMUP_ROWS:
        rec["skip"] = "warmup"
        return rec
    if "adx" not in sdf.columns:
        indicators.add_all_indicators(sdf)
    sdf = sdf.dropna(subset=["adx", "bb_upper", "bb_lower"]).reset_index(drop=True)
    if len(sdf) < MIN_WARMUP_ROWS:
        rec["skip"] = "warmup"
        return rec
    row = sdf.iloc[-1]
    spot = float(row["close"])
    rec["spot"] = round(spot, 2)

    vix_snap = vix_snapshot_at(vix, d)
    if vix_snap:
        rec["vix"] = vix_snap["level"]
        rec["vix_zone"] = vix_snap["zone"]

    regime, gate, _ = regime_gate_at(sdf, vix_snap)
    rec["regime"] = regime
    rec["gate"] = gate
    l1_open = gate != "NO_TRADE" and regime != "RANGE_LV"
    rec["l1_status"] = "PASSED" if l1_open else "BLOCKED"

    rec["l2_status"] = "PASSED"  # frozen audit: daily_pnl=0, no expiry/event -> APPROVED

    bias, strength, verdict, score, total = technical_verdict_at(sdf)
    rec["l3_status"] = "PASSED" if bias != "NEUTRAL" else "NEUTRAL"
    rec["tech_bias"] = bias
    rec["tech_strength"] = strength
    rec["tech_conf"] = verdict.get("confidence") if verdict else None
    rec["tech_score_total"] = f"{score}/{total}"

    ores = options_layer_at(snaps, d, spot, bias)
    rec["l4_status"] = ores["status"]
    rec["pcr"] = ores.get("pcr")
    rec["max_pain"] = ores.get("max_pain")
    rec["walls"] = ores.get("walls") or {}

    ires = institutional_layer_at(fii, d)
    rec["l5_status"] = ires["status"]
    rec["fii_sentiment"] = ires.get("fii_sentiment")
    rec["fii_net"] = ires.get("fii_net")
    rec["fii_5d"] = ires.get("fii_5d")

    mres = ml_predict_at(ml, d)
    rec["l6_status"] = mres["status"]
    rec["ml_verdict"] = mres.get("verdict")
    rec["ml_prob"] = mres.get("prob")
    rec["ml_accs"] = mres.get("accs") or {}

    score_c = 0
    for k in ("l1_status", "l2_status", "l3_status", "l4_status", "l5_status", "l6_status"):
        if rec[k] == "PASSED":
            score_c += 1
    rec["confluence_score"] = score_c
    rec["max_score"] = 6
    rec["confluence_pct"] = round(score_c / 6 * 100, 1)

    l1_ok = rec["l1_status"] == "PASSED"
    if score_c >= 5 and l1_ok:
        rec["grade"] = "A+"
        rec["action"] = f"HIGH_CONVICTION_{bias}"
    elif score_c >= 4 and l1_ok:
        rec["grade"] = "A"
        rec["action"] = f"MODERATE_{bias}"
    else:
        rec["grade"] = "NO_SIGNAL"
        rec["action"] = "STAY_OUT"

    # entry params (frozen runner path) only for directional candidates
    directional = rec["action"].startswith(("HIGH_CONVICTION", "MODERATE"))
    rec["candidate"] = directional
    if directional:
        side = "CE" if ("BUY_CALL" in rec["action"] or "BULLISH" in rec["action"]) else "PE"
        rec["option_type"] = side
        walls = rec["walls"]
        if side == "CE" and walls.get("nearest_resistance"):
            strike = round(walls["nearest_resistance"] / 50) * 50
        elif side == "PE" and walls.get("nearest_support"):
            strike = round(walls["nearest_support"] / 50) * 50
        else:
            strike = round((spot * (1.01 if side == "CE" else 0.99)) / 50) * 50
        rec["strike"] = strike
        expiry = exp_cal.get_expiry_for_trade_date(d)
        if expiry is None:
            rec["expiry"] = None
            rec["contract_status"] = "CONTRACT_UNAVAILABLE"
            rec["candidate"] = False
            return rec
        rec["expiry"] = str(expiry)
        rec["expiry_weekday"] = expiry.strftime("%A")
        rec["days_to_expiry"] = (expiry - d).days
        # Phase F2 contract validation: (expiry, strike, side) must exist in the
        # day-d chain. Unavailable contract -> CONTRACT_UNAVAILABLE, no trade,
        # no silent substitution, no fabricated price.
        cdf = snaps.get(d)
        contract_ok = (cdf is not None and "strike" in cdf.columns
                       and "expiry" in cdf.columns
                       and bool(((cdf["expiry"] == expiry.strftime("%d-%b-%Y"))
                                 & (cdf["strike"] == strike)).any()))
        rec["contract_status"] = "AVAILABLE" if contract_ok else "CONTRACT_UNAVAILABLE"
        if not contract_ok:
            rec["candidate"] = False
            return rec
        ttm = max((expiry - d).days, 1)
        ltp = price_strike_lookup(snaps, d, strike, side, expiry=expiry)
        entry = ltp if ltp is not None else bs_premium(spot, strike, ttm, BS_SIGMA, side)
        if not entry or entry <= 0:
            entry = round(spot * 0.006, 2)
        rec["entry_premium"] = round(entry, 2)
        atr = max(10.0, entry * 0.25)
        sl = round(max(2.0, entry - 1.5 * atr), 2)
        rec["sl_premium"] = sl
        rec["target_premium"] = round(entry + 2.0 * (entry - sl), 2)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("/tmp", "opencode", "phaseE"))
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    nifty, vix, fii, ml, snaps = load_inputs()
    nifty_dates = [d.date() for d in nifty["date"]]
    window = [d for d in nifty_dates if WINDOW_START <= d <= WINDOW_END]

    from multiprocessing import Pool
    results = []
    with Pool() as pool:
        tasks = [(d, nifty, vix, fii, ml, snaps, nifty_dates) for d in window]
        for i, rec in enumerate(pool.starmap(evaluate_day, tasks, chunksize=8)):
            results.append(rec)
    results.sort(key=lambda r: r["date"])

    # simulate candidate trades sequentially
    trades = []
    for rec in results:
        if not rec.get("candidate"):
            continue
        t = dt.date.fromisoformat(rec["date"])
        expiry = dt.date.fromisoformat(rec["expiry"])
        out = simulate_trade(t, rec["spot"], rec["entry_premium"], rec["sl_premium"],
                             rec["target_premium"], rec["strike"], rec["option_type"],
                             expiry, nifty, snaps, nifty_dates)
        trades.append({**rec, "simulation": out})

    # input fingerprints
    input_files = ["data/nifty_history.csv", "data/india_vix.csv",
                   "data/fii_dii_history.csv", "data/ml_features.csv"]
    fingerprints = {}
    for p in input_files:
        fp = os.path.join(ROOT, p)
        fingerprints[p] = {"sha256": sha256_file(fp),
                           "mtime": os.path.getmtime(fp),
                           "size": os.path.getsize(fp)}
    for sd in sorted(snaps):
        fingerprints[f"data/oi_snapshots/NIFTY_{sd}.csv"] = None
    cal_path = os.path.join(ROOT, "data", "historical", "expiry_calendar.csv")
    if os.path.exists(cal_path):
        fingerprints["data/historical/expiry_calendar.csv"] = {
            "sha256": sha256_file(cal_path), "size": os.path.getsize(cal_path)}

    out = {
        "run_id": run_id,
        "git_head": None,
        "input_fingerprints": fingerprints,
        "frozen_identity": {
            "confluence_thresholds": {"A_plus": 5, "A": 4, "requires_regime_pass": True},
            "cost": {"COST_PER_TRADE": COST_PER_TRADE, "SLIPPAGE_PCT": SLIPPAGE_PCT},
            "exit": {"SL_BAND": SL_BAND, "TP_BAND": TP_BAND,
                     "ATR_pct_of_entry": 0.25, "SL_ATR_MULT": 1.5, "RR": "1:2",
                     "expiry_weekday": "historical (Thu thru 2025-08-28, Tue from 2025-09-02)",
                     "lots": 1, "lot_size": LOT_SIZE},
            "ml_hyperparams": {"n_estimators": 100, "max_depth_xgb_lgb": 4,
                               "max_depth_rf": 5, "lr": 0.05, "random_state": 42,
                               "split": "0.8/0.2"},
            "deviations_documented": [
                "ML trained walk-forward per day (frozen fn trains on full file) - no-lookahead fix",
                "VIX/nifty/indicator slices <= t (frozen uses global last row) - no-lookahead fix",
                "OI snapshot chosen = latest dated <= t (frozen uses newest file on disk)",
                "Phase F2: contract expiry = actual historical weekly from expiry_calendar.csv "
                "(Thursday thru 2025-08-28, Tuesday from 2025-09-02, holiday Monday shifts) - "
                "replaces fixed next-Thursday model",
                "Phase F2: contract validation - candidate traded only if (expiry,strike,side) "
                "exists in the day-t chain; else CONTRACT_UNAVAILABLE (no substitute, no fabricated price)",
                "Phase F2: intraday marks use the specific (expiry,strike) contract LTP; BS(sigma=0.15) "
                "fallback at that contract's true TTM",
                "day-level mark = snapshot LTP else BS(sigma=0.15) at that day's close",
            ],
        },
        "window": {"start": str(WINDOW_START), "end": str(WINDOW_END),
                   "trading_days": len(window)},
        "daily": results,
        "trades": trades,
    }

    with open(os.path.join(args.out, f"results_{run_id}.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)

    # summary print
    print(f"run_id={run_id}  window={WINDOW_START}..{WINDOW_END}  days={len(window)}")
    print("--- decision funnel ---")
    grades = {}
    regimes = {}
    for r in results:
        grades[r["grade"]] = grades.get(r["grade"], 0) + 1
        regimes[r["regime"]] = regimes.get(r["regime"], 0) + 1
    print("grade:", dict(sorted(grades.items())))
    print("regime:", dict(sorted(regimes.items())))
    cand = [r for r in results if r.get("candidate")]
    print(f"directional candidates: {len(cand)}/{len(results)}")
    for tr in trades:
        sim = tr.get("simulation")
        simtxt = (sim["reason"] + " net " + str(sim["net_pnl"]) if sim
                  else "STILL_OPEN")
        print("  ", tr["date"], tr["regime"], tr["gate"], tr["grade"], tr["action"],
              f"confluence {tr['confluence_score']}/6",
              f"strike {tr['strike']} {tr.get('option_type')}",
              "entry", tr["entry_premium"], "SL", tr["sl_premium"], "TP", tr["target_premium"],
              "->", simtxt)
    if trades:
        nets = [tr["simulation"]["net_pnl"] for tr in trades if tr["simulation"]]
        wins = [n for n in nets if n > 0]
        losses = [n for n in nets if n <= 0]
        gross_win, gross_loss = sum(wins), sum(losses)
        print(f"--- trades: n={len(nets)} win={len(wins)} loss={len(losses)} "
              f"winrate={len(wins)/len(nets)*100:.1f}% pf={(gross_win/abs(gross_loss)) if gross_loss else float('inf'):.2f} "
              f"net={sum(nets):,.0f} Rupees")
    print(f"output: {args.out}/results_{run_id}.json")


if __name__ == "__main__":
    main()
