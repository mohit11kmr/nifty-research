# Phase I.3 — Regime-Aware Research Discovery (Audit Report)

**Experiment id:** `phase_i3_regime_aware_research_discovery_v1`
**Date:** 2026-08-16
**Status:** COMPLETED — Stage 1 (features/regimes/behaviors) and Stage 2
(questions/screens) run in full; Stage 3 ran as a **CONTROLLED AI run**
(12 bounded proposals across the highest-conviction questions, screens, full
research). No auto-promotion, no live trading, no modification of frozen
artifacts.

---

## 1. Objective

Phase I.3 discovers **regime-aware research questions** and **AI-generated
strategy proposals** over the frozen unified dataset (646 sessions,
2024-01-01..2026-08-13). It builds, from scratch, a deterministic discovery
pipeline: feature panel → regime classification → behavior library →
conviction-ranked research questions → AI packets → bounded AI proposal
generation → fast screens → full research backtests with the canonical cost
model → audit + final response.

All writes are confined to `results/phase_i3/`, `data/research_cache/`,
`strategy_research_memory/phase_i3_memory.jsonl`, `audit/`, `tests/` (spec
hard rules). No file under `strategies/`, `ground_truth.db`,
`paper_account.json`, the control/Range-HV engines, `cost_model.py` or the
unified dataset was modified.

## 2. Dataset integrity (spec 4)

Frozen manifest `data/historical/manifests/unified_research_dataset.json`
verified: every file sha256, `calendar_hash` and `stable_content_hash` matches
on-disk data (`verify_integrity` passes). 646 trading sessions, zero missing
dataset days.

**Data artifact discovered and handled:** the bhavcopy source stores the
**underlying close** in `settle_price` for expiring contracts on their expiry
date (verified against raw CSV row
`2024-01-18,NIFTY,OPTIDX,2024-01-18,21550.0,CE,...,settle_price=21462.25`
while `close=0.2` ≈ intrinsic). The research runner marks such rows from
`close` instead (`Contract.mark`), so expiry-day exits are not corrupted.
The feature panel is unaffected (near-expiry chain excludes the expiring
contract by construction).

## 3. Resource profile (spec 6)

`research_resource_manager` detected 4 cores / 7.6 GiB RAM / 27 GiB free disk.
Workers = cores−1, RAM target 0.60. The 354 MB options CSV drives a ~31 s
`load_context`; the stage-3 worker model was therefore changed to **one
subprocess per packet** so a long-lived parent never accumulates the options
chain in RAM across 12 backtests (the first monolithic run died mid-way with
no traceback — consistent with cumulative-memory pressure on this box; the
per-packet workers are memory-isolated and each writes a debuggable log).

## 4. Stage 1 — features / regimes / behaviors / questions

### Feature panel
`(646 × 45)` panel, `feature_version` hashed from registry; warm-up NaNs only
in the first ~50 sessions (verified by leakage probe and no-future-NaN check).
Two construction bugs fixed during development:
- `_chain_agg` now aggregates **near-expiry only** (was: all expiries, which
  inflated `atm_premium_pct`);
- `pcr_oi` corrected to put-OI / call-OI (was inverted).

### Regimes (deterministic k-means, k=3, seed 42, n_init=10)
| Regime | n | mean VIX | mean HV20 | mean 20d ret | mean PCR | atm prem % |
|--------|---|----------|-----------|--------------|----------|------------|
| REGIME_A (calm) | 377 | 12.5 | 0.10 | +1.1% | 0.93 | 0.46 |
| REGIME_B (stressed) | 175 | 16.9 | 0.10 | −2.8% | 0.75 | 0.73 |
| REGIME_C (high-vol) | 94 | 17.1 | 0.20 | +3.6% | 0.97 | 0.64 |

94 regime transitions recorded; transition matrices and after-transition
forward returns are **evaluation-only** (never features).

### Behaviors (19; forward returns are evaluation, not features)
Highest signal-to-noise observations:
- `gap_reversal_down` (gap < −0.5%): n=59, fwd5 mean **+0.75%** vs +0.11% baseline
- `trend_follow_down_5d` (ret5 < −2%): n=84, fwd5 **+0.58%** vs +0.11%
- `atm_expensive`: n=130, fwd5 **+0.58%** vs +0.11%
- `vix_panic` (VIX>25): n=7, fwd5 +4.3% — **NOT_RELIABLE** (n<20), kept as context
- `max_pain_above_spot`: n=464, fwd5 +0.14% vs +0.11% — HIGH confidence, near-noise
  edge → the packet is explicitly framed as a **null test**.

### Questions (12, budget-respecting)
RQ-01..RQ-12 ranked reliability-tier-first (HIGH→MEDIUM→LOW→NOT_RELIABLE,
then |Δ| vs baseline) → `results/phase_i3/research_questions.yaml` and
`stage1_report.json`. No behaviour is silently dropped; low-n conditions stay
visible with their NOT_RELIABLE confidence.

## 5. Stage 2 — AI packets (12)

`results/phase_i3/ai_packets/PK-RQ-01.yaml..PK-RQ-12.yaml` — OBSERVED /
INFERRED / HYPOTHESIS separation, gates (registered features, supported
families, canonical cost model, EOD, point-in-time safety),
`generation_instructions`. Each packet also embeds the observed evidence so
the AI generator has no need to re-derive it.

## 6. Stage 3 — CONTROLLED AI run (spec 25/32/34)

Budget enforced: 12 proposals (≤ MAX_PROPOSALS=24), ≤1 hypothesis per packet.
Each packet sent to an isolated `opencode run --model opencode/big-pickle
--pure` subprocess; raw outputs frozen under `results/phase_i3/ai_proposals/
raw/`; every proposal fast-screened (schema/risk/data/expiry/execution/
sample-size) then fully researched (canonical costs, dev ≤2026-02-28,
OOS ≥2026-03-01, sample buckets, concentration, regime robustness,
deterministic `result_hash` + reproducibility re-run).

| packet | family | screen | status | n | net | OOS | conc / regime |
|--------|--------|--------|--------|----|-----|-----|---------------|
| PK-RQ-01 | MAX_PAIN_REVERT (IC) | SCREENED_IN | RESEARCHED | 285 | −263 036 | MEASURED | BALANCED / MULTI |
| PK-RQ-02 | EXPIRY_CYCLE | REJECT | — | — | — | — | STRADDLE ⊄ EXPIRY_CYCLE |
| PK-RQ-03 | GAP_BOUNCE (CALL) | SCREENED_IN | RESEARCHED | 43 | +23 591 | INSUFFICIENT | HIGH_CONC / MULTI |
| PK-RQ-04 | VOL_CONTRACTION | REJECT | — | — | — | — | screen |
| PK-RQ-05 | MEAN_REVERSION | — | REJECTED | — | — | — | SCHEMA_ERROR |
| PK-RQ-06 | VOL_EXPANSION | — | REJECTED | — | — | — | SCHEMA_ERROR |
| PK-RQ-07 | GAP_BOUNCE | — | REJECTED | — | — | — | SCHEMA_ERROR |
| PK-RQ-08 | VOL_EXPANSION (STRADDLE) | SCREENED_IN | RESEARCHED | 94 | −600 624 | MEASURED | BALANCED / MULTI |
| PK-RQ-09 | INSTITUTIONAL_FLOW | LOW_FREQUENCY | RESEARCHED* | 19 | −39 160 | INSUFFICIENT | SAMPLE_TOO_SMALL |
| PK-RQ-10 | TREND_FOLLOWING | — | REJECTED | — | — | — | SCHEMA_ERROR |
| PK-RQ-11 | OI_BUILDUP | — | REJECTED | — | — | — | SCHEMA_ERROR |
| PK-RQ-12 | EXPIRY_CYCLE | REJECT | — | — | — | — | screen |

\* PK-RQ-09 correctly kept its LOW_FREQUENCY label through the full research
stage (19 trades < 20 → **NOT_RELIABLE**), per the sample-size policy — it is
not silently dropped.

### Honest outcomes (no overfitting, no promotion)
- **PK-RQ-01** max-pain-revert iron condor: 285 trades, 32% win, PF 0.54,
  net **−263 K** after costs. The null hypothesis (max pain does not give a
  reversion edge) **holds** — recorded as negative knowledge.
- **PK-RQ-03** gap-bounce long call: 43 trades, net **+23.6 K** but
  **OOS_INSUFFICIENT** (only 9 OOS trades) and HIGH_CONCENTRATION (top3% > 50%)
  → *not reliable*, kept as a candidate for future paper testing, not promoted.
- **PK-RQ-08** VIX<12 long straddle: 94 trades, PF 0.5, net **−600 K** — long
  gamma bleeds theta; confirms "sellers win, buyers bleed".
- **PK-RQ-09** FII-share-rising long call: n=19, **NOT_RELIABLE**, net −39 K.

5 proposals failed YAML parse (SCHEMA_ERROR) and 3 failed screen — all recorded
with structured reasons in `results/phase_i3/discovery_report.json` and the
append-only research memory. Result hashes were deterministic (re-run of
already-researched packets reused identical `result_hash`).

## 7. Hard rules compliance

- No live trading / auto-promotion / optimization loop / arbitrary AI code.
- No modification of `strategies/`, `ground_truth.db`, `paper_account.json`,
  control or Range-HV engines, `cost_model.py`, expiry semantics, or any
  frozen Phase I/F/H artifact.
- Writes confined to the allowed paths (above). Deterministic re-runs.
- Budget respected (12 ≤ 24 proposals, 12 questions, 1 hypothesis/packet).
- Sample-size policy enforced (<20 → NOT_RELIABLE / OOS_INSUFFICIENT).

## 8. Regression note (pre-existing, unrelated)

`tests.test_phase_i_research` (Phase I.1) fails its data-gate: the Phase I
example proposals embed the **pre-unified** manifest hash (`ff068e6d…`) which
no longer matches the current unified manifest (`df7dd65f…`). This predates
Phase I.3 (unified dataset refresh) and is outside Phase I.3 scope; frozen
Phase I proposals are not modified. The unified-data alignment suite
(`test_unified_data_alignment`, 33 tests) and the new Phase I.3 suite
(26 tests) pass. Phase I.3 regression: all modules import and the full
pipeline re-runs deterministically.

## 9. Deliverables

- Pipeline: `research_resource_manager.py`, `research_dataset.py`,
  `research_cache.py`, `research_checkpoint.py`, `research_feature_registry.py`,
  `research_feature_engine.py`, `research_regime_discovery.py`,
  `research_behavior_engine.py`, `research_memory.py`,
  `research_question_engine.py`, `research_ai_packet.py`,
  `research_conditions.py`, `research_screener.py`, `research_runner.py`,
  `ai_phase_i3_discovery.py`.
- Tests: `tests/test_phase_i3_research_discovery.py` (26 tests, OK).
- Outputs: `results/phase_i3/{stage1_report,stage2_report,discovery_report}.json`,
  `research_questions.yaml`, `ai_packets/PK-*.yaml`,
  `ai_proposals/PK-*.yaml` + `raw/`, `proposal_research/PK-*.json`,
  `checkpoints/checkpoints.jsonl`.
- Memory: `strategy_research_memory/phase_i3_memory.jsonl` (observations,
  tests, negative knowledge).
- This audit + final response (§39).

## 10. Suggested next steps (human decision)

1. Paper-test the gap-bounce long-call family (PK-RQ-03) with a longer OOS
   window and wider strike band — but note HIGH_CONCENTRATION.
2. Do NOT trade long VIX<12 straddles or max-pain iron condors: the evidence
   is negative after costs.
3. Re-run the five SCHEMA_ERROR packets with a stricter prompt/schema contract
   if more AI proposals are desired within budget.
