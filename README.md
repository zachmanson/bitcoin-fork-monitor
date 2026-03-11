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

## Seeding historical orphan data

A CSV of known historical orphaned blocks can be imported with:

```bash
python seed_stale_blocks.py
```

This populates the database with real historical fork events so the dashboard has data to display immediately.
