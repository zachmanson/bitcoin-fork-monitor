"""
REST endpoint: GET /api/forks

Returns a paginated list of fork events ordered by detected_at descending
(most recent first). The dashboard uses this to populate the fork history table.

Pagination is handled via offset and limit query parameters, which is the
standard REST pattern for paginated collections. SQLModel's .offset() and
.limit() translate directly to SQL OFFSET and LIMIT clauses.
"""

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import ForkEvent

router = APIRouter(prefix="/api", tags=["forks"])


@router.get("/forks")
def get_forks(
    offset: int = 0,
    # Query() lets us add constraints to query parameters.
    # le=200 means "less than or equal to 200" — prevents a caller from
    # requesting an unlimited number of rows in one shot.
    limit: int = Query(default=50, le=200),
    session: Session = Depends(get_session),
) -> list:
    """
    Return a paginated list of fork events, most recent first.

    Query parameters:
        offset (int): Number of records to skip. Default 0.
        limit  (int): Maximum records to return. Default 50, max 200.

    Returns:
        List of ForkEvent dicts ordered by detected_at DESC.
    """
    forks = session.exec(
        select(ForkEvent)
        .order_by(ForkEvent.detected_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    return list(forks)
