from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        env_key = key.strip()
        if not env_key or env_key in os.environ:
            continue

        os.environ[env_key] = _strip_quotes(value.strip())


def _read_int(value: str | None, fallback: int) -> int:
    if value is None:
        return fallback

    try:
        parsed = int(value)
    except ValueError:
        return fallback

    return parsed if parsed > 0 else fallback


def _read_bool(value: str | None, fallback: bool) -> bool:
    if value is None:
        return fallback

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return fallback


def _normalize_database_url(value: str | None) -> str | None:
    if not value:
        return value

    parts = urlsplit(value)
    if not parts.query:
        return value

    query_items = parse_qsl(parts.query, keep_blank_values=True)
    schema = None
    normalized_items: list[tuple[str, str]] = []

    for key, item_value in query_items:
        if key == "schema":
            schema = item_value
            continue
        normalized_items.append((key, item_value))

    if schema:
        options_value = next((item_value for key, item_value in normalized_items if key == "options"), None)
        search_path_option = f"-csearch_path={schema}"

        if options_value is None:
            normalized_items.append(("options", search_path_option))
        elif search_path_option not in options_value:
            updated_items: list[tuple[str, str]] = []
            for key, item_value in normalized_items:
                if key == "options":
                    updated_items.append((key, f"{item_value} {search_path_option}"))
                else:
                    updated_items.append((key, item_value))
            normalized_items = updated_items

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(normalized_items, doseq=True),
            parts.fragment,
        )
    )


def _extract_database_schema(value: str | None) -> str | None:
    if not value:
        return None

    parts = urlsplit(value)
    if not parts.query:
        return None

    query_items = parse_qsl(parts.query, keep_blank_values=True)
    for key, item_value in query_items:
        if key == "schema":
            return item_value or None

    return None


@dataclass(frozen=True)
class Config:
    root_dir: Path
    host: str
    port: int
    data_file: Path
    session_ttl_ms: int
    seed_password: str
    seed_demo_users: bool
    admin_account: str
    admin_password: str
    database_url: str | None
    database_schema: str | None
    db_init_sql_file: Path
    db_bootstrap_admin_db: str
    init_db_on_startup: bool
    minio_endpoint: str | None
    minio_access_key: str | None
    minio_secret_key: str | None


def load_config(root_dir: Path) -> Config:
    _load_env_file(root_dir / ".env")
    _load_env_file(root_dir / ".env.local")

    seed_password = os.environ.get("RIBSYS_SEED_PASSWORD", "123456")
    raw_database_url = os.environ.get("DATABASE_URL")

    return Config(
        root_dir=root_dir,
        host=os.environ.get("RIBSYS_API_HOST", "127.0.0.1"),
        port=_read_int(os.environ.get("RIBSYS_API_PORT"), 8787),
        data_file=root_dir / os.environ.get("RIBSYS_API_DATA_FILE", "server/.data/dev-db.json"),
        session_ttl_ms=_read_int(
            os.environ.get("RIBSYS_SESSION_TTL_MS"),
            7 * 24 * 60 * 60 * 1000,
        ),
        seed_password=seed_password,
        seed_demo_users=_read_bool(os.environ.get("RIBSYS_SEED_DEMO_USERS"), True),
        admin_account=os.environ.get("RIBSYS_ADMIN_ACCOUNT", "admin"),
        admin_password=os.environ.get("RIBSYS_ADMIN_PASSWORD", seed_password),
        database_url=_normalize_database_url(raw_database_url),
        database_schema=_extract_database_schema(raw_database_url),
        db_init_sql_file=root_dir / os.environ.get("RIBSYS_DB_INIT_SQL_FILE", "db/init.sql"),
        db_bootstrap_admin_db=os.environ.get("RIBSYS_DB_BOOTSTRAP_ADMIN_DB", "postgres"),
        init_db_on_startup=_read_bool(os.environ.get("RIBSYS_INIT_DB_ON_STARTUP"), True),
        minio_endpoint=os.environ.get("MINIO_ENDPOINT"),
        minio_access_key=os.environ.get("MINIO_ACCESS_KEY"),
        minio_secret_key=os.environ.get("MINIO_SECRET_KEY"),
    )
