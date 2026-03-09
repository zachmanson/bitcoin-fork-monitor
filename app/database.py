"""
Database engine configuration and session management for bitcoin-fork-monitor.

The production database is a SQLite file (bitcoin_fork.db) in the working
directory. This survives process restarts and is small enough for the expected
data volume (one row per Bitcoin block since genesis, ~900 000 blocks).
"""

from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = "sqlite:///bitcoin_fork.db"

# check_same_thread=False is required for SQLite when a connection might be
# used across multiple threads (FastAPI runs requests in a thread pool).
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def create_db_and_tables() -> None:
    """
    Create all database tables defined in the SQLModel metadata.

    This function is idempotent — calling it multiple times is safe and will not
    drop or alter existing tables. Call it once at application startup.

    The import of `app.models` is intentional: SQLModel.metadata only knows
    about a table after the class that defines it has been imported. Without this
    import, create_all() would create an empty schema.
    """
    from app import models  # noqa: F401 — side-effect import populates metadata

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session per request.

    Yields a Session and ensures it is closed when the request finishes,
    even if an exception was raised. Use this as a FastAPI Depends() argument.

    Yields:
        Session: An active SQLModel session bound to the production engine.

    Example:
        @app.get("/blocks")
        def list_blocks(session: Session = Depends(get_session)):
            return session.exec(select(Block)).all()
    """
    with Session(engine) as session:
        yield session
