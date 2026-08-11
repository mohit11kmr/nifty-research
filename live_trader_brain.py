"""Master Decision Brain & Intellectual Synthesis Engine for NIFTY Research.

Synthesizes 5 High-Level Dimensions of Quantitative Trading:
1. Trader Psychology & Tilt Defense (trader_psychology.py)
2. Smart Money Concepts & Order Blocks (smc_intelligence.py)
3. Monte Carlo Account Survival Matrix (monte_carlo.py)
4. Super-AI Machine Learning Ensemble (super_ai_ml.py)
5. Capital Preservation & SEBI Rules (capital_guard.py)
"""
import os
import sys
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))


def evaluate_master_trader_brain():
    """Synthesize complete intellectual matrix into one unified trading recommendation."""
    print("🧠 [LIVE TRADER BRAIN] Synthesizing Master Quantitative Matrix...")

    # 1. Trader Psychology Audit
    try:
        import trader_psychology
        psych = trader_psychology.PsychologyGuard().audit_trade_psychology()
    except Exception as e:
        psych = {"psychology_status": "ERROR", "error": str(e)}

    # 2. Smart Money Concepts (SMC) Structure
    try:
        import smc_intelligence
        smc = smc_intelligence.analyze_smc_structure()
    except Exception as e:
        smc = {"smc_status": "ERROR", "error": str(e)}

    # 3. Monte Carlo Survival Probability
    try:
        import monte_carlo
        mc = monte_carlo.run_monte_carlo_simulation()
    except Exception as e:
        mc = {"survival_status": "ERROR", "error": str(e)}

    # 4. Super-AI ML Ensemble
    try:
        import super_ai_ml
        ml = super_ai_ml.train_super_ai_ensemble()
    except Exception as e:
        ml = {"ml_status": "ERROR", "error": str(e)}

    # 5. Capital Guard Audit
    try:
        import capital_guard
        cg = capital_guard.CapitalGuard().full_capital_safety_audit()
    except Exception as e:
        cg = {"capital_guard_status": "ERROR", "error": str(e)}

    # Master Decision Synthesis
    psych_ok = psych.get("psychology_status") == "HEALTHY_MINDSET"
    cg_ok = cg.get("safety_status") == "APPROVED" or not cg.get("kill_switch", {}).get("is_kill_switch_active")
    mc_ok = mc.get("account_survival_rate_pct", 0) >= 95.0
    ml_verdict = ml.get("super_ai_verdict", "NEUTRAL_SIDEWAYS") if ml else "NEUTRAL_SIDEWAYS"

    if psych_ok and cg_ok and mc_ok and ml_verdict != "NEUTRAL_SIDEWAYS":
        overall_master_verdict = f"RECOMMENDED_{ml_verdict}"
        confidence = "HIGH (INTELLECTUAL MATRIX ALIGNED)"
    else:
        overall_master_verdict = "STAND_BY_NO_TRADE"
        confidence = "PROTECTION MODE (DISCIPLINE FIRST)"

    output = {
        "timestamp": dt.datetime.now().strftime("%d %b %Y %H:%M IST"),
        "master_trader_verdict": overall_master_verdict,
        "master_confidence_level": confidence,
        "dimension_1_psychology": {
            "status": psych.get("psychology_status"),
            "warnings": psych.get("psychological_warnings"),
        },
        "dimension_2_smart_money_concepts": {
            "structure": smc.get("smc_market_structure"),
            "order_blocks": smc.get("institutional_order_blocks"),
        },
        "dimension_3_monte_carlo_risk": {
            "survival_probability_pct": mc.get("account_survival_rate_pct"),
            "expected_drawdown_pct": mc.get("average_expected_drawdown_pct"),
        },
        "dimension_4_super_ai_ml": {
            "verdict": ml_verdict,
            "probability": ml.get("ensemble_bullish_probability") if ml else 0.5,
        },
        "dimension_5_capital_guard": {
            "safety_status": cg.get("safety_status"),
            "kill_switch": cg.get("kill_switch", {}).get("status"),
        },
    }

    print(json.dumps(output, indent=2))
    return output


if __name__ == "__main__":
    evaluate_master_trader_brain()
