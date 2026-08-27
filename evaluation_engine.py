"""Phase 6 — Read-Only Evaluation Engine (measurement only).

Establishes the project's first trustworthy empirical performance baseline
from the Ground Truth ledger. This module NEVER writes to ground_truth.db:
it queries through a read-only SQLite connection (copy fallback when the
WAL/shm files prevent a true RO open) and only computes derived metrics.

Measurement discipline (Phase 6 spec):
  * Every cohort is explicitly labeled (REAL_FRESH / REAL_STALE / SIMULATED /
    ESTIMATED / FALLBACK / LEGACY / UNKNOWN / ...).
  * Every metric is tagged with data sufficiency (ADEQUATE / INSUFFICIENT_SAMPLE).
  * Nothing is invented: missing data stays missing, UNKNOWN stays UNKNOWN.
  * Deterministic: same frozen inputs -> same metrics.
"""
import os
import sys
import json
import copy
import shutil
import tempfile
import sqlite3
import hashlib
import datetime as dt

import truth

sys.path.insert(0, os.path.dirname(__file__))

GT_DB = os.path.join("data", "ground_truth.db")
AUDIT_DB = os.path.join("data", "historical_audit.db")

# ---------------------------------------------------------------------------
# Documented minimum sample thresholds (statistical discipline, not strategy)
# ---------------------------------------------------------------------------
MIN_SIGNAL_SAMPLE = 20
MIN_PREDICTION_SAMPLE = 20
MIN_OUTCOME_SAMPLE = 30
MIN_CONFIDENCE_SAMPLE = 20
MIN_REGIME_SAMPLE = 20

CONFIDENCE_BANDS = [
    (0.00, 0.50), (0.50, 0.60), (0.60, 0.70),
    (0.70, 0.80), (0.80, 0.90), (0.90, 1.00),
]

FAILURE_TAXONOMY = [
    "DATA_ERROR", "FEATURE_ERROR", "SIGNAL_ERROR", "REGIME_ERROR",
    "MODEL_ERROR", "RISK_ERROR", "EXECUTION_ERROR", "TIMING_ERROR",
    "UNKNOWN",
]

_TS_FMT = "%Y-%m-%d %H:%M:%S IST"


def _now():
    return dt.datetime.now().strftime(_TS_FMT)


# ---------------------------------------------------------------------------
# small statistical helpers
# ---------------------------------------------------------------------------
def _mean(xs):
    xs = [float(x) for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def _median(xs):
    xs = sorted(float(x) for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    mid = n // 2
    val = xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2.0
    return round(val, 4)


def _freq(xs):
    out = {}
    for x in xs:
        if x is None:
            continue
        out[x] = out.get(x, 0) + 1
    return out


def sufficiency(n, min_sample):
    """ADEQUATE only at/above the documented minimum sample."""
    return "ADEQUATE" if (n is not None and n >= min_sample) else "INSUFFICIENT_SAMPLE"


def confidence_band(conf):
    """Map a confidence value to its band label. None -> None."""
    if conf is None:
        return None
    conf = max(0.0, min(1.0, float(conf)))
    for lo, hi in CONFIDENCE_BANDS:
        if lo <= conf < hi:
            return f"{lo:.2f}-{hi:.2f}"
    return "0.90-1.00"


# ---------------------------------------------------------------------------
# cohort selection (STEP 5 / layer 1)
# ---------------------------------------------------------------------------
def cohort_label(prov_status, freshness_seconds, budget_seconds=truth.DAILY_CACHE_FRESHNESS_H * 3600):
    """Explicit cohort label from provenance + freshness.

    REAL + fresh -> REAL_FRESH (the only preferred empirical cohort).
    REAL + stale -> REAL_STALE. Everything else keeps its truth status.
    """
    status = str(prov_status or truth.UNKNOWN).upper()
    if status == truth.REAL:
        fs = truth.freshness_status(freshness_seconds, budget_seconds)
        if fs == truth.REAL:
            return "REAL_FRESH"
        if fs == truth.STALE:
            return "REAL_STALE"
        return f"REAL_{fs}"  # MISSING / INVALID freshness
    return status  # SIMULATED / LEGACY / UNKNOWN / ...


def split_cohorts(rows, budget_seconds=truth.DAILY_CACHE_FRESHNESS_H * 3600):
    """Partition rows into explicit cohorts. Rows are dicts with
    'provenance_status' and optionally 'freshness_seconds'."""
    cohorts = {}
    for row in rows:
        label = cohort_label(row.get("provenance_status"), row.get("freshness_seconds"), budget_seconds)
        cohorts.setdefault(label, []).append(row)
    return cohorts


def select_eligible(cohorts, allowed=("REAL_FRESH",)):
    """Eligible rows for empirical claims - default ONLY REAL_FRESH."""
    out = []
    for label in allowed:
        out.extend(cohorts.get(label, []))
    return out


# ---------------------------------------------------------------------------
# pure evaluation layers (each independently testable)
# ---------------------------------------------------------------------------
def signal_metrics(signal_rows, min_sample=MIN_SIGNAL_SAMPLE):
    """STEP 10 - signal level evaluation.

    signal_rows: dicts with direction, prediction_correct, net_pnl, and
    provenance/signal_type fields. Hit rate is computed only for signals
    that actually carry a directional claim (a signal is not a prediction).
    """
    total = len(signal_rows)
    directional = [r for r in signal_rows if r.get("direction")]
    non_directional = total - len(directional)
    with_outcome = [r for r in signal_rows if r.get("net_pnl") is not None]
    correct = [r for r in signal_rows if r.get("prediction_correct") == "CORRECT"]
    incorrect = [r for r in signal_rows if r.get("prediction_correct") == "INCORRECT"]
    neutral = [r for r in signal_rows if r.get("prediction_correct") == "NEUTRAL"]

    pnls = [r.get("net_pnl") for r in with_outcome]
    return {
        "sample_size": total,
        "directional_claims": len(directional),
        "non_directional": non_directional,
        "signals_with_outcome": len(with_outcome),
        "data_sufficiency": sufficiency(total, min_sample),
        "hit_rate": round(len(correct) / len(directional), 4) if directional else None,
        "correct": len(correct),
        "incorrect": len(incorrect),
        "neutral": len(neutral),
        "false_positive_rate": round(len(incorrect) / len(directional), 4) if directional else None,
        "false_negative_rate": None,  # not defined without a labeled positive class
        "average_net_pnl": _mean(pnls),
        "median_net_pnl": _median(pnls),
        "outcome_distribution": _freq([r.get("outcome_class") for r in with_outcome]),
        "by_signal_type": _by_dimension(signal_rows, "signal_type", "prediction_correct", "net_pnl"),
        "by_market_state": _by_dimension(signal_rows, "market_state", "prediction_correct", "net_pnl"),
    }


def prediction_metrics(pred_rows, min_sample=MIN_PREDICTION_SAMPLE):
    """STEP 11 - prediction level evaluation (already-evaluated predictions)."""
    n = len(pred_rows)
    verdicts = _freq([r.get("prediction_correct") for r in pred_rows])
    correct = verdicts.get("CORRECT", 0)
    incorrect = verdicts.get("INCORRECT", 0)
    neutral = verdicts.get("NEUTRAL", 0)
    unknown = verdicts.get("UNKNOWN", 0)
    decided = correct + incorrect + neutral
    pnls = [r.get("net_pnl") for r in pred_rows if r.get("net_pnl") is not None]
    return {
        "sample_size": n,
        "data_sufficiency": sufficiency(n, min_sample),
        "evaluated": decided,
        "correct": correct,
        "incorrect": incorrect,
        "neutral": neutral,
        "unknown": unknown,
        "pending": len([r for r in pred_rows if r.get("evaluation_status") in (None, "PENDING")]),
        "accuracy": round(correct / decided, 4) if decided else None,
        "average_net_pnl": _mean(pnls),
        "median_net_pnl": _median(pnls),
        "by_model": _by_dimension(pred_rows, "model_type", "prediction_correct", "net_pnl"),
        "by_model_version": _by_dimension(pred_rows, "model_version", "prediction_correct", "net_pnl"),
        "by_signal_type": _by_dimension(pred_rows, "signal_type", "prediction_correct", "net_pnl"),
        "by_market_state": _by_dimension(pred_rows, "market_state", "prediction_correct", "net_pnl"),
        "by_confidence_band": _by_dimension(pred_rows, "confidence_band", "prediction_correct", "net_pnl"),
    }


def decision_metrics(decision_rows, min_sample=MIN_SIGNAL_SAMPLE):
    """STEP 12/15 - decision level evaluation (SKIP/ENTER/REJECT split)."""
    n = len(decision_rows)
    types = _freq([r.get("decision_type") for r in decision_rows])
    entered = types.get("ENTER", 0)
    skipped = types.get("SKIP", 0)
    rejected = types.get("REJECT", 0)
    approved = _freq([r.get("capital_guard_state") for r in decision_rows])
    return {
        "sample_size": n,
        "data_sufficiency": sufficiency(n, min_sample),
        "by_type": types,
        "acceptance_rate": round(entered / n, 4) if n else None,
        "skip_rate": round(skipped / n, 4) if n else None,
        "rejection_rate": round(rejected / n, 4) if n else None,
        "capital_guard_states": approved,
    }


def risk_guard_metrics(decision_rows, min_sample=MIN_OUTCOME_SAMPLE):
    """STEP 13 (risk guards) - REJECT analysis with outcome evidence."""
    rejected = [r for r in decision_rows if r.get("decision_type") == "REJECT"]
    out = []
    for r in rejected:
        if r.get("net_pnl") is None:
            cls = "UNCERTAIN"
        elif float(r.get("net_pnl", 0)) > 0:
            cls = "POSSIBLE_MISSED_OPPORTUNITY"
        else:
            cls = "GOOD_REJECTION"
        out.append({
            "decision_id": r.get("decision_id"),
            "rejection_reason": r.get("reason"),
            "capital_guard_state": r.get("capital_guard_state"),
            "classification": cls,
            "posterior_net_pnl": r.get("net_pnl"),
        })
    return {
        "rejected_requests": len(rejected),
        "data_sufficiency": sufficiency(len(rejected), min_sample),
        "classifications": _freq([o["classification"] for o in out]),
        "detail": out,
    }


def execution_metrics(exec_rows, min_sample=MIN_OUTCOME_SAMPLE):
    """STEP 14 - execution quality (fills, slippage, fees)."""
    n = len(exec_rows)
    slippages = [r.get("slippage") for r in exec_rows if r.get("slippage") is not None]
    fees = [r.get("fees") for r in exec_rows if r.get("fees") is not None]
    estimated = len([r for r in exec_rows if r.get("estimated_fill")])
    return {
        "sample_size": n,
        "data_sufficiency": sufficiency(n, min_sample),
        "average_slippage": _mean(slippages),
        "median_slippage": _median(slippages),
        "average_fees": _mean(fees),
        "estimated_fill_count": estimated,
        "estimated_fill_pct": round(estimated / n, 4) if n else None,
        "execution_modes": _freq([r.get("execution_mode") for r in exec_rows]),
    }


def outcome_metrics(outcome_rows, min_sample=MIN_OUTCOME_SAMPLE):
    """STEP 16/18 - realized outcome + MFE/MAE evaluation."""
    n = len(outcome_rows)
    classes = _freq([r.get("outcome_class") for r in outcome_rows])
    wins = classes.get("WIN", 0)
    losses = classes.get("LOSS", 0)
    pnls = [r.get("net_pnl") for r in outcome_rows if r.get("net_pnl") is not None]
    rets = [r.get("return_pct") for r in outcome_rows if r.get("return_pct") is not None]
    durations = [r.get("duration_s") for r in outcome_rows if r.get("duration_s") is not None]
    mfes = [r.get("mfe") for r in outcome_rows if r.get("mfe") is not None]
    maes = [r.get("mae") for r in outcome_rows if r.get("mae") is not None]
    mfe_sources = _freq([r.get("mfe_source") for r in outcome_rows])
    return {
        "sample_size": n,
        "data_sufficiency": sufficiency(n, min_sample),
        "by_class": classes,
        "win_rate": round(wins / n, 4) if n else None,
        "loss_rate": round(losses / n, 4) if n else None,
        "average_net_pnl": _mean(pnls),
        "median_net_pnl": _median(pnls),
        "total_net_pnl": round(sum(pnls), 2) if pnls else None,
        "average_return_pct": _mean(rets),
        "median_return_pct": _median(rets),
        "average_duration_s": _mean(durations),
        "median_duration_s": _median(durations),
        "mfe": {"average": _mean(mfes), "median": _median(mfes), "available": len(mfes)},
        "mae": {"average": _mean(maes), "median": _median(maes), "available": len(maes)},
        "mfe_source_distribution": mfe_sources,
    }


def confidence_calibration(pred_rows, min_sample=MIN_CONFIDENCE_SAMPLE):
    """STEP 12 - group predictions into confidence bands and compare observed
    success. Does NOT recalibrate - only measures.
    """
    bands = {}
    for r in pred_rows:
        band = r.get("confidence_band")
        if band is None:
            continue
        bands.setdefault(band, []).append(r)
    out = {}
    for band in sorted(bands):
        rows = bands[band]
        verdicts = _freq([r.get("prediction_correct") for r in rows])
        decided = verdicts.get("CORRECT", 0) + verdicts.get("INCORRECT", 0)
        pnls = [r.get("net_pnl") for r in rows if r.get("net_pnl") is not None]
        out[band] = {
            "sample_size": len(rows),
            "data_sufficiency": sufficiency(len(rows), min_sample),
            "observed_success_rate": round(verdicts.get("CORRECT", 0) / decided, 4) if decided else None,
            "average_outcome": _mean(pnls),
            "median_outcome": _median(pnls),
            "failure_rate": round(verdicts.get("INCORRECT", 0) / decided, 4) if decided else None,
        }
    return {
        "bands": out,
        "calibration_status": _calibration_status(out, min_sample),
    }


def _calibration_status(bands, min_sample):
    """Classify calibration as CALIBRATED / PARTIALLY_CALIBRATED /
    UNCALIBRATED / INSUFFICIENT_DATA."""
    adequate = [b for b in bands.values() if b["data_sufficiency"] == "ADEQUATE"]
    if not adequate or len(adequate) < 3:
        return "INSUFFICIENT_DATA"
    successes = [b["observed_success_rate"] for b in adequate if b["observed_success_rate"] is not None]
    if len(successes) < 3:
        return "INSUFFICIENT_DATA"
    lo, hi = min(successes), max(successes)
    if hi - lo <= 0.10:
        return "CALIBRATED"
    if hi - lo <= 0.25:
        return "PARTIALLY_CALIBRATED"
    return "UNCALIBRATED"


def regime_metrics(signal_rows, min_sample=MIN_REGIME_SAMPLE):
    """STEP 13 - performance segmented by market_state/regime."""
    by_regime = {}
    for r in signal_rows:
        state = r.get("market_state") or truth.UNKNOWN
        by_regime.setdefault(state, []).append(r)
    out = {}
    for state in sorted(by_regime):
        rows = by_regime[state]
        directional = [r for r in rows if r.get("direction")]
        correct = len([r for r in rows if r.get("prediction_correct") == "CORRECT"])
        entered = len([r for r in rows if r.get("decision_type") == "ENTER"])
        pnls = [r.get("net_pnl") for r in rows if r.get("net_pnl") is not None]
        out[state] = {
            "sample_size": len(rows),
            "data_sufficiency": sufficiency(len(rows), min_sample),
            "signal_success": round(correct / len(directional), 4) if directional else None,
            "decision_acceptance": round(entered / len(rows), 4) if rows else None,
            "net_outcome_total": round(sum(pnls), 2) if pnls else None,
            "average_net_pnl": _mean(pnls),
        }
    return out


def _by_dimension(rows, dim, verdict_key, pnl_key):
    """Group metrics by a dimension (signal_type / market_state / model / band)."""
    groups = {}
    for r in rows:
        key = r.get(dim) or truth.UNKNOWN
        groups.setdefault(key, []).append(r)
    out = {}
    for key in sorted(groups, key=str):
        g = groups[key]
        verdicts = _freq([r.get(verdict_key) for r in g])
        decided = verdicts.get("CORRECT", 0) + verdicts.get("INCORRECT", 0)
        pnls = [r.get(pnl_key) for r in g if r.get(pnl_key) is not None]
        out[str(key)] = {
            "sample_size": len(g),
            "correct": verdicts.get("CORRECT", 0),
            "incorrect": verdicts.get("INCORRECT", 0),
            "success_rate": round(verdicts.get("CORRECT", 0) / decided, 4) if decided else None,
            "average_net_pnl": _mean(pnls),
            "median_net_pnl": _median(pnls),
        }
    return out


# ---------------------------------------------------------------------------
# failure analysis (STEP 17) - classify only with evidence, else UNKNOWN
# ---------------------------------------------------------------------------
def classify_failure(row):
    """Classify a joined signal-chain row into a failure category with evidence.

    Returns (category, evidence) or (None, None) when the row is healthy
    (no trade / successful chain). UNKNOWN is returned only when evidence
    for a category is genuinely absent but something is incomplete.
    """
    if row is None:
        return truth.UNKNOWN, "no record to classify"
    obs = row.get("observation") or row
    snap = row.get("feature_snapshot") or row
    sig = row.get("signal") or row
    dec = row.get("decision") or row
    pred = row.get("prediction") or row
    ev = row.get("evaluation") or row

    valid = obs.get("valid", obs.get("obs_valid"))
    price = obs.get("price", obs.get("obs_price"))
    if valid == 0 or price is None:
        ref = obs.get("observation_id") or obs.get("obs_id") or sig.get("signal_id")
        return "DATA_ERROR", f"observation {ref} invalid or missing price"
    if snap.get("snapshot_id") is None:
        return "FEATURE_ERROR", f"signal {sig.get('signal_id')} has no feature snapshot"
    if dec and dec.get("decision_type") == "REJECT":
        return "RISK_ERROR", f"rejected by capital guard ({dec.get('capital_guard_state')}): {dec.get('reason') or dec.get('dec_reason')}"
    if pred and ev and ev.get("prediction_correct") == "INCORRECT":
        return "MODEL_ERROR", f"prediction {pred.get('prediction_id') or pred.get('pred_id')} direction wrong (moved {ev.get('actual_move')})"
    if dec and sig and _parse_ts(dec.get("decision_ts")) and _parse_ts(sig.get("signal_ts")) \
            and _parse_ts(dec["decision_ts"]) < _parse_ts(sig["signal_ts"]):
        return "TIMING_ERROR", "decision timestamp precedes signal timestamp"
    if snap and sig and snap.get("feature_ts") and sig.get("signal_ts") \
            and _parse_ts(snap["feature_ts"]) and _parse_ts(sig["signal_ts"]) \
            and _parse_ts(snap["feature_ts"]) > _parse_ts(sig["signal_ts"]):
        return "FEATURE_ERROR", "feature snapshot timestamp after signal timestamp"
    if sig.get("signal_ts") and not sig.get("direction") and dec and dec.get("decision_type") == "ENTER":
        return "SIGNAL_ERROR", "ENTER decision without a directional claim"
    if sig.get("direction") and sig.get("market_state") in (None, truth.UNKNOWN):
        return "REGIME_ERROR", "directional signal without a market_state"
    return None, None


def failure_summary(chain_rows):
    """Aggregate classifications across chains."""
    classified = []
    for row in chain_rows:
        cat, ev = classify_failure(row)
        if cat is None:
            continue
        classified.append({"category": cat, "evidence": ev})
    counts = _freq([c["category"] for c in classified])
    return {
        "classified_failures": len(classified),
        "healthy_or_no_trade": len(chain_rows) - len(classified),
        "by_category": counts,
        "most_common": max(counts, key=counts.get) if counts else None,
        "detail": classified,
    }


def _parse_ts(ts):
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


# ---------------------------------------------------------------------------
# leakage verification (STEP 23) - read-only invariant checks
# ---------------------------------------------------------------------------
def verify_leakage(chain_rows):
    """Verify no future data leaked into decision-time records.

    Checks: feature_ts <= signal_ts <= decision_ts; evaluation only exists
    after the prediction horizon; prediction base_price matches the
    observation price at signal time.
    """
    issues = []
    for row in chain_rows:
        sig = row.get("signal") or row
        snap = row.get("feature_snapshot") or row
        dec = row.get("decision") or row
        pred = row.get("prediction") or row
        ev = row.get("evaluation") or row
        obs = row.get("observation") or row

        sig_dt = _parse_ts(sig.get("signal_ts"))
        feat_dt = _parse_ts(snap.get("feature_ts"))
        dec_dt = _parse_ts(dec.get("decision_ts"))
        if sig_dt and feat_dt and feat_dt > sig_dt:
            issues.append(f"signal {sig.get('signal_id')}: feature_ts after signal_ts")
        if sig_dt and dec_dt and dec_dt < sig_dt:
            issues.append(f"signal {sig.get('signal_id')}: decision_ts before signal_ts")

        if pred and ev and ev.get("eval_ts"):
            ev_dt = _parse_ts(ev["eval_ts"])
            hz = _parse_ts(pred.get("horizon_end_ts"))
            if hz and ev_dt and ev_dt.date() < hz.date():
                issues.append(f"prediction {pred.get('prediction_id') or pred.get('pred_id')}: evaluated before horizon end")
        obs_price = obs.get("price") if obs else None
        if obs_price is None:
            obs_price = row.get("obs_price")
        if pred and pred.get("base_price") is not None and obs_price is not None:
            if abs(float(pred["base_price"]) - float(obs_price)) > 1e-6:
                issues.append(f"prediction {pred.get('prediction_id') or pred.get('pred_id')}: base_price != observation price")
    return {"leakage_issues": len(issues), "issues": issues, "clean": not issues}


# ---------------------------------------------------------------------------
# chain health monitor (Phase 6.5) - read-only invariant checks across the
# full signal->...->evaluation chain. Detects breaks BEFORE they corrupt
# future evaluation. Never repairs anything.
# ---------------------------------------------------------------------------
def _prov_status(raw):
    return truth.deserialize_provenance(raw).get("status", truth.UNKNOWN)


def _add_finding(findings, ftype, record_id, evidence, severity="WARNING"):
    findings.append({"type": ftype, "record_id": record_id,
                     "evidence": evidence, "severity": severity})


def chain_health_report(engine, include_generated_at=True):
    """Read-only chain health over the ground truth ledger.

    Detects orphans, missing/duplicate outcomes, missing feature snapshots,
    provenance loss, timestamp inconsistencies and invalid state transitions.
    Every finding carries record id + evidence + severity
    (INFO / WARNING / ERROR / CRITICAL). Historical records are never
    modified. Output is deterministic for a frozen DB (drop `generated_at`
    before fingerprinting).
    """
    findings = []
    ro = engine._conn_ro
    tables = engine._tables()

    def q(sql, params=()):
        return ro.execute(sql, params).fetchall()

    # ---- ORPHAN_SIGNAL: a signal with no decision at all ----
    if {"signals", "decisions"} <= tables:
        for (sid,) in q("SELECT s.signal_id FROM signals s WHERE NOT EXISTS"
                        " (SELECT 1 FROM decisions d WHERE d.signal_id=s.signal_id)"):
            _add_finding(findings, "ORPHAN_SIGNAL", f"signal:{sid}",
                         "signal has no decision record", "WARNING")

    # ---- ORPHAN_PREDICTION: prediction whose signal is missing ----
    if {"predictions", "signals"} <= tables:
        for (pid, sid) in q("SELECT p.prediction_id, p.signal_id FROM predictions p"
                            " WHERE NOT EXISTS (SELECT 1 FROM signals s WHERE s.signal_id=p.signal_id)"):
            _add_finding(findings, "ORPHAN_PREDICTION", f"prediction:{pid}",
                         f"prediction references missing signal:{sid}", "WARNING")

    # ---- ORPHAN_DECISION: decision whose signal is missing ----
    if {"decisions", "signals"} <= tables:
        for (did, sid) in q("SELECT d.decision_id, d.signal_id FROM decisions d"
                            " WHERE NOT EXISTS (SELECT 1 FROM signals s WHERE s.signal_id=d.signal_id)"):
            _add_finding(findings, "ORPHAN_DECISION", f"decision:{did}",
                         f"decision references missing signal:{sid}", "WARNING")

    # ---- ORPHAN_EXECUTION: execution with no decision ----
    if "executions" in tables:
        for row in q("SELECT e.execution_id, e.decision_id, e.provenance_json FROM executions e"
                     " WHERE e.decision_id IS NULL"):
            sev = "INFO" if _prov_status(row[2]) == truth.LEGACY else "WARNING"
            _add_finding(findings, "ORPHAN_EXECUTION", f"execution:{row[0]}",
                         f"execution has no decision (decision_id={row[1]})", sev)

    # ---- ORPHAN_POSITION: position whose entry execution has no decision ----
    if {"positions", "executions"} <= tables:
        for row in q("SELECT pos.position_id, pos.provenance_json FROM positions pos"
                     " LEFT JOIN executions e ON e.execution_id=pos.entry_execution_id"
                     " WHERE e.execution_id IS NULL OR e.decision_id IS NULL"):
            sev = "INFO" if _prov_status(row[1]) == truth.LEGACY else "WARNING"
            _add_finding(findings, "ORPHAN_POSITION", f"position:{row[0]}",
                         "position entry execution has no decision link", sev)

    # ---- MISSING_FEATURE_SNAPSHOT: signal with no feature snapshot ----
    if {"signals", "feature_snapshots"} <= tables:
        for (sid,) in q("SELECT s.signal_id FROM signals s WHERE NOT EXISTS"
                        " (SELECT 1 FROM feature_snapshots fs WHERE fs.signal_id=s.signal_id)"):
            _add_finding(findings, "MISSING_FEATURE_SNAPSHOT", f"signal:{sid}",
                         "signal has no feature snapshot", "WARNING")

    # ---- MISSING_OUTCOME: closed position without an outcome ----
    if {"positions", "outcomes"} <= tables:
        for (pid,) in q("SELECT pos.position_id FROM positions pos WHERE pos.status='CLOSED'"
                        " AND NOT EXISTS (SELECT 1 FROM outcomes o WHERE o.position_id=pos.position_id)"):
            _add_finding(findings, "MISSING_OUTCOME", f"position:{pid}",
                         "closed position has no outcome record", "ERROR")

    # ---- DUPLICATE_OUTCOME: more than one outcome per position ----
    if "outcomes" in tables:
        for (posid, n) in q("SELECT position_id, COUNT(*) FROM outcomes GROUP BY position_id"
                            " HAVING COUNT(*) > 1"):
            _add_finding(findings, "DUPLICATE_OUTCOME", f"position:{posid}",
                         f"{n} outcome rows for one position", "CRITICAL")

    # ---- PROVENANCE_LOSS: NULL/corrupt provenance (non-legacy rows) ----
    for t in ("market_observations", "feature_snapshots", "signals", "predictions",
              "decisions", "executions", "positions", "outcomes", "evaluations"):
        if t not in tables:
            continue
        pk = {"positions": "position_id", "outcomes": "outcome_id",
              "evaluations": "evaluation_id"}.get(t, f"{t[:-1]}_id")
        cols = {r[1] for r in q(f"PRAGMA table_info({t})")}
        if pk not in cols or "provenance_json" not in cols:
            continue
        for row in q(f"SELECT {pk}, provenance_json FROM {t} WHERE provenance_json IS NULL"):
            _add_finding(findings, "PROVENANCE_LOSS", f"{t}:{row[0]}",
                         f"{t} row has no provenance", "INFO")

    # ---- TIMESTAMP_INCONSISTENCY: feature_ts after signal_ts / decision before signal / exit before entry ----
    if {"feature_snapshots", "signals"} <= tables:
        for (fsid, sid) in q("SELECT fs.snapshot_id, fs.signal_id FROM feature_snapshots fs"
                             " JOIN signals s ON s.signal_id=fs.signal_id"
                             " WHERE fs.feature_ts IS NOT NULL AND s.signal_ts IS NOT NULL"
                             " AND fs.feature_ts > s.signal_ts"):
            _add_finding(findings, "TIMESTAMP_INCONSISTENCY", f"snapshot:{fsid}",
                         f"feature_ts after signal_ts for signal:{sid}", "ERROR")
    if {"decisions", "signals"} <= tables:
        for (did, sid) in q("SELECT d.decision_id, d.signal_id FROM decisions d"
                            " JOIN signals s ON s.signal_id=d.signal_id"
                            " WHERE d.decision_ts IS NOT NULL AND s.signal_ts IS NOT NULL"
                            " AND d.decision_ts < s.signal_ts"):
            _add_finding(findings, "TIMESTAMP_INCONSISTENCY", f"decision:{did}",
                         f"decision_ts before signal_ts for signal:{sid}", "ERROR")
    if {"positions"} <= tables:
        for (pid,) in q("SELECT position_id FROM positions WHERE exit_timestamp IS NOT NULL"
                        " AND entry_timestamp IS NOT NULL AND exit_timestamp < entry_timestamp"):
            _add_finding(findings, "TIMESTAMP_INCONSISTENCY", f"position:{pid}",
                         "exit_timestamp before entry_timestamp", "CRITICAL")

    # ---- INVALID_STATE_TRANSITION: impossible quantity / no entry execution / duplicate entry ----
    if "positions" in tables:
        for row in q("SELECT position_id, quantity, status FROM positions"
                     " WHERE quantity IS NULL OR quantity <= 0"):
            _add_finding(findings, "INVALID_STATE_TRANSITION", f"position:{row[0]}",
                         f"impossible quantity ({row[1]}, status={row[2]})", "ERROR")
        for (pid,) in q("SELECT position_id FROM positions WHERE entry_execution_id IS NULL"):
            _add_finding(findings, "INVALID_STATE_TRANSITION", f"position:{pid}",
                         "position without an entry execution", "ERROR")
        for (pid,) in q("SELECT position_id FROM positions WHERE entry_execution_id IN"
                        " (SELECT entry_execution_id FROM positions"
                        "  WHERE entry_execution_id IS NOT NULL"
                        "  GROUP BY entry_execution_id HAVING COUNT(*)>1)"):
            _add_finding(findings, "INVALID_STATE_TRANSITION", f"position:{pid}",
                         "entry execution reused by multiple positions", "CRITICAL")

    by_severity = {}
    for f in findings:
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1
    summary = {
        "total_findings": len(findings),
        "by_severity": by_severity,
        "health": "HEALTHY" if not (by_severity.get("ERROR") or by_severity.get("CRITICAL")) else "UNHEALTHY",
    }
    out = {"findings": findings, "summary": summary}
    if include_generated_at:
        out["generated_at"] = _now()
    return out


def observation_state(rep):
    """Classify the live observation state from a report dict.

    NO_DIRECTIONAL_TRADES_YET - zero directional signals / predictions / trades
    (a healthy state when the engine legitimately emits STAY_OUT / SKIP).
    PENDING_OUTCOMES - directional trades exist but no outcome is realized.
    ACCUMULATING_OUTCOMES - realized outcomes exist.
    """
    counts = rep.get("counts", {})
    predictions = counts.get("predictions", 0)
    outcomes = counts.get("outcomes", 0)
    executions = counts.get("executions", 0)
    if predictions == 0 and executions == 0 and outcomes == 0:
        return "NO_DIRECTIONAL_TRADES_YET"
    if outcomes == 0:
        return "PENDING_OUTCOMES"
    return "ACCUMULATING_OUTCOMES"


def live_observation_report(engine, include_generated_at=True):
    """Read-only Phase 6.5 live-observation snapshot.

    Combines the evaluation report, the chain-health findings and the
    observation-state classification into one deterministic health view.
    """
    rep = engine.evaluation_report()
    health = chain_health_report(engine, include_generated_at=include_generated_at)
    findings = health["findings"]
    sev = health["summary"]["by_severity"]
    obs = {
        "observation_window": rep.get("observation_window"),
        "counts": rep["counts"],
        "directional_signals": rep["signal_evaluation"]["directional_claims"],
        "stay_out_skip": rep["decision_evaluation"]["skip_rate"],
        "open_positions": rep["open_positions"],
        "closed_positions": rep["closed_positions"],
        "pending_predictions": rep["pending_predictions"],
        "unresolved_outcomes": rep["unresolved_outcomes"],
        "cohort_sizes": rep["cohort_sizes"],
        "leakage_clean": rep["leakage_verification"]["clean"],
        "chain_findings": len(findings),
        "chain_by_severity": sev,
        "chain_error_critical": (sev.get("ERROR", 0) + sev.get("CRITICAL", 0)),
        "provenance_findings": len([f for f in findings if f["type"] == "PROVENANCE_LOSS"]),
        "state": observation_state(rep),
        "health": health["summary"]["health"],
    }
    if include_generated_at:
        obs["generated_at"] = _now()
    return obs


class EvaluationEngine:
    """Read-only evaluation facade over ground_truth.db (+ legacy audit db).

    Guarantees:
      * never executes INSERT/UPDATE/DELETE
      * opens the truth DB read-only (mode=ro), copying to a temp file as a
        fallback so production history can never be modified
      * every metric is deterministic and tagged with data sufficiency
    """

    def __init__(self, gt_db=GT_DB, audit_db=AUDIT_DB, budget_seconds=None):
        self.gt_db = gt_db
        self.audit_db = audit_db
        self.budget_seconds = budget_seconds or truth.DAILY_CACHE_FRESHNESS_H * 3600
        self._conn = None
        self._conn_ro = self._connect_ro(gt_db)

    def _connect_ro(self, db_file):
        if not os.path.exists(db_file):
            raise FileNotFoundError(f"ground truth db not found: {db_file}")
        try:
            conn = sqlite3.connect(f"file:{os.path.abspath(db_file)}?mode=ro", uri=True, timeout=5)
            conn.execute("PRAGMA query_only=ON")
            return conn
        except sqlite3.OperationalError:
            # WAL/shm unavailable for a pure-RO open: read a frozen copy.
            tmp = tempfile.mkdtemp(prefix="phase6_ro_")
            copy_path = os.path.join(tmp, "ground_truth.db")
            shutil.copy2(db_file, copy_path)
            conn = sqlite3.connect(copy_path, timeout=5)
            conn.execute("PRAGMA query_only=ON")
            self._copy_dir = tmp
            return conn

    def _tables(self):
        rows = self._conn_ro.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {r[0] for r in rows}

    def _q(self, sql, params=()):
        return self._conn_ro.execute(sql, params).fetchall()

    def _qdict(self, sql, params=()):
        """Rows as dicts from the exact SQL executed - no col/row mismatch."""
        cur = self._conn_ro.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def _row_dict(self, table, cols, row):
        return dict(zip(cols, row))

    # ------------------------------------------------------------------
    # row loaders (joined, provenance parsed)
    # ------------------------------------------------------------------
    def _load_signal_rows(self):
        tables = self._tables()
        if "signals" not in tables:
            return []
        cols = [c[1] for c in self._q(f"PRAGMA table_info(signals)")]
        rows = self._q("SELECT * FROM signals")
        out = []
        for r in rows:
            d = self._row_dict("signals", cols, r)
            out.append(d)
        return out

    def _load_snapshot_freshness(self):
        tables = self._tables()
        if "feature_snapshots" not in tables:
            return {}
        rows = self._q("SELECT signal_id, freshness_seconds, feature_ts FROM feature_snapshots")
        return {r[0]: {"freshness_seconds": r[1], "feature_ts": r[2]} for r in rows}

    def _load_prediction_rows(self):
        tables = self._tables()
        if "predictions" not in tables:
            return []
        rows = self._qdict(
            "SELECT p.*, s.signal_type, s.market_state, s.direction AS signal_direction,"
            " s.provenance_json AS signal_provenance_json,"
            " ev.prediction_correct, ev.status AS evaluation_status, ev.eval_ts, ev.actual_move,"
            " o.net_pnl, o.outcome_class, o.mfe, o.mae"
            " FROM predictions p"
            " LEFT JOIN signals s ON s.signal_id = p.signal_id"
            " LEFT JOIN evaluations ev ON ev.prediction_id = p.prediction_id"
            " LEFT JOIN decisions d ON d.prediction_id = p.prediction_id"
            " LEFT JOIN executions e ON e.decision_id = d.decision_id"
            " LEFT JOIN positions pos ON pos.entry_execution_id = e.execution_id"
            " LEFT JOIN outcomes o ON o.position_id = pos.position_id")
        for d in rows:
            d["confidence_band"] = confidence_band(d.get("confidence"))
        return rows

    def _load_decision_rows(self):
        tables = self._tables()
        if "decisions" not in tables:
            return []
        rows = self._qdict(
            "SELECT d.*, s.signal_type, s.market_state,"
            " o.net_pnl, o.outcome_class"
            " FROM decisions d"
            " LEFT JOIN signals s ON s.signal_id = d.signal_id"
            " LEFT JOIN executions e ON e.decision_id = d.decision_id"
            " LEFT JOIN positions pos ON pos.entry_execution_id = e.execution_id"
            " LEFT JOIN outcomes o ON o.position_id = pos.position_id")
        for d in rows:
            if d.get("risk_state"):
                try:
                    d["risk_state"] = json.loads(d["risk_state"])
                except (ValueError, TypeError):
                    pass
        return rows

    def _load_execution_rows(self):
        tables = self._tables()
        if "executions" not in tables:
            return []
        return self._qdict("SELECT * FROM executions")

    def _load_outcome_rows(self):
        tables = self._tables()
        if "outcomes" not in tables:
            return []
        return self._qdict(
            "SELECT o.*, pos.symbol, pos.side, pos.strike, pos.option_type,"
            " pos.provenance_json AS position_provenance_json"
            " FROM outcomes o LEFT JOIN positions pos ON pos.position_id = o.position_id")

    def _load_chain_rows(self):
        """Joined signal->...->outcome rows for failure/leakage analysis."""
        tables = self._tables()
        if "signals" not in tables:
            return []
        return self._qdict(
            "SELECT s.*, snap.snapshot_id, snap.freshness_seconds, snap.feature_ts,"
            " o.observation_id AS obs_id, o.price AS obs_price, o.valid AS obs_valid,"
            " d.decision_id AS dec_id, d.decision_type, d.capital_guard_state, d.reason AS dec_reason, d.decision_ts,"
            " p.prediction_id AS pred_id, p.predicted_direction, p.base_price, p.horizon_end_ts, p.confidence,"
            " ev.prediction_correct, ev.actual_move, ev.eval_ts,"
            " oc.net_pnl, oc.outcome_class"
            " FROM signals s"
            " LEFT JOIN feature_snapshots snap ON snap.signal_id = s.signal_id"
            " LEFT JOIN market_observations o ON o.observation_id = s.observation_id"
            " LEFT JOIN decisions d ON d.signal_id = s.signal_id"
            " LEFT JOIN predictions p ON p.signal_id = s.signal_id"
            " LEFT JOIN evaluations ev ON ev.prediction_id = p.prediction_id"
            " LEFT JOIN executions e ON e.decision_id = d.decision_id"
            " LEFT JOIN positions pos ON pos.entry_execution_id = e.execution_id"
            " LEFT JOIN outcomes oc ON oc.position_id = pos.position_id")

    # ------------------------------------------------------------------
    # public read-only report methods
    # ------------------------------------------------------------------
    def counts(self):
        tables = self._tables()
        out = {}
        for t in ("market_observations", "feature_snapshots", "signals",
                  "predictions", "decisions", "evaluations"):
            out[t] = int(self._q(f"SELECT COUNT(*) FROM {t}")[0][0]) if t in tables else 0
        # executions / positions / outcomes only count when they belong to a
        # recorded signal chain - imported legacy ledger rows (decision_id
        # NULL) are tracked in the DB but excluded from evaluation counts.
        if "executions" in tables:
            out["executions"] = int(self._q(
                "SELECT COUNT(*) FROM executions WHERE decision_id IS NOT NULL")[0][0])
        else:
            out["executions"] = 0
        if "positions" in tables and "executions" in tables:
            out["positions"] = int(self._q(
                "SELECT COUNT(*) FROM positions WHERE entry_execution_id IN"
                " (SELECT execution_id FROM executions WHERE decision_id IS NOT NULL)")[0][0])
        else:
            out["positions"] = 0
        if "outcomes" in tables and "positions" in tables and "executions" in tables:
            out["outcomes"] = int(self._q(
                "SELECT COUNT(*) FROM outcomes WHERE position_id IN"
                " (SELECT pos.position_id FROM positions pos WHERE pos.entry_execution_id IN"
                "  (SELECT execution_id FROM executions WHERE decision_id IS NOT NULL))")[0][0])
        else:
            out["outcomes"] = 0
        return out

    def provenance_distribution(self):
        tables = self._tables()
        out = {}
        for t in ("market_observations", "signals", "feature_snapshots",
                  "decisions", "predictions", "executions", "positions",
                  "outcomes", "evaluations"):
            if t not in tables:
                continue
            rows = self._q(f"SELECT provenance_json FROM {t}")
            statuses = {}
            for (prov,) in rows:
                statuses.setdefault(truth.deserialize_provenance(prov).get("status", truth.UNKNOWN), 0)
                statuses[truth.deserialize_provenance(prov).get("status", truth.UNKNOWN)] += 1
            out[t] = statuses
        return out

    def cohorts(self):
        sig_rows = self._load_signal_rows()
        freshness = self._load_snapshot_freshness()
        for r in sig_rows:
            f = freshness.get(r.get("signal_id"), {})
            r["freshness_seconds"] = f.get("freshness_seconds")
            r["feature_ts"] = f.get("feature_ts")
            r["provenance_status"] = truth.deserialize_provenance(r.get("provenance_json")).get("status", truth.UNKNOWN)
        return split_cohorts(sig_rows, self.budget_seconds)

    def evaluation_report(self):
        """Full read-only report with every layer + cohort + baseline."""
        counts = self.counts()
        cohorts = self.cohorts()

        # signals with evaluation linkage for hit-rate
        chain = self._load_chain_rows()
        signal_rows = []
        for c in chain:
            signal_rows.append({
                "signal_id": c.get("signal_id"),
                "signal_type": c.get("signal_type"),
                "market_state": c.get("market_state"),
                "direction": c.get("direction"),
                "provenance_status": truth.deserialize_provenance(c.get("provenance_json")).get("status", truth.UNKNOWN),
                "freshness_seconds": c.get("freshness_seconds"),
                "prediction_correct": c.get("prediction_correct"),
                "net_pnl": c.get("net_pnl"),
                "outcome_class": c.get("outcome_class"),
            })
        pred_rows = self._load_prediction_rows()
        dec_rows = self._load_decision_rows()
        exec_rows = self._load_execution_rows()
        outcome_rows = self._load_outcome_rows()

        leakage = verify_leakage(chain)

        report = {
            "report_version": "phase6-evaluation-v1",
            "generated_at": _now(),
            "observation_window": self._q(
                "SELECT MIN(signal_ts), MAX(signal_ts) FROM signals")[0]
                                  if "signals" in self._tables() else None,
            "source": {"ground_truth_db": self.gt_db,
                       "database_sha256": _file_sha256(self.gt_db)},
            "counts": counts,
            "open_positions": int(self._q("SELECT COUNT(*) FROM positions WHERE status='OPEN'")[0][0])
                              if "positions" in self._tables() else 0,
            "closed_positions": int(self._q("SELECT COUNT(*) FROM positions WHERE status='CLOSED'")[0][0])
                                if "positions" in self._tables() else 0,
            "pending_predictions": len([r for r in pred_rows
                                        if r.get("evaluation_status") in (None, "PENDING")]),
            "unresolved_outcomes": int(self._q("SELECT COUNT(*) FROM positions WHERE status='OPEN' AND position_id NOT IN (SELECT position_id FROM outcomes)")[0][0])
                                   if "positions" in self._tables() and "outcomes" in self._tables() else 0,
            "provenance_distribution": self.provenance_distribution(),
            "cohorts": {label: [r.get("signal_id") for r in rows] for label, rows in cohorts.items()},
            "cohort_sizes": {label: len(rows) for label, rows in cohorts.items()},
            "evaluation_cohort": {
                "preferred": "REAL_FRESH",
                "eligible_count": len(cohorts.get("REAL_FRESH", [])),
                "excluded_legacy": len(cohorts.get("LEGACY", [])),
                "excluded_simulated": len(cohorts.get("SIMULATED", [])),
                "excluded_stale": len(cohorts.get("REAL_STALE", [])),
                "excluded_unknown": len(cohorts.get("UNKNOWN", [])),
                "excluded_other": {k: len(v) for k, v in cohorts.items()
                                   if k not in ("REAL_FRESH", "REAL_STALE", "SIMULATED", "LEGACY", "UNKNOWN")},
            },
            "signal_evaluation": signal_metrics(signal_rows),
            "prediction_evaluation": prediction_metrics(pred_rows),
            "decision_evaluation": decision_metrics(dec_rows),
            "execution_evaluation": execution_metrics(exec_rows),
            "outcome_evaluation": outcome_metrics(outcome_rows),
            "confidence_calibration": confidence_calibration(pred_rows),
            "regime_analysis": regime_metrics(signal_rows),
            "risk_guard_analysis": risk_guard_metrics(dec_rows),
            "failure_analysis": failure_summary(chain),
            "leakage_verification": leakage,
        }
        return report

    def evaluation_summary(self):
        r = self.evaluation_report()
        return {
            "counts": r["counts"],
            "cohort_sizes": r["cohort_sizes"],
            "signal_evaluation": r["signal_evaluation"],
            "prediction_evaluation": r["prediction_evaluation"],
            "outcome_evaluation": r["outcome_evaluation"],
            "leakage_clean": r["leakage_verification"]["clean"],
        }

    def signal_performance(self):
        return self.evaluation_report()["signal_evaluation"]

    def prediction_performance(self):
        return self.evaluation_report()["prediction_evaluation"]

    def failure_summary(self):
        return self.evaluation_report()["failure_analysis"]

    def confidence_calibration(self):
        return self.evaluation_report()["confidence_calibration"]

    def regime_performance(self):
        return self.evaluation_report()["regime_analysis"]

    def baseline_status(self):
        r = self.evaluation_report()
        return {
            "report_version": r["report_version"],
            "generated_at": r["generated_at"],
            "database_sha256": r["source"]["database_sha256"],
            "counts": r["counts"],
            "evaluation_cohort": r["evaluation_cohort"],
        }


def _file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def report_json(engine):
    return json.dumps(engine.evaluation_report(), indent=2, sort_keys=True, default=str)


def _canonical_report(engine):
    """Deterministic report payload for hashing.

    `generated_at` is wall-clock metadata (not an input), so it is excluded
    from the reproducibility fingerprint - otherwise two runs that straddle a
    second boundary hash differently despite identical metrics.
    """
    rep = engine.evaluation_report()
    rep.pop("generated_at", None)
    return json.dumps(rep, indent=2, sort_keys=True, default=str)


def verify_reproducibility(engine):
    """Same frozen inputs -> identical metrics (STEP 23 reproducibility)."""
    a = _canonical_report(engine)
    b = _canonical_report(engine)
    return {"reproducible": a == b, "hash_a": hashlib.sha256(a.encode()).hexdigest(),
            "hash_b": hashlib.sha256(b.encode()).hexdigest()}


if __name__ == "__main__":
    engine = EvaluationEngine()
    rep = engine.evaluation_report()
    print(json.dumps(rep, indent=2, sort_keys=True, default=str))
