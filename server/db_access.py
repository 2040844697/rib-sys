from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import Config


def require_database_url(config: Config) -> str:
    if not config.database_url:
        raise RuntimeError("DATABASE_URL is required for database-backed authentication.")
    return config.database_url


def connect(config: Config, *, row_factory: Any | None = None):
    import psycopg

    kwargs: dict[str, Any] = {"autocommit": False}
    if row_factory is not None:
        kwargs["row_factory"] = row_factory
    return psycopg.connect(require_database_url(config), **kwargs)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
