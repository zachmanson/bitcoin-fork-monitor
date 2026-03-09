"""
Tests for app/database.py — covers DATA-01 requirements.

Verifies that create_db_and_tables() creates the expected schema and
can be called multiple times without error or side effects.
"""

import pytest
from sqlalchemy import inspect
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import StaticPool


def make_in_memory_engine():
    """
    Create a fresh in-memory SQLite engine for isolated database tests.

    Using StaticPool so all connections within this engine share the same
    in-memory database — required for SQLite in-memory mode.
    """
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


# DATA-01: create_db_and_tables() must create all three expected tables.
# This proves the schema definition is wired up correctly and models
# are imported before create_all() is called.
def test_create_tables_creates_all_three():
    """All three model tables exist after calling create_db_and_tables()."""
    engine = make_in_memory_engine()

    # Patch DATABASE_URL to use our in-memory engine for this test
    import app.database as db_module

    original_engine = db_module.engine
    db_module.engine = engine
    try:
        db_module.create_db_and_tables()
    finally:
        db_module.engine = original_engine

    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    assert "block" in table_names, f"Expected 'block' in tables, got: {table_names}"
    assert "forkevent" in table_names, f"Expected 'forkevent' in tables, got: {table_names}"
    assert "syncstate" in table_names, f"Expected 'syncstate' in tables, got: {table_names}"


# DATA-01: create_db_and_tables() must be safe to call multiple times.
# This matters because the function is called at application startup —
# a restart should not fail or corrupt the schema.
def test_create_tables_is_idempotent():
    """Calling create_db_and_tables() twice raises no exception."""
    engine = make_in_memory_engine()

    import app.database as db_module

    original_engine = db_module.engine
    db_module.engine = engine
    try:
        # Both calls must succeed without error
        db_module.create_db_and_tables()
        db_module.create_db_and_tables()
    finally:
        db_module.engine = original_engine
