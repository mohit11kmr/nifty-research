"""Institutional Volume Analytics & Pocket Pivot Engine for NIFTY Research.

Adopted from volume base reserch architecture:
Calculates (from REAL volume/price data):
1. Volume Surge Ratio (Current Volume / 20-period Volume SMA)
2. On-Balance Volume (OBV) & EMA Trend Alignment
3. Chaikin Money Flow (CMF 20) Institutional Inflow/Outflow
4. Pocket Pivot Institutional Accumulation Detector

Reports NO_DATA honestly when no real volume data is available - it never
fabricates a surge or an accumulation signal.
"""
import os
import json
import numpy as np
import pandas as pd

HIST_PATH = os.path.join("data", "nifty_history.csv")


def _load_real_history():
    """Load real daily OHLCV history (NSE data cached to nifty_history.csv)."""
    if not os.path.exists(HIST_PATH):
        return None
    try:
        df = pd.read_csv(HIST_PATH)
        need = ["open", "high", "low", "close", "volume"]
        if df.empty or not all(c in df.columns for c in need):
            return None
        for c in need:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=need)
        df = df[df["volume"] > 0]
        return df if len(df) >= 2 else None
    except Exception:
        return None


def _chaikin_money_flow(df, period=20):
    hl = df["high"] - df["low"]
    if (hl <= 0).any():
        return None
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / hl
    mfv = mfm * df["volume"]
    mfv_sum = mfv.rolling(period).sum()
    vol_sum = df["volume"].rolling(period).sum()
    cmf = (mfv_sum / vol_sum).dropna()
    return float(cmf.iloc[-1]) if not cmf.empty else None


def _obv_trend(df):
    sign = np.sign(df["close"].diff()).fillna(0)
    obv = (sign * df["volume"]).cumsum()
    obv = pd.Series(obv, index=df.index)
    if len(obv) < 21:
        return "FLAT"
    ema_fast = obv.ewm(span=5, adjust=False).mean().iloc[-1]
    ema_slow = obv.ewm(span=20, adjust=False).mean().iloc[-1]
    if ema_fast > ema_slow:
        return "ACCUMULATION_BULLISH"
    if ema_fast < ema_slow:
        return "DISTRIBUTION_BEARISH"
    return "FLAT"


def compute_volume_analytics(spot_price=None):
    """Compute volume surge ratio, CMF, OBV, and Pocket Pivot accumulation status."""
    df = _load_real_history()
    if df is None:
        return {
            "volume_analytics_status": "NO_DATA",
            "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S IST"),
            "spot_price": spot_price,
            "volume_surge_ratio": None,
            "chaikin_money_flow_cmf": None,
            "on_balance_volume_trend": "NO_DATA",
            "pocket_pivot_detected": False,
            "institutional_conviction": "NO_DATA",
            "volume_bias": "NEUTRAL",
            "analytics_insight": "No real volume data available - no volume signal computed.",
        }

    spot = float(spot_price) if spot_price else float(df["close"].iloc[-1])

    # Real volume surge ratio (latest / 20-period SMA)
    vol_series = df["volume"].tail(21)
    vol_sma20 = float(vol_series.iloc[:-1].mean()) if len(vol_series) > 1 else 0.0
    latest_vol = float(vol_series.iloc[-1])
    vol_surge_ratio = round(latest_vol / vol_sma20, 2) if vol_sma20 > 0 else None

    cmf_20 = _chaikin_money_flow(df)
    obv_trend = _obv_trend(df)

    # Pocket pivot: 2x volume surge on an up day closing in the top 25% of range
    last = df.iloc[-1]
    day_range = float(last["high"] - last["low"])
    closes_high = day_range > 0 and float(last["close"]) >= float(last["low"]) + 0.75 * day_range
    up_day = float(last["close"]) > float(last["open"])
    vol_surge_up = (vol_surge_ratio is not None and vol_surge_ratio >= 2.0)
    pocket_pivot_detected = bool(vol_surge_up and closes_high and up_day)

    if vol_surge_ratio is None and cmf_20 is None:
        institutional_conviction = "NEUTRAL_VOLUME_FLOW"
        bias = "NEUTRAL"
    elif (vol_surge_ratio is not None and vol_surge_ratio >= 2.0) and (cmf_20 is not None and cmf_20 > 0.10):
        institutional_conviction = "INSTITUTIONAL_HEAVY_ACCUMULATION"
        bias = "BULLISH"
    elif (vol_surge_ratio is not None and vol_surge_ratio >= 1.5) and (cmf_20 is not None and cmf_20 > 0.0):
        institutional_conviction = "MODERATE_ACCUMULATION"
        bias = "BULLISH"
    elif cmf_20 is not None and cmf_20 < -0.10:
        institutional_conviction = "INSTITUTIONAL_DISTRIBUTION"
        bias = "BEARISH"
    else:
        institutional_conviction = "NEUTRAL_VOLUME_FLOW"
        bias = "NEUTRAL"

    cmf_txt = f"{cmf_20:+.2f}" if cmf_20 is not None else "N/A"
    surge_txt = f"{vol_surge_ratio:.2f}x" if vol_surge_ratio is not None else "N/A"

    return {
        "volume_analytics_status": "COMPUTED",
        "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "spot_price": spot,
        "volume_surge_ratio": vol_surge_ratio,
        "chaikin_money_flow_cmf": cmf_20,
        "on_balance_volume_trend": obv_trend,
        "pocket_pivot_detected": pocket_pivot_detected,
        "institutional_conviction": institutional_conviction,
        "volume_bias": bias,
        "analytics_insight": (f"Volume Surge {surge_txt} of 20-period SMA with CMF at {cmf_txt}. "
                              + ("Pocket Pivot accumulation pattern detected."
                                 if pocket_pivot_detected else "No pocket pivot pattern.")),
    }


if __name__ == "__main__":
    print("=== TESTING VOLUME ANALYTICS & POCKET PIVOT ENGINE ===")
    res = compute_volume_analytics()
    print(json.dumps(res, indent=2))
