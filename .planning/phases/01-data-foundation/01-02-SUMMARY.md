---
phase: 01-data-foundation
plan: "02"
subsystem: analytics
tags: [python, pytest, tdd, pure-function]

requires: []

provides:
  - "calculate_stale_rate(canonical, orphaned) pure Python function"
  - "7-test suite pinning the stale rate formula denominator"

affects:
  - phase 2 ingestion (stale rate calculated on ingested block data)
  - phase 3 API (stale rate served from this function)
  - phase 4 UI (stale rate displayed to users)

tech-stack:
  added: [pytest, sqlmodel (installed as dependency for test infrastructure)]
  patterns:
    - "Pure function module (app/analytics.py) with no I/O imports — business logic isolated from database layer"
    - "TDD: failing test committed before implementation"
    - "Denominator-pinning test: explicit inequality assertion guards formula correctness"

key-files:
  created:
    - app/analytics.py
    - tests/test_analytics.py
  modified: []

key-decisions:
  - "Denominator is (canonical + orphaned) — total blocks seen, not just canonical. This means stale rate answers 'what fraction of all broadcast blocks were orphaned?' rather than 'what fraction of canonical blocks had competition?'"
  - "Return 0.0 on zero-zero input rather than raising — fresh database state is not an error"
  - "ValueError on negative counts — counts are physically meaningful, negatives indicate a caller bug"

patterns-established:
  - "Pure function module: app/analytics.py is the pattern for business logic — no db imports, independently testable"
  - "Denominator-pinning test: test_stale_rate_denominator_definition shows how to pin a formula by asserting both the correct result AND that an incorrect formula would differ"

requirements-completed: [DATA-03]

duration: 2min
completed: 2026-03-09
---

# Phase 1 Plan 02: Stale Rate Formula Summary

**calculate_stale_rate pure function with 7-test TDD suite that pins the denominator as (canonical + orphaned), making formula drift immediately detectable**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-09T16:49:26Z
- **Completed:** 2026-03-09T16:51:44Z
- **Tasks:** 1 (TDD task — 2 commits: RED + GREEN)
- **Files modified:** 2

## Accomplishments

- Wrote 7 failing tests covering normal case, formula-pinning, edge cases (zero-zero, all-orphaned, all-canonical), and negative input rejection
- Implemented `calculate_stale_rate` as a pure function with Google-style docstring explaining the formula rationale
- Confirmed the denominator-pinning test (`test_stale_rate_denominator_definition`) actually fails when the formula is broken — it is a real guard, not a tautology

## TDD Cycle

- **RED commit:** `892c200` — `test(01-02): add failing stale rate formula tests`
  - Tests failed with `ModuleNotFoundError: No module named 'app.analytics'` (expected)
- **GREEN commit:** `2e55e1e` — `feat(01-02): implement calculate_stale_rate formula`
  - All 7 tests pass, exit 0

## Task Commits

1. **RED — failing tests** - `892c200` (test)
2. **GREEN — implementation** - `2e55e1e` (feat)

## Files Created/Modified

- `app/analytics.py` - Pure function module: `calculate_stale_rate(canonical, orphaned) -> float`, formula docstring, ValueError guard, zero-total guard
- `tests/test_analytics.py` - 7 tests pinning the stale rate formula; includes denominator-definition test with explicit inequality assertion

## Decisions Made

- **Denominator is (canonical + orphaned):** The stale rate answers "what fraction of all broadcast blocks were orphaned?" A denominator of `canonical` alone would answer a different, less useful question.
- **0.0 on zero-zero input:** A fresh database with no blocks is not an error state. Raising would complicate callers unnecessarily.
- **ValueError on negative counts:** Block counts are physically meaningful. A negative value means a caller bug, not a domain edge case — failing loudly is correct.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed sqlmodel to unblock conftest import**
- **Found during:** Task 1 RED phase
- **Issue:** `tests/conftest.py` (created by parallel plan 01-01) imports `sqlmodel` which was not installed. This caused `conftest.py` to fail to load, blocking test collection.
- **Fix:** Ran `pip install sqlmodel`. The conftest fixture imports `app.models` lazily (inside the fixture body, not at module level), so no models stub was needed.
- **Files modified:** None (pip install only)
- **Verification:** Conftest loaded cleanly; test collection proceeded to expected `ModuleNotFoundError` on `app.analytics`
- **Committed in:** Not committed (pip install, no project file changed)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** The sqlmodel install was necessary because plan 01-01 (parallel wave-1 plan) created the conftest before plan 01-02 ran. No scope creep — the install is a project dependency already listed in `pyproject.toml`.

## Issues Encountered

None beyond the sqlmodel install described above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `calculate_stale_rate` is ready to be called by the ingestion layer (Phase 2) and the API layer (Phase 3)
- `app/analytics.py` has no imports from the database layer — it can be used before the database schema is finalized
- The denominator is locked by a CI test; any future change to the formula will surface immediately

---
*Phase: 01-data-foundation*
*Completed: 2026-03-09*

## Self-Check: PASSED

- FOUND: app/analytics.py
- FOUND: tests/test_analytics.py
- FOUND: 892c200 (RED commit)
- FOUND: 2e55e1e (GREEN commit)
- pytest tests/test_analytics.py: 7 passed, 0 failed
