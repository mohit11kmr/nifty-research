# EXTERNAL ARCHITECTURE BENCHMARK

> Benchmark of NIFTY-RESEARCH vs NautilusTrader, LumiBot, Optopsy, QSTrader.
> **Architecture benchmark and adoption-planning phase only. READ-ONLY.**
> No application code, strategy, thresholds, risk rules, databases, or paper
> account were modified. No dependencies added. No commit.
> Sources: current NIFTY-RESEARCH source/ledger (2026-08-13) + public
> repositories/documentation of the four reference projects (fetched 2026-08-13).
> Every conclusion is tagged **[FACT]** (direct evidence), **[INFERENCE]**
> (derived), or **[UNKNOWN]** (no evidence).

---

# 0. Context

NIFTY-RESEARCH state (from `audit/MASTER-PROJECT-BLUEPRINT.md`):
- 149 signals, 149 decisions, all SKIP (regime `RANGE_LV` = NO TRADE gate).
- 0 predictions / executions / positions / outcomes / evaluations.
- Paper account (10 stale OPEN positions, ₹3,381.25 cash) diverged from the
  immutable ground-truth ledger (0 executions there).
- No order lifecycle, no exits, no MTM, no fees/slippage in paper.
- Truth/provenance layer, capital guard, and ledger are the strongest parts.
- 26 of 94 modules DEAD/DORMANT/NO-OP.

The goal of this benchmark: **find what is genuinely better in the four mature
projects, decide what NIFTY-RESEARCH should adopt / reject and why, and state
the smallest architecture that fixes the paper/execution divergence without
losing the NIFTY-specific identity.**

---

# 1. Reference Projects (evidence summary)

## A. NautilusTrader (nautechsystems/nautilus_trader)
**[FACT]** Rust-native core + Python control plane (PyO3; no Rust toolchain
needed for wheels). v1.224.0 (PyPI) / v2 (Rust-native runtime).
- **License: LGPL-3.0-or-later** (LICENSE, repo metadata, PyPI classifier) —
  NOT Apache-2.0. Link/import OK; copying/modifying source into our project
  triggers LGPL obligations. Contributions require CLA.
- Single `NautilusKernel` shared by **Backtest / Sandbox / Live** contexts.
- Event-driven: `MessageBus` (Pub/Sub), `Cache` (in-memory state:
  instruments/accounts/orders/positions), `DataEngine`, `ExecutionEngine`,
  `RiskEngine`, `Portfolio`.
- Events: `OrderAccepted`, `OrderFilled`, `OrderCanceled` (execution);
  `PositionOpened/Changed/Closed` (from fills); `AccountState`; `TimeEvent`.
- Order FSM: INITIALIZED, DENIED, EMULATED, RELEASED, SUBMITTED, ACCEPTED,
  REJECTED, CANCELED, EXPIRED, TRIGGERED, PENDING_UPDATE/PENDING_CANCEL,
  PARTIALLY_FILLED, FILLED, VOIDED. Contingencies OCO/OUO/OTO.
- Fills carry last_qty/last_px/trade_id/commission; `OrderFillVoided` corrects.
- Fees: MakerTakerFeeModel (maker/taker, rebates), FixedFeeModel,
  PerContractFeeModel, TieredNotionalOptionFeeModel, CappedOptionFeeModel.
- Slippage: backtest fill models (prob_slippage one tick against direction,
  random_seed for reproducibility).
- Accounting: Portfolio realized/unrealized/total PnL, net_exposure,
  mark_values, equity (cash: balances + mark value; margin: + unrealized),
  balance invariant `total == locked + free`, margin scopes.
- **Options first-class**: OptionContract, OptionSpread (≤4 legs), BS greeks,
  imply_vol, OptionGreeks as persistent/replayable Data. **No NSE adapter.**
- RiskEngine: pre-trade checks, max_notional_per_order, order submit/modify
  rate limits, OrderDenied on failure — present in backtest AND live.
- Determinism: single-threaded kernel → deterministic event ordering;
  formal DST contract (seed, binary hash, config hash → bitwise-identical);
  ParquetDataCatalog + BacktestNode.
- Monitoring: `metrics_snapshot()` (event rate, staleness, queue depth);
  immutable messages for replay/audit; no built-in dashboards.
- Overkill: Rust toolchain, multi-venue adapters, madsim/DST machinery,
  Redis persistence, multi-currency breadth. OSS scope explicitly
  "single-node backtesting and live trading for individual and small-team
  quantitative traders" — same class of user as us.

## B. LumiBot (Lumiwealth/lumibot)
**[FACT]** Python, single `Strategy` class with React-style lifecycle
(`initialize()` + `on_trading_iteration()`, order callbacks).
- **License: GNU GPL-3.0** (LICENSE file) despite MIT badge in README/PyPI —
  treat as GPL-3.0. Private research low-risk; distribution matters.
- **Same strategy class runs backtest, paper, live** — runner/config change
  only (env vars IS_BACKTESTING, BACKTESTING_DATA_SOURCE; broker paper
  endpoints like Alpaca PAPER=True; no local Paper broker class).
- DataSource abstraction with **disk caching** (parquet/feather per source,
  optional S3 mirror); ~130 pandas-ta indicators **computed once over the
  full series, memoized O(1)/O(log N), sliced to bar t (no lookahead)**,
  identical API in backtest and live.
- Execution: create_order supports market/limit/stop/stop-limit/trailing and
  bracket/OCO/OTO/MULTILEG; TradingFee (flat/percent/per-contract);
  TradingSlippage (SMART_LIMIT fills mid±slippage); BacktestingBroker
  simulates positions/orders/cash, margins, option MTM, cash settlement.
- Options: AssetType.OPTION, get_chains/get_greeks, OptionsHelper (expiry
  selection, delta→strike, portfolio greeks, multileg pricing), MULTILEG
  orders (iron condor example). **US-centric only — no NSE.**
- AI: LLM-in-the-loop agent runtime (not relevant to our needs).
- Weaknesses: heavy generic abstraction (multi-broker/crypto/Polymarket),
  US-only options data/brokers, large install surface.

## C. Optopsy (goldspanlabs/optopsy, formerly mikekulakov/optopsy)
**[FACT]** Python options backtesting engine, v2.3.0 (2026-03), active
(1,442 stars, last push 2026-06-30). Docs: goldspanlabs.github.io/optopsy.
- **License: AGPL-3.0-or-later** (switched from GPL-3.0 Feb 2026).
  Patterns/ideas free; copying code into a distributed/hosted product triggers
  AGPL source-release obligations.
- **Data model**: flat pandas DataFrame; required columns
  `underlying_symbol, option_type, expiration, quote_date, strike, bid, ask,
  delta`; optional greeks/IV/OI. Multi-expiry = rows sharing `expiration`.
- **Strategy definitions**: 38 pre-built functions (`long_calls`,
  `long_straddles`, `iron_condor`, calendars, diagonals, collars...) with
  **per-leg delta targeting** `TargetRange(target, min, max)`.
- Entry/exit: `max_entry_dte` (default 90), `exit_dte` (0=hold to expiry),
  `dte_interval`, `min_bid_ask`, `stop_loss`, `take_profit`, `max_hold_days`.
- Simulation: `simulate()` chronological replay with `capital`, `quantity`,
  `max_positions`, `selector` → trade_log, equity_curve, summary. Entries/
  exits matched to bid/ask quote rows by contract+date; **no exercise/
  settlement engine, no internal Greeks** (delta read from data).
- Execution realism: commissions (per-contract + base + min) and slippage in
  4 modes (`mid`, `spread`, `liquidity`, `per_leg`); long fills near ask /
  short near bid. **No partial fills, no MTM.**
- Performance: grouped statistics by DTE × delta interval (count/mean/std/
  percentiles of % return); `compute_risk_metrics()` adds Sharpe, Sortino,
  VaR, CVaR, Calmar, Omega, tail ratio.
- Best ideas for us: per-leg delta TargetRange; DTE-bucket entry/exit;
  flat chain table keyed by `expiration`; slippage/commission knobs;
  bucket-wise grouped statistics.
- Limitations: no live/broker, no margin/assignment sim, delta must come
  from data, CSV-dependent.

## D. QSTrader (mhallsmoore/qstrader)
**[FACT]** "Modular schedule-driven backtesting framework for long-short
equities/ETF" (QuantStart). 3,433 stars; last push 2024-06-30 (v0.3.0) —
low activity, not archived.
- **License: MIT** (2015-2024 QuantStart/QuarkGluon). Copy/modify freely.
- Architecture: `BacktestTradingSession.run()` → `DailyBusinessDaySimulationEngine`
  yields SimulationEvents (pre_market, market_open, market_close, post_market);
  QuantTradingSystem runs AlphaModel → PortfolioConstructionModel → ExecutionHandler
  → broker. Modular seams: alpha → construction → risk → execution → broker.
- Accounting: Portfolio (cash + PositionHandler, total_market_value,
  total_equity, unrealised/realised P&L); Position (avg_bought/avg_sold,
  commissions, realised = (sell−avg)·qty, unrealised = (price−avg)·qty).
  Fills priced buy@ask/sell@bid + fee model; Transaction objects.
- Reproducibility: deterministic by construction (fixed business-day
  timestamps, no PRNG in sim path); pinned dependency versions; PortfolioEvent
  history auditable.
- Evaluation: CAGR, Sharpe (zero risk-free), Sortino, max drawdown + duration,
  weekly/monthly/yearly aggregation; TearsheetStatistics (cumulative returns
  vs benchmark, underwater curve, monthly heatmap); JSONStatistics export.
- Execution realism: **market orders only**, same-day close fills, Zero/
  Percent fee models; **slippage unimplemented** (TODO); no partial fills.
- Options: **NO** (Equity/Cash assets only). No live trading.
- Best ideas for us: Portfolio/Position accounting discipline with avg-price
  + commissions; deterministic auditable schedule loop; modular seam
  (alpha→construction→risk→execution→broker) as interfaces; MIT tearsheet +
  JSON metrics export.

---

# 2. Comparison Matrix

| Capability | NIFTY-RESEARCH | NautilusTrader | LumiBot | Optopsy | QSTrader |
|---|---|---|---|---|---|
| Data architecture | Cached CSV + SQLite (research.db) + provenance budgets | ParquetDataCatalog, typed Data objects, persistence subpackage | DataSource abstraction + disk cache (parquet/feather) | Flat pandas chain DataFrame (expiration-keyed) | CSVDailyBarDataSource → DataFrames |
| Event architecture | Monolithic chain (`generate_precision_signal`); sequential node graph in `agent_workflow_graph` | Full event-driven: MessageBus, Cache-as-state, event-sourced immutable messages | Strategy lifecycle loop (initialize + on_trading_iteration) | Strategy function → simulate() replay loop | Schedule-driven SimulationEvents (pre/market_open/close/post) |
| Strategy abstraction | 6-layer confluence baked into one function; grade logic inline | Strategy class, decoupled from engines (ports-adapters) | Single Strategy class, portable across modes | 38 pre-built strategy functions + delta targeting | AlphaModel → PortfolioConstructionModel seam |
| Paper trading | `paper_trader.py` JSON singleton; no lifecycle/MTM/fees | Sandbox context = same engine, simulated venues | Broker paper endpoints (Alpaca PAPER) + BacktestingBroker | No (research only) | No (backtest only) |
| Live trading | DISABLED (env-gated broker client) | Live context, multi-venue adapters (no NSE) | Live brokers (no NSE options) | No | No |
| Backtesting | `backtester.py`/`multitf.py`/`premium_seller.py` (BS premium, slippage 1.5%, ₹40 cost) | Same engine as live, deterministic | BacktestingBroker + data source | simulate() chronological replay | Schedule-driven daily-bar |
| Replay | None (live ticks→research.db only) | Catalog replay, deterministic DST | Historical data source replay | simulate() | Historical bar replay |
| Execution lifecycle | execute_paper_order/close_paper_position; NO order FSM, NO partial fills/cancels | Full order FSM + contingencies + fill events + reconciliation | Market/limit/stop/trailing + bracket/OCO/OTO/MULTILEG | No lifecycle (matches quote rows) | Market orders only, same-day close |
| Portfolio accounting | paper_account.json (cash, open positions, realized); no MTM, no fees | Full: equity=balances+mark, realized/unrealized, margin, currency-safe | get_portfolio_value/cash/positions; backtest margins + option MTM | equity_curve per closed trade; no MTM | Portfolio/Position avg-price accounting, fees, realised vs unrealised |
| Options | First-class NIFTY: OI walls, PCR, max pain, Greeks (BS), PoP, GEX, skew, smart strikes | First-class generic: OptionContract/Spread, BS greeks, imply_vol, OptionGreeks replay (no NSE) | Options API US-only (ThetaData/Alpaca/IB) | Research-only: delta-target legs, DTE buckets, expiry rows | NONE |
| Risk | capital_guard (3% kill-switch, expiry trap, event risk, 1% sizer), VaR, delta guard, trailing | RiskEngine pre-trade, max_notional, rate limits (backtest AND live) | BacktestingBroker margins; no strategy-level risk engine | No (risk in metrics only) | RiskModel hook (minimal) |
| Ground Truth | Immutable append-only provenance ledger (best-in-class for research) | Event-sourced immutable messages + Cache state; venue reconciliation | None comparable | None | PortfolioEvent history (auditable) |
| Evaluation | evaluation_engine, frozen baseline, insufficient-sample gate, chain-health | `analysis` component performance stats | Some stats | DTE×delta grouped stats + risk metrics (Sharpe/Sortino/VaR/CVaR/Calmar/Omega) | CAGR/Sharpe/Sortino/maxDD/tearsheet/JSON |
| Reproducibility | byte-identical re-run, frozen baseline, no shuffling | Bitwise DST contract, seeded fills, catalog | Indicator memoization (no lookahead) | Deterministic simulation | Deterministic by construction, pinned deps |
| Testing | 172 tests, chain-health detectors | TestKit + DST + spec testing ladder | Basic | Not strong | Integration tests, version-pinned equality |
| Monitoring | chain-health report, live_observation, 6 read-only MCP tools | metrics_snapshot, message-bus hierarchy, immutable audit trail | Logging | None | Tearsheet/JSON reports |

---

# 3. What They Do Better (verified strongest capabilities)

```
NautilusTrader → event/state integrity + order FSM + deterministic replay +
                 backtest/live parity + strict accounting (one engine, three contexts)
LumiBot        → strategy portability (same class, backtest/paper/live) +
                 disk-cached data + memoized no-lookahead indicators
Optopsy        → options strategy research: delta-target legs, DTE buckets,
                 expiry-keyed chain table, slippage/commission knobs, grouped stats
QSTrader       → research/evaluation discipline: portfolio accounting with
                 avg-price + commissions, tearsheet + JSON metrics, deterministic loop
```

**Pattern-by-pattern analysis:**

### Pattern 1 — One engine, three contexts (backtest/paper/live)
- **Project:** NautilusTrader (Backtest/Sandbox/Live share `NautilusKernel`); LumiBot (same `Strategy` class, runner/config switches mode).
- **How it works:** strategy and engines are mode-agnostic; only data source, clock, and execution backend differ.
- **Why better:** no logic duplication; a strategy validated in backtest is the same code that trades paper then live.
- **Current equivalent:** `agent_workflow_graph` node chain + `paper_trader` + `backtester` are SEPARATE code paths with different cost models (paper has none).
- **Gap:** paper vs backtest vs live use different execution/accounting; parity only via ledger, not shared engine.
- **Complexity:** medium (shared execution/accounting core).
- **Risk:** low-medium (must not break existing ledger append-only integrity).

### Pattern 2 — Explicit order/position lifecycle FSM
- **Project:** NautilusTrader (order states + `OrderFilled` + `PositionOpened/Closed`); LumiBot (order classes + callbacks).
- **How it works:** every state transition is an event; fills carry qty/px/commission; positions derive causally from fills.
- **Why better:** partial fills, cancels, corrections, reconciliation are first-class; accounting is derived, never hand-set.
- **Current equivalent:** `execute_paper_order` / `close_paper_position` — atomic happy-path, no intermediate states, no fill detail, nothing auto-closes.
- **Gap:** no lifecycle → stale OPEN positions, no exits, no MTM, divergence from ledger.
- **Complexity:** low-medium (paper order FSM with 4-6 states, plus scheduled exit/MTM).
- **Risk:** low (additive to paper layer; ledger unchanged).

### Pattern 3 — Realistic paper costs and MTM (fees, slippage, marking)
- **Project:** NautilusTrader (fee models incl. options-specific, slippage fill models); LumiBot (TradingFee/TradingSlippage, backtest option MTM); Optopsy (commission + 4 slippage modes).
- **How it works:** fills price at bid/ask ± slippage; commissions per contract; open positions marked to last quote; P&L = realized + unrealized.
- **Why better:** paper P&L approximates live P&L; NEUTRAL-band outcome logic (`|pnl| < costs`) only works if costs are modeled.
- **Current equivalent:** backtester has slippage 1.5% + ₹40 cost; **paper has none** (blueprint MEDIUM finding).
- **Gap:** paper P&L not market-marked; outcomes impossible to classify honestly.
- **Complexity:** low.
- **Risk:** low.

### Pattern 4 — No-lookahead memoized indicators + cached data
- **Project:** LumiBot (pandas-ta ~130 indicators, full-series compute once, slice to bar t, memoized; disk cache).
- **How it works:** indicators computed over full history once, then each bar reads prefix; identical API in all modes.
- **Why better:** fast research loops, no accidental lookahead, parity between research and live.
- **Current equivalent:** `indicators.py` recomputes per call; `market_brain` consensus uses cached CSVs; `ml_features.csv` was 5 days stale (X08).
- **Gap:** no explicit no-lookahead guarantee; stale feature files silently consumed.
- **Complexity:** low.
- **Risk:** low.

### Pattern 5 — Deterministic replay + experiment snapshot
- **Project:** NautilusTrader (DST contract, catalog replay, seeded fills); QSTrader (deterministic loop, pinned deps); Optopsy (`simulate()` replay).
- **How it works:** same inputs + same config → identical run; replay historical data through the same engine.
- **Why better:** reproducibility is a prerequisite for any A/B; frozen baseline can be re-verified.
- **Current equivalent:** frozen baseline + byte-identical re-run exists; no replay harness through paper/execution path.
- **Gap:** can't replay a market day through the paper path to debug fills/exits.
- **Complexity:** medium.
- **Risk:** low.

### Pattern 6 — Portfolio accounting as a first-class component
- **Project:** QSTrader (Position avg-price, commissions, realized vs unrealized); NautilusTrader (equity = balances + mark value; total = locked + free).
- **How it works:** cash + positions are the single source of truth; every fill mutates both through Transactions; P&L derived.
- **Why better:** reconciliation possible; accounting identical across modes.
- **Current equivalent:** `paper_account.json` (cash_balance, open_positions, realized_pnl) is ad-hoc and NOT reconciled to the ledger.
- **Gap:** paper account and ledger diverged (10 stale positions vs 0 ledger executions).
- **Complexity:** medium (single Accounting module shared by paper/backtest).
- **Risk:** medium (must preserve ledger immutability; this fixes the divergence).

### Pattern 7 — Options-specific research primitives (delta targeting, DTE buckets, expiry-keyed chain)
- **Project:** Optopsy (TargetRange per-leg delta; max_entry_dte/exit_dte/dte_interval; flat expiration-keyed rows).
- **How it works:** strategies select legs by delta bands and expiries by DTE windows; statistics grouped by DTE × delta.
- **Why better:** directly encodes how Indian weekly options traders think (DTE to expiry, delta for strike); replaces hardcoded %-OTM rules.
- **Current equivalent:** `smart_strike_selector` (delta 0.30-0.55, OI floor, premium cap) — partially there; DTE-bucket research absent; premium_seller hardcodes expiry handling.
- **Gap:** DTE-windowed research + delta-band statistics + expiration-keyed research table.
- **Complexity:** low-medium.
- **Risk:** low.

### Pattern 8 — Evaluation tearsheet + risk-adjusted metrics + JSON export
- **Project:** QSTrader (CAGR/Sharpe/Sortino/maxDD/tearsheet/JSON); Optopsy (Sharpe/Sortino/VaR/CVaR/Calmar/Omega); NautilusTrader (analysis component).
- **How it works:** metrics computed only when sample adequate; exported for audit.
- **Why better:** standard risk-adjusted language; comparable across strategies.
- **Current equivalent:** evaluation_engine reports with insufficient-sample gate; richer option metrics (MFE/MAE, R-multiple, NEUTRAL band) already designed in PHASE2-OUTCOME-ENGINE but never exercised (0 outcomes).
- **Gap:** tearsheet output + JSON export; standard risk metrics once outcomes exist.
- **Complexity:** low.
- **Risk:** low.

---

# 4. What NOT to Replace (protect our architecture)

**[FACT]** These must stay — they are genuinely better than the reference projects' equivalents for our purpose:

| Component | Why protect |
|---|---|
| `truth.py` provenance layer | Reference projects have NO provenance/freshness vocabulary. Statuses (REAL+FRESH/STALE/MISSING/FALLBACK/SIMULATED/INVALID/LEGACY/UNKNOWN) + envelope are ahead of all four. |
| `ground_truth.py` immutable ledger | Append-only, FK-guarded, provenance-enveloped. Nautilus event-sourcing is the closest analogue, but ours is simpler and already proven (149 REAL records, chain HEALTHY). |
| `capital_guard.py` NIFTY risk philosophy | 3% kill-switch, expiry trap, event risk, 1% sizer, no-averaging. Nautilus RiskEngine is generic (rate limits, notional) and would NOT express NIFTY/SEBI rules. Keep ours; optionally add Nautilus-style pre-trade "denial code" reporting. |
| NIFTY-specific confluence (6-layer) + OI intelligence + options analytics | OI walls, Murarkar matrix, PCR/max pain, GEX, skew, smart_strike_selector are our specialization — none of the four projects have NSE OI intelligence. |
| Existing evaluation layer + frozen baseline + insufficient-sample gate | QSTrader's tearsheet is additive, not a replacement. Our honesty gate (no claims without sample) is stronger. |
| MCP interface (`mcp_nifty.py`) | None of the four expose a trading MCP server; this is our integration advantage. |
| Current risk philosophy | RANGE_LV = NO TRADE, defined-risk only, loss control is the edge. Do not let a framework's generic risk layer override this. |

---

# 5. What NOT to Adopt (explicitly rejected)

| Candidate | Why reject |
|---|---|
| NautilusTrader as a dependency/framework | LGPL-3.0 (copy/modify obligations), no NSE adapter (option chain via Playwright needed), Rust wheel + catalog + DST machinery is overkill for single-user NIFTY. Use as pattern reference only. |
| LumiBot as a dependency | GPL-3.0 (ambiguous with MIT badge), US-only options/brokers, large generic surface. Pattern reference only. |
| Optopsy as a dependency | AGPL-3.0 (network source-release obligations if we host), no internal Greeks, delta required from data, no exercise/settlement — insufficient for NSE weekly settlement. Adopt ideas (delta targeting, DTE buckets) as our own implementation. |
| QSTrader as a dependency | MIT (safe to borrow), but no options and effectively unmaintained. Borrow accounting/metrics ideas directly (MIT permits copying with notice). |
| Full event-driven MessageBus architecture (Nautilus) | Our scale does not need Pub/Sub, kernels, and adapter ecosystems. A lightweight order/position FSM + state events is enough. The ledger already gives us the immutable audit trail. |
| LLM/agentic trading runtimes (LumiBot AI agents) | No evidence basis (0 outcomes); decorative. Already have dead `multi_agent_swarm` we should not resurrect. |
| Extra ML (all four projects' ML surface) | No data; ML is honest context-only today. Benchmark confirms no edge exists to justify it. |
| Microservices / Redis persistence / multi-currency / multi-venue breadth | Single-user, local, single-market. Adds complexity with zero value here. |
| Generic portfolio infrastructure that duplicates our ledger | QSTrader/Nautilus portfolio objects would duplicate ground_truth tables (positions/outcomes). We need a thin accounting layer, not a second portfolio system. |

---

# 6. Event-Driven Architecture Benchmark (Plan §9)

**Question:** should NIFTY-RESEARCH adopt `MarketEvent / SignalEvent / OrderEvent / FillEvent / PositionEvent / OutcomeEvent`?

**Verdict: PARTIALLY ADOPT (lightweight event/state model, no framework).**

- **Benefit:** the single biggest failure (paper account diverged from ledger, stale positions, no exits) is a lifecycle problem. An order/position FSM with explicit state transitions fixes it with 4-6 states, not a message bus.
- **Complexity:** low if implemented as plain dataclasses + a state table in the existing ledger (no event bus, no queue). The existing `ground_truth` tables already ARE the append-only event log; we only need the intermediate FSM states and derivation rules.
- **Compatibility with Ground Truth:** high — the FSM would write into `executions`/`positions`/`outcomes` tables that already exist but are empty (149 signals, 0 executions). No schema change required (per Phase plan, schema is frozen).
- **Migration risk:** low — additive; live decision path (STAY_OUT) unchanged.
- **Adopt in full (Nautilus MessageBus)?** No — REJECT. No async infrastructure needed at our scale.

---

# 7. Paper / Execution Benchmark (Plan §8 — highest priority)

Known weakness confirmed by evidence: paper account diverged from ledger
(10 stale OPEN positions vs 0 ledger executions); no order lifecycle, no
exits, no MTM, no fees/slippage.

What the reference projects do (verified):
- **Order lifecycle:** Nautilus order FSM (states + fill events + cancellation +
  reconciliation); LumiBot order classes + callbacks.
- **Position lifecycle:** positions derived causally from fills
  (PositionOpened/Changed/Closed).
- **Fills:** carry qty/px/commission; partial fills supported.
- **Cash:** single balance invariant (`total = locked + free`).
- **Commissions:** per-contract / percent / fixed models.
- **Slippage:** fill models (mid±, one tick adverse, volume-based).
- **Mark-to-market:** open positions marked to last quote; equity curve per bar.
- **Partial fills / cancellations:** Nautilus full; LumiBot partial in backtest.
- **Reconciliation:** Nautilus venue reconciliation; LumiBot broker sync.
- **Replays:** catalog replay.

**Smallest architecture that fixes our problem (recommendation, NOT implemented):**

```
LEG-1 (P0)  Paper order FSM (6 states): SUBMITTED → ACCEPTED → PARTIALLY_FILLED
            → FILLED | CANCELED | REJECTED. Fills write qty/px/commission.
            Fixes: no lifecycle, no fills detail.
LEG-2 (P1)  Ledger reconciliation: every paper execution/close ALSO writes the
            ground_truth execution/position rows it already has (today 0 are
            written). Fixes: divergence.
LEG-3 (P1)  Cost + MTM: per-contract commission + slippage on fill (reuse
            backtester's 1.5% slippage / ₹40 cost model), open positions marked
            to last quote in research.db `ticks`/spot. Fixes: no MTM, no costs.
LEG-4 (P2)  Scheduled auto-exit (expiry 15:05 square-off + stop/target) →
            closes the 10 stale positions + future orphans. Fixes: no exits.
LEG-5 (P2)  Replay harness: replay a stored market day (research.db ticks/spot)
            through the paper path for deterministic debugging (Nautilus/QSTrader
            replay idea, minimal scope).
```

Complexity: low-medium. Risk: low (additive; ledger schema unchanged;
STAY_OUT decision path untouched).

---

# 8. Backtest / Paper / Live Parity (Plan §10)

**Goal:** same strategy, same signal logic, same execution model, same
accounting across BACKTEST / PAPER / LIVE without duplicating logic.

**[FACT]** Today: `backtester.py` (BS premium, slippage 1.5%, ₹40 cost),
`paper_trader.py` (no costs), and the env-gated broker client are three
separate execution/accounting paths.

**Recommendation (PARTIAL ADOPT, staged):**
1. Extract a single **execution/accounting core** (order FSM + fills + costs +
   MTM + P&L) used by paper now and backtest next (LumiBot/Nautilus "one
   engine" idea, implemented at our scale).
2. Signal logic stays in `precision_signals` (already shared — it IS the
   strategy). Only execution/accounting needs unifying.
3. LIVE stays disabled; parity means the broker client eventually delegates to
   the same order FSM and mirrors into the same ledger.
4. Do NOT adopt a framework to achieve this — a ~400-line module plus the
   existing ledger tables covers it.

---

# 9. Options Research Benchmark (Plan §11)

Verified improvements worth adopting (from Optopsy; implement ourselves):

| Improvement | Ref | Current NIFTY-RESEARCH | Gap | Value |
|---|---|---|---|---|
| Per-leg delta targeting with target/min/max bands | Optopsy TargetRange | `smart_strike_selector` uses delta 0.30-0.55 single band | explicit target band + multi-leg leg-by-leg targeting | High (replaces %-OTM heuristics) |
| DTE-windowed entry/exit research (max_entry_dte, exit_dte, dte_interval) | Optopsy | premium_seller/backtester hardcode expiry handling | systematic DTE bucketing for research | High (Indian weekly/monthly) |
| Expiration-keyed flat chain research table | Optopsy | `data/oi_snapshots/*.csv` per-day files | unified research table keyed by expiration | Medium |
| Slippage/commission knobs in simulation | Optopsy/Nautilus/LumiBot | backtester has fixed 1.5%/₹40; paper none | parameterized cost model | High |
| Grouped statistics by DTE × delta interval | Optopsy | evaluation_engine reports totals | bucket-wise research reporting | Medium |
| Standard risk metrics (Sharpe/Sortino/VaR/CVaR/Calmar/Omega) | Optopsy/QSTrader | exists for equities, not options | add to outcome metrics | Medium (only once outcomes exist) |

Do NOT adopt wholesale: Optopsy's data-format requirements, its lack of
internal Greeks (ours are better — BS greeks, PoP, breakevens), and AGPL code.

---

# 10. Research / Evaluation Benchmark (Plan §12)

Verified improvements (from QSTrader + Optopsy, aligned with our existing design):

- **Tearsheet + JSON export** (QSTrader MIT — can copy with notice): cumulative
  returns vs benchmark, underwater curve, monthly heatmap; JSON metrics export
  for the ledger. **Low complexity, do once outcomes exist.**
- **Risk-adjusted metrics** (Sharpe/Sortino/maxDD/Calmar) — add to the already
  designed outcome metrics (MFE/MAE, R-multiple, NEUTRAL band). Gate on
  adequate sample (we already have the insufficient-sample gate).
- **Walk-forward** — we already have honest walk-forward in `ml_engine`
  (no edge). Do not add metrics without data (0 outcomes).
- **Experiment snapshots / benchmark datasets** — our frozen baseline +
  byte-identical re-run already exceeds QSTrader. Keep.
- **Reproducibility** — adopt LumiBot's no-lookahead memoized indicator
  pattern + explicit freshness guard so stale `ml_features.csv` (5-day stale,
  X08) can never be silently consumed.

---

# 11. Simplicity Test (Plan §13)

> Can this be implemented inside the existing project with less complexity than
> adopting the entire external framework?

| Proposed pattern | Internal implementation size | vs adopting framework | Verdict |
|---|---|---|---|
| Paper order FSM + fills | ~150-250 lines + existing ledger tables | Nautilus (Rust, LGPL, whole platform) | **Internal wins decisively** |
| Cost/MTM accounting module | ~150 lines | LumiBot (GPL, whole framework) | **Internal wins** |
| Delta-target / DTE-bucket research | ~200 lines research helper | Optopsy (AGPL, data-format constraints) | **Internal wins** |
| Tearsheet/metrics export | ~150 lines (MIT can borrow) | QSTrader (no options, unmaintained) | **Internal wins** |
| Event/state model | dataclasses, no bus | Nautilus MessageBus | **Internal wins** |

**Rule confirmed: small internal components over large external dependencies
for every candidate except QSTrader metrics, where MIT permits direct (small,
credited) copying.**

---

# 12. License / Adoption Safety (Plan §14)

| Project | License | Copy code? | Implement ideas? | Integration obligations? | Use |
|---|---|---|---|---|---|
| NautilusTrader | LGPL-3.0-or-later | No (copyleft on modified source) | Yes | Import-as-lib OK; no | Reference only |
| LumiBot | GPL-3.0 (MIT badge unreliable) | No | Yes | Copying → GPL; distribution matters | Reference only |
| Optopsy | AGPL-3.0-or-later | No (network copyleft) | Yes | Hosting a derivative → AGPL source release | Reference only |
| QSTrader | MIT | Yes (with copyright notice) | Yes | Attribution only | Safe to borrow metrics/accounting ideas; credit in source |

**[FACT]** Nothing from Nautilus/LumiBot/Optopsy will be copied into
NIFTY-RESEARCH. QSTrader MIT items (tearsheet/JSON metrics, avg-price
accounting) may be implemented with attribution if adopted.

---

# 13. Recommended Target Architecture (Plan §16)

```
CURRENT ARCHITECTURE
  monolithic precision_signals chain + paper_trader JSON singleton
  (paper ≠ backtest ≠ ledger; 0 outcomes)
          ↓
BENCHMARK FINDINGS
  1 engine/3 contexts (Nautilus, LumiBot) · order FSM (Nautilus) ·
  paper costs+MTM (all) · no-lookahead cached indicators (LumiBot) ·
  delta/DTE options research (Optopsy) · tearsheet+JSON (QSTrader)
          ↓
RECOMMENDED ARCHITECTURE  (preserves NIFTY identity; nothing replaced, only added)

  Truth (unchanged — provenance layer)
    ↓
  Event / State Integrity (NEW: lightweight order/position FSM writing into
    existing ground_truth tables; fills carry qty/px/commission; positions
    derived from fills; NO message bus)
    ↓
  Strategy (unchanged — 6-layer precision_signals + NIFTY OI/greeks)
    ↓
  Risk (unchanged — capital_guard + regime gate; ADD: denial-code reporting)
    ↓
  Execution (UNIFIED accounting core: order FSM + fees + slippage + MTM;
    paper now, backtest next, live-later via same core; ledger reconciliation)
    ↓
  Ground Truth (unchanged ledger; now also receives executions/positions/outcomes)
    ↓
  Evaluation (ADD: tearsheet + JSON export + risk-adjusted metrics, gated;
    keep insufficient-sample gate + frozen baseline)
    ↓
  Experimentation (ADD later: one-variable paper-only A/B vs frozen baseline)
    ↓
  Future Self-Improvement (only after validated outcomes — NOT now)
```

Prioritized capability order is preserved: Truth → Event/State Integrity →
Strategy → Risk → Execution → Ground Truth → Evaluation → Experimentation →
Self-Improvement.

---

# 14. FINAL RECOMMENDATION (Plan §18 — summary)

- **Architecturally strongest overall:** NautilusTrader (single engine across
  backtest/sandbox/live, event-sourced integrity, order FSM, strict
  accounting, deterministic replay).
- **Strongest for options research:** Optopsy (delta-target legs, DTE buckets,
  expiry-keyed chain, slippage/commission knobs, grouped stats).
- **Strongest for execution/paper-live parity:** NautilusTrader (sandbox
  context + same engine) with LumiBot second (same strategy class, simpler).
- **Strongest for evaluation/research:** QSTrader (portfolio accounting,
  tearsheet, JSON metrics) with Optopsy's risk metrics second.
- **What to adopt from each:**
  - NautilusTrader → order/position FSM, fill-carrying events, cost+MTM
    accounting, deterministic replay (all reimplemented internally).
  - LumiBot → strategy-portable lifecycle, disk caching, no-lookahead
    memoized indicators.
  - Optopsy → delta TargetRange, DTE-windowed entry/exit, expiration-keyed
    research table, grouped statistics.
  - QSTrader → avg-price portfolio accounting, tearsheet + JSON metrics
    (MIT, with attribution).
- **What NOT to adopt:** any of the four as a dependency/framework; message
  bus / event infra; LLM agent runtimes; extra ML; microservices; duplicate
  portfolio systems; second databases.
- **Adopt a full framework or only selected patterns?** **Selected patterns
  only, reimplemented internally.** Every candidate passes the simplicity test
  as a small internal component; every framework brings license risk and
  NSE-options incompatibility.
- **Single most valuable improvement:** a **paper order/position lifecycle
  with fill detail + cost/MTM accounting, reconciled to the ground-truth
  ledger** (fixes the divergence, stale positions, no exits, and unmeasurable
  outcomes in one move).
- **What should be implemented first:** Leg-1 order FSM + Leg-2 ledger
  reconciliation (see roadmap ADOPT-01/ADOPT-02), which unblocks honest
  outcome accumulation.

---

*Compiled 2026-08-13. READ-ONLY phase; no code/db/strategy/dependency changes,
no commit. Reference facts cited per project from public docs/repos fetched
2026-08-13; NIFTY-RESEARCH facts from current source + ledger + audit reports
(MASTER-PROJECT-BLUEPRINT.md, TRADING_DECISION_FLOW.md, X03-X08, PHASE4A/6/6.5).*
