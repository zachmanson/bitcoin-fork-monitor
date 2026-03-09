# Project Research Summary

**Project:** Bitcoin Fork Monitor
**Domain:** Bitcoin blockchain fork detection / stale block analytics dashboard
**Researched:** 2026-03-09
**Confidence:** MEDIUM

## Executive Summary

Bitcoin Fork Monitor is a personal, local-only web dashboard for tracking historical and live Bitcoin stale block (orphan) events and computing stale rate metrics. The right approach is a single-process Node.js application: a backend poller subscribes to the mempool.space WebSocket for real-time block events, detects forks by tracking competing blocks at the same height, persists all data to SQLite, and serves a SvelteKit SPA via Fastify's static file plugin. No microservices, no external database server, no auth layer — the scope is a personal tool with a total dataset under 1 MB (~880,000 blocks, ~4,000 fork events ever).

The recommended stack is full-stack TypeScript: Fastify 5 + `@fastify/schedule` for the backend, SQLite via `better-sqlite3` + Drizzle ORM for persistence, SvelteKit 2 (SPA mode) for the frontend, Lightweight Charts v5 for time-series charting, and SSE (`EventSource`) for real-time browser push. This combination eliminates language context-switching, keeps deployment to a single `node index.ts`, and avoids every overengineered alternative that the domain might tempt a developer toward (PostgreSQL, Socket.io, Next.js, OS cron).

The two dominant risks are: (1) the mempool.space backfill hitting undisclosed rate limits and causing an IP ban that halts all development, and (2) silent data corruption from using block height as an identifier instead of block hash. Both must be addressed in the first phase before any data is written to the database. A third structural risk is that mempool.space's historical orphan data is incomplete before ~2015, meaning the stale rate for early blocks will structurally undercount — this must be communicated in the UI, not treated as a bug to be fixed.

## Key Findings

### Recommended Stack

The entire tool runs as one Node.js 22 LTS process. Fastify 5 handles HTTP routing, static file serving (`@fastify/static`), and the polling scheduler (`@fastify/schedule`). The backend uses `better-sqlite3` (synchronous API — no async overhead) with Drizzle ORM for type-safe schema management and migrations. The frontend is a SvelteKit 2 SPA built to `dist/` and served by Fastify — no SSR, no separate server. Real-time data flows from the backend to the browser via SSE (`EventSource`), and from mempool.space to the backend via WebSocket (`ws` library). Charting uses TradingView's Lightweight Charts v5, which is purpose-built for financial time-series and has a dedicated Svelte 5 wrapper.

Drizzle 0.45.x (stable) is the explicit version — avoid the 1.0.0-beta series. Node.js 22 ships with a stable global `fetch`, so `node-fetch` is not needed.

**Core technologies:**
- Node.js 22 LTS: runtime — active LTS until 2027, native TS type-stripping, matches Fastify v5 requirements
- TypeScript 5.x: full-stack type safety — eliminates context-switching between backend and frontend
- Fastify 5: HTTP + scheduler — ~3-4x faster than Express, first-class TypeScript, `@fastify/schedule` for the polling loop
- `ws` 8.x: outbound WebSocket client — subscribes to mempool.space block feed
- better-sqlite3 + Drizzle 0.45.x: persistence — zero-config, synchronous API, ACID, schema-as-code
- SvelteKit 2 (SPA/adapter-static): frontend — 1.6 KB runtime vs React's 42 KB, runes reactivity suits real-time data
- Lightweight Charts v5: charting — purpose-built for time-series, 35 kB, multi-pane support
- SSE (native `EventSource`): browser push — simpler than WebSocket for one-directional server-to-client updates

### Expected Features

The feature dependency chain flows from the data layer outward: persistence enables backfill, backfill enables all historical stats, and the live block feed enables real-time fork detection, which enables all live stats. Nothing in the UI is useful until the data layer and backfill are complete.

**Must have (table stakes):**
- Data persistence (SQLite schema) — everything else depends on this
- Backfill on first run — without complete history, stale rate is meaningless
- Fork/orphan event detection — the core purpose of the tool
- Live block feed — real-time heartbeat of the dashboard
- Orphan event log — tabular history of fork events with date, height, competing hashes, winner
- Stale rate summary stat — the headline metric (stale / (canonical + stale))
- Stale rate over time chart — weekly/monthly aggregated trend line
- Summary stats panel — total canonical blocks, total stale, stale rate, last fork date

**Should have (differentiators):**
- Rolling stale rate by epoch/year — shows the historical decline since 2017
- Fork resolution time — seconds between competing blocks and canonical resolution
- Competing miner attribution — which pool mined the orphaned block (requires coinbase parsing)
- Per-year/per-month orphan count table — useful for research, low complexity

**Defer (v2+):**
- Stale rate vs hashrate overlay — requires additional data source, high complexity
- Block propagation delay context — research-grade feature, very high complexity
- Multi-chain support — explicit anti-feature; hard-code to Bitcoin mainnet

**Explicit anti-features (never build):** user authentication, push notifications, full blockchain DAG visualization, price overlay, transaction-level data, mempool fee analysis.

### Architecture Approach

A single Node.js process with four internal modules communicating through SQLite and an in-process `EventEmitter`. The Poller connects to mempool.space WebSocket and falls back to REST polling on disconnect. The Fork Detector receives new-block events and queries for competing blocks at the same height. The Backfill Worker runs once on first launch, paging through all historical heights to populate the blocks table. The HTTP/SSE Server reads from SQLite and pushes new events to connected browser clients. The build order is strict: schema first, then the API client module, then backfill, then fork detection, then the live poller, then the API server, then the frontend.

**Major components:**
1. SQLite schema (blocks, fork_events, sync_state) — the foundation; all other components read from or write to this
2. mempool.space API client — rate-limited REST client + WebSocket subscriber; single point of external contact
3. Backfill Worker — one-time full history population with checkpoint/resume via `sync_state` table
4. Fork Detector — height-collision detection logic; called per new block from both backfill and live monitoring
5. Poller — WebSocket subscription + REST fallback; emits `new_block`/`new_fork` events
6. HTTP/SSE Server (Fastify) — serves API endpoints and SSE stream to the SvelteKit SPA
7. SvelteKit SPA — dashboard pages consuming the local API

### Critical Pitfalls

1. **Block height used as primary key** — height is not unique; two competing blocks share the same height during a fork. Use block hash as the primary key everywhere. Never upsert-by-height during live monitoring. Address in the schema before writing a single row.

2. **Backfill hitting mempool.space rate limits** — 880,000 blocks requires tens of thousands of API calls. Use 200–500ms delay between requests from day one, implement exponential backoff on 429 responses, and checkpoint progress in the `sync_state` table after each batch. Do NOT prototype without rate limiting — an IP ban breaks all development.

3. **WebSocket disconnect silently drops fork events** — reconnection resumes from the current tip, silently skipping any blocks in the gap. On reconnect, gap-fill by fetching all blocks between `lastKnownHeight` and current tip via REST before resuming WebSocket. Detect gaps by comparing `previous_block_hash` of the first post-reconnect block against the last stored hash.

4. **Wrong stale rate denominator** — the correct formula is `stale_count / (canonical_count + stale_count)`. Using only canonical count in the denominator is wrong by definition. Define and test this formula explicitly before writing any aggregation queries.

5. **Historical data completeness assumed** — mempool.space orphan data before ~2015 is structurally incomplete (orphans must be observed live to be indexed). Display era-based data confidence notes in the UI; never present pre-2015 stale rate as authoritative.

## Implications for Roadmap

Based on the feature dependency graph, architecture build order, and pitfall phase warnings, the following phase structure is recommended:

### Phase 1: Data Foundation

**Rationale:** Every other component writes to or reads from the database. Pitfalls 1 and 5 (hash as PK, stale/orphan terminology) must be resolved here before any data is persisted. This is also where the `BlockDataSource` interface should be defined so the API client is source-agnostic from the start (Pitfall 8 mitigation).

**Delivers:** SQLite schema (`blocks`, `fork_events`, `sync_state` tables), Drizzle migrations, stale rate formula definition and unit tests, `BlockDataSource` interface.

**Addresses (from FEATURES.md):** Data persistence (table stakes #1)

**Avoids:** Pitfall 1 (height as key), Pitfall 5 (stale rate denominator), Pitfall 6 (orphan/stale terminology confusion)

### Phase 2: External API Client + Backfill

**Rationale:** Backfill must complete before any stats are meaningful, and the rate-limiting/checkpointing strategy must be baked into the backfill from the start (Pitfall 2 and 7). The API client module is shared by backfill and live monitoring; building it first as a standalone module with rate limiting ensures the same discipline applies everywhere.

**Delivers:** mempool.space API client (REST + WebSocket wrapper, 200–500ms throttle, exponential backoff on 429), Backfill Worker with cursor persistence in `sync_state`, end-to-end backfill validated on a small height range.

**Addresses (from FEATURES.md):** Backfill on first run (table stakes #2)

**Avoids:** Pitfall 2 (rate limit IP ban), Pitfall 3 (partial history), Pitfall 7 (backfill state lost on restart)

**Research flag:** The behavior of `GET /api/blocks/:height` — whether it returns orphaned blocks at a height or only the canonical block — is unconfirmed (LOW confidence in ARCHITECTURE.md). This must be verified against the live API before or during this phase. The fork detection strategy in the backfill may need to pivot depending on the answer.

### Phase 3: Fork Detection + Live Monitoring

**Rationale:** Fork detection logic is the core value of the tool. Building it after the API client and schema are established allows clean unit testing with mock API responses. The WebSocket reconnect/gap-fill strategy (Pitfall 4) must be designed into this phase, not bolted on later.

**Delivers:** Fork Detector module (height-collision detection, `fork_events` table writes), Poller (WebSocket + REST fallback), gap-fill logic on reconnect, EventEmitter event bus connecting poller to API server.

**Addresses (from FEATURES.md):** Fork/orphan event detection (table stakes #3), Live block feed (table stakes #4)

**Avoids:** Pitfall 4 (WebSocket disconnect drops events), Pitfall 10 (assuming WS pushes orphan notifications directly)

### Phase 4: Backend API + SSE Server

**Rationale:** With data flowing into SQLite and fork events being detected, the read-side API can be built against real data. SSE is simpler to implement than WebSocket and sufficient for the single-user local dashboard use case.

**Delivers:** Fastify HTTP/SSE server, REST endpoints (`GET /api/stats`, `GET /api/forks`, `GET /api/blocks`), SSE endpoint (`GET /api/events`), `@fastify/static` serving the SvelteKit build.

**Addresses (from FEATURES.md):** Summary stats panel (table stakes #8), Stale rate summary stat (table stakes #6)

### Phase 5: Frontend Dashboard

**Rationale:** The frontend is a pure read path against the local API. Building it last means it can be tested against real data, not mocks. The SvelteKit SPA mode means it builds to static files served by Fastify — no separate deploy step.

**Delivers:** SvelteKit SPA with live block feed, orphan event log, stale rate over time chart (Lightweight Charts v5), summary stats panel, SSE connection for real-time updates.

**Addresses (from FEATURES.md):** All remaining table stakes features (#5, #6, #7, #8), plus the differentiation features (rolling stale rate by epoch, per-year/month tables) as follow-on tasks in this phase.

**Avoids:** Pitfall 9 (displaying fork events before chain resolution — mark recent blocks as unresolved), Pitfall 3 (pre-2015 data confidence — add era notes to charts)

### Phase Ordering Rationale

- Schema before everything: no component functions without the data model, and the primary key decision (hash, not height) is a structural choice that cannot be refactored cheaply later
- API client before backfill: rate limiting must be a first-class concern, not a retrofit; the same client module is reused in live monitoring
- Backfill before live monitoring: the live poller's gap-fill logic on reconnect is architecturally identical to the backfill worker; building backfill first creates the pattern
- Backend API before frontend: allows the frontend to be built against real data, accelerating development and reducing mock maintenance
- This order also matches the architecture research's suggested build order exactly (ARCHITECTURE.md "Suggested Build Order")

### Research Flags

Phases needing deeper research during planning:
- **Phase 2 (API Client + Backfill):** The behavior of `GET /api/blocks/:height` is LOW confidence — whether orphaned blocks are included in the response is architecturally decisive. Must be validated against the live API before writing backfill fork detection. Also validate actual rate limits empirically before choosing a throttle interval.
- **Phase 3 (Fork Detection + Live Monitoring):** The stale block confirmation window (how long before `in_best_chain` flips to `false` after a fork) is unconfirmed. May need a 1–3 block delay before recording definitive fork events.

Phases with standard patterns (research can be skipped):
- **Phase 1 (Data Foundation):** SQLite + Drizzle schema design is well-documented; no research needed
- **Phase 4 (Backend API + SSE):** SSE with Fastify is a standard pattern; no research needed
- **Phase 5 (Frontend Dashboard):** SvelteKit SPA + Lightweight Charts patterns are well-documented

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core technologies (Fastify 5, SvelteKit 2, Drizzle 0.45, better-sqlite3, Lightweight Charts 5, Node 22 LTS) all verified against official sources and npm. The only MEDIUM item is the Svelte 5 Lightweight Charts wrapper (single GitHub source). |
| Features | MEDIUM | Feature list and competitive landscape are well-grounded. The critical unknown is mempool.space API capability for returning orphaned blocks at a height — this affects what is feasible without building on an assumption. |
| Architecture | MEDIUM | Single-process architecture pattern is clearly right for this scope. The open question about `GET /api/blocks/:height` behavior (returns stale blocks or canonical only?) is a MEDIUM-to-LOW confidence area that affects the core backfill and detection strategy. |
| Pitfalls | MEDIUM | Core pitfalls (rate limits, height-as-key, WebSocket gaps, denominator ambiguity) are well-sourced across multiple community and academic sources. mempool.space rate limit specifics remain undisclosed — the 200–500ms recommendation is community-reported, not official. |

**Overall confidence:** MEDIUM

### Gaps to Address

- **`GET /api/blocks/:height` response shape:** Does the endpoint return orphaned/stale blocks at a height, or only the canonical block? This is the single most critical unanswered API question. Validate against the live API at the very start of Phase 2. If orphans are not returned, the backfill fork detection strategy pivots to tracking blocks seen via WebSocket and retrospectively checking their status — a significantly different implementation.

- **mempool.space actual rate limits:** The 200–500ms throttle recommendation is community-sourced. Validate empirically during early Phase 2 development by monitoring 429 response frequency and adjusting. Start conservatively at 500ms.

- **Stale block confirmation window:** How quickly does `in_best_chain` flip to `false` after a fork resolves on mempool.space? If there is a multi-minute delay, the live fork detector must re-check recent blocks on subsequent block arrivals. Validate during Phase 3.

- **Pre-2015 historical data completeness:** The research confirms early orphan data is sparse, but the exact coverage boundary (which block heights have reliable orphan data) is not known. Determine empirically during backfill and document in the UI.

## Sources

### Primary (HIGH confidence)
- [nodejs.org LTS releases](https://nodejs.org/en/about/previous-releases) — Node.js 22 LTS dates
- [npm: fastify](https://www.npmjs.com/package/fastify) — Fastify 5.8.2 current version
- [npm: drizzle-orm](https://www.npmjs.com/package/drizzle-orm) — Drizzle 0.45.1 stable
- [npm: better-sqlite3](https://www.npmjs.com/package/better-sqlite3) — version 12.6.2
- [TradingView Lightweight Charts](https://www.tradingview.com/lightweight-charts/) — v5.0 release, multi-pane support
- [SvelteKit GitHub releases](https://github.com/sveltejs/kit/releases) — 2.x current
- [OpenJS Foundation: Fastify growth](https://openjsf.org/blog/fastifys-growth-and-success) — Fastify v5 Node >=20 requirement

### Secondary (MEDIUM confidence)
- [mempool.space REST API docs](https://mempool.space/docs/api/rest) — block status, orphan detection via `in_best_chain`
- [mempool.space WebSocket API docs](https://mempool.space/docs/api/websocket) — subscription format, block events
- [mempool/mempool.js README](https://github.com/mempool/mempool.js/blob/main/README-bitcoin.md) — API shape confirmation
- [Hashrate Index: Stale blocks overview](https://hashrateindex.com/blog/what-are-orphan-blocks-and-stale-blocks-an-overview/) — historical stale rate ~0.1-1%
- [QuickNode: Reorg handling](https://www.quicknode.com/docs/streams/reorg-handling) — block height vs. hash reliability
- [Bitcoin DSN Fork Monitor (KIT)](https://www.dsn.kastel.kit.edu/bitcoin/forks/) — propagation analysis context
- [CoinMetrics Reorg & Fork Tracker](https://gitbook-docs.coinmetrics.io/network-data/cm-labs/reorg-and-fork-tracker-overview) — feature comparison
- [better-sqlite3 GitHub](https://github.com/WiseLibs/better-sqlite3) — synchronous API, throughput characteristics
- [SSE vs WebSocket comparison](https://systemdesignschool.io/blog/server-sent-events-vs-websocket) — SSE for unidirectional push
- [Academic paper: recovering blockchain metrics](https://eprint.iacr.org/2018/1134.pdf) — early orphan data incompleteness

### Tertiary (LOW confidence)
- [mempool/mempool GitHub discussion #752](https://github.com/mempool/mempool/discussions/752) — rate limits undisclosed, community-reported behavior
- [mempool/mempool GitHub issue #4106](https://github.com/mempool/mempool/issues/4106) — rate limit discoverability
- [0xB10C/fork-observer](https://github.com/0xB10c/fork-observer) — alternative architecture using Bitcoin Core RPC
- [lightweight-charts-svelte](https://github.com/HuakunShen/lightweight-charts-svelte) — Svelte 5 wrapper, single community source

---
*Research completed: 2026-03-09*
*Ready for roadmap: yes*
