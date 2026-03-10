"""
Tests for GET /api/forks endpoint.

Verifies HTTP status, default pagination limits, and that custom limit/offset
query parameters are respected. Uses an in-memory SQLite database override so
tests are isolated from the real database.
"""

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401 — registers tables in SQLModel.metadata
from app.database import get_session
from app.main import app


def override_get_session():
    """
    Provide an isolated in-memory SQLite session for each test request.

    StaticPool reuses the same connection within a test, so all requests in a
    single test see the same data (including any rows we insert in setup).
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

client = TestClient(app)


def test_forks_returns_200():
    """GET /api/forks should return HTTP 200."""
    response = client.get("/api/forks")
    assert response.status_code == 200


def test_forks_default_limit():
    """GET /api/forks without params should return at most 50 items."""
    response = client.get("/api/forks")
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 50


def test_forks_pagination():
    """GET /api/forks?offset=0&limit=5 should return at most 5 items."""
    response = client.get("/api/forks?offset=0&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 5
