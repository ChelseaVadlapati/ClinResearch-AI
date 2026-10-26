"""Isolated database fixtures; optional PostgreSQL uses a unique temporary schema."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from clinresearch.database.load import load_export
from clinresearch.database.models import Base
from clinresearch.database.session import initialize, make_engine
from clinresearch.ingestion.csv import validate_export

FIXTURE = Path(__file__).parent / "fixtures" / "synthea"


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURE


@pytest.fixture(params=["sqlite", "postgresql"] if os.getenv("TEST_DATABASE_URL") else ["sqlite"])
def engine(request):
    """Never clear a shared database: isolate PostgreSQL tests by random schema."""
    if request.param == "postgresql":
        url = os.environ["TEST_DATABASE_URL"]
        admin = create_engine(url)
        schema = f"test_{uuid4().hex}"
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        db = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        initialize(db)
        yield db
        db.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
    else:
        db = make_engine("sqlite://")
        db.dispose()
        # A single connection keeps in-memory SQLite visible in TestClient threads.
        db = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        from sqlalchemy import event

        @event.listens_for(db, "connect")
        def foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        initialize(db)
        yield db
        Base.metadata.drop_all(db)
        db.dispose()


@pytest.fixture
def loaded(engine, fixture_dir):
    load_export(engine, validate_export(fixture_dir))
    return engine
