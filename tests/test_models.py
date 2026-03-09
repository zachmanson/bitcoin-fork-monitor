"""
Tests for app/models.py — covers DATA-02 requirements.

Verifies the key constraint that makes fork detection work correctly:
Block.hash is the primary key, so two blocks at the same height can coexist
(they are a fork), but two blocks with the same hash cannot (that would be
a duplicate row, not a fork).
"""

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models import Block


# DATA-02: The schema must allow two blocks at the same height with different hashes.
# This is the fundamental representation of a temporary fork — two competing
# blocks at height N, one canonical and one orphaned.
def test_two_blocks_same_height(session):
    """Two Block rows at the same height with different hashes both persist."""
    block_a = Block(
        hash="aaaa0000",
        height=800_000,
        timestamp=datetime(2023, 1, 1, 12, 0, 0),
        is_canonical=True,
    )
    block_b = Block(
        hash="bbbb1111",
        height=800_000,
        timestamp=datetime(2023, 1, 1, 12, 0, 5),
        is_canonical=False,
    )

    session.add(block_a)
    session.add(block_b)
    session.commit()

    results = session.exec(select(Block).where(Block.height == 800_000)).all()
    assert len(results) == 2, f"Expected 2 blocks at height 800000, got {len(results)}"


# DATA-02: Block.hash must be a primary key — inserting a duplicate hash must fail.
# This catches accidental double-inserts and confirms the schema enforces
# hash uniqueness at the database level, not just in application code.
def test_block_hash_is_primary_key(session):
    """Inserting a second Block with the same hash raises IntegrityError."""
    block_original = Block(
        hash="deadbeef",
        height=800_000,
        timestamp=datetime(2023, 1, 1, 12, 0, 0),
    )
    session.add(block_original)
    session.commit()

    block_duplicate = Block(
        hash="deadbeef",
        height=800_001,  # Different height, same hash — still a violation
        timestamp=datetime(2023, 1, 1, 12, 10, 0),
    )
    session.add(block_duplicate)

    with pytest.raises(IntegrityError):
        session.commit()
