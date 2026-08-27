"""Phase H1 v2 - Strategy Compiler.

compile(spec) -> CompiledStrategy. The compiled strategy exposes a STABLE
interface (evaluate / generate_candidate / build_order / build_exit_rules)
that references the EXISTING deterministic engines - it never duplicates or
reimplements them. Project-rule references are resolved ONLY against the
curated allowlist in strategy_schema.py; nothing is executed from the file.
"""
import importlib

import strategy_schema as S


def _resolve(ref):
    """Resolve an allowlisted module.function reference to a callable."""
    module_name, _, func_name = ref.partition(".")
    if ref not in S.PROJECT_RULE_ALLOWLIST:
        raise ValueError(f"project_ref {ref!r} is not in the allowlist")
    mod = importlib.import_module(module_name)
    fn = getattr(mod, func_name, None)
    if not callable(fn):
        raise ValueError(f"allowlisted reference {ref!r} does not resolve to a callable")
    return fn


def _apply(op, left, right):
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    raise ValueError(f"unsupported operator {op!r}")


def _coerce(value, field_type):
    if value is None:
        return None
    if field_type == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if field_type == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    return value


class CompiledStrategy:
    """Immutable view over a validated strategy specification."""

    def __init__(self, spec, spec_hash):
        self.spec = spec
        self.spec_hash = spec_hash
        st = spec["strategy"]
        self.strategy_id = st["id"]
        self.version = st["version"]
        self.name = st.get("name")
        self.classification = st.get("classification")
        self.data_requirements = list(spec.get("data_requirements") or [])

    # ---- stable interface ---------------------------------------------------
    def evaluate(self, context):
        """Evaluate entry conditions against a decision-time context.

        Declarative conditions are evaluated against registered fields.
        Project-rule conditions are DELEGATED to the existing engine: they
        resolve to their allowlisted function and are called with the context
        keys that match their parameters; results that cannot be computed from
        the given context are reported as None (never fabricated).
        """
        entry = self.spec.get("entry") or {}
        conds = entry.get("conditions") or {}
        verdict = {"entry_allowed": False, "conditions": {}}

        def eval_block(block, mode):
            for i, cond in enumerate(block or []):
                key = f"{mode}[{i}]:{cond.get('id') or i}"
                verdict["conditions"][key] = self._eval_one(cond, context)

        eval_block(conds.get("all"), "all")
        eval_block(conds.get("any"), "any")

        all_ok = all(verdict["conditions"][k] is True for k in verdict["conditions"] if k.startswith("all"))
        any_ok = any(verdict["conditions"][k] is True for k in verdict["conditions"] if k.startswith("any"))
        has_any = any(k.startswith("any") for k in verdict["conditions"])
        verdict["entry_allowed"] = all_ok and (not has_any or any_ok)
        return verdict

    def generate_candidate(self, context):
        """Return a candidate dict from a decision-time context.

        For MVP the candidate is produced by the existing engine and passed in
        as context['candidate_rec'] (the compiler packages it, it does not
        recompute strikes/premiums). Returns None when no candidate is present
        in the context.
        """
        rec = context.get("candidate_rec")
        if not isinstance(rec, dict) or not rec.get("candidate"):
            return None
        return {
            "entry_date": rec.get("date"),
            "side": rec.get("option_type"),
            "option_type": rec.get("option_type"),
            "strike": rec.get("strike"),
            "short_strike": rec.get("short_strike"),
            "expiry": rec.get("expiry"),
            "entry_premium": rec.get("entry_premium") or rec.get("entry_net") or rec.get("entry_credit"),
            "sl_premium": rec.get("sl_premium"),
            "target_premium": rec.get("target_premium"),
            "lots": (self.spec.get("risk", {}).get("position_size") or {}).get("lots", 1),
            "lot_size": (self.spec.get("risk", {}).get("position_size") or {}).get("lot_size", 75),
        }

    def build_order(self, candidate, context):
        """Build order dict(s) in the paper_execution.submit_order shape.

        NEVER submits - this is a pure descriptor. Returns a list of leg
        orders (1 for NAKED_OPTION, 2 for a vertical spread, 4 for a condor).
        """
        if not candidate:
            return []
        itype = self.spec.get("instrument", {}).get("type")
        base = {
            "symbol": self.spec.get("market", {}).get("underlying", "NIFTY"),
            "lots": int(candidate.get("lots", 1)),
            "lot_size": int(candidate.get("lot_size", 75)),
            "entry_price": float(candidate.get("entry_premium") or 0.0),
            "sl_price": float(candidate.get("sl_premium")) if candidate.get("sl_premium") else None,
            "target_price": float(candidate.get("target_premium")) if candidate.get("target_premium") else None,
            "requested_price": float(candidate.get("entry_premium") or 0.0),
            "order_kind": "OPEN",
        }
        if itype == "NAKED_OPTION":
            return [{**base, "side": "BUY",
                     "option_type": candidate["option_type"], "strike": candidate["strike"]}]
        if itype == "DEFINED_RISK_DIRECTIONAL":
            long_side = candidate["side"]
            return [
                {**base, "side": "BUY", "option_type": long_side,
                 "strike": candidate["strike"]},
                {**base, "side": "SELL", "option_type": long_side,
                 "strike": candidate["short_strike"]},
            ]
        if itype == "DEFINED_RISK_RANGE":
            strikes = candidate.get("strikes") or {}
            legs = [
                ("SELL", "CE", strikes.get("short_call")),
                ("SELL", "PE", strikes.get("short_put")),
                ("BUY", "CE", strikes.get("long_call")),
                ("BUY", "PE", strikes.get("long_put")),
            ]
            orders = []
            for side, opt, strike in legs:
                if strike is None:
                    continue
                orders.append({**base, "side": side, "option_type": opt, "strike": strike})
            return orders
        return []

    def build_exit_rules(self, position, context):
        """Return the exit policy for a position (references the existing
        exit_evaluator reason vocabulary and the spec's declared rules)."""
        exit_sec = self.spec.get("exit", {})
        return {
            "stop": exit_sec.get("stop"),
            "target": exit_sec.get("target"),
            "expiry": exit_sec.get("expiry"),
            "allowed_reasons": list(exit_sec.get("allowed_reasons") or []),
            "evaluator_ref": "exit_evaluator.ExitEvaluator",
        }

    # ---- internals ------------------------------------------------------------
    def _eval_one(self, cond, context):
        if "field" in cond:
            fld = cond["field"]
            raw = context.get(fld)
            if raw is None:
                return None  # not evaluable from this context
            expected = S.FIELD_TYPES.get(fld)
            left = _coerce(raw, expected)
            right = _coerce(cond.get("value"), expected)
            try:
                return bool(_apply(cond["operator"], left, right))
            except TypeError:
                return None
        if cond.get("rule") == S.PROJECT_RULE_TOKEN:
            fn = _resolve(cond["project_ref"])
            try:
                import inspect
                params = inspect.signature(fn).parameters
                kwargs = {k: v for k, v in context.items() if k in params and v is not None}
                if len(kwargs) < len([p for p in params.values() if p.default is inspect.Parameter.empty]):
                    return None
                result = fn(**kwargs)
                if isinstance(result, tuple):
                    result = result[0]
                return bool(result)
            except Exception:
                return None
        return None


def compile_strategy(spec):
    """Compile a validated spec dict into a CompiledStrategy (deterministic)."""
    h = S.spec_hash(spec)
    return CompiledStrategy(spec, h)


def compile_file(path):
    """Compile a YAML strategy file."""
    import yaml
    from strategy_validator import validate_file
    vr = validate_file(path)
    if not vr.valid:
        raise ValueError(f"refusing to compile invalid spec {path}:\n" + "\n".join(vr.errors))
    with open(path) as fh:
        spec = yaml.safe_load(fh)
    return compile_strategy(spec)
