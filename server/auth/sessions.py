from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any

from ..db_access import utc_now


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SessionRepository:
    def _dict_row(self):
        from psycopg.rows import dict_row

        return dict_row

    def create_session(
        self,
        conn,
        *,
        user_id: str,
        ttl_ms: int,
        created_ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        raw_token = secrets.token_urlsafe(32)
        issued_at = utc_now()
        expires_at = issued_at + timedelta(milliseconds=ttl_ms)

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth_sessions (
                  id,
                  user_id,
                  token_hash,
                  issued_at,
                  expires_at,
                  last_seen_at,
                  created_ip,
                  user_agent
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    f"session_{secrets.token_hex(8)}",
                    user_id,
                    hash_session_token(raw_token),
                    issued_at,
                    expires_at,
                    issued_at,
                    created_ip,
                    user_agent,
                ),
            )

        return {
            "token": raw_token,
            "issuedAt": issued_at,
            "expiresAt": expires_at,
        }

    def get_active_session_by_token(self, conn, token: str) -> dict[str, Any] | None:
        token_hash = hash_session_token(token)
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM auth_sessions
                WHERE token_hash = %s
                  AND revoked_at IS NULL
                  AND expires_at > NOW()
                LIMIT 1
                """,
                (token_hash,),
            )
            row = cur.fetchone()
        return row

    def touch_session(self, conn, session_id: str) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE auth_sessions
                SET last_seen_at = NOW()
                WHERE id = %s
                """,
                (session_id,),
            )

    def revoke_session_by_token(self, conn, token: str) -> None:
        token_hash = hash_session_token(token)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = NOW()
                WHERE token_hash = %s
                  AND revoked_at IS NULL
                """,
                (token_hash,),
            )

    def cleanup_expired_sessions(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM auth_sessions
                WHERE expires_at <= NOW()
                """
            )
