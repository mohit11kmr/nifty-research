# Phase G — Network Disconnect / Recovery Resilience

Status: **PASS** (all critical items). One production bug found and fixed
(`quant_daemon` None-spot log crash). Test suite: `tests/test_phase_g_network_resilience.py`
(34 tests) — full suite `unittest discover -s tests` = **356 tests OK**.

Date: 2026-08-14. Scope: resilience test only. **No strategy/threshold/regime/
stop/target/expiry/ML/capital-guard logic changed.**

---

## 1. Baseline (recorded before test runs)

| Item | Value |
|---|---|
| Current time | 2026-08-14 09:5x IST |
| Daemon status | RUNNING (PID 514766, `quant_daemon.py --start` since 09:15) |
| Last successful cycle | continuously (log `data/quant_daemon.log`) |
| GT signals/decisions | 327 / 327 (all SKIP/STAY_OUT, honest) |
| GT executions / positions / outcomes | 0 / 0 / 0 |
| Paper cash | ₹3,381.25 (`data/paper_account.json`) |
| Realized P&L / fees / slippage | 0.0 / (legacy) / (legacy) |
| Open paper positions (FSM-derived) | 0 (10 legacy `open_positions`, untouched) |
| GT observation count | 327 |

Data freshness (`truth.asset_freshness_report()`): nifty_history REAL (0.0h),
india_vix REAL (17.6h vs 20h), fii_dii REAL (1.2h vs 6h), oi_snapshots REAL
(17.6h), ml_features STALE (21.7h), tf_scan STALE (21.7h).

Baseline checks: `python test_all.py` ✅, `unittest discover -s tests -v` ✅
(322→356 tests), `tests/test_fix_verification.py` ✅, `pip check` ✅ (no broken
requirements), `git diff --check` ✅ (clean).

---

## 2. Current Network / Data Dependencies

| Feed | Source | Timeout / cadence | Failure path |
|---|---|---|---|
| NIFTY spot | yfinance `^NSEI` 1m (`live_market_fetch.fetch_live_market_spot`) | requests timeout 25s (yfinance default); 1 attempt, no retry | `{"status":"UNAVAILABLE","spot":None}` → `update_live_market_cache` falls back to `_last_real_spot()` (research.db `spot` table) → else UNAVAILABLE |
| Options / OI | NSE chain via Playwright (`nse_live`) → `data/oi_snapshots/*.csv`; `oi_intel.pcr_and_pain` / `oi_walls` / `skew.compute_iv_skew` | snapshot written per day; no freshness check at read | `options_layer` = NO_SNAPSHOT / NOT_COMPUTED / ERROR |
| VIX | Yahoo `^INDIAVIX` daily → `data/india_vix.csv` (`regime_filter._load_vix`) | daily cache, 20h budget | missing/corrupt file → `vix_snapshot()` returns `None` |
| FII/DII | free mirror API → `data/fii_dii_history.csv` | 6h budget | `institutional.institutional_scan()` → NEUTRAL/None or ERROR layer |
| Research DB quotes | `data/research.db` `ticks` (tick_recorder, live streamer) | 120s freshness budget (`truth.LIVE_SPOT_FRESHNESS_S`) | `ResearchDBQuoteSource` → REAL/STALE/MISSING/INVALID envelope |
| ML context | XGBoost/LightGBM/RF ensemble | on-demand | `super_ai_ml_layer` = NO_DATA / ERROR |
| Broker/API | Angel One (`broker_status`) | credentials gated | never touches paper path |
| NSE/Yahoo (data_fetcher) | plain requests | 20s connect / 25s per request; 1 attempt | graceful `None` return |

---

## 3. Failure Scenarios — Expected vs Actual

### A — NIFTY feed failure — PASS
- Expected: REAL → STALE/MISSING, no new directional trade from stale data.
- Actual: `fetch_live_market_spot()` returns spot=None on any exception (never
  a fabricated price). `auto_paper_runner.run_auto_paper_trader()`:
  `if not spot: return {"status":"STAND_DOWN","reason":"no live or cached spot"}`.
  Verified by `NiftyFeedFailureTests.test_feed_down_stand_down_no_trade`.
- Cached fallback: `_last_real_spot()` returns the last recorded real spot with
  `is_live=False` (CACHED_REAL) — **not** mislabeled REAL (test
  `test_cached_spot_fallback_not_mislabeled_real`). Note: the fallback dict
  carries **no `status` key**, so consumers cannot programmatically distinguish
  CACHED_REAL from LIVE_REAL (see Gaps G1/G5).

### B — OPTIONS/OI failure — PASS
- Expected: OPTIONS = STALE/MISSING; no silent use of stale OI, no invented OI.
- Actual: no snapshot → `options_layer` NO_SNAPSHOT; chain read error →
  `options_layer` ERROR; no spot anchor → NOT_COMPUTED. No fabricated PCR: a
  failing OI layer cannot contribute confluence (default `pcr=1.0` is neutral,
  can never create a false PASS — `precision_signals.py:169`). Verified by
  `OptionsOiFailureTests` (no invented pcr, STAY_OUT signal).

### C — VIX failure — PASS
- Expected: VIX = STALE/MISSING; no fabricated VIX.
- Actual: `_load_vix` returns None on missing/corrupt file → `vix_snapshot()`
  returns None. `vix_zone(None)` → honest default `VIX_NORMAL`; `expected_move`
  returns None when VIX absent. Verified by `VixFailureTests`.

### D — All external feeds unavailable — PASS
- Expected: NO new trade; system fails closed.
- Actual: spot=None → `STAND_DOWN` (the signal path is never reached). Even with
  spot present, if every confluence layer errors, `generate_precision_signal`
  returns `STAY_OUT`/`NO_SIGNAL`. Verified by `AllFeedFailureTests` (both).

---

## 4. Open-Position Failure Scenario — PASS

With an isolated temp fixture (`PaperExecutionEngine` + temp account/GT):
- Quote MISSING → exit evaluator `skip_reason="MISSING_QUOTE"`, `triggered=False`;
  `run_exit_checks` records `skipped`, **no close**; position remains open;
  GT outcomes untouched (0 rows), executions unchanged (1 = entry only).
- MTM with no quote → `quote_status="NO_QUOTE"`, `price_basis="entry_fallback"`,
  mark = entry price, flagged — **never guessed**. STALE quote → valued at quote
  but flagged `STALE` (`price_basis="ltp"`).
- No fabricated quote, no fabricated P&L, no auto-close because a quote vanished.
- Verified: `OpenPositionFeedLossTests`.

---

## 5. Stop / Target During Network Failure — PASS

- STALE quote below the stop → **NOT** falsely triggered
  (`skip_reason="STALE_QUOTE_NO_TRIGGER"`). STALE quote above target → **NOT**
  falsely triggered. Only a REAL (fresh) quote can trigger price exits
  (`exit_evaluator.evaluate_position`, precedence + freshness guard).
- Controls (fresh REAL quote) correctly trigger STOP_LOSS / TAKE_PROFIT —
  proving the skip is due to freshness, not a dead rule.
- Verified: `StopTargetDuringFeedLossTests`.

---

## 6. Expiry During Network Failure — PASS

- Expiry day + square-off time + **no exit price** →
  `skip_reason="NO_EXIT_PRICE_SQUARE_OFF_PENDING"`; no fabricated square-off
  price; no close; no auto-roll.
- Expiry day + STALE last price → mandatory time-based `EXPIRY_SQUARE_OFF`
  proceeds using the last real (STALE-accepted) price; no new position created
  after the close (no auto-roll by construction).
- Verified: `ExpiryDuringFeedLossTests`.

---

## 7. Recovery — PASS

- After quote loss, a REAL fresh quote resumes normal evaluation **without any
  manual DB repair**: MISSING cycle (skip) → recovery cycle closes via
  STOP_LOSS, single GT outcome.
- Recovery closes at the **recovery timestamp**, not a backfilled one
  (`test_recovery_not_retroactive`: close fill ts = 14:30 recovery cycle).
- Verified: `RecoveryTests`.

---

## 8. Missed-Cycle Recovery — PASS

- Failed cycles are visible (skip decisions recorded; `STAND_DOWN` printed;
  daemon log line shows the cycle with spot `N/A` when down).
- Recovery cycle succeeds. Repeated checks stay idempotent: 1 close total, 2 GT
  executions (entry+exit), 1 GT outcome — **no duplicate signal/decision/
  execution/position/outcome**, no catch-up trade, no retroactive timestamp.
- Verified: `MissedCycleRecoveryTests`, `DuplicatePreventionTests`.

---

## 9. Duplicate Prevention — PASS

- `close_position` on an already-closed ref raises `ValueError` (second close
  rejected).
- `run_exit_checks` evaluates only open positions and is idempotent by
  construction (FSM + `closed_refs` guard).
- GT `outcomes.position_id` is UNIQUE → one outcome per position.
- All GT tables carry append-only UPDATE/DELETE triggers
  (`observations/snapshots/signals/predictions/decisions/executions/outcomes/
  evaluations/positions_append_only`).
- Executions are unique by `broker_reference` (fill id) — a single fill can
  never mirror twice.
- Verified: `DuplicatePreventionTests`.

---

## 10. Freshness Recovery — PASS

Measured transition (isolated FakeQuoteSource envelope):

```
REAL (age 5s)   -> STOP_LOSS triggers
STALE (age 900s)-> skipped: STALE_QUOTE_NO_TRIGGER
MISSING (no row)-> skipped: MISSING_QUOTE
REAL (age 5s)   -> triggers again
```

`truth.freshness_status`: age ≤ budget → REAL; > budget → STALE; None → MISSING.
Last-good → failure → recovery timestamps are the quote `quote_timestamp` /
`recv_ts` in each envelope (production research.db rows carry `recv_ts`).

---

## 11. Fallbacks — Classification

| Fallback | Class | Can it create a stale-data trade? |
|---|---|---|
| `_last_real_spot()` (research.db last spot, is_live=False) | CACHED_REAL | ⚠️ No age gate — see G1 |
| MTM / exit entry-price valuation when quote MISSING | CACHED_REAL (flagged NO_QUOTE/entry_fallback) | No (never treated as live mark) |
| MTM STALE quote valuation | STALE (flagged) | No |
| `pcr = _to_float(..., 1.0)` neutral default | ESTIMATED (neutral) | No (cannot produce a false PASS) |
| `max_pain = pcr_data.get("max_pain", spot)` | ESTIMATED (spot-anchored) | No (reporting only) |
| `entry_premium = spot*0.006` when strike premium ≤0 (`auto_paper_runner.py:97`) | ESTIMATED | Only post-gate (after a real directional signal); uses **current** spot, not stale |
| `ce_strike`/`pe_strike` spot±1% when no OI walls | ESTIMATED (spot-anchored) | Only post-gate |

No fallback is ever mislabeled REAL. All flagged/neutral by construction.

---

## 12. Daemon Resilience — PASS (one bug fixed)

- Feed failure / temporary timeout / repeated timeout: `update_live_market_cache`
  and `run_auto_paper_trader` catch their own errors and return UNAVAILABLE /
  STAND_DOWN; the 30s loop continues (**verified**).
- **Bug found + fixed:** `quant_daemon.py:81` formatted
  `f"{live.get('spot', 0.0):,.2f}"` — when the feed is down with **no cached
  spot**, `live["spot"]` is `None` and the format string raises `TypeError`,
  killing the daemon on the very first down-cycle. Fixed to render `N/A` when
  spot is None. The fix requires a daemon restart to take effect for the
  running process (PID 514766).
- Feed restoration: next cycle picks up the fresh tick (loop is stateless
  across feeds).
- Exception recovery: an **unexpected** exception in a cycle is still
  fail-stop — it propagates, the reason is visible in the traceback, and the
  PID file is removed via `finally`. There is no supervisor/auto-restart
  (see G3).
- Verified: `DaemonResilienceTests` (feed-failure survival + fail-stop with
  PID cleanup).

---

## 13. Timeout / Retry Behavior

| Feed | Timeout | Retries | Backoff |
|---|---|---|---|
| NSE (data_fetcher) | 20s connect / 25s request | 0 | none |
| Yahoo chart (data_fetcher) | 25s | 0 | none |
| yfinance spot (live_market_fetch) | yfinance default | 0 | none |
| Research DB quotes | sqlite read-only | 0 | none |

No aggressive retries were added (per phase rules). The 30s daemon cadence is
the natural retry. Report missing resilience controls as gaps → see G1–G5.

---

## 14. Position / Paper Account Safety — PASS

During failure/recovery the paper account stays consistent: cash only changes
on actual fills; realized P&L is booked NET (gross − fees, slippage embedded in
fill prices); no accidental position creation (STAY_OUT/STAND_DOWN gates);
MTM with missing quotes uses flagged entry-price valuation. Verified across
`OpenPositionFeedLossTests`, `RecoveryTests`, `DuplicatePreventionTests`.

---

## 15. Ground Truth Safety — PASS (MATCH)

- No fabricated observation marked REAL: `record_signal_chain` with no spot
  records `valid=0` and provenance `status=MISSING` (verified).
- No duplicate signal/execution/outcome (see §9). Provenance stays honest.
- Append-only triggers verified present for all chain tables.
- `record_signal_chain` freshness is stored from `truth.file_freshness`.

---

## 16. Production Data Safety — PASS

All failure injection used temp fixtures (`PaperExecutionEngine(account_file=tmp,
gt_db_file=tmp)`, patched daemon PID/LOG paths, mocked feed functions). Tests
never wrote to `data/ground_truth.db`, `data/research.db`, `data/nifty_history.csv`,
or the daemon PID/log. `ProductionIsolationTests` asserts no stray files appear
under `data/` beyond daemon-owned files (nifty_history.csv, india_vix.csv,
ground_truth.db, paper_account.json, history.db, quant_daemon.log).

Note: a production daemon (PID 514766) is running and legitimately writes
observations (327 signals to GT) — that is daemon behavior, not test behavior.

---

## 17. Known Gaps (reported, not silently changed)

- **G1 (moderate):** `live_market_fetch._last_real_spot()` fallback has **no age
  gate**. On total feed loss the last recorded spot (potentially from the prior
  close if tick_recorder is down) is accepted as the live cache row and used for
  signal computation. `auto_paper_runner` only checks `if not spot`, not
  freshness. Recommended: stamp `status=CACHED_REAL` + `age_s` and gate
  spot-anchored evaluation on `truth.LIVE_SPOT_FRESHNESS_S`.
- **G2 (low):** OI snapshot consumption (`precision_signals.py:159` reads
  `snaps[-1]`) has **no freshness budget and picks the last lexicographic file,
  not the newest mtime**. A stale snapshot can feed the options layer silently
  (it still cannot fabricate a PASS, but it is not flagged).
- **G3 (moderate):** `quant_daemon` has **no per-cycle `try/except`** — an
  unexpected exception in capital-guard/VaR/MTF/volume/signal code is fail-stop
  (visible traceback + PID cleanup, but no auto-restart). The feed-failure crash
  was fixed; a supervisor/systemd restart policy is the recommended follow-up.
- **G4 (info):** no retry/backoff on transient Yahoo/NSE failures (single
  attempt per cycle). Acceptable per phase rules (30s cadence is the retry).
- **G5 (info):** the `_last_real_spot` fallback dict has **no `status` key**, so
  consumers cannot programmatically distinguish CACHED_REAL from LIVE_REAL.

---

## 18. Acceptance Criteria — Results

| Criterion | Result |
|---|---|
| NIFTY Feed Failure | PASS |
| OPTIONS/OI Failure | PASS |
| VIX Failure | PASS |
| All-Feed Failure | PASS |
| Fail-Closed Behavior | PASS |
| Open Position Safety | PASS |
| Stop-Loss Safety | PASS |
| Take-Profit Safety | PASS |
| Expiry Safety | PASS |
| Recovery | PASS |
| Missed Cycle Handling | PASS |
| Duplicate Prevention | PASS |
| Freshness Recovery | PASS |
| Daemon Resilience | PASS (feed-failure crash fixed) |
| Ground Truth Integrity | PASS |
| Reconciliation | PASS |
| Production Isolation | PASS |
| Tests | PASS (34 new; 356 total) |
| Strategy Unchanged | YES |
| No Fabricated Data | YES |

---

## 19. Files Changed

- `quant_daemon.py` — None-safe daemon log line (feed-failure crash fix).
- `tests/test_phase_g_network_resilience.py` — new (34 tests, full matrix).
- `audit/PHASE-G-NETWORK-RESILIENCE.md` — this document.
