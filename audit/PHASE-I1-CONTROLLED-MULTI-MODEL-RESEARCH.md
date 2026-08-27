# Phase I.1 — Controlled Multi-Model Strategy Research (Audit Report)

**Experiment id:** `phase_i1_controlled_multi_model_v1`
**Date:** 2026-08-16
**Status:** COMPLETED — findings preserved for human review; no auto-promotion.

---

## 1. Objective

Measure whether three AI models — **Big Pickle**, **DeepSeek (deepseek-chat)**,
**Qwen Coder (qwen3-coder)** — produce genuinely useful, non-duplicate,
researchable strategy hypotheses when given the *identical* research prompt
and run through the *existing* Phase I deterministic gates.

This is a **research-quality experiment only**. It is not a strategy
generator and not a trading system. All outputs are immutable, all
evaluations go through existing gates (no bypass), and no production write
or broker call is made.

## 2. Method (spec sections 4-21)

- **Canonical prompt** (frozen, sha256
  `6745b9d47f23f580ee29e003f8502c3fb0745a99d9f86cf882186efd966aec13`,
  copy stored at `strategy_proposals/phase_i1/canonical_prompt_v1_used.md`):
  one prompt with `<<SLOT>>` / `<<CATEGORY>>` placeholders, expanded
  deterministically and byte-identically for all models per slot.
- **Models × slots:** 3 models × 3 slots = 9 budgeted proposals
  (slot A DIRECTIONAL, slot B MEAN REVERSION / RANGE, slot C DEFINED RISK
  STRUCTURE). Generation: isolated `opencode run --model <id> --pure`
  subprocess per slot; raw output frozen before any evaluation.
- **Fixed environment:** manifest hash
  `ff068e6d54094f696ce02ea357503251fb0ce973b286fcaa4f357bedbd7fa57a`,
  window `2025-08-13..2026-08-13`, dev/OOS cut `2026-03-01`, min trades 20,
  cost ₹40/order + 1.5% slippage, lot 75.
- **Pipeline:** freeze raw → parse → hash → validate (schema/data/risk gates)
  → dedupe (exact + semantic near-dup) → backtest x2 with equal result_hash
  (engine-registered ids only) → baseline → transparent model metrics →
  human review table.

## 3. Generation status

| model | p1 | p2 | p3 |
|---|---|---|---|
| big_pickle | generated + valid | generated + valid | generated + valid |
| deepseek | generated + valid (hardened YAML extractor) | generated + valid | generated + valid |
| qwen | **MODEL_UNAVAILABLE** | MODEL_UNAVAILABLE | MODEL_UNAVAILABLE |

Qwen was unreachable through the controlled harness: opencode's CLI requests
`max_tokens=32000` for qwen3-coder (models.dev metadata), but the OpenRouter
account balance only affords ~18.2k tokens per request. Config overrides
(`maxTokens`, `maxOutputTokens`, `provider.models.<id>.limit.output`,
custom alias model) were all verified ineffective in the `opencode run`
path. Per spec §3 the model was declared unavailable and the experiment
continued with the available models; no credits were purchased. The supplier
error output is preserved at
`strategy_proposals/phase_i1/raw/qwen_p1_openrouter_max_tokens_error.txt`.

## 4. Validation + dedupe results

All 6 generated proposals passed **every** Phase I gate
(`validation_status=VALIDATED`, `failure=None`). One expected warning on
big_pickle_p1: EXPIRY_CALENDAR coverage PARTIAL (400 sessions outside
calendar coverage).

| proposal | strategy_id | classification |
|---|---|---|
| phase_i1_big_pickle_p1 | trend_pullback_call_v1 | UNIQUE |
| phase_i1_big_pickle_p2 | range_fade_stretch_v1 | UNIQUE |
| phase_i1_big_pickle_p3 | maxpain_brokenwing_condor_v1 | UNIQUE |
| phase_i1_deepseek_p1 | trend_breakout_v2 | UNIQUE |
| phase_i1_deepseek_p2 | range_hv_condor_v1 | UNIQUE |
| phase_i1_deepseek_p3 | trend_breakout_condor_v1 | UNIQUE |

**Zero exact/near duplicates across the 6 proposals.** The two models chose
different strategy families within the same slot categories (e.g. slot A:
pullback-continuation vs breakout; slot C: broken-wing condor vs trend
breakout condor), so there is no copycat behavior between models.

## 5. Backtest status

Backtests completed: **0**. All 6 proposals declare novel strategy ids that
are not engine-registered
(`current_control_v1`, `directional_spread_v1`, `range_hv_iron_condor_v1`),
so they reached `EXECUTION_UNSUPPORTED` (recorded, reviewed on research
quality). This is the documented platform reality of frozen engines executing
their own logic: only faithful re-declarations would be backtestable, and
those are duplicates by construction.

## 6. Model aggregation (transparent; no P&L-only ranking)

| metric | big_pickle | deepseek | qwen |
|---|---|---|---|
| proposals submitted | 3 / 3 | 3 / 3 | 3 / 3 |
| proposals valid (validation_pass_rate) | 3 (1.0) | 3 (1.0) | 0 (0.0) |
| unique rate | 1.0 | 1.0 | 0.0 |
| duplicate rate | 0.0 | 0.0 | 0.0 |
| backtest completion rate | 0.0 | 0.0 | 0.0 |
| average net P&L / PF | n/a | n/a | n/a |

Per spec §15, models are compared on validity, novelty, risk correctness and
data compatibility — **not** on unbacktested P&L claims. No P&L ranking was
produced.

## 7. Human review table (spec section 21) — machine draft only

All 9 rows carry `review_status: PENDING_REVIEW`. Machine draft:

- 6 × `REQUEST MORE DATA` (VALIDATED + EXECUTION_UNSUPPORTED — no
  deterministic engine available).
- 3 × `REJECT` (MODEL_UNAVAILABLE — no proposal produced).

No row was auto-promoted to `CONTROLLED PAPER CANDIDATE`. Promotion requires
a human decision recorded via the review workflow.

## 8. Key findings

1. **Both available models are structurally compliant**: 6/6 proposals pass
   the full existing gate stack (schema, data, risk) without a single error.
2. **No cross-model plagiarism**: all 6 proposals are UNIQUE; the two models
   independently invented distinct hypotheses in each slot category.
3. **Novelty costs backtestability**: every novel strategy id is
   `EXECUTION_UNSUPPORTED`. The engine-backed trio is the only backtestable
   set, and re-declaring it is a duplicate. This is an honest, structural
   outcome of the platform, not a model failure.
4. **Model comparison is incomplete by design**: with 0 backtests and 1 of 3
   models unavailable, there is **no evidence of any model advantage**.
   Verdict: **INSUFFICIENT EXPERIMENT** for ranking models; the 6 hypotheses
   are preserved for human review.

## 9. Disclosed limitations

- **Prompt seeding defect:** the schema skeleton in the frozen prompt shows
  `parent_strategy_id: current_control_v1` as an example value. All 6
  proposals echoed it. The leak was **symmetric across models** (no model
  advantage), but it weakens novelty independence and is disclosed rather
  than hidden. The prompt is intentionally left immutable so the frozen
  outputs remain reproducible under the exact prompt that produced them; a
  future Phase I.2 must use a new canonical prompt file with a neutral
  placeholder.
- **Qwen unavailable** due to OpenRouter credit pre-authorization (see §3);
  config-level max_tokens reduction does not work in the `opencode run` path.
- **Freeze re-invocation verified:** a killed big_pickle p3 run (bash timeout)
  could not overwrite the already-frozen raw; `_freeze_write` refuses content
  changes, and re-running generation on a frozen raw returns
  `generated_now=False` without invoking the model.

## 10. Verification

- `tests/test_phase_i1_multi_model.py`: 27 tests OK (prompt isolation,
  dedupe, freeze discipline, extraction, constants, artifacts, evaluation,
  deterministic reruns, aggregation, review discipline, no-production-writes,
  no-broker-calls).
- `tests.test_phase_i_research`: 13 tests OK (existing pipeline unaffected).
- Evaluation reruns produce byte-identical eval JSONs (determinism).
- No writes outside `strategy_proposals/phase_i1/` and `results/phase_i1/`;
  no broker or production paths referenced.

## 11. Artifacts

- `prompts/AI_MULTI_MODEL_RESEARCH_V1.md` — canonical prompt (frozen).
- `strategy_proposals/phase_i1/canonical_prompt_v1_used.md` — prompt-as-used.
- `strategy_proposals/phase_i1/raw/*.txt` — 7 immutable raw outputs.
- `strategy_proposals/phase_i1/proposals/phase_i1_*.yaml` — 6 frozen proposals.
- `results/phase_i1/*.eval.json` — 9 evaluation records.
- `results/phase_i1/experiment.json` — experiment provenance + records.
- `results/phase_i1/review_table.json` — human review draft table.
- `ai_multi_model_experiment.py` — experiment runner (generate/evaluate/
  aggregate/review).
- `tests/test_phase_i1_multi_model.py` — verification suite.
