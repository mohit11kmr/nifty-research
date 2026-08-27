# OpenCode — DATA-ARCHIVE-01
# Angel One Historical Market Recorder + Proprietary Research Data Archive

## Objective

Build a read-only, provenance-aware market-data recorder so NIFTY/options contracts are archived while they are live.

The verified Angel One capability report establishes:

- live NFO WebSocket streaming is supported
- current OI is supported
- historical OI is supported for LIVE F&O contracts
- historical candles are supported for LIVE option contracts
- expired option historical candles are NOT supported
- expired F&O contract master/history is NOT supported
- the daily instrument master contains currently tradable instruments
- WebSocket V2 supports NFO streaming and reconnect

Therefore the long-term solution is:

```text
LIVE CONTRACT
    ↓
ANGEL ONE
    ↓
RAW ARCHIVE
    ↓
NORMALIZED RESEARCH DATA
    ↓
FUTURE BACKTEST
```

This phase is DATA ONLY.

---

# CRITICAL RULES

DO NOT:

- change any strategy
- change thresholds/confluence/regime/SL/TP/capital/expiry rules
- optimize anything
- run parameter sweeps
- add AI strategy generation
- create real trades
- call placeOrder/modifyOrder/cancelOrder/GTT/EDIS
- write market data into Ground Truth
- modify paper_account.json
- fabricate missing ticks
- forward-fill stale data as fresh
- label estimates as REAL
- expose API credentials
- automatically buy paid data

The recorder must be broker-order-disabled.

---

# 1. READ PROJECT FIRST

Read:

```text
audit/MASTER-PROJECT-BLUEPRINT.md
audit/PHASE-G-NETWORK-RESILIENCE.md
audit/PHASE-F3-EXPIRY-CONSISTENCY-BACKTEST.md
audit/PHASE-H1-V2-STRATEGY-LAB.md
audit/DEEP-HISTORICAL-DATA-RESEARCH.md
audit/DATA-SOURCE-RESEARCH.md
audit/ANGELONE-DATA-INTEGRATION.md
```

Inspect:

```text
quant_daemon.py
live_market_fetch.py
data_fetcher.py
history_logger.py
oi_intel.py
mcp_nifty.py
calendar_expiry.py
historical_expiry.py
```

Inspect existing SmartAPI integration if present.

Never print secrets.

---

# 2. DAILY INSTRUMENT MASTER ARCHIVE

Archive the Angel One instrument master before market activity each trading day.

Store raw immutable copies under:

```text
data/market_archive/instrument_master/YYYY-MM-DD/
```

Record:

```text
raw file
retrieved_at
sha256
source URL
record count
```

Extract relevant NIFTY/NFO contracts into:

```text
data/market_archive/contracts/YYYY-MM-DD.csv
```

or the project's existing efficient format.

---

# 3. CONTRACT METADATA

Archive at least:

```text
exchange
exchange segment
token
symbol
name
underlying
instrument type
expiry
strike
CE/PE
lot size
tick size
freeze quantity
```

Preserve:

```text
date + token + contract metadata
```

because tokens may be recycled after expiry.

---

# 4. CONTRACT DISCOVERY

Create a deterministic subscription planner.

Priority:

```text
NIFTY index
NIFTY futures
NIFTY options
```

For options use an explicit configurable selection policy, not strategy logic.

Example:

```text
ATM
+ N strikes above
+ N strikes below
+ current/next relevant expiries
```

Do not optimize this coverage in this phase.

Record the exact subscription plan.

---

# 5. WEBSOCKET V2

Use Angel One WebSocket V2.

Capture, when available and trustworthy:

```text
exchange/event timestamp
local receive timestamp
token
symbol
LTP
open
high
low
close
volume
OI
bid
ask
best-5 only if verified reliable
```

The verified report notes unreliable `openInterestChange` and an SDK issue around best-5 buy/sell labels.

Do not store known-unreliable fields as canonical REAL values.

Use explicit quality flags such as:

```text
INVALID_OR_UNTRUSTED
```

when appropriate.

---

# 6. RAW FIRST

Raw data must be written before normalization.

Suggested:

```text
data/market_archive/raw/YYYY/MM/DD/angelone_ws/
data/market_archive/raw/YYYY/MM/DD/instrument_master/
```

Raw files are append-only and immutable.

Do not rewrite historical raw data in place.

---

# 7. NORMALIZED DATA

Create:

```text
data/market_archive/normalized/
```

Options schema:

```text
event_time
receive_time
exchange
exchange_segment
token
symbol
underlying
instrument_type
expiry
strike
side
ltp
open
high
low
close
volume
oi
bid
ask
source
source_url
instrument_master_date
retrieved_at
raw_file_hash
availability_time
provenance
quality
```

Do not fabricate missing fields.

---

# 8. TIME / TIMEZONE

Canonical project timezone:

```text
Asia/Kolkata
```

Preserve:

```text
exchange/event timestamp
local receive timestamp
```

Detect:

```text
future timestamps
duplicate ticks
out-of-order events
invalid values
```

Do not silently repair anomalies.

---

# 9. POINT-IN-TIME

Every record must expose:

```text
event_time
availability_time
```

A historical decision at `t` may only use records where:

```text
availability_time <= t
```

This is mandatory.

---

# 10. DUPLICATES / ORDERING

Classify duplicates as:

```text
EXACT_DUPLICATE
CONFLICTING_DUPLICATE
```

Do not silently discard conflicting records.

Preserve raw order, normalize by event time, and record out-of-order anomalies.

---

# 11. NETWORK RESILIENCE

Follow Phase G behavior:

```text
NETWORK ON
→ STREAMING

NETWORK OFF
→ STALE/MISSING
→ NO FABRICATED DATA
→ RECONNECT

NETWORK ON
→ FRESH STREAM
```

Record:

```text
connect_time
disconnect_time
reconnect_time
retry_count
resubscribe_count
reason
```

Preserve gaps. Never invent missing ticks.

---

# 12. HEARTBEAT / RATE LIMITS

Monitor WebSocket heartbeat.

If heartbeat fails:

```text
connection_state = STALE
```

then controlled reconnect.

Honor verified Angel One rate limits.

Centralize timeout/retry/backoff configuration.

A failed request is never valid market data.

---

# 13. DAILY SESSION LIFECYCLE

Support:

```text
PREOPEN
OPEN
RUNNING
DISCONNECTED
RECOVERING
CLOSING
CLOSED
```

Target trading window:

```text
09:15–15:30 IST
```

Use the project's trading calendar for holidays.

---

# 14. DAILY CLOSE

At close:

1. Stop adding new subscriptions.
2. Flush buffered events.
3. Validate counts.
4. Compute hashes.
5. Write manifest.
6. Mark day:

```text
COMPLETE
PARTIAL
FAILED
```

A significant unresolved stream gap means `PARTIAL`, not `COMPLETE`.

---

# 15. DAILY MANIFEST

Create:

```text
data/market_archive/manifests/YYYY-MM-DD.json
```

Include:

```text
date
source
instrument_master_sha256
raw_files
normalized_files
contracts_subscribed
events_received
events_normalized
duplicates
conflicts
disconnects
reconnects
coverage_start
coverage_end
status
```

Do not invent counts.

---

# 16. DATA QUALITY

Use:

```text
REAL
CACHED_REAL
STALE
MISSING
INVALID
UNKNOWN
```

Raw Angel One observations can be `REAL` when actually received.

Known-unreliable fields must carry appropriate quality flags.

---

# 17. CONTRACT ARCHIVE VALUE

Preserve enough data to support future:

```text
option entry/exit reconstruction
OI evolution
intraday PCR derivation where fields permit
MFE/MAE
stop/target research
vertical spreads
iron condors
other defined-risk option research
```

Do not claim a capability unless archived fields actually support it.

---

# 18. NO GROUND TRUTH / PAPER COUPLING

The recorder must never write market ticks to:

```text
data/ground_truth.db
```

and never write:

```text
data/paper_account.json
```

Ground Truth remains the decision/outcome ledger.

---

# 19. NO ORDER ENDPOINTS

The recorder must not call:

```text
placeOrder
modifyOrder
cancelOrder
GTT
EDIS
```

Add a safety test for prohibited trading calls.

---

# 20. LOCAL SECRETS

Use existing local environment/config.

Never print, persist, commit, or report:

```text
API key
client ID
PIN
TOTP secret
JWT
refresh token
feed token
```

If credentials are unavailable:

```text
ANGELONE_NOT_CONFIGURED
```

Do not ask the user to paste secrets into chat.

---

# 21. CLI

Create:

```text
angelone_market_recorder.py
```

Commands:

```bash
python angelone_market_recorder.py status
python angelone_market_recorder.py discover
python angelone_market_recorder.py plan
python angelone_market_recorder.py run
python angelone_market_recorder.py validate YYYY-MM-DD
python angelone_market_recorder.py manifest YYYY-MM-DD
python angelone_market_recorder.py coverage
```

`run` must require explicit invocation.

Do not add cron/systemd automation in this phase.

---

# 22. DRY RUN

Support:

```bash
python angelone_market_recorder.py plan
python angelone_market_recorder.py run --dry-run
```

Dry-run:

- loads config
- parses instrument master
- calculates subscription plan
- reports contracts/tokens
- does NOT stream
- does NOT place orders

---

# 23. CONTRACT PLAN REPORT

`plan` should report:

```text
date
ATM reference
expiry dates
strike range
contracts selected
tokens selected
CE count
PE count
futures count
```

Do not optimize the plan.

---

# 24. SOURCE COMPLEMENT

At/after close, if official NSE EOD is available:

Archive it separately.

Keep:

```text
source = ANGEL_ONE
source = NSE
```

as separate source records.

Optionally create normalized cross-source comparisons.

---

# 25. SOURCE COMPARISON

Compare aligned Angel One vs NSE fields:

```text
timestamp
price
OI where semantics match
volume where semantics match
contract
```

Classify:

```text
MATCH
MINOR_DIFFERENCE
CONFLICT
NOT_COMPARABLE
```

Do not declare one source incorrect without evidence.

---

# 26. TESTS

Create:

```text
tests/test_angelone_market_recorder.py
```

Test with mocks/fixtures:

- instrument master parsing
- contract filtering
- CE/PE
- expiry
- strike
- subscription planning
- duplicate handling
- conflict handling
- out-of-order events
- timestamp normalization
- timezone
- availability time
- manifest
- checksum
- disconnect/reconnect
- resubscribe
- stale status
- gap preservation
- close flush
- no order endpoints
- no secret logging
- no Ground Truth writes
- no paper-account writes

The full test suite must not require live Angel One.

---

# 27. PRODUCTION ISOLATION

Before any controlled live recorder session:

Record:

```text
paper_account.json hash
ground_truth.db hash/mtime
```

After validation, verify unchanged.

Archive files are expected to change; production trading/ledger state is not.

---

# 28. DOCUMENTATION

Create:

```text
audit/DATA-ARCHIVE-01-ANGELONE-MARKET-RECORDER.md
```

Include:

- objective
- Angel One capabilities used
- archived fields
- contract-selection policy
- WebSocket modes
- timestamps/timezone
- point-in-time rules
- network recovery
- rate limits
- storage
- provenance
- daily manifest
- source comparison
- secrets/security
- production isolation
- tests
- limitations
- future research capabilities

---

# 29. ACCEPTANCE CRITERIA

```text
Authentication                         PASS/FAIL
Instrument master archive              PASS/FAIL
Contract discovery                     PASS/FAIL
Subscription planner                  PASS/FAIL
NIFTY streaming                        PASS/FAIL
Options streaming                      PASS/FAIL
OI capture                             PASS/FAIL
Raw immutable archive                  PASS/FAIL
Normalized archive                    PASS/FAIL
Timestamp/timezone correctness         PASS/FAIL
Point-in-time availability             PASS/FAIL
Duplicate handling                     PASS/FAIL
Conflict handling                      PASS/FAIL
Disconnect detection                   PASS/FAIL
Reconnect                              PASS/FAIL
Resubscribe                            PASS/FAIL
Gap preservation                       PASS/FAIL
Daily manifest                         PASS/FAIL
Daily close flush                      PASS/FAIL
Rate-limit safety                      PASS/FAIL
No order endpoints                    PASS/FAIL
No secret leakage                     PASS/FAIL
No Ground Truth writes                PASS/FAIL
No paper-account writes               PASS/FAIL
Tests                                  PASS/FAIL
Production isolation                  PASS/FAIL
```

All critical items must PASS before recommending regular daily collection.

---

# 30. STOP AFTER IMPLEMENTATION

Do NOT:

- add cron/systemd
- alter strategies
- re-run strategy optimization
- promote Range-HV
- enable live trading
- build AI strategy generation

First validate the recorder.

Then perform one controlled market session.

---

# FINAL RESPONSE

Return exactly:

```text
DATA-ARCHIVE-01 — ANGEL ONE MARKET RECORDER

Angel One Authentication:
PASS/FAIL/NOT_CONFIGURED

Instrument Master:
PASS/FAIL

Contracts Discovered:
X

Contracts Planned:
X

NIFTY Streaming:
PASS/FAIL

Options Streaming:
PASS/FAIL

OI Capture:
PASS/FAIL

Raw Archive:
PASS/FAIL

Normalized Archive:
PASS/FAIL

Timestamp/Timezone:
PASS/FAIL

Point-in-Time:
PASS/FAIL

Duplicate Handling:
PASS/FAIL

Conflict Handling:
PASS/FAIL

Disconnect Recovery:
PASS/FAIL

Resubscribe:
PASS/FAIL

Gap Preservation:
PASS/FAIL

Daily Manifest:
PASS/FAIL

Rate-Limit Safety:
PASS/FAIL

Order Endpoints Used:
YES/NO

Secrets Leaked:
YES/NO

Ground Truth Modified:
YES/NO

Paper Account Modified:
YES/NO

Tests:
PASS/FAIL

Production Isolation:
PASS/FAIL

Recorder Status:
READY_FOR_CONTROLLED_SESSION / NOT_READY

Today's Archive:
<path / NOT_RUN>

Archive Hash:
<hash / NOT_RUN>

Historical Research Value:
<description>

Biggest Remaining Gap:
<description>

Next Safe Phase:
CONTROLLED LIVE DATA SESSION / REVIEW / HOLD
```

## FINAL RULE

The purpose of this phase is to **remember the market while the contracts are alive**.

We are not trading.

We are not optimizing.

We are building the project's own historical evidence layer:

```text
LIVE MARKET
    ↓
ANGEL ONE
    ↓
RAW ARCHIVE
    ↓
NORMALIZED ARCHIVE
    ↓
PROVENANCE
    ↓
FUTURE BACKTEST
```

No fabricated data. No lookahead. No order placement. No strategy changes.
