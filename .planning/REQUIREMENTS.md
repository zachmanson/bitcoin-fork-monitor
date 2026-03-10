# Requirements: Bitcoin Fork Monitor

**Defined:** 2026-03-09
**Core Value:** Real-time detection and historical analysis of Bitcoin temporary forks, with an accurate stale rate calculated across the full blockchain history.

## v1 Requirements

### Data Foundation

- [x] **DATA-01**: System persists block and orphan event data in a local SQLite database that survives process restarts
- [x] **DATA-02**: Block hash is used as primary key for all block records (not block height) to prevent silent orphan record loss
- [x] **DATA-03**: Stale rate is calculated as `orphaned_blocks / (canonical_blocks + orphaned_blocks)` — formula is enforced at the data layer

### Backfill

- [x] **BACK-01**: On first run, system backfills complete historical fork/orphan data from genesis via mempool.space API
- [x] **BACK-02**: Backfill progress is checkpointed to SQLite so a restart resumes where it left off rather than restarting from scratch
- [x] **BACK-03**: Backfill implements adaptive rate limiting and exponential backoff to avoid being blocked by mempool.space

### Live Monitoring

- [x] **MONI-01**: System subscribes to new Bitcoin blocks in real-time via mempool.space WebSocket API
- [x] **MONI-02**: System detects temporary forks when competing blocks appear at the same height and records orphaned blocks
- [x] **MONI-03**: System falls back to REST polling if WebSocket is unavailable and performs gap-fill on reconnect to avoid missed forks

### Dashboard

- [ ] **DASH-01**: User can view a live block feed showing the most recent blocks as they arrive, with fork events highlighted
- [x] **DASH-02**: User can view a summary stats panel showing: total canonical blocks, total orphaned blocks, current stale rate, date of last fork
- [ ] **DASH-03**: User can view a paginated fork event log showing: block height, date, orphaned block hash, canonical block hash, fork resolution time
- [ ] **DASH-04**: Dashboard receives real-time updates via Server-Sent Events (SSE) without requiring a page refresh

### Analytics

- [ ] **ANAL-01**: User can view a stale rate over time chart aggregated by week or month
- [ ] **ANAL-02**: User can view stale rate broken down by year or difficulty era, with a data confidence note for pre-2015 data
- [ ] **ANAL-03**: Fork resolution time (seconds between competing blocks) is recorded and displayed per fork event in the event log

## v2 Requirements

### Analytics

- **ANLV2-01**: Competing miner attribution — which mining pool mined the orphaned block vs the canonical winner (requires coinbase transaction parsing)
- **ANLV2-02**: Stale rate vs network hashrate overlay chart — correlate stale rate decline with hashrate growth
- **ANLV2-03**: Block propagation delay flagging — identify same-miner orphan pairs within short time windows

## Out of Scope

| Feature | Reason |
|---------|--------|
| User authentication | Personal tool, runs locally — auth adds complexity with zero value |
| Push notifications / alerts | Passive recording only — no alerting infrastructure needed |
| Full blockchain DAG visualization | ~880k blocks — data volume makes this impractical for v1 |
| Multi-chain support (BCH, BSV, etc.) | Scope creep; hard-code to Bitcoin mainnet |
| Price / market data overlay | Not relevant to fork monitoring; noise |
| Transaction-level data | Block-level data is sufficient for fork analysis |
| Node connectivity monitoring | API-based approach only; no running a full node |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Complete |
| DATA-02 | Phase 1 | Complete |
| DATA-03 | Phase 1 | Complete |
| BACK-01 | Phase 2 | Complete |
| BACK-02 | Phase 2 | Complete |
| BACK-03 | Phase 2 | Complete |
| MONI-01 | Phase 3 | Complete |
| MONI-02 | Phase 3 | Complete |
| MONI-03 | Phase 3 | Complete |
| DASH-01 | Phase 5 | Pending |
| DASH-02 | Phase 4 | Complete |
| DASH-03 | Phase 5 | Pending |
| DASH-04 | Phase 4 | Pending |
| ANAL-01 | Phase 5 | Pending |
| ANAL-02 | Phase 5 | Pending |
| ANAL-03 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 16 total
- Mapped to phases: 16
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-09*
*Last updated: 2026-03-09 after roadmap creation*
