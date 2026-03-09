"""
Pure fork detection functions for bitcoin-fork-monitor.

These functions contain no network calls, no threading, and no global state.
The database session is always passed in as a parameter. This design makes
the logic trivially testable in isolation and safe to reuse from the live
monitor, the backfill worker, or any future replay tool.

A Bitcoin "fork" (more precisely a temporary fork or orphan race) occurs when
two miners find a valid block at the same height nearly simultaneously. The
network briefly holds two competing chains until the next block is mined on
one of them, making that the longer (canonical) chain. The other block is
then orphaned. This module detects and records those events.
"""

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.models import Block, ForkEvent


def detect_fork_at_height(session: Session, height: int, new_hash: str) -> Optional[Block]:
    """
    Check whether a competing block already exists at the given height.

    A fork exists when two blocks have the same height but different hashes.
    This function queries the Block table for any row at ``height`` whose hash
    differs from ``new_hash``. If such a row exists, a fork has been detected.

    This function is read-only — it does not modify the database. The caller
    decides what to do with the returned competing block (typically call
    ``write_fork_event`` next).

    Args:
        session: An active database session.
        height: The chain height to check for competing blocks.
        new_hash: The hash of the newly-seen block (the one we're checking against).

    Returns:
        The existing competing Block if one is found at the same height with a
        different hash, or None if no fork is detected.
    """
    # Query for any block at this height that is NOT the block we just saw.
    # If the result is non-None, we have two different blocks at the same height — a fork.
    statement = select(Block).where(Block.height == height, Block.hash != new_hash)
    return session.exec(statement).first()


def write_fork_event(
    session: Session,
    height: int,
    canonical_hash: str,
    orphaned_hash: str,
    canonical_ts: datetime,
    orphaned_ts: datetime,
) -> ForkEvent:
    """
    Record a fork event in the database and flag the orphaned block.

    This function performs three operations atomically (inside a single commit):
    1. Idempotency check: if a ForkEvent with matching (height, canonical_hash,
       orphaned_hash) already exists, return it without inserting a duplicate.
       This handles monitor restarts or duplicate WebSocket notifications safely.
    2. Update the orphaned block: sets ``is_canonical = False`` on the Block row
       identified by ``orphaned_hash`` so canonical-chain queries exclude it.
    3. Insert a ForkEvent row with the computed ``resolution_seconds``.

    resolution_seconds formula:
        abs((canonical_ts - orphaned_ts).total_seconds())

    Using ``abs()`` ensures the value is always non-negative regardless of
    which block had the earlier header timestamp (miners can set timestamps
    within a small window, so the orphaned block might have a later timestamp
    than the canonical one).

    Args:
        session: An active database session.
        height: The chain height where the fork occurred.
        canonical_hash: Hash of the block that survived in the best chain.
        orphaned_hash: Hash of the block that was reorged out.
        canonical_ts: Header timestamp of the canonical block.
        orphaned_ts: Header timestamp of the orphaned block.

    Returns:
        The ForkEvent row (either the newly inserted one or the pre-existing
        one if this fork was already recorded — idempotency guarantee).
    """
    # Idempotency check: look for an existing ForkEvent with the same key tuple.
    # Professional convention: always check before insert for operations that may
    # be retried (monitor restarts, duplicate events, etc.).
    existing = session.exec(
        select(ForkEvent).where(
            ForkEvent.height == height,
            ForkEvent.canonical_hash == canonical_hash,
            ForkEvent.orphaned_hash == orphaned_hash,
        )
    ).first()

    if existing is not None:
        return existing

    # resolution_seconds: how long did the fork last?
    # abs() guarantees a non-negative duration regardless of timestamp ordering.
    resolution_seconds = abs((canonical_ts - orphaned_ts).total_seconds())

    # Flag the orphaned block so canonical-chain queries exclude it.
    # We look up the block by its hash (the primary key), update the flag,
    # and re-add it to the session so SQLModel tracks the change.
    orphaned_block = session.get(Block, orphaned_hash)
    if orphaned_block is not None:
        orphaned_block.is_canonical = False
        session.add(orphaned_block)

    # Create and persist the ForkEvent.
    event = ForkEvent(
        height=height,
        canonical_hash=canonical_hash,
        orphaned_hash=orphaned_hash,
        resolution_seconds=resolution_seconds,
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    return event
