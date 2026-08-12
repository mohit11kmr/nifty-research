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

RES_LEVELS = [24500, 24550, 24600]      # CE walls (resistance above spot)
SUP_LEVELS = [24450, 24400, 24350]      # PE walls (support below spot)


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


def main():
    print(f"alert_monitor: poll {POLL_SEC}s | levels R{list(map(str,RES_LEVELS))} S{list(map(str,SUP_LEVELS))}", flush=True)
    state = {"regime": None, "zone": None, "above": None, "below": None}
    last_regime_check = 0.0
    while True:
        spot, ts = _live_spot()
        if spot is not None:
            # breakout/resistance logic
            for lvl in RES_LEVELS:
                crossed = state["above"]
                if spot > lvl and crossed is not None and crossed < lvl:
                    _notify(f"BREAKOUT ABOVE {lvl}", f"NIFTY {spot:,.0f} crossed {lvl} (live). Opportunity check!", urgent=True)
                elif spot < lvl and crossed is not None and crossed > lvl:
                    _notify(f"RECLAIMED BELOW {lvl}", f"NIFTY {spot:,.0f} fell back under {lvl}. Stand by.", urgent=True)
            for lvl in SUP_LEVELS:
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
