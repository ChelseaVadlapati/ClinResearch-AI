"""Database engine configuration, with no embedded credentials."""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event

from clinresearch.configuration import database_url


def make_engine(url: str | None = None) -> Engine:
    """Create an engine; callers must configure DATABASE_URL explicitly."""
    url = url or os.environ.get("DATABASE_URL")
    engine = create_engine(database_url(url), pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


def initialize(engine: Engine) -> None:
    """Upgrade additively; preserve existing tables and records."""
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
