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

import expiry_calendar  # canonical single-owner NIFTY weekly-expiry service


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
    return {
        "today": today.isoformat(),
        "weekday": today.strftime("%A"),
        "days_to_expiry": (expiry_calendar.get_expiry_for_trade_date(today) - today).days,
        "is_expiry_day": expiry_calendar.is_expiry_day(today),
        "next_expiry": expiry_calendar.get_expiry_for_trade_date(today).isoformat(),
        "era": expiry_calendar.expiry_era(today),
        "source": expiry_calendar.describe(today)["source"],
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
    don't call repeatedly. DISABLED unless BROKER_MCP_ENABLED=1 is set in .env."""
    if os.environ.get("BROKER_MCP_ENABLED") != "1":
        return {"ok": False,
                "error": "broker_status disabled - set BROKER_MCP_ENABLED=1 in .env to expose live broker data to MCP"}
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
            "SELECT * FROM ticks WHERE symbol=? AND recv_ts >= datetime('now','localtime','-1 day') "
            "ORDER BY recv_ts DESC LIMIT ?", (symbol, limit)
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


@mcp.tool()
def ground_truth_signal(signal_grade: str = "A+ GRADE (SUPER PRECISE)",
                        signal_action: str = "HIGH_CONVICTION_CALL",
                        nifty_spot: float = None, vix: float = None,
                        vix_zone: str = "NORMAL", market_state: str = "UNKNOWN",
                        confluence_checks: dict = None) -> dict:
    """Record a trade setup into the immutable ground-truth ledger as a full
    chain (observation -> signal -> prediction -> decision). Re-derives the
    prediction direction from the signal action; returns the chain ids. Use
    this when the nifty-analyst produces a concrete setup, so the next
    session close can score it. Leave signal_action as STAY_OUT to log a
    no-trade day honestly."""
    import ground_truth
    sig = {
        "signal_action": signal_action,
        "signal_grade": signal_grade,
        "confluence_score": "5/6",
        "nifty_spot": nifty_spot,
        "vix": vix,
        "vix_zone": vix_zone,
        "market_state": market_state,
        "confluence_checks": confluence_checks or {},
    }
    ledger = ground_truth.GroundTruthDB()
    return _safe(ledger.record_signal_chain, sig)


@mcp.tool()
def ground_truth_status() -> dict:
    """Ground-truth ledger status: row counts, pending prediction evaluations,
    reproducibility of the latest signal, and integrity gate (append-only).
    Also runs pending prediction evaluations against the latest close."""
    import ground_truth
    ledger = ground_truth.GroundTruthDB()
    out = {}
    out["counts"] = _safe(ledger.counts)
    out["pending_evaluated"] = _safe(ledger.evaluate_pending_predictions)
    latest = None
    try:
        row = ledger._cur().execute(
            "SELECT signal_id FROM signals ORDER BY signal_id DESC LIMIT 1"
        ).fetchone()
        if row:
            latest = _safe(ledger.verify_reproducibility, int(row[0]))
    except Exception as e:
        latest = {"error": f"{type(e).__name__}: {e}"}
    out["latest_signal_reproducible"] = latest
    out["integrity"] = _safe(ledger.integrity_check)
    return out


# ---------------------------------------------------------------------------
# Phase 6 - read-only evaluation tools (measurement only, never mutate)
# ---------------------------------------------------------------------------
def _eval_engine():
    import evaluation_engine
    return evaluation_engine


@mcp.tool()
def evaluation_summary() -> dict:
    """Read-only Phase 6 performance summary from the ground-truth ledger:
    row counts, cohort sizes, signal/prediction/outcome evaluation, and the
    leakage-verification flag. Never writes to the ledger."""
    ee = _eval_engine()
    engine = ee.EvaluationEngine(gt_db=ee.GT_DB)
    try:
        return _safe(engine.evaluation_summary)
    finally:
        try:
            engine._conn_ro.close()
        except Exception:
            pass


@mcp.tool()
def signal_performance() -> dict:
    """Read-only signal-level hit rate / outcome distribution by signal type
    and market regime from REAL_FRESH-eligible records."""
    ee = _eval_engine()
    engine = ee.EvaluationEngine(gt_db=ee.GT_DB)
    try:
        return _safe(engine.signal_performance)
    finally:
        try:
            engine._conn_ro.close()
        except Exception:
            pass


@mcp.tool()
def prediction_performance() -> dict:
    """Read-only prediction accuracy / calibration / P&L by model, confidence
    band and market regime."""
    ee = _eval_engine()
    engine = ee.EvaluationEngine(gt_db=ee.GT_DB)
    try:
        return _safe(engine.prediction_performance)
    finally:
        try:
            engine._conn_ro.close()
        except Exception:
            pass


@mcp.tool()
def failure_summary() -> dict:
    """Read-only failure taxonomy aggregation (DATA_ERROR / FEATURE_ERROR /
    MODEL_ERROR / RISK_ERROR / ...) with evidence preserved."""
    ee = _eval_engine()
    engine = ee.EvaluationEngine(gt_db=ee.GT_DB)
    try:
        return _safe(engine.failure_summary)
    finally:
        try:
            engine._conn_ro.close()
        except Exception:
            pass


@mcp.tool()
def confidence_calibration() -> dict:
    """Read-only confidence-band vs observed-success calibration status
    (CALIBRATED / PARTIALLY_CALIBRATED / UNCALIBRATED / INSUFFICIENT_DATA)."""
    ee = _eval_engine()
    engine = ee.EvaluationEngine(gt_db=ee.GT_DB)
    try:
        return _safe(engine.confidence_calibration)
    finally:
        try:
            engine._conn_ro.close()
        except Exception:
            pass


@mcp.tool()
def regime_performance() -> dict:
    """Read-only performance segmented by market_state/regime with sample
    sufficiency labels."""
    ee = _eval_engine()
    engine = ee.EvaluationEngine(gt_db=ee.GT_DB)
    try:
        return _safe(engine.regime_performance)
    finally:
        try:
            engine._conn_ro.close()
        except Exception:
            pass


@mcp.tool()
def baseline_status() -> dict:
    """Read-only frozen-baseline status: report version, ledger db sha256,
    row counts and evaluation cohort eligibility (REAL_FRESH etc.)."""
    ee = _eval_engine()
    engine = ee.EvaluationEngine(gt_db=ee.GT_DB)
    try:
        return _safe(engine.baseline_status)
    finally:
        try:
            engine._conn_ro.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Phase 6.5 - read-only live observation / chain health tools
# ---------------------------------------------------------------------------
@mcp.tool()
def live_observation_status() -> dict:
    """Read-only Phase 6.5 observation snapshot: counts, directional signals,
    STAY_OUT/SKIP rate, open/closed positions, pending predictions, chain
    findings and the observation state
    (NO_DIRECTIONAL_TRADES_YET / PENDING_OUTCOMES / ACCUMULATING_OUTCOMES)."""
    ee = _eval_engine()
    engine = ee.EvaluationEngine(gt_db=ee.GT_DB)
    try:
        return _safe(ee.live_observation_report, engine)
    finally:
        try:
            engine._conn_ro.close()
        except Exception:
            pass


@mcp.tool()
def ground_truth_chain_health() -> dict:
    """Read-only chain-health monitor over the full ground truth chain. Flags
    ORPHAN_* records, MISSING/DUPLICATE outcomes, MISSING_FEATURE_SNAPSHOT,
    PROVENANCE_LOSS, TIMESTAMP_INCONSISTENCY and INVALID_STATE_TRANSITION with
    severity INFO/WARNING/ERROR/CRITICAL. Never modifies the ledger."""
    ee = _eval_engine()
    engine = ee.EvaluationEngine(gt_db=ee.GT_DB)
    try:
        return _safe(ee.chain_health_report, engine)
    finally:
        try:
            engine._conn_ro.close()
        except Exception:
            pass


@mcp.tool()
def pending_evaluations() -> dict:
    """Read-only list of predictions not yet evaluated against their horizon
    close (i.e. whose outcome is still unknown)."""
    ee = _eval_engine()
    engine = ee.EvaluationEngine(gt_db=ee.GT_DB)
    try:
        rows = engine._load_prediction_rows()
        pending = [r for r in rows if r.get("evaluation_status") in (None, "PENDING")]
        return _safe(lambda: {"pending": len(pending),
                              "prediction_ids": [r.get("prediction_id") for r in pending]})
    finally:
        try:
            engine._conn_ro.close()
        except Exception:
            pass


@mcp.tool()
def open_positions() -> dict:
    """Read-only list of currently open paper/live positions from the ledger
    (never places orders)."""
    ee = _eval_engine()
    engine = ee.EvaluationEngine(gt_db=ee.GT_DB)
    try:
        tables = engine._tables()
        if "positions" not in tables:
            return _safe(lambda: {"open": 0, "positions": []})
        rows = engine._qdict("SELECT * FROM positions WHERE status='OPEN'")
        return _safe(lambda: {"open": len(rows),
                              "positions": [{k: rows[i].get(k) for k in
                                             ("position_id", "symbol", "side", "strike",
                                              "option_type", "quantity", "entry_price",
                                              "entry_timestamp", "position_ref")}
                                            for i in range(len(rows))]})
    finally:
        try:
            engine._conn_ro.close()
        except Exception:
            pass


@mcp.tool()
def outcome_status() -> dict:
    """Read-only outcome status: by_class (WIN/LOSS/BREAKEVEN), total net P&L,
    MFE/MAE availability and mfe_source distribution."""
    ee = _eval_engine()
    engine = ee.EvaluationEngine(gt_db=ee.GT_DB)
    try:
        return _safe(lambda: engine.evaluation_report()["outcome_evaluation"])
    finally:
        try:
            engine._conn_ro.close()
        except Exception:
            pass


if __name__ == "__main__":
    mcp.run()
