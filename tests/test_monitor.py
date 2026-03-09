"""
Unit tests for app/monitor.py — the live block monitoring thread.

All network I/O (WebSocket connections, HTTP calls) is mocked so tests
run without hitting the real network. The in-memory SQLite engine from
conftest.py is used for database operations.

Test strategy:
    Each test isolates one behavior of the monitor's state machine by patching
    the functions that interact with external systems. This is the professional
    approach to testing background workers: test behavior, not implementation.

Classes:
    TestWebSocketSubscribe  — WebSocket connect and subscription message
    TestBackfillGate        — Monitor waits for backfill_complete before subscribing
    TestRestFallback        — 3 consecutive WS failures trigger REST fallback + WARNING
    TestGapFill             — Gap-fill fetches missing blocks from last_synced to tip
    TestGapFillForkDetection — Fork detection runs on every gap-filled block
    TestLastSyncedHeight    — SyncState.last_synced_height updated after every block
"""

import json
import logging
import time
from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest
from sqlmodel import Session, select

# These imports will cause ImportError until app/monitor.py is created.
# That is intentional — this is the TDD RED phase.
from app.monitor import (
    _process_block,
    _rest_gap_fill,
    _wait_for_backfill,
    _ws_loop,
    run_monitor,
)
from app.models import Block, ForkEvent, SyncState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_block_data(height: int, block_id: str = None, timestamp: int = 1_700_000_000) -> dict:
    """Build a minimal block dict in the shape returned by mempool.space WebSocket."""
    if block_id is None:
        block_id = f"hash_{height:06d}"
    return {"id": block_id, "height": height, "timestamp": timestamp}


def _seed_sync_state(session: Session, last_synced_height: int = 0, backfill_complete: bool = True) -> SyncState:
    """Insert a SyncState row and return it (attached to session)."""
    state = SyncState(last_synced_height=last_synced_height, backfill_complete=backfill_complete)
    session.add(state)
    session.commit()
    session.refresh(state)
    return state


# ---------------------------------------------------------------------------
# TestWebSocketSubscribe
# ---------------------------------------------------------------------------

class TestWebSocketSubscribe:
    """Verify the monitor sends the correct subscription message after connecting."""

    def test_subscribe_message_sent_after_connect(self, session):
        """
        After connecting to the WebSocket, the monitor must immediately send
        {"action": "want", "data": ["blocks"]} to subscribe to new block events.

        This is how mempool.space's WebSocket API works: the client connects
        and then tells the server what data it wants to receive.
        """
        _seed_sync_state(session, last_synced_height=800_000, backfill_complete=True)

        # Mock the WebSocket connection object.
        mock_ws = MagicMock()
        # StopIteration causes the for-loop over messages to exit immediately.
        mock_ws.__iter__ = MagicMock(return_value=iter([]))

        with patch("app.monitor.websockets.sync.client.connect") as mock_connect:
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_ws)
            mock_connect.return_value.__exit__ = MagicMock(return_value=False)

            # _ws_loop raises when the message iterator is exhausted — catch it
            try:
                _ws_loop(session, pending_resolutions=[])
            except Exception:
                pass  # Expected: connection closed after empty iterator

            # Verify subscription message was sent
            expected = json.dumps({"action": "want", "data": ["blocks"]})
            mock_ws.send.assert_called_once_with(expected)

    def test_non_block_messages_are_ignored(self, session):
        """
        The WebSocket stream includes heartbeats and other non-block events.
        Messages without a "block" key must be discarded without touching the DB.
        """
        _seed_sync_state(session, last_synced_height=800_000, backfill_complete=True)

        # Messages that should be silently ignored
        non_block_messages = [
            json.dumps({"ping": "pong"}),
            json.dumps({"mempoolInfo": {"count": 1234}}),
        ]

        mock_ws = MagicMock()
        mock_ws.__iter__ = MagicMock(return_value=iter(non_block_messages))

        with patch("app.monitor.websockets.sync.client.connect") as mock_connect, \
             patch("app.monitor._process_block") as mock_process:
            mock_connect.return_value.__enter__ = MagicMock(return_value=mock_ws)
            mock_connect.return_value.__exit__ = MagicMock(return_value=False)

            try:
                _ws_loop(session, pending_resolutions=[])
            except Exception:
                pass

            # _process_block must NOT be called for non-block messages
            mock_process.assert_not_called()


# ---------------------------------------------------------------------------
# TestBackfillGate
# ---------------------------------------------------------------------------

class TestBackfillGate:
    """Verify _wait_for_backfill polls until backfill_complete is True."""

    def test_wait_returns_when_backfill_complete_is_true(self, engine):
        """
        _wait_for_backfill() should return (not block forever) once the
        SyncState row has backfill_complete=True.

        We use the engine fixture here (not session) because _wait_for_backfill
        opens its own short-lived sessions internally — it does not reuse
        a caller-provided session. This is the production pattern for background
        threads: open and close sessions for each poll, don't hold one open.
        """
        # Pre-seed a completed state in the test database
        with Session(engine) as s:
            s.add(SyncState(last_synced_height=800_000, backfill_complete=True))
            s.commit()

        with patch("app.monitor.engine", engine), \
             patch("app.monitor.time.sleep") as mock_sleep:
            _wait_for_backfill()
            # Should return without sleeping (backfill was already complete)
            mock_sleep.assert_not_called()

    def test_wait_polls_until_backfill_complete(self, engine):
        """
        _wait_for_backfill() must poll the DB repeatedly while
        backfill_complete is False, then return when it becomes True.

        We simulate this by patching the SyncState query to return
        False twice, then True on the third call.
        """
        false_state = MagicMock()
        false_state.backfill_complete = False
        true_state = MagicMock()
        true_state.backfill_complete = True

        # Simulate: False, False, True
        side_effects = [false_state, false_state, true_state]

        with patch("app.monitor.engine", engine), \
             patch("app.monitor.Session") as mock_session_cls, \
             patch("app.monitor.time.sleep") as mock_sleep:

            # Set up the mock session to return states from our list
            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_session.exec.return_value.first.side_effect = side_effects

            _wait_for_backfill()

            # Should have slept twice (once per False result)
            assert mock_sleep.call_count == 2


# ---------------------------------------------------------------------------
# TestRestFallback
# ---------------------------------------------------------------------------

class TestRestFallback:
    """Verify 3 consecutive WebSocket failures trigger REST fallback + WARNING log."""

    def test_warning_logged_after_three_consecutive_failures(self, session, caplog):
        """
        After WS_FAILURE_THRESHOLD (3) consecutive WebSocket failures,
        run_monitor() must log a WARNING message so operators know the system
        has fallen back to REST polling.

        Logging is the primary observability signal for this state change.

        We patch _rest_gap_fill to raise SystemExit on first call, which stops
        the loop cleanly after the WARNING has been emitted. The session mock
        returns a valid SyncState so the REST fallback path can call _rest_gap_fill.
        """
        _seed_sync_state(session, last_synced_height=800_000, backfill_complete=True)

        ws_call_count = {"n": 0}

        def fail_ws_loop(*args, **kwargs):
            ws_call_count["n"] += 1
            raise Exception("WebSocket connection failed")

        def stop_after_first_gap_fill(*args, **kwargs):
            raise SystemExit("test done")

        mock_state = MagicMock()
        mock_state.last_synced_height = 800_000

        with patch("app.monitor._wait_for_backfill"), \
             patch("app.monitor._ws_loop", side_effect=fail_ws_loop), \
             patch("app.monitor._rest_gap_fill", side_effect=stop_after_first_gap_fill), \
             patch("app.monitor.time.sleep"), \
             patch("app.monitor.time.time", return_value=0.0), \
             patch("app.monitor.Session") as mock_session_cls:

            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_session.exec.return_value.first.return_value = mock_state

            with caplog.at_level(logging.WARNING, logger="app.monitor"):
                try:
                    run_monitor()
                except SystemExit:
                    pass  # Expected — we exit after the WARNING is logged

            # Confirm WARNING was logged about REST fallback
            warning_messages = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert len(warning_messages) >= 1, "Expected WARNING log after 3 WS failures"
            assert any("fallback" in r.message.lower() or "rest" in r.message.lower()
                       for r in warning_messages), "WARNING should mention REST fallback"

    def test_rest_poll_called_during_fallback(self, session):
        """
        Once in REST fallback mode, _rest_gap_fill must be called to keep
        the DB current when WebSocket is unavailable.

        We confirm _rest_gap_fill is invoked by stopping the loop on first call.
        """
        _seed_sync_state(session, last_synced_height=800_000, backfill_complete=True)

        ws_call_count = {"n": 0}
        gap_fill_calls = {"n": 0}

        def fail_ws_loop(*args, **kwargs):
            ws_call_count["n"] += 1
            raise Exception("WebSocket connection failed")

        def mock_gap_fill(*args, **kwargs):
            gap_fill_calls["n"] += 1
            raise SystemExit("test done")

        mock_state = MagicMock()
        mock_state.last_synced_height = 800_000

        with patch("app.monitor._wait_for_backfill"), \
             patch("app.monitor._ws_loop", side_effect=fail_ws_loop), \
             patch("app.monitor._rest_gap_fill", side_effect=mock_gap_fill), \
             patch("app.monitor.time.sleep"), \
             patch("app.monitor.time.time", return_value=0.0), \
             patch("app.monitor.Session") as mock_session_cls:

            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_session.exec.return_value.first.return_value = mock_state

            try:
                run_monitor()
            except SystemExit:
                pass

            assert gap_fill_calls["n"] >= 1, "_rest_gap_fill must be called during REST fallback"


# ---------------------------------------------------------------------------
# TestGapFill
# ---------------------------------------------------------------------------

class TestGapFill:
    """Verify _rest_gap_fill fetches blocks from last_synced_height to tip."""

    def test_gap_fill_fetches_from_last_synced_to_tip(self, session):
        """
        _rest_gap_fill must:
        1. Call fetch_tip_height() to determine the current chain tip.
        2. Walk from state.last_synced_height to tip using fetch_blocks_page.

        We verify that fetch_blocks_page is called with an argument at or above
        last_synced_height (the page walk starts from the right place).
        """
        state = _seed_sync_state(session, last_synced_height=800_010, backfill_complete=True)

        # Tip is 5 blocks ahead — gap fill should bridge that
        tip = 800_015

        page_blocks = [
            _make_block_data(800_011),
            _make_block_data(800_012),
            _make_block_data(800_013),
            _make_block_data(800_014),
            _make_block_data(800_015),
        ]

        with patch("app.monitor.fetch_tip_height", return_value=tip), \
             patch("app.monitor.fetch_blocks_page", return_value=page_blocks) as mock_fetch, \
             patch("app.monitor._process_block") as mock_process, \
             patch("app.monitor.time.sleep"):

            _rest_gap_fill(session, state)

            # fetch_blocks_page must have been called at least once
            mock_fetch.assert_called()
            # The start height arg must be >= last_synced_height
            first_call_height = mock_fetch.call_args_list[0][0][0]
            assert first_call_height >= 800_010

    def test_gap_fill_processes_blocks_in_ascending_order(self, session):
        """
        _rest_gap_fill processes blocks in ascending height order.
        The API returns blocks in descending order per page; the monitor
        must reverse (or sort) them before calling _process_block.
        """
        state = _seed_sync_state(session, last_synced_height=800_000, backfill_complete=True)
        tip = 800_003

        # API returns in descending order
        page_blocks = [
            _make_block_data(800_003),
            _make_block_data(800_002),
            _make_block_data(800_001),
        ]

        processed_heights = []

        def record_height(sess, block_data, pending_resolutions):
            processed_heights.append(block_data["height"])

        with patch("app.monitor.fetch_tip_height", return_value=tip), \
             patch("app.monitor.fetch_blocks_page", return_value=page_blocks), \
             patch("app.monitor._process_block", side_effect=record_height), \
             patch("app.monitor.time.sleep"):

            _rest_gap_fill(session, state)

            # Heights must be in ascending order
            ascending = sorted(processed_heights)
            assert processed_heights == ascending, (
                f"Blocks must be processed in ascending order. Got: {processed_heights}"
            )


# ---------------------------------------------------------------------------
# TestGapFillForkDetection
# ---------------------------------------------------------------------------

class TestGapFillForkDetection:
    """Verify fork detection runs for every block processed via gap-fill."""

    def test_detect_fork_called_for_each_gap_filled_block(self, session):
        """
        _process_block must call detect_fork_at_height for every block it processes,
        not only blocks that appear to be at a new height. Fork detection happens
        at the per-block level regardless of gap-fill or live mode.
        """
        state = _seed_sync_state(session, last_synced_height=800_000, backfill_complete=True)

        block_data = _make_block_data(800_001, block_id="hash_a")

        with patch("app.monitor.detect_fork_at_height", return_value=None) as mock_detect, \
             patch("app.monitor.write_fork_event") as mock_write:

            _process_block(session, block_data, pending_resolutions=[])

            # detect_fork_at_height must be called exactly once per block
            mock_detect.assert_called_once_with(session, 800_001, "hash_a")
            # No fork was returned, so write_fork_event should NOT be called
            mock_write.assert_not_called()

    def test_write_fork_event_called_when_fork_detected_during_gap_fill(self, session):
        """
        When detect_fork_at_height returns a competing block (fork detected),
        _process_block must call fetch_block_status for both hashes and then
        call write_fork_event with the resolved canonical/orphaned assignments.
        """
        state = _seed_sync_state(session, last_synced_height=800_000, backfill_complete=True)

        new_block_data = _make_block_data(800_001, block_id="hash_canonical", timestamp=1_700_000_100)

        # The competing block already in the DB
        competing_block = Block(
            hash="hash_orphaned",
            height=800_001,
            timestamp=datetime.utcfromtimestamp(1_700_000_000),
            is_canonical=True,
        )
        session.add(competing_block)
        session.commit()

        # fetch_block_status: canonical is in best chain, orphaned is not
        def mock_status(block_hash):
            if block_hash == "hash_canonical":
                return {"in_best_chain": True}
            return {"in_best_chain": False}

        with patch("app.monitor.detect_fork_at_height", return_value=competing_block), \
             patch("app.monitor.fetch_block_status", side_effect=mock_status), \
             patch("app.monitor.write_fork_event") as mock_write:

            _process_block(session, new_block_data, pending_resolutions=[])

            mock_write.assert_called_once()
            call_kwargs = mock_write.call_args
            # Verify canonical and orphaned hashes were correctly assigned
            args = call_kwargs[0] if call_kwargs[0] else []
            kwargs = call_kwargs[1] if call_kwargs[1] else {}
            # Accept either positional or keyword args
            all_args = list(args) + list(kwargs.values())
            assert "hash_canonical" in all_args or kwargs.get("canonical_hash") == "hash_canonical"
            assert "hash_orphaned" in all_args or kwargs.get("orphaned_hash") == "hash_orphaned"


# ---------------------------------------------------------------------------
# TestLastSyncedHeight
# ---------------------------------------------------------------------------

class TestLastSyncedHeight:
    """Verify SyncState.last_synced_height is updated after every processed block."""

    def test_last_synced_height_updated_after_each_block(self, session):
        """
        After _process_block completes, SyncState.last_synced_height must be
        updated to reflect the newly-processed block's height.

        This is critical for crash recovery: if the monitor restarts, it must
        resume from the last successfully-processed block, not from an older
        checkpoint.
        """
        state = _seed_sync_state(session, last_synced_height=800_000, backfill_complete=True)

        block_data = _make_block_data(800_001, block_id="hash_new")

        with patch("app.monitor.detect_fork_at_height", return_value=None):
            _process_block(session, block_data, pending_resolutions=[])

        # Refresh the SyncState from the DB to see the committed value
        session.expire_all()
        updated_state = session.exec(select(SyncState)).first()
        assert updated_state.last_synced_height == 800_001, (
            f"Expected last_synced_height=800_001, got {updated_state.last_synced_height}"
        )

    def test_last_synced_height_monotonically_increases(self, session):
        """
        last_synced_height must never decrease, even if blocks arrive out of order.
        _process_block uses max(current_height, block_height) to ensure monotonicity.

        Why does this matter? If a re-org notification arrives with a slightly
        older block height, we don't want to reset the sync position backwards.
        """
        state = _seed_sync_state(session, last_synced_height=800_005, backfill_complete=True)

        # Process a block at a height lower than last_synced_height
        lower_block_data = _make_block_data(800_003, block_id="hash_lower")

        with patch("app.monitor.detect_fork_at_height", return_value=None):
            _process_block(session, lower_block_data, pending_resolutions=[])

        session.expire_all()
        updated_state = session.exec(select(SyncState)).first()
        # Must not have regressed to 800_003
        assert updated_state.last_synced_height == 800_005, (
            f"last_synced_height must not decrease. Expected 800_005, got {updated_state.last_synced_height}"
        )
