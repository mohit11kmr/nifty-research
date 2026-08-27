"""Phase I.3 - AI Hypothesis Packet Generator (spec sections 21-22).

Deterministically converts a research question into an AI hypothesis packet
that an external AI (opencode subprocess) turns into a proposal. Every packet
explicitly separates:

    OBSERVED    - what the data showed (deterministic, from behavior engine)
    INFERRED    - what that suggests (interpretation)
    HYPOTHESIS  - the testable claim the AI must operationalize

Gate enforcement (section 22): a packet only references REGISTERED features
(research_feature_registry.require_registered), declares a supported
execution family, declares risk/expiry/data requirements and expected failure
modes, and is point-in-time safe by construction. Unknown features cannot
enter an AI proposal.
"""
import os
import yaml

import research_feature_registry as FREG

REPO = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(REPO, "results", "phase_i3")
PACKETS_DIR = os.path.join(RESULTS_DIR, "ai_packets")

SUPPORTED_FAMILIES = {
    "TREND_FOLLOWING", "MEAN_REVERSION", "GAP_BOUNCE", "PCR_CONTRA",
    "OI_BUILDUP", "INSTITUTIONAL_FLOW", "MAX_PAIN_REVERT", "EXPIRY_CYCLE",
    "VOL_EXPANSION", "VOL_CONTRACTION", "REGIME_SWITCH",
}


def _observed_summary(question, behavior_report):
    for b in behavior_report["behaviors"]:
        if b["observation"] == question["observation"]:
            cb = b["conditional_behavior"]["fwd_5d"]
            bl = b["baseline"]["fwd_5d"]
            return {
                "n_sessions": b["n_sessions"],
                "frequency": b["frequency"],
                "confidence": b["confidence"],
                "fwd_5d_mean": cb["mean"] if cb else None,
                "fwd_5d_hit_rate": cb["hit_rate_up"] if cb else None,
                "baseline_fwd_5d_mean": bl["mean"] if bl else None,
                "delta_vs_baseline": round(cb["mean"] - bl["mean"], 5) if cb and bl else None,
            }
    return {}


def build_packets(questions, behavior_report):
    FREG.require_registered({f for q in questions for f in q["required_data"]})
    packets = []
    for q in questions:
        if q["candidate_family"] not in SUPPORTED_FAMILIES:
            continue
        packet = {
            "packet_id": f"PK-{q['question_id']}",
            "question_id": q["question_id"],
            "candidate_family": q["candidate_family"],
            "observed": _observed_summary(q, behavior_report),
            "inferred": (
                f"The {q['candidate_family']} family is the most plausible "
                f"explanation for the observed {q['observed_frequency'] * 100:.1f}% "
                f"frequency behaviour "
                f"('{q['observation']}') with confidence {q['confidence']}."
            ),
            "hypothesis": q["hypothesis"],
            "market_context": q["market_context"],
            "required_data": q["required_data"],
            "expected_failure_modes": q["expected_failure_modes"],
            "gates": {
                "point_in_time_safe": True,
                "features_registered": sorted(set(q["required_data"]) & FREG.registered_ids()),
                "execution_family_supported": q["candidate_family"] in SUPPORTED_FAMILIES,
                "cost_model": "canonical (40/order, 1.5% slippage)",
                "resolution": "EOD",
                "defined_risk": q["candidate_family"] != "VOL_EXPANSION",
            },
            "generation_instructions": (
                "Operationalize this hypothesis as a deterministic EOD strategy "
                "proposal in the Phase I.3 YAML schema. Entry conditions must use "
                "ONLY the registered feature ids in required_data. Direction and "
                "instrument must map to one of: OPTION_LONG (CALL/PUT/STRADDLE) or "
                "OPTION_IRON_CONDOR. Never reference unregistered features. Declare "
                "risk (defined risk for shorts), expiry handling, expected failure "
                "modes and a testable research question."
            ),
        }
        packets.append(packet)
    return packets


def write_packets(packets):
    os.makedirs(PACKETS_DIR, exist_ok=True)
    paths = []
    for p in packets:
        path = os.path.join(PACKETS_DIR, f"{p['packet_id']}.yaml")
        with open(path, "w") as fh:
            yaml.safe_dump(p, fh, sort_keys=False, default_flow_style=False)
        paths.append(path)
    return paths
