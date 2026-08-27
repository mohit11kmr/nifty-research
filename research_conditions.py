"""Phase I.3 - Point-in-time condition DSL (shared by screener + runner).

Entry/exit conditions in a Phase I.3 proposal reference REGISTERED feature
ids only. Ops are strict and deterministic:

    > >= < <= == != between(lo,hi) in(value1,value2,...)

Values are numeric literals (or None checks); percentile/"today" values are
forbidden so conditions stay point-in-time safe (a value derived from the full
window would leak the future). This module is the single evaluator used by the
fast screen and the full research runner - one DSL, one behaviour.
"""
import numpy as np

import research_feature_registry as FREG

OPS = {">", ">=", "<", "<=", "==", "!=", "between", "in"}


def validate_condition(cond):
    """Return a list of schema violations (empty = valid)."""
    errs = []
    if not isinstance(cond, dict):
        return ["condition must be a dict"]
    field = cond.get("field")
    if field not in FREG.registered_ids():
        errs.append(f"field '{field}' not registered")
    op = cond.get("op")
    if op not in OPS:
        errs.append(f"op '{op}' not supported (must be one of {sorted(OPS)})")
    if op in ("between",):
        v = cond.get("value")
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            errs.append("between requires value=[lo, hi]")
    elif op == "in":
        v = cond.get("value")
        if not isinstance(v, (list, tuple)) or not v:
            errs.append("in requires a non-empty value list")
    else:
        v = cond.get("value")
        if isinstance(v, (list, dict)) or (v is None and op not in ("==", "!=")):
            errs.append(f"op '{op}' requires a numeric scalar value")
    return errs


def validate_conditions(conditions):
    errs = []
    if not isinstance(conditions, list) or not conditions:
        return ["entry.conditions must be a non-empty list"]
    for i, c in enumerate(conditions):
        for e in validate_condition(c):
            errs.append(f"conditions[{i}]: {e}")
    return errs


def _cmp(value, op, ref):
    try:
        value = float(value)
        ref = float(ref)
    except (TypeError, ValueError):
        return False
    if op == ">":
        return value > ref
    if op == ">=":
        return value >= ref
    if op == "<":
        return value < ref
    if op == "<=":
        return value <= ref
    if op == "==":
        return abs(value - ref) < 1e-9
    if op == "!=":
        return abs(value - ref) >= 1e-9
    return False


def _in(value, items):
    try:
        return float(value) in [float(x) for x in items]
    except (TypeError, ValueError):
        return False


def evaluate(panel_row, conditions):
    """Evaluate a list of ANDed conditions against one panel row.

    A NaN feature never satisfies a numeric condition (no fabricated signal).
    """
    for cond in conditions:
        field = cond.get("field")
        op = cond.get("op")
        value = panel_row.get(field)
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return False
        if op in (">", ">=", "<", "<=", "==", "!="):
            if not _cmp(value, op, cond.get("value")):
                return False
        elif op == "between":
            lo, hi = cond["value"]
            if not (float(lo) <= float(value) <= float(hi)):
                return False
        elif op == "in":
            if not _in(value, cond["value"]):
                return False
        else:
            return False
    return True


def expected_signal_dates(panel, conditions):
    """Sessions where the entry conditions fire (used by the sample-size gate)."""
    return [d for d, row in panel.iterrows() if evaluate(row, conditions)]
