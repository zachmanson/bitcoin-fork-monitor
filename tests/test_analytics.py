"""
Tests for app/analytics.py — stale rate formula.

The stale rate is the core metric of the bitcoin-fork-monitor project.
These tests pin the denominator definition so any change to the formula
immediately breaks CI.

Formula: orphaned / (canonical + orphaned)
"""
import pytest

from app.analytics import calculate_stale_rate


def test_stale_rate_normal_case():
    # 1 orphan in 100 total blocks = 1% stale rate
    assert calculate_stale_rate(canonical=99, orphaned=1) == pytest.approx(1 / 100)


def test_stale_rate_denominator_definition():
    # If this test fails, the denominator has been changed.
    # The formula must be orphaned / (canonical + orphaned).
    canonical = 95
    orphaned = 5
    result = calculate_stale_rate(canonical, orphaned)
    expected = orphaned / (canonical + orphaned)   # the correct formula
    assert result == pytest.approx(expected)
    assert result != pytest.approx(orphaned / canonical)  # explicitly NOT orphaned/canonical


def test_stale_rate_zero_blocks():
    # Fresh database: no division by zero
    assert calculate_stale_rate(canonical=0, orphaned=0) == 0.0


def test_stale_rate_all_orphaned():
    # Degenerate case: every block is orphaned
    assert calculate_stale_rate(canonical=0, orphaned=10) == pytest.approx(1.0)


def test_stale_rate_all_canonical():
    # No forks ever: stale rate is zero
    assert calculate_stale_rate(canonical=100, orphaned=0) == pytest.approx(0.0)


def test_stale_rate_negative_canonical_raises():
    with pytest.raises(ValueError):
        calculate_stale_rate(canonical=-1, orphaned=5)


def test_stale_rate_negative_orphaned_raises():
    with pytest.raises(ValueError):
        calculate_stale_rate(canonical=5, orphaned=-1)
