# PHASE D — FIRST GENUINE PAPER OUTCOME (Observation & Validation)

**Status:** OBSERVATION COMPLETE (window continues) · ZERO-TRADE WINDOW
**Date:** 2026-08-13
**Spec:** `OPENCODE_PHASE_D_FIRST_GENUINE_PAPER_OUTCOME.md`
**Git baseline:** `cf132ca` (`phase6-baseline-2026-08-13-3678c7f0`)
**Prior phases:** A (FSM), B (cost/MTM), C (auto-exit) — all independently verified.

## 1. Mandate

Observation only. **No strategy change, no entry/signal/threshold/guard/ML
change, no forced trade, no synthetic data.** The market decides whether a
genuine setup occurs. Phase D success does not require a profit — it requires
that any genuine candidate travels the full lifecycle without integrity error.

## 2. Observation Window

| Field | Value |
|---|---|
| observation_start | 2026-08-13 18:52:37 IST (baseline snapshot taken) |
| observation_end | 2026-08-14 15:30 IST (end of next trading session) |
| git_commit | cf132ca (working tree unchanged for strategy modules) |
| baseline_id | `PHASED_20260813_185237_CF132CA` |
| market/data sources | NSE (cached chain), Yahoo `^NSEI` 1m (live/cached spot), `^INDIAVIX` (cached), FII/DII cache, research.db ticks |

This session covers the 18:52–18:59 IST after-hours segment (Thursday expiry
day, market closed at 15:30 IST). Continued monitoring during the next
market-hours session is the remaining portion of the window; a trade occurring
then continues from this baseline with the same rules.

## 3. Baseline (before observation)

| Check | Result |
|---|---|
| `git rev-parse --short HEAD` | cf132ca |
| `git diff --check` | clean |
| `python test_all.py` | 34/34 OK |
| `python -m unittest discover -s tests` | 268/268 OK |
| `python tests/test_fix_verification.py` | exit 0 |
| `pip check` | no broken requirements |
| `pip-audit` (uvx) | no known vulnerabilities |

Production state at start (read-only):

- Ground Truth ledger: observations 240 · feature_snapshots 240 · signals 240 ·
  predictions 0 · decisions 240 · executions 0 · positions 0 · outcomes 0 ·
  evaluations 0.
- Paper account: cash ₹3,381.25 · realized ₹0.00 · unrealized ₹0.00 · fees ₹0 ·
  slippage ₹0 · equity (marked) ₹3,381.25 · FSM orders 0 · FSM positions 0 ·
  **10 legacy positions** (pre-Phase-A, classified LEGACY, never auto-converted).
- Reconciliation: **MATCH**, 0 errors, 10 legacy INFO.
- Chain health: **HEALTHY**, 0 findings.
- Data fingerprints of ground_truth.db / paper_account.json recorded
  (`data/_phaseD_baseline_fp.txt`). No production data was altered to establish
  the baseline.

## 4. Integrity finding discovered at baseline (documented halt + fix)

**Problem (DATA/UNKNOWN taxonomy — test-hygiene integrity bug):** the full test
suite was appending genuine-but-test-triggered signal chains into the
**production** ground truth ledger. Root cause: `tests/test_fix_verification.py`
`TestR1PrecisionHonestConfluence.setUp` called the production
`precision_signals.generate_precision_signal()`, which records an
observation→signal→decision chain to `ground_truth.DB_FILE`. Evidence: 7
byte-identical chains (ids 241–247, ts 18:54:02–18:54:12 IST) appeared during a
single `unittest discover` run; ground_truth.db fingerprint changed
`9b539f…`→`8ff1da…`.

**Action taken (per "stop and report before changing code"):**
1. Fixed the test to isolate Ground Truth writes to a temp DB
   (`tests/test_fix_verification.py`, +10/−2, test-only change; strategy code
   untouched). Verified: after the fix the full suite leaves ground_truth.db
   **byte-identical** (sha `994f974…` before == after) with counts pinned at
   240/240/240/240.
2. Surgically removed the 7 test-artifact chains (241–247) from the production
   ledger, restored the append-only DELETE triggers, reset `sqlite_sequence`,
   verified `PRAGMA integrity_check=ok` and counts back to the exact baseline.
   No genuine row (≤ 240) was touched. The one genuine observation recorded by
   this phase's runner is chain **248** (kept).

No production Ground Truth record was rewritten; only unambiguous test artifacts
created minutes earlier were removed.

## 5. Genuine signals observed

One genuine signal cycle was executed through the **production runner**
(`auto_paper_runner.run_auto_paper_trader()`), the same code path the daemon
uses every 30s, at 18:58:07 IST (market closed):

| Field | Value |
|---|---|
| timestamp | 2026-08-13 18:58:12 IST |
| market_state | post-close (expiry Thursday), cached spot from today's 15:29 bar |
| spot used | ₹24,395.85 (**flagged STALE**, see Data Quality) |
| regime | **RANGE_LV** → gate **NO_TRADE** |
| India VIX | 11.42 (VIX_CHEAP), expected move from cache |
| technical layer | PASSED (CALL bias, 4/6 consensus, conf 66%) |
| options layer | MIXED (PCR 0.777, max pain 24,400, walls 24,300/24,500) |
| institutional layer | NEUTRAL |
| ML layer | NEUTRAL_SIDEWAYS (ensemble p 0.4793) |
| capital guard | APPROVED (kill-switch off, no event data) |
| confluence | **2/6 (33%)** → below A-grade minimum |
| final action | **STAY_OUT** (NO_SIGNAL – FILTERED OUT NOISE) |
| decision reason | regime gate closed (RANGE_LV → NO_TRADE) |
| category | **STAY_OUT** (project terminology) |
| runner result | `{status: STAND_DOWN, reason: signal STAY_OUT…}` |

The strategy's own 6-layer gate rejected the setup even though MTF was 3/4
bullish and technicals leaned CALL — exactly the intended loss-control behavior
(no forced entry, no regime bypass).

## 6. Directional candidates / first genuine trade

**Directional candidates: 0. Genuine ENTER: NO. Completed paper trades: 0.**

`evaluation_engine.live_observation_report` independently confirms:
`state = NO_DIRECTIONAL_TRADES_YET`, `directional_signals = 0`,
`stay_out_skip = 1.0`, open positions 0, closed 0, pending predictions 0,
leakage_clean, provenance findings 0, chain findings 0.

Per spec §15, this is **valid observation, not failure**:
`NO_GENUINE_DIRECTIONAL_TRADE_OBSERVED` (in this segment of the window). No
threshold was loosened, no gate bypassed, no trade fabricated.

## 7. Lifecycle audit results (NOT_OBSERVED items)

| Stage | Result | Note |
|---|---|---|
| Decision | NOT_OBSERVED | SKIP decision recorded at chain 248; no actionable signal to verify against |
| Paper entry (FSM) | NOT_OBSERVED | no ENTER; FSM submit/accept/fill path verified in Phase A tests (268-test suite green) |
| Ground Truth mirroring | PASS (observed state) | 0 paper orders ↔ 0 GT executions ↔ 0 GT positions; reconciliation MATCH, 0 errors |
| MTM | PASS (read-only) | `mark_to_market_report` ran; fingerprints of paper_account.json + ground_truth.db unchanged; unrealized 0, no close, no outcome, no fabricated quote |
| Auto-exit | NOT_OBSERVED | no position; exit evaluator/FSM verified in Phase C (STOP_LOSS/TAKE_PROFIT/EXPIRY_SQUARE_OFF tests) |
| Outcome | NOT_OBSERVED | outcomes 0; close_position append-only + single-outcome rules verified in Phase C |
| Evaluation | INSUFFICIENT_SAMPLE | 0 predictions, 0 outcomes → no statistics manufactured |

## 8. Reconciliation

Paper account ↔ FSM ↔ GT execution ↔ GT position ↔ GT outcome:
**MATCH, 0 errors** (10 legacy INFO positions excluded by design — never
converted, never fabricated).

## 9. Chain health

**HEALTHY**, 0 findings across orphan detection, provenance, timestamp,
transition, outcome/execution duplication. Provenance: all recorded chains are
`REAL` (observation `source=precision_signals`, decision `source=decision_rule`).

## 10. Data quality

- NIFTY spot for execution: **STALE flag** — `live_market_fetch` returned the
  15:29:00 IST bar of the day with `is_live=True` at 18:58 IST (after hours).
  This is the existing fetch behavior; the runner consumed it, but the regime
  gate still produced STAY_OUT, so no trade decision was distorted. Flagged per
  spec §16; not treated as fresh. The GT observation records the REAL price it
  used with REAL provenance, and freshness metadata (`freshness_status=REAL`,
  cache age) is stored in the snapshot.
- Option chain/OI (cached snapshot, PCR 0.777, walls), VIX (cached 11.42),
  institutional (cached NEUTRAL): all from cache with provenance REAL.
- Quote used for MTM: none required (0 FSM positions); legacy positions are not
  MTM'd (no fabricated marks).

## 11. Problems found

1. **Test-suite → production Ground Truth write (fixed).** Documented in §4.
   Test-only change; re-verified byte-identical after full suite.
2. **After-hours "live" flag (observed, not fixed).**
   `live_market_fetch.fetch_live_market_spot` labels the last intraday bar as
   live after close. Harmless today (gate blocked the trade) but must be
   recognized as a stale-data risk if a genuine candidate ever appears after
   hours. No code changed (observation phase; logged for the continuation).

## 12. Strategy changes

**NONE.** `git diff` for this phase touches only
`tests/test_fix_verification.py` (integrity isolation). Strategy, entry,
signal, thresholds, RANGE_LV→NO_TRADE, confluence minimum, confidence,
capital guard, sizing, strike selection, stop, target, expiry square-off:
**all unchanged and frozen.**

## 13. Conclusions (per spec taxonomy)

| Item | Verdict |
|---|---|
| Baseline + window recorded | OBSERVED |
| Genuine signal cycle | OBSERVED (1 cycle, STAY_OUT) |
| Directional candidate evidence | UNKNOWN (none generated) |
| Decision verification | OBSERVED (SKIP consistent with frozen rules) |
| Paper entry / FSM / exit / outcome | NOT_OBSERVED (verified by prior-phase tests + green suite) |
| MTM read-only safety | OBSERVED (PASS) |
| Reconciliation / chain health | OBSERVED (MATCH / HEALTHY) |
| Trading edge | **INSUFFICIENT_SAMPLE** — 0 directional predictions, 0 outcomes |

## 14. Next steps (bounded by spec)

- Continue observation through 2026-08-14 15:30 IST (market hours) with the
  same runner; a genuine candidate will be allowed to flow through the frozen
  FSM→GT→exit→outcome→evaluation pipeline unmodified.
- Do **not** start optimization/A-B/ML retraining until ≥ several genuine
  outcomes exist for controlled evaluation.
