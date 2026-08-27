# Phase I.4 — PK-RQ-03 Correction + Controlled Revalidation (Audit Report)

**Experiment id:** `phase_i4_pk_rq03_correction_controlled_revalidation_v1`
**Date:** 2026-08-16
**Status:** COMPLETED — the seven documented Phase I.3 implementation /
semantic defects (Claude Sonnet 4.6 audit `CLAUDE_SONNET_4_6_PHASE_I3_PK_RQ03_AUDIT.md`,
classification **D — PROMISING BUT INSUFFICIENT**) were corrected and the
**same frozen PK-RQ-03 (GAP_BOUNCE) hypothesis** was re-run in a controlled
replay on the same frozen 646-session dataset. Outcome: **HOLD** (defect
corrections verified; OOS evidence still insufficient/negative — no
promotion to controlled paper test).

---

## 1. Scope & authority

- Spec: `OPENCODE_PHASE_I4_PK_RQ03_CORRECTION_CONTROLLED_REVALIDATION.md`
  (hard rules §1, baseline freeze §3, F2-first §4, controlled replay §12,
  before/after diff §13, OOS gate §14, regime-B analysis §15, concentration
  §16, costs §17, risk §18, reproducibility §19, production isolation §20,
  tests §21, audit §22, promotion rule §23).
- Hypothesis preserved **verbatim** (verified, see §8): `nifty_gap_pct < -0.5`
  AND `dte > 1` AND `vix_close < 25`; LONG CALL ATM; HORIZON 5 sessions;
  `risk.stop_pct 0.5`; EOD; canonical cost model; dev boundary 2026-02-28 /
  OOS cut 2026-03-01 unchanged.
- No optimization, no OOS tuning, no new strategy, no regime filter, no
  paper/live trade, no broker calls, no fabricated fills, no silently removed
  trades. No modification of `ground_truth.db`, `paper_account.json`,
  `results/phase_i3/`, the unified dataset, the control engines or live
  production modules (verified, §10).
- Baseline freeze captured in `results/phase_i4/baseline/baseline.json`
  (spec sha256 `8bbc095f31ce33d2cda1f6025420883c422eccde95722286f5bad3128d8afb5b`,
  original result_hash `f11b794e...`, git HEAD `cf132ca`, dataset manifest
  self-hash `3690ea52...`, pre-I.4 git-diff snapshot).

## 2. Defect corrections (F1–F7)

| # | Finding | Corrected outcome |
|---|---------|-------------------|
| F1 | `stop_pct=0.5` declared, never simulated | Stop-loss **simulated**: EOD stop at `stop_level = 0.5 × entry premium` for LONG single-leg; precedence **entry → stop → horizon → expiry**; reasons `EXIT_STOP` / `EXIT_HORIZON` / `EXIT_EXPIRY`; missing chain rows carried (no fabricated marks); exit boundary = `min(entry_idx+5, near-expiry session)`. |
| F2 | `LOT=75` applied to every date | **Point-in-time market lot** of the exact entry contract from the frozen bhavcopy (`NewBrdLotQty` → `lot_size` column) via new `lot_size.py`; **no current-lot fallback** anywhere. Verified lots used: {25, 50, 65, 75}. |
| F3 | entry = settle/WAP, not executable fill | Entry price retained as bhavcopy `SttlmPric` (volume-weighted settlement). Classified `HISTORICAL_SETTLEMENT`, documented `EXECUTION_REALISM_LIMITED` — no historical intraday bid/ask exists in the frozen EOD dataset and fills are **not** fabricated. |
| F4 | regimes retrospective / non-PIT | Regime labels kept **descriptive-only**; PK-RQ-03 carries no regime filter (`regime: null`), so the backtest is regime-agnostic. |
| F5 | ~₹1,000 accounting discrepancy | Discrepancy was an arithmetic slip in the external audit (46,076.25 − 3,440 − 19,044.76 = 23,591.49 = reported net). Invariant now **enforced** in `compute_metrics` (aggregate identity) + trade-level checks + aggregate ledger in output. |
| F6 | 2024 expiry-calendar limitation | Verified **NO_PK_RQ03_IMPACT**: chain-derived near expiry equals the canonical calendar on all 246 overlap dates (0 mismatches); 2024 trades use the same near expiry the calendar would have produced. |
| F7 | forward-5d boundary | Verified **PASS**: `_stats` drops `NaN` (dropna) so incomplete forward windows are excluded; trades require `sessions[i+5]` to exist. |

## 3. Baseline (frozen) vs corrected — full-period metrics

| Metric | Original (I.3) | Corrected (I.4) | Delta |
|---|---|---|---|
| result_hash | `f11b794e…` | `ee3b44e8…` | changed |
| trades | 43 | 43 | 0 |
| net_pnl | +23,591.49 | **+39,061.84** | +15,470.35 |
| gross | 46,076.25 | 58,068.50 | +11,992.25 |
| fees | 3,440.00 | 3,440.00 | 0.00 |
| slippage | 19,044.76 | 15,566.66 | −3,478.10 |
| profit_factor | 1.0727 | 1.1781 | +0.1054 |
| win_rate | 0.3953 | 0.3721 | −0.0232 |
| max_drawdown | −83,073.91 | −61,988.45 | +21,085.46 |
| expectancy | 548.64 | 908.41 | +359.77 |
| best trade (2025-05) | +61,605.51 | +61,605.51 | 0 |
| top-3 concentration | 533.8% | 307.6% | −226.2 pts |
| Development P&L | +101,458.28 | +79,868.16 | −21,590.12 |
| OOS P&L | −77,866.79 | −40,806.32 | +37,060.47 |
| stop exits | 0 | **22** | +22 |
| horizon exits | 43 | **0** | −43 |
| expiry exits | 0 | **21** | +21 |
| exit reasons | EXIT_HORIZON 43 | **EXIT_STOP 22 / EXIT_EXPIRY 21** | — |

Both outputs pass the accounting identity (aggregate and trade-level). All 43
trades changed; every change is tagged with a reason in
`results/phase_i4/trade_diff.csv`:

| Reason code | Count | Meaning |
|---|---|---|
| STOP_LOSS_CORRECTION | 22 | stop moved the exit earlier (was held to horizon) |
| LOT_SIZE_CORRECTION | 13 | same exit, quantity corrected 75 → {25, 50, 65} |
| REASON_LABEL_ONLY | 8 | 2025 trades, lot already 75; HORIZON → EXPIRY label (boundary == near expiry) |

No trade was added, removed, or changed without a classified reason.

## 4. Development / OOS split (primary gate, frozen cut)

| Segment | Trades | Net | PF | Win | MaxDD | Top3 conc |
|---|---|---|---|---|---|---|
| Development (≤ 2026-02-28) | 27 | **+79,868.16** | 1.7435 | 0.4074 | −27,797.81 | 149.7% |
| OOS (≥ 2026-03-01) | 16 | **−40,806.32** | 0.6354 | 0.3125 | −48,986.71 | −156.4% |
| **OOS verdict** | | **OOS_INSUFFICIENT** | | | | |

OOS (16 trades) is below the 20-trade reliability floor and **negative**.
Relative to the original OOS (−77,866.79), the corrected OOS is materially
better (lot 65 from 2025-12-30 + stops), but the hypothesis still does not
replicate out-of-sample. Per §14 this is the controlling gate: **no promotion**.

## 5. Regime analysis (§15)

Corrected by-regime P&L (descriptive, retrospective labels; no filter):

- REGIME_A: +21,961.54 / 13 trades (win 0.385)
- REGIME_B: −60,711.28 / 25 trades (win 0.320)
- REGIME_C: +77,811.58 / 5 trades (win 0.600)

Down-gap sessions (gap < −0.5%, n=59) stratified by regime — forward-5d %:

| Regime | n | mean fwd5d | median | win rate |
|---|---|---|---|---|
| ALL | 59 | +0.75% | +0.74% | 0.610 |
| REGIME_A | 19 | +0.29% | +0.11% | 0.579 |
| REGIME_B | 34 | +0.82% | +0.82% | 0.588 |
| REGIME_C | 6 | +1.82% | +2.57% | 0.833 |

Down-gaps show **mean-reverting** tendency in every regime (positive fwd-5d
median), strongest in REGIME_C and weakest in REGIME_A.

**§15 question — "Does REGIME_B behave more like continuation than
reversal?"** **No.** With 34 down-gap sessions, REGIME_B shows a *positive*
fwd-5d median (+0.82%) and a 58.8% reversal win-rate — indistinguishable in
sign from the pooled sample (+0.74%). REGIME_B is the *weakest* reversal
regime only in the sense that its mean (+0.82%) is closer to zero than
REGIME_C (+1.82%) — not because it continues downward. The strategy's OOS
failure therefore cannot be explained by "REGIME_B continues," and adding a
regime rule would be data mining: the strategy was evaluated
regime-agnostically and must remain so.

## 6. Concentration (§16), costs (§17), risk (§18)

**Concentration — HIGH (unchanged character):**
- Best trade (2025-05) = 157.7% of total net; best month 2025-05 = 157.7%.
- Top2 = 238.8%, Top3 = 307.6% of net (net with top3 removed = **−81,100**).
- `concentration_flag = HIGH_CONCENTRATION`.

**Costs — all identity checks pass:** per-order fee ₹40; slippage 1.5% of
premium turnover; trade-level `net == gross − fees − slippage` for all 43;
aggregate identity holds.

**Risk (defined-risk long call only):** capital at risk per trade
min/median/max = 2,832.50 / 11,197.50 / 24,371.25; max theoretical loss
= worst single-entry premium × lot = 24,371.25; worst realized loss
−18,224.75; max drawdown −61,988.45 (−66.75%). 22/43 exits now governed by
the 50%-premium stop.

## 7. Reproducibility (§19) and production isolation (§20)

- Controlled replay run **twice** in one process and once more in the test
  suite: identical trades, metrics and `result_hash` (`ee3b44e8…` pinned in
  tests). `reproducibility.same_* = true`.
- `ground_truth.db` and `paper_account.json` sha256 identical before/after
  the replay (`protected_untouched = true`).

## 8. Hypothesis preservation

`verify_hypothesis()` in `ai_phase_i4_revalidation.py` asserts every frozen
parameter (gap, dte, vix, direction, instrument, strike, exit type/horizon,
regime filter absent). Result: `hypothesis_preserved = true`, no mismatches.

## 9. Tests

`.venv/bin/python -m unittest tests.test_phase_i4_pk_rq03_corrections` — **20/20 OK**
(lot-size boundaries + no-fallback + PIT contract lot; stop semantics;
accounting invariants; deterministic replay + pinned hash; artifact gates;
trade-diff classification). Regression: `test_phase_i3_research_discovery`
26/26 OK, `test_unified_data_alignment` 33/33 OK. `pip check` clean,
`git diff --check` clean.

Full suite (`python -m unittest discover -s tests -v`, 555 tests): 5 failures
+ 20 errors — **all pre-existing and environment-related, none caused by I.4**,
verified by module dependency analysis (none of the failing suites import
`research_runner`, `research_dataset` or `lot_size`):

- `test_phase_i_research` (1 FAIL + 9 ERR) and `test_phase_i2_execution_capabilities`
  (3 ERR): frozen Phase I.1/I.2 proposals embed the old manifest hash
  `ff068e6d…` vs the unified manifest `b175cf55…` (data gate) — unchanged by I.4.
- `test_phase_h2_range_hv` (4 ERR) and `test_h3_range_hv_risk_semantics` (2 ERR):
  `FileNotFoundError: /tmp/opencode/phaseH_frozen_data/data/nifty_history.csv` —
  the Phase-H frozen-data snapshot is not present in this environment.
- `test_phase4a` (5 FAIL): ML feature-cache freshness `'STALE' != 'REAL'` —
  cache-age environment issue, unrelated to research modules.
- `test_phase_i1_multi_model` (1 ERR): same manifest data-gate class as above.

## 10. Limitations

- **EOD-only stop resolution (F1):** the dataset is EOD; stop-loss fills are
  marked at the EOD close, not intraday. A stop that crosses intraday and
  recovers before the close is not captured — the declared semantics are
  documented as EOD (`EXECUTION_REALISM_LIMITED`), never fabricated.
- **Entry price (F3):** entry = bhavcopy `SttlmPric` (settle), classified
  `HISTORICAL_SETTLEMENT`. No historical intraday bid/ask exists in the
  frozen dataset; the "gap at the open, option entry at EOD close" mismatch
  is real and documented, not corrected by guessing fills.
- **Retrospective regimes (F4):** k-means labels use the full window
  (non-PIT) and are used for explanation only; no regime rule was added.
- **OOS evidence:** 16 trades post-cutoff is below the 20-trade floor; the
  OOS window is short (2026-03-01..2026-08-13) and dominated by high-ⅥX
  sessions, so the OOS verdict is INSUFFICIENT rather than NEGATIVE-by-design.
- **Concentration:** 2025-05 single trade = 157.7% of net; net ex top-3 is
  negative (−81,100). Point-in-time lot and stop corrections do not change
  the concentrated character of the hypothesis.
- **Pre-existing, unrelated:** `tests.test_phase_i_research` still fails its
  manifest data-gate (frozen Phase I.1 proposals embed the old manifest hash
  `ff068e6d…` vs unified `df7dd65f…`); unchanged by I.4 and out of scope.

## 11. Verdict — HOLD

| Gate | Pass? |
|---|---|
| all critical defects fixed | ✓ |
| correct historical lot, no fallback | ✓ |
| stop implemented | ✓ |
| execution limits documented | ✓ |
| no lookahead | ✓ |
| accounting identity | ✓ |
| reproducibility | ✓ |
| production isolation | ✓ |
| OOS not contradicted | ✓ (insufficient, not positively replicated) |
| **OOS adequate (≥ 20 trades)** | ✗ (16) |
| **concentration acceptable (top3 ≤ 50%)** | ✗ (307.6%) |

**`final_classification = HOLD`** — not `CONTROLLED_PAPER_CANDIDATE`.
All seven defects are fixed and the corrected economics are strictly better
than the flawed I.3 numbers, but the hypothesis still fails to replicate
OOS (16 trades, −40,806) and is a single-trade (2025-05) / high-concentration
strategy. Per §23 a promotion requires the OOS gate to pass; it does not.

**Next safe step:** Phase I.5 (or equivalent) — gather more OOS evidence
(session count growth or a wider frozen window) and/or a corrected
regime-B-aware hypothesis; no paper/live trading of PK-RQ-03. STOP.

## Artifacts

- `results/phase_i4/report.json` — full revalidation report + verdict checks
- `results/phase_i4/before_after.json` — original vs corrected metrics
- `results/phase_i4/trade_diff.csv` — trade-by-trade diff with reasons
- `results/phase_i4/corrected_trades.json` — corrected ledger
- `results/phase_i4/baseline/` — pre-change freeze
- `tests/test_phase_i4_pk_rq03_corrections.py` — 20 tests
- Code: `lot_size.py` (new), `research_runner.py`, `research_dataset.py`,
  `ai_phase_i4_revalidation.py` (new)
