"""Technical indicators - pure pandas/numpy, no TA-Lib dependency."""
import numpy as np
import pandas as pd


def sma(s, n):
    return s.rolling(n, min_periods=n).mean()


def ema(s, n):
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    r = 100 - (100 / (1 + rs))
    return r.fillna(50.0)


def macd(close, fast=12, slow=26, signal=9):
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger(close, n=20, k=2.0):
    mid = sma(close, n)
    std = close.rolling(n, min_periods=n).std()
    return mid + k * std, mid, mid - k * std


def adx(high, low, close, period=14):
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean(), plus_di, minus_di


def atr(high, low, close, period=14):
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def roc(close, n=10):
    return close.pct_change(n) * 100


def stochastic(high, low, close, n=14):
    hh = high.rolling(n, min_periods=n).max()
    ll = low.rolling(n, min_periods=n).min()
    k = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    d = k.rolling(3, min_periods=3).mean()
    return k, d


def volume_profile_bias(close, volume, n=20):
    """Price-volume: rising price on rising volume => conviction."""
    vol_sma = sma(volume, n)
    vol_expand = volume > 1.3 * vol_sma
    return vol_expand


def supertrend(high, low, close, period=10, mult=3.0):
    """Returns trend direction: +1 (up) / -1 (down)."""
    a = atr(high, low, close, period)
    hl2 = (high + low) / 2
    upper = hl2 + mult * a
    lower = hl2 - mult * a
    st = pd.Series(np.nan, index=close.index)
    dirn = pd.Series(1, index=close.index, dtype=float)
    upper = np.array(upper, copy=True)
    lower = np.array(lower, copy=True)
    close_n = np.array(close, copy=True)
    st_n = np.array(st, copy=True)
    dir_n = np.array(dirn, copy=True)
    n = len(close)
    for i in range(1, n):
        if close_n[i] > upper[i - 1]:
            dir_n[i] = 1
        elif close_n[i] < lower[i - 1]:
            dir_n[i] = -1
        else:
            dir_n[i] = dir_n[i - 1]
            if dir_n[i] == 1 and lower[i] < lower[i - 1]:
                lower[i] = lower[i - 1]
            if dir_n[i] == -1 and upper[i] > upper[i - 1]:
                upper[i] = upper[i - 1]
        if dir_n[i] == 1:
            st_n[i] = lower[i]
        else:
            st_n[i] = upper[i]
    return pd.Series(dir_n, index=close.index), pd.Series(st_n, index=close.index)


def add_all_indicators(df):
    """Attach every indicator column to a OHLCV dataframe (in place)."""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    v = df["volume"] if "volume" in df else pd.Series(0, index=df.index)

    df["sma20"] = sma(c, 20)
    df["sma50"] = sma(c, 50)
    df["sma200"] = sma(c, 200)
    df["ema9"] = ema(c, 9)
    df["ema21"] = ema(c, 21)
    df["rsi14"] = rsi(c)
    macd_l, sig, hist = macd(c)
    df["macd"] = macd_l
    df["macd_signal"] = sig
    df["macd_hist"] = hist
    ub, mb, lb = bollinger(c)
    df["bb_upper"] = ub
    df["bb_mid"] = mb
    df["bb_lower"] = lb
    adx_, pdi, mdi = adx(h, l, c)
    df["adx"] = adx_
    df["pdi"] = pdi
    df["mdi"] = mdi
    df["atr14"] = atr(h, l, c)
    df["roc10"] = roc(c)
    k, d = stochastic(h, l, c)
    df["stoch_k"] = k
    df["stoch_d"] = d
    df["supertrend"] = supertrend(h, l, c)[0]
    df["vol_expand"] = volume_profile_bias(c, v)
    df["vwap20"] = (c * v).rolling(20, min_periods=20).sum() / v.rolling(20, min_periods=20).sum().replace(0, np.nan)
    df["day_pct"] = c.pct_change() * 100
    return df
