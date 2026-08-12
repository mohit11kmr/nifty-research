"""Live browser dashboard - serves live_dash.html + JSON API from research.db.

stdlib-only. Run:  .venv/bin/python live_dash.py [port]
Open:  http://localhost:8766
"""
import json
import os
import sqlite3
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "data", "research.db")
HTML_PATH = os.path.join(HERE, "live_dash.html")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8766


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def _api_spot():
    con = _connect()
    row = con.execute("SELECT recv_ts, value, pct_chg FROM spot ORDER BY recv_ts DESC LIMIT 1").fetchone()
    prev = con.execute("SELECT value FROM spot ORDER BY recv_ts DESC LIMIT 2 OFFSET 1").fetchone()
    con.close()
    if not row:
        return {"ok": False, "error": "no spot data"}
    return {
        "ok": True,
        "value": round(row["value"], 1),
        "pct_chg": round(row["pct_chg"], 2) if row["pct_chg"] is not None else None,
        "recv_ts": row["recv_ts"],
        "prev": round(prev["value"], 1) if prev else None,
        "is_live": abs(datetime.now().timestamp() - datetime.fromisoformat(row["recv_ts"]).timestamp()) < 120,
    }


def _load_snapshot_oi():
    """OI from freshest snapshot (live refresh file first, then latest dated)."""
    snap_dir = os.path.join(HERE, "data", "oi_snapshots")
    live = os.path.join(snap_dir, "oi_NIFTY_live.json")
    candidates = [live]
    try:
        dated = sorted(
            f for f in os.listdir(snap_dir)
            if f.startswith("oi_NIFTY_") and f.endswith(".json"))
        if dated:
            candidates.append(os.path.join(snap_dir, dated[-1]))
    except OSError:
        pass
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            d = json.load(open(path))
        except Exception:
            continue
        meta = d.get("_meta") or {}
        out = {}
        for k, v in d.items():
            if k in ("date", "symbol", "_meta"):
                continue
            try:
                out[float(k)] = v
            except (TypeError, ValueError):
                continue
        return out, meta
    return {}, {}


def _api_ticks(limit=15):
    con = _connect()
    rows = con.execute(
        "SELECT recv_ts, strike, side, ltp, bid, ask, oi, oi_chg, volume "
        "FROM ticks WHERE date(recv_ts)=date('now','localtime') "
        "ORDER BY recv_ts DESC LIMIT ?", (limit,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def _api_chain(atm_radius=400):
    """Latest CE/PE quotes for strikes around current spot (OI walls + LTP)."""
    con = _connect()
    spot_row = con.execute("SELECT value FROM spot ORDER BY recv_ts DESC LIMIT 1").fetchone()
    if not spot_row:
        con.close()
        return {"ok": False, "error": "no spot"}
    spot = spot_row["value"]
    lo, hi = spot - atm_radius, spot + atm_radius
    rows = con.execute(
        "SELECT strike, side, ltp, bid, ask, oi, oi_chg, volume, pct_chg, recv_ts "
        "FROM ticks WHERE date(recv_ts)=date('now','localtime') AND strike BETWEEN ? AND ? "
        "ORDER BY recv_ts, strike, side", (lo, hi)).fetchall()
    oi_rows = con.execute(
        "SELECT strike, side, oi, oi_chg, recv_ts FROM ticks "
        "WHERE date(recv_ts)=date('now','localtime') AND strike BETWEEN ? AND ? AND oi IS NOT NULL "
        "ORDER BY recv_ts, strike, side", (lo, hi)).fetchall()
    con.close()
    latest = {}
    for r in rows:
        key = (r["strike"], r["side"])
        if key not in latest or r["recv_ts"] >= latest[key]["recv_ts"]:
            latest[key] = dict(r)
    oi_latest = {}
    for r in oi_rows:
        key = (r["strike"], r["side"])
        if key not in oi_latest or r["recv_ts"] >= oi_latest[key]["recv_ts"]:
            oi_latest[key] = dict(r)
    strikes = sorted({k[0] for k in latest} | {k[0] for k in oi_latest})
    snap_oi, snap_meta = _load_snapshot_oi()
    chain = []
    for s in strikes:
        ce = latest.get((s, "CE")) or {}
        pe = latest.get((s, "PE")) or {}
        ce_oi = oi_latest.get((s, "CE")) or {}
        pe_oi = oi_latest.get((s, "PE")) or {}
        snap = snap_oi.get(s) or {}
        chain.append({
            "strike": s,
            "ce_ltp": ce.get("ltp"), "ce_oi": ce_oi.get("oi") if ce_oi.get("oi") is not None else snap.get("ce_oi"),
            "ce_oi_chg": ce_oi.get("oi_chg") if ce_oi.get("oi_chg") is not None else snap.get("ce_oi_chg"),
            "ce_vol": ce.get("volume"), "ce_ts": ce.get("recv_ts"),
            "pe_ltp": pe.get("ltp"), "pe_oi": pe_oi.get("oi") if pe_oi.get("oi") is not None else snap.get("pe_oi"),
            "pe_oi_chg": pe_oi.get("oi_chg") if pe_oi.get("oi_chg") is not None else snap.get("pe_oi_chg"),
            "pe_vol": pe.get("volume"), "pe_ts": pe.get("recv_ts"),
        })
    # quick PCR on OI
    ce_oi = sum((c["ce_oi"] or 0) for c in chain)
    pe_oi = sum((c["pe_oi"] or 0) for c in chain)
    return {"ok": True, "spot": round(spot, 1), "chain": chain,
            "pcr_oi": round(pe_oi / ce_oi, 3) if ce_oi else None,
            "oi_ts": snap_meta.get("timestamp", "")}


def _api_status():
    pid = os.path.exists("/tmp/opencode/recorder.pid") and open("/tmp/opencode/recorder.pid").read().strip() or "?"
    con = _connect()
    n_spot = con.execute("SELECT COUNT(*) FROM spot WHERE date(recv_ts)=date('now','localtime')").fetchone()[0]
    n_ticks = con.execute("SELECT COUNT(*) FROM ticks WHERE date(recv_ts)=date('now','localtime')").fetchone()[0]
    con.close()
    return {"recorder_pid": pid, "today_spot": n_spot, "today_ticks": n_ticks}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send_json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self):
        try:
            with open(HTML_PATH, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            body = b"live_dash.html not found"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/spot":
            return self._send_json(_api_spot())
        if u.path == "/api/ticks":
            q = parse_qs(u.query)
            try:
                n = int(q.get("n", ["8"])[0])
            except (TypeError, ValueError):
                n = 8
            n = max(1, min(n, 200))
            return self._send_json(_api_ticks(n))
        if u.path == "/api/chain":
            return self._send_json(_api_chain())
        if u.path == "/api/status":
            return self._send_json(_api_status())
        return self._send_html()


if __name__ == "__main__":
    print(f"live_dash: http://localhost:{PORT}  (ctrl+c to stop)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
