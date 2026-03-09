"""
FastAPI application entrypoint for bitcoin-fork-monitor.

This module defines the FastAPI app instance and its lifespan context manager.
The lifespan is a professional pattern for managing startup/shutdown logic in
FastAPI apps — it replaces the older @app.on_event("startup") approach.

Startup sequence:
  1. Create database tables (idempotent, safe to call every restart).
  2. Check whether the historical backfill has already completed.
  3. If not complete, launch the backfill worker in a background thread.

Shutdown sequence:
  - If the backfill thread is still running, wait up to 5 seconds for it to
    finish gracefully. The thread is also marked daemon=True, so if the process
    is killed, the OS will clean it up automatically without waiting.

Why a background thread rather than an async task?
  The backfill worker performs synchronous I/O (httpx, SQLModel sessions) in a
  tight loop. Running it as an asyncio task would block the event loop and make
  the FastAPI server unresponsive to requests. A separate OS thread lets both
  run concurrently without blocking each other.

Why daemon=True?
  Daemon threads do not prevent the Python interpreter from exiting. If
  uvicorn receives a shutdown signal (e.g., Ctrl+C), it won't hang waiting for
  the backfill thread — the join(timeout=5.0) below gives it a short grace
  period, and then the process exits cleanly.
"""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import Session, select

from app.backfill import run_backfill
from app.database import create_db_and_tables, engine
from app.models import SyncState
from app.monitor import run_monitor

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown.

    On startup: initializes the database and conditionally starts the backfill
    background thread. On shutdown: gives the thread up to 5 seconds to finish.

    The `yield` in an asynccontextmanager lifespan is where FastAPI serves
    requests — everything before yield is startup, everything after is shutdown.
    """
    # --- Startup ---

    # Ensure all SQLModel tables exist. Safe to call on every restart.
    create_db_and_tables()

    # Initialize thread references to None so the shutdown block always has a
    # valid reference, even if a thread was never launched (e.g., backfill skipped).
    backfill_thread = None
    monitor_thread = None

    # Check whether a previous run already completed the full history backfill.
    # We open and immediately close a session here — this is intentional.
    # The backfill thread owns its own session for the duration of its work.
    with Session(engine) as session:
        state = session.exec(select(SyncState)).first()
        already_done = state is not None and state.backfill_complete

    if already_done:
        logger.info("Backfill already complete — skipping thread launch")
    else:
        logger.info("Starting backfill worker thread")
        backfill_thread = threading.Thread(
            target=run_backfill,
            daemon=True,       # does not block process exit
            name="backfill",   # visible in thread dumps and logs
        )
        backfill_thread.start()

    # Always launch the monitor thread, regardless of whether backfill ran.
    # The monitor gates on backfill_complete internally via _wait_for_backfill(),
    # so main.py does not need to know whether backfill is in progress or done —
    # the monitor will wait for the right moment to subscribe to the WebSocket.
    logger.info("Starting monitor thread (waits for backfill internally)")
    monitor_thread = threading.Thread(
        target=run_monitor,
        daemon=True,       # does not block process exit
        name="monitor",    # visible in thread dumps and logs
    )
    monitor_thread.start()

    yield  # FastAPI serves requests here

    # --- Shutdown ---

    # Give the backfill thread a short window to write its current checkpoint
    # before the process exits. 5 seconds is enough to finish the current page
    # commit without hanging indefinitely on a slow network call.
    if backfill_thread is not None and backfill_thread.is_alive():
        logger.info("Waiting for backfill thread to finish (timeout=5s)...")
        backfill_thread.join(timeout=5.0)

    if monitor_thread is not None and monitor_thread.is_alive():
        logger.info("Waiting for monitor thread to finish (timeout=5s)...")
        monitor_thread.join(timeout=5.0)


app = FastAPI(title="Bitcoin Fork Monitor", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    """Return server status. Used to confirm startup succeeded."""
    return {"status": "ok"}
