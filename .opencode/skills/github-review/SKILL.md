---
name: github-review
description: Git/GitHub workflow management, issue and pull request reviews, commit preparation, and CI failure investigation.
---

# GitHub Review Skill

Use this skill when interacting with Git repositories, reviewing issues/PRs, analyzing CI failures, and staging clean commits.

## Mandatory Rule
**NEVER AUTOMATICALLY PUSH OR MERGE UNLESS EXPLICITLY REQUESTED.**
Always prepare git commits locally and present diffs to the user before pushing to remote repositories.

## Workflow & Features

1. **Git Repository Hygiene**:
   - Inspect status (`git status`) and diffs (`git diff`).
   - Ensure `AGENTS.md`, `README.md`, `USER_GUIDE.md`, `run_all.py`, and `test_all.py` are synchronized on every code change.
2. **Issue & Pull Request Inspection**:
   - Fetch PR branch context, issue comments, and requested changes via GitHub MCP (`github`).
3. **CI/CD Failure Investigation**:
   - Inspect GitHub Actions workflow logs to locate failing step traces.
4. **Commit Preparation**:
   - Write clear, conventional commit messages (`git commit -m "..."`).
