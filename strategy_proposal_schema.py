"""Phase I - AI Strategy Proposal Schema.

Single source of truth for the AI strategy research layer. Defines:
  - the proposal document shape (proposal + strategy + research blocks)
  - which fields an AI may compose (reuses the existing FIELD_REGISTRY,
    PROJECT_RULE_ALLOWLIST and DATA_REQUIREMENT_TOKENS from strategy_schema)
  - the structured failure codes
  - deterministic hashing (proposal_hash) and normalized rule fingerprinting
    for duplicate detection

Safety invariants (from the phase instructions):
  - AI may only compose registered platform primitives (no arbitrary code).
  - The proposal must NOT be a parallel strategy engine: its strategy block is
    a full strategy specification that feeds the EXISTING strategy_validator /
    strategy_compiler pipeline.
"""
import hashlib
import json
import re

PROPOSAL_SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Proposal document blocks
# ---------------------------------------------------------------------------
PROPOSAL_TOP_BLOCKS = ("proposal", "strategy", "research")

PROPOSAL_META_REQUIRED = (
    "proposal_id", "title", "author_type", "author_model", "created_at",
    "parent_strategy_id", "hypothesis", "research_question",
    "expected_failure_modes",
)

# proposal block sub-keys (the "proposal:" section of the YAML)
PROPOSAL_META_KEYS = (
    "proposal_id", "title", "author_type", "author_model", "created_at",
    "parent_strategy_id", "hypothesis", "research_question",
    "expected_failure_modes",
)

AUTHOR_TYPES = ("HUMAN", "AI")

# research block sub-keys (fixed research window + dataset identity)
RESEARCH_KEYS = (
    "dataset_manifest_hash", "start_date", "end_date", "dev_oos_cut",
    "min_required_trades", "note",
)

# ---------------------------------------------------------------------------
# Structured failure codes (section 17)
# ---------------------------------------------------------------------------
FAILURE_CODES = (
    "SCHEMA_ERROR",
    "LOOKAHEAD_ERROR",
    "RISK_ERROR",
    "EXPIRY_ERROR",
    "DATA_INSUFFICIENT",
    "UNSUPPORTED_INSTRUMENT",
    "EXECUTION_UNSUPPORTED",
    "OOS_INSUFFICIENT",
    "SAMPLE_INSUFFICIENT",
    "DUPLICATE_PROPOSAL",
    "REJECTED_ARBITRARY_CODE",
)

# Registry statuses (section 18)
REGISTRY_STATUSES = (
    "DRAFT", "VALIDATED", "BACKTESTED", "REVIEW", "REJECTED",
    "PAPER_CANDIDATE", "RETIRED",
)

# Human review decisions (section 26)
HUMAN_DECISIONS = (
    "REJECT", "REQUEST_MORE_DATA", "RUN_CONTROLLED_PAPER_TEST",
)

# ---------------------------------------------------------------------------
# Arbitrary-code rejection tokens (section 7)
# ---------------------------------------------------------------------------
FORBIDDEN_CODE_PATTERNS = (
    re.compile(r"\beval\b"),
    re.compile(r"\bexec\b"),
    re.compile(r"\b__import__\b"),
    re.compile(r"\bimport\b"),
    re.compile(r"\bos\.system\b"),
    re.compile(r"\bsubprocess\b"),
    re.compile(r"\bgetattr\b"),
    re.compile(r"\bsetattr\b"),
    re.compile(r"\bcompile\s*\("),
    re.compile(r"\bglobals\s*\("),
    re.compile(r"\blocals\s*\("),
    re.compile(r"\b__dict__\b"),
    re.compile(r"\bshutil\b"),
    re.compile(r"\bsocket\b"),
    re.compile(r"\bctypes\b"),
    re.compile(r"\bpickle\s*[.(]"),
    re.compile(r"\bimport\s+pickle\b"),
    re.compile(r"\bsys\.path\b"),
    re.compile(r"\bshell\s*=\s*True"),
    re.compile(r"\$\(.*\)"),          # shell command substitution
    re.compile(r"`[^`]+`"),           # backtick shell
    re.compile(r"python\s+-[a-z]+"),
    re.compile(r"!python"),
    re.compile(r"\bopen\s*\("),
    re.compile(r"\brequests?\s*\."),
)

# ---------------------------------------------------------------------------
# Lookahead / point-in-time safety (section 8) - extends strategy_schema
# ---------------------------------------------------------------------------
import strategy_schema as S  # noqa: E402

LOOKAHEAD_FORBIDDEN = S.LOOKAHEAD_FORBIDDEN_SUBSTRINGS + (
    "future_", "tomorrow", "next_close", "next_open",
)
FORBIDDEN_LOOKAHEAD_PATTERNS = tuple(
    re.compile(r"\b" + re.escape(x) + r"\b") if x.isidentifier()
    else re.compile(re.escape(x))
    for x in LOOKAHEAD_FORBIDDEN
)

# ---------------------------------------------------------------------------
# Compute budget (section 21)
# ---------------------------------------------------------------------------
MAX_PROPOSALS_PER_RUN = 4
MAX_BACKTESTS_PER_SESSION = 2
MAX_COMPUTE_SECONDS = 1800

# ---------------------------------------------------------------------------
# Execution compatibility (section 13): proposals cannot change the cost model.
# ---------------------------------------------------------------------------
CANONICAL_COST_PER_ORDER = 40.0
CANONICAL_SLIPPAGE_PCT = 0.015
CANONICAL_LOT_SIZE = 75

# ---------------------------------------------------------------------------
# Hashing + fingerprints
# ---------------------------------------------------------------------------
def proposal_hash(proposal):
    """Deterministic sha256 of the canonical proposal document."""
    canonical = json.dumps(proposal, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def strategy_spec_hash(spec):
    return S.spec_hash(spec)


def _norm(value):
    """Normalize a value for fingerprinting (stable, order-insensitive)."""
    if isinstance(value, dict):
        return {str(k): _norm(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, list):
        return [_norm(v) for v in value]
    return value


def normalized_rule_fingerprint(spec):
    """Normalized rule fingerprint for duplicate detection.

    Ignores cosmetic fields (description, notes, ids, versions) and keeps only
    the behavior-bearing structure: regime gate, entry conditions, direction,
    instrument, strike rule refs, risk sizing, exit reasons, execution model,
    data requirements.
    """
    def pick(d, keys):
        if not isinstance(d, dict):
            return d
        return {k: _norm(d[k]) for k in keys if k in d}

    keep = {
        "market": pick(spec.get("market"), ("underlying",)),
        "regime": pick(spec.get("regime"), ("allowed",)),
        "entry": pick(spec.get("entry"), ("conditions", "gate")),
        "direction": pick(spec.get("direction"), ("mode", "rule", "project_ref", "side_map")),
        "instrument": pick(spec.get("instrument"), ("type", "option_side", "lot_size")),
        "strike_selection": pick(spec.get("strike_selection"), ("rule", "project_ref")),
        "risk": pick(spec.get("risk"), ("rule", "project_ref", "position_size")),
        "exit": pick(spec.get("exit"), ("stop", "target", "expiry", "allowed_reasons")),
        "execution": pick(spec.get("execution"), ("cost_model", "slippage_pct")),
        "data_requirements": _norm(spec.get("data_requirements")),
    }
    canonical = json.dumps(keep, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
