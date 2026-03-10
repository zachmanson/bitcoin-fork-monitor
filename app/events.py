"""
Thread-to-async event bridge for bitcoin-fork-monitor.

The monitor thread runs in a background OS thread (not the asyncio event loop)
and calls event_bus.notify() each time a new block is processed. SSE client
connections live in the asyncio event loop. This module bridges that gap.

Why per-client queues?
    Each SSE connection (browser tab) subscribes with its own asyncio.Queue.
    A shared queue would let the first reader steal events from all other
    subscribers — the second tab would never see a block it didn't consume
    first. Per-client queues ensure every connected tab receives every event.

Why asyncio.run_coroutine_threadsafe?
    asyncio.Queue is not thread-safe. You cannot call queue.put_nowait() from
    a different OS thread — it will corrupt the event loop's internal state.
    run_coroutine_threadsafe() is the only correct way to schedule a coroutine
    from outside the event loop's thread. It posts a callback to the loop's
    thread-safe queue and returns a concurrent.futures.Future.

Pattern: Pattern 3 from the phase research doc — one Queue per subscriber,
    notify() schedules put() via run_coroutine_threadsafe, set_loop() captures
    the running event loop reference before threads start.
"""

import asyncio
from typing import Optional


class EventBus:
    """
    Thread-safe event broadcaster for SSE clients.

    The monitor thread calls notify() after processing each block. The SSE
    endpoint (Plan 02) subscribes to receive those events as asyncio.Queues
    that it can await without blocking the event loop.

    Lifecycle:
        1. main.py lifespan calls set_loop() before any threads start.
        2. SSE handler calls subscribe() to get a dedicated queue.
        3. Monitor thread calls notify() — each subscriber's queue gets the data.
        4. SSE handler calls unsubscribe() on disconnect (or when generator exits).
    """

    def __init__(self) -> None:
        # One Queue per active SSE client connection.
        self._subscribers: list[asyncio.Queue] = []
        # The running asyncio event loop. Set by set_loop() before threads start.
        # None means no loop has been registered yet — notify() is a no-op until set.
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Store a reference to the running event loop.

        Must be called from the asyncio thread (main.py lifespan) before any
        background threads start calling notify(). After this point, notify()
        can safely schedule coroutines on the loop from other threads.

        Args:
            loop: The running event loop from the FastAPI lifespan context.
        """
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        """
        Register a new SSE client and return its dedicated event queue.

        The queue has a maxsize of 100 to bound memory usage. If the SSE client
        is too slow to consume events, put() will block (in the event loop) —
        this is acceptable because we process Bitcoin blocks roughly once per
        10 minutes in normal operation.

        Returns:
            asyncio.Queue: A queue that will receive event dicts from notify().
        """
        # maxsize=100 caps memory if a slow client falls behind
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """
        Remove a client's queue from the subscriber list.

        Called by the SSE generator when the client disconnects. Silently
        ignores the case where q is not in the list (e.g., double-unsubscribe).

        Args:
            q: The queue previously returned by subscribe().
        """
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass  # Already removed — that's fine

    def notify(self, data: dict) -> None:
        """
        Broadcast data to all active SSE subscribers.

        Called from the monitor background thread after each block is processed.
        Thread-safe: uses run_coroutine_threadsafe to enqueue data on the
        asyncio event loop without touching the Queue from the wrong thread.

        If no loop has been registered yet (set_loop not called), this is a
        no-op. This can happen during startup before the event loop is running.

        Args:
            data: The event payload to broadcast (e.g., block metadata dict).
        """
        if self._loop is None:
            return

        # Snapshot the list before iterating — subscribers may be added/removed
        # concurrently by SSE handlers on the event loop thread.
        for q in list(self._subscribers):
            # Schedule q.put(data) on the event loop from this background thread.
            # This is the correct API for cross-thread asyncio communication.
            asyncio.run_coroutine_threadsafe(q.put(data), self._loop)


# Module-level singleton — imported by monitor.py (notify) and the SSE
# endpoint (subscribe/unsubscribe). One bus serves all clients.
event_bus = EventBus()
