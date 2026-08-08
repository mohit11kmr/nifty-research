"""Sentiment engine - aggregates global risk, domestic positioning, FII/DII.

Risk-on / risk-off scoring used by the agent's reasoning:
Positive score = risk-on (bullish Nifty), negative = risk-off.
"""
import datetime as dt


def score_global(snap):
    """Score global snapshot: US indices, DXY, metals, crude, BTC."""
    score = 0
    notes = []
    if not snap:
        return 0, notes

    us = snap.get("S&P 500", {})
    if us.get("change_pct") is not None:
        if us["change_pct"] > 0.5:
            score += 2; notes.append("S&P positive => risk-on")
        elif us["change_pct"] > 0:
            score += 1; notes.append("S&P mildly positive")
        elif us["change_pct"] > -0.5:
            score -= 1; notes.append("S&P mildly negative")
        else:
            score -= 2; notes.append("S&P sharply negative => risk-off")

    nasdaq = snap.get("Nasdaq", {})
    if nasdaq.get("change_pct") is not None:
        score += (1 if nasdaq["change_pct"] > 0 else -1)
        notes.append(f"Nasdaq {nasdaq['change_pct']:+.1f}%")

    dxy = snap.get("Dollar Index", {})
    if dxy.get("change_pct") is not None:
        # weak dollar = EM/FII inflow positive
        if dxy["change_pct"] < -0.3:
            score += 2; notes.append("Dollar weak => FII inflow likely (EM positive)")
        elif dxy["change_pct"] > 0.3:
            score -= 1; notes.append("Dollar firm => mild headwind for EM")

    gold = snap.get("Gold", {})
    if gold.get("change_pct") is not None:
        if gold["change_pct"] > 1.0:
            score -= 1; notes.append(f"Gold +{gold['change_pct']:.1f}% = fear/hedge demand up")
        # gold up + dollar down usually risk-on rotated into metals, not bearish

    crude = snap.get("Crude Oil", {})
    if crude.get("change_pct") is not None:
        if crude["change_pct"] > 2.0:
            score -= 1; notes.append("Crude spiking = inflation/margin concern for India")

    btc = snap.get("Bitcoin", {})
    if btc.get("change_pct") is not None:
        score += (1 if btc["change_pct"] > 1 else 0)
        if btc["change_pct"] > 1:
            notes.append("Crypto risk-on")

    usdinr = snap.get("USDINR", {})
    if usdinr.get("change_pct") is not None:
        if usdinr["change_pct"] > 0.3:
            score -= 1; notes.append(f"Rupee weakening (USDINR {usdinr['change_pct']:+.2f}%) => FII outflow risk")
        elif usdinr["change_pct"] < -0.3:
            score += 1; notes.append("Rupee firm => foreign flows positive")

    return score, notes


def score_fii_dii(fdi, horizon_days=1):
    """FII/DII cash + futures positioning score."""
    score = 0
    notes = []
    if not fdi or "error" in fdi:
        return 0, notes
    fii_cash = fdi.get("fii_equity_cash") or 0
    dii_cash = fdi.get("dii_equity_cash") or 0
    fii_idx_fut = fdi.get("fii_future_index") or 0

    # Combined net (FII + DII) in crores
    net = fii_cash + dii_cash
    notes.append(f"FII cash {fii_cash:+,.0f} cr | DII cash {dii_cash:+,.0f} cr | Net {net:+,.0f} cr")
    if net > 1500:
        score += 2; notes.append("Strong net buying => bullish")
    elif net > 0:
        score += 1; notes.append("Net buying => mildly bullish")
    elif net > -1500:
        score -= 1; notes.append("Net selling => mildly bearish")
    else:
        score -= 2; notes.append("Strong net selling => bearish")

    if fii_idx_fut:
        notes.append(f"FII index futures {fii_idx_fut:+,.0f}")
        score += (1 if fii_idx_fut > 0 else -1)
    return score, notes


def score_options(pcr, max_pain, spot):
    """Options positioning: PCR + spot vs max pain."""
    score = 0
    notes = []
    if pcr:
        if pcr > 1.5:
            score += 1; notes.append(f"PCR {pcr:.2f} = put-heavy => contrarian bullish")
        elif pcr < 0.7:
            score -= 1; notes.append(f"PCR {pcr:.2f} = call-heavy => contrarian bearish")
        else:
            notes.append(f"PCR {pcr:.2f} = balanced")
    if max_pain and spot:
        diff = (spot - max_pain) / max_pain * 100
        if abs(diff) > 1.0:
            pull = "up" if diff < 0 else "down"
            score += (1 if pull == "up" else -1) if abs(diff) > 1.5 else 0
            notes.append(f"Spot {diff:+.1f}% vs Max Pain {max_pain:,.0f} => magnetic pull {pull}")
    return score, notes


def aggregate(snap, fdi, pcr=None, max_pain=None, spot=None, weights=None):
    """Combine all sentiment into one score + reasoning lines."""
    w = weights or {"global": 1.0, "fii": 1.5, "options": 0.5}
    gs, gnotes = score_global(snap)
    fs, fnotes = score_fii_dii(fdi)
    os_, onotes = score_options(pcr, max_pain, spot)

    total = gs * w["global"] + fs * w["fii"] + os_ * w["options"]
    notes = (gnotes or []) + (fnotes or []) + (onotes or [])

    if total >= 2:
        label, strength = "BULLISH", "strong"
    elif total > 0:
        label, strength = "MILDLY BULLISH", "moderate"
    elif total == 0:
        label, strength = "NEUTRAL", "balanced"
    elif total > -2:
        label, strength = "MILDLY BEARISH", "moderate"
    else:
        label, strength = "BEARISH", "strong"

    return {
        "score": round(total, 2),
        "global_score": gs,
        "fii_score": fs,
        "options_score": os_,
        "label": label,
        "strength": strength,
        "notes": notes,
    }
