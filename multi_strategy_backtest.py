"""Phase H: multi-strategy fair comparison (MEASUREMENT ONLY).

Runs four candidates over the SAME frozen dataset, expiry calendar, cost
model, slippage model and evaluation framework:

  A - Current control (frozen 6-layer funnel -> naked directional option).
      Executed EXACTLY by the authoritative backtest_frozen.py functions
      (evaluate_day + simulate_trade) so the control reproduces the F3
      baseline byte-for-byte.
  B - Defined-risk directional spread (bull call / bear put vertical),
      same entry funnel restricted to eligible trend regimes, deterministic
      strike construction (long leg = control strike, short leg = listed
      strike nearest long +/- SPREAD_WIDTH), same ATR SL/TP formula applied
      to the net spread premium.
  C - Defined-risk RANGE_HV iron condor (premium_seller structure) using
      the shared execution model (chain-LTP pricing, COST_PER_TRADE per
      order, SLIPPAGE_PCT adverse per fill, lot=75, expiry calendar).
  D - No-trade control (RANGE_LV-style permanent abstention): 0 trades.

Production isolation: this script only READS data/* caches and WRITES to
--out. It never touches ground_truth.db, paper_account.json, or any
data/* file. Deterministic: single-process evaluation, fixed seeds, no
randomness; two runs produce byte-identical trade lists/metrics.
"""
import argparse
import datetime as dt
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

import backtest_frozen as bf  # noqa: E402  (authoritative frozen control engine)
import expiry_calendar as exp_cal  # noqa: E402  (canonical expiry service)
from cost_model import COST_PER_TRADE, SLIPPAGE_PCT  # noqa: E402

LOT_SIZE = bf.LOT_SIZE
BS_SIGMA = bf.BS_SIGMA
WINDOW_START = bf.WINDOW_START
WINDOW_END = bf.WINDOW_END
MIN_WARMUP_ROWS = bf.MIN_WARMUP_ROWS
SL_BAND = bf.SL_BAND
TP_BAND = bf.TP_BAND

# Frozen candidate constants (freeze BEFORE results are seen - no tuning).
SPREAD_WIDTH = 500.0          # B: vertical width in index points (single integer constant)
SPREAD_VIX_MAX = 25.0         # C: iron condor VIX ceiling (premium_seller RICH/HIGH gate)
SPREAD_VIX_MIN = 16.0         # C: iron condor VIX floor
CONDOR_OTM_PCT = 0.02         # C: short legs ~2% OTM (premium_seller structure)
CONDOR_WING_PTS = 150.0       # C: wings 150 pts further OTM (premium_seller structure)
CONDOR_TARGET_PCT = 0.50      # C: book +50% of max credit
CONDOR_STOP_MULT = 2.0        # C: cut when credit doubles
CONDOR_CLOSE_BEFORE_DAYS = 2  # C: close N calendar days before expiry
CAPITAL = 100000.0            # same starting capital basis for all candidates
RISK_PCT_PER_TRADE = 0.01     # documented reference only (all candidates size 1 lot)

CANDIDATE_SPECS = {
    "A_CURRENT_CONTROL": {
        "name": "Current frozen strategy / control",
        "instrument": "naked long directional option (1 lot CE/PE), as frozen in backtest_frozen.py",
        "entry_gate": "6-layer confluence funnel (l1 regime gate passed, l2 approved, "
                      "l3 technical bias != NEUTRAL, l4 OI/skew, l5 institutional, l6 ML) "
                      "grade A+ (>=5/6) or A (>=4/6)",
        "direction_logic": "frozen side selection in backtest_frozen.py "
                           "('BUY_CALL'/'BULLISH' in action -> CE else PE); documented frozen defect => all-PUT in F2/F3",
        "regime_restriction": "none beyond l1 gate (RANGE_LV / NO_TRADE excluded)",
        "expiry_rule": "expiry_calendar.get_expiry_for_trade_date(d) (canonical historical weekly)",
        "strike_rule": "wall strike (nearest resistance/support) else spot*(1.01/0.99), rounded to 50",
        "entry_price": "day-d chain LTP for (expiry,strike,side) else BS(sigma=0.15)",
        "stop_rule": "SL = max(2.0, entry - 1.5*ATR), ATR = max(10.0, 0.25*entry); trigger mark<=SL*1.001",
        "target_rule": "target = entry + 2*(entry-SL); trigger mark>=TP*0.999",
        "exit_rule": "STOP_LOSS / TAKE_PROFIT / EXPIRY_SQUARE_OFF (contract's real expiry)",
        "position_size": "1 lot (75 qty)",
        "cost_model": "COST_PER_TRADE=40.0 per order (2 orders round-trip = 80)",
        "slippage_model": "SLIPPAGE_PCT=0.015 adverse per fill",
        "data_requirements": "nifty_history, india_vix, fii_dii_history, ml_features, oi_snapshots, expiry_calendar",
        "unsupported_conditions": "contract not listed -> CONTRACT_UNAVAILABLE, no trade, no substitute",
        "frozen_reference": "backtest_frozen.py F3 baseline: 48 trades, win 33.3%, PF 1.01, net 1906.43",
    },
    "B_DIRECTIONAL_SPREAD": {
        "name": "Defined-risk directional vertical spread",
        "instrument": "vertical spread (bull call spread / bear put spread), 1 lot (75 qty)",
        "entry_gate": "SAME 6-layer confluence funnel as control (identical candidate days)",
        "regime_restriction": "TREND_HV or TREND_LV only (eligible trend regime); RANGE_* excluded",
        "direction_logic": "bias from layer-3 technical verdict / action: CALL-bias -> bull call spread, "
                           "PUT-bias -> bear put spread (correct directional mapping, frozen for B)",
        "expiry_rule": "expiry_calendar.get_expiry_for_trade_date(d) (canonical historical weekly)",
        "strike_rule": "long leg = wall strike (nearest resistance/support) else spot*(1.01/0.99) "
                       "rounded to 50, recomputed with B's correct side; "
                       "short leg = listed strike nearest to long +/- SPREAD_WIDTH(500) in day-d chain",
        "entry_price": "net debit = long LTP - short LTP (chain LTP else BS(sigma=0.15) per leg); "
                       "skip if net debit <= 0 or either leg unlisted",
        "stop_rule": "SAME formula as control applied to net debit: ATR = max(10.0, 0.25*net_debit), "
                     "SL = max(2.0, net_debit - 1.5*ATR); trigger on net mark",
        "target_rule": "target = net_debit + 2*(net_debit-SL); trigger on net mark",
        "exit_rule": "STOP_LOSS / TAKE_PROFIT / EXPIRY_SQUARE_OFF (net intrinsic at real expiry); "
                     "max loss bounded by width - net debit",
        "position_size": "1 lot (75 qty)",
        "cost_model": "COST_PER_TRADE=40.0 per order (4 orders round-trip = 160)",
        "slippage_model": "SLIPPAGE_PCT=0.015 adverse per fill (4 fills round-trip)",
        "data_requirements": "same dataset as control",
        "unsupported_conditions": "short leg not listed or net debit<=0 -> CONTRACT_UNAVAILABLE, no trade",
        "frozen_reference": "PHASE-H spec frozen before results; width 500 not tuned",
    },
    "C_RANGE_HV_IRON_CONDOR": {
        "name": "Defined-risk RANGE_HV iron condor (premium_seller structure)",
        "instrument": "iron condor (short 2% OTM strangle + 150-pt wings), 1 lot (75 qty)",
        "entry_gate": "regime == RANGE_HV and 16.0 <= VIX < 25.0 (premium_seller RICH/HIGH selling window)",
        "regime_restriction": "RANGE_HV only (frozen; narrows premium_seller gate that also allowed "
                              "RANGE_LV / TREND_LV)",
        "direction_logic": "market-neutral (credit collection)",
        "expiry_rule": "expiry_calendar.get_expiry_for_trade_date(d) (canonical historical weekly)",
        "strike_rule": "short call Kc = round(S*1.02/50)*50, short put Kp = round(S*0.98/50)*50; "
                       "wings = nearest listed strike to Kc+150 / Kp-150",
        "entry_price": "net credit = (Kc+Kp)-(wings) from chain LTP else BS(sigma=0.15) per leg; "
                       "skip if credit <= 0 or any leg unlisted",
        "stop_rule": "cut when net credit >= 2.0 * entry credit (premium_seller STOP_MULT)",
        "target_rule": "book at credit <= 0.5 * entry credit (premium_seller PROFIT_TARGET_PCT)",
        "exit_rule": "TARGET / STOP / TIME (close when days_since_entry >= DTE - 2) / EXPIRY / EOD",
        "position_size": "1 lot (75 qty) - shared sizing convention; premium_seller's original "
                         "1%-capital units replaced by shared 1-lot basis (documented difference)",
        "cost_model": "COST_PER_TRADE=40.0 per order (8 orders round-trip = 320)",
        "slippage_model": "SLIPPAGE_PCT=0.015 adverse per fill (8 fills round-trip)",
        "data_requirements": "same dataset as control",
        "unsupported_conditions": "any leg unlisted or credit<=0 -> CONTRACT_UNAVAILABLE, no trade",
        "frozen_reference": "premium_seller.py deterministic structure (frozen constants above)",
    },
    "D_NO_TRADE": {
        "name": "No-trade control",
        "instrument": "none",
        "entry_gate": "never (permanent RANGE_LV-style abstention)",
        "direction_logic": "none",
        "regime_restriction": "all regimes -> NO TRADE",
        "expiry_rule": "n/a",
        "strike_rule": "n/a",
        "entry_price": "n/a",
        "stop_rule": "n/a",
        "target_rule": "n/a",
        "exit_rule": "n/a",
        "position_size": "0",
        "cost_model": "0",
        "slippage_model": "0",
        "data_requirements": "none",
        "unsupported_conditions": "n/a",
        "frozen_reference": "control condition, not a trading strategy",
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(p: str) -> str:
    return bf.sha256_file(p)


def dir_sha256(path: str) -> str:
    """Order-stable hash of all files in a directory (names sorted)."""
    h = hashlib.sha256()
    for name in sorted(os.listdir(path)):
        fp = os.path.join(path, name)
        if os.path.isfile(fp):
            h.update(name.encode())
            h.update(b"\x00")
            h.update(bf.sha256_file(fp).encode())
    return h.hexdigest()


def load_inputs(data_root=None):
    """Load the frozen dataset. data_root overrides the repo root so a snapshot
    of the input files can be frozen for reproducible comparison runs."""
    if data_root:
        bf.ROOT = data_root
        exp_cal.CALENDAR_CSV = os.path.join(data_root, "data", "historical", "expiry_calendar.csv")
    return bf.load_inputs()


def nifty_dates_of(nifty):
    return [d.date() for d in nifty["date"]]


def day_records(window, nifty, vix, fii, ml, snaps, nifty_dates):
    """Evaluate every day with the authoritative frozen funnel. Uses a process
    Pool exactly like backtest_frozen.main() - each day is independent and
    Pool.map preserves input order, so results are deterministic."""
    from multiprocessing import Pool
    tasks = [(d, nifty, vix, fii, ml, snaps, nifty_dates) for d in window]
    with Pool() as pool:
        results = pool.starmap(bf.evaluate_day, tasks, chunksize=8)
    return {str(d): rec for d, rec in zip(window, results)}


def contract_mark(snaps, d, strike, side, expiry, spot=None):
    """Day-level mark for one (expiry, strike, side) contract: chain LTP else
    BS(sigma=0.15) at the contract's true TTM. Mirrors backtest_frozen."""
    ttm = max((expiry - d).days, 1)
    ltp = bf.price_strike_lookup(snaps, d, strike, side, expiry=expiry)
    if ltp is not None:
        return ltp
    if spot is None:
        return None
    return bf.bs_premium(spot, strike, ttm, BS_SIGMA, side)


def listed_strikes_for(snaps, d, expiry, side):
    cdf = snaps.get(d)
    if cdf is None or "strike" not in cdf.columns:
        return []
    sub = cdf[cdf["expiry"] == expiry.strftime("%d-%b-%Y")]
    return sorted(sub["strike"].unique().tolist())


def nearest_strike(target, listed):
    if not listed:
        return None
    return min(listed, key=lambda k: abs(k - target))


# ---------------------------------------------------------------------------
# Candidate A - control (authoritative backtest_frozen path, no modification)
# ---------------------------------------------------------------------------
def run_candidate_a(recs, nifty, snaps, nifty_dates):
    trades = []
    for d_str, rec in sorted(recs.items()):
        if not rec.get("candidate"):
            continue
        t = dt.date.fromisoformat(rec["date"])
        expiry = dt.date.fromisoformat(rec["expiry"])
        sim = bf.simulate_trade(t, rec["spot"], rec["entry_premium"], rec["sl_premium"],
                                rec["target_premium"], rec["strike"], rec["option_type"],
                                expiry, nifty, snaps, nifty_dates)
        if sim:
            sim["slippage"] = round(SLIPPAGE_PCT * (rec["entry_premium"] + sim["exit_mark"]) * LOT_SIZE, 2)
        mfe, mae = _control_mfe_mae(t, expiry, rec["strike"], rec["option_type"],
                                    rec["entry_premium"], nifty, snaps, nifty_dates, sim)
        trades.append(_finalize(rec, sim, mfe, mae))
    return trades


def _control_mfe_mae(t, expiry, strike, side, entry, nifty, snaps, nifty_dates, sim):
    """Replay the day-level mark path (same pricing fns) to compute MFE/MAE in
    Rupees (gross, before fees). Does NOT alter the trade outcome."""
    idx = nifty_dates.index(t)
    best, worst = 0.0, 0.0
    seen = []
    for j in nifty_dates[idx + 1:]:
        row = nifty[nifty["date"] == pd.Timestamp(j)].iloc[0]
        mark = contract_mark(snaps, j, strike, side, expiry, spot=float(row["close"]))
        if mark is None:
            continue
        seen.append((j, mark))
        if sim and j > dt.date.fromisoformat(sim["exit_date"]):
            break
    for j, mark in seen:
        pnl = (mark - entry) * LOT_SIZE
        best = max(best, pnl)
        worst = min(worst, pnl)
    if sim:
        em = sim["exit_mark"]
        pnl = (em - entry) * LOT_SIZE
        best = max(best, pnl)
        worst = min(worst, pnl)
    return round(best, 2), round(worst, 2)


# ---------------------------------------------------------------------------
# Candidate B - defined-risk directional vertical spread
# ---------------------------------------------------------------------------
def build_spread(rec, snaps, d, side, long_strike):
    """Return (long_leg, short_leg) strikes or None if unavailable/invalid."""
    expiry = dt.date.fromisoformat(rec["expiry"])
    sign = 1 if side == "CE" else -1
    target = long_strike + sign * SPREAD_WIDTH
    listed = listed_strikes_for(snaps, d, expiry, side)
    short_strike = nearest_strike(target, listed)
    if short_strike is None:
        return None
    long_ok = short_ok = False
    cdf = snaps.get(d)
    if cdf is not None and "strike" in cdf.columns and "expiry" in cdf.columns:
        e = expiry.strftime("%d-%b-%Y")
        long_ok = bool(((cdf["expiry"] == e) & (cdf["strike"] == long_strike)).any())
        short_ok = bool(((cdf["expiry"] == e) & (cdf["strike"] == short_strike)).any())
    if not (long_ok and short_ok):
        return None
    return long_strike, short_strike, side, expiry


def simulate_spread(t, spot, expiry, long_strike, short_strike, side,
                    nifty, snaps, nifty_dates):
    """Day-level spread path. Returns close dict or None if still open."""
    ttm0 = max((expiry - t).days, 1)
    long_in = bf.price_strike_lookup(snaps, t, long_strike, side, expiry=expiry)
    long_in = long_in if long_in is not None else bf.bs_premium(spot, long_strike, ttm0, BS_SIGMA, side)
    short_in = bf.price_strike_lookup(snaps, t, short_strike, side, expiry=expiry)
    short_in = short_in if short_in is not None else bf.bs_premium(spot, short_strike, ttm0, BS_SIGMA, side)
    if long_in is None or short_in is None:
        return {"error": "NO_PRICE"}
    net_debit = round(long_in - short_in, 2)
    if net_debit <= 0:
        return {"error": "INVALID_NET_DEBIT"}
    fill_in_net = round(long_in * (1 + SLIPPAGE_PCT) - short_in * (1 - SLIPPAGE_PCT), 2)
    atr = max(10.0, net_debit * 0.25)
    sl = round(max(2.0, net_debit - 1.5 * atr), 2)
    target = round(net_debit + 2.0 * (net_debit - sl), 2)

    idx = nifty_dates.index(t)
    mfe, mae = 0.0, 0.0
    log = []
    for j in nifty_dates[idx + 1:]:
        row = nifty[nifty["date"] == pd.Timestamp(j)].iloc[0]
        spot_j = float(row["close"])
        lm = contract_mark(snaps, j, long_strike, side, expiry, spot_j)
        sm = contract_mark(snaps, j, short_strike, side, expiry, spot_j)
        if lm is None or sm is None:
            continue
        net_mark = lm - sm
        pnl = (net_mark - net_debit) * LOT_SIZE
        mfe = max(mfe, pnl)
        mae = min(mae, pnl)
        square_off_due = j == expiry
        if square_off_due:
            fill_out_net = lm * (1 - SLIPPAGE_PCT) - sm * (1 + SLIPPAGE_PCT)
            net = (fill_out_net - fill_in_net) * LOT_SIZE - 4 * COST_PER_TRADE
            slip = SLIPPAGE_PCT * (long_in + short_in + lm + sm) * LOT_SIZE
            return {"exit_date": str(j), "reason": "EXPIRY_SQUARE_OFF", "exit_mark": round(net_mark, 2),
                    "fill_out": round(fill_out_net, 2), "net_pnl": round(net, 2),
                    "slippage": round(slip, 2),
                    "mfe": round(mfe, 2), "mae": round(mae, 2), "entry_net": net_debit,
                    "sl_net": sl, "target_net": target, "days_held": (j - t).days, "log": log}
        if net_mark <= sl * SL_BAND:
            fill_out_net = lm * (1 - SLIPPAGE_PCT) - sm * (1 + SLIPPAGE_PCT)
            net = (fill_out_net - fill_in_net) * LOT_SIZE - 4 * COST_PER_TRADE
            slip = SLIPPAGE_PCT * (long_in + short_in + lm + sm) * LOT_SIZE
            return {"exit_date": str(j), "reason": "STOP_LOSS", "exit_mark": round(net_mark, 2),
                    "fill_out": round(fill_out_net, 2), "net_pnl": round(net, 2),
                    "slippage": round(slip, 2),
                    "mfe": round(mfe, 2), "mae": round(mae, 2), "entry_net": net_debit,
                    "sl_net": sl, "target_net": target, "days_held": (j - t).days, "log": log}
        if net_mark >= target * TP_BAND:
            fill_out_net = lm * (1 - SLIPPAGE_PCT) - sm * (1 + SLIPPAGE_PCT)
            net = (fill_out_net - fill_in_net) * LOT_SIZE - 4 * COST_PER_TRADE
            slip = SLIPPAGE_PCT * (long_in + short_in + lm + sm) * LOT_SIZE
            return {"exit_date": str(j), "reason": "TAKE_PROFIT", "exit_mark": round(net_mark, 2),
                    "fill_out": round(fill_out_net, 2), "net_pnl": round(net, 2),
                    "slippage": round(slip, 2),
                    "mfe": round(mfe, 2), "mae": round(mae, 2), "entry_net": net_debit,
                    "sl_net": sl, "target_net": target, "days_held": (j - t).days, "log": log}
        log.append({"date": str(j), "spot": spot_j, "long_mark": lm, "short_mark": sm, "net_mark": round(net_mark, 2)})
    return None


def run_candidate_b(recs, nifty, snaps, nifty_dates):
    trades = []
    for d_str, rec in sorted(recs.items()):
        if not rec.get("candidate"):
            continue
        if rec["regime"] not in ("TREND_HV", "TREND_LV"):
            continue
        bias = rec.get("tech_bias")
        if bias == "CALL":
            side = "CE"
        elif bias == "PUT":
            side = "PE"
        else:
            continue
        walls = rec["walls"]
        spot = rec["spot"]
        if side == "CE" and walls.get("nearest_resistance"):
            long_strike = round(walls["nearest_resistance"] / 50) * 50
        elif side == "PE" and walls.get("nearest_support"):
            long_strike = round(walls["nearest_support"] / 50) * 50
        else:
            long_strike = round((spot * (1.01 if side == "CE" else 0.99)) / 50) * 50
        d = dt.date.fromisoformat(rec["date"])
        built = build_spread(rec, snaps, d, side, long_strike)
        if built is None:
            continue
        long_strike, short_strike, _, expiry = built
        sim = simulate_spread(d, rec["spot"], expiry, long_strike, short_strike, side,
                              nifty, snaps, nifty_dates)
        if sim is None:
            sim = {"status": "STILL_OPEN"}
        out = dict(rec)
        out["option_type"] = f"SPREAD_{side}"
        out["strike"] = long_strike
        out["short_strike"] = short_strike
        out["spread_width"] = abs(short_strike - long_strike)
        out["simulation"] = sim
        out["mfe"] = sim.get("mfe") if isinstance(sim, dict) else None
        out["mae"] = sim.get("mae") if isinstance(sim, dict) else None
        trades.append(out)
    return trades


# ---------------------------------------------------------------------------
# Candidate C - RANGE_HV iron condor (premium_seller structure, shared model)
# ---------------------------------------------------------------------------
def build_condor(spot, expiry, snaps, d):
    Kc = round(spot * (1 + CONDOR_OTM_PCT) / 50) * 50
    Kp = round(spot * (1 - CONDOR_OTM_PCT) / 50) * 50
    listed = listed_strikes_for(snaps, d, expiry, "CE")
    KcW = nearest_strike(Kc + CONDOR_WING_PTS, listed)
    KpW = nearest_strike(Kp - CONDOR_WING_PTS, listed)
    cdf = snaps.get(d)
    ok = cdf is not None and "strike" in cdf.columns and "expiry" in cdf.columns
    e = expiry.strftime("%d-%b-%Y")
    needed = [Kc, Kp, KcW, KpW]
    if ok and all(x is not None and ((cdf["expiry"] == e) & (cdf["strike"] == x)).any() for x in needed):
        return Kc, Kp, KcW, KpW
    return None


def condor_legs(snaps, d, expiry, Kc, Kp, KcW, KpW, spot):
    ttm = max((expiry - d).days, 1)
    legs = {}
    for name, strike, side in (("Kc", Kc, "CE"), ("Kp", Kp, "PE"),
                               ("KcW", KcW, "CE"), ("KpW", KpW, "PE")):
        m = bf.price_strike_lookup(snaps, d, strike, side, expiry=expiry)
        if m is None:
            m = bf.bs_premium(spot, strike, ttm, BS_SIGMA, side)
        legs[name] = m
    if any(v is None for v in legs.values()):
        return None
    return legs


def simulate_condor(t, spot, expiry, strikes, nifty, snaps, nifty_dates):
    Kc, Kp, KcW, KpW = strikes
    legs = condor_legs(snaps, t, expiry, Kc, Kp, KcW, KpW, spot)
    if legs is None:
        return {"error": "NO_PRICE"}
    entry_credit = round((legs["Kc"] + legs["Kp"]) - (legs["KcW"] + legs["KpW"]), 2)
    if entry_credit <= 0:
        return {"error": "INVALID_CREDIT"}
    # adverse fills: sell shorts at (1-slip), buy wings at (1+slip)
    fill_in = round(legs["Kc"] * (1 - SLIPPAGE_PCT) + legs["Kp"] * (1 - SLIPPAGE_PCT)
                    - legs["KcW"] * (1 + SLIPPAGE_PCT) - legs["KpW"] * (1 + SLIPPAGE_PCT), 2)
    dte = (expiry - t).days
    width_risk = (KcW - Kc)
    max_loss = width_risk - entry_credit

    idx = nifty_dates.index(t)
    mfe, mae = 0.0, 0.0
    log = []
    j = t
    for jj in nifty_dates[idx + 1:]:
        j = jj
        row = nifty[nifty["date"] == pd.Timestamp(jj)].iloc[0]
        spot_j = float(row["close"])
        legs_t = condor_legs(snaps, jj, expiry, Kc, Kp, KcW, KpW, spot_j)
        if legs_t is None:
            continue
        cur_credit = round((legs_t["Kc"] + legs_t["Kp"]) - (legs_t["KcW"] + legs_t["KpW"]), 2)
        pnl = (entry_credit - cur_credit) * LOT_SIZE
        mfe = max(mfe, pnl)
        mae = min(mae, pnl)
        reason = None
        if j == expiry:
            reason = "EXPIRY"
        elif cur_credit >= CONDOR_STOP_MULT * entry_credit:
            reason = "STOP"
        elif cur_credit <= (1 - CONDOR_TARGET_PCT) * entry_credit:
            reason = "TARGET"
        elif (jj - t).days >= dte - CONDOR_CLOSE_BEFORE_DAYS:
            reason = "TIME"
        if reason:
            fill_out = round(legs_t["Kc"] * (1 + SLIPPAGE_PCT) + legs_t["Kp"] * (1 + SLIPPAGE_PCT)
                             - legs_t["KcW"] * (1 - SLIPPAGE_PCT) - legs_t["KpW"] * (1 - SLIPPAGE_PCT), 2)
            net = (fill_in - fill_out) * LOT_SIZE - 8 * COST_PER_TRADE
            slip = SLIPPAGE_PCT * (legs["Kc"] + legs["Kp"] + legs["KcW"] + legs["KpW"]
                                   + legs_t["Kc"] + legs_t["Kp"] + legs_t["KcW"] + legs_t["KpW"]) * LOT_SIZE
            return {"exit_date": str(j), "reason": reason, "exit_credit": round(cur_credit, 2),
                    "fill_out": round(fill_out, 2), "net_pnl": round(net, 2),
                    "slippage": round(slip, 2),
                    "mfe": round(mfe, 2), "mae": round(mae, 2), "entry_credit": entry_credit,
                    "max_loss": round(max_loss, 2), "days_held": (j - t).days, "log": log}
        log.append({"date": str(jj), "spot": spot_j, "credit": cur_credit})
    # eod force close at last evaluated day
    if j == t:
        return None
    legs_t = condor_legs(snaps, j, expiry, Kc, Kp, KcW, KpW, spot)
    if legs_t is None:
        return None
    cur_credit = round((legs_t["Kc"] + legs_t["Kp"]) - (legs_t["KcW"] + legs_t["KpW"]), 2)
    fill_out = round(legs_t["Kc"] * (1 + SLIPPAGE_PCT) + legs_t["Kp"] * (1 + SLIPPAGE_PCT)
                     - legs_t["KcW"] * (1 - SLIPPAGE_PCT) - legs_t["KpW"] * (1 - SLIPPAGE_PCT), 2)
    net = (fill_in - fill_out) * LOT_SIZE - 8 * COST_PER_TRADE
    slip = SLIPPAGE_PCT * (legs["Kc"] + legs["Kp"] + legs["KcW"] + legs["KpW"]
                           + legs_t["Kc"] + legs_t["Kp"] + legs_t["KcW"] + legs_t["KpW"]) * LOT_SIZE
    return {"exit_date": str(j), "reason": "EOD", "exit_credit": round(cur_credit, 2),
            "fill_out": round(fill_out, 2), "net_pnl": round(net, 2),
            "slippage": round(slip, 2),
            "mfe": round(mfe, 2), "mae": round(mae, 2), "entry_credit": entry_credit,
            "max_loss": round(max_loss, 2), "days_held": (j - t).days, "log": log}


def run_candidate_c(recs, nifty, snaps, nifty_dates):
    trades = []
    pos = None          # planned open position {entry, expiry, strikes, rec, sim}
    for d in nifty_dates:
        if pos is not None:
            if pos["sim"] is not None and str(d) == pos["sim"]["exit_date"]:
                sim = pos["sim"]
                rec = dict(pos["rec"])
                rec["simulation"] = sim
                rec["mfe"] = sim.get("mfe")
                rec["mae"] = sim.get("mae")
                rec["option_type"] = "IRON_CONDOR"
                rec["strike"] = (f"{pos['strikes'][2]:.0f}/{pos['strikes'][0]:.0f}-"
                                 f"{pos['strikes'][1]:.0f}/{pos['strikes'][3]:.0f}")
                trades.append(rec)
                pos = None
            continue
        rec = recs.get(str(d))
        if not rec or rec.get("skip"):
            continue
        if rec["regime"] != "RANGE_HV":
            continue
        vix = rec.get("vix")
        if vix is None or not (SPREAD_VIX_MIN <= vix < SPREAD_VIX_MAX):
            continue
        expiry = exp_cal.get_expiry_for_trade_date(d)
        if expiry is None:
            continue
        strikes = build_condor(rec["spot"], expiry, snaps, d)
        if strikes is None:
            continue
        legs = condor_legs(snaps, d, expiry, *strikes, rec["spot"])
        if legs is None:
            continue
        credit = (legs["Kc"] + legs["Kp"]) - (legs["KcW"] + legs["KpW"])
        if credit <= 0:
            continue
        sim = simulate_condor(d, rec["spot"], expiry, strikes, nifty, snaps, nifty_dates)
        if sim is None or not sim.get("exit_date"):
            continue
        pos = {"sim": sim, "expiry": expiry, "strikes": strikes, "rec": rec}
    return trades


def run_candidate_d(recs, nifty, snaps, nifty_dates):
    return []


def _finalize(rec, sim, mfe, mae):
    out = dict(rec)
    out["simulation"] = sim
    out["mfe"] = mfe
    out["mae"] = mae
    return out


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
PER_CANDIDATE_ORDERS = {"A_CURRENT_CONTROL": 2, "B_DIRECTIONAL_SPREAD": 4,
                        "C_RANGE_HV_IRON_CONDOR": 8, "D_NO_TRADE": 0}


def trade_rows(cand, trades):
    orders = PER_CANDIDATE_ORDERS.get(cand, 0)
    rows = []
    for t in trades:
        s = t.get("simulation")
        if not s or not s.get("exit_date"):
            continue
        rows.append({
            "entry_date": t["date"], "exit_date": s["exit_date"],
            "regime": t.get("regime"), "grade": t.get("grade"),
            "option_type": t.get("option_type"), "strike": t.get("strike"),
            "short_strike": t.get("short_strike"), "spread_width": t.get("spread_width"),
            "entry_premium": t.get("entry_premium") or s.get("entry_net") or s.get("entry_credit"),
            "reason": s.get("reason"), "net_pnl": float(s["net_pnl"]),
            "fees": orders * COST_PER_TRADE,
            "slippage": float(s.get("slippage") or 0.0),
            "mfe": float(t.get("mfe") or s.get("mfe") or 0.0),
            "mae": float(t.get("mae") or s.get("mae") or 0.0),
            "days_held": int(s.get("days_held") or 0),
        })
    return rows


def equity_curve(nets):
    e = 0.0
    out = []
    for n in nets:
        e += n
        out.append(e)
    return out


def max_drawdown(equity):
    peak = -1e18
    mdd = 0.0
    for e in equity:
        peak = max(peak, e)
        mdd = min(mdd, e - peak)
    return mdd


def compute_metrics(cand, rows, window_days, capital=CAPITAL):
    nets = [r["net_pnl"] for r in rows]
    n = len(nets)
    m = {"candidate": cand, "trade_count": n}
    if n == 0:
        for k in ("win_count", "loss_count", "breakeven_count", "win_rate", "gross_pnl",
                  "fees", "slippage", "net_pnl", "profit_factor", "expectancy", "average_trade",
                  "median_trade", "max_drawdown", "average_win", "average_loss", "mfe", "mae",
                  "average_hold", "trade_frequency", "sharpe", "sortino", "calmar",
                  "max_drawdown_pct"):
            m[k] = None if k in ("sharpe", "sortino", "calmar") else 0.0
        m["trades_per_month"] = 0.0
        m["trades_per_year"] = 0.0
        m["avg_days_between_trades"] = None
        m["status"] = "INSUFFICIENT_DATA"
        return m
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    gross_win = sum(wins)
    gross_loss_neg = sum(x for x in nets if x < 0)
    eq = equity_curve(nets)
    mdd = max_drawdown(eq)
    mdd_pct = mdd / capital * 100
    holds = [r["days_held"] for r in rows]
    mfe = np.mean([r["mfe"] for r in rows])
    mae = np.mean([r["mae"] for r in rows])
    orders = PER_CANDIDATE_ORDERS.get(cand, 0)
    fees = orders * COST_PER_TRADE * n
    slippage = sum(r["slippage"] for r in rows)

    trades_per_year = n
    trades_per_month = n / 12.0
    avg_gap = (window_days / max(n - 1, 1)) if n > 1 else None

    # daily P&L series over the window for risk-adjusted metrics
    pnl_by_date = {}
    for r in rows:
        pnl_by_date.setdefault(r["exit_date"], 0.0)
        pnl_by_date[r["exit_date"]] += r["net_pnl"]
    dret = np.array([v / capital for v in pnl_by_date.values()])
    sharpe = sortino = calmar = None
    if len(dret) >= 20:
        mean_r = dret.mean()
        std_r = dret.std(ddof=1)
        if std_r > 0:
            sharpe = round(mean_r / std_r * np.sqrt(252), 3)
            down = dret[dret < 0]
            dstd = down.std(ddof=1) if len(down) > 1 else 0.0
            sortino = round(mean_r / dstd * np.sqrt(252), 3) if dstd > 0 else None
            ann_ret_pct = sum(nets) / capital * 100
            calmar = round(ann_ret_pct / abs(mdd_pct), 3) if mdd_pct != 0 else None
    m.update({
        "win_count": len(wins), "loss_count": len(losses),
        "breakeven_count": n - len(wins) - len(losses),
        "win_rate": round(len(wins) / n * 100, 1),
        "gross_pnl": round(sum(nets) + fees + slippage, 2),
        "fees": round(fees, 2),
        "slippage": round(slippage, 2),
        "net_pnl": round(sum(nets), 2),
        "profit_factor": round(gross_win / abs(gross_loss_neg), 3) if gross_loss_neg else (None if gross_win == 0 else float("inf")),
        "expectancy": round(np.mean(nets), 2),
        "average_trade": round(np.mean(nets), 2),
        "median_trade": round(float(np.median(nets)), 2),
        "max_drawdown": round(mdd, 2),
        "max_drawdown_pct": round(mdd_pct, 2),
        "average_win": round(np.mean(wins), 2) if wins else None,
        "average_loss": round(np.mean(losses), 2) if losses else None,
        "mfe": round(float(mfe), 2), "mae": round(float(mae), 2),
        "average_hold": round(float(np.mean(holds)), 2),
        "trade_frequency": {"trades_per_month": round(trades_per_month, 2),
                            "trades_per_year": round(trades_per_year, 2),
                            "avg_days_between_trades": round(avg_gap, 1) if avg_gap else None},
        "sharpe": sharpe, "sortino": sortino, "calmar": calmar,
        "status": "INSUFFICIENT_SAMPLE" if n < 20 else "MEASURED",
    })
    return m


def group_by(rows, key):
    out = {}
    for r in rows:
        out.setdefault(r.get(key), []).append(r["net_pnl"])
    return {str(k): {"trades": len(v), "winrate": round(sum(1 for x in v if x > 0) / len(v) * 100, 1),
                     "net": round(sum(v), 2)} for k, v in sorted(out.items(), key=lambda kv: str(kv[0]))}


def concentration(rows):
    nets = [r["net_pnl"] for r in rows]
    total = sum(nets)
    if total == 0:
        return {"best_month_pct": None, "best_trade_pct": None, "top5_trades_pct": None}
    months = {}
    for r in rows:
        months.setdefault(r["exit_date"][:7], 0.0)
        months[r["exit_date"][:7]] += r["net_pnl"]
    best_month = max(months.values())
    top5 = sorted(nets, reverse=True)[:5]
    return {
        "best_month": max(months, key=months.get),
        "best_month_pct": round(best_month / total * 100, 1),
        "best_trade_pct": round(max(nets) / total * 100, 1),
        "top5_trades_pct": round(sum(top5) / total * 100, 1),
    }


def monthly_rows(rows):
    months = {}
    for r in rows:
        months.setdefault(r["exit_date"][:7], []).append(r["net_pnl"])
    return {k: {"trades": len(v), "winrate": round(sum(1 for x in v if x > 0) / len(v) * 100, 1),
                "net": round(sum(v), 2)} for k, v in sorted(months.items())}


def oos_split(rows):
    dev = [r for r in rows if r["exit_date"] < "2026-03-01"]
    oos = [r for r in rows if r["exit_date"] >= "2026-03-01"]
    def agg(v):
        if not v:
            return {"trades": 0, "net": 0.0}
        w = sum(1 for r in v if r["net_pnl"] > 0)
        return {"trades": len(v), "winrate": round(w / len(v) * 100, 1), "net": round(sum(r["net_pnl"] for r in v), 2)}
    return {"development_until_2026_02_28": agg(dev), "out_of_sample_from_2026_03_01": agg(oos)}


def fingerprints(nifty, vix, fii, ml, snaps, data_root=None):
    root = data_root or ROOT
    f = {}
    for name, p in (("nifty_history", "data/nifty_history.csv"),
                    ("india_vix", "data/india_vix.csv"),
                    ("fii_dii_history", "data/fii_dii_history.csv"),
                    ("ml_features", "data/ml_features.csv"),
                    ("expiry_calendar", "data/historical/expiry_calendar.csv")):
        f[name] = {"sha256": sha256_file(os.path.join(root, p)), "size": os.path.getsize(os.path.join(root, p))}
    f["oi_snapshots_dir"] = {"sha256": dir_sha256(os.path.join(root, "data", "oi_snapshots")),
                             "files": len([x for x in os.listdir(os.path.join(root, "data", "oi_snapshots"))])}
    f["dataset_composite_hash"] = sha256_bytes("|".join(f[k]["sha256"] for k in
        ("nifty_history", "india_vix", "fii_dii_history", "ml_features", "expiry_calendar")).encode())
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("/tmp", "opencode", "phaseH"))
    ap.add_argument("--data-root", default=ROOT,
                    help="root containing data/... for a frozen dataset snapshot")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    nifty, vix, fii, ml, snaps = load_inputs(data_root=args.data_root)
    nifty_dates = nifty_dates_of(nifty)
    window = [d for d in nifty_dates if WINDOW_START <= d <= WINDOW_END]

    recs = day_records(window, nifty, vix, fii, ml, snaps, nifty_dates)

    spec_hash = sha256_bytes(json.dumps(CANDIDATE_SPECS, sort_keys=True).encode())
    fp = fingerprints(nifty, vix, fii, ml, snaps, data_root=args.data_root)

    run = {}
    for cand, fn in (("A_CURRENT_CONTROL", run_candidate_a),
                     ("B_DIRECTIONAL_SPREAD", run_candidate_b),
                     ("C_RANGE_HV_IRON_CONDOR", run_candidate_c),
                     ("D_NO_TRADE", run_candidate_d)):
        trades = fn(recs, nifty, snaps, nifty_dates)
        rows = trade_rows(cand, trades)
        metrics = compute_metrics(cand, rows, len(window))
        run[cand] = {
            "trades": rows,
            "metrics": metrics,
            "by_regime": group_by(rows, "regime"),
            "by_grade": group_by(rows, "grade"),
            "monthly": monthly_rows(rows),
            "oos": oos_split(rows),
            "concentration": concentration(rows),
        }
    trades_a = [t for t in run["A_CURRENT_CONTROL"]["trades"]]
    control_check = {"trades": len(trades_a),
                     "win_rate": run["A_CURRENT_CONTROL"]["metrics"]["win_rate"],
                     "net_pnl": run["A_CURRENT_CONTROL"]["metrics"]["net_pnl"],
                     "pf": run["A_CURRENT_CONTROL"]["metrics"]["profit_factor"]}

    payload = {
        "window": {"start": str(WINDOW_START), "end": str(WINDOW_END), "trading_days": len(window)},
        "fingerprints": fp,
        "spec_hash": spec_hash,
        "control_repro_check": control_check,
        "candidates": run,
    }
    canonical = json.dumps(payload, sort_keys=True, default=str)
    result_hash = sha256_bytes(canonical.encode())
    out = {"run_timestamp": dt.datetime.now().isoformat(), "result_hash": result_hash, **payload}
    with open(os.path.join(args.out, "phaseH_multi_strategy.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    with open(os.path.join(ROOT, "results", "phaseH_multi_strategy.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)

    print("PHASE H run - control repro check:", control_check)
    for cand in ("A_CURRENT_CONTROL", "B_DIRECTIONAL_SPREAD", "C_RANGE_HV_IRON_CONDOR", "D_NO_TRADE"):
        m = run[cand]["metrics"]
        print(f"  {cand}: n={m['trade_count']} winrate={m['win_rate']} net={m['net_pnl']} "
              f"pf={m['profit_factor']} mdd={m['max_drawdown']}")
    print("result_hash:", result_hash)


if __name__ == "__main__":
    main()
