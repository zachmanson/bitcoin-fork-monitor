"""
Tests for GET /api/stats endpoint.

These tests verify the stats summary endpoint returns the correct HTTP status
and response shape. The DB is overridden with an in-memory SQLite instance so
tests never touch the real bitcoin_fork.db file.

app.dependency_overrides is FastAPI's built-in dependency injection override
mechanism — it replaces get_session() with our test version for the duration
of these tests. This is how professional FastAPI test suites work: you swap the
database dependency rather than mocking individual queries.
"""

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401 — ensures SQLModel.metadata knows our tables
from app.database import get_session
from app.main import app

# --- Dependency override: use in-memory SQLite for tests ---


def override_get_session():
    """
    Replace the real DB session with an in-memory SQLite session.

    StaticPool ensures all connections reuse the same in-memory database
    (SQLite in-memory databases are per-connection by default, which would
    cause each request to see an empty database).
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_session] = override_get_session

# TestClient wraps the ASGI app and lets tests make HTTP requests synchronously.
# httpx is required under the hood (FastAPI 0.135+ uses httpx transport).
client = TestClient(app)


def test_stats_returns_200():
    """GET /api/stats should return HTTP 200."""
    response = client.get("/api/stats")
    assert response.status_code == 200


def test_stats_shape():
    """GET /api/stats response must include all required fields with correct types."""
    response = client.get("/api/stats")
    data = response.json()

    assert "canonical_blocks" in data
    assert "orphaned_blocks" in data
    assert "stale_rate" in data
    assert "last_fork_at" in data

    # Types check
    assert isinstance(data["canonical_blocks"], int)
    assert isinstance(data["orphaned_blocks"], int)
    assert isinstance(data["stale_rate"], float)
    # last_fork_at is null when no forks have been recorded
    assert data["last_fork_at"] is None or isinstance(data["last_fork_at"], str)
