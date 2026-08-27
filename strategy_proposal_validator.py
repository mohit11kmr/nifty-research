"""Phase I - AI Strategy Proposal Validator.

Deterministic validation of a strategy proposal document against the Phase I
schema and gates. The proposal is a RESEARCH DOCUMENT; the AI is a hypothesis
generator, never a code author. Every gate is a hard deterministic check:

  - schema (unknown fields / missing blocks)
  - arbitrary-code rejection (REJECTED_ARBITRARY_CODE)
  - lookahead / point-in-time (LOOKAHEAD_ERROR)
  - risk (RISK_ERROR) - uses the H3 lessons: max-loss and credit semantics
    must be valid BEFORE any performance testing
  - data (DATA_INSUFFICIENT) - against the unified research manifest
  - expiry (EXPIRY_ERROR) - canonical expiry + research window coverage
  - execution compatibility (EXECUTION_UNSUPPORTED) - canonical cost model
  - unsupported instrument (UNSUPPORTED_INSTRUMENT)
  - the strategy block must also pass the EXISTING strategy_validator

The validator NEVER executes anything from the proposal.
"""
import json
import os
import re

import strategy_schema as S
import strategy_proposal_schema as PS
from strategy_validator import validate_spec as validate_existing_spec

REPO = os.path.dirname(os.path.abspath(__file__))
UNIFIED_MANIFEST = os.path.join(
    REPO, "data", "historical", "manifests", "unified_research_dataset.json")
EXPIRY_CALENDAR = os.path.join(REPO, "data", "historical", "expiry_calendar.csv")

# data_requirement token -> (manifest missing-days key, manifest sha key, column name)
DATA_MANIFEST_KEYS = {
    "NIFTY": ("nifty", "nifty_hash", "nifty_dataset"),
    "VIX": ("vix", "vix_hash", "vix_dataset"),
    "OPTIONS": ("options_eod", "options_hash", "options_dataset"),
    "OI": ("participant_oi", "participant_oi_hash", "participant_oi_dataset"),
    "FII_DII": ("participant_oi", "participant_oi_hash", "participant_oi_dataset"),
    "ML_FEATURES": None,
    "EXPIRY_CALENDAR": ("expiry", "expiry_hash", "expiry_calendar"),
}


class ProposalValidationResult:
    def __init__(self, proposal, errors, warnings, hashes, failure_code=None):
        self.proposal = proposal
        self.errors = list(errors)
        self.warnings = list(warnings)
        self.hashes = dict(hashes or {})
        self.failure_code = failure_code

    @property
    def valid(self):
        return not self.errors

    def __bool__(self):
        return self.valid

    def report(self):
        lines = ["proposal_hash: " + str(self.hashes.get("proposal_hash"))]
        lines.append(f"valid: {self.valid}")
        if self.failure_code:
            lines.append(f"failure_code: {self.failure_code}")
        for e in self.errors:
            lines.append(f"ERROR {e}")
        for w in self.warnings:
            lines.append(f"WARNING {w}")
        return "\n".join(lines)


def _fmt(path, msg):
    return f"[{path}] {msg}"


def _first_failure(code_priority, seen):
    for code in code_priority:
        if code in seen:
            return code
    return None


def _manifest():
    if not os.path.exists(UNIFIED_MANIFEST):
        return None
    with open(UNIFIED_MANIFEST) as fh:
        return json.load(fh)


def _coverage(manifest, token):
    """Return ('FULL'|'PARTIAL'|'MISSING', detail) for a data token."""
    key = DATA_MANIFEST_KEYS.get(token)
    if key is None:  # e.g. ML_FEATURES has no manifest column
        return "FILE", "validated by file presence"
    missing_key, sha_key, column = key
    if not manifest:
        return "MISSING", "no unified manifest"
    if token == "EXPIRY_CALENDAR":
        missing = manifest.get("expiry_calendar_missing_sessions") or []
        if not missing:
            return "FULL", "no missing sessions"
        return "PARTIAL", f"{len(missing)} sessions outside calendar coverage"
    missing = manifest.get("missing_dataset_days") or {}
    missing_days = missing.get(missing_key)
    if missing_days is None:
        return "MISSING", f"manifest has no column for {token}"
    if not missing_days:
        return "FULL", "no missing sessions"
    return "PARTIAL", f"{len(missing_days)} missing sessions"


def validate_proposal(proposal):
    """Validate a parsed proposal document. Deterministic error ordering."""
    errors = []
    warnings = []
    seen_failures = set()

    # ------------------------------------------------------------------
    # 1. Schema gate
    # ------------------------------------------------------------------
    if not isinstance(proposal, dict):
        errors.append("proposal must be a mapping")
        seen_failures.add("SCHEMA_ERROR")
        hashes = {"proposal_hash": PS.proposal_hash(proposal or {})}
        return ProposalValidationResult(proposal, errors, warnings, hashes,
                                        failure_code="SCHEMA_ERROR")

    for key in proposal:
        if key not in PS.PROPOSAL_TOP_BLOCKS:
            errors.append(_fmt(key, f"unknown top-level block "
                                    f"(allowed: {', '.join(PS.PROPOSAL_TOP_BLOCKS)})"))
            seen_failures.add("SCHEMA_ERROR")

    meta = proposal.get("proposal")
    if not isinstance(meta, dict):
        errors.append("proposal block (metadata) is required and must be a mapping")
        seen_failures.add("SCHEMA_ERROR")
    else:
        for key in meta:
            if key not in PS.PROPOSAL_META_KEYS:
                errors.append(_fmt(f"proposal.{key}", "unknown metadata key"))
                seen_failures.add("SCHEMA_ERROR")
        for key in PS.PROPOSAL_META_REQUIRED:
            if key not in meta or meta[key] in (None, "", []):
                errors.append(_fmt(f"proposal.{key}", "missing required field"))
                seen_failures.add("SCHEMA_ERROR")
        pid = meta.get("proposal_id")
        if pid is not None and not S.ID_PATTERN.match(str(pid)):
            errors.append(_fmt("proposal.proposal_id",
                               f"invalid id {pid!r} (must match [a-z0-9_]+)"))
            seen_failures.add("SCHEMA_ERROR")
        auth = meta.get("author_type")
        if auth is not None and auth not in PS.AUTHOR_TYPES:
            errors.append(_fmt("proposal.author_type",
                               f"must be one of {', '.join(PS.AUTHOR_TYPES)}"))
            seen_failures.add("SCHEMA_ERROR")
        emf = meta.get("expected_failure_modes")
        if emf is not None and not isinstance(emf, list):
            errors.append("proposal.expected_failure_modes must be a list")
            seen_failures.add("SCHEMA_ERROR")

    strategy_block = proposal.get("strategy")
    if not isinstance(strategy_block, dict):
        errors.append("strategy block is required and must be a full strategy spec")
        seen_failures.add("SCHEMA_ERROR")

    research = proposal.get("research")
    if not isinstance(research, dict):
        errors.append("research block is required (fixed window + dataset identity)")
        seen_failures.add("SCHEMA_ERROR")
    else:
        for key in research:
            if key not in PS.RESEARCH_KEYS:
                errors.append(_fmt(f"research.{key}", "unknown research key"))
                seen_failures.add("SCHEMA_ERROR")
        for key in ("dataset_manifest_hash", "start_date", "end_date", "dev_oos_cut"):
            if key not in research or not research[key]:
                errors.append(_fmt(f"research.{key}", "missing required field"))
                seen_failures.add("SCHEMA_ERROR")

    # ------------------------------------------------------------------
    # 2. Arbitrary-code rejection (scans the ENTIRE document)
    # ------------------------------------------------------------------
    _scan_arbitrary_code(proposal, errors, seen_failures)

    # ------------------------------------------------------------------
    # 3. Lookahead / point-in-time gate (scans the ENTIRE document)
    # ------------------------------------------------------------------
    _scan_lookahead(proposal, errors, seen_failures)

    # ------------------------------------------------------------------
    # 4. Existing strategy-spec validation (the strategy block must be a
    #    valid EXISTING strategy spec; no parallel engine is created).
    # ------------------------------------------------------------------
    if isinstance(strategy_block, dict):
        existing = validate_existing_spec(strategy_block)
        if not existing.valid:
            errors.append(f"strategy block failed the existing strategy validator: "
                          f"{' | '.join(existing.errors[:6])}")
            seen_failures.add("SCHEMA_ERROR")
            spec_hash = existing.hashes.get("spec_hash")
        else:
            spec_hash = existing.hashes.get("spec_hash")
        # promotion safety: state.promoted must never be true (defense in depth)
        state = strategy_block.get("state") or {}
        if state.get("promoted") is True:
            errors.append("strategy.state.promoted must never be true from a proposal")
            seen_failures.add("RISK_ERROR")

    # ------------------------------------------------------------------
    # 5. Risk gate (H3 lessons applied BEFORE performance testing)
    # ------------------------------------------------------------------
    if isinstance(strategy_block, dict):
        _gate_risk(strategy_block, errors, seen_failures)

    # ------------------------------------------------------------------
    # 6. Data gate
    # ------------------------------------------------------------------
    _gate_data(strategy_block, research, errors, warnings, seen_failures)

    # ------------------------------------------------------------------
    # 7. Expiry gate
    # ------------------------------------------------------------------
    _gate_expiry(strategy_block, research, errors, seen_failures)

    # ------------------------------------------------------------------
    # 8. Execution compatibility gate (canonical cost model only)
    # ------------------------------------------------------------------
    _gate_execution(strategy_block, errors, seen_failures)

    # ------------------------------------------------------------------
    # 9. Unsupported instrument
    # ------------------------------------------------------------------
    if isinstance(strategy_block, dict):
        itype = (strategy_block.get("instrument") or {}).get("type")
        if itype is not None and itype not in S.INSTRUMENT_TYPES:
            errors.append(_fmt("strategy.instrument.type",
                               f"unsupported instrument {itype!r}"))
            seen_failures.add("UNSUPPORTED_INSTRUMENT")

    hashes = {
        "proposal_hash": PS.proposal_hash(proposal),
        "spec_hash": spec_hash if "spec_hash" in dir() else None,
        "fingerprint": PS.normalized_rule_fingerprint(strategy_block)
        if isinstance(strategy_block, dict) else None,
    }
    failure = _first_failure(PS.FAILURE_CODES, seen_failures)
    return ProposalValidationResult(proposal, errors, warnings, hashes,
                                    failure_code=failure)


# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------
def _scan_arbitrary_code(node, errors, seen_failures, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            _scan_arbitrary_code(k, errors, seen_failures, path)
            _scan_arbitrary_code(v, errors, seen_failures, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _scan_arbitrary_code(v, errors, seen_failures, f"{path}[{i}]")
    elif isinstance(node, str):
        for pat in PS.FORBIDDEN_CODE_PATTERNS:
            if pat.search(node):
                errors.append(_fmt(path, f"arbitrary-code token {pat.pattern!r} "
                                         f"in value {node!r}"))
                seen_failures.add("REJECTED_ARBITRARY_CODE")
                break


def _scan_lookahead(node, errors, seen_failures, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            _scan_lookahead(k, errors, seen_failures, path)
            _scan_lookahead(v, errors, seen_failures, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _scan_lookahead(v, errors, seen_failures, f"{path}[{i}]")
    elif isinstance(node, str):
        low = node.lower()
        for pat in PS.FORBIDDEN_LOOKAHEAD_PATTERNS:
            if pat.search(low):
                errors.append(_fmt(path, f"lookahead/point-in-time concept "
                                         f"{node!r} at strategy time"))
                seen_failures.add("LOOKAHEAD_ERROR")
                break


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------
def _gate_risk(spec, errors, seen_failures):
    risk = spec.get("risk")
    if not isinstance(risk, dict):
        errors.append("risk gate: risk block required")
        seen_failures.add("RISK_ERROR")
        return
    if "rule" not in risk:
        errors.append("risk gate: risk.rule must be defined (EXISTING_PROJECT_RULE)")
        seen_failures.add("RISK_ERROR")
    ps_ = risk.get("position_size")
    if not isinstance(ps_, dict) or not ps_.get("lots") or not ps_.get("lot_size"):
        errors.append("risk gate: position_size (lots + lot_size) required")
        seen_failures.add("RISK_ERROR")
    else:
        if not isinstance(ps_.get("lots"), int) or ps_.get("lots") <= 0:
            errors.append("risk gate: position_size.lots must be a positive integer")
            seen_failures.add("RISK_ERROR")
        if not isinstance(ps_.get("lot_size"), int) or ps_.get("lot_size") <= 0:
            errors.append("risk gate: position_size.lot_size must be a positive integer")
            seen_failures.add("RISK_ERROR")
        if int(ps_.get("lot_size", 0)) != PS.CANONICAL_LOT_SIZE:
            errors.append(f"risk gate: lot_size must be the canonical "
                          f"{PS.CANONICAL_LOT_SIZE}")
            seen_failures.add("EXECUTION_UNSUPPORTED")
    mr = risk.get("max_risk_pct")
    if mr is not None:
        try:
            mr = float(mr)
        except (TypeError, ValueError):
            errors.append("risk gate: max_risk_pct must be numeric")
            seen_failures.add("RISK_ERROR")
            mr = None
        if mr is not None and not (0 < mr <= 1):
            errors.append("risk gate: max_risk_pct must be in (0, 1]")
            seen_failures.add("RISK_ERROR")

    # capital basis must be declared (position sizing is impossible otherwise)
    capital = risk.get("capital_basis")
    if capital is not None:
        try:
            capital = float(capital)
        except (TypeError, ValueError):
            errors.append("risk gate: capital_basis must be numeric")
            seen_failures.add("RISK_ERROR")
            capital = None
        if capital is not None and capital <= 0:
            errors.append("risk gate: capital_basis must be positive")
            seen_failures.add("RISK_ERROR")
    else:
        errors.append("risk gate: capital_basis must be declared (no implicit capital)")
        seen_failures.add("RISK_ERROR")

    # exit must be defined (at least stop/target/expiry)
    exit_sec = spec.get("exit")
    if not isinstance(exit_sec, dict):
        errors.append("risk gate: exit block required")
        seen_failures.add("RISK_ERROR")
    else:
        if not any(k in exit_sec for k in ("stop", "target", "expiry")):
            errors.append("risk gate: exit must define stop/target/expiry")
            seen_failures.add("RISK_ERROR")

    # multi-leg structures need max-loss + credit semantics declared (H3)
    itype = (spec.get("instrument") or {}).get("type")
    if itype in ("DEFINED_RISK_RANGE", "DEFINED_RISK_DIRECTIONAL"):
        if not isinstance(exit_sec, dict) or (exit_sec.get("expiry") or {}).get("rule") != S.CANONICAL_EXPIRY_TOKEN:
            errors.append("risk gate: multi-leg structure requires "
                          "exit.expiry.rule == CANONICAL_EXPIRY")
            seen_failures.add("EXPIRY_ERROR")
        note = str(risk.get("note") or "")
        if "max loss" not in note.lower() and "max_loss" not in note.lower() \
           and "maximum loss" not in note.lower():
            errors.append("risk gate: multi-leg structure must declare its "
                          "maximum-loss semantics in risk.note (H3 lesson)")
            seen_failures.add("RISK_ERROR")
        strikes = spec.get("strike_selection")
        if not isinstance(strikes, dict) or strikes.get("rule") != S.PROJECT_RULE_TOKEN:
            errors.append("risk gate: multi-leg strike construction must use an "
                          "EXISTING_PROJECT_RULE (no arbitrary strike math)")
            seen_failures.add("RISK_ERROR")


def _gate_data(spec, research, errors, warnings, seen_failures):
    if not isinstance(spec, dict):
        return
    tokens = spec.get("data_requirements")
    if not isinstance(tokens, list) or not tokens:
        errors.append("data gate: data_requirements must be a non-empty list")
        seen_failures.add("DATA_INSUFFICIENT")
        return
    manifest = _manifest()
    if not manifest:
        errors.append("data gate: unified research manifest not found; "
                      "cannot verify data coverage")
        seen_failures.add("DATA_INSUFFICIENT")
    else:
        declared = research.get("dataset_manifest_hash") if isinstance(research, dict) else None
        manifest_sha = _manifest_sha()
        if declared and manifest_sha and declared != manifest_sha:
            errors.append(f"data gate: research.dataset_manifest_hash "
                          f"{declared} does not match the unified manifest "
                          f"{manifest_sha[:16]}...")
            seen_failures.add("DATA_INSUFFICIENT")
    for tok in tokens:
        if tok not in S.DATA_REQUIREMENT_TOKENS:
            errors.append(_fmt("data_requirements", f"unknown token {tok!r}"))
            seen_failures.add("DATA_INSUFFICIENT")
            continue
        status, detail = _coverage(manifest, tok)
        if status == "MISSING":
            errors.append(f"data gate: {tok} unavailable ({detail})")
            seen_failures.add("DATA_INSUFFICIENT")
        elif status == "PARTIAL":
            warnings.append(f"data gate: {tok} coverage is PARTIAL ({detail})")


def _gate_expiry(spec, research, errors, seen_failures):
    if not isinstance(spec, dict):
        return
    itype = (spec.get("instrument") or {}).get("type")
    if itype in S.INSTRUMENT_TYPES and itype is not None:
        exit_sec = spec.get("exit") or {}
        exp = (exit_sec.get("expiry") or {}) if isinstance(exit_sec, dict) else {}
        if exp.get("rule") != S.CANONICAL_EXPIRY_TOKEN:
            errors.append("expiry gate: options strategy must use "
                          "exit.expiry.rule == CANONICAL_EXPIRY")
            seen_failures.add("EXPIRY_ERROR")
    if not isinstance(research, dict):
        return
    start = research.get("start_date")
    end = research.get("end_date")
    if not start or not end:
        return
    # the canonical calendar only covers >= 2025-08-13; earlier research
    # windows cannot be evaluated without expiry reconstruction.
    cal_start = "2025-08-13"
    if start < cal_start:
        errors.append(f"expiry gate: research window starts {start} before the "
                      f"canonical expiry calendar coverage ({cal_start}); "
                      f"expiry reconstruction is not permitted")
        seen_failures.add("EXPIRY_ERROR")
    if start > end:
        errors.append(f"expiry gate: start_date {start} after end_date {end}")
        seen_failures.add("EXPIRY_ERROR")


def _gate_execution(spec, errors, seen_failures):
    if not isinstance(spec, dict):
        return
    execution = spec.get("execution")
    if not isinstance(execution, dict):
        errors.append("execution gate: execution block required")
        seen_failures.add("EXECUTION_UNSUPPORTED")
        return
    cost = execution.get("cost_model") or {}
    cp = cost.get("cost_per_order")
    slip = execution.get("slippage_pct")
    if cp != PS.CANONICAL_COST_PER_ORDER:
        errors.append(f"execution gate: cost_per_order must be the canonical "
                      f"{PS.CANONICAL_COST_PER_ORDER} (AI cannot change the cost model)")
        seen_failures.add("EXECUTION_UNSUPPORTED")
    if slip != PS.CANONICAL_SLIPPAGE_PCT:
        errors.append(f"execution gate: slippage_pct must be the canonical "
                      f"{PS.CANONICAL_SLIPPAGE_PCT} (AI cannot change the cost model)")
        seen_failures.add("EXECUTION_UNSUPPORTED")


def _manifest_sha():
    if not os.path.exists(UNIFIED_MANIFEST):
        return None
    import hashlib
    with open(UNIFIED_MANIFEST, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def validate_file(path):
    """Validate a YAML proposal file from disk."""
    import yaml
    with open(path) as fh:
        proposal = yaml.safe_load(fh)
    return validate_proposal(proposal)
