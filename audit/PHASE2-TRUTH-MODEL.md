# PHASE 2 — Truth Model & False-Confidence Elimination

> Design deliverable. Built 2026-08-13. No application code modified.
> Covers master-prompt phases 1–4: evidence reconciliation → truth map →
> Truth Layer design → eliminate false confidence.

---

## 1. Evidence reconciliation (Phase 1)

The X-Ray documents (X01–X08) and the earlier audit reports conflict on several
High findings. Per the mandate to reconcile rather than trust filenames, every
disputed claim was **re-verified against the current working tree (HEAD
`cf132ca`, "Remediate audit findings and untrack sensitive runtime state")**.

### 1.1 Disputed findings — reconciled by empirical check

| Disputed claim | X-Ray doc | FINAL-AUDIT-REPORT | Current code (verified 2026-08-13) | Verdict |
|---|---|---|---|---|
| `precision_signals` hardcodes 80% consensus (H1) | present | RESOLVED | **FIXED** — layers compute from real data; `NOT_COMPUTED`/`NEUTRAL` on missing; docstring "no hardcoded spot/VIX/consensus is ever presented as live" | **CONFIRMED: fixed** |
| `capital_guard` 1-lot floor (H2) | present | RESOLVED | **FIXED** — "No 1-lot floor… returns 0 lots + status TRADE_BLOCKED" | **CONFIRMED: fixed** |
| Hardcoded spot/vix reported as live (M1) | present | RESOLVED | precision_signals **fixed**; but `run_all.py:162`, `live_ticker_service.py:26-27,39-40`, `smart_strike_selector.py:30,116` **still hardcode 24403.10 / vix 12.0** | **PARTIAL: core fixed, periphery remains** |
| `history_logger` per-call connect (M5) | per-call | RESOLVED | **FIXED** — one persistent WAL + busy_timeout connection | **CONFIRMED: fixed** |
| `date(recv_ts)` full-table scan (PF-H1) | full scan | RESOLVED | **FIXED** — `live_dash.py` uses sargable `recv_ts >= ? AND recv_ts < ?` bounds + index | **CONFIRMED: fixed** |
| research.db unbounded (PF-H2) | unbounded | RESOLVED | `data_retention.py` exists (30-day purge, `--vacuum`) but **not wired into any scheduler** — manual only; DB now 258 MB | **PARTIAL: tooling exists, automation missing** |
| audit DB + paper account in git (S-H1) | tracked | RESOLVED | **FIXED** — `git ls-files` shows no sensitive state | **CONFIRMED: fixed** |
| `.env` 0644 (M6) | 0644 | RESOLVED | **FIXED** — 0600 | **CONFIRMED: fixed** |
| `requests` CVE / mcp CVEs | old | RESOLVED | **FIXED** — requests 2.34.2, mcp 1.29.0, pip 26.2.1 (lock file) | **CONFIRMED: fixed** |

**Conclusion:** X01–X08 describe a mix of pre- and post-remediation states.
The core signal-integrity fixes (H1, H2, M1-core, M5, PF-H1, S-H1, M6, dep CVEs)
are **CONFIRMED present in the current tree**. X01–X08 must be read as a
*pre-remediation baseline* for those items. The remaining unremediated items
below are the true Phase-2 backlog.

### 1.2 Findings still present in current code (verified)

| ID | Location | Detail | Class |
|---|---|---|---|
| F1 | `run_all.py:162` | step 13 calls `select_best_strike(spot_price=24403.10, "CE")` — hardcoded | CONFIRMED |
| F2 | `live_ticker_service.py:26-27,39-40` | yfinance failure → hardcoded spot 24403.10 / vix 12.0 presented as tick | CONFIRMED |
| F3 | `smart_strike_selector.py:30,116` | `DEFAULT_SPOT = 24403.10`; param default | CONFIRMED |
| F4 | `lstm_neural_engine.py:16-19` | deterministic `mean(linspace(0.8,1.2))·0.52+0.08` = 0.60 always; labeled "simulated" in comment but presented as engine output in run_all step 6 | CONFIRMED |
| F5 | `market_brain.py:135,168-181` | frozen "TRAINED" constants (0.45/0.30, reliabilities 0.49/0.46/0.55/0.46); trainer never writes back | CONFIRMED |
| F6 | `premium_seller.py:160` | `units * 25` — lot 25 vs platform 75; headline 72.5%/PF 2.6 inconsistent with platform | CONFIRMED |
| F7 | `monte_carlo.py:13,15,29` | `np.random.seed(42)`, hardcoded WR 0.55 → deterministic; "PASSED" not evidence | CONFIRMED |
| F8 | `var_risk_manager.py:74-98` | stress = `capital × drop × 0.5` at fixed 0.5Δ → always PASSED | CONFIRMED |
| F9 | `volume_profile.py:26` | missing volume → `np.random.randint(1000,5000)` fabricated | CONFIRMED |
| F10 | `volatility_forecaster.py:26-29` | <10 samples → seeded fabricated returns | CONFIRMED |
| F11 | `auto_enhancer.py:35-43` | writes "automatically updated weights, volume profile zones, and risk limits" — adaptive_weights is an honest no-op, audits are read-only | CONFIRMED (false success claim) |
| F12 | `super_ai_ml.py:42-92` | 80/20 fixed chronological split; fixed hyperparams; no persistence; context-only per AGENTS.md | CONFIRMED |
| F13 | `paper_trade_journal` table + CSV | created in `history_logger.py`, referenced in `backup_data.py:34`, **never INSERTed** | CONFIRMED (dormant) |
| F14 | `multi_agent_swarm.py` | 0 importers — dead | CONFIRMED |
| F15 | Data staleness | `data/ml_features.csv` Aug 08, `data/tf_scan.csv` Aug 08 vs `data/nifty_history.csv` Aug 13 — ML/tf consumers silently read stale caches | CONFIRMED |
| F16 | run_all step 17 | imports `skew, equity_quant, mcx_intel` and prints "Executed" — **never calls them** | CONFIRMED |
| F17 | `data_retention.py` | exists but unscheduled; research.db 258 MB and growing | CONFIRMED |

### 1.3 Findings previously claimed but NOT reproduced

| Claim | Status |
|---|---|
| QA-M3 strike grid rounding → non-existent strikes | **REJECTED (false positive)** per FINAL-AUDIT; grid is 50 pts and correct |
| LSTM trained network | **PROBABLE: never was** — code is a formula (F4) |
| trainer→market_brain feedback loop | **CONFIRMED absent** — trainer is manual-only, constants frozen (F5) |

---

## 2. System Truth Map (Phase 2) — what it really does today

| Capability / Claim | Implementation | Evidence | Status |
|---|---|---|---|
| Signal generation (A+ grade) | 6-layer confluence, all layers from real data; grade gated on PASSED count | `precision_signals.py:58-208` | **REAL** (core); peripherals still carry hardcoded fallbacks (F1–F3) |
| ML prediction | sklearn walk-forward (`ml_engine`) + XGB/LGBM/RF (`super_ai_ml`), both context-only, no persistence | AGENTS.md; X06 | **REAL but context-limited; stale cache** (F15) |
| Performance claims | 42.8% trainer hit-rate; 72.5% premium-seller | `results/training_report.md`; `premium_seller.py:160` | **REAL measurement (42.8%)**; **MISLEADING (72.5%, lot-25)** |
| Backtesting | BS option/underlying with slippage 1.5%, ₹40 cost; genuine walk-forward only in ml_engine | `backtester.py` | **REAL** (cost model unvalidated vs live fills) |
| Risk management | 1% sizer (no floor), 3%/7% limits, 0DTE trap, event-risk | `capital_guard.py` | **REAL**, remediated; event-risk always NO_EVENT_DATA |
| Adaptive learning | Q-learning weight file + auto-enhance + reflection | `adaptive_weights.py`, `auto_enhancer.py` | **FABRICATED as a claim (F11)** — actual behavior is honest no-op, nothing consumed |
| Market regime | 4-regime gate + VIX zones + expected move | `regime_filter.py` | **REAL** |
| Execution simulation | paper ledger + gated auto-trader (1 lot × 75) | `paper_trader.py`, `auto_paper_runner.py` | **REAL**, but no persistent journal rows (F13) |
| Outcome tracking | `tick_history`/`signal_history` audit trail | `history_logger.py` | **REAL for market+signal**; **MISSING for trade outcomes** (F13) |
| Self-improvement | none beyond decorative state | — | **MISSING** (Level 0/1, see Self-Improvement doc) |

---

## 3. Truth / Provenance Layer design (Phase 3)

### 3.1 Result status vocabulary

Every generated result carries exactly one status:

```
REAL               — computed from observed data (no substitution)
SIMULATED          — model output under explicit assumptions (paper, backtest)
ESTIMATED          — derived/implied (reconstructed IV, MFE interpolation)
FALLBACK           — substituted value because primary source unavailable
STALE              — computed from data older than its freshness budget
MISSING            — not computable (no data, never set)
INVALID            — violates invariants (timestamp in future, leak detected)
FABRICATED/UNSUPPORTED — produced by hardcoded/synthetic substitution
```

### 3.2 Common result metadata (provenance envelope)

```
source            e.g. nse_ws, yahoo, cache:nifty_history.csv, paper_account.json
timestamp         when this result object was produced (UTC ISO)
data_timestamp    max observed data time used in computation
data_freshness    age of newest + oldest input (seconds)
feature_version   hash of the feature-set definition used
model_version     model id + training data window (None for rules)
parameter_version hash of all thresholds/constants consulted
signal_version    hash of the signal definition (layer set + weights)
fallback_used     true/false
fallback_reason   enum: NO_DATA / EXCEPTION / STALE / NONE
confidence        only if statistically calibrated; else null
evaluation_method how any accuracy number was derived (walk-forward/OOS/in-sample)
environment       python version, deps lock hash, git commit
execution_mode    LIVE / PAPER / BACKTEST / DRY_RUN
```

### 3.3 Where metadata enters the pipeline

1. **At the acquisition boundary**: every cache-writer stamps provenance into a
   per-dataset sidecar (`data/<name>.meta.json`) — fetch time, source, rows,
   completeness. `live_market_fetch`/`build_data`/`tick_recorder` write it.
2. **At every engine boundary**: each engine returns `{result, provenance}` —
   the engine declares what it read (`data_freshness`, `fallback_used`) instead
   of the caller guessing.
3. **At the signal boundary**: `precision_signals` embeds per-layer status in
   the output dict (already partially present as `checks[]`); promote that to a
   structured provenance block persisted with the signal.
4. **At persistence**: `history_logger` extends tables with a `provenance_json`
   column; new tables (outcome/experiment) carry it natively.
5. **At presentation**: MCP tools + dashboards surface status badges
   (REAL/SIMULATED/FALLBACK/STALE) instead of raw numbers.

### 3.4 Minimum viable implementation (no new framework)

- A single `truth.py` helper module with:
  - `Status` enum + `envelope(...)` builder
  - `hash_version(dict)` for feature/param/signal versions
  - `freshness(path, budget_h)` checker used by build_data and every cache reader
- Sidecar `.meta.json` per dataset, written on cache write, read by consumers.
- Migration of the 3 audit tables to include `provenance_json TEXT` (nullable).

### 3.5 Rules this layer enforces

- A `FALLBACK` result may not be labelled REAL downstream; it may only be
  reported as FALLBACK.
- Any result older than its freshness budget is downgraded to STALE at read time.
- Any module that fabricates (`np.random`, hardcoded literals as data) must tag
  output `FABRICATED/UNSUPPORTED` — making F4/F9/F10 visible rather than silent.
- One registry (single source of truth) for `feature_version`, `model_version`,
  `parameter_version`, `signal_version` — the things that are currently frozen
  or duplicated.

---

## 4. Eliminate false confidence (Phase 4)

| # | Claim | Why misleading | Evidence | Correct interpretation | How to replace | Priority |
|---|---|---|---|---|---|---|
| 1 | "Platform has automatically updated weights, volume profile zones, and risk limits" | Nothing is mutated; adaptive_weights is an honest no-op | `auto_enhancer.py:35-43`; `adaptive_weights.py` no-op branch | `AUTO_ENHANCEMENT_NOOP` — audited, changed nothing | Re-word verdict to reflect reality; status REAL vs NOOP | **P0** |
| 2 | market_brain "TRAINED RULES / ~70%" | Constants frozen; measured hit-rate 42.8% (n=194) | `market_brain.py:121-181`; `results/training_report.md` | Calibration is stale/frozen; below coin-flip in test | Move to `data/market_brain_params.json` + provenance; display measured value | **P0** |
| 3 | LSTM 0.60 "prediction" | Deterministic formula, no data, no network | `lstm_neural_engine.py:16-19` | Cosmetic demo, zero information | Remove from run_all or tag `SIMULATED/UNSUPPORTED` | **P0** |
| 4 | Monte Carlo "PASSED" | seed 42 + hardcoded WR ⇒ deterministic | `monte_carlo.py:13,29` | Illustrative, not evidence | Parameterize from real outcome distribution; report CI | **P1** |
| 5 | VaR stress "PASSED_ALL_3" | `capital × drop × 0.5` formula, not a simulation | `var_risk_manager.py:74-98` | Hedged-loss formula | Estimate from real portfolio greeks; report uncertainty | **P1** |
| 6 | Premium-seller 72.5% / PF 2.6 | lot 25 vs platform 75 | `premium_seller.py:160` | Wrong unit → misleading edge | Re-run at 75; publish both | **P1** |
| 7 | "ULTRA_ROBUST" (long-term) | single-threshold label on an unaudited backtest | `long_term_backtest.py:130` | Marketing label | Use calibrated metrics + caveats | **P2** |
| 8 | run_all step 17 "Executed" | imports only; nothing runs | `run_all.py:196-204` | Dead print | Remove or actually invoke | **P2** |
| 9 | Hardcoded 24403.10/12.0 fallbacks | presented as live | F1–F3 | Fake-live | Route through live_market_fetch (honest UNAVAILABLE) | **P0** |
| 10 | 42.8% trainer hit-rate | genuinely measured but below coin-flip and not used | `results/training_report.md` | Honest but fatal to any "trained" claim | Keep as baseline; never present as edge | P1 |

### 4.1 Design guard: unsupported claims cannot silently reappear

1. **Provenance enforcement**: no number reaches MCP/report without a status
   tag; presentation layer renders `FABRICATED/UNSUPPORTED` distinctly.
2. **Verdict templates**: `auto_enhancer`-style success strings must be derived
   from actual diff of state (before/after), not hardcoded.
3. **Frozen-constant audit**: a CI check greps for `TRAINED`, `ULTRA_ROBUST`,
   `PASSED_ALL`, `seed(42)` and fails with a provenance-required notice.
4. **Single registry**: all thresholds live in versioned params (not source
   literals) so "trained" is only ever used when a writer updated it.
