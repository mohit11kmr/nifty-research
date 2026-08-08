"""Strategy library - popular options-buying logics converted to tradable rules.

Each strategy returns a Signal Series: +1 => buy CALL, -1 => buy PUT, 0 => no trade.
Signals are generated on bar close (next bar open entry in backtest).
"""
import numpy as np
import pandas as pd

SIGNAL_CALL = 1
SIGNAL_PUT = -1
SIGNAL_NONE = 0


def _ensure_sma(df, n):
    col = f"sma{n}"
    if col not in df.columns:
        df[col] = df["close"].rolling(n, min_periods=n).mean()
    return df[col]


def _ensure_roc(df, n):
    col = f"roc{n}"
    if col not in df.columns:
        df[col] = df["close"].pct_change(n) * 100
    return df[col]


def _spread(s):
    return s.rolling(3, min_periods=3).mean()


def strat_trend_sma(df, fast=20, slow=50, adx_thresh=25, use_adx=True):
    """Bullish: close>SMA(fast)>SMA(slow) & ADX strong. Bearish mirror."""
    f = _ensure_sma(df, fast)
    s = _ensure_sma(df, slow)
    cond_call = (df["close"] > f) & (f > s)
    cond_put = (df["close"] < f) & (f < s)
    if use_adx:
        cond_call &= df["adx"] > adx_thresh
        cond_put &= df["adx"] > adx_thresh
    sig = np.where(cond_call, SIGNAL_CALL, np.where(cond_put, SIGNAL_PUT, SIGNAL_NONE))
    return pd.Series(sig, index=df.index)


def strat_rsi_mean_reversion(df, low=30, high=70):
    """RSI oversold => expect bounce buy CALL; overbought => buy PUT."""
    cond_call = df["rsi14"] < low
    cond_put = df["rsi14"] > high
    return pd.Series(np.where(cond_call, SIGNAL_CALL, np.where(cond_put, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


def strat_macd_cross(df, require_hist=True):
    """MACD line crosses above signal => CALL; below => PUT."""
    cross_up = (df["macd"] > df["macd_signal"]) & (df["macd"].shift(1) <= df["macd_signal"].shift(1))
    cross_dn = (df["macd"] < df["macd_signal"]) & (df["macd"].shift(1) >= df["macd_signal"].shift(1))
    if require_hist:
        cross_up &= df["macd_hist"] > 0
        cross_dn &= df["macd_hist"] < 0
    return pd.Series(np.where(cross_up, SIGNAL_CALL, np.where(cross_dn, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


def strat_vwap(df):
    """Price above VWAP => CALL; below => PUT."""
    cond_call = df["close"] > df["vwap20"]
    cond_put = df["close"] < df["vwap20"]
    return pd.Series(np.where(cond_call, SIGNAL_CALL, np.where(cond_put, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


def strat_bollinger_mean_rev(df, bands=2.0):
    """Touch upper BB => PUT (mean reversion); lower BB => CALL."""
    cond_call = df["close"] < df["bb_lower"]
    cond_put = df["close"] > df["bb_upper"]
    return pd.Series(np.where(cond_call, SIGNAL_CALL, np.where(cond_put, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


def strat_breakout(df, lookback=20):
    """Close makes new N-day high => CALL; new low => PUT."""
    hi = df["close"].rolling(lookback, min_periods=lookback).max().shift(1)
    lo = df["close"].rolling(lookback, min_periods=lookback).min().shift(1)
    cond_call = df["close"] > hi
    cond_put = df["close"] < lo
    return pd.Series(np.where(cond_call, SIGNAL_CALL, np.where(cond_put, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


def strat_supertrend(df, require_adx=False, adx_thresh=20):
    """SuperTrend +1 => CALL; -1 => PUT (optionally only when ADX confirms)."""
    cond_call = df["supertrend"] == 1
    cond_put = df["supertrend"] == -1
    if require_adx:
        cond_call &= df["adx"] > adx_thresh
        cond_put &= df["adx"] > adx_thresh
    return pd.Series(np.where(cond_call, SIGNAL_CALL, np.where(cond_put, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


def strat_donchian_band(df, lookback=20):
    """Close above rolling high, holds = CALL; below rolling low = PUT."""
    hi = df["high"].rolling(lookback, min_periods=lookback).max().shift(1)
    lo = df["low"].rolling(lookback, min_periods=lookback).min().shift(1)
    cond_call = df["close"] > hi
    cond_put = df["close"] < lo
    return pd.Series(np.where(cond_call, SIGNAL_CALL, np.where(cond_put, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


def strat_triple_screen(df, adx_thresh=25, rsi_low=40, rsi_high=60):
    """Trend filter (ADX) + RSI pullback entry - intraday-style options logic."""
    trend_up = df["pdi"] > df["mdi"]
    trend_dn = df["pdi"] < df["mdi"]
    strong = df["adx"] > adx_thresh
    cond_call = trend_up & strong & (df["rsi14"] < rsi_low)
    cond_put = trend_dn & strong & (df["rsi14"] > rsi_high)
    return pd.Series(np.where(cond_call, SIGNAL_CALL, np.where(cond_put, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


def strat_stoch_cross(df, low=20, high=80):
    """Stochastic K crosses above D in oversold => CALL; below in overbought => PUT."""
    k_up = (df["stoch_k"] > df["stoch_d"]) & (df["stoch_k"].shift(1) <= df["stoch_d"].shift(1)) & (df["stoch_k"] < low + 10)
    k_dn = (df["stoch_k"] < df["stoch_d"]) & (df["stoch_k"].shift(1) >= df["stoch_d"].shift(1)) & (df["stoch_k"] > high - 10)
    return pd.Series(np.where(k_up, SIGNAL_CALL, np.where(k_dn, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


def strat_momentum_roc(df, n=10, thresh=2.0):
    """Strong positive ROC => CALL momentum; strong negative => PUT."""
    roc_col = _ensure_roc(df, n)
    cond_call = roc_col > thresh
    cond_put = roc_col < -thresh
    return pd.Series(np.where(cond_call, SIGNAL_CALL, np.where(cond_put, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


def strat_volume_confirmed_trend(df, fast=20, slow=50):
    """Trend + volume expansion (sabse popular youtuber logic)."""
    base = strat_trend_sma(df, fast, slow, adx_thresh=20, use_adx=False)
    confirmed = base.copy()
    confirmed[df["vol_expand"] == False] = SIGNAL_NONE  # noqa: E712
    return confirmed


def strat_golden_cross(df, fast=20, slow=50):
    """SMA fast crosses above slow => CALL (golden cross); below => death cross PUT."""
    f = _ensure_sma(df, fast)
    s = _ensure_sma(df, slow)
    cross_up = (f > s) & (f.shift(1) <= s.shift(1))
    cross_dn = (f < s) & (f.shift(1) >= s.shift(1))
    return pd.Series(np.where(cross_up, SIGNAL_CALL, np.where(cross_dn, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


def _vwap_band(df, n=20, mult=2.0):
    """Typical-price volume-weighted band + standard deviations."""
    typ = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].fillna(0)
    vwap = (typ * vol).rolling(n, min_periods=n).sum() / vol.rolling(n, min_periods=n).sum().replace(0, np.nan)
    # rolling sd of (price - vwap)
    diff = (df["close"] - vwap)
    sd = diff.rolling(n, min_periods=n).std()
    return vwap, vwap + mult * sd, vwap - mult * sd


def strat_vwap_band(df, n=20, mult=2.0):
    """VWAP deviation: price re-touches lower VWAP band from above => CALL (bounce).
    Price over-extends above upper band => PUT (mean reversion)."""
    vwap, up, low = _vwap_band(df, n, mult)
    # buy zone: close dips below lower band (premium cheap) while trend still above sma50
    dip_below = df["close"] < low
    over_extend = df["close"] > up
    cond_call = dip_below & (df["close"] > df["sma50"])
    cond_put = over_extend & (df["close"] < df["sma50"])
    return pd.Series(np.where(cond_call, SIGNAL_CALL, np.where(cond_put, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


def strat_vwap_trend(df, n=20, mult=1.0):
    """VWAP anchor trend: price sustained ABOVE vwap band top => CALL momentum.
    Below band bottom => PUT momentum."""
    vwap, up, low = _vwap_band(df, n, mult)
    cond_call = df["close"] > up
    cond_put = df["close"] < low
    return pd.Series(np.where(cond_call, SIGNAL_CALL, np.where(cond_put, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


def strat_global_sentiment(df, sent_df=None, thresh=2):
    """Global risk-on/off driven strategy. Needs sentiment series aligned to df index."""
    if sent_df is None:
        return pd.Series(SIGNAL_NONE, index=df.index)
    s = sent_df.reindex(df.index).fillna(0)
    return pd.Series(np.where(s >= thresh, SIGNAL_CALL, np.where(s <= -thresh, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


def strat_fii_dii(df, fii_series=None, thresh=1500):
    """FII/DII net flow strategy: strong net buying => CALL, selling => PUT."""
    if fii_series is None:
        return pd.Series(SIGNAL_NONE, index=df.index)
    s = fii_series.reindex(df.index).fillna(0)
    return pd.Series(np.where(s >= thresh, SIGNAL_CALL, np.where(s <= -thresh, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


def strat_gamma_buy(df, n=20):
    """Mean-reversion calibrated by VWAP bands + RSI zone (gamma-friendly entry)."""
    vwap, up, low = _vwap_band(df, n, 1.5)
    rsi = df["rsi14"]
    cond_call = (df["close"] < vwap) & (rsi < 45)
    cond_put = (df["close"] > vwap) & (rsi > 55)
    return pd.Series(np.where(cond_call, SIGNAL_CALL, np.where(cond_put, SIGNAL_PUT, SIGNAL_NONE)), index=df.index)


ALL_STRATEGIES = {
    "trend_sma": strat_trend_sma,
    "rsi_meanrev": strat_rsi_mean_reversion,
    "macd_cross": strat_macd_cross,
    "vwap": strat_vwap,
    "bollinger": strat_bollinger_mean_rev,
    "breakout": strat_breakout,
    "supertrend": strat_supertrend,
    "donchian": strat_donchian_band,
    "triple_screen": strat_triple_screen,
    "stoch_cross": strat_stoch_cross,
    "momentum_roc": strat_momentum_roc,
    "volume_trend": strat_volume_confirmed_trend,
    "golden_cross": strat_golden_cross,
    "vwap_band": strat_vwap_band,
    "vwap_trend": strat_vwap_trend,
    "gamma_buy": strat_gamma_buy,
}


def build_param_grid():
    """~1000+ strategy parameter combinations for the batch research run."""
    grid = []
    for fast, slow in [(5, 20), (5, 50), (10, 30), (10, 50), (10, 100), (20, 50), (20, 100), (20, 200), (30, 60), (50, 200), (5, 100), (10, 200)]:
        for adx in [0, 20, 25, 30]:
            grid.append({"name": "trend_sma", "params": {"fast": fast, "slow": slow, "adx_thresh": adx, "use_adx": adx > 0}})
    for low, high in [(20, 80), (25, 75), (30, 70), (35, 65), (40, 60), (45, 55), (15, 85)]:
        grid.append({"name": "rsi_meanrev", "params": {"low": low, "high": high}})
        grid.append({"name": "stoch_cross", "params": {"low": low, "high": high}})
    grid.append({"name": "macd_cross", "params": {"require_hist": True}})
    grid.append({"name": "macd_cross", "params": {"require_hist": False}})
    grid.append({"name": "vwap", "params": {}})
    for bands in [1.5, 1.8, 2.0, 2.2, 2.5, 2.8, 3.0]:
        grid.append({"name": "bollinger", "params": {"bands": bands}})
    for lb in [5, 8, 10, 12, 15, 18, 20, 25, 30, 35, 40, 45, 50, 55, 60]:
        grid.append({"name": "breakout", "params": {"lookback": lb}})
        grid.append({"name": "donchian", "params": {"lookback": lb}})
        for thresh in [1.0, 1.5, 2.0, 2.5, 3.0]:
            grid.append({"name": "momentum_roc", "params": {"n": lb, "thresh": thresh}})
    for require, adx in [(False, 0), (True, 20), (True, 25), (True, 30)]:
        grid.append({"name": "supertrend", "params": {"require_adx": require, "adx_thresh": adx}})
    for adx, lo, hi in [(20, 30, 70), (20, 40, 60), (25, 35, 65), (25, 30, 70), (30, 40, 60), (30, 25, 75)]:
        grid.append({"name": "triple_screen", "params": {"adx_thresh": adx, "rsi_low": lo, "rsi_high": hi}})
    for fast, slow in [(5, 20), (5, 50), (10, 30), (10, 50), (10, 100), (20, 50), (20, 100), (20, 200)]:
        grid.append({"name": "golden_cross", "params": {"fast": fast, "slow": slow}})
    grid.append({"name": "volume_trend", "params": {"fast": 20, "slow": 50}})
    for n in [15, 20, 30]:
        for mult in [1.0, 1.5, 2.0, 2.5]:
            grid.append({"name": "vwap_band", "params": {"n": n, "mult": mult}})
            grid.append({"name": "vwap_trend", "params": {"n": n, "mult": mult}})
            grid.append({"name": "gamma_buy", "params": {"n": n}})
    return grid


def build_grid_with_holds():
    """Expand every config across multiple holding periods => 1000+ backtests."""
    base = build_param_grid()
    out = []
    for cfg in base:
        for hold in [1, 2, 3, 5, 7, 10]:
            c = {"name": cfg["name"], "params": dict(cfg["params"]), "hold": hold}
            out.append(c)
    return out
