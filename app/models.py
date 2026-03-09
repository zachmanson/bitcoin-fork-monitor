"""
SQLModel table definitions for bitcoin-fork-monitor.

Three tables are defined here:
  - Block: one row per block hash seen on the network (canonical and orphaned)
  - ForkEvent: one row per detected temporary fork
  - SyncState: a single row tracking the backfill and sync progress

Note on foreign keys: ForkEvent stores canonical_hash and orphaned_hash as plain
string columns rather than foreign keys pointing at Block. SQLite requires the
PRAGMA foreign_keys=ON pragma to enforce FK constraints, and that pragma is off
by default. Enforcement can be added later by enabling the pragma on each
connection; for now the application layer is responsible for consistency.
"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Block(SQLModel, table=True):
    """
    A Bitcoin block observed on the network.

    hash is the primary key because it uniquely identifies a block across all
    heights. Two blocks at the same height with different hashes is exactly the
    fork condition we are trying to detect, so height must NOT be the primary key.

    Attributes:
        hash: The block's SHA-256d hash (hex string). Primary key.
        height: The block's position in the chain. Indexed for fast range queries.
        timestamp: The block's header timestamp (from the miner, not wall clock).
        is_canonical: True if this block is part of the best chain; False if orphaned.
    """

    hash: str = Field(primary_key=True)
    height: int = Field(index=True)
    timestamp: datetime
    is_canonical: bool = Field(default=True)


class ForkEvent(SQLModel, table=True):
    """
    A recorded temporary fork — two competing blocks at the same height.

    One block won (canonical_hash) and one was orphaned (orphaned_hash).

    Attributes:
        id: Auto-incrementing surrogate primary key.
        height: The chain height where the fork occurred.
        canonical_hash: Hash of the block that survived in the best chain.
        orphaned_hash: Hash of the block that was reorged out.
        detected_at: Wall-clock time when this fork was detected by the monitor.
        resolution_seconds: How long (in seconds) the fork lasted before resolving.
            None if the fork is still unresolved or the duration was not measured.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    height: int
    canonical_hash: str
    orphaned_hash: str
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    resolution_seconds: Optional[float] = Field(default=None)


class SyncState(SQLModel, table=True):
    """
    Progress tracking for the backfill and live sync processes.

    There will typically be one row in this table, updated in place.

    Attributes:
        id: Auto-incrementing surrogate primary key.
        last_synced_height: The highest block height successfully fetched and stored.
            Backfill resumes from this height on restart.
        backfill_complete: True once the initial history backfill has finished.
        updated_at: Wall-clock time this row was last modified.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    last_synced_height: int = Field(default=0)
    backfill_complete: bool = Field(default=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
