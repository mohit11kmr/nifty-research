# Nifty Research Web Platform — Design

Date: 2026-08-11
Status: Approved (approach A + performance design)

## Purpose

One FastAPI web app that exposes the full Nifty Research toolset through a
browser UI: live dashboard, option chain analysis, backtesting, research DB
explorer, tick recorder control, and blog viewer. All computation stays in the
existing Python modules; the app is a thin, cached, real-time wrapper.

## Decisions (from brainstorming)

- **Scope:** Full platform (dashboard + backtest + DB explorer + recorder + blog).
- **Stack:** FastAPI backend + plain HTML/JS/CSS frontend (no node/npm build step).
- **Interactivity:** Full control from UI (backtests, report refresh, recorder start/stop).
- **Access:** Localhost only (127.0.0.1 bind default; `--host 0.0.0.0` override).
- **Live updates:** Real-time via WebSocket (throttled broadcasts).
- **Long-term/performance:** FastAPI monolith reusing existing `.py` modules as
  libraries; LRU/TTL caching; async executor for blocking calls; async job queue
  for backtests; WS broadcast hub with fan-out; throttled tick pushes.

## Architecture

```
app/
  main.py               # FastAPI app, router registration, static serve, lifespan
  config.py             # paths (DATA_DIR, DB_PATH), constants, throttle windows
  hub.py                # WebSocket broadcast hub + throttle batching
  services/
    report_service.py   # daily_report.py sections as cached JSON dicts
    chain_service.py    # nse_live fetch + oi_intel analysis, 15s TTL cache
    backtest_service.py # asyncio job queue -> backtester/strategies/multitf/premium_seller
    recorder_service.py # tick_recorder subprocess manager (PID, status, log tail)
    research_service.py # research.db indexed queries (ticks/oi/skew/spot)
    blog_service.py     # blog/posts read + blog_post.py subprocess
  routers/
    dashboard.py        # GET /api/dashboard
    chain.py            # GET /api/chain + WS /ws/chain
    backtest.py         # POST/GET /api/backtest + WS /ws/backtest/{id}
    recorder.py         # GET/POST /api/recorder/* + WS /ws/recorder
    research.py         # GET /api/research/*
    blog.py             # GET /api/blog/posts
  static/
    index.html, dashboard.html, chain.html, backtest.html, research.html,
    recorder.html, blog.html
    js/app.js ws.js charts.js <page>.js
    css/app.css
run_app.py              # entry point: python run_app.py (port 8766)
tests/
  test_services.py      # unit tests per service (cache hit/miss, error)
  test_api.py           # TestClient: every endpoint 200 + JSON shape
  test_ws.py            # hub broadcast to one client
  smoke.py              # full app start -> GET /api/dashboard non-empty
```

Dependencies added: `fastapi`, `uvicorn`. Reused: pandas, numpy, scikit-learn,
playwright, existing project modules. No node/npm.

Concurrency: FastAPI `async def` endpoints; blocking module calls run in
`run_in_executor` (ThreadPool). WebSocket hub uses asyncio broadcast. Backtest
jobs are asyncio.Tasks in a bounded queue.

## Data Flow & Caching

Principle: no expensive compute on every request; everything served from cache.

| Layer            | Cache          | Invalidation              |
|------------------|----------------|---------------------------|
| chain_service    | 15s TTL        | TTL expiry                |
| report_service   | 60s TTL        | TTL expiry                |
| research_service | LRU (max 64)   | LRU eviction              |
| backtest_service | in-memory dict | evict oldest, keep max 10 |
| blog_service     | mtime-based    | file mtime change         |

- Dashboard = one payload combining independently cached sections (regime,
  walls/PCR/maxpain, institutional, stockflow top-10, vix snapshot). One stale
  section does not invalidate the whole payload.
- Live chain WS: browser connects -> single live fetch (threaded) -> analysis ->
  throttle 2s -> hub fan-out to N clients (one fetch per N clients).
- Backtest: POST -> job_id -> executor runs -> WS pushes result. No polling.
- Recorder: subprocess.Popen(["python3", "tick_recorder.py", sym]); service
  tracks PID, tails last 30 log lines, status pushed every 5s over WS. Stop =
  SIGTERM. Script itself unchanged.
- Errors: every service try/except; JSON error + stack in debug mode; frontend
  shows friendly message + status badge. Chain failure degrades only the chain
  card.

## API

```
GET  /api/dashboard
GET  /api/chain?symbol=NIFTY
GET  /api/regime
GET  /api/institutional
GET  /api/stockflow?top=12
GET  /api/tfscan
GET  /api/ml
GET  /api/premiumseller
POST /api/backtest                      {strategy, symbol, tf, hold, params} -> {job_id}
GET  /api/backtest/{id}                 {status: queued|running|done|error, result?}
GET  /api/backtest/strategies           available strategies + param grids
GET  /api/recorder/status               {running, pid, db, ticks, spot, log_tail}
POST /api/recorder/start                {symbol}
POST /api/recorder/stop
GET  /api/research/db/status            {rows, size, tables, last_ts}
GET  /api/research/ticks?symbol&strike&from&to&limit=500
GET  /api/research/oi?strike&date&limit
GET  /api/research/ivskew?time&limit
GET  /api/research/spot?from&to
GET  /api/blog/posts
GET  /api/blog/posts/{date}
WS   /ws/chain?symbol=NIFTY             throttled 2s live chain push
WS   /ws/recorder                       status push 5s
WS   /ws/backtest/{job_id}              progress + done
```

All queries param-bound (SQLite), paths sanitized.

## Frontend

Plain HTML+JS, dark theme, top nav tabs. Chart.js via CDN (no npm).

| Page        | Content                                                        |
|-------------|----------------------------------------------------------------|
| Dashboard   | Regime gate banner (RANGE_LV=red NO_TRADE), VIX + expected move, spot, PCR, max pain, walls, matrix signal, institutional, stockflow top-10 |
| Chain       | Full strike table (CE/PE OI, chg, IV), walls/build-up highlight, max-pain line, live via /ws/chain |
| Backtest    | Strategy dropdown, TF, symbol, hold, params JSON. Run -> live progress WS -> P&L chart + metrics (win%, PF, maxDD, sharpe) |
| Research    | DB stats, tick explorer (filter symbol/strike/date, table + chart), IV skew plot, spot chart |
| Recorder    | Start/stop button, live status card (pid, tick count, spot, log tail) via WS |
| Blog        | Post list + full post view |

## Testing & Verification

- Unit: service cache hit/miss/error paths against real modules with small fixtures.
- API: TestClient asserts 200 + JSON schema per endpoint.
- WS: asyncio hub broadcast test.
- Smoke: app start -> GET /api/dashboard non-empty.
- Perf gates on this box: dashboard < 200ms cached; 10 WS clients broadcast <
  100ms; 1yr daily backtest < 2s.
- Run: `python run_app.py` -> http://127.0.0.1:8766 ; `pytest tests/ -q`.

## Existing Scripts

- Existing `.py` modules untouched; still run via CLI (`daily_report.py`,
  `build_data.py`, `tick_recorder.py`, `blog_post.py`).
- App imports them as libraries. Recorder runs as subprocess (same script, same DB).
- Only repo change: `requirements.txt` gains fastapi/uvicorn.

## Non-Goals (this phase)

- No auth (localhost-only).
- No Docker.
- No research.db schema migration.
- No mobile PWA.
