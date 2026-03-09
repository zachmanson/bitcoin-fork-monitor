# Bitcoin Fork Monitor

## What This Is

A personal web dashboard that monitors the Bitcoin blockchain for temporary forks — events where two miners produce competing blocks at the same height before the network resolves to a single canonical chain. It backfills full historical fork data on first run, tracks all orphaned/stale blocks, and displays live monitoring alongside historical analysis.

## Core Value

Real-time detection and historical analysis of Bitcoin temporary forks, with an accurate stale rate (orphaned blocks / total blocks) calculated across the full blockchain history.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Monitor new Bitcoin blocks via a public API (e.g. mempool.space) and detect fork events in real-time
- [ ] Backfill complete historical fork data from genesis on first run
- [ ] Calculate and display stale rate (total orphaned blocks / total blocks)
- [ ] Web dashboard with: live block feed, fork event log, stale rate over time chart, summary stats panel
- [ ] Persist fork and block data locally so backfill only runs once

### Out of Scope

- User authentication / multi-user — personal tool, runs locally
- Push notifications / alerts — passive recording only
- Full blockchain graph visualization — data volume too high, not worth it for v1

## Context

- Data source: mempool.space public API (tracks orphaned/stale blocks historically)
- Orphaned blocks are rare (~0.1–0.5% stale rate historically) — total dataset is tiny (< 1MB)
- Full history backfill is feasible: ~880,000 blocks but only ~1,000–4,000 fork events ever
- After backfill, monitoring is incremental — poll for new blocks and append fork events
- Personal use only — no hosting, auth, or multi-user concerns

## Constraints

- **API**: Must use a public Bitcoin API (no running a full node) — mempool.space preferred
- **Deployment**: Runs locally; no cloud hosting requirement
- **Data**: Stale/orphaned block data must be sourced from an API that tracks them (not inferrable from canonical chain alone)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use mempool.space as primary data source | Public, free, tracks historical orphaned blocks explicitly | — Pending |
| Full history backfill on first run | Data is tiny; complete stale rate is more meaningful than partial | — Pending |
| No real-time alerts | Passive monitoring suits the use case | — Pending |

---
*Last updated: 2026-03-09 after initialization*
