"""Multi-Leg Option Spreads Engine for NIFTY Research.

Constructs defined-risk multi-leg option combinations priced from REAL
market data (latest OI snapshot CSV) with Black-Scholes fallback:
1. Bull Call Spread
2. Bear Put Spread
3. Iron Condor
4. Short Strangle (with hedged wings = defined risk)

All premiums come from live snapshot LTPs / BS pricing (no hardcoded
values). Includes Probability of Profit (PoP), breakevens, max risk /
reward and risk-reward ratio computed from the actual premiums.
"""
import glob
import os
import json
import datetime as dt

import numpy as np
import pandas as pd

from greeks import bs_price_and_greeks, probability_of_profit

LOT_SIZE = 75
WING = 200
DEFAULT_SIGMA = 0.15
R = 0.06
SNAP_DIR = os.path.join("data", "oi_snapshots")


def _default_spot():
    """Last real NIFTY close from cache; None if unavailable (no literal)."""
    try:
        hist = os.path.join("data", "nifty_history.csv")
        if os.path.exists(hist):
            df = pd.read_csv(hist)
            col = [c for c in ("Close", "close", "Adj Close") if c in df.columns]
            if col:
                return float(df[col[0]].dropna().iloc[-1])
    except Exception:
        pass
    return None


def _parse_expiry(chain):
    if chain is None or "expiry" not in chain.columns:
        return None
    exp = str(chain["expiry"].dropna().iloc[0]).strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(exp, fmt).date()
        except ValueError:
            continue
    return None


def _latest_chain():
    """Most recent snapshot; prefers a contract that has NOT expired yet."""
    snaps = sorted(glob.glob(os.path.join(SNAP_DIR, "NIFTY_*.csv")))
    if not snaps:
        return None, None, False
    today = dt.date.today()
    chosen, stale = None, False
    for path in snaps:
        df = pd.read_csv(path)
        exp = _parse_expiry(df)
        if exp is None:
            continue
        if exp >= today:
            chosen = (df, os.path.basename(path))
            break
    if chosen is None:
        chosen = (pd.read_csv(snaps[-1]), os.path.basename(snaps[-1]))
        stale = True
    return chosen[0], chosen[1], stale


def _expiry_days(chain):
    exp = _parse_expiry(chain)
    if exp is None:
        return 20
    return max(int((exp - dt.date.today()).days), 1)


def _f(row, col):
    v = row.get(col)
    if v is None:
        return None
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _quote_map(chain):
    q = {}
    if chain is None:
        return q
    for _, r in chain.iterrows():
        q[int(r["strike"])] = {
            "ce_ltp": _f(r, "ce_ltp"),
            "pe_ltp": _f(r, "pe_ltp"),
            "ce_iv": _f(r, "ce_iv"),
            "pe_iv": _f(r, "pe_iv"),
        }
    return q


def _leg_premium(qmap, spot, strike, side, t_days):
    row = qmap.get(strike, {})
    ltp_key, iv_key = (("ce_ltp", "ce_iv") if side == "CE" else ("pe_ltp", "pe_iv"))
    ltp, iv = row.get(ltp_key), row.get(iv_key)
    sigma = _iv_frac(iv)
    if ltp and ltp > 0:
        return {"premium": round(ltp, 2), "iv": sigma, "source": "market"}
    g = bs_price_and_greeks(spot, strike, t_days, sigma, side=side, r=R)
    return {"premium": round(g["price"], 2), "iv": sigma, "source": "bs"}


def _iv_frac(iv):
    """NSE snapshot IV is in percent (0.77 = 0.77%) -> convert to fraction."""
    if iv and 0 < iv < 300:
        return round(iv / 100.0, 4)
    return DEFAULT_SIGMA


def _atm_strike(spot):
    return round(spot / 50) * 50


def _pop(spot, lower, upper, ivs, t_days):
    sigma = np.mean([_iv_frac(iv) for iv in ivs]) if ivs else DEFAULT_SIGMA
    if not sigma:
        sigma = DEFAULT_SIGMA
    p = probability_of_profit(spot, lower=lower, upper=upper,
                              sigma_ann=sigma, t_days=t_days, r=R)
    return round(p * 100, 1) if p is not None else None


def _finalize(spot, strategy, legs, net_pts, max_risk_pts, max_reward_pts,
              be_lower, be_upper, sigma_avg, t_days, snapshot, stale,
              expiry_date, lot=LOT_SIZE):
    rr = None
    if max_risk_pts and max_risk_pts > 0 and max_reward_pts is not None:
        rr = f"1 : {max_reward_pts / max_risk_pts:.2f}"
    pop = _pop(spot, be_lower, be_upper, sigma_avg, t_days)
    out = {
        "strategy": strategy,
        "spot_price": round(spot, 2),
        "snapshot": snapshot or "bs-priced",
        "expiry": str(expiry_date) if expiry_date else None,
        "expiry_days": t_days,
        "stale_snapshot": stale,
        "lot_size": lot,
        "legs": legs,
        "net_premium_per_lot": round(net_pts * lot, 2),
        "max_risk_per_lot": round(max_risk_pts * lot, 2) if max_risk_pts is not None else None,
        "max_reward_per_lot": round(max_reward_pts * lot, 2) if max_reward_pts is not None else None,
        "breakevens": {"lower": be_lower, "upper": be_upper},
        "probability_of_profit": pop,
        "profit_probability": f"{pop}%" if pop is not None else None,
        "risk_reward_ratio": rr,
    }
    return out


def construct_multi_leg_strategy(spot_price=None, strategy_type="IRON_CONDOR",
                                 t_days=None, width=WING):
    """Construct multi-leg option combinations with defined risk.

    Premiums are priced from the latest real OI snapshot; Black-Scholes is
    the fallback when market data is missing. `width` = wing width (pts).
    """
    chain, snapshot, stale = _latest_chain()
    spot = float(spot_price) if spot_price else _default_spot()
    if spot is None:
        return {
            "strategy": strategy_type.upper(),
            "status": "MISSING",
            "spot_price": None,
            "reason": "No real spot available - no multi-leg strategy computed (honest stand-down, no hardcoded fallback).",
            "legs": [],
            "strikes": [],
            "net_premium_per_lot": None,
            "max_risk_per_lot": None,
            "max_reward_per_lot": None,
            "breakevens": {"lower": None, "upper": None},
            "probability_of_profit": None,
            "risk_reward_ratio": None,
        }
    if t_days is None:
        t_days = _expiry_days(chain)
    expiry_date = _parse_expiry(chain)
    qmap = _quote_map(chain)
    atm = _atm_strike(spot)
    st = strategy_type.upper()

    if st == "BULL_CALL_SPREAD":
        k1, k2 = atm, atm + width
        buy = _leg_premium(qmap, spot, k1, "CE", t_days)
        sell = _leg_premium(qmap, spot, k2, "CE", t_days)
        net_debit = buy["premium"] - sell["premium"]
        be = k1 + net_debit
        return _finalize(spot, "BULL_CALL_SPREAD", [
            {"action": "BUY", "option_type": "CE", "strike": k1, "premium": buy["premium"], "iv": buy["iv"], "source": buy["source"]},
            {"action": "SELL", "option_type": "CE", "strike": k2, "premium": sell["premium"], "iv": sell["iv"], "source": sell["source"]},
        ], -net_debit, net_debit, width - net_debit, be, None,
            [buy["iv"], sell["iv"]], t_days, snapshot, stale, expiry_date)

    if st == "BEAR_PUT_SPREAD":
        k1, k2 = atm, atm - width
        buy = _leg_premium(qmap, spot, k1, "PE", t_days)
        sell = _leg_premium(qmap, spot, k2, "PE", t_days)
        net_debit = buy["premium"] - sell["premium"]
        be = k1 - net_debit
        return _finalize(spot, "BEAR_PUT_SPREAD", [
            {"action": "BUY", "option_type": "PE", "strike": k1, "premium": buy["premium"], "iv": buy["iv"], "source": buy["source"]},
            {"action": "SELL", "option_type": "PE", "strike": k2, "premium": sell["premium"], "iv": sell["iv"], "source": sell["source"]},
        ], -net_debit, net_debit, width - net_debit, None, be,
            [buy["iv"], sell["iv"]], t_days, snapshot, stale, expiry_date)

    if st == "SHORT_STRANGLE":
        inner = width // 4 if width != WING else 150
        kp, kc = atm - inner, atm + inner
        sell_p = _leg_premium(qmap, spot, kp, "PE", t_days)
        sell_c = _leg_premium(qmap, spot, kc, "CE", t_days)
        hedge = width if width == WING else width
        khp, khc = kp - hedge, kc + hedge
        buy_p = _leg_premium(qmap, spot, khp, "PE", t_days)
        buy_c = _leg_premium(qmap, spot, khc, "CE", t_days)
        net_credit = sell_p["premium"] + sell_c["premium"] - buy_p["premium"] - buy_c["premium"]
        be_lo, be_hi = kp - net_credit, kc + net_credit
        wing_p = hedge - (sell_p["premium"] - buy_p["premium"])
        wing_c = hedge - (sell_c["premium"] - buy_c["premium"])
        max_risk = max(wing_p, wing_c)
        return _finalize(spot, "SHORT_STRANGLE", [
            {"action": "SELL", "option_type": "PE", "strike": kp, "premium": sell_p["premium"], "iv": sell_p["iv"], "source": sell_p["source"]},
            {"action": "SELL", "option_type": "CE", "strike": kc, "premium": sell_c["premium"], "iv": sell_c["iv"], "source": sell_c["source"]},
            {"action": "BUY", "option_type": "PE", "strike": khp, "premium": buy_p["premium"], "iv": buy_p["iv"], "source": buy_p["source"]},
            {"action": "BUY", "option_type": "CE", "strike": khc, "premium": buy_c["premium"], "iv": buy_c["iv"], "source": buy_c["source"]},
        ], net_credit, max_risk, net_credit, be_lo, be_hi,
            [sell_p["iv"], sell_c["iv"], buy_p["iv"], buy_c["iv"]], t_days, snapshot, stale, expiry_date)

    # IRON_CONDOR (default; ideal for RANGE_LV chop)
    inner = width // 4 if width != WING else 150
    kp_sell, kp_buy = atm - inner, atm - inner - width
    kc_sell, kc_buy = atm + inner, atm + inner + width
    sell_p = _leg_premium(qmap, spot, kp_sell, "PE", t_days)
    buy_p = _leg_premium(qmap, spot, kp_buy, "PE", t_days)
    sell_c = _leg_premium(qmap, spot, kc_sell, "CE", t_days)
    buy_c = _leg_premium(qmap, spot, kc_buy, "CE", t_days)
    net_credit = sell_p["premium"] + sell_c["premium"] - buy_p["premium"] - buy_c["premium"]
    be_lo, be_hi = kp_sell - net_credit, kc_sell + net_credit
    wing_p = width - (sell_p["premium"] - buy_p["premium"])
    wing_c = width - (sell_c["premium"] - buy_c["premium"])
    max_risk = max(wing_p, wing_c)
    out = _finalize(spot, "IRON_CONDOR", [
        {"action": "SELL", "option_type": "PE", "strike": kp_sell, "premium": sell_p["premium"], "iv": sell_p["iv"], "source": sell_p["source"]},
        {"action": "BUY", "option_type": "PE", "strike": kp_buy, "premium": buy_p["premium"], "iv": buy_p["iv"], "source": buy_p["source"]},
        {"action": "SELL", "option_type": "CE", "strike": kc_sell, "premium": sell_c["premium"], "iv": sell_c["iv"], "source": sell_c["source"]},
        {"action": "BUY", "option_type": "CE", "strike": kc_buy, "premium": buy_c["premium"], "iv": buy_c["iv"], "source": buy_c["source"]},
    ], net_credit, max_risk, net_credit, be_lo, be_hi,
        [sell_p["iv"], buy_p["iv"], sell_c["iv"], buy_c["iv"]], t_days, snapshot, stale, expiry_date)
    out["recommended_for"] = "Low Volatility Range-Bound Market (RANGE_LV)"
    return out


if __name__ == "__main__":
    print("=== TESTING MULTI-LEG OPTION STRATEGY ENGINE ===")
    for st in ("IRON_CONDOR", "BULL_CALL_SPREAD", "BEAR_PUT_SPREAD", "SHORT_STRANGLE"):
        print(json.dumps(construct_multi_leg_strategy(strategy_type=st), indent=2))
        print()
