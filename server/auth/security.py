from __future__ import annotations

import hashlib
import secrets
from typing import Any

from ..errors import AppError


def normalize_text(value: Any, field_name: str, min_length: int = 1) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if len(normalized) < min_length:
        raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
    return normalized


def hash_password(password: str, salt: str | None = None) -> dict[str, Any]:
    raw_salt = salt or secrets.token_hex(16)
    iterations = 120000
    key_length = 64
    digest = "sha512"
    hashed = hashlib.pbkdf2_hmac(
        digest,
        password.encode("utf-8"),
        raw_salt.encode("utf-8"),
        iterations,
        dklen=key_length,
    ).hex()

    return {
        "hash": hashed,
        "salt": raw_salt,
        "iterations": iterations,
        "keyLength": key_length,
        "digest": digest,
    }


def verify_password(password: str, password_meta: dict[str, Any]) -> bool:
    candidate = hashlib.pbkdf2_hmac(
        password_meta["digest"],
        password.encode("utf-8"),
        password_meta["salt"].encode("utf-8"),
        int(password_meta["iterations"]),
        dklen=int(password_meta["keyLength"]),
    ).hex()
    return secrets.compare_digest(candidate, password_meta["hash"])
