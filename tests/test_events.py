"""
Unit tests for the EventBus thread-to-async bridge and the SSE endpoint.

These tests verify that EventBus correctly manages per-client queues and that
notify() safely delivers events from a background thread to asyncio subscribers.

The tricky test here is test_notify_with_loop_enqueues: it spins up a real
asyncio event loop in a background thread (simulating the FastAPI event loop),
registers it with the bus, then calls notify() from yet another thread (the
test thread, simulating the monitor thread). This exercises the exact cross-
thread call path that the production code uses.

The SSE endpoint tests use TestClient in streaming mode to verify the
Content-Type header and cleanup behavior. TestClient does not support truly
long-lived SSE connections — it's synchronous — so these tests verify
connection setup and cleanup only, not full event delivery over time.
"""

import asyncio
import threading
import time
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.events import EventBus, event_bus
from app.main import app

# Module-level client — matches the pattern used in test_stats.py and test_forks.py.
# Using a module-level TestClient avoids triggering the app lifespan (startup/shutdown),
# which would start the monitor and backfill threads. Those threads are not needed
# for SSE endpoint tests, and their 5-second join timeouts would slow down the suite.
client = TestClient(app)


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


# ---------------------------------------------------------------------------
# SSE endpoint tests
# ---------------------------------------------------------------------------


def test_sse_content_type():
    """
    GET /api/events endpoint is registered and FastAPI sets Content-Type: text/event-stream.

    SSE is a browser standard: the server sets Content-Type: text/event-stream
    and the browser's built-in EventSource API handles the rest. We verify this
    by checking the route is registered in the app's route list and the response
    class is EventSourceResponse, which guarantees the correct content-type header.

    We also verify the /api/events path exists via the OpenAPI schema, which is a
    lightweight integration check that does not require opening a long-lived stream.

    Background: Starlette's TestClient runs ASGI requests synchronously — it blocks
    until the ASGI handler returns. An SSE endpoint streams forever (indefinite
    generator), so calling client.stream("/api/events") would block the test thread
    indefinitely. Testing headers via the route registry avoids this limitation.
    """
    # Check the endpoint is registered in the OpenAPI schema
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json().get("paths", {})
    assert "/api/events" in paths, "GET /api/events must appear in OpenAPI schema"

    # Verify the response class is EventSourceResponse — this guarantees
    # Content-Type: text/event-stream will be set when the endpoint is called.
    from app.routers.events import router
    from fastapi.sse import EventSourceResponse

    route = next(r for r in router.routes if r.path == "/api/events")
    assert route.response_class is EventSourceResponse


def test_sse_unsubscribe_on_disconnect():
    """
    The SSE generator must call event_bus.unsubscribe() in its finally block.

    We test this by running the async generator directly with a mocked Request
    that simulates an immediate disconnect. This verifies the try/finally
    cleanup logic without the TestClient blocking issue.

    Why mock Request?
        Starlette's TestClient runs ASGI calls synchronously until the handler
        returns. An infinite SSE generator never returns, so client.stream() blocks
        forever. Running the generator directly in asyncio bypasses the HTTP layer
        and tests the cleanup logic in isolation.

    Pattern:
        1. Create a fresh EventBus (isolated from module-level singleton)
        2. Build a mock Request whose is_disconnected() returns True immediately
        3. Inject the queue by calling subscribe() before running the generator
        4. Drive the generator one step — it should detect disconnect and exit
        5. Verify the subscriber list is empty after the generator finishes
    """
    from app.routers.events import sse_events

    async def run_test():
        # Use a fresh EventBus so this test is isolated from the module singleton.
        test_bus = EventBus()
        test_bus.set_loop(asyncio.get_event_loop())

        # Mock Request.is_disconnected() to return True on the first call.
        # This causes the generator to break immediately after subscribing.
        mock_request = AsyncMock()
        mock_request.is_disconnected.return_value = True

        # Temporarily patch the event_bus inside the router module so the
        # generator uses our test_bus instead of the module singleton.
        import app.routers.events as events_module
        original_bus = events_module.event_bus
        events_module.event_bus = test_bus

        try:
            # Collect events from the generator — it should exit after detecting disconnect.
            events = []
            async for event in sse_events(mock_request):
                events.append(event)
                break  # Safety: stop after first yield in case disconnect is slow

        finally:
            events_module.event_bus = original_bus

        # After the generator exits, the finally block should have called unsubscribe().
        assert len(test_bus._subscribers) == 0, (
            "Generator finally block must call event_bus.unsubscribe(q)"
        )

    asyncio.run(run_test())
