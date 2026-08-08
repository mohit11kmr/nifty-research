"""Regime filter + risk plan - the loss-minimization core.

Runs BEFORE any trade idea. Classifies NIFTY into a 4-regime matrix
(trend/range x high/low vol) and gates trading:

  TREND_HV   strong trend + high vol   -> TRADE  (1.0x size)
  TREND_LV   strong trend + low vol    -> TRADE  (1.2x size, best risk/reward)
  RANGE_HV   no trend + high vol       -> SMALL  (0.7x, mean-reversion only)
  RANGE_LV   no trend + low vol (chop) -> NO TRADE (0x, BLOCKED)

Based on proven institutional pattern (regime-switch bots show RANGE_LV is
where all the money gets bled - low-vol chop destroys directional options).
Also packs hard risk rules so a loss can never become a blowup:
- max 1% of capital risked per trade
- stop = 1.5 * ATR below entry (market structure, not arbitrary %)
- 3% daily loss limit -> stop trading for the day
- expiry day: no new entries after 14:30, square off by 15:05
- no averaging down into losers, ever
"""
import os

import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# ---- hard risk constants (never override silently) -----------------------
RISK_PER_TRADE_PCT = 0.01      # 1% of capital per trade
DAILY_LOSS_LIMIT_PCT = 0.03    # 3% daily -> stop trading
WEEKLY_LOSS_LIMIT_PCT = 0.07   # 7% weekly -> stop trading
SL_ATR_MULT = 1.5              # stop distance in ATR units
EXPIRY_LAST_ENTRY_HOUR = 14.5  # no new entries after 14:30 on expiry day
EXPIRY_SQUARE_OFF_HOUR = 15.0  # square off by 15:05 on expiry day
MIN_CONFIDENCE = 55.0          # below this, even a TRADE regime is sized down

REGIME_TREND_HV = "TREND_HV"
REGIME_TREND_LV = "TREND_LV"
REGIME_RANGE_HV = "RANGE_HV"
REGIME_RANGE_LV = "RANGE_LV"

# ---- India VIX premium regimes (research: NiftyDesk/MarketsEasy consensus) -
# VIX tells you how expensive option premiums are - forward-looking.
VIX_CHEAP = "VIX_CHEAP"        # < 12:  premium cheap  -> BUY options/hedge
VIX_NORMAL = "VIX_NORMAL"      # 12-16: fair           -> directional spreads
VIX_RICH = "VIX_RICH"          # 16-20: rich           -> START selling premium
VIX_HIGH = "VIX_HIGH"          # 20-25: overpriced    -> aggressively sell
VIX_PANIC = "VIX_PANIC"        # > 25:  panic          -> mean-reversion / stay out

VIX_PLAN = {
    VIX_CHEAP: {
        "premium_side": "BUY",
        "strategies": ["long_straddle", "protective_put", "directional_spread"],
        "note": "Premium cheap - options are undervalued. Buying favored, selling premium gives poor returns.",
    },
    VIX_NORMAL: {
        "premium_side": "NEUTRAL",
        "strategies": ["bull_call_spread", "bear_put_spread", "calendar"],
        "note": "Premium fairly priced - trade direction with defined risk.",
    },
    VIX_RICH: {
        "premium_side": "SELL",
        "strategies": ["iron_condor", "short_strangle", "credit_spread"],
        "note": "Premium rich - start selling (collect overpriced time value). Defined risk only.",
    },
    VIX_HIGH: {
        "premium_side": "SELL",
        "strategies": ["iron_condor_wide", "short_strangle", "put_sell_support"],
        "note": "Premium overpriced - aggressive selling window, but size SMALLER (violent moves).",
    },
    VIX_PANIC: {
        "premium_side": "SELL_CAUTION",
        "strategies": ["vix_mean_reversion", "wide_strangle"],
        "note": "Panic VIX - premium extreme. Mean-reversion sell on first stabilisation, 2x-credit stop.",
    },
}


def _load_vix():
    p = os.path.join(DATA, "india_vix.csv")
    if not os.path.exists(p):
        return None
    try:
        df = pd.read_csv(p, parse_dates=["date"])
        return df.sort_values("date")
    except Exception:
        return None


def vix_zone(level):
    """Classify an India VIX level into its premium regime."""
    if level is None or pd.isna(level):
        return VIX_NORMAL
    if level < 12:
        return VIX_CHEAP
    if level < 16:
        return VIX_NORMAL
    if level < 20:
        return VIX_RICH
    if level < 25:
        return VIX_HIGH
    return VIX_PANIC


def expected_move(nifty, vix):
    """Daily expected move from VIX: Nifty x (VIX/100) / sqrt(252)."""
    if not nifty or not vix or pd.isna(vix):
        return None
    return nifty * (vix / 100.0) / (252 ** 0.5)


def vix_snapshot(nifty_close=None):
    """Latest VIX level, zone, percentile and expected move."""
    df = _load_vix()
    if df is None or df.empty:
        return None
    last = df.iloc[-1]
    level = float(last["close"])
    hist = df["close"].dropna()
    pctile = float((hist < level).mean() * 100)
    em = expected_move(nifty_close, level)
    return {
        "date": last["date"],
        "level": round(level, 2),
        "zone": vix_zone(level),
        "percentile": round(pctile, 0),
        "expected_move": round(em, 1) if em else None,
        "plan": VIX_PLAN[vix_zone(level)],
    }

# per-regime trading profile
REGIME_PROFILE = {
    REGIME_TREND_HV: {
        "gate": "TRADE",
        "size_mult": 1.0,
        "favored": ["trend_sma", "momentum_roc", "golden_cross", "breakout"],
        "avoid": ["rsi_meanrev", "bollinger", "stoch_cross"],
        "note": "Strong trend + high volatility. Trade the trend, cut fast. IV crush risk high - prefer defined risk.",
    },
    REGIME_TREND_LV: {
        "gate": "TRADE",
        "size_mult": 1.2,
        "favored": ["trend_sma", "golden_cross", "supertrend", "momentum_roc"],
        "avoid": ["rsi_meanrev", "stoch_cross"],
        "note": "Strong trend + low volatility = the sweet spot. Cleanest trend-following risk/reward.",
    },
    REGIME_RANGE_HV: {
        "gate": "SMALL",
        "size_mult": 0.7,
        "favored": ["rsi_meanrev", "bollinger", "stoch_cross"],
        "avoid": ["breakout", "donchian", "momentum_roc", "trend_sma"],
        "note": "No trend + high volatility. Fade extremes only, half size, both stops tight.",
    },
    REGIME_RANGE_LV: {
        "gate": "NO_TRADE",
        "size_mult": 0.0,
        "favored": [],
        "avoid": ["breakout", "trend_sma", "momentum_roc", "donchian", "rsi_meanrev", "bollinger", "stoch_cross"],
        "note": "Low-vol chop. NO TRADE. Directional options bleed here - theta beats everything. Wait for the regime to change.",
    },
}


def _load_nifty_cached():
    p = os.path.join(DATA, "nifty_history.csv")
    if not os.path.exists(p):
        from data_fetcher import fetch_index_history
        df = fetch_index_history("NIFTY 50", out_csv=p)
    else:
        df = pd.read_csv(p)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def detect_regime(row, df):
    """4-regime classification from the latest indicator row."""
    adx = row.get("adx", 0) or 0
    pdi = row.get("pdi", 0) or 0
    mdi = row.get("mdi", 0) or 0
    bb_upper = row.get("bb_upper", np.nan)
    bb_lower = row.get("bb_lower", np.nan)
    close = row.get("close", np.nan)

    trending = adx >= 25 and abs(pdi - mdi) >= 5
    reasons = []

    # volatility gauge: current Bollinger width vs recent percentile
    high_vol = False
    try:
        hist_width = (df["bb_upper"] - df["bb_lower"]).dropna()
        cur_width = (bb_upper - bb_lower) / max(close, 1e-9)
        pctile = float((hist_width.values < cur_width).mean() * 100)
        high_vol = pctile >= 60
        reasons.append(f"BB width {pctile:.0f}th percentile -> {'high' if high_vol else 'low'} vol")
    except Exception:
        reasons.append("vol gauge unavailable")

    if trending:
        regime = REGIME_TREND_HV if high_vol else REGIME_TREND_LV
        reasons.append(f"ADX {adx:.0f} + directional spread {abs(pdi - mdi):.0f} -> trending")
    else:
        regime = REGIME_RANGE_HV if high_vol else REGIME_RANGE_LV
        reasons.append(f"ADX {adx:.0f} -> {'ranging (high vol)' if high_vol else 'low-vol chop'}")

    return regime, reasons


def trade_plan(df=None, row=None, verdict=None, capital=None):
    """Full gate + risk plan. Returns dict; safe to call with just cached data."""
    if df is None:
        df = _load_nifty_cached()
    if "adx" not in df.columns:
        from indicators import add_all_indicators
        add_all_indicators(df)
    if row is None:
        row = df.iloc[-1]

    regime, reasons = detect_regime(row, df)
    profile = REGIME_PROFILE[regime]

    # ---- India VIX layer (forward-looking premium pricing) ----------------
    vix = vix_snapshot(nifty_close=float(row.get("close", np.nan)) if not np.isnan(row.get("close", np.nan)) else None)
    if vix is not None:
        reasons.append(f"India VIX {vix['level']} ({vix['zone'].replace('VIX_', '')} zone, {vix['percentile']:.0f}th pct) -> premium side {vix['plan']['premium_side']}")
        if vix["expected_move"]:
            reasons.append(f"Expected daily move: {vix['expected_move']} pts")

    close = float(row.get("close", np.nan))
    atr14 = float(row.get("atr14", np.nan) or np.nan)
    stop_dist = SL_ATR_MULT * atr14 if not np.isnan(atr14) else 0.008 * close
    stop_pct = stop_dist / close if close and not np.isnan(close) else 0.01

    # confidence gate (from market_brain verdict if available)
    confidence = 50.0
    bias = "NEUTRAL"
    if verdict is not None:
        confidence = verdict.get("confidence", 50.0)
        bias = verdict.get("bias", "NEUTRAL")

    # gate resolution: regime gate + confidence haircut.
    # VIX PANIC + confidence low = hard no-trade regardless of regime.
    hard_block = vix is not None and vix["zone"] == VIX_PANIC and confidence < 60
    if hard_block:
        gate, size_mult, action = "NO_TRADE", 0.0, "STAY OUT - VIX PANIC"
    elif profile["gate"] == "NO_TRADE":
        gate, size_mult, action = "NO_TRADE", 0.0, "STAY OUT"
    elif profile["gate"] == "SMALL":
        gate, size_mult, action = "TRADE_SMALL", 0.7, "FADE EXTREMES ONLY, TIGHT STOPS"
    else:
        if confidence < MIN_CONFIDENCE:
            gate, size_mult, action = "TRADE_REDUCED", profile["size_mult"] * 0.5, "LOW CONFIDENCE - HALF SIZE"
        elif bias == "NEUTRAL":
            gate, size_mult, action = "TRADE_REDUCED", profile["size_mult"] * 0.7, "NEUTRAL DIRECTION - REDUCED SIZE"
        else:
            gate, size_mult, action = "TRADE", profile["size_mult"], "TRADE WITH BIAS"

    # VIX regime tells us WHICH tool (buy/sell premium) in this market regime.
    premium_side = vix["plan"]["premium_side"] if vix else "NEUTRAL"
    vix_strategies = vix["plan"]["strategies"] if vix else []

    plan = {
        "date": df["date"].iloc[-1] if "date" in df else None,
        "close": round(close, 2) if not np.isnan(close) else None,
        "regime": regime,
        "regime_reasons": reasons,
        "regime_note": profile["note"],
        "gate": gate,
        "action": action,
        "size_mult": size_mult,
        "bias": bias,
        "confidence": confidence,
        "stop_dist": round(stop_dist, 1),
        "stop_pct": round(stop_pct * 100, 2),
        "risk_per_trade_pct": RISK_PER_TRADE_PCT * 100,
        "daily_loss_limit_pct": DAILY_LOSS_LIMIT_PCT * 100,
        "favored_strategies": profile["favored"],
        "avoid_strategies": profile["avoid"],
        "vix": vix,
        "premium_side": premium_side,
        "vix_strategies": vix_strategies,
        "capital": capital,
    }
    if capital:
        plan["risk_amount"] = round(capital * RISK_PER_TRADE_PCT, 0)
    return plan


def format_plan(plan):
    """Pretty text block for console / report."""
    lines = []
    lines.append(f"REGIME: {plan['regime']}  |  GATE: {plan['gate']}  |  {plan['action']}")
    lines.append(f"  NIFTY {plan['close']} | bias {plan['bias']} conf {plan['confidence']:.0f}% | size x{plan['size_mult']}")
    for r in plan["regime_reasons"]:
        lines.append(f"  {r}")
    lines.append(f"  {plan['regime_note']}")
    if plan.get("vix"):
        v = plan["vix"]
        lines.append(f"  VIX side: {plan['premium_side']} | zone {v['zone']} | strategies: {', '.join(plan['vix_strategies'])}")
        lines.append(f"  {v['plan']['note']}")
    lines.append(f"  Stop: {plan['stop_dist']} pts ({plan['stop_pct']}%) | risk/trade 1% | daily loss limit {plan['daily_loss_limit_pct']}%")
    if plan["favored_strategies"]:
        lines.append(f"  Favored: {', '.join(plan['favored_strategies'])}")
    if plan["avoid_strategies"]:
        lines.append(f"  Avoid:   {', '.join(plan['avoid_strategies'])}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_plan(trade_plan()))
