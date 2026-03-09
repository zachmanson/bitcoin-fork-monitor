---
phase: 03-fork-detection-live-monitoring
plan: 02
subsystem: live-monitor
tags: [monitor, websocket, rest-fallback, gap-fill, tdd, moni-01, moni-03, threading]
dependency_graph:
  requires: [detect_fork_at_height, write_fork_event, fetch_block_status, fetch_blocks_page, SyncState]
  provides: [run_monitor, _process_block, _rest_gap_fill, _wait_for_backfill]
  affects: [main-lifespan, fork-events-api]
tech_stack:
  added: [websockets==14.1 (sync client)]
  patterns: [state-machine, tdd-red-green, dependency-injection, background-thread, pending-resolution-retry]
key_files:
  created:
    - app/monitor.py
    - tests/test_monitor.py
  modified:
    - app/main.py
decisions:
  - "time.time() is patched in REST fallback tests so the WS reconnect interval check does not trigger unexpectedly during unit tests"
  - "pending_resolutions uses a mutable list passed by reference — same list is shared across _ws_loop and _process_block calls within one monitor session"
  - "monitor_thread initialized to None before startup conditional so shutdown block always has a valid reference"
  - "websockets.sync.client used instead of async websockets — monitor runs in a background thread without access to FastAPI's asyncio event loop"
metrics:
  duration: 8m
  completed_date: "2026-03-09"
  tasks_completed: 3
  files_modified: 3
requirements_satisfied: [MONI-01, MONI-03]
---

# Phase 03 Plan 02: Live Monitor Summary

**One-liner:** Resilient live monitoring thread with WebSocket subscription, 3-failure REST fallback, 5-minute reconnect, gap-fill on reconnect, and per-block SyncState updates — fully tested with 12 unit tests using mocked network I/O.

## What Was Built

### app/monitor.py (new)

Five public/private functions implementing the monitoring state machine:

**`_wait_for_backfill() -> None`**
Opens and closes a fresh `Session(engine)` every 5 seconds, polling `SyncState.backfill_complete`. Returns immediately when True. Logs INFO on first call and on return. This is the startup gate: the monitor will not subscribe to the WebSocket until the historical backfill is done, ensuring `last_synced_height` is stable before gap-fill logic starts.

**`_process_block(session, block_data, pending_resolutions) -> None`**
The unified block-processing path — called from both the WebSocket loop and the REST gap-fill loop. Responsibilities:
1. Retry any pending fork resolutions from previous blocks.
2. Upsert the `Block` row (skip if hash already exists).
3. Call `detect_fork_at_height` — if a competing block is found, call `_handle_fork`.
4. Update `SyncState.last_synced_height` using `max()` to guarantee monotonicity.

**`_handle_fork(session, new_hash, new_timestamp, competing_block, pending_resolutions) -> None`**
Calls `fetch_block_status` for both hashes to determine canonical vs orphaned. If both return `in_best_chain=True` (ambiguous — can happen in the seconds after a re-org propagates), writes a `ForkEvent` with `resolution_seconds=None` and appends to `pending_resolutions` for later retry. Otherwise calls `write_fork_event` immediately.

**`_rest_gap_fill(session, state) -> None`**
Fetches from `state.last_synced_height` to `fetch_tip_height()` using `fetch_blocks_page`. Mirrors the backfill page-walking pattern: requests pages in ascending order, filters blocks below `last_synced_height`, sorts each page ascending, calls `_process_block` on each. Sleeps `REQUEST_THROTTLE_SECONDS` between pages.

**`run_monitor() -> None`**
Entry point launched from `app/main.py` lifespan. State machine:
- **Normal mode:** attempt `_ws_loop()`. On failure: increment `consecutive_failures`. At `WS_FAILURE_THRESHOLD=3`: log WARNING, enter REST fallback.
- **REST fallback mode:** call `_rest_gap_fill()` every 30 seconds. Every 5 minutes: attempt WebSocket reconnect. On reconnect success: run gap-fill, log INFO, return to normal mode.
- Any unhandled exception: log ERROR, sleep 10s, retry (prevents tight crash loops).

### app/main.py (modified)

Added `from app.monitor import run_monitor` import and wired the monitor thread into the lifespan:

```python
monitor_thread = None  # initialized before startup conditional

# Always starts — monitor gates on backfill_complete internally
monitor_thread = threading.Thread(target=run_monitor, daemon=True, name="monitor")
monitor_thread.start()

# Shutdown
if monitor_thread is not None and monitor_thread.is_alive():
    monitor_thread.join(timeout=5.0)
```

The key design decision: unlike the backfill thread (skipped if `backfill_complete=True`), the monitor always launches. The monitor decides when to activate via `_wait_for_backfill()`. This keeps main.py simple and lets the monitor own its startup logic.

### tests/test_monitor.py (new)

12 tests across 6 classes covering MONI-01 and MONI-03 behaviors:

| Class | Tests | What is tested |
|---|---|---|
| TestWebSocketSubscribe | 2 | SUBSCRIBE_MSG sent after connect; non-block messages ignored |
| TestBackfillGate | 2 | Returns immediately when done; polls while False |
| TestRestFallback | 2 | WARNING logged at 3 failures; _rest_gap_fill called in fallback |
| TestGapFill | 2 | fetch_blocks_page called from last_synced_height; ascending order |
| TestGapFillForkDetection | 2 | detect_fork_at_height called per block; write_fork_event on fork |
| TestLastSyncedHeight | 2 | last_synced_height updated after block; monotonically increases |

## TDD Execution

**Task 1 (RED stubs):** Created `tests/test_monitor.py` with 6 class stubs and 12 pass-body methods. No import of `app.monitor` — collected by pytest with zero errors.

**Task 2 RED:** Replaced stubs with real tests importing `from app.monitor import run_monitor, _process_block, _rest_gap_fill, _wait_for_backfill`. Confirmed `ModuleNotFoundError` — RED phase valid.

**Task 2 GREEN:** Created `app/monitor.py`. Two issues surfaced during GREEN:
1. `record_height` test helper missing `pending_resolutions` keyword argument — fixed inline (Rule 1: bug in test helper).
2. REST fallback tests hung due to `time.time()` returning real values, causing the WS reconnect interval check to fire before `_rest_gap_fill` could be called with a valid state. Fixed by patching `app.monitor.time.time` to return `0.0` and returning a mock `SyncState` from the session mock.

After fixes: 12/12 tests passing. Full suite: 47 passed.

## Commits

| Task | Commit | Description |
|---|---|---|
| Task 1 | 63298a6 | test(03-02): add test stubs for monitor module |
| Task 2 | 8786cdd | feat(03-02): implement monitor.py with WebSocket loop, REST fallback, and gap-fill |
| Task 3 | b6c1abf | feat(03-02): wire monitor_thread into app/main.py lifespan |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test helper function signature mismatch**
- **Found during:** Task 2 GREEN phase (first test run)
- **Issue:** `record_height(sess, block_data, pending)` — positional arg named `pending` did not match `_process_block`'s keyword arg `pending_resolutions`. Mock raised `TypeError`.
- **Fix:** Renamed parameter to `pending_resolutions` to match the actual function signature.
- **Files modified:** tests/test_monitor.py
- **Commit:** 8786cdd

**2. [Rule 1 - Bug] REST fallback tests hung due to unpatched time.time()**
- **Found during:** Task 2 GREEN phase (test_warning_logged_after_three_consecutive_failures and test_rest_poll_called_during_fallback)
- **Issue:** The WS reconnect interval check (`time.time() - last_ws_attempt >= 300`) used real `time.time()`, and `last_ws_attempt` defaulted to `0.0`. When `time.time()` returned current epoch (~1.7 billion), the condition was immediately True, triggering additional `_ws_loop` calls before `_rest_gap_fill` was reached. With `state=None` from the unset mock, `_rest_gap_fill` was never called, causing infinite loop.
- **Fix:** Patch `app.monitor.time.time` to return `0.0` (making `0.0 - 0.0 = 0 < 300`), and configure `mock_session.exec.return_value.first.return_value` to return a valid mock state.
- **Files modified:** tests/test_monitor.py
- **Commit:** 8786cdd

## Key Design Notes for Developer

**Why `websockets.sync.client` instead of async?**
The monitor runs in a background thread, not in FastAPI's asyncio event loop. `websockets.sync.client.connect()` is the synchronous API — it blocks the thread (which is fine, that's the thread's entire job) and uses standard `for message in ws` iteration. Using the async API from a regular thread would require creating a new event loop, which adds complexity with no benefit here.

**Why is the state machine tracking `consecutive_failures` instead of any failure?**
A single network blip (e.g., a brief Wi-Fi drop) should not trigger the 30-second REST polling cadence. Counting only *consecutive* failures means the system stays in fast WebSocket mode through transient errors and only falls back to REST when there's a sustained outage. This is a common pattern in production data pipelines.

**Why does `_process_block` use `max()` for `last_synced_height`?**
WebSocket events could theoretically arrive slightly out of order (e.g., a re-org notification followed by a delayed old block). Using `max()` ensures we never move the sync cursor backwards, so a restart always resumes from the highest successfully-processed height rather than an older one.

**Why does `pending_resolutions` use a shared mutable list?**
Both `_ws_loop` and `_rest_gap_fill` call `_process_block`, which needs to track unresolved forks across multiple block invocations. A mutable list passed by reference from `run_monitor` is the simplest approach — no class state needed, and it's clearly visible in the function signatures that this state is being threaded through.

## Self-Check: PASSED

- app/monitor.py: FOUND
- tests/test_monitor.py: FOUND
- app/main.py (contains monitor_thread): FOUND
- .planning/phases/03-fork-detection-live-monitoring/03-02-SUMMARY.md: FOUND
- Commit 63298a6: FOUND
- Commit 8786cdd: FOUND
- Commit b6c1abf: FOUND
