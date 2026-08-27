---
name: bug-fix
description: Systematic workflow to understand, reproduce, fix, test, and verify confirmed bugs without introducing unrelated refactoring.
---

# Bug Fix Skill

Use this skill when investigating and resolving a confirmed bug or runtime defect.

## Bug Fixing Workflow

```text
Understand Problem -> Reproduce Defect -> Identify Root Cause -> Minimal Targeted Fix -> Targeted Unit Test -> Full Regression Test -> Verify
```

### Step 1: Understand
Read the error log, stack trace, or user report thoroughly. Never guess the cause without log evidence.

### Step 2: Reproduce
Write a minimal reproducing test case or command that consistently triggers the bug.

### Step 3: Identify Root Cause
Trace the exact line and state mutation breaking the contract.

### Step 4: Implement Minimal Targeted Fix
Apply the smallest, safest code edit to fix the root cause.
**DO NOT perform unrelated code refactoring, styling changes, or unnecessary architectural shifts.**

### Step 5: Test & Verify
Run the reproducing test to confirm the fix works.

### Step 6: Regression Test
Run the full test suite (`python3 test_all.py`) to confirm no existing functionality broke.
