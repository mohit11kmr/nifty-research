# MASTER PROJECT BLUEPRINT — NIFTY-RESEARCH

> Full project X-ray. READ-ONLY analysis; no application code was modified.
> Evidence is from current source, current databases, current runtime data.
> Every major conclusion is tagged **[FACT]** (direct evidence), **[INFERENCE]**
> (derived from evidence), or **[UNKNOWN]** (no evidence). Baseline:
> git `cf132ca`, tests 172/172 OK, ledger `data/ground_truth.db` (149 REAL
> signals, all STAY_OUT/SKIP, window 2026-08-13 12:45→~15:00 IST).

---

## 1. Executive Summary

NIFTY-RESEARCH is a **research + decision-support + paper-trading platform for
Indian options (NIFTY/BANKNIFTY) and MCX**, not a live-trading system. It
ingests NSE/Yahoo data into caches, computes regime/technical/OI/institutional
signals, gates everything through a 6-layer confluence + capital guard, records
every decision into an immutable ground-truth ledger, and evaluates results
against a frozen baseline. It currently produces **zero directional trades**
by design: the market is in `RANGE_LV` (low-vol chop, ADX 12.7) whose
documented rule is NO TRADE. The strongest parts are the truth/provenance
layer, the risk guard, and honest ML reporting. The weakest parts are: no
proven trading edge (0 outcomes), a self-improvement stack that is an honest
no-op, a diverged paper account, and many dead/dormant modules.

## 2. What the Project Really Is

**[FACT]** It is a **combination**: research platform + signal engine +
options analytics + risk management + paper trading + evaluation platform.
It is **NOT** a live trading system **[FACT]** — Angel One broker tools are
env-gated off (`BROKER_MCP_ENABLED`), and every execution path is paper-only
and additionally gated by the STAY_OUT signal.

- **What problem is it trying to solve?** Beat theta / retail option losses by
  only trading defined-risk setups that pass regime + confluence + capital
  guard; avoid low-vol chop entirely; and honestly measure whether any edge
  exists (so far: it cannot prove one).
- **Who uses it?** A single owner-operator (Mohit) via CLI, MCP tools
  (opencode `nifty-trader`), a scheduled Hermes cron (daily report → blog),
  and a `quant_daemon` background loop.
- **What happens when it runs?** Cached data is loaded/freshened → regime is
  classified → a 6-layer precision signal is computed and recorded to the
  ledger → a decision (SKIP/ENTER) is recorded → if ENTER, paper execution
  mirrors to the ledger → EOD reports + blog are generated. Today every run
  records SKIP.

## 3. Plain-English Explanation

```
INPUT          NSE option chain, NIFTY price history, India VIX, FII/DII,
               (all cached in data/)
   ↓
PROCESS        The system asks "is the market trending or chopping?"
               (ADX). "Is volatility high or low?" (Bollinger width).
               If it is chopping + low vol → STOP, no trade.
               Only in a trending/high-vol regime does it check 6
               conditions: regime, capital safety, technical indicators,
               options PCR, institutional flow, ML vote.
   ↓
DECISION       If fewer than 4 of 6 conditions agree AND regime not open
               → "STAY_OUT / SKIP" (safe, no money at risk).
               Only a full agreement → "ENTER" (paper).
   ↓
OUTPUT         Today: 149 recorded SKIPs, 0 trades, healthy ledger,
               daily report + blog. Nothing is being traded, by design.
```

**[FACT]** All 149 ledger signals are `STAY_OUT` with decision `SKIP`,
`capital_guard_state=APPROVED` (approving the absence of a trade).

## 4. System Architecture

```
┌─ DATA LAYER ─────────────────────────────────────────────────────────┐
│ nse_live.py (browser chain)  data_fetcher.py (NSE/Yahoo)             │
│ live_feed.py (NSE WS ticks)  live_ticker_service.py (5s stream)      │
│ live_market_fetch.py (spot)  institutional.py (FII/DII API)          │
│ tick_recorder.py → data/research.db  build_data.py → data/*.csv      │
└───────────────┬───────────────────────────────────────────────────────┘
                ▼
┌─ VALIDATION ─────────────────────────────────────────────────────────┐
│ truth.py (status vocab + freshness budgets, Phase 3/4A)              │
│ asset_freshness_report() → REAL/STALE/MISSING labels                 │
└───────────────┬───────────────────────────────────────────────────────┘
                ▼
┌─ FEATURE / STATE ────────────────────────────────────────────────────┐
│ indicators.py (ADX/PDI/MDI/BB/SMA/RSI/MACD/Supertrend)               │
│ regime_filter.py → 4-regime gate + India VIX zone (RANGE_LV=NO_TRADE)│
│ market_brain.py → technical consensus + verdict (bias/confidence)    │
└───────────────┬───────────────────────────────────────────────────────┘
                ▼
┌─ SIGNAL ─────────────────────────────────────────────────────────────┐
│ precision_signals.py → 6-layer confluence (regime, capital guard,    │
│   technical, options PCR/skew, institutional, super-AI ML)           │
│   grade: A+/A (directional) or NO_SIGNAL→STAY_OUT                    │
└───────────────┬───────────────────────────────────────────────────────┘
                ▼
┌─ RISK ───────────────────────────────────────────────────────────────┐
│ capital_guard.py (3% kill-switch, expiry trap, event risk, 1% sizer) │
│ var_risk_manager.py, delta_hedging_guard.py, dynamic_trailing.py     │
└───────────────┬───────────────────────────────────────────────────────┘
                ▼
┌─ EXECUTION (PAPER ONLY) ─────────────────────────────────────────────┐
│ auto_paper_runner.py / agent_workflow_graph.py → paper_trader.py     │
│   (execute/close) → mirrors to ground_truth ledger                   │
│   LIVE: Angel One via angel_one_client.py — DISABLED unless env flag │
└───────────────┬───────────────────────────────────────────────────────┘
                ▼
┌─ TRUTH LEDGER ───────────────────────────────────────────────────────┐
│ ground_truth.py: observation→snapshot→signal→prediction→decision→    │
│   execution→position→outcome (append-only, FK-guarded, provenance)   │
└───────────────┬───────────────────────────────────────────────────────┘
                ▼
┌─ EVALUATION (READ-ONLY) ─────────────────────────────────────────────┐
│ evaluation_engine.py: performance/confidence/regime/failure reports, │
│   chain health, live observation; phase6_pipeline.py frozen baseline │
└───────────────────────────────────────────────────────────────────────┘
Also: mcp_nifty.py (trading MCP server), daily_report.py → blog_post.py,
systematic_report.py, web_dashboard.py / live_dash.py (HTML terminals),
notifications_system.py (Telegram), quant_daemon.py (background loop).
```

## 5. Data Flow (each stage)

| Stage | Input | Process | Output | File/Function | Next |
|---|---|---|---|---|---|
| Market data | NSE/Yahoo/API | fetch→cache | `data/*.csv`, `research.db` | `build_data.py`, `nse_live.py`, `live_feed.py` | validation |
| Data validation | cached files | freshness check | REAL/STALE/MISSING | `truth.asset_freshness_report` | freshness |
| Freshness | mtimes | budget compare | status labels | `truth.file_freshness` | feature gen |
| Feature gen | daily OHLC | indicators | ADX/PDI/MDI/BB/SMA/RSI | `indicators.add_all_indicators` | market state |
| Market state | indicator row | 4-regime classify | RANGE_LV (today) | `regime_filter.detect_regime` | signal |
| Signal engines | state + chain + FII | 6-layer confluence | STAY_OUT (today) | `precision_signals.generate_precision_signal` | scoring |
| Scoring | 6 layer statuses | count passes | 2/6 (33%) | same | risk |
| Risk | capital guard audit | approve/block | APPROVED | `capital_guard` | decision |
| Decision | action + guard | map rule | SKIP | `ground_truth._derive_decision` | execution |
| Execution | ENTER decision | paper order | EXECUTED (none today) | `paper_trader` | position |
| Position | execution | open/close | OPEN (none in ledger) | `paper_trader` / `ground_truth.record_position` | outcome |
| Outcome | closed position | classify | WIN/LOSS (none) | `ground_truth.record_outcome` | evaluation |
| Evaluation | outcomes | reports | null (insufficient) | `evaluation_engine` | baseline |

**[FACT]** `predictions/executions/positions/outcomes/evaluations` are all 0 in
the ledger. Confidence is not emitted top-level; `market_state` column NULL
(persistence gap, Phase 6.6 finding).

## 6. Data Sources

| Data | Source | Freq | Freshness | Storage | Real/Sim | Used by |
|---|---|---|---|---|---|---|
| NIFTY daily OHLC | Yahoo | daily | budget 20h, REAL | `data/nifty_history.csv` | REAL | regime, signals, backtests |
| India VIX | Yahoo | daily | STALE today (21.6h) | `data/india_vix.csv` | REAL | regime, VIX zone |
| Option chain (OI/LTP/IV) | NSE browser | on-demand | last snap 2026-08-12 STALE | `data/oi_snapshots/*.csv` | REAL | oi_intel, strike, gamma |
| FII/DII cash+F&O | mrchartist API | daily | 6h budget, REAL | `data/fii_dii_history.csv` | REAL (89-97% null rows in ml features) | institutional, ML |
| ML features | derived | daily | REAL | `data/ml_features.csv` (496 rows × 24) | REAL | super_ai_ml, ml_engine |
| Ticks (per-strike) | NSE WS | live mkt hrs | research.db | `ticks` 1.95M rows | REAL | microstructure |
| Spot samples | Yahoo 1m | 60s | research.db | `spot` 751 rows | REAL | dashboard |
| Stocks (Nifty 50) | Yahoo | daily | `data/stocks/` | REAL | stock_flow, equity_quant |
| MCX | API | daily | cached | REAL | mcx_intel |
| Broker | Angel One | — | DISABLED (env flag) | — | — | broker_status tool |

**[FACT]** Missing/stale today: today's OI snapshot (uses 2026-08-12), India
VIX (21.6h old), institutional columns mostly null in `ml_features.csv`.

## 7. Module Map

94 modules. Classification summary (full evidence map in
`/tmp` analysis, 2026-08-13): **DEAD 11** (`agent.py`, `angel_one_mcp.py`,
`anti_spoofing.py`, `empirical_proof.py`, `mcp_pattern_bridge.py`,
`multi_agent_swarm.py`, `portfolio_rebalance.py`, `profit_engine.py`,
`telegram_notifier.py`, `trade_journal.py`, `trainer.py` — zero importers),
**DORMANT 15** (e.g. `live_trader_brain`, `lob_microstructure`, `monte_carlo`,
`smc_intelligence`, `pattern_recognition`, `volatility_forecaster`,
`connection_resilience`, `backup_data` — test/manual only), **NO-OP 2**
(`auto_enhancer`, `adaptive_weights`), **ACTIVE ~60** (entrypoint-reached),
plus report-only/gated/standalone (e.g. `live_dash`, `oi_refresh`,
`alert_monitor`, `angel_one_client`). Core active chain:
`run_all.py` (23-step orchestrator) → `precision_signals`,
`capital_guard`, `regime_filter`, `market_brain`, `oi_intel`,
`paper_trader`, `ground_truth`, `evaluation_engine`; `mcp_nifty.py`
exposes ~30 tools; `quant_daemon.py` runs paper + auto-enhancer loop;
`hermes_agent.py` schedules pre/intraday/post-market; `daily_report.py`
builds the report + blog.

**[FACT]** `audit/X04`/`X07` claim run_all does not call equity_quant/mcx_intel/
skew — stale; `run_all.py:243-261` calls them.

## 8. Actual Trading Strategy

**[FACT]** The one strategy is **regime-gated multi-factor confluence on
directional options buying**:

- Market condition: TREND_HV/TREND_LV (ADX≥25, |PDI−MDI|≥5) or RANGE_HV
  (mean-rev). RANGE_LV = hard NO TRADE.
- Setup: 6-layer confluence must hit ≥4/6 AND regime PASSED for a directional
  grade (A or A+).
- Filters: PCR/skew alignment, FII non-neutral, ML non-neutral, capital guard.
- Candidate: signal_action `HIGH_CONVICTION_*` / `MODERATE_*`.
- Entry: strike from OI walls (`recommended_call_strike`), delta 0.30-0.55
  via `smart_strike_selector` (data-driven since 2026-08-12).
- Sizing: 1% risk cap (`capital_guard`), lot 75.
- Stop: 1.5×ATR / 0.8% index SL (`sl_points`). Target: 1:2 (tgt_points).
- Exit: paper `close_paper_position` exists; **nothing auto-closes** **[FACT]**
  (10 positions from 2026-08-12 still OPEN).

A secondary **premium-selling defined-risk** strategy exists in
`premium_seller.py` (iron condor backtest, VIX 16-25 gated) — research/report
only, not wired to live decisions. **No strategy has ever produced a live
directional candidate.** **[FACT]**

## 9. Decision Engine

```
Market state (ADX 12.7, |PDI−MDI| 1.0) ─► RANGE_LV ─► gate NO_TRADE [FIRST/HARD GATE]
   ▼
6-layer confluence (score 2/6 today):
  L1 regime        BLOCKED (hard)   L2 capital guard APPROVED
  L3 technical     PASSED CALL 66%  L4 options MIXED (PCR 0.754 vs CALL)
  L5 institutional NEUTRAL          L6 ML NEUTRAL_SIDEWAYS
   ▼
Grade: requires ≥4/6 AND regime PASSED → NO_SIGNAL → STAY_OUT
   ▼
_derive_decision: STAY_OUT → SKIP (capital guard only REJECTs an ENTER)
```

- First gate: `regime_filter.detect_regime`. Hard gates: RANGE_LV NO_TRADE;
  VIX PANIC + conf<60; grade regime-PASSED requirement. Secondary: ≥4/6
  confluence. Thresholds: ADX 25, |PDI−MDI| 5, BB pctile 60, PCR 1.2/0.8,
  MIN_CONFIDENCE 55, confluence 4/6. **[FACT]**
- Rejection reasons recorded: `no evaluable signal (STAY_OUT/NO_SIGNAL)`
  (149/149). **[FACT]**

## 10. Options Engine

| Component | Nature | Evidence |
|---|---|---|
| OI walls / build-up | REAL (snapshot) | `oi_intel.oi_walls` |
| PCR / max pain | REAL calc | `oi_intel.pcr_and_pain` (max-pain bug fixed 2026-08-12) |
| IV / Greeks (Δ Γ Θ V ρ) | CALCULATED (BS) | `greeks.bs_price_and_greeks` |
| PoP / breakevens | CALCULATED | `greeks.probability_of_profit` |
| Strike selection | CALCULATED (BS delta 0.30-0.55 + real OI LTP) | `smart_strike_selector` |
| Spreads (iron condor etc) | CALCULATED from real LTP | `multi_leg_options` |
| IV skew | REAL/ESTIMATED | `skew.compute_iv_skew` |
| GEX/gamma flip | CALCULATED | `gamma_flip.calculate_gamma_exposure` |
| LOB microstructure | REAL (tick depth counts) | `lob_microstructure` (dormant) |

**[FACT]** Snapshot today is 2026-08-12 (stale); `stale_snapshot` flag exists.

## 11. Risk System

**[FACT]** `capital_guard.py`: 3% daily kill-switch (`check_daily_kill_switch`),
expiry trap, event risk, 1% position sizer, drawdown de-risking. Current
audit: `APPROVED`, kill-switch OPEN/False. Additional: `var_risk_manager`
(95%/99% VaR + stress), `delta_hedging_guard`, `dynamic_trailing`
(ATR trailing), `regime_filter` risk plan (stop=1.5×ATR). **Answer:** "What
prevents an unsafe trade?" — the regime gate (RANGE_LV=NO TRADE) plus the 1% /
3% / 7% / no-averaging / defined-risk rules plus capital guard block. **[FACT]**
Gap: risk rules are advisory in paper paths; no automated portfolio-level
exposure cap across strategies, and `connection_resilience` is DORMANT (not
wired into live paths).

## 12. Execution System

| Mode | Status | Evidence |
|---|---|---|
| LIVE | **DISABLED** | `broker_status` env-gated; `angel_one_client` behind `BROKER_MCP_ENABLED=1` |
| PAPER | Active, gated | `paper_trader.execute_paper_order`, mirrored to ledger (LEGACY provenance) |
| SIMULATED | LSTM etc. tagged SIMULATED | provenance vocab |
| BACKTEST | Active (research) | `backtester.py`, `multitf.py`, `premium_seller.py`, `long_term_backtest.py` |

**[FACT]** Paper account: 10 OPEN positions (9× BUY CE 24450 @ ₹140.0 stale
hardcode from 2026-08-12 pre-fix, 1× BUY PE 24500 @ ₹28.25), cash ₹3,381.25,
realized ₹0, closed 0, last updated 2026-08-12 15:55. **Diverged from the
ledger** (0 executions/positions there). No exit management, no MTM, no fees/
slippage model in paper.

## 13. Ground Truth System

`ground_truth.py` implements the canonical chain:
observation → feature_snapshot → signal → [prediction] → decision → execution
→ position → outcome → evaluation. Append-only (triggers block UPDATE/DELETE),
FK-guarded, provenance-enveloped (`truth.py` status vocab), deterministic
re-derivation from `checks_json`. **[FACT]** Current state: 149 observations /
149 snapshots / 149 signals / 149 decisions, all REAL provenance, all SKIP.
**Limitations:** prediction/execution/position/outcome tables never exercised
in production; `market_state`/`confidence` columns unfilled (top-level keys
not emitted by generator); paper account not reconciled to ledger.

## 14. Evaluation System

Can measure: cohort selection (REAL_FRESH eligibility), signal counts,
decision posture (SKIP rate), chain health (0 findings), leakage (clean),
reproducibility (byte-identical), provenance integrity. **[FACT]**
Cannot measure (insufficient data, all null): hit rate, win rate, prediction
accuracy, MFE/MAE, confidence calibration, regime/strategy performance,
P&L attribution, failure classification (0 losses). `evaluation_engine.py` +
`phase6_pipeline.py` enforce an insufficient-sample gate before any claim.

## 15. Current Live Behavior

**[FACT]** Signals 149, decisions 149 (SKIP 100%), directional candidates 0,
predictions 0, executions 0, positions 0, outcomes 0, evaluations 0.
Why: regime RANGE_LV (ADX 12.7, |PDI−MDI| 1.0, BB 46th pctile) → hard
NO_TRADE gate; even if open, confluence 2/6 < 4/6. Expected per documented
rule, not a bug. Market data REAL (nifty cache fresh); VIX and OI snapshot
stale (secondary).

## 16. ML/AI Reality

**[FACT] REAL ML (context-only):** `super_ai_ml.py` (XGB/LGBM/RF `.fit()`,
fixed 80/20 split, retrained every call, never persisted, no computed
baseline — honest caveat in docstrings). `ml_engine.py` walk-forward
meta-blender (chronological, baseline vs most-common-class, edge reported:
~51% vs ~52% → no edge). **[FACT] SIMULATION:** `lstm_neural_engine`
(linspace+mean, tagged SIMULATED), `monte_carlo` (parametric).
**[FACT] RULE-BASED/NO-OP/REPORT:** everything else (auto_enhancer NOOP,
adaptive_weights NOOP, reflection rule-based, multi_agent_swarm dead,
smc/pattern heuristics). **No model is ever saved to disk.** **[FACT]**

## 17. Self-Learning Reality

- Learn from outcomes? **NO** (0 outcomes exist).
- Modify parameters automatically? **NO** — `auto_enhancer` =
  `AUTO_ENHANCEMENT_NOOP`, `adaptive_weights` writes JSON but no outcome feed.
- Retrain models? **YES** (but meaningless — retrains every call, no
  persistence, ~coin-flip).
- Generate hypotheses? **YES** (rule-based; 9 identical never-applied
  hypotheses from 0 trades).
- Run experiments / compare to baseline? **PARTIAL** — baseline exists
  (frozen), no experiment engine.
- Promote/rollback improvements? **NO**.
- Improve itself automatically? **NO.** **[FACT]**

## 18. Strengths (top 10)

1. Truth & provenance layer (status vocab, freshness budgets). **[FACT]**
2. Capital guard + hard risk rules enforced in code. **[FACT]**
3. Immutable append-only ground-truth ledger with FK integrity. **[FACT]**
4. Honest ML posture (baseline/edge reported, no overclaiming). **[FACT]**
5. Chain-health + live-observation monitoring (Phase 6.5). **[FACT]**
6. Data-driven fake-data audit (2026-08-12) — real premiums/deltas/OI. **[FACT]**
7. Strong test discipline (172 tests passing). **[FACT]**
8. Read-only evaluation + frozen baseline discipline. **[FACT]**
9. Options analytics depth (Greeks, PoP, breakevens, GEX, skew). **[FACT]**
10. MCP tooling + scheduled automation (Hermes cron, quant daemon). **[FACT]**

## 19. Weaknesses (material)

- **CRITICAL:** No proven edge — 0 directional outcomes ever; strategy cannot
  be validated. **[FACT]**
- **CRITICAL:** Paper account (10 stale open positions, hardcoded ₹140 entries,
  no exits) diverged from ground-truth ledger. **[FACT]**
- **HIGH:** Self-improvement stack is decorative (no-op loops writing JSON).
  **[FACT]**
- **HIGH:** ML retrains every call, models never persisted/versioned. **[FACT]**
- **HIGH:** Institutional feature columns 88-97% null → ML "institutional"
  signal is degenerate. **[FACT]**
- **HIGH:** OI snapshot + VIX stale → options layer and premium pricing use
  yesterday's data. **[FACT]**
- **MEDIUM:** market_state/confidence not persisted to ledger columns
  (observability gap). **[FACT]**
- **MEDIUM:** 26 of 94 modules DEAD/DORMANT/NO-OP add maintenance noise. **[FACT]**
- **MEDIUM:** No fees/slippage/exit models; paper P&L not market-marked. **[FACT]**
- **LOW:** Audit docs X04/X07 stale vs current run_all. **[FACT]**

## 20. Actual Trading Edge

**UNPROVEN.** **[FACT]** Zero directional outcomes exist, so no win rate /
edge can be measured. ML is ~coin-flip (51% vs 52% baseline). The regime gate
and capital guard demonstrably prevent trading in a no-trade regime — a risk-
control "edge" (loss avoidance) that is defensible but not a profit edge.
Partially supported: backtest of iron condor selling (72.5% win, PF 2.6) in
`premium_seller.py` — historical simulation only, not validated live.

## 21. Claim vs Reality

| Claim | Actual | Evidence | Verdict |
|---|---|---|---|
| AI trading | Rule-based confluence + context ML | `precision_signals` | OVERSTATED |
| ML prediction | Coin-flip context only | ml_engine ~51% vs 52% | HONEST, no edge |
| Options intelligence | Real OI/Greeks/PoP/GEX | modules | SUPPORTED |
| Institutional-grade | Risk guard + provenance yes; execution no | capital_guard, truth | PARTIAL |
| Real-time trading | Paper only; live disabled | BROKER_MCP_ENABLED | PARTIAL |
| Risk management | Strong and enforced | capital_guard, regime | SUPPORTED |
| Self-learning | Honest no-op | auto_enhancer NOOP | NOT TRUE YET |
| Backtesting | Real, multi-TF | backtester, multitf, premium_seller | SUPPORTED |

## 22. Failure Modes

| Mode | Detection | Impact | Mitigation | Gap |
|---|---|---|---|---|
| DATA_FAILURE | truth freshness | stale/missing inputs | budgets + labels | intraday chain not refreshed |
| FEATURE_FAILURE | exceptions→NOT_COMPUTED | layer skipped | honest status | — |
| REGIME_FAILURE | detect_regime | over/under-gating | conservative RANGE_LV | no regime history tracking |
| SIGNAL_FAILURE | grade logic | STAY_OUT always | — | 0 candidates ever |
| MODEL_FAILURE | — | coin-flip context | documented no-edge | no drift/persistence |
| RISK_FAILURE | capital_guard | block | kill-switch | no portfolio exposure cap |
| EXECUTION_FAILURE | — | paper only | — | no exit automation |
| BROKER_FAILURE | env flag | n/a (disabled) | — | untested live path |
| NETWORK_FAILURE | — | n/a | connection_resilience DORMANT | not wired |
| DATABASE_FAILURE | append-only triggers | write blocked | guarded | paper/ledger divergence |
| EVALUATION_FAILURE | insufficient-sample gate | null claims | gate | no real data to evaluate |
| OPERATIONAL_FAILURE | daemon logs | — | PID daemon | stale paper positions |

## 23. Maturity Scores

| Area | Score | Evidence |
|---|---|---|
| Data Quality | 7/10 | provenance + budgets; stale VIX/chain, null FII columns |
| Architecture | 7/10 | clean layered design; 26 dead/dormant modules |
| Signal Engine | 5/10 | correct logic, 0 candidates ever produced |
| Options Intelligence | 8/10 | real Greeks/PoP/GEX/skew, data-driven |
| Risk | 8/10 | hard rules + guard; no portfolio exposure cap |
| Execution | 3/10 | paper-only, no exits/MTM, diverged account |
| Ground Truth | 8/10 | immutable, provenance, healthy; unused for trades |
| Evaluation | 7/10 | honest gates; nothing to evaluate yet |
| ML | 3/10 | honest but unpracticed (no persistence, no edge) |
| Self-Improvement | 1/10 | honest no-op |
| Testing | 8/10 | 172 tests green, chain health |
| Production Readiness | 4/10 | live trading disabled; paper hygiene gaps |

## 24. Target State (ideal, not built)

Truth → Observation → Signal → Decision → Execution → Outcome → Evaluation →
Failure Analysis → Experiment → Validation → Controlled Improvement. Required
capabilities: (a) every stage emits provenance; (b) candidate generation is
decoupled from gating so rejection reasons are measurable; (c) paper execution
with real premiums, exits, fees and reconciliation to the ledger; (d) ≥20
real outcomes before any edge claim; (e) experiment engine that changes ONE
variable, paper-only, gated by the frozen baseline; (f) ML only as context,
persisted and drift-checked; (g) self-improvement that is a closed loop only
after validated outcomes exist.

## 25. What Should Not Be Built

1. More ML models / neural nets (no data: 0 outcomes; existing ML is coin-flip).
2. Autonomous strategy/self-improvement activation (no validation basis).
3. Multi-agent swarms / LLM agents (decorative; dead modules already exist).
4. More duplicate signal/indicator engines (94 modules already).
5. Microservices / new infrastructure / new DBs (single-user, local scale).

## 26. Roadmap (prioritized)

| Phase | Goal | Why | Components | Risk | Validation | Exit criteria |
|---|---|---|---|---|---|---|
| 1 | Hygiene | restore integrity | close/clean stale paper positions; reconcile paper↔ledger | low | manual reconcile | paper account + ledger agree |
| 2 | Observability | see the gates | emit market_state/confidence; refresh intraday chain/VIX | low | chain-health green | columns populated, freshness REAL |
| 3 | Candidate evidence | prove generation path | paper-only RANGE_HV/TREND exercises in a controlled script (no threshold changes) | med | 20+ outcomes | measurable candidate counts + first outcomes |
| 4 | Strategy validation | know the edge | run strategy A/B vs frozen baseline | med | baseline delta | ≥20 outcomes, edge vs baseline reported |
| 5 | Execution reliability | paper realism | exits, MTM, fees/slippage, auto-close | med | paper P&L tracked | 0 orphan positions |
| 6 | Experiment engine | controlled change | one-variable, paper-only, rollback | med | paper outcomes | promote/rollback decision recorded |
| 7 | ML (context) | honest assist | persist models, walk-forward, drift check | low | edge vs baseline | ML reported as context only |
| 8 | Self-improvement | closed loop | only after validated outcomes | high | promotion gate | improvement only on measured edge |

## 27. Fact / Inference / Unknown

FACTs: ledger contents (149/149 SKIP), regime inputs (ADX 12.7 etc.), dead/
dormant classification, paper account state, ML no-edge evidence, no model
files, broker disabled, audit-doc staleness. INFERENCEs: paper positions were
pre-fix manual/path artifacts; "loss-avoidance is the current edge"; the
~1.95M ticks' usefulness. UNKNOWN: who exactly recorded each signal burst;
why the paper account was never reconciled; real broker behavior (never run).

## 28. Final Executive Summary

```
PROJECT NAME: NIFTY-RESEARCH
WHAT IT REALLY IS: A single-user Indian-options research + decision-support +
  paper-trading + evaluation platform (NSE/MCX); NOT a live trading system.
PRIMARY PURPOSE: Trade only defined-risk, high-confluence NIFTY setups, avoid
  low-vol chop, and honestly measure whether an edge exists.
INPUTS: NIFTY OHLC, India VIX, NSE option chain/OI, FII/DII, MCX, live ticks,
  ML features (all cached in data/).
CORE PROCESS: Regime gate → 6-layer confluence → capital guard → decision →
  immutable ground-truth ledger → read-only evaluation vs frozen baseline.
OUTPUTS: Precision signal (STAY_OUT today), decision record, paper trades,
  daily report + blog, MCP tools, dashboards, evaluation/failure reports.
ACTUAL TRADING STRATEGY: Regime-gated directional options (delta 0.30-0.55,
  defined risk, 1% risk, 1.5xATR stop, 1:2 target); secondary premium-selling
  backtest (iron condor). 0 candidates ever generated.
CURRENT DECISION LOGIC: RANGE_LV→NO_TRADE hard gate + ≥4/6 confluence +
  capital-guard; STAY_OUT→SKIP, ENTER→guard-REJECT path.
CURRENT LIVE BEHAVIOR: 149/149 SKIP, 0 predictions/executions/positions/
  outcomes; expected for RANGE_LV; ledger HEALTHY.
CURRENT ML STATUS: 2 real fits (super_ai_ml context-only ~coin-flip; ml_engine
  walk-forward honest no-edge), retrained per call, never persisted.
CURRENT LEARNING STATUS: NO learning (0 outcomes; auto-enhancer honest no-op).
CURRENT SELF-IMPROVEMENT STATUS: NO (decorative no-op loops; no promotion/
  rollback).
ACTUAL TRADING EDGE: UNPROVEN (0 outcomes; ML ~51% vs 52%; only backtested
  premium-selling support).
STRONGEST COMPONENT: Truth & provenance layer + ground-truth ledger + risk guard.
WEAKEST COMPONENT: Execution/paper hygiene (10 stale positions, no exits,
  diverged from ledger).
BIGGEST MISSING CAPABILITY: A validated directional candidate path with ≥20
  paper outcomes — without it nothing is measurable.
CURRENT MATURITY: 5.5/10
TARGET MATURITY: 8/10 (after hygiene, observability, outcome accumulation,
  experiment engine).
TOP 10 THINGS TO IMPROVE:
1. Reconcile/close stale paper account; enforce paper↔ledger parity.
2. Persist market_state + confidence in signals.
3. Refresh intraday OI snapshot + VIX freshness.
4. Accumulate ≥20 real paper outcomes (paper-only regime exercises).
5. Auto-exit / MTM / fees-slippage in paper trading.
6. Wire portfolio-level exposure cap (beyond 1%/3%/7%).
7. Persist + version ML models; stop retrain-per-call.
8. Fix institutional feature gaps in ml_features.csv.
9. Reconcile stale audit docs (X04/X07); archive DEAD modules.
10. Add rejection-reason accounting to the ledger (count per gate).
TOP 5 THINGS NOT TO BUILD:
1. More ML models / neural nets.
2. Autonomous self-improvement activation.
3. Agent swarms / LLM agents.
4. More duplicate signal engines.
5. Microservices / new infra / new DBs.
FIRST 3 RECOMMENDED NEXT STEPS:
1. Paper/ledger reconciliation + stale-position cleanup (integrity).
2. Observability wiring (market_state/confidence + intraday freshness).
3. Paper-only, evidence-driven regime exercises to generate the first real
   outcomes (controlled; no threshold changes).
```

---

*Compiled 2026-08-13. Read-only; no application code modified. Sources:
94-module import evidence map, ML module audit, ledger/data DB queries,
current source reads, Phase 2-6.6 audit reports.*
