from __future__ import annotations

from typing import Any

from ..config import Config
from ..db_access import connect
from ..store import hash_password
from .repository import AuthRepository


DEFAULT_GROUP = {
    "id": "group_1",
    "name": "月海谷仓",
    "qqGroupNumber": None,
    "description": "认证模块一期默认群组，用于保障注册后有基础可见性。",
}

ADMIN_ROLES = ["member", "group_buy_maintainer", "stock_keeper", "admin"]

DEMO_USERS: list[dict[str, Any]] = [
    {
        "id": "user_member",
        "groupId": "group_1",
        "account": "member",
        "displayName": "成员A",
        "qqNumber": "123456",
        "groupNickname": "A昵称",
        "roles": ["member"],
    },
    {
        "id": "user_maintainer",
        "groupId": "group_1",
        "account": "maintainer",
        "displayName": "维护人小满",
        "qqNumber": "223344",
        "groupNickname": "小满",
        "roles": ["member", "group_buy_maintainer"],
    },
    {
        "id": "user_stock",
        "groupId": "group_1",
        "account": "stock",
        "displayName": "囤货人阿简",
        "qqNumber": "334455",
        "groupNickname": "阿简",
        "roles": ["member", "stock_keeper"],
    },
]


def _mirror_audit(
    audit_store,
    *,
    actor_user_id: str | None,
    action: str,
    object_type: str,
    object_id: str,
    before: Any,
    after: Any,
    reason: str | None,
) -> None:
    if audit_store is None:
        return

    audit_store.create_audit_log(
        actor_user_id=actor_user_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        before=before,
        after=after,
        reason=reason,
    )
    audit_store.persist()


def ensure_identity_seed(config: Config, *, audit_store=None) -> dict[str, Any]:
    if not config.database_url:
        return {"enabled": False, "seededAdmin": False, "seededDemoUsers": 0}

    repo = AuthRepository(config)
    seeded_admin = False
    seeded_demo_users = 0

    with connect(config) as conn:
        repo.ensure_group(
            conn,
            group_id=DEFAULT_GROUP["id"],
            name=DEFAULT_GROUP["name"],
            qq_group_number=DEFAULT_GROUP["qqGroupNumber"],
            description=DEFAULT_GROUP["description"],
        )

        admin_user = repo.get_user_by_account_or_qq(conn, config.admin_account)
        if admin_user is None:
            admin_user = repo.create_user(
                conn,
                user_id="user_admin",
                group_id=DEFAULT_GROUP["id"],
                account=config.admin_account,
                qq_number="445566",
                display_name="管理员",
                group_nickname="管理员",
                password_meta=hash_password(config.admin_password),
                roles=ADMIN_ROLES,
            )
            repo.create_audit_log(
                conn,
                actor_user_id=None,
                action="user.seed_admin",
                object_type="user",
                object_id=admin_user["id"],
                before=None,
                after=admin_user,
                reason="服务启动自动初始化管理员",
            )
            _mirror_audit(
                audit_store,
                actor_user_id=None,
                action="user.seed_admin",
                object_type="user",
                object_id=admin_user["id"],
                before=None,
                after=admin_user,
                reason="服务启动自动初始化管理员",
            )
            seeded_admin = True
        else:
            repo.ensure_user_roles(conn, admin_user["id"], ADMIN_ROLES)

        if config.seed_demo_users:
            for demo in DEMO_USERS:
                existing = repo.get_user_by_account_or_qq(conn, demo["account"])
                if existing is not None:
                    repo.ensure_user_roles(conn, existing["id"], demo["roles"])
                    continue

                created = repo.create_user(
                    conn,
                    user_id=demo["id"],
                    group_id=demo["groupId"],
                    account=demo["account"],
                    qq_number=demo["qqNumber"],
                    display_name=demo["displayName"],
                    group_nickname=demo["groupNickname"],
                    password_meta=hash_password(config.seed_password),
                    roles=demo["roles"],
                )
                repo.create_audit_log(
                    conn,
                    actor_user_id=None,
                    action="user.seed_demo",
                    object_type="user",
                    object_id=created["id"],
                    before=None,
                    after=created,
                    reason="服务启动自动初始化演示账号",
                )
                _mirror_audit(
                    audit_store,
                    actor_user_id=None,
                    action="user.seed_demo",
                    object_type="user",
                    object_id=created["id"],
                    before=None,
                    after=created,
                    reason="服务启动自动初始化演示账号",
                )
                seeded_demo_users += 1

        conn.commit()

    return {
        "enabled": True,
        "seededAdmin": seeded_admin,
        "seededDemoUsers": seeded_demo_users,
    }
