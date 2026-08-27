"""Phase I.3 - Behaviour Engine (spec section 18).

Describes what the data does, conditionally, without claiming a tradable edge.

Every behaviour has:
    observation      - the pattern definition (boolean condition on the panel)
    sample           - the qualifying sessions (dates)
    frequency        - n / total sessions
    conditional_behavior - forward 1d/5d mean+median return and hit rate
    baseline         - unconditional forward behaviour for the same window
    confidence       - NOT_RELIABLE (<20) / LOW (20-49) / MEDIUM (50-199) / HIGH (>=200)
    data_limitations - overlapping 5d windows, condition rarity, proxy inputs

Forward returns are EVALUATION ONLY: the behaviour engine never feeds future
data back into features. A behaviour is NOT an edge and is not auto-promoted.
"""
import json
import numpy as np
import pandas as pd

import research_cache as RC
import research_feature_registry as FREG

CONFIDENCE_BANDS = [(20, "NOT_RELIABLE"), (50, "LOW"), (200, "MEDIUM"), (np.inf, "HIGH")]


def confidence(n):
    for lo, label in CONFIDENCE_BANDS:
        if n < lo:
            return label
    return "HIGH"


def _stats(vals):
    vals = vals.dropna()
    if not len(vals):
        return None
    return {
        "mean": round(float(vals.mean()), 5),
        "median": round(float(vals.median()), 5),
        "hit_rate_up": round(float((vals > 0).mean()), 4),
        "n": int(len(vals)),
    }


def _behavior(panel, mask, name, description, limitations):
    fwd = _forward(panel)
    total = len(panel)
    dates = list(panel.index[mask.fillna(False).to_numpy()])
    n = len(dates)
    b = {
        "observation": description,
        "condition": name,
        "sample": dates,
        "frequency": round(n / total, 4) if total else None,
        "n_sessions": n,
        "conditional_behavior": {
            "fwd_1d": _stats(fwd["fwd_1d"].loc[mask.fillna(False)]),
            "fwd_5d": _stats(fwd["fwd_5d"].loc[mask.fillna(False)]),
        },
        "baseline": {
            "fwd_1d": _stats(fwd["fwd_1d"]),
            "fwd_5d": _stats(fwd["fwd_5d"]),
        },
        "confidence": confidence(n),
        "data_limitations": limitations,
        "status": "NOT_RELIABLE" if n < 20 else "MEASURED",
    }
    return b


def _forward(panel):
    c = panel["nifty_close"]
    return pd.DataFrame({
        "fwd_1d": c.shift(-1) / c - 1,
        "fwd_5d": c.shift(-5) / c - 1,
    })


def _q(series, q):
    return series.quantile(q)


def discover_behaviors(panel, meta):
    source_hash = meta["source_hash"]
    fv = meta["feature_version"]
    cached, state = RC.get("behavior_report", source_hash, feature_version=fv)
    if cached is not None:
        return cached, state

    ret5 = panel["nifty_ret_5d"]
    ret1 = panel["nifty_ret_1d"]
    gap = panel["nifty_gap_pct"]
    hv = panel["nifty_20d_hv"]
    vix = panel["vix_close"]
    pcr = panel["pcr_oi"]
    vix_zone = panel["vix_zone"]
    oi_growth = panel["oi_total_growth_5d"]
    mpd = panel["max_pain_dist_pct"]
    exp_day = panel["expiry_day"]
    atm = panel["atm_premium_pct"]
    fii_chg = panel["fii_oi_share_chg_5d"]
    dte = panel["dte"]

    conditions = [
        ("trend_follow_up_5d", ret5 > 0.02,
         "5-session return > +2% (recent strong trend)",
         ["overlapping 5d windows; trend can be regime-specific"]),
        ("trend_follow_down_5d", ret5 < -0.02,
         "5-session return < -2% (recent sharp decline)",
         ["overlapping 5d windows; falling regimes can persist"]),
        ("mean_reversion_up_5d", ret5 > 0.05,
         "5-session return > +5% (extended rally)",
         ["small n possible; overlap in 5d windows"]),
        ("mean_reversion_down_5d", ret5 < -0.05,
         "5-session return < -5% (extended sell-off)",
         ["small n possible; overlap in 5d windows"]),
        ("vix_panic", vix > 25,
         "VIX > 25 (panic premium zone)",
         ["rare condition; small n likely"]),
        ("vix_high", vix_zone >= 4,
         "VIX in HIGH/PANIC zone (>=20)",
         ["condition frequency moderate"]),
        ("vix_cheap", vix_zone <= 1,
         "VIX < 12 (cheap premium)",
         ["condition frequency moderate"]),
        ("hv_above_vix", hv > vix / 100,
         "20d realized HV (annualized) above VIX level",
         ["HV and VIX are different measures; comparison is descriptive"]),
        ("pcr_low_decile", pcr <= _q(pcr.dropna(), 0.10),
         "PCR (put/call OI) in bottom decile - call-heavy flow",
         ["PCR is point-in-time OI ratio; decile boundary uses full window"]),
        ("pcr_high_decile", pcr >= _q(pcr.dropna(), 0.90),
         "PCR in top decile - put-heavy flow",
         ["decile boundary uses full window"]),
        ("oi_growth_top_quintile", oi_growth >= _q(oi_growth.dropna(), 0.80),
         "total option OI grew >80th percentile over 5 sessions (build-up)",
         ["overlapping 5d OI windows"]),
        ("expiry_day_sessions", exp_day == 1,
         "option expiry session",
         ["expiry calendar semantics; weekly expiry concentration"]),
        ("max_pain_above_spot", mpd > 0.5,
         "spot >0.5% away from max-pain strike",
         ["max pain computed on ATM band; settlement-day drift not priced"]),
        ("gap_continuation_up", gap > 0.5,
         "opening gap > +0.5% (continuation/reversal probe)",
         ["gap direction alone ignores overnight context"]),
        ("gap_reversal_down", gap < -0.5,
         "opening gap < -0.5%",
         ["gap direction alone ignores overnight context"]),
        ("atm_expensive", atm >= _q(atm.dropna(), 0.80),
         "near-ATM option premium proxy in top quintile (vol expensive)",
         ["premium proxy from settle prices; not true implied vol"]),
        ("fii_share_rising_5d", fii_chg > 1.0,
         "FII participant-OI share rose >1pp over 5 sessions",
         ["participant OI is aggregate EQ derivatives (no options split)"]),
        ("high_dte_early_week", dte >= 6,
         "6+ days to weekly expiry (early cycle)",
         ["weekly expiry calendar structure"]),
        ("low_dte_late_week", dte <= 1,
         "1 or fewer days to weekly expiry (late cycle)",
         ["weekly expiry calendar structure"]),
    ]

    behaviors = []
    for name, mask, desc, lims in conditions:
        mask = mask.reindex(panel.index).astype(bool)
        behaviors.append(_behavior(panel, mask, name, desc, lims))

    report = {
        "n_behaviors": len(behaviors),
        "behaviors": behaviors,
        "feature_version": fv,
        "note": "descriptive only; forward returns are evaluation, not features",
    }
    RC.put("behavior_report", source_hash, report, feature_version=fv)
    return report, state


if __name__ == "__main__":
    import research_feature_engine as FE
    panel, meta = FE.build_panel()
    report, state = discover_behaviors(panel, meta)
    for b in report["behaviors"]:
        cb = b["conditional_behavior"]["fwd_5d"]
        bl = b["baseline"]["fwd_5d"]
        print(f"{b['condition']:>28} n={b['n_sessions']:4d} conf={b['confidence']:>10} "
              f"fwd5 mean={cb['mean'] if cb else None:>10} base={bl['mean'] if bl else None:>10}")
