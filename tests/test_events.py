"""
Unit tests for the EventBus thread-to-async bridge.

These tests verify that EventBus correctly manages per-client queues and that
notify() safely delivers events from a background thread to asyncio subscribers.

The tricky test here is test_notify_with_loop_enqueues: it spins up a real
asyncio event loop in a background thread (simulating the FastAPI event loop),
registers it with the bus, then calls notify() from yet another thread (the
test thread, simulating the monitor thread). This exercises the exact cross-
thread call path that the production code uses.
"""

import asyncio
import threading
import time

import pytest

from app.events import EventBus


def test_subscribe_returns_queue():
    """subscribe() should return an asyncio.Queue instance."""
    bus = EventBus()
    q = bus.subscribe()
    assert isinstance(q, asyncio.Queue)


def test_unsubscribe_removes_queue():
    """After unsubscribe(), the queue should no longer be in _subscribers."""
    bus = EventBus()
    q = bus.subscribe()
    assert q in bus._subscribers
    bus.unsubscribe(q)
    assert q not in bus._subscribers


def test_unsubscribe_nonexistent_is_noop():
    """Calling unsubscribe() with a queue not in the list should not raise."""
    bus = EventBus()
    q = asyncio.Queue()
    bus.unsubscribe(q)  # Should not raise


def test_notify_without_loop_is_noop():
    """
    Calling notify() before set_loop() is called should not raise.

    During the brief startup window between process start and the event loop
    becoming ready, the monitor thread might theoretically call notify() —
    this must be a silent no-op, not a crash.
    """
    bus = EventBus()
    q = bus.subscribe()
    bus.notify({"type": "block"})  # _loop is None — must not raise


def test_notify_with_loop_enqueues():
    """
    notify() called from a background thread should deliver data to the queue.

    This test simulates the production setup:
        - A real asyncio event loop runs in a daemon thread (like FastAPI's loop).
        - The bus's set_loop() is called with that loop.
        - notify() is called from the test thread (like the monitor thread).
        - The subscriber queue should receive the data within 1 second.

    Key: asyncio.run_coroutine_threadsafe schedules q.put() on the event loop
    thread, so we need the loop actually running (loop.run_forever()) to process
    it. The 0.1s sleep gives the scheduled coroutine time to execute.

    We retrieve the result by scheduling q.get() onto the running loop from the
    test thread using run_coroutine_threadsafe(), then blocking on the resulting
    concurrent.futures.Future. We cannot call loop.run_until_complete() while
    the loop is already running in another thread — that would raise RuntimeError.
    """
    loop = asyncio.new_event_loop()
    bus = EventBus()
    bus.set_loop(loop)
    q = bus.subscribe()

    # Start the event loop in a daemon thread — mirrors FastAPI's event loop
    # running in the main thread while the monitor runs in a background thread.
    def run_loop():
        loop.run_forever()

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()

    # notify() from the test thread — this is the cross-thread call path
    bus.notify({"type": "block"})

    # Give run_coroutine_threadsafe time to schedule and execute q.put()
    time.sleep(0.1)

    # Retrieve the result: schedule q.get() onto the running loop, then block
    # on the concurrent.futures.Future it returns. This is the correct way to
    # call into an already-running event loop from an outside thread.
    future = asyncio.run_coroutine_threadsafe(
        asyncio.wait_for(q.get(), timeout=1.0),
        loop,
    )
    result = future.result(timeout=2.0)
    assert result == {"type": "block"}

    # Clean up: stop the event loop thread
    loop.call_soon_threadsafe(loop.stop)
    t.join(timeout=2.0)
