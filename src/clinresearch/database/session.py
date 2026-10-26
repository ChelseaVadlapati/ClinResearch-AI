"""Database engine configuration, with no embedded credentials."""

import os

from sqlalchemy import Engine, create_engine, event

from clinresearch.database.models import Base


def make_engine(url: str | None = None) -> Engine:
    """Create an engine; callers must configure DATABASE_URL explicitly."""
    url = url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Set DATABASE_URL (see .env.example)")
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


def initialize(engine: Engine) -> None:
    """Create the MVP schema; existing tables are preserved (not a migration tool)."""
    Base.metadata.create_all(engine)
