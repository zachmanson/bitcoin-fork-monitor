# Phase 2: API Client + Backfill - Context

**Gathered:** 2026-03-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Fetch full Bitcoin blockchain history from mempool.space and persist it to SQLite. This phase delivers a rate-limited HTTP client and a checkpointed backfill worker. No live monitoring, no WebSocket subscriptions, no dashboard — just history ingestion.

</domain>

<decisions>
## Implementation Decisions

### Startup behavior
- Backfill runs in a **background thread**, not blocking the API server
- FastAPI starts immediately; API can serve (empty/partial) data while backfill runs in parallel
- Use **FastAPI lifespan context manager** (`asynccontextmanager`) to launch and join the backfill thread — idiomatic FastAPI pattern, ensures clean shutdown on Ctrl+C
- On startup, check `SyncState.backfill_complete`: if True, **skip silently** with one log line — do not launch the thread
- When backfill completes, the thread sets `backfill_complete = True` in SyncState and exits — no inter-thread signaling, API reads the flag from DB on demand

### Checkpoint frequency
- Write `last_synced_height` to SyncState every **100 blocks** — at most 100 blocks of re-work on crash, negligible write overhead (~9000 total writes)
- SyncState row is **updated in place** (single row, not appended) — matches existing model design

### Progress visibility
- Log a progress line every **1000 blocks** using Python's `logging` module at INFO level
- Format: `Backfill: 45000/880000 blocks (5.1%) — height 45000`
- Use `logging` (not `print`) — integrates with Uvicorn logging, can be redirected to file without code changes

### Error / network failure handling
- On 5xx or network error: retry up to **5 times** with exponential backoff (1s, 2s, 4s, 8s, 16s)
- **Same backoff utility** handles both HTTP 429 (rate limit) and 5xx — consistent behavior, less code
- If all 5 retries exhausted: log `ERROR` with the failed height, thread exits cleanly
- On next app restart, backfill resumes from last checkpoint automatically (no special recovery logic needed)
- Thread failure does **not** crash the FastAPI server

### Claude's Discretion
- Exact mempool.space endpoint selection and fork detection strategy (validate `GET /api/blocks/:height` behavior at research time — see STATE.md blocker)
- HTTP client library choice (httpx is idiomatic for FastAPI ecosystem; requests also fine)
- Exact 500ms throttle implementation (time.sleep vs asyncio.sleep)
- Module structure within `app/` (e.g., `app/api_client.py`, `app/backfill.py`)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/models.py` — `Block`, `ForkEvent`, `SyncState` table classes. Backfill reads/writes all three directly.
- `app/database.py` — `engine`, `get_session()` generator, `create_db_and_tables()`. Backfill uses `Session(engine)` directly (not the FastAPI dependency injection version).
- `SyncState.last_synced_height` — already defined as the checkpoint field. Backfill resumes from this value.
- `SyncState.backfill_complete` — already defined as the completion flag. Startup check reads this.

### Established Patterns
- SQLModel `Session(engine)` pattern from `database.py` — backfill creates its own session in the worker thread (not the FastAPI `get_session()` dependency, which is designed for request-scoped use)
- `datetime.utcnow()` used in `ForkEvent.detected_at` and `SyncState.updated_at` — continue this pattern
- Docstrings on all public functions (what, inputs, outputs, assumptions) — established in Phase 1

### Integration Points
- `app/main.py` — does not exist yet; Phase 2 creates it. The lifespan function lives here.
- Backfill thread imports `Block`, `ForkEvent`, `SyncState` from `app/models.py` and `engine` from `app/database.py`
- Phase 3 (live monitoring) will add to `app/main.py` lifespan — Phase 2 establishes the pattern

</code_context>

<specifics>
## Specific Ideas

- The STATE.md blocker is important: `GET /api/blocks/:height` behavior (whether it returns orphaned blocks or only canonical) must be validated at research time — the entire fork detection strategy depends on it
- mempool.space rate limits are undisclosed; 500ms throttle is the starting point, empirical adjustment expected

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 02-api-client-backfill*
*Context gathered: 2026-03-09*
