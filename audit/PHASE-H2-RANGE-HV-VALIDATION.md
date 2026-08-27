# Phase H2 — RANGE-HV Iron Condor Validation Audit

**Status:** MEASUREMENT ONLY — no strategy mutation, no optimization, no promotion.
**Candidate:** `range_hv_iron_condor_v1` (Candidate C, multi-strategy research).
**Window:** 2025-08-13 .. 2026-08-13 (245 trading days).
**Authoritative data root:** `/tmp/opencode/phaseH_frozen_data` (frozen snapshot; live `data/nifty_history.csv` has drifted — see §23).
**Report artifact:** `/tmp/opencode/phaseH2_report.json`.
**Test module:** `tests/test_phase_h2_range_hv.py` (17 tests, all green).

---

## 1. Objective
Rigorously validate the frozen RANGE-HV iron condor before any promotion
decision. Phase H2 is evidence-gathering only: the strategy, its rule set,
strike width, delta target, expiry selection, stops/targets, filters, VIX
thresholds, regime logic, position sizing and capital model are ALL treated as
immutable. Nothing was changed, swept, re-optimized, or regenerated.

## 2. Frozen Candidate Identity
- **id:** `range_hv_iron_condor_v1`, version 1, lifecycle `BACKTESTED`, `promoted: false`
- **classification:** `PROMISING_BUT_INSUFFICIENT`
- **spec_hash (stable):** `56ba02752efc4650efe1d8c88165f3396e3ae10aaa15519d9b13e33a4e0d1adb`
- **Strategy parameters (frozen, unchanged):**
  - Regime gate: `RANGE_HV` only (HV regime filter; RANGE_LV = NO TRADE)
  - VIX gate: `16.0 <= VIX < 25.0`
  - Structure: iron condor, ±2% OTM (short legs), 150-pt wings, NIFTY (lot 75)
  - Target: 50% of credit; Stop: 2.0x credit (never hit in window); Time exit
    at close day (expiry - 2); Expiry carry
  - Costs: ₹40/order, 8 orders/trade, slippage 1.5% of credit

## 3. Data Integrity (frozen snapshot)
Fingerprints recorded in the report are byte-identical to the committed
reference (multi-strategy research run). Dataset composite:
`018c182ef833c620d3b36ac22faadf956caabb42bf5264445e4…`.

| File | sha256 |
|---|---|
| `nifty_history.csv` | `691bf02d08d0a2ec58acac88751e695c44232ddaf886020be25057721466f49d` |
| `india_vix.csv` | `9bd5c22a45d1636751d4453053c26cfdb5da0df02add577c64dea2207175c0e3` |
| `fii_dii_history.csv` | `6c9d76f8e2a4ccc35099c7d392df11de63a7adff47852ac13c4f48bda3948cc7` |
| `ml_features.csv` | `6e1225dfce06ca1135eba7c38c62fbacfcad6bcdae188d98c25735a1ddc14cbd` |
| `historical/expiry_calendar.csv` | `3abbe4ccb003d9f9228d9bdfaf73041403dae5ed4a43f30e223bc9fc6b426ad2` |
| `oi_snapshots/` (247 files) | `5e01e40ec018aa438ed0d3054296666c1b8e41aab6d4f9a7c33df9492804c708` |

## 4. Eligibility Classification (245 days)
| Status | Count |
|---|---|
| NOT_RANGE_HV (no trade by regime) | 201 |
| VIX_GATE_FAIL (regime OK, VIX outside 16–25) | 18 |
| TRADE | 6 |
| POSITION_LOCKED (single-position lock) | 14 |
| TRADE_CLOSE (day before expiry close-out) | 6 |

**Headline:** Of the 37 RANGE_HV days in the window, 19 passed the VIX gate
(confirming the spec note "only 19 RANGE_HV days in the frozen window satisfy
the VIX gate"). Of those 19 free-to-trade gate-passing days, **all 19 became
TRADE / POSITION_LOCKED / TRADE_CLOSE — there is NO structure/price/credit
rejection in this window.** The six trades and the ten lock days are the only
things that kept the count below 19.

## 5. Six-Trade Reconstruction (exact, byte-matched to committed reference)
| # | Entry | Exit | Structure | Entry credit | Exit | Net PnL | Fees | Slippage | MaxRisk/lot* | MFE | MAE | Held |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-03-04 | 03-09 | 25100/24950-P 24000/23850 | 167.3 | TIME | −131.75 | 320 | 892.12 | (na) | 1,728.8 | 0 | 5 |
| 2 | 2026-04-08 | 04-13 | 24650/24500-P 23500/23350 | 37.3 | EXPIRY | +2,256.25 | 320 | 217.52 | 8,452 | 2,793.8 | −97.5 | 5 |
| 3 | 2026-04-15 | 04-20 | 24850/24700-P 23750/23600 | 45.5 | TARGET | +1,440.25 | 320 | 286.65 | 7,838 | 2,047.5 | 0 | 5 |
| 4 | 2026-04-21 | 04-27 | 25200/25050-P 24100/23950 | 223.6 | TIME | −587.00 | 320 | 424.57 | (na) | 183.8 | −2,970 | 6 |
| 5 | 2026-04-28 | 05-04 | 24650/24500-P 23500/23350 | 39.5 | TARGET | +1,483.75 | 320 | 229.05 | 8,284 | 2,032.5 | 0 | 6 |
| 6 | 2026-05-05 | 05-11 | 24650/24500-P 23550/23400 | 42.5 | TARGET | +1,786.75 | 320 | 226.24 | 8,066 | 2,332.5 | −1,552.5 | 6 |

\* MaxRisk/lot = (wing_width − entry_credit) × 75, only meaningful when
credit < width (trades 2,3,5,6); see §17. Trades 1 & 4 collected MORE credit
than the 150-pt wing width — frozen-engine formula yields a negative number
(§17 artifact).

Net: **+6,248.25** across 6 trades; 4 wins / 2 losses; PF **9.693**;
max drawdown **−587.00** — identical to `results/phaseH_multi_strategy.json`
(C_RANGE_HV_IRON_CONDOR).

## 6. Profit Concentration
| Metric | Value |
|---|---|
| Total | 6,248.25 |
| Best trade | 2,256.25 (**36.1%** of total) |
| Worst trade | −587.00 |
| Median | 1,483.75 |
| Top-2 share | 64.7% |
| Top-3 share | **88.5%** |

n=6 with 88.5% of PnL in 3 trades is **HIGH_CONCENTRATION** — the profile is
dominated by a short streak; not robust evidence of edge.

## 7. Monthly Stability (grouped by ENTRY month)
| Entry month | Trades | Net PnL |
|---|---|---|
| 2026-03 | 1 | −131.75 |
| 2026-04 | 4 | +4,593.25 |
| 2026-05 | 1 | +1,786.75 |

NOTE: the CLI `strategy_lab.py` monthly report groups by EXIT month
(2026-04: 3 trades +3,110; 2026-05: 2 trades +3,270). The two views differ
by construction; the validator uses entry-month to align with entry eligibility.

## 8. VIX Bands at Entry
| Band | Trades | Wins | Net |
|---|---|---|---|
| 16–18 | 2 | 1 | +1,199.75 |
| 18–20 | 3 | 3 | +5,180.25 |
| 20–22 | 1 | 0 | −131.75 |
| 22–25 | 0 | – | – |

All three wins in 18–20 and both losses outside it — but n is too small to
conclude a band effect.

## 9. Day-of-Week / Expiry Distance
- Entries: Tuesday 3, Wednesday 3.
- Days held: 5–6 (weeklies: Thursday pre-SEBI, Tuesday post-SEBI calendar —
  frozen `expiry_calendar.csv` used, matching the committed reference).
- Wednesday entries: −131.75 / +2,256.25 / +1,440.25; Tuesday entries:
  −587.00 / +1,483.75 / +1,786.75.

## 10. Exit Analysis
| Exit | Count | Wins | Avg PnL | Net | Avg MFE | Avg MAE | Avg hold |
|---|---|---|---|---|---|---|---|
| TARGET (50%) | 3 | 3 | +1,570.25 | +4,710.75 | 2,137.5 | −517.5 | 5.7 |
| TIME (close day) | 2 | 0 | −359.38 | −718.75 | 956.25 | −1,485.0 | 5.5 |
| EXPIRY carry | 1 | 1 | +2,256.25 | +2,256.25 | 2,793.8 | −97.5 | 5.0 |
| STOP (2x credit) | 0 | – | – | – | – | – | – |

No STOP exit was ever triggered in the window. Both TIME exits were the
strategy's own loss control.

## 11. Cost Accounting
| Item | Amount |
|---|---|
| Gross PnL (before cost) | +10,444.40 |
| Fees (6 × ₹320 = 6 × 8 orders × ₹40) | −1,920.00 |
| Slippage (1.5% of credit × 8 legs) | −2,276.15 |
| **Net** | **+6,248.25** |

Fees+slippage consume **40.2%** of gross PnL. The edge is real only AFTER
costs; pre-cost numbers alone would overstate the result.

## 12. Out-of-Sample Split (cut 2026-04-01)
| Split | Trades | Wins | Net | WR | PF |
|---|---|---|---|---|---|
| Development | 1 | 0 | −131.75 | 0% | 0.00 |
| Out-of-sample | 5 | 4 | +6,380.00 | 80% | 11.869 |

OOS is **5 trades**, far below the 20+ outcome threshold → verdict
**OOS_INSUFFICIENT**. A 5-trade sample cannot validate an edge.

## 13. Walk-Forward Note
The strategy was never walk-forward optimized: parameters (2% OTM, 150-pt
wings, 50% target) are fixed and pre-declared in the frozen spec. However,
with only 6 trades there is no meaningful train/test generalization split
beyond §12. No further partitioning was performed (would be data mining).

## 14. Bootstrap Robustness
- n=6, mean of resampled sums **+6,204.19**, 90% CI **[+1,803.75, +10,237.50]**,
  P(negative total) **1.1%**, estimated win rate 66.7%.
- Lower CI bound is positive but the interval is extremely wide; with n=6 the
  bootstrap is informational only, not a validation.

## 15. Drawdown / Risk
- Max drawdown **−587.00** (single losing trade), max single loss −587.00,
  largest consecutive losing streak 1.
- Equity path: −131.75 → +2,124.50 → +3,564.75 → +2,977.75 → +4,461.50 → +6,248.25.
- Worst intra-trade MAE **−2,970.00** (trade 4) — a TIME exit booked −587 but
  the position was underwater by ~2,970 at its worst; the 150-pt wings contained it.

## 16. Eligibility Trace vs Engine — No Lookahead
- `eligibility_trace()` replicates `run_candidate_c` branch order and single-
  position lock, annotated with per-day regime + VIX. Trace TRADE dates
  **exactly match** engine entry dates (6/6).
- Entry uses only data available on/before entry day; simulation touches only
  dates > entry; VIX at entry = day-of-entry snapshot; exit_date > entry_date.
- Regression test `TestH2Trades.test_no_lookahead` asserts all of the above.

## 17. RISK_MODEL_MISMATCH (promotion blocker)
The frozen spec declares `max_risk_pct: 1.0` (1% of ₹100k capital). The
measured 1-lot defined-risk exposure (wing_width − entry_credit) × 75 is:

| Trade | MaxRisk/lot | % of 100k |
|---|---|---|
| 2 | 8,452 | 8.5% |
| 3 | 7,838 | 7.8% |
| 5 | 8,284 | 8.3% |
| 6 | 8,066 | 8.1% |

**~8% exposure vs declared 1% = RISK_MODEL_MISMATCH.** Either the spec's risk
model or the capital model is wrong; the mismatch alone blocks promotion.

**Artifact note:** trades 1 & 4 collected credit (167.3 / 223.6) greater than
the 150-pt wing width. The frozen engine computes
`max_loss = (width − credit) × lot`, which is NEGATIVE for those trades (na).
Under naive marking the model treats them as guaranteed-profit ("risk-free"),
which is wrong after fill-adjusted widths — flagged in tests
(`test_risk_model_mismatch_documented`).

## 18. Reproducibility / Determinism
- Two full validator runs produced **byte-identical** JSON
  (`phaseH2_report.json`) — the measurement is deterministic.
- `engine_trades()` ×2 and `eligibility_trace()` ×2 produce identical output.
- Test suite asserts determinism directly.

## 19. Spec Consistency / Engine Equivalence
- `strategy_lab.py validate/compile` on frozen snapshot: spec-consistent,
  spec_hash stable (`56ba0275…`).
- `equivalence range_hv_iron_condor_v1 --data-root <snapshot>`:
  **spec-consistency 0 violations, MATCH 6/6 trades** (run hash
  `ce8fd465e497`, reference `c1d3a044e574`).
- `BacktestAdapter` metrics equal committed reference exactly
  (trade_count 6, win_count 4, net 6,248.25, PF 9.693, maxDD −587.00).

## 20. Production Isolation
- Measurement path never opens `data/ground_truth.db`, `data/paper_account.json`,
  or any `data/` file for writing (open() write-guard test, same pattern as
  the Phase H suite). Zero blocked writes recorded.
- Note: `ground_truth.db` on disk IS being mutated by the external live daemon
  between measurements — environmental, not caused by H2 (byte-hash compare is
  therefore flaky and was replaced by the write-guard).

## 21. Promotion Gate Verdict
**HOLD — DO NOT PROMOTE.** RANGE-HV iron condor remains
`PROMISING_BUT_INSUFFICIENT`.

Reasons:
1. n=6 total, n=5 OOS → far below the 20+ outcome threshold (OOS_INSUFFICIENT).
2. Profit concentration: 88.5% of PnL from 3 trades.
3. **RISK_MODEL_MISMATCH**: measured ~8% capital exposure vs declared 1% —
   promotion would violate the hard 1%-per-trade risk rule.
4. 0 trades in the last ~3 months of the window (53 RANGE_LV days + 12 RANGE_HV
   days all VIX-gate-failed) → the strategy is currently structurally inactive.
5. No STOP exit in 6 trades → untested tail behaviour; trade 4's −2,970 MAE
   shows real tail exposure the model under-reports.

Promotion requires: (a) fixing the risk/capital model, (b) a materially larger
OOS sample, (c) evidence the strategy re-activates (current gate conditions
produce no trades).

## 22. Test Results (final battery)
```
.venv/bin/python -m unittest tests.test_phase_h2_range_hv -v
Ran 17 tests in ~420s -> OK
```
Full battery (`tests.test_phase_h2_range_hv` + `test_strategy_lab` + `test_all`):
```
Ran 47 tests in 767.122s -> OK
```
Tests cover: candidate identity + stable spec_hash; exact 6-trade reconstruction
vs committed reference; eligibility counts (37/19/6/10/3, all gate-passing free
days trade); trace==engine dates; low-VIX gate fails; cost accounting
(fees 320 = 8×40, net = gross − fees − slippage); exit classification
(TARGET/TIME/EXPIRY, no STOP); entry-condition satisfaction; no-lookahead;
OOS split (dev 1 / OOS 5); profit-concentration flag; risk-model mismatch +
credit>width artifact; determinism; spec-consistency 0 violations; metric
match vs reference; production write-guard.

## 23. Data Divergence Note
Live `data/nifty_history.csv` has drifted from the committed fingerprint
(live `fd3a459d…` vs frozen `691bf02d…`). ALL H2 measurement ran against
`/tmp/opencode/phaseH_frozen_data`. Any future H2 re-run MUST target the same
frozen root; results are not comparable against live files until the drift
is reconciled.

---

### Appendix A — Artifact Hashes
- H2 result (canonical 6-trade JSON): `2751d12f0463a59fb9ed973acef365a52eda0d6133a4372c825249d3ed11ffa6`
- Committed reference result: `c1d3a044e574…`
- Condor equivalence run: `ce8fd465e497…` (control run `79ed7c3b865e…`)
- Dataset composite: `018c182e…`
- Candidate spec_hash: `56ba0275…`

### Appendix B — Commit State
No commits were made during Phase H2 (per critical rule). Base commit remains
`cf132ca`. H1 v2 files (`multi_strategy_backtest.py`,
`results/phaseH_multi_strategy.json`, `strategies/*.yaml`) remain untracked.

### Appendix C — Files
- `phase_h2_validation.py` — measurement module (`RangeHVValidator`)
- `tests/test_phase_h2_range_hv.py` — 17-test suite
- `OPENCODE_PHASE_H2_RANGE_HV_VALIDATION.md` — plan
- `/tmp/opencode/phaseH2_report.json` — full report
- `/tmp/opencode/phaseH_frozen_data` — authoritative frozen snapshot
- `audit/PHASE-H1-V2-STRATEGY-LAB.md` — prior H1 v2 audit (unchanged)
