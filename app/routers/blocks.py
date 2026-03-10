"""
REST endpoint: GET /api/blocks

Returns the most recent blocks (by height) from the database, including both
canonical and orphaned blocks. The dashboard uses is_canonical to visually
highlight fork events — orphaned blocks appear with a visual indicator.

Why return both canonical and orphaned blocks?
    A fork means two blocks exist at the same height. If we filtered to
    canonical-only, the dashboard would never see the orphaned side of a fork.
    The frontend uses the is_canonical field to decide how to render each block.
"""

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import Block

router = APIRouter(prefix="/api", tags=["blocks"])


@router.get("/blocks")
def get_blocks(
    # le=200 caps the maximum page size to protect against large result sets.
    limit: int = Query(default=50, le=200),
    session: Session = Depends(get_session),
) -> list:
    """
    Return the most recent blocks by height descending.

    Returns both canonical and orphaned blocks. The dashboard uses
    is_canonical to visually highlight fork events.

    Query parameters:
        limit (int): Maximum records to return. Default 50, max 200.

    Returns:
        List of Block dicts ordered by height DESC.
    """
    blocks = session.exec(
        select(Block).order_by(Block.height.desc()).limit(limit)
    ).all()

    return list(blocks)
