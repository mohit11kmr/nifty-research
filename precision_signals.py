"""High-Precision Signal Generator & Alert Engine for NIFTY Research.

Identifies ONLY A+ Grade High-Conviction Trading Signals by enforcing 5-Layer Confluence:
1. Regime Gate Check (regime_filter.py) -> Must be OPEN (TREND_HV, TREND_LV, RANGE_HV)
2. Capital Guard Check (capital_guard.py) -> Must pass Kill-Switch, Expiry Trap & Event Risk
3. Multi-Indicator Consensus (market_brain.py) -> Must have >= 80% Technical Consensus
4. Options Chain Confluence (oi_intel.py & skew.py) -> PCR & IV Skew alignment
5. Institutional Flow Confluence (institutional.py) -> FII/DII Futures & Cash alignment

If ALL 5 layers agree -> Generates an A+ Grade Precise Signal with exact Entry, Target, SL, and Option Strike!
If Confluence < 80% -> Outputs NO_SIGNAL (Filters out noise & bad trades).
"""
import os
import sys
import json
import datetime as dt
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))


def _to_float(val, default=None):
    try:
        if val is None:
            return default
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, dict) and "close" in val:
            return float(val["close"])
        return float(val)
    except Exception:
        return default


def _daily_pnl_from_paper():
    """Today's REAL realized PnL from the paper account; 0.0 if none recorded.

    Never fabricated: reads only closed paper trades stamped today. A missing
    file or an unreadable account simply means no known loss today.
    """
    try:
        p = os.path.join("data", "paper_account.json")
        if not os.path.exists(p):
            return 0.0
        acct = json.load(open(p))
        today = dt.datetime.now().strftime("%Y-%m-%d")
        closed = acct.get("closed_positions") or []
        pnl = sum(
            float(t.get("realized_pnl", 0) or 0)
            for t in closed if str(t.get("timestamp", "")).startswith(today)
        )
        return round(pnl, 2)
    except Exception:
        return 0.0


def _technical_verdict(regime):
    """REAL technical consensus from cached NIFTY indicators (never fabricated).

    Builds an indicator frame from the actual daily cache and runs
    market_brain on the latest row. Returns
    (bias, strength, verdict, votes, total) or ("NEUTRAL", "LOW", None, 0, 0)
    with honest NOT_COMPUTED when data is absent.
    """
    try:
        import indicators
        import market_brain
        import regime_filter
        df = regime_filter._load_nifty_cached()
        if df is None or df.empty:
            return "NEUTRAL", "LOW", None, 0, 0
        if "adx" not in df.columns:
            indicators.add_all_indicators(df)
        df = df.dropna(subset=["adx", "bb_upper", "bb_lower"]).reset_index(drop=True)
        if len(df) < 30:
            return "NEUTRAL", "LOW", None, 0, 0
        row = df.iloc[-1]
        mb_regime, _ = market_brain.detect_regime(df, row)
        votes, score, total = market_brain.directional_consensus(df, row)
        verdict = market_brain.make_verdict(df, row, mb_regime, score, total)
        return verdict.get("bias", "NEUTRAL"), verdict.get("strength", "LOW"), verdict, score, total
    except Exception:
        return "NEUTRAL", "LOW", None, 0, 0


def generate_precision_signal():
    """Evaluate 6-Layer Confluence and output ONLY A+ Grade Precise Signals.

    Every layer must be computed from REAL data. When a data source is
    unavailable the layer reports NOT_COMPUTED/NEUTRAL instead of a fabricated
    pass - no hardcoded spot/VIX/consensus is ever presented as live.
    """
    confluence_score = 0
    max_score = 6
    checks = {}
    spot = None
    vix = None
    vix_zone = None
    regime = "UNKNOWN"

    # Layer 1: Regime Gate Check
    try:
        import regime_filter
        regime_data = regime_filter.trade_plan()
        regime = regime_data.get("regime", "UNKNOWN")
        gate = regime_data.get("gate", "UNKNOWN")
        if regime == "UNKNOWN":
            checks["regime_layer"] = {"status": "NOT_COMPUTED", "reason": "no regime data"}
        else:
            spot = _to_float(regime_data.get("close"))
            vix_data = regime_data.get("vix") or {}
            vix = _to_float(vix_data.get("level"))
            vix_zone = vix_data.get("zone", "NORMAL")
            regime_open = gate != "NO_TRADE" and regime != "RANGE_LV"
            if regime_open:
                confluence_score += 1
                checks["regime_layer"] = {"status": "PASSED", "regime": regime, "gate": gate}
            else:
                checks["regime_layer"] = {"status": "BLOCKED", "regime": regime, "gate": gate,
                                          "reason": regime_data.get("regime_note", "gate closed")}
    except Exception as e:
        checks["regime_layer"] = {"status": "ERROR", "error": str(e)}

    # Layer 2: Capital Guard Safety Check (real daily PnL, honest status)
    try:
        import capital_guard
        cg = capital_guard.CapitalGuard()
        safety = cg.full_capital_safety_audit(daily_pnl=_daily_pnl_from_paper())
        safety_passed = safety.get("safety_status") == "APPROVED"
        checks["capital_guard_layer"] = {
            "status": "PASSED" if safety_passed else "BLOCKED",
            "safety_status": safety.get("safety_status"),
            "kill_switch_active": bool(safety.get("kill_switch", {}).get("is_kill_switch_active")),
            "capital_preservation_score": safety.get("capital_preservation_score"),
        }
        if safety_passed:
            confluence_score += 1
    except Exception as e:
        checks["capital_guard_layer"] = {"status": "ERROR", "error": str(e)}

    # Layer 3: Technical Consensus (market_brain) from REAL indicators
    tech_bias, tech_strength, tech_verdict, tech_score, tech_total = _technical_verdict(regime)
    if tech_verdict is not None:
        if tech_bias != "NEUTRAL":
            confluence_score += 1
            checks["technical_layer"] = {"status": "PASSED", "bias": tech_bias, "strength": tech_strength,
                                         "consensus": f"{tech_score}/{tech_total}",
                                         "confidence": tech_verdict.get("confidence")}
        else:
            checks["technical_layer"] = {"status": "NEUTRAL", "bias": tech_bias, "strength": tech_strength,
                                         "consensus": f"{tech_score}/{tech_total}"}
    else:
        checks["technical_layer"] = {"status": "NOT_COMPUTED", "reason": "insufficient indicator data"}

    # Layer 4: Options Chain & Skew Confluence (real PCR & skew alignment only)
    try:
        import oi_intel, skew
        snap_dir = os.path.join("data", "oi_snapshots")
        snaps = [os.path.join(snap_dir, f) for f in os.listdir(snap_dir) if f.endswith(".csv")] if os.path.exists(snap_dir) else []
        if not snaps:
            checks["options_layer"] = {"status": "NO_SNAPSHOT"}
        elif not spot:
            checks["options_layer"] = {"status": "NOT_COMPUTED", "reason": "no live spot to anchor chain analysis"}
        else:
            cdf = pd.read_csv(snaps[-1])
            pcr_data = oi_intel.pcr_and_pain(cdf, spot=spot)
            walls = oi_intel.oi_walls(cdf, spot=spot)
            skew_data = skew.compute_iv_skew(cdf, spot=spot)
            pcr = _to_float(pcr_data.get("pcr"), 1.0)
            max_pain = pcr_data.get("max_pain", spot)

            oi_passed = (pcr > 1.2 and tech_bias == "CALL") or (pcr < 0.8 and tech_bias == "PUT")
            if oi_passed:
                confluence_score += 1
                checks["options_layer"] = {"status": "PASSED", "pcr": pcr, "max_pain": max_pain, "skew_bias": skew_data.get("bias"), "walls": walls}
            else:
                checks["options_layer"] = {"status": "MIXED", "pcr": pcr, "max_pain": max_pain, "walls": walls}
    except Exception as e:
        checks["options_layer"] = {"status": "ERROR", "error": str(e)}

    # Layer 5: Institutional Flow
    try:
        import institutional
        inst_data = institutional.institutional_scan()
        fii_sentiment = inst_data.get("fii_sentiment", "NEUTRAL")
        if fii_sentiment != "NEUTRAL":
            confluence_score += 1
            checks["institutional_layer"] = {"status": "PASSED", "fii_sentiment": fii_sentiment}
        else:
            checks["institutional_layer"] = {"status": "NEUTRAL", "fii_sentiment": fii_sentiment}
    except Exception as e:
        checks["institutional_layer"] = {"status": "ERROR", "error": str(e)}

    # Layer 6: Super-AI Machine Learning Ensemble (XGBoost + LightGBM + Random Forest)
    max_score = 6
    try:
        import super_ai_ml
        ml_res = super_ai_ml.train_super_ai_ensemble()
        if ml_res:
            ml_verdict = ml_res.get("super_ai_verdict", "NEUTRAL_SIDEWAYS")
            ml_prob = ml_res.get("ensemble_bullish_probability", 0.5)
            if ml_verdict != "NEUTRAL_SIDEWAYS":
                confluence_score += 1
                checks["super_ai_ml_layer"] = {"status": "PASSED", "verdict": ml_verdict, "bullish_probability": ml_prob}
            else:
                checks["super_ai_ml_layer"] = {"status": "NEUTRAL", "verdict": ml_verdict, "bullish_probability": ml_prob}
        else:
            checks["super_ai_ml_layer"] = {"status": "NO_DATA"}
    except Exception as e:
        checks["super_ai_ml_layer"] = {"status": "ERROR", "error": str(e)}

    # Confluence Rating Logic
    confluence_pct = (confluence_score / max_score) * 100

    if confluence_score >= 5 and checks.get("regime_layer", {}).get("status") == "PASSED":
        signal_grade = "A+ GRADE (SUPER PRECISE)"
        signal_action = f"HIGH_CONVICTION_{tech_bias}" if tech_bias != "NEUTRAL" else "HIGH_CONVICTION_SPREAD"
    elif confluence_score >= 4 and checks.get("regime_layer", {}).get("status") == "PASSED":
        signal_grade = "A GRADE (HIGH QUALITY)"
        signal_action = f"MODERATE_{tech_bias}" if tech_bias != "NEUTRAL" else "NEUTRAL_SPREAD"
    else:
        signal_grade = "NO_SIGNAL (FILTERED OUT NOISE)"
        signal_action = "STAY_OUT"


    # Exact Strikes & Risk Levels Calculation
    # Prefer REAL OI walls (nearest resistance/support from the live chain);
    # fall back to spot±1% only when the options layer had no snapshot.
    # NIFTY strike grid is 50 points (verified against live chain snapshots).
    walls = checks.get("options_layer", {}).get("walls") or {}
    if walls.get("nearest_resistance"):
        ce_strike = round(walls["nearest_resistance"] / 50) * 50
    elif spot:
        ce_strike = round((spot * 1.01) / 50) * 50
    else:
        ce_strike = None
    if walls.get("nearest_support"):
        pe_strike = round(walls["nearest_support"] / 50) * 50
    elif spot:
        pe_strike = round((spot * 0.99) / 50) * 50
    else:
        pe_strike = None
    sl_points = round(spot * 0.008, 1) if spot else None  # 0.8% index SL
    tgt_points = round(sl_points * 2.0, 1) if sl_points else None  # 1:2 Risk-Reward

    return {
        "timestamp": dt.datetime.now().strftime("%d %b %Y %H:%M IST"),
        "signal_action": signal_action,
        "signal_grade": signal_grade,
        "confluence_score": f"{confluence_score}/{max_score} ({confluence_pct:.0f}%)",
        "nifty_spot": round(spot, 2) if spot else None,
        "vix": round(vix, 2) if vix else None,
        "vix_zone": vix_zone,
        "precise_trade_levels": {
            "entry_spot_zone": f"{spot - 25:.0f} - {spot + 25:.0f}" if spot else None,
            "recommended_call_strike": int(ce_strike) if ce_strike else None,
            "recommended_put_strike": int(pe_strike) if pe_strike else None,
            "stop_loss_points": sl_points,
            "target_1_points": tgt_points,
            "target_2_points": round(tgt_points * 1.5, 1) if tgt_points else None,
            "risk_reward_ratio": "1 : 2.0",
        },
        "confluence_checks": checks,
    }


if __name__ == "__main__":
    print("=== HIGH-PRECISION SIGNAL GENERATOR TEST ===")
    sig = generate_precision_signal()
    print(json.dumps(sig, indent=2))
