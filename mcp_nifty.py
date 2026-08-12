"""Nifty Research Trading MCP Server.

Exposes the entire quant platform (regime filter, OI intel, gamma flip,
institutional flow, precision signals, capital guard, stock flow, ML context,
broker status) as MCP tools so opencode can reason over live project data
without shelling out to python -c one-liners.

Run via stdio (opencode launches it):
    .venv/bin/python mcp_nifty.py

Every tool reads from the data/ cache first - never re-downloads.
"""
import os
import sys
import json
import glob
import sqlite3
import datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("nifty-research")

NIFTY_EXPIRY_WEEKDAY = 3  # Thursday


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    import numpy as np
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return [_jsonable(v) for v in obj.tolist()]
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dt.datetime):
        return obj.strftime("%d %b %Y %H:%M IST")
    return str(obj)


def _safe(fn, *args, **kwargs):
    try:
        return {"ok": True, "data": _jsonable(fn(*args, **kwargs))}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _latest_chain_csv():
    snaps = sorted(glob.glob(os.path.join("data", "oi_snapshots", "NIFTY_*.csv")))
    if not snaps:
        return None
    import pandas as pd
    df = pd.read_csv(snaps[-1])
    return df


def _latest_chain_spot():
    snaps = sorted(glob.glob(os.path.join("data", "oi_snapshots", "oi_NIFTY_*.json")))
    if snaps:
        try:
            with open(snaps[-1]) as f:
                meta = json.load(f).get("_meta", {})
            if meta.get("spot"):
                return float(meta["spot"])
        except Exception:
            pass
    return None


def _spot_fallback():
    import pandas as pd
    if os.path.exists(os.path.join("data", "nifty_history.csv")):
        df = pd.read_csv(os.path.join("data", "nifty_history.csv"))
        return float(df["close"].iloc[-1])
    return None


def _current_spot():
    return _latest_chain_spot() or _spot_fallback()


def _nifty_indicator_df():
    import pandas as pd
    import indicators
    path = os.path.join("data", "nifty_history.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return indicators.add_all_indicators(df)


def _read_vix():
    import pandas as pd
    path = os.path.join("data", "india_vix.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    return df.iloc[-1]["close"]


def _expiry_status():
    today = dt.date.today()
    days_ahead = (NIFTY_EXPIRY_WEEKDAY - today.weekday()) % 7
    expiry = today + dt.timedelta(days=days_ahead)
    return {
        "today": today.isoformat(),
        "weekday": today.strftime("%A"),
        "days_to_expiry": days_ahead,
        "is_expiry_day": days_ahead == 0,
        "next_expiry": expiry.isoformat(),
    }


@mcp.tool()
def market_snapshot() -> dict:
    """One-call full market picture: regime gate, VIX zone, technicals, option
    chain (PCR/max pain/walls/Murarkar), gamma flip, institutional flow and
    expiry status. Use this FIRST for any 'aaj ka NIFTY setup' question."""
    out = {}
    out["regime"] = _safe(lambda: __import__("regime_filter").trade_plan())
    out["expiry"] = _expiry_status()
    out["spot"] = _current_spot()

    vix = _read_vix()
    if vix is not None:
        zone = (
            "CHEAP" if vix < 12 else
            "NORMAL" if vix < 16 else
            "RICH" if vix < 20 else
            "HIGH" if vix < 25 else "PANIC"
        )
        out["vix"] = {"level": round(float(vix), 2), "zone": zone}

    chain = _latest_chain_csv()
    spot = out["spot"]
    if chain is not None and spot:
        out["chain"] = {
            "intel": _safe(lambda: __import__("oi_intel").pcr_and_pain(chain, spot=spot)),
            "walls": _safe(lambda: __import__("oi_intel").oi_walls(chain, spot=spot)),
            "murarkar": _safe(lambda: __import__("oi_intel").murarkar_matrix(chain, spot)),
        }
        out["gamma"] = _safe(lambda: __import__("gamma_flip").calculate_gamma_exposure(chain, spot=spot))

    out["fii_dii"] = _safe(lambda: __import__("institutional").institutional_scan())

    df = _nifty_indicator_df()
    if df is not None:
        out["technicals"] = _safe(lambda: __import__("market_brain").analyze_market(df))
    return out


@mcp.tool()
def regime_trade_plan(capital: float = None) -> dict:
    """Regime gate + trade plan (TREND_HV/LV, RANGE_HV/LV, VIX premium zone,
    size multiplier, allowed/avoided strategies). RANGE_LV means NO TRADE."""
    return _safe(lambda: __import__("regime_filter").trade_plan(capital=capital))


@mcp.tool()
def vix_intel() -> dict:
    """India VIX level, premium zone (CHEAP/NORMAL/RICH/HIGH/PANIC), percentile
    and expected daily move. Decides BUY vs SELL options strategy."""
    return _safe(lambda: __import__("regime_filter").trade_plan()["vix"])


@mcp.tool()
def option_chain_intel() -> dict:
    """Latest cached NIFTY option chain: PCR, max pain, top CE/PE OI walls and
    Murarkar OI build-up matrix (institutional positioning read)."""
    chain = _latest_chain_csv()
    if chain is None:
        return {"ok": False, "error": "No option chain snapshot in data/oi_snapshots"}
    spot = _current_spot()
    out = {"spot": spot, "snapshot": os.path.basename(_latest_chain_csv_path())}
    out["pcr_max_pain"] = _safe(lambda: __import__("oi_intel").pcr_and_pain(chain, spot=spot))
    out["walls"] = _safe(lambda: __import__("oi_intel").oi_walls(chain, spot=spot))
    out["murarkar"] = _safe(lambda: __import__("oi_intel").murarkar_matrix(chain, spot))
    return out


def _latest_chain_csv_path():
    snaps = sorted(glob.glob(os.path.join("data", "oi_snapshots", "NIFTY_*.csv")))
    return snaps[-1] if snaps else ""


@mcp.tool()
def gamma_flip_intel() -> dict:
    """Market-maker gamma exposure (GEX): gamma flip strike, long/short gamma
    regime and liquidity sweep pools. Above flip = stabilizing, below =
    accelerating volatility."""
    chain = _latest_chain_csv()
    if chain is None:
        return {"ok": False, "error": "No option chain snapshot in data/oi_snapshots"}
    return _safe(lambda: __import__("gamma_flip").calculate_gamma_exposure(chain, spot=_current_spot()))


@mcp.tool()
def institutional_flow() -> dict:
    """FII/DII cash + F&O positioning and institutional sentiment from cached
    data/fii_dii_history.csv."""
    return _safe(lambda: __import__("institutional").institutional_scan())


@mcp.tool()
def technical_consensus() -> dict:
    """Multi-indicator technical verdict: bias (CALL/PUT/NEUTRAL), strength,
    confidence, support/resistance, favored vs avoided strategies."""
    df = _nifty_indicator_df()
    if df is None:
        return {"ok": False, "error": "data/nifty_history.csv missing - run python build_data.py"}
    return _safe(lambda: __import__("market_brain").analyze_market(df))


@mcp.tool()
def precision_signal() -> dict:
    """6-layer confluence precision signal (regime + capital guard + technicals
    + options + institutional + ML). Only outputs A+ Grade signals; otherwise
    NO_SIGNAL = stay out."""
    return _safe(lambda: __import__("precision_signals").generate_precision_signal())


@mcp.tool()
def capital_guard_audit(daily_pnl: float = 0.0, is_expiry: bool = False, drawdown_pct: float = 0.0, capital: float = 100000.0) -> dict:
    """SEBI loss-prevention audit: 3% daily kill-switch, 0DTE expiry trap guard,
    event-risk filter, drawdown de-risking and strict 1% position sizing."""
    return _safe(
        lambda: __import__("capital_guard").CapitalGuard(capital=capital).full_capital_safety_audit(
            daily_pnl=daily_pnl, is_expiry=is_expiry, drawdown_pct=drawdown_pct
        )
    )


@mcp.tool()
def stock_scan(top: int = 8) -> dict:
    """Nifty 50 institutional accumulation scan (trend + buying period +
    momentum + volume). Returns top-N strongest accumulation stocks from cache."""
    return _safe(lambda: __import__("stock_flow").scan_universe(top=int(top), throttle=0.05))


@mcp.tool()
def super_ai_ml_context() -> dict:
    """Super-AI ML ensemble (XGBoost/LightGBM/RF). CONTEXT ONLY - has no
    standalone edge (~51% vs 52% baseline). Use as agreement counter, never as
    a buy/sell trigger."""
    return _safe(lambda: __import__("super_ai_ml").train_super_ai_ensemble())


@mcp.tool()
def expiry_status() -> dict:
    """NIFTY weekly expiry info: is today expiry day, days until next expiry."""
    return _expiry_status()


@mcp.tool()
def expected_move() -> dict:
    """Expected daily move from India VIX = NIFTY x (VIX/100)/sqrt(252)."""
    spot = _current_spot()
    vix = _read_vix()
    if not spot or vix is None:
        return {"ok": False, "error": "Missing spot or VIX data"}
    move = spot * (vix / 100.0) / (252 ** 0.5)
    return {"spot": spot, "vix": round(float(vix), 2), "expected_move_pts": round(move, 1)}


@mcp.tool()
def broker_status(area: str = "profile") -> dict:
    """Angel One broker account status. area: 'profile' (account), 'holdings'
    (equity holdings), 'positions' (open F&O positions). Live API - rate limited,
    don't call repeatedly."""
    if area not in ("profile", "holdings", "positions"):
        return {"ok": False, "error": "area must be profile | holdings | positions"}
    from angel_one_client import manager
    return _safe(getattr(manager, "get_" + area))


@mcp.tool()
def recent_ticks(symbol: str = "NIFTY", limit: int = 20) -> dict:
    """Recent live tick rows from data/research.db (tick_recorder output).
    Only populated during market hours. limit max 100."""
    limit = max(1, min(int(limit), 100))
    db_path = os.path.join("data", "research.db")
    if not os.path.exists(db_path):
        return {"ok": False, "error": "data/research.db missing - run python tick_recorder.py during market hours"}
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT * FROM ticks WHERE symbol=? ORDER BY ts DESC LIMIT ?", (symbol, limit)
        ).fetchall()
        cols = [c[0] for c in conn.execute("SELECT * FROM ticks LIMIT 0").description]
        conn.close()
        return {"ok": True, "columns": cols, "rows": [_jsonable(list(r)) for r in rows]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def full_daily_report() -> dict:
    """Generate the combined daily report (regime + chain + institutional +
    stock flow + TF edge + ML context + premium seller) as text."""
    import io
    import contextlib
    import daily_report
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            daily_report.main()
        return {"ok": True, "report": buf.getvalue()}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    mcp.run()
