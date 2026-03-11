# Bitcoin Fork Monitor

This was my first time using Claude Code to develop an entire project from scratch — front to back. Every design decision, architecture choice, and line of code was built collaboratively through conversation. It was a genuine learning experience: I came in with a strong Python background but limited web dev experience, and this project introduced me to FastAPI, SQLModel, SvelteKit, Server-Sent Events, and the full lifecycle of building and shipping a real web application.

---

## What it does

Bitcoin Fork Monitor tracks temporary forks (also called orphaned blocks or stale blocks) on the Bitcoin blockchain in real time.

When two miners find a valid block at the same height at nearly the same time, the network briefly has two competing chains. One eventually wins (becomes "canonical") and the other is discarded ("orphaned"). These events are rare but real, and they reveal something interesting about how a decentralized consensus system heals itself.

This app:

- **Backfills historical fork data** by pulling block history from a public Bitcoin API and detecting any heights where multiple valid block hashes existed
- **Monitors the live chain** via a WebSocket connection to a Bitcoin node, detecting new forks as they happen
- **Stores everything** in a local SQLite database using SQLModel (a type-safe ORM built on SQLAlchemy + Pydantic)
- **Serves a REST API** via FastAPI with endpoints for fork events, block data, sync state, and analytics
- **Streams live updates** to connected clients using Server-Sent Events (SSE), so the dashboard refreshes automatically without polling
- **Displays a real-time dashboard** built with SvelteKit showing recent forks, chain stats, and analytics charts

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI |
| Database | SQLite via SQLModel |
| Live updates | Server-Sent Events (SSE) |
| Frontend | SvelteKit |
| Bitcoin data | Public block explorer API + WebSocket |

---

## Running locally

**Backend:**
```bash
pip install -e .
uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

The API will be at `http://localhost:8000` and the dashboard at `http://localhost:5173`.

---

## Backfill and historical data

When you first run the app, it will automatically begin backfilling block history from the [mempool.space](https://mempool.space) public API. This works by fetching blocks page by page and recording any heights where two different block hashes existed — those are forks.

**This takes a while.** The Bitcoin chain is ~880,000 blocks deep. The backfill is throttled to be respectful of the API, so expect it to run in the background for several hours before the database is fully populated. The app is usable while it runs — the dashboard will show data as it comes in.

Progress is checkpointed, so if you restart the server the backfill resumes from where it left off.

### Seeding known historical orphans (faster start)

For a quicker way to populate fork events, you can seed from a crowd-sourced dataset of known stale blocks (~2,000 orphans going back to 2011):

```bash
python seed_stale_blocks.py
```

This downloads a CSV from [bitcoin-data/stale-blocks](https://github.com/bitcoin-data/stale-blocks) and imports it directly. Run it once the backfill has made some progress (so canonical block hashes are available in the DB). It's safe to re-run — all inserts are guarded against duplicates.
