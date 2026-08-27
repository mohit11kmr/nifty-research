# Phase H3 — RANGE-HV Iron Condor: Risk / Contract-Semantics / Measurement Integrity + 646-Session Validation Audit

**Status:** MEASUREMENT ONLY — no strategy mutation, no optimization, no promotion.
**Candidate:** `range_hv_iron_condor_v1` (Candidate C, multi-strategy research).
**Unified dataset:** 646 sessions (2024-01-01 .. 2026-08-13), manifest `data/historical/manifests/unified_research_dataset.json`.
**Frozen snapshot:** `/tmp/opencode/phaseH_frozen_data` (H2 canonical root, 2025-08-13 .. 2026-08-13).
**Report artifacts:** `/tmp/opencode/h3/h3_report.json` (cached baseline) and `/tmp/opencode/h3_full/h3_report.json` (fresh baseline re-run) — byte-identical on every measured section.
**Test module:** `tests/test_h3_range_hv_risk_semantics.py` (20 tests, all green).
**Measurement module:** `phase_h3_risk_semantics.py`.

---

## 1. Objective
Determine whether the frozen Range-HV candidate is internally correct and
economically interpretable BEFORE evaluating it on the unified 646-session
dataset. H3 is a risk/contract-semantics/measurement-integrity phase: it
checks whether what the H2 report *showed* (credits, max losses, risk) is
what the strategy *actually does*, then runs the candidate over the unified
dataset. The strategy, rules, widths, thresholds, expiry selection, stops,
sizing and capital model are ALL immutable. Nothing was swept or re-optimized.

## 2. Frozen Candidate Identity (unchanged from H2)
- **id:** `range_hv_iron_condor_v1`, version 1, lifecycle `BACKTESTED`, `promoted: false`
- **classification:** `PROMISING_BUT_INSUFFICIENT`
- **spec_hash (stable, recomputed this phase):** `56ba02752efc4650efe1d8c88165f3396e3ae10aaa15519d9b13e33a4e0d1adb` — matches H2.
- **Frozen parameters (unchanged):** RANGE_HV gate; VIX 16.0–25.0; iron condor ±2% OTM, 150-pt wings, lot 75; target 50% credit; stop 2.0x credit; TIME exit at expiry−2; costs ₹40/order × 8 orders; slippage 1.5%.

## 3. Data Integrity (unified dataset + frozen snapshot)
- Unified manifest: `trading_sessions = 646`, coverage 2024-01-01..2026-08-13,
  no missing days for nifty/vix/options/participant_oi;
  `calendar_hash = 54965462…`, `expiry_hash = 3abbe4cc…` (identical to the
  expiry hash recorded in the DATA-ALIGNMENT-01 manifest and in H2 §3).
- Frozen-vs-unified price consistency (cross-check in report):
  - NIFTY close: 496 overlapping rows, max deviation **3.5e-6%**.
  - VIX close: 245 overlapping rows, max abs deviation **0.0025** (float noise).
- The frozen snapshot fingerprints (`nifty_history 691bf02d…`, `india_vix 9bd5c22a…`,
  `oi_snapshots dir 5e01e40e…`, etc.) remain byte-identical to H2 records.
- **Conclusion:** unified and frozen data are effectively identical in the
  overlapping window; the unified replay is a faithful evaluation surface.

## 4. H2 Baseline Reproduction (STOP-condition check)
`RangeHVValidator.run_all()` was executed on the frozen snapshot (fresh run,
not cached) and compared against the previously produced
`/tmp/opencode/h3_baseline_repro.json`:

- **6 trades, net +6,248.25, PF 9.693, max DD −587.00** — reproduced exactly.
- Every measured section of the H3 report (contract audit, risk semantics,
  max-loss matrix, 646 replay, H2-vs-H3, regime sensitivity, OOS,
  reproducibility) is **byte-identical** between the cached-baseline run and
  the fresh-baseline run.
- **BASELINE_REPRODUCTION: PASS.** The H2 report is deterministic and
  reproducible; nothing about the engine changed between phases.

## 5. CONTRACT-SEMANTICS BUG: `entry_premium` is the control premium on grade-A days
The H2 trade rows reported `entry_premium` = **167.3** (trade 1) and
**223.55** (trade 4). Direct reconstruction from the unified chain shows the
TRUE condor credits are **68.8** and **51.7**. Root cause located at
`multi_strategy_backtest.py` (~line 583) in `trade_rows`:

```python
"entry_premium": t.get("entry_premium") or s.get("entry_net") or s.get("entry_credit"),
```

- The `rec` for grade-A funnel days carries the CONTROL directional premium
  (`t["entry_premium"]`, e.g. the MODERATE_PUT 24000 PE = 167.3 on 2026-03-04;
  MODERATE_CALL = 223.55 on 2026-04-21). Candidate C is a condor, not a
  directional control, so this field must NOT win for C.
- Trades 2/3/5/6 had `grade = NO_SIGNAL` → `t.get("entry_premium")` is `None`
  → the fallback correctly used `sim.entry_credit` (37.3/45.5/39.55/42.45).
- **Impact:** the H2 "credit (167.3) > wing width (150)" phenomenon is a
  MEASUREMENT ARTIFACT. It is not a real economic structure. It propagates
  into `max_risk_per_share = wing_width − entry_premium`, producing the
  impossible negative max-loss for trades 1 & 4 (−17.30 / −73.55).

### Corrected per-trade contract facts (all legs from chain LTP, no BS fallback used)
| # | Entry | ShortC | LongC | ShortP | LongP | True credit | True max loss/share | True max loss/lot | True risk % of 100k |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-03-04 | 24950 (113.1) | 25100 (73.15) | 24000 (167.3) | 23850 (138.45) | 68.8 | 81.2 | 6,090.00 | 6.09% |
| 2 | 2026-04-08 | 24500 (49.7) | 24650 (30.05) | 23500 (65.4) | 23350 (47.75) | 37.3 | 112.7 | 8,452.50 | 8.45% |
| 3 | 2026-04-15 | 24700 (47.45) | 24850 (24.85) | 23750 (77.5) | 23600 (54.6) | 45.5 | 104.5 | 7,837.50 | 7.84% |
| 4 | 2026-04-21 | 25050 (63.75) | 25200 (35.95) | 24100 (90.5) | 23950 (66.6) | 51.7 | 98.3 | 7,372.50 | 7.37% |
| 5 | 2026-04-28 | 24500 (50.8) | 24650 (30.95) | 23500 (55.3) | 23350 (35.6) | 39.55 | 110.45 | 8,283.75 | 8.28% |
| 6 | 2026-05-05 | 24500 (57.75) | 24650 (33.75) | 23550 (50.3) | 23400 (31.85) | 42.45 | 107.55 | 8,066.25 | 8.07% |

All credits are below the 150-pt wing; all corrected max losses are positive.

## 6. RISK_MODEL_MISMATCH — confirmed (promotion blocker, unchanged)
- Spec declares `max_risk_pct: 1.0`. Measured true risk is **6.09–8.45%** of
  ₹100k capital on every trade.
- The `premium_seller` sizer `units = max(int(capital*risk_pct/max(max_loss,1)), 1)`
  floors to **1 lot** on this capital: the minimum position (1 lot × ₹6–8.5k
  max loss) already exceeds 1%. A 1% position is **structurally unachievable**
  at lot=75 / ₹100k. To honour 1% on the worst trade the capital basis must be
  ≥ **₹8,45,250** (max loss/lot × 100).
- This mismatch alone blocks promotion (hard 1%-per-trade rule).

## 7. Max-Loss Matrix (engine formula semantics)
`simulate_condor` computes `max_loss = (KcW − Kc) − credit` (call-side width
only). The true iron-condor bound is `max(call_width, put_width) − credit`.

| Case | CallW | PutW | Credit | Engine max loss | True max loss | Understatement |
|---|---|---|---|---|---|---|
| credit < width | 150 | 150 | 40 | 110 | 110 | 0 |
| credit == width | 150 | 150 | 150 | 0 | 0 | 0 |
| credit > width | 150 | 150 | 160 | **−10** | −10 | (negative artifact) |
| unequal wings | 150 | **250** | 40 | 110 | **210** | **−100** |
| wide wings | 200 | 200 | 50 | 150 | 150 | 0 |

- All 6 real trades have symmetric 150/150 wings → the engine understatement
  does not bite them, but the formula is wrong in general (latent semantic
  risk if wings ever diverge). Fees (₹320/trade) and adverse exit slippage are
  also OUTSIDE `max_loss` — a loss exit costs more than the model's bound.

## 8. 646-Session Replay (unified dataset)
Measurement layer (regime via `regime_filter_detect`, VIX via `vix_snapshot_at`,
both on the unified 646-row series) was computed for every session; the
strategy was invoked ONLY on sessions with an authoritative canonical expiry
(`expiry_calendar.csv`, 2025-08-13 .. 2026-08-13). Pre-window sessions were
NOT traded against a forward-rule expiry (per the no-guess rule).

| Session class | Count |
|---|---|
| DATA_INSUFFICIENT (indicator warmup) | 55 |
| NON_CANDIDATE (regime/VIX gate) | 532 |
| RESEARCHABLE (RANGE_HV + VIX pass + canonical expiry) | 22 |
| EXPIRY_DATA_LIMITATION (RANGE_HV + VIX pass, pre-window) | 37 |

- **37 sessions** that would have been trade candidates are EXPIRY_DATA_LIMITATION:
  the canonical calendar does not cover pre-2025-08-13 dates, and the phase
  constraint forbids reconstructing/guessing a different expiry. (Reconstruction
  from the options archive is technically possible as a future, separately
  approved step — not performed here.)
- Replay over the researchable window produces **8 trades, net +8,267.75,
  PF 12.503, 75% win**, max DD −587.00.

### Profit Concentration (8-trade replay)
| Metric | Value |
|---|---|
| Best trade | +2,256.25 (27.3% of total) |
| Top 2 trades | 48.9% of total |
| Top 3 trades | 66.8% of total |
| Worst trade | −587.00 |
| Mean / median | 1,033.47 / 1,440.25 |
| Expectancy | 1,033.47 |

Returns are concentrated in 2–3 trades (≈ half of all profit from 2 wins),
consistent with a low-n regime-classified sample. This concentration — not
just n — is why no risk-normalized economic claim is made here. A risk-
normalized comparison (per-₹-of-max-loss) is meaningless at n=8 and is
explicitly NOT asserted.

## 9. H2-vs-H3 Comparison
| Aspect | Result |
|---|---|
| Matched trades (same entry/exit) | **6/6** — identical P&L (0 diffs) |
| Only in H2 | 0 |
| Only in H3 (unified replay) | **2026-05-15, 2026-05-19** |

- The 6 H2 trades reproduce **exactly** on the unified dataset (same credits,
  same exits, same net P&L −131.75 / +2,256.25 / +1,440.25 / −587.00 /
  +1,483.75 / +1,786.75).
- The 2 extra H3 trades are **measurement artifacts**, not edge: their regime
  flips RANGE_LV → RANGE_HV purely because the unified series carries more
  history.

## 10. Regime-Boundary Sensitivity (key finding)
`high_vol` in `regime_filter_detect` = bb-width percentile ≥ 60 over the
series' trailing history. The unified 646-row series and the frozen 497-row
series (frozen start 2024-08-12) therefore label the same market day
differently:

- **39 regime flips** across the researchable window (≈16% of 245 days) when
  the measurement layer is recomputed on a frozen-depth-equivalent series.
- The 2 extra trades (2026-05-15, 2026-05-19) sit exactly on this boundary:
  unified says RANGE_HV (trades), frozen-depth says RANGE_LV (no trade).
- **Consequence:** the RANGE_HV/RANGE_LV boundary is history-depth sensitive;
  candidate eligibility is NOT robust to how much nifty history the dataset
  carries. This is a measurement-integrity finding, not a strategy defect,
  but it means any "6 vs 8 trades" comparison must be read as dataset-
  dependent, not as evidence of edge.

## 11. Out-of-Sample Split (cut 2026-04-01, unchanged)
| Split | Trades | Wins | Net | WR | PF |
|---|---|---|---|---|---|
| Development | 1 | 0 | −131.75 | 0% | 0.00 |
| Out-of-sample | 7 | 6 | +8,399.50 | 85.7% | 15.309 |

**OOS_INSUFFICIENT** (n=7 < 20): no OOS claim is possible. Note the OOS slice
now contains the 2 artifact trades — the OOS numbers are inflated by the
regime-flip artifacts of §10.

## 12. Reproducibility / Determinism
- H2 baseline reproduced from a fresh `RangeHVValidator` run: 6 trades,
  +6,248.25 — identical to the cached run and to H2.
- The full H3 pipeline (audit, replay, sensitivity, OOS, findings) produced
  **byte-identical JSON** in two independent runs (cached vs fresh baseline).
- Replay engine double-run hash: identical (`abec9947…`).
- Dataset sentinel mtimes unchanged across the run → read-only isolation held.

## 13. Production Isolation
- Measurement never writes `ground_truth.db`, `paper_account.json`, or any
  `data/*` file (open() write-guard test passes; sentinel mtimes unchanged).
- All outputs written only to `--out`.

## 14. Promotion Gate Verdict
**HOLD — DO NOT PROMOTE.** `range_hv_iron_condor_v1` remains
`PROMISING_BUT_INSUFFICIENT`.

Reasons:
1. **RISK_MODEL_MISMATCH (confirmed, unambiguously):** 6.09–8.45% measured vs
   1.0% declared; 1% is structurally unachievable at lot 75 / ₹1L (min lot
   already exceeds 1%).
2. n=8 total, n=7 OOS — both far below the 20+ outcome threshold.
3. 2 of the 8 replay trades are regime-boundary artifacts (history-depth
   sensitivity), so the "improved" 8-trade result is not economic evidence.
4. Contract-semantics bug found and corrected (measurement-only fix); the
   strategy's own economics are unchanged and still carry the above blockers.
5. Fees+slippage still consume ~40% of gross PnL (H2 §11); no new evidence
   the edge survives after cost at scale.

## 15. Phase STOP-condition status
- **BASELINE_REPRODUCTION: PASS** (H2 reproduces byte-identical) — no
  `BASELINE_REPRODUCTION_FAILURE` stop.
- Phase executes to completion: contract semantics audited, risk semantics
  established, max-loss matrix documented, 646-session unified replay
  completed with honest classification and artifact attribution.

## 16. Test Results (final battery)
```
.venv/bin/python -m unittest tests.test_h3_range_hv_risk_semantics -v
Ran 20 tests in ~130s -> OK
```
Covers: spec-hash identity; unified manifest integrity; freeze inputs;
six-trade contract audit (true credits below 150, mislabel on grade-A days,
negative-max-loss artifact, corrected positive max loss, risk % 6.09–8.45);
baseline net 6,248.25; max-loss matrix (negative artifact, unequal-wing
understatement, symmetric agreement); 646-session classification
(55/532/22/37); extra trades are regime-flip artifacts (flip_count 39,
RANGE_HV vs RANGE_LV); 6/6 H2 trades reproduce with zero P&L diffs; replay
P&L equality on overlap; reproducibility (identical double-run, 246
researchable days); OOS_INSUFFICIENT; production write-guard + sentinel mtimes.

Regression: `tests.test_phase_h2_range_hv` + `tests.test_phase_h_multi_strategy`
(40 tests) remain green.

## 17. Data Divergence Note (unchanged from H2 §23)
Live `data/nifty_history.csv` has drifted from the frozen fingerprint. All H3
measurement ran against the frozen snapshot (baseline) and the unified
normalized dataset (replay); live files were not used.

---

### Appendix A — Artifact Hashes
- H3 report (cached baseline): `/tmp/opencode/h3/h3_report.json`
- H3 report (fresh baseline): `/tmp/opencode/h3_full/h3_report.json` — byte-identical sections
- H2 baseline repro: `/tmp/opencode/h3_baseline_repro.json`
- Unified manifest `calendar_hash`: `54965462e130df5491c919bc53d9bac681f3f88b711a0abdfd7da8084a593dcf`
- Candidate spec_hash: `56ba02752efc4650efe1d8c88165f3396e3ae10aaa15519d9b13e33a4e0d1adb`

### Appendix B — Commit State
No commits were made during Phase H3 (per critical rule). Base commit remains
`cf132ca`. H3 files (`phase_h3_risk_semantics.py`, `tests/test_h3_range_hv_risk_semantics.py`,
this audit) are new, untracked measurement artifacts.

### Appendix C — Files
- `phase_h3_risk_semantics.py` — H3 measurement module (freeze / baseline /
  contract audit / risk semantics / max-loss matrix / 646 replay / regime
  sensitivity / OOS / reproducibility / isolation / findings)
- `tests/test_h3_range_hv_risk_semantics.py` — 20-test suite
- `/tmp/opencode/h3/h3_report.json`, `/tmp/opencode/h3_full/h3_report.json` — full reports
- `audit/PHASE-H2-RANGE-HV-VALIDATION.md` — prior phase audit (unchanged)
- `/tmp/opencode/phaseH_frozen_data` — authoritative frozen snapshot
