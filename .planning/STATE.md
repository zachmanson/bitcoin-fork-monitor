---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 05-04 — Analytics views complete. Full dashboard shipped. All 12 plans complete.
last_updated: "2026-03-10T21:37:52.035Z"
last_activity: 2026-03-10 — 05-03 human verification approved
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 12
  completed_plans: 12
  percent: 92
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-09)

**Core value:** Real-time detection and historical analysis of Bitcoin temporary forks, with an accurate stale rate calculated across the full blockchain history.
**Current focus:** Phase 5 — Frontend Dashboard

## Current Position

Phase: 5 of 5 (Frontend Dashboard)
Plan: 3 of 4 complete in current phase
Status: In progress — 05-03 verified, next is 05-04 (Analytics / stale rate chart)
Last activity: 2026-03-10 — 05-03 human verification approved

Progress: [█████████░] 92%

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
| Phase 04-backend-api-sse-server P01 | 5m | 2 tasks | 12 files |
| Phase 04-backend-api-sse-server P02 | 25m | 1 tasks | 3 files |
| Phase 05-frontend-dashboard P01 | 15m | 2 tasks | 10 files |
| Phase 05-frontend-dashboard P02 | 20m | 2 tasks | 6 files |
| Phase 05-frontend-dashboard P04 | 20m | 3 tasks | 3 files |

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
- [Phase 04-backend-api-sse-server]: EventBus uses per-client asyncio.Queue: each SSE connection gets its own queue so a slow browser tab cannot steal events meant for other tabs
- [Phase 04-backend-api-sse-server]: asyncio.run_coroutine_threadsafe is the only correct cross-thread queue API: asyncio.Queue is not thread-safe, direct put_nowait() from monitor thread would corrupt event loop state
- [Phase 04-backend-api-sse-server]: event_bus.set_loop() called before thread start in lifespan: the event loop must be captured before background threads begin or notify() would have a None loop reference
- [Phase 04-backend-api-sse-server]: 1-second inner timeout in SSE generator: enables responsive disconnect detection while 15-cycle counter preserves 15-second keepalive SLA
- [Phase 04-backend-api-sse-server]: SSE tests bypass TestClient.stream(): use OpenAPI schema + route registry for content-type, asyncio.run() with AsyncMock Request for disconnect cleanup
- [Phase 05-frontend-dashboard]: 2016-block windows used as era boundaries — technically precise, matches difficulty adjustment cycle
- [Phase 05-frontend-dashboard]: low_confidence flag for eras below height 321000 (pre-2015 orphan data less reliable)
- [Phase 05-frontend-dashboard]: vite bumped from ^5 to ^6 to satisfy @sveltejs/vite-plugin-svelte peer dependency in SvelteKit 2.53.4
- [Phase 05-frontend-dashboard]: src/app.html added (not in plan) — required SvelteKit root template
- [Phase 05-frontend-dashboard]: Singleton SseManager: one EventSource for the whole app; components subscribe via callback set
- [Phase 05-frontend-dashboard]: Full list replace on SSE update in LiveFeed: handles re-orgs correctly without prepend logic
- [Phase 05-frontend-dashboard]: Lightweight Charts v5 time axis requires YYYY-MM-DD strings — monthly data converted to first-of-month, weekly ISO week strings converted to Monday date

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2]: `GET /api/blocks/:height` behavior is LOW confidence — must verify whether the endpoint returns orphaned blocks at a height or only canonical. This affects the entire backfill fork detection strategy. Validate against live API at the start of Phase 2.
- [Phase 2]: mempool.space actual rate limits are undisclosed. Start at 500ms throttle and adjust empirically.
- [Phase 3]: Stale block confirmation window (how quickly `in_best_chain` flips false) is unconfirmed. May need a 1-3 block delay before recording definitive fork events.

## Session Continuity

Last session: 2026-03-10T20:57:04.629Z
Stopped at: Completed 05-04 — Analytics views complete. Full dashboard shipped. All 12 plans complete.
Resume file: None
