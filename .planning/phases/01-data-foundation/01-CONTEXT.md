# Phase 1: Data Foundation - Context

**Gathered:** 2026-03-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Set up the project foundation: Python environment, SQLite database schema via SQLModel, and the stale rate formula with a unit test. This phase delivers the data layer everything else reads and writes. No API calls, no monitoring, no UI — just the schema and formula, correct by construction.

</domain>

<decisions>
## Implementation Decisions

### Language & Runtime
- **Python** — not TypeScript/Node.js (despite research recommendation)
- CLAUDE.md's pytest reference was intentional; this is a Python project
- FastAPI for the backend web framework (async-native, production-grade, good learning investment)
- SQLModel for database ORM (FastAPI creator's library; integrates DB models and API schemas, works natively with FastAPI)
- SQLite as the database (local, lightweight, sufficient for this data volume)

### Frontend
- Separate JS frontend (not Python-rendered HTML/Jinja2)
- FastAPI serves JSON API; browser-side JS handles the dashboard
- Frontend framework decision deferred to Phase 5

### Testing
- pytest for all tests (per CLAUDE.md)
- Tests in `/tests` directory (per CLAUDE.md)
- Phase 1 must include a unit test asserting the stale rate formula: `orphaned / (canonical + orphaned)`

### Claude's Discretion
- Project directory structure and module layout (follow professional Python conventions)
- Exact SQLModel field types and constraints
- Migration strategy (Alembic vs SQLModel's built-in `create_all`)
- Virtual environment and dependency management tooling (poetry, pip, uv, etc.)

</decisions>

<specifics>
## Specific Ideas

- CLAUDE.md explicitly sets expectations: clean, professional, modular code — not quick scripts
- Code should be structured like a real-world software project: modular architecture, testable components, clear separation of concerns
- All important functions should have docstrings (what, inputs, outputs, assumptions)

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project, no existing code

### Established Patterns
- None yet — Phase 1 establishes the baseline patterns all future phases follow

### Integration Points
- SQLModel models defined here will be imported by Phase 2 (backfill), Phase 3 (monitoring), Phase 4 (API server)
- The stale rate formula defined here will be called by Phase 4's `/api/stats` endpoint

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-data-foundation*
*Context gathered: 2026-03-09*
