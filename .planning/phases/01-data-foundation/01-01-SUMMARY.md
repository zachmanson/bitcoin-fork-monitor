---
phase: 01-data-foundation
plan: 01
subsystem: database
tags: [python, sqlmodel, sqlite, fastapi, pytest]

# Dependency graph
requires: []
provides:
  - SQLModel table classes: Block, ForkEvent, SyncState
  - Idempotent create_db_and_tables() function
  - FastAPI-compatible get_session() dependency
  - StaticPool in-memory conftest fixture for all tests
affects:
  - 01-02-data-foundation (stale rate formula builds on this session fixture)
  - 02-backfill (imports Block, ForkEvent, SyncState from app.models)
  - 03-monitoring (imports models and get_session)
  - 04-api (imports models, get_session, and build on schema)

# Tech tracking
tech-stack:
  added:
    - sqlmodel 0.0.21+
    - fastapi 0.115.0+
    - pytest 8.0+
    - Python 3.12
  patterns:
    - SQLModel table=True for combined ORM/Pydantic model
    - hash-as-primary-key for Block (enables fork coexistence at same height)
    - StaticPool in-memory SQLite for isolated test sessions
    - Side-effect import pattern (from app import models) before metadata.create_all()

key-files:
  created:
    - pyproject.toml
    - app/__init__.py
    - app/models.py
    - app/database.py
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_database.py
    - tests/test_models.py
  modified: []

key-decisions:
  - "Block.hash is the primary key (not Block.id) — two blocks at the same height with different hashes must both persist to represent a fork"
  - "ForkEvent stores canonical_hash and orphaned_hash as plain strings, not FK constraints — SQLite FK enforcement requires PRAGMA foreign_keys=ON which is off by default; document this for future enforcement"
  - "pyproject.toml created manually (uv not available) with pip install for dependencies"
  - "test_create_tables_creates_all_three patches db_module.engine rather than calling create_db_and_tables against the production file engine"

patterns-established:
  - "Import pattern: always 'from app import models  # noqa: F401' before SQLModel.metadata.create_all() to populate metadata"
  - "Test isolation: StaticPool + in-memory SQLite ensures each test gets a clean schema — no shared state between tests"
  - "Docstring standard: all functions have docstrings with what/inputs/outputs/assumptions"

requirements-completed: [DATA-01, DATA-02]

# Metrics
duration: 3min
completed: 2026-03-09
---

# Phase 1 Plan 01: Project Setup and SQLModel Schema Summary

**SQLite schema via SQLModel with Block (hash PK), ForkEvent, and SyncState — plus pytest infrastructure with StaticPool in-memory fixtures and 4 passing tests**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-09T16:48:44Z
- **Completed:** 2026-03-09T16:51:44Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Three SQLModel table classes (Block, ForkEvent, SyncState) with correct constraints — Block uses hash as primary key so two blocks at the same height can coexist, representing an actual fork
- Idempotent create_db_and_tables() that safely runs at startup regardless of existing schema state
- StaticPool in-memory conftest fixture that gives each test a fresh, isolated schema with no file I/O
- 4 tests passing: table creation, idempotency, two-blocks-same-height persistence, and duplicate-hash IntegrityError

## Task Commits

Each task was committed atomically:

1. **Task 1: Project setup and SQLModel schema definition** - `58b0ad8` (feat)
2. **Task 2: Database and model tests** - `19b818e` (test)

## Files Created/Modified

- `pyproject.toml` - Project definition with sqlmodel, fastapi deps and pytest config (testpaths, addopts)
- `app/__init__.py` - Empty package marker
- `app/models.py` - Block (hash PK), ForkEvent (id PK, string hashes, no FK enforcement), SyncState (id PK, progress tracking)
- `app/database.py` - ENGINE, create_db_and_tables() (idempotent), get_session() (FastAPI Depends-compatible)
- `tests/__init__.py` - Empty package marker
- `tests/conftest.py` - session fixture with StaticPool + in-memory SQLite, fresh schema per test
- `tests/test_database.py` - DATA-01: creates all three tables, idempotency under double-call
- `tests/test_models.py` - DATA-02: two blocks at same height persist, duplicate hash raises IntegrityError

## Decisions Made

- **Block.hash as primary key:** Height is explicitly NOT the primary key. Two blocks at the same height with different hashes is exactly the fork condition to detect — a height-based PK would silently drop one of them.
- **No FK constraints on ForkEvent.canonical_hash / orphaned_hash:** SQLite FK enforcement requires `PRAGMA foreign_keys=ON` per connection. Documented in module docstring; application layer is responsible for consistency until the pragma is added.
- **Manual pyproject.toml:** uv was not available in the environment. Created pyproject.toml manually and used `pip install` directly.
- **Engine patching in test_database.py:** The `create_db_and_tables` tests patch `db_module.engine` to use the in-memory engine rather than calling against the production file. This keeps test_database.py consistent with the no-file-db goal without refactoring the production function signature.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All three tables defined and tested — Phase 2 (backfill) and Phase 3 (monitoring) can import directly from `app.models`
- Session fixture in conftest.py is ready for all future test files
- `get_session()` is ready for Phase 4 FastAPI dependency injection
- No blockers for Phase 1 Plan 02 (stale rate formula)

---
*Phase: 01-data-foundation*
*Completed: 2026-03-09*
