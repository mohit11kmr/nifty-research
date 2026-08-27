"""Phase I.3 - Research Question Engine (spec section 20).

Turns the strongest measured behaviours into bounded, testable research
questions. The engine:

  * ranks behaviours by confidence and deviation from baseline,
  * maps each to a candidate execution family + hypothesis + failure modes,
  * respects the Phase I.3 budget: at most MAX_QUESTIONS research questions,
    each with at most 2 hypotheses (MAX_QUESTIONS * 2 <= 24 AI proposals),
  * emits questions/questions.yaml under results/phase_i3/.

Every question carries the observation, its market context (regime mix it was
observed in), the hypothesis, required_data (registered features only),
candidate_family and expected_failure_modes - so an AI proposal generator has
an explicit, gated spec to work from.
"""
import os
import json
import yaml

import research_feature_registry as FREG

REPO = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(REPO, "results", "phase_i3")
QUESTIONS_PATH = os.path.join(RESULTS_DIR, "research_questions.yaml")

MAX_QUESTIONS = 12
MAX_HYPOTHESES_PER_QUESTION = 2

# behaviour name -> (candidate_family, hypothesis template, failure modes)
FAMILY_MAP = {
    "trend_follow_up_5d": (
        "TREND_FOLLOWING",
        "Sustained 5-session gains do NOT persist; continuation fades next week.",
        ["regime-dependent persistence", "overlapping windows overstate signal", "costs erode small edges"],
    ),
    "trend_follow_down_5d": (
        "MEAN_REVERSION",
        "Sharp 5-session declines tend to rebound over the following week.",
        ["falling regimes persist longer than the window", "gap risk on entry", "sample includes 2024-2025 stress"],
    ),
    "mean_reversion_up_5d": (
        "MEAN_REVERSION",
        "Extended rallies (>+5% / 5d) pull back in the next week.",
        ["rare condition (n<20)", "strong-trend regimes override", "timing of fade is critical"],
    ),
    "mean_reversion_down_5d": (
        "MEAN_REVERSION",
        "Extended sell-offs (<-5% / 5d) bounce over the next week.",
        ["rare condition (n<20)", "crash continuation risk", "entries during falling regimes"],
    ),
    "vix_panic": (
        "VOL_CONTRACTION",
        "VIX > 25 marks a local volatility extreme followed by above-average 5d recovery.",
        ["n=7 (NOT_RELIABLE)", "panic can extend", "option premium marks differ from spot path"],
    ),
    "vix_high": (
        "VOL_CONTRACTION",
        "High-VIX (>=20) periods precede above-average 5-session spot recovery.",
        ["n=41 (LOW)", "high VIX can persist weeks", "premium stays expensive after spot recovery"],
    ),
    "vix_cheap": (
        "VOL_EXPANSION",
        "Cheap-VIX (<12) periods show below-average next-week drift.",
        ["low drift is a weak effect", "VIX can compress further before expanding"],
    ),
    "hv_above_vix": (
        "VOL_EXPANSION",
        "When realized HV exceeds the VIX level, realized volatility normalizes down.",
        ["HV vs VIX comparison is approximate", "no clean entry timing"],
    ),
    "pcr_low_decile": (
        "PCR_CONTRA",
        "Bottom-decile PCR (call-heavy) shows no reliable 5d directional bias.",
        ["contra-PCR is crowded", "OI is settlement-biased", "no edge detected"],
    ),
    "pcr_high_decile": (
        "PCR_CONTRA",
        "Top-decile PCR (put-heavy) shows no reliable 5d directional bias.",
        ["contra-PCR is crowded", "OI is settlement-biased", "no edge detected"],
    ),
    "oi_growth_top_quintile": (
        "OI_BUILDUP",
        "Sharp 5-session option-OI build-up precedes slightly above-average 5d drift.",
        ["OI build-up is lagging flow", "expiry-roll artefacts", "weak delta vs baseline"],
    ),
    "expiry_day_sessions": (
        "EXPIRY_CYCLE",
        "Expiry sessions carry mildly above-average next-week drift.",
        ["expiry mechanics change post-2025 (Tuesday weeklies)", "small effect"],
    ),
    "max_pain_above_spot": (
        "MAX_PAIN_REVERT",
        "Spot far from max pain does not reliably drift toward it within a week.",
        ["max pain is a settlement-day phenomenon", "drift often occurs intraday on expiry"],
    ),
    "gap_continuation_up": (
        "GAP_BOUNCE",
        "Positive opening gaps (>+0.5%) continue modestly over the next week.",
        ["gap is stale information by close", "costs dominate a small edge"],
    ),
    "gap_reversal_down": (
        "GAP_BOUNCE",
        "Negative opening gaps (<-0.5%) reverse upward over the next week.",
        ["gap is stale information by close", "falling regimes can gap down repeatedly"],
    ),
    "atm_expensive": (
        "VOL_CONTRACTION",
        "Expensive near-ATM premium proxy precedes above-average 5d spot drift.",
        ["premium proxy is not true IV", "spot drift is not premium P&L"],
    ),
    "fii_share_rising_5d": (
        "INSTITUTIONAL_FLOW",
        "Rising 5-session FII participant-OI share precedes above-average 5d drift.",
        ["aggregate EQ OI only (no futures/options split)", "participant data is end-of-day"],
    ),
    "high_dte_early_week": (
        "EXPIRY_CYCLE",
        "Early-cycle sessions (6+ days to expiry) behave near baseline.",
        ["weekday/cycle effects are weak", "weekly expiry structure is recent"],
    ),
    "low_dte_late_week": (
        "EXPIRY_CYCLE",
        "Late-cycle sessions (<=1 day to expiry) behave near baseline.",
        ["weekday/cycle effects are weak", "expiry-day pinning is intraday"],
    ),
}


def _regime_context(regime_report):
    interp = regime_report.get("interpretation", {})
    return {
        "mix": {k: v["n"] for k, v in interp.items()},
        "note": "regime mix over the observation window (A=calm, B=stressed, C=high-vol)",
    }


_TIER = {"HIGH": 4, "MEDIUM": 3, "LOW": 2, "NOT_RELIABLE": 1}


def _rank_behaviors(behaviors):
    """Reliability first, then magnitude of deviation from baseline."""
    ranked = []
    for b in behaviors:
        cb = b["conditional_behavior"]["fwd_5d"]
        bl = b["baseline"]["fwd_5d"]
        if not cb or not bl:
            continue
        delta = cb["mean"] - bl["mean"]
        tier = _TIER.get(b["confidence"], 1)
        ranked.append((b, tier, abs(delta), cb["n"]))
    ranked.sort(key=lambda t: (-t[1], -t[2], -t[3]))
    return ranked


def _rank_key(t):
    return (-t[1], -t[2], -t[3])


def build_questions(behavior_report, regime_report):
    ranked = _rank_behaviors(behavior_report["behaviors"])
    questions = []
    used = set()
    for b, tier, delta, n in ranked:
        name = b["condition"]
        if name not in FAMILY_MAP or len(questions) >= MAX_QUESTIONS:
            continue
        if name in used:
            continue
        used.add(name)
        family, hypothesis, failures = FAMILY_MAP[name]
        required = _required_features(family)
        questions.append({
            "question_id": f"RQ-{len(questions) + 1:02d}",
            "observation": b["observation"],
            "observed_frequency": b["frequency"],
            "observed_n": b["n_sessions"],
            "confidence": b["confidence"],
            "market_context": _regime_context(regime_report),
            "hypothesis": hypothesis,
            "required_data": required,
            "candidate_family": family,
            "expected_failure_modes": failures,
            "n_hypotheses_budget": MAX_HYPOTHESES_PER_QUESTION,
        })
    return questions


def _required_features(family):
    base = ["nifty_close", "vix_close", "vix_rank_252", "nifty_20d_hv",
            "nifty_ret_5d", "pcr_oi", "dte", "expiry_day"]
    extra = {
        "OI_BUILDUP": ["oi_total_growth_5d", "oi_total"],
        "PCR_CONTRA": ["pcr_oi", "pcr_oi_chg"],
        "VOL_EXPANSION": ["atm_premium_pct", "vix_zone"],
        "VOL_CONTRACTION": ["atm_premium_pct", "vix_zone"],
        "INSTITUTIONAL_FLOW": ["fii_oi_share", "fii_oi_share_chg_5d"],
        "MAX_PAIN_REVERT": ["max_pain_dist_pct", "max_pain_strike"],
        "GAP_BOUNCE": ["nifty_gap_pct"],
        "EXPIRY_CYCLE": ["dte", "expiry_day"],
        "TREND_FOLLOWING": ["nifty_ret_5d", "nifty_ret_20d", "nifty_trend_20d"],
        "MEAN_REVERSION": ["nifty_ret_5d", "nifty_ret_20d"],
        "REGIME_SWITCH": [],
    }
    return sorted(set(base + extra.get(family, [])))


def write_questions(questions):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    doc = {
        "phase": "I.3",
        "budget": {"max_questions": MAX_QUESTIONS,
                   "max_hypotheses_per_question": MAX_HYPOTHESES_PER_QUESTION,
                   "max_ai_proposals": MAX_QUESTIONS * MAX_HYPOTHESES_PER_QUESTION},
        "questions": questions,
    }
    with open(QUESTIONS_PATH, "w") as fh:
        yaml.safe_dump(doc, fh, sort_keys=False, default_flow_style=False)
    return QUESTIONS_PATH


if __name__ == "__main__":
    import research_feature_engine as FE
    import research_regime_discovery as RR
    import research_behavior_engine as BE
    panel, meta = FE.build_panel()
    regime, _ = RR.discover_regimes(panel, meta)
    behavior, _ = BE.discover_behaviors(panel, meta)
    qs = build_questions(behavior, regime)
    print(json.dumps([{k: v for k, v in q.items() if k != "market_context"} for q in qs], indent=2))
