"""Small explicit configuration contract; errors never include credential values."""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy.engine import make_url


def database_url(value: str | None):
    if not value:
        raise ValueError("Set DATABASE_URL (see .env.example)")
    try:
        url = make_url(value)
    except Exception as exc:
        raise ValueError("DATABASE_URL is not a valid SQLAlchemy URL") from exc
    if url.drivername not in {"sqlite", "postgresql+psycopg"}:
        raise ValueError("DATABASE_URL must use sqlite or postgresql+psycopg")
    if url.drivername == "postgresql+psycopg" and not (url.host and url.database and url.username):
        raise ValueError("PostgreSQL configuration requires host, database and user")
    return url


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "event": record.getMessage(),
            }
        )


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
