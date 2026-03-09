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
from sqlmodel import Session, select

from app.models import Block, ForkEvent
from app.fork_detector import detect_fork_at_height, write_fork_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_block(hash: str, height: int, ts: datetime, is_canonical: bool = True) -> Block:
    """Create and return an unsaved Block instance with the given fields."""
    return Block(hash=hash, height=height, timestamp=ts, is_canonical=is_canonical)


TS_A = datetime(2024, 1, 1, 12, 0, 0)
TS_B = datetime(2024, 1, 1, 12, 0, 10)  # 10 seconds later than TS_A


# ---------------------------------------------------------------------------
# TestDetectFork
# Tests for detect_fork_at_height(session, height, new_hash) -> Optional[Block]
# ---------------------------------------------------------------------------


class TestDetectFork:
    def test_no_fork_when_height_empty(self, session: Session):
        """When no blocks exist at a given height, returns None (no fork)."""
        result = detect_fork_at_height(session, height=100, new_hash="aaa111")
        assert result is None

    def test_no_fork_when_same_hash(self, session: Session):
        """When only the same-hash block exists at that height, returns None.

        This handles the case where a block we've already stored comes in again —
        that's not a fork, just a duplicate notification.
        """
        block = _make_block("aaa111", height=100, ts=TS_A)
        session.add(block)
        session.commit()

        result = detect_fork_at_height(session, height=100, new_hash="aaa111")
        assert result is None

    def test_detects_fork_when_different_hash_exists(self, session: Session):
        """When a different-hash block exists at the same height, returns that block.

        This is the fork condition: two blocks at the same height with different
        hashes means the network split temporarily and two miners found a block.
        """
        existing = _make_block("aaa111", height=100, ts=TS_A)
        session.add(existing)
        session.commit()

        result = detect_fork_at_height(session, height=100, new_hash="bbb222")
        assert result is not None
        assert result.hash == "aaa111"
        assert result.height == 100


# ---------------------------------------------------------------------------
# TestWriteForkEvent
# Tests for write_fork_event(session, height, canonical_hash, orphaned_hash,
#                             canonical_ts, orphaned_ts) -> ForkEvent
# ---------------------------------------------------------------------------


class TestWriteForkEvent:
    def test_inserts_fork_event_row(self, session: Session):
        """write_fork_event inserts a ForkEvent with correct height, hashes, and resolution."""
        canon = _make_block("can111", height=200, ts=TS_A)
        orphan = _make_block("orp222", height=200, ts=TS_B)
        session.add(canon)
        session.add(orphan)
        session.commit()

        event = write_fork_event(
            session,
            height=200,
            canonical_hash="can111",
            orphaned_hash="orp222",
            canonical_ts=TS_A,
            orphaned_ts=TS_B,
        )

        assert event.id is not None
        assert event.height == 200
        assert event.canonical_hash == "can111"
        assert event.orphaned_hash == "orp222"
        assert event.resolution_seconds == pytest.approx(10.0)

    def test_resolution_seconds_is_abs(self, session: Session):
        """resolution_seconds is always non-negative regardless of argument order.

        abs() ensures we get a positive duration even if the timestamps are
        passed with canonical_ts later than orphaned_ts (which can happen if
        the orphaned block had a slightly earlier header time).
        """
        canon = _make_block("can333", height=300, ts=TS_B)   # TS_B is LATER
        orphan = _make_block("orp444", height=300, ts=TS_A)  # TS_A is EARLIER
        session.add(canon)
        session.add(orphan)
        session.commit()

        # canonical_ts=TS_B (later), orphaned_ts=TS_A (earlier) → diff is negative before abs
        event = write_fork_event(
            session,
            height=300,
            canonical_hash="can333",
            orphaned_hash="orp444",
            canonical_ts=TS_B,
            orphaned_ts=TS_A,
        )
        assert event.resolution_seconds >= 0
        assert event.resolution_seconds == pytest.approx(10.0)

    def test_orphan_block_is_canonical_set_false(self, session: Session):
        """write_fork_event sets the orphaned block's is_canonical to False.

        This is a side effect of write_fork_event: it looks up the orphaned
        block by hash and sets is_canonical = False so queries for canonical
        blocks will correctly exclude it.
        """
        canon = _make_block("can555", height=400, ts=TS_A)
        orphan = _make_block("orp666", height=400, ts=TS_B, is_canonical=True)
        session.add(canon)
        session.add(orphan)
        session.commit()

        write_fork_event(
            session,
            height=400,
            canonical_hash="can555",
            orphaned_hash="orp666",
            canonical_ts=TS_A,
            orphaned_ts=TS_B,
        )

        session.refresh(orphan)
        assert orphan.is_canonical is False


# ---------------------------------------------------------------------------
# TestForkIdempotency
# Tests that write_fork_event does not insert duplicate rows on repeat calls
# ---------------------------------------------------------------------------


class TestForkIdempotency:
    def test_second_call_returns_existing_row(self, session: Session):
        """Calling write_fork_event twice with identical args returns the same row.

        Idempotency matters because the live monitor might re-process a block
        notification if the WebSocket reconnects or the app restarts. We check
        by height + canonical_hash + orphaned_hash before inserting.
        """
        canon = _make_block("can777", height=500, ts=TS_A)
        orphan = _make_block("orp888", height=500, ts=TS_B)
        session.add(canon)
        session.add(orphan)
        session.commit()

        kwargs = dict(
            session=session,
            height=500,
            canonical_hash="can777",
            orphaned_hash="orp888",
            canonical_ts=TS_A,
            orphaned_ts=TS_B,
        )
        first = write_fork_event(**kwargs)
        second = write_fork_event(**kwargs)

        assert first.id == second.id

    def test_no_duplicate_rows_in_db(self, session: Session):
        """After two identical write_fork_event calls, only one ForkEvent row exists."""
        canon = _make_block("can999", height=600, ts=TS_A)
        orphan = _make_block("orpaaa", height=600, ts=TS_B)
        session.add(canon)
        session.add(orphan)
        session.commit()

        kwargs = dict(
            session=session,
            height=600,
            canonical_hash="can999",
            orphaned_hash="orpaaa",
            canonical_ts=TS_A,
            orphaned_ts=TS_B,
        )
        write_fork_event(**kwargs)
        write_fork_event(**kwargs)

        rows = session.exec(select(ForkEvent).where(ForkEvent.height == 600)).all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# TestOrphanFlagged
# Tests that the orphaned block's is_canonical flag is correctly updated
# ---------------------------------------------------------------------------


class TestOrphanFlagged:
    def test_orphaned_block_is_canonical_false(self, session: Session):
        """Orphaned block's is_canonical transitions from True to False."""
        canon = _make_block("canbbb", height=700, ts=TS_A)
        orphan = _make_block("orpccc", height=700, ts=TS_B, is_canonical=True)
        session.add(canon)
        session.add(orphan)
        session.commit()

        assert orphan.is_canonical is True  # sanity: starts as True

        write_fork_event(
            session,
            height=700,
            canonical_hash="canbbb",
            orphaned_hash="orpccc",
            canonical_ts=TS_A,
            orphaned_ts=TS_B,
        )

        session.refresh(orphan)
        assert orphan.is_canonical is False

    def test_canonical_block_is_canonical_unchanged(self, session: Session):
        """Canonical block's is_canonical remains True after write_fork_event."""
        canon = _make_block("canddd", height=800, ts=TS_A, is_canonical=True)
        orphan = _make_block("orpeee", height=800, ts=TS_B, is_canonical=True)
        session.add(canon)
        session.add(orphan)
        session.commit()

        write_fork_event(
            session,
            height=800,
            canonical_hash="canddd",
            orphaned_hash="orpeee",
            canonical_ts=TS_A,
            orphaned_ts=TS_B,
        )

        session.refresh(canon)
        assert canon.is_canonical is True


# ---------------------------------------------------------------------------
# TestPendingResolution
# Tests for ForkEvent written with resolution_seconds=None (unresolved fork)
# ---------------------------------------------------------------------------


class TestPendingResolution:
    def test_fork_event_with_none_resolution(self, session: Session):
        """A ForkEvent written via direct insert can have resolution_seconds=None.

        This tests the ForkEvent model itself: it should accept None for
        resolution_seconds (the field is Optional[float]). In practice the
        monitor may write a pending event before confirmation and update it later.
        """
        canon = _make_block("canfff", height=900, ts=TS_A)
        orphan = _make_block("orpggg", height=900, ts=TS_B)
        session.add(canon)
        session.add(orphan)
        session.commit()

        event = ForkEvent(
            height=900,
            canonical_hash="canfff",
            orphaned_hash="orpggg",
            resolution_seconds=None,
        )
        session.add(event)
        session.commit()
        session.refresh(event)

        assert event.resolution_seconds is None
        assert event.height == 900
