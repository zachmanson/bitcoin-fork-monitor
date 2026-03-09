# Roadmap: Bitcoin Fork Monitor

## Overview

Five phases that build strictly bottom-up: the SQLite schema is the foundation everything else reads and writes. Once the schema exists, the rate-limited API client and backfill worker populate full blockchain history. With data in place, fork detection and live monitoring provide the core value. The backend API and SSE layer expose that data to browsers. Finally, the SvelteKit dashboard renders all of it — built last so it runs against real data, not mocks.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Data Foundation** - SQLite schema, SQLModel ORM, and stale rate formula — the dependency everything else builds on (completed 2026-03-09)
- [x] **Phase 2: API Client + Backfill** - Rate-limited mempool.space client and checkpointed full history backfill (completed 2026-03-09)
- [ ] **Phase 3: Fork Detection + Live Monitoring** - Height-collision fork detection, WebSocket poller with REST fallback, gap-fill on reconnect
- [ ] **Phase 4: Backend API + SSE Server** - FastAPI HTTP/SSE server exposing block and fork data with real-time push
- [ ] **Phase 5: Frontend Dashboard** - SvelteKit SPA with live block feed, fork event log, stale rate chart, and summary stats

## Phase Details

### Phase 1: Data Foundation
**Goal**: The SQLite schema, SQLModel ORM configuration, and stale rate formula are in place — correct by construction, with block hash as primary key and a tested denominator definition
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03
**Success Criteria** (what must be TRUE):
  1. Running the app from a fresh checkout creates a SQLite database file with the correct schema (block, forkevent, syncstate tables)
  2. The block table uses block hash as its primary key — inserting two blocks at the same height creates two distinct rows without collision
  3. A unit test asserts the stale rate formula as `orphaned / (canonical + orphaned)` and fails if the denominator is changed
  4. SQLModel create_all runs idempotently — running it twice produces no error and no schema drift
**Plans**: 2 plans

Plans:
- [ ] 01-01-PLAN.md — Python project setup + SQLModel schema (block, forkevent, syncstate tables) + test infrastructure
- [ ] 01-02-PLAN.md — Stale rate formula (calculate_stale_rate) + TDD unit tests pinning the denominator

### Phase 2: API Client + Backfill
**Goal**: Full Bitcoin blockchain history (all orphaned/stale blocks since genesis) is persisted in SQLite via a rate-limited, checkpointed backfill that can survive process restarts
**Depends on**: Phase 1
**Requirements**: BACK-01, BACK-02, BACK-03
**Success Criteria** (what must be TRUE):
  1. Running the app for the first time triggers the backfill worker, which fetches historical fork/orphan data from mempool.space and writes it to SQLite
  2. Killing and restarting the app mid-backfill resumes from the last checkpointed height rather than restarting from genesis
  3. The API client enforces at least 500ms between requests and applies exponential backoff on HTTP 429 responses — no IP ban during development
  4. After backfill completes, the sync_state table records a "backfill complete" marker and the worker does not run again on subsequent starts
**Plans**: 2 plans

Plans:
- [ ] 02-01-PLAN.md — mempool.space HTTP client (fetch_blocks_page) with retry/backoff + 8 unit tests covering BACK-03
- [ ] 02-02-PLAN.md — Backfill worker (run_backfill, checkpointing) + FastAPI lifespan entrypoint + 5 unit tests covering BACK-01, BACK-02

### Phase 3: Fork Detection + Live Monitoring
**Goal**: The system detects Bitcoin temporary forks in real-time as competing blocks arrive at the same height, records orphaned blocks, and never silently misses a fork event across WebSocket disconnects
**Depends on**: Phase 2
**Requirements**: MONI-01, MONI-02, MONI-03
**Success Criteria** (what must be TRUE):
  1. When a new block arrives via WebSocket, the system checks for a competing block at the same height and records a fork_event row if one exists
  2. If the WebSocket connection drops and reconnects, the system gap-fills by fetching all missed blocks via REST before resuming WebSocket — no fork events are silently skipped
  3. If the WebSocket is completely unavailable, the system falls back to REST polling on a configurable interval and continues detecting forks
  4. Fork resolution time (seconds between competing blocks) is recorded in each fork_event row
**Plans**: TBD

Plans:
- [ ] 03-01: Fork Detector module (height-collision detection, fork_events writes, resolution time)
- [ ] 03-02: Poller with WebSocket subscription, REST fallback, and gap-fill on reconnect

### Phase 4: Backend API + SSE Server
**Goal**: A FastAPI server exposes block and fork data via REST endpoints and pushes real-time updates to browser clients via Server-Sent Events
**Depends on**: Phase 3
**Requirements**: DASH-02, DASH-04
**Success Criteria** (what must be TRUE):
  1. GET /api/stats returns a JSON response with total canonical blocks, total orphaned blocks, current stale rate, and date of last fork
  2. GET /api/forks returns a paginated list of fork events (block height, date, orphaned hash, canonical hash, resolution time)
  3. GET /api/blocks returns the most recent blocks with fork events highlighted
  4. GET /api/events (SSE) pushes a new event to connected clients within 2 seconds of a new block or fork being recorded
**Plans**: TBD

Plans:
- [ ] 04-01: FastAPI server with REST endpoints (/api/stats, /api/forks, /api/blocks)
- [ ] 04-02: SSE endpoint (/api/events) with EventEmitter bus connecting poller to browser clients

### Phase 5: Frontend Dashboard
**Goal**: Users can see the Bitcoin blockchain's fork history and live activity in a web dashboard — live block feed, fork event log, stale rate over time chart, and summary stats all render correctly and update without page refresh
**Depends on**: Phase 4
**Requirements**: DASH-01, DASH-03, ANAL-01, ANAL-02, ANAL-03
**Success Criteria** (what must be TRUE):
  1. The live block feed shows the most recent blocks as they arrive, with fork events visually highlighted, updating in real-time without a page refresh
  2. The fork event log shows a paginated table of all fork events with block height, date, orphaned hash, canonical hash, and fork resolution time in seconds
  3. The stale rate over time chart renders as a weekly or monthly aggregated trend line across the full blockchain history
  4. The era breakdown view shows stale rate by year or difficulty era, with a visible data confidence note for pre-2015 data
  5. The summary stats panel shows total canonical blocks, total orphaned blocks, current stale rate, and date of last fork — updating live via SSE
**Plans**: TBD

Plans:
- [ ] 05-01: SvelteKit SPA setup with live block feed and SSE connection
- [ ] 05-02: Fork event log (paginated table) and summary stats panel
- [ ] 05-03: Stale rate over time chart (Lightweight Charts v5) and era breakdown view with data confidence notes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Foundation | 2/2 | Complete   | 2026-03-09 |
| 2. API Client + Backfill | 2/2 | Complete   | 2026-03-09 |
| 3. Fork Detection + Live Monitoring | 0/2 | Not started | - |
| 4. Backend API + SSE Server | 0/2 | Not started | - |
| 5. Frontend Dashboard | 0/3 | Not started | - |
