# PHASE E — FROZEN STRATEGY HISTORICAL BACKTEST (MEASUREMENT ONLY)

**Date:** 2026-08-13 | **Window:** 2025-08-13 → 2026-08-13 (245 trading days)
**Runner:** `backtest_frozen.py` (new, isolated; NO production code changed)
**Result:** `NO_DEMONSTRABLE_STABLE_EDGE` → keep paper-only, no live capital, no strategy change.

---

## 1. What was measured (frozen identity, source-verified)

The exact decision chain the live runner executes, replayed day-by-day:

| Layer | Source | PASS condition |
|---|---|---|
| L1 Regime gate | `regime_filter.trade_plan()` logic | gate != NO_TRADE AND regime != RANGE_LV |
| L2 Capital guard | `capital_guard.full_capital_safety_audit(daily_pnl=0)` | safety_status == APPROVED |
| L3 Technical consensus | `market_brain` on cached indicators | tech_bias != NEUTRAL |
| L4 Options chain | `oi_intel.pcr_and_pain` / `oi_walls` / `skew` | (PCR>1.2 & CALL) or (PCR<0.8 & PUT) |
| L5 Institutional | `institutional.institutional_scan` | fii_sentiment != NEUTRAL |
| L6 Super-AI ML | xgb/lgb/rf ensemble (walk-forward) | verdict != NEUTRAL_SIDEWAYS |

Grade: **A+ = score≥5 + L1 passed** (HIGH_CONVICTION_*), **A = score≥4 + L1 passed** (MODERATE_*), else **NO_SIGNAL/STAY_OUT**. Entry gate = grade/action only (`auto_paper_runner.py`).

Execution model (frozen): lots=1 (75 qty), side BUY; entry = chain LTP else BS(σ=0.15) of best strike (no chain → spot×0.99 for the PE path); ATR = max(10, 0.25·entry); SL = max(2.0, entry−1.5·ATR); target = entry+2·(entry−SL); triggers mark ≤ SL·1.001 / ≥ TP·0.999; expiry square-off on NIFTY weekly Thursday; costs `COST_PER_TRADE=40.0`, `SLIPPAGE_PCT=0.015` (adverse, BUY ref×1.015 / SELL ref×0.985).

## 2. Data inventory & coverage (why the funnel is what it is)

| Source | Coverage | Window impact |
|---|---|---|
| `nifty_history.csv` | 496 rows, 2024-08-12→2026-08-13 | trading-day universe (tail gaps: 2026-08-08, 2026-08-11 absent) |
| `india_vix.csv` | 245 rows, 2025-08-13→2026-08-13 | L1 VIX layer; 6 window days VIX_PANIC |
| `oi_snapshots/` | **4 CSV days only** (2026-08-08/11/12/13) | L4 evaluable on 3 in-window days → **0 of 245 days passed** |
| `fii_dii_history.csv` | 60 sessions, 2026-05-19→2026-08-12 | L5 evaluable on 60 days; 185 days NO_DATA |
| `ml_features.csv` | 496 rows full 2y | L6 walk-forward, always evaluable |
| `research.db` ticks | recent days only | not usable for the window → day-level marks |

## 3. No-lookahead fixes (documented, not strategy changes)

1. All inputs windowed to `<= t` (nifty, VIX, indicators, FII/DII, ML). Frozen code reads the global last row — live-safe (last row = today), lookahead in replay.
2. **ML trained per-day on slice ≤ t, predicting row t.** Frozen `train_super_ai_ensemble` fits the full file and predicts the final bar; identical hyperparams/80-20 split reproduced per day (labels reference data ≤ t).
3. Options snapshot = latest dated ≤ t (frozen uses newest file on disk).
4. Contract expiry = next Thursday (frozen 20-day constant is a display fallback only).
5. Marks: snapshot LTP if a chain exists for that strike/date, else BS(σ=0.15) at day close. No intraday path.

## 4. Decision funnel (245 days)

```
grade:      A 42   A+ 4   NO_SIGNAL 199
regime:     RANGE_LV 172 | RANGE_HV 37 | TREND_HV 31 | TREND_LV 5
gate:       NO_TRADE 178 | TRADE_SMALL 37 | TRADE_REDUCED 30
L1: PASSED 67 / BLOCKED 178     L2: PASSED 245
L3: PASSED 195 / NEUTRAL 50     L4: NO_SNAPSHOT 242 / MIXED 3 / PASSED 0
L5: NO_DATA 185 / PASSED 43 / NEUTRAL 17
L6: PASSED 183 / NEUTRAL 62
confluence: 1→7d, 2→57d, 3→116d, 4→61d (42 A + 19 NO_SIGNAL), 5→4d
```
- **RANGE_LV = 70% of the year** → the live zero-trade window observed in Phase D is the *typical* state, not a coincidence.
- Non-RANGE_LV days: 73; of those 27 still NO_SIGNAL (confluence <4). 46 candidates fired (63% of open-gate days).
- L2 added a point on **every** day (structurally inert, see D2). L4 added a point on **zero** days. L5 available only from 2026-05-19.
- **Cross-validation vs Phase D live:** replay 2026-08-10/12/13 = RANGE_LV, NO_TRADE, cf 2-4 → NO_SIGNAL/STAY_OUT — identical to the live observation (STAY_OUT, cf 2/6 on 2026-08-13).

## 5. Trade simulation (46 directional candidates — all PUT buys)

```
n=46   wins=14   losses=32   winrate=30.4%
gross_win=₹151,230   gross_loss=₹-139,048   PF=1.09   net=₹+12,182
expectancy=₹+265/trade   avg_win=₹+10,802   avg_loss=₹-4,345
max_win=₹+38,711   max_loss=₹-9,286   avg hold=2.2 days
exits: STOP_LOSS 26 | TAKE_PROFIT 7 | EXPIRY_SQUARE_OFF 13
```

### By grade (confluence separation)
| grade | n | win% | net |
|---|---|---|---|
| A (4/6) | 42 | 31% | +9,335 |
| A+ (5/6) | 4 | 25% | +2,847 |

**Higher-confluence tier did NOT perform better** (small n, but direction is negative).

### By regime family (entry-day regime)
| regime | n | win | net |
|---|---|---|---|
| RANGE_HV | 22 | 5 | **−28,939** |
| TREND_HV | 20 | 7 | +32,681 |
| TREND_LV | 4 | 2 | +8,441 |

Money is made only in TREND regimes and bled in RANGE_HV — the "fade extremes" regime the gate only lets through at SMALL size.

### By month
`2025-08 +6,772(3) | 2025-10 −24,463(8) | 2025-11 +1,668(1) | 2026-01 −33,058(6) | 2026-03 +78,808(14) | 2026-04 −7,610(4) | 2026-06 −17,835(7) | 2026-07 +7,899(3)` — **all net profit lives in one month (Mar-26).** Feb/May/Aug-26: zero trades (regime gate closed).

### ML separation
| ML status | n | win% | net |
|---|---|---|---|
| PASSED (non-neutral) | 43 | 33% | +26,892 (+625/t) |
| NEUTRAL | 3 | 0% | −14,710 |

ML-NEUTRAL trades (all with L5 institutional backing) lost every time; even the ML-PASSED pool is marginal. No exploitable separation.

## 6. Frozen-code defects found (documented — NOT fixed, measurement phase)

- **D1 `auto_paper_runner.py:89` — the runner can never buy a CALL.** `option_type = "CE" if ("BUY_CALL" in action or "BULLISH" in action) else "PE"`; signal actions are `HIGH_CONVICTION_*` / `MODERATE_*` — neither substring ever matches. Every live paper entry (and all 46 replay trades) is a **PE (put) buy**, regardless of the CALL/PUT label. The strike logic's CE branch is dead code.
- **D2 L2 capital guard is inert in this entry path:** kill-switch needs a −₹3,000 daily realized loss (never hit with daily_pnl=0), event calendar is never configured (`NO_EVENT_DATA` → allow), expiry trap is never activated (audit called without `is_expiry`). Passed 245/245.
- **D3 L4 options layer never passed all year** (data-starved + PCR rule rarely satisfiable) — contributes 0 points in this window.
- **D4 Grade-A fires at 4/6 with L4/L5 frequently missing:** 43/46 trades executed with NO institutional data and none with options data; a "A" grade is effectively regime+guard+tech+ML.

## 7. Reproducibility & isolation

- **Reproducibility:** two independent runs produced byte-identical `daily` + `trades` (sha256 `cb384a6f4326b835…`), incl. per-day ML accuracies. Deterministic.
- **Isolation:** 4 input caches byte-identical across Phase E (nifty `b7ee5741…`, vix `9bd5c22a…`, fii `b5a696ce…`, ml `6e1225df…`). `paper_account.json` sha matches Phase D baseline exactly. `ground_truth.db` / `historical_audit.db` mtimes predate Phase E (no writes possible — replay never imports ledger/precision modules). Regression: **268 tests OK**.
- Artifacts: `/tmp/opencode/phaseE/results_20260813_*.json` (two identical runs), `backtest_frozen.py` in repo root.

## 8. Interpretation

1. **The Phase D zero-trade window is the norm, not the exception:** RANGE_LV gate closed 73% of the year. `NO_GENUINE_DIRECTIONAL_TRADE_OBSERVED` (Phase D) is fully consistent with the frozen strategy's own historical behavior.
2. **When the gate opens, the frozen strategy trades often (46/73 open days) but without a demonstrable edge:** PF 1.09, 30.4% WR, +₹265/trade expectancy, all profit concentrated in one month, A+ (5/6) no better than A (4/6), ML separation weak.
3. **Two structural reasons the funnel fires despite missing layers:** L2 is always-on (inert) and L4 never contributed; grade-A only needs 4/6.
4. **Premium model caveat:** entries/marks use the frozen BS σ=0.15 constant (vs real VIX 11-12%), so put-entry cost is *overstated* — conservative for the buyer, would not create a false positive edge.

## 9. FINAL RESPONSE

```
FROZEN STRATEGY BACKTEST (PHASE E) — 2025-08-13 → 2026-08-13
=============================================================
WINDOW      : 245 trading days (NIFTY daily cache; VIX 1y; FII/DII 60 sess;
              OI snapshots 4 days; ML features 2y)
REPLAY      : 6-layer frozen confluence, day-by-day, strict no-lookahead
              (all inputs windowed <= t; ML walk-forward per day)
RESULTS     : RANGE_LV gate closed 172/245 (70%) -> NO_TRADE 178 days
              candidates 46/245 (all PUT buys - frozen runner defect D1)
              trades 46 | winrate 30.4% | PF 1.09 | net ₹+12,182
              expectancy ₹+265/trade | profit 100% from Mar-2026 alone
              A+ (5/6) 25% WR < A (4/6) 31% WR (higher conf. NOT better)
FUNNEL      : L1 67 pass | L2 245 pass (inert) | L3 195 | L4 0 (data-starved)
              L5 43 | L6 183 (NO_DATA 185 / NO_SNAPSHOT 242)
DEFECTS     : D1 CE-unreachable in auto_paper_runner (all entries = PE)
              D2 capital-guard inert | D3 options layer 0/245 | D4 A-grade on 4/6
CROSS-VAL   : replay Aug-2026 == Phase D live (RANGE_LV, STAY_OUT) ✓
REPRODUCIBILITY: 2 runs byte-identical (sha cb384a6f4326b835) ✓
ISOLATION   : 4 caches byte-identical; paper_account sha matches Phase D;
              GT/ledger untouched; 268 tests OK ✓
VERDICT     : INSUFFICIENT evidence of stable edge. Paper-only continues.
              NO strategy change. NO live capital.
              (Phase D observation window still running -> 2026-08-14 15:30 IST)
```
