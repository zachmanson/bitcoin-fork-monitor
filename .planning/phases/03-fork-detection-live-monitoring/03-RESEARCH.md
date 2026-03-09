# Phase 3: Fork Detection + Live Monitoring - Research

**Researched:** 2026-03-09
**Domain:** WebSocket real-time monitoring, fork detection logic, Python threading
**Confidence:** HIGH (core patterns), MEDIUM (WebSocket payload field details)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- Record a ForkEvent **immediately** when two blocks collide at the same height — no N-block delay. By the time the WebSocket delivers both competing blocks, the chain has already resolved.
- Use **mempool.space `in_best_chain` field** (from `GET /api/block/{hash}/status`) to determine which block is canonical vs orphaned. Do not guess based on arrival order.
- `resolution_seconds` uses **block header timestamps** (already stored in `Block.timestamp`) — consistent with how backfill-recorded forks work.
- If `in_best_chain` hasn't updated yet when we query: **record the ForkEvent with `resolution_seconds=None`** and schedule a follow-up check after the next block arrives.
- **3 consecutive WebSocket failures** trigger fallback to REST polling.
- REST fallback **polling interval: 30 seconds**.
- While in REST fallback mode, **attempt WebSocket reconnect every 5 minutes**.
- Log **WARNING when falling back** to REST, **INFO when recovering** to WebSocket. Log only on state transitions.
- **`SyncState.last_synced_height` is the source of truth** for gap-fill. Monitor updates it on every new block processed.
- Gap-fill lookback is **uncapped** — always fill from `last_synced_height` to current tip.
- **Full fork detection runs on gap-fill blocks** (same height-collision logic on every fetched block).
- `last_synced_height` is shared between backfill and live monitoring — not a separate field.
- **Second background thread** (`monitor_thread`) added to `app/main.py` lifespan alongside existing `backfill_thread`.
- Monitor thread **waits for `backfill_complete` before subscribing** — polls `SyncState.backfill_complete` on startup.
- **Fork detection logic lives in `app/fork_detector.py`** — pure functions, independently testable.
- **Live monitor lives in `app/monitor.py`** — parallel to `app/backfill.py`.

### Claude's Discretion

- WebSocket library choice (websockets, websocket-client, or httpx WebSocket support)
- Exact mempool.space WebSocket subscription message format and event parsing
- In-memory state representation for tracking "pending" fork events awaiting resolution_seconds
- Exact backoff/retry timing for the 5-minute WebSocket reconnect attempts

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| MONI-01 | System subscribes to new Bitcoin blocks in real-time via mempool.space WebSocket API | WebSocket library (`websockets 16.0` sync client), endpoint `wss://mempool.space/api/v1/ws`, subscription message format documented below |
| MONI-02 | System detects temporary forks when competing blocks appear at the same height and records orphaned blocks | Fork detector pure functions in `app/fork_detector.py`; query existing Block rows by height, call `/api/block/{hash}/status` for `in_best_chain` |
| MONI-03 | System falls back to REST polling if WebSocket is unavailable and performs gap-fill on reconnect to avoid missed forks | REST fallback reuses `fetch_blocks_page` + `fetch_tip_height`; gap-fill from `last_synced_height`; same fork detection runs on gap-fill blocks |
</phase_requirements>

---

## Summary

Phase 3 introduces two new modules: `app/fork_detector.py` (pure detection logic) and `app/monitor.py` (the live monitoring thread). A second background thread is added to the FastAPI lifespan. The monitor waits for backfill completion, then subscribes to new blocks via the mempool.space WebSocket, applying the same fork-detection logic on each incoming block. If the WebSocket fails, the system falls back to REST polling at 30-second intervals and attempts reconnection every 5 minutes.

The key insight for fork detection is that competing blocks for the same height arrive via WebSocket in the same session or shortly after each other (Bitcoin forks are rare and resolve within one or two block times). When a new block arrives, the monitor queries the local Block table for any existing block at that height. If one already exists, a fork is detected: both blocks are stored, `in_best_chain` is resolved via `GET /api/block/{hash}/status`, and a ForkEvent row is written.

The `websockets` library (v16.0) is the correct choice for this project. It provides a synchronous threading client (`websockets.sync.client.connect`) that integrates cleanly with the existing threading-based architecture. This avoids introducing asyncio, which would conflict with the synchronous `Session(engine)` DB pattern already established by the backfill thread.

**Primary recommendation:** Use `websockets.sync.client.connect` with a `while True` reconnect loop, 3-consecutive-failure tracking, and the established `RETRY_DELAYS` backoff pattern from `api_client.py`.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| websockets | 16.0 | WebSocket client (sync/threading) | Active, well-documented, official sync API matches threading model; avoids asyncio conflict |
| httpx | (existing, via api_client.py) | REST fallback + block status queries | Already in project; `fetch_tip_height` and `fetch_blocks_page` reused directly |
| sqlmodel | >=0.0.21 (existing) | DB writes for Block, ForkEvent, SyncState | Already in project |
| threading | stdlib | Background monitor thread | Already established pattern in `app/main.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json | stdlib | WebSocket message parsing | Sending subscription messages and parsing block events |
| time | stdlib | Sleep between REST polls and reconnect attempts | REST fallback polling loop |
| datetime | stdlib | `resolution_seconds` calculation from block timestamps | Already used in backfill |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| websockets (sync) | websocket-client | websocket-client is callback-based (different mental model), requires `run_forever()` blocking; websockets sync is simpler for a linear receive loop |
| websockets (sync) | httpx WebSocket | httpx WebSocket support is asyncio-only; incompatible with sync threading model |
| websockets (sync) | asyncio + websockets | asyncio would require converting DB session usage to async; significant refactor risk |

**Installation:**
```bash
pip install "websockets>=16.0"
```

Add to `pyproject.toml` dependencies:
```toml
"websockets>=16.0",
```

---

## Architecture Patterns

### Recommended Project Structure (new files only)
```
app/
├── fork_detector.py     # Pure functions: detect_fork(), write_fork_event(), resolve_fork_event()
├── monitor.py           # Live monitor thread: run_monitor(), _do_monitor(), WebSocket + REST fallback
└── main.py              # Extended: monitor_thread alongside backfill_thread in lifespan
```

### Pattern 1: Synchronous WebSocket Receive Loop
**What:** Use `websockets.sync.client.connect` in a `while True` loop. On `ConnectionClosed` or error, increment a failure counter. At 3 consecutive failures, switch to REST fallback mode.
**When to use:** Whenever the monitor is in WebSocket mode (the default).

```python
# Source: websockets 16.0 docs (https://websockets.readthedocs.io/en/stable/reference/sync/client.html)
import json
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed

WS_URL = "wss://mempool.space/api/v1/ws"
SUBSCRIBE_MSG = json.dumps({"action": "want", "data": ["blocks"]})

def _ws_loop(on_block):
    """Connect to mempool.space WebSocket and yield block events.

    Calls on_block(block_data) for each incoming block.
    Raises ConnectionClosed on disconnect — caller manages retry.
    """
    with connect(WS_URL, open_timeout=30, ping_interval=30, ping_timeout=10) as ws:
        ws.send(SUBSCRIBE_MSG)
        for raw in ws:
            msg = json.loads(raw)
            if "block" in msg:
                on_block(msg["block"])
```

### Pattern 2: Fork Detection — Height Collision Check
**What:** On receiving a new block, query the Block table for any existing block at the same height. If found, two blocks exist at the same height — that's a fork. Use `in_best_chain` from the REST status endpoint to determine which is canonical.
**When to use:** Called on every block processed by the monitor (both WebSocket and gap-fill paths).

```python
# app/fork_detector.py — pure function, independently testable
def detect_and_record_fork(session: Session, new_block_hash: str, new_block_height: int,
                            new_block_ts: datetime) -> bool:
    """
    Check if a fork exists at new_block_height and record it if so.

    A fork exists when there is already a Block row at this height with a
    different hash. The new block may be canonical or orphaned — we query
    the /api/block/{hash}/status endpoint to determine which is which.

    Returns True if a fork was recorded, False otherwise.
    """
    existing = session.exec(
        select(Block).where(Block.height == new_block_height)
                     .where(Block.hash != new_block_hash)
    ).first()

    if existing is None:
        return False  # no fork

    # Query /api/block/{hash}/status for in_best_chain
    # ... (fetch_block_status called for both hashes)
    # Record ForkEvent with canonical_hash, orphaned_hash, resolution_seconds
    ...
```

### Pattern 3: REST Fallback and Gap-Fill
**What:** When WebSocket is unavailable, poll `fetch_tip_height()` every 30 seconds and call `fetch_blocks_page()` from `last_synced_height` to tip. Apply the same fork detection on each fetched block. This is structurally identical to how backfill walks pages — reuse the same logic.
**When to use:** After 3 consecutive WebSocket failures, and during reconnect on any WebSocket session.

```python
# REST fallback — reuses existing api_client functions
def _rest_poll_loop(session, state, on_block):
    tip = fetch_tip_height()
    current = state.last_synced_height
    while current <= tip:
        page_top = current + 14
        blocks = fetch_blocks_page(page_top)
        for block_data in sorted(blocks, key=lambda b: b["height"]):
            if block_data["height"] >= current:
                on_block(block_data)
        current += 15
        time.sleep(0.5)  # same throttle as backfill
```

### Pattern 4: Pending Fork Resolution
**What:** When `in_best_chain` hasn't flipped yet (both blocks appear canonical), record the ForkEvent with `resolution_seconds=None`. Track these pending events in a simple in-memory list. On the next block processed, retry resolution for any pending events.
**When to use:** Rare edge case within seconds of a fork.

```python
# In-memory tracking — simple list is sufficient (forks are rare)
# Structure: list of dicts with block hashes that need resolution_seconds filled in
_pending_resolutions: list[dict] = []
# e.g., {"fork_event_id": 42, "hash_a": "abc...", "hash_b": "def...", "ts_a": ..., "ts_b": ...}
```

### Anti-Patterns to Avoid
- **Sharing sessions across threads:** The monitor thread MUST create its own `Session(engine)`. Never pass a session from the FastAPI request scope or the backfill thread.
- **Guessing canonical by arrival order:** Arrival order over WebSocket is not deterministic. Always use `in_best_chain` from the status endpoint.
- **Introducing asyncio for WebSocket:** `websockets.sync.client` exists precisely to avoid this. Using asyncio would require rewriting the DB session pattern.
- **Logging on every poll:** Only log on state transitions (WebSocket → REST fallback, REST fallback → WebSocket recovered). Not on every 30-second poll.
- **Writing ForkEvent without checking for duplicate:** The monitor may re-process the same height during gap-fill after reconnect. Check for existing ForkEvent at (height, canonical_hash, orphaned_hash) before inserting.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WebSocket framing and ping/pong keepalive | Custom socket wrapper | `websockets.sync.client.connect` with `ping_interval=30` | RFC 6455 compliant; handles fragmented frames, masking, keepalive automatically |
| JSON send/receive with proper encoding | Custom serializer | `json.dumps` / `json.loads` | Trivial; no hand-rolling needed |
| HTTP retries for block status fetch | Custom retry loop | Existing `fetch_blocks_page` pattern or a new `fetch_block_status(hash)` function using the same `RETRY_DELAYS` loop | The retry logic in `api_client.py` is already tested and handles 429/5xx correctly |

**Key insight:** The block status endpoint (`GET /api/block/{hash}/status`) needs a new thin function in `api_client.py` — not a hand-rolled retry, but applying the same `RETRY_DELAYS` pattern already established.

---

## Common Pitfalls

### Pitfall 1: WebSocket Block Payload Does Not Include `in_best_chain`
**What goes wrong:** Developer assumes the WebSocket block event has `in_best_chain` and uses it directly. It doesn't — that field is only on the `GET /api/block/{hash}/status` REST endpoint.
**Why it happens:** The REST `/api/v1/blocks` response and WebSocket block payload are structurally similar (same `id`, `height`, `timestamp`, `extras` fields) but neither includes `in_best_chain`. The status is on a separate subresource.
**How to avoid:** After detecting a height collision (two blocks at same height in DB), make a separate `GET /api/block/{hash}/status` call for each competing hash to get `in_best_chain`.
**Warning signs:** Assuming `block_data["in_best_chain"]` exists causes a `KeyError` on first fork event.

### Pitfall 2: WebSocket Messages Before Subscription Confirmation
**What goes wrong:** The WebSocket connection is established but no blocks arrive because the subscription message was never sent (or sent too early before the server is ready).
**Why it happens:** mempool.space requires an explicit subscription message `{"action": "want", "data": ["blocks"]}` after connecting. The server doesn't push blocks by default.
**How to avoid:** Send the subscription message immediately after `connect()`, before entering the receive loop. The server may send a "connection-established" ping frame first — handle or ignore it.
**Warning signs:** Connected but no messages after 10+ minutes (Bitcoin produces a block ~every 10 minutes).

### Pitfall 3: Gap-Fill Duplicates ForkEvent Rows
**What goes wrong:** Monitor disconnects at height 900, reconnects at 905. Gap-fill fetches heights 900-905. If a fork was detected live at 901 and also found in gap-fill, two ForkEvent rows are written for the same fork.
**Why it happens:** `_process_block` in backfill always writes a ForkEvent for any orphan. If the same orphan appears twice (live + gap-fill), two rows are inserted.
**How to avoid:** In `fork_detector.py`, check if a ForkEvent already exists at (height, canonical_hash, orphaned_hash) before inserting. Make ForkEvent creation idempotent.
**Warning signs:** Duplicate ForkEvent rows with the same height and hashes.

### Pitfall 4: Monitor Thread Starts Before Backfill Completes
**What goes wrong:** Monitor subscribes to WebSocket and processes height 900, but backfill is still writing heights 895-900. Two threads write Block rows at the same heights concurrently.
**Why it happens:** The monitor launch doesn't wait for `SyncState.backfill_complete`.
**How to avoid:** At monitor startup, poll `SyncState.backfill_complete` in a short sleep loop before subscribing. This is already a locked decision in CONTEXT.md.
**Warning signs:** SQLite `UNIQUE constraint failed: block.hash` errors on Block inserts at the transition zone.

### Pitfall 5: `resolution_seconds` Sign Error
**What goes wrong:** `resolution_seconds` comes out negative, or is computed using wall-clock `datetime.utcnow()` instead of block header timestamps.
**Why it happens:** Block timestamps are miner-set Unix integers. The orphaned block sometimes has a slightly earlier or later timestamp than the canonical block. Using `abs()` is safer than assuming which is larger.
**How to avoid:** Use `abs((canonical_ts - orphaned_ts).total_seconds())` where both are `Block.timestamp` values (already stored as naive UTC datetimes in the Block table). Matches how backfill computes resolution time.
**Warning signs:** Negative `resolution_seconds` values in the ForkEvent table.

### Pitfall 6: WebSocket Reconnect Spam
**What goes wrong:** On network failure, reconnect attempts happen in a tight loop with no backoff, causing excessive connection attempts to mempool.space.
**Why it happens:** A naive `while True: connect()` without sleep.
**How to avoid:** Apply the same `RETRY_DELAYS = [1, 2, 4, 8, 16]` backoff pattern from `api_client.py` for the first few attempts. After 3 consecutive failures, switch to REST fallback and try WebSocket reconnect every 5 minutes — matching the CONTEXT.md decision.
**Warning signs:** Logs showing rapid "Connection failed" messages.

---

## Code Examples

Verified patterns from official sources and existing codebase:

### WebSocket Subscribe + Receive Loop (websockets 16.0 sync)
```python
# Source: https://websockets.readthedocs.io/en/stable/reference/sync/client.html
import json
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed

WS_URL = "wss://mempool.space/api/v1/ws"

def _connect_and_stream(on_block_fn):
    """
    Connect to mempool.space WebSocket, subscribe to blocks, and call
    on_block_fn(block_data: dict) for each new block event.

    Raises ConnectionClosed on disconnect; caller must handle retry.
    """
    with connect(WS_URL, open_timeout=30, ping_interval=30, ping_timeout=10) as ws:
        # mempool.space requires explicit subscription after connecting.
        # Without this message, no block events are pushed.
        ws.send(json.dumps({"action": "want", "data": ["blocks"]}))

        for raw_message in ws:
            msg = json.loads(raw_message)
            # Block events arrive as {"block": { ...block_data... }}
            if "block" in msg:
                on_block_fn(msg["block"])
```

### Block Status Check (new function in api_client.py)
```python
# New function following the established RETRY_DELAYS pattern
def fetch_block_status(block_hash: str) -> dict:
    """
    Fetch the canonical status of a block from mempool.space.

    Endpoint: GET /api/block/{hash}/status
    Returns: {"in_best_chain": bool, "next_best": str | None}

    Uses the same retry/backoff pattern as fetch_blocks_page.

    Args:
        block_hash: The block's SHA-256d hash (hex string).

    Returns:
        A dict with 'in_best_chain' (bool) and optionally 'next_best' (str).

    Raises:
        RuntimeError: If all retry attempts are exhausted.
    """
    url = f"{BASE_URL}/api/block/{block_hash}/status"
    with httpx.Client(timeout=30.0) as client:
        for attempt, delay in enumerate(RETRY_DELAYS):
            is_last_attempt = attempt == len(RETRY_DELAYS) - 1
            try:
                resp = client.get(url)
                if resp.status_code in _RETRYABLE_STATUS_CODES:
                    logger.warning(
                        "Retryable HTTP %d fetching block status %s (attempt %d/%d).",
                        resp.status_code, block_hash[:8], attempt + 1, len(RETRY_DELAYS),
                    )
                    time.sleep(delay)
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.RequestError as exc:
                logger.warning(
                    "Network error fetching block status %s (attempt %d/%d): %s",
                    block_hash[:8], attempt + 1, len(RETRY_DELAYS), exc,
                )
                if not is_last_attempt:
                    time.sleep(delay)
                continue
    raise RuntimeError(f"All retries exhausted fetching block status for {block_hash}")
```

### Fork Detection Pure Function
```python
# app/fork_detector.py — pure, independently testable
from datetime import datetime
from typing import Optional
from sqlmodel import Session, select
from app.models import Block, ForkEvent

def detect_fork_at_height(session: Session, height: int, new_hash: str) -> Optional[Block]:
    """
    Check if a competing block already exists at this height.

    Returns the existing Block if a fork is detected, None otherwise.
    A fork exists when there is already a Block at height with a different hash.
    """
    return session.exec(
        select(Block).where(Block.height == height)
                     .where(Block.hash != new_hash)
    ).first()


def write_fork_event(
    session: Session,
    height: int,
    canonical_hash: str,
    orphaned_hash: str,
    canonical_ts: datetime,
    orphaned_ts: datetime,
) -> ForkEvent:
    """
    Record a ForkEvent for a detected fork. Idempotent — skips insert if
    a ForkEvent already exists for this (height, canonical_hash, orphaned_hash).

    resolution_seconds is the absolute difference between block header timestamps.
    """
    # Idempotency check: don't duplicate if gap-fill re-processes the same fork
    existing = session.exec(
        select(ForkEvent)
        .where(ForkEvent.height == height)
        .where(ForkEvent.canonical_hash == canonical_hash)
        .where(ForkEvent.orphaned_hash == orphaned_hash)
    ).first()
    if existing is not None:
        return existing

    resolution_seconds = abs((canonical_ts - orphaned_ts).total_seconds())

    event = ForkEvent(
        height=height,
        canonical_hash=canonical_hash,
        orphaned_hash=orphaned_hash,
        resolution_seconds=resolution_seconds,
    )
    session.add(event)
    session.commit()
    return event
```

### Monitor Thread Startup Gate
```python
# app/monitor.py — wait for backfill before subscribing
import time
from sqlmodel import Session, select
from app.database import engine
from app.models import SyncState

BACKFILL_POLL_INTERVAL_SECONDS = 5

def _wait_for_backfill() -> None:
    """
    Block until SyncState.backfill_complete is True.

    Polls the database every 5 seconds. Logs at INFO on first check and
    when backfill completes, so long waits are observable.
    """
    logger.info("Monitor waiting for backfill to complete...")
    while True:
        with Session(engine) as session:
            state = session.exec(select(SyncState)).first()
            if state is not None and state.backfill_complete:
                logger.info("Backfill complete — starting live monitor")
                return
        time.sleep(BACKFILL_POLL_INTERVAL_SECONDS)
```

### lifespan Extension in main.py
```python
# app/main.py — add monitor_thread alongside backfill_thread
from app.monitor import run_monitor

# Inside lifespan, after backfill_thread launch:
logger.info("Starting monitor thread (waits for backfill internally)")
monitor_thread = threading.Thread(
    target=run_monitor,
    daemon=True,
    name="monitor",
)
monitor_thread.start()

# Inside shutdown (after yield):
if monitor_thread is not None and monitor_thread.is_alive():
    logger.info("Waiting for monitor thread to finish (timeout=5s)...")
    monitor_thread.join(timeout=5.0)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| asyncio-based WebSocket clients (websockets < 10) | `websockets.sync.client` threading API | websockets 10.0+ (sync added ~2022, stable in 16.0) | No asyncio needed for background thread use cases |
| `@app.on_event("startup")` FastAPI hooks | `@asynccontextmanager lifespan` | FastAPI 0.93+ (2023) | Already used in this project's `main.py` |
| Guessing canonical block by first-seen | `in_best_chain` REST status endpoint | Always available on mempool.space | Correct determination of fork winner without guessing |

**Deprecated/outdated:**
- `websocket-client` library's `run_forever()` + callback model: Still works, but the `websockets.sync.client` pattern is cleaner for a linear receive loop without callbacks.

---

## Open Questions

1. **WebSocket block payload: does it include `extras.orphans`?**
   - What we know: The REST `/api/v1/blocks` response includes `extras.orphans`. The WebSocket block event payload is structurally similar but the exact fields aren't confirmed in official documentation.
   - What's unclear: Whether the WebSocket push includes `extras.orphans` or only the core block header fields.
   - Recommendation: The CONTEXT.md decision resolves this elegantly — fork detection is based on height collision in the database, NOT on `extras.orphans` from the WebSocket payload. When block B arrives at height H where block A already exists, we have a fork. We do NOT rely on `extras.orphans` in the live monitor path. This eliminates the uncertainty entirely.

2. **`in_best_chain` update latency**
   - What we know: The CONTEXT.md decision says: if `in_best_chain` hasn't updated yet, record `ForkEvent.resolution_seconds=None` and retry on next block.
   - What's unclear: How long (in practice) it takes for mempool.space to update `in_best_chain` after a fork resolves. Could be seconds, could be sub-second.
   - Recommendation: Implement the retry-on-next-block mechanism. In the rare case of a pending resolution, a list of `{fork_event_id, hash_a, hash_b}` dicts held in thread-local memory is sufficient. Retry on each subsequent block processed until both return a clear `in_best_chain` value.

3. **WebSocket "connection established" initial message**
   - What we know: Some WebSocket APIs send an initial handshake/confirmation message before events start.
   - What's unclear: Whether mempool.space sends a "connection established" or "pong" message before the first block event.
   - Recommendation: The receive loop should silently ignore messages that don't contain a `"block"` key (`if "block" in msg`). This is a safe default regardless.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `pytest tests/test_fork_detector.py -x -q` |
| Full suite command | `pytest -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MONI-01 | WebSocket subscribe sends `{"action": "want", "data": ["blocks"]}` and receives block events | unit (mock WS) | `pytest tests/test_monitor.py::TestWebSocketSubscribe -x -q` | ❌ Wave 0 |
| MONI-01 | Monitor thread waits for backfill_complete before subscribing | unit | `pytest tests/test_monitor.py::TestBackfillGate -x -q` | ❌ Wave 0 |
| MONI-02 | Fork detected when two blocks arrive at same height | unit | `pytest tests/test_fork_detector.py::TestDetectFork -x -q` | ❌ Wave 0 |
| MONI-02 | ForkEvent written with correct canonical/orphaned hashes and resolution_seconds | unit | `pytest tests/test_fork_detector.py::TestWriteForkEvent -x -q` | ❌ Wave 0 |
| MONI-02 | ForkEvent creation is idempotent (no duplicate rows on re-process) | unit | `pytest tests/test_fork_detector.py::TestForkIdempotency -x -q` | ❌ Wave 0 |
| MONI-02 | Block with `in_best_chain=False` is marked `is_canonical=False` | unit | `pytest tests/test_fork_detector.py::TestOrphanFlagged -x -q` | ❌ Wave 0 |
| MONI-02 | Pending fork (in_best_chain not yet resolved) records `resolution_seconds=None` | unit | `pytest tests/test_fork_detector.py::TestPendingResolution -x -q` | ❌ Wave 0 |
| MONI-03 | After 3 WS failures, monitor switches to REST fallback (WARNING logged) | unit (mock) | `pytest tests/test_monitor.py::TestRestFallback -x -q` | ❌ Wave 0 |
| MONI-03 | Gap-fill fetches all blocks between last_synced_height and tip | unit | `pytest tests/test_monitor.py::TestGapFill -x -q` | ❌ Wave 0 |
| MONI-03 | Gap-fill runs full fork detection (same logic as live path) | unit | `pytest tests/test_monitor.py::TestGapFillForkDetection -x -q` | ❌ Wave 0 |
| MONI-03 | last_synced_height updated after every processed block | unit | `pytest tests/test_monitor.py::TestLastSyncedHeight -x -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_fork_detector.py -x -q`
- **Per wave merge:** `pytest -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_fork_detector.py` — covers MONI-02 (pure function tests, no WS mocking needed)
- [ ] `tests/test_monitor.py` — covers MONI-01, MONI-03 (mock `websockets.sync.client.connect` and `fetch_blocks_page`)

*(Existing `tests/conftest.py` with `engine_fixture` and `session_fixture` covers all DB setup needs — no changes required.)*

---

## Sources

### Primary (HIGH confidence)
- [websockets 16.0 sync client docs](https://websockets.readthedocs.io/en/stable/reference/sync/client.html) — connect(), send(), recv(), ConnectionClosed exception, ping parameters
- [websockets PyPI](https://pypi.org/project/websockets/) — version 16.0, Python >=3.10 support confirmed
- Existing codebase (`app/backfill.py`, `app/api_client.py`, `app/models.py`, `app/main.py`) — HIGH confidence on all patterns, directly read

### Secondary (MEDIUM confidence)
- [mempool.space WebSocket docs](https://mempool.space/docs/api/websocket) — WebSocket endpoint `wss://mempool.space/api/v1/ws`, subscription format `{"action": "want", "data": ["blocks"]}`, block event key `"block"` — confirmed by multiple sources
- [mempool.space REST docs](https://mempool.space/docs/api/rest) — `GET /api/block/{hash}/status` returns `{"in_best_chain": bool, "next_best": str}` — confirmed by mempool.js README and multiple sources
- [mempool.js README](https://github.com/mempool/mempool.js/blob/main/README-bitcoin.md) — confirms block status endpoint fields

### Tertiary (LOW confidence)
- WebSocket block event payload exact field list (especially whether `extras.orphans` is present in live WS events) — unverified, but resolved by design: fork detection uses DB height collision, not WS payload orphan list

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — websockets 16.0 sync client confirmed, all other dependencies already in project
- Architecture patterns: HIGH — derived directly from existing backfill.py and main.py patterns
- WebSocket subscription format: MEDIUM — confirmed across multiple secondary sources, not verified against live connection
- `in_best_chain` on status endpoint: MEDIUM — confirmed by mempool.js README, multiple sources consistent
- WebSocket block payload field list: LOW — not fully documented; mitigated by design decision to use DB height collision for fork detection
- Pitfalls: HIGH — derived from code analysis and established patterns

**Research date:** 2026-03-09
**Valid until:** 2026-06-09 (stable APIs, 90-day estimate)
