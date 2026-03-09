# Feature Landscape

**Domain:** Bitcoin blockchain fork monitoring / network health dashboard
**Researched:** 2026-03-09

## Table Stakes

Features users expect from any blockchain monitoring dashboard. Missing any of these makes the product feel incomplete or broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Live block feed | Any monitoring tool shows latest blocks in real time — this is the heartbeat of the dashboard | Low | mempool.space WebSocket API provides block events; poll REST as fallback |
| Block height + timestamp display | Every block explorer shows this; it's the minimum useful block metadata | Low | Height, timestamp, miner (coinbase), size/weight |
| Fork/orphan event detection | Core purpose of the tool; detecting when two competing blocks exist at the same height | Medium | Requires comparing block-at-height across canonical and orphaned chains |
| Orphan event log | Tabular history of detected fork events (date, height, competing block hashes, winner) | Low | Table with pagination; filters by date range |
| Stale rate (summary stat) | The headline metric — what percentage of all blocks ever mined were orphaned | Low | Calculated as orphaned blocks / (canonical + orphaned blocks) |
| Stale rate over time chart | Expected from any analytics dashboard; shows trends visually | Medium | Time-series chart; weekly/monthly aggregation; requires Chart.js or similar |
| Data persistence | Without persistence, every restart loses data and requires re-backfill | Medium | SQLite or flat file; must survive process restart |
| Backfill on first run | Without full history, stale rate is meaningless — partial data is misleading | High | Fetch all historical orphan events from mempool.space; can take minutes |
| Summary stats panel | At-a-glance numbers: total canonical blocks, total orphaned, stale rate, last fork date | Low | Derived from stored data; refreshes on new blocks |

## Differentiators

Features that set this tool apart from existing blockchain explorers. Not expected by default, but add meaningful value.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Rolling stale rate by epoch | Stale rate has declined sharply since 2017 (pool latency improvements); showing by difficulty epoch or year reveals this trend | Medium | Segment by ~2016-block difficulty windows or calendar year |
| Fork resolution time | How many seconds elapsed between competing blocks and the canonical winner being determined | Medium | Requires block timestamp of both competing blocks |
| Competing miner attribution | Which mining pool mined the orphaned block vs the winner — reveals propagation advantages | Medium | Parse coinbase transaction of orphaned blocks; map to known pool addresses |
| Stale rate vs hashrate overlay | Correlating stale rate with network hashrate growth could reveal propagation quality trends | High | Requires fetching additional hashrate data; visual correlation chart |
| Per-year / per-month orphan count table | Raw counts broken down by time period, useful for research | Low | Simple GROUP BY on stored data |
| Block propagation delay context | DSN KIT research shows same-miner blocks within 100s are notable; flagging these is research-grade | High | Requires comparing miner identity across sequential orphan pairs |

## Anti-Features

Features to explicitly NOT build for this personal, single-user tool.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| User authentication | Personal tool, runs locally; auth adds complexity with zero value | Run on localhost; no auth layer |
| Push notifications / alerts | Project spec says passive recording only; alerts require notification infrastructure | Show a visual badge or browser tab indicator if desired later |
| Full blockchain graph visualization | ~880,000 blocks, rendering all as a DAG is a data volume problem — not worth it for v1 | Show orphan events as a table + minimal timeline chart |
| Multi-chain support (BCH, BSV, etc.) | Scope creep; each chain needs its own data source and logic | Hard-code to Bitcoin mainnet |
| Price overlay / market data | Not relevant to fork monitoring; adds noise | Omit entirely; focus on chain health metrics |
| Transaction-level data | Not needed for fork analysis; mempool transaction tracking is a different product | Only fetch block-level data |
| Mempool fee analysis | mempool.space already does this better; no need to duplicate | Link to mempool.space for fee data |
| Node connectivity monitoring | ForkMonitor.info (BitMEX) monitors 13 nodes; replicating this requires running nodes | Use API-based approach only |

## Feature Dependencies

```
Data Persistence
  └── Backfill on First Run (backfill writes to storage)
        └── Summary Stats Panel (derived from stored data)
        └── Stale Rate (summary stat) (derived from stored data)
        └── Stale Rate Over Time Chart (aggregated from stored data)
        └── Orphan Event Log (reads from stored data)

Live Block Feed
  └── Fork/Orphan Event Detection (detection happens on each new block)
        └── Orphan Event Log (new events appended)
        └── Summary Stats Panel (counts updated)
        └── Stale Rate (summary stat) (recalculated)

Fork/Orphan Event Detection
  └── Rolling Stale Rate by Epoch (differentiator, requires detected events)
  └── Fork Resolution Time (differentiator, requires competing block timestamps)
  └── Competing Miner Attribution (differentiator, requires orphaned block coinbase)
```

## MVP Recommendation

Prioritize for v1:

1. **Data persistence** — SQLite schema first; everything else writes to or reads from it
2. **Backfill on first run** — Fetch complete orphan history from mempool.space REST API; write to DB
3. **Fork/orphan event detection** — Poll mempool.space for new blocks; detect forks at same height
4. **Live block feed** — WebSocket or polling; show last N blocks in real time
5. **Orphan event log** — Table of all recorded fork events
6. **Stale rate summary stat** — Single number from DB counts
7. **Stale rate over time chart** — Weekly or monthly aggregated orphan rate line chart
8. **Summary stats panel** — Total blocks, total orphans, stale rate, last event

Defer:

- **Rolling stale rate by epoch** — Easy to add after MVP; requires no new data, just a GROUP BY
- **Fork resolution time** — Adds value but needs careful timestamp handling
- **Competing miner attribution** — Requires coinbase parsing logic; nice-to-have for research

## Data Source Reality Check

mempool.space is the only practical public API that tracks orphaned/stale blocks historically without running a full node. Key capabilities confirmed:

- REST endpoint `/api/v1/blocks` returns recent blocks with orphan status via `in_best_chain` flag
- WebSocket API supports block subscriptions (`wsWantData(['blocks'])`)
- Historical orphaned block data is available but may require iterating through block height ranges and checking `in_best_chain`
- Rate limits are not publicly disclosed; backfill must implement throttling/backoff

**Confidence: MEDIUM** — mempool.space API shape confirmed via search results and GitHub library docs; specific orphan history endpoint needs direct API verification during implementation.

## Competitive Landscape Context

| Tool | Focus | Gap This Project Fills |
|------|-------|------------------------|
| blockchain.com/charts/n-orphaned-blocks | Count chart only, no events list | Full event log + computed stale rate |
| forkmonitor.info (BitMEX) | Live consensus fork monitoring, node-connected | Historical orphan analysis, no node required |
| DSN KIT fork monitor | Academic research, propagation analysis | Accessible personal dashboard with persistence |
| coinmetrics.io reorg tracker | Enterprise, multi-chain | Free, Bitcoin-only, runs locally |
| mempool.space | Full block explorer, no fork-focused view | Dedicated fork/stale rate analytics |

## Sources

- [mempool.space REST API](https://mempool.space/docs/api/rest) — block status, orphan detection via `in_best_chain`
- [mempool.space WebSocket API](https://mempool.space/docs/api/websocket) — live block subscriptions
- [Blockchain.com Orphaned Blocks Chart](https://www.blockchain.com/charts/n-orphaned-blocks) — historical orphan count data
- [Hashrate Index: Orphan and Stale Blocks Overview](https://hashrateindex.com/blog/what-are-orphan-blocks-and-stale-blocks-an-overview/) — stale rate ~0.1-1% historically
- [Bitcoin DSN Fork Monitor (KIT)](https://www.dsn.kastel.kit.edu/bitcoin/forks/) — propagation analysis, competing miner patterns
- [CoinMetrics Reorg & Fork Tracker](https://gitbook-docs.coinmetrics.io/network-data/cm-labs/reorg-and-fork-tracker-overview) — blockchain tip monitoring features
- [Forkmonitor.info (BitMEX)](https://forkmonitor.info/) — node-connected consensus monitoring
- [BitMEX Fork Monitor Launch](https://bitcoinmagazine.com/technical/bitmex-launches-new-fork-monitoring-website-keep-track-bitcoin-forks) — feature intent and design rationale
- [Bitcoin Optech 2025 Year in Review](https://bitcoinops.org/en/newsletters/2025/12/19/) — block propagation and stale rate research context
