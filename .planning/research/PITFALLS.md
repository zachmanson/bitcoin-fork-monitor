# Domain Pitfalls: Bitcoin Fork Monitor

**Domain:** Bitcoin blockchain fork detection / orphan block monitoring via public API
**Researched:** 2026-03-09
**Overall confidence:** MEDIUM — core pitfalls verified across multiple sources; some mempool.space specifics (undisclosed rate limits, exact pagination) rely on community reports rather than official docs.

---

## Critical Pitfalls

Mistakes that cause rewrites, data corruption, or fundamentally wrong outputs.

---

### Pitfall 1: Treating Block Height as a Stable Identifier Near the Chain Tip

**What goes wrong:** During live monitoring, a block is stored keyed by height (e.g., height 880123). A reorg occurs and the block at that height is replaced. The application now has stale or duplicate records — the orphaned block may have been overwritten, or the new canonical block is treated as already-seen.

**Why it happens:** Block height is intuitive and works for finalized history, but it is NOT a unique identifier. Two competing blocks can share the same height simultaneously during a fork. The block *hash* is the only stable, collision-free reference.

**Consequences:** Silent data corruption. Orphan events missed or double-counted. Stale rate calculation becomes wrong without any visible error.

**Prevention:** Use block hash as the primary key everywhere. When a new block arrives at a height already in the database, that is a fork event — record both the canonical block and the orphaned block with their hashes. Never upsert-by-height during live monitoring.

**Detection:** If your stale rate ever shows 0% after several days of live monitoring, check whether height-based deduplication is silently discarding orphan records.

**Phase:** Address in the core data model before any persistence layer is built (foundation phase).

---

### Pitfall 2: Backfill Will Hit mempool.space Rate Limits

**What goes wrong:** Naively iterating through all ~880,000 historical blocks at full speed (e.g., one request per block, no delay) will trigger HTTP 429 responses from mempool.space. Repeated violations can result in IP bans. The rate limits are deliberately undisclosed — the project's own GitHub discussion (#752) states: "if you have to ask, you will hit them."

**Why it happens:** Backfilling 880,000 blocks one at a time would require hundreds of thousands of requests. Even paginated endpoints returning 10–25 blocks per call require 35,000–88,000 requests. Public APIs don't tolerate sustained bulk traffic.

**Consequences:** Backfill stalls mid-run, leaving the database in a partial state. An IP ban breaks live monitoring too, not just backfill. Resuming after a ban requires extra state tracking.

**Prevention:**
1. Implement a conservative request delay from the start (e.g., 200–500ms between requests, yielding 2–5 req/s).
2. Implement exponential backoff with jitter on every 429 response — do not just sleep a fixed interval.
3. Checkpoint progress (last successfully processed block hash + height) so backfill can resume after interruption without restarting from genesis.
4. Use the paginated bulk blocks endpoint (`GET /api/v1/blocks/:startHeight`) which returns multiple blocks per call, minimizing total requests.

**Detection:** Watch for HTTP 429 in backfill logs. Add a circuit-breaker that pauses and alerts rather than hammering through errors.

**Phase:** Design the rate-limit and checkpoint strategy before writing backfill code (backfill phase). Do NOT prototype without rate limiting, as the IP block will affect all subsequent development.

---

### Pitfall 3: Assuming All Historical Orphan Blocks Are Captured by Any Single API

**What goes wrong:** The project assumes mempool.space's historical orphan/stale block data is complete and accurate for all 880,000 blocks back to genesis. In practice, orphan data before roughly 2013–2015 is sparse or unreliable across all public APIs. Academic research has found stale blocks in historical data that were not captured by conventional live monitoring approaches.

**Why it happens:** Orphan blocks must be *observed* at the network level when they occur. Before widespread monitoring infrastructure existed, many early orphans were never indexed. APIs like mempool.space rely on Bitcoin Core's electrs-based indexing, which tracks which blocks are in the best chain — but orphaned competitors to early blocks may not exist in the indexed dataset at all.

**Consequences:** The stale rate calculation for the full historical period will undercount orphans for the early blockchain (roughly blocks 0–250,000). Displaying "100% accurate stale rate since genesis" is misleading when early data is structurally incomplete.

**Prevention:**
1. When displaying stale rate charts, segment by era: pre-2013 data is best-effort, post-2015 data is reliable.
2. Query mempool.space's block status endpoint for blocks in the historical range and count `in_best_chain: false` results — but document that gaps in early data are expected, not bugs.
3. Surface a data confidence note in the UI for the pre-2015 period.

**Detection:** If zero orphans appear for any 6-month window before 2013 (when the stale rate should have been higher, 1–2%), that is a data completeness gap, not evidence of a perfect network.

**Phase:** UI/display phase — ensure charts and stats panel communicate data reliability by era. Document the limitation in ARCHITECTURE.md so the roadmap doesn't promise "complete history."

---

### Pitfall 4: WebSocket Disconnect Silently Drops Orphan Events

**What goes wrong:** The application subscribes to mempool.space's WebSocket for live block notifications. The WebSocket disconnects (network hiccup, server restart, keepalive failure). The reconnect logic re-subscribes and resumes from the *current* chain tip — silently skipping all blocks that arrived during the disconnection window. Any fork events in that gap are permanently lost.

**Why it happens:** WebSocket reconnection restores the channel but does not replay missed events. New-block WebSocket messages are fire-and-forget; there is no replay or catch-up mechanism in the mempool.space WebSocket API.

**Consequences:** Gaps in the live fork log. Stale rate calculation for the live period undercounts orphans. The gap is invisible to the user unless explicit continuity checking is built in.

**Prevention:**
1. Track the hash and height of the last successfully processed block.
2. On reconnect: query the REST API for all blocks between `lastKnownHeight` and current tip, process them in order, *then* resume WebSocket subscription.
3. Implement WebSocket heartbeat/ping monitoring — treat silence beyond 30–60 seconds as a disconnection requiring reconnect.
4. Log all reconnect events with the gap window so gaps are visible in operational logs.

**Detection:** After any WebSocket reconnect, compare the `previous_block_hash` of the first post-reconnect block against the `hash` of the last stored block. Mismatch means blocks were missed.

**Phase:** Live monitoring phase. Must be designed before the WebSocket integration is considered "done."

---

### Pitfall 5: Stale Rate Denominator Ambiguity Produces Misleading Statistics

**What goes wrong:** The stale rate calculation uses the wrong denominator, producing a number that looks plausible but measures something subtly different from what is displayed. Common wrong denominators:
- Only canonical blocks (undercounts total work, slightly inflates stale rate)
- Only the range of heights with known orphans (inflates rate by ignoring orphan-free windows)
- Distinct block heights (correct) vs. total block records (double-counts heights with forks)

**Why it happens:** The formula "orphaned blocks / total blocks" is ambiguous: does "total blocks" mean total canonical blocks mined, or total blocks attempted (canonical + stale)? The correct formula for stale rate is: `stale_count / (canonical_count + stale_count)`. Using just `canonical_count` in the denominator is technically wrong but close to correct at low stale rates (0.1%), becoming meaningless at higher rates.

**Consequences:** A slightly wrong formula goes unnoticed because stale rates are so low (~0.1–0.5%) that the numerical difference is small. But it makes comparisons to published academic stale rates unreliable, and the formula is wrong by definition.

**Prevention:** Explicitly define and document the formula before implementation: `stale_rate = stale_count / (canonical_count + stale_count)`. Count stale blocks as any block with `in_best_chain: false`. Count canonical blocks as any block with `in_best_chain: true`. The denominator is the sum of both.

**Detection:** Cross-check your calculated stale rate against published figures (blockchain.com chart of orphaned blocks per day, academic measurements of ~0.41% in 2016). A 2–3x discrepancy indicates a denominator bug.

**Phase:** Data model and stats calculation phase. Define this before writing any aggregation queries.

---

## Moderate Pitfalls

---

### Pitfall 6: Conflating "Orphan Block" and "Stale Block" Terminology in Code and UI

**What goes wrong:** The codebase mixes the terms "orphan" and "stale" inconsistently. Since Bitcoin Core v0.10 (2015), true orphan blocks (blocks whose parent hash is unknown) are impossible due to headers-first sync. What this project actually tracks are *stale blocks* — valid blocks that lost the race to be included in the longest chain and whose parent IS known. Using "orphan" for both concepts in code makes it harder to reason about the data.

**Why it happens:** The terms are used interchangeably in popular writing, Bitcoin Core's wallet UI labels block rewards from stale blocks as "orphaned," and mempool.space itself may use both terms.

**Prevention:** Choose one term per concept in code: use `stale_block` for what this project tracks (valid blocks not in best chain), and avoid `orphan` unless specifically referring to the pre-2015 phenomenon. Comment the distinction in schema definitions.

**Phase:** Foundation/data model phase.

---

### Pitfall 7: Backfill State Not Surviving Process Restart

**What goes wrong:** Backfill runs for hours through 800,000 blocks. The process crashes or is restarted. Without checkpointing, backfill restarts from genesis, re-requesting hundreds of thousands of blocks and risking rate limit bans.

**Why it happens:** Simple implementations track progress in memory only. A crash loses all progress.

**Prevention:** Persist the last-successfully-processed `(height, hash)` pair to the local database after each batch commit. On startup, check for a backfill checkpoint and resume from it. Design backfill as idempotent: re-processing an already-stored block with the same hash is a no-op, not an error.

**Phase:** Backfill phase — design checkpoint persistence before writing backfill loop.

---

### Pitfall 8: No Fallback When mempool.space is Unavailable

**What goes wrong:** The application has a single data source (mempool.space). During outages or rate-limit bans, both live monitoring and backfill halt completely with no degraded mode.

**Why it happens:** Building against one API is simpler. Fallback paths are added "later."

**Prevention:**
1. Design the data layer to be source-agnostic: a `BlockDataSource` interface with one mempool.space implementation.
2. For the personal-use scope of this project, a fallback to blockstream.info (which exposes similar block status endpoints) provides resilience without significant complexity.
3. Alternatively, expose the self-hosted mempool instance option — mempool is open-source and can be run locally with a Bitcoin full node.

**Phase:** Architecture/foundation phase for the interface definition; fallback implementation can be deferred.

---

## Minor Pitfalls

---

### Pitfall 9: Displaying Fork Events Before Chain Resolution

**What goes wrong:** A block arrives and is immediately displayed as "canonical" or as a "fork event" before the network has resolved the competing chain. Within 1–3 blocks (10–30 minutes), a reorg may flip which block is canonical. The UI shows incorrect information during this window.

**Prevention:** Mark the most recent N blocks (N = 3 is a reasonable safety margin) as "unconfirmed" or "pending resolution" in the UI. Only show definitive fork/orphan status for blocks with at least 3 confirmations.

**Phase:** UI/display phase.

---

### Pitfall 10: Assuming the mempool.space WebSocket Pushes Orphan Notifications Directly

**What goes wrong:** The developer assumes the WebSocket will emit an event specifically when a block becomes orphaned. In reality, the WebSocket pushes new-block notifications. Orphan detection requires the application to notice when two different blocks share the same height, or when a new block's `previousblockhash` skips over the locally stored tip — inferring the orphan event from block sequence, not from a dedicated notification.

**Prevention:** Implement local chain-tip state tracking. On each new-block WebSocket event: compare `block.previousblockhash` against the stored tip hash. A mismatch means a reorg occurred; query the REST API for the competing block(s) at that height to record the orphan.

**Phase:** Live monitoring phase.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Data model design | Stale vs. orphan term confusion; height-as-key | Define schema with hash as PK before writing any code |
| Backfill implementation | Rate limits cause IP ban mid-backfill | Implement rate limiting + checkpointing before first run |
| Backfill implementation | Process crash loses all progress | Persist checkpoint to DB after each batch |
| Live monitoring | WebSocket disconnect drops orphan events | Gap-fill logic on reconnect using REST API |
| Live monitoring | No orphan notification from WebSocket | Infer orphans from block sequence comparison |
| Stats/aggregation | Wrong stale rate denominator | Document and test formula explicitly |
| UI/display | Premature orphan labeling before chain resolves | Mark recent blocks as unresolved |
| Data display | Pre-2015 historical data presented as complete | Add era-based data confidence notes |

---

## Sources

- mempool.space rate limit discussion (undisclosed limits, community-confirmed): https://github.com/mempool/mempool/discussions/752
- mempool.space rate limit documentation discoverability issue: https://github.com/mempool/mempool/issues/4106
- mempool.space WebSocket API reference: https://mempool.space/docs/api/websocket
- QuickNode: Reorg handling, block height vs. hash reliability: https://www.quicknode.com/docs/streams/reorg-handling
- QuickNode blog on reorgs and block numbers: https://blog.quicknode.com/understanding-blockchain-reorgs-why-block-numbers-dont-matter-as-much-as-you-think/
- Bitcoin developer reference (block chain, hash linkage): https://developer.bitcoin.org/reference/block_chain.html
- Hashrate Index: Stale block vs orphan block overview: https://hashrateindex.com/blog/what-are-orphan-blocks-and-stale-blocks-an-overview/
- Lightspark: Stale block definition and history: https://www.lightspark.com/glossary/stale-block
- Bitcoin Wiki: Orphan Block (terminology, historical context): https://en.bitcoin.it/wiki/Orphan_Block
- D-Central: Orphan blocks historical data reliability: https://d-central.tech/orphan-blocks-the-overlooked-pieces-of-bitcoins-blockchain-puzzle/
- Curvegrid: WebSocket vs polling for blockchain monitoring: https://www.curvegrid.com/blog/2024-01-17-blockchain-event-monitoring-possibilities-with-multibaas-polling-websockets-and-webhooks
- Academic paper on recovering blockchain metrics / stale block undercounting: https://eprint.iacr.org/2018/1134.pdf
- CoinMetrics Reorg & Fork Tracker documentation: https://gitbook-docs.coinmetrics.io/network-data/cm-labs/reorg-and-fork-tracker-overview
