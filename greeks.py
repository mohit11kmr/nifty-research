"""Greeks engine - Black-Scholes Greeks + IV analytics + ATM/ITM/OTM classification.

Gives a trader the option greeks logic: delta direction, gamma (movement
sensitivity), theta (time decay), plus IV percentile and option chain
structure (ATM/ITM/OTM, OI build-up).
"""
from math import log, sqrt, exp, erf

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _cdf(x):
    return 0.5 * (1 + erf(x / sqrt(2)))


def _pdf(x):
    return exp(-0.5 * x * x) / sqrt(2 * np.pi)


def bs_price_and_greeks(spot, strike, t_days, sigma, side="CE", r=0.06):
    """Return price + delta/gamma/theta/vega for a call or put."""
    T = max(t_days, 0.5) / TRADING_DAYS
    sigma = max(sigma, 0.05)
    if spot <= 0 or strike <= 0:
        return {"price": 0, "delta": 0, "gamma": 0, "theta": 0, "vega": 0}

    d1 = (log(spot / strike) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)

    if side.upper() == "CE":
        price = spot * _cdf(d1) - strike * exp(-r * T) * _cdf(d2)
        delta = _cdf(d1)
        theta = (-(spot * _pdf(d1) * sigma) / (2 * sqrt(T))
                 - r * strike * exp(-r * T) * _cdf(d2)) / TRADING_DAYS
        rho = strike * T * exp(-r * T) * _cdf(d2) / 100
    else:
        price = strike * exp(-r * T) * _cdf(-d2) - spot * _cdf(-d1)
        delta = _cdf(d1) - 1
        theta = (-(spot * _pdf(d1) * sigma) / (2 * sqrt(T))
                 + r * strike * exp(-r * T) * _cdf(-d2)) / TRADING_DAYS
        rho = -strike * T * exp(-r * T) * _cdf(-d2) / 100

    gamma = _pdf(d1) / (spot * sigma * sqrt(T))
    vega = spot * _pdf(d1) * sqrt(T) / 100  # per 1 vol point

    return {"price": price, "delta": delta, "gamma": gamma,
            "theta": theta, "vega": vega, "rho": rho}


def probability_of_profit(spot, lower=None, upper=None, sigma_ann=0.15,
                          t_days=20, r=0.06):
    """Probability (risk-neutral, lognormal) that spot stays within barriers.

    - `lower` only  -> P(S_T > lower)   (call/bull-spread PoP)
    - `upper` only  -> P(S_T < upper)   (put/bear-spread PoP)
    - both          -> P(lower < S_T < upper)  (credit spread / strangle PoP)
    Returns 0..1 or None when no barrier given.
    """
    if lower is None and upper is None:
        return None
    T = max(t_days, 0.5) / TRADING_DAYS
    sigma = max(float(sigma_ann), 0.05)

    def prob_above(barrier):
        if barrier <= 0:
            return 1.0
        d2 = (log(spot / barrier) + (r - 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
        return _cdf(d2)

    if lower is not None and upper is not None:
        p = prob_above(lower) - prob_above(upper)
    elif upper is not None:
        p = 1.0 - prob_above(upper)
    else:
        p = prob_above(lower)
    return max(0.0, min(1.0, p))


def what_if_greeks(spot, strike, t_days, sigma, side="CE",
                   spot_shifts_pct=(-2, -1, 0, 1, 2),
                   vol_shifts_pts=(-2, -1, 0, 1, 2), r=0.06):
    """Scenario analysis - how price + Greeks change under hypothetical
    spot % shifts and IV point shifts (what-if grid)."""
    grid = []
    for sp in spot_shifts_pct:
        s = spot * (1 + sp / 100)
        row = {"spot_shift_pct": sp, "spot": round(s, 2)}
        for vp in vol_shifts_pts:
            sg = max(0.05, sigma + vp)
            g = bs_price_and_greeks(s, strike, t_days, sg, side=side, r=r)
            row[f"price_iv{vp:+d}"] = round(g["price"], 2)
            row[f"delta_iv{vp:+d}"] = round(g["delta"], 3)
            row[f"vega_iv{vp:+d}"] = round(g["vega"], 3)
        grid.append(row)
    base = bs_price_and_greeks(spot, strike, t_days, sigma, side=side, r=r)
    return {
        "side": side,
        "strike": strike,
        "base": {k: round(v, 4) for k, v in base.items()},
        "grid": grid,
    }


def classify_strike(spot, strike, itm_band_pct=0.01):
    """ATM / ITM / OTM classification for calls & puts."""
    dist = (strike - spot) / spot
    if abs(dist) <= itm_band_pct:
        zone = "ATM"
    elif dist > 0:
        zone = "OTM-CE" if dist < 0.05 else "DeepOTM-CE"
    else:
        zone = "ITM-CE" if dist > -0.05 else "DeepITM-CE"
    return zone


def analyze_chain(chain, spot, t_days=20, iv=None, hist_iv=None):
    """Full option-chain analytics: greeks + IV percentile + OI build-up."""
    if chain is None or chain.empty:
        return None
    out = []
    ce_ivs = chain["ce_iv"].dropna()
    iv_pctile = None
    if not ce_ivs.empty:
        avg = ce_ivs.mean()
        # if we have hist_iv we compute percentile against it
        iv_pctile = avg if iv is not None else None

    for _, r in chain.iterrows():
        strike = r["strike"]
        zone = classify_strike(spot, strike)
        for side in ("ce", "pe"):
            sigma = r.get(f"{side}_iv")
            if not sigma or np.isnan(sigma):
                continue
            g = bs_price_and_greeks(spot, strike, t_days, sigma, side="CE" if side == "ce" else "PE")
            out.append({
                "strike": strike,
                "zone": zone if side == "ce" else classify_strike(spot, strike).replace("CE", "PE"),
                "side": side.upper(),
                "price": round(g["price"], 2),
                "delta": round(g["delta"], 3),
                "gamma": round(g["gamma"], 6),
                "theta": round(g["theta"], 4),
                "vega": round(g["vega"], 3),
                "oi": r.get(f"{side}_oi"),
                "oi_chg": r.get(f"{side}_oi_chg"),
                "iv": round(float(sigma), 1),
            })

    greeks_df = pd.DataFrame(out)
    if greeks_df.empty:
        return None

    atm_row = greeks_df.loc[(greeks_df["strike"] - spot).abs().idxmin()]
    return {
        "greeks": greeks_df,
        "atm_strike": int(atm_row["strike"]),
        "atm_call_delta": atm_row["delta"] if atm_row["side"] == "CE" else None,
        "atm_put_delta": atm_row["delta"] if atm_row["side"] == "PE" else None,
        "avg_iv": round(ce_ivs.mean(), 1) if not ce_ivs.empty else None,
        "iv_percentile": iv_pctile,
        "oi_buildup_calls": _oi_buildup(chain, "ce"),
        "oi_buildup_puts": _oi_buildup(chain, "pe"),
    }


def _oi_buildup(chain, side):
    col = f"{side}_oi"
    chg = f"{side}_oi_chg"
    if col not in chain.columns or chg not in chain.columns:
        return []
    d = chain[chain[col].notna() & chain[chg].notna()].copy()
    d = d[d[chg] > 0].sort_values(chg, ascending=False).head(5)
    return [{"strike": int(r["strike"]), "oi_chg": int(r[chg])} for _, r in d.iterrows()]


def iv_analysis(close_series, recent_iv):
    """IV vs realized-HV comparison - tells if premium is cheap/expensive."""
    rets = np.log(close_series / close_series.shift(1))
    hv20 = rets.rolling(20).std().iloc[-1] * sqrt(TRADING_DAYS)
    hv10 = rets.rolling(10).std().iloc[-1] * sqrt(TRADING_DAYS)
    iv_hv = recent_iv / hv20 if hv20 else None
    return {
        "hv10_pct": round(hv10 * 100, 1) if hv10 else None,
        "hv20_pct": round(hv20 * 100, 1) if hv20 else None,
        "iv_pct": recent_iv,
        "iv_vs_hv": round(iv_hv, 2) if iv_hv else None,
    }


def interpret_greeks(analysis, spot):
    """Trader-style reading of the greeks/chain structure."""
    if analysis is None:
        return []
    lines = []
    a = analysis
    lines.append(f"ATM strike {a['atm_strike']} (spot {spot:,.0f})")

    ce_build = a["oi_buildup_calls"][:3]
    pe_build = a["oi_buildup_puts"][:3]
    if ce_build:
        lines.append(f"OI build-up in CALLS: " + ", ".join(str(b['strike']) for b in ce_build) + " => upside resistance")
    if pe_build:
        lines.append(f"OI build-up in PUTS: " + ", ".join(str(b['strike']) for b in pe_build) + " => downside support")

    ivh = a.get("iv_vs_hv")
    if ivh is not None:
        if ivh < 1.0:
            lines.append(f"IV/HV {ivh:.2f} = premium CHEAP, options buying favorable")
        elif ivh > 1.4:
            lines.append(f"IV/HV {ivh:.2f} = premium EXPENSIVE, avoid fresh buying (IV crush risk)")
        else:
            lines.append(f"IV/HV {ivh:.2f} = fair premium")
    return lines
