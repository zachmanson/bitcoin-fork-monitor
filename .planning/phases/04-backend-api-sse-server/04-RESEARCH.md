# Phase 4: Backend API + SSE Server - Research

**Researched:** 2026-03-09
**Domain:** FastAPI REST endpoints, Server-Sent Events (SSE), thread-to-async bridging
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DASH-02 | User can view a summary stats panel showing: total canonical blocks, total orphaned blocks, current stale rate, date of last fork | `GET /api/stats` endpoint — counts from Block table + last ForkEvent.detected_at |
| DASH-04 | Dashboard receives real-time updates via Server-Sent Events (SSE) without requiring a page refresh | `GET /api/events` SSE endpoint — asyncio.Queue broadcast bus bridges monitor thread to browser clients |
</phase_requirements>

---

## Summary

Phase 4 adds the HTTP and SSE layer that exposes the SQLite data to browser clients. The project already has a FastAPI app instance in `app/main.py`, a running monitor thread that writes new blocks and fork events, and a `get_session` dependency in `database.py`. This phase layers three REST endpoints and one SSE endpoint on top of that foundation — no new background threads, no new database tables.

The central design challenge is the SSE endpoint: the monitor thread is synchronous (it uses `websockets.sync.client` and blocks on `Session`), but SSE requires an async generator running in FastAPI's asyncio event loop. The standard solution is a per-client `asyncio.Queue` maintained in an in-process event bus. When the monitor thread records a new block or fork, it calls `asyncio.run_coroutine_threadsafe()` to safely enqueue a payload into every connected client's queue. Each SSE endpoint generator then `await queue.get()` in an infinite loop and yields events as they arrive.

**Critical version finding:** The project's `pyproject.toml` currently pins `fastapi>=0.115.0`. Native FastAPI SSE (`from fastapi.sse import EventSourceResponse`) was added in FastAPI 0.135.0 (released March 1, 2026). The installed version is 0.115.6, which does NOT have `fastapi.sse`. The plan MUST either upgrade FastAPI to >=0.135.0 OR use `sse-starlette` (which works with 0.115.x). Upgrading FastAPI is the cleaner long-term path since it requires no third-party dependency; using sse-starlette avoids a major version bump mid-project. **Recommendation: upgrade FastAPI to >=0.135.0** — the breaking-change surface from 0.115 to 0.135 is minimal (Starlette version bump to >=0.46.0) and the native API is simpler.

**Primary recommendation:** Upgrade FastAPI to >=0.135.0, implement SSE with native `fastapi.sse.EventSourceResponse`, bridge the monitor thread using an in-process event bus of per-client `asyncio.Queue` objects, and implement REST endpoints as thin query functions over the existing SQLModel session.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.135.0 | REST + SSE endpoints | Already in project; 0.135 adds native SSE |
| SQLModel | >=0.0.21 | ORM queries for endpoints | Already in project; `get_session` dep exists |
| Starlette | >=0.46.0 | Required by FastAPI 0.135 | Transitive; auto-upgraded with FastAPI |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `fastapi.sse` | (part of FastAPI 0.135) | `EventSourceResponse`, `ServerSentEvent` | The SSE endpoint only |
| `asyncio` (stdlib) | Python 3.12 | `Queue`, `run_coroutine_threadsafe` | Thread-to-async event bus |
| `httpx` | (dev/test only) | TestClient for SSE integration tests | Testing only |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Native `fastapi.sse` | `sse-starlette` 3.3.2 | sse-starlette works with 0.115.x; avoids upgrade risk. Native is simpler once upgraded. |
| Per-client `asyncio.Queue` | Redis Pub/Sub | Redis adds infra; overkill for a single-process local tool |
| `asyncio.run_coroutine_threadsafe` | `loop.call_soon_threadsafe` + `queue.put_nowait` | Both are correct. `run_coroutine_threadsafe` is slightly safer for awaitable puts. |

**Installation (upgrade):**
```bash
pip install "fastapi>=0.135.0"
```

Or update `pyproject.toml`:
```toml
"fastapi>=0.135.0",
```

---

## Architecture Patterns

### Recommended Project Structure

```
app/
├── main.py          # Add REST routers + SSE endpoint; existing lifespan unchanged
├── routers/
│   ├── __init__.py
│   ├── stats.py     # GET /api/stats
│   ├── forks.py     # GET /api/forks (paginated)
│   └── blocks.py    # GET /api/blocks (recent)
├── events.py        # EventBus — global subscriber list + broadcast helper
├── models.py        # (existing) Block, ForkEvent, SyncState
├── database.py      # (existing) engine, get_session
└── monitor.py       # (existing) — call event_bus.notify() after each DB write
```

Using a `routers/` subdirectory is a standard FastAPI convention for keeping endpoints organized as the app grows. Each router file owns one resource group.

### Pattern 1: REST Endpoint with SQLModel Dependency Injection

**What:** A path function that receives a `Session` via `Depends(get_session)` and runs a SELECT query.

**When to use:** Every REST endpoint — stats, forks, blocks.

```python
# Source: https://sqlmodel.tiangolo.com/tutorial/fastapi/limit-and-offset/
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select, func
from app.database import get_session
from app.models import Block, ForkEvent

router = APIRouter()

@router.get("/api/forks")
def list_forks(
    offset: int = 0,
    limit: int = Query(default=50, le=200),
    session: Session = Depends(get_session),
):
    forks = session.exec(
        select(ForkEvent).order_by(ForkEvent.height.desc()).offset(offset).limit(limit)
    ).all()
    return forks
```

### Pattern 2: Stats Aggregation Query

**What:** Single endpoint that runs COUNT queries and computes stale rate in Python.

**When to use:** `GET /api/stats` only.

```python
from sqlmodel import Session, select, func
from app.analytics import calculate_stale_rate

@router.get("/api/stats")
def get_stats(session: Session = Depends(get_session)):
    canonical = session.exec(
        select(func.count()).where(Block.is_canonical == True)  # noqa: E712
    ).one()
    orphaned = session.exec(
        select(func.count()).where(Block.is_canonical == False)  # noqa: E712
    ).one()
    last_fork = session.exec(
        select(ForkEvent).order_by(ForkEvent.detected_at.desc())
    ).first()
    return {
        "canonical_blocks": canonical,
        "orphaned_blocks": orphaned,
        "stale_rate": calculate_stale_rate(canonical, orphaned),
        "last_fork_at": last_fork.detected_at if last_fork else None,
    }
```

Note: `func.count()` without a `.where()` on a large table is fine for SQLite at ~900k rows. This runs in single-digit milliseconds.

### Pattern 3: SSE Event Bus (Thread-to-Async Bridge)

**What:** A module-level `EventBus` class that holds a list of per-client `asyncio.Queue` objects. The monitor thread calls `bus.notify(data)` after every DB write; the SSE endpoint's generator `await`s each queue.

**When to use:** The SSE endpoint in 04-02, and the monitor's `_process_block` function (which calls `bus.notify`).

```python
# app/events.py
import asyncio
from typing import Any

class EventBus:
    """
    In-process publish/subscribe bus for SSE clients.

    Why per-client queues? Each SSE connection is an open HTTP response
    streaming data to one browser tab. If we used a single shared queue,
    the first client to call queue.get() would consume the event before
    other clients see it. Per-client queues are the standard pattern for
    broadcast SSE.

    Thread safety: asyncio.Queue is not thread-safe, so we use
    asyncio.run_coroutine_threadsafe() to enqueue from the monitor thread.
    """

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called at FastAPI startup to capture the event loop."""
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        """Register a new SSE client. Returns a queue to await on."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a client queue on disconnect."""
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def notify(self, data: Any) -> None:
        """
        Called from the monitor thread to broadcast an event.

        run_coroutine_threadsafe schedules a coroutine on the event loop
        from any OS thread. It is the correct way to call async code from
        synchronous threads — do not use queue.put_nowait() directly from
        a thread, as asyncio.Queue is not thread-safe.
        """
        if self._loop is None:
            return
        for q in list(self._subscribers):
            asyncio.run_coroutine_threadsafe(q.put(data), self._loop)


event_bus = EventBus()
```

```python
# SSE endpoint (app/main.py or app/routers/events.py)
# Source: https://fastapi.tiangolo.com/tutorial/server-sent-events/
import asyncio
from collections.abc import AsyncIterable
from fastapi import Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from app.events import event_bus

@app.get("/api/events", response_class=EventSourceResponse)
async def sse_events(request: Request) -> AsyncIterable[ServerSentEvent]:
    q = event_bus.subscribe()
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                data = await asyncio.wait_for(q.get(), timeout=15.0)
                yield ServerSentEvent(data=data, event="update")
            except asyncio.TimeoutError:
                # Keep-alive comment; prevents proxy/browser from closing idle connections.
                # FastAPI 0.135 sends these automatically every 15s, but explicit is fine.
                yield ServerSentEvent(comment="keepalive")
    finally:
        event_bus.unsubscribe(q)
```

### Pattern 4: Capturing the Event Loop at Startup

**What:** Store `asyncio.get_event_loop()` in the `EventBus` during FastAPI lifespan startup, before any threads try to call `notify()`.

**When to use:** `app/main.py` lifespan, immediately after `create_db_and_tables()`.

```python
# In lifespan startup block (app/main.py)
import asyncio
from app.events import event_bus

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    event_bus.set_loop(asyncio.get_event_loop())  # capture before threads start
    # ... rest of existing startup
    yield
    # ... shutdown
```

### Pattern 5: Monitor Calls `event_bus.notify()`

**What:** After each `_process_block` DB commit in `monitor.py`, call `event_bus.notify()` with a small dict payload.

**When to use:** End of `_process_block()`, after `session.commit()` on the SyncState update.

```python
# In monitor.py _process_block(), after SyncState commit
from app.events import event_bus

event_bus.notify({
    "type": "block",
    "height": height,
    "hash": block_hash,
    "is_fork": competing_block is not None,
})
```

### Anti-Patterns to Avoid

- **Shared `asyncio.Queue` (broadcast pitfall):** A single queue means only one client receives each event. Use per-client queues.
- **Calling `queue.put_nowait()` from a thread:** `asyncio.Queue` is not thread-safe. Always use `run_coroutine_threadsafe`.
- **Storing `asyncio.get_event_loop()` at module import time:** The loop doesn't exist until FastAPI starts. Capture it in the lifespan function.
- **Blocking the async endpoint with a `time.sleep()`:** Any blocking call inside an `async def` endpoint freezes the entire event loop. Use `await asyncio.sleep()`.
- **Missing `request.is_disconnected()` check:** Without it, queues accumulate indefinitely for disconnected clients, growing until process OOM.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Thread → async bridging | Custom lock/pipe/socket | `asyncio.run_coroutine_threadsafe` | stdlib; handles event loop wakeup correctly |
| SSE wire format | Custom `text/event-stream` formatter | `fastapi.sse.ServerSentEvent` | Handles escaping, multi-line data, `id:`, `retry:` fields per W3C spec |
| Request body pagination validation | Manual `if limit > 200: raise` | `Query(default=50, le=200)` | FastAPI validates automatically and includes in OpenAPI docs |
| Stale rate formula | Re-implement in router | `app.analytics.calculate_stale_rate()` | Already exists, already tested — call it |
| Keep-alive pings | Timer thread sending comments | FastAPI 0.135 auto-pings every 15s | Built into `EventSourceResponse` |

**Key insight:** The heavy lifting (DB writes, fork detection, WebSocket subscription) is already done by the monitor thread. This phase is thin: expose what's in SQLite, pipe new events to browsers.

---

## Common Pitfalls

### Pitfall 1: asyncio.Queue Not Thread-Safe

**What goes wrong:** Monitor thread calls `queue.put_nowait(data)` directly. Intermittent crashes or data corruption under load because CPython's asyncio internals use non-thread-safe data structures.

**Why it happens:** `asyncio.Queue` documentation states "not thread-safe." Developers see it looks like `queue.Queue` and assume it is.

**How to avoid:** Always use `asyncio.run_coroutine_threadsafe(q.put(data), loop)` from non-async threads. This is the stdlib-blessed pattern.

**Warning signs:** `RuntimeError: Non-thread-safe operation invoked on an event loop` in logs.

### Pitfall 2: FastAPI Version Does Not Have `fastapi.sse`

**What goes wrong:** `from fastapi.sse import EventSourceResponse` raises `ImportError` at startup.

**Why it happens:** `fastapi.sse` was added in 0.135.0. The project currently installs 0.115.6.

**How to avoid:** Upgrade FastAPI in pyproject.toml to `>=0.135.0` and run `pip install -e .` (or `pip install "fastapi>=0.135.0"`).

**Warning signs:** `ImportError: cannot import name 'EventSourceResponse' from 'fastapi'` on startup.

### Pitfall 3: Event Loop Not Captured Before Thread Start

**What goes wrong:** `event_bus.set_loop()` is called after the monitor thread has already started, creating a race condition where `notify()` is called before `_loop` is set.

**Why it happens:** Thread startup is in the lifespan, and `set_loop()` is added after it.

**How to avoid:** Always call `event_bus.set_loop(asyncio.get_event_loop())` as the first statement after `create_db_and_tables()` in lifespan, before any `threading.Thread(...).start()` calls.

**Warning signs:** SSE clients connect but receive no events; `event_bus._loop is None` at notify time.

### Pitfall 4: `func.count()` Comparison with Boolean in SQLModel

**What goes wrong:** `select(func.count()).where(Block.is_canonical == True)` triggers a SQLAlchemy warning about comparing with `== True` vs `is_(True)`.

**Why it happens:** SQLAlchemy prefers `.is_(True)` for boolean columns.

**How to avoid:** Use `Block.is_canonical.is_(True)` or add `# noqa: E712` comment if the `== True` form is kept for readability.

### Pitfall 5: SSE Client Count Grows Forever

**What goes wrong:** Browser tabs close but their queues stay in `event_bus._subscribers`, accumulating notifications in memory.

**Why it happens:** Missing `finally: event_bus.unsubscribe(q)` block in the SSE generator.

**How to avoid:** Always wrap the SSE generator loop in `try/finally` with `unsubscribe` in the `finally` block.

### Pitfall 6: Slow Stats Query on 900k-Row Block Table

**What goes wrong:** `SELECT COUNT(*) FROM block WHERE is_canonical = 1` runs in hundreds of milliseconds after backfill.

**Why it happens:** `is_canonical` is not indexed in the current schema (only `height` is indexed).

**How to avoid:** Either accept the slow count (it's a personal tool, not a high-traffic API), or add `index=True` to `Block.is_canonical` in models.py. A 900k-row SQLite count without index runs in ~50-150ms, which is acceptable. Adding the index is a schema migration (requires `ALTER TABLE` or drop-and-recreate).

**Recommendation:** Do not add the index in this phase. Measure the actual query time at dev; if over 200ms, add it.

---

## Code Examples

Verified patterns from official sources:

### SQLModel Offset/Limit Pagination

```python
# Source: https://sqlmodel.tiangolo.com/tutorial/fastapi/limit-and-offset/
from fastapi import Query
from sqlmodel import select

@router.get("/api/forks")
def list_forks(
    offset: int = 0,
    limit: int = Query(default=50, le=200),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(ForkEvent)
        .order_by(ForkEvent.detected_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
```

### COUNT Query with SQLModel

```python
# Source: SQLModel/SQLAlchemy official — func.count()
from sqlmodel import func, select

canonical_count = session.exec(
    select(func.count(Block.hash)).where(Block.is_canonical.is_(True))
).one()
```

### FastAPI 0.135 SSE Native API

```python
# Source: https://fastapi.tiangolo.com/tutorial/server-sent-events/
from collections.abc import AsyncIterable
from fastapi.sse import EventSourceResponse, ServerSentEvent

@app.get("/api/events", response_class=EventSourceResponse)
async def sse_events() -> AsyncIterable[ServerSentEvent]:
    yield ServerSentEvent(data={"msg": "connected"}, event="init")
    while True:
        await asyncio.sleep(1)
        yield ServerSentEvent(data={"ping": True}, event="ping")
```

### Cross-Thread Safe Enqueue

```python
# Source: https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.run_coroutine_threadsafe
import asyncio

# Called from monitor thread (non-async context):
asyncio.run_coroutine_threadsafe(queue.put(payload), event_loop)
```

### FastAPI Router Registration

```python
# Source: FastAPI official docs — routers
from fastapi import APIRouter
router = APIRouter(prefix="/api", tags=["api"])

# In main.py:
app.include_router(router)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` | `@asynccontextmanager async def lifespan` | FastAPI 0.93 (2023) | Already used in this project — no change needed |
| `sse-starlette` third-party package | `fastapi.sse` native module | FastAPI 0.135.0 (Mar 2026) | Simpler import, no extra dep — requires upgrade |
| Manual `text/event-stream` response | `EventSourceResponse` + `ServerSentEvent` | FastAPI 0.135.0 / Starlette | W3C-compliant formatting, keep-alive built in |
| `offset`/`limit` pagination | (same — still standard for SQLite) | N/A | Cursor-based is better for large datasets; overkill here |

**Deprecated/outdated:**
- `@app.on_event("startup")`: Deprecated since FastAPI 0.93. This project already uses the modern lifespan pattern — no change needed.
- `sse-starlette` as the only SSE option: Still works but now redundant with native FastAPI SSE.

---

## Open Questions

1. **Should `GET /api/blocks` return all blocks or just recent N?**
   - What we know: The roadmap says "most recent blocks with fork events highlighted." Phase 5 (dashboard) will render a live block feed.
   - What's unclear: How many blocks to return (last 10? 50? 100?), and whether orphaned blocks should appear in this list.
   - Recommendation: Return last 50 blocks ordered by `height DESC`, include both canonical and orphaned (the dashboard phase will highlight forks). Add `limit` query param, max 200.

2. **Should `event_bus.notify()` send a full block payload or just a signal?**
   - What we know: Phase 5 will render a live block feed. The SSE payload needs enough data to update the UI without a separate REST call.
   - What's unclear: Exact fields Phase 5 will need (determined in Phase 5 research).
   - Recommendation: Send a minimal but complete dict: `{type, height, hash, timestamp, is_canonical, is_fork}`. Keep it small; the dashboard can fetch full detail via REST if needed.

3. **Does `request.is_disconnected()` work reliably in FastAPI 0.135?**
   - What we know: It is part of the Starlette `Request` API and is standard practice.
   - What's unclear: Behavior with some reverse proxies (nginx, Caddy) that buffer SSE.
   - Recommendation: Implement with `is_disconnected()` check plus the `try/finally` unsubscribe. Sufficient for a local dev tool; no reverse proxy in scope.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/test_stats.py tests/test_forks.py tests/test_blocks.py -x -q` |
| Full suite command | `pytest -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-02 | `GET /api/stats` returns correct canonical, orphaned, stale_rate, last_fork_at | unit | `pytest tests/test_stats.py -x -q` | ❌ Wave 0 |
| DASH-02 | Stale rate formula uses existing `calculate_stale_rate` | unit | `pytest tests/test_stats.py::test_stats_stale_rate -x -q` | ❌ Wave 0 |
| DASH-04 | `GET /api/events` returns `text/event-stream` content type | unit | `pytest tests/test_events.py::test_sse_content_type -x -q` | ❌ Wave 0 |
| DASH-04 | Monitor thread event reaches SSE client queue within 2s | integration | `pytest tests/test_events.py::test_event_bus_notify -x -q` | ❌ Wave 0 |
| (DASH-03 partial) | `GET /api/forks` returns paginated results with offset/limit | unit | `pytest tests/test_forks.py -x -q` | ❌ Wave 0 |
| (DASH-01 partial) | `GET /api/blocks` returns recent blocks, both canonical and orphaned | unit | `pytest tests/test_blocks.py -x -q` | ❌ Wave 0 |

### Testing SSE Endpoints

FastAPI's `TestClient` (from `starlette.testclient`) supports streaming responses but does not truly test long-lived SSE connections. For this phase:

- **Unit test `EventBus`** directly — call `notify()` from a thread, assert the queue received the item.
- **Test REST endpoints** with `TestClient` as normal synchronous JSON responses.
- **SSE content-type test:** Use `TestClient` with `stream=True` and check `response.headers["content-type"] == "text/event-stream"`.
- **Integration test for 2-second window:** Spin up `EventBus`, call `notify()` in a thread, assert queue is non-empty within 100ms. The "2 second" SLA is a system-level guarantee, not a unit test requirement.

### Sampling Rate

- **Per task commit:** `pytest tests/test_stats.py tests/test_forks.py tests/test_blocks.py tests/test_events.py -x -q`
- **Per wave merge:** `pytest -x -q` (full suite)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_stats.py` — covers DASH-02 (`/api/stats` endpoint)
- [ ] `tests/test_forks.py` — covers `/api/forks` pagination
- [ ] `tests/test_blocks.py` — covers `/api/blocks` recent blocks
- [ ] `tests/test_events.py` — covers DASH-04 (EventBus + SSE content type)
- [ ] `app/events.py` — EventBus module (does not exist yet)
- [ ] `app/routers/` directory + `__init__.py`

---

## Sources

### Primary (HIGH confidence)

- FastAPI official docs — Server-Sent Events: https://fastapi.tiangolo.com/tutorial/server-sent-events/
- FastAPI release notes — 0.135.0 SSE addition confirmed: https://fastapi.tiangolo.com/release-notes/
- FastAPI PyPI page — version 0.135.1 current, 0.115.6 installed: https://pypi.org/project/fastapi/
- SQLModel official docs — limit/offset pagination: https://sqlmodel.tiangolo.com/tutorial/fastapi/limit-and-offset/
- Python stdlib docs — `asyncio.loop.run_coroutine_threadsafe`: https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.run_coroutine_threadsafe
- Python stdlib docs — `asyncio.Queue` (not thread-safe): https://docs.python.org/3/library/asyncio-queue.html

### Secondary (MEDIUM confidence)

- sse-starlette PyPI (3.3.2, Feb 2026): https://pypi.org/project/sse-starlette/ — confirmed as fallback if FastAPI upgrade is blocked
- deepwiki.com sse-starlette usage guide — thread bridge pattern using `run_coroutine_threadsafe`

### Tertiary (LOW confidence)

- Various Medium articles on SSE + FastAPI — cross-referenced against official docs; patterns consistent

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — FastAPI and SQLModel are already in the project; SSE version requirement verified against official release notes and PyPI
- Architecture: HIGH — per-client queue pattern is the standard approach, verified against official Python asyncio docs and sse-starlette docs
- Pitfalls: HIGH — thread safety issue is documented in Python stdlib; version mismatch verified by checking installed vs required version

**Research date:** 2026-03-09
**Valid until:** 2026-04-09 (FastAPI is actively releasing; SSE API unlikely to change in next 30 days)
