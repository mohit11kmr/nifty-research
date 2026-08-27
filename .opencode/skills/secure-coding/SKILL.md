---
name: secure-coding
description: Review and implement secure coding practices. Requires empirical evidence before declaring any security vulnerability fixed.
---

# Secure Coding Skill

Use this skill when auditing or implementing security fixes across the codebase.

## Mandatory Rule
**REQUIRE EVIDENCE BEFORE DECLARING A VULNERABILITY FIXED.**
Never claim a security vulnerability or secret exposure is resolved without concrete evidence (e.g. running grep scans, static analysis checks, or security unit tests).

## Security Audit & Remediation Checklist

### 1. Secret Hygiene & Credentials
- Scan entire repository for hardcoded API keys, JWT secrets, passwords, or tokens.
- Ensure all secrets are loaded dynamically from environment variables (`os.getenv`) or gitignored config files.

### 2. Injection & SQL Safety
- Ensure all database queries use parameterized placeholders (`?` or `%s`), never raw string formatting.
- Audit raw shell commands (`subprocess`, `os.system`) for unsanitized input injection.

### 3. Input Validation & Data Sanitization
- Validate all incoming API parameters, query strings, and payloads against strict type/range boundaries.
- Sanitize path inputs to prevent Directory/Path Traversal attacks (`../`).

### 4. Authentication & Authorization
- Verify session token expiration, cryptographic hash algorithm strength, and privilege check enforcement on every sensitive endpoint.
- Protect against Broken Object Level Authorization (BOLA).

### 5. Transport & Data Protection
- Ensure HTTPS/TLS for all external network endpoints.
- Avoid logging sensitive user data, auth tokens, or private payload details.

### 6. Verification Protocol
- Run security test cases or regression checks.
- Document exact diffs and empirical test proof.
