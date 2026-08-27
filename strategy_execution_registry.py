"""Phase I.2 - Execution Family Registry (spec sections 4/6/11).

Maps a validated strategy SPEC to a registered deterministic execution family.
Resolution is purely declarative over:

    instrument.type x direction.mode x instrument.option_side x risk.note

Nothing is executed here. compile_executor raises a structured
ValueError("EXECUTION_UNSUPPORTED: <CODE>: <reason>") when the spec cannot be
mapped to a registered family - never a silent fallback.
"""
import strategy_execution_capabilities as C
from strategy_execution_capabilities import (
    POSITION_CONSTRUCTION_UNSUPPORTED,
    INSTRUMENT_UNSUPPORTED,
    DATA_FIELD_UNSUPPORTED,
    RISK_SEMANTIC_UNDEFINED,
    GRANULARITY_UNSUPPORTED,
    FAMILY_NOT_REGISTERED,
)

CREDIT = "CREDIT"
DEBIT = "DEBIT"

# risk.note markers that declare the cash flow semantics of a defined-risk
# directional spread (spec section 10: control premium != condor credit).
_CREDIT_MARKERS = (
    "net credit", "credit received", "credit capture", "max credit",
    "wing width minus net credit", "collect premium", "premium selling",
    "credit spread",
)
_DEBIT_MARKERS = (
    "net debit", "debit", "premium paid for the spread", "buy the spread",
)

# Markers that make a DEFINED_RISK_RANGE structure a NON-standard (asymmetric /
# broken-wing / anchored) construction. The deterministic IRON_CONDOR family
# only covers the symmetric four-leg structure (spec section 9 invariants).
_ASYM_MARKERS = (
    "asymmetric", "broken-wing", "brokenwing", "broken wing", "max pain",
    "max_pain", "maxpain", "widest wing", "narrower wing", "wider wing",
    "wing multiplier", "wing_multiplier", "1.5x", "expected move", "anchor",
    "insurance", "unbalanced",
)
_ASYM_ID_TOKENS = ("brokenwing", "broken-wing", "maxpain", "asymmetric")


def _text_has_markers(text, markers):
    low = (text or "").lower()
    return any(mk in low for mk in markers)


def _credit_or_debit(spec):
    """Cash-flow semantics of a DEFINED_RISK_DIRECTIONAL spread.

    Returns (CREDIT|DEBIT, note) or (None, RISK_SEMANTIC_UNDEFINED) when the
    spec does not declare the cash-flow basis (spec section 11: reject
    RISK_SEMANTIC_UNDEFINED rather than infer).
    """
    note = ((spec.get("risk") or {}).get("note")) or ""
    if _text_has_markers(note, _CREDIT_MARKERS) and not _text_has_markers(note, _DEBIT_MARKERS):
        return CREDIT, note
    if _text_has_markers(note, _DEBIT_MARKERS):
        return DEBIT, note
    return None, RISK_SEMANTIC_UNDEFINED


def _asymmetric_condor(spec):
    """True when a DEFINED_RISK_RANGE structure deviates from the symmetric
    iron condor the deterministic engine can construct."""
    ss = spec.get("strike_selection") or {}
    if ss.get("params"):
        return True
    if _text_has_markers(((spec.get("risk") or {}).get("note")), _ASYM_MARKERS):
        return True
    sid = ((spec.get("strategy") or {}).get("id")) or ""
    low = sid.lower()
    if any(tok in low for tok in _ASYM_ID_TOKENS):
        return True
    return False


def resolve_family(spec):
    """Map a validated strategy spec to a family id.

    Returns (family_id, None) or (None, (code, reason)). Raises nothing; the
    registry's compile_executor turns the (code, reason) into the structured
    ValueError used across the pipeline.
    """
    instrument = spec.get("instrument") or {}
    itype = instrument.get("type")
    mode = ((spec.get("direction") or {}).get("mode"))
    sides = tuple(instrument.get("option_side") or [])

    if itype == "NAKED_OPTION":
        if mode == "DIRECTIONAL":
            return "OPTION_BUY", None
        return None, (INSTRUMENT_UNSUPPORTED,
                      "NAKED_OPTION only maps to a directional buy family")

    if itype == "DEFINED_RISK_DIRECTIONAL":
        if mode != "DIRECTIONAL":
            return None, (INSTRUMENT_UNSUPPORTED,
                          "DEFINED_RISK_DIRECTIONAL requires direction.mode=DIRECTIONAL")
        if len(sides) != 1:
            return None, (POSITION_CONSTRUCTION_UNSUPPORTED,
                          f"vertical spread requires exactly one option_side (got {list(sides)})")
        cash, note = _credit_or_debit(spec)
        if cash is None:
            return None, (RISK_SEMANTIC_UNDEFINED,
                          "defined-risk directional spread does not declare net credit/debit in risk.note")
        side = sides[0]
        if cash == CREDIT:
            return ("CALL_CREDIT_SPREAD" if side == "CE" else "PUT_CREDIT_SPREAD"), None
        return ("BULL_CALL_SPREAD" if side == "CE" else "BEAR_PUT_SPREAD"), None

    if itype == "DEFINED_RISK_RANGE":
        if mode != "NEUTRAL":
            return None, (INSTRUMENT_UNSUPPORTED,
                          "DEFINED_RISK_RANGE requires direction.mode=NEUTRAL")
        if set(sides) != {"CE", "PE"}:
            return None, (POSITION_CONSTRUCTION_UNSUPPORTED,
                          f"defined-risk range requires option_side [CE, PE] (got {list(sides)})")
        if _asymmetric_condor(spec):
            return None, (POSITION_CONSTRUCTION_UNSUPPORTED,
                          "asymmetric / broken-wing / anchored condor - not the "
                          "symmetric four-leg structure the deterministic family supports")
        return "IRON_CONDOR", None

    return None, (INSTRUMENT_UNSUPPORTED, f"unsupported instrument.type {itype!r}")


class ExecutionFamily:
    """A registered execution family: capability + executor factory."""

    def __init__(self, family_id, capability, executor_class):
        self.family_id = family_id
        self.capability = capability
        self.executor_class = executor_class

    @property
    def supported(self):
        return self.capability is not None

    def compile_executor(self, compilation):
        return self.executor_class(compilation, self)


class ExecutionRegistry:
    """register / lookup / capability check / compile executor / list."""

    def __init__(self, families=None):
        self._families = {}
        for fam in (families or []):
            self.register(fam)

    def register(self, family):
        if family.family_id in self._families:
            raise ValueError(f"family {family.family_id} already registered")
        self._families[family.family_id] = family
        return family

    def lookup(self, family_id):
        return self._families.get(family_id)

    def capability_check(self, family_id):
        fam = self.lookup(family_id)
        return fam.capability if fam is not None else None

    def list_supported(self):
        return sorted(self._families)

    def compile_executor(self, compilation):
        """Full capability gate: granularity -> family resolution -> data-field
        (vacuous) -> registered executor. Raises ValueError with a structured
        EXECUTION_UNSUPPORTED code when any gate fails (never a silent fallback)."""
        spec = compilation.compiled.spec
        description = (spec.get("description") or "")
        granularity = C.granularity_gate(description)
        if granularity:
            raise ValueError(
                f"EXECUTION_UNSUPPORTED: {granularity}: description demands a "
                f"finer resolution than the EOD research dataset provides")

        family_id, failure = resolve_family(spec)
        if family_id is None:
            code, reason = failure
            raise ValueError(f"EXECUTION_UNSUPPORTED: {code}: {reason}")

        for block in ("all", "any"):
            for cond in ((spec.get("entry") or {}).get("conditions") or {}).get(block) or []:
                vacuous = C.vacuous_strike_threshold(cond)
                if vacuous:
                    raise ValueError(
                        f"EXECUTION_UNSUPPORTED: {DATA_FIELD_UNSUPPORTED}: "
                        f"condition {vacuous!r} compares a strike-typed field "
                        f"({cond.get('field')}) against a vacuous sub-1000 constant")

        fam = self.lookup(family_id)
        if fam is None or not fam.supported:
            raise ValueError(
                f"EXECUTION_UNSUPPORTED: {FAMILY_NOT_REGISTERED}: family "
                f"{family_id!r} resolved but has no deterministic registered "
                f"executor (registered: {self.list_supported()})")

        return fam.compile_executor(compilation)


_default_registry = None


def default_registry():
    """Process-wide default registry with the three tested families."""
    global _default_registry
    if _default_registry is None:
        import strategy_execution
        from strategy_execution_capabilities import capability as _cap
        _default_registry = ExecutionRegistry([
            ExecutionFamily("OPTION_BUY", _cap("OPTION_BUY"),
                            strategy_execution.OptionBuyExecutor),
            ExecutionFamily("CALL_CREDIT_SPREAD", _cap("CALL_CREDIT_SPREAD"),
                            strategy_execution.CreditVerticalExecutor),
            ExecutionFamily("IRON_CONDOR", _cap("IRON_CONDOR"),
                            strategy_execution.IronCondorExecutor),
        ])
    return _default_registry
