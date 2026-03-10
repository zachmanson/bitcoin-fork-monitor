"""
REST endpoint: GET /api/stats

Returns a summary of the fork monitor's current state:
  - How many canonical and orphaned blocks are in the database.
  - The calculated stale rate (orphaned / total seen).
  - The timestamp of the most recent fork event, if any.

This is the primary "health dashboard" endpoint — the frontend will poll it to
display the headline numbers. Because it aggregates across the entire Block table
it may be a few seconds stale, which is fine for display purposes.

Why func.count(Block.hash) instead of func.count()?
    Both return the row count, but specifying the column (func.count(Block.hash))
    makes the intent explicit: we're counting non-null hash values, not just rows.
    It's clearer to a reader and is consistent with how most SQL style guides
    recommend writing COUNT queries. Either form produces identical SQL here.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session, func, select

from app.analytics import calculate_stale_rate
from app.database import get_session
from app.models import Block, ForkEvent

# APIRouter groups these endpoints under a shared prefix and tag.
# The prefix "/api" means the full path is /api/stats.
# Tags appear in the auto-generated OpenAPI docs at /docs.
router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def get_stats(session: Session = Depends(get_session)) -> dict:
    """
    Return aggregate statistics for the fork monitor dashboard.

    Depends(get_session) is FastAPI's dependency injection: FastAPI calls
    get_session() automatically and passes the resulting Session here.
    This is the standard pattern for database access in FastAPI — you don't
    create or close sessions yourself; FastAPI manages the lifecycle.

    Returns:
        dict with keys:
            canonical_blocks (int): Blocks currently in the best chain.
            orphaned_blocks (int): Blocks that lost a fork competition.
            stale_rate (float): orphaned / (canonical + orphaned).
            last_fork_at (datetime | None): Timestamp of the most recent fork.
    """
    # Count canonical blocks: SELECT COUNT(hash) FROM block WHERE is_canonical = 1
    # .one() is safe here because COUNT always returns exactly one row.
    canonical_blocks: int = session.exec(
        select(func.count(Block.hash)).where(Block.is_canonical.is_(True))
    ).one()

    # Count orphaned blocks: SELECT COUNT(hash) FROM block WHERE is_canonical = 0
    orphaned_blocks: int = session.exec(
        select(func.count(Block.hash)).where(Block.is_canonical.is_(False))
    ).one()

    # Most recent fork event, or None if no forks have been recorded yet.
    last_fork: Optional[ForkEvent] = session.exec(
        select(ForkEvent).order_by(ForkEvent.detected_at.desc())
    ).first()

    return {
        "canonical_blocks": canonical_blocks,
        "orphaned_blocks": orphaned_blocks,
        "stale_rate": calculate_stale_rate(canonical_blocks, orphaned_blocks),
        "last_fork_at": last_fork.detected_at if last_fork is not None else None,
    }
