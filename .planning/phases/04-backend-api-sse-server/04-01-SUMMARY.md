---
phase: 04-backend-api-sse-server
plan: 01
subsystem: backend-api
tags: [fastapi, rest-api, event-bus, sse, thread-safety, tdd]
dependency_graph:
  requires: []
  provides:
    - app/events.py (EventBus singleton)
    - app/routers/stats.py (GET /api/stats)
    - app/routers/forks.py (GET /api/forks)
    - app/routers/blocks.py (GET /api/blocks)
  affects:
    - app/main.py (event_bus.set_loop wired, 3 routers registered)
    - app/monitor.py (event_bus.notify wired in _process_block)
    - Plan 02 SSE endpoint (depends on EventBus and REST routers existing)
tech_stack:
  added:
    - fastapi>=0.135.0 (upgraded from 0.115.0)
    - httpx>=0.27.0 (dev dep, required by FastAPI TestClient in 0.135+)
  patterns:
    - Per-client asyncio.Queue for SSE fan-out
    - asyncio.run_coroutine_threadsafe for thread-to-async bridge
    - FastAPI dependency injection via Depends(get_session)
    - app.dependency_overrides for in-memory DB test isolation
key_files:
  created:
    - app/events.py
    - app/routers/__init__.py
    - app/routers/stats.py
    - app/routers/forks.py
    - app/routers/blocks.py
    - tests/test_events.py
    - tests/test_stats.py
    - tests/test_forks.py
    - tests/test_blocks.py
  modified:
    - app/main.py
    - app/monitor.py
    - pyproject.toml
decisions:
  - "EventBus uses per-client asyncio.Queue: each SSE connection gets its own queue so a slow browser tab cannot steal events meant for other tabs"
  - "asyncio.run_coroutine_threadsafe is the only correct cross-thread queue API: asyncio.Queue is not thread-safe, direct put_nowait() from monitor thread would corrupt event loop state"
  - "event_bus.set_loop() called before thread start in lifespan: the event loop must be captured before background threads begin or notify() would have a None loop reference"
  - "httpx added as dev dependency: FastAPI 0.135+ TestClient requires httpx for its async transport layer"
  - "func.count(Block.hash) preferred over func.count(): explicit column reference makes COUNT intent clearer in /api/stats query"
metrics:
  duration: "5 minutes"
  completed_date: "2026-03-09"
  tasks_completed: 2
  files_created: 9
  files_modified: 3
---

# Phase 4 Plan 01: Backend API + EventBus Summary

**One-liner:** REST endpoints (/api/stats, /api/forks, /api/blocks) and a thread-safe EventBus singleton using asyncio.run_coroutine_threadsafe and per-client queues as the monitor-to-SSE bridge.

## What Was Built

### EventBus (app/events.py)

A thread-to-async bridge that allows the monitor background thread to broadcast
block events to SSE client connections running in the asyncio event loop.

Key design: each SSE subscriber gets its own `asyncio.Queue(maxsize=100)`. When
the monitor calls `event_bus.notify(data)`, it schedules `q.put(data)` on every
subscriber's queue via `asyncio.run_coroutine_threadsafe`. This is the only
correct way to interact with an asyncio.Queue from an OS thread — the Queue
internals are not thread-safe.

### REST Endpoints

Three routers mounted at `/api`:

| Endpoint | Description |
|---|---|
| `GET /api/stats` | canonical/orphaned block counts, stale_rate, last_fork_at |
| `GET /api/forks` | paginated fork events, detected_at DESC, offset/limit |
| `GET /api/blocks` | recent blocks by height DESC, both canonical and orphaned |

All use `Depends(get_session)` for FastAPI dependency injection and are tested
with `app.dependency_overrides` swapping to an in-memory SQLite engine.

### Wiring

- `app/main.py lifespan`: calls `event_bus.set_loop(asyncio.get_event_loop())`
  before any threads start, then registers all three routers via `include_router`.
- `app/monitor.py _process_block()`: calls `event_bus.notify({...})` after the
  final `session.commit()` on SyncState, broadcasting each new block to SSE clients.

## Test Coverage

| File | Tests | Status |
|---|---|---|
| tests/test_events.py | 5 | Green |
| tests/test_stats.py | 2 | Green |
| tests/test_forks.py | 3 | Green |
| tests/test_blocks.py | 2 | Green |
| Full suite | 59 | Green (no regressions) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_notify_with_loop_enqueues: loop.run_until_complete() cannot be called while loop is running**
- **Found during:** Task 1 TDD RED/GREEN cycle
- **Issue:** The plan's suggested test pattern called `loop.run_until_complete()` to retrieve
  the queue result, but the loop was already running in a background thread via `loop.run_forever()`.
  Python raises `RuntimeError: This event loop is already running` in this case.
- **Fix:** Replaced `loop.run_until_complete(asyncio.wait_for(q.get(), ...))` with
  `asyncio.run_coroutine_threadsafe(asyncio.wait_for(q.get(), ...), loop).result(timeout=2.0)`.
  This schedules q.get() on the running loop from the test thread and blocks on the
  `concurrent.futures.Future` it returns — the correct cross-thread API.
- **Files modified:** tests/test_events.py
- **Commit:** 92bfceb (included in Task 1 commit)

## Commits

| Task | Commit | Description |
|---|---|---|
| Task 1 | 92bfceb | feat(04-01): upgrade FastAPI to 0.135+, add EventBus, write test scaffolds |
| Task 2 | b9479f4 | feat(04-01): implement REST routers and wire EventBus into main.py + monitor.py |

## Self-Check: PASSED

All files verified present on disk. Both task commits confirmed in git log.
Full test suite: 59 passed, 0 failed.
