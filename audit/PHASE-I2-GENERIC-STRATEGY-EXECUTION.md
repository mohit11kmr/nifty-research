# Phase I.2 — Generic Strategy Execution Layer (Audit Report)

**Experiment id:** `phase_i2_generic_execution_v1`
**Date:** 2026-08-16
**Status:** COMPLETED — every frozen Phase I.1 proposal now has an explicit
execution-family diagnosis or a deterministic generic backtest; findings
preserved for human review; no auto-promotion.

---

## 1. Objective

Phase I.1 recorded all six generated proposals as `EXECUTION_UNSUPPORTED`
(no engine-registered strategy id) **without** a per-proposal reason. Phase I.2
adds a **generic, capability-checked execution layer** built exclusively from
registered deterministic project primitives, then replays the six frozen
proposals through it.

Deliverable: each proposal resolves to a registered deterministic execution
family, OR fails with a structured `EXECUTION_UNSUPPORTED: <CODE>: <reason>`
diagnosis. The research output shape, evaluation vector and baseline
comparison are unchanged from the engine path.

## 2. Method (spec sections 1/5/15/19)

- **Scope:** only proposals whose `strategy_id` is NOT engine-registered are
  routed to the generic layer; the three frozen engines
  (`current_control_v1`, `directional_spread_v1`, `range_hv_iron_condor_v1`)
  keep the untouched `BacktestAdapter` path.
- **Layer:** `strategy_execution.py` (deterministic executors),
  `strategy_execution_registry.py` (family resolution + capability gates),
  `strategy_execution_capabilities.py` (declarative capability matrix).
- **Replay:** `ai_phase_i2_replay.py` — reads frozen
  `strategy_proposals/phase_i1/proposals/*.yaml`, runs each through the
  existing `run_research` pipeline (generic branch), writes **only** to
  `results/phase_i2/`. It never calls `persist_research` (would mutate the
  frozen phase_i1 registry) and never calls `evaluate_proposal` (would write
  into `results/phase_i1/`).
- **Determinism (spec section 20):** every supported replay is run twice and
  the `result_hash` must be identical. The engine-backed control
  (`current_control_v1`) is computed exactly once and reused for all six
  baselines.
- **Fixed environment:** manifest hash
  `ff068e6d54094f696ce02ea357503251fb0ce973b286fcaa4f357bedbd7fa57a`, window
  `2025-08-13..2026-08-13`, dev/OOS cut `2026-03-01`, min trades 20,
  cost ₹40/order + 1.5% slippage, lot 75.

## 3. Capability matrix (spec section 7)

Only families with a deterministic implementation **and** dedicated tests are
claimed (`tests/test_phase_i2_execution_capabilities.py`). All are EOD,
defined-risk, with canonical stop/target/MTM and cost model support.

| family | multi_leg | risk basis | risk_semantics | tests |
|---|---|---|---|---|
| `OPTION_BUY` | no | premium paid on the single long option | DEFINED (max loss = entry premium) | yes |
| `CALL_CREDIT_SPREAD` | yes | wing width minus net credit | DEFINED (max loss = \|long−short\| − entry_credit) | yes |
| `IRON_CONDOR` | yes | call wing width (or put wing width) | DEFINED (max loss = wing width − entry_credit) | yes |

Not claimed this phase (deterministic primitives exist but no tests / no I.1
need): `PUT_CREDIT_SPREAD`, `BULL_CALL_SPREAD`, `BEAR_PUT_SPREAD` → resolve but
report `FAMILY_NOT_REGISTERED` (see §9).

## 4. Replay results — six frozen proposals

| proposal | strategy_id | resolved family | outcome | reason |
|---|---|---|---|---|
| `phase_i1_big_pickle_p1` | `trend_pullback_call_v1` | `OPTION_BUY` | **BACKTESTED**, 0 trades | honest literal evaluation (see §6) |
| `phase_i1_big_pickle_p2` | `range_fade_stretch_v1` | `CALL_CREDIT_SPREAD` | **BACKTESTED**, 0 trades | honest literal evaluation (see §6) |
| `phase_i1_big_pickle_p3` | `maxpain_brokenwing_condor_v1` | — | **NOT_RUN** | `POSITION_CONSTRUCTION_UNSUPPORTED`: asymmetric / broken-wing / max-pain condor — not the symmetric four-leg structure |
| `phase_i1_deepseek_p1` | `trend_breakout_v2` | `OPTION_BUY` (resolved) | **NOT_RUN** | `DATA_FIELD_UNSUPPORTED`: condition `oi_wall_break` compares strike-typed `OI_WALL` against vacuous constant `> 0.5` (sub-1000) |
| `phase_i1_deepseek_p2` | `range_hv_condor_v1` | `IRON_CONDOR` | **BACKTESTED**, 12 trades | deterministic condor replay, RANGE_HV only |
| `phase_i1_deepseek_p3` | `trend_breakout_condor_v1` | — | **NOT_RUN** | `POSITION_CONSTRUCTION_UNSUPPORTED`: `strike_selection.params.wing_multiplier = 1.5` → asymmetric wings |

All six were validated and compiled cleanly (Phase I gates, no bypass); all
descriptions are EOD (granularity gate passes); reproducibility `True` on
every supported replay.

## 5. Backtested results

| proposal | family | trades | net P&L | PF | win% | fees | slippage | status | OOS |
|---|---|---|---|---|---|---|---|---|---|
| big_pickle_p1 | OPTION_BUY | 0 | 0.0 | 0.0 | — | 0.0 | 0.0 | INSUFFICIENT_DATA | 0 |
| big_pickle_p2 | CALL_CREDIT_SPREAD | 0 | 0.0 | 0.0 | — | 0.0 | 0.0 | INSUFFICIENT_DATA | 0 |
| deepseek_p2 | IRON_CONDOR | 12 | −1027.5 | 0.892 | 66.7 | 3840.0 | 3207.75 | INSUFFICIENT_SAMPLE | 2 |

Control (engine-backed, unchanged): `current_control_v1` = 48 trades,
+1906.43, PF 1.011, win 33.3%. Baseline verdict for every replayed proposal:
`NOT_RELIABLE` (n < 20).

## 6. Honest-literal findings (spec section 15)

- **big_pickle_p1 (`VIX_ZONE != "RICH"`):** the day record stores
  `vix_zone = "VIX_RICH"` but the literal is `"RICH"`. Evaluated **literally**
  (never fudged by prefix-stripping) the condition is always true; the
  remaining gates decide the day. This is a spec-authoring bug, preserved and
  documented — Phase I.2 does not rewrite frozen strategy semantics.
- **big_pickle_p1 0 trades:** entry is `TREND_HV` + `ADX > 25` + `45 ≤ RSI ≤ 55`
  + EMA alignment. Only 31/245 days are TREND_HV and those run RSI 57–72, so
  the RSI≤55 cap leaves zero qualifying days. Honest.
- **big_pickle_p2 0 trades:** entry is `RANGE_HV` + `VIX 16–25` +
  `RSI ≥ 72` + regime gate + options layer + `sell_ok`. RSI ≥ 72 occurs on only
  3/245 days; none satisfy the full conjunction. Honest.
- **deepseek_p1:** `OI_WALL > 0.5` is vacuous because `OI_WALL` is a strike
  LEVEL (int/float, e.g. 24500.0), not a fraction — flagged by the
  strike-typed vacuous-comparison gate before execution. `FII_SENTIMENT` also
  has only 59/245 window days (24.1% coverage, < 50% floor). Either alone
  blocks execution; the gate reports the first.
- **Option-side discipline:** `NAKED_OPTION` requires exactly one
  `option_side`; `DEFINED_RISK_DIRECTIONAL` requires exactly one side with a
  declared credit/debit cash-flow note (`RISK_SEMANTIC_UNDEFINED` otherwise);
  `DEFINED_RISK_RANGE` requires `[CE, PE]` symmetric (asymmetric detection:
  `params`, broken-wing/max-pain tokens in note or id).
- **Premium units are family-explicit:** OPTION_BUY uses premium-per-unit
  (entry = chain LTP else BS(σ=0.15)); the credit vertical uses net credit =
  short − long per unit (fill in/out with adverse slippage, 4 orders/round
  trip); the condor uses net credit with 8 orders/round trip. Control premium
  is never reused across families.

## 7. Gates implemented (order of application)

1. Granularity gate — intraday/tick/min tokens in the description →
   `GRANULARITY_UNSUPPORTED`.
2. Family resolution — instrument × mode × sides × risk note →
   registered family or structured failure.
3. Vacuous strike-typed data gate — `OI_WALL`/`MAX_PAIN` vs < 1000 constant →
   `DATA_FIELD_UNSUPPORTED`.
4. Registered-family gate — resolved family without executor/tests →
   `FAMILY_NOT_REGISTERED`.
5. Data-field coverage gate — an entry field present on < 50% of no-skip
   window days → `DATA_FIELD_UNSUPPORTED`.
6. Entry evaluation — every condition must resolve `True`; a single
   unresolved (None) condition blocks the entry (no fabrication).
7. Contract availability (Phase F2 rule) — exact (expiry, strike, side) must
   exist in the day's chain; otherwise no trade.
8. Expiry-unresolved (spec section 13) — no expiry for the trade date → skip
   the day.

## 8. Implementation notes (spec section 15)

- **Read-only context:** `GenericContext` loads the frozen dataset once per
  `data_root` (module cache) and restores the module-level `bf.ROOT` /
  `exp_cal.CALENDAR_CSV` globals that `multi_strategy_backtest.load_inputs`
  mutates. `day_records` (multiprocessing Pool) runs once.
- **Indicators:** `indicators.add_all_indicators` does NOT emit EMA20/EMA50;
  they are added explicitly via `indicators.ema`. Indicator rows are
  trailing-only, so the full-frame value at day `d` equals the slice-≤-d value
  (the same value the frozen `evaluate_day` funnel used).
- **Option buy:** control-style strike (OI wall, else 1% OTM, round to 50),
  canonical SL/TP (ATR = max(10, 0.25·entry); SL = max(2, entry − 1.5·ATR);
  target = entry + 2·(entry − SL)), `backtest_frozen.simulate_trade` day loop,
  reason mapping STOP_LOSS→STOP / TAKE_PROFIT→TARGET / EXPIRY_SQUARE_OFF→EXPIRY.
- **Credit vertical:** `simulate_credit_vertical` mirrors the frozen condor
  exit semantics (TARGET ≤ 0.5× credit, STOP ≥ 2.0× credit, TIME at dte−2,
  EXPIRY, EOD force-close); net = (fill_in − fill_out)·lot − 4·cost; slippage =
  1.5% × (short+long in/out)·lot; max_loss = |long−short| − entry_credit.
- **Iron condor:** mirrors `run_candidate_c` single-position management
  WITHOUT the engine's VIX band (spec-driven entry only; engine constants are
  never applied to proposals).
- **Engine constants not applied to proposals:** e.g. `SPREAD_VIX_MIN/MAX`
  only apply to the registered `range_hv_iron_condor_v1` engine path.

## 9. Remaining unsupported (documented, not silent)

`PUT_CREDIT_SPREAD`, `BULL_CALL_SPREAD`, `BEAR_PUT_SPREAD` resolve to families
but are **not registered** this phase → `FAMILY_NOT_REGISTERED`. Deterministic
primitives for them exist, but capability claims require tests (spec section 7)
and no frozen I.1 proposal needs them.

## 10. Safety & isolation verification

- Writes: **only** `results/phase_i2/` (new). Verified: `results/phase_i1/`
  (10 eval.json + experiment.json) and the phase_i1 proposal registry are
  byte-identical before/after; no `*.research.json` exists in `results/phase_i1/`.
- No broker calls, no paper account, no ground-truth writes, no parameter
  optimization, no mutation of frozen proposals or frozen engine strategies.
- No arbitrary Python/AI code is executed (no eval/exec/import of proposal
  content); project-rule entry references resolve ONLY against the curated
  `strategy_schema.PROJECT_RULE_ALLOWLIST`.
- No fabricated fills/quotes/OI/expiry; no lookahead (trailing-only
  indicators; day-record funnel identical to the frozen engine).

## 11. Tests (spec section 22)

New: `tests/test_phase_i2_execution_capabilities.py` — 23 tests
(21 fast + 2 slow):
- capability matrix, granularity gate, vacuous strike gate, coverage gate,
  credit/debit semantics, asymmetric-condor detection, six-proposal
  classification, compile gates (supported/unresolvable/unregistered/
  granularity), literal-evaluation honesty, missing-field honesty,
  frozen-I.1-artifacts-untouched.
- slow regression: engine path unchanged (control 48 trades / 1906.43 /
  1.011) + generic replay determinism (result_hash stable across reruns).

Regression run (all green, 63 tests):
- `tests.test_phase_i_research` — Phase I research pipeline incl. frozen
  equivalence.
- `tests.test_phase_i1_multi_model` — frozen I.1 experiment still reports
  `EXECUTION_UNSUPPORTED` via `evaluate_proposal` (untouched).
- `tests.test_phase_h_multi_strategy` — Phase H engines unchanged.

## 12. Findings for human review

- `deepseek_p2` (`range_hv_condor_v1`) is the only proposal that produces
  trades (12) — but n<20 → `NOT_RELIABLE`, net −₹1,027.50, PF 0.892. Request
  more data; do not promote.
- `big_pickle_p1` / `big_pickle_p2` are self-selecting no-trade entries under
  literal evaluation (see §6) — the strict entry is the proposal's own design,
  not an execution artifact.
- `big_pickle_p3`, `deepseek_p1`, `deepseek_p3` are genuinely
  non-executable by a symmetric deterministic family on this dataset.

**Verdict: EXECUTION_SUPPORTED for `deepseek_p2` (IRON_CONDOR); all others
carry an explicit, auditable `EXECUTION_UNSUPPORTED` code + reason. No
auto-promotion.**
