"""
Data-layer business logic for bitcoin-fork-monitor.

This module holds pure computational functions — no database queries,
no HTTP calls, no side effects. Functions here take plain Python values
and return plain Python values, which makes them trivially testable.

Keeping business logic separate from I/O is a standard layering practice:
it lets you verify formulas are correct independently of whether the
database or network are working.
"""


def calculate_stale_rate(canonical: int, orphaned: int) -> float:
    """
    Calculate the stale block rate for a set of observed blocks.

    The stale rate measures what fraction of all blocks seen on the network
    were ultimately not included in the best chain (i.e. were orphaned).

    Formula:
        stale_rate = orphaned / (canonical + orphaned)

    The denominator is the total number of blocks seen, not just the
    canonical count. This is intentional: a stale rate of 1% means 1 in
    every 100 blocks broadcast was orphaned.

    Args:
        canonical: Number of blocks that ended up in the best chain (>= 0).
        orphaned:  Number of blocks that were not included in the best chain (>= 0).

    Returns:
        A float in the range [0.0, 1.0] representing the stale rate.
        Returns 0.0 when both counts are zero (no blocks observed yet).

    Raises:
        ValueError: If either argument is negative.
    """
    if canonical < 0 or orphaned < 0:
        raise ValueError(
            f"Block counts must be non-negative, got canonical={canonical}, orphaned={orphaned}"
        )

    total = canonical + orphaned

    if total == 0:
        return 0.0

    return orphaned / total
