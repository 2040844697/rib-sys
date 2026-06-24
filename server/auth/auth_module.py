from __future__ import annotations

from typing import Any

from ..config import Config
from ..db_access import connect, to_iso
from ..errors import AppError
from .permissions import list_capabilities
from .repository import AuthRepository
from .security import hash_password, normalize_text, verify_password
from .sessions import SessionRepository


def _user_snapshot(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "account": user["account"],
        "displayName": user["displayName"],
        "qqNumber": user["qqNumber"],
        "groupNickname": user["groupNickname"],
        "roles": list(user["roles"]),
    }


class AuthModule:
    def __init__(self, config: Config):
        self.config = config
        self.repo = AuthRepository(config)
        self.sessions = SessionRepository()

    def is_enabled(self) -> bool:
        return bool(self.config.database_url)

    def get_health(self) -> dict[str, Any]:
        return self.repo.get_health_counts()

    def login(
        self,
        payload: dict[str, Any],
        *,
        created_ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        account = normalize_text(payload.get("account"), "账号")
        password = normalize_text(payload.get("password"), "密码", 6)

        with connect(self.config) as conn:
            user = self.repo.get_user_credentials_by_account_or_qq(conn, account)
            if user is None or not verify_password(password, user["passwordMeta"]):
                raise AppError(
                    401,
                    "账号或密码不正确。开发种子账号包括 member / maintainer / stock / admin。",
                    "UNAUTHORIZED",
                )

            self.sessions.cleanup_expired_sessions(conn)
            session = self.sessions.create_session(
                conn,
                user_id=user["id"],
                ttl_ms=self.config.session_ttl_ms,
                created_ip=created_ip,
                user_agent=user_agent,
            )
            audit_after = {
                "sessionExpiresAt": to_iso(session["expiresAt"]),
                "createdIp": created_ip,
                "userAgent": user_agent,
            }
            self.repo.update_last_login(conn, user["id"])
            self.repo.create_audit_log(
                conn,
                actor_user_id=user["id"],
                action="auth.login",
                object_type="user",
                object_id=user["id"],
                before=None,
                after=audit_after,
                reason="用户登录",
            )
            conn.commit()

        return {
            "userId": user["id"],
            "displayName": user["displayName"],
            "roles": list(user["roles"]),
            "next": "/app/groups",
            "sessionToken": session["token"],
            "session": {
                "expiresAt": to_iso(session["expiresAt"]),
            },
        }

    def register_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        display_name = normalize_text(payload.get("displayName"), "展示名", 2)
        qq_number = normalize_text(payload.get("qqNumber"), "QQ 号", 5)
        group_nickname = normalize_text(payload.get("groupNickname"), "群昵称", 2)
        password = normalize_text(payload.get("password"), "密码", 6)
        confirm_password = normalize_text(payload.get("confirmPassword"), "确认密码", 6)

        if password != confirm_password:
            raise AppError(400, "两次输入的密码不一致", "VALIDATION_FAILED")

        with connect(self.config) as conn:
            duplicated = self.repo.get_user_by_account_or_qq(conn, qq_number)
            if duplicated is not None:
                raise AppError(
                    400,
                    "这个 QQ 号已被使用，可以直接登录或联系管理员。",
                    "DUPLICATED_OPERATION",
                )

            default_group_id = self.repo.get_default_group_id(conn)
            if not default_group_id:
                raise AppError(500, "默认群组不存在，无法完成注册", "DEFAULT_GROUP_MISSING")

            user_id = f"user_{qq_number}"
            suffix = 1
            while self.repo.get_user_by_id(conn, user_id) is not None:
                suffix += 1
                user_id = f"user_{qq_number}_{suffix}"

            created_user = self.repo.create_user(
                conn,
                user_id=user_id,
                group_id=default_group_id,
                account=qq_number,
                qq_number=qq_number,
                display_name=display_name,
                group_nickname=group_nickname,
                password_meta=hash_password(password),
                roles=["member"],
            )
            self.repo.create_audit_log(
                conn,
                actor_user_id=None,
                action="user.register",
                object_type="user",
                object_id=created_user["id"],
                before=None,
                after=created_user,
                reason="前端注册",
            )
            conn.commit()

        return {
            "ok": True,
            "userId": created_user["id"],
            "canLoginNow": True,
            "nextAction": "login",
        }

    def get_user_by_session_token(self, session_token: str | None) -> dict[str, Any] | None:
        if not session_token:
            return None

        with connect(self.config) as conn:
            self.sessions.cleanup_expired_sessions(conn)
            session = self.sessions.get_active_session_by_token(conn, session_token)
            if session is None:
                conn.rollback()
                return None

            self.sessions.touch_session(conn, session["id"])
            user = self.repo.get_user_by_id(conn, session["user_id"])
            conn.commit()
            return user

    def logout(self, session_token: str | None) -> dict[str, Any]:
        if not session_token:
            return {"ok": True}

        with connect(self.config) as conn:
            session = self.sessions.get_active_session_by_token(conn, session_token)
            self.sessions.revoke_session_by_token(conn, session_token)
            if session is not None:
                self.repo.create_audit_log(
                    conn,
                    actor_user_id=session["user_id"],
                    action="auth.logout",
                    object_type="user",
                    object_id=session["user_id"],
                    before=None,
                    after=None,
                    reason="用户登出",
                )
            conn.commit()

        return {"ok": True}

    def build_bootstrap(self, user: dict[str, Any]) -> dict[str, Any]:
        return {
            "currentUser": _user_snapshot(user),
            "defaultGroupId": user["groupId"],
            "capabilities": list_capabilities(user),
        }

    def read_me(self, user: dict[str, Any]) -> dict[str, Any]:
        return _user_snapshot(user)

    def update_me(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        display_name = normalize_text(payload.get("displayName"), "展示名", 2)
        group_nickname = normalize_text(payload.get("groupNickname"), "群昵称", 2)

        with connect(self.config) as conn:
            before = self.repo.get_user_by_id(conn, user["id"])
            if before is None:
                raise AppError(404, "用户不存在", "NOT_FOUND")

            updated = self.repo.update_profile(
                conn,
                user_id=user["id"],
                display_name=display_name,
                group_nickname=group_nickname,
            )
            self.repo.create_audit_log(
                conn,
                actor_user_id=user["id"],
                action="user.update_profile",
                object_type="user",
                object_id=user["id"],
                before=before,
                after=updated,
                reason="用户更新个人资料",
            )
            conn.commit()

        return {"ok": True}
