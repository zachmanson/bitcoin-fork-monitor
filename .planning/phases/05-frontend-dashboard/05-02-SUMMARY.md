---
phase: 05-frontend-dashboard
plan: 02
subsystem: ui
tags: [svelte, sveltekit, typescript, sse, eventsource]

requires:
  - phase: 05-01
    provides: SvelteKit scaffold, vite proxy to FastAPI, CSS design tokens, app.html/layout.svelte
  - phase: 04-backend-api-sse-server
    provides: /api/blocks, /api/stats, /api/events SSE endpoint, /api/analytics endpoints

provides:
  - Typed API client module (api.ts) covering all backend endpoints
  - Singleton SSE connection manager (sse.ts) with subscribe/unsubscribe pattern
  - Display format utilities (format.ts) for hashes, timestamps, stale rate, resolution time
  - StatsPanel component: 4 stat cards that re-fetch on every SSE update event
  - LiveFeed component: live block table with orphaned row highlighting and copy-to-clipboard
  - Wired +page.svelte replacing Plan 01 placeholders with real components

affects:
  - 05-03 (ForkEventLog component will import from $lib/api and $lib/sse)
  - 05-04 (analytics chart components will import from $lib/api and $lib/format)

tech-stack:
  added: []
  patterns:
    - "Singleton SSE manager: one EventSource shared across all components via subscribe callbacks"
    - "SSE-driven refresh: components re-fetch on update event arrival, never poll on a timer"
    - "Typed fetch wrappers: all API calls go through api.ts, components import types and functions"
    - "onMount/onDestroy lifecycle: connect + subscribe in onMount, unsubscribe in onDestroy"

key-files:
  created:
    - frontend/src/lib/api.ts
    - frontend/src/lib/sse.ts
    - frontend/src/lib/format.ts
    - frontend/src/lib/components/StatsPanel.svelte
    - frontend/src/lib/components/LiveFeed.svelte
  modified:
    - frontend/src/routes/+page.svelte

key-decisions:
  - "Singleton SseManager pattern: one EventSource for the whole app; components subscribe via callback set instead of creating their own connections"
  - "Full list replace on SSE update: LiveFeed replaces entire block list on every update, which correctly handles re-orgs where canonical/orphaned status of existing blocks can change"
  - "copy-to-clipboard via navigator.clipboard.writeText: standard browser API, no library needed"

patterns-established:
  - "Shared SSE module pattern: import sseManager from $lib/sse, call connect() once, subscribe() returns unsubscribe function for onDestroy"
  - "API module pattern: all fetch calls centralized in $lib/api with typed interfaces and error throwing"
  - "Format module pattern: all display string transformations in $lib/format, no inline formatting in components"

requirements-completed: [DASH-01, DASH-04]

duration: 20min
completed: 2026-03-10
---

# Phase 5 Plan 02: Live Block Feed and Summary Stats Summary

**Typed API layer, singleton SSE manager, and two real-time Svelte components (StatsPanel + LiveFeed) that update without page refresh via server-sent events**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-03-10T16:15:00Z
- **Completed:** 2026-03-10T16:35:00Z
- **Tasks:** 2 of 3 (checkpoint hit at Task 3 — awaiting human verification)
- **Files modified:** 6

## Accomplishments
- Created `$lib/api.ts` with typed fetch wrappers for all five backend endpoints (blocks, stats, forks, stale-rate-over-time, era-breakdown)
- Created `$lib/sse.ts` singleton SSE manager — one EventSource connection shared across all components; components subscribe via callbacks dispatched on every "update" event
- Created `$lib/format.ts` with five pure formatter functions (truncateHash, formatTimestamp, formatStaleRate, formatResolution, copyToClipboard)
- Built `StatsPanel.svelte`: 4 stat cards that re-fetch /api/stats on mount and on each SSE update event
- Built `LiveFeed.svelte`: block table with canonical/orphaned badge, orange row tint for orphaned blocks, truncated hash with clipboard copy button
- Updated `+page.svelte` to render StatsPanel and LiveFeed, with fork log and analytics sections remaining as Plan 03/04 placeholders

## Task Commits

Each task was committed atomically:

1. **Task 1: Create API layer, SSE module, and format utilities** - `ab26451` (feat)
2. **Task 2: Build StatsPanel and LiveFeed components, wire into page** - `26311c9` (feat)

**Plan metadata:** pending final docs commit after checkpoint verification

## Files Created/Modified
- `frontend/src/lib/api.ts` - Typed fetch wrappers and TypeScript interfaces for Block, Stats, ForkEvent, StaleRatePoint, EraBreakdown
- `frontend/src/lib/sse.ts` - SseManager singleton class; singleton exported as `sseManager`
- `frontend/src/lib/format.ts` - Pure display formatter functions (no component coupling)
- `frontend/src/lib/components/StatsPanel.svelte` - 4-card stats panel with SSE-driven data refresh
- `frontend/src/lib/components/LiveFeed.svelte` - Real-time block table with orphaned row highlighting and copy button
- `frontend/src/routes/+page.svelte` - Page shell wired with StatsPanel and LiveFeed imports

## Decisions Made
- **Singleton SSE manager:** one EventSource for the whole app dispatches to a Set of callbacks. Components call `sseManager.subscribe(fn)` which returns an unsubscribe function for use in `onDestroy`. This avoids duplicate backend queues.
- **Full list replace on update:** LiveFeed replaces the entire block array on each SSE event rather than prepending. This is simpler and handles re-orgs correctly — a block that was canonical may become orphaned in the next fetch.
- **navigator.clipboard API:** Used directly in format.ts with a try/catch returning boolean success; no third-party library needed.

## Deviations from Plan

None — plan executed exactly as written. All three files in Task 1 and all three files in Task 2 were created as specified. `npm run build` succeeded after each task.

## Issues Encountered

None — `src/lib/` directory did not exist yet (Plan 01 only created routes); created it alongside `src/lib/components/` before writing files. This was expected based on the Plan 01 summary.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness
- `$lib/api`, `$lib/sse`, `$lib/format` are ready for Plans 03 and 04 to import
- StatsPanel and LiveFeed are live; Fork Event Log (Plan 03) and Analytics (Plan 04) sections are placeholder stubs
- Awaiting checkpoint:human-verify confirmation before marking plan fully complete

---
*Phase: 05-frontend-dashboard*
*Completed: 2026-03-10*
