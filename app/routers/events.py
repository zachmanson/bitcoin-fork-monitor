"""
SSE (Server-Sent Events) endpoint for real-time block notifications.

This module exposes GET /api/events, which keeps a long-lived HTTP connection
open and pushes a server-sent event to the client every time the monitor thread
records a new Bitcoin block.

Why SSE instead of WebSockets?
    SSE is unidirectional: server → browser only. For a dashboard that only
    needs to receive block updates (not send anything back), SSE is simpler —
    no handshake protocol, no client library required, and the browser's built-in
    EventSource API reconnects automatically on drops. WebSockets add two-way
    complexity that this use case does not need.

Why per-client queue?
    Each browser tab that opens an EventSource connection calls subscribe() and
    gets its own asyncio.Queue. Events are pushed to every queue independently,
    so a slow tab cannot steal events from a fast tab — all connected clients
    receive every block notification.

Why asyncio.wait_for with a 15-second timeout?
    SSE connections are long-lived (minutes to hours between Bitcoin blocks).
    Without a timeout, the generator would await q.get() indefinitely on an idle
    connection. After 15 seconds with no block event, we send an SSE "comment"
    line (the keepalive). Comments are ignored by the browser's EventSource API
    but prevent proxy servers and browsers from closing an apparently idle
    connection.

Why request.is_disconnected()?
    Without this check, a closed browser tab leaves its queue in the subscriber
    list consuming memory. The generator checks for disconnect before each await
    so it can exit cleanly and trigger the finally block.
"""

import asyncio
from collections.abc import AsyncIterable

from fastapi import APIRouter, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.events import event_bus

# APIRouter groups related endpoints under a shared prefix and OpenAPI tag.
# This router is mounted in main.py via app.include_router(events.router).
router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events", response_class=EventSourceResponse)
async def sse_events(request: Request) -> AsyncIterable[ServerSentEvent]:
    """
    Stream real-time block events to a connected browser tab.

    Each connected client gets a dedicated asyncio.Queue (via event_bus.subscribe).
    The generator loops indefinitely, awaiting events from that queue with a 15-
    second timeout. On timeout it yields a keepalive comment. On client disconnect
    it breaks. The finally block always calls unsubscribe() to clean up the queue.

    Args:
        request: FastAPI injects this automatically. Used to poll is_disconnected().

    Yields:
        ServerSentEvent: One event per block notification, or a keepalive comment
        on 15-second idle intervals.
    """
    # Register this client. subscribe() returns a dedicated queue that will
    # receive every future notify() call until we call unsubscribe().
    q = event_bus.subscribe()

    # Count idle 1-second ticks. Send a keepalive every 15 idle ticks (= 15 seconds).
    # Using a 1-second inner timeout lets us detect client disconnects promptly
    # without waiting the full 15 seconds before reaching the is_disconnected() check.
    idle_ticks = 0
    KEEPALIVE_INTERVAL = 15  # number of 1-second idle ticks between keepalives

    try:
        while True:
            # Check for client disconnect before blocking on the queue.
            # is_disconnected() is a coroutine that returns True when the browser
            # tab has closed its connection. Without this, closed tabs accumulate.
            if await request.is_disconnected():
                break

            try:
                # Wait up to 1 second for the next block event.
                # A 1-second timeout keeps the disconnect check responsive — the
                # loop re-checks is_disconnected() every second rather than every
                # 15 seconds. Bitcoin blocks arrive roughly every 10 minutes, so
                # the queue is usually empty and we time out each tick.
                data = await asyncio.wait_for(q.get(), timeout=1.0)
                idle_ticks = 0  # reset idle counter on a real event
                # event="update" is the SSE event type name. The browser's
                # EventSource.addEventListener("update", handler) will match this.
                yield ServerSentEvent(data=data, event="update")
            except asyncio.TimeoutError:
                # No block this second — increment idle counter.
                idle_ticks += 1
                if idle_ticks >= KEEPALIVE_INTERVAL:
                    idle_ticks = 0
                    # SSE comments start with ":" and are ignored by EventSource.
                    # They exist only to prevent proxy/browser idle timeouts.
                    yield ServerSentEvent(comment="keepalive")
    finally:
        # Always remove this client's queue — even if an exception occurred.
        # This is the critical cleanup that prevents memory leaks.
        event_bus.unsubscribe(q)
