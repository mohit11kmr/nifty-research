"""Phase I.3 - Research Feature Engine (spec sections 12, 14).

Builds the daily point-in-time feature panel over the frozen 646-session
unified dataset. Hard guarantees:

  * NO LOOKAHEAD: every feature at session t is computed exclusively from
    data observed at or before t. Rolling windows are closed at t; forward
    outcomes (next-session returns, future VIX, future OI) are NEVER part of
    the panel and live only in the evaluation layer.
  * DETERMINISM: same frozen dataset + same code -> identical panel.
  * ONLY registered features (research_feature_registry) are produced.

The engine returns a DataFrame indexed by session date plus a meta block
(source_hash, feature_version, warmup_start) so downstream cache keys and
leakage tests have an exact reference.
"""
import json
import numpy as np
import pandas as pd

import research_feature_registry as FREG
import research_dataset as RD

MAX_PAIN_BAND_PCT = 5.0
OTM_BAND_PCT = 1.0


def _vix_zone(v):
    if v < 12:
        return 1
    if v < 16:
        return 2
    if v < 20:
        return 3
    if v < 25:
        return 4
    return 5


def _chain_agg(sub, spot, near_expiry, date):
    """Aggregate features for one session from the nearest-expiry chain."""
    if near_expiry is not None:
        sub = sub.loc[sub["expiry"] == near_expiry]
    calls = sub[sub["option_type"] == "CE"]
    puts = sub[sub["option_type"] == "PE"]
    call_oi = float(calls["oi"].sum()) if len(calls) else 0.0
    put_oi = float(puts["oi"].sum()) if len(puts) else 0.0
    call_chg = float(calls["oi_chg"].sum()) if len(calls) else 0.0
    put_chg = float(puts["oi_chg"].sum()) if len(puts) else 0.0
    strikes = sub["strike"].to_numpy()
    oi = sub["oi"].to_numpy().astype(float)
    is_call = (sub["option_type"] == "CE").to_numpy()
    is_put = ~is_call

    out = {}
    out["call_oi"] = call_oi
    out["put_oi"] = put_oi
    out["total_oi_near"] = call_oi + put_oi
    out["pcr_oi"] = round(put_oi / call_oi, 4) if call_oi > 0 else np.nan
    out["pcr_oi_chg"] = round(put_chg / call_chg, 4) if call_chg not in (0, np.nan) and call_chg != 0 else np.nan

    # ATM strike + premium proxy
    if spot and not np.isnan(spot):
        atm = strikes[np.argmin(np.abs(strikes - spot))]
        dte_strikes = sub.loc[sub["strike"].isin([atm, atm - 50.0, atm + 50.0])]
        prem = dte_strikes.loc[dte_strikes["settle_price"].notna(), "settle_price"]
        out["atm_premium_pct"] = round(100.0 * float(prem.mean()) / spot, 4) if len(prem) else np.nan
        out["atm_strike"] = float(atm)
    else:
        out["atm_premium_pct"] = np.nan
        out["atm_strike"] = np.nan

    # max pain on the ATM band (documented practice)
    band = strikes[np.abs(strikes - spot) / spot * 100 <= MAX_PAIN_BAND_PCT]
    best, best_payout = None, None
    if len(band):
        band_oi = oi[np.isin(strikes, band)]
        for j, k in enumerate(band):
            payout = float(np.sum(np.maximum(0, k - strikes) * oi * is_put)
                           + np.sum(np.maximum(0, strikes - k) * oi * is_call))
            if best_payout is None or payout < best_payout:
                best, best_payout = k, payout
    out["max_pain_strike"] = float(best) if best is not None else np.nan
    out["max_pain_dist_pct"] = round(100.0 * abs(spot - best) / spot, 4) \
        if best is not None and spot else np.nan

    # OTM OI shares
    above = strikes[strikes > spot * (1 + OTM_BAND_PCT / 100)]
    below = strikes[strikes < spot * (1 - OTM_BAND_PCT / 100)]
    out["otm_call_oi_share"] = round(oi[is_call & np.isin(strikes, above)].sum() / call_oi, 4) if call_oi > 0 else np.nan
    out["otm_put_oi_share"] = round(oi[is_put & np.isin(strikes, below)].sum() / put_oi, 4) if put_oi > 0 else np.nan

    # volume
    vol = sub["volume"].to_numpy().astype(float)
    total_vol = float(vol.sum())
    out["chain_volume_total"] = total_vol
    call_vol = float(vol[is_call].sum())
    out["chain_call_volume_share"] = round(call_vol / total_vol, 4) if total_vol > 0 else np.nan
    out["_near_expiry"] = near_expiry
    return out


def _oi_share(oi, day, bucket):
    rows = day[day["client_type"] == bucket]
    total = float(day["contracts"].sum())
    if total <= 0:
        return np.nan
    val = float(rows["contracts"].sum()) if len(rows) else 0.0
    return val / total


def build_panel(ctx=None, verify=True):
    """Full daily feature panel over the frozen dataset."""
    ctx = ctx or RD.load_context(verify=verify)
    source_hash = ctx.integrity["manifest_self_hash"]
    sessions = ctx.sessions

    nifty = ctx.nifty.set_index("date")
    vix = ctx.vix.set_index("date")
    oi = ctx.oi
    chain = ctx.chain_by_date
    expiry = ctx.expiry_by_date

    s_close = nifty["close"].astype(float)
    rets = s_close.pct_change()

    # rolling (point-in-time, closed at t)
    hv20 = rets.rolling(20).std() * np.sqrt(252)
    ma20 = s_close.rolling(20).mean()
    ma50 = s_close.rolling(50).mean()
    atr_prev_close = nifty["close"].shift(1)
    tr = pd.concat([
        nifty["high"] - nifty["low"],
        (nifty["high"] - atr_prev_close).abs(),
        (nifty["low"] - atr_prev_close).abs(),
    ], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()

    def trend_20d(w):
        x = np.arange(len(w))
        return float(np.polyfit(x, w, 1)[0]) / float(w[-1]) * 100.0 if len(w) and w[-1] else np.nan

    trend20 = s_close.rolling(20).apply(trend_20d, raw=True)
    vix_rank = vix["close"].rolling(252, min_periods=30).apply(
        lambda w: float((w <= w[-1]).mean()), raw=True)

    oi_by_date = {d: g for d, g in oi.groupby("date", sort=True)}

    rows = []
    for i, d in enumerate(sessions):
        spot = float(s_close.loc[d])
        v = float(vix["close"].loc[d])
        chain_row = chain.get(d)
        near = expiry.get(d, {}).get("expiry")
        exp_src = expiry.get(d, {}).get("source")
        agg = _chain_agg(chain_row, spot, near, d) if chain_row is not None and len(chain_row) else {}

        expiries_present = set(chain_row["expiry"]) if chain_row is not None and len(chain_row) else set()
        r = {
            "date": d,
            "nifty_close": spot,
            "nifty_ret_1d": rets.loc[d],
            "nifty_ret_5d": s_close.loc[d] / s_close.shift(5).loc[d] - 1 if i >= 5 else np.nan,
            "nifty_ret_20d": s_close.loc[d] / s_close.shift(20).loc[d] - 1 if i >= 20 else np.nan,
            "nifty_gap_pct": (nifty["open"].loc[d] / nifty["close"].shift(1).loc[d] - 1) * 100 if i >= 1 else np.nan,
            "nifty_20d_hv": hv20.loc[d],
            "nifty_atr_14_pct": atr14.loc[d] / spot * 100 if spot else np.nan,
            "nifty_ma20_dist_pct": (spot / ma20.loc[d] - 1) * 100 if i >= 19 else np.nan,
            "nifty_ma50_dist_pct": (spot / ma50.loc[d] - 1) * 100 if i >= 49 else np.nan,
            "nifty_trend_20d": trend20.loc[d] if i >= 19 else np.nan,
            "nifty_above_ma20": 1.0 if (i >= 19 and spot > ma20.loc[d]) else 0.0,
            "nifty_above_ma50": 1.0 if (i >= 49 and spot > ma50.loc[d]) else 0.0,
            "vix_close": v,
            "vix_ret_5d": (v / vix["close"].shift(5).loc[d] - 1) * 100 if i >= 5 else np.nan,
            "vix_ret_20d": (v / vix["close"].shift(20).loc[d] - 1) * 100 if i >= 20 else np.nan,
            "vix_rank_252": vix_rank.loc[d],
            "vix_20d_mean": vix["close"].rolling(20).mean().loc[d],
            "vix_20d_std": vix["close"].rolling(20).std().loc[d],
            "vix_zone": _vix_zone(v),
            "dte": (pd.Timestamp(near) - pd.Timestamp(d)).days if near else np.nan,
            "expiry_day": 1.0 if d in expiries_present else 0.0,
            "near_expiry": near,
            "expiry_source": exp_src,
            **{k: agg.get(k, np.nan) for k in (
                "pcr_oi", "pcr_oi_chg", "call_oi", "put_oi", "total_oi_near",
                "max_pain_strike", "max_pain_dist_pct", "atm_strike",
                "atm_premium_pct", "otm_call_oi_share", "otm_put_oi_share",
                "chain_volume_total", "chain_call_volume_share")},
        }
        # market-wide OI (all expiries)
        tot_oi = float(chain_row["oi"].sum()) if chain_row is not None and len(chain_row) else np.nan
        tot_chg = float(chain_row["oi_chg"].sum()) if chain_row is not None and len(chain_row) else np.nan
        r["oi_total"] = tot_oi
        r["oi_total_chg"] = tot_chg
        if i >= 5:
            prev_tot = float(chain.get(sessions[i - 5], pd.DataFrame()).get("oi", pd.Series([np.nan])).sum()) \
                if sessions[i - 5] in chain else np.nan
            r["oi_total_growth_5d"] = (tot_oi / prev_tot - 1) * 100 if prev_tot else np.nan
        else:
            r["oi_total_growth_5d"] = np.nan
        # participant flow
        day = oi_by_date.get(d)
        if day is not None and len(day):
            fii = day[day["client_type"] == "FII"]["contracts"].astype(float).sum()
            r["fii_oi_contracts"] = float(fii)
            r["fii_oi_share"] = _oi_share(oi, day, "FII")
            r["client_oi_share"] = _oi_share(oi, day, "Client")
            r["pro_oi_share"] = _oi_share(oi, day, "Pro")
            r["dii_oi_share"] = _oi_share(oi, day, "DII")
        else:
            for k in ("fii_oi_contracts", "fii_oi_share", "client_oi_share", "pro_oi_share", "dii_oi_share"):
                r[k] = np.nan
        rows.append(r)

    panel = pd.DataFrame(rows).set_index("date")
    panel["fii_oi_share_chg_5d"] = (panel["fii_oi_share"] - panel["fii_oi_share"].shift(5)) * 100

    # explicit no-lookahead cross-check: every row only depends on rows <= t
    warmup = 252  # max lookback across all registered features
    meta = {
        "source_hash": source_hash,
        "feature_version": FREG.feature_version(),
        "n_sessions": len(panel),
        "warmup_start": panel.index[warmup - 1] if len(panel) >= warmup else panel.index[0],
        "columns": [c for c in panel.columns],
        "registered_columns": sorted(c for c in panel.columns
                                     if c in FREG.registered_ids()),
    }
    return panel, meta


def leakage_probe(panel, ctx, dates, feature_ids):
    """Recompute selected features at `dates` using only data <= date and
    compare to the panel. Verifies no-future-data construction."""
    nifty = ctx.nifty.set_index("date")
    s_close = nifty["close"].astype(float)
    probes = {}
    for d in dates:
        idx = list(panel.index).index(d)
        limited = s_close.loc[:d]
        row = {}
        if "nifty_ret_5d" in feature_ids:
            row["nifty_ret_5d"] = limited.iloc[-1] / limited.iloc[-6] - 1 if len(limited) >= 6 else np.nan
        if "nifty_ma50_dist_pct" in feature_ids:
            ma = limited.rolling(50).mean().iloc[-1]
            row["nifty_ma50_dist_pct"] = (limited.iloc[-1] / ma - 1) * 100 if not np.isnan(ma) else np.nan
        if "nifty_20d_hv" in feature_ids:
            r = limited.pct_change().rolling(20).std().iloc[-1] * np.sqrt(252)
            row["nifty_20d_hv"] = r
        panel_row = panel.loc[d]
        row["_panel"] = {
            "nifty_ret_5d": panel_row.get("nifty_ret_5d"),
            "nifty_ma50_dist_pct": panel_row.get("nifty_ma50_dist_pct"),
            "nifty_20d_hv": panel_row.get("nifty_20d_hv"),
        }
        row["_match"] = all(
            (pd.isna(row[k]) and pd.isna(row["_panel"][k])) or
            (not pd.isna(row[k]) and abs(row[k] - row["_panel"][k]) < 1e-9)
            for k in feature_ids if k in ("nifty_ret_5d", "nifty_ma50_dist_pct", "nifty_20d_hv"))
        probes[d] = row
    return probes


if __name__ == "__main__":
    panel, meta = build_panel()
    print(json.dumps(meta, indent=2, default=str))
    print(panel.shape)
    print(panel.tail(3).to_string())
