from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from .config import Config


@dataclass(frozen=True)
class DbBootstrapResult:
    enabled: bool
    applied: bool
    reason: str
    checksum: str | None = None
    database_created: bool = False


def _log(message: str) -> None:
    print(f"[ribsys-db-bootstrap] {message}")


def describe_database_target(config: Config) -> str:
    if not config.database_url:
        return "DATABASE_URL=<unset>"

    parts = urlsplit(config.database_url)
    username = parts.username or "-"
    hostname = parts.hostname or "-"
    port = f":{parts.port}" if parts.port else ""
    database_name = parts.path.lstrip("/") or "-"
    schema = config.database_schema or "public"
    return f"{parts.scheme}://{username}@{hostname}{port}/{database_name} (schema={schema})"


def _replace_database_name(database_url: str, database_name: str) -> str:
    parts = urlsplit(database_url)
    path = f"/{database_name.lstrip('/')}"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _extract_database_name(database_url: str) -> str:
    parts = urlsplit(database_url)
    database_name = parts.path.lstrip("/")
    if not database_name:
        raise RuntimeError("DATABASE_URL must include a database name.")
    return database_name


def _ensure_database_exists(config: Config, psycopg_module) -> bool:
    from psycopg import sql

    target_database = _extract_database_name(config.database_url or "")
    admin_database_url = _replace_database_name(
        config.database_url or "",
        config.db_bootstrap_admin_db,
    )

    _log(
        "target database missing, checking via admin connection "
        f"'{config.db_bootstrap_admin_db}' for database '{target_database}'"
    )
    with psycopg_module.connect(admin_database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_database,))
            if cur.fetchone():
                _log(f"database '{target_database}' already exists")
                return False

            cur.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_database))
            )
            _log(f"database '{target_database}' created")

    return True


def _ensure_schema_exists(config: Config, conn) -> None:
    if not config.database_schema or config.database_schema == "public":
        return

    from psycopg import sql

    _log(f"ensuring schema '{config.database_schema}' exists")
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                sql.Identifier(config.database_schema)
            )
        )


def _is_missing_database_error(error: Exception) -> bool:
    sqlstate = getattr(error, "sqlstate", None)
    if sqlstate == "3D000":
        return True

    message = str(error).lower()
    return 'database "ribsys" does not exist' in message or "does not exist" in message and "database" in message


def initialize_database_schema(config: Config) -> DbBootstrapResult:
    if not config.database_url or not config.init_db_on_startup:
        _log("skipped because DATABASE_URL is not configured or startup init is disabled")
        return DbBootstrapResult(
            enabled=False,
            applied=False,
            reason="DATABASE_URL not configured or startup init disabled",
        )

    _log(
        "starting bootstrap "
        f"(target={describe_database_target(config)}, "
        f"init_sql={config.db_init_sql_file}, "
        f"admin_db={config.db_bootstrap_admin_db})"
    )
    if not config.db_init_sql_file.exists():
        _log(f"init SQL file not found: {config.db_init_sql_file}")
        raise RuntimeError(f"DB init SQL file not found: {config.db_init_sql_file}")

    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - depends on local environment
        _log("psycopg is not installed; database bootstrap cannot continue")
        raise RuntimeError(
            "DATABASE_URL is configured but psycopg is not installed. "
            "Run `pip install -r requirements.txt` first."
        ) from exc

    sql_text = config.db_init_sql_file.read_text(encoding="utf-8")
    checksum = hashlib.sha256(sql_text.encode("utf-8")).hexdigest()
    database_created = False
    _log(f"loaded init SQL (checksum={checksum[:12]})")

    try:
        _log("connecting to target database")
        conn = psycopg.connect(config.database_url, autocommit=True)
    except Exception as exc:
        if not _is_missing_database_error(exc):
            _log(f"failed to connect to target database: {exc}")
            raise
        _log(f"target database is missing, will attempt to create it: {exc}")
        database_created = _ensure_database_exists(config, psycopg)
        _log("retrying connection to target database")
        conn = psycopg.connect(config.database_url, autocommit=True)

    with conn:
        _ensure_schema_exists(config, conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ribsys_schema_bootstrap (
                  schema_name TEXT PRIMARY KEY,
                  checksum TEXT NOT NULL,
                  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            cur.execute(
                """
                SELECT checksum
                FROM ribsys_schema_bootstrap
                WHERE schema_name = %s
                """,
                ("core",),
            )
            row = cur.fetchone()

            if row and row[0] == checksum:
                _log("schema already up to date; skipping SQL apply")
                return DbBootstrapResult(
                    enabled=True,
                    applied=False,
                    reason="schema already up to date",
                    checksum=checksum,
                    database_created=database_created,
                )

            _log("applying init SQL")
            cur.execute(sql_text)
            cur.execute(
                """
                INSERT INTO ribsys_schema_bootstrap (schema_name, checksum, applied_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (schema_name)
                DO UPDATE SET
                  checksum = EXCLUDED.checksum,
                  applied_at = EXCLUDED.applied_at
                """,
                ("core", checksum),
            )

    result = DbBootstrapResult(
        enabled=True,
        applied=True,
        reason="database created and schema applied" if database_created else "schema applied",
        checksum=checksum,
        database_created=database_created,
    )
    _log(result.reason)
    return result
