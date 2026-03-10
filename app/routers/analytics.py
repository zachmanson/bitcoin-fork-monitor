"""
Analytics API endpoints for bitcoin-fork-monitor.

This module provides two historical analysis endpoints:

1. /api/analytics/stale-rate-over-time
   Groups blocks by calendar week or month and computes the stale rate
   for each bucket. Useful for spotting trends over time — did stale
   rates rise during a particular year?

2. /api/analytics/era-breakdown
   Groups blocks by difficulty adjustment era. Bitcoin recalculates its
   mining difficulty every 2016 blocks (roughly every two weeks). This
   boundary is technically precise: each era is a period of stable
   mining economics, making it a more meaningful unit than a calendar
   year or halving cycle. The halving is every 210,000 blocks; eras are
   every 2016 blocks — much finer granularity.

Why 2016-block eras specifically?
   The difficulty adjustment window IS the era boundary because it's the
   period over which network hashrate was stable. A high stale rate in
   one era vs another likely reflects a hashrate shift or mining
   centralization change, not random variation.

These endpoints are consumed by the SvelteKit frontend for rendering
time-series charts and era bar charts.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from app.analytics import calculate_stale_rate
from app.database import engine
from app.models import Block

# APIRouter lets us define a group of related endpoints in isolation.
# The prefix and tags here are picked up by FastAPI's OpenAPI docs.
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# Dependency injection: FastAPI will call this function and pass the
# resulting session into any route that declares it as a parameter.
# Using a generator + yield ensures the session is closed after each request,
# even if the request handler raises an exception.
def get_session():
    with Session(engine) as session:
        yield session


@router.get("/stale-rate-over-time")
def stale_rate_over_time(
    period: Literal["weekly", "monthly"] = "monthly",
    session: Session = Depends(get_session),
) -> list[dict]:
    """
    Return stale rate aggregated by time period.

    Query param:
        period: "monthly" (default) or "weekly"

    Returns a list of buckets sorted by period ascending. Each bucket:
        {
            "period":     "2009-01"    (monthly) or "2009-W01" (weekly),
            "canonical":  int,
            "orphaned":   int,
            "stale_rate": float        (range [0.0, 1.0])
        }

    Empty list is a valid response if the database has no blocks yet.

    SQLite date functions: strftime() formats a datetime column into a
    string. '%Y-%m' gives "YYYY-MM" for monthly grouping; '%Y-W%W' gives
    "YYYY-WNN" for weekly grouping. We use func.strftime() from SQLAlchemy
    to pass this through to the SQLite engine.
    """
    if period == "monthly":
        # SQLite strftime('%Y-%m', timestamp) → "2009-01"
        period_expr = func.strftime("%Y-%m", Block.timestamp)
    else:
        # SQLite strftime('%Y-W%W', timestamp) → "2009-W01"
        # %W = week number of the year (00-53, Monday as first day)
        period_expr = func.strftime("%Y-W%W", Block.timestamp)

    # Build the aggregation query.
    # func.sum(cast) counts True (1) vs False (0) values for canonical/orphaned.
    # This is a common SQLite pattern since there's no native COUNT(FILTER(...)).
    rows = session.exec(
        select(
            period_expr.label("bucket"),
            func.sum(Block.is_canonical.cast(int)).label("canonical"),
            func.sum((~Block.is_canonical).cast(int)).label("orphaned"),
        )
        .group_by(period_expr)
        .order_by(period_expr)
    ).all()

    result = []
    for row in rows:
        canonical = int(row.canonical or 0)
        orphaned = int(row.orphaned or 0)
        result.append(
            {
                "period": row.bucket,
                "canonical": canonical,
                "orphaned": orphaned,
                "stale_rate": calculate_stale_rate(canonical, orphaned),
            }
        )

    return result


@router.get("/era-breakdown")
def era_breakdown(session: Session = Depends(get_session)) -> list[dict]:
    """
    Return stale rate aggregated by difficulty adjustment era.

    Each era is a 2016-block window:
        era 0 = heights 0–2015
        era 1 = heights 2016–4031
        era N = heights (N*2016)–(N*2016 + 2015)

    Era number is computed as: height // 2016
    SQLite integer division floors automatically, matching Python's // behavior.

    Returns a list sorted by era ascending. Each item:
        {
            "era":          int,
            "height_start": int,       min height in this era
            "height_end":   int,       max height seen in this era
            "canonical":    int,
            "orphaned":     int,
            "stale_rate":   float,
            "low_confidence": bool     True for eras before height 321000
        }

    low_confidence marks eras where block data is less reliable.
    Bitcoin height ~321000 was reached in late 2014; before that, orphan
    detection was inconsistent (mempool.space historical data may have gaps).
    """
    # Integer division by 2016 gives the era number.
    # SQLAlchemy handles column / literal as integer division for integer columns.
    era_expr = (Block.height / 2016).label("era_num")

    rows = session.exec(
        select(
            era_expr,
            func.min(Block.height).label("height_start"),
            func.max(Block.height).label("height_end"),
            func.sum(Block.is_canonical.cast(int)).label("canonical"),
            func.sum((~Block.is_canonical).cast(int)).label("orphaned"),
        )
        .group_by(era_expr)
        .order_by(era_expr)
    ).all()

    result = []
    for row in rows:
        canonical = int(row.canonical or 0)
        orphaned = int(row.orphaned or 0)
        height_start = int(row.height_start)
        height_end = int(row.height_end)
        era_num = int(row.era_num)

        # Low-confidence threshold: eras that start before block 321000.
        # The number 321000 corresponds to approximately late 2014 /
        # early 2015 when the Bitcoin ecosystem was still maturing and
        # orphan tracking by block explorers was less complete.
        low_confidence = height_start < 321_000

        result.append(
            {
                "era": era_num,
                "height_start": height_start,
                "height_end": height_end,
                "canonical": canonical,
                "orphaned": orphaned,
                "stale_rate": calculate_stale_rate(canonical, orphaned),
                "low_confidence": low_confidence,
            }
        )

    return result
