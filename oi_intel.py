"""OI intelligence - strike-level Open Interest analysis + Nitin Murarkar logic.

What this gives:
1. Strike build-up: where is OI being added TODAY (fresh positions), per strike.
2. OI spike detection: strikes where OI jumped abnormally vs their own history.
3. OI walls: highest CE OI (resistance) / highest PE OI (support) - S/R from options.
4. PCR + max pain + ATM context.
5. Murarkar-style reasoning: OI up + PCR up = bullish, price+OI 4-pattern matrix,
   institutional interpretation (hedging vs margin-play vs fresh longs).
"""
import os
import json
import datetime as dt

import numpy as np
import pandas as pd

SNAP_DIR = os.path.join("data", "oi_snapshots")


def _spike_zscore(series, recent=15):
    """How unusual the latest value is vs its own recent history (in std)."""
    series = pd.Series(series, dtype="float")
    hist = series.iloc[-recent:-1] if len(series) > recent else series.iloc[:-1]
    if len(hist) < 5:
        return 0.0
    m, s = hist.mean(), hist.std()
    if not s or np.isnan(s) or s == 0:
        return 0.0
    return float((series.iloc[-1] - m) / s)


def detect_build_up(chain, top_n=6, chg_min_pct=8):
    """Strikes with strong OI change today (fresh build-up), CE and PE sides.

    chain: option-chain df (strike, ce_oi, ce_oi_chg, pe_oi, pe_oi_chg, ...)
    Returns dict with top build-up strikes, direction interpretation.
    """
    df = chain.copy()
    df = df[df["ce_oi_chg"].notna() | df["pe_oi_chg"].notna()]

    ce = df.sort_values("ce_oi_chg", ascending=False).head(top_n)
    pe = df.sort_values("pe_oi_chg", ascending=False).head(top_n)

    return {
        "ce_build_up": [
            {
                "strike": int(r["strike"]),
                "oi_chg": int(r["ce_oi_chg"]) if not pd.isna(r["ce_oi_chg"]) else 0,
                "oi": int(r["ce_oi"]) if not pd.isna(r["ce_oi"]) else 0,
                "chg_pct": round(r["ce_pct_chg"], 1) if not pd.isna(r["ce_pct_chg"]) else None,
                "iv": round(r["ce_iv"], 1) if not pd.isna(r["ce_iv"]) else None,
                "ltp": round(r["ce_ltp"], 1) if not pd.isna(r["ce_ltp"]) else None,
            }
            for _, r in ce.iterrows()
        ],
        "pe_build_up": [
            {
                "strike": int(r["strike"]),
                "oi_chg": int(r["pe_oi_chg"]) if not pd.isna(r["pe_oi_chg"]) else 0,
                "oi": int(r["pe_oi"]) if not pd.isna(r["pe_oi"]) else 0,
                "chg_pct": round(r["pe_pct_chg"], 1) if not pd.isna(r["pe_pct_chg"]) else None,
                "iv": round(r["pe_iv"], 1) if not pd.isna(r["pe_iv"]) else None,
                "ltp": round(r["pe_ltp"], 1) if not pd.isna(r["pe_ltp"]) else None,
            }
            for _, r in pe.iterrows()
        ],
    }


def detect_oi_spike(chain, symbol="NIFTY", z_thresh=2.0):
    """Strikes where OI spiked vs their own recent history (multi-day OI snapshots).

    Uses saved snapshots in data/oi_snapshots/<symbol>_<date>.csv.
    Falls back to intraday signal (chg_pct >> normal) when no history exists.
    """
    spikes = {"ce": [], "pe": []}
    hist = load_history(symbol)
    if hist is None:
        return spikes

    for side, col in [("ce", "ce_oi"), ("pe", "pe_oi")]:
        for strike, ser in hist.items():
            s = ser[col]
            if len(s) < 6:
                continue
            z = _spike_zscore(s)
            if z >= z_thresh and s.iloc[-1] > 0:
                spikes[side].append({
                    "strike": int(strike),
                    "zscore": round(z, 2),
                    "oi": int(s.iloc[-1]),
                    "oi_prev": int(s.iloc[-2]),
                    "oi_chg": int(s.iloc[-1] - s.iloc[-2]),
                    "chg_pct": round((s.iloc[-1] / max(s.iloc[-2], 1) - 1) * 100, 1),
                })
    for side in spikes:
        spikes[side].sort(key=lambda r: r["zscore"], reverse=True)
        spikes[side] = spikes[side][:8]
    return spikes


def save_snapshot(chain, symbol="NIFTY"):
    """Persist today's chain so spike detection works over time."""
    os.makedirs(SNAP_DIR, exist_ok=True)
    today = dt.date.today().isoformat()
    path = os.path.join(SNAP_DIR, f"{symbol}_{today}.csv")
    chain.to_csv(path, index=False)
    return path


def load_history(symbol="NIFTY"):
    """Load saved OI snapshots into {strike: Series(ce_oi), Series(pe_oi)}.

    Only strikes present across multiple snapshots are included.
    """
    if not os.path.isdir(SNAP_DIR):
        return None
    files = sorted(f for f in os.listdir(SNAP_DIR)
                   if f.startswith(symbol + "_") and f.endswith(".csv"))
    if len(files) < 2:
        return None
    cols = ["strike", "ce_oi", "pe_oi"]
    frames = []
    for f in files[-30:]:
        try:
            df = pd.read_csv(os.path.join(SNAP_DIR, f), usecols=cols)
            date = f.split("_")[1].replace(".csv", "")
            df["date"] = date
            frames.append(df)
        except Exception:
            continue
    if len(frames) < 2:
        return None
    all_df = pd.concat(frames, ignore_index=True)
    # strikes present on every snapshot
    strike_counts = all_df.groupby("strike")["date"].nunique()
    stable = strike_counts[strike_counts >= 2].index
    all_df = all_df[all_df["strike"].isin(stable)]

    out = {}
    for st, grp in all_df.groupby("strike"):
        grp = grp.sort_values("date")
        out[int(st)] = {
            "ce_oi": pd.Series(grp["ce_oi"].astype(float).to_numpy()),
            "pe_oi": pd.Series(grp["pe_oi"].astype(float).to_numpy()),
        }
    return out


def oi_walls(chain, n=3, spot=None):
    """Highest OI strikes = the market's own support/resistance."""
    ce = chain.sort_values("ce_oi", ascending=False).head(n)
    pe = chain.sort_values("pe_oi", ascending=False).head(n)
    res = [int(s) for s in ce["strike"]]
    sup = [int(s) for s in pe["strike"]]
    out = {"resistance_oi": res, "support_oi": sup, "n": n}
    if spot is not None:
        out["spot"] = round(float(spot), 2)
        out["nearest_resistance"] = min((s for s in res if s > spot), default=None)
        out["nearest_support"] = max((s for s in sup if s < spot), default=None)
    return out


def pcr_and_pain(chain, spot=None):
    """PCR (all + ATM band), max pain, total CE/PE OI."""
    ce_tot = chain["ce_oi"].fillna(0).sum()
    pe_tot = chain["pe_oi"].fillna(0).sum()
    pcr = pe_tot / ce_tot if ce_tot else None

    ce_chg_tot = chain["ce_oi_chg"].fillna(0).sum()
    pe_chg_tot = chain["pe_oi_chg"].fillna(0).sum()
    pcr_chg = pe_chg_tot / ce_chg_tot if ce_chg_tot else None

    # Max pain computed on the liquid ATM band only (spot ±8%) - the wide
    # ±15% strike set lets far OTM OI drag the pain point to extremes.
    band = chain
    if spot is not None:
        band = chain[chain["strike"].between(spot * 0.92, spot * 1.08)]
    if band.empty:
        band = chain

    # Vectorized max pain (PERFORMANCE-AUDIT PF-M3): payout per candidate
    # strike K = sum over settlement S of max(0, K-S)*ce_oi[S] +
    # max(0, S-K)*pe_oi[S]. Equivalent to the previous O(n^2) nested loop but
    # computed as two matrix products over the band.
    strikes = band["strike"].to_numpy(dtype=float)
    if strikes.size == 0:
        best = None
    else:
        ce_oi = band["ce_oi"].fillna(0).to_numpy(dtype=float)
        pe_oi = band["pe_oi"].fillna(0).to_numpy(dtype=float)
        k = strikes[:, None]
        s = strikes[None, :]
        payout = np.maximum(k - s, 0.0) @ ce_oi + np.maximum(s - k, 0.0) @ pe_oi
        best = strikes[int(np.argmin(payout))]

    return {
        "pcr": round(pcr, 3) if pcr else None,
        "pcr_oi_chg": round(pcr_chg, 3) if pcr_chg else None,
        "ce_total_oi": int(ce_tot),
        "pe_total_oi": int(pe_tot),
        "max_pain": int(best) if best else None,
    }


def murarkar_matrix(chain, spot):
    """Price+OI 4-pattern matrix - what institutions are really doing.

    Uses CE/PE OI *change* plus price move to classify fresh build-ups:
    Price up + CE OI up   = fresh CALL buying (bullish / or call writers adding = cap)
    Price up + PE OI up   = put WRITING at support (bullish)
    Price down + PE OI up = fresh PUT buying (bearish)
    Price down + CE OI up = call WRITING at resistance (bearish cap)
    """
    ce_chg = chain["ce_oi_chg"].fillna(0).sum()
    pe_chg = chain["pe_oi_chg"].fillna(0).sum()
    df = chain[chain["strike"] <= spot]
    if df.empty:
        df = chain
    ce_atm_chg = df["ce_oi_chg"].fillna(0).sum()
    pe_atm_chg = df["pe_oi_chg"].fillna(0).sum()

    pcr = pcr_and_pain(chain, spot)
    pcr_dir = (pcr["pcr_oi_chg"] or 0) > 0

    return {
        "ce_oi_change": int(ce_chg),
        "pe_oi_change": int(pe_chg),
        "ce_oi_change_atm": int(ce_atm_chg),
        "pe_oi_change_atm": int(pe_atm_chg),
        "pcr_rising": bool(pcr_dir),
        "signal": "OI up + PCR up = BULLISH" if pcr_dir and pe_chg > 0 else
                  ("OI up + PCR down = CALL heavy, watch cap" if not pcr_dir and ce_chg > 0 else "neutral"),
    }


def save_history_json(chain, symbol="NIFTY", extra=None):
    """Save a compact JSON of today's OI per strike for daily diffing."""
    os.makedirs(SNAP_DIR, exist_ok=True)
    today = dt.date.today().isoformat()
    rec = {"date": today, "symbol": symbol}
    for _, r in chain.iterrows():
        rec[str(int(r["strike"]))] = {
            "ce_oi": r["ce_oi"], "pe_oi": r["pe_oi"],
            "ce_oi_chg": r["ce_oi_chg"], "pe_oi_chg": r["pe_oi_chg"],
        }
    if extra:
        rec["_meta"] = extra
    path = os.path.join(SNAP_DIR, f"oi_{symbol}_{today}.json")
    with open(path, "w") as f:
        json.dump(rec, f)
    return path
