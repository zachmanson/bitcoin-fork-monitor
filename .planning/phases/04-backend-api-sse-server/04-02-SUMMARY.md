---
phase: 04-backend-api-sse-server
plan: 02
subsystem: api
tags: [fastapi, sse, server-sent-events, asyncio, event-bus]

# Dependency graph
requires:
  - phase: 04-01
    provides: EventBus singleton (subscribe/unsubscribe/notify), FastAPI 0.135 with SSE support
provides:
  - GET /api/events SSE endpoint streaming real-time block notifications to browser clients
  - Per-client asyncio.Queue subscriber pattern with try/finally cleanup
  - 1-second poll loop for responsive disconnect detection (15-cycle keepalive)
affects:
  - 05-frontend-dashboard (consumes /api/events via browser EventSource API)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - SSE endpoint as async generator with response_class=EventSourceResponse
    - 1-second inner timeout loop for responsive disconnect detection
    - try/finally for guaranteed unsubscribe on generator exit
    - Direct async generator testing with mocked Request (bypasses TestClient limitation)

key-files:
  created:
    - app/routers/events.py
  modified:
    - app/main.py
    - tests/test_events.py

key-decisions:
  - "1-second inner timeout instead of 15-second: Starlette is_disconnected() cannot interrupt an awaiting wait_for() — short timeout keeps the disconnect check responsive while still supporting keepalives via a counter"
  - "SSE tests use OpenAPI schema + direct async generator inspection instead of TestClient.stream(): Starlette's synchronous ASGI transport blocks until the handler returns; infinite SSE generators never return, making stream() deadlock"
  - "Keepalive sent every 15 idle ticks (15 seconds) via counter: preserves the 15-second keepalive SLA while allowing 1-second disconnect poll"

patterns-established:
  - "SSE generators: use asyncio.wait_for(q.get(), timeout=1.0) with idle counter for keepalives instead of a single 15s timeout — enables responsive disconnect detection"
  - "Testing infinite SSE generators: run the async generator directly with AsyncMock Request instead of TestClient — avoids synchronous ASGI transport deadlock"

requirements-completed: [DASH-04]

# Metrics
duration: 25min
completed: 2026-03-10
---

# Phase 4 Plan 02: SSE Endpoint Summary

**GET /api/events implemented as an async generator SSE endpoint with per-client asyncio.Queue and responsive disconnect cleanup, completing the Phase 4 real-time delivery pipeline**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-03-10T03:50:00Z
- **Completed:** 2026-03-10T04:15:00Z
- **Tasks:** 2/2 (all complete, including human verification)
- **Files modified:** 3

## Accomplishments
- Created `app/routers/events.py` with `GET /api/events` SSE endpoint consuming the EventBus from Plan 01
- Wired the events router into `app/main.py` (4th `include_router` call)
- Added two SSE-specific tests to `tests/test_events.py` — all 7 tests pass, full suite 61 passed

## Task Commits

Each task was committed atomically:

1. **Task 1 (TDD RED): Add failing SSE tests** - `6e57616` (test)
2. **Task 1 (TDD GREEN): SSE endpoint + main.py update** - `90eddc2` (feat)
3. **Task 2: Human verification checkpoint** - Approved 2026-03-10 (live server checks passed)

_TDD task split: RED commit first with failing tests, GREEN commit with passing implementation._

## Files Created/Modified
- `app/routers/events.py` — GET /api/events: EventSourceResponse async generator with per-client queue, 1s poll loop, 15-cycle keepalive, try/finally cleanup
- `app/main.py` — Added `from app.routers import events` and `app.include_router(events.router)`
- `tests/test_events.py` — Added `test_sse_content_type` and `test_sse_unsubscribe_on_disconnect`

## Decisions Made

**1s inner timeout instead of 15s:**
The plan specified `asyncio.wait_for(q.get(), timeout=15.0)`. During implementation, we discovered that Starlette's `is_disconnected()` uses `anyio.CancelScope(cancel=True)` which is non-blocking — it checks immediately whether a disconnect message is queued. But with a 15s timeout on `q.get()`, the disconnect check only runs every 15 seconds. Switching to 1s with an idle counter achieves both: responsive disconnect detection AND the 15-second keepalive SLA.

**Direct generator testing instead of TestClient.stream():**
The plan suggested `TestClient.stream("GET", "/api/events")` for the SSE tests. Starlette's TestClient runs ASGI calls synchronously via `anyio.from_thread.BlockingPortal.call()`, which blocks until the ASGI handler returns. An infinite SSE generator never returns, so `client.stream()` deadlocks the test thread. We replaced this with:
- `test_sse_content_type`: Verifies endpoint registration via OpenAPI schema + checks `route.response_class is EventSourceResponse` (the library guarantee for text/event-stream header)
- `test_sse_unsubscribe_on_disconnect`: Runs the generator directly via `asyncio.run()` with a mocked `Request` that returns `is_disconnected() = True` immediately

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Changed 15s wait_for timeout to 1s with keepalive counter**
- **Found during:** Task 1 (implementation + test design)
- **Issue:** `asyncio.wait_for(q.get(), timeout=15.0)` makes disconnect detection take up to 15 seconds after the client closes. The `is_disconnected()` check only runs once every 15 seconds.
- **Fix:** Changed timeout to 1.0s; added `idle_ticks` counter that triggers keepalive at tick 15. Production behavior is identical (keepalive every 15s), disconnect response is 15x faster.
- **Files modified:** `app/routers/events.py`
- **Committed in:** `90eddc2` (Task 1 GREEN commit)

**2. [Rule 1 - Bug] Replaced TestClient.stream() tests with direct generator tests**
- **Found during:** Task 1 (test verification)
- **Issue:** `TestClient.stream("GET", "/api/events")` deadlocks because Starlette's synchronous ASGI transport cannot return until the generator exits. The generator loops indefinitely.
- **Fix:** `test_sse_content_type` checks OpenAPI schema + route registry. `test_sse_unsubscribe_on_disconnect` runs the generator directly with `asyncio.run()` and `AsyncMock(Request)`.
- **Files modified:** `tests/test_events.py`
- **Committed in:** `6e57616` (RED), `90eddc2` (GREEN)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — bugs in the plan's suggested implementation)
**Impact on plan:** Production SSE behavior unchanged (keepalive still every 15s). Tests are more reliable by bypassing the TestClient limitation.

## Issues Encountered
- Starlette's `_TestClientTransport.handle_request()` uses `portal.call()` which blocks synchronously until the ASGI handler completes. This fundamental design means TestClient cannot test infinite SSE streams. Documented and worked around with direct generator testing.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- Phase 4 backend is complete: FastAPI 0.135, EventBus, three REST endpoints (/api/stats, /api/forks, /api/blocks), SSE endpoint (/api/events), full test suite (61 tests green)
- Human verification passed: live server confirmed returning correct JSON from REST endpoints, SSE connection stays open and receives data: lines, OpenAPI docs show all four /api/* endpoints, clean shutdown on Ctrl+C
- Phase 5 (frontend dashboard) can now consume /api/events via browser EventSource API

## Self-Check: PASSED

- FOUND: app/routers/events.py
- FOUND: .planning/phases/04-backend-api-sse-server/04-02-SUMMARY.md
- FOUND commit: 6e57616 (test RED)
- FOUND commit: 90eddc2 (feat GREEN)

---
*Phase: 04-backend-api-sse-server*
*Completed: 2026-03-10*
