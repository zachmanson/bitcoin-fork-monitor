"""
Unit tests for app/monitor.py — the live block monitoring thread.

Test structure follows the MONI-01 and MONI-03 test map from the plan.
All network I/O (WebSocket connections, HTTP calls) is mocked so tests
run without hitting the real network.

Classes:
    TestWebSocketSubscribe  — WebSocket connect and subscription message
    TestBackfillGate        — Monitor waits for backfill_complete before subscribing
    TestRestFallback        — 3 consecutive WS failures trigger REST fallback + WARNING
    TestGapFill             — Gap-fill fetches missing blocks from last_synced to tip
    TestGapFillForkDetection — Fork detection runs on every gap-filled block
    TestLastSyncedHeight    — SyncState.last_synced_height updated after every block
"""

import pytest
from unittest.mock import patch, MagicMock

# NOTE: We intentionally do NOT import from app.monitor here.
# app/monitor.py does not exist yet — importing it would cause an ImportError
# and prevent pytest from collecting this file. The real imports are added
# in Task 2 once the module is created (TDD RED → GREEN progression).


class TestWebSocketSubscribe:
    """Verify that the monitor sends the subscription message after connecting."""

    def test_subscribe_message_sent_after_connect(self):
        # Will verify: after connecting to WS_URL, monitor sends
        # {"action": "want", "data": ["blocks"]} as the first message
        pass

    def test_non_block_messages_are_ignored(self):
        # Will verify: messages without a "block" key are silently discarded
        # and do not cause errors or unexpected DB writes
        pass


class TestBackfillGate:
    """Verify the monitor waits for SyncState.backfill_complete before proceeding."""

    def test_wait_returns_when_backfill_complete_is_true(self):
        # Will verify: _wait_for_backfill() polls SyncState every 5 seconds
        # and returns as soon as backfill_complete is True
        pass

    def test_wait_blocks_while_backfill_incomplete(self):
        # Will verify: _wait_for_backfill() continues polling while
        # backfill_complete is False (checked via call count on the DB query)
        pass


class TestRestFallback:
    """Verify 3 consecutive WebSocket failures trigger REST fallback with WARNING."""

    def test_warning_logged_after_three_consecutive_failures(self):
        # Will verify: run_monitor() logs a WARNING after the 3rd consecutive
        # WebSocket failure (WS_FAILURE_THRESHOLD)
        pass

    def test_rest_poll_called_during_fallback(self):
        # Will verify: after entering REST fallback, _rest_gap_fill is called
        # at the REST_POLL_INTERVAL_SECONDS cadence
        pass


class TestGapFill:
    """Verify _rest_gap_fill fetches blocks from last_synced_height to tip."""

    def test_gap_fill_fetches_from_last_synced_to_tip(self):
        # Will verify: _rest_gap_fill calls fetch_tip_height() and then
        # fetch_blocks_page() starting from state.last_synced_height
        pass

    def test_gap_fill_processes_blocks_in_ascending_order(self):
        # Will verify: blocks returned by the API are processed in ascending
        # height order (lowest height first), matching the _process_block contract
        pass


class TestGapFillForkDetection:
    """Verify fork detection runs on every block processed during gap-fill."""

    def test_detect_fork_called_for_each_gap_filled_block(self):
        # Will verify: when _rest_gap_fill processes blocks, it calls
        # detect_fork_at_height for each block (not just canonical blocks)
        pass

    def test_write_fork_event_called_when_fork_detected_during_gap_fill(self):
        # Will verify: if detect_fork_at_height returns a competing block,
        # write_fork_event is called with the correct canonical/orphaned hashes
        pass


class TestLastSyncedHeight:
    """Verify SyncState.last_synced_height is updated after every processed block."""

    def test_last_synced_height_updated_after_each_block(self):
        # Will verify: after _process_block completes, SyncState.last_synced_height
        # is set to max(current_height, processed_block_height) and committed
        pass

    def test_last_synced_height_monotonically_increases(self):
        # Will verify: last_synced_height never decreases even if blocks arrive
        # out of order (uses max() to protect against that case)
        pass
