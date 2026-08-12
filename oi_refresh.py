"""Live OI refresher - periodically fetches NSE chain via browser into a
freshest snapshot file that live_dash reads. stdlib + project deps.

Run:  .venv/bin/python -u oi_refresh.py   (background / nohup / setsid)
Writes: data/oi_snapshots/oi_NIFTY_live.json  (overwritten each cycle)
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SNAP_DIR = os.path.join(HERE, "data", "oi_snapshots")
LIVE_FILE = os.path.join(SNAP_DIR, "oi_NIFTY_live.json")
INTERVAL = int(os.environ.get("OI_REFRESH_SEC", "120"))


def _write_live(chain, meta=None):
    os.makedirs(SNAP_DIR, exist_ok=True)
    rec = {"date": meta.get("timestamp", "") if meta else "",
           "symbol": "NIFTY", "_meta": meta or {}}
    for _, r in chain.iterrows():
        rec[str(int(r["strike"]))] = {
            "ce_oi": r["ce_oi"], "pe_oi": r["pe_oi"],
            "ce_oi_chg": r["ce_oi_chg"], "pe_oi_chg": r["pe_oi_chg"],
        }
    tmp = LIVE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f)
    os.replace(tmp, LIVE_FILE)
    return len(rec) - 2


def main():
    from nse_live import fetch_option_chain_live, close
    print(f"oi_refresh: every {INTERVAL}s -> {LIVE_FILE}", flush=True)
    while True:
        t0 = time.time()
        try:
            df, meta = fetch_option_chain_live("NIFTY")
            n = _write_live(df, meta)
            ts = meta.get("timestamp", "?")
            print(f"  ok: {n} strikes @ {ts} ({time.time()-t0:.0f}s)", flush=True)
        except Exception as e:
            print(f"  fail: {e}", flush=True)
        try:
            close()
        except Exception:
            pass
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
