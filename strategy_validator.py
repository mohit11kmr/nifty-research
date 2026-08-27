"""Phase H1 v2 - Strategy Validator.

Deterministic validation of a strategy specification against the controlled
schema. Rejects unknown fields, unknown operators, unknown/forbidden fields,
unsupported instruments, missing risk/exit/expiry/data, lookahead leakage and
unsupported combinations. Never executes anything from the spec; project-rule
references are checked against the curated allowlist only.
"""
import os
import re
import json
from dataclasses import dataclass, field

import strategy_schema as S

REQUIRED_TOP = (
    "schema_version", "strategy", "description", "market", "regime", "entry",
    "direction", "instrument", "strike_selection", "risk", "exit",
    "execution", "data_requirements", "state", "references",
)
REQUIRED_STRATEGY = ("id", "name", "version", "classification")

CONDITION_FIELDS = ("field", "operator", "value", "rule", "project_ref",
                    "note", "id")


def _fmt(path, msg):
    return f"[{path}] {msg}"


class ValidationResult:
    def __init__(self, spec, errors, warnings, hashes):
        self.spec = spec
        self.errors = list(errors)
        self.warnings = list(warnings)
        self.hashes = hashes

    @property
    def valid(self):
        return not self.errors

    def __bool__(self):
        return self.valid

    def report(self):
        lines = []
        lines.append(f"valid: {self.valid}")
        lines.append(f"spec_hash: {self.hashes.get('spec_hash')}")
        for e in self.errors:
            lines.append(f"ERROR {e}")
        for w in self.warnings:
            lines.append(f"WARNING {w}")
        return "\n".join(lines)


def validate_spec(spec, base_dir=None, expect_filename=None):
    """Validate a parsed spec dict. Deterministic error ordering.

    base_dir / expect_filename are used for the identity check (strategy.id
    must equal the YAML file stem when loading from the registry).
    """
    errors = []
    warnings = []
    if not isinstance(spec, dict):
        errors.append("spec must be a mapping")
        return ValidationResult(spec, errors, warnings, {})

    # --- top-level / unknown keys -----------------------------------------
    for key in spec:
        if key not in REQUIRED_TOP:
            errors.append(_fmt(key, f"unknown top-level key (allowed: {', '.join(REQUIRED_TOP)})"))

    # --- schema_version ----------------------------------------------------
    sv = spec.get("schema_version")
    if sv != S.SCHEMA_VERSION:
        errors.append(_fmt("schema_version", f"expected {S.SCHEMA_VERSION!r}, got {sv!r}"))

    # --- strategy identity --------------------------------------------------
    st = spec.get("strategy")
    if not isinstance(st, dict):
        errors.append("strategy must be a mapping")
    else:
        for key in st:
            if key not in REQUIRED_STRATEGY:
                errors.append(_fmt(f"strategy.{key}", "unknown strategy key"))
        for key in REQUIRED_STRATEGY:
            if key not in st:
                errors.append(_fmt(f"strategy.{key}", "missing required key"))
        sid = st.get("id")
        if sid is not None and not isinstance(sid, str):
            errors.append("strategy.id must be a string")
        elif sid is not None and not S.ID_PATTERN.match(sid):
            errors.append(_fmt("strategy.id", f"invalid id {sid!r} (must match [a-z0-9_]+)"))
        ver = st.get("version")
        if ver is not None and not isinstance(ver, int):
            errors.append("strategy.version must be an integer")
        if expect_filename:
            stem = os.path.splitext(os.path.basename(expect_filename))[0]
            if sid != stem:
                errors.append(_fmt("strategy.id", f"must equal file stem {stem!r}, got {sid!r}"))

    # --- market --------------------------------------------------------------
    market = spec.get("market")
    if not isinstance(market, dict):
        errors.append("market must be a mapping")
    elif market.get("underlying") not in S.UNDERLYINGS:
        errors.append(_fmt("market.underlying",
                           f"unsupported (MVP supports only {', '.join(S.UNDERLYINGS)})"))

    # --- regime ---------------------------------------------------------------
    regime = spec.get("regime")
    if not isinstance(regime, dict):
        errors.append("regime must be a mapping")
    else:
        allowed = regime.get("allowed")
        if not isinstance(allowed, list) or not allowed:
            errors.append("regime.allowed must be a non-empty list")
        else:
            seen = set()
            for r in allowed:
                if r not in S.REGIMES:
                    errors.append(_fmt("regime.allowed", f"unknown regime {r!r}"))
                if r in S.HARD_BLOCKED_REGIMES:
                    errors.append(_fmt("regime.allowed",
                                       f"{r} is a hard no-trade regime and may never be allowed"))
                if r in seen:
                    errors.append(_fmt("regime.allowed", f"duplicate regime {r!r}"))
                seen.add(r)

    # --- entry ----------------------------------------------------------------
    entry = spec.get("entry")
    if not isinstance(entry, dict):
        errors.append("entry must be a mapping")
    else:
        conds = entry.get("conditions")
        if not isinstance(conds, dict) or ("all" not in conds and "any" not in conds):
            errors.append("entry.conditions must be a mapping with at least one of 'all'/'any'")
        else:
            _validate_condition_blocks(conds, errors, "entry.conditions")
        gate = entry.get("gate")
        if gate is not None:
            if not isinstance(gate, dict):
                errors.append("entry.gate must be a mapping")
            else:
                for key in gate:
                    if key not in ("grade",):
                        errors.append(_fmt(f"entry.gate.{key}", "unknown gate key"))
                grade = gate.get("grade")
                if grade is not None:
                    if not isinstance(grade, dict):
                        errors.append("entry.gate.grade must be a mapping")
                    else:
                        mc = grade.get("min_confluence")
                        if not isinstance(mc, int) or not (1 <= mc <= 6):
                            errors.append("entry.gate.grade.min_confluence must be int 1..6")

    # --- direction -------------------------------------------------------------
    direction = spec.get("direction")
    if not isinstance(direction, dict):
        errors.append("direction must be a mapping")
    else:
        mode = direction.get("mode")
        if mode not in S.DIRECTION_MODES:
            errors.append(_fmt("direction.mode",
                               f"must be one of {', '.join(S.DIRECTION_MODES)}"))
        rule = direction.get("rule")
        if rule is not None:
            _validate_project_rule(direction, errors, "direction")

    # --- instrument -------------------------------------------------------------
    instrument = spec.get("instrument")
    if not isinstance(instrument, dict):
        errors.append("instrument must be a mapping")
    else:
        itype = instrument.get("type")
        if itype not in S.INSTRUMENT_TYPES:
            errors.append(_fmt("instrument.type",
                               f"unsupported instrument (allowed: {', '.join(S.INSTRUMENT_TYPES)})"))
        for key in ("option_side", "lot_size"):
            if key not in instrument:
                errors.append(_fmt(f"instrument.{key}", "missing required key"))
        lot = instrument.get("lot_size")
        if lot is not None and (not isinstance(lot, int) or lot <= 0):
            errors.append("instrument.lot_size must be a positive integer")

    # --- strike selection ---------------------------------------------------------
    strike = spec.get("strike_selection")
    if not isinstance(strike, dict):
        errors.append("strike_selection must be a mapping")
    else:
        _validate_project_rule(strike, errors, "strike_selection")

    # --- risk -----------------------------------------------------------------------
    risk = spec.get("risk")
    if not isinstance(risk, dict):
        errors.append("risk must be a mapping")
    else:
        if "rule" not in risk:
            errors.append("risk.rule must be defined (EXISTING_PROJECT_RULE)")
        _validate_project_rule(risk, errors, "risk")
        ps = risk.get("position_size")
        if not isinstance(ps, dict) or not ps.get("lots") or not ps.get("lot_size"):
            errors.append("risk.position_size must define lots and lot_size")
        else:
            if not isinstance(ps.get("lots"), int) or ps.get("lots") <= 0:
                errors.append("risk.position_size.lots must be a positive integer")
            if not isinstance(ps.get("lot_size"), int) or ps.get("lot_size") <= 0:
                errors.append("risk.position_size.lot_size must be a positive integer")

    # --- exit --------------------------------------------------------------------------
    exit_sec = spec.get("exit")
    if not isinstance(exit_sec, dict):
        errors.append("exit must be a mapping")
    else:
        has_any_exit = False
        for key in ("stop", "target", "expiry"):
            if key in exit_sec:
                has_any_exit = True
                sub = exit_sec[key]
                if not isinstance(sub, dict):
                    errors.append(f"exit.{key} must be a mapping")
                else:
                    if key == "expiry":
                        if sub.get("rule") != S.CANONICAL_EXPIRY_TOKEN:
                            errors.append("exit.expiry.rule must be CANONICAL_EXPIRY")
                    else:
                        _validate_project_rule(sub, errors, f"exit.{key}")
        if not has_any_exit:
            errors.append("exit must define at least one of stop/target/expiry")
        reasons = exit_sec.get("allowed_reasons")
        if not isinstance(reasons, list) or not reasons:
            errors.append("exit.allowed_reasons must be a non-empty list")

    # --- expiry required when options are involved -------------------------------------
    if instrument and isinstance(instrument, dict) and \
       instrument.get("type") in S.INSTRUMENT_TYPES:
        exp = (exit_sec or {}).get("expiry") if isinstance(exit_sec, dict) else None
        if not exp:
            errors.append("exit.expiry must be defined for an options instrument")

    # --- execution -----------------------------------------------------------------------
    execution = spec.get("execution")
    if not isinstance(execution, dict):
        errors.append("execution must be a mapping")
    else:
        cost = execution.get("cost_model")
        if not isinstance(cost, dict) or not isinstance(cost.get("cost_per_order"), (int, float)) \
           or not isinstance(cost.get("orders_per_round_trip"), int):
            errors.append("execution.cost_model must define cost_per_order (number) "
                          "and orders_per_round_trip (int)")
        slip = execution.get("slippage_pct")
        if not isinstance(slip, (int, float)) or not (0 <= slip < 1):
            errors.append("execution.slippage_pct must be a fraction in [0, 1)")

    # --- data requirements ------------------------------------------------------------------
    data_req = spec.get("data_requirements")
    if not isinstance(data_req, list) or not data_req:
        errors.append("data_requirements must be a non-empty list")
    else:
        for tok in data_req:
            if tok not in S.DATA_REQUIREMENT_TOKENS:
                errors.append(_fmt("data_requirements", f"unknown token {tok!r}"))

    # --- state --------------------------------------------------------------------------------
    state = spec.get("state")
    if not isinstance(state, dict):
        errors.append("state must be a mapping")
    else:
        lc = state.get("lifecycle")
        if lc not in S.LIFECYCLES:
            errors.append(_fmt("state.lifecycle",
                               f"must be one of {', '.join(S.LIFECYCLES)}"))
        cls = state.get("classification")
        if not isinstance(cls, str) or not cls:
            errors.append("state.classification must be a non-empty string")
        if state.get("promoted") is True:
            errors.append("state.promoted must never be true from a spec (promotion is explicit)")

    # --- supported combinations ---------------------------------------------------------------
    if direction and instrument:
        mode = direction.get("mode")
        itype = instrument.get("type")
        if mode == "NEUTRAL" and itype != "DEFINED_RISK_RANGE":
            errors.append("supported-combination: NEUTRAL direction requires "
                          "DEFINED_RISK_RANGE instrument")
        if itype == "DEFINED_RISK_RANGE" and mode != "NEUTRAL":
            errors.append("supported-combination: DEFINED_RISK_RANGE requires NEUTRAL direction")
        if mode == "DIRECTIONAL" and itype not in ("NAKED_OPTION", "DEFINED_RISK_DIRECTIONAL"):
            errors.append("supported-combination: DIRECTIONAL requires a directional instrument")

    # --- lookahead safety -----------------------------------------------------------------------
    _validate_lookahead(spec, errors)

    hashes = {"spec_hash": S.spec_hash(spec)}
    return ValidationResult(spec, errors, warnings, hashes)


# ---------------------------------------------------------------------------
def _validate_condition_blocks(conds, errors, path):
    for block in ("all", "any"):
        lst = conds.get(block)
        if lst is None:
            continue
        if not isinstance(lst, list) or not lst:
            errors.append(_fmt(f"{path}.{block}", "must be a non-empty list"))
            continue
        for i, cond in enumerate(lst):
            p = f"{path}.{block}[{i}]"
            _validate_condition(cond, errors, p)


def _validate_condition(cond, errors, path):
    if not isinstance(cond, dict):
        errors.append(_fmt(path, "condition must be a mapping"))
        return
    for key in cond:
        if key not in CONDITION_FIELDS:
            errors.append(_fmt(path, f"unknown condition key {key!r}"))
    has_field = "field" in cond
    has_rule = "rule" in cond
    if has_field and has_rule:
        errors.append(_fmt(path, "condition must be EITHER declarative (field) "
                                 "OR project-rule (rule), not both"))
        return
    if has_field:
        fld = cond.get("field")
        if not S.is_allowed_field(fld):
            errors.append(_fmt(path, f"unknown/unregistered field {fld!r} "
                                     f"(registry: {', '.join(S.FIELD_REGISTRY)})"))
        op = cond.get("operator")
        if not S.is_safe_operator(op):
            errors.append(_fmt(path, f"invalid operator {op!r} "
                                     f"(allowed: {', '.join(S.OPERATORS)})"))
        if "value" not in cond:
            errors.append(_fmt(path, "declarative condition requires 'value'"))
        if S.is_forbidden_lookahead(fld):
            errors.append(_fmt(path, f"lookahead field {fld!r} is forbidden at strategy time"))
    elif has_rule:
        if cond.get("rule") != S.PROJECT_RULE_TOKEN:
            errors.append(_fmt(path, f"unknown rule {cond.get('rule')!r} "
                                     f"(only {S.PROJECT_RULE_TOKEN} is supported)"))
        ref = cond.get("project_ref")
        if not ref or not S.is_allowed_project_ref(ref):
            errors.append(_fmt(path, f"project_ref {ref!r} is not in the allowlist "
                                     f"(no arbitrary code)"))
    else:
        errors.append(_fmt(path, "condition must declare 'field' or 'rule'"))
    # nested note is free text; nothing to validate.


def _validate_project_rule(section, errors, path):
    rule = section.get("rule")
    if rule == S.PROJECT_RULE_TOKEN:
        ref = section.get("project_ref")
        if not ref or not S.is_allowed_project_ref(ref):
            errors.append(_fmt(f"{path}.project_ref",
                               f"{ref!r} is not in the allowlist (no arbitrary code)"))
    elif rule is not None:
        errors.append(_fmt(f"{path}.rule", f"unknown rule {rule!r} "
                                           f"(only {S.PROJECT_RULE_TOKEN} is supported)"))


def _validate_lookahead(spec, errors):
    """Recursively scan strategy-time structures for forbidden future concepts."""
    def scan(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if S.is_forbidden_lookahead(k):
                    errors.append(_fmt(path, f"forbidden lookahead key {k!r}"))
                scan(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                scan(v, f"{path}[{i}]")
        elif isinstance(node, str):
            # free-text notes may legitimately discuss exits; only flag when a
            # FUTURE_-style field appears in a condition position. Conditions
            # are already handled by _validate_condition, so here we stay quiet
            # for prose. Real leakage only ever lives in field names/values.
            if S.is_forbidden_lookahead(node):
                errors.append(_fmt(path, f"forbidden lookahead value {node!r}"))
    scan(spec, "")


def validate_file(path):
    """Validate a YAML strategy file from disk (deterministic)."""
    import yaml
    with open(path, "r") as fh:
        spec = yaml.safe_load(fh)
    return validate_spec(spec, base_dir=os.path.dirname(path),
                         expect_filename=os.path.basename(path))
