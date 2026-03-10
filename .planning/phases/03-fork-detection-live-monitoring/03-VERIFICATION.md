---
phase: 03-fork-detection-live-monitoring
verified: 2026-03-09T00:00:00Z
status: passed
score: 11/11 must-haves verified
gaps: []
human_verification:
  - test: "Start the app against a live network and confirm the monitor logs 'Backfill complete — starting live monitor' followed by 'WebSocket connected and subscribed to block events'"
    expected: "Both log lines appear in stdout. New blocks arriving on the Bitcoin network are processed and Block rows appear in bitcoin_forks.db at heights matching the current chain tip."
    why_human: "Requires a live network connection to mempool.space and a completed (or mocked) backfill — cannot verify real WebSocket subscription in automated tests."
  - test: "Kill the running process while in WebSocket mode, restart it, confirm 'Gap-fill: from height N to tip M' appears in logs where N is the last processed height"
    expected: "The gap-fill log line shows N = last_synced_height from SyncState before the kill, and M = current tip. No blocks in that range are skipped."
    why_human: "Crash/resume requires a real process kill mid-operation and a live network to validate gap-fill correctness."
  - test: "Block the WebSocket endpoint (e.g. firewall rule or host override) for 3 block intervals and confirm 'switching to REST fallback polling' WARNING appears and REST polling begins"
    expected: "WARNING log line appears after 3 consecutive WebSocket failures. The DB continues to receive new Block rows via REST polling at ~30-second intervals."
    why_human: "Sustained WebSocket outage simulation requires network-level manipulation; the automated test mocks the failure but cannot verify the full end-to-end observable behavior."
---

# Phase 3: Fork Detection and Live Monitoring — Verification Report

**Phase Goal:** Live block monitoring — WebSocket listener detects competing blocks (forks) at the same height, writes ForkEvent records to the database, falls back to REST polling when WebSocket fails, and fills any gaps on reconnect. The system runs continuously in a background thread started at app startup.
**Verified:** 2026-03-09
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Two blocks at the same height with different hashes are detected as a fork | VERIFIED | `detect_fork_at_height` queries Block table with `height == h AND hash != new_hash`; 3 tests in TestDetectFork pass |
| 2 | ForkEvent is written with correct canonical_hash, orphaned_hash, and resolution_seconds | VERIFIED | `write_fork_event` computes `abs((canonical_ts - orphaned_ts).total_seconds())`; TestWriteForkEvent 3 tests pass |
| 3 | write_fork_event is idempotent — second call with same args returns existing row, no duplicate inserted | VERIFIED | Idempotency check queries by (height, canonical_hash, orphaned_hash) before insert; TestForkIdempotency 2 tests pass |
| 4 | fetch_block_status returns in_best_chain bool from mempool.space status endpoint | VERIFIED | `fetch_block_status` in api_client.py hits `/api/block/{hash}/status`, returns raw JSON dict; import confirmed |
| 5 | resolution_seconds uses abs() and is always non-negative | VERIFIED | Line 106 of fork_detector.py: `abs((canonical_ts - orphaned_ts).total_seconds())`; test_resolution_seconds_is_abs passes |
| 6 | Monitor waits for backfill_complete=True before subscribing to WebSocket | VERIFIED | `_wait_for_backfill()` polls SyncState in a loop; TestBackfillGate 2 tests pass including polling behavior |
| 7 | Each block received via WebSocket calls detect_fork_at_height and writes ForkEvent if collision found | VERIFIED | `_process_block` calls `detect_fork_at_height` → `_handle_fork` → `write_fork_event`; TestGapFillForkDetection 2 tests pass |
| 8 | After 3 consecutive WebSocket failures, WARNING logged and REST polling begins | VERIFIED | `consecutive_failures >= WS_FAILURE_THRESHOLD` triggers `in_rest_fallback = True` + WARNING log; TestRestFallback 2 tests pass |
| 9 | On WebSocket reconnect, gap-fill runs from last_synced_height to tip before resuming live subscription | VERIFIED | `run_monitor` calls `_rest_gap_fill` after successful `_ws_loop` reconnect (lines 449-451); TestGapFill 2 tests pass |
| 10 | SyncState.last_synced_height is updated after every block processed | VERIFIED | `_process_block` updates `state.last_synced_height = max(state.last_synced_height, height)` and commits; TestLastSyncedHeight 2 tests pass |
| 11 | Monitor thread launches from app/main.py lifespan alongside backfill_thread and joins on shutdown | VERIFIED | `app/main.py` lines 85-110: `threading.Thread(target=run_monitor, daemon=True, name="monitor")` with `join(timeout=5.0)` on shutdown |

**Score:** 11/11 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/fork_detector.py` | Pure `detect_fork_at_height()` and `write_fork_event()` functions | VERIFIED | 128 lines; both functions present with full docstrings; no network calls; session injected |
| `app/api_client.py` | `fetch_block_status(block_hash)` with RETRY_DELAYS backoff | VERIFIED | Function at line 145; hits `/api/block/{hash}/status`; follows identical retry pattern to `fetch_blocks_page` |
| `tests/test_fork_detector.py` | MONI-02 unit tests covering 5 classes | VERIFIED | 11 tests across TestDetectFork, TestWriteForkEvent, TestForkIdempotency, TestOrphanFlagged, TestPendingResolution — all pass |
| `app/monitor.py` | `run_monitor()` entry point, WebSocket loop, REST fallback, gap-fill | VERIFIED | 468 lines; exports `run_monitor`, `_process_block`, `_rest_gap_fill`, `_wait_for_backfill`, `_ws_loop` |
| `app/main.py` | `monitor_thread` launched in lifespan | VERIFIED | Lines 89-95: thread created and started; lines 108-110: join on shutdown; `from app.monitor import run_monitor` at line 41 |
| `tests/test_monitor.py` | MONI-01 and MONI-03 unit tests with 6 classes | VERIFIED | 12 tests across TestWebSocketSubscribe, TestBackfillGate, TestRestFallback, TestGapFill, TestGapFillForkDetection, TestLastSyncedHeight — all pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app/fork_detector.py` | `app/api_client.fetch_block_status` | Called during fork detection to resolve in_best_chain | NOT DIRECT — BY DESIGN | fork_detector.py intentionally does not import api_client. fetch_block_status is called by `_handle_fork` in monitor.py — the plan explicitly required this separation |
| `app/fork_detector.py` | `app/models.ForkEvent` | `session.add(ForkEvent(...))` | VERIFIED | Line 117 of fork_detector.py: `ForkEvent(height=..., canonical_hash=..., orphaned_hash=..., resolution_seconds=...)` |
| `app/monitor.py` | `app/fork_detector.detect_fork_at_height` | Called on every block received (live + gap-fill) | VERIFIED | Line 148: `competing_block = detect_fork_at_height(session, height, block_hash)` |
| `app/monitor.py` | `app/api_client.fetch_blocks_page` | Gap-fill and REST fallback polling | VERIFIED | Line 362: `blocks = fetch_blocks_page(page_top)` inside `_rest_gap_fill` |
| `app/monitor.py` | `app/models.SyncState` | Reads backfill_complete gate; writes last_synced_height per block | VERIFIED | Lines 98-100 (_wait_for_backfill), lines 156-161 (_process_block) |
| `app/main.py` | `app/monitor.run_monitor` | `threading.Thread(target=run_monitor)` | VERIFIED | Line 41: `from app.monitor import run_monitor`; line 91: `threading.Thread(target=run_monitor, ...)` |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| MONI-01 | 03-02-PLAN.md | System subscribes to new Bitcoin blocks in real-time via mempool.space WebSocket API | SATISFIED | `_ws_loop` connects to `wss://mempool.space/api/v1/ws`, sends `{"action": "want", "data": ["blocks"]}` subscription; TestWebSocketSubscribe verifies subscription message sent |
| MONI-02 | 03-01-PLAN.md | System detects temporary forks when competing blocks appear at the same height and records orphaned blocks | SATISFIED | `detect_fork_at_height` + `write_fork_event` in fork_detector.py; orphaned block `is_canonical` set to False; 11 unit tests pass |
| MONI-03 | 03-02-PLAN.md | System falls back to REST polling if WebSocket is unavailable and performs gap-fill on reconnect | SATISFIED | `run_monitor` state machine: 3 consecutive failures → REST fallback; `_rest_gap_fill` called every 30s in fallback; WS reconnect attempted every 5 minutes with gap-fill run on success; 4 tests cover fallback and gap-fill |

No orphaned requirements — REQUIREMENTS.md lists MONI-01, MONI-02, MONI-03 all marked Complete for Phase 3, and all three are claimed in plan frontmatter.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `app/monitor.py` | 370 | `_process_block(session, block_data, pending_resolutions=[])` — fresh list per block in gap-fill | Warning | Ambiguous forks detected during gap-fill cannot carry their pending_resolutions to subsequent gap-fill blocks. Each block gets an isolated throw-away list. Forks written with `resolution_seconds=None` during gap-fill will not be retried within the same `_rest_gap_fill` call. They would only be retried if the monitor returns to WebSocket mode and processes a subsequent block via `_ws_loop` (which does use the shared `pending_resolutions`). In practice, most forks resolve within 1-2 blocks and the REST fallback window means multiple `_rest_gap_fill` calls will run, each retrying the pending items from the DB perspective via future `_process_block` calls — but not via the in-memory list. |

No blocker anti-patterns found. No TODO/FIXME/placeholder comments found in phase files. No empty implementations or stub return values.

---

### Human Verification Required

#### 1. Live WebSocket Subscription

**Test:** Run `uvicorn app.main:app --reload` against a real database with `backfill_complete=True`. Watch logs for `WebSocket connected and subscribed to block events`. Wait for a Bitcoin block (~10 min average interval) and confirm a new Block row appears in `bitcoin_forks.db`.
**Expected:** Block row inserted at the current chain tip height. `SyncState.last_synced_height` advances.
**Why human:** Real WebSocket subscription requires live network access to mempool.space and a real Bitcoin block arriving.

#### 2. Crash Recovery and Gap-Fill

**Test:** With the app running in WebSocket mode, kill the process with Ctrl+C. Wait 2+ minutes. Restart the app. Confirm logs show `Gap-fill: from height N to tip M` where N is the height before the kill.
**Expected:** All blocks mined during the downtime appear in the DB after restart. No heights are skipped.
**Why human:** Requires live network, controlled process termination, and real blocks arriving during the downtime window.

#### 3. REST Fallback Triggering

**Test:** Block `mempool.space` at the OS level (e.g., `/etc/hosts` redirect or firewall rule) while the app is running in WebSocket mode. Wait for 3 connection failures. Confirm `switching to REST fallback polling` WARNING appears in logs.
**Expected:** WARNING log within ~60 seconds of blocking the host. DB continues to receive Block rows via REST polling at ~30-second intervals (requires mempool.space REST endpoint to remain reachable, or a second mock).
**Why human:** Sustained WebSocket outage requires network-level intervention that cannot be replicated in a unit test.

---

### Design Deviation Note

The PLAN (03-02) stated: `pending_resolutions` is a mutable list shared across `_ws_loop` and `_rest_gap_fill` calls. In the implementation, `_rest_gap_fill` does not accept `pending_resolutions` as a parameter and instead passes a fresh `[]` to each `_process_block` call (line 370). This means the in-memory pending-resolution retry mechanism does not function across blocks within a single `_rest_gap_fill` invocation.

This is not a blocker because:
1. None of the must-have truths or MONI requirements require cross-block pending-resolution retry within a single gap-fill call.
2. ForkEvents with `resolution_seconds=None` are correctly persisted to the DB.
3. The `_ws_loop` path (normal mode) does use the shared list correctly.
4. The test for this behavior (TestGapFillForkDetection) validates the more important guarantee: fork detection and ForkEvent writing occur for every gap-filled block.

Flagged as a warning-level finding for the next developer working in this area.

---

### Gaps Summary

No gaps. All must-have truths verified against actual implementation. All required artifacts exist, are substantive, and are correctly wired. All three MONI requirements are satisfied with passing unit tests. Full suite: 47 passed, 0 failed, 0 errors.

The one warning-level finding (pending_resolutions not shared in gap-fill) does not block the phase goal and has no must-have truth asserting this behavior.

---

_Verified: 2026-03-09_
_Verifier: Claude (gsd-verifier)_
