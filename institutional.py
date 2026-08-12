"""Institutional FII/DII module - hedge/margin CE logic.

Sources:
- Free JSON API (fii-diidata.mrchartist.com) mirroring NSE's daily
  FII/DII cash + participant-wise F&O open interest reports.
- NSE publishes these every evening (~5:30-7 PM IST).

Logic (Murarkar-style institutional read):
- FII short CALL OI rising near a CE wall = institutions WRITING calls
  (margin/income selling) => supply at that level. This is the "margin CE"
  play - institutions sell CE into strength.
- FII short PUT OI rising near a PE wall = writing puts (support).
- FII long CALL/PUT OI rising = spec buying, weaker signal than writing.
- FII index futures net = the core directional stance.
- Client (retail) net vs FII/Pro net divergence = fade the crowd.
"""
import datetime as dt
import json
import os

import pandas as pd
import requests

API_BASE = "https://fii-diidata.mrchartist.com/api"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _get(endpoint):
    r = requests.get(f"{API_BASE}/{endpoint}", timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_fii_dii_history(limit=60, cache=True):
    """Return daily FII/DII cash + F&O participant OI as a DataFrame."""
    cache_path = os.path.join(DATA_DIR, "fii_dii_history.csv")
    if cache and os.path.exists(cache_path):
        age = dt.datetime.now().timestamp() - os.path.getmtime(cache_path)
        if age < 6 * 3600:
            df = pd.read_csv(cache_path)
            df["date"] = pd.to_datetime(df["date"])
            return df
    rows = _get("history")
    df = pd.DataFrame(rows)
    for c in df.columns:
        if c != "date":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], format="%d-%b-%Y", errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    if cache:
        os.makedirs(DATA_DIR, exist_ok=True)
        df.to_csv(cache_path, index=False)
    return df.tail(limit).reset_index(drop=True)


def _latest_nonzero(df, col):
    for v in df[col].dropna().iloc[::-1]:
        if v != 0:
            return v
    return 0.0


def _last_two_nonzero(df, col):
    """Return (current, previous) latest distinct nonzero values for a column."""
    vals = [v for v in df[col].dropna().iloc[::-1] if v != 0]
    cur = vals[0] if vals else 0.0
    prev = vals[1] if len(vals) > 1 else cur
    return float(cur), float(prev)


def institutional_scan(df=None):
    """Full institutional positioning read from history. Returns dict + text."""
    if df is None:
        df = fetch_fii_dii_history()
    if df.empty:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    def chg(cur, prev):
        a, b = float(cur or 0), float(prev or 0)
        return round(a - b, 1)

    fii_net = float(last.get("fii_net") or 0)
    dii_net = float(last.get("dii_net") or 0)
    fii_5d = float(df["fii_net"].tail(5).sum())
    dii_5d = float(df["dii_net"].tail(5).sum())

    # Index futures stance (evening provisional rows may be 0 -> use latest nonzero)
    fut_net, fut_prev = _last_two_nonzero(df, "fii_idx_fut_net")
    fut_net_chg = round(fut_net - fut_prev, 1)

    # Option writing (margin CE/PE logic) - FII SHORT side
    ce_short, ce_short_prev = _last_two_nonzero(df, "fii_idx_call_short")
    pe_short, pe_short_prev = _last_two_nonzero(df, "fii_idx_put_short")
    ce_short_chg = round(ce_short - ce_short_prev, 1)
    pe_short_chg = round(pe_short - pe_short_prev, 1)

    # Option buying (spec)
    ce_long, ce_long_prev = _last_two_nonzero(df, "fii_idx_call_long")
    pe_long, pe_long_prev = _last_two_nonzero(df, "fii_idx_put_long")
    ce_long_chg = round(ce_long - ce_long_prev, 1)
    pe_long_chg = round(pe_long - pe_long_prev, 1)

    pcr = _latest_nonzero(df, "pcr")
    sentiment = float(last.get("sentiment_score") or 0)

    signals = []
    if fii_net > 0 and fii_5d > 0:
        signals.append("FII buying cash (today + 5d)")
    elif fii_net < 0 and fii_5d < 0:
        signals.append("FII selling cash (today + 5d)")
    elif fii_net > 0:
        signals.append("FII bought cash today")
    else:
        signals.append("FII sold cash today")

    if fut_net > 0:
        signals.append(f"FII index futures NET LONG ({fut_net:,.0f} cnt)")
    elif fut_net < 0:
        signals.append(f"FII index futures NET SHORT ({fut_net:,.0f} cnt)")

    # Margin CE logic: rising short CE = supply being written
    if ce_short_chg > 0:
        signals.append(f"FII WRITING calls (+{ce_short_chg:,.0f} CE short OI) => supply/resistance")
    if pe_short_chg > 0:
        signals.append(f"FII WRITING puts (+{pe_short_chg:,.0f} PE short OI) => support")
    if ce_long_chg > 0:
        signals.append(f"FII BUYING calls (+{ce_long_chg:,.0f} CE long OI) => spec long")
    if pe_long_chg > 0:
        signals.append(f"FII BUYING puts (+{pe_long_chg:,.0f} PE long OI) => hedge/spec")

    if pcr > 0:
        signals.append(f"FII option PCR {pcr:.2f} ({'>1 bullish' if pcr > 1 else '<1 bearish'})")

    # Directional stance: BULLISH/BEARISH/NEUTRAL from real cash + 5d flows
    if fii_net > 0 and fii_5d > 0:
        fii_sentiment = "BULLISH"
    elif fii_net < 0 and fii_5d < 0:
        fii_sentiment = "BEARISH"
    else:
        fii_sentiment = "NEUTRAL"

    # Client vs smart money divergence (if client data present)
    if "client_idx_fut_net" in df.columns:
        cli = float(last.get("client_idx_fut_net") or 0)
        cli_chg = chg(last.get("client_idx_fut_net"), prev.get("client_idx_fut_net"))
        if cli * fut_net < 0 and cli_chg != 0:
            signals.append(f"CROWD vs SMART: Client {cli:,.0f} opposite FII {fut_net:,.0f} => fade client")

    return {
        "date": last["date"].strftime("%Y-%m-%d"),
        "fii_net": fii_net, "dii_net": dii_net,
        "fii_5d": fii_5d, "dii_5d": dii_5d,
        "fut_net": fut_net, "fut_net_chg": fut_net_chg,
        "ce_short": ce_short, "pe_short": pe_short,
        "ce_short_chg": ce_short_chg, "pe_short_chg": pe_short_chg,
        "ce_long": ce_long, "pe_long": pe_long,
        "ce_long_chg": ce_long_chg, "pe_long_chg": pe_long_chg,
        "pcr": pcr, "sentiment": sentiment, "fii_sentiment": fii_sentiment,
        "signals": signals,
    }


def format_scan(s):
    if not s:
        return ["FII/DII data unavailable"]
    lines = [
        f"FII/DII {s['date']} | FII net {s['fii_net']:+,.0f} Cr (5d {s['fii_5d']:+,.0f}) | "
        f"DII net {s['dii_net']:+,.0f} Cr (5d {s['dii_5d']:+,.0f})",
        f"FII idx futures net {s['fut_net']:+,.0f} cnt ({s['fut_net_chg']:+,.0f} chg)",
        f"CE short OI {s['ce_short']:,.0f} ({s['ce_short_chg']:+,.0f}) | "
        f"PE short OI {s['pe_short']:,.0f} ({s['pe_short_chg']:+,.0f})",
        f"CE long OI {s['ce_long']:,.0f} ({s['ce_long_chg']:+,.0f}) | "
        f"PE long OI {s['pe_long']:,.0f} ({s['pe_long_chg']:+,.0f})",
        f"FII PCR {s['pcr']:.2f} | sentiment {s['sentiment']:+.0f}",
    ]
    if s["signals"]:
        lines.append("  * " + " | ".join(s["signals"]))
    return lines


if __name__ == "__main__":
    for line in format_scan(institutional_scan()):
        print(line)
