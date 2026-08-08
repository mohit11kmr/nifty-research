"""Timing intelligence - trade timing, gap scenarios, IV spikes, session logic.

What this gives a trader:
1. GAP scenarios (gap up/down) - fill vs continuation probability from real data
2. Intraday session analysis (opening range, time-of-day) from 15m data
3. IV/VIX spike detection - what happens to Nifty when IV spikes
4. Day-of-week / expiry timing stats
5. Indian market session timing rules (ORB, power hours)
"""
import datetime as dt
import time

import numpy as np
import pandas as pd
import requests

YH = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"}
NSE_OPEN = dt.time(9, 15)
NSE_CLOSE = dt.time(15, 30)


# ---------------------------------------------------------------- gaps
def analyze_gaps(df, min_rows=60):
    """Gap up/down/fill stats from daily OHLC data.

    gap% = (open_t - close_{t-1})/close_{t-1}*100
    filled = day's low <= prev close (up gap) or day's high >= prev close (down gap)
    """
    if len(df) < min_rows:
        return None
    close_prev = df["close"].shift(1)
    gap_pct = (df["open"] - close_prev) / close_prev * 100
    is_gap_up = gap_pct > 0.2
    is_gap_dn = gap_pct < -0.2

    filled = pd.Series(np.nan, index=df.index, dtype="object")
    filled.loc[is_gap_up] = (df["low"] <= close_prev).loc[is_gap_up]
    filled.loc[is_gap_dn] = (df["high"] >= close_prev).loc[is_gap_dn]

    next_ret = df["close"].pct_change().shift(-1) * 100
    gap_ret = df["close"].pct_change() * 100

    stats = {}
    for label, mask, kind in [("GAP_UP", is_gap_up, "up"), ("GAP_DOWN", is_gap_dn, "down")]:
        m = mask.fillna(False)
        n = int(m.sum())
        if n < 5:
            stats[label] = {"count": n, "note": "too few samples"}
            continue
        fill_vals = filled[m]
        fill_rate = fill_vals.astype(float).mean() * 100
        nxt = next_ret[m]
        stats[label] = {
            "count": n,
            "avg_gap_pct": round(gap_pct[m].mean(), 2),
            "fill_rate_pct": round(fill_rate, 1),
            "next_day_avg_ret_pct": round(nxt.mean(), 2),
            "next_day_win_rate_pct": round((nxt > 0).mean() * 100, 1),
            "continuation_pct": round(100 - fill_rate, 1),
        }

    # Big gap check (>= 0.8%)
    big_up = (gap_pct >= 0.8).fillna(False)
    big_dn = (gap_pct <= -0.8).fillna(False)
    for label, m in [("BIG_GAP_UP", big_up), ("BIG_GAP_DOWN", big_dn)]:
        n = int(m.sum())
        if n >= 5:
            nxt = next_ret[m]
            stats[label] = {
                "count": n,
                "avg_gap_pct": round(gap_pct[m].mean(), 2),
                "fill_rate_pct": round(filled[m].astype(float).mean() * 100, 1),
                "next_day_avg_ret_pct": round(nxt.mean(), 2),
                "next_day_win_rate_pct": round((nxt > 0).mean() * 100, 1),
            }
    return stats


def interpret_gaps(gaps):
    """Trader-readable gap scenario reasoning."""
    if not gaps:
        return []
    lines = []
    for key in ["GAP_UP", "GAP_DOWN", "BIG_GAP_UP", "BIG_GAP_DOWN"]:
        g = gaps.get(key)
        if not g or "note" in g:
            continue
        lines.append(
            f"{key}: avg {g['avg_gap_pct']:+.1f}%, fill rate {g['fill_rate_pct']:.0f}%, "
            f"next-day win {g['next_day_win_rate_pct']:.0f}% (avg {g['next_day_avg_ret_pct']:+.2f}%), n={g['count']}")
    return lines


# ---------------------------------------------------------------- intraday
def fetch_intraday(interval="15m", range_="10d"):
    """Fetch NIFTY intraday bars from Yahoo. Returns DataFrame or None."""
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval={interval}&range={range_}",
            headers=YH, timeout=25)
        d = r.json()["chart"]["result"][0]
        ts = d["timestamp"]
        q = d["indicators"]["quote"][0]
        rows = []
        for i, t in enumerate(ts):
            try:
                rows.append({
                    "datetime": pd.to_datetime(t, unit="s", utc=True).tz_convert("Asia/Kolkata"),
                    "open": q["open"][i], "high": q["high"][i],
                    "low": q["low"][i], "close": q["close"][i],
                    "volume": q["volume"][i] or 0,
                })
            except (TypeError, IndexError):
                continue
        df = pd.DataFrame(rows).dropna(subset=["open", "close"])
        return df
    except Exception:  # noqa: BLE001
        return None


def intraday_analysis(intra):
    """Opening range breakout + session position + time-of-day from 15m bars."""
    if intra is None or intra.empty:
        return None
    intra = intra.set_index("datetime").sort_index()
    res = {}
    # Group by date
    for day, grp in intra.groupby(intra.index.date):
        grp = grp.dropna()
        if len(grp) < 5:
            continue
        first = grp.iloc[0]
        # Opening range = first 15-30 min (first 2 bars)
        or_hi = grp.iloc[:2]["high"].max()
        or_lo = grp.iloc[:2]["low"].min()
        last = grp.iloc[-1]
        # VWAP of the day (fallback to simple typical-price avg if volume = 0)
        typ = (grp["high"] + grp["low"] + grp["close"]) / 3
        vol_sum = grp["volume"].sum()
        if vol_sum and vol_sum > 0:
            vwap = (typ * grp["volume"]).sum() / vol_sum
        else:
            vwap = typ.mean()

        res[str(day)] = {
            "open": round(first["open"], 1),
            "close": round(last["close"], 1),
            "day_high": round(grp["high"].max(), 1),
            "day_low": round(grp["low"].min(), 1),
            "or_high": round(or_hi, 1),
            "or_low": round(or_lo, 1),
            "vwap": round(vwap, 1) if not np.isnan(vwap) else None,
            "session_pct_chg": round((last["close"] / first["open"] - 1) * 100, 2),
            "range_pct": round((grp["high"].max() - grp["low"].min()) / first["open"] * 100, 2),
            "broke_or_up": bool(last["close"] > or_hi),
            "broke_or_dn": bool(last["close"] < or_lo),
            "closing_vs_vwap": round((last["close"] / vwap - 1) * 100, 2) if vwap and not np.isnan(vwap) else None,
        }
    return res


def trade_timing_logic(day_date):
    """Indian session timing rules based on current date/time."""
    lines = []
    lines.append("Session: 09:15-15:30 IST | Best entry windows:")
    lines.append("  - 09:15-09:45: Opening Range Breakout (ORB) - trade first 15-min range break")
    lines.append("  - 09:15-10:30: High liquidity + high volatility (best for options buying)")
    lines.append("  - 13:00-14:30: Lunch lull, avoid fresh entries")
    lines.append("  - 14:30-15:15: Power hour, directional push before close")
    lines.append("  - 15:15-15:30: Avoid new positions, square off")
    dow = day_date.weekday()
    if dow == 3:  # Thursday
        lines.append("  -> TODAY is WEEKLY EXPIRY (Thu): high OI churn, big IV swings - reduce size")
    return lines


# ---------------------------------------------------------------- IV spike
def fetch_vix():
    """India VIX + US VIX daily closes from Yahoo. Returns (india_df, us_df) or Nones."""
    out = []
    for ticker, tag in [("^INDIAVIX", "india"), ("^VIX", "us")]:
        try:
            r = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y",
                headers=YH, timeout=25)
            d = r.json()["chart"]["result"][0]
            ts = d["timestamp"]
            q = d["indicators"]["quote"][0]
            rows = [{"date": pd.to_datetime(t, unit="s").date(), "vix": q["close"][i]}
                    for i, t in enumerate(ts) if q["close"][i] is not None]
            out.append((tag, pd.DataFrame(rows)))
        except Exception:  # noqa: BLE001
            out.append((tag, None))
        time.sleep(0.3)
    return dict(out)


def analyze_iv_spike(vix_df, nifty_df, spike_thresh=0.20):
    """Detect IV spikes and measure Nifty reaction after them."""
    if vix_df is None or vix_df.empty:
        return None
    v = vix_df.sort_values("date").reset_index(drop=True)
    v["date"] = pd.to_datetime(v["date"]).dt.normalize()
    v["vix_chg"] = v["vix"].pct_change() * 100
    v["vix_pctile"] = v["vix"].rolling(60, min_periods=30).rank(pct=True) * 100

    spikes = v[v["vix_chg"] > spike_thresh * 100].copy()
    last = v.iloc[-1]

    # Nifty forward returns after spikes (align on dates)
    res = {"last_vix": round(float(last["vix"]), 1),
           "last_vix_chg_pct": round(float(last["vix_chg"]), 2) if not np.isnan(last["vix_chg"]) else None,
           "vix_percentile": round(float(last["vix_pctile"]), 0) if not np.isnan(last["vix_pctile"]) else None}
    res["spike_count_1y"] = int(len(spikes))

    if nifty_df is not None and not nifty_df.empty and len(spikes) >= 3:
        nif = nifty_df.copy()
        nif["date"] = pd.to_datetime(nif["date"]).dt.normalize()
        fwd = []
        for _, s in spikes.iterrows():
            idx = nif.index[nif["date"] == s["date"]]
            if idx.empty:
                continue
            i = idx[0]
            if i + 5 < len(nif):
                r3 = (nif["close"].iloc[min(i + 3, len(nif) - 1)] / nif["close"].iloc[i] - 1) * 100
                r5 = (nif["close"].iloc[min(i + 5, len(nif) - 1)] / nif["close"].iloc[i] - 1) * 100
                fwd.append((r3, r5))
        if fwd:
            res["nifty_after_spike_3d"] = round(float(np.mean([f[0] for f in fwd])), 2)
            res["nifty_after_spike_5d"] = round(float(np.mean([f[1] for f in fwd])), 2)
            res["nifty_after_spike_win_3d"] = round((np.array([f[0] for f in fwd]) > 0).mean() * 100, 0)
    return res


def interpret_iv_spike(ana):
    """Reasoning about current IV state and spike history."""
    if not ana:
        return []
    lines = []
    lines.append(f"India VIX {ana['last_vix']} (change {ana.get('last_vix_chg_pct', 'n/a')}%), "
                 f"percentile {ana.get('vix_percentile', 'n/a')}%")
    if ana.get("vix_percentile") is not None:
        p = ana["vix_percentile"]
        if p > 80:
            lines.append("VIX at extreme high => IV crush risk HIGH, avoid buying options now, prefer selling/hedging")
        elif p > 60:
            lines.append("VIX elevated => premium expensive, expect choppy market")
        elif p < 20:
            lines.append("VIX low => premium cheap, options BUYING favorable (good delta risk)")
        else:
            lines.append("VIX mid => normal premium regime")
    if ana.get("spike_count_1y"):
        lines.append(f"{ana['spike_count_1y']} IV spikes in last year; "
                     f"avg Nifty 3d after spike: {ana.get('nifty_after_spike_3d', 'n/a')}%, "
                     f"win {ana.get('nifty_after_spike_win_3d', 'n/a')}%")
    return lines


# ---------------------------------------------------------------- week timing
def day_of_week_stats(df):
    """Which weekdays perform best - for expiry/timing planning."""
    if len(df) < 80:
        return None
    df = df.copy()
    df["dow"] = df.index.dayofweek
    rows = []
    names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for d, grp in df.groupby("dow"):
        if int(d) not in range(5):
            continue
        ret = grp["close"].pct_change() * 100
        rows.append({
            "day": names[int(d)],
            "avg_ret_pct": round(ret.mean(), 3),
            "win_rate_pct": round((ret > 0).mean() * 100, 1),
            "n": len(grp),
        })
    return pd.DataFrame(rows)


def interpret_dow(stats):
    if stats is None or stats.empty:
        return []
    lines = []
    best = stats.loc[stats["avg_ret_pct"].idxmax()]
    worst = stats.loc[stats["avg_ret_pct"].idxmin()]
    lines.append(f"Best day: {best['day']} (avg {best['avg_ret_pct']:+.2f}%, win {best['win_rate_pct']:.0f}%)")
    lines.append(f"Weakest day: {worst['day']} (avg {worst['avg_ret_pct']:+.2f}%, win {worst['win_rate_pct']:.0f}%)")
    return lines


# ---------------------------------------------------------------- timing votes
def timing_votes(df, gaps, dow_stats, iv_ana, today_dow=None):
    """Convert timing stats into directional votes for the brain.

    Returns a list of dicts: {signal, dir(+1/-1/0), weight, note} plus an
    aggregated score. Values are calibrated from the backtested stats so a
    gap/I.V.-event that historically leads to an edge actually shifts the verdict.
    """
    votes = []
    close_prev = df["close"].shift(1).iloc[-1]
    gap_pct = (df["open"].iloc[-1] - close_prev) / close_prev * 100 if close_prev else 0.0

    if gaps and abs(gap_pct) >= 0.8:
        # Big gap TODAY: next-day stats measured directly from history.
        if gap_pct <= -0.8:
            big_dn = gaps.get("BIG_GAP_DOWN")
            if big_dn and "count" in big_dn and big_dn["next_day_win_rate_pct"] >= 60:
                votes.append({"signal": "big_gap_down", "dir": 1, "weight": 1.5,
                              "note": f"BIG_GAP_DOWN today - historically {big_dn['next_day_win_rate_pct']:.0f}% "
                                      f"next-day win (avg {big_dn['next_day_avg_ret_pct']:+.2f}%) => bounce bias"})
            else:
                votes.append({"signal": "big_gap_down", "dir": 1, "weight": 0.7,
                              "note": "Large gap down today - historical next-day bounce edge, buy dips"})
        else:
            big_up = gaps.get("BIG_GAP_UP")
            if big_up and "count" in big_up and big_up["next_day_win_rate_pct"] >= 55:
                votes.append({"signal": "big_gap_up", "dir": 1, "weight": 0.7,
                              "note": f"BIG_GAP_UP today - {big_up['next_day_win_rate_pct']:.0f}% next-day win "
                                      f"(but {big_up['fill_rate_pct']:.0f}% fill => chase risk, use pullback entry)"})
            else:
                votes.append({"signal": "big_gap_up", "dir": 0, "weight": 0.5,
                              "note": "Large gap up today - watch for gap-fill risk before chasing"})

    if dow_stats is not None and not dow_stats.empty and today_dow is not None:
        row = dow_stats[dow_stats["day"] == today_dow]
        if not row.empty:
            r = row.iloc[0]
            if r["avg_ret_pct"] > 0.03 and r["win_rate_pct"] >= 52:
                votes.append({"signal": "dow", "dir": 1, "weight": 0.5,
                              "note": f"{r['day']} historically favorable "
                                      f"(avg {r['avg_ret_pct']:+.2f}%, win {r['win_rate_pct']:.0f}%)"})
            elif r["win_rate_pct"] < 46:
                votes.append({"signal": "dow", "dir": -1, "weight": 0.6,
                              "note": f"{r['day']} historically weak (win {r['win_rate_pct']:.0f}%) "
                                      f"=> reduce longs / expiry risk"})

    if iv_ana:
        p = iv_ana.get("vix_percentile")
        if p is not None and p > 80:
            votes.append({"signal": "iv", "dir": -1, "weight": 1.0,
                          "note": "VIX extreme high => IV crush risk, expect mean-reversion down"})
        if iv_ana.get("nifty_after_spike_3d") is not None and iv_ana["spike_count_1y"] >= 3:
            w = iv_ana.get("nifty_after_spike_win_3d", 50)
            if w < 40 and iv_ana["nifty_after_spike_3d"] < 0:
                votes.append({"signal": "iv_spike_aftermath", "dir": -1, "weight": 1.0,
                              "note": f"Recent IV spikes led to {iv_ana['nifty_after_spike_3d']:+.2f}% "
                                      f"Nifty (win {w:.0f}%) in 3d => post-spike drift is bearish"})

    total_w = max(sum(abs(v["weight"]) for v in votes), 1e-9)
    score = sum(v["dir"] * v["weight"] for v in votes) / total_w
    return votes, round(score, 2)
