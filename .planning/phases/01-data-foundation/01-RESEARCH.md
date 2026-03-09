# Phase 1: Data Foundation - Research

**Researched:** 2026-03-09
**Domain:** Python, SQLModel, SQLite, pytest
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Python** — not TypeScript/Node.js
- **FastAPI** for the backend web framework (async-native, production-grade)
- **SQLModel** for ORM — integrates DB models and API schemas, built on Pydantic + SQLAlchemy
- **SQLite** as the database (local, lightweight)
- **pytest** for all tests
- Tests in `/tests` directory
- Phase 1 must include a unit test asserting the stale rate formula: `orphaned / (canonical + orphaned)`
- Separate JS frontend (not Jinja2); FastAPI serves JSON only

### Claude's Discretion
- Project directory structure and module layout (follow professional Python conventions)
- Exact SQLModel field types and constraints
- Migration strategy (Alembic vs SQLModel's built-in `create_all`)
- Virtual environment and dependency management tooling (poetry, pip, uv, etc.)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DATA-01 | System persists block and orphan event data in a local SQLite database that survives process restarts | SQLModel `create_engine` with a file path (not in-memory) ensures persistence across restarts; `create_all()` on startup is idempotent |
| DATA-02 | Block hash is used as primary key for all block records (not block height) | SQLModel `Field(primary_key=True)` on `hash: str` column; hash is naturally unique, height is not (two blocks at same height = two rows) |
| DATA-03 | Stale rate is calculated as `orphaned_blocks / (canonical_blocks + orphaned_blocks)` — formula is enforced at the data layer | A pure Python function in the data layer, covered by a pytest unit test that asserts the denominator formula exactly |
</phase_requirements>

---

## Summary

Phase 1 establishes the data layer for the entire project: SQLite database schema, SQLModel ORM models, and the stale rate formula with a unit test. This is a greenfield Python project with no existing code.

SQLModel (version 0.0.37, February 2026) is the correct ORM choice here — it unifies SQLAlchemy's database power with Pydantic's validation, and both models and API schemas can be derived from the same class definitions. For Phase 1, which has no FastAPI endpoints yet, SQLModel still delivers value by establishing the exact schema the later phases will read and write.

The migration strategy decision for Phase 1 is `SQLModel.metadata.create_all()`. It is natively idempotent (no error on re-run, no schema drift if schema matches), which satisfies the success criterion. Alembic is the right tool for schema evolution in later phases but adds unnecessary setup complexity to Phase 1.

**Primary recommendation:** Use `uv` for dependency management, `SQLModel.metadata.create_all()` (not Alembic) for Phase 1 schema initialization, and an in-memory SQLite engine in pytest fixtures for test isolation.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12+ | Runtime | Type annotation improvements (`X | Y` union syntax), better error messages |
| SQLModel | 0.0.37 | ORM + schema unification | Combines SQLAlchemy and Pydantic; FastAPI creator's library; single model class serves DB and API |
| SQLAlchemy | (transitive via SQLModel) | DB engine + query layer | SQLModel wraps it; `create_engine`, `Session`, `StaticPool` come from here |
| pytest | 8.x | Test runner | Locked by CLAUDE.md; fixture system integrates cleanly with SQLModel sessions |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uv | latest | Dependency/venv management | Recommended for new Python projects in 2025-2026; 10-100x faster than pip; handles Python version management too |
| pydantic | 2.x (transitive via SQLModel) | Data validation | Comes with SQLModel; used implicitly for field validation |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| uv | poetry | Poetry is mature and feature-rich; uv is faster and simpler for a single-developer project |
| uv | pip + venv | pip is universal but slower; no lock file by default; fine if uv is unfamiliar |
| SQLModel `create_all` | Alembic | Alembic needed for safe schema evolution; overkill for Phase 1 greenfield; introduce in a later phase when schema changes become real |

**Installation:**
```bash
# Using uv (recommended)
uv init bitcoin-fork-monitor
uv add sqlmodel fastapi pytest

# Or using pip + requirements.txt
pip install sqlmodel fastapi pytest
```

---

## Architecture Patterns

### Recommended Project Structure

```
bitcoin-fork-monitor/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app entry point (Phase 4)
│   ├── database.py      # Engine creation, create_all, get_session dependency
│   ├── models.py        # All SQLModel table models (blocks, fork_events, sync_state)
│   └── analytics.py     # Stale rate formula and other business logic
├── tests/
│   ├── __init__.py
│   ├── conftest.py      # Shared pytest fixtures (in-memory engine, session)
│   └── test_analytics.py # Unit tests for stale rate formula
├── bitcoin_fork.db      # SQLite database file (gitignored)
├── pyproject.toml       # Dependencies (uv/poetry) or requirements.txt
└── CLAUDE.md
```

**Why this layout:**
- `models.py` centralizes all table definitions — avoids circular import issues that arise from splitting models across files
- `database.py` owns engine creation and the session dependency — one place to change DB path or connection args
- `analytics.py` isolates the stale rate formula so it's independently testable without touching any DB
- `tests/conftest.py` shared fixtures keep individual test files clean

### Pattern 1: SQLModel Table Definition

**What:** Define a database table as a Python class inheriting `SQLModel` with `table=True`.
**When to use:** Every persisted entity.

```python
# Source: https://sqlmodel.tiangolo.com/tutorial/create-db-and-table/
from sqlmodel import SQLModel, Field
from datetime import datetime

class Block(SQLModel, table=True):
    """A Bitcoin block record.

    Uses block hash as primary key — not height — so two blocks at
    the same height (a temporary fork) produce two distinct rows.
    """
    hash: str = Field(primary_key=True)
    height: int
    timestamp: datetime
    is_canonical: bool = True
```

Key points:
- `hash: str = Field(primary_key=True)` satisfies DATA-02 — hash is the PK, not height
- `is_canonical: bool` tracks whether this block is in the main chain (False = orphaned)
- SQLite stores datetime as ISO 8601 text; SQLAlchemy handles the conversion automatically

### Pattern 2: Database Engine + Session Dependency

**What:** Create the SQLite engine once at module level; provide a session via a generator function.
**When to use:** `database.py` module.

```python
# Source: https://sqlmodel.tiangolo.com/tutorial/create-db-and-table/
from sqlmodel import SQLModel, Session, create_engine

DATABASE_URL = "sqlite:///bitcoin_fork.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

def create_db_and_tables() -> None:
    """Create all SQLModel tables if they do not already exist.

    Idempotent: safe to call on every startup. Uses SQLModel.metadata.create_all,
    which issues CREATE TABLE IF NOT EXISTS under the hood.
    """
    SQLModel.metadata.create_all(engine)

def get_session():
    """Yield a database session for use as a FastAPI dependency."""
    with Session(engine) as session:
        yield session
```

`check_same_thread=False` is required for SQLite when accessed from multiple threads (FastAPI's async request handling).

### Pattern 3: Stale Rate Formula — Data Layer Function

**What:** A pure function that computes the stale rate. Lives in `analytics.py`, not in a model class.
**When to use:** Called by Phase 4's `/api/stats` endpoint.

```python
def calculate_stale_rate(canonical: int, orphaned: int) -> float:
    """Calculate the Bitcoin stale block rate.

    Formula: orphaned / (canonical + orphaned)

    Args:
        canonical: Count of blocks in the longest chain.
        orphaned: Count of blocks not in the longest chain.

    Returns:
        Stale rate as a float in [0.0, 1.0]. Returns 0.0 if no blocks exist.

    Raises:
        ValueError: If either count is negative.
    """
    if canonical < 0 or orphaned < 0:
        raise ValueError("Block counts must be non-negative")
    total = canonical + orphaned
    if total == 0:
        return 0.0
    return orphaned / total
```

This satisfies DATA-03 — formula is explicit and isolated. The unit test pins the denominator definition.

### Pattern 4: pytest Fixtures with In-Memory SQLite

**What:** conftest.py provides a clean session per test using an in-memory database.
**When to use:** All database-touching tests.

```python
# Source: https://sqlmodel.tiangolo.com/tutorial/fastapi/tests/
import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

@pytest.fixture(name="session")
def session_fixture():
    """Yield an isolated in-memory SQLite session for each test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
```

`StaticPool` forces SQLAlchemy to reuse a single connection — required for in-memory SQLite so the created tables remain visible within the same test.

### Anti-Patterns to Avoid

- **Using block height as primary key:** Height is not unique — two competing blocks share a height. Using height as PK causes the second INSERT to silently overwrite the first (violating DATA-02). Use hash.
- **Calling `create_all()` before importing models:** SQLModel's metadata is only populated when model classes are imported. If `create_all()` runs before `from app.models import Block`, no tables are created. Always import models first.
- **Global mutable session in tests:** Creating a single session for all tests causes state leakage. The per-function fixture scope (pytest default) ensures each test gets a clean slate.
- **`sqlite:///` vs `sqlite://` in tests:** Production uses `sqlite:///filename.db` (file). Tests use `sqlite://` (in-memory, empty filename). Confusing these causes tests to write real files or fail to find tables.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema definition | Custom SQL CREATE TABLE strings | SQLModel models | Type safety, Pydantic validation, FastAPI schema generation — all free |
| Table creation idempotency | Custom `IF NOT EXISTS` checks | `SQLModel.metadata.create_all()` | Already idempotent; re-running on startup is safe by design |
| Test database isolation | Manual DROP TABLE / teardown | In-memory SQLite + per-function fixture | StaticPool in-memory engine is destroyed after each test automatically |
| Session lifecycle | Manual `session.close()` calls | `with Session(engine) as session:` context manager | Context manager closes on exit even if an exception occurs |

**Key insight:** SQLModel's `create_all()` emits `CREATE TABLE IF NOT EXISTS` internally. It is idempotent by construction — the success criterion "running twice produces no error and no schema drift" is satisfied without any extra logic.

---

## Common Pitfalls

### Pitfall 1: Model Import Order with `create_all()`

**What goes wrong:** `create_all()` runs but creates zero tables. Database file exists but is empty.
**Why it happens:** `SQLModel.metadata` collects table definitions as classes are imported. If `create_all()` is called in `database.py` before `models.py` is imported anywhere, metadata is empty.
**How to avoid:** In `database.py`, call `create_db_and_tables()` only after models are imported. In `main.py`, use FastAPI's lifespan event:
```python
from app import models  # noqa: F401 — import triggers registration
from app.database import create_db_and_tables

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield
```
**Warning signs:** DB file exists but `sqlite3 bitcoin_fork.db ".tables"` returns nothing.

### Pitfall 2: SQLite Thread Safety with FastAPI

**What goes wrong:** `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`.
**Why it happens:** SQLite's default mode rejects cross-thread connection sharing. FastAPI handles requests across threads.
**How to avoid:** Always include `connect_args={"check_same_thread": False}` in `create_engine()`. This is safe because SQLModel manages one session per request with proper locking.
**Warning signs:** Error only appears under concurrent requests, not single-threaded tests.

### Pitfall 3: Stale Rate Division by Zero

**What goes wrong:** `ZeroDivisionError` when no blocks have been ingested yet (fresh database).
**Why it happens:** `orphaned / (canonical + orphaned)` with both counts at zero.
**How to avoid:** The formula function must guard against `total == 0` and return `0.0`. The unit test should assert this edge case explicitly.

### Pitfall 4: `table=True` Forgotten

**What goes wrong:** Model class defined but no table created in the database.
**Why it happens:** SQLModel classes without `table=True` are treated as pure Pydantic schemas — no SQLAlchemy table is registered.
**How to avoid:** Every class meant as a DB table must include `table=True` in the class definition. Classes meant only for API I/O (request/response bodies) intentionally omit it.

---

## Code Examples

### Minimal Working Schema (three tables)

```python
# app/models.py
# Source: https://sqlmodel.tiangolo.com/tutorial/create-db-and-table/
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class Block(SQLModel, table=True):
    """A Bitcoin block — canonical or orphaned.

    Primary key is block hash, not height. Two blocks at the same height
    (a fork) produce two distinct rows without collision.
    """
    hash: str = Field(primary_key=True)
    height: int = Field(index=True)
    timestamp: datetime
    is_canonical: bool = Field(default=True)


class ForkEvent(SQLModel, table=True):
    """A recorded temporary fork: two competing blocks at the same height."""
    id: Optional[int] = Field(default=None, primary_key=True)
    height: int
    canonical_hash: str = Field(foreign_key="block.hash")
    orphaned_hash: str = Field(foreign_key="block.hash")
    detected_at: datetime = Field(default_factory=datetime.utcnow)


class SyncState(SQLModel, table=True):
    """Checkpoint for backfill progress — survives process restarts."""
    id: Optional[int] = Field(default=None, primary_key=True)
    last_synced_height: int = Field(default=0)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### Stale Rate Unit Test

```python
# tests/test_analytics.py
import pytest
from app.analytics import calculate_stale_rate


def test_stale_rate_formula():
    """Denominator must be canonical + orphaned (not orphaned alone or canonical alone)."""
    assert calculate_stale_rate(canonical=99, orphaned=1) == pytest.approx(1 / 100)


def test_stale_rate_denominator_definition():
    """Pin the exact formula: orphaned / (canonical + orphaned).

    If the denominator ever changes, this test must fail.
    """
    canonical = 95
    orphaned = 5
    result = calculate_stale_rate(canonical, orphaned)
    expected = orphaned / (canonical + orphaned)  # 5/100 = 0.05
    assert result == pytest.approx(expected)
    # Explicitly assert it is NOT orphaned/canonical
    assert result != pytest.approx(orphaned / canonical)


def test_stale_rate_zero_blocks():
    """No blocks yet — formula returns 0.0 without error."""
    assert calculate_stale_rate(canonical=0, orphaned=0) == 0.0


def test_stale_rate_all_orphaned():
    """Edge case: all blocks are orphaned."""
    assert calculate_stale_rate(canonical=0, orphaned=10) == pytest.approx(1.0)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SQLAlchemy models + separate Pydantic schemas | SQLModel unified models | ~2021 (SQLModel released) | Single source of truth; no duplication between DB and API layers |
| pip + requirements.txt | uv with pyproject.toml | 2024-2025 (uv matured) | 10-100x faster installs; lock file included; Python version management built in |
| Alembic for all migrations | `create_all()` for greenfield, Alembic for evolution | Ongoing practice | `create_all()` is idempotent and sufficient for Phase 1; Alembic adds value only when changing an existing schema |

**Deprecated/outdated:**
- Hand-written `CREATE TABLE` SQL strings: SQLModel handles this with full type safety
- `flask-sqlalchemy` pattern of `db.Model` base class: SQLModel's `SQLModel` base is the modern equivalent for FastAPI projects

---

## Open Questions

1. **`fork_events` table — foreign keys to `block.hash` or inline hash columns?**
   - What we know: SQLModel supports `foreign_key="block.hash"` on string fields
   - What's unclear: Whether FK constraints are enforced by SQLite (they require `PRAGMA foreign_keys = ON` which SQLite disables by default)
   - Recommendation: Store both hashes as plain string columns in Phase 1; add FK enforcement as an explicit decision in Phase 2 when the data model is exercised under real data

2. **Alembic vs `create_all` for long-term schema management**
   - What we know: `create_all()` is sufficient and idempotent for Phase 1's greenfield schema
   - What's unclear: When the schema first needs to change (e.g., adding a column in Phase 3), `create_all()` will NOT migrate existing databases
   - Recommendation: Document this limitation in the Phase 1 plan; defer Alembic introduction to the phase that first requires a schema change

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` section — Wave 0 creates this |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | SQLite file created on startup; tables present after `create_db_and_tables()` | integration | `pytest tests/test_database.py -x` | Wave 0 |
| DATA-02 | Two blocks at same height with different hashes both persist (no collision) | integration | `pytest tests/test_models.py::test_two_blocks_same_height -x` | Wave 0 |
| DATA-03 | `calculate_stale_rate(99, 1)` returns `0.01`; denominator is `canonical + orphaned` | unit | `pytest tests/test_analytics.py -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/ -x -q`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/__init__.py` — makes tests a package (required for relative imports)
- [ ] `tests/conftest.py` — in-memory SQLite session fixture
- [ ] `tests/test_analytics.py` — stale rate formula assertions
- [ ] `tests/test_models.py` — DATA-02 two-blocks-at-same-height test
- [ ] `tests/test_database.py` — DATA-01 create_all idempotency test
- [ ] `pyproject.toml` — project definition with `[tool.pytest.ini_options]`
- [ ] Framework install: `uv add pytest` or `pip install pytest`

---

## Sources

### Primary (HIGH confidence)

- [sqlmodel.tiangolo.com/tutorial/create-db-and-table](https://sqlmodel.tiangolo.com/tutorial/create-db-and-table/) — engine creation, model definition, `create_all` usage
- [sqlmodel.tiangolo.com/tutorial/code-structure](https://sqlmodel.tiangolo.com/tutorial/code-structure/) — recommended project layout, avoiding circular imports
- [sqlmodel.tiangolo.com/tutorial/fastapi/tests](https://sqlmodel.tiangolo.com/tutorial/fastapi/tests/) — pytest fixture pattern, `StaticPool`, in-memory SQLite

### Secondary (MEDIUM confidence)

- [github.com/fastapi/sqlmodel releases](https://github.com/fastapi/sqlmodel/releases) — confirmed version 0.0.37 released February 2026
- [betterstack.com SQLModel guide](https://betterstack.com/community/guides/scaling-python/sqlmodel-orm/) — best practices verified against official docs
- Multiple 2025-2026 sources confirm uv as the recommended dependency manager for new Python projects

### Tertiary (LOW confidence)

- Migration section added to SQLModel docs (PR #1555) — confirms Alembic is officially documented path; integrated migration planned but not yet shipped

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — SQLModel version confirmed from GitHub releases; pytest locked by project; uv recommendation cross-verified across multiple 2025-2026 sources
- Architecture: HIGH — structure derived from official SQLModel code-structure docs, verified against FastAPI best practices
- Pitfalls: HIGH — import order and thread safety issues are documented in official SQLModel/FastAPI sources; division-by-zero is a direct consequence of the formula

**Research date:** 2026-03-09
**Valid until:** 2026-06-09 (SQLModel is fairly stable; uv tooling evolves fast but the patterns are stable)
