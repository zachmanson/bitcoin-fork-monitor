"""
Live block monitoring thread for bitcoin-fork-monitor.

This module runs continuously in a background thread and keeps the database
current with the live Bitcoin network. It implements a resilient state machine:

  1. Wait for the initial backfill to complete (backfill_complete gate).
  2. Subscribe to mempool.space via WebSocket for real-time block notifications.
  3. On each block: detect forks, write ForkEvent rows, update SyncState.
  4. After 3 consecutive WebSocket failures: fall back to REST polling every 30s.
  5. Every 5 minutes in REST fallback: attempt to restore the WebSocket connection.

Why a state machine rather than just retrying forever?
    A single transient failure (brief network blip) should not trigger the
    slower REST fallback. Tracking consecutive_failures means only sustained
    outages switch modes. This keeps latency low during normal operation.

Thread safety note:
    run_monitor() opens a single long-lived Session(engine) for the monitor
    lifecycle. This session is never shared with other threads. All DB writes
    are committed immediately after each block to minimize re-work on crash.

Why WebSocket for live data?
    WebSockets are persistent bidirectional connections. Once the server sends
    a "subscribe" message, the server pushes new blocks to the client as they
    arrive — no polling overhead. REST polling is the fallback because it works
    everywhere but has latency equal to the poll interval.
"""

import json
import logging
import time
from datetime import datetime
from typing import Optional

import websockets.sync.client
from sqlmodel import Session, select

from app.api_client import (
    REQUEST_THROTTLE_SECONDS,
    fetch_block_status,
    fetch_blocks_page,
    fetch_tip_height,
)
from app.database import engine
from app.fork_detector import detect_fork_at_height, write_fork_event
from app.models import Block, ForkEvent, SyncState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# WebSocket endpoint for mempool.space live block events.
# The protocol is: connect → send SUBSCRIBE_MSG → receive block events.
WS_URL = "wss://mempool.space/api/v1/ws"

# Subscription payload. Tells mempool.space we want "blocks" events.
# JSON-encoded once at module load — no need to re-encode on every connect.
SUBSCRIBE_MSG = json.dumps({"action": "want", "data": ["blocks"]})

# After this many consecutive WebSocket failures, switch to REST fallback.
WS_FAILURE_THRESHOLD = 3

# How often to poll via REST while in fallback mode.
REST_POLL_INTERVAL_SECONDS = 30

# How often to attempt WebSocket reconnect while in REST fallback mode.
WS_RECONNECT_INTERVAL_SECONDS = 300  # 5 minutes

# How often to check SyncState.backfill_complete while waiting for backfill.
BACKFILL_POLL_INTERVAL_SECONDS = 5


# ---------------------------------------------------------------------------
# Backfill gate
# ---------------------------------------------------------------------------

def _wait_for_backfill() -> None:
    """
    Block until SyncState.backfill_complete is True.

    Opens and closes a fresh DB session on each poll cycle. We don't hold a
    session open across sleeps because SQLite connections should be short-lived
    in a multi-threaded context. This is a standard pattern for background
    threads that need to check shared state periodically.

    The monitor must not subscribe to the WebSocket before backfill completes
    because gap-fill logic (which runs on reconnect) uses last_synced_height
    to know where to start. During backfill, that value is being written by
    the backfill thread — reading it early could cause double-processing.
    """
    logger.info("Monitor waiting for backfill to complete...")

    while True:
        with Session(engine) as session:
            state = session.exec(select(SyncState)).first()
            if state is not None and state.backfill_complete:
                logger.info("Backfill complete — starting live monitor")
                return

        time.sleep(BACKFILL_POLL_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Block processing
# ---------------------------------------------------------------------------

def _process_block(session: Session, block_data: dict, pending_resolutions: list) -> None:
    """
    Process one block: upsert it into the DB, detect forks, update SyncState.

    This function is called from both the WebSocket loop (live) and the REST
    gap-fill loop. The same code path handles both, ensuring fork detection
    is never skipped regardless of which mode the monitor is in.

    Pending resolutions:
        When a fork is detected but fetch_block_status is ambiguous for both
        competing blocks (both return in_best_chain=True — can happen in the
        seconds after a re-org), we write the ForkEvent with
        resolution_seconds=None and add the event to pending_resolutions.
        On the next call to _process_block, we retry any pending items and
        fill in resolution_seconds if the ambiguity has resolved.

    Args:
        session: Active SQLModel session. Caller owns the session lifecycle.
        block_data: Block dict from mempool.space (WebSocket or REST).
                    Required keys: "id" (hash), "height", "timestamp" (Unix int).
        pending_resolutions: Mutable list of (fork_event_id, canonical_hash,
                             orphaned_hash) tuples awaiting resolution.
    """
    block_hash = block_data["id"]
    height = block_data["height"]
    # Convert Unix timestamp to naive UTC datetime for storage.
    # utcfromtimestamp produces a naive datetime (no tzinfo), matching the column type.
    timestamp = datetime.utcfromtimestamp(block_data["timestamp"])

    # --- Retry any pending fork resolutions from previous blocks ---
    _retry_pending_resolutions(session, pending_resolutions)

    # --- Upsert the block row ---
    if session.get(Block, block_hash) is None:
        session.add(Block(hash=block_hash, height=height, timestamp=timestamp, is_canonical=True))
        session.commit()

    # --- Fork detection ---
    competing_block = detect_fork_at_height(session, height, block_hash)

    if competing_block is not None:
        _handle_fork(session, block_hash, timestamp, competing_block, pending_resolutions)

    # --- Update SyncState ---
    # Use max() to guarantee last_synced_height never decreases.
    # This protects against out-of-order notifications (e.g., a stale re-org event).
    state = session.exec(select(SyncState)).first()
    if state is not None:
        state.last_synced_height = max(state.last_synced_height, height)
        state.updated_at = datetime.utcnow()
        session.add(state)
        session.commit()


def _handle_fork(
    session: Session,
    new_hash: str,
    new_timestamp: datetime,
    competing_block: Block,
    pending_resolutions: list,
) -> None:
    """
    Resolve which block is canonical and write a ForkEvent.

    Calls fetch_block_status for both the new block and the competing block
    to determine which one is in the current best chain. If the result is
    ambiguous (both claim in_best_chain=True, which can happen in the seconds
    right after a re-org), writes the ForkEvent with resolution_seconds=None
    and adds it to pending_resolutions for later retry.

    Args:
        session: Active SQLModel session.
        new_hash: Hash of the newly-arrived block.
        new_timestamp: Timestamp of the newly-arrived block.
        competing_block: The existing Block that conflicts with new_hash at the same height.
        pending_resolutions: Mutable list of pending items (extended if ambiguous).
    """
    new_status = fetch_block_status(new_hash)
    competing_status = fetch_block_status(competing_block.hash)

    new_in_best = new_status.get("in_best_chain", False)
    competing_in_best = competing_status.get("in_best_chain", False)

    if new_in_best and not competing_in_best:
        # Clear winner: the new block is canonical
        canonical_hash, orphaned_hash = new_hash, competing_block.hash
        canonical_ts, orphaned_ts = new_timestamp, competing_block.timestamp
        event = write_fork_event(session, competing_block.height, canonical_hash, orphaned_hash, canonical_ts, orphaned_ts)

    elif competing_in_best and not new_in_best:
        # Clear winner: the competing block (already in DB) is canonical
        canonical_hash, orphaned_hash = competing_block.hash, new_hash
        canonical_ts, orphaned_ts = competing_block.timestamp, new_timestamp
        event = write_fork_event(session, competing_block.height, canonical_hash, orphaned_hash, canonical_ts, orphaned_ts)

    else:
        # Ambiguous: both claim in_best_chain=True (or both False).
        # Write the event with resolution_seconds=None and retry later.
        logger.info(
            "Fork at height %d is ambiguous (new=%s, competing=%s) — will retry",
            competing_block.height, new_hash, competing_block.hash,
        )
        # Write with None resolution — write_fork_event is idempotent
        # so retrying won't create a duplicate row
        event = ForkEvent(
            height=competing_block.height,
            canonical_hash=new_hash,
            orphaned_hash=competing_block.hash,
            resolution_seconds=None,
        )
        session.add(event)
        session.commit()
        session.refresh(event)

        pending_resolutions.append((event.id, new_hash, competing_block.hash))
        return

    logger.info(
        "Fork at height %d: canonical=%s, orphaned=%s, resolved in %.1fs",
        competing_block.height,
        canonical_hash,
        orphaned_hash,
        event.resolution_seconds if event.resolution_seconds is not None else 0.0,
    )


def _retry_pending_resolutions(session: Session, pending_resolutions: list) -> None:
    """
    Attempt to fill in resolution_seconds for any ambiguous ForkEvents.

    Called at the start of each _process_block invocation. If enough time has
    passed for the re-org to propagate, fetch_block_status should now return
    a clear winner. If still ambiguous, the item stays in pending_resolutions.

    Args:
        session: Active SQLModel session.
        pending_resolutions: Mutable list of (event_id, canonical_hash, orphaned_hash).
                             Items are removed when successfully resolved.
    """
    still_pending = []

    for event_id, canonical_hash, orphaned_hash in pending_resolutions:
        canonical_status = fetch_block_status(canonical_hash)
        orphaned_status = fetch_block_status(orphaned_hash)

        canonical_in_best = canonical_status.get("in_best_chain", False)
        orphaned_in_best = orphaned_status.get("in_best_chain", False)

        if canonical_in_best and not orphaned_in_best:
            # Now resolvable: update the ForkEvent with resolution_seconds
            event = session.get(ForkEvent, event_id)
            if event is not None:
                canonical_block = session.get(Block, canonical_hash)
                orphaned_block = session.get(Block, orphaned_hash)
                if canonical_block and orphaned_block:
                    event.resolution_seconds = abs(
                        (canonical_block.timestamp - orphaned_block.timestamp).total_seconds()
                    )
                    session.add(event)
                    session.commit()
                    logger.info("Resolved pending fork %d: %.1fs", event_id, event.resolution_seconds)
                    continue  # Do not re-add to still_pending

        still_pending.append((event_id, canonical_hash, orphaned_hash))

    pending_resolutions.clear()
    pending_resolutions.extend(still_pending)


# ---------------------------------------------------------------------------
# WebSocket loop
# ---------------------------------------------------------------------------

def _ws_loop(session: Session, pending_resolutions: list) -> None:
    """
    Connect to the mempool.space WebSocket and process live block events.

    This function is synchronous (using websockets.sync.client) rather than
    async. We run the monitor in a background thread, so we don't have access
    to FastAPI's asyncio event loop. The synchronous WebSocket client lets us
    use blocking I/O the same way we would with any other network call.

    The function exits (raises) on connection failure. The caller (run_monitor)
    is responsible for counting failures and deciding whether to retry or fall
    back to REST polling.

    Args:
        session: Active SQLModel session (reused from run_monitor).
        pending_resolutions: Mutable list passed through to _process_block.

    Raises:
        websockets.exceptions.ConnectionClosed: If the server closes the connection.
        Exception: On any other connection or protocol error.
    """
    with websockets.sync.client.connect(
        WS_URL,
        open_timeout=30,
        ping_interval=30,
        ping_timeout=10,
    ) as ws:
        # Subscribe to block events immediately after connecting.
        # mempool.space requires this message before it will push block data.
        ws.send(SUBSCRIBE_MSG)
        logger.info("WebSocket connected and subscribed to block events")

        for raw_message in ws:
            try:
                msg = json.loads(raw_message)
            except json.JSONDecodeError:
                logger.warning("Received non-JSON WebSocket message — ignoring")
                continue

            # Only process messages that contain a block payload.
            # The stream includes heartbeats and mempool info we don't need.
            if "block" not in msg:
                continue

            block_data = msg["block"]
            logger.debug("WebSocket block at height %d", block_data.get("height", "?"))
            _process_block(session, block_data, pending_resolutions)


# ---------------------------------------------------------------------------
# REST gap-fill
# ---------------------------------------------------------------------------

def _rest_gap_fill(session: Session, state: SyncState) -> None:
    """
    Fetch and process all blocks between last_synced_height and the current tip.

    Called during REST fallback mode to keep the DB current when WebSocket is
    unavailable. Also called on WebSocket reconnect to fill in any blocks that
    arrived while the WebSocket was disconnected.

    The page-walking logic mirrors backfill.py: mempool.space returns blocks in
    descending order per page, so we reverse each page before processing to
    maintain ascending height order. This ensures _process_block always sees
    blocks in chronological order, which keeps last_synced_height monotonic.

    Args:
        session: Active SQLModel session.
        state: Current SyncState row (used to determine start height).
    """
    tip = fetch_tip_height()
    current_height = state.last_synced_height

    logger.info("Gap-fill: from height %d to tip %d", current_height, tip)

    while current_height <= tip:
        # Request a page starting at current_height + 14 (same pattern as backfill).
        # The page contains up to 15 blocks descending from that height.
        page_top = current_height + 14
        blocks = fetch_blocks_page(page_top)

        # Filter out any blocks below our start height (page may overlap slightly),
        # then sort ascending so _process_block sees heights in order.
        relevant_blocks = [b for b in blocks if b["height"] >= current_height]
        relevant_blocks.sort(key=lambda b: b["height"])

        for block_data in relevant_blocks:
            _process_block(session, block_data, pending_resolutions=[])

        current_height += 15
        time.sleep(REQUEST_THROTTLE_SECONDS)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_monitor() -> None:
    """
    Entry point for the monitor background thread.

    Called from app/main.py lifespan via threading.Thread(target=run_monitor).

    State machine:
        - Normal mode: attempt WebSocket subscription in _ws_loop().
          On failure: increment consecutive_failures.
          At WS_FAILURE_THRESHOLD failures: switch to REST fallback, log WARNING.
        - REST fallback mode: poll every REST_POLL_INTERVAL_SECONDS.
          Every WS_RECONNECT_INTERVAL_SECONDS: attempt WebSocket reconnect.
          On WS reconnect success: run gap-fill, then resume WebSocket mode, log INFO.

    Any unhandled exception in the outer loop is logged at ERROR and causes a
    short sleep before retrying. This prevents a tight crash loop if something
    unexpected happens (e.g., DB connection lost).
    """
    _wait_for_backfill()

    # Single long-lived session for the monitor lifecycle.
    # Background threads must not share sessions with request handlers.
    with Session(engine) as session:
        pending_resolutions: list = []
        consecutive_failures = 0
        in_rest_fallback = False
        last_ws_attempt = 0.0  # epoch time of last WebSocket attempt

        while True:
            try:
                if not in_rest_fallback:
                    # --- Normal mode: try WebSocket ---
                    try:
                        _ws_loop(session, pending_resolutions)
                        # If _ws_loop returns without raising, connection closed cleanly.
                        consecutive_failures = 0

                    except Exception as ws_exc:
                        consecutive_failures += 1
                        logger.warning(
                            "WebSocket failure %d/%d: %s",
                            consecutive_failures,
                            WS_FAILURE_THRESHOLD,
                            ws_exc,
                        )

                        if consecutive_failures >= WS_FAILURE_THRESHOLD:
                            logger.warning(
                                "WebSocket failed %d consecutive times — switching to REST fallback polling",
                                consecutive_failures,
                            )
                            in_rest_fallback = True
                            last_ws_attempt = time.time()

                else:
                    # --- REST fallback mode ---
                    state = session.exec(select(SyncState)).first()
                    if state is not None:
                        _rest_gap_fill(session, state)

                    time.sleep(REST_POLL_INTERVAL_SECONDS)

                    # Periodically attempt to restore WebSocket connection
                    if time.time() - last_ws_attempt >= WS_RECONNECT_INTERVAL_SECONDS:
                        logger.info("Attempting WebSocket reconnect after REST fallback...")
                        try:
                            last_ws_attempt = time.time()
                            _ws_loop(session, pending_resolutions)
                            # Reconnect succeeded — run gap-fill then resume WS mode
                            state = session.exec(select(SyncState)).first()
                            if state is not None:
                                _rest_gap_fill(session, state)
                            in_rest_fallback = False
                            consecutive_failures = 0
                            logger.info("WebSocket reconnected — resuming live monitoring")
                        except Exception as reconnect_exc:
                            logger.warning("WebSocket reconnect failed: %s", reconnect_exc)

            except SystemExit:
                # Allow test-injected SystemExit to propagate (used in tests to stop the loop)
                raise
            except Exception as outer_exc:
                logger.error(
                    "Unexpected error in monitor loop — will retry in 10s: %s",
                    outer_exc,
                    exc_info=True,
                )
                time.sleep(10)
