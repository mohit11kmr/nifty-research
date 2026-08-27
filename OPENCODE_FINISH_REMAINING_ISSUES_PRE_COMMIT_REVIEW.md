# OpenCode — Finish Remaining Audit Issues + Final Pre-Commit Review

The project has already completed a deep audit, remediation, and re-audit.

Previous verification:

- `test_all.py` → 34/34 OK
- `tests/test_fix_verification.py` → 18/18 OK
- MCP stdio handshake → 16 tools OK
- `pip-audit` → No known vulnerabilities
- `data/` sensitive files → clean
- `FIX-LOG.md` exists
- `FINAL-AUDIT-REPORT.md` exists

Your job now is:

**Finish remaining issues → run regression tests → perform final re-audit → make the repository commit-ready**

---

# STEP 1 — Inspect Current Repository State

Before making any changes, run:

```bash
git status
git diff --stat
git diff --cached --stat
```

Determine:

- staged changes
- unstaged changes
- deleted files
- modified files
- untracked files

Do not blindly restore, delete, or overwrite anything.

---

# STEP 2 — Review Remaining Issues

According to the previous audit, the following items remain:

```text
S-M3 token expiry
R4 backup script
PF-M2
PF-M3
R7 refactor
R8 refactor
R9 refactor
R15 hygiene
```

First read the existing audit reports and `FIX-LOG.md` to understand the exact meaning and current status of each item.

Classify every item as:

```text
OPEN
DEFERRED
ACCEPTED RISK
FIXED
FALSE POSITIVE
NEEDS VERIFICATION
```

Do not assume the previous classification is correct. Verify it against the actual code.

---

# STEP 3 — Reassess Priority

For every remaining issue, determine:

```text
Security impact
Data-loss impact
Financial/business impact
Production impact
User impact
Regression risk
Implementation complexity
```

Prioritize in this order:

1. Security
2. Data integrity / backup
3. Production reliability
4. Performance
5. Maintainability
6. Repository hygiene

---

# STEP 4 — S-M3 Token Expiry

Thoroughly inspect S-M3.

Determine:

- What token is involved?
- Where is the token generated?
- Where is it stored?
- Is expiration implemented?
- Where is token validation performed?
- Is there a refresh mechanism?
- What should happen when a token expires?

If token expiration is required:

- implement secure expiration
- validate expiry
- reject expired tokens
- add appropriate tests
- run regression tests

If expiration cannot safely be implemented yet, do not mark it as an accepted risk without evidence.

Document the exact reason and required future remediation.

---

# STEP 5 — R4 Backup Script

Inspect the backup implementation thoroughly.

Verify:

- the correct database/files are backed up
- backups are actually usable
- timestamps are handled correctly
- failures are detected
- exit codes are correct
- incomplete/corrupted backups can be detected
- retention strategy exists where required
- restoration is possible
- credentials/secrets are handled securely

Where safe and practical, perform a:

**backup + restore verification**

Do not consider a backup successful merely because the backup command exited successfully.

---

# STEP 6 — PF-M2 / PF-M3

Verify the performance findings using both source-code inspection and runtime evidence where available.

Check:

- database queries
- N+1 queries
- unnecessary file reads
- repeated calculations
- unnecessary API calls
- caching opportunities
- inefficient loops
- memory usage
- blocking operations

Establish a baseline before changing performance-sensitive code where practical.

Then apply the smallest safe optimization.

Do not sacrifice correctness or maintainability for a minor optimization.

Run the existing tests after every meaningful optimization.

---

# STEP 7 — R7 / R8 / R9 Refactors

For each refactor, determine:

- Is this an actual defect?
- Is this technical debt only?
- Does it improve security or reliability?
- Is it required for production readiness?
- What is the regression risk?
- Does it require a large architectural rewrite?

If the change is small, well-contained, and low risk:

**perform the refactor.**

If it requires a major rewrite or architectural redesign:

Do not rewrite the project unnecessarily.

Keep it deferred and document the reason.

---

# STEP 8 — R15 Repository Hygiene

Inspect the repository for:

- temporary files
- debug files
- generated artifacts
- duplicate files
- stale documentation
- unnecessary dependencies
- unnecessary files
- stale reports
- untracked data
- incorrect `.gitignore` rules

Keep the repository clean without removing anything required by the application.

---

# STEP 9 — Run Regression Tests

After each completed fix, run the relevant:

```text
unit tests
integration tests
security tests
fix verification tests
```

Then run the complete existing test suite:

```bash
python test_all.py
```

Also run the project's actual available commands for:

```text
lint
type checking
build
```

Do not invent commands that the project does not use.

---

# STEP 10 — Security Re-Audit

After security-related changes, perform a targeted security re-audit of the repository.

Pay special attention to:

- authentication
- authorization
- token handling
- secrets
- file access
- command execution
- dependency vulnerabilities
- input validation

Run:

```bash
pip-audit
```

Record the result.

---

# STEP 11 — Final Re-Audit

Perform a final targeted re-audit of the entire project.

Verify:

- all previous Critical findings
- all previous High findings
- remaining Medium findings
- repeated vulnerability patterns elsewhere
- regressions
- newly introduced issues

Do not close a finding merely because code was changed.

**Verify actual behavior.**

---

# STEP 12 — Update Audit Documentation

Update these files to reflect the final state:

```text
FIX-LOG.md
FINAL-AUDIT-REPORT.md
SECURITY-AUDIT.md
PERFORMANCE-AUDIT.md
REMEDIATION-PLAN.md
```

Every issue must have one final status:

```text
FIXED
PARTIALLY FIXED
DEFERRED
ACCEPTED RISK
FALSE POSITIVE
NEEDS VERIFICATION
```

Do not leave ambiguous statuses.

---

# STEP 13 — Final Quality Gate

Evaluate the project using this gate:

```text
Tests                PASS/FAIL
Fix verification     PASS/FAIL
Security audit       PASS/FAIL
Dependency audit     PASS/FAIL
Build                PASS/FAIL
Backup verification  PASS/FAIL/N/A
Regression audit     PASS/FAIL
```

If any critical gate fails:

**Do not declare the project commit-ready.**

---

# STEP 14 — Pre-Commit Senior Code Review

Before declaring the repository commit-ready, review all changes like a senior production engineer.

Run:

```bash
git status
git diff
git diff --cached
```

For every change, verify:

- Why was it changed?
- Which audit finding does it address?
- Is it actually required?
- Could it change existing behavior?
- Is there any debug code?
- Are there any secrets?
- Is there any unrelated change?
- Is test evidence available?
- Is documentation updated where necessary?

Identify suspicious or unrelated changes explicitly.

---

# IMPORTANT RULES

- Do not commit.
- Do not push.
- Do not rewrite the project unnecessarily.
- Do not hide failing tests.
- Do not claim success without evidence.
- Do not mark uncertain issues as fixed.
- Do not remove production data.
- Do not create destructive database migrations without necessity.
- Do not expose secrets.
- Do not make unrelated refactors.
- Preserve existing working behavior unless the audit finding requires a change.

The goal is:

**Make the existing project secure, stable, tested, maintainable, and production-ready — not rewrite it unnecessarily.**

---

# FINAL RESPONSE

Return the following summary:

```text
REMAINING ISSUES BEFORE:
X

FIXED NOW:
X

DEFERRED:
X

ACCEPTED RISK:
X

FALSE POSITIVE:
X

NEEDS VERIFICATION:
X

TESTS:
PASS/FAIL

FIX VERIFICATION:
PASS/FAIL

SECURITY:
PASS/FAIL

PIP-AUDIT:
PASS/FAIL

BUILD:
PASS/FAIL

BACKUP:
PASS/FAIL/N/A

FINAL PROJECT HEALTH:
__/10

PRODUCTION READINESS:
__/10

COMMIT READY:
YES/NO
```

If `COMMIT READY: NO`, list the exact blockers.

If `COMMIT READY: YES`, provide:

1. Modified files
2. Deleted files
3. Staged changes
4. Unstaged changes
5. Recommended commit message

**Do not commit or push anything.**
