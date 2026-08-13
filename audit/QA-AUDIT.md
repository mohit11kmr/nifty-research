# QA Audit — Code + Business Logic + Database + API + Frontend + Testing

> Deep audit Phases 3, 5, 6, 7, 8, 10 consolidated. No app code modified.
> Built: 2026-08-12. Test run: `test_all.py` 34/34 OK (5.2s) + `tests/` 16/16 OK.
> RE-AUDITED: 2026-08-13 — every finding re-verified against the fixed code.
> Re-audit test run: `test_all.py` 34/34 OK + `tests/test_fix_verification.py` 18/18 OK.
> Re-audit result: QA-H1, QA-H2, QA-M1, QA-M2, QA-M4, QA-M5 **RESOLVED**;
> QA-M3 **REJECTED (false positive — NIFTY strike grid is 50, not 100)**.

---

## 1. Business Logic — High

### QA-H1. `precision_signals` fabricates Layer 3 (technical consensus) and capital-layer input
- **File**: `precision_signals.py:79` and `:66-70`.
- **Evidence**: `market_brain.make_verdict(df=None, row=None,
  consensus_score=0.8, total_votes=6)` — caller passes a **hardcoded 80%
  consensus** with no df/row. Inside `make_verdict` (market_brain.py:118):
  `pct_score = 0.8/6 = 0.133` and `row={} → rsi14=50`, so the "technical
  consensus layer" is not computed from real indicators. Capital layer:
  `full_capital_safety_audit()` with no `daily_pnl` → kill switch always
  inactive → label "100% Risk Compliant" (line 70) hardcoded.
- **Impact**: A+ / A "5-6 Layer Confluence" signals can be generated while
  two layers are fabricated constants. Downstream `signal_history` logging
  records these as real → poisons accuracy tracking.
- **Severity**: High (business-integrity). **Confidence**: High.
- **Fix**: compute real `market_brain` consensus from real df/row; pass real
  `daily_pnl` into the capital layer; remove hardcoded labels.
- **RESOLVED (2026-08-13)**: `precision_signals.py` now computes every layer
  from real data; unavailable sources report `NOT_COMPUTED`/`NEUTRAL`/
  `BLOCKED`/`ERROR` (no fabricated pass). Capital layer feeds real daily PnL
  from the paper account (`_daily_pnl_from_paper`). `confluence_score`
  strictly equals the count of PASSED layers. Verified by
  `tests/test_fix_verification.py::TestR1PrecisionHonestConfluence`.

### QA-H2. `capital_guard.compute_position_size` floors lots at 1, violating the 1% cap
- **File**: `capital_guard.py:105`.
- **Evidence**: `allowed_lots = max(int(adjusted_risk_cap / max(risk_per_lot, 1.0)), 1)`.
  When `adjusted_risk_cap < risk_per_lot`, floor yields **1 lot** → actual
  risk > cap; line 117 then reports `is_risk_compliant: False` but still
  returns 1 lot. The guard's stated purpose ("NEVER exceed 1% risk limit")
  is broken by construction.
- **Impact**: sizing recommendation can exceed 1% risk; if wired to real
  orders → over-risk exposure.
- **Severity**: High (risk module). **Confidence**: High.
- **Fix**: remove the `, 1` floor → return 0 lots + `status: BLOCKED`.
- **RESOLVED (2026-08-13)**: floor removed (`capital_guard.py:122-130`);
  sub-lot risk returns 0 lots + `TRADE_BLOCKED`; invalid stop-loss also
  blocks with a reason instead of fabricating risk. Structure stop = 1.5×ATR
  mapped to premium space (0.5×stop_dist, ATM delta≈0.5); derivation
  failures surface via `derivation_error`. Verified by
  `tests/test_fix_verification.py::TestR3CapitalGuard`.

---

## 2. Business Logic — Medium

- **QA-M1** `precision_signals.py:38-41,49-50` — `spot=24500.0`, `vix=12.0`,
  `vix_zone="NORMAL"`, `regime="RANGE_LV"` hardcoded defaults; on regime
  failure these are reported as `nifty_spot`/`vix` → fabricated live-looking
  values. Confidence: High.
  **RESOLVED (2026-08-13)**: hardcoded defaults removed — spot/VIX/zone only
  come from `regime_filter.trade_plan()`; on failure the layer reports
  `NOT_COMPUTED` and `nifty_spot`/`vix` return `None` (`precision_signals.py:101-122`).
- **QA-M2** `precision_signals.py:104` — `or (vix > 16.0)` lets the options
  layer pass regardless of PCR alignment, contradicting the documented
  "PCR & IV Skew alignment" requirement. Confidence: High.
  **RESOLVED (2026-08-13)**: the `vix > 16` bypass is gone — options layer
  passes only on real PCR↔bias alignment, else `MIXED`
  (`precision_signals.py:172-177`).
- **QA-M3** `precision_signals.py:165` — `round(walls["nearest_resistance"]/50)*50`
  can yield non-existent NIFTY strikes (grid is 100; e.g. 24550). Confidence: High.
  **REJECTED (2026-08-13, false positive)**: NIFTY strike grid is **50 points**
  (24500/24550/24600…), verified against live option-chain snapshots and the
  current code comment (`precision_signals.py:229-242`). 24550 is a valid
  strike. No change made.
- **QA-M4** `capital_guard.py:133-144` — SL derived as 50% of premium (owner
  rule = 1.5×ATR structure stop); derivation pulls in `regime_filter` +
  `smart_strike_selector` I/O inside a "guard" call; exceptions swallowed →
  silent `NOT_COMPUTED`. Confidence: High.
  **RESOLVED (2026-08-13)**: SL = 1.5×ATR structure stop mapped to premium
  space (`0.5×stop_dist`, ATM delta≈0.5) via `regime_filter.trade_plan()`;
  any derivation failure is surfaced in the sizing result under
  `derivation_error` (never silently swallowed) (`capital_guard.py:159-191`).
- **QA-M5** `history_logger.py` — every tick: 2 DB connects + `CREATE TABLE
  IF NOT EXISTS` + pandas CSV append; dual-write SQLite+CSV (duplication,
  divergence risk); no lock → concurrent writers can interleave/corrupt CSV.
  Confidence: High.
  **RESOLVED (2026-08-13)**: one persistent WAL-mode connection +
  `busy_timeout` reused for all writes; `CREATE TABLE` runs once at init, not
  per tick (`history_logger.py:59-76`). CSV dual-write remains by documented
  design (CSV = human-readable audit trail, SQLite = queryable); writes are
  single-process under `_conn_lock`. Verified by
  `tests/test_fix_verification.py::TestR11HistoryLoggerWal`.

---

## 3. Database Audit (Phase 5)

- Schema sane: `ticks`/`spot` (research.db, WAL ✓, indexes on
  symbol/side/strike/recv_ts and recv_ts), `tick_history`/`signal_history`/
  `paper_trade_journal` (historical_audit.db, WAL ✓, busy_timeout ✓).
- **DB-D1**: `date(recv_ts)=` function defeats indexes (→ PF-H1). High.
  **RESOLVED (2026-08-13)**: no `date()` wrapper usage remains in
  `live_dash.py`/`tick_recorder.py`/`mcp_nifty.py` — all queries use direct
  `recv_ts` comparisons (`mcp_nifty.recent_ticks` uses
  `recv_ts >= datetime('now','localtime','-1 day')`).
- **DB-D2**: No FK constraints anywhere (ticks/spot/journal are standalone —
  acceptable for append-only telemetry; no relations to enforce).
- **DB-D3**: `ticks` has no retention (→ PF-H2). High.
  **RESOLVED (2026-08-13)**: `data_retention.py` purges rows older than
  `--keep-days` (default 30) with optional VACUUM. Verified by
  `tests/test_fix_verification.py::TestR7DataRetention`.
- **DB-D4**: No migrations; schemas inline in writers; `historical_audit.db`
  committed to git (→ SECURITY S-H1). Medium.
  **RESOLVED (2026-08-13)**: `historical_audit.db`, `paper_account.json`,
  signal/tick/journal CSVs, `.pid`, adaptive-weights, enhancement-log and
  rebalance files untracked + gitignored (`.gitignore`, `git rm --cached`).
- SQL injection: none (all parameterized). Confidence: High.

---

## 4. API Audit (Phase 6)

| Endpoint | AUTH | INPUT | VALIDATION | DB | NOTES |
|---|---|---|---|---|---|
| `GET /api/spot` | none (localhost) | — | — | spot | `fromisoformat` OK (ISO ms format verified) |
| `GET /api/ticks?n=` | none | `n` | **clamped 1–200** ✓ | ticks full-scan | PF-H1 |
| `GET /api/chain` | none | — | fixed radius 400 | 2× full-scan | PF-H1 |
| `GET /api/status` | none | — | — | counts | reads `/tmp/opencode/recorder.pid` unguarded; `log_message` silenced (no access log) |
| MCP tools (15) | none (stdio) | scalar params | `limit` clamped ≤100 ✓, `top=int` ✓, `area` allowlisted ✓ | caches/DB | `broker_status` live broker data (S-L1) |
| `web_dashboard` | — | none | — | broker login side-effect | no server |

No pagination/filtering issues beyond the clamp; no idempotency need (read-only).
Confidence for table: High.

---

## 5. Frontend Audit (Phase 7)

- `live_dash.html` (131 lines): poll loop, `innerHTML` rendering of
  DB-derived values (S-L3, defense-in-depth). No eval/write. No loading/
  error/empty states beyond minimal — **stale-data UX**: on `fetch` failure the
  page silently keeps old values (no retry/error banner). Medium-Low.
- `web_dashboard` HTML: static; shows honest "Not Connected". Fine.
- No bundle/build/a11y concerns for a personal dashboard.

---

## 6. Testing Audit (Phase 10)

- **Covered** (50 tests, green): 18 engine smoke tests (`test_all.py`) +
  greeks/strike/multi-leg units (`tests/`).
- **Missing (critical)**:
  - `regime_filter` — the primary gate (fan-in 11) — **no test**.
  - `oi_intel` max-pain/PCR — **no test** (and P4 duplicated logic).
  - `history_logger` audit writes + CSV/DB consistency — **no test**.
  - End-to-end paper flow (`auto_paper_runner` → `paper_trader`) — **no test**
    (QA-H1/H2 are exactly what an E2E test would have caught).
  - All 15 MCP tools + `live_dash` endpoints — **no test**.
  - `run_all` orchestration, `institutional`, `mtf_alignment`,
    `data_fetcher`, `backtester` — no tests.
- Tests are meaningful (assert real structure, reject hardcoded premiums),
  not superficial. Confidence: High.

---

## 7. Summary of QA findings

High: QA-H1 (fabricated confluence), QA-H2 (risk sizer floor).
Medium: QA-M1..M5, DB-D1..D4.
Low: frontend stale-data UX, no access logs.

## 8. Re-audit status (2026-08-13)

| Finding | Verdict | Where verified |
|---|---|---|
| QA-H1 fabricated confluence | **RESOLVED** | `test_fix_verification` R1 |
| QA-H2 risk sizer floor | **RESOLVED** | `test_fix_verification` R3 |
| QA-M1 hardcoded spot/VIX | **RESOLVED** | R1 |
| QA-M2 `or vix>16` bypass | **RESOLVED** | R1 |
| QA-M3 strike grid 100 | **REJECTED** — grid is 50 | `precision_signals.py:229-242` |
| QA-M4 SL/exception swallow | **RESOLVED** | R3 |
| QA-M5 history_logger conn churn | **RESOLVED** | R11 |
| DB-D1 `date()` defeats index | **RESOLVED** | grep over writers |
| DB-D3 no ticks retention | **RESOLVED** | `data_retention.py` + R7 |
| DB-D4 DB committed to git | **RESOLVED** | `.gitignore` + `git rm --cached` |

Re-audit test run: `test_all.py` 34/34 OK + `tests/test_fix_verification.py` 18/18 OK.
