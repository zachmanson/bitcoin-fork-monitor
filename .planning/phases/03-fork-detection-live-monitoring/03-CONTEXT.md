# Phase 3: Fork Detection + Live Monitoring - Context

**Gathered:** 2026-03-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Detect Bitcoin temporary forks in real-time as competing blocks arrive at the same height, record orphaned blocks and fork events, and stay resilient across WebSocket disconnects via gap-fill and REST fallback. No dashboard, no API endpoints — just the monitoring thread and fork detection logic that downstream phases read from.

</domain>

<decisions>
## Implementation Decisions

### Orphan confirmation timing
- Record a ForkEvent **immediately** when two blocks collide at the same height — no N-block delay. By the time the WebSocket delivers both competing blocks, the chain has already resolved.
- Use **mempool.space `in_best_chain` field** to determine which block is canonical vs orphaned. Do not guess based on arrival order.
- `resolution_seconds` uses **block header timestamps** (already stored in `Block.timestamp`) — consistent with how backfill-recorded forks work, and reflects when miners produced the competing blocks rather than our observation time.
- If `in_best_chain` hasn't updated yet when we query (rare, but possible within seconds of a fork): **record the ForkEvent with `resolution_seconds=None`** and schedule a follow-up check after the next block arrives. Captures the event immediately, fills in resolution time once the chain settles.

### WebSocket failure handling
- **3 consecutive WebSocket failures** trigger fallback to REST polling — consistent with the retry philosophy established in `api_client.py`.
- REST fallback **polling interval: 30 seconds** — captures blocks well within the ~10-minute block window without excessive API calls.
- While in REST fallback mode, **attempt WebSocket reconnect every 5 minutes**. On success, switch back to WebSocket. On failure, stay on REST.
- Log **WARNING when falling back** to REST, **INFO when recovering** to WebSocket — consistent with backfill's logging conventions. Only log on state transitions, not on every poll.

### Gap-fill on reconnect
- **`SyncState.last_synced_height` is the source of truth** for gap-fill. The live monitor updates this field on every new block it processes (one DB write per block, ~once per 10 minutes).
- Gap-fill lookback is **uncapped** — always fill from `last_synced_height` to current tip. Data volume is tiny, no need for a cap.
- **Full fork detection runs on gap-fill blocks** — the same height-collision logic runs on every fetched block, ensuring no fork events are silently skipped across disconnects (MONI-03).
- `last_synced_height` is shared between backfill and live monitoring — not a separate field. The monitor takes over writing it once backfill completes.

### Thread architecture
- **Second background thread** (`monitor_thread`) added to `app/main.py` lifespan alongside the existing `backfill_thread`. Same pattern: `threading.Thread(target=run_monitor, daemon=True)`, `join(timeout=5.0)` on shutdown.
- Monitor thread **waits for `backfill_complete` before subscribing** — polls `SyncState.backfill_complete` on startup and only begins live monitoring once backfill finishes. Prevents write conflicts during the final backfill heights.
- **Fork detection logic lives in `app/fork_detector.py`** — pure functions for height-collision detection, ForkEvent writing, and resolution time calculation. Both the live monitor and any future backfill replay can import it. Isolated and independently testable.
- **Live monitor lives in `app/monitor.py`** — parallel to `app/backfill.py`. Backfill handles history; monitor handles live.

### Claude's Discretion
- WebSocket library choice (websockets, websocket-client, or httpx WebSocket support)
- Exact mempool.space WebSocket subscription message format and event parsing
- In-memory state representation for tracking "pending" fork events awaiting resolution_seconds
- Exact backoff/retry timing for the 5-minute WebSocket reconnect attempts

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/api_client.py` — `fetch_blocks_page()` and `fetch_tip_height()`: REST fallback and gap-fill reuse these directly. Retry/backoff logic already handles 429s and 5xx errors.
- `app/models.py` — `Block`, `ForkEvent`, `SyncState`: all three tables are written by Phase 3. `SyncState.last_synced_height` is the gap-fill resume point; `SyncState.backfill_complete` is the monitor startup gate.
- `app/database.py` — `engine`, `Session(engine)` pattern: monitor thread creates its own session (not the FastAPI dependency injection `get_session()`), same as backfill.
- `app/main.py` — lifespan context manager: Phase 3 adds `monitor_thread` alongside `backfill_thread`. Pattern is established — just extend it.

### Established Patterns
- `Session(engine)` for background threads (not `Depends(get_session)` — that's request-scoped)
- `threading.Thread(daemon=True)` + `join(timeout=5.0)` for graceful shutdown
- `datetime.utcnow()` for all wall-clock timestamps
- `logging` module at INFO/WARNING/ERROR (not `print`) — integrates with Uvicorn logging
- `RETRY_DELAYS = [1, 2, 4, 8, 16]` pattern from api_client.py — explicit backoff schedule
- Docstrings on all public functions (what, inputs, outputs, assumptions)

### Integration Points
- `app/main.py` lifespan: Phase 3 adds the `monitor_thread` launch and join. The backfill thread and monitor thread coexist; monitor waits for backfill to complete before starting WebSocket.
- `app/fork_detector.py` (new): will be imported by `app/monitor.py` for live detection and potentially by backfill tests for unit testing the detection logic in isolation.
- `Block.is_canonical`: fork detector flips this to `False` for orphaned blocks, consistent with how backfill populated it.
- Phase 4 reads `ForkEvent` rows and `Block` rows via REST endpoints — Phase 3's writes are Phase 4's reads.

</code_context>

<specifics>
## Specific Ideas

- The STATE.md blocker ("stale block confirmation window") is resolved: record immediately, use mempool.space `in_best_chain` for authority.
- Resolution time uses block header timestamps, not wall-clock detection times — this makes live-detected fork events comparable to backfill-detected fork events in the same table.
- The monitor thread gates on `backfill_complete` to avoid write conflicts — this means the WebSocket subscription doesn't start during initial startup on a fresh database. Expected behavior.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-fork-detection-live-monitoring*
*Context gathered: 2026-03-09*
