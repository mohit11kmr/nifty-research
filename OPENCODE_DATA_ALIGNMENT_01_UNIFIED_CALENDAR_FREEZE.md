# OpenCode — DATA-ALIGNMENT-01
# Unified Trading Calendar + Cross-Dataset Alignment + Research Dataset Freeze

## Objective

The options EOD deep archive is complete and verified for 2024-01-01 → 2026-08-13. VIX and participant-OI have also been expanded. However, two genuine sessions are present in the options archive but absent from the current NIFTY/Yahoo-driven trading-day list:

- 2025-02-01 — special Saturday session
- 2026-08-11 — genuine trading session

This phase establishes one authoritative historical session calendar, backfills the two sessions in other datasets where legitimately available, cross-validates all datasets, and freezes one unified research manifest.

This is DATA ALIGNMENT / VALIDATION ONLY.

## Critical Rules

Do NOT:

- change strategy logic or thresholds
- change regime/confluence/risk/SL/TP/expiry rules
- optimize or run parameter sweeps
- promote Range-HV
- run strategy experiments
- train ML
- modify Ground Truth or paper_account.json
- fabricate, interpolate, or forward-fill missing market data
- silently drop genuine sessions
- overwrite the verified options archive
- replace official data with Yahoo without provenance

Goal:

```text
ONE AUTHORITATIVE HISTORICAL CALENDAR
+
ONE ALIGNED DATASET
+
NO STRATEGY CHANGES
```

---

# 1. Read Current Data Documents

Read:

```text
audit/OPTIONS-EOD-DATA-ARCHIVE.md
audit/DEEP-HISTORICAL-DATA-RESEARCH.md
audit/HISTORICAL-DATA-COVERAGE-EXPANDED.md
audit/DATA-SOURCE-RESEARCH.md
audit/ANGELONE-DATA-INTEGRATION.md
audit/PHASE-F3-EXPIRY-CONSISTENCY-BACKTEST.md
```

Inspect:

```text
data/historical/normalized/options_eod_expanded.csv
data/historical/normalized/vix_expanded.csv
data/historical/normalized/participant_oi_expanded.csv
data/historical/raw/bhavcopy/
data/historical/manifests/
nifty_history.csv
calendar_expiry.py
historical_expiry.py
collect_historical_data.py
```

---

# 2. Create the Authoritative Session Calendar

Use source priority:

1. NSE/options EOD trading-date evidence
2. NSE official market/holiday evidence
3. Existing validated project calendars
4. Other sources only for cross-checking

Do NOT use Yahoo as the sole authority.

Create:

```text
data/historical/normalized/trading_calendar_expanded.csv
```

Columns:

```text
date
session_status
source_evidence
source_file
provenance
```

Statuses:

```text
TRADING_SESSION
MARKET_HOLIDAY
NO_ARCHIVE
UNKNOWN
```

---

# 3. Investigate the Two Known Mismatches

Explicitly verify:

```text
2025-02-01
2026-08-11
```

For each determine:

```text
was market open?
which datasets contain it?
which datasets lack it?
why?
```

Do not assume the existing Yahoo day list is correct.

---

# 4. Backfill 2025-02-01

Search official/legitimate sources for:

```text
NIFTY
VIX
participant OI
other required expanded inputs
```

If legitimate data exists:

- collect
- normalize
- preserve raw provenance
- hash
- validate

If a dataset genuinely lacks the session:

```text
MISSING
```

Do not fill from adjacent days.

---

# 5. Backfill 2026-08-11

Do the same for:

```text
NIFTY
VIX
participant OI
```

Options EOD already contains the session.

Do not overwrite the verified options archive.

---

# 6. Dataset-by-Dataset Alignment

For:

```text
options_eod_expanded
vix_expanded
participant_oi_expanded
nifty_history
other canonical historical inputs
```

produce:

```text
date
calendar_session_status
dataset_status
```

Dataset status:

```text
PRESENT
MISSING
NOT_APPLICABLE
INVALID
UNKNOWN
```

Distinguish a market holiday from a dataset gap.

---

# 7. Never Silently Drop Real Sessions

If canonical calendar says:

```text
TRADING_SESSION
```

but a dataset has no observation:

```text
DATASET_GAP
```

Report it explicitly.

Do not remove the date from the common calendar.

---

# 8. No Fabrication

For missing data use:

```text
MISSING
```

Never:

- interpolate VIX
- forward-fill participant OI
- copy previous-day values
- use next-day values
- infer session data from unrelated series

---

# 9. Cross-Dataset Validation

For each canonical trading session check:

```text
NIFTY underlying price
options underlying price
VIX date
participant-OI date
options trade date
expiry calendar
```

Validate:

```text
date alignment
timezone
underlying consistency
```

For options EOD `UndrlygPric`, compare against the best official NIFTY reference where applicable and report tolerance.

---

# 10. Special Session: 2025-02-01

Treat this separately because it is a Saturday session.

Verify:

```text
options session
NIFTY session
VIX
participant OI
session timing if available
```

Do not apply normal weekday assumptions.

---

# 11. Recent Session: 2026-08-11

Verify all datasets and determine why it was absent from `nifty_history.csv`.

Treat the issue as a source-calendar problem unless evidence proves otherwise.

Preserve provenance if NIFTY data must be repaired.

---

# 12. Unified Dataset Manifest

Create:

```text
data/historical/manifests/unified_research_dataset.json
```

Include:

```text
dataset_name
calendar_path
calendar_hash
options_dataset
options_hash
vix_dataset
vix_hash
participant_oi_dataset
participant_oi_hash
nifty_dataset
nifty_hash
expiry_calendar
expiry_hash
coverage_start
coverage_end
trading_sessions
missing_dataset_days
provenance_summary
schema_version
created_at
```

This becomes the frozen input manifest for future research.

---

# 13. Unified Coverage Matrix

Create/update:

```text
audit/HISTORICAL-DATA-COVERAGE-UNIFIED.md
```

For every canonical session:

```text
date
NIFTY
OPTIONS_EOD
OI
VIX
PARTICIPANT_OI
EXPIRY
SESSION_STATUS
OVERALL_STATUS
```

Overall status:

```text
FULL
PARTIAL
INSUFFICIENT
INVALID
```

Never hide partial days.

---

# 14. Canonical Calendar Hash

Create a deterministic hash of canonical session rows:

```text
calendar_hash = SHA256(sorted canonical session rows)
```

Same calendar must produce same hash.

---

# 15. Freeze Without Overwriting Source Datasets

Do not rewrite source datasets merely to create the unified view.

Future research should reference:

```text
unified_research_dataset.json
```

and its exact hashes rather than rediscovering files ad hoc.

---

# 16. Reproducibility

Run alignment twice.

Require:

```text
same calendar
same hashes
same coverage
same classifications
```

except documented timestamps.

---

# 17. Idempotency

Run a second time.

Expected:

```text
new downloads = 0
duplicate raw files = 0
normalized stats identical
hashes identical
```

No incremental-run clobber.

---

# 18. Tests

Create:

```text
tests/test_unified_data_alignment.py
```

Test:

- canonical calendar generation
- 2025-02-01 classification
- 2026-08-11 classification
- missing-session detection
- no forward-fill
- no interpolation
- no future-data usage
- date alignment
- timezone
- underlying validation
- manifest hashes
- deterministic output
- idempotency
- production isolation

---

# 19. Production Safety

Do NOT modify:

```text
data/ground_truth.db
paper_account.json
production signals
production outcomes
live order state
```

Only historical research data and audit artifacts may change.

---

# 20. Strategy Must Remain Untouched

Do NOT modify:

```text
strategies/*.yaml
regime_filter.py
precision_signals.py
capital_guard.py
paper_execution.py
exit_evaluator.py
strategy_schema.py
strategy_validator.py
strategy_compiler.py
```

unless a pure data-calendar compatibility change is unavoidable.

If strategy modification appears necessary:

STOP and report.

---

# 21. Do Not Wire Into Backtest Yet

This phase ends with:

```text
aligned datasets
+
frozen manifest
+
coverage evidence
```

Do NOT modify:

```text
regime_filter
backtest_frozen
multi_strategy_backtest
Strategy Creator
paper runner
```

The aligned dataset must first be reviewed.

---

# 22. Documentation

Create:

```text
audit/DATA-ALIGNMENT-01-UNIFIED-CALENDAR.md
```

Include:

## Canonical Calendar

## Source Priority

## 2025-02-01

## 2026-08-11

## Dataset Alignment

## Missing Data

## Cross-Dataset Validation

## Coverage

## Dataset Hashes

## Reproducibility

## Idempotency

## Production Isolation

## Limitations

## Frozen Manifest

---

# 23. Final Response

Return exactly:

```text
DATA-ALIGNMENT-01 — UNIFIED HISTORICAL DATASET

Canonical Calendar:
<path>

Calendar Hash:
<hash>

Coverage:
<start → end>

Trading Sessions:
X

Market Holidays:
X

2025-02-01:
PRESENT / MISSING / UNKNOWN

2026-08-11:
PRESENT / MISSING / UNKNOWN

NIFTY:
FULL / PARTIAL / INSUFFICIENT

OPTIONS EOD:
FULL / PARTIAL / INSUFFICIENT

VIX:
FULL / PARTIAL / INSUFFICIENT

PARTICIPANT OI:
FULL / PARTIAL / INSUFFICIENT

EXPIRY:
FULL / PARTIAL / INSUFFICIENT

Cross-Dataset Alignment:
PASS/FAIL

Underlying Validation:
PASS/FAIL

No Fabrication:
PASS/FAIL

Point-in-Time:
PASS/FAIL

Reproducibility:
PASS/FAIL

Idempotency:
PASS/FAIL

Production Data Untouched:
YES/NO

Unified Dataset Manifest:
<path>

Manifest Hash:
<hash>

Largest Remaining Data Gap:
<description>

Most Important Finding:
<description>

Next Safe Phase:
REVIEW / H3 RISK-SEMANTICS / BACKTEST SANITY CHECK / HOLD
```

## FINAL RULE

The goal is:

```text
ONE AUTHORITATIVE SESSION CALENDAR
        +
ALIGNED DATASETS
        +
FROZEN HASHED MANIFEST
        =
TRUSTWORTHY RESEARCH INPUT
```

Do not optimize the strategy.
Do not change the strategy.
Do not run experiments.
Do not fabricate missing data.

First establish unified data truth. Then research strategies against it.
