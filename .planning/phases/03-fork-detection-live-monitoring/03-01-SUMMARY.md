---
phase: 03-fork-detection-live-monitoring
plan: 01
subsystem: fork-detection
tags: [fork-detector, api-client, tdd, moni-02]
dependency_graph:
  requires: []
  provides: [detect_fork_at_height, write_fork_event, fetch_block_status]
  affects: [live-monitor, backfill]
tech_stack:
  added: []
  patterns: [pure-function, idempotent-insert, tdd-red-green]
key_files:
  created:
    - app/fork_detector.py
    - tests/test_fork_detector.py
  modified:
    - app/api_client.py
decisions:
  - "fetch_block_status follows the identical RETRY_DELAYS/backoff pattern as fetch_blocks_page — network I/O is uniform across the module"
  - "write_fork_event idempotency key is (height, canonical_hash, orphaned_hash) — simple three-column equality check, no composite DB constraint needed"
  - "resolution_seconds uses abs() — orphaned blocks can have slightly later header timestamps than the canonical block (miners have a small timestamp window)"
  - "fork_detector.py is pure — no imports of api_client — fetch_block_status is called by the monitor which decides canonical/orphaned before calling write_fork_event"
metrics:
  duration: 4m
  completed_date: "2026-03-09"
  tasks_completed: 2
  files_modified: 3
requirements_satisfied: [MONI-02]
---

# Phase 03 Plan 01: Fork Detection Foundation Summary

**One-liner:** Pure fork detection functions (detect_fork_at_height, write_fork_event) plus fetch_block_status with RETRY_DELAYS backoff, fully tested with 11 MONI-02 unit tests using in-memory SQLite.

## What Was Built

### app/fork_detector.py (new)

Two public pure functions:

- `detect_fork_at_height(session, height, new_hash) -> Optional[Block]`: queries the Block table for any row at the given height with a different hash. Returns the competing block or None. Read-only — no DB writes.

- `write_fork_event(session, height, canonical_hash, orphaned_hash, canonical_ts, orphaned_ts) -> ForkEvent`: idempotent insert of a ForkEvent row. On re-call with the same (height, canonical_hash, orphaned_hash), returns the existing row. Side effect: sets the orphaned block's `is_canonical = False`. Uses `abs()` for resolution_seconds so the value is always non-negative.

"Pure" means: no network calls, no threading, no global state. Session is passed in. These functions can be called safely from the monitor, backfill, or any future replay tool.

### app/api_client.py (extended)

Added `fetch_block_status(block_hash) -> dict`:

- Endpoint: `GET /api/block/{block_hash}/status`
- Returns raw JSON dict with `in_best_chain: bool` and optionally `next_best: str | None`
- Identical retry/backoff structure to `fetch_blocks_page` (RETRY_DELAYS, _RETRYABLE_STATUS_CODES, httpx.RequestError handling)
- Full professional docstring covering endpoint, args, returns, raises, and retry behavior
- No `time.sleep` outside the retry loop — inter-call throttling is the caller's responsibility

### tests/test_fork_detector.py (new)

11 tests across 5 classes covering all MONI-02 behaviors:

| Class | Tests | Coverage |
|---|---|---|
| TestDetectFork | 3 | empty height, same hash, different hash |
| TestWriteForkEvent | 3 | row fields, abs() resolution, orphan flag |
| TestForkIdempotency | 2 | same ID returned, no duplicate row |
| TestOrphanFlagged | 2 | orphan False, canonical unchanged |
| TestPendingResolution | 1 | ForkEvent with resolution_seconds=None |

## TDD Execution

**Task 1 (RED stub):** Created test file with class stubs (pass bodies), no import of app.fork_detector — parseable by pytest but not yet testing anything real. Added fetch_block_status to api_client.py.

**Task 2 RED:** Replaced stubs with real failing tests importing `from app.fork_detector import detect_fork_at_height, write_fork_event`. Confirmed ImportError — RED phase valid.

**Task 2 GREEN:** Created app/fork_detector.py. All 11 tests passed immediately. Full suite: 35 passed (24 baseline + 11 new).

## Commits

| Task | Commit | Description |
|---|---|---|
| Task 1 | 9cb207e | feat(03-01): add fetch_block_status to api_client and test stubs |
| Task 2 | 53412fe | feat(03-01): implement fork_detector.py with full test suite green |

## Deviations from Plan

None — plan executed exactly as written.

## Key Design Notes for Developer

**Why pass the session in?** This is dependency injection — a professional pattern where dependencies (the DB session) are provided by the caller rather than created inside the function. It makes testing trivial (pass in an in-memory session), and it gives the caller control over transaction boundaries.

**Why idempotency?** The live monitor will use WebSockets which can reconnect. If a block notification arrives twice, we don't want two ForkEvent rows. Checking before inserting is simpler than catching unique constraint violations and more portable across databases.

**Why abs()?** Bitcoin block timestamps are set by miners and can be off by up to 2 hours (per the protocol). An orphaned block might have a header timestamp slightly after the canonical block's timestamp. Without abs(), the duration would be negative — which is meaningless.

**Why no import of api_client in fork_detector?** Separation of concerns. The fork_detector functions are pure data logic. The monitor is the coordinator that calls the API, decides which block is canonical, then calls write_fork_event. Keeping these separate makes each layer independently testable.

## Self-Check: PASSED

- app/fork_detector.py: FOUND
- tests/test_fork_detector.py: FOUND
- .planning/phases/03-fork-detection-live-monitoring/03-01-SUMMARY.md: FOUND
- Commit 9cb207e: FOUND
- Commit 53412fe: FOUND
