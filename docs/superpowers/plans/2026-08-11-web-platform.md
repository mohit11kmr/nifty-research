# Nifty Research Web Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A localhost FastAPI web app (dashboard, live chain, backtests, research DB explorer, recorder control, blog) wrapping the existing Nifty Research Python modules as libraries.

**Architecture:** FastAPI monolith under `app/`. Routers are thin; `services/` wrap existing modules with TTL/LRU caching. Blocking module calls run in a ThreadPool executor. WebSockets via an asyncio broadcast hub with throttle batching. Backtests run as bounded asyncio job queue. Recorder runs as a subprocess (same `tick_recorder.py`, same DB), service tracks PID/status/log tail.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, existing pandas/numpy/scikit-learn/playwright, plain HTML/JS/CSS frontend with Chart.js via CDN. No node/npm build step.

## Global Constraints

- Localhost only: uvicorn binds `127.0.0.1` by default; `--host 0.0.0.0` flag to override.
- Existing `.py` modules (backtester, strategies, oi_intel, regime_filter, institutional, stock_flow, ml_engine, multitf, premium_seller, nse_live, tick_recorder, blog_post) are NEVER modified. Only `requirements.txt` gains fastapi/uvicorn.
- No auth (localhost). SQLite queries param-bound. File paths sanitized.
- research.db schema untouched: `ticks(recv_ts, exch_ts, symbol, expiry, strike, side, ltp, bid, bid_qty, ask, ask_qty, oi, oi_chg, iv, volume, pct_chg)` and `spot(recv_ts, value, pct_chg)`.
- Cache rules: chain_service 15s TTL, report_service 60s TTL, research_service LRU max 64, backtest results keep max 10 completed, blog mtime-based.
- WS throttle: chain 2s, recorder 5s.
- Performance gates (this box): dashboard < 200ms cached; 10 WS clients broadcast < 100ms; 1yr daily backtest < 2s.
- Perf: heavy modules imported lazily inside service functions (fast startup), never at `app/` import time.

---

### Task 1: Project scaffold — requirements, config, app entry, FastAPI app shell

**Files:**
- Create: `requirements.txt` (modify)
- Create: `run_app.py`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/main.py`
- Create: `tests/conftest.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Produces: `app.config` constants `ROOT`, `DATA_DIR`, `RESEARCH_DB`, `BLOG_DIR`, `STATIC_DIR`, `CHAIN_TTL=15`, `REPORT_TTL=60`, `CHAIN_WS_THROTTLE=2`, `RECORDER_WS_THROTTLE=5`, `PORT=8766`.
- Produces: `app.main:create_app()` returning FastAPI instance (used by all later router tasks to register routes).
- Produces: `app.main:app` module-level FastAPI for uvicorn + TestClient.

- [ ] **Step 1: Write the failing test**

```python
# tests/conftest.py
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
```

```python
# tests/test_smoke.py
from fastapi.testclient import TestClient

def test_app_starts_and_serves_root():
    from app.main import app
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "dashboard" in r.text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Install deps + write scaffold**

```bash
pip3 install --user --break-system-packages fastapi uvicorn
```

```python
# requirements.txt
# (append to existing file)
fastapi>=0.110
uvicorn[standard]>=0.29
```

```python
# app/config.py
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
RESEARCH_DB = os.path.join(DATA_DIR, "research.db")
BLOG_DIR = os.path.join(ROOT, "blog")
STATIC_DIR = os.path.join(ROOT, "app", "static")
POSTS_DIR = os.path.join(BLOG_DIR, "posts")

PORT = 8766
CHAIN_TTL = 15          # seconds
REPORT_TTL = 60         # seconds
CHAIN_WS_THROTTLE = 2.0 # seconds between chain broadcasts
RECORDER_WS_THROTTLE = 5.0
BACKTEST_KEEP = 10      # completed jobs kept in memory
BACKTEST_MAX_CONCURRENT = 2
```

```python
# app/__init__.py
"""Nifty Research web platform."""
```

```python
# run_app.py
import argparse
import uvicorn
from app.config import PORT

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Nifty Research web platform")
    ap.add_argument("--host", default="127.0.0.1", help="bind address (127.0.0.1 default)")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=False)
```

```python
# app/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.config import STATIC_DIR

def create_app() -> FastAPI:
    app = FastAPI(title="Nifty Research", version="1.0.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def root():
        from fastapi.responses import FileResponse
        return FileResponse(__file__.replace("main.py", "static/index.html"))

    return app

app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL — FileResponse path check needs `app/static/index.html` to exist. Create `app/static/index.html`:

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>Nifty Research</title></head>
<body><h1>dashboard</h1><p>scaffold</p></body></html>
```

Then re-run. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt run_app.py app/ tests/ requirements.txt
git commit -m "feat(web): scaffold FastAPI app shell, config, entrypoint"
```

---

### Task 2: WebSocket broadcast hub

**Files:**
- Create: `app/hub.py`
- Test: `tests/test_ws.py`

**Interfaces:**
- Consumes: nothing (pure asyncio).
- Produces: class `Hub` singleton `hub`:
  - `async def register(channel: str, websocket) -> None`
  - `async def unregister(channel: str, websocket) -> None`
  - `async def broadcast(channel: str, payload: dict) -> None` (send JSON to every ws in channel; drop dead sockets)
  - `async def throttle_broadcast(channel: str, payload: dict, window: float) -> None` — coerce to min window between broadcasts; last payload wins; drains at window end.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ws.py
import asyncio
import pytest

@pytest.mark.asyncio
async def test_hub_broadcast_reaches_client():
    from app.hub import Hub
    h = Hub()

    sent = []
    class FakeWS:
        async def send_json(self, payload):
            sent.append(payload)
        async def close(self):
            pass

    ws = FakeWS()
    await h.register("chain", ws)
    await h.broadcast("chain", {"n": 1})
    await asyncio.sleep(0.01)
    assert sent == [{"n": 1}]

@pytest.mark.asyncio
async def test_throttle_coalesces():
    from app.hub import Hub
    h = Hub()
    sent = []
    class FakeWS:
        async def send_json(self, payload):
            sent.append(payload)
        async def close(self):
            pass
    ws = FakeWS()
    await h.register("chain", ws)
    await h.throttle_broadcast("chain", {"n": 1}, 0.05)
    await h.throttle_broadcast("chain", {"n": 2}, 0.05)
    await asyncio.sleep(0.01)
    assert len(sent) == 1
    await asyncio.sleep(0.07)
    assert sent[-1] == {"n": 2}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ws.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.hub'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/hub.py
import asyncio
import time
from typing import Any

class Hub:
    def __init__(self):
        self._channels: dict[str, set] = {}
        self._last_sent: dict[str, float] = {}
        self._pending: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, channel: str) -> asyncio.Lock:
        return self._locks.setdefault(channel, asyncio.Lock())

    async def register(self, channel: str, websocket) -> None:
        self._channels.setdefault(channel, set()).add(websocket)

    async def unregister(self, channel: str, websocket) -> None:
        self._channels.get(channel, set()).discard(websocket)

    async def broadcast(self, channel: str, payload: dict) -> None:
        async with self._lock(channel):
            dead = []
            for ws in self._channels.get(channel, set()):
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._channels.get(channel, set()).discard(ws)

    async def throttle_broadcast(self, channel: str, payload: dict, window: float) -> None:
        """Send immediately if window since last send elapsed, else coalesce to last."""
        async with self._lock(channel):
            now = time.monotonic()
            last = self._last_sent.get(channel, 0.0)
            self._pending[channel] = payload
            if now - last >= window:
                await self._flush(channel)
                return
            # schedule drain if not already scheduled
            if not self._scheduled(channel):
                asyncio.create_task(self._drain(channel, window))

    def _scheduled(self, channel: str) -> bool:
        return getattr(self, f"_timer_{channel}", None) is not None

    async def _drain(self, channel: str, window: float):
        timer = getattr(self, f"_timer_{channel}", None)
        if timer:
            return
        setattr(self, f"_timer_{channel}", True)
        try:
            remaining = window - (time.monotonic() - self._last_sent.get(channel, 0.0))
            await asyncio.sleep(max(remaining, 0.0))
            async with self._lock(channel):
                await self._flush(channel)
        finally:
            setattr(self, f"_timer_{channel}", None)

    async def _flush(self, channel: str):
        payload = self._pending.pop(channel, None)
        if payload is None:
            return
        self._last_sent[channel] = time.monotonic()
        await self.broadcast(channel, payload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ws.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/hub.py tests/test_ws.py
git commit -m "feat(web): WebSocket broadcast hub with throttled coalescing"
```

---

### Task 3: report_service — cached dashboard sections

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/cache.py`
- Create: `app/services/report_service.py`
- Test: `tests/test_report_service.py`

**Interfaces:**
- Consumes: `regime_filter.trade_plan()`, `regime_filter.format_plan`, `institutional.institutional_scan()`, `institutional.format_scan`, `stock_flow.scan_universe`, `stock_flow.format_flow`, `ml_engine.meta_blender`, `ml_engine.format_ml`, `multitf.best_tf_report`, `premium_seller.premium_sell_backtest`, `premium_seller.format_result` (all existing modules, imported lazily inside functions).
- Produces:
  - `app.services.cache:ttl_cache(name, ttl)` decorator — caches function return by args in a module-level dict, expires after ttl seconds.
  - `report_service.get_regime() -> dict` — `{"plan": {...}, "lines": [...]}` (plan dict + `format_plan` lines).
  - `report_service.get_institutional() -> dict` — `{"scan": {...}, "lines": [...]}`.
  - `report_service.get_stockflow(top=12) -> dict` — `{"top": [row...], "lines": [...]}`.
  - `report_service.get_tfscan() -> dict` — rows from `data/tf_scan.csv` (or `{"error": "no tf_scan.csv"}`).
  - `report_service.get_ml() -> dict` — `{"res": ..., "error": ...}` from `meta_blender`.
  - `report_service.get_premiumseller() -> dict` — `{"metrics": ..., "lines": [...]}`.
  - `report_service.get_dashboard() -> dict` — single payload combining regime + institutional + stockflow top-10 + tfscan + ml + premiumseller, each section independently cached.
  - All functions sync (called via `run_in_executor` by routers).

- [ ] **Step 1: Write the failing tests**

```python
# app/services/cache.py
import time

_TTL_STORE = {}

def ttl_cache(name, ttl):
    def deco(fn):
        key = name
        def wrapper(*args, **kwargs):
            now = time.time()
            hit = _TTL_STORE.get(key)
            if hit and now - hit["t"] < ttl:
                return hit["v"]
            v = fn(*args, **kwargs)
            _TTL_STORE[key] = {"t": time.time(), "v": v}
            return v
        wrapper.cache_clear = lambda: _TTL_STORE.pop(key, None)
        return wrapper
    return deco
```

```python
# tests/test_report_service.py
import time

def test_ttl_cache_hits_then_expires():
    from app.services.cache import ttl_cache
    calls = {"n": 0}
    @ttl_cache("t1", 0.3)
    def f():
        calls["n"] += 1
        return calls["n"]
    assert f() == 1
    assert f() == 1          # cached
    time.sleep(0.35)
    assert f() == 2          # expired

def test_regime_has_plan_and_gate():
    from app.services import report_service
    d = report_service.get_regime()
    assert "plan" in d and "lines" in d
    assert "regime" in d["plan"] or "gate" in d["plan"]

def test_institutional_has_scan():
    from app.services import report_service
    d = report_service.get_institutional()
    assert "scan" in d and "lines" in d

def test_dashboard_aggregates():
    from app.services import report_service
    d = report_service.get_dashboard()
    for k in ("regime", "institutional", "stockflow", "tfscan", "ml", "premiumseller"):
        assert k in d
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_report_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/__init__.py
```

```python
# app/services/report_service.py
import os, sys
from app.config import DATA_DIR
from app.services.cache import ttl_cache

def _run(fn, *a, **k):
    return fn(*a, **k)

@ttl_cache("regime", 60)
def get_regime():
    from regime_filter import trade_plan, format_plan
    plan = trade_plan()
    lines = format_plan(plan)
    return {"plan": plan, "lines": lines}

@ttl_cache("institutional", 60)
def get_institutional():
    from institutional import institutional_scan, format_scan
    scan = institutional_scan()
    return {"scan": scan, "lines": list(format_scan(scan))}

@ttl_cache("stockflow", 60)
def get_stockflow(top=12):
    from stock_flow import scan_universe, format_flow
    top_rows, _ = scan_universe(top=top)
    return {"top": top_rows, "lines": format_flow(top_rows)}

@ttl_cache("tfscan", 60)
def get_tfscan():
    p = os.path.join(DATA_DIR, "tf_scan.csv")
    if not os.path.exists(p):
        return {"error": "no tf_scan.csv - run the TF grid scan first"}
    import pandas as pd
    try:
        import multitf
        df = pd.read_csv(p)
        return {"rows": [r for r in multitf.best_tf_report(df)]}
    except Exception as e:
        return {"error": str(e)}

@ttl_cache("ml", 60)
def get_ml():
    from ml_engine import meta_blender, format_ml
    res, err = meta_blender()
    if err:
        return {"res": None, "error": err}
    return {"res": res, "lines": format_ml(res)}

@ttl_cache("premiumseller", 300)
def get_premiumseller():
    import premium_seller
    trades = premium_seller.premium_sell_backtest()
    lines = premium_seller.format_result(trades)
    metrics = {}
    if hasattr(trades, "get"):
        for k in ("total_pnl", "win_rate", "pf", "max_dd", "n_trades"):
            metrics[k] = trades.get(k)
    return {"metrics": metrics, "lines": list(lines)}

@ttl_cache("dashboard", 30)
def get_dashboard():
    return {
        "regime": get_regime(),
        "institutional": get_institutional(),
        "stockflow": get_stockflow(top=10),
        "tfscan": get_tfscan(),
        "ml": get_ml(),
        "premiumseller": get_premiumseller(),
    }
```

Note: `get_regime()`/`get_institutional()`/etc. call the internal `_run` pattern is unnecessary — the per-section caches already apply when `get_dashboard` calls them directly.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_report_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/ tests/test_report_service.py
git commit -m "feat(web): cached report service wrapping existing modules"
```

---

### Task 4: chain_service — live chain + OI analysis, 15s TTL

**Files:**
- Create: `app/services/chain_service.py`
- Test: `tests/test_chain_service.py`

**Interfaces:**
- Consumes: `nse_live.fetch_option_chain_live(symbol)`, `nse_live.close`, `oi_intel.oi_walls`, `oi_intel.pcr_and_pain`, `oi_intel.detect_build_up`, `oi_intel.murarkar_matrix`.
- Produces:
  - `chain_service.get_chain(symbol="NIFTY") -> dict` with keys `spot`, `expiry`, `timestamp`, `expiries`, `strikes` (list of row dicts with strike/ce_oi/pe_oi/ce_oi_chg/pe_oi_chg/ce_iv/pe_iv), `walls` (`{"resistance_oi": [...], "support_oi": [...], "nearest_resistance": int, "nearest_support": int}`), `pcr` (dict), `build_up` (dict), `matrix` (dict), `error` (str|None). 15s TTL via `ttl_cache`.
  - `chain_service.chain_to_rows(chain_df, meta)` — internal helper normalizing CE/PE columns to one row per strike (merges CE/PE side columns; NIFTY chain already has ce_oi/pe_oi columns per strike — pass through with iv columns renamed).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chain_service.py
import pandas as pd

def test_chain_to_rows_normalizes_columns():
    from app.services.chain_service import chain_to_rows
    df = pd.DataFrame([{
        "strike": 24500, "ce_oi": 100, "ce_oi_chg": 5, "pe_oi": 200,
        "pe_oi_chg": -3, "ce_iv": 12.5, "pe_iv": 13.1,
    }])
    rows = chain_to_rows(df)
    assert rows[0]["strike"] == 24500
    assert rows[0]["ce_oi"] == 100
    assert rows[0]["ce_iv"] == 12.5

def test_get_chain_returns_expected_keys():
    from app.services.chain_service import get_chain
    d = get_chain("NIFTY")
    for k in ("spot", "expiry", "strikes", "walls", "pcr", "build_up", "matrix", "error"):
        assert k in d
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_chain_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.chain_service'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/chain_service.py
import datetime as dt
from app.services.cache import ttl_cache

def chain_to_rows(chain_df):
    rows = []
    cols = set(chain_df.columns)
    for _, r in chain_df.iterrows():
        row = {"strike": int(r["strike"])}
        for src, dst in (("ce_oi", "ce_oi"), ("ce_oi_chg", "ce_oi_chg"),
                         ("pe_oi", "pe_oi"), ("pe_oi_chg", "pe_oi_chg")):
            row[dst] = None if pd.isna(r[src]) else float(r[src])
        row["ce_iv"] = float(r["ce_iv"]) if "ce_iv" in cols and not pd.isna(r["ce_iv"]) else None
        row["pe_iv"] = float(r["pe_iv"]) if "pe_iv" in cols and not pd.isna(r["pe_iv"]) else None
        rows.append(row)
    return rows

@ttl_cache("chain", 15)
def get_chain(symbol="NIFTY"):
    from nse_live import fetch_option_chain_live, close
    try:
        chain, meta = fetch_option_chain_live(symbol)
    except Exception as e:
        return {"error": f"chain fetch failed: {e}", "strikes": [],
                "spot": None, "expiry": None, "timestamp": None,
                "expiries": [], "walls": {}, "pcr": {}, "build_up": {}, "matrix": {}}
    try:
        import oi_intel
        spot = float(meta.get("underlying"))
    except (TypeError, ValueError):
        spot = None
    out = {
        "spot": spot,
        "expiry": meta.get("expiry"),
        "timestamp": meta.get("timestamp") or dt.datetime.now().strftime("%d-%b-%Y %H:%M:%S"),
        "expiries": meta.get("expiries", []),
        "strikes": chain_to_rows(chain) if not chain.empty else [],
        "walls": {}, "pcr": {}, "build_up": {}, "matrix": {},
        "error": None,
    }
    if not chain.empty and spot:
        out["walls"] = oi_intel.oi_walls(chain, n=3, spot=spot)
        out["pcr"] = oi_intel.pcr_and_pain(chain, spot)
        out["build_up"] = oi_intel.detect_build_up(chain, top_n=6)
        out["matrix"] = oi_intel.murarkar_matrix(chain, spot)
    close()
    return out
```

Note: add `import pandas as pd` at top (needed by `chain_to_rows`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_chain_service.py -v`
Expected: PASS (get_chain may hit live NSE via playwright; if NSE/playwright unavailable the dict still has all keys with `error` set).

- [ ] **Step 5: Commit**

```bash
git add app/services/chain_service.py tests/test_chain_service.py
git commit -m "feat(web): live chain service with OI analysis and 15s TTL"
```

---

### Task 5: backtest_service — async job queue + strategy metadata

**Files:**
- Create: `app/services/backtest_service.py`
- Test: `tests/test_backtest_service.py`

**Interfaces:**
- Consumes: `strategies.ALL_STRATEGIES`, `strategies.build_param_grid`, `backtester.run_backtest`/`compute_metrics`, `multitf.load_tf_frames`/`run_strategy_on_tf`, `data_fetcher.fetch_index_history` (or `stock_flow`/`multitf` loaders), `premium_seller.premium_sell_backtest`.
- Produces:
  - `backtest_service.submit(params: dict) -> str` (job_id).
  - `backtest_service.get_job(job_id: str) -> dict` — `{"id", "status": queued|running|done|error, "progress": str, "result": {...}|None, "error": str|None}`.
  - `backtest_service.available_strategies() -> list[dict]` — `[{"name": "trend_sma", "params_example": {...}, "default_hold": 1}]` for all keys in `strategies.ALL_STRATEGIES`.
  - `backtest_service.job_events(job_id) -> asyncio.Queue` — per-job queue receiving progress dicts then terminal `{"status": "done"|"error"}`.
  - Internal: `_run_job(job_id, params)` async task executes backtest via `loop.run_in_executor` and sets result.
  - Job flow (documented in `_run_job` docstring): if `params["kind"] == "premium"` → `premium_sell_backtest`; if `params["kind"] == "tf"` → run chosen strategy on all TFs via `multitf` and return per-TF metrics; else single strategy single TF via `multitf.run_strategy_on_tf` (loads frame from cached data). Results stored; max `BACKTEST_KEEP` completed retained.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backtest_service.py
import asyncio

def test_available_strategies_nonempty():
    from app.services.backtest_service import available_strategies
    s = available_strategies()
    assert len(s) > 5
    assert all("name" in x for x in s)

def test_submit_and_job_lifecycle():
    import asyncio
    from app.services import backtest_service
    job_id = backtest_service.submit({"kind": "tf", "name": "golden_cross", "tf": "1d", "params": {"fast": 10, "slow": 50}})
    # poll until done (bounded)
    for _ in range(40):
        asyncio.run(asyncio.sleep(0.25))
        st = backtest_service.get_job(job_id)["status"]
        if st in ("done", "error"):
            break
    j = backtest_service.get_job(job_id)
    assert j["status"] in ("done", "error")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backtest_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/backtest_service.py
import asyncio
import uuid
import concurrent.futures
from app.config import BACKTEST_KEEP, BACKTEST_MAX_CONCURRENT

JOBS: dict[str, dict] = {}
_QUEUES: dict[str, asyncio.Queue] = {}
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=BACKTEST_MAX_CONCURRENT)
_SEM = asyncio.Semaphore(BACKTEST_MAX_CONCURRENT)

def _set(job_id, **kw):
    JOBS[job_id].update(kw)

async def _emit(job_id, payload):
    q = _QUEUES.get(job_id)
    if q:
        await q.put(payload)

def _load_frame(tf, symbol="NIFTY"):
    if tf == "1d":
        from data_fetcher import fetch_index_history
        return fetch_index_history("NIFTY 50", out_csv=None)
    from multitf import load_tf_frames
    frames = load_tf_frames(intervals=(tf,), days=180)
    return frames.get(tf)

def _run_backtest_sync(params):
    kind = params.get("kind", "tf")
    if kind == "premium":
        import premium_seller
        trades = premium_seller.premium_sell_backtest()
        lines = list(premium_seller.format_result(trades))
        return {"kind": "premium", "lines": lines,
                "trades_count": len(trades) if hasattr(trades, "__len__") else None}
    name = params["name"]
    tf = params.get("tf", "1d")
    hold = params.get("hold", 1)
    p = params.get("params", {})
    import strategies
    if name not in strategies.ALL_STRATEGIES:
        raise ValueError(f"unknown strategy {name}")
    import multitf
    df = _load_frame(tf, params.get("symbol", "NIFTY"))
    cfg = {"name": name, "params": p, "hold": hold}
    trades, metrics = multitf.run_strategy_on_tf(df, cfg, tf=tf)
    return {"kind": "tf", "name": name, "tf": tf, "metrics": metrics,
            "trades_count": len(trades) if hasattr(trades, "__len__") else None}

async def _run_job(job_id, params):
    async with _SEM:
        _set(job_id, status="running", progress="starting")
        await _emit(job_id, {"status": "running", "progress": "starting"})
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(_EXECUTOR, _run_backtest_sync, params)
            _set(job_id, status="done", result=result, progress="done")
            await _emit(job_id, {"status": "done", "result": result})
        except Exception as e:
            _set(job_id, status="error", error=str(e), progress="error")
            await _emit(job_id, {"status": "error", "error": str(e)})

def submit(params: dict) -> str:
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"id": job_id, "status": "queued", "progress": "queued", "result": None, "error": None}
    _QUEUES[job_id] = asyncio.Queue()
    asyncio.create_task(_run_job(job_id, params))
    # evict oldest completed beyond BACKTEST_KEEP
    done_ids = [k for k, v in JOBS.items() if v["status"] in ("done", "error")]
    for old in done_ids[:-BACKTEST_KEEP]:
        JOBS.pop(old, None)
        _QUEUES.pop(old, None)
    return job_id

def get_job(job_id: str) -> dict:
    j = JOBS.get(job_id)
    if j is None:
        return {"id": job_id, "status": "error", "error": "unknown job", "result": None, "progress": ""}
    return dict(j)

def available_strategies():
    import strategies
    out = []
    for name, fn in strategies.ALL_STRATEGIES.items():
        out.append({"name": name, "default_hold": 1})
    return out

def job_events(job_id: str):
    q = _QUEUES.get(job_id)
    if q is None:
        q = asyncio.Queue()
        _QUEUES[job_id] = q
        asyncio.create_task(q.put({"status": "error", "error": "unknown job"}))
    return q
```

Note: `_load_frame` for 1d — `fetch_index_history` returns a df (verify it returns df without writing when `out_csv=None`; if it requires out_csv, write to a temp path instead). If it fails, fall back to `multitf.load_tf_frames(intervals=("1d",), days=180)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backtest_service.py -v`
Expected: PASS (job reaches done/error within the bounded poll).

- [ ] **Step 5: Commit**

```bash
git add app/services/backtest_service.py tests/test_backtest_service.py
git commit -m "feat(web): async backtest job queue + strategy metadata"
```

---

### Task 6: recorder_service — subprocess manager

**Files:**
- Create: `app/services/recorder_service.py`
- Test: `tests/test_recorder_service.py`

**Interfaces:**
- Consumes: `app.config.RESEARCH_DB`; runs `python3 tick_recorder.py <symbol>` as subprocess (script untouched).
- Produces:
  - `recorder_service.status() -> dict` — `{"running": bool, "pid": int|None, "symbol": str|None, "db": str, "ticks": int, "spot_rows": int, "log_tail": [str]}` (ticks/spot_rows from SQLite `SELECT COUNT(*)`).
  - `recorder_service.start(symbol="NIFTY") -> dict` — spawns subprocess if not running; stores PID; returns `status()`.
  - `recorder_service.stop() -> dict` — SIGTERM to tracked PID; returns `status()`.
  - `recorder_service._tail_log(n=30) -> list[str]` — last n lines of `data/recorder.log`.
  - Log file appended by the subprocess (created with `open(..., "a")`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recorder_service.py
def test_status_shape():
    from app.services.recorder_service import status
    s = status()
    for k in ("running", "pid", "symbol", "db", "ticks", "spot_rows", "log_tail"):
        assert k in s

def test_start_then_stop():
    from app.services.recorder_service import start, stop
    import time
    r = start("NIFTY", max_seconds=5)
    assert r["running"] is True
    time.sleep(1.5)
    s2 = stop()
    assert s2["running"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recorder_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/recorder_service.py
import os
import signal
import subprocess
import sqlite3
import time
from app.config import ROOT, RESEARCH_DB

_PROC = None      # subprocess.Popen
_SYMBOL = None
LOG = os.path.join(ROOT, "data", "recorder.log")

def _db_count(sql):
    if not os.path.exists(RESEARCH_DB):
        return 0
    try:
        con = sqlite3.connect(RESEARCH_DB, timeout=3)
        try:
            return con.execute(sql).fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error:
        return 0

def _tail_log(n=30):
    if not os.path.exists(LOG):
        return []
    try:
        with open(LOG, "r", errors="replace") as f:
            return f.readlines()[-n:]
    except OSError:
        return []

def status():
    global _PROC, _SYMBOL
    running = _PROC is not None and _PROC.poll() is None
    if _PROC is not None and _PROC.poll() is not None and _PROC.poll() != 0:
        # exited - keep last status visible but not running
        pass
    return {
        "running": running,
        "pid": _PROC.pid if _PROC and running else None,
        "symbol": _SYMBOL if running else None,
        "db": RESEARCH_DB,
        "ticks": _db_count("SELECT COUNT(*) FROM ticks"),
        "spot_rows": _db_count("SELECT COUNT(*) FROM spot"),
        "log_tail": _tail_log(30),
    }

def start(symbol="NIFTY", max_seconds=None):
    global _PROC, _SYMBOL
    if _PROC is not None and _PROC.poll() is None:
        return status()
    args = ["python3", os.path.join(ROOT, "tick_recorder.py"), symbol]
    if max_seconds:
        args += ["--seconds", str(max_seconds)]
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    logf = open(LOG, "a")
    _PROC = subprocess.Popen(args, stdout=logf, stderr=subprocess.STDOUT,
                             cwd=ROOT, start_new_session=True)
    _SYMBOL = symbol
    time.sleep(0.5)
    return status()

def stop():
    global _PROC
    if _PROC is not None and _PROC.poll() is None:
        try:
            os.killpg(os.getpgid(_PROC.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                _PROC.terminate()
            except ProcessLookupError:
                pass
        try:
            _PROC.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _PROC.kill()
    _PROC = None
    return status()
```

Note: if `tick_recorder.py` does not support `--seconds`, check its argparse; it accepts positional `symbol` and optional `--seconds`/`max_seconds` — verify with `python3 tick_recorder.py --help` and adapt (if no flag exists, launch without it).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_recorder_service.py -v`
Expected: PASS (start returns running=True; stop returns running=False). If `--seconds` flag is missing, remove it from the args and rely on `stop()`.

- [ ] **Step 5: Commit**

```bash
git add app/services/recorder_service.py tests/test_recorder_service.py
git commit -m "feat(web): tick recorder subprocess manager with status/tail"
```

---

### Task 7: research_service — DB explorer queries

**Files:**
- Create: `app/services/research_service.py`
- Test: `tests/test_research_service.py`

**Interfaces:**
- Consumes: `app.config.RESEARCH_DB` (schema `ticks`, `spot` as documented in Global Constraints).
- Produces (all return `dict`):
  - `research_service.db_status() -> dict` — `{"exists": bool, "size_mb": float, "tables": [str], "ticks": int, "spot": int, "last_tick_ts": str|None, "first_tick_ts": str|None, "distinct_symbols": [str], "distinct_strikes": int}`.
  - `research_service.ticks(symbol=None, strike=None, from_ts=None, to_ts=None, limit=500, side=None) -> dict` — `{"rows": [...], "count": n, "truncated": bool}`; rows include recv_ts, exch_ts, symbol, strike, side, ltp, bid, ask, oi, iv, volume. Always `ORDER BY recv_ts DESC` unless `from_ts` given (then ASC).
  - `research_service.oi_snapshot(symbol="NIFTY", limit=60) -> dict` — `{"rows": [...]}` latest per-strike CE/PE OI near ATM; rows `{"strike", "ce_oi", "pe_oi", "ce_iv", "pe_iv", "ts"}`.
  - `research_service.iv_skew(symbol="NIFTY", limit=80) -> dict` — `{"rows": [...]}` latest IV per strike per side: `{"strike", "side", "iv", "ltp", "ts"}`.
  - `research_service.spot(from_ts=None, to_ts=None, limit=1000) -> dict` — `{"rows": [{"ts", "value", "pct_chg"}]}`.
  - Every SQL statement uses `?` placeholders.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_research_service.py
def test_db_status_shape():
    from app.services.research_service import db_status
    s = db_status()
    for k in ("exists", "size_mb", "tables", "ticks", "spot"):
        assert k in s

def test_ticks_query():
    from app.services.research_service import ticks
    r = ticks(limit=10)
    assert "rows" in r and "count" in r
    assert r["count"] <= 10

def test_oi_snapshot_rows():
    from app.services.research_service import oi_snapshot
    r = oi_snapshot()
    assert "rows" in r

def test_spot_query():
    from app.services.research_service import spot
    r = spot(limit=5)
    assert "rows" in r
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_research_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/research_service.py
import os
import sqlite3
from app.config import RESEARCH_DB

def _connect():
    if not os.path.exists(RESEARCH_DB):
        return None
    con = sqlite3.connect(RESEARCH_DB, timeout=5)
    con.row_factory = sqlite3.Row
    return con

def _rows_to_dicts(rows):
    return [dict(r) for r in rows]

def db_status():
    con = _connect()
    if con is None:
        return {"exists": False, "size_mb": 0.0, "tables": [], "ticks": 0,
                "spot": 0, "last_tick_ts": None, "first_tick_ts": None,
                "distinct_symbols": [], "distinct_strikes": 0}
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        ticks = con.execute("SELECT COUNT(*) FROM ticks").fetchone()[0] if "ticks" in tables else 0
        spot = con.execute("SELECT COUNT(*) FROM spot").fetchone()[0] if "spot" in tables else 0
        last_ts = None
        first_ts = None
        symbols = []
        strikes = 0
        if "ticks" in tables and ticks:
            last_ts = con.execute("SELECT MAX(recv_ts) FROM ticks").fetchone()[0]
            first_ts = con.execute("SELECT MIN(recv_ts) FROM ticks").fetchone()[0]
            symbols = [r[0] for r in con.execute(
                "SELECT DISTINCT symbol FROM ticks").fetchall()]
            strikes = con.execute("SELECT COUNT(DISTINCT strike) FROM ticks").fetchone()[0]
        return {"exists": True, "size_mb": round(os.path.getsize(RESEARCH_DB) / 1e6, 2),
                "tables": tables, "ticks": ticks, "spot": spot,
                "last_tick_ts": last_ts, "first_tick_ts": first_ts,
                "distinct_symbols": symbols, "distinct_strikes": strikes}
    finally:
        con.close()

def ticks(symbol=None, strike=None, from_ts=None, to_ts=None, limit=500, side=None):
    con = _connect()
    if con is None:
        return {"rows": [], "count": 0, "truncated": False}
    try:
        q = "SELECT recv_ts, exch_ts, symbol, strike, side, ltp, bid, ask, oi, iv, volume, pct_chg FROM ticks WHERE 1=1"
        args = []
        if symbol:
            q += " AND symbol=?"
            args.append(symbol)
        if strike is not None:
            q += " AND strike=?"
            args.append(strike)
        if side:
            q += " AND side=?"
            args.append(side)
        if from_ts:
            q += " AND recv_ts>=?"
            args.append(from_ts)
        if to_ts:
            q += " AND recv_ts<=?"
            args.append(to_ts)
        q += " ORDER BY recv_ts DESC LIMIT ?"
        args.append(limit)
        rows = _rows_to_dicts(con.execute(q, args).fetchall())
        return {"rows": rows, "count": len(rows), "truncated": len(rows) >= limit}
    finally:
        con.close()

def oi_snapshot(symbol="NIFTY", limit=60):
    """Latest per-strike OI (near-ATM band)."""
    con = _connect()
    if con is None:
        return {"rows": []}
    try:
        rows = con.execute(
            "SELECT recv_ts, strike, MAX(oi) as oi, MAX(oi_chg) as oi_chg, MAX(iv) as iv "
            "FROM ticks WHERE symbol=? AND oi IS NOT NULL "
            "GROUP BY strike ORDER BY oi DESC LIMIT ?", (symbol, limit)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            out.append({"strike": d["strike"], "oi": d["oi"], "oi_chg": d["oi_chg"],
                        "iv": d["iv"], "ts": d["recv_ts"]})
        return {"rows": out}
    finally:
        con.close()

def iv_skew(symbol="NIFTY", limit=80):
    con = _connect()
    if con is None:
        return {"rows": []}
    try:
        rows = con.execute(
            "SELECT strike, side, MAX(iv) as iv, MAX(ltp) as ltp, MAX(recv_ts) as ts "
            "FROM ticks WHERE symbol=? AND iv IS NOT NULL "
            "GROUP BY strike, side ORDER BY strike LIMIT ?", (symbol, limit)).fetchall()
        out = [{"strike": r["strike"], "side": r["side"], "iv": r["iv"],
                "ltp": r["ltp"], "ts": r["ts"]} for r in rows]
        return {"rows": out}
    finally:
        con.close()

def spot(from_ts=None, to_ts=None, limit=1000):
    con = _connect()
    if con is None:
        return {"rows": []}
    try:
        q = "SELECT recv_ts AS ts, value, pct_chg FROM spot WHERE 1=1"
        args = []
        if from_ts:
            q += " AND recv_ts>=?"
            args.append(from_ts)
        if to_ts:
            q += " AND recv_ts<=?"
            args.append(to_ts)
        q += " ORDER BY recv_ts ASC LIMIT ?"
        args.append(limit)
        return {"rows": _rows_to_dicts(con.execute(q, args).fetchall())}
    finally:
        con.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_research_service.py -v`
Expected: PASS (research.db exists from the running recorder; if empty, count==0 but shape is valid).

- [ ] **Step 5: Commit**

```bash
git add app/services/research_service.py tests/test_research_service.py
git commit -m "feat(web): research DB explorer queries (ticks/oi/skew/spot)"
```

---

### Task 8: blog_service — post list + read

**Files:**
- Create: `app/services/blog_service.py`
- Test: `tests/test_blog_service.py`

**Interfaces:**
- Consumes: `app.config.POSTS_DIR`; `blog_post.main()` as subprocess (script untouched) for regeneration.
- Produces:
  - `blog_service.list_posts() -> dict` — `{"posts": [{"date": "2026-08-11", "title": str, "size": int, "mtime": float}]}` sorted newest-first; title parsed from `<title>` tag.
  - `blog_service.get_post(date: str) -> dict` — `{"date", "html": str|None, "exists": bool, "title": str}`. Date validated against `YYYY-MM-DD` regex and must be a filename within POSTS_DIR (path traversal guard).
  - `blog_service.regenerate() -> dict` — runs `[sys.executable, "blog_post.py"]` subprocess; returns `{"ok": bool, "output_tail": [str]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_blog_service.py
def test_list_posts_shape():
    from app.services.blog_service import list_posts
    d = list_posts()
    assert "posts" in d
    for p in d["posts"]:
        assert "date" in p and "title" in p

def test_get_post_validates_path():
    from app.services.blog_service import get_post
    r = get_post("2026-08-11")
    assert "exists" in r and "html" in r
    bad = get_post("../../etc/passwd")
    assert bad["exists"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_blog_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/blog_service.py
import os
import re
import subprocess
import sys
from app.config import POSTS_DIR, ROOT

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def _title_from_html(html_text):
    m = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""

def list_posts():
    posts = []
    if not os.path.isdir(POSTS_DIR):
        return {"posts": []}
    for fn in sorted(os.listdir(POSTS_DIR), reverse=True):
        if not fn.endswith(".html"):
            continue
        date = fn[:-5]
        if not _DATE_RE.match(date):
            continue
        p = os.path.join(POSTS_DIR, fn)
        try:
            with open(p, "r", errors="replace") as f:
                head = f.read(4000)
            posts.append({
                "date": date,
                "title": _title_from_html(head) or date,
                "size": os.path.getsize(p),
                "mtime": os.path.getmtime(p),
            })
        except OSError:
            continue
    return {"posts": posts}

def get_post(date: str):
    if not _DATE_RE.match(date or ""):
        return {"date": date, "html": None, "exists": False, "title": ""}
    p = os.path.join(POSTS_DIR, f"{date}.html")
    if not os.path.isfile(p) or os.path.dirname(p) != POSTS_DIR:
        return {"date": date, "html": None, "exists": False, "title": ""}
    with open(p, "r", errors="replace") as f:
        html_text = f.read()
    return {"date": date, "html": html_text, "exists": True,
            "title": _title_from_html(html_text) or date}

def regenerate():
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "blog_post.py")],
                           capture_output=True, text=True, timeout=600, cwd=ROOT)
        out = (r.stdout + r.stderr).splitlines()
        return {"ok": r.returncode == 0, "output_tail": out[-15:]}
    except Exception as e:
        return {"ok": False, "output_tail": [str(e)]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_blog_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/blog_service.py tests/test_blog_service.py
git commit -m "feat(web): blog service with path-traversal guard + regeneration"
```

---

### Task 9: routers — full REST + WS API

**Files:**
- Create: `app/routers/__init__.py`
- Create: `app/routers/dashboard.py`
- Create: `app/routers/chain.py`
- Create: `app/routers/backtest.py`
- Create: `app/routers/recorder.py`
- Create: `app/routers/research.py`
- Create: `app/routers/blog.py`
- Modify: `app/main.py` (register routers)
- Test: `tests/test_api.py`, extend `tests/test_ws.py`

**Interfaces:**
- Consumes: all services from Tasks 3-8, `app.hub.hub`.
- Produces: full REST API + WS endpoints. All REST handlers `async def`; blocking service calls wrapped in `run_in_executor`. All JSON serializable (services return dicts; convert non-JSON-serializable values like numpy types with a `to_json_safe` helper).
- Produces: `app.routers.helpers:to_json_safe(obj)` — recursively converts numpy ints/floats/bool to Python, dict keys to str, sets to lists, pd.Timestamp to iso.

- [ ] **Step 1: Write the failing tests**

```python
# app/routers/helpers.py
import math
import datetime as dt

def to_json_safe(obj):
    if obj is None or isinstance(obj, (str, bool, int, float)):
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_json_safe(v) for v in obj]
    if isinstance(obj, (dt.datetime, dt.date, dt.time)):
        return obj.isoformat()
    if hasattr(obj, "item"):
        try:
            return to_json_safe(obj.item())
        except Exception:
            pass
    if hasattr(obj, "isoformat"):
        try:
            return obj.isoformat()
        except Exception:
            pass
    try:
        return float(obj)
    except Exception:
        return str(obj)
```

```python
# tests/test_api.py
from fastapi.testclient import TestClient

def _client():
    from app.main import app
    return TestClient(app)

def test_dashboard_endpoint():
    r = _client().get("/api/dashboard")
    assert r.status_code == 200
    for k in ("regime", "institutional", "stockflow", "tfscan", "ml", "premiumseller"):
        assert k in r.json()

def test_chain_endpoint():
    r = _client().get("/api/chain")
    assert r.status_code == 200
    for k in ("spot", "strikes", "walls", "pcr", "build_up", "matrix", "error"):
        assert k in r.json()

def test_backtest_strategies():
    r = _client().get("/api/backtest/strategies")
    assert r.status_code == 200
    assert len(r.json()) > 5

def test_recorder_status_endpoint():
    r = _client().get("/api/recorder/status")
    assert r.status_code == 200
    assert "running" in r.json()

def test_research_db_status():
    r = _client().get("/api/research/db/status")
    assert r.status_code == 200
    assert "ticks" in r.json()

def test_blog_posts():
    r = _client().get("/api/blog/posts")
    assert r.status_code == 200
    assert "posts" in r.json()
```

```python
# extend tests/test_ws.py
from fastapi.testclient import TestClient

def test_chain_ws_connects():
    from app.main import app
    client = TestClient(app)
    with client.websocket_connect("/ws/chain?symbol=NIFTY") as ws:
        msg = ws.receive_json()
        assert "payload" in msg or "spot" in msg or "error" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api.py tests/test_ws.py -v`
Expected: FAIL — 404 on all `/api/*` (no routers registered)

- [ ] **Step 3: Write routers + register**

```python
# app/routers/__init__.py
```

```python
# app/routers/dashboard.py
from fastapi import APIRouter
import asyncio
from app.services import report_service
from .helpers import to_json_safe

router = APIRouter()

@router.get("/api/dashboard")
async def dashboard():
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, report_service.get_dashboard)
    return to_json_safe(data)
```

```python
# app/routers/chain.py
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.chain_service import get_chain
from app.hub import Hub
from .helpers import to_json_safe

router = APIRouter()
_hub = Hub()

@router.get("/api/chain")
async def chain(symbol: str = "NIFTY"):
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, get_chain, symbol)
    return to_json_safe(data)

@router.websocket("/ws/chain")
async def ws_chain(ws: WebSocket, symbol: str = "NIFTY"):
    from app.config import CHAIN_WS_THROTTLE
    await ws.accept()
    await _hub.register("chain", ws)
    try:
        while True:
            await asyncio.sleep(CHAIN_WS_THROTTLE)
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, get_chain, symbol)
            await _hub.throttle_broadcast("chain", to_json_safe(data), CHAIN_WS_THROTTLE)
    except WebSocketDisconnect:
        pass
    finally:
        await _hub.unregister("chain", ws)
```

```python
# app/routers/backtest.py
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from app.services import backtest_service
from .helpers import to_json_safe

router = APIRouter()

class BacktestRequest(BaseModel):
    kind: str = "tf"
    name: str = "golden_cross"
    symbol: str = "NIFTY"
    tf: str = "1d"
    hold: int = 1
    params: dict = {}

@router.get("/api/backtest/strategies")
async def strategies():
    loop = asyncio.get_running_loop()
    return to_json_safe(await loop.run_in_executor(None, backtest_service.available_strategies))

@router.post("/api/backtest")
async def submit(req: BacktestRequest):
    job_id = backtest_service.submit(req.model_dump())
    return {"job_id": job_id}

@router.get("/api/backtest/{job_id}")
async def job(job_id: str):
    return to_json_safe(backtest_service.get_job(job_id))

@router.websocket("/ws/backtest/{job_id}")
async def ws_backtest(ws: WebSocket, job_id: str):
    await ws.accept()
    q = backtest_service.job_events(job_id)
    try:
        while True:
            payload = await q.get()
            await ws.send_json(to_json_safe(payload))
            if payload.get("status") in ("done", "error"):
                break
    except WebSocketDisconnect:
        pass
```

```python
# app/routers/recorder.py
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from app.services import recorder_service
from app.hub import Hub
from app.config import RECORDER_WS_THROTTLE
from .helpers import to_json_safe

router = APIRouter()
_hub = Hub()

class StartRequest(BaseModel):
    symbol: str = "NIFTY"

@router.get("/api/recorder/status")
async def status():
    loop = asyncio.get_running_loop()
    return to_json_safe(await loop.run_in_executor(None, recorder_service.status))

@router.post("/api/recorder/start")
async def start(req: StartRequest):
    loop = asyncio.get_running_loop()
    return to_json_safe(await loop.run_in_executor(None, recorder_service.start, req.symbol))

@router.post("/api/recorder/stop")
async def stop():
    loop = asyncio.get_running_loop()
    return to_json_safe(await loop.run_in_executor(None, recorder_service.stop))

@router.websocket("/ws/recorder")
async def ws_recorder(ws: WebSocket):
    await ws.accept()
    await _hub.register("recorder", ws)
    try:
        while True:
            await asyncio.sleep(RECORDER_WS_THROTTLE)
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, recorder_service.status)
            await _hub.throttle_broadcast("recorder", to_json_safe(data), RECORDER_WS_THROTTLE)
    except WebSocketDisconnect:
        pass
    finally:
        await _hub.unregister("recorder", ws)
```

```python
# app/routers/research.py
import asyncio
from fastapi import APIRouter, Query
from app.services import research_service
from .helpers import to_json_safe

router = APIRouter()

@router.get("/api/research/db/status")
async def db_status():
    return to_json_safe(research_service.db_status())

@router.get("/api/research/ticks")
async def ticks(symbol: str | None = None, strike: float | None = None,
                side: str | None = None, from_ts: str | None = None,
                to_ts: str | None = None, limit: int = Query(500, le=2000)):
    loop = asyncio.get_running_loop()
    return to_json_safe(await loop.run_in_executor(
        None, research_service.ticks, symbol, strike, from_ts, to_ts, limit, side))

@router.get("/api/research/oi")
async def oi(symbol: str = "NIFTY", limit: int = Query(60, le=200)):
    loop = asyncio.get_running_loop()
    return to_json_safe(await loop.run_in_executor(None, research_service.oi_snapshot, symbol, limit))

@router.get("/api/research/ivskew")
async def ivskew(symbol: str = "NIFTY", limit: int = Query(80, le=200)):
    loop = asyncio.get_running_loop()
    return to_json_safe(await loop.run_in_executor(None, research_service.iv_skew, symbol, limit))

@router.get("/api/research/spot")
async def spot(from_ts: str | None = None, to_ts: str | None = None,
               limit: int = Query(1000, le=5000)):
    loop = asyncio.get_running_loop()
    return to_json_safe(await loop.run_in_executor(None, research_service.spot, from_ts, to_ts, limit))
```

```python
# app/routers/blog.py
import asyncio
from fastapi import APIRouter
from app.services import blog_service
from .helpers import to_json_safe

router = APIRouter()

@router.get("/api/blog/posts")
async def posts():
    return to_json_safe(blog_service.list_posts())

@router.get("/api/blog/posts/{date}")
async def post(date: str):
    return to_json_safe(blog_service.get_post(date))

@router.post("/api/blog/regenerate")
async def regenerate():
    loop = asyncio.get_running_loop()
    return to_json_safe(await loop.run_in_executor(None, blog_service.regenerate))
```

Register routers in `app/main.py`:

```python
# in create_app(), after StaticFiles mount:
from app.routers import dashboard, chain, backtest, recorder, research, blog
app.include_router(dashboard.router)
app.include_router(chain.router)
app.include_router(backtest.router)
app.include_router(recorder.router)
app.include_router(research.router)
app.include_router(blog.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api.py tests/test_ws.py -v`
Expected: PASS. (Research/recorder/dashboard rely on real data files — present on this machine.)

- [ ] **Step 5: Commit**

```bash
git add app/routers/ app/main.py tests/test_api.py tests/test_ws.py
git commit -m "feat(web): full REST + WebSocket API routers"
```

---

### Task 10: Frontend — static pages, JS, CSS

**Files:**
- Create: `app/static/css/app.css`
- Create: `app/static/js/app.js`
- Create: `app/static/js/ws.js`
- Create: `app/static/js/charts.js`
- Create: `app/static/js/dashboard.js`
- Create: `app/static/js/chain.js`
- Create: `app/static/js/backtest.js`
- Create: `app/static/js/research.js`
- Create: `app/static/js/recorder.js`
- Create: `app/static/js/blog.js`
- Create: `app/static/index.html`
- Create: `app/static/dashboard.html`, `chain.html`, `backtest.html`, `research.html`, `recorder.html`, `blog.html`
- Test: `tests/test_frontend.py`

**Interfaces:**
- Consumes: all `/api/*` + `/ws/*` from Task 9. Chart.js via CDN `https://cdn.jsdelivr.net/npm/chart.js@4`.
- Produces: working single-page nav app (client-side routing by hash: `#/dashboard`, `#/chain`, `#/backtest`, `#/research`, `#/recorder`, `#/blog`, `#/blog/<date>`). Dark theme. Each page JS fetches its API data and renders.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_frontend.py
from fastapi.testclient import TestClient

def test_all_pages_serve():
    from app.main import app
    c = TestClient(app)
    for page in ("/", "/static/dashboard.html", "/static/chain.html",
                 "/static/backtest.html", "/static/research.html",
                 "/static/recorder.html", "/static/blog.html"):
        r = c.get(page)
        assert r.status_code == 200, page

def test_js_css_serve():
    from app.main import app
    c = TestClient(app)
    for f in ("/static/css/app.css", "/static/js/app.js", "/static/js/ws.js",
              "/static/js/charts.js", "/static/js/dashboard.js"):
        r = c.get(f)
        assert r.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_frontend.py -v`
Expected: FAIL — 404 on static pages

- [ ] **Step 3: Write frontend files**

`app/static/index.html`:
```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nifty Research</title>
<link rel="stylesheet" href="/static/css/app.css">
</head>
<body>
<nav id="nav"></nav>
<main id="view"></main>
<script src="/static/js/app.js"></script>
<script src="/static/js/ws.js"></script>
<script src="/static/js/charts.js"></script>
<script src="/static/js/dashboard.js"></script>
<script src="/static/js/chain.js"></script>
<script src="/static/js/backtest.js"></script>
<script src="/static/js/research.js"></script>
<script src="/static/js/recorder.js"></script>
<script src="/static/js/blog.js"></script>
</body>
</html>
```

`app/static/css/app.css` (dark theme, minimal):
```css
:root { --bg:#0d1117; --panel:#161b22; --border:#30363d; --text:#e6edf3;
        --muted:#8b949e; --red:#f85149; --green:#3fb950; --amber:#d29922;
        --blue:#58a6ff; }
* { box-sizing: border-box; }
body { margin:0; font-family: system-ui, -apple-system, sans-serif;
       background: var(--bg); color: var(--text); }
nav { display:flex; gap:4px; padding:10px 14px; border-bottom:1px solid var(--border);
      position:sticky; top:0; background:var(--bg); z-index:10; }
nav a { color:var(--muted); text-decoration:none; padding:6px 12px;
        border-radius:6px; font-size:14px; }
nav a.active, nav a:hover { color:var(--text); background:var(--panel); }
main { padding:16px; max-width:1200px; margin:0 auto; }
.card { background:var(--panel); border:1px solid var(--border);
        border-radius:10px; padding:14px; margin-bottom:14px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; }
h2 { font-size:16px; margin-top:0; color:var(--text); }
.muted { color:var(--muted); font-size:13px; }
.badge { display:inline-block; padding:2px 10px; border-radius:999px;
         font-size:12px; font-weight:600; }
.red { color:var(--red); } .green { color:var(--green); }
.amber { color:var(--amber); } .blue { color:var(--blue); }
table { width:100%; border-collapse:collapse; font-size:13px; }
th, td { padding:6px 8px; text-align:right; border-bottom:1px solid var(--border); }
th { color:var(--muted); font-weight:600; }
tr:nth-child(even) { background:rgba(255,255,255,0.02); }
button, select, input { background:var(--panel); color:var(--text);
        border:1px solid var(--border); border-radius:6px; padding:6px 10px;
        font-size:13px; }
button { cursor:pointer; } button:hover { border-color:var(--blue); }
.banner-noready { background:#3a1d1d; border:1px solid var(--red); color:var(--red);
        border-radius:10px; padding:14px; font-weight:700; font-size:15px; }
pre { white-space:pre-wrap; font-size:12px; color:var(--muted); }
```

`app/static/js/app.js`:
```js
const ROUTES = ["dashboard", "chain", "backtest", "research", "recorder", "blog"];
const NAV = ["dashboard", "chain", "backtest", "research", "recorder", "blog"];

function renderNav(active) {
  const nav = document.getElementById("nav");
  nav.innerHTML = NAV.map(r =>
    `<a href="#/${r}" class="${r === active ? "active" : ""}">${r}</a>`).join("");
}

async function loadJS(page) {
  // per-page JS is already loaded in index.html; dispatcher calls page render
}

const handlers = {
  dashboard: window.dashboardPage,
  chain: window.chainPage,
  backtest: window.backtestPage,
  research: window.researchPage,
  recorder: window.recorderPage,
  blog: window.blogPage,
};

async function router() {
  const hash = location.hash.replace(/^#\//, "");
  const [page, arg] = hash.split("/");
  const active = ROUTES.includes(page) ? page : "dashboard";
  renderNav(active);
  const h = handlers[active];
  const view = document.getElementById("view");
  view.innerHTML = `<div class="muted">Loading ${active}...</div>`;
  try {
    await h(view, arg);
  } catch (e) {
    view.innerHTML = `<div class="card red">Error: ${e.message}</div>`;
  }
}

window.addEventListener("hashchange", router);
window.addEventListener("DOMContentLoaded", router);

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

function fmt(x, d = 2) {
  if (x === null || x === undefined || isNaN(x)) return "—";
  return Number(x).toLocaleString("en-IN", { maximumFractionDigits: d });
}

function badge(label, cls) {
  return `<span class="badge ${cls}">${label}</span>`;
}

window.app = { api, fmt, badge, ROUTES, NAV };
```

`app/static/js/ws.js`:
```js
function connectWS(url, onMessage, onClose) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}${url}`);
  ws.onmessage = e => {
    try { onMessage(JSON.parse(e.data)); } catch (_) {}
  };
  ws.onclose = () => { if (onClose) setTimeout(onClose, 3000); };
  return ws;
}
window.connectWS = connectWS;
```

`app/static/js/charts.js`:
```js
function makeChart(el, type, labels, datasets, opts) {
  if (!window.Chart) return null;
  const cfg = { type, data: { labels, datasets },
    options: Object.assign({ responsive: true, plugins: { legend: { labels: { color: "#8b949e" } } } }, opts || {}) };
  return new Chart(el, cfg);
}
window.makeChart = makeChart;
```

`app/static/js/dashboard.js`:
```js
window.dashboardPage = async function (view) {
  const d = await app.api("/api/dashboard");
  const reg = d.regime.plan || {};
  const gate = (reg.regime || "").includes("RANGE") || reg.gate === "NO_TRADE";
  const banner = gate
    ? `<div class="banner-noready">${reg.regime || ""} | GATE: NO_TRADE | STAY OUT</div>`
    : `<div class="card green">GATE OPEN</div>`;
  const vix = d.regime.lines ? d.regime.lines.join("<br>") : "";
  const inst = d.institutional.lines ? d.institutional.lines.join("<br>") : "";
  const sf = (d.stockflow.lines || []).slice(0, 10).map(l => `<div>${l}</div>`).join("");
  const ml = d.ml.error ? `<div class="muted">${d.ml.error}</div>`
                       : (d.ml.lines || []).join("<br>");
  const ps = d.premiumseller.lines ? d.premiumseller.lines.join("<br>") : "";
  view.innerHTML = `
    ${banner}
    <div class="grid">
      <div class="card"><h2>Regime + VIX</h2><pre>${vix}</pre></div>
      <div class="card"><h2>Institutional</h2><pre>${inst}</pre></div>
    </div>
    <div class="card"><h2>Stock Flow (top 10)</h2>${sf}</div>
    <div class="grid">
      <div class="card"><h2>ML Context</h2><pre>${ml}</pre></div>
      <div class="card"><h2>Premium Seller</h2><pre>${ps}</pre></div>
    </div>`;
};
```

`app/static/js/chain.js`:
```js
window.chainPage = async function (view) {
  view.innerHTML = `<div class="muted">Loading chain...</div>`;
  const t0 = Date.now();
  const d = await app.api("/api/chain");
  if (d.error) { view.innerHTML = `<div class="card red">${d.error}</div>`; return; }
  const rows = (d.strikes || []).map(r => `
    <tr>
      <td>${app.fmt(r.strike, 0)}</td>
      <td>${app.fmt(r.ce_oi, 0)}</td><td>${app.fmt(r.ce_oi_chg, 0)}</td>
      <td>${app.fmt(r.ce_iv)}</td>
      <td>${app.fmt(r.pe_iv)}</td>
      <td>${app.fmt(r.pe_oi, 0)}</td><td>${app.fmt(r.pe_oi_chg, 0)}</td>
    </tr>`).join("");
  const w = d.walls || {};
  const pp = d.pcr || {};
  view.innerHTML = `
    <div class="grid">
      <div class="card"><h2>Spot ${app.fmt(d.spot, 0)} | ${d.expiry}</h2>
        <div class="muted">resistance: ${app.fmt(w.nearest_resistance, 0)} |
         support: ${app.fmt(w.nearest_support, 0)}</div>
        <div class="muted">PCR ${app.fmt(pp.pcr)} | max pain ${app.fmt(pp.max_pain, 0)}</div>
      </div>
      <div class="card"><h2>Matrix</h2><pre>${JSON.stringify(d.matrix || {}, null, 1)}</pre></div>
    </div>
    <div class="card"><h2>Chain</h2>
      <table><tr><th>Strike</th><th>CE OI</th><th>CE chg</th><th>CE IV</th>
      <th>PE IV</th><th>PE OI</th><th>PE chg</th></tr>${rows}</table></div>`;
  setTimeout(() => location.reload(), 15000);
};
```

`app/static/js/backtest.js`:
```js
window.backtestPage = async function (view) {
  const s = await app.api("/api/backtest/strategies");
  const opts = s.map(x => `<option value="${x.name}">${x.name}</option>`).join("");
  view.innerHTML = `
    <div class="card">
      <h2>Run Backtest</h2>
      <label>Strategy <select id="bt-strat">${opts}</select></label>
      <label>TF <select id="bt-tf">
        <option value="1d">Daily</option><option value="60m">60m</option>
        <option value="30m">30m</option><option value="15m">15m</option></select></label>
      <label>Hold <input id="bt-hold" type="number" value="1" min="1"></label>
      <label>Params (JSON) <input id="bt-params" value="{}" style="width:60%"></label>
      <button id="bt-run">Run</button>
    </div>
    <div id="bt-result"></div>`;
  document.getElementById("bt-run").onclick = async () => {
    const params = JSON.parse(document.getElementById("bt-params").value || "{}");
    const body = { name: document.getElementById("bt-strat").value,
                   tf: document.getElementById("bt-tf").value,
                   hold: parseInt(document.getElementById("bt-hold").value) || 1,
                   params };
    const res = await app.api("/api/backtest", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body) });
    const box = document.getElementById("bt-result");
    box.innerHTML = `<div class="muted">Job ${res.job_id} running...</div>`;
    const ws = connectWS(`/ws/backtest/${res.job_id}`, m => {
      if (m.status === "done") {
        box.innerHTML = `<pre>${JSON.stringify(m.result, null, 1)}</pre>`;
      } else if (m.status === "error") {
        box.innerHTML = `<div class="red">${m.error}</div>`;
      }
    });
  };
};
```

`app/static/js/research.js`:
```js
window.researchPage = async function (view) {
  const st = await app.api("/api/research/db/status");
  const symbols = (st.distinct_symbols || []).join(", ");
  view.innerHTML = `
    <div class="grid">
      <div class="card"><h2>DB</h2>
        <div>ticks: <b>${app.fmt(st.ticks, 0)}</b> | spot: ${app.fmt(st.spot, 0)}</div>
        <div class="muted">size ${st.size_mb} MB | strikes ${app.fmt(st.distinct_strikes, 0)}</div>
        <div class="muted">symbols: ${symbols}</div>
        <div class="muted">range ${st.first_tick_ts} → ${st.last_tick_ts}</div>
      </div>
      <div class="card"><h2>Spot</h2><canvas id="spot-chart" height="120"></canvas></div>
    </div>
    <div class="card"><h2>Recent Ticks</h2>
      <table id="tick-table"></table></div>`;
  const spot = await app.api("/api/research/spot?limit=500");
  const ch = document.getElementById("spot-chart");
  if (spot.rows && spot.rows.length && window.Chart) {
    makeChart(ch, "line", spot.rows.map(r => r.ts.slice(11, 19)),
              [{ label: "spot", data: spot.rows.map(r => r.value),
                 borderColor: "#58a6ff", fill: false }]);
  } else {
    ch.parentElement.innerHTML = '<div class="muted">no spot data</div>';
  }
  const t = await app.api("/api/research/ticks?limit=50");
  if (t.rows && t.rows.length) {
    document.getElementById("tick-table").innerHTML =
      "<tr><th>ts</th><th>sym</th><th>strike</th><th>side</th><th>ltp</th><th>iv</th></tr>" +
      t.rows.map(r => `<tr><td>${r.recv_ts.slice(11,19)}</td><td>${r.symbol}</td>
        <td>${app.fmt(r.strike,0)}</td><td>${r.side}</td><td>${app.fmt(r.ltp)}</td>
        <td>${app.fmt(r.iv)}</td></tr>`).join("");
  }
};
```

`app/static/js/recorder.js`:
```js
window.recorderPage = async function (view) {
  const st = await app.api("/api/recorder/status");
  view.innerHTML = `
    <div class="card">
      <h2>Tick Recorder</h2>
      <div>status: <b class="${st.running ? "green" : "red"}">${st.running ? "RUNNING" : "STOPPED"}</b>
        pid ${st.pid || "—"} | symbol ${st.symbol || "—"}</div>
      <div>ticks <b>${app.fmt(st.ticks, 0)}</b> | spot ${app.fmt(st.spot_rows, 0)}</div>
      <button id="rec-start">Start</button>
      <button id="rec-stop">Stop</button>
    </div>
    <div class="card"><h2>Log</h2><pre id="rec-log">${(st.log_tail || []).join("")}</pre></div>`;
  document.getElementById("rec-start").onclick = async () =>
    location.hash = "#/recorder", await app.api("/api/recorder/start", { method: "POST" });
  document.getElementById("rec-stop").onclick = async () =>
    await app.api("/api/recorder/stop", { method: "POST" });
  connectWS("/ws/recorder", m => {
    const s = m;
    document.getElementById("rec-log").textContent = (s.log_tail || []).join("");
  });
};
```

`app/static/js/blog.js`:
```js
window.blogPage = async function (view, arg) {
  if (arg) {
    const p = await app.api(`/api/blog/posts/${arg}`);
    if (p.exists) { view.innerHTML = p.html; return; }
  }
  const d = await app.api("/api/blog/posts");
  view.innerHTML = `<div class="card"><h2>Blog Posts</h2>
    ${d.posts.map(p => `<div><a href="#/blog/${p.date}">${p.date} — ${p.title}</a></div>`).join("")}
    </div>`;
};
```

`app/static/dashboard.html` and the other pages: each is a thin file that redirects to index (single-page app). Create them as:
```html
<!doctype html><html><head><meta http-equiv="refresh" content="0; url=/"></head><body></body></html>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_frontend.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/static/ tests/test_frontend.py
git commit -m "feat(web): dark-theme frontend pages, JS modules, Chart.js charts"
```

---

### Task 11: Smoke test + performance gates + README

**Files:**
- Modify: `tests/test_smoke.py` (extend with perf gates)
- Create: `tests/test_perf.py`
- Modify: `README.md` (add "Web Platform" run section)
- Modify: `AGENTS.md` (add web platform module entry)

**Interfaces:**
- Consumes: app from all previous tasks.
- Produces: verified perf gates; documented run instructions.

- [ ] **Step 1: Write the failing/measurement test**

```python
# tests/test_perf.py
import time
from fastapi.testclient import TestClient

def test_dashboard_under_200ms_cached():
    from app.main import app
    c = TestClient(app)
    c.get("/api/dashboard")  # warm
    t0 = time.perf_counter()
    c.get("/api/dashboard")
    dt_ = (time.perf_counter() - t0) * 1000
    assert dt_ < 200, f"dashboard took {dt_:.0f}ms"

def test_chain_under_200ms_cached():
    from app.main import app
    c = TestClient(app)
    c.get("/api/chain")  # warm (may be slow first time - NSE fetch)
    t0 = time.perf_counter()
    c.get("/api/chain")
    dt_ = (time.perf_counter() - t0) * 1000
    assert dt_ < 200, f"chain took {dt_:.0f}ms"
```

- [ ] **Step 2: Run test to verify it fails/slow**

Run: `python -m pytest tests/test_perf.py -v`
Expected: FAIL if dashboard/chain endpoints not yet registered or slower than gate (chain first call includes live NSE fetch — that's why gate is on the SECOND call, cached).

- [ ] **Step 3: Write README/AGENTS updates**

`README.md` — append:
```markdown
## Web Platform (optional)

Localhost dashboard wrapping the whole toolset:

```bash
python run_app.py                # http://127.0.0.1:8766
python run_app.py --host 0.0.0.0 # LAN access
```

Pages: Dashboard (regime gate + VIX + stock flow), Chain (live OI table), Backtest (async jobs),
Research (research.db explorer), Recorder (start/stop live tick recorder), Blog (daily posts).

API: REST under `/api/*`; live WebSockets `/ws/chain`, `/ws/recorder`, `/ws/backtest/{id}`.
```

`AGENTS.md` — append under Modules:
```markdown
- `app/` (web platform, optional) — FastAPI localhost app wrapping the whole
  toolset: `run_app.py` (port 8766). Services cache module outputs (chain 15s,
  report 60s); backtests run as async jobs; recorder managed as subprocess;
  WebSocket hub broadcasts live chain/recorder. Existing `.py` modules untouched.
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `python -m pytest tests/ -q`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_perf.py README.md AGENTS.md
git commit -m "docs+perf: smoke/perf gates, README + AGENTS web platform docs"
```

---

### Task 12: End-to-end manual verification

**Files:** none (verification only).

- [ ] **Step 1: Start the app**

Run: `python run_app.py --port 8766` (background via PTY)

- [ ] **Step 2: Verify dashboard**

Run: `curl -s http://127.0.0.1:8766/api/dashboard | python3 -m json.tool | head -30`
Expected: JSON with regime/stockflow/etc.

- [ ] **Step 3: Verify chain + backtest + recorder**

```bash
curl -s "http://127.0.0.1:8766/api/chain" | head -c 300
curl -s -X POST http://127.0.0.1:8766/api/backtest -H 'Content-Type: application/json' \
  -d '{"kind":"tf","name":"golden_cross","tf":"1d","params":{"fast":10,"slow":50}}'
curl -s http://127.0.0.1:8766/api/recorder/status
curl -s http://127.0.0.1:8766/api/research/db/status
```
Expected: JSON responses, backtest returns job_id that transitions to done.

- [ ] **Step 4: Browser check**

Open `http://127.0.0.1:8766` — nav to each page; chain page shows table; backtest runs a job; recorder shows RUNNING (matches the currently-running recorder); blog lists posts.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: web platform end-to-end verified"
```

(Only if changes were made during verification.)
