from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _read_int(value: str | None, fallback: int) -> int:
    if value is None:
        return fallback

    try:
        parsed = int(value)
    except ValueError:
        return fallback

    return parsed if parsed > 0 else fallback


@dataclass(frozen=True)
class Config:
    root_dir: Path
    host: str
    port: int
    data_file: Path
    session_ttl_ms: int
    seed_password: str
    admin_account: str
    admin_password: str


def load_config(root_dir: Path) -> Config:
    seed_password = os.environ.get("RIBSYS_SEED_PASSWORD", "123456")

    return Config(
      root_dir=root_dir,
      host=os.environ.get("RIBSYS_API_HOST", "127.0.0.1"),
      port=_read_int(os.environ.get("RIBSYS_API_PORT"), 8787),
      data_file=root_dir
      / os.environ.get("RIBSYS_API_DATA_FILE", "server/.data/dev-db.json"),
      session_ttl_ms=_read_int(os.environ.get("RIBSYS_SESSION_TTL_MS"), 7 * 24 * 60 * 60 * 1000),
      seed_password=seed_password,
      admin_account=os.environ.get("RIBSYS_ADMIN_ACCOUNT", "admin"),
      admin_password=os.environ.get("RIBSYS_ADMIN_PASSWORD", seed_password),
    )
