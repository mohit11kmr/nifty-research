"""Phase H1 v2 - Strategy schema: single source of truth for the controlled
field registry, safe operators, supported instruments, regimes, lookahead
policy and the PROJECT-RULE allowlist.

No arbitrary Python is ever executed from a strategy file. Project rules are
declarative references resolved ONLY against this curated allowlist.
"""
import re

SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Controlled field registry (declarative conditions may reference ONLY these)
# ---------------------------------------------------------------------------
FIELD_REGISTRY = (
    "REGIME",       # TREND_HV / TREND_LV / RANGE_HV / RANGE_LV
    "VIX",          # India VIX level (float)
    "VIX_ZONE",     # VIX_CHEAP / VIX_NORMAL / VIX_RICH / VIX_HIGH / VIX_PANIC
    "ADX",          # trend strength
    "EMA20",        # 20-period EMA
    "EMA50",        # 50-period EMA
    "RSI",          # relative strength index
    "PCR",          # put-call ratio
    "OI_WALL",      # nearest OI wall strike
    "SKEW",         # IV skew bias (CALL / PUT / NEUTRAL)
    "MAX_PAIN",     # max pain strike
    "FII_SENTIMENT",  # institutional scan sentiment
    "ML_VERDICT",   # super-AI ML ensemble verdict
    "SPOT",         # NIFTY spot close at decision time
    "ATR",          # average true range
    "GRADE",        # funnel grade A+ / A / NO_SIGNAL
    "CONFLUENCE_SCORE",  # 0..6 passed layers
    "ACTION",       # funnel action token
)

FIELD_TYPES = {
    "REGIME": "str", "VIX": "float", "VIX_ZONE": "str", "ADX": "float",
    "EMA20": "float", "EMA50": "float", "RSI": "float", "PCR": "float",
    "OI_WALL": "float", "SKEW": "str", "MAX_PAIN": "float",
    "FII_SENTIMENT": "str", "ML_VERDICT": "str", "SPOT": "float",
    "ATR": "float", "GRADE": "str", "CONFLUENCE_SCORE": "int",
    "ACTION": "str",
}

# Safe operators only
OPERATORS = (">", ">=", "<", "<=", "==", "!=")

# Regimes known to the project
REGIMES = ("TREND_HV", "TREND_LV", "RANGE_HV", "RANGE_LV")
# RANGE_LV is a hard no-trade regime; it may never be an allowed regime.
HARD_BLOCKED_REGIMES = ("RANGE_LV",)

UNDERLYINGS = ("NIFTY",)

# Instrument types supported by the platform
INSTRUMENT_TYPES = (
    "NAKED_OPTION",             # long directional CE/PE, 1 lot (control)
    "DEFINED_RISK_DIRECTIONAL", # vertical spread (bull call / bear put)
    "DEFINED_RISK_RANGE",       # iron condor (market neutral credit)
)

DIRECTION_MODES = ("DIRECTIONAL", "NEUTRAL")

LIFECYCLES = (
    "DRAFT", "VALIDATED", "BACKTESTED", "REVIEW", "PAPER",
    "PROMOTED", "REJECTED", "RETIRED",
)

# Standard data-requirement tokens (validated against the project data cache)
DATA_REQUIREMENT_TOKENS = (
    "NIFTY", "VIX", "OPTIONS", "OI", "FII_DII", "ML_FEATURES",
    "EXPIRY_CALENDAR",
)

# Post-trade / future concepts that may never appear in strategy-time fields
LOOKAHEAD_FORBIDDEN_SUBSTRINGS = (
    "future_", "tomorrow", "next_close", "future_vix", "future_oi",
    "future_high", "future_low", "outcome", "realized_pnl", "exit_price",
)

# Project-rule allowlist: strategy files may reference ONLY these
# module.function names, resolved against this explicit map (never getattr).
PROJECT_RULE_ALLOWLIST = {
    "backtest_frozen.regime_gate_at": "backtest_frozen",
    "backtest_frozen.technical_verdict_at": "backtest_frozen",
    "backtest_frozen.options_layer_at": "backtest_frozen",
    "backtest_frozen.institutional_layer_at": "backtest_frozen",
    "backtest_frozen.ml_predict_at": "backtest_frozen",
    "backtest_frozen.evaluate_day": "backtest_frozen",
    "backtest_frozen.simulate_trade": "backtest_frozen",
    "expiry_calendar.get_expiry_for_trade_date": "expiry_calendar",
    "premium_seller.sell_ok": "premium_seller",
    "multi_strategy_backtest.build_condor": "multi_strategy_backtest",
    "multi_strategy_backtest.simulate_condor": "multi_strategy_backtest",
    "multi_strategy_backtest.build_spread": "multi_strategy_backtest",
    "multi_strategy_backtest.simulate_spread": "multi_strategy_backtest",
    "multi_strategy_backtest.run_candidate_a": "multi_strategy_backtest",
    "multi_strategy_backtest.run_candidate_b": "multi_strategy_backtest",
    "multi_strategy_backtest.run_candidate_c": "multi_strategy_backtest",
}

PROJECT_RULE_TOKEN = "EXISTING_PROJECT_RULE"
CANONICAL_EXPIRY_TOKEN = "CANONICAL_EXPIRY"

ID_PATTERN = re.compile(r"^[a-z0-9_]+$")


def is_allowed_field(name):
    return name in FIELD_REGISTRY


def is_safe_operator(op):
    return op in OPERATORS


def is_forbidden_lookahead(name):
    return any(sub in str(name).lower() for sub in LOOKAHEAD_FORBIDDEN_SUBSTRINGS)


def is_allowed_project_ref(ref):
    return ref in PROJECT_RULE_ALLOWLIST


def spec_hash(spec):
    """Deterministic sha256 of a parsed spec dict (JSON-canonical)."""
    import hashlib
    import json
    canonical = json.dumps(spec, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
