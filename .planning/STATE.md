---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: planning
stopped_at: Completed 03-02-PLAN.md — live monitoring thread
last_updated: "2026-03-10T02:58:36.660Z"
last_activity: 2026-03-09 — Roadmap created
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 6
  completed_plans: 6
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-09)

**Core value:** Real-time detection and historical analysis of Bitcoin temporary forks, with an accurate stale rate calculated across the full blockchain history.
**Current focus:** Phase 1 — Data Foundation

## Current Position

Phase: 1 of 5 (Data Foundation)
Plan: 0 of 2 in current phase
Status: Ready to plan
Last activity: 2026-03-09 — Roadmap created

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01-data-foundation P02 | 2 | 1 tasks | 2 files |
| Phase 01-data-foundation P01 | 3 | 2 tasks | 8 files |
| Phase 02-api-client-backfill P01 | 2m | 1 tasks | 2 files |
| Phase 02-api-client-backfill P02 | 3m | 2 tasks | 3 files |
| Phase 03-fork-detection-live-monitoring P01 | 4m | 2 tasks | 3 files |
| Phase 03-fork-detection-live-monitoring P02 | 8m | 3 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Pre-phase]: Use mempool.space as primary data source (public, free, tracks historical orphans)
- [Pre-phase]: Full history backfill on first run (data is tiny; complete stale rate is more meaningful)
- [Pre-phase]: Single Node.js process with Fastify + SvelteKit SPA (no microservices)
- [Phase 01-02]: Stale rate denominator is (canonical + orphaned) — total blocks seen, not just canonical
- [Phase 01-02]: Return 0.0 on zero-zero input (fresh database is not an error); raise ValueError on negative counts (caller bug)
- [Phase 01-01]: Block.hash is the primary key — two blocks at same height with different hashes must both persist to represent a fork
- [Phase 01-01]: ForkEvent hashes stored as plain strings (no FK enforcement) — SQLite requires PRAGMA foreign_keys=ON which is off by default
- [Phase 01-01]: pyproject.toml created manually (uv unavailable); pip install used for sqlmodel, fastapi, pytest
- [Phase 02-api-client-backfill]: time.sleep only inside retry loop; inter-page throttle belongs to backfill worker, not API client
- [Phase 02-api-client-backfill]: RETRY_DELAYS list is single source of truth for backoff schedule (5 entries = 5 total attempts)
- [Phase 02-api-client-backfill]: Pre-populate SyncState in test_backfill_detects_fork so mock only needs 2 API calls instead of 54k+
- [Phase 02-api-client-backfill]: daemon=True backfill thread with 5s join timeout ensures clean uvicorn shutdown without blocking
- [Phase 03-fork-detection-live-monitoring]: fetch_block_status follows identical RETRY_DELAYS pattern as fetch_blocks_page — uniform network I/O across api_client module
- [Phase 03-fork-detection-live-monitoring]: write_fork_event idempotency key is (height, canonical_hash, orphaned_hash) — no composite DB constraint needed
- [Phase 03-fork-detection-live-monitoring]: fork_detector.py is pure — no api_client import — monitor decides canonical/orphaned before calling write_fork_event
- [Phase 03-fork-detection-live-monitoring]: resolution_seconds uses abs() — orphaned blocks can have later header timestamps due to miner timestamp window
- [Phase 03-fork-detection-live-monitoring]: websockets.sync.client used instead of async — monitor runs in background thread without FastAPI event loop access
- [Phase 03-fork-detection-live-monitoring]: pending_resolutions uses mutable list passed by reference — shared across _process_block calls within one monitor session lifecycle
- [Phase 03-fork-detection-live-monitoring]: monitor_thread always starts in lifespan; _wait_for_backfill() gates internally so main.py does not need to know backfill status

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2]: `GET /api/blocks/:height` behavior is LOW confidence — must verify whether the endpoint returns orphaned blocks at a height or only canonical. This affects the entire backfill fork detection strategy. Validate against live API at the start of Phase 2.
- [Phase 2]: mempool.space actual rate limits are undisclosed. Start at 500ms throttle and adjust empirically.
- [Phase 3]: Stale block confirmation window (how quickly `in_best_chain` flips false) is unconfirmed. May need a 1-3 block delay before recording definitive fork events.

## Session Continuity

Last session: 2026-03-09T22:27:44.741Z
Stopped at: Completed 03-02-PLAN.md — live monitoring thread
Resume file: None
