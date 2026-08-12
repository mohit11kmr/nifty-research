"""Intraday opportunity alert monitor - desktop popup (notify-send) on setup change.

Triggers (each fires once per state change, not every poll):
  1. REGIME CHANGE: regime gate leaves RANGE_LV (NO_TRADE -> OPEN) or VIX zone changes
  2. BREAKOUT: spot crosses 24500 (CE wall + gamma flip) up, or 24450/24400 down
  3. KILL-SWITCH / warning levels

Run:  setsid .venv/bin/python -u alert_monitor.py
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DASH = "http://127.0.0.1:8766"
POLL_SEC = int(os.environ.get("ALERT_POLL_SEC", "30"))
REGIME_POLL_SEC = 180


def _notify(title, body, urgent=False):
    try:
        subprocess.run(
            ["notify-send", "-u", "critical" if urgent else "normal",
             "-a", "NIFTY ALERT", title, body],
            timeout=5, check=False)
        sound = "bell.oga" if urgent else "complete.oga"
        subprocess.run(["paplay", f"/usr/share/sounds/freedesktop/stereo/{sound}"],
                       timeout=5, check=False)
    except Exception as e:
        print(f"  notify err: {e}", flush=True)


def _get_json(url):
    import urllib.request
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r)


def _live_spot():
    try:
        d = _get_json(f"{DASH}/api/spot")
        if d.get("ok"):
            return float(d["value"]), d.get("recv_ts")
    except Exception:
        pass
    return None, None


def _regime_state():
    """Regime + VIX + expected move from cached regime_filter."""
    try:
        from regime_filter import trade_plan
        plan = trade_plan()
        r = plan.get("regime", "")
        vix = plan.get("vix") or {}
        return {
            "regime": r,
            "gate": plan.get("gate"),
            "vix_zone": vix.get("zone", "").replace("VIX_", ""),
            "vix_level": vix.get("level"),
            "expected_move": vix.get("expected_move"),
        }
    except Exception as e:
        print(f"  regime err: {e}", flush=True)
        return None


def _oi_levels(spot):
    """Dynamic support/resistance from real OI walls; spot-relative fallback.

    Uses the freshest option chain snapshot (real OI). If no snapshot exists,
    falls back to spot-relative bands (nearest strikes) instead of stale
    hardcoded 2025-era levels.
    """
    try:
        import glob
        import oi_intel
        import pandas as pd
        snaps = sorted(glob.glob(os.path.join("data", "oi_snapshots", "NIFTY_*.csv")))
        if snaps:
            cdf = pd.read_csv(snaps[-1])
            walls = oi_intel.oi_walls(cdf, spot=spot)
            res = [int(s) for s in walls.get("resistance_oi", []) if int(s) > spot]
            sup = [int(s) for s in walls.get("support_oi", []) if int(s) < spot]
            if res or sup:
                return res or [], sup or []
    except Exception as e:
        print(f"  oi-levels err: {e}", flush=True)

    # spot-relative fallback (nearest 50 strikes around spot)
    base = int(round(spot / 50.0) * 50)
    res = [base + 50, base + 100, base + 150]
    sup = [base - 50, base - 100, base - 150]
    return res, sup


def main():
    print("alert_monitor: poll {}s | dynamic OI-wall levels (spot-relative fallback)".format(POLL_SEC), flush=True)
    state = {"regime": None, "zone": None, "above": None, "below": None}
    last_regime_check = 0.0
    while True:
        spot, ts = _live_spot()
        if spot is not None:
            res_levels, sup_levels = _oi_levels(spot)
            # breakout/resistance logic
            for lvl in res_levels:
                crossed = state["above"]
                if spot > lvl and crossed is not None and crossed < lvl:
                    _notify(f"BREAKOUT ABOVE {lvl}", f"NIFTY {spot:,.0f} crossed {lvl} (live). Opportunity check!", urgent=True)
                elif spot < lvl and crossed is not None and crossed > lvl:
                    _notify(f"RECLAIMED BELOW {lvl}", f"NIFTY {spot:,.0f} fell back under {lvl}. Stand by.", urgent=True)
            for lvl in sup_levels:
                crossed = state["below"]
                if spot < lvl and crossed is not None and crossed > lvl:
                    _notify(f"BREAKDOWN BELOW {lvl}", f"NIFTY {spot:,.0f} broke {lvl} (live). Opportunity check!", urgent=True)
                elif spot > lvl and crossed is not None and crossed < lvl:
                    _notify(f"BOUNCED ABOVE {lvl}", f"NIFTY {spot:,.0f} reclaimed {lvl}. Stand by.", urgent=True)
            state["above"], state["below"] = spot, spot
        else:
            print(f"  {datetime.now():%H:%M:%S} no live spot (pre-market/dash down)", flush=True)

        if time.time() - last_regime_check >= REGIME_POLL_SEC:
            last_regime_check = time.time()
            rs = _regime_state()
            if rs:
                if rs["regime"] != state["regime"]:
                    old = state["regime"] or "?"
                    if old != "?" and rs["gate"] != "NO_TRADE":
                        _notify(f"REGIME CHANGE: {old} -> {rs['regime']}",
                                f"Gate {rs['gate']} | VIX {rs['vix_zone']} ({rs['vix_level']}). Opportunity window open!", urgent=True)
                    elif rs["gate"] == "NO_TRADE":
                        _notify(f"REGIME: {rs['regime']}",
                                "Gate NO_TRADE. No directional setup. Stand by (no averaging, no FOMO).")
                    state["regime"] = rs["regime"]
                    state["zone"] = rs["vix_zone"]
                elif rs["vix_zone"] != state["zone"]:
                    _notify(f"VIX ZONE CHANGE: {state['zone']} -> {rs['vix_zone']}",
                            f"VIX {rs['vix_level']}. Expected move {rs['expected_move']} pts. Check setup plan.")
                    state["zone"] = rs["vix_zone"]
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
