# Technology Stack

**Project:** Bitcoin Fork Monitor
**Researched:** 2026-03-09
**Confidence:** MEDIUM-HIGH (core stack verified via official sources; mempool.space API detail is MEDIUM — docs require direct access)

---

## Recommended Stack

### Runtime and Language

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Node.js | 22.x LTS | Runtime for both backend poller and build tooling | Active LTS until 2027-04, has native TypeScript type-stripping (run `.ts` files directly), aligns with Fastify v5 requirement |
| TypeScript | 5.x (latest) | Type safety across backend and frontend | Full-stack TypeScript eliminates context-switching; Drizzle ORM and Fastify both have first-class TS support |

### Backend Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Fastify | 5.x (5.8.2 current) | HTTP API server serving frontend and REST endpoints | Fastify v5 drops support for Node < 20, targets v20+; ~3-4x faster than Express; first-class TypeScript; plugin ecosystem (schedule, CORS, static). For a personal tool the perf gap is irrelevant — the real win is TypeScript ergonomics and the `@fastify/schedule` plugin for the poller loop |

### Polling and Scheduling

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `@fastify/schedule` | latest | Schedules the block-polling loop inside the Fastify process | Integrates with Fastify lifecycle (jobs stop on server close, no orphan timers). `toad-scheduler` underneath — supports fixed-interval tasks perfectly for "poll every 60s". No separate process, no OS cron required for a personal tool |
| `ws` (WebSocket client) | 8.x | Subscribe to mempool.space WebSocket for real-time block events | mempool.space pushes new blocks over WebSocket (`blocks` subscription). This avoids polling latency for live feed. `ws` is the standard bare Node.js WebSocket client |

**Polling strategy:** Use mempool.space WebSocket (`wss://mempool.space/api/v1/ws`) as primary real-time feed for new block events. Fall back to HTTP polling (`GET /api/v1/blocks`) for backfill and reconnect scenarios. Do NOT rely solely on polling intervals — the WS push dramatically reduces detection latency.

### Database

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| SQLite (via better-sqlite3) | 12.6.2 | Local persistence for blocks, fork events, stale rate history | Zero-config, single file, synchronous API fits perfectly with a local personal tool. Total dataset is < 1 MB (≤ 4,000 fork events ever). No separate server process, no auth, no maintenance. ACID transactions. Portable |
| Drizzle ORM | 0.45.1 (stable) | Schema management, type-safe queries, migrations | Drizzle runs on top of better-sqlite3 with a synchronous API (no async overhead). Schema-as-code gives TypeScript types for free. Migration system means the DB evolves without manual SQL. Avoid 1.0.0-beta.x — breaking changes still in flux as of early 2026 |

**Do not use:** PostgreSQL (requires a server process, overkill for < 1 MB of data), Prisma (heavy codegen overhead, worse TypeScript experience for SQLite in 2025), raw sqlite3 (callback-based, no TypeScript types).

### Frontend Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| SvelteKit | 2.x (2.49+ current) | Full-stack web framework serving the dashboard UI | Personal dashboard is the ideal SvelteKit use case — smaller bundle than React/Next.js (Svelte runtime: 1.6 KB vs React: 42 KB), reactivity via runes is simpler for real-time data binding, less boilerplate, excellent for internal tools. Svelte 5 runes system is stable and production-ready as of late 2024 |

**SvelteKit configuration for this project:** Run in single-page app (SPA) mode with `adapter-static` or directly served by Fastify as static files. No SSR needed — all data comes from the local Fastify API. This keeps the architecture clean: Fastify owns the API + static file serving, SvelteKit builds to `dist/`.

**Do not use:** Next.js (React ecosystem overhead, SSR complexity not needed for local tool), plain React (no routing/build tooling included), Vue (smaller ecosystem than both React and Svelte for dashboards).

### Charting

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Lightweight Charts (TradingView) | 5.x (5.0 current) | Stale rate over time chart, block timeline | Purpose-built for time-series financial data. 35 kB bundle. Version 5 adds multi-pane support and data conflation (auto-merges dense data when zoomed out). Performance is far beyond Chart.js or Recharts for time-indexed data. Has a dedicated Svelte 5 wrapper (`lightweight-charts-svelte`) |

**Do not use:** Chart.js (general-purpose, not optimized for time-series; no built-in financial semantics), Recharts (React-only, wrong ecosystem), D3.js (too low-level; would require building chart primitives from scratch).

### Frontend Data Transport

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Native `EventSource` (SSE) | browser built-in | Push new block/fork events from Fastify to dashboard in real-time | Server-Sent Events are simpler than WebSockets for one-directional server-to-client push. Fastify has `@fastify/sse-plugin` or can stream manually. No extra client library needed. Reconnects automatically. For a local dashboard with a single user, SSE is the right tool |

**Do not use:** Socket.io (adds protocol negotiation overhead and a large client bundle for a simple use case), raw WebSocket server (SSE is simpler for unidirectional push).

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `node-fetch` / native `fetch` | Node 22 built-in | HTTP calls to mempool.space REST API | Node 22 has stable global `fetch` — no extra dependency needed for REST calls |
| `@fastify/cors` | latest | CORS headers during local dev | Required if frontend dev server (Vite) is on a different port than Fastify |
| `@fastify/static` | latest | Serve built SvelteKit SPA from Fastify | Single-process deployment: Fastify serves API + static files |
| `vite` | 6.x | Frontend build tool (comes with SvelteKit) | SvelteKit's default bundler, no configuration needed |
| `drizzle-kit` | matching drizzle-orm | Run migrations and generate schema | CLI tool for applying Drizzle migrations |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Backend framework | Fastify 5 | Express | Express has no TypeScript support out of the box, lower performance, and no built-in scheduler integration |
| Backend framework | Fastify 5 | Hono | Hono is excellent but optimized for edge runtimes; Fastify's plugin ecosystem is larger for local server use |
| Backend language | TypeScript/Node | Python + FastAPI | Python/FastAPI is good for crypto dashboards but creates a language split with the Svelte frontend. Full-stack TypeScript is simpler for a solo developer |
| Database | SQLite / Drizzle | PostgreSQL | Massive overkill; requires a separate server process and maintenance for < 1 MB data |
| Database | SQLite / Drizzle | Prisma | Heavy codegen, slower cold start, worse ergonomics for SQLite vs. Drizzle |
| Frontend | SvelteKit | Next.js (React) | 42 KB React runtime vs 1.6 KB Svelte; SSR/RSC complexity irrelevant for a local SPA dashboard |
| Frontend | SvelteKit | Vite + plain Svelte | SvelteKit adds routing and API conventions with no penalty; simpler than wiring these up manually |
| Charting | Lightweight Charts 5 | Recharts | React ecosystem — wrong frontend choice |
| Charting | Lightweight Charts 5 | Chart.js | General purpose; lacks time-series financial semantics; lower performance for dense data |
| Real-time transport | SSE (EventSource) | Socket.io | Socket.io is overkill for one-way push to a single local user |
| Scheduling | @fastify/schedule | OS-level cron | OS cron requires a separate process and can't leverage the in-process DB connection; adds operational complexity for a personal tool |

---

## Installation

```bash
# Backend (create as separate package or monorepo)
npm install fastify @fastify/schedule @fastify/static @fastify/cors toad-scheduler ws
npm install drizzle-orm better-sqlite3
npm install -D typescript @types/node @types/better-sqlite3 @types/ws drizzle-kit tsx

# Frontend (SvelteKit)
npm create svelte@latest frontend
cd frontend
npm install lightweight-charts lightweight-charts-svelte
```

**Project structure:**

```
bitcoin-fork-monitor/
  backend/
    src/
      db/         # Drizzle schema + migrations
      poller/     # mempool.space WS client + HTTP backfill
      api/        # Fastify route handlers
      index.ts    # Entry point
  frontend/       # SvelteKit SPA
    src/
      lib/        # Shared components, chart wrappers
      routes/     # Dashboard pages
```

---

## mempool.space API Notes

**Confidence: MEDIUM** (docs accessible but not verified via WebFetch — based on WebSearch findings and mempool.js README)

- **WebSocket:** `wss://mempool.space/api/v1/ws` — subscribe with `{"action": "want", "data": ["blocks"]}`. Pushes new block data on each Bitcoin block (~10 min interval). This is the live feed mechanism.
- **Block status:** `GET /api/block/{hash}/status` — returns `{"in_best_chain": bool, "next_best": string}`. A block with `in_best_chain: false` is orphaned/stale.
- **Block list:** `GET /api/v1/blocks/{height}` — returns 10 blocks starting at height. Used for backfill by paginating downward from tip to genesis.
- **Historical stale detection strategy:** Mempool.space does NOT provide a dedicated "list all orphaned blocks" endpoint. The backfill process must walk block heights, fetch competing blocks at the same height where they exist, and check `in_best_chain` to identify orphans. This is a key architectural finding — the backfill is feasible but requires careful rate limiting against the public API.

**Rate limiting risk:** mempool.space public API has undocumented rate limits. The backfill of ~880,000 blocks requires careful throttling (e.g., 10 req/s max, exponential backoff). This should be treated as a **phase-level research flag** when implementing the backfill phase.

---

## Sources

- Fastify v5 release: [OpenJS Foundation](https://openjsf.org/blog/fastifys-growth-and-success) | [npm](https://www.npmjs.com/package/fastify) — HIGH confidence
- SvelteKit 2.x releases: [Svelte blog](https://svelte.dev/blog) | [GitHub releases](https://github.com/sveltejs/kit/releases) — HIGH confidence
- Drizzle ORM 0.45.1: [npm](https://www.npmjs.com/package/drizzle-orm) | [Drizzle docs](https://orm.drizzle.team/docs/get-started-sqlite) — HIGH confidence
- better-sqlite3 12.6.2: [npm](https://www.npmjs.com/package/better-sqlite3) — HIGH confidence
- Lightweight Charts v5: [TradingView](https://www.tradingview.com/lightweight-charts/) | [GitHub releases](https://github.com/tradingview/lightweight-charts/releases) — HIGH confidence
- Node.js 22 LTS: [nodejs.org](https://nodejs.org/en/about/previous-releases) — HIGH confidence
- mempool.space WebSocket API: [Official docs](https://mempool.space/docs/api/websocket) | [mempool.js README](https://github.com/mempool/mempool.js/blob/main/README-bitcoin.md) — MEDIUM confidence (docs not directly fetched)
- mempool.space block status `in_best_chain`: [mempool.js README](https://github.com/mempool/mempool.js/blob/main/README-bitcoin.md) — MEDIUM confidence
- SQLite vs PostgreSQL for local tools: [HN discussion](https://news.ycombinator.com/item?id=32676455) | [DataCamp comparison](https://www.datacamp.com/blog/sqlite-vs-postgresql-detailed-comparison) — MEDIUM confidence
- SvelteKit for dashboards: [SvelteKit vs Next.js 2025](https://medium.com/better-dev-nextjs-react/next-js-vs-sveltekit-in-2025-ecosystem-power-vs-pure-performance-5bec5c736df2) — MEDIUM confidence (single source)
- Lightweight Charts Svelte 5 wrapper: [GitHub](https://github.com/HuakunShen/lightweight-charts-svelte) — MEDIUM confidence
