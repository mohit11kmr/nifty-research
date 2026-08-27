"""Phase I.3 - Fast Screen (spec section 26).

Cheap, deterministic gates that run BEFORE any backtest and reject obvious dead
ends. Proposals that pass the schema/risk/data/expiry/execution gates and show
a plausible sample size are SCREENED_IN; valid but rare-condition proposals are
labelled LOW_FREQUENCY (never silently dropped); anything else is REJECT with a
structured reason. Valid low-frequency proposals keep their label through the
full research stage so the sample-size policy (§29) is applied visibly.
"""
import os
import datetime as dt
import yaml

import research_conditions as RC
import research_feature_registry as FREG

DIRECTIONS = {"LONG", "SHORT", "NEUTRAL"}
INSTRUMENTS = {"CALL", "PUT", "STRADDLE", "IRON_CONDOR"}
EXIT_TYPES = {"HORIZON", "EXPIRY", "CONDITION"}
MIN_SIGNAL_DATES = 20

SUPPORTED_FAMILY_BY_INSTRUMENT = {
    "CALL": ("TREND_FOLLOWING", "MEAN_REVERSION", "GAP_BOUNCE", "PCR_CONTRA",
             "OI_BUILDUP", "INSTITUTIONAL_FLOW", "MAX_PAIN_REVERT", "EXPIRY_CYCLE"),
    "PUT": ("TREND_FOLLOWING", "MEAN_REVERSION", "GAP_BOUNCE", "PCR_CONTRA",
            "OI_BUILDUP", "INSTITUTIONAL_FLOW", "MAX_PAIN_REVERT", "EXPIRY_CYCLE"),
    "STRADDLE": ("VOL_EXPANSION",),
    "IRON_CONDOR": ("VOL_CONTRACTION", "MAX_PAIN_REVERT", "MEAN_REVERSION",
                    "EXPIRY_CYCLE"),
}


def load_proposal(path):
    with open(path) as fh:
        doc = yaml.safe_load(fh)
    return doc


def validate_proposal(doc):
    """Schema validation. Returns (violations: list)."""
    errs = []
    prop = (doc or {}).get("proposal")
    strat = (doc or {}).get("strategy")
    if not prop:
        return ["missing proposal block"]
    if not strat:
        return ["missing strategy block"]

    entry = strat.get("entry") or {}
    conditions = entry.get("conditions")
    errs += [f"entry: {e}" for e in RC.validate_conditions(conditions)]

    direction = entry.get("direction")
    if direction not in DIRECTIONS:
        errs.append(f"entry.direction '{direction}' not in {sorted(DIRECTIONS)}")
    instrument = entry.get("instrument")
    if instrument not in INSTRUMENTS:
        errs.append(f"entry.instrument '{instrument}' not in {sorted(INSTRUMENTS)}")
    if direction == "SHORT" and instrument not in ("IRON_CONDOR",):
        errs.append("SHORT direction only supported for defined-risk IRON_CONDOR")
    if direction == "NEUTRAL" and instrument != "IRON_CONDOR":
        errs.append("NEUTRAL direction only supported for IRON_CONDOR")
    if direction == "LONG" and instrument == "IRON_CONDOR":
        errs.append("IRON_CONDOR cannot be direction LONG")

    strike_sel = entry.get("strike_selection")
    if strike_sel not in ("ATM", "OTM_1", "ITM_1"):
        errs.append(f"entry.strike_selection '{strike_sel}' not in ATM/OTM_1/ITM_1")

    exit_ = strat.get("exit") or {}
    etype = exit_.get("type")
    if etype not in EXIT_TYPES:
        errs.append(f"exit.type '{etype}' not in {sorted(EXIT_TYPES)}")
    if etype == "HORIZON":
        h = exit_.get("horizon_sessions")
        if not isinstance(h, int) or not (1 <= h <= 20):
            errs.append("exit.horizon_sessions must be int in 1..20")
    if etype == "CONDITION" and not RC.validate_conditions([exit_.get("condition") or {}]):
        errs.append("exit.condition must be a valid single condition")

    risk = strat.get("risk") or {}
    if not risk.get("defined_risk") and instrument in ("IRON_CONDOR",):
        errs.append("IRON_CONDOR requires risk.defined_risk=true")

    exec_ = strat.get("execution") or {}
    if exec_.get("cost_model") != "canonical":
        errs.append("execution.cost_model must be 'canonical'")
    if exec_.get("resolution") != "EOD":
        errs.append("execution.resolution must be 'EOD'")

    req_feats = strat.get("required_features") or []
    if not isinstance(req_feats, list) or not req_feats:
        errs.append("strategy.required_features must be a non-empty list")
    try:
        FREG.require_registered(req_feats)
    except ValueError as e:
        errs.append(str(e))
    cond_fields = {c.get("field") for c in conditions or []}
    if not cond_fields.issubset(set(req_feats)):
        errs.append(f"entry condition fields not declared in required_features: "
                    f"{sorted(cond_fields - set(req_feats))}")

    reg = strat.get("regime") or {}
    allowed = reg.get("allowed")
    if allowed is not None:
        if not isinstance(allowed, list) or not all(a.startswith("REGIME_") for a in allowed):
            errs.append("regime.allowed must be a list of REGIME_* labels (or null)")
    return errs


def fast_screen(doc, panel, regime_labels=None):
    """Fast screen: schema/risk/data/expiry/execution/sample-size sanity.

    Returns {"verdict": SCREENED_IN|REJECT|LOW_FREQUENCY, "reasons": [...]}."""
    violations = validate_proposal(doc)
    if violations:
        return {"verdict": "REJECT", "reasons": [f"schema: {v}" for v in violations],
                "schema_violations": violations}
    strat = doc["strategy"]
    entry = strat["entry"]
    conditions = entry["conditions"]
    req_feats = strat.get("required_features") or []

    # data gate: all required features must be present in the panel
    missing = [f for f in req_feats if f not in panel.columns]
    if missing:
        return {"verdict": "REJECT", "reasons": [f"data: features missing from panel: {missing}"],
                "schema_violations": []}

    # regime gate: every referenced regime must exist
    allowed = (strat.get("regime") or {}).get("allowed") or []
    if allowed and regime_labels is not None:
        unknown = sorted(set(allowed) - set(regime_labels))
        if unknown:
            return {"verdict": "REJECT", "reasons": [f"regime: unknown labels {unknown}"],
                    "schema_violations": []}

    # expiry gate: signals must occur on sessions with resolvable expiry
    sig_dates = RC.expected_signal_dates(panel, conditions)
    if allowed:
        sig_dates = [d for d in sig_dates if regime_labels.get(d) in allowed]

    # execution gate: instrument must match a supported family
    instrument = entry["instrument"]
    family = doc["proposal"].get("candidate_family")
    if family and family not in SUPPORTED_FAMILY_BY_INSTRUMENT[instrument]:
        return {"verdict": "REJECT",
                "reasons": [f"execution: family '{family}' incompatible with instrument '{instrument}'"],
                "schema_violations": []}

    reasons = [
        f"signals_in_window={len(sig_dates)}",
        f"instrument={instrument}, direction={entry.get('direction')}, family={family}",
    ]
    if len(sig_dates) < 20:
        reasons.append("sample-size: <20 signals in window")
        return {"verdict": "LOW_FREQUENCY" if sig_dates else "REJECT",
                "reasons": reasons, "signal_dates": sig_dates, "schema_violations": []}
    reasons.append("sample-size: >=20 signals in window")
    return {"verdict": "SCREENED_IN", "reasons": reasons,
            "signal_dates": sig_dates, "schema_violations": []}
