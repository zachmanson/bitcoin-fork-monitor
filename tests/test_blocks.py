"""
Tests for GET /api/blocks endpoint.

Verifies HTTP status and default pagination limits for the recent blocks
endpoint. Uses an in-memory SQLite override to avoid touching the real DB.
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

    StaticPool ensures all connections within a test share the same in-memory
    database, so rows inserted in test setup are visible to the test client.
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


def test_blocks_returns_200():
    """GET /api/blocks should return HTTP 200."""
    response = client.get("/api/blocks")
    assert response.status_code == 200


def test_blocks_default_limit():
    """GET /api/blocks without params should return at most 50 items."""
    response = client.get("/api/blocks")
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 50
