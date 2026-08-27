---
name: release-check
description: Production-readiness audit and pre-release verification checklist.
---

# Release Check Skill

Use this skill before releasing code to production or tagging a milestone release.

## Pre-Release Verification Checklist

1. **Automated Test Pass (34/34)**: Run `python3 test_all.py` to confirm 100% test suite pass rate.
2. **Build & Syntax Verification**: Verify compilation (`python3 -m py_compile *.py`).
3. **Security Audit**: Ensure 0 hardcoded secrets, passwords, or PAT tokens in git tracking.
4. **Dependency Audit**: Verify all required packages are locked in `requirements.txt`.
5. **Database Migration & Journal Sanity**: Check SQLite WAL mode and DB integrity.
6. **Documentation Synchronization**: Verify `README.md`, `USER_GUIDE.md`, and `AGENTS.md` accurately reflect all features.
7. **Git Clean Status**: Confirm clean working tree (`git status`).
