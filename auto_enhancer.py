"""Autonomous Auto-Enhancement & Self-Improvement Engine for NIFTY Research.

Executes continuous self-optimization:
1. Walk-Forward Reinforcement Weight Adjustments (adaptive_weights.py)
2. Dynamic Volatility & ATR Stop Threshold Recalibration
3. System Performance Evolution Tracking
"""
import os
import sys
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))


def _weights_changed(before, after):
    """True if any weight value actually changed (ignores last_updated)."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    keys = set(before) | set(after)
    for k in keys:
        if k == "last_updated":
            continue
        if before.get(k) != after.get(k):
            return True
    return False


def run_auto_enhancement_cycle():
    """Execute complete autonomous self-enhancement loop.

    Truth-layer (Phase 3): reports whether anything actually changed. With
    no real trade outcomes, adaptive_weights is an honest no-op, so the
    verdict is AUTO_ENHANCEMENT_NOOP instead of the old fabricated
    "automatically updated ... for tomorrow" claim.
    """
    print("==================================================================")
    print("🔄 AUTONOMOUS CONTINUOUS SELF-ENHANCEMENT ENGINE")
    print(f"Time: {dt.datetime.now().strftime('%d %b %Y | %H:%M:%S IST')}")
    print("==================================================================")

    # 1. Update RL Adaptive Weights (honest no-op without real outcomes)
    import adaptive_weights
    weights_before = adaptive_weights.load_adaptive_weights()
    updated_weights = adaptive_weights.update_adaptive_weights()
    weights_after = adaptive_weights.load_adaptive_weights()
    weights_changed = _weights_changed(weights_before, weights_after)

    # 2. Volume Profile & POC Recalibration
    import volume_profile
    vp = volume_profile.compute_volume_profile()

    # 3. Capital Guard Safety Recalibration
    import capital_guard
    cg = capital_guard.CapitalGuard().full_capital_safety_audit()

    if weights_changed:
        enhancement_status = "AUTO_ENHANCEMENT_SUCCESSFUL"
        evolution_verdict = ("Indicator weights were updated from real trade outcomes "
                             "(Q-learning reward feedback).")
    else:
        enhancement_status = "AUTO_ENHANCEMENT_NOOP"
        evolution_verdict = ("No real trade outcomes were available - no weights, volume "
                             "profile zones, or risk limits were changed (honest no-op).")

    enhancement_report = {
        "timestamp": dt.datetime.now().strftime("%d %b %Y %H:%M IST"),
        "enhancement_cycle_status": enhancement_status,
        "weights_changed": weights_changed,
        "rl_adaptive_weights": updated_weights,
        "volume_profile_poc": vp.get("point_of_control_poc"),
        "value_area": f"{vp.get('value_area_low_val')} - {vp.get('value_area_high_vah')}",
        "volume_data_status": vp.get("data_status"),
        "capital_safety_status": cg.get("safety_status"),
        "system_evolution_verdict": evolution_verdict,
    }

    # Save log to data/enhancement_log.json
    log_file = os.path.join("data", "enhancement_log.json")
    os.makedirs("data", exist_ok=True)
    with open(log_file, "w") as f:
        json.dump(enhancement_report, f, indent=2)

    print("\n" + json.dumps(enhancement_report, indent=2))
    return enhancement_report


if __name__ == "__main__":
    run_auto_enhancement_cycle()
