---
name: test-and-verify
description: Comprehensive verification workflow ensuring all code modifications are empirically validated through targeted and regression tests.
---

# Test and Verify Skill

Use this skill to validate code changes before concluding any task.

## Mandatory Rule
**NEVER CLAIM PASS WITHOUT EVIDENCE.**
Always execute the build, compilation, or automated test command and output the empirical results.

## Verification Protocol

1. **Pre-Change Baseline**: Run existing tests or check build status to confirm the starting baseline.
2. **Apply Modification**: Make the minimal required code edit.
3. **Targeted Test Run**: Execute the specific unit test or script directly validating the changed component.
4. **Full Regression Test Run**: Run the entire project test suite (`python3 test_all.py`).
5. **Static & Build Audit**: Verify compilation (`python3 -m py_compile *.py`) and type/lint sanity.
6. **Report Evidence**: Provide exact execution output (e.g., `Ran 34 tests in 5.2s — OK`) as proof.
