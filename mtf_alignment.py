"""Multi-Timeframe Trend Alignment Engine for NIFTY Research.

Computes trend alignment across 4 trend windows from REAL market data:
  5m_micro / 15m_swing / 1h_structural / daily_macro

Each window's trend is derived from actual close prices (slope + EMA
position + RSI). When no real data is available the engine reports NO_DATA
instead of fabricating a signal.
"""
import os
import sys
import json
import datetime as dt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

HIST_PATH = os.path.join("data", "nifty_history.csv")

# (label, window_bars) - trend measured over the last N real EOD closes.
# Intraday labels are proxies for short->long horizon; basis is transparent.
WINDOWS = [
    ("5m_micro_trend", 5),
    ("15m_swing_trend", 10),
    ("1h_structural_trend", 20),
    ("daily_macro_trend", 50),
]


def _load_real_history():
    """Load real daily close history (NSE data cached to nifty_history.csv)."""
    if not os.path.exists(HIST_PATH):
        return None
    try:
        df = pd.read_csv(HIST_PATH)
        if df.empty or "close" not in df.columns:
            return None
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["close"])
        return df if len(df) >= 2 else None
    except Exception:
        return None


def _window_trend(closes, ema_series, rsi_val, window):
    """Real trend read: slope over the window + price vs EMA + RSI."""
    win = closes.tail(window)
    if len(win) < 2:
        return {"trend": "NEUTRAL", "basis": "EOD_window", "note": "insufficient bars"}
    slope = float((win.iloc[-1] - win.iloc[0]) / (len(win) - 1))
    price = float(closes.iloc[-1])
    ema = float(ema_series.iloc[-1])
    above_ema = price > ema
    if slope > 0 and above_ema:
        trend = "BULLISH"
    elif slope < 0 and not above_ema:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"
    return {
        "trend": trend,
        "rsi": round(float(rsi_val), 1) if rsi_val is not None and rsi_val == rsi_val else None,
        "above_vwap": above_ema,
        "slope_points": round(float(slope), 2),
        "basis": "EOD_window",
        "window_bars": window,
    }


def compute_mtf_alignment(spot_price=None):
    """Compute trend alignment across the 4 windows from real close data."""
    df = _load_real_history()
    if df is None:
        return {
            "mtf_engine_status": "NO_DATA",
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
            "spot_price": spot_price,
            "overall_direction": "NEUTRAL",
            "alignment_score": "0/4",
            "alignment_status": "NO_DATA - no history available (run build_data.py)",
            "timeframe_details": {},
        }

    closes = df["close"].astype(float)
    spot = float(spot_price) if spot_price else float(closes.iloc[-1])

    ema_series = closes.ewm(span=20, adjust=False).mean()
    try:
        from indicators import rsi
        rsi_series = rsi(closes, period=14)
        rsi_val = float(rsi_series.dropna().iloc[-1]) if not rsi_series.dropna().empty else None
    except Exception:
        rsi_val = None

    timeframe_trends = {}
    for label, w in WINDOWS:
        timeframe_trends[label] = _window_trend(closes, ema_series, rsi_val, w)

    bullish_count = sum(1 for tf in timeframe_trends.values() if tf["trend"] == "BULLISH")
    bearish_count = sum(1 for tf in timeframe_trends.values() if tf["trend"] == "BEARISH")

    if bullish_count == 4:
        alignment_status = "4/4 WINDOWS BULLISH (ULTRA HIGH CONFLUENCE)"
        overall_direction = "BULLISH"
    elif bearish_count == 4:
        alignment_status = "4/4 WINDOWS BEARISH (ULTRA HIGH CONFLUENCE)"
        overall_direction = "BEARISH"
    elif bullish_count >= 3:
        alignment_status = "3/4 WINDOWS BULLISH (HIGH ALIGNMENT)"
        overall_direction = "BULLISH"
    elif bearish_count >= 3:
        alignment_status = "3/4 WINDOWS BEARISH (HIGH ALIGNMENT)"
        overall_direction = "BEARISH"
    else:
        alignment_status = "MIXED ALIGNMENT (NOISY / CHOPPY MARKET)"
        overall_direction = "NEUTRAL"

    return {
        "mtf_engine_status": "ALIGNMENT_COMPUTED",
        "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "spot_price": spot,
        "overall_direction": overall_direction,
        "alignment_score": f"{max(bullish_count, bearish_count)}/4 Aligned",
        "alignment_status": alignment_status,
        "timeframe_details": timeframe_trends
    }


if __name__ == "__main__":
    print("=== TESTING MULTI-TIMEFRAME ALIGNMENT ENGINE ===")
    res = compute_mtf_alignment()
    print(json.dumps(res, indent=2))
