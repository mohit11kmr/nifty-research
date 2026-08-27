# OpenCode — DATA EXPANSION v2
## Comprehensive Historical Market Data Research + Angel One SmartAPI Integration

### Objective
Build the most complete, truthful, provenance-aware NIFTY/options research dataset realistically available from:
- Official NSE / primary sources
- Angel One SmartAPI
- Reputable secondary sources only when necessary

This is a **data acquisition, validation, and integration phase** only.

DO NOT change strategy, thresholds, confluence, RANGE_LV, SL/TP, capital guard, expiry rules, ML behavior, or live execution. Do not optimize, fabricate, silently fill missing data, overwrite verified datasets, modify Ground Truth, modify paper account, expose credentials, or purchase paid data automatically.

---

## 1. READ PROJECT FIRST

Read:
```text
audit/MASTER-PROJECT-BLUEPRINT.md
audit/PHASE-H-MULTI-STRATEGY-BACKTEST.md
audit/PHASE-H1-V2-STRATEGY-LAB.md
audit/PHASE-F3-EXPIRY-CONSISTENCY-BACKTEST.md
audit/PHASE-G-NETWORK-RESILIENCE.md
audit/TRADING_DECISION_FLOW.md
```

Inspect:
```text
data/
data/historical/
data/oi_snapshots/
research.db
nifty_history.csv
india_vix.csv
fii_dii_history.csv
ml_features.csv
collect_historical_data.py
live_market_fetch.py
data_fetcher.py
oi_intel.py
mcp_nifty.py
history_logger.py
quant_daemon.py
```

Also inspect any existing Angel One/SmartAPI integration. Never print secrets.

---

## 2. INVENTORY CURRENT DATA

Create a source/coverage table for:
- NIFTY historical and intraday
- options EOD and intraday
- OI
- VIX
- FII/DII
- expiry/contract master
- ML features
- live feeds

For every dataset record source, date range, granularity, provenance, freshness, and whether it is canonical.

---

## 3. DEEP INTERNET RESEARCH

Research current official sources first:
- NSE F&O reports
- NSE UDiFF / bhavcopy
- NSE OI
- participant-wise OI
- FII derivatives statistics
- contract files
- historical EOD
- historical trade/order data
- historical/intraday snapshot products

Then research reputable providers, broker APIs, public datasets, academic datasets, and archives.

For every source verify:
- exact coverage
- granularity
- historical depth
- access method
- cost
- current URL
- provenance
- license/terms evidence where available
- limitations

Do not assume an old API/page still works; verify current official documentation.

---

## 4. ANGEL ONE SMARTAPI

The user has an Angel One account.

Investigate current official SmartAPI capabilities for:
- authentication
- instrument master
- historical candle API
- supported exchanges/intervals
- WebSocket
- live NIFTY
- live option prices where supported
- historical option candles
- expired F&O contract history
- historical OI
- option-chain capability
- rate limits
- retention/depth

Classify every capability:
```text
SUPPORTED
NOT_SUPPORTED
UNKNOWN
```

Never ask the user to paste API keys, password, TOTP, access tokens, or client secrets into chat.

If local credentials exist, read them from the existing local environment/config only and never print them.

Create:
```text
audit/ANGELONE-DATA-INTEGRATION.md
```

Document:
- capabilities verified
- limitations
- authentication status
- instrument/token mapping
- historical limitations
- OI/option-chain availability
- WebSocket/live capabilities
- current-source comparison
- recommended role of Angel One

Do not place orders or call trading/order endpoints for this phase.

---

## 5. ANGEL ONE ROLE

Do not automatically replace the current live data source.

If supported, use Angel One first as an isolated candidate for:
- live NIFTY
- supported live option prices
- supported futures
- supported historical candles

Compare Angel One with the existing source for:
- timestamp
- symbol
- price
- freshness
- contract mapping

Classify:
```text
MATCH
MINOR_DIFFERENCE
CONFLICT
NOT_TESTED
```

If Angel One lacks expired F&O history or historical OI, mark the gap explicitly and use other verified sources.

---

## 6. DATA PRIORITY

Prioritize:
```text
P0 historical option-chain/OI intraday
P1 historical option price/tick
P2 NIFTY intraday
P3 VIX intraday
P4 FII/DII
P5 order-book history
```

Do not spend time on P5 while P0 is unresolved.

---

## 7. HISTORICAL OPTIONS/OI

Search specifically for:
- historical NIFTY option chain
- historical option OI
- 1-minute/5-minute option snapshots
- historical option trades/ticks
- historical bid/ask
- underlying spot with option records

For each candidate source record:
```text timestamp
underlying
expiry
strike
CE/PE
LTP
bid
ask
volume
OI
underlying price
source
```

Prefer intraday snapshots over EOD when legitimately available.

If only EOD exists, label `EOD_ONLY`.

Never fabricate historical OI or option prices.

---

## 8. NIFTY / VIX / FII-DII / CONTRACTS

Collect/research:
- NIFTY 1m/5m/15m
- India VIX EOD/intraday
- FII derivatives / participant OI / DII where available
- contract master, expiry, strike, CE/PE, lot size, trade dates

Use existing:
```text
calendar_expiry.py
historical_expiry.py
```
as internal canonical expiry logic after external verification.

Do not replace historical expiry with guessed weekday rules.

---

## 9. POINT-IN-TIME / NO LOOKAHEAD

For every record store where possible:
```text
source_timestamp
availability_timestamp
retrieved_at
```

For decision time `t`, only data with:
```text
availability_timestamp <= t
```
may be used.

Detect future timestamps, future snapshots, and late-published information where relevant.

---

## 10. RAW / NORMALIZED / QUARANTINE

Use:
```text
data/historical/raw/
data/historical/normalized/
data/historical/quarantine/
data/historical/manifests/
```

Rules:
- RAW = immutable source copy
- NORMALIZED = canonical project schema
- QUARANTINE = uncertain/conflicting/unverified

Never merge quarantined data into the canonical dataset automatically.

---

## 11. CANONICAL SCHEMA

Options:
```text
timestamp
underlying
instrument
expiry
strike
side
ltp
bid
ask
volume
oi
underlying_price
source
source_url
retrieved_at
raw_file_hash
availability_time
provenance
quality
```

Index:
```text
timestamp
symbol
open
high
low
close
volume
source
source_url
retrieved_at
raw_file_hash
availability_time
provenance
quality
```

Provenance values:
```text
REAL
CACHED_REAL
ESTIMATED
SIMULATED
UNKNOWN
```

Never label reconstructed data REAL.

---

## 12. SOURCE QUALITY

Classify:
```text
A = official primary
B = reputable provider
C = public/community but verifiable
D = uncertain provenance
E = unusable
```

Only A/B enter canonical datasets by default.
C stays quarantined until reviewed.
D/E are not canonical.

---

## 13. DUPLICATES / CONFLICTS

When multiple sources overlap, compare:
- timestamp
- price
- OI
- volume
- expiry
- strike

Classify:
```text
MATCH
MINOR_DIFFERENCE
CONFLICT
```

Do not silently choose a source.

Keep conflicting raw records.

---

## 14. MANIFEST + COVERAGE

Every downloaded/normalized dataset must have a manifest containing:
```text
dataset
source
source_url
retrieved_at
coverage_start
coverage_end
granularity
format
sha256
provenance
quality
```

Create:
```text
audit/DATA-SOURCE-RESEARCH.md
audit/HISTORICAL-DATA-COVERAGE-EXPANDED.md
audit/DEEP-HISTORICAL-DATA-RESEARCH.md
```

Coverage matrix per trading day:
```text
date
NIFTY EOD
NIFTY intraday
OPTIONS EOD
OPTIONS intraday
OI
VIX
FII/DII
contract master
expiry
FULL
PARTIAL
INSUFFICIENT
```

Where possible report 1-year, 2-year, and 3-year coverage, but do not expand the backtest window automatically.

---

## 15. DATA EXPANSION TARGET

Aim for:
```text
minimum useful: 2 years
preferred: 3+ years
```

especially for NIFTY, options, OI, expiry and VIX.

Only use reliably sourced years.

---

## 16. COLLECTOR

Create or safely extend:
```text
collect_historical_data_deep.py
```

Suggested CLI:
```bash
python collect_historical_data_deep.py discover
python collect_historical_data_deep.py audit
python collect_historical_data_deep.py angelone-capabilities
python collect_historical_data_deep.py collect
python collect_historical_data_deep.py validate
python collect_historical_data_deep.py coverage
python collect_historical_data_deep.py manifest
```

Implement:
- checksum verification
- duplicate prevention
- timeout/retry/backoff
- resume
- provenance
- no-secret logging

Do not require credentials if public sources are available.

If Angel One is not configured:
```text
ANGELONE_NOT_CONFIGURED
```
and continue the rest of the phase.

---

## 17. LIVE ANGEL ONE READ-ONLY TEST

If credentials are locally available, run an isolated read-only test:
- authentication
- instrument lookup
- NIFTY quote
- supported option quote
- timestamp/freshness
- WebSocket/reconnect if supported

Do not place an order.

---

## 18. NETWORK / STALE DATA

Use Phase G resilience rules.

For any new feed:
```text
network failure
→ STALE/MISSING
→ no false trade
→ reconnect
→ REAL/FRESH
```

A cached value must expose its age/status.

Never allow stale cache to masquerade as live.

Test:
- NIFTY stale
- options stale
- VIX stale
- all feeds stale

without changing strategy.

---

## 19. TESTS

Create:
```text
tests/test_data_expansion.py
tests/test_angelone_data.py
```

Test:
- manifest
- checksums
- provenance
- timestamp/timezone normalization
- option validation
- expiry/CE/PE
- OI
- point-in-time filtering
- duplicate detection
- conflict detection
- stale cache
- Angel One auth handling
- instrument mapping
- live quote handling
- failure/recovery
- no secrets in logs
- no production writes

Use mocks/fixtures; unit tests must not depend on live external APIs.

---

## 20. PRODUCTION SAFETY

Do NOT modify:
```text
data/ground_truth.db
paper_account.json
production signals
production outcomes
live order state
```

Do not use Ground Truth as historical data storage.

If the already-running daemon writes legitimate observation rows, distinguish those from collector/test writes.

Fingerprint existing verified datasets before collection and verify hashes/mtimes afterward. Never silently overwrite:
```text
data/historical/
data/oi_snapshots/
research.db
```

---

## 21. PAID DATA

If the best source is paid:
```text
DO NOT PURCHASE
```

Report:
```text
provider
dataset
coverage
granularity
cost
access requirements
why it adds value
```

No automatic purchase.

---

## 22. BACKTEST READINESS

At the end classify:
```text
FULL_HISTORICAL_BACKTEST_READY
PARTIAL_BACKTEST_READY
EOD_ONLY
INTRADAY_DATA_MISSING
OPTIONS_TICK_DATA_MISSING
PAID_DATA_REQUIRED
ANGELONE_NOT_CONFIGURED
```

Explain exactly why.

A frozen backtest may be rerun only as a data-quality sanity check. Do not optimize.

---

## 23. STRATEGY MUST REMAIN UNCHANGED

Do not modify:
```text
strategies/*.yaml
precision_signals.py
regime_filter.py
capital_guard.py
paper_execution.py
exit_evaluator.py
```

unless a pure data-ingestion compatibility fix is unavoidable.

If a strategy change appears necessary:
STOP and report.

---

## 24. FINAL TESTING

Run:
```bash
python test_all.py
python -m unittest discover -s tests -v
python tests/test_fix_verification.py
pip check
pip-audit
git diff --check
```

Report:
- new tests
- existing tests
- total tests
- production isolation

---

# FINAL RESPONSE

Return exactly:

```text
DATA EXPANSION v2 — FINAL REPORT

Historical Window:
<start → end>

NIFTY EOD:
<summary>

NIFTY Intraday:
<summary>

OPTIONS EOD:
<summary>

OPTIONS Intraday:
<summary>

OPTIONS Ticks:
<summary>

OI:
<summary>

VIX:
<summary>

FII/DII:
<summary>

Expiry / Contract Master:
<summary>

ANGEL ONE:
Configured: YES/NO
Authentication: PASS/FAIL/NOT_CONFIGURED
Instrument Lookup: PASS/FAIL/NOT_TESTED
NIFTY Live Quote: PASS/FAIL/NOT_TESTED
Supported Option Quote: PASS/FAIL/NOT_TESTED
Historical Candle API: AVAILABLE/UNAVAILABLE/UNKNOWN
Expired F&O Historical: AVAILABLE/UNAVAILABLE/UNKNOWN
Historical OI: AVAILABLE/UNAVAILABLE/UNKNOWN
Option Chain: AVAILABLE/UNAVAILABLE/UNKNOWN
WebSocket: AVAILABLE/UNAVAILABLE/UNKNOWN
Current Source Comparison: MATCH/MINOR_DIFFERENCE/CONFLICT/NOT_TESTED
Recommended Role: <description>

Sources Researched:
X

Official Sources:
X

Free Sources:
X

Paid Sources Identified:
X

Accepted Sources:
X

Rejected Sources:
X

Trading Days:
X

FULL Data Days:
X

PARTIAL Data Days:
X

INSUFFICIENT Data Days:
X

Point-in-Time:
PASS/FAIL

Provenance:
PASS/FAIL

Conflict Detection:
PASS/FAIL

Freshness:
PASS/FAIL

No Fabricated Data:
YES/NO

Network Recovery:
PASS/FAIL

Production Data Untouched:
YES/NO

Tests:
PASS/FAIL

Canonical Dataset:
<path>

Dataset Hash:
<hash>

Most Valuable New Dataset:
<description>

Biggest Remaining Data Gap:
<description>

Paid Data With Highest Value:
<description>

Backtest Readiness:
FULL_HISTORICAL_BACKTEST_READY / PARTIAL_BACKTEST_READY / EOD_ONLY / INTRADAY_DATA_MISSING / OPTIONS_TICK_DATA_MISSING / PAID_DATA_REQUIRED / ANGELONE_NOT_CONFIGURED

Strategy Changed:
NO

Optimization:
NO

AI Strategy Generation:
NO

Next Safe Phase:
BACKTEST / MORE DATA / REVIEW / HOLD
```

# FINAL RULE

**Data first. Strategy second. Optimization last.**

Use official/primary sources whenever possible.

Use Angel One only for capabilities actually verified from current documentation and the connected account.

Never label estimated/reconstructed data REAL.
Never use future information.
Never silently overwrite verified datasets.
Never purchase paid data automatically.
Never place an order.
Never change the trading strategy during this phase.
