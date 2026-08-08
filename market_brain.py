"""Market brain - knowledge base + reasoning engine.

Trader-style reasoning engine that combines:
- Market regime detection (trending / ranging / volatile / transition)
- Multi-indicator directional consensus
- Regime->strategy mapping (right tool for the market state)
- Options layer (IV regime, strike selection, risk)
Produces a structured verdict with EXPLICIT REASONING (why each call).
"""
import numpy as np
import pandas as pd

REGIME_TRENDING = "TRENDING"
REGIME_RANGE = "RANGE"
REGIME_VOLATILE = "VOLATILE"
REGIME_TRANSITION = "TRANSITION"


def detect_regime(df, row):
    """Classify market state from a single row of indicator data."""
    adx = row.get("adx", 0)
    pdi = row.get("pdi", 0)
    mdi = row.get("mdi", 0)

    # Bollinger band width percentile across recent window (volatility gauge)
    bb_width = (row.get("bb_upper", 0) - row.get("bb_lower", 0)) / max(row.get("close", 1), 1)
    hist_width = df["bb_upper"] - df["bb_lower"]
    width_pctile = float((hist_width < (row.get("bb_upper", 0) - row.get("bb_lower", 0))).mean() * 100)

    reasons = []
    if adx >= 25 and abs(pdi - mdi) >= 5:
        regime = REGIME_TRENDING
        reasons.append(f"ADX {adx:.0f} strong + directional spread {abs(pdi-mdi):.0f}")
    elif adx <= 20:
        regime = REGIME_RANGE
        reasons.append(f"ADX {adx:.0f} low = choppy/range-bound")
    elif width_pctile >= 80:
        regime = REGIME_VOLATILE
        reasons.append(f"Bollinger width at {width_pctile:.0f}th percentile = volatility spike")
    else:
        regime = REGIME_TRANSITION
        reasons.append(f"ADX {adx:.0f} = trend forming, no direction yet")
    return regime, reasons


def directional_consensus(df, row):
    """Each indicator votes +1 (bullish), -1 (bearish), 0 (neutral). Returns votes + score."""
    votes = {}
    close = row.get("close", 0)

    votes["price_vs_sma50"] = 1 if close > row.get("sma50", close) else (-1 if close < row.get("sma50", close) else 0)
    votes["price_vs_sma20"] = 1 if close > row.get("sma20", close) else (-1 if close < row.get("sma20", close) else 0)
    votes["super_trend"] = 1 if row.get("supertrend", 0) == 1 else (-1 if row.get("supertrend", 0) == -1 else 0)

    rsi = row.get("rsi14", 50)
    votes["rsi"] = 1 if 45 <= rsi <= 65 else (-1 if (rsi > 70 or rsi < 30) else 0)
    votes["macd"] = 1 if row.get("macd_hist", 0) > 0 else (-1 if row.get("macd_hist", 0) < 0 else 0)
    votes["adx_pdi"] = 1 if row.get("pdi", 0) > row.get("mdi", 0) else (-1 if row.get("pdi", 0) < row.get("mdi", 0) else 0)

    score = sum(votes.values())
    total = len(votes)
    return votes, score, total


def regime_strategy_bias(regime):
    """Which strategy families fit the current market state (YouTuber logic mapping)."""
    mapping = {
        REGIME_TRENDING: {
            "favored": ["trend_sma", "momentum_roc", "volume_trend", "golden_cross"],
            "avoid": ["rsi_meanrev", "bollinger", "stoch_cross"],
            "note": "Trend is king. Let winners run, momentum options work.",
        },
        REGIME_RANGE: {
            "favored": ["rsi_meanrev", "bollinger", "stoch_cross"],
            "avoid": ["breakout", "donchian", "momentum_roc"],
            "note": "Range-bound: fade extremes, buy dips at support, sell at resistance.",
        },
        REGIME_VOLATILE: {
            "favored": ["breakout", "momentum_roc"],
            "avoid": ["rsi_meanrev", "bollinger"],
            "note": "Volatile: big moves, but IV crush risk high. Trade breakouts only, cut fast.",
        },
        REGIME_TRANSITION: {
            "favored": ["supertrend", "golden_cross"],
            "avoid": ["breakout", "bollinger"],
            "note": "Trend forming: wait for confirmation, small size.",
        },
    }
    return mapping[regime]


def options_layer(row):
    """Options-specific reasoning (IV regime, strike distance, risk)."""
    iv = row.get("iv", 0)
    close = row.get("close", 0)
    hv = row.get("hv", 0)
    note = []
    if iv and hv:
        iv_ratio = iv / hv if hv else 0
        if iv_ratio < 1.0:
            note.append(f"IV ({iv:.0f}%) < HV ({hv:.0f}%) = cheap premium, buying favorable")
        elif iv_ratio > 1.4:
            note.append(f"IV ({iv:.0f}%) >> HV ({hv:.0f}%) = premium expensive, avoid buying")
        else:
            note.append(f"IV ({iv:.0f}%) vs HV ({hv:.0f}%) = fair premium")
    return note


def make_verdict(df, row, regime, consensus_score, total_votes, horizon_bias=0):
    """Final decision with explicit reasoning lines.

    TRAINED RULES (derived from walk-forward training):
    1. PUT calls beat CALL calls on NIFTY daily data -> tighten CALL threshold, loosen PUT.
    2. VOLATILE regime most reliable -> weight regime stronger there.
    3. High confidence score alone is NOT predictive -> blend regime reliability.
    """
    reasons = []
    regime_fit = regime_strategy_bias(regime)

    pct_score = consensus_score / total_votes if total_votes else 0

    # Calibration from training: PUTs were 44.8% vs CALLs 27.8%
    call_thresh, put_thresh = 0.45, 0.30

    if regime == REGIME_TRENDING:
        if pct_score > call_thresh:
            bias, strength = "CALL", "HIGH"
        elif pct_score < -put_thresh:
            bias, strength = "PUT", "HIGH"
        else:
            bias, strength = "NEUTRAL", "LOW"
    elif regime == REGIME_RANGE:
        rsi = row.get("rsi14", 50)
        if rsi < 30:
            bias, strength = "CALL", "MEDIUM"
        elif rsi > 70:
            bias, strength = "PUT", "MEDIUM"
        elif pct_score < -put_thresh:
            bias, strength = "PUT", "LOW"
        elif pct_score > call_thresh:
            bias, strength = "CALL", "LOW"
        else:
            bias, strength = "NEUTRAL", "LOW"
    elif regime == REGIME_VOLATILE:
        # Trained: best accuracy here. Bias on consensus, weaker threshold.
        bias = "CALL" if pct_score > 0.10 else ("PUT" if pct_score < -0.10 else "NEUTRAL")
        strength = "MEDIUM" if bias != "NEUTRAL" else "LOW"
    else:  # transition
        bias = "PUT" if pct_score < -put_thresh else ("CALL" if pct_score > call_thresh else "NEUTRAL")
        strength = "LOW"

    reasons.append(f"Regime: {regime} - {regime_fit['note']}")
    reasons.append(f"Consensus: {consensus_score}/{total_votes} votes {'bullish' if consensus_score>0 else ('bearish' if consensus_score<0 else 'neutral')}")
    reasons.append(f"Trained calibration: CALL needs {call_thresh*100:.0f}% consensus, PUT needs {put_thresh*100:.0f}%")

    # TRAINED RELIABILITY (walk-forward hit-rates, 2-day horizon, real NIFTY 2024-26)
    # RANGE ~49%, TRENDING ~46%, VOLATILE ~70% (small sample), TRANSITION ~46%
    regime_reliability = {
        REGIME_RANGE: 0.49,
        REGIME_TRENDING: 0.46,
        REGIME_VOLATILE: 0.55,
        REGIME_TRANSITION: 0.46,
    }
    if bias == "NEUTRAL":
        confidence = 50.0
    else:
        consensus_part = abs(pct_score)
        strength_bonus = {"HIGH": 0.10, "MEDIUM": 0.05, "LOW": 0.0}[strength]
        confidence = (regime_reliability[regime] + consensus_part * 0.25 + strength_bonus) * 100
        confidence = max(50.0, min(confidence, 75.0))  # honest cap: never overstate

    levels = {"support": None, "resistance": None}
    if not np.isnan(row.get("bb_lower", np.nan)):
        levels["support"] = row["bb_lower"]
    if not np.isnan(row.get("bb_upper", np.nan)):
        levels["resistance"] = row["bb_upper"]
    if not np.isnan(row.get("sma50", np.nan)):
        levels["support"] = max(filter(None, [levels["support"], row["sma50"]])) if levels["support"] else row["sma50"]
    if not np.isnan(row.get("sma200", np.nan)):
        levels["resistance"] = max(filter(None, [levels["resistance"], row["sma200"]])) if levels["resistance"] else row["sma200"]

    opt_notes = options_layer(row)

    return {
        "bias": bias,
        "strength": strength,
        "confidence": round(confidence, 0),
        "reasons": reasons,
        "favored_strategies": regime_fit["favored"],
        "avoid_strategies": regime_fit["avoid"],
        "levels": levels,
        "options_notes": opt_notes,
    }


def analyze_market(df, iv=None):
    """Full reasoning pipeline for the latest row of a data frame."""
    row = df.iloc[-1]
    regime, regime_reasons = detect_regime(df, row)
    votes, score, total = directional_consensus(df, row)
    if iv is not None:
        row = row.copy()
        hv = float(np.log(df["close"] / df["close"].shift(1)).tail(20).std() * np.sqrt(252))
        row["iv"] = iv
        row["hv"] = hv
    verdict = make_verdict(df, row, regime, score, total)
    return {
        "date": df.index[-1],
        "close": row["close"],
        "regime": regime,
        "regime_reasons": regime_reasons,
        "votes": votes,
        "consensus_score": score,
        "total_votes": total,
        "verdict": verdict,
    }
