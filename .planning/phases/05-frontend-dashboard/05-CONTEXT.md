# Phase 5: Frontend Dashboard - Context

**Gathered:** 2026-03-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the SvelteKit SPA that presents Bitcoin fork history and live activity. Delivers: live block feed (SSE-driven), paginated fork event log, stale rate over time chart, era breakdown view, and summary stats panel. Backend API (FastAPI) is complete — this phase is frontend-only.

</domain>

<decisions>
## Implementation Decisions

### Live block feed
- New blocks slide in at the top of the feed (push existing rows down)
- Orphaned/fork blocks get a colored row background (orange or red tint) — immediately visible at a glance
- Feed shows the last 50 blocks (matches `/api/blocks?limit=50` default)
- Each row shows: block height, truncated hash, timestamp, canonical/orphaned badge

### Dashboard layout & navigation
- Single scrolling page with sections — stats panel → live feed → fork log → analytics charts
- No tabs, no sidebar, no router-level navigation
- Dark mode throughout

### Summary stats panel
- 4 stat cards in a row at the top: canonical blocks, orphaned blocks, stale rate, last fork date
- Stats re-fetch `/api/stats` whenever an SSE block event arrives (no polling, reuses existing SSE connection)

### Analytics chart controls
- Stale rate over time chart: toggle button for weekly ↔ monthly aggregation, default monthly
- Era breakdown appears as a section below the trend chart (not a toggle on the same chart)
- Eras defined by difficulty adjustment era (every 2016 blocks ≈ 2 weeks), not by year or halving epoch
- Pre-2015 data confidence note appears as an inline annotation on early-era rows/bars (info icon or asterisk visible in context)

### Data display format
- Block hashes: first 8 + last 8 characters with a copy-to-clipboard button (e.g. `0000abc1…ff2d3e4f`)
- Fork resolution time: decimal seconds, e.g. `12.3s`
- Timestamps: absolute format `YYYY-MM-DD HH:MM UTC` throughout (no relative times)
- Stale rate: displayed as percentage, e.g. `0.42%`

### Claude's Discretion
- Exact color values for the dark theme (shades, accent colors)
- Specific orange/red tint values for orphaned row highlighting
- Typography, spacing, card shadow styling
- Loading and error states for each section
- Whether to use Tailwind CSS or scoped Svelte styles
- Pagination controls style for the fork event log (prev/next buttons vs page numbers)
- Chart axis labels and grid styling within Lightweight Charts v5

</decisions>

<specifics>
## Specific Ideas

- The live block feed should feel like a monitoring dashboard (think Grafana or a block explorer live feed) — clear, data-dense, not flashy
- The difficulty adjustment era breakdown is the most technically precise era definition — each era is a 2016-block window
- Resolution time in the fork log is already stored as `resolution_seconds` (float) in the database — display as `{value:.1f}s`

</specifics>

<code_context>
## Existing Code Insights

### Backend API surface (all endpoints complete)
- `GET /api/stats` → `{canonical_blocks, orphaned_blocks, stale_rate, last_fork_at}`
- `GET /api/blocks?limit=50` → list of `{hash, height, timestamp, is_canonical}`
- `GET /api/forks?offset=0&limit=50` → paginated list of `{id, height, canonical_hash, orphaned_hash, detected_at, resolution_seconds}`
- `GET /api/events` → SSE stream, event type `"update"`, per-client asyncio.Queue
- `GET /health` → `{status: "ok"}`
- No analytics endpoint yet — `/api/analytics/stale-rate-over-time` and `/api/analytics/era-breakdown` need to be added as part of this phase

### SSE event structure
- EventBus.notify() sends a dict; the event type in the SSE stream is `"update"`
- Frontend should use `EventSource` and listen for `addEventListener("update", handler)`
- Keepalive comments are sent every 15 seconds — EventSource ignores them automatically

### Data models (relevant to frontend)
- `Block.is_canonical: bool` — true = canonical, false = orphaned
- `ForkEvent.resolution_seconds: Optional[float]` — may be null for unresolved forks
- `ForkEvent.detected_at: datetime` — UTC wall-clock time

### Established patterns
- Backend is pure FastAPI (Python) — SvelteKit SPA is a new addition, not integrated into existing Python project
- No frontend code exists yet — starting from scratch

### Integration points
- SvelteKit dev server proxies `/api/*` to FastAPI (localhost:8000) during development
- In production: FastAPI serves static SvelteKit build files, or run separately — Claude's discretion

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 05-frontend-dashboard*
*Context gathered: 2026-03-10*
