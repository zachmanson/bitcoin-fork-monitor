# Architecture Patterns

**Domain:** Bitcoin blockchain fork monitor (local web dashboard)
**Researched:** 2026-03-09

---

## Recommended Architecture

A single-process Node.js application with four internal modules communicating through a shared SQLite database and an in-process event emitter. No microservices, no message queue — the data volume and personal-use context don't justify the overhead.

```
┌─────────────────────────────────────────────────────┐
│                   Node.js Process                   │
│                                                     │
│  ┌──────────────┐     ┌───────────────────────────┐ │
│  │   Poller     │────▶│     Fork Detector         │ │
│  │  (setInterval│     │  (compares blocks at same │ │
│  │  + WS client)│     │   height, flags orphans)  │ │
│  └──────────────┘     └─────────────┬─────────────┘ │
│         │                           │               │
│         ▼                           ▼               │
│  ┌──────────────────────────────────────────────┐   │
│  │              SQLite (better-sqlite3)         │   │
│  │  tables: blocks, fork_events, sync_state     │   │
│  └──────────────────────────────────────────────┘   │
│         │                           │               │
│         ▼                           ▼               │
│  ┌──────────────┐     ┌───────────────────────────┐ │
│  │  Backfill    │     │   HTTP/SSE API Server     │ │
│  │  Worker      │     │  (Express + /api routes   │ │
│  │  (runs once) │     │   + SSE /events stream)   │ │
│  └──────────────┘     └─────────────┬─────────────┘ │
│                                     │               │
└─────────────────────────────────────┼───────────────┘
                                      │
                              ┌───────▼───────┐
                              │   Browser     │
                              │  (Vite/React  │
                              │   dashboard)  │
                              └───────────────┘
```

**External dependency:** mempool.space REST API + WebSocket API

---

## Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| **Poller** | Connects to mempool.space WebSocket; receives new block notifications; falls back to REST polling every 60s | Fork Detector (via event emitter), SQLite (write raw block records) |
| **Fork Detector** | On each new block: queries SQLite for other blocks at the same height; calls `GET /block/:hash/status` if ambiguous; writes fork_events rows | SQLite (read/write), mempool.space REST API |
| **Backfill Worker** | On first run (sync_state.backfill_complete = false): pages through all historical heights; populates blocks table; marks complete | SQLite (read/write), mempool.space REST API |
| **HTTP/SSE Server** | Serves `/api/*` JSON endpoints for dashboard data; streams `text/event-stream` on `/api/events` when fork or block detected | SQLite (read-only), Poller/Fork Detector (via event emitter) |
| **Frontend** | Browser SPA: live block feed, fork event log, stale rate chart, summary stats | HTTP/SSE Server |

---

## Data Flow

### Backfill (one-time, first run)

```
startup
  └── check sync_state.backfill_complete
        └── false → Backfill Worker starts
              ├── GET /api/v1/blocks/:height (batch up to 10)
              ├── for each block hash: GET /api/block/:hash/status → in_best_chain
              ├── write to SQLite: blocks table (hash, height, timestamp, in_best_chain)
              ├── if multiple blocks at height: write fork_events row
              └── advance cursor → height + 10 → repeat
                  └── when tip reached: set sync_state.backfill_complete = true
```

**Rate limiting consideration:** mempool.space public API is undocumented on limits but community reports ~250 req/min. At 880,000 heights and batches of 10, that is ~88,000 batch requests. At 250 req/min that is ~6 hours. In practice, orphan blocks are rare — only heights with competing blocks need the status check. The backfill worker should: (a) use the batch endpoint for all heights, (b) only call `/block/:hash/status` for heights that return more than one block hash. This collapses the status-check requests to ~1,000–4,000 total, making backfill feasible in under an hour with conservative throttling (100ms delay between requests).

### Live Monitoring (ongoing, after backfill)

```
mempool.space WebSocket
  └── message: { action: "want", data: ["blocks"] }
        └── receive: { block: { height, id (hash), timestamp, ... } }
              ├── write block to SQLite
              ├── Fork Detector: GET /api/block/:hash/status
              │     └── in_best_chain = false → write fork_event
              └── emit "new_block" / "new_fork" on internal EventEmitter
                    └── SSE Server: push event to connected browser clients
```

**Fallback:** If WebSocket disconnects, Poller switches to polling `GET /api/blocks/tip/height` every 30 seconds. On height change, fetch the new block and run fork detection.

### Dashboard Read Path

```
Browser
  └── on load: GET /api/stats → { stale_rate, total_blocks, total_forks }
  └── on load: GET /api/forks?limit=50 → recent fork events
  └── SSE connect: GET /api/events → EventSource stream
        └── on "block": update live feed
        └── on "fork": append to fork log, recalculate stale rate
```

---

## Key API Endpoints Used (mempool.space)

All are MEDIUM–HIGH confidence based on official docs and multiple sources:

| Endpoint | Purpose | Notes |
|----------|---------|-------|
| `GET /api/blocks/:height` | Get block hash(es) at a height | Returns array; multiple entries = potential fork height |
| `GET /api/block/:hash/status` | Check if block is in best chain | `in_best_chain: false` = orphaned/stale |
| `GET /api/blocks/tip/height` | Current chain tip height | Used for backfill cursor and polling fallback |
| `GET /api/v1/blocks/:height?minHeight=X` | Bulk block fetch (up to 10) | Used during backfill for efficiency |
| WebSocket `wss://mempool.space/api/v1/ws` | Real-time new block notifications | Send `{"action":"want","data":["blocks"]}`; receive `{block:{...}}` messages |

**Critical caveat (LOW confidence):** It is not confirmed whether `GET /api/blocks/:height` returns all competing blocks at a height (including stale ones) or only the canonical one. If it returns only the canonical block, orphan detection must work differently — e.g., tracking block hashes seen via WebSocket and retroactively checking status after chain resolves. This must be verified early in development.

---

## Patterns to Follow

### Pattern 1: Backfill Cursor in SQLite

Store the last successfully processed height in a `sync_state` table. On crash/restart, resume from cursor rather than restarting from genesis.

```typescript
// sync_state table
CREATE TABLE sync_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
-- keys: 'backfill_complete' (0/1), 'backfill_cursor' (height number)
```

### Pattern 2: Fork Detection via Height Collision

A fork event is detected when two or more distinct block hashes exist at the same height in the `blocks` table with `in_best_chain` values of mixed true/false. Write a single `fork_events` row when this is resolved (canonical block known).

```typescript
// fork_events table
CREATE TABLE fork_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  height INTEGER NOT NULL,
  canonical_hash TEXT NOT NULL,
  stale_hash TEXT NOT NULL,
  detected_at INTEGER NOT NULL  -- unix timestamp
);
```

### Pattern 3: SSE Over WebSocket for Dashboard

The dashboard is read-only and only needs server-push. Use `text/event-stream` (SSE) from the Express server to the browser. Simpler than a second WebSocket server, works over HTTP/2 multiplexing, has built-in browser reconnection. The Node.js process connects outbound to mempool.space WebSocket; the browser connects inbound to the local SSE endpoint.

```typescript
// Express SSE endpoint
app.get('/api/events', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  const send = (event: string, data: unknown) =>
    res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
  emitter.on('new_block', (block) => send('block', block));
  emitter.on('new_fork', (fork) => send('fork', fork));
  req.on('close', () => { /* cleanup listeners */ });
});
```

### Pattern 4: Synchronous SQLite Writes

Use `better-sqlite3` (synchronous API) for all database writes. Avoids callback/promise complexity for a single-process tool. Throughput is more than sufficient for this data volume (max ~4,000 fork events ever, ~880,000 block rows total — well under 1MB).

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Per-Block REST Polling for New Blocks

**What:** Polling `GET /api/blocks/tip/height` every few seconds as the primary detection mechanism.
**Why bad:** Adds unnecessary latency (up to 60s between polls), wastes API quota, misses the ~2-second window when competing blocks both exist before one is orphaned.
**Instead:** Use mempool.space WebSocket as primary; REST polling only as fallback.

### Anti-Pattern 2: Scanning All Heights for Orphans During Live Monitoring

**What:** On every new block, re-checking status of the last N blocks to find newly orphaned ones.
**Why bad:** Redundant API calls; mempool.space WebSocket already delivers new blocks in real-time.
**Instead:** Check status only for blocks that arrived via the WebSocket feed at the same height as a previously seen block. Orphans are resolved within one block (~10 min) — a short confirmation window of 2 blocks suffices.

### Anti-Pattern 3: Storing Full Block Data

**What:** Fetching and storing full transaction lists, raw block hex, etc.
**Why bad:** Unnecessary volume; full block is ~1–4MB each × 880,000 blocks.
**Instead:** Store only: hash, height, timestamp, in_best_chain, size (optional). The dashboard only needs summary statistics and fork event records.

### Anti-Pattern 4: Separate Processes for Poller and API Server

**What:** Running the backfill worker, poller, and API server as separate OS processes communicating via IPC or a message broker.
**Why bad:** Adds operational complexity for a personal tool; in-process EventEmitter is sufficient at this data rate (one block per ~10 minutes).
**Instead:** Single Node.js process with internal event bus.

---

## Suggested Build Order

Dependencies flow from data layer outward:

```
1. SQLite schema + migrations
   ├── blocks, fork_events, sync_state tables
   └── No other component works without this

2. mempool.space API client module
   ├── REST: getBlocksAtHeight, getBlockStatus, getTipHeight
   ├── WebSocket: subscribe to blocks feed
   └── Rate-limit throttle (100ms min between REST requests)

3. Backfill Worker
   ├── Depends on: SQLite schema, API client
   └── Can be tested end-to-end with a small height range

4. Fork Detector
   ├── Depends on: SQLite schema, API client
   └── Can be unit-tested with mock API responses

5. Poller (live monitoring)
   ├── Depends on: API client, Fork Detector
   └── Integrates WebSocket + fallback polling

6. HTTP/SSE API Server
   ├── Depends on: SQLite schema (read-only queries)
   └── Emits SSE events from Poller/Fork Detector EventEmitter

7. Frontend Dashboard
   ├── Depends on: HTTP/SSE Server being running
   └── Can be built with static mock data initially
```

---

## Scalability Considerations

Not a concern for this project — personal tool, local only. However:

| Concern | Current approach | If it ever mattered |
|---------|-----------------|---------------------|
| Data volume | SQLite, ~1MB total | PostgreSQL at >1GB |
| Concurrent readers | Single user, SSE | Add connection pooling |
| API rate limits | 100ms throttle on backfill | Self-host mempool.space instance |
| Backfill time | ~1 hour for full history | Incremental restart via cursor handles crashes |

---

## Open Questions

1. **Does `GET /api/blocks/:height` return stale/orphaned blocks or only the canonical block?** This is the single most important API question. If it returns only the canonical block, the backfill fork detection strategy must change — potentially requiring tracking blocks seen via the WebSocket and retrospectively checking their status. Must verify against actual API response before building the backfill worker.

2. **WebSocket reconnection behavior:** mempool.space WebSocket occasionally drops. What is the correct backfill-on-reconnect strategy — re-check the last N tip heights to catch any blocks missed during the outage?

3. **Stale block window:** After a fork, how long does mempool.space take to update `in_best_chain` to `false` for the losing block? If there is a delay, the live monitor may need to re-check recently seen blocks 1–2 blocks later.

---

## Sources

- [mempool.space REST API documentation](https://mempool.space/docs/api/rest) — MEDIUM confidence (docs visible in search snippets, not WebFetched directly)
- [mempool.space WebSocket API documentation](https://mempool.space/docs/api/websocket) — MEDIUM confidence (subscription format confirmed via multiple sources)
- [mempool/mempool.js README](https://github.com/mempool/mempool.js/blob/main/README-bitcoin.md) — MEDIUM confidence
- [0xB10C/fork-observer](https://github.com/0xB10C/fork-observer) — MEDIUM confidence (architecture described via search; uses Bitcoin Core RPC, not mempool.space)
- [better-sqlite3](https://github.com/WiseLibs/better-sqlite3) — HIGH confidence (npm, well-established)
- [SSE vs WebSocket comparison](https://systemdesignschool.io/blog/server-sent-events-vs-websocket) — MEDIUM confidence (multiple corroborating sources)
- [mempool.space rate limits discussion](https://github.com/mempool/mempool/discussions/752) — LOW confidence (community discussion, not official documentation)
