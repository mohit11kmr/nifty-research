# EXTERNAL ADOPTION ROADMAP

> Companion to `audit/EXTERNAL-ARCHITECTURE-BENCHMARK.md`.
> **Benchmark and adoption-planning phase only. READ-ONLY. Nothing here has
> been implemented.** Priority: P0 = MUST ADOPT, P1 = HIGH VALUE,
> P2 = NICE TO HAVE, P3 = REFERENCE ONLY, REJECT = DO NOT ADOPT.
> NIFTY-RESEARCH current state basis: 149 signals / 149 SKIP / 0 outcomes;
> paper account (10 stale OPEN positions) diverged from ground-truth ledger
> (0 executions); 172 tests green; frozen baseline phase6-baseline-2026-08-13.

---

# Top 10 Prioritized Changes

## ADOPT-01 — Paper order/position lifecycle FSM
- **ID:** ADOPT-01
- **Reference Project:** NautilusTrader (order FSM, fill events, PositionOpened/Closed)
- **Capability:** Execution lifecycle
- **Current Gap:** `paper_trader.execute_paper_order`/`close_paper_position` are atomic happy-path; no intermediate states, no fill detail, no partial fills/cancels, nothing auto-closes (10 stale OPEN positions from 2026-08-12).
- **Recommended Adoption:** Add a minimal order FSM to the paper layer: SUBMITTED → ACCEPTED → PARTIALLY_FILLED → FILLED | CANCELED | REJECTED; fills record qty/px/commission; positions derived causally from fills. Plain dataclasses + existing ledger tables; NO message bus.
- **Priority:** P0
- **Complexity:** Low–Medium (~150-250 lines)
- **Risk:** Low (additive; ledger schema unchanged; STAY_OUT path untouched)
- **Expected Benefit:** Fixes stale positions + lifecycle gap; every trade has an auditable state trail.
- **Dependencies:** none
- **Validation:** new tests: order state transitions, partial fill accounting, cancel path; chain-health remains HEALTHY; ledger still append-only.

## ADOPT-02 — Paper ↔ ground-truth ledger reconciliation
- **ID:** ADOPT-02
- **Reference Project:** NautilusTrader (venue reconciliation), QSTrader (Transaction-driven accounting)
- **Capability:** Ground-truth integrity / accounting
- **Current Gap:** paper_account.json and ground_truth ledger diverged (10 OPEN vs 0 executions/positions rows); two "run everything" paths (run_all vs quant_daemon) execute different things (X03).
- **Recommended Adoption:** Every paper execution/close writes the ground_truth execution/position rows (tables already exist and are empty); a read-only reconciliation report flags any mismatch between paper_account.json and the ledger; consolidate the auto-runner to ONE path.
- **Priority:** P0
- **Complexity:** Low–Medium
- **Risk:** Medium (ledger integrity must be preserved; do not touch append-only triggers or schema)
- **Expected Benefit:** Ends divergence — single source of truth for what was executed.
- **Dependencies:** ADOPT-01 (FSM writes the records reconciliation reads)
- **Validation:** reconciliation report shows 0 mismatches; test inserts a paper execution and asserts ledger row + paper_account.json agree.

## ADOPT-03 — Cost + mark-to-market in paper execution
- **ID:** ADOPT-03
- **Reference Project:** NautilusTrader (fee models incl. option-specific, slippage fill models), LumiBot (TradingFee/TradingSlippage, option MTM), Optopsy (commission + 4 slippage modes)
- **Capability:** Execution realism
- **Current Gap:** paper has NO fees/slippage/MTM (backtester has 1.5% slippage + ₹40 cost); open positions not marked to market; P&L not market-marked → outcomes can't be honestly classified (NEUTRAL band needs costs).
- **Recommended Adoption:** Parameterized cost model (per-contract + slippage on fill, reuse backtester's ₹40/1.5% defaults); open positions marked to last quote from research.db `ticks`/spot; report realized + unrealized P&L.
- **Priority:** P1
- **Complexity:** Low (~150 lines)
- **Risk:** Low (paper-only)
- **Expected Benefit:** Paper P&L approximates live; honest WIN/LOSS/NEUTRAL outcome classification becomes possible.
- **Dependencies:** ADOPT-01
- **Validation:** test: fill with slippage+commission changes cash and position cost basis; MTM snapshot reflects last quote.

## ADOPT-04 — Scheduled auto-exit (square-off + stop/target)
- **ID:** ADOPT-04
- **Reference Project:** NautilusTrader (position lifecycle, contingency orders), Optopsy (stop_loss/take_profit/max_hold_days)
- **Capability:** Execution lifecycle / risk
- **Current Gap:** nothing auto-closes; expiry 15:05 square-off rule (OWNER_INSTRUCTIONS) and 1.5×ATR stop are not enforced on paper positions.
- **Recommended Adoption:** A paper exit scheduler: stop (1.5×ATR / 0.8%), target (1:2), and expiry-day 15:05 square-off; closes orphans (incl. the 10 stale positions once reconciled) and records exit_reason.
- **Priority:** P1
- **Complexity:** Medium
- **Risk:** Medium (must respect ledger immutability; exits are new rows, not edits)
- **Expected Benefit:** No more orphan positions; risk rules actually enforced on paper; outcomes get exit reasons (needed by outcome engine).
- **Dependencies:** ADOPT-01, ADOPT-02
- **Validation:** chain-health MISSING_OUTCOME detectors stay clean; test forces expiry square-off and asserts position closed + outcome row created.

## ADOPT-05 — Unified execution/accounting core (backtest ↔ paper parity)
- **ID:** ADOPT-05
- **Reference Project:** NautilusTrader (one kernel, three contexts), LumiBot (same strategy class, all modes)
- **Capability:** Backtest/paper/live parity
- **Current Gap:** backtester and paper_trader are separate execution/accounting paths with different cost models.
- **Recommended Adoption:** Extract the accounting core (order FSM + fills + costs + MTM + P&L) from ADOPT-01/03 into a shared module used by paper now and backtest next; signal logic already shared via precision_signals. LIVE remains disabled.
- **Priority:** P1
- **Complexity:** Medium
- **Risk:** Medium (unifying paths must not change existing backtest results — regression tests against current outputs)
- **Expected Benefit:** Same execution model across backtest/paper; strategy validated in backtest is the same code that trades paper.
- **Dependencies:** ADOPT-01, ADOPT-03
- **Validation:** backtest outputs byte-identical to frozen baseline after refactor; paper fills use identical accounting.

## ADOPT-06 — No-lookahead memoized indicators + freshness guard
- **ID:** ADOPT-06
- **Reference Project:** LumiBot (pandas-ta indicators computed once, sliced to bar t, memoized; disk cache)
- **Capability:** Data / reproducibility
- **Current Gap:** indicators recompute per call; `ml_features.csv` silently consumed 5 days stale (X08); no explicit no-lookahead guarantee.
- **Recommended Adoption:** Memoize indicators over the cached series with bar-slicing; add a hard freshness guard (reject feature files older than budget — truth.py already labels them).
- **Priority:** P2
- **Complexity:** Low
- **Risk:** Low (research-only paths; decision path unchanged)
- **Expected Benefit:** Faster research loops; impossible to silently train on stale features.
- **Dependencies:** none
- **Validation:** freshness guard test: stale ml_features → feature generation errors instead of proceeding.

## ADOPT-07 — Delta-target strike/leg selection (TargetRange)
- **ID:** ADOPT-07
- **Reference Project:** Optopsy (per-leg delta targeting with target/min/max)
- **Capability:** Options research / strategy
- **Current Gap:** `smart_strike_selector` uses a single delta band (0.30-0.55) + %-premium cap; multi-leg legs not delta-targeted per leg.
- **Recommended Adoption:** Extend strike selection to explicit target/min/max delta bands per leg (helper for multi_leg_options and premium_seller research). Reimplement internally, not Optopsy code.
- **Priority:** P2
- **Complexity:** Low–Medium
- **Risk:** Low (research helper; no change to live decision thresholds)
- **Expected Benefit:** DTE/delta-consistent leg selection matching how NSE weekly traders actually strike; replaces %-OTM heuristics.
- **Dependencies:** none
- **Validation:** unit tests: given spot/IV/DTE, selected strike lands inside the delta band; reproducible across runs.

## ADOPT-08 — DTE-windowed entry/exit + expiration-keyed research table
- **ID:** ADOPT-08
- **Reference Project:** Optopsy (max_entry_dte/exit_dte/dte_interval; flat expiration-keyed chain)
- **Capability:** Options research
- **Current Gap:** premium_seller/backtester hardcode expiry handling; oi_snapshots are per-day files, not expiry-keyed.
- **Recommended Adoption:** Add DTE-window entry/exit parameters to the backtesters; a read-only research view keyed by (expiration, quote_date) over oi_snapshots.
- **Priority:** P2
- **Complexity:** Medium
- **Risk:** Low (research-only)
- **Expected Benefit:** Systematic Indian weekly/monthly expiry research (e.g. "45-DTE iron condor, exit at 21-DTE").
- **Dependencies:** none
- **Validation:** backtest grid runs with DTE windows; results reproducible vs frozen baseline methodology.

## ADOPT-09 — Tearsheet + JSON metrics export
- **ID:** ADOPT-09
- **Reference Project:** QSTrader (tearsheet: cumulative vs benchmark, underwater, monthly heatmap; JSON export) — MIT, borrow with attribution
- **Capability:** Evaluation / reporting
- **Current Gap:** evaluation_engine reports and gates on insufficient sample but has no standard tearsheet/JSON export.
- **Recommended Adoption:** Add tearsheet render + JSON export of gated metrics (CAGR, Sharpe, Sortino, max drawdown, trade stats) behind the existing insufficient-sample gate; include our option-specific metrics (MFE/MAE, R-multiple, NEUTRAL band) when outcomes exist.
- **Priority:** P2
- **Complexity:** Low (~150 lines)
- **Risk:** Low (reporting only; gate already exists)
- **Expected Benefit:** Comparable, auditable research output; JSON feeds the ledger/dashboards.
- **Dependencies:** ADOPT-03 (needs costs) for meaningful P&L metrics
- **Validation:** empty-outcomes run exports null/INSUFFICIENT_SAMPLE; synthetic 20-outcome fixture exports full metrics.

## ADOPT-10 — Replay harness for paper/backtest debugging
- **ID:** ADOPT-10
- **Reference Project:** NautilusTrader (deterministic replay via catalog), QSTrader (deterministic loop)
- **Capability:** Reproducibility / debugging
- **Current Gap:** no way to replay a stored market day (research.db ticks/spot) through the paper path to debug fills/exits.
- **Recommended Adoption:** A read-only replay runner that feeds recorded ticks/spot through the paper FSM with the same clock semantics, enabling deterministic debugging of a day.
- **Priority:** P3
- **Complexity:** Medium
- **Risk:** Low (paper-only, no market writes)
- **Expected Benefit:** Debug stale-position/exit bugs deterministically; seed for future experiments.
- **Dependencies:** ADOPT-01, ADOPT-05
- **Validation:** replay of 2026-08-12 tick data reproduces the recorded position states.

---

# P3 — REFERENCE ONLY (study, do not build now)

- Nautilus DST bitwise-determinism contract → already approximated by our
  byte-identical re-run + frozen baseline; adopt concepts when experiments begin.
- Nautilus RiskEngine pre-trade denial codes → add denial-code reporting to
  capital_guard (P3; improves rejection-reason accounting).
- LumiBot disk-caching abstraction → we already cache to data/; no framework needed.

# REJECT — DO NOT ADOPT

- NautilusTrader / LumiBot / Optopsy as dependencies (LGPL/GPL/AGPL + no NSE
  adapter + overkill).
- Message bus / Pub-Sub / event infrastructure (scale does not justify it).
- LLM/agentic trading runtimes (no evidence basis; 0 outcomes).
- Extra ML of any kind (no data; existing ML honest context-only).
- Microservices / Redis / multi-currency / multi-venue breadth.
- Duplicate portfolio systems (would shadow ground_truth tables).
- Second databases (ledger + research.db + paper JSON already cover needs).

# Suggested sequencing

```
PHASE A (integrity, P0):        ADOPT-01 → ADOPT-02
PHASE B (realism, P1):          ADOPT-03 → ADOPT-04 → ADOPT-05
PHASE C (research, P2):         ADOPT-06 → ADOPT-07 → ADOPT-08 → ADOPT-09
PHASE D (replay, P3):           ADOPT-10
Every phase: run 172 tests + chain-health; baseline stays frozen; nothing
implemented in this benchmark phase.
```

---

*Compiled 2026-08-13. READ-ONLY. No implementation performed; no code, schema,
strategy, thresholds, risk rules, paper account, or dependencies changed; no
commit.*
