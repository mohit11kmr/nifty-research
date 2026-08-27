# Phase 3 — Truth & Provenance Layer: Implementation Report

> Date: 2026-08-13 | Base commit: `cf132ca` (Remediate audit findings...)
> Roadmap items: **P-01, P-02, P-03, P-04, P-09** (from
> `audit/PHASE2-IMPLEMENTATION-ROADMAP.md` Phase 1 — Truth & Provenance).

## What was implemented

### 1. Shared truth contract — `truth.py` (NEW, root-level)

A single small module (no framework) implementing the design in
`audit/PHASE2-TRUTH-MODEL.md` §3:

- **Status vocabulary**: `REAL, SIMULATED, ESTIMATED, FALLBACK, STALE,
  MISSING, INVALID, UNSUPPORTED`.
- **`envelope(result, status, source, timestamp, data_timestamp,
  fallback_used, fallback_reason, evaluation_method, **extra)`** — attaches a
  provenance envelope to a result dict without mutating the input; only
  populated keys are emitted.
- **`hash_version(payload)`** — stable SHA-256 content hash (for
  feature/parameter/signal versioning later).
- **Freshness**: `freshness_status(age_s, budget_s)` (REAL/STALE/INVALID/
  MISSING), `file_freshness(path, budget_h)`, and
  `asset_freshness_report()` scanning the known dataset cache against
  budgets taken from existing project rules (not invented):
  - daily cache (nifty_history, india_vix, ml_features, tf_scan, oi_snapshots):
    **20h** — `build_data.py::_fresh(max_age_h=20)`
  - FII/DII: **6h** — institutional cache rule
  - live spot: **120s** — 60s sampling from `tick_recorder.py` (budget helper
    present, live consumers not yet wired)

> Note: the roadmap suggested `platform/truth.py`; the repo is a flat 90-file
> layout, so a root-level `truth.py` was used to avoid a new package + import
> rewrite (minimal scope per spec Phase 15).

### 2. Silent hardcoded market fallbacks removed (P-01)

Traced each fallback (why added / trigger / consumers / safe handling):

| File:line (old) | What | Now |
|---|---|---|
| `run_all.py:162` `select_best_strike(spot_price=24403.10)` | fake live spot | real spot from `regime_filter.trade_plan().get("close")`; MISSING → honest stand-down print |
| `run_all.py:103` `atm_strike = ... else 24500` | fake strike for token lookup | token lookup skipped with `MISSING` message when no real spot |
| `live_ticker_service.py:26-27` `else 24403.10 / 12.0` | fake live tick | live fetch → `REAL`; else last real spot from `research.db:spot` → `FALLBACK` + `fallback_reason`; else `MISSING` (spot=None, stream stands down, nothing logged) |
| `live_ticker_service.py:39-40` `CACHED_TICK` with `24403.10/12.0` | fabricated cache tick | replaced by the honest chain above (Vix `None` on fallback, never `12.0`) |
| `smart_strike_selector.py:30/116/119` `DEFAULT_SPOT=24403.10` | fake spot default | `select_best_strike(spot_price=None)` → `MISSING_SPOT` result with `status: MISSING`, no strike, no literal |
| `multi_leg_options.py:26/42` `DEFAULT_SPOT=24403.10` | fake spot default | `_default_spot()` returns last real cached close or `None`; `None` → honest `MISSING` result |
| `lstm_neural_engine.py:13` `spot_price=24403.10` | fake spot default | `None` default (display-only, engine already SIMULATED) |
| `volatility_forecaster.py:24` `current_spot=24278.85` | fake spot default | `None` → last real cached close; `None` → `spot_status: MISSING` |

Acceptance check: `grep 24403.10` across `*.py` (excluding tests/audit/
experiments) now returns **zero** matches. A grep-guard test enforces this.

### 3. False claims corrected with labels (P-03, P-04 + spec Phase 7)

| Module | Old claim | Now | Values unchanged? |
|---|---|---|---|
| `market_brain.py:121-181` | "TRAINED RULES / TRAINED RELIABILITY (~70%)" | `calibration: FROZEN_PARAMETER_MODEL`, `measured_hit_rate_pct: 42.8`, `measured_hit_rate_n: 194`, `reliability_source`; reasons say "Frozen parameter calibration (measured 42.8%, n=194)" | YES — thresholds & confidence math identical |
| `lstm_neural_engine.py` | "LSTM Recurrent Memory indicates..." (unsupported 0.60) | output tagged `SIMULATED` + `evaluation_method: deterministic_simulation`; insight says "deterministic, not a trained model" | YES — same weights/probabilities |
| `monte_carlo.py` | "PASSED (100% Statistical Survival)" | tagged `SIMULATED`, `random_seed: 42`; verdict "SIMULATED PASS (deterministic seed-42 scenario, parametric inputs)" | YES — same numbers (test_08 still passes) |
| `var_risk_manager.py` | `PASSED_ALL_3_HISTORICAL_CRASH_SCENARIOS`, "Kill-Switch Lock Engaged" | `evaluation_method: formulaic_estimate`, per-scenario `loss_method: ESTIMATED (formulaic capital*drop*0.5)`, survival strings "ESTIMATED PASS" | YES — same formulas |
| `auto_enhancer.py:35-43` | "Platform has automatically updated weights, volume profile zones, and risk limits for tomorrow" | `_weights_changed()` before/after diff → `AUTO_ENHANCEMENT_NOOP` + honest verdict when nothing changed; `weights_changed` flag; `volume_data_status` surfaced | YES — no-op behavior preserved |
| `volume_profile.py:26` | `np.random.randint(1000,5000)` when no volume | real volume path → `data_status: REAL`; else uniform-frequency histogram (equal weight, **no random numbers**) → `data_status: ESTIMATED` + `volume_source` note | YES when real volume present (normal path) |
| `volatility_forecaster.py:26-29` | silent `np.random.normal` returns | placeholder returns tagged `data_status: SIMULATED` + `evaluation_method: deterministic_simulation_seed42`; real returns → `ESTIMATED` | YES — same GARCH math |
| `super_ai_ml.py:4` | docstring "Walk-Forward Hyperparameter Optimization" | honest "FIXED 80/20 split (NOT walk-forward)... CONTEXT ONLY" | YES — code untouched |
| `run_all.py:201-206` step 17 | "Multi-Asset Analytics ... Executed" (nothing ran) | actually calls `skew.multi_index_scan()`, `equity_quant.scan_equity_outperformers()`, `mcx_intel.analyze_mcx_commodities()` and prints real results | YES |

### 4. Freshness surfacing (P-09)

- `truth.asset_freshness_report()` scans the dataset cache against budgets.
- `run_all.py` step 0 "Truth & Provenance" preamble prints real spot +
  every non-REAL cache entry (currently flags `ml_features.csv` and
  `tf_scan.csv` as **STALE** — 113–114h vs 20h budget).
- `super_ai_ml.py` output now carries `feature_freshness`, `feature_age_h`,
  `feature_freshness_budget_h` so ML context can't silently train on a stale
  cache. (`ml_engine.py` freshness is deferred — see Remaining.)

### 5. Truthful representation / provenance propagation (P-04, spec Phase 8)

- `live_ticker_service.stream_live_market_ticks` prints a `(FALLBACK)` tag
  when it streams a cached tick and stands down (logs nothing) when
  `MISSING`.
- `run_all.py` prints `SIMULATED - deterministic_simulation` for LSTM and
  `Method: parametric_var_zscore` for VaR.
- Verified: no MCP tool (`mcp_nifty.py`) and no report/web generator
  (`web_dashboard.py`, `systematic_report.py`, `daily_report.py`,
  `blog_post.py`) emits the old untagged overclaim strings.

## Tests

New file: `tests/test_truth_layer.py` — **26 tests**, unittest style
(matching the existing `tests/` convention). Coverage per spec Phase 10:

| Requirement | Test(s) |
|---|---|
| fresh → REAL | `test_fresh_data_is_real`, `test_fresh_file_is_real` |
| stale → STALE | `test_stale_data_is_stale` |
| missing → MISSING | `test_missing_data_is_missing`, `test_ticker_stands_down_when_nothing_available` |
| invalid → INVALID | `test_invalid_age_is_invalid`, `test_future_mtime_is_invalid` |
| fallback → FALLBACK + reason | `test_ticker_explicit_fallback_keeps_reason`, `test_fallback_provenance_survives`, `test_ticker_live_path_is_real` |
| simulation → SIMULATED | `test_lstm_is_simulated`, `test_monte_carlo_is_simulated_seed42`, `test_volatility_forecaster_tags_placeholder_returns` |
| unsupported claim → corrected | `test_market_brain_not_trained`, `test_var_is_parametric_and_stress_is_formulaic`, `test_volume_profile_no_random_volume` |
| provenance preservation | `test_envelope_adds_provenance_without_mutation`, `test_hash_version_is_stable_and_distinct`, `test_lstm_status_survives` |
| grep-guards (P-01 anti-regression) | `test_grep_guard_no_hardcoded_spot`, `test_grep_guard_no_spot_strike_fallback`, `test_grep_guard_no_fake_trained_labels`, `test_grep_guard_no_false_enhancement_claim`, `test_grep_guard_no_default_spot_constant` |

### Results (base = `cf132ca`, all run with `.venv/bin/python`)

| Check | Baseline | After | Status |
|---|---|---|---|
| `test_all.py` | 34 OK | 34 OK | PASS |
| `python -m unittest discover -s tests` | 45 OK | **71 OK** (45 + 26 new) | PASS |
| `python tests/test_fix_verification.py` | 29 OK | 29 OK | PASS |
| `pip check` | clean | clean | PASS |
| `git diff --check` | — | clean | PASS |
| `python -m pytest tests/ -q` | not available | not available | REPORTED (not installed; do not install per spec) |
| `pip-audit` | not available | not available | REPORTED (not installed) |
| `run_all.py` end-to-end | — | exit 0; honest preamble (2 STALE flags), all 23 steps execute | PASS |

## Phase 12 — Remaining false-truth pattern search

Search performed across `*.py` (excluding `.venv/`, `.opencode/`, `audit/`,
`tests/`, `experiments/`): hardcoded market values, `np.random` fabrication,
"trained/accuracy/robustness" claims, fake adaptive/learning claims.

**Fixed**: every item above (run_all, ticker, strike, multi-leg, LSTM,
Monte Carlo, VaR stress, market_brain, auto_enhancer, volume_profile,
volatility_forecaster, super_ai_ml docstring, run_all step 17).

**Remaining**:
- `long_term_backtest.py:130` `"ULTRA_ROBUST"` — dead module (0 importers,
  X07). Deferred to roadmap **P-16** (archive dead code); tagged in
  code review notes, never rendered by any live path.
- `ml_engine.py` reads `ml_features.csv` without emitting a freshness tag on
  its own (walk-forward model is honest; staleness is surfaced by run_all
  preamble + super_ai_ml). Deferred to P-05/P-09 wiring in Ground-Truth
  phase.
- `history_logger.log_market_tick` stores values without a provenance/status
  column — cached `FALLBACK` ticks are logged without the tag. Needs the
  schema change (`provenance_json`) from Ground-Truth phase.
- `premium_seller.py` lot-25 vs lot-75 unit (F6) — roadmap **P-10**
  (Baseline phase); label-only deferral.

**False positive / accepted (no action, would be unrelated refactor)**:
- `profit_engine.generate_profit_plan(spot=24583.8)` and
  `dynamic_trailing.compute_trailing_stops(entry_price=24500.0)` — parameterized
  *example inputs* for planning utilities with **zero consumers**; never
  rendered as live market truth.
- `skew.py` / `gamma_flip.py` `__main__` dummy-chain fixtures and
  `token_lookup.py` mock token table — explicit test data.
- `mcp_nifty.py` `vix < 12` regime threshold — real VIX band rule (AGENTS.md).

**Needs verification**:
- `expectancy_calculator` default example parameters (55% / ₹2000 / ₹1000) —
  utility defaults; verify no consumer passes them as live facts (none found).
- `quant_daemon.py` / `control_center.py` docstrings describing
  "reinforcement auto-enhancement" — they now invoke the honest NOOP engine;
  wording is aspirational but not output-fabricating.

## Phase 13 — Security & safety review

- `truth.py` performs **no I/O writes, no DB, no network**; only reads
  `os.path.getmtime` and pure computations. It cannot be abused to overwrite
  provenance or hide data.
- `envelope()` copies its input; callers at engine boundaries set status
  explicitly. No code path labels fabricated data as `REAL` — the only
  `REAL` producers are the live yfinance paths; every fallback path sets
  `FALLBACK`/`MISSING`/`SIMULATED`.
- `freshness_status` is conservative: negative/None ages and bad budgets →
  `INVALID`/`MISSING`, never downgraded to usable.
- No risk-control code (`capital_guard`, position sizing, broker paths) was
  modified; truth changes are isolated from strategy/risk behavior (spec
  Phase 9).

## Phase 16 — Final truth audit (independent answers)

1. **Can the system distinguish real vs simulated vs fallback vs stale vs
   missing?** YES — `truth.py` vocabulary + tags on LSTM, Monte Carlo, VaR
   stress, volatility forecaster, ticker, strike selector, multi-leg, volume
   profile, freshness report.
2. **Can unsupported model claims be identified?** YES —
   `FROZEN_PARAMETER_MODEL` + measured 42.8% reference on market_brain; LSTM
   `SIMULATED`; super_ai_ml honest docstring + freshness tags.
3. **Can downstream consumers preserve provenance?** PARTIAL — envelopes
   survive in dict outputs (ticker, LSTM, smart_strike); `history_logger`
   DB rows still lack a status column (deferred schema change).
4. **Can the system silently present stale/fallback data as live truth?**
   NO — ticker CACHED_TICK is tagged `FALLBACK`, MISSING stands down; run_all
   preamble surfaces every STALE cache; super_ai_ml tags `feature_freshness`.
5. **Are the old `24403.10 / 12.0` fallbacks still capable of creating false
   market truth?** NO — grep-guard test enforces zero occurrences; all
   consumers route through real-spot or honest MISSING.
6. **Are current ML labels truthful?** YES for the scope of this phase
   (LSTM, super_ai_ml, market_brain, Monte Carlo, VaR); `ml_engine` is the
   honest walk-forward model and is unchanged.
7. **Are tests proving the behavior?** YES — 26 new unit tests + grep-guards.

## Phase 17 — Acceptance criteria

| Criterion | Result |
|---|---|
| Truth contract exists | PASS (`truth.py`) |
| Freshness handling exists | PASS (20h/6h/120s budgets + report) |
| Missing-data handling exists | PASS (MISSING_SPOT, ticker stand-down, MISSING multi-leg) |
| Fallbacks are explicit | PASS (FALLBACK + fallback_reason, SIMULATED tags) |
| Unsupported claims corrected | PASS (FROZEN_PARAMETER_MODEL, NOOP, ESTIMATED) |
| Provenance survives downstream | PASS/partial (dict outputs yes; DB column deferred) |
| Tests added and passing | PASS (26 new, 71 total discover) |
| Existing tests remain green | PASS (34 + 45 + 29) |
| Security checks remain green | PASS (review above) |
| Dependency audit remains clean | PASS (`pip check` clean; `pip-audit` unavailable — reported) |
| No unrelated refactor | PASS (all changes are truth-labeling/fallback; strategy & risk untouched) |

## Remaining problems & risks

- `history_logger` and `ml_engine` provenance/status propagation needs the
  Ground-Truth schema (`provenance_json`) — do not patch around it here.
- `ml_features.csv` / `tf_scan.csv` are STALE; rebuilding them is
  `build_data.py` scope (network) and was not forced during this phase.
- `pip-audit` is not installed; dependency audit relies on `pip check`
  until the tool is added.
- `pytest` is not installed; the project's unittest suite is the source of
  truth.

## Next phase (must happen before Ground Truth + Outcome Engine)

Ground Truth & Outcome Engine can begin only after:
1. **Decision** — no structural work remains; current state is honest and
   every important claim traces to evidence.
2. **Schema agreement** — `platform/ground_truth.py` design in
   `audit/PHASE2-GROUND-TRUTH.md` reviewed against the now-honest outputs so
   prediction→decision→execution→outcome links match the real (tagged)
   result shapes.
3. **Provenance column** — add `provenance_json` to the 3 audit tables
   (`history_logger`) so the tagged statuses survive persistence.
4. **Freshness wiring** — rebuild `ml_features.csv`/`tf_scan.csv` and
   enforce the 20h budget at read time in `ml_engine`.

Then proceed to roadmap **Phase 2 — Ground Truth + Outcome Engine
(P-05, P-06, P-15)**.
