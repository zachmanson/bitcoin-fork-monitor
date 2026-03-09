---
phase: 02-api-client-backfill
plan: "02"
subsystem: backfill-worker
tags: [backfill, threading, fastapi, checkpoint, resume, tdd]
one_liner: "Checkpointed backfill worker with 100-block resume safety and FastAPI lifespan thread management"

dependency_graph:
  requires:
    - 02-01  # api_client.fetch_blocks_page
    - 01-01  # models: Block, ForkEvent, SyncState
    - 01-02  # database: engine, create_db_and_tables
  provides:
    - app/backfill.py  # run_backfill(), _do_backfill(engine=None)
    - app/main.py      # FastAPI app with lifespan
  affects:
    - Phase 03 (live monitor will consume the same DB schema)

tech_stack:
  added:
    - fastapi.FastAPI (lifespan context manager)
    - threading.Thread (background backfill worker)
    - contextlib.asynccontextmanager (lifespan decorator)
  patterns:
    - "Dependency injection with default: _do_backfill(engine=None) accepts injected engine for tests"
    - "Thread-owned session: backfill thread creates its own Session(engine), never shares with request handlers"
    - "Checkpoint-resume: SyncState.last_synced_height written every 100 blocks, not every block"
    - "Exception guard in run_backfill(): catches all exceptions so server startup never fails due to backfill"

key_files:
  created:
    - app/backfill.py
    - app/main.py
    - tests/test_backfill.py
  modified:
    - tests/test_backfill.py  # fixed test_backfill_detects_fork mock setup

decisions:
  - "Pre-populate SyncState in test_backfill_detects_fork so the loop starts at tip height, not genesis (avoids needing 54k+ mocked page responses)"
  - "Backfill thread is daemon=True so uvicorn --reload shutdown does not block waiting for the thread"
  - "join(timeout=5.0) on shutdown gives the thread a grace window to commit its current checkpoint page"
  - "CHECKPOINT_INTERVAL=100 matches the plan spec; checkpoints fire when current_height % 100 == 0 after each 15-block page advance"

metrics:
  duration_minutes: 3
  completed_date: "2026-03-09"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 1
  tests_added: 5
  tests_total: 24
---

# Phase 02 Plan 02: Backfill Worker and FastAPI Entrypoint Summary

**One-liner:** Checkpointed backfill worker with 100-block resume safety and FastAPI lifespan thread management

## What Was Built

### Task 1: Backfill worker with checkpoint/resume logic and tests

`app/backfill.py` implements the historical backfill that walks blockchain history from the last checkpoint to the current chain tip, storing Block and ForkEvent rows in SQLite.

Key design decisions in the implementation:

- `run_backfill()` wraps `_do_backfill()` in a `try/except Exception` so a crash in the backfill never propagates to the FastAPI server.
- `_do_backfill(engine=None)` accepts an optional engine for dependency injection in tests. When `None`, it falls back to the module-level production engine. This avoids fragile module-global patching in tests.
- Checkpoints are written every `CHECKPOINT_INTERVAL=100` blocks by checking `if current_height % CHECKPOINT_INTERVAL == 0` after each 15-block page. This means checkpoints fire at heights that are multiples of 100 (100, 200, 300...) as the loop advances in 15-block strides.
- `_process_block()` uses `session.get(Block, hash) is None` guards before inserting, making the backfill idempotent on restart.
- The API returns blocks with key `"id"` for the canonical hash; orphan entries use `"hash"`. These are different keys — the code reflects this explicitly in comments.

`tests/test_backfill.py` covers five behaviors:
- `test_backfill_writes_blocks`: 30 canonical Block rows from 2 pages of 15
- `test_backfill_detects_fork`: ForkEvent + orphan Block row from a block with `extras.orphans`
- `test_backfill_skips_if_complete`: `fetch_blocks_page` never called when `backfill_complete=True`
- `test_backfill_resumes_from_checkpoint`: first content page uses `page_top = 114` (100 + 14) when checkpoint is at 100
- `test_checkpoint_frequency`: spy confirms checkpoints are far fewer than 250 (one per multiple of 100) plus final completion write

### Task 2: FastAPI entrypoint with lifespan thread management

`app/main.py` defines the FastAPI application with a lifespan context manager that:
1. Calls `create_db_and_tables()` on every startup (idempotent).
2. Reads `SyncState` to check `backfill_complete` — avoids re-launching a thread after the initial sync is done.
3. Starts a `daemon=True` background thread targeting `run_backfill()`.
4. On shutdown, joins the thread with a 5-second timeout.

The `/health` endpoint returns `{"status": "ok"}` to confirm the server started successfully.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_backfill_detects_fork mock setup**

- **Found during:** Task 1 RED → GREEN phase (test was failing immediately)
- **Issue:** `test_backfill_detects_fork` provided only 2 `side_effect` responses (`[single_page, single_page]`) but `_do_backfill()` starts from `last_synced_height=0` by default. With tip at height 820819, the loop would need ~54,721 page calls — exhausting the mock iterator on the second call with `StopIteration`.
- **Fix:** Pre-populate `SyncState(last_synced_height=820819)` before calling `_do_backfill()`. The loop then starts at 820819, fetches one content page (`page_top = 820833`), advances `current_height` to `820834 > 820819`, and exits cleanly. Total: 2 API calls (tip probe + 1 content page), matching the mock.
- **Files modified:** `tests/test_backfill.py`
- **Commit:** 0cce9eb

## Verification

Full test suite result:
```
24 passed, 13 warnings in 0.52s
```

Breakdown:
- `tests/test_analytics.py`: 7 tests
- `tests/test_api_client.py`: 8 tests
- `tests/test_backfill.py`: 5 tests
- `tests/test_database.py`: 2 tests
- `tests/test_models.py`: 2 tests

Smoke test:
```
python -c "from app.main import app; print(app.title)"
# Bitcoin Fork Monitor
```

## Self-Check: PASSED

All files verified:
- FOUND: app/backfill.py
- FOUND: app/main.py
- FOUND: tests/test_backfill.py
- FOUND commit: 0cce9eb (Task 1)
- FOUND commit: 7d800ce (Task 2)
