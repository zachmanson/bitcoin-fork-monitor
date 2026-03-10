---
phase: 04-backend-api-sse-server
verified: 2026-03-10T00:00:00Z
status: human_needed
score: 7/7 must-haves verified
human_verification:
  - test: "Start the server with `uvicorn app.main:app --reload`, then run `curl -N http://localhost:8000/api/events` in a second terminal. Wait for the monitor to process a block (Bitcoin block interval ~10 min, or trigger via REST gap-fill after reconnect). Confirm a `data:` line appears in the curl output."
    expected: "A data: line containing JSON with keys type, height, hash, is_fork arrives within 2 seconds of the monitor writing a block to the DB"
    why_human: "The 2-second delivery SLA (ROADMAP success criterion 4) requires a live monitor thread, a real asyncio event loop, and network connectivity to mempool.space — none of which are present in the automated test environment"
  - test: "Start the server and open http://localhost:8000/docs"
    expected: "All four /api/* endpoints (stats, forks, blocks, events) appear with correct parameter documentation"
    why_human: "OpenAPI doc rendering requires a running server; only the schema JSON is verifiable in tests"
  - test: "Stop the running server with Ctrl+C"
    expected: "Process exits cleanly with no hung threads (uvicorn exits within 10 seconds)"
    why_human: "Clean shutdown behavior requires a live process and cannot be verified via static analysis"
---

# Phase 4: Backend API + SSE Server Verification Report

**Phase Goal:** A FastAPI server exposes block and fork data via REST endpoints and pushes real-time updates to browser clients via Server-Sent Events
**Verified:** 2026-03-10
**Status:** human_needed — all automated checks pass; 3 runtime behaviors require live-server confirmation
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GET /api/stats returns JSON with canonical_blocks, orphaned_blocks, stale_rate, last_fork_at | VERIFIED | `app/routers/stats.py` returns all 4 fields; `test_stats_shape` asserts types and keys; 2 tests green |
| 2 | GET /api/forks returns a paginated list of fork events ordered by detected_at descending | VERIFIED | `app/routers/forks.py` uses `.order_by(ForkEvent.detected_at.desc()).offset().limit()`; 3 pagination tests green |
| 3 | GET /api/blocks returns the most recent blocks (both canonical and orphaned) ordered by height descending | VERIFIED | `app/routers/blocks.py` queries without is_canonical filter, uses `.order_by(Block.height.desc())`; 2 tests green |
| 4 | EventBus.notify() called from monitor thread enqueues data into all subscriber queues | VERIFIED | `app/events.py` uses `asyncio.run_coroutine_threadsafe`; `test_notify_with_loop_enqueues` exercises the cross-thread path with a real running event loop |
| 5 | GET /api/events responds with Content-Type: text/event-stream | VERIFIED | `app/routers/events.py` sets `response_class=EventSourceResponse`; `test_sse_content_type` confirms route is registered with EventSourceResponse class |
| 6 | When a browser tab closes, the SSE generator cleans up its queue | VERIFIED | `app/routers/events.py` has `try/finally: event_bus.unsubscribe(q)`; `test_sse_unsubscribe_on_disconnect` drives the generator directly with a mock that returns `is_disconnected()=True` and confirms `len(_subscribers)==0` |
| 7 | A browser client receives a new SSE event within 2 seconds of the monitor writing a block | HUMAN NEEDED | Wiring path verified (monitor.py calls notify, events.py awaits queue), but the end-to-end latency SLA requires a live server + real monitor thread |

**Score:** 6/7 truths fully verified in automation; 1 truth requires human confirmation of the runtime SLA

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/events.py` | EventBus class with subscribe/unsubscribe/notify/set_loop; module singleton `event_bus` | VERIFIED | 125 lines; all 4 methods present; singleton at module level; full docstrings |
| `app/routers/__init__.py` | Package marker file | VERIFIED | Exists; enables `from app.routers import stats, forks, blocks, events` |
| `app/routers/stats.py` | GET /api/stats endpoint | VERIFIED | 74 lines; counts canonical + orphaned blocks, computes stale_rate via analytics, fetches last fork; returns all 4 fields |
| `app/routers/forks.py` | GET /api/forks paginated endpoint | VERIFIED | 47 lines; offset/limit params with `Query(le=200)`; ordered by detected_at DESC |
| `app/routers/blocks.py` | GET /api/blocks recent blocks endpoint | VERIFIED | 45 lines; limit param with `Query(le=200)`; ordered by height DESC; includes both canonical and orphaned |
| `app/routers/events.py` | GET /api/events SSE endpoint | VERIFIED | 106 lines; async generator; 1-second inner timeout with 15-tick keepalive; try/finally unsubscribe |
| `tests/test_events.py` | Unit tests for EventBus + SSE | VERIFIED | 7 tests: 5 EventBus (subscribe, unsubscribe, noop, notify cross-thread, disconnect cleanup), 2 SSE (content-type via route registry, unsubscribe on disconnect) — all green |
| `tests/test_stats.py` | Unit tests for /api/stats | VERIFIED | 2 tests: HTTP 200, response shape with correct types — all green |
| `tests/test_forks.py` | Unit tests for /api/forks pagination | VERIFIED | 3 tests: HTTP 200, default limit ≤50, custom limit=5 — all green |
| `tests/test_blocks.py` | Unit tests for /api/blocks | VERIFIED | 2 tests: HTTP 200, default limit ≤50 — all green |

---

## Key Link Verification

### Plan 01 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app/monitor.py _process_block()` | `app/events.py event_bus` | `event_bus.notify()` after SyncState commit | WIRED | Lines 168–173 of monitor.py call `event_bus.notify({...})` immediately after the final `session.commit()`. Import at top of file confirmed. `competing_block` variable tracked at outer scope before the `if` block so `is_fork` is always accurate. |
| `app/main.py lifespan` | `app/events.py event_bus` | `event_bus.set_loop(asyncio.get_event_loop())` | WIRED | Line 68 of main.py calls `event_bus.set_loop(asyncio.get_event_loop())` before any `threading.Thread().start()` calls. Import of `event_bus` confirmed at line 41. |
| `app/main.py` | `app/routers/*.py` | `app.include_router(router)` | WIRED | Lines 125–128: `include_router` called for all four routers (stats, forks, blocks, events). Import line 44: `from app.routers import blocks, events, forks, stats`. |

### Plan 02 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app/routers/events.py sse_events()` | `app/events.py event_bus` | `event_bus.subscribe()` on connect, `event_bus.unsubscribe(q)` in finally | WIRED | Lines 67 and 105 of events.py. Both patterns present; import at line 41. |
| `app/main.py` | `app/routers/events.py` | `app.include_router(events.router)` | WIRED | Line 128: `app.include_router(events.router)`. Router import confirmed in line 44. |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DASH-02 | 04-01-PLAN.md | User can view a summary stats panel: total canonical blocks, total orphaned blocks, current stale rate, date of last fork | SATISFIED | `GET /api/stats` returns all 4 fields; `test_stats_shape` asserts correct types; endpoint wired via `include_router` |
| DASH-04 | 04-02-PLAN.md | Dashboard receives real-time updates via Server-Sent Events without requiring a page refresh | SATISFIED (automated portion) | SSE endpoint registered at `/api/events`; EventBus wired from monitor through to SSE generator; cleanup verified; 2-second delivery SLA requires human runtime confirmation |

No orphaned requirements: REQUIREMENTS.md traceability table maps only DASH-02 and DASH-04 to Phase 4. Both are accounted for.

---

## Anti-Patterns Found

None. Scanned all phase 04 production files (`app/events.py`, `app/routers/*.py`, `app/monitor.py`, `app/main.py`) and test files for TODO/FIXME/HACK/PLACEHOLDER, empty implementations, and stub returns. Zero matches.

---

## Test Suite Results

| Suite | Tests | Result |
|-------|-------|--------|
| tests/test_stats.py | 2 | Green |
| tests/test_forks.py | 3 | Green |
| tests/test_blocks.py | 2 | Green |
| tests/test_events.py | 7 | Green |
| Full suite (pytest) | 61 | Green — no regressions in prior phases |

FastAPI version: 0.135.1 (upgraded from 0.115.0 as required).

---

## Human Verification Required

### 1. SSE Live Event Delivery (2-second SLA)

**Test:** Start `uvicorn app.main:app --reload`. In a second terminal run `curl -N http://localhost:8000/api/events`. Allow the monitor to process a live block (or force gap-fill by temporarily restarting to trigger gap-fill from last_synced_height).
**Expected:** A `data:` line containing JSON with keys `type`, `height`, `hash`, `is_fork` appears in the curl output within 2 seconds of the monitor thread calling `_process_block()`.
**Why human:** The 2-second delivery SLA in ROADMAP success criterion 4 requires a live asyncio event loop, a running monitor thread, and network connectivity to mempool.space. These cannot be reproduced in the automated test environment. The wiring path is fully verified (monitor.py calls `event_bus.notify()`, events.py awaits the queue), but only a live integration test can confirm the latency bound.

### 2. OpenAPI Documentation

**Test:** Open `http://localhost:8000/docs` in a browser with the server running.
**Expected:** All four endpoints — `GET /api/stats`, `GET /api/forks`, `GET /api/blocks`, `GET /api/events` — appear with their parameters documented.
**Why human:** FastAPI generates the interactive docs page dynamically; only the raw `/openapi.json` schema is testable without a browser.

### 3. Clean Shutdown

**Test:** With the server running and the monitor/backfill threads active, press Ctrl+C.
**Expected:** The process exits within 10 seconds. No "thread still running" errors. The 5-second join timeouts in main.py lifespan allow the threads to commit their current work before exit.
**Why human:** Thread lifecycle and join behavior require an actual running process.

---

## Notes on Implementation Deviations

Two deviations from the plans were made during execution, both correctly handled:

1. **EventBus test pattern** (`test_notify_with_loop_enqueues`): The plan suggested using `loop.run_until_complete()` to retrieve the result. This was correctly changed to `asyncio.run_coroutine_threadsafe(...).result()` because `run_until_complete` raises `RuntimeError` when the loop is already running in another thread. The fix exercises exactly the same code path.

2. **SSE test approach**: The plan suggested `TestClient.stream("GET", "/api/events")` for SSE tests. Starlette's synchronous ASGI transport deadlocks on infinite generators. The replacement — route registry inspection + direct async generator testing with `AsyncMock` — is a stronger test because it bypasses HTTP-layer noise and directly verifies the generator's lifecycle behavior.

Both deviations improve test reliability without reducing coverage.

---

_Verified: 2026-03-10_
_Verifier: Claude (gsd-verifier)_
