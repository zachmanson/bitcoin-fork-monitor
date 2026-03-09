"""
Backfill worker for bitcoin-fork-monitor.

On first run (empty database), this worker fetches the full blockchain history
from genesis to the current chain tip and stores every block, flagging any
orphaned blocks as ForkEvent rows.

The worker is designed to be crash-safe: it writes a checkpoint to SyncState
every CHECKPOINT_INTERVAL blocks, so restarting the app resumes from the last
checkpoint rather than replaying from genesis.

Thread safety note:
    run_backfill() is intended to be called from a background thread launched
    by the FastAPI lifespan. It owns its own SQLModel Session — it does NOT
    share a session with the request handlers. Session objects are not
    thread-safe, so the backfill thread must never use the get_session()
    dependency from database.py.
"""

import logging
import time
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.api_client import fetch_blocks_page
from app.database import engine as _module_engine
from app.models import Block, ForkEvent, SyncState

logger = logging.getLogger(__name__)

# How often (in blocks) to write the resume checkpoint to SyncState.
# Lower values = safer on crash, but more DB writes. 100 is a reasonable default.
CHECKPOINT_INTERVAL = 100

# Log a progress message every LOG_INTERVAL blocks so long runs stay observable.
LOG_INTERVAL = 1000

# Seconds to sleep between page fetches. Defined here (not in api_client) because
# throttling between pages is a backfill concern, not an HTTP client concern.
THROTTLE_SECONDS = 0.5


def run_backfill() -> None:
    """
    Entry point for the backfill background thread.

    Calls _do_backfill() and catches any exception that escapes, logging it
    at ERROR level. This ensures a backfill failure never propagates up to
    the thread framework and crash the FastAPI server.

    If the backfill fails partway through, the last checkpoint is preserved
    in SyncState, so the next app restart resumes from where it left off
    rather than replaying from genesis.
    """
    try:
        _do_backfill()
    except Exception:
        logger.exception(
            "Backfill worker failed — will resume from checkpoint on next start"
        )


def _do_backfill(engine=None) -> None:
    """
    Core backfill implementation: walks blockchain history and writes DB rows.

    Args:
        engine: SQLAlchemy engine to use. Defaults to the production engine from
                app.database. Pass a test engine to run against an in-memory DB.

    Behavior:
        1. Get-or-create SyncState (handles first run with empty table).
        2. If backfill_complete is True, return early — nothing to do.
        3. Probe the API for the current chain tip height.
        4. Walk from last_synced_height to tip in 15-block pages.
        5. For each block: write a Block row; for each orphan, write Block + ForkEvent.
        6. Checkpoint every CHECKPOINT_INTERVAL blocks and at completion.
    """
    # Fall back to the module-level production engine if no engine is injected.
    # This is the standard "dependency injection with default" pattern.
    if engine is None:
        engine = _module_engine

    with Session(engine) as session:
        # --- Step 1: Get or create SyncState ---
        # On first run the table is empty; we create a row with defaults (height=0).
        state = session.exec(select(SyncState)).first()
        if state is None:
            state = SyncState()
            session.add(state)
            session.commit()
            session.refresh(state)

        # --- Step 2: Skip if already complete ---
        if state.backfill_complete:
            logger.info("Backfill already complete — skipping")
            return

        # --- Step 3: Detect current chain tip ---
        # Passing a height larger than the chain tip causes mempool.space to return
        # the most recent blocks. blocks[0]["height"] is the current tip.
        first_page = fetch_blocks_page(999_999_999)
        tip_height = first_page[0]["height"]

        logger.info(
            "Backfill starting from height %d to tip %d",
            state.last_synced_height,
            tip_height,
        )
        logger.info(
            "Note: orphan data only available from height ~820,819 onward"
            " (mempool.space limitation)"
        )

        # --- Step 4: Walk pages from checkpoint to tip ---
        # The API returns blocks in DESCENDING order from start_height.
        # To walk ascending from current_height, we request page_top = current_height + 14
        # and filter out any blocks below current_height (the page may overlap slightly).
        current_height = state.last_synced_height

        while current_height <= tip_height:
            page_top = current_height + 14
            blocks = fetch_blocks_page(page_top)

            for block_data in blocks:
                block_height = block_data["height"]

                # Filter: skip any blocks from a prior page that might be in this response.
                # This can happen at the boundary between pages.
                if block_height < current_height:
                    continue

                _process_block(session, block_data)

            current_height += 15
            time.sleep(THROTTLE_SECONDS)

            # Checkpoint every CHECKPOINT_INTERVAL blocks so a restart can resume here.
            if current_height % CHECKPOINT_INTERVAL == 0:
                write_checkpoint(session, state, current_height)

            # Periodic progress log so long backfills are observable.
            if current_height % LOG_INTERVAL == 0:
                percent = (current_height / tip_height * 100) if tip_height else 0
                logger.info(
                    "Backfill: %d/%d blocks (%.1f%%) — height %d",
                    current_height,
                    tip_height,
                    percent,
                    current_height,
                )

        # --- Step 5: Mark complete and write final checkpoint ---
        state.backfill_complete = True
        write_checkpoint(session, state, tip_height)
        logger.info("Backfill complete — %d blocks processed", tip_height)


def _process_block(session: Session, block_data: dict) -> None:
    """
    Write one block (and any of its orphans) to the database.

    Creates a canonical Block row and, for each entry in extras.orphans,
    an orphan Block row and a ForkEvent row linking the two.

    Args:
        session: Active SQLModel session. Caller owns the transaction.
        block_data: One block dict from the mempool.space API response.
    """
    height = block_data["height"]

    # The API uses "id" for the canonical hash (not "hash").
    canonical_hash = block_data["id"]

    # Convert Unix timestamp to a naive UTC datetime.
    # Using replace(tzinfo=None) strips the tzinfo after localization so the
    # datetime stored in SQLite is naive (no timezone), matching the column type.
    ts = datetime.fromtimestamp(
        block_data["timestamp"], tz=timezone.utc
    ).replace(tzinfo=None)

    # Guard: skip insert if this block was already stored (idempotent on resume).
    if session.get(Block, canonical_hash) is None:
        session.add(Block(hash=canonical_hash, height=height, timestamp=ts, is_canonical=True))

    # Process orphaned blocks at this height (if any).
    for orphan in block_data["extras"]["orphans"]:
        orphan_hash = orphan["hash"]

        if session.get(Block, orphan_hash) is None:
            session.add(
                Block(hash=orphan_hash, height=height, timestamp=ts, is_canonical=False)
            )

        session.add(
            ForkEvent(
                height=height,
                canonical_hash=canonical_hash,
                orphaned_hash=orphan_hash,
            )
        )

    # Commit after each block to keep writes frequent and reduce re-work on crash.
    session.commit()


def write_checkpoint(session: Session, state: SyncState, height: int) -> None:
    """
    Persist the current sync position to SyncState.

    Called every CHECKPOINT_INTERVAL blocks during backfill and once more at
    completion. Writing state.backfill_complete = True before calling this
    function will persist that flag as well.

    Args:
        session: Active SQLModel session used for the backfill.
        state: The SyncState row to update (already attached to this session).
        height: The block height to record as the new resume point.
    """
    state.last_synced_height = height
    state.updated_at = datetime.utcnow()
    session.add(state)
    session.commit()
