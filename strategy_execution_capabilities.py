"""Phase I.2 - Execution Capability Matrix.

Each execution family declares its supported capabilities (spec section 7).

The hard rule (spec section 7):

    Do not claim a capability until it has tests.

A family is ONLY listed here when (a) it has a deterministic implementation
composed exclusively from registered project primitives AND (b) that
implementation is exercised by tests/test_phase_i2_execution_capabilities.py.

This module is declarative. It never executes anything from a proposal.
"""
import re

# ---------------------------------------------------------------------------
# Resolution codes (spec section 3 failure categories)
# ---------------------------------------------------------------------------
ENTRY_UNSUPPORTED = "ENTRY_UNSUPPORTED"
INSTRUMENT_UNSUPPORTED = "INSTRUMENT_UNSUPPORTED"
POSITION_CONSTRUCTION_UNSUPPORTED = "POSITION_CONSTRUCTION_UNSUPPORTED"
RISK_UNSUPPORTED = "RISK_UNSUPPORTED"
EXIT_UNSUPPORTED = "EXIT_UNSUPPORTED"
DATA_FIELD_UNSUPPORTED = "DATA_FIELD_UNSUPPORTED"
EXPIRY_UNSUPPORTED = "EXPIRY_UNSUPPORTED"
P_AND_L_UNSUPPORTED = "P_AND_L_UNSUPPORTED"
COST_MODEL_UNSUPPORTED = "COST_MODEL_UNSUPPORTED"
MULTI_LEG_UNSUPPORTED = "MULTI_LEG_UNSUPPORTED"
GRANULARITY_UNSUPPORTED = "GRANULARITY_UNSUPPORTED"
RISK_SEMANTIC_UNDEFINED = "RISK_SEMANTIC_UNDEFINED"
FAMILY_NOT_REGISTERED = "FAMILY_NOT_REGISTERED"

# ---------------------------------------------------------------------------
# Execution resolution (spec section 15 - no false fill precision)
# ---------------------------------------------------------------------------
EOD = "EOD"
INTRADAY = "INTRADAY"
TICK = "TICK"
RESOLUTIONS = (EOD, INTRADAY, TICK)

# ---------------------------------------------------------------------------
# Granularity gate (spec sections 14/15)
# ---------------------------------------------------------------------------
# A strategy description that claims an intraday/tick operating mode cannot be
# faithfully replayed from the EOD research dataset. Word-boundary scan so a
# word like "expected" never trips "expected move" style false positives.
_INTRADAY_TOKENS = (
    r"\bintraday\b", r"\bintra-day\b", r"\btick\b", r"\breal-time\b",
    r"\brealtime\b", r"\bminutes?\b", r"\b5[ \u2011-]?min\b", r"\b15[ \u2011-]?min\b",
    r"\b30[ \u2011-]?min\b", r"\b60[ \u2011-]?min\b", r"\bhourly\b",
    r"\bminute[\s-]?(chart|frame)\b", r"\bm1\b", r"\bm5\b", r"\bm15\b",
)
_GRANULARITY_RE = re.compile("|".join(_INTRADAY_TOKENS), re.IGNORECASE)


def granularity_gate(description):
    """Return GRANULARITY_UNSUPPORTED when the description demands a finer
    resolution than the EOD research dataset can provide, else None."""
    if not description:
        return None
    if _GRANULARITY_RE.search(str(description)):
        return GRANULARITY_UNSUPPORTED
    return None


# ---------------------------------------------------------------------------
# Data-field gate (spec section 3 / DATA_FIELD_UNSUPPORTED)
# ---------------------------------------------------------------------------
# OI_WALL and MAX_PAIN are STRIKE LEVELS (e.g. 24500.0), not fractions.
# A literal comparison like "OI_WALL > 0.5" is vacuous: the condition is
# always true whenever the field exists and is not a meaningful strategy rule.
STRIKE_TYPED_FIELDS = ("OI_WALL", "MAX_PAIN")
_VACUOUS_STRIKE_LEVEL = 1000.0


def vacuous_strike_threshold(condition):
    """Return the condition id (or field) when a strike-typed field is compared
    against a sub-1000 constant, else None."""
    if not isinstance(condition, dict) or condition.get("field") not in STRIKE_TYPED_FIELDS:
        return None
    value = condition.get("value")
    if isinstance(value, (int, float)) and not isinstance(value, bool) \
            and abs(float(value)) < _VACUOUS_STRIKE_LEVEL:
        return condition.get("id") or condition.get("field")
    return None


# Coverage floor for a field referenced by an entry condition. A proposal whose
# hard entry gate depends on a field that exists on fewer than 50% of the
# evaluable window days cannot be faithfully backtested on this dataset (the
# declared data requirement is not met for a majority of the window).
COVERAGE_MIN_PCT = 50.0


def coverage_failed(available, usable):
    if not usable:
        return None
    pct = available / len(usable) * 100.0
    if pct < COVERAGE_MIN_PCT:
        return round(pct, 1)
    return None


# ---------------------------------------------------------------------------
# Capability matrix (spec section 7)
# ---------------------------------------------------------------------------
# Only the families with a deterministic implementation + dedicated tests are
# declared. Everything else is reported as EXECUTION_UNSUPPORTED and listed in
# the audit's "remaining unsupported families".
CAPABILITY_TABLE = {
    "OPTION_BUY": {
        "family_id": "OPTION_BUY",
        "entry_supported": True,
        "multi_leg": False,
        "risk_supported": True,
        "expiry_supported": True,
        "stop_supported": True,
        "target_supported": True,
        "MTM_supported": True,
        "cost_model_supported": True,
        "min_granularity": EOD,
        "required_data": ["NIFTY", "OPTIONS_EOD", "VIX", "OI", "EXPIRY_CALENDAR"],
        "supported_market_types": ["NIFTY"],
        "risk_basis": "premium paid on the single long option",
        "risk_semantics": "DEFINED (max loss = entry premium, capital at risk)",
    },
    "CALL_CREDIT_SPREAD": {
        "family_id": "CALL_CREDIT_SPREAD",
        "entry_supported": True,
        "multi_leg": True,
        "risk_supported": True,
        "expiry_supported": True,
        "stop_supported": True,
        "target_supported": True,
        "MTM_supported": True,
        "cost_model_supported": True,
        "min_granularity": EOD,
        "required_data": ["NIFTY", "OPTIONS_EOD", "VIX", "OI", "EXPIRY_CALENDAR"],
        "supported_market_types": ["NIFTY"],
        "risk_basis": "wing width minus net credit received",
        "risk_semantics": "DEFINED (max loss = |long - short| - entry_credit)",
    },
    "IRON_CONDOR": {
        "family_id": "IRON_CONDOR",
        "entry_supported": True,
        "multi_leg": True,
        "risk_supported": True,
        "expiry_supported": True,
        "stop_supported": True,
        "target_supported": True,
        "MTM_supported": True,
        "cost_model_supported": True,
        "min_granularity": EOD,
        "required_data": ["NIFTY", "OPTIONS_EOD", "VIX", "EXPIRY_CALENDAR"],
        "supported_market_types": ["NIFTY"],
        "risk_basis": "call wing width (or put wing width)",
        "risk_semantics": "DEFINED (max loss = wing width - entry_credit)",
    },
}


def capability(family_id):
    """Capability dict for a family, or None when not declared."""
    return CAPABILITY_TABLE.get(family_id)


def list_supported_families():
    return sorted(CAPABILITY_TABLE)
