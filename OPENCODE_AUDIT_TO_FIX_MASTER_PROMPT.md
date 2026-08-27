# OpenCode — Audit-to-Fix Remediation Master Prompt

Audit phase पूरा हो चुका है और repository में audit reports उपलब्ध हैं।

अब तुम **Senior Principal Developer + Security Engineer + QA Engineer** के रूप में remediation शुरू करो।

---

# 1. पहले Audit पढ़ो

सबसे पहले इन files को पढ़ो:

```text
AUDIT.md
SECURITY-AUDIT.md
ARCHITECTURE-AUDIT.md
PERFORMANCE-AUDIT.md
QA-AUDIT.md
DEPENDENCY-AUDIT.md
REMEDIATION-PLAN.md
```

इन reports के findings को दोबारा source code से verify करो।

Audit report में दिया गया finding गलत हो तो blindly fix मत करो।

---

# 2. Fix Priority

Problems इस क्रम में fix करो:

```text
CRITICAL
↓
HIGH
↓
MEDIUM
↓
LOW
```

लेकिन dependency वाले issues में dependency order follow करो।

Security और data-integrity issues को सामान्य code-quality issues से ऊपर priority दो।

---

# 3. एक बार में एक Logical Fix

एक साथ पूरे project को rewrite मत करो।

हर finding के लिए:

```text
READ
↓
UNDERSTAND
↓
IDENTIFY ROOT CAUSE
↓
PATCH
↓
TEST
↓
VERIFY
↓
RE-AUDIT
```

---

# 4. Root Cause Fix करो

सिर्फ symptom मत हटाओ।

उदाहरण:

अगर authorization bypass मिला है तो केवल एक endpoint पर check जोड़कर मत रुकना।

पूरे authorization pattern को inspect करो और देखो कि वही vulnerability दूसरे endpoints में भी तो नहीं है।

एक problem का fix लगाने के बाद:

**Search entire repository for the same vulnerability pattern.**

---

# 5. Code Changes

Code modification से पहले:

- affected files identify करो
- dependencies identify करो
- existing behavior समझो
- related tests देखो

फिर minimal safe change करो।

Unrelated refactoring मत करो।

Existing working functionality को बिना कारण rewrite मत करो।

---

# 6. प्रत्येक Fix के बाद Tests

हर fix के बाद applicable tests चलाओ:

```text
unit tests
integration tests
API tests
E2E tests
security tests
lint
type checking
build
```

Project में जो commands उपलब्ध हैं उन्हें पहले identify करो।

Fail होने पर error को diagnose करके fix करो।

---

# 7. Regression Testing

हर critical fix के बाद verify करो:

- existing feature अभी काम कर रहा है
- API response नहीं टूटा
- database behavior नहीं टूटा
- authentication नहीं टूटी
- authorization नहीं टूटी
- frontend flow नहीं टूटा
- payment/business flow नहीं टूटा

---

# 8. Security Fix Verification

Security finding fix करने के बाद सिर्फ code देखकर satisfied मत हो।

जहाँ संभव हो attack scenario reproduce करो।

उदाहरण:

```text
unauthorized request
invalid token
expired token
different user's resource access
role escalation
malicious input
duplicate request
replay request
```

फिर verify करो कि attack अब fail हो रहा है।

---

# 9. Database Changes

Database/schema change हो तो:

- migration बनाओ
- existing data compatibility check करो
- rollback safety देखो
- indexes verify करो
- constraints verify करो
- production migration risk note करो

Production database को बिना explicit requirement के destructive तरीके से modify मत करो।

---

# 10. Dependency Updates

Dependency vulnerability के मामले में:

पहले यह verify करो:

```text
current version
vulnerable version
fixed version
breaking changes
compatibility
```

फिर appropriate version पर upgrade करो।

Upgrade के बाद:

```text
install
lint
test
build
```

चलाओ।

---

# 11. Fix Log

एक नई file maintain करो:

```text
FIX-LOG.md
```

हर fix के लिए:

```text
Finding:
Severity:
Status:
Files Changed:
Root Cause:
Fix:
Tests:
Verification:
Regression Risk:
```

Status:

```text
FIXED
PARTIALLY FIXED
NOT FIXED
NEEDS VERIFICATION
```

---

# 12. Re-Audit

सभी Critical और High findings fix करने के बाद पूरे project का targeted re-audit करो।

विशेष रूप से:

```text
security
authorization
authentication
business logic
database integrity
API
performance
```

फिर verify करो कि:

- original issue खत्म हुआ
- same issue दूसरी जगह नहीं है
- नया vulnerability नहीं आया
- regression नहीं आया

---

# 13. Medium और Low Issues

Critical और High issues successfully verify होने के बाद:

Medium issues fix करो।

फिर Low issues।

Low-priority cleanup के लिए risky architectural rewrite मत करो।

---

# 14. Final Verification

सभी fixes के बाद पूरा project verify करो:

```text
INSTALL
↓
LINT
↓
TYPE CHECK
↓
UNIT TEST
↓
INTEGRATION TEST
↓
E2E TEST
↓
BUILD
↓
SECURITY CHECK
↓
FINAL RE-AUDIT
```

जहाँ कोई command project में उपलब्ध नहीं है वहाँ उसे invent मत करो।

---

# 15. Final Report

एक नई file बनाओ:

```text
FINAL-AUDIT-REPORT.md
```

इसमें दिखाओ:

## Fixed

सभी successfully fixed findings।

## Partially Fixed

जो पूरी तरह fix नहीं हुए।

## Not Fixed

जो अभी बाकी हैं।

## Needs Verification

जिनके लिए runtime/production information चाहिए।

## Remaining Risks

जो risks अभी बचे हैं।

## Files Changed

सभी modified files।

## Tests Passed

चलाए गए सभी tests और उनका result।

## Build Status

PASS / FAIL

## Security Status

PASS / FAIL / PARTIAL

## Production Readiness

0–10 score।

---

# IMPORTANT SAFETY RULES

1. बिना evidence के functionality change मत करो।
2. unrelated files modify मत करो।
3. secrets commit मत करो।
4. production credentials expose मत करो।
5. database data delete मत करो।
6. destructive migration बिना आवश्यकता के मत बनाओ।
7. tests bypass करके fix को successful मत बताओ।
8. failing tests छुपाओ मत।
9. build fail हो तो `PASS` मत लिखो।
10. uncertain fix को `NEEDS VERIFICATION` लिखो।

---

# FINAL RESPONSE

अंत में केवल यह summary दो:

```text
AUDIT FINDINGS:
Critical: X
High: X
Medium: X
Low: X

FIXED:
X

PARTIALLY FIXED:
X

NOT FIXED:
X

NEEDS VERIFICATION:
X

TESTS:
PASS / FAIL

BUILD:
PASS / FAIL

SECURITY:
PASS / FAIL / PARTIAL

FINAL PROJECT HEALTH:
__/10

PRODUCTION READINESS:
__/10
```

इसके बाद remaining risks और सबसे जरूरी next actions बताओ।

---

# IMPORTANT EXECUTION RULE

अगर कोई Critical या High finding fix करते समय दूसरे related issues मिलते हैं, तो उन्हें भी trace करो और जरूरत के अनुसार audit report तथा FIX-LOG.md update करो।

लेकिन unrelated refactoring शुरू मत करो।

**Goal: existing project को सुरक्षित, stable, tested और production-ready बनाना है — project को बिना जरूरत rewrite करना नहीं।**
