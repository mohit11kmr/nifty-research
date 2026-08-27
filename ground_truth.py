"""Ground Truth Database + Outcome Engine (Phase 5).

Implements the canonical immutable event chain that makes the system's
historical record trustworthy:

    MARKET OBSERVATION -> FEATURE SNAPSHOT -> SIGNAL -> PREDICTION
    -> DECISION -> EXECUTION -> POSITION -> EXIT -> REALIZED OUTCOME
    -> EVALUATION

Design basis: audit/PHASE2-GROUND-TRUTH.md (physical design section 4),
audit/PHASE2-OUTCOME-ENGINE.md (outcome + taxonomy rules) and the Phase 5
specification (OPENCODE_PHASE5_GROUND_TRUTH_OUTCOME_ENGINE.md).

Honesty rules enforced here (not just documented):
  * Append-only: UPDATE/DELETE on every truth table is rejected by SQLite
    triggers. Only `positions` may be updated, and ONLY the exit/status
    fields (entry fields are immutable, a closed position cannot re-open,
    and once CLOSED it cannot close again).
  * Provenance: every record carries the Phase 3/4A provenance envelope.
    Legacy imports are marked LEGACY and never upgraded to REAL.
  * Missing data: never invented. A feature with no value stays None with a
    reason; MFE/MAE with no tick data is stored null with mfe_source=NONE.
  * Anti-leakage: signal/future close data is only ever read by the Outcome
    Engine strictly AFTER the evaluation horizon.
"""
import os
import sys
import json
import sqlite3
import datetime as dt

import truth

sys.path.insert(0, os.path.dirname(__file__))

DB_FILE = os.path.join("data", "ground_truth.db")
RESEARCH_DB = os.path.join("data", "research.db")
NIFTY_HISTORY_CSV = os.path.join("data", "nifty_history.csv")

_SIGNAL_TS_FMT = "%Y-%m-%d %H:%M:%S IST"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS market_observations (
    observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    price REAL,
    source TEXT,
    valid INTEGER NOT NULL DEFAULT 1,
    reason TEXT,
    provenance_json TEXT
);
CREATE TABLE IF NOT EXISTS feature_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    feature_ts TEXT NOT NULL,
    feature_version TEXT,
    freshness_seconds REAL,
    features_json TEXT,
    provenance_json TEXT,
    FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
);
CREATE TABLE IF NOT EXISTS signals (
    signal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_ts TEXT NOT NULL,
    symbol TEXT,
    direction TEXT,
    signal_type TEXT,
    score TEXT,
    confidence REAL,
    market_state TEXT,
    observation_id INTEGER,
    signal_version TEXT,
    parameter_version TEXT,
    feature_version TEXT,
    checks_json TEXT,
    provenance_json TEXT,
    FOREIGN KEY (observation_id) REFERENCES market_observations(observation_id)
);
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL,
    predicted_direction TEXT NOT NULL,
    horizon TEXT,
    base_price REAL,
    confidence REAL,
    calibration TEXT,
    model_type TEXT,
    model_version TEXT,
    prediction_ts TEXT NOT NULL,
    horizon_end_ts TEXT,
    provenance_json TEXT,
    FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
);
CREATE TABLE IF NOT EXISTS decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    prediction_id INTEGER,
    decision_type TEXT NOT NULL,
    decision_ts TEXT NOT NULL,
    reason TEXT,
    risk_state TEXT,
    capital_guard_state TEXT,
    execution_mode TEXT,
    provenance_json TEXT,
    FOREIGN KEY (signal_id) REFERENCES signals(signal_id),
    FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)
);
CREATE TABLE IF NOT EXISTS executions (
    execution_id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER,
    symbol TEXT,
    side TEXT,
    quantity INTEGER,
    strike REAL,
    option_type TEXT,
    requested_price REAL,
    fill_price REAL,
    execution_ts TEXT NOT NULL,
    slippage REAL,
    fees REAL,
    execution_mode TEXT NOT NULL,
    estimated_fill INTEGER,
    broker_reference TEXT,
    provenance_json TEXT,
    FOREIGN KEY (decision_id) REFERENCES decisions(decision_id)
);
CREATE TABLE IF NOT EXISTS positions (
    position_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_execution_id INTEGER,
    exit_execution_id INTEGER,
    symbol TEXT,
    side TEXT,
    quantity INTEGER,
    strike REAL,
    option_type TEXT,
    entry_price REAL,
    exit_price REAL,
    entry_timestamp TEXT,
    exit_timestamp TEXT,
    fees REAL,
    status TEXT NOT NULL,
    current_sl REAL,
    current_tgt REAL,
    position_ref TEXT,
    provenance_json TEXT,
    FOREIGN KEY (entry_execution_id) REFERENCES executions(execution_id),
    FOREIGN KEY (exit_execution_id) REFERENCES executions(execution_id)
);
CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL UNIQUE,
    exit_ts TEXT,
    exit_price REAL,
    exit_reason TEXT,
    realized_pnl REAL,
    gross_pnl REAL,
    net_pnl REAL,
    fees REAL,
    slippage REAL,
    duration_s REAL,
    mfe REAL,
    mae REAL,
    mfe_source TEXT,
    return_pct REAL,
    outcome_class TEXT,
    provenance_json TEXT,
    FOREIGN KEY (position_id) REFERENCES positions(position_id)
);
CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    outcome_id INTEGER,
    prediction_id INTEGER,
    eval_ts TEXT,
    prediction_correct TEXT,
    execution_quality TEXT,
    method TEXT,
    status TEXT,
    actual_move REAL,
    base_price REAL,
    provenance_json TEXT,
    FOREIGN KEY (outcome_id) REFERENCES outcomes(outcome_id),
    FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)
);
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(signal_ts);
CREATE INDEX IF NOT EXISTS idx_snapshots_signal ON feature_snapshots(signal_id);
CREATE INDEX IF NOT EXISTS idx_predictions_signal ON predictions(signal_id);
CREATE INDEX IF NOT EXISTS idx_decisions_signal ON decisions(signal_id);
CREATE INDEX IF NOT EXISTS idx_executions_decision ON executions(decision_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_executions_broker_ref ON executions(broker_reference);
CREATE INDEX IF NOT EXISTS idx_positions_open ON positions(entry_timestamp);
CREATE INDEX IF NOT EXISTS idx_outcomes_position ON outcomes(position_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_prediction ON evaluations(prediction_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_status ON evaluations(status);
"""

# Append-only: no UPDATE, no DELETE on immutable truth tables.
_APPEND_ONLY_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS observations_append_only BEFORE UPDATE ON market_observations
BEGIN SELECT RAISE(ABORT, 'market_observations: append-only'); END;
CREATE TRIGGER IF NOT EXISTS observations_no_delete BEFORE DELETE ON market_observations
BEGIN SELECT RAISE(ABORT, 'market_observations: append-only'); END;
CREATE TRIGGER IF NOT EXISTS snapshots_append_only BEFORE UPDATE ON feature_snapshots
BEGIN SELECT RAISE(ABORT, 'feature_snapshots: append-only'); END;
CREATE TRIGGER IF NOT EXISTS snapshots_no_delete BEFORE DELETE ON feature_snapshots
BEGIN SELECT RAISE(ABORT, 'feature_snapshots: append-only'); END;
CREATE TRIGGER IF NOT EXISTS signals_append_only BEFORE UPDATE ON signals
BEGIN SELECT RAISE(ABORT, 'signals: append-only'); END;
CREATE TRIGGER IF NOT EXISTS signals_no_delete BEFORE DELETE ON signals
BEGIN SELECT RAISE(ABORT, 'signals: append-only'); END;
CREATE TRIGGER IF NOT EXISTS predictions_append_only BEFORE UPDATE ON predictions
BEGIN SELECT RAISE(ABORT, 'predictions: append-only'); END;
CREATE TRIGGER IF NOT EXISTS predictions_no_delete BEFORE DELETE ON predictions
BEGIN SELECT RAISE(ABORT, 'predictions: append-only'); END;
CREATE TRIGGER IF NOT EXISTS decisions_append_only BEFORE UPDATE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions: append-only'); END;
CREATE TRIGGER IF NOT EXISTS decisions_no_delete BEFORE DELETE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions: append-only'); END;
CREATE TRIGGER IF NOT EXISTS executions_append_only BEFORE UPDATE ON executions
BEGIN SELECT RAISE(ABORT, 'executions: append-only'); END;
CREATE TRIGGER IF NOT EXISTS executions_no_delete BEFORE DELETE ON executions
BEGIN SELECT RAISE(ABORT, 'executions: append-only'); END;
CREATE TRIGGER IF NOT EXISTS outcomes_append_only BEFORE UPDATE ON outcomes
BEGIN SELECT RAISE(ABORT, 'outcomes: append-only'); END;
CREATE TRIGGER IF NOT EXISTS outcomes_no_delete BEFORE DELETE ON outcomes
BEGIN SELECT RAISE(ABORT, 'outcomes: append-only'); END;
CREATE TRIGGER IF NOT EXISTS evaluations_append_only BEFORE UPDATE ON evaluations
BEGIN SELECT RAISE(ABORT, 'evaluations: append-only'); END;
CREATE TRIGGER IF NOT EXISTS evaluations_no_delete BEFORE DELETE ON evaluations
BEGIN SELECT RAISE(ABORT, 'evaluations: append-only'); END;
"""

# positions are mutable-but-logged: only the exit fields may change, a closed
# position cannot re-open or close twice, and status is restricted.
_POSITION_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS positions_entry_immutable
BEFORE UPDATE ON positions
FOR EACH ROW
WHEN OLD.entry_execution_id != NEW.entry_execution_id
  OR OLD.entry_price != NEW.entry_price
  OR OLD.entry_timestamp != NEW.entry_timestamp
  OR OLD.symbol != NEW.symbol
  OR OLD.side != NEW.side
  OR OLD.quantity != NEW.quantity
  OR OLD.strike != NEW.strike
  OR OLD.option_type != NEW.option_type
BEGIN SELECT RAISE(ABORT, 'positions: entry fields immutable'); END;

CREATE TRIGGER IF NOT EXISTS positions_no_reclose
BEFORE UPDATE ON positions
FOR EACH ROW
WHEN OLD.status = 'CLOSED' AND NEW.status = 'CLOSED'
BEGIN SELECT RAISE(ABORT, 'positions: already closed'); END;

CREATE TRIGGER IF NOT EXISTS positions_status_guard
BEFORE UPDATE ON positions
FOR EACH ROW
WHEN NEW.status NOT IN ('OPEN', 'CLOSED', 'CANCELLED')
BEGIN SELECT RAISE(ABORT, 'positions: invalid status'); END;

CREATE TRIGGER IF NOT EXISTS positions_no_delete BEFORE DELETE ON positions
BEGIN SELECT RAISE(ABORT, 'positions: append-only'); END;
"""


def now_str():
    """Current IST timestamp in the signal-history convention."""
    return dt.datetime.now().strftime(_SIGNAL_TS_FMT)


def _parse_ts(ts):
    """Parse an IST string (or ISO-with-T) to a naive local datetime."""
    if not ts:
        return None
    s = str(ts).strip()
    if s.endswith("IST"):
        s = s[:-3].strip()
    s = s.replace("T", " ").replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


class GroundTruthDB:
    """Canonical Ground Truth persistence + Outcome Engine.

    All writes are INSERTs (append-only triggers reject UPDATE/DELETE on
    truth tables). Positions may be closed via `close_position`, which is
    the only sanctioned mutation and only touches exit/status fields.
    """

    def __init__(self, db_file=None):
        self.db_file = db_file or DB_FILE
        self._conn = None

    # ------------------------------------------------------------------
    # connection / schema
    # ------------------------------------------------------------------
    def _connect(self):
        if self._conn is not None:
            return self._conn
        os.makedirs(os.path.dirname(os.path.abspath(self.db_file)), exist_ok=True)
        conn = sqlite3.connect(self.db_file, timeout=10)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_SCHEMA)
        conn.executescript(_INDEXES)
        conn.executescript(_APPEND_ONLY_TRIGGERS)
        conn.executescript(_POSITION_TRIGGERS)
        conn.commit()
        self._conn = conn
        return conn

    def _prov(self, prov):
        return truth.serialize_provenance(truth.canonical_provenance(**(prov or {})))

    def _cur(self):
        return self._connect().cursor()

    # ------------------------------------------------------------------
    # Stage 0 - MARKET OBSERVATION
    # ------------------------------------------------------------------
    def record_observation(self, ts, symbol, price, source, valid=1, reason=None,
                           provenance=None):
        cur = self._cur()
        cur.execute(
            "INSERT INTO market_observations (ts, symbol, price, source, valid, reason, provenance_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, symbol, price, source, valid, reason, self._prov(provenance)),
        )
        self._conn.commit()
        return cur.lastrowid

    # ------------------------------------------------------------------
    # Stage 1 - FEATURE SNAPSHOT
    # ------------------------------------------------------------------
    def record_feature_snapshot(self, signal_id, feature_ts, feature_version,
                                freshness_seconds, features_json, provenance=None):
        cur = self._cur()
        cur.execute(
            "INSERT INTO feature_snapshots (signal_id, feature_ts, feature_version,"
            " freshness_seconds, features_json, provenance_json) VALUES (?, ?, ?, ?, ?, ?)",
            (signal_id, feature_ts, feature_version, freshness_seconds,
             json.dumps(features_json, sort_keys=True, default=str),
             self._prov(provenance)),
        )
        self._conn.commit()
        return cur.lastrowid

    # ------------------------------------------------------------------
    # Stage 2 - SIGNAL
    # ------------------------------------------------------------------
    def record_signal(self, signal_ts, symbol, direction, signal_type, score,
                      confidence, market_state, observation_id, signal_version,
                      parameter_version, feature_version, checks_json,
                      provenance=None):
        cur = self._cur()
        cur.execute(
            "INSERT INTO signals (signal_ts, symbol, direction, signal_type, score,"
            " confidence, market_state, observation_id, signal_version,"
            " parameter_version, feature_version, checks_json, provenance_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (signal_ts, symbol, direction, signal_type, score, confidence,
             market_state, observation_id, signal_version, parameter_version,
             feature_version,
             json.dumps(checks_json, sort_keys=True, default=str) if checks_json else None,
             self._prov(provenance)),
        )
        self._conn.commit()
        return cur.lastrowid

    # ------------------------------------------------------------------
    # Stage 3 - PREDICTION
    # ------------------------------------------------------------------
    def record_prediction(self, signal_id, predicted_direction, base_price,
                          horizon=None, horizon_end_ts=None, confidence=None,
                          calibration="UNKNOWN", model_type=None,
                          model_version=None, prediction_ts=None,
                          provenance=None):
        prediction_ts = prediction_ts or now_str()
        cur = self._cur()
        cur.execute(
            "INSERT INTO predictions (signal_id, predicted_direction, horizon, base_price,"
            " confidence, calibration, model_type, model_version, prediction_ts,"
            " horizon_end_ts, provenance_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (signal_id, predicted_direction, horizon, base_price, confidence,
             calibration, model_type, model_version, prediction_ts, horizon_end_ts,
             self._prov(provenance)),
        )
        self._conn.commit()
        return cur.lastrowid

    # ------------------------------------------------------------------
    # Stage 5 - DECISION
    # ------------------------------------------------------------------
    def record_decision(self, decision_type, signal_id=None, prediction_id=None,
                        reason=None, risk_state=None, capital_guard_state=None,
                        execution_mode=None, decision_ts=None, provenance=None):
        decision_ts = decision_ts or now_str()
        cur = self._cur()
        cur.execute(
            "INSERT INTO decisions (signal_id, prediction_id, decision_type, decision_ts,"
            " reason, risk_state, capital_guard_state, execution_mode, provenance_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (signal_id, prediction_id, decision_type, decision_ts, reason,
             json.dumps(risk_state, sort_keys=True, default=str) if risk_state else None,
             capital_guard_state, execution_mode, self._prov(provenance)),
        )
        self._conn.commit()
        return cur.lastrowid

    # ------------------------------------------------------------------
    # Stage 6 - EXECUTION
    # ------------------------------------------------------------------
    def record_execution(self, decision_id, symbol, side, quantity, requested_price,
                         fill_price, execution_ts, execution_mode="PAPER",
                         estimated_fill=True, slippage=0.0, fees=0.0,
                         broker_reference=None, strike=None, option_type=None,
                         provenance=None):
        cur = self._cur()
        cur.execute(
            "INSERT INTO executions (decision_id, symbol, side, quantity, strike, option_type,"
            " requested_price, fill_price, execution_ts, slippage, fees, execution_mode,"
            " estimated_fill, broker_reference, provenance_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (decision_id, symbol, side, quantity, strike, option_type,
             requested_price, fill_price, execution_ts, slippage, fees, execution_mode,
             1 if estimated_fill else 0, broker_reference, self._prov(provenance)),
        )
        self._conn.commit()
        return cur.lastrowid

    # ------------------------------------------------------------------
    # Stage 7 - POSITION
    # ------------------------------------------------------------------
    def record_position(self, entry_execution_id, symbol, side, quantity, entry_price,
                        entry_timestamp, status="OPEN", current_sl=None,
                        current_tgt=None, position_ref=None, strike=None,
                        option_type=None, provenance=None):
        cur = self._cur()
        cur.execute(
            "INSERT INTO positions (entry_execution_id, symbol, side, quantity, strike, option_type,"
            " entry_price, entry_timestamp, status, current_sl, current_tgt, position_ref,"
            " provenance_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry_execution_id, symbol, side, quantity, strike, option_type,
             entry_price, entry_timestamp, status, current_sl, current_tgt, position_ref,
             self._prov(provenance)),
        )
        self._conn.commit()
        return cur.lastrowid

    # ------------------------------------------------------------------
    # Stage 8+9 - EXIT -> REALIZED OUTCOME (Outcome Engine)
    # ------------------------------------------------------------------
    def close_position(self, position_id, exit_price, exit_timestamp, exit_reason,
                       exit_side="SELL", fees=0.0, slippage=0.0,
                       exit_execution_id=None, provenance=None):
        """Close a position and compute its canonical outcome (called once).

        Raises ValueError if the position is missing or already closed - a
        closed outcome can never be produced twice (no duplicate attribution).
        """
        cur = self._cur()
        row = cur.execute(
            "SELECT position_id, status FROM positions WHERE position_id = ?",
            (position_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"position {position_id} not found")
        if row[1] == "CLOSED":
            raise ValueError(f"position {position_id} already closed")

        pos = self.get_position(position_id)
        qty = int(pos["quantity"])
        side = str(pos["side"]).upper()
        entry = float(pos["entry_price"])
        entry_dt = _parse_ts(pos["entry_timestamp"])
        exit_dt = _parse_ts(exit_timestamp)

        if side == "SELL":
            gross = (entry - exit_price) * qty
        else:
            gross = (exit_price - entry) * qty
        net = gross - float(fees) - float(slippage)
        duration_s = (exit_dt - entry_dt).total_seconds() if (entry_dt and exit_dt) else None
        return_pct = (net / (entry * qty) * 100.0) if entry and qty else None

        cost_floor = float(fees) + max(float(slippage), 0.0)
        if gross > cost_floor:
            outcome_class = "WIN"
        elif gross < -cost_floor:
            outcome_class = "LOSS"
        else:
            outcome_class = "BREAKEVEN"

        mfe, mae, mfe_source = self._mfe_mae(pos, entry_dt, exit_dt)

        cur.execute(
            "UPDATE positions SET status='CLOSED', exit_price=?, exit_timestamp=?,"
            " exit_execution_id=? WHERE position_id=?",
            (exit_price, exit_timestamp, exit_execution_id, position_id),
        )
        self._conn.commit()

        cur.execute(
            "INSERT INTO outcomes (position_id, exit_ts, exit_price, exit_reason,"
            " realized_pnl, gross_pnl, net_pnl, fees, slippage, duration_s, mfe, mae,"
            " mfe_source, return_pct, outcome_class, provenance_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (position_id, exit_timestamp, exit_price, exit_reason, net, gross, net,
             fees, slippage, duration_s, mfe, mae, mfe_source, return_pct,
             outcome_class, self._prov(provenance)),
        )
        self._conn.commit()
        return cur.lastrowid

    def _mfe_mae(self, pos, entry_dt, exit_dt):
        """Best-effort MFE/MAE from the real research.db tick stream.

        Returns (mfe, mae, source). Never fabricates: with no matching tick
        data the values are None with source 'NONE'.
        """
        if entry_dt is None or exit_dt is None or exit_dt <= entry_dt:
            return None, None, "NONE"
        try:
            conn = sqlite3.connect(RESEARCH_DB, timeout=10)
            expiries = [r[0] for r in conn.execute("SELECT DISTINCT expiry FROM ticks").fetchall()]
            active = None
            for exp in sorted(expiries):
                d = dt.datetime.strptime(exp, "%d-%b-%Y")
                if d >= entry_dt.replace(hour=0, minute=0, second=0):
                    active = exp
                    break
            if active is None:
                conn.close()
                return None, None, "NONE"
            t0 = entry_dt.strftime("%Y-%m-%dT%H:%M:%S")
            t1 = exit_dt.strftime("%Y-%m-%dT%H:%M:%S")
            rows = conn.execute(
                "SELECT ltp FROM ticks WHERE symbol=? AND strike=? AND side=? AND expiry=?"
                " AND recv_ts>=? AND recv_ts<=? AND ltp IS NOT NULL AND ltp>0",
                (pos.get("symbol"), pos.get("strike"), pos.get("option_type"), active, t0, t1),
            ).fetchall()
            conn.close()
            if not rows:
                return None, None, "NONE"
            side = str(pos.get("side") or "BUY").upper()
            if side == "SELL":
                diffs = [float(pos["entry_price"]) - ltp for ltp, in rows]
            else:
                diffs = [ltp - float(pos["entry_price"]) for ltp, in rows]
            mfe = round(max(diffs), 2)
            mae = round(-min(diffs), 2)
            return mfe, mae, "FULL"
        except Exception:
            return None, None, "NONE"

    # ------------------------------------------------------------------
    # Canonical chain recording
    # ------------------------------------------------------------------
    @staticmethod
    def _direction_from_action(action):
        action = str(action or "").upper()
        if any(k in action for k in ("CALL", "BULLISH")):
            return "UP"
        if any(k in action for k in ("PUT", "BEARISH")):
            return "DOWN"
        return None

    def _derive_decision(self, signal_action, signal_grade, capital_guard_audit):
        """Deterministic signal->decision mapping (documented rule).

        No evaluable signal -> SKIP. Actionable + guard APPROVED -> ENTER.
        Actionable + guard not approved -> REJECT.
        """
        action = str(signal_action or "")
        grade = str(signal_grade or "")
        if action in ("STAY_OUT", "NO_SIGNAL") or "STAY_OUT" in grade:
            return "SKIP", "no evaluable signal (STAY_OUT/NO_SIGNAL)"
        if capital_guard_audit:
            status = capital_guard_audit.get("safety_status")
            if status and status != "APPROVED":
                return "REJECT", f"capital guard not approved ({status})"
        return "ENTER", "signal actionable"

    def record_signal_chain(self, signal_data, capital_guard_audit=None,
                            decision_override=None, provenance=None,
                            freshness_seconds=None):
        """Record the full canonical chain for one generated signal.

        observation -> signal -> feature_snapshot -> [prediction] -> decision.

        signal_data: the dict returned by precision_signals.
        capital_guard_audit: CapitalGuard().full_capital_safety_audit() dict.
        decision_override: force decision_type (e.g. ENTER) when the caller
            is about to actually execute even if guard is RESTRICTED.
        Returns {observation_id, snapshot_id, signal_id, prediction_id,
                 decision_id}.
        """
        now = now_str()
        prov = dict(provenance or {})
        action = signal_data.get("signal_action", "STAY_OUT")
        grade = signal_data.get("signal_grade", "NO_SIGNAL")
        spot = signal_data.get("nifty_spot")
        checks = signal_data.get("confluence_checks") or {}
        signal_version = truth.hash_version(checks)
        feature_version = prov.get("feature_version") or signal_version

        # data freshness of the input cache at signal time (Phase 7)
        if freshness_seconds is None:
            try:
                fr = truth.file_freshness(NIFTY_HISTORY_CSV, truth.DAILY_CACHE_FRESHNESS_H)
                freshness_seconds = round(fr["age_h"] * 3600, 1) if fr["age_h"] is not None else None
            except Exception:
                freshness_seconds = None
        freshness_status = truth.freshness_status(freshness_seconds, truth.DAILY_CACHE_FRESHNESS_H * 3600)

        # Stage 0 - observation (the spot that fed the signal)
        observation_id = self.record_observation(
            ts=now, symbol="NIFTY", price=spot,
            source="precision_signals:nifty_spot",
            valid=1 if spot is not None else 0,
            reason=None if spot is not None else "no cached spot available",
            provenance={"status": truth.REAL if spot is not None else truth.MISSING,
                        "source": "precision_signals"},
        )

        # Stage 2 - signal (checks_json embeds the action/grade so the chain
        # can be re-derived deterministically from stored inputs)
        stored_checks = dict(checks)
        stored_checks["_action"] = action
        stored_checks["_grade"] = grade
        direction = self._direction_from_action(action)
        signal_id = self.record_signal(
            signal_ts=now, symbol="NIFTY", direction=direction,
            signal_type="precision_signal",
            score=signal_data.get("confluence_score"),
            confidence=signal_data.get("confidence"),
            market_state=signal_data.get("market_state"),
            observation_id=observation_id, signal_version=signal_version,
            parameter_version=None, feature_version=feature_version,
            checks_json=stored_checks,
            provenance={"status": truth.REAL, "source": "precision_signals",
                        "evaluation_method": "6_layer_confluence",
                        "signal_version": signal_version},
        )

        # Stage 1 - feature snapshot (minimum reproducible feature state)
        snapshot_id = self.record_feature_snapshot(
            signal_id=signal_id, feature_ts=now, feature_version=feature_version,
            freshness_seconds=freshness_seconds,
            features_json={
                "regime": signal_data.get("market_state"),
                "nifty_spot": spot,
                "vix": signal_data.get("vix"),
                "vix_zone": signal_data.get("vix_zone"),
                "confluence_checks": checks,
                "freshness_status": freshness_status,
                "feature_version": feature_version,
            },
            provenance={"status": truth.REAL, "source": "precision_signals",
                        "data_freshness": f"{freshness_seconds}s" if freshness_seconds is not None else None},
        )

        # Stage 3 - prediction (only when a directional claim exists)
        prediction_id = None
        if direction:
            horizon_end = self._next_trading_date(_parse_ts(now))
            prediction_id = self.record_prediction(
                signal_id=signal_id, predicted_direction=direction,
                base_price=spot,
                horizon="next_trading_session_close",
                horizon_end_ts=horizon_end.strftime("%Y-%m-%d") if horizon_end else None,
                confidence=None, calibration="UNKNOWN",
                model_type="precision_signal_rule", model_version=signal_version,
                prediction_ts=now,
                provenance={"status": truth.REAL, "source": "precision_signals",
                            "calibration": "UNKNOWN"},
            )

        # Stage 5 - decision
        decision_type, reason = self._derive_decision(action, grade, capital_guard_audit)
        if decision_override:
            decision_type = decision_override
        risk_state = None
        cg_state = None
        if capital_guard_audit:
            cg_state = capital_guard_audit.get("safety_status")
            risk_state = {
                "safety_status": cg_state,
                "kill_switch_active": bool(capital_guard_audit.get("kill_switch", {}).get("is_kill_switch_active")),
                "capital_preservation_score": capital_guard_audit.get("capital_preservation_score"),
            }
        decision_id = self.record_decision(
            decision_type=decision_type, signal_id=signal_id,
            prediction_id=prediction_id, reason=reason,
            risk_state=risk_state, capital_guard_state=cg_state,
            execution_mode="PAPER",
            decision_ts=now,
            provenance={"status": truth.REAL, "source": "decision_rule",
                        "decision_rule_version": "v1"},
        )

        return {
            "observation_id": observation_id,
            "snapshot_id": snapshot_id,
            "signal_id": signal_id,
            "prediction_id": prediction_id,
            "decision_id": decision_id,
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _next_trading_date(self, signal_dt):
        """First trading date strictly after the signal date (from cache)."""
        if signal_dt is None:
            return None
        try:
            import pandas as pd
            if not os.path.exists(NIFTY_HISTORY_CSV):
                return None
            df = pd.read_csv(NIFTY_HISTORY_CSV)
            dates = [str(d).strip() for d in df.iloc[:, 0]]
            signal_date = signal_dt.strftime("%Y-%m-%d")
            for d in dates:
                if d > signal_date:
                    return _parse_ts(d)
        except Exception:
            return None
        return None

    def _next_close_after(self, signal_date):
        """(date_str, close) of the first session strictly after signal_date."""
        try:
            import pandas as pd
            if not os.path.exists(NIFTY_HISTORY_CSV):
                return None
            df = pd.read_csv(NIFTY_HISTORY_CSV)
            df.columns = [str(c).strip().lower() for c in df.columns]
            dcol = [c for c in df.columns if "date" in c]
            ccol = [c for c in df.columns if c == "close"]
            if not dcol or not ccol:
                return None
            for _, row in df.iterrows():
                d = str(row[dcol[0]]).strip()
                if d > signal_date:
                    try:
                        return d, float(row[ccol[0]])
                    except (TypeError, ValueError):
                        return d, None
        except Exception:
            return None
        return None

    # ------------------------------------------------------------------
    # Stage 10 - EVALUATION (Outcome Engine observer)
    # ------------------------------------------------------------------
    def evaluate_pending_predictions(self):
        """Evaluate predictions whose horizon (next session close) has data.

        Only closes strictly AFTER the signal session are read - no future
        data can leak into a decision record. Returns number evaluated.
        """
        cur = self._cur()
        done = 0
        rows = cur.execute(
            "SELECT p.prediction_id, p.signal_id, p.predicted_direction, p.base_price,"
            " p.prediction_ts FROM predictions p WHERE NOT EXISTS ("
            "  SELECT 1 FROM evaluations e WHERE e.prediction_id = p.prediction_id)"
        ).fetchall()
        for prediction_id, signal_id, direction, base_price, prediction_ts in rows:
            signal = self.get_signal(signal_id)
            signal_dt = _parse_ts(signal["signal_ts"]) if signal else None
            if signal_dt is None:
                continue
            nxt = self._next_close_after(signal_dt.strftime("%Y-%m-%d"))
            if nxt is None:
                continue  # horizon still in the future -> stays PENDING
            _, close = nxt
            if close is None:
                cur.execute(
                    "INSERT INTO evaluations (prediction_id, eval_ts, prediction_correct,"
                    " execution_quality, method, status, actual_move, base_price, provenance_json)"
                    " VALUES (?, ?, 'UNKNOWN', 'UNKNOWN', 'next_trading_session_close', 'SKIPPED', NULL, ?, ?)",
                    (prediction_id, now_str(), base_price,
                     truth.serialize_provenance({"status": truth.UNKNOWN,
                                                 "reason": "close missing for horizon"})),
                )
                done += 1
                continue
            if base_price is None:
                correct = "UNKNOWN"
                status = "SKIPPED"
                actual_move = None
            else:
                actual_move = close - float(base_price)
                if actual_move == 0:
                    correct = "NEUTRAL"
                elif (actual_move > 0) == (direction == "UP"):
                    correct = "CORRECT"
                else:
                    correct = "INCORRECT"
                status = "DONE"
            cur.execute(
                "INSERT INTO evaluations (prediction_id, eval_ts, prediction_correct,"
                " execution_quality, method, status, actual_move, base_price, provenance_json)"
                " VALUES (?, ?, ?, 'UNKNOWN', 'next_trading_session_close', ?, ?, ?, ?)",
                (prediction_id, now_str(), correct, status, actual_move, base_price,
                 truth.serialize_provenance({"status": truth.REAL, "source": "nifty_history"})),
            )
            done += 1
        self._conn.commit()
        return done

    def evaluate_execution_quality(self, outcome_id):
        """Execution quality for an outcome (paper executions: UNKNOWN)."""
        cur = self._cur()
        existing = cur.execute(
            "SELECT evaluation_id FROM evaluations WHERE outcome_id=? AND execution_quality IS NOT NULL",
            (outcome_id,),
        ).fetchone()
        if existing:
            return existing[0]
        cur.execute(
            "INSERT INTO evaluations (outcome_id, eval_ts, prediction_correct,"
            " execution_quality, method, status, provenance_json)"
            " VALUES (?, ?, NULL, 'UNKNOWN', 'paper_execution', 'DONE', ?)",
            (outcome_id, now_str(),
             truth.serialize_provenance({"status": truth.SIMULATED,
                                         "execution_mode": "PAPER"})),
        )
        self._conn.commit()
        return cur.lastrowid

    # ------------------------------------------------------------------
    # readers
    # ------------------------------------------------------------------
    def get_signal(self, signal_id):
        cur = self._cur()
        row = cur.execute("SELECT * FROM signals WHERE signal_id=?", (signal_id,)).fetchone()
        return self._row_to_dict(cur, "signals", row)

    def get_snapshot(self, signal_id):
        cur = self._cur()
        row = cur.execute("SELECT * FROM feature_snapshots WHERE signal_id=?",
                          (signal_id,)).fetchone()
        return self._row_to_dict(cur, "feature_snapshots", row)

    def get_decision(self, decision_id):
        cur = self._cur()
        row = cur.execute("SELECT * FROM decisions WHERE decision_id=?",
                          (decision_id,)).fetchone()
        return self._row_to_dict(cur, "decisions", row)

    def get_prediction(self, prediction_id):
        cur = self._cur()
        row = cur.execute("SELECT * FROM predictions WHERE prediction_id=?",
                          (prediction_id,)).fetchone()
        return self._row_to_dict(cur, "predictions", row)

    def get_position(self, position_id):
        cur = self._cur()
        row = cur.execute("SELECT * FROM positions WHERE position_id=?",
                          (position_id,)).fetchone()
        return self._row_to_dict(cur, "positions", row)

    def position_id_by_ref(self, position_ref):
        """Resolve a paper/broker position reference (position_ref column) to the
        ledger's numeric position_id, or None if unknown."""
        cur = self._cur()
        row = cur.execute("SELECT position_id FROM positions WHERE position_ref=?",
                          (position_ref,)).fetchone()
        return row[0] if row else None

    def get_outcome(self, position_id):
        cur = self._cur()
        row = cur.execute("SELECT * FROM outcomes WHERE position_id=?",
                          (position_id,)).fetchone()
        return self._row_to_dict(cur, "outcomes", row)

    def get_execution(self, execution_id):
        cur = self._cur()
        row = cur.execute("SELECT * FROM executions WHERE execution_id=?",
                          (execution_id,)).fetchone()
        return self._row_to_dict(cur, "executions", row)

    def get_evaluation(self, prediction_id=None, outcome_id=None):
        cur = self._cur()
        if prediction_id is not None:
            row = cur.execute("SELECT * FROM evaluations WHERE prediction_id=?",
                              (prediction_id,)).fetchone()
        elif outcome_id is not None:
            row = cur.execute("SELECT * FROM evaluations WHERE outcome_id=?",
                              (outcome_id,)).fetchone()
        else:
            return None
        return self._row_to_dict(cur, "evaluations", row)

    @staticmethod
    def _row_to_dict(cur, table, row):
        if row is None:
            return None
        cols = [c[1] for c in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        out = dict(zip(cols, row))
        out["provenance"] = truth.deserialize_provenance(out.pop("provenance_json", None))
        for key in ("checks_json", "risk_state", "features_json"):
            if key in out and isinstance(out.get(key), str):
                try:
                    out[key] = json.loads(out[key])
                except (ValueError, TypeError):
                    pass
        return out

    def trace_chain(self, signal_id):
        """Full canonical trace for a signal (all downstream records)."""
        signal = self.get_signal(signal_id)
        if signal is None:
            return None
        observation = None
        snapshot = self.get_snapshot(signal_id)
        prediction = None
        decision = None
        execution = None
        position = None
        outcome = None
        evaluation = None

        if signal.get("observation_id"):
            cur = self._cur()
            row = cur.execute("SELECT * FROM market_observations WHERE observation_id=?",
                              (signal["observation_id"],)).fetchone()
            observation = self._row_to_dict(cur, "market_observations", row)

        cur = self._cur()
        pred_rows = cur.execute("SELECT prediction_id FROM predictions WHERE signal_id=?",
                                (signal_id,)).fetchall()
        if pred_rows:
            prediction = self.get_prediction(pred_rows[0][0])
        dec_rows = cur.execute("SELECT decision_id FROM decisions WHERE signal_id=?",
                               (signal_id,)).fetchall()
        if dec_rows:
            decision = self.get_decision(dec_rows[0][0])
        if decision:
            exec_rows = cur.execute("SELECT execution_id FROM executions WHERE decision_id=?",
                                    (decision["decision_id"],)).fetchall()
            if exec_rows:
                execution = self.get_execution(exec_rows[0][0])
        if execution:
            pos_rows = cur.execute("SELECT position_id FROM positions WHERE entry_execution_id=?",
                                   (execution["execution_id"],)).fetchall()
            if pos_rows:
                position = self.get_position(pos_rows[0][0])
        if position:
            outcome = self.get_outcome(position["position_id"])
        if prediction:
            evaluation = self.get_evaluation(prediction_id=prediction["prediction_id"])

        return {
            "observation": observation,
            "feature_snapshot": snapshot,
            "signal": signal,
            "prediction": prediction,
            "decision": decision,
            "execution": execution,
            "position": position,
            "outcome": outcome,
            "evaluation": evaluation,
        }

    # ------------------------------------------------------------------
    # reproducibility (Phase 20)
    # ------------------------------------------------------------------
    def verify_reproducibility(self, signal_id):
        """Deterministic re-derivation of stored records from stored inputs.

        Returns {checks: {...}, reproducible: bool}. Same stored inputs ->
        same stored decision/outcome/prediction.
        """
        chain = self.trace_chain(signal_id)
        checks = {}
        if chain is None:
            return {"checks": {"chain_exists": False}, "reproducible": False}

        sig = chain["signal"]
        snap = chain["feature_snapshot"]
        dec = chain["decision"]
        pred = chain["prediction"]
        pos = chain["position"]
        outc = chain["outcome"]

        checks["feature_snapshot_exists"] = snap is not None
        checks["observation_linked"] = chain["observation"] is not None

        # prediction direction re-derived from stored signal action
        stored_checks = sig.get("checks_json") or {}
        stored_action = stored_checks.get("_action")
        derived_direction = self._direction_from_action(stored_action) if stored_action else None
        if pred:
            checks["prediction_direction_matches_signal"] = (
                derived_direction == pred["predicted_direction"]
            )
        else:
            checks["no_prediction_for_non_directional"] = derived_direction is None

        # decision re-derived from stored action/grade + stored guard state
        if dec:
            stored_grade = stored_checks.get("_grade")
            guard_state = dec.get("capital_guard_state")
            audit = {"safety_status": guard_state} if guard_state else None
            derived_type, _ = self._derive_decision(stored_action, stored_grade, audit)
            checks["decision_matches_derived_rule"] = derived_type == dec["decision_type"]
            checks["decision_timestamp_after_signal"] = (
                _parse_ts(dec["decision_ts"]) >= _parse_ts(sig["signal_ts"])
            )

        # outcome re-derived from stored entry/exit
        if pos and outc:
            qty = int(pos["quantity"])
            side = str(pos["side"]).upper()
            entry = float(pos["entry_price"])
            exit_p = float(outc["exit_price"])
            gross = (exit_p - entry) * qty if side != "SELL" else (entry - exit_p) * qty
            fees = float(outc["fees"] or 0.0)
            slippage = float(outc["slippage"] or 0.0)
            net = gross - fees - slippage
            checks["outcome_gross_matches"] = round(gross, 2) == round(outc["gross_pnl"], 2)
            checks["outcome_net_matches"] = round(net, 2) == round(outc["net_pnl"], 2)
            cost_floor = fees + max(slippage, 0.0)
            expected_class = "WIN" if gross > cost_floor else ("LOSS" if gross < -cost_floor else "BREAKEVEN")
            checks["outcome_class_matches"] = expected_class == outc["outcome_class"]
            checks["single_outcome"] = True

        reproducible = all(checks.values()) if checks else False
        return {"checks": checks, "reproducible": reproducible}

    # ------------------------------------------------------------------
    # legacy import (Phase 17)
    # ------------------------------------------------------------------
    def import_legacy_paper_positions(self, account_file=None):
        """Import pre-existing paper_account.json positions with LEGACY
        provenance and no fabricated signal/decision linkage.

        Idempotent: positions already imported (by position_ref) are skipped.
        """
        account_file = account_file or os.path.join("data", "paper_account.json")
        if not os.path.exists(account_file):
            return 0
        try:
            with open(account_file) as f:
                account = json.load(f)
        except (ValueError, OSError):
            return 0
        positions = list(account.get("open_positions") or []) + list(account.get("closed_trades") or [])
        imported = 0
        for p in positions:
            pos_ref = p.get("position_id")
            cur = self._cur()
            exists = cur.execute("SELECT position_id FROM positions WHERE position_ref=?",
                                 (pos_ref,)).fetchone()
            if exists:
                continue
            side = p.get("side", "BUY")
            qty = int(p.get("quantity") or p.get("lots", 1) * 75)
            entry = float(p.get("entry_price", 0) or 0)
            ts = p.get("timestamp") or now_str()
            status = p.get("status", "OPEN")
            prov = {"status": truth.LEGACY, "source": "paper_account.json",
                    "execution_mode": "PAPER"}
            exec_id = self.record_execution(
                decision_id=None, symbol=p.get("symbol", "NIFTY"), side=side,
                quantity=qty, requested_price=entry, fill_price=entry,
                execution_ts=ts, execution_mode="PAPER", estimated_fill=True,
                fees=0.0, slippage=0.0, broker_reference=pos_ref,
                strike=p.get("strike"), option_type=p.get("option_type"),
                provenance=prov,
            )
            pos_id = self.record_position(
                entry_execution_id=exec_id, symbol=p.get("symbol", "NIFTY"),
                side=side, quantity=qty, entry_price=entry, entry_timestamp=ts,
                status=status, current_sl=p.get("sl_price"),
                current_tgt=p.get("target_price"), position_ref=pos_ref,
                strike=p.get("strike"), option_type=p.get("option_type"),
                provenance=prov,
            )
            if status == "CLOSED" and p.get("exit_price") is not None:
                exit_ts = p.get("exit_timestamp") or now_str()
                exit_exec_id = self.record_execution(
                    decision_id=None, symbol=p.get("symbol", "NIFTY"),
                    side="SELL" if side.upper() == "BUY" else "BUY",
                    quantity=qty, requested_price=p["exit_price"],
                    fill_price=p["exit_price"], execution_ts=exit_ts,
                    execution_mode="PAPER", estimated_fill=True,
                    broker_reference=f"{pos_ref}_EXIT",
                    strike=p.get("strike"), option_type=p.get("option_type"),
                    provenance={"status": truth.LEGACY, "source": "paper_account.json",
                                "execution_mode": "PAPER"},
                )
                self.close_position(
                    position_id=pos_id, exit_price=p["exit_price"],
                    exit_timestamp=exit_ts, exit_reason="MANUAL",
                    exit_execution_id=exit_exec_id,
                    provenance={"status": truth.LEGACY, "source": "paper_account.json",
                                "execution_mode": "PAPER"},
                )
            imported += 1
        return imported

    # ------------------------------------------------------------------
    # reporting
    # ------------------------------------------------------------------
    def counts(self):
        cur = self._cur()
        out = {}
        for table in ("market_observations", "feature_snapshots", "signals",
                      "predictions", "decisions", "executions", "positions",
                      "outcomes", "evaluations"):
            out[table] = int(cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        return out

    def outcome_summary(self):
        cur = self._cur()
        rows = cur.execute("SELECT outcome_class, COUNT(*), "
                           "COALESCE(SUM(realized_pnl),0) FROM outcomes GROUP BY outcome_class").fetchall()
        summary = {"total": 0, "realized_pnl_total": 0.0, "by_class": {}}
        for cls, cnt, pnl in rows:
            summary["by_class"][cls] = {"count": int(cnt), "realized_pnl": round(float(pnl), 2)}
            summary["total"] += int(cnt)
            summary["realized_pnl_total"] += float(pnl)
        summary["realized_pnl_total"] = round(summary["realized_pnl_total"], 2)
        return summary

    def prediction_summary(self):
        cur = self._cur()
        rows = cur.execute(
            "SELECT prediction_correct, COUNT(*) FROM evaluations WHERE prediction_correct IS NOT NULL"
            " GROUP BY prediction_correct").fetchall()
        total_predictions = int(cur.execute("SELECT COUNT(*) FROM predictions").fetchone()[0])
        evaluated = sum(int(c) for _, c in rows)
        return {
            "total_predictions": total_predictions,
            "evaluated": evaluated,
            "pending": total_predictions - evaluated,
            "by_verdict": {verdict: int(cnt) for verdict, cnt in rows},
        }

    def integrity_check(self):
        """PRAGMA integrity_check + orphan/duplicate checks."""
        cur = self._cur()
        integrity = cur.execute("PRAGMA integrity_check").fetchone()[0]
        issues = []
        if integrity != "ok":
            issues.append(f"PRAGMA integrity_check: {integrity}")
        orphans = cur.execute(
            "SELECT COUNT(*) FROM predictions p LEFT JOIN signals s ON p.signal_id=s.signal_id"
            " WHERE s.signal_id IS NULL").fetchone()[0]
        if orphans:
            issues.append(f"orphan predictions: {orphans}")
        dup_outcomes = cur.execute(
            "SELECT position_id, COUNT(*) c FROM outcomes GROUP BY position_id HAVING c>1").fetchall()
        if dup_outcomes:
            issues.append(f"duplicate outcomes: {dup_outcomes}")
        dup_evals = cur.execute(
            "SELECT prediction_id, COUNT(*) c FROM evaluations WHERE prediction_id IS NOT NULL"
            " GROUP BY prediction_id HAVING c>1").fetchall()
        if dup_evals:
            issues.append(f"duplicate prediction evaluations: {dup_evals}")
        return {"ok": not issues, "integrity": integrity, "issues": issues}

    def ground_truth_report(self):
        return {
            "ground_truth_status": "ACTIVE",
            "database_file": self.db_file,
            "counts": self.counts(),
            "outcome_summary": self.outcome_summary(),
            "prediction_summary": self.prediction_summary(),
            "integrity": self.integrity_check(),
        }


if __name__ == "__main__":
    import json as _json
    gt = GroundTruthDB()
    _ = gt.evaluate_pending_predictions()
    print(_json.dumps(gt.ground_truth_report(), indent=2, default=str))
