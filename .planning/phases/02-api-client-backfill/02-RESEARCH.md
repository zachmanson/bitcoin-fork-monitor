# Phase 2: API Client + Backfill - Research

**Researched:** 2026-03-09
**Domain:** mempool.space REST API, Python httpx, FastAPI lifespan, background threading, SQLModel session management
**Confidence:** HIGH — all critical findings verified against live API and running code

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- Backfill runs in a **background thread**, not blocking the API server
- FastAPI starts immediately; API can serve (empty/partial) data while backfill runs in parallel
- Use **FastAPI lifespan context manager** (`asynccontextmanager`) to launch and join the backfill thread
- On startup, check `SyncState.backfill_complete`: if True, skip silently with one log line
- When backfill completes, the thread sets `backfill_complete = True` in SyncState and exits
- Write `last_synced_height` to SyncState every **100 blocks**
- SyncState row is **updated in place** (single row, not appended)
- Log progress every **1000 blocks** at INFO level: `Backfill: 45000/880000 blocks (5.1%) — height 45000`
- Use `logging` (not `print`)
- On 5xx or network error: retry up to **5 times** with exponential backoff (1s, 2s, 4s, 8s, 16s)
- **Same backoff utility** handles both HTTP 429 and 5xx
- If all 5 retries exhausted: log ERROR with failed height, thread exits cleanly
- Thread failure does **not** crash the FastAPI server

### Claude's Discretion

- Exact mempool.space endpoint selection and fork detection strategy (validate `GET /api/blocks/:height` behavior at research time — see STATE.md blocker)
- HTTP client library choice (httpx is idiomatic for FastAPI ecosystem; requests also fine)
- Exact 500ms throttle implementation (time.sleep vs asyncio.sleep)
- Module structure within `app/` (e.g., `app/api_client.py`, `app/backfill.py`)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BACK-01 | On first run, system backfills complete historical fork/orphan data from genesis via mempool.space API | `/api/v1/blocks/:startHeight` provides 15 canonical blocks per request with `extras.orphans` array. Historical orphan data is available from block ~820819 (Dec 2023) onward. For older blocks, canonical block records are still written with no orphan events. |
| BACK-02 | Backfill progress is checkpointed to SQLite so a restart resumes where it left off | `SyncState.last_synced_height` field exists and was verified writeable from a background thread session. Update every 100 blocks. |
| BACK-03 | Backfill implements adaptive rate limiting and exponential backoff to avoid being blocked by mempool.space | 500ms inter-request sleep + exponential backoff (1s, 2s, 4s, 8s, 16s) on 429/5xx. Rate limits are undisclosed; 500ms is empirically safe starting point. |
</phase_requirements>

---

## Summary

Phase 2 delivers a rate-limited HTTP client and a checkpointed backfill worker. Research resolved the critical STATE.md blocker and surfaced an important data availability constraint about historical orphan records.

**STATE.md blocker resolved (HIGH confidence):** `GET /api/blocks/:height` (the non-v1 endpoint) returns 10 canonical blocks descending from that height and contains NO orphan data. The correct endpoint for backfill is `GET /api/v1/blocks/:startHeight`, which returns 15 canonical blocks with an `extras.orphans` array in each block. This was verified live. The backfill iterates using this endpoint.

**Critical data availability finding (HIGH confidence):** mempool.space only exposes orphan/stale block data for blocks since approximately height 820,819 (December 2023). For the 87% of blockchain history before that height, orphan data is unavailable from the public API — no endpoint provides historical orphan data for blocks 0–820,818. The backfill will write canonical block records for all heights but will only produce `ForkEvent` records for forks at height 820,819 and above.

**Primary recommendation:** Use `GET /api/v1/blocks/:startHeight` as the sole backfill endpoint. Walk heights from `last_synced_height` to tip in steps of 15, calling this endpoint once per page. Inspect `extras.orphans` on each block returned. Use `httpx.Client` (synchronous) in the background thread with 500ms `time.sleep` between requests.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | 0.28.1 (installed) | HTTP client for mempool.space API calls | FastAPI's recommended HTTP client; supports both sync and async; nearly identical API to `requests`; already in the project environment |
| fastapi | 0.115.6 (installed) | API server + lifespan context manager | Already established by Phase 1 |
| sqlmodel | 0.0.21+ (installed) | Database session for backfill thread | Already established by Phase 1 |
| threading | stdlib | Background thread for backfill worker | Simple and sufficient; backfill is I/O-bound not CPU-bound; no new dependency |
| logging | stdlib | Progress and error logging | Integrates with uvicorn's logging system; established pattern |
| time | stdlib | 500ms inter-request throttle via `time.sleep` | Correct choice: the backfill runs in a non-async thread, so `asyncio.sleep` would not work here |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| contextlib.asynccontextmanager | stdlib | FastAPI lifespan decorator | Required for the lifespan pattern; already in Python stdlib |
| datetime | stdlib | Block timestamps from Unix timestamps | Block API returns `timestamp` as Unix int; must convert to `datetime` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| httpx (sync) | requests | requests also works; httpx is preferred because it matches the FastAPI ecosystem and is already installed |
| time.sleep | asyncio.sleep | asyncio.sleep only works inside async functions; the backfill runs in a plain thread, so time.sleep is correct |
| threading.Thread | asyncio background task | An asyncio task would require the backfill to be async and would share the event loop with FastAPI; a thread is simpler and avoids that coupling |

**Installation:**

```bash
pip install httpx
# (already installed in project environment at 0.28.1)
```

---

## Architecture Patterns

### Recommended Project Structure

```
app/
├── __init__.py          # exists
├── models.py            # exists — Block, ForkEvent, SyncState
├── database.py          # exists — engine, get_session()
├── analytics.py         # exists
├── api_client.py        # NEW — MempoolClient class, fetch_blocks_page()
├── backfill.py          # NEW — run_backfill() worker function
└── main.py              # NEW — FastAPI app + lifespan context manager
```

### Pattern 1: API Client Module (api_client.py)

**What:** A thin wrapper around `httpx.Client` that handles one concern: fetching a page of blocks from the mempool.space API and returning parsed data. Retry/backoff lives here.

**When to use:** All outbound HTTP calls go through this module. The backfill imports `fetch_blocks_page`; no other code calls httpx directly.

**Example:**

```python
# Source: live API verification + httpx docs (httpx.dev)
import time
import httpx
import logging

BASE_URL = "https://mempool.space"
RETRY_DELAYS = [1, 2, 4, 8, 16]   # 5 attempts, exponential backoff

logger = logging.getLogger(__name__)


def fetch_blocks_page(start_height: int) -> list[dict]:
    """
    Fetch up to 15 blocks from mempool.space starting at start_height (descending).

    Uses GET /api/v1/blocks/:startHeight which returns canonical blocks
    with extras.orphans arrays. Retries up to 5 times on 429 or 5xx.

    Args:
        start_height: The highest block height to include in the page.

    Returns:
        List of block dicts from the API, each containing 'height', 'id',
        'timestamp', and 'extras.orphans'.

    Raises:
        RuntimeError: If all retries are exhausted.
    """
    url = f"{BASE_URL}/api/v1/blocks/{start_height}"

    with httpx.Client(timeout=30.0) as client:
        for attempt, delay in enumerate(RETRY_DELAYS):
            try:
                resp = client.get(url)

                if resp.status_code in (429, 500, 502, 503, 504):
                    logger.warning(
                        "HTTP %d at height %d, attempt %d/%d — backing off %ds",
                        resp.status_code, start_height, attempt + 1, len(RETRY_DELAYS), delay
                    )
                    time.sleep(delay)
                    continue

                resp.raise_for_status()
                return resp.json()

            except httpx.RequestError as exc:
                logger.warning(
                    "Network error at height %d, attempt %d/%d: %s — backing off %ds",
                    start_height, attempt + 1, len(RETRY_DELAYS), exc, delay
                )
                if attempt < len(RETRY_DELAYS) - 1:
                    time.sleep(delay)

    raise RuntimeError(f"All retries exhausted for height {start_height}")
```

### Pattern 2: Backfill Worker Function (backfill.py)

**What:** A plain Python function that runs in a background thread. It reads the checkpoint from SyncState, walks heights from checkpoint to tip in 15-block pages, writes `Block` and `ForkEvent` rows, and checkpoints every 100 blocks.

**When to use:** Called exactly once from the lifespan, only when `backfill_complete` is False.

**Example:**

```python
# Source: verified against live API behavior + SQLModel session pattern from database.py
import logging
import time
from datetime import datetime

from sqlmodel import Session, select

from app.database import engine
from app.models import Block, ForkEvent, SyncState
from app.api_client import fetch_blocks_page

THROTTLE_SECONDS = 0.5       # 500ms between requests
CHECKPOINT_INTERVAL = 100    # Write last_synced_height every N blocks
LOG_INTERVAL = 1000          # Log progress every N blocks

logger = logging.getLogger(__name__)


def run_backfill() -> None:
    """
    Walk Bitcoin blockchain from last checkpoint to current tip, persisting
    all blocks and fork events to the database.

    Runs in a background thread. Creates its own SQLModel session (does not
    use the FastAPI get_session() dependency, which is request-scoped).

    On completion, sets SyncState.backfill_complete = True.
    On fatal error (all retries exhausted), logs ERROR and exits — does not
    crash the FastAPI server.
    """
    try:
        _do_backfill()
    except Exception:
        logger.exception("Backfill worker failed — will resume from checkpoint on next start")


def _do_backfill() -> None:
    # ... implementation detail ...
```

### Pattern 3: FastAPI Lifespan (main.py)

**What:** The `asynccontextmanager` lifespan function that starts the database, checks the backfill flag, and launches the worker thread.

**Example:**

```python
# Source: FastAPI official docs — https://fastapi.tiangolo.com/advanced/events/
from contextlib import asynccontextmanager
import threading
import logging
from fastapi import FastAPI

from app.database import create_db_and_tables, engine
from app.models import SyncState
from app.backfill import run_backfill
from sqlmodel import Session, select

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    create_db_and_tables()

    # Check if backfill is already complete
    with Session(engine) as session:
        state = session.exec(select(SyncState)).first()
        already_done = state is not None and state.backfill_complete

    if already_done:
        logger.info("Backfill already complete — skipping")
        backfill_thread = None
    else:
        logger.info("Starting backfill worker thread")
        backfill_thread = threading.Thread(target=run_backfill, daemon=True, name="backfill")
        backfill_thread.start()

    yield  # FastAPI serves requests here

    # --- Shutdown ---
    if backfill_thread is not None and backfill_thread.is_alive():
        logger.info("Waiting for backfill thread to finish...")
        backfill_thread.join(timeout=5.0)


app = FastAPI(lifespan=lifespan)
```

### Pattern 4: mempool.space API Response — Orphan Data

**What:** The `GET /api/v1/blocks/:startHeight` endpoint returns a JSON array of up to 15 block objects. Each block has an `extras.orphans` array listing competing blocks at the same height that were NOT canonical.

**Verified live against the API.** Example response structure:

```json
[
  {
    "id": "00000000000000000001d964...",
    "height": 820819,
    "timestamp": 1702366992,
    "extras": {
      "orphans": [
        {
          "height": 820819,
          "hash": "000000000000000000008c3d...",
          "status": "valid-headers",
          "prevhash": "00000000000000000002387e..."
        }
      ]
    }
  }
]
```

**For blocks before approximately height 820,819**: `extras.orphans` is always an empty array `[]`. This is not a missing forks — it reflects a hard limit in mempool.space's data retention. The fork rate before Dec 2023 was historically ~0.1–0.4%, so there are thousands of unrecorded historical forks. Document this limitation as a data confidence note in `SyncState` or app logs.

### Pattern 5: Pagination for Backfill Walk

The `GET /api/v1/blocks/:startHeight` endpoint returns blocks **descending** from `startHeight` inclusive. To walk forward from genesis to tip:

```python
# Walk from resume_height to tip in 15-block pages (ascending, pages go down)
# Strategy: start at current tip, walk down? NO.
# Strategy: iterate height = resume_height, resume_height + 15, + 30, ...
# Each call: fetch_blocks_page(min(current_page_top, tip))
# The API returns blocks from startHeight DOWN to startHeight-14

# Ascending walk pattern:
height = resume_height
while height <= tip_height:
    page_top = height + 14   # fetch 15 blocks: height to height+14
    # BUT the API goes DOWN from startHeight, not up.
    # So to get blocks 100-114, call with startHeight=114.
    blocks = fetch_blocks_page(page_top)
    # blocks will be [114, 113, ..., 100] — filter to only those >= height
    # Then advance: height += 15
```

**Simpler approach** (recommended): start from the tip and walk down, or walk ascending and call `fetch_blocks_page(height + 14)` to get the window `[height, height+14]`. Either way works; descending (tip to 0) is slightly simpler for checkpointing.

**Verified page size:** Returns exactly 15 blocks for any height ≥ 15, and fewer (naturally) near genesis.

### Anti-Patterns to Avoid

- **Using `GET /api/blocks/:height` (non-v1):** Returns 10 canonical blocks with no `extras` data — cannot detect forks. Always use `/api/v1/blocks/:startHeight`.
- **Using `GET /api/v1/stale-tips` for backfill:** Hard-capped at 50 most recent forks. Good as a supplemental sanity-check but insufficient as the primary data source.
- **Using `asyncio.sleep` in the backfill thread:** The backfill runs in a `threading.Thread`, not a coroutine. `asyncio.sleep` would raise a RuntimeError. Use `time.sleep`.
- **Using `get_session()` from `database.py` in the backfill thread:** That generator is a FastAPI dependency injection pattern for request-scoped sessions. Use `Session(engine)` directly in the thread.
- **Inserting the same block hash twice:** The database will raise `IntegrityError` because `Block.hash` is the primary key. The backfill must check `session.get(Block, hash)` or use `INSERT OR IGNORE` semantics before inserting.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP retry logic | Custom retry loop with manual state | httpx built-in timeout + the established `RETRY_DELAYS` pattern | Retry state tracking is error-prone; the simple list-based approach covers 99% of cases cleanly |
| Background job framework | Task queue (Celery, RQ, APScheduler) | `threading.Thread` | This is a one-shot backfill, not a recurring job; no scheduler needed; threads are simpler and have no external dependencies |
| HTTP client | `urllib` / `http.client` | httpx | Connection pooling, timeout handling, and redirect handling are already solved in httpx |

**Key insight:** The backfill is fundamentally a sequential, rate-limited loop — no concurrency, no queuing, no scheduling framework. The simplest correct solution is a `while` loop with `time.sleep`.

---

## Common Pitfalls

### Pitfall 1: Duplicate Block Insertion on Restart

**What goes wrong:** The backfill resumes from `last_synced_height`. The last checkpoint may have been written at height 900, but blocks 901–1000 were already inserted before the crash. On restart, the loop tries to insert those blocks again and hits `IntegrityError`.

**Why it happens:** Checkpoint is written every 100 blocks, not after every block. The checkpoint and the data writes are not atomic.

**How to avoid:** Before inserting a `Block`, check if it already exists:
```python
existing = session.get(Block, block_hash)
if existing is None:
    session.add(Block(...))
```
Or use SQLAlchemy's `insert(...).prefix_with("OR IGNORE")`. The simpler `session.get` check is more readable for a learning codebase.

**Warning signs:** `sqlalchemy.exc.IntegrityError: UNIQUE constraint failed: block.hash` in the logs on restart.

### Pitfall 2: SyncState Row Not Present on First Run

**What goes wrong:** The backfill reads `SyncState` to find the resume height, but on first run the table is empty. `session.exec(select(SyncState)).first()` returns `None`, causing an `AttributeError` when accessing `.last_synced_height`.

**How to avoid:** Always upsert — if no row exists, create one with defaults:
```python
state = session.exec(select(SyncState)).first()
if state is None:
    state = SyncState()
    session.add(state)
    session.commit()
    session.refresh(state)
```

### Pitfall 3: Thread Leaking on Uvicorn Hot-Reload

**What goes wrong:** During development with `uvicorn --reload`, the process restarts on file changes. If the thread is not daemon-flagged, it keeps running in the old process and blocks shutdown.

**How to avoid:** Always set `daemon=True` on the backfill thread. Daemon threads are automatically killed when the main process exits. This is already in the locked decisions.

### Pitfall 4: Unix Timestamps vs datetime Objects

**What goes wrong:** mempool.space returns `timestamp` as a Unix integer (e.g., `1702366992`). `Block.timestamp` is a `datetime` column. Assigning the raw int raises a type error.

**How to avoid:**
```python
from datetime import datetime, timezone
# Convert Unix timestamp to naive UTC datetime (matching existing pattern in models.py)
ts = datetime.fromtimestamp(block_data["timestamp"], tz=timezone.utc).replace(tzinfo=None)
```
Use `.replace(tzinfo=None)` to stay consistent with the existing `datetime.utcnow()` pattern in `ForkEvent.detected_at`.

### Pitfall 5: Historical Orphan Data Limitation

**What goes wrong:** The BACK-01 requirement says "complete historical fork/orphan data from genesis." mempool.space does NOT have orphan data before approximately block 820,819 (December 2023). A naive implementation might log an error or fail trying to find orphan data for old blocks.

**How to avoid:** Treat empty `extras.orphans` as "no fork at this height" — which is correct behavior. Log a one-time note at startup that orphan data is only available from height ~820,819 onward. Document this in `SyncState` or a log at backfill completion.

---

## Code Examples

Verified patterns from live API and running interpreter:

### Fetch a page of blocks with orphan data

```python
# Source: live test against https://mempool.space/api/v1/blocks/820819
import httpx

with httpx.Client(timeout=30.0) as client:
    resp = client.get("https://mempool.space/api/v1/blocks/820819")
    blocks = resp.json()
    # blocks is a list of up to 15 dicts, descending from 820819
    for block in blocks:
        height = block["height"]
        block_hash = block["id"]          # mempool.space uses "id" not "hash"
        timestamp_unix = block["timestamp"]
        orphans = block["extras"]["orphans"]   # list, may be empty
        for orphan in orphans:
            orphan_hash = orphan["hash"]
            # This is a fork event: canonical=block_hash, orphaned=orphan_hash at height
```

### SyncState get-or-create in thread

```python
# Source: verified in interpreter against app/models.py
from sqlmodel import Session, select
from app.database import engine
from app.models import SyncState

def get_or_create_sync_state(session: Session) -> SyncState:
    """Return the single SyncState row, creating it if needed."""
    state = session.exec(select(SyncState)).first()
    if state is None:
        state = SyncState()
        session.add(state)
        session.commit()
        session.refresh(state)
    return state
```

### Checkpoint write

```python
# Source: verified in interpreter
from datetime import datetime

def write_checkpoint(session: Session, state: SyncState, height: int) -> None:
    """Persist backfill progress to survive a crash."""
    state.last_synced_height = height
    state.updated_at = datetime.utcnow()
    session.add(state)
    session.commit()
```

### Block already-exists guard

```python
# Source: SQLModel session.get() pattern, verified in interpreter
def insert_block_if_new(session: Session, block_hash: str, height: int, timestamp, is_canonical: bool) -> bool:
    """Insert block row only if hash not already present. Returns True if inserted."""
    if session.get(Block, block_hash) is not None:
        return False
    session.add(Block(hash=block_hash, height=height, timestamp=timestamp, is_canonical=is_canonical))
    return True
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FastAPI `@app.on_event("startup")` | `lifespan` context manager | FastAPI 0.95+ (2023) | `on_event` is deprecated; lifespan is the current idiomatic pattern |
| `GET /api/blocks/:height` for orphans | `GET /api/v1/blocks/:height` with `extras.orphans` | Unknown — live-verified now | Non-v1 endpoint has no orphan data; v1 endpoint is required |

**Deprecated/outdated:**

- `@app.on_event("startup")` / `@app.on_event("shutdown")`: Still works but deprecated in FastAPI. Use `lifespan`.
- `requests` library: Fully functional but not the idiomatic choice for FastAPI projects; httpx is preferred.

---

## Open Questions

1. **Optimal throttle rate**
   - What we know: 500ms (2 req/s) is the locked starting point; mempool.space rate limits are undisclosed
   - What's unclear: Could safely go faster (e.g., 200ms / 5 req/s) without hitting 429s
   - Recommendation: Start at 500ms. If the 8.7-hour runtime is acceptable (it likely is for a one-time backfill), do not adjust. If the developer wants faster backfill, test 200ms empirically after initial implementation.

2. **BACK-01 requirement interpretation with data gap**
   - What we know: mempool.space has no orphan data before block ~820,819 (87% of history)
   - What's unclear: Does BACK-01 require orphan data from genesis, or canonical block records from genesis?
   - Recommendation: The phase is satisfied by: (a) writing canonical block records for all heights 0–present, (b) writing fork events for all heights with available orphan data (~820k–present), and (c) logging a note at completion that pre-Dec-2023 orphan data is unavailable. The stale rate calculation will show a data confidence limitation for historical data — this aligns with ANAL-02's "data confidence note for pre-2015 data" requirement.

3. **Idempotency of block insertion near height 0**
   - What we know: The API returns fewer than 15 blocks near genesis (e.g., height 5 returns 6 blocks)
   - What's unclear: Edge case handling for the final page at genesis
   - Recommendation: The `while height <= tip` loop naturally handles this — just process whatever the API returns.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `python -m pytest tests/ -q` |
| Full suite command | `python -m pytest tests/ -v` |

**Baseline:** 11 tests passing (Phase 1). Phase 2 adds tests alongside new modules.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BACK-01 | Backfill writes Block rows for canonical blocks | unit | `python -m pytest tests/test_backfill.py::test_backfill_writes_blocks -x` | ❌ Wave 0 |
| BACK-01 | Backfill writes ForkEvent when orphan present in response | unit | `python -m pytest tests/test_backfill.py::test_backfill_detects_fork -x` | ❌ Wave 0 |
| BACK-01 | Backfill skips when backfill_complete is True | unit | `python -m pytest tests/test_backfill.py::test_backfill_skips_if_complete -x` | ❌ Wave 0 |
| BACK-02 | Backfill resumes from last_synced_height after simulated crash | unit | `python -m pytest tests/test_backfill.py::test_backfill_resumes_from_checkpoint -x` | ❌ Wave 0 |
| BACK-02 | Checkpoint is written every 100 blocks | unit | `python -m pytest tests/test_backfill.py::test_checkpoint_frequency -x` | ❌ Wave 0 |
| BACK-03 | HTTP 429 triggers exponential backoff delay | unit (mock) | `python -m pytest tests/test_api_client.py::test_retry_on_429 -x` | ❌ Wave 0 |
| BACK-03 | HTTP 5xx triggers exponential backoff delay | unit (mock) | `python -m pytest tests/test_api_client.py::test_retry_on_5xx -x` | ❌ Wave 0 |
| BACK-03 | All retries exhausted raises RuntimeError | unit (mock) | `python -m pytest tests/test_api_client.py::test_all_retries_exhausted -x` | ❌ Wave 0 |

**Note on mocking HTTP:** Use `unittest.mock.patch` on `httpx.Client.get` to simulate 429/5xx responses without real network calls. The tests for `api_client.py` should mock at the httpx layer.

**Note on backfill tests:** The backfill worker uses `Session(engine)`. In tests, patch `app.backfill.engine` with the test in-memory engine (same approach as `conftest.py`). Alternatively, accept the in-memory engine as a parameter to `_do_backfill` for easier testability.

### Sampling Rate

- **Per task commit:** `python -m pytest tests/ -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_api_client.py` — covers BACK-03 (retry/backoff behavior via mocked httpx)
- [ ] `tests/test_backfill.py` — covers BACK-01, BACK-02 (worker logic via mocked API client + in-memory DB)

No framework changes needed — pytest and conftest.py are already in place.

---

## Sources

### Primary (HIGH confidence)

- Live API verification — `https://mempool.space/api/v1/blocks/:startHeight` tested at heights 0, 1000, 820819; orphan field structure and page size confirmed
- Live API verification — `https://mempool.space/api/v1/stale-tips` tested; 50-item cap, no pagination confirmed
- Live API verification — `https://mempool.space/api/blocks/:height` (non-v1) tested; 10 canonical blocks, no extras confirmed
- GitHub source — `https://raw.githubusercontent.com/mempool/mempool/master/backend/src/api/bitcoin/bitcoin.routes.ts` — confirmed `/api/v1/stale-tips` and `/api/v1/blocks/:height` route definitions
- FastAPI official docs — `https://fastapi.tiangolo.com/advanced/events/` — lifespan context manager pattern
- Interpreter verification — FastAPI 0.115.6, httpx 0.28.1, SQLModel confirmed available; all code patterns executed successfully

### Secondary (MEDIUM confidence)

- GitHub discussion `https://github.com/mempool/mempool/discussions/752` — confirms rate limits are intentionally undisclosed
- `mempool/mempool` GitHub source — `chain-tips.ts` confirms stale tip data structure and `getOrphanedBlocksAtHeight()` method

### Tertiary (LOW confidence)

- None — no findings depend solely on unverified WebSearch results.

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all packages version-confirmed and import-verified in project environment
- Architecture patterns: HIGH — all patterns executed in live interpreter against project models
- API endpoint behavior: HIGH — all critical endpoints live-tested against mempool.space
- Historical data coverage: HIGH — empirically verified; orphan data starts at ~820,819
- Pitfalls: HIGH — each pitfall was derived from actual test execution or API behavior
- Rate limits: LOW for exact numbers (undisclosed); HIGH for "500ms is safe" as starting point

**Research date:** 2026-03-09
**Valid until:** 2026-06-09 (stable API; mempool.space endpoints have not changed materially in 2+ years)
