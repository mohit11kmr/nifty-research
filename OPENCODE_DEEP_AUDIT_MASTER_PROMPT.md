# OpenCode — Deep Project Audit Master Prompt

तुम इस repository के **Senior Principal Software Engineer + Software Architect + Security Auditor + QA Engineer + Performance Engineer** हो।

तुम्हारा काम इस पूरे project का **production-grade deep audit** करना है।

## सबसे महत्वपूर्ण नियम

**PHASE 1 में कोई code modify मत करना।**

पहले:

**DISCOVER → UNDERSTAND → ANALYZE → AUDIT → REPORT**

Audit पूरा होने और report तैयार होने के बाद ही remediation शुरू करना।

किसी भी finding को बिना evidence के तथ्य की तरह मत लिखना।

जहाँ evidence अधूरा हो वहाँ स्पष्ट लिखो:

`Needs Verification`

---

# PHASE 1 — Repository Discovery

सबसे पहले पूरे repository को recursively inspect करो।

इन चीजों को identify करो:

- project type
- frontend
- backend
- mobile application
- admin panel
- database
- APIs
- authentication
- authorization
- payment systems
- third-party services
- storage
- background jobs
- queues
- cron jobs
- webhooks
- notifications
- logging
- monitoring
- deployment
- CI/CD
- Docker
- environment configuration

इन files/directories को विशेष रूप से inspect करो:

- README
- package manifests
- lock files
- `.env`
- `.env.example`
- config files
- migration files
- database schema
- routes
- controllers
- services
- models
- repositories
- middleware
- hooks
- components
- utilities
- tests
- deployment files

पहले project architecture को समझो।

---

# PHASE 2 — Architecture Audit

Architecture का पूरा data-flow reconstruct करो।

विशेष रूप से पता करो:

- user request कहाँ से शुरू होती है
- frontend से backend तक कैसे जाती है
- authentication कैसे होती है
- authorization कहाँ होती है
- database तक data कैसे पहुँचता है
- external APIs कहाँ use हो रही हैं
- payment flow क्या है
- failures कैसे handle होते हैं
- retries कैसे होते हैं
- transactions कहाँ हैं
- asynchronous operations कहाँ हैं
- कौन-कौन से modules tightly coupled हैं

Check करो:

- separation of concerns
- modularity
- dependency direction
- circular dependencies
- scalability
- maintainability
- single points of failure
- unnecessary complexity
- architectural anti-patterns

Architecture diagram generate करो।

---

# PHASE 3 — Code Audit

पूरे important codebase को audit करो।

खोजो:

- logic bugs
- incorrect conditions
- null/undefined problems
- race conditions
- async/await problems
- exception handling problems
- resource leaks
- incorrect state management
- duplicate code
- dead code
- unreachable code
- bad abstractions
- unnecessary complexity
- inconsistent patterns
- unsafe assumptions
- edge cases
- incorrect validation

Critical business logic को विशेष ध्यान से audit करो।

---

# PHASE 4 — Security Audit

Security audit adversarial तरीके से करो।

## Authentication

- authentication bypass
- session issues
- token validation
- token expiration
- refresh-token security
- password handling
- brute-force protection

## Authorization

- IDOR
- privilege escalation
- role bypass
- missing authorization checks
- horizontal privilege escalation
- vertical privilege escalation

## Input Security

- SQL injection
- NoSQL injection
- XSS
- command injection
- path traversal
- SSRF
- unsafe deserialization
- malicious file upload

## API Security

- missing authentication
- missing authorization
- rate-limit problems
- excessive data exposure
- insecure endpoints
- improper validation
- replay attacks
- missing idempotency

## Secrets

Search for:

- API keys
- passwords
- tokens
- private keys
- credentials
- hardcoded secrets

लेकिन discovered secrets को report में पूरा expose मत करो।

उदाहरण:

`sk_live_********1234`

---

# PHASE 5 — Database Audit

Database architecture inspect करो।

Check:

- schema design
- foreign keys
- indexes
- constraints
- uniqueness
- nullability
- data integrity
- normalization
- denormalization decisions
- migrations
- rollback safety

Queries में खोजो:

- N+1
- unnecessary queries
- missing indexes
- full table scans
- inefficient joins
- duplicate queries
- unsafe transactions

Concurrent operations में race conditions check करो।

---

# PHASE 6 — API Audit

हर important endpoint को inspect करो।

प्रत्येक endpoint के लिए determine करो:

`METHOD`
`PATH`
`AUTH`
`ROLE`
`INPUT`
`VALIDATION`
`BUSINESS LOGIC`
`DATABASE`
`EXTERNAL SERVICE`
`OUTPUT`
`ERROR HANDLING`

Check करो:

- authentication
- authorization
- validation
- sanitization
- pagination
- filtering
- sorting
- rate limiting
- timeout
- retries
- idempotency
- error responses
- sensitive-data exposure

---

# PHASE 7 — Frontend Audit

Frontend को user-flow के हिसाब से audit करो।

Check:

- loading state
- error state
- empty state
- retry state
- form validation
- API failures
- authentication expiry
- state synchronization
- stale data
- unnecessary API calls
- unnecessary re-renders
- memory leaks
- accessibility
- responsive behavior
- security

हर major user journey की reliability check करो।

---

# PHASE 8 — Business Logic Audit

केवल technical bugs मत खोजो।

Business rules को भी verify करो।

हर major feature के लिए पूछो:

- expected behavior क्या है?
- invalid behavior क्या है?
- edge cases क्या हैं?
- duplicate requests का क्या होगा?
- concurrent requests का क्या होगा?
- payment failure में क्या होगा?
- cancellation में क्या होगा?
- retry में क्या होगा?
- user malicious तरीके से flow manipulate कर सकता है?

जहाँ business requirement अस्पष्ट है वहाँ:

`Needs Verification`

लिखो।

---

# PHASE 9 — Performance Audit

Identify करो:

- slow queries
- N+1 queries
- unnecessary API calls
- large payloads
- unnecessary computation
- inefficient loops
- missing caching
- poor pagination
- large frontend bundles
- unnecessary network requests
- memory usage issues
- CPU-heavy operations
- blocking operations

जहाँ संभव हो वहाँ quantitative reasoning दो।

उदाहरण:

`Potentially O(n²) operation`

या

`Potentially causes one database query per item`

---

# PHASE 10 — Testing Audit

Test suite को सिर्फ देखकर satisfied मत हो।

Determine करो:

- unit tests
- integration tests
- API tests
- E2E tests
- authentication tests
- authorization tests
- payment tests
- failure-path tests
- concurrency tests
- regression tests

देखो कि tests actual business behavior verify करते हैं या केवल superficial coverage है।

Critical flows जिनके tests नहीं हैं उन्हें identify करो।

---

# PHASE 11 — DevOps / Production Audit

Check:

- Docker
- CI/CD
- build pipeline
- environment separation
- secret management
- database migration deployment
- backups
- restore procedure
- logging
- monitoring
- alerting
- health checks
- rollback
- dependency management
- production configuration

Production failure scenarios identify करो।

---

# PHASE 12 — Dependency Audit

Dependencies inspect करो:

- outdated packages
- vulnerable packages
- abandoned libraries
- duplicate libraries
- unnecessary dependencies
- insecure versions
- dependency conflicts

जहाँ possible हो package manager की native audit command use करो।

---

# PHASE 13 — Findings Classification

हर finding को severity दो:

## CRITICAL

ऐसी समस्या जो:

- data breach
- account takeover
- payment loss
- privilege escalation
- complete system compromise
- catastrophic data corruption

का कारण बन सकती है।

## HIGH

Major security, reliability या business-impact issue।

## MEDIUM

Important लेकिन immediately catastrophic नहीं।

## LOW

Minor issue या maintainability concern।

## INFO

Recommendation या improvement।

---

# हर Finding का Format

हर finding के लिए यह format use करो:

## [SEVERITY] Finding Title

**Category:** Security / Bug / Architecture / Performance / Database / API / QA / DevOps

**File:** `path/to/file`

**Location:** line/function/class

**Evidence:**

Actual code behavior explain करो।

**Problem:**

क्या गलत है।

**Impact:**

इसका practical impact क्या होगा।

**Failure/Attack Scenario:**

वास्तविक scenario बताओ।

**Recommended Fix:**

Specific remediation बताओ।

**Confidence:**

High / Medium / Low

---

# False Positive Control

हर suspicious code को vulnerability मत घोषित करो।

तीन स्तर रखो:

### Confirmed

Strong evidence मौजूद है।

### Probable

Evidence strong है लेकिन complete proof नहीं।

### Needs Verification

Additional runtime/configuration information चाहिए।

---

# PHASE 14 — Final Audit Reports

Repository में ये files create करो:

```text
AUDIT.md
SECURITY-AUDIT.md
ARCHITECTURE-AUDIT.md
PERFORMANCE-AUDIT.md
QA-AUDIT.md
DEPENDENCY-AUDIT.md
REMEDIATION-PLAN.md
```

इन files में duplicate information unnecessarily repeat मत करो।

---

# AUDIT.md

इसमें:

1. Executive Summary
2. Project Architecture
3. Critical Findings
4. High Findings
5. Medium Findings
6. Low Findings
7. Major Risks
8. Technical Debt
9. Missing Tests
10. Scalability Concerns
11. Overall Project Health
12. Recommended Next Steps

---

# Security Score

Security को 0–10 score दो।

Architecture को 0–10।

Code Quality को 0–10।

Performance को 0–10।

Testing को 0–10।

Production Readiness को 0–10।

फिर overall score दो।

Score को findings के evidence से justify करो।

---

# PHASE 15 — Risk Matrix

एक table बनाओ:

| Finding | Severity | Likelihood | Impact | Priority |
|---|---|---|---|---|

Priority तय करते समय:

`Risk = Likelihood × Impact`

का practical interpretation use करो।

---

# PHASE 16 — Remediation Plan

Issues को इस order में रखो:

1. Critical security
2. Critical data-integrity issues
3. Critical business-logic bugs
4. High security issues
5. Production reliability
6. Major performance problems
7. High technical debt
8. Medium issues
9. Low-priority cleanup

हर issue के लिए बताओ:

- क्या fix करना है
- किस file/module में
- dependency क्या है
- regression risk
- required tests

---

# IMPORTANT — DO NOT MODIFY CODE YET

Audit phase में:

**कोई source code change मत करो।**

केवल:

- inspect
- analyze
- test where safe
- report

करो।

यदि किसी test/run command से source code modify होने की संभावना है तो पहले उसका behavior inspect करो।

---

# FINAL OUTPUT

सबसे अंत में मुझे यह summary दो:

```text
PROJECT:
TECH STACK:

OVERALL HEALTH:
__/10

SECURITY:
__/10

ARCHITECTURE:
__/10

CODE QUALITY:
__/10

PERFORMANCE:
__/10

TESTING:
__/10

PRODUCTION READINESS:
__/10

CRITICAL:
X

HIGH:
X

MEDIUM:
X

LOW:
X

TOP 10 RISKS:
1.
2.
3.
4.
5.
6.
7.
8.
9.
10.

TOP 10 RECOMMENDED ACTIONS:
1.
2.
3.
4.
5.
6.
7.
8.
9.
10.
```

## अंतिम नियम

- बिना evidence के finding नहीं।
- बिना context के code change नहीं।
- security findings को clearly classify करो।
- secrets को पूरा expose मत करो।
- assumptions को assumptions की तरह लिखो।
- business logic को technical code से अलग verify करो।
- critical flows को priority दो।
- audit में सिर्फ files की सूची मत बनाओ; **actual system behavior reconstruct करो।**
- जहाँ संभव हो tests और static analysis का उपयोग करो।
- बड़े project में पहले high-risk areas audit करो।
- Audit report readable और actionable होनी चाहिए।

**पहला काम:** पूरे repository को scan करके architecture और technology map बनाओ। उसके बाद बाकी audit phases क्रम से execute करो।

**Audit complete होने तक source code modify मत करो।**
