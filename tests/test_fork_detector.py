"""
Unit tests for fork detection logic (MONI-02).

Tests cover the two pure functions in app.fork_detector:
  - detect_fork_at_height: finds a competing block at the same height
  - write_fork_event: records a ForkEvent and marks the orphan block

All tests use the in-memory SQLite session fixture from conftest.py.
"Pure" here means no network calls, no threads — just DB reads and writes.
The session is passed in, making each function independently testable.
"""

import pytest
from datetime import datetime
from sqlmodel import Session

from app.models import Block, ForkEvent


# ---------------------------------------------------------------------------
# TestDetectFork
# Tests for detect_fork_at_height(session, height, new_hash) -> Optional[Block]
# ---------------------------------------------------------------------------


class TestDetectFork:
    def test_no_fork_when_height_empty(self, session: Session):
        # When no blocks exist at a given height, detect_fork_at_height returns None
        pass

    def test_no_fork_when_same_hash(self, session: Session):
        # When only the same-hash block exists at that height, returns None
        pass

    def test_detects_fork_when_different_hash_exists(self, session: Session):
        # When a different-hash block exists at the same height, returns that block
        pass


# ---------------------------------------------------------------------------
# TestWriteForkEvent
# Tests for write_fork_event(session, height, canonical_hash, orphaned_hash,
#                             canonical_ts, orphaned_ts) -> ForkEvent
# ---------------------------------------------------------------------------


class TestWriteForkEvent:
    def test_inserts_fork_event_row(self, session: Session):
        # write_fork_event creates and returns a ForkEvent with correct fields
        pass

    def test_resolution_seconds_is_abs(self, session: Session):
        # resolution_seconds = abs(ts_diff) — always non-negative regardless of order
        pass

    def test_orphan_block_is_canonical_set_false(self, session: Session):
        # The orphaned block's is_canonical field is set to False after write_fork_event
        pass


# ---------------------------------------------------------------------------
# TestForkIdempotency
# Tests that write_fork_event does not insert duplicate rows on repeat calls
# ---------------------------------------------------------------------------


class TestForkIdempotency:
    def test_second_call_returns_existing_row(self, session: Session):
        # Calling write_fork_event twice with identical args returns the same row
        pass

    def test_no_duplicate_rows_in_db(self, session: Session):
        # After two identical calls, only one ForkEvent row exists in the DB
        pass


# ---------------------------------------------------------------------------
# TestOrphanFlagged
# Tests that the orphaned block's is_canonical flag is correctly updated
# ---------------------------------------------------------------------------


class TestOrphanFlagged:
    def test_orphaned_block_is_canonical_false(self, session: Session):
        # Orphaned block is_canonical goes from True to False after write_fork_event
        pass

    def test_canonical_block_is_canonical_unchanged(self, session: Session):
        # Canonical block's is_canonical remains True after write_fork_event
        pass


# ---------------------------------------------------------------------------
# TestPendingResolution
# Tests for ForkEvent written with resolution_seconds=None (unresolved fork)
# ---------------------------------------------------------------------------


class TestPendingResolution:
    def test_fork_event_with_none_resolution(self, session: Session):
        # A ForkEvent can be written with resolution_seconds=None for unresolved forks
        pass
