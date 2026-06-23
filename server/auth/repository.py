from __future__ import annotations

import json
import secrets
from typing import Any

from ..config import Config
from ..db_access import connect, utc_now


def _role_order_key(role: str) -> tuple[int, str]:
    order = {
        "member": 0,
        "group_buy_maintainer": 1,
        "stock_keeper": 2,
        "admin": 3,
    }
    return (order.get(role, 99), role)


class AuthRepository:
    def __init__(self, config: Config):
        self.config = config

    def _dict_row(self):
        from psycopg.rows import dict_row

        return dict_row

    def _build_user_snapshot(self, conn, row: dict[str, Any]) -> dict[str, Any]:
        roles = self.list_roles(conn, row["id"])
        return {
            "id": row["id"],
            "groupId": row["group_id"],
            "account": row["account"],
            "displayName": row["display_name"],
            "qqNumber": row["qq_number"],
            "groupNickname": row["group_nickname"],
            "roles": roles,
            "status": row["status"],
        }

    def list_roles(self, conn, user_id: str) -> list[str]:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT role
                FROM user_roles
                WHERE user_id = %s
                """,
                (user_id,),
            )
            return sorted((row["role"] for row in cur.fetchall()), key=_role_order_key)

    def get_user_by_id(self, conn, user_id: str) -> dict[str, Any] | None:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM users
                WHERE id = %s
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()
        return self._build_user_snapshot(conn, row) if row else None

    def get_user_by_account_or_qq(
        self,
        conn,
        account_or_qq: str,
        *,
        active_only: bool = False,
    ) -> dict[str, Any] | None:
        status_sql = "AND status = 'active'" if active_only else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM users
                WHERE (account = %s OR qq_number = %s)
                {status_sql}
                LIMIT 1
                """,
                (account_or_qq, account_or_qq),
            )
            row = cur.fetchone()
        return self._build_user_snapshot(conn, row) if row else None

    def get_user_credentials_by_account_or_qq(
        self,
        conn,
        account_or_qq: str,
    ) -> dict[str, Any] | None:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM users
                WHERE status = 'active'
                  AND (account = %s OR qq_number = %s)
                LIMIT 1
                """,
                (account_or_qq, account_or_qq),
            )
            row = cur.fetchone()
        if row is None:
            return None

        snapshot = self._build_user_snapshot(conn, row)
        snapshot["passwordMeta"] = {
            "hash": row["password_hash"],
            "salt": row["password_salt"],
            "iterations": row["password_iterations"],
            "keyLength": row["password_key_length"],
            "digest": row["password_digest"],
        }
        return snapshot

    def ensure_group(
        self,
        conn,
        *,
        group_id: str,
        name: str,
        qq_group_number: str | None = None,
        description: str | None = None,
    ) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO groups (id, name, qq_group_number, description, status)
                VALUES (%s, %s, %s, %s, 'enabled')
                ON CONFLICT (id) DO UPDATE
                SET name = EXCLUDED.name,
                    qq_group_number = COALESCE(groups.qq_group_number, EXCLUDED.qq_group_number),
                    description = COALESCE(groups.description, EXCLUDED.description),
                    updated_at = NOW()
                """,
                (group_id, name, qq_group_number, description),
            )

    def create_user(
        self,
        conn,
        *,
        user_id: str,
        group_id: str,
        account: str,
        qq_number: str,
        display_name: str,
        group_nickname: str,
        password_meta: dict[str, Any],
        roles: list[str],
        status: str = "active",
    ) -> dict[str, Any]:
        now = utc_now()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (
                  id,
                  group_id,
                  account,
                  password_hash,
                  password_salt,
                  password_iterations,
                  password_key_length,
                  password_digest,
                  display_name,
                  qq_number,
                  group_nickname,
                  status,
                  password_changed_at,
                  created_at,
                  updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    group_id,
                    account,
                    password_meta["hash"],
                    password_meta["salt"],
                    int(password_meta["iterations"]),
                    int(password_meta["keyLength"]),
                    password_meta["digest"],
                    display_name,
                    qq_number,
                    group_nickname,
                    status,
                    now,
                    now,
                    now,
                ),
            )

            for role in sorted(set(roles), key=_role_order_key):
                cur.execute(
                    """
                    INSERT INTO user_roles (id, user_id, role)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, role) DO NOTHING
                    """,
                    (f"role_{secrets.token_hex(8)}", user_id, role),
                )

        return {
            "id": user_id,
            "groupId": group_id,
            "account": account,
            "displayName": display_name,
            "qqNumber": qq_number,
            "groupNickname": group_nickname,
            "roles": sorted(set(roles), key=_role_order_key),
            "status": status,
        }

    def ensure_user_roles(self, conn, user_id: str, roles: list[str]) -> None:
        with conn.cursor() as cur:
            for role in sorted(set(roles), key=_role_order_key):
                cur.execute(
                    """
                    INSERT INTO user_roles (id, user_id, role)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, role) DO NOTHING
                    """,
                    (f"role_{secrets.token_hex(8)}", user_id, role),
                )

    def update_last_login(self, conn, user_id: str) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET last_login_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (user_id,),
            )

    def update_profile(
        self,
        conn,
        *,
        user_id: str,
        display_name: str,
        group_nickname: str,
    ) -> dict[str, Any] | None:
        current_user = self.get_user_by_id(conn, user_id)
        if current_user is None:
            return None

        with conn.cursor() as cur:
            # 只有群昵称真的变化时才沉淀别名，避免噪音数据。
            if current_user["groupNickname"] != group_nickname:
                cur.execute(
                    """
                    INSERT INTO user_aliases (id, user_id, alias, source)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        f"alias_{secrets.token_hex(8)}",
                        user_id,
                        current_user["groupNickname"],
                        "group_nickname",
                    ),
                )

            cur.execute(
                """
                UPDATE users
                SET display_name = %s,
                    group_nickname = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (display_name, group_nickname, user_id),
            )

        return self.get_user_by_id(conn, user_id)

    def create_audit_log(
        self,
        conn,
        *,
        actor_user_id: str | None,
        action: str,
        object_type: str,
        object_id: str,
        before: Any,
        after: Any,
        reason: str | None,
    ) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_logs (
                  id,
                  actor_user_id,
                  action,
                  object_type,
                  object_id,
                  before_json,
                  after_json,
                  reason,
                  created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, NOW())
                """,
                (
                    f"audit_{secrets.token_hex(8)}",
                    actor_user_id,
                    action,
                    object_type,
                    object_id,
                    None if before is None else json.dumps(before, ensure_ascii=False),
                    None if after is None else json.dumps(after, ensure_ascii=False),
                    reason,
                ),
            )

    def get_default_group_id(self, conn) -> str | None:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT id
                FROM groups
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """
            )
            row = cur.fetchone()
        return row["id"] if row else None

    def get_health_counts(self) -> dict[str, Any]:
        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute("SELECT COUNT(*) AS total FROM groups")
                groups = cur.fetchone()["total"]
                cur.execute("SELECT COUNT(*) AS total FROM users")
                users = cur.fetchone()["total"]
                cur.execute("SELECT COUNT(*) AS total FROM auth_sessions")
                sessions = cur.fetchone()["total"]
            conn.rollback()

        return {"ok": True, "groups": groups, "users": users, "sessions": sessions}
