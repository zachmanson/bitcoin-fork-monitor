"""
Pytest configuration and shared fixtures for the bitcoin-fork-monitor test suite.

Each test gets a fresh in-memory SQLite database via the session fixture.
StaticPool ensures the same in-memory connection is reused within a single test,
which is required for SQLite in-memory databases (different connections would see
different empty databases).
"""

import pytest
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import StaticPool


def _make_test_engine():
    """
    Create a fresh in-memory SQLite engine with all tables created.

    Using StaticPool is required for in-memory SQLite: without it, each new
    Session() call would open a new connection and see an empty database.
    With StaticPool, all connections share the same in-memory instance.
    """
    # Import models so SQLModel.metadata knows about our tables before create_all
    from app import models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="engine")
def engine_fixture():
    """
    Provide a fresh in-memory SQLite engine for a single test.

    Useful for tests that need to create their own Session objects (e.g.,
    background worker tests where the worker opens its own session internally).

    Yields:
        Engine: A SQLModel engine backed by an in-memory SQLite database.
    """
    yield _make_test_engine()


@pytest.fixture(name="session")
def session_fixture():
    """
    Provide an in-memory SQLite session for a single test.

    Creates all tables fresh for each test, yields a session, then tears down.
    No real database file is written — all data lives in memory and is discarded
    when the test completes.

    Yields:
        Session: A SQLModel session backed by an in-memory SQLite database.
    """
    engine = _make_test_engine()

    with Session(engine) as session:
        yield session
