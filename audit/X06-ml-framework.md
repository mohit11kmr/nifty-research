# X06 — ML Framework Audit (X-Ray)

> X-Ray phase 6. Built 2026-08-13. Which modules are real ML, which are
> simulation, and the platform's ML-honesty discipline (AGENTS.md).

---

## 1. Classification summary (11 modules)

| Module | Actual ML? | Adaptive? | Live path? | Class |
|---|---|---|---|---|
| `ml_engine.py` | Yes (sklearn, walk-forward) | Re-fits every run; no persistence | Context only (`daily_report.py:126`) | (a)+(c) |
| `super_ai_ml.py` | Yes (XGB/LGBM/RF) | Re-fits every run; no persistence | Signal layer 6 + master brain; doc'd context-only | (a)+(c) |
| `trainer.py` | No (evaluates rule brain) | No feedback; constants hardcoded in market_brain | No caller | (b)/(c) |
| `lstm_neural_engine.py` | No (simulation) | No | run_all(6) display only | (d) |
| `adaptive_weights.py` | No (clamped ±lr) | Code can; no outcomes supplied & no consumer | Not used | (b)/(c) |
| `auto_enhancer.py` | No | No-op + boilerplate log | Daemon every 2.5 min, changes nothing | (b)/(d) |
| `reflection_engine.py` | No | Template hypotheses, never validated | run_all(15) | (b)/(c) |
| `volatility_forecaster.py` | No (fixed GARCH constants) | No; fabricates data when <10 samples | Smoke test only | (b)/(c)/(d) |
| `portfolio_rebalance.py` | No | Fixed equal-weight backtest | Manual only | (b)/(c) |
| `empirical_proof.py` | No | Fixed verification | No caller | (b)/(c)/(d) |
| `equity_quant.py` | No (formula scans) | Fixed formulas | Imported but never invoked | (b)/(c) |

**Bottom line: no module qualifies as truly (a) "self-adapting from live data
with persisted state that feeds decisions."** The only real model fitting
(ml_engine, super_ai_ml) is stateless, cache-fed, and deliberately demoted to
context/agreement-counting per AGENTS.md.

## 2. The two real ML modules

### `ml_engine.py`
- **Direction forecast + meta-blender** of 9–16 strategy signals via genuine
  **walk-forward** (`walk_forward_eval`: train_days 180/200, step 20, no shuffling).
- Out-of-sample accuracy ~**51% vs baseline ~52%** → no standalone edge.
- Direction classifier ~49% vs baseline ~52% → coin flip.
- **No model persistence** (no .pkl/.joblib anywhere in repo). Trains from
  `data/ml_features.csv` — which is **stale** (Aug 8 vs nifty_history Aug 13).
- Consumer: `daily_report.py:126` (context section only).

### `super_ai_ml.py`
- XGBoost / LightGBM / RandomForest ensemble (n_estimators=100, max_depth=4,
  lr=0.05; RF 100/5). Docstring claims "Walk-Forward Hyperparameter
  Optimization"; **actual code = fixed 80/20 chronological split, fixed
  hyperparams, retrains every call, no persistence**.
- Verdict: avg prob >0.55 → BULLISH, <0.45 → BEARISH.
- Used live as **Layer 6 of precision_signals** (+1 point if non-neutral) and
  **Dimension 4 of live_trader_brain**; exposed as MCP `super_ai_ml_context`.
- AGENTS.md marks it **"CONTEXT ONLY (~51% vs 52% baseline, no standalone edge)"**.

## 3. The "learning theater" modules

### `trainer.py`
- Evaluates the **rule-based** market_brain walk-forward; writes
  `results/predictions_log.csv` (246 rows) + `results/training_report.md`
  (overall hit-rate **42.8%, n=194**).
- **No caller** — manual `python trainer.py` only.
- Results were baked into market_brain as **compile-time constants**
  (call_thresh 0.45 / put_thresh 0.30; reliabilities 0.49/0.46/0.55/0.46) with
  comments claiming "TRAINED RULES". Trainer never writes back → frozen.

### `adaptive_weights.py`
- Q-learning-style: reward ±`learning_rate(0.05)`, clamp [0.2, 3.0].
- `update_adaptive_weights()` only changes weights **when `trade_outcomes` is
  supplied** — **no caller ever supplies outcomes** (auto_enhancer calls it with
  no args). And `load_adaptive_weights` has **zero consumers**.
- Current file (2026-08-13) shows rsi=0.2, supertrend/pcr/skew=3.0 — pinned at
  clamp bounds (decorative state; nothing reads it).

### `auto_enhancer.py`
- Calls (1) adaptive_weights no-op, (2) volume_profile read-only audit,
  (3) capital_guard read-only audit — then writes: *"Platform has automatically
  updated weights, volume profile zones, and risk limits for tomorrow's market
  session."* → **a claim that is false** (nothing mutates).
- Overwrites `enhancement_log.json` each run. Runs every 5th daemon cycle.

### `reflection_engine.py`
- Two hardcoded templates: WR < 50% → "increase ATR stop 1.5x→2.0x"; else →
  "expand RR 1:2 → 1:2.5". Appends to `reflection_hypotheses.jsonl`.
- **Zero consumers**; hypotheses never validated/applied.
- Current file: **7 identical entries all generated against an empty paper
  account** ("Win Rate is 0.0% across 0 trades").

## 4. Fake / simulation modules

### `lstm_neural_engine.py` (claim: 15-min LSTM RNN)
- No NN, no tensorflow/pytorch, no data input. "Recurrent weights" =
  `np.linspace(0.8, 1.2, lookback_bars)`; output `bullish_prob =
  clamp(mean(w)·0.52 + 0.08)` = **0.60 every call** → always
  `LSTM_BULLISH_SEQUENCE`. `spot_price` used only for display. run_all step 6.

### `volatility_forecaster.py`
- "GARCH(1,1)" = **single one-step update** `σ² = ω + α·r² + β·σ²` with
  hardcoded ω=2e-6, α=0.08, β=0.90 — never estimated from data (no MLE/fit).
- <10 samples → fabricates `np.random.seed(42); normal(0,0.0025,50)`.
- Smoke-test only.

### `long_term_backtest.py` (in infra sweep)
- "46-year" S&P/BSE Sensex audit; verdict string hardcoded **"ULTRA_ROBUST"**.

## 5. Honesty rules actually enforced (AGENTS.md)

- Report accuracy AND baseline AND edge; no shuffling (time-series).
- ML = context/agreement counter only, never a buy/sell trigger.
- Don't retrain repeatedly hunting for edge (overfit warning documented).

## 6. Cross-cutting findings

1. **No trained model is ever persisted** (no .pkl/.joblib/.pt/.h5/.onnx).
2. Two modules advertise learning that is not wired: adaptive_weights
   (no consumer + no outcomes) and reflection_engine (never validated).
   auto_enhancer logs a false "weights updated" success.
3. lstm_neural_engine is deterministic formula as deep-learning theater.
4. ml_engine + super_ai_ml genuinely fit models but are context-gated and
   **train on a stale cache** (ml_features Aug 8 vs nifty_history Aug 13).
5. trainer.py output (42.8% hit-rate, below coin flip) contradicts the
   "70%" reliability comment in market_brain — the frozen constants overstate
   skill relative to measured evidence.

## 7. Recommendation state (unchanged since first pass)

Keep ML demoted to context. If re-derived: fresh walk-forward, edge vs baseline
reported, persisted model + cache rebuild, and trainer.py must write back into
a *runtime config* (not source literals) — or the frozen "TRAINED" labels stay
misleading.
