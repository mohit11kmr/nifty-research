# PHASE 2 — Ground Truth Architecture

> Design deliverable. Built 2026-08-13. No application code modified.
> Covers master-prompt Phase 5: the canonical lifecycle that lets us answer
> "Was this signal actually correct?" and "What happened after this decision?"

---

## 1. Design goal

Today the platform records market ticks and generated signals (`history_logger`),
but **there is no link between a signal and what happened after it**. The paper
ledger (`paper_account.json`) is decoupled from the audit trail
(`signal_history`), there is no signal→decision→execution→outcome chain, and the
`paper_trade_journal` table exists but is never written (X03 F13).

Ground truth = a permanent, immutable, timestamped chain:

```
MARKET OBSERVATION → FEATURE SNAPSHOT → SIGNAL → PREDICTION → CONFIDENCE
→ DECISION → EXECUTION → POSITION → EXIT → REALIZED OUTCOME → EVALUATION
```

## 2. Canonical lifecycle stages

### Stage 0 — MARKET OBSERVATION
- **Required data**: NSE tick stream / Yahoo spot / VIX / OI snapshot.
- **Timestamp rules**: UTC ISO, from source (NSE msg time if present, else
  receive time). Never server-local-only.
- **Identifier**: `observation_id` (hash of source+symbol+ts+last_price).
- **Immutable fields**: source, symbol, raw LTP/bid/ask/oi/iv, source ts.
- **Missing-data behavior**: row must still exist with `valid=0` + reason.

### Stage 1 — FEATURE SNAPSHOT
- **Required data**: the exact indicator/feature vector consumed at decision time.
- **Timestamp rules**: `feature_ts = observation_ts` of the last input included;
  `feature_version` recorded (hash of feature-set definition).
- **Identifier**: `feature_snapshot_id`.
- **Immutable fields**: all raw feature values + versions consulted.
- **Missing-data behavior**: features are only persisted for the signals that
  fire; every feature must carry its own `data_freshness` so STALE is detectable.

### Stage 2 — SIGNAL
- **Required data**: 6-layer confluence verdict (regime, capital, technical,
  OI/skew, institutional, ML), per-layer status.
- **Timestamp rules**: `signal_ts` ≥ max feature ts; never backdated.
- **Identifier**: `signal_id` (surrogate PK, stable across re-computation).
- **Immutable fields**: layer statuses, grade, confluence score, versions,
  provenance envelope.
- **Missing-data behavior**: a signal with a NOT_COMPUTED layer is either a
  downgraded grade or NO_SIGNAL — never a silent pass.

### Stage 3 — PREDICTION
- **Required data**: directional claim (UP/DOWN/NEUTRAL) + horizon (bars/minutes).
- **Timestamp rules**: `prediction_ts`; `horizon_end_ts = signal_ts + horizon`.
- **Identifier**: `prediction_id = signal_id + 1` (1:1).
- **Immutable fields**: direction, horizon, base price.
- **Missing-data behavior**: prediction recorded only when a signal fires with
  a directional claim.

### Stage 4 — CONFIDENCE
- **Required data**: a number with a **defined calibration basis**.
- **Timestamp rules**: same as prediction.
- **Identifier**: part of prediction row.
- **Immutable fields**: confidence value, calibration method
  (walk-forward/OOS/in-sample/rule-based), null when not calibrated.
- **Missing-data behavior**: rule-constant confidences (e.g. the frozen market
  brain values) are flagged `calibration=UNKNOWN` until re-derived.

### Stage 5 — DECISION
- **Required data**: chosen action (BUY_CE/BUY_PE/SPREAD/NO_TRADE), rationale
  (signal + risk approval).
- **Timestamp rules**: `decision_ts`; must be after signal, before execution.
- **Identifier**: `decision_id` (1:1 with signal; NO_TRADE still recorded).
- **Immutable fields**: action, reason code, risk state at decision.
- **Missing-data behavior**: every signal maps to exactly one decision
  (trade or no-trade) — decisions are never implied.

### Stage 6 — EXECUTION
- **Required data**: instrument, side, qty/lots, limit/price, venue
  (PAPER/backtest), fill price + latency if available.
- **Timestamp rules**: `order_ts`, `fill_ts` (may differ).
- **Identifier**: `execution_id`; `parent_decision_id` FK.
- **Immutable fields**: requested price, fill price, fill time, slippage.
- **Missing-data behavior**: paper fills use mid/LTP with explicit
  `estimated_fill=True`; rejected orders recorded as REJECTED (not dropped).

### Stage 7 — POSITION
- **Required data**: open qty, entry price, status (OPEN/CLOSED), SL/TGT set.
- **Timestamp rules**: `open_ts`; `close_ts` null while open.
- **Identifier**: `position_id`.
- **Immutable fields**: entry; **mutable-but-logged**: SL/TGT updates
  (every update = a position_event row).
- **Missing-data behavior**: position always created at execution; entries in
  `paper_account.json` reconcile with position table on startup.

### Stage 8 — EXIT
- **Required data**: exit price, exit time, reason (SL/TGT/TIME/EMERGENCY/MANUAL).
- **Timestamp rules**: `exit_ts`; must be > open_ts; recorded even for 0-lot/untraded.
- **Identifier**: tied to position_id (1:1 close event).
- **Immutable fields**: exit price, exit time, exit reason.

### Stage 9 — REALIZED OUTCOME
- **Required data**: P/L (realized), fees/slippage, MFE, MAE, duration.
- **Timestamp rules**: `eval_ts = exit_ts` (realized) or `eval_ts` for mark.
- **Identifier**: `outcome_id` (1:1 with position).
- **Immutable fields**: realized P/L, fees. **MFE/MAE** recomputed from the tick
  stream and stamped with the data window used (they depend on data retention).
- **Missing-data behavior**: if tick data was purged before MFE/MAE could be
  computed, store `MFE=null, reason=PURGED` — never fabricate.

### Stage 10 — EVALUATION
- **Required data**: outcome vs prediction — was the directional claim right?
  was execution poor even though prediction was right?
- **Timestamp rules**: `eval_ts`; evaluation is append-only; never rewritten.
- **Identifier**: `evaluation_id`.
- **Immutable fields**: prediction_vs_outcome (HIT/MISS/N/A),
  execution_quality (GOOD/BAD/UNKNOWN), eval method + versions.
- **Missing-data behavior**: evaluation only after outcome horizon;
  still-pending horizons show `status=PENDING`.

## 3. Hard invariants (anti-corruption rules)

The schema **must prevent**:

| Hazard | Prevention |
|---|---|
| Look-ahead bias | Features are snapshotted at signal time; evaluation horizon is strictly forward; any feature read of `t+k` during generation is a schema violation (feature table has no future rows by construction) |
| Future-data leakage | Feature snapshot rows reference observation rows with `feature_ts <= signal_ts`; DB CHECK enforces `signal_ts >= max_feature_ts` |
| Duplicate outcome attribution | 1:1 FKs signal→prediction→decision; execution→position→outcome; a position belongs to one decision only |
| Mismatched timestamps | ISO UTC everywhere; source time vs receive time stored separately; clock-skew guard logs and flags |
| Stale-data contamination | Every feature row stores `data_freshness`; evaluation can filter signals whose inputs were STALE at decision time |
| Retroactive modification of historical truth | Append-only tables: UPDATE forbidden (application-level trigger rejects); corrections write a new versioned row + `supersedes` link |

## 4. Physical design (SQLite, minimal)

New file `data/ground_truth.db` (separate from research.db so retention purges
never touch it):

```
signals            signal_id PK, signal_ts, grade, confluence, checks_json,
                   feature_version, param_version, signal_version, provenance_json
predictions        prediction_id PK, signal_id FK, direction, horizon, base_price,
                   confidence, calibration, horizon_end_ts
decisions          decision_id PK, prediction_id FK, action, reason_code, risk_state,
                   decision_ts
executions         execution_id PK, decision_id FK, instrument, side, qty, req_price,
                   fill_price, fill_ts, venue, estimated_fill, slippage
positions          position_id PK, execution_id FK, open_ts, entry_price, status,
                   current_sl, current_tgt
position_events    id PK, position_id FK, event_ts, event_type(SL_CHANGE/TGT/EXIT/EMERGENCY),
                   new_value
outcomes           outcome_id PK, position_id FK, exit_ts, exit_price, exit_reason,
                   realized_pnl, fees, mfe, mae, duration_s, mfe_source(PURGED/NONE/FULL)
evaluations        evaluation_id PK, outcome_id FK, eval_ts, prediction_correct,
                   execution_quality, method, status(PENDING/DONE/SKIPPED)
market_observations observation_id PK, ts, symbol, price, source, valid, reason
feature_snapshots  snapshot_id PK, signal_id FK, feature_ts, feature_version,
                   freshness_seconds, features_json
```

- **Indexes**: `signal_ts`, `(signals.signal_ts, evaluations.status)`,
  `positions.open_ts`, FKs.
- **WAL + busy_timeout** (same pattern as fixed `history_logger`).
- **Append-only enforcement**: schema triggers `BEFORE UPDATE ... RAISE(ABORT)`
  on all truth tables; corrections use `supersedes_by` columns.
- **Clock sync**: a `system_clock` check on daemon start (log delta vs NTP) to
  flag skew before timestamps are trusted.

## 5. Reconciliation entry points (current code → ground truth)

| Today | Tomorrow |
|---|---|
| `history_logger.signal_history` | seed `signals` + `predictions` from logged signals (add horizon) |
| `paper_account.json` open_positions/closed_trades | seed `positions` + `outcomes` at close; journal every state change |
| `tick_recorder` research.db ticks | source for MFE/MAE recompute (retention-aware) |
| `auto_paper_runner` gates | emit decision rows (including STAND_DOWN/NO_SIGNAL → NO_TRADE decisions) |

Backfill rule: historical `paper_account.json` closed trades can be imported
with `execution_quality=UNKNOWN`, `prediction_correct=UNKNOWN` rather than
fabricated — honesty over completeness.
