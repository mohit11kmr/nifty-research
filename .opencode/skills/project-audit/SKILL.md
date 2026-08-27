---
name: project-audit
description: Deeply audit a codebase for architecture, bugs, security, performance, database, testing, and production readiness. Enforces 'Audit first, modify later'.
---

# Project Audit Skill

Use this skill when tasked with a comprehensive repository audit or code review.

## Mandatory Rule
**AUDIT FIRST, MODIFY LATER.**
Do NOT modify any source code files during the initial audit phase. Gather empirical findings, analyze architecture, dependencies, security, and test coverage before proposing or applying fixes.

## Audit Workflow

### 1. Environment & Tech Stack Discovery
- Detect language, framework, database, dependencies, package manager, and build system.
- Check compilation/syntax integrity: `python3 -m py_compile *.py` or build scripts.

### 2. Architecture & Code Quality
- Review component separation (UI, logic, data layers).
- Inspect module coupling, circular imports, and dead/unused code.
- Verify adherence to project coding standards and instructions.

### 3. Bugs & Runtime Vulnerabilities
- Scan for unhandled exceptions, `NoneType` dereferences, division by zero, unclosed database handles, or file descriptor leaks.
- Check network API call resilience, timeout handlers, and reconnect logic.

### 4. Security Audit
- Check for hardcoded API keys, secrets, tokens, or credentials.
- Audit input validation, SQL injection risks, XSS/CSRF vectors, and file upload paths.
- Verify authentication, authorization, and rate-limiting enforcement.

### 5. Database & Data Model Review
- Review schema indexes, query efficiency, transaction isolation, and locking behavior.
- Check migration hygiene and backup safeguards.

### 6. Test Suite & Coverage Analysis
- Run existing automated test suite (`python3 test_all.py` or equivalent).
- Report total tests, pass/fail status, and coverage gaps.

### 7. Performance & Resource Audit
- Detect N+1 query patterns, inefficient loops, excessive RAM allocations, or blocking calls on async loops.

### 8. Audit Report Generation
Produce a clear report structured as:
- Executive Summary & Health Score (0-100%)
- Critical Findings & Bugs
- Security Vulnerabilities
- Performance Bottlenecks
- Verification Evidence & Test Status
- Recommended Action Plan (prioritized)
