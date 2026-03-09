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
    # StaticPool reuses the same connection for all requests to this engine.
    # This is required for in-memory SQLite because each new connection gets
    # its own isolated database — without StaticPool, the session would see
    # an empty database even after create_all() ran on the engine.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Import models so SQLModel.metadata knows about our tables before create_all
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        yield session
