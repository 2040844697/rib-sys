from __future__ import annotations

import copy
import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Config
from .errors import AppError
from .file_audit import AuditService, FileService, ensure_file_audit_state
from .warehouse_dispatch import WarehouseDispatchModule, ensure_warehouse_dispatch_state


ROLE_PERMISSIONS = {
    "member": [
        "group:view",
        "group_buy:view",
        "record:create_self",
        "record:view_self",
        "charge:view_self",
        "dispatch:create_self",
    ],
    "group_buy_maintainer": [
        "goods:create",
        "goods:update",
        "goods:view",
        "group_buy:create",
        "group_buy:update_own",
        "group_buy:update_any",
        "group_buy:cancel",
        "record:create_for_member",
        "record:view_group",
        "record:mark_exception",
        "charge:view_group",
        "charge:confirm_payment",
        "charge:adjust",
    ],
    "stock_keeper": [
        "dispatch:process_assigned",
        "warehouse:view",
        "goods:view",
        "charge:confirm_payment",
    ],
    "admin": ["group:edit", "member:manage", "audit:view", "user:manage", "role:manage"],
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clone(value: Any) -> Any:
    return copy.deepcopy(value)


def normalize_text(value: Any, field_name: str, min_length: int = 1) -> str:
    next_value = value.strip() if isinstance(value, str) else ""
    if len(next_value) < min_length:
        raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
    return next_value


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


def has_role(user: dict[str, Any], expected_roles: str | list[str]) -> bool:
    roles = expected_roles if isinstance(expected_roles, list) else [expected_roles]
    return any(role in user["roles"] for role in roles)


def has_permission(user: dict[str, Any], permission: str) -> bool:
    if "admin" in user["roles"]:
        return True

    return any(permission in ROLE_PERMISSIONS.get(role, []) for role in user["roles"])


def list_capabilities(user: dict[str, Any]) -> list[str]:
    capabilities = {"group:view", "group_buy:view", "record:create_self"}
    for role in user["roles"]:
        capabilities.update(ROLE_PERMISSIONS.get(role, []))
    return sorted(capabilities)


def create_seed_user(
    *,
    user_id: str,
    group_id: str,
    account: str,
    password: str,
    display_name: str,
    qq_number: str,
    group_nickname: str,
    roles: list[str],
) -> dict[str, Any]:
    timestamp = utc_now_iso()
    return {
        "id": user_id,
        "groupId": group_id,
        "account": account,
        "passwordMeta": hash_password(password),
        "displayName": display_name,
        "qqNumber": qq_number,
        "groupNickname": group_nickname,
        "roles": roles,
        "status": "active",
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }


def create_initial_data(config: Config) -> dict[str, Any]:
    timestamp = utc_now_iso()
    users = [
        create_seed_user(
            user_id="user_member",
            group_id="group_1",
            account="member",
            password=config.seed_password,
            display_name="成员A",
            qq_number="123456",
            group_nickname="A昵称",
            roles=["member"],
        ),
        create_seed_user(
            user_id="user_maintainer",
            group_id="group_1",
            account="maintainer",
            password=config.seed_password,
            display_name="维护人小满",
            qq_number="223344",
            group_nickname="小满",
            roles=["member", "group_buy_maintainer"],
        ),
        create_seed_user(
            user_id="user_stock",
            group_id="group_1",
            account="stock",
            password=config.seed_password,
            display_name="囤货人阿简",
            qq_number="334455",
            group_nickname="阿简",
            roles=["member", "stock_keeper"],
        ),
        create_seed_user(
            user_id="user_admin",
            group_id="group_1",
            account=config.admin_account,
            password=config.admin_password,
            display_name="管理员莓莓",
            qq_number="445566",
            group_nickname="莓莓",
            roles=["member", "group_buy_maintainer", "stock_keeper", "admin"],
        ),
        create_seed_user(
            user_id="user_guest_a",
            group_id="group_1",
            account="guest_a",
            password=config.seed_password,
            display_name="成员B",
            qq_number="556677",
            group_nickname="小果",
            roles=["member"],
        ),
        create_seed_user(
            user_id="user_guest_b",
            group_id="group_1",
            account="guest_b",
            password=config.seed_password,
            display_name="成员C",
            qq_number="667788",
            group_nickname="小羽",
            roles=["member"],
        ),
        create_seed_user(
            user_id="user_guest_c",
            group_id="group_2",
            account="guest_c",
            password=config.seed_password,
            display_name="测试成员D",
            qq_number="778899",
            group_nickname="小晴",
            roles=["member"],
        ),
    ]

    return {
        "version": 1,
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "counters": {
            "user": len(users),
            "userAlias": 0,
            "fileObject": 0,
            "auditLog": 0,
        },
        "groups": [
            {
                "id": "group_1",
                "name": "月海谷仓",
                "description": "第一阶段移动端优先体验团，用于验证拼团、付款和排发流程。",
                "coverImageUrl": None,
                "leaderId": "user_admin",
                "memberIds": [
                    "user_member",
                    "user_maintainer",
                    "user_stock",
                    "user_admin",
                    "user_guest_a",
                    "user_guest_b",
                ],
                "createdAt": timestamp,
                "updatedAt": timestamp,
            },
            {
                "id": "group_2",
                "name": "星砂拼团局",
                "description": "轻量测试团，保留一组简洁数据用于空状态和长文本验证。",
                "coverImageUrl": None,
                "leaderId": "user_maintainer",
                "memberIds": ["user_maintainer", "user_guest_c"],
                "createdAt": timestamp,
                "updatedAt": timestamp,
            },
        ],
        "users": users,
        "userAliases": [],
        "fileObjects": [],
        "auditLogs": [],
    }


def remove_group_buy_management_state(state: dict[str, Any]) -> bool:
    # 团购管理已迁移到 DB；这里只清理旧团购/商品 JSON。
    changed = False
    for key in ("groupBuys", "groupBuyItems"):
        if key in state:
            state.pop(key, None)
            changed = True
    counters = state.setdefault("counters", {})
    for key in ("groupBuy", "groupBuyItem"):
        if key in counters:
            counters.pop(key, None)
            changed = True
    return changed


def remove_order_logistics_state(state: dict[str, Any]) -> bool:
    # 订单物流已迁移到 DB；这里只清理旧下单和国际批次 JSON。
    changed = False
    for key in (
        "orderScreenshots",
        "internationalBatches",
        "internationalBatchRecords",
        "internationalFeeAllocations",
    ):
        if key in state:
            state.pop(key, None)
            changed = True
    counters = state.setdefault("counters", {})
    for key in (
        "orderScreenshot",
        "internationalBatch",
        "internationalBatchRecord",
        "internationalFeeAllocation",
    ):
        if key in counters:
            counters.pop(key, None)
            changed = True
    return changed


def remove_transfer_exception_state(state: dict[str, Any]) -> bool:
    # 转单和异常已迁移到 DB；这里只清理旧转单 JSON。
    changed = False
    for key in ("transfers", "transferItems"):
        if key in state:
            state.pop(key, None)
            changed = True
    counters = state.setdefault("counters", {})
    for key in ("transfer", "transferItem"):
        if key in counters:
            counters.pop(key, None)
            changed = True
    return changed


class LegacyJsonRuntime:
    def __init__(self, config: Config, state: dict[str, Any], created_fresh_data: bool):
        self.config = config
        self.state = state
        self.created_fresh_data = created_fresh_data
        self.sessions: dict[str, dict[str, Any]] = {}
        ensure_file_audit_state(self.state)
        remove_order_logistics_state(self.state)
        remove_transfer_exception_state(self.state)
        ensure_warehouse_dispatch_state(self.state)
        self.audit_service = AuditService(
            state=self.state,
            next_id=self.next_id,
            can_list_logs=self.can_list_audit_logs,
            can_view_log=self.can_view_audit_log,
            get_user_snapshot_by_id=self.get_user_snapshot_by_id,
        )
        self.file_service = FileService(
            state=self.state,
            next_id=self.next_id,
            audit_service=self.audit_service,
            get_user_snapshot_by_id=self.get_user_snapshot_by_id,
            now_iso=utc_now_iso,
        )
        self.warehouse_dispatch_module = WarehouseDispatchModule(
            state=self.state,
            next_id=self.next_id,
            audit_log=self.audit_service.log,
            now_iso=utc_now_iso,
            has_permission_by_user_id=self.has_permission_by_user_id,
            get_user_snapshot_by_id=self.get_user_snapshot_by_id,
            require_group_buy_record=self._database_group_buy_record_dependency_required,
            build_group_buy_record_summary=self._database_group_buy_record_dependency_required,
            mark_stocked=self._database_group_buy_record_dependency_required,
            mark_dispatch_requested=self._database_group_buy_record_dependency_required,
            mark_dispatched=self._database_group_buy_record_dependency_required,
            mark_completed=self._database_group_buy_record_dependency_required,
            link_charge=self._database_group_buy_record_dependency_required,
            create_charge=self._database_charge_dependency_required,
        )

    @property
    def startup_info(self) -> dict[str, Any]:
        return {
            "createdFreshData": self.created_fresh_data,
            "seedAccounts": [
                {"account": "member", "roles": ["member"]},
                {"account": "maintainer", "roles": ["member", "group_buy_maintainer"]},
                {"account": "stock", "roles": ["member", "stock_keeper"]},
                {
                    "account": self.config.admin_account,
                    "roles": ["member", "group_buy_maintainer", "stock_keeper", "admin"],
                },
            ],
        }

    def persist(self) -> None:
        self.state["updatedAt"] = utc_now_iso()
        self.config.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.config.data_file.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def next_id(self, counter_key: str, prefix: str) -> str:
        self.state["counters"][counter_key] += 1
        return f"{prefix}_{self.state['counters'][counter_key]}"

    def _database_charge_dependency_required(self, *args, **kwargs):
        raise RuntimeError("Charge creation now requires the database-backed AppContext module.")

    def _database_group_buy_dependency_required(self, *args, **kwargs):
        raise RuntimeError("Group buy management now requires the database-backed AppContext module.")

    def _database_group_buy_record_dependency_required(self, *args, **kwargs):
        raise RuntimeError("Group buy records now requires the database-backed AppContext module.")

    def create_audit_log(
        self,
        *,
        actor_user_id: str | None,
        action: str,
        object_type: str,
        object_id: str,
        before: Any,
        after: Any,
        reason: str | None,
    ) -> None:
        self.audit_service.log(
            actor_user_id=actor_user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before=before,
            after=after,
            reason=reason,
        )

    def cleanup_expired_sessions(self) -> None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        expired = [
            token for token, session in self.sessions.items() if session["expiresAt"] <= now_ms
        ]
        for token in expired:
            self.sessions.pop(token, None)

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        return next((user for user in self.state["users"] if user["id"] == user_id), None)

    def get_user_snapshot_by_id(self, user_id: str) -> dict[str, Any] | None:
        user = self.get_user_by_id(user_id)
        return self.get_user_snapshot(user) if user is not None else None

    def get_group_by_id(self, group_id: str) -> dict[str, Any] | None:
        return next((group for group in self.state["groups"] if group["id"] == group_id), None)

    def get_user_snapshot(self, user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": user["id"],
            "account": user["account"],
            "displayName": user["displayName"],
            "qqNumber": user["qqNumber"],
            "groupNickname": user["groupNickname"],
            "roles": clone(user["roles"]),
        }

    def can_view_group(self, user: dict[str, Any], group: dict[str, Any]) -> bool:
        return "admin" in user["roles"] or user["id"] in group["memberIds"]

    def can_view_group_buy(self, user: dict[str, Any], group_buy: dict[str, Any]) -> bool:
        group = self.get_group_by_id(group_buy["groupId"])
        return group is not None and self.can_view_group(user, group)

    def can_list_audit_logs(self, user: dict[str, Any]) -> bool:
        return has_permission(user, "audit:view")

    def can_view_audit_log(self, user: dict[str, Any], log: dict[str, Any]) -> bool:
        if has_permission(user, "audit:view"):
            return True

        actor_user_id = log.get("actorUserId")
        return actor_user_id == user["id"]

    def can_view_goods_catalog(self, user: dict[str, Any]) -> bool:
        return has_permission(user, "goods:view")

    def has_permission_by_user_id(self, user_id: str, permission: str) -> bool:
        user = self.get_user_by_id(user_id)
        return user is not None and has_permission(user, permission)

    def assert_goods_permission(self, user: dict[str, Any], permission: str) -> None:
        if not has_permission(user, permission):
            raise AppError(403, "当前账号没有商品图鉴权限", "FORBIDDEN")

    def require_order_logistics_user(self, actor_user_id: str) -> dict[str, Any]:
        user = self.get_user_by_id(actor_user_id)
        if user is None:
            raise AppError(404, "用户不存在", "NOT_FOUND")
        if not has_role(user, ["group_buy_maintainer", "admin"]):
            raise AppError(403, "当前账号没有下单转运维护权限", "FORBIDDEN")
        return user

    def assert_order_logistics_permission(self, actor_user_id: str) -> None:
        self.require_order_logistics_user(actor_user_id)

    def require_visible_group(self, user: dict[str, Any], group_id: str) -> dict[str, Any]:
        group = self.get_group_by_id(group_id)
        if group is None or not self.can_view_group(user, group):
            raise AppError(404, "谷团不存在", "NOT_FOUND")
        return group

    def on_charge_confirmed(
        self,
        charge_id: str,
        *,
        proof_id: str | None,
        actor_user_id: str | None,
    ) -> dict[str, Any]:
        return self.warehouse_dispatch_module.confirm_charge(
            charge_id,
            proof_id=proof_id,
            actor_user_id=actor_user_id,
        )

    def get_health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "groups": len(self.state["groups"]),
            "users": len(self.state["users"]),
            "fileObjects": len(self.state["fileObjects"]),
            "auditLogs": len(self.state["auditLogs"]),
            "stockItems": len(self.state["stockItems"]),
            "dispatchRequests": len(self.state["dispatchRequests"]),
            "dispatchItems": len(self.state["dispatchItems"]),
            "domesticShipments": len(self.state["domesticShipments"]),
        }

    def sync_registered_user(self, user: dict[str, Any]) -> None:
        existing = self.get_user_by_id(user["id"])
        if existing is None:
            self.state["users"].append(clone(user))
        else:
            existing.update(clone(user))

        default_group = self.get_group_by_id(user.get("groupId") or "group_1")
        # 业务页仍然依赖 memberIds，可见性在这里顺手补齐。
        if default_group and user["id"] not in default_group["memberIds"]:
            default_group["memberIds"].append(user["id"])
            default_group["updatedAt"] = utc_now_iso()

        self.persist()

    def sync_user_profile(self, *, user_id: str, display_name: str, group_nickname: str) -> None:
        user = self.get_user_by_id(user_id)
        if user is None:
            return

        # 这里只同步前端仍会读取的展示字段，避免影子数据再次长成主数据源。
        user["displayName"] = display_name
        user["groupNickname"] = group_nickname
        user["updatedAt"] = utc_now_iso()
        self.persist()

    def create_upload_object(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        result = self.file_service.create_upload_object(
            uploaded_by=user["id"],
            bucket=payload.get("bucket"),
            object_key=payload.get("objectKey"),
            url=payload.get("url"),
            content_type=payload.get("contentType"),
            size_bytes=payload.get("sizeBytes"),
        )
        self.persist()
        return result

    def void_file_object(
        self,
        user: dict[str, Any],
        file_object_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        result = self.file_service.void_file_object(
            actor_user_id=user["id"],
            file_object_id=file_object_id,
            reason=payload.get("reason"),
        )
        self.persist()
        return result

    def list_audit_logs(self, user: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        return self.audit_service.list_logs(user, filters)

    def stock_in_records(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        result = self.warehouse_dispatch_module.stock_in_records(payload, actor_user_id=user["id"])
        self.persist()
        return result

    def list_dispatchable_items(self, user: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        return self.warehouse_dispatch_module.list_dispatchable_items(filters, actor_user_id=user["id"])

    def create_dispatch_request(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        result = self.warehouse_dispatch_module.create_dispatch_request(payload, actor_user_id=user["id"])
        self.persist()
        return result

    def mark_dispatch_packed(
        self,
        user: dict[str, Any],
        dispatch_request_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        result = self.warehouse_dispatch_module.mark_dispatch_packed(
            dispatch_request_id,
            payload,
            actor_user_id=user["id"],
        )
        self.persist()
        return result

    def record_domestic_fee(
        self,
        user: dict[str, Any],
        dispatch_request_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        result = self.warehouse_dispatch_module.record_domestic_fee(
            dispatch_request_id,
            payload,
            actor_user_id=user["id"],
        )
        self.persist()
        return result

    def record_domestic_shipment(
        self,
        user: dict[str, Any],
        dispatch_request_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        result = self.warehouse_dispatch_module.record_domestic_shipment(
            dispatch_request_id,
            payload,
            actor_user_id=user["id"],
        )
        self.persist()
        return result

    def complete_dispatch_request(
        self,
        user: dict[str, Any],
        dispatch_request_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        result = self.warehouse_dispatch_module.complete_dispatch_request(
            dispatch_request_id,
            payload,
            actor_user_id=user["id"],
        )
        self.persist()
        return result

    def build_bootstrap(self, user: dict[str, Any]) -> dict[str, Any]:
        return {
            "currentUser": self.get_user_snapshot(user),
            "defaultGroupId": user.get("groupId") or self.state["groups"][0]["id"],
            "capabilities": list_capabilities(user),
        }

    def build_groups(self, user: dict[str, Any]) -> dict[str, Any]:
        items = []
        for group in self.state["groups"]:
            if not self.can_view_group(user, group):
                continue

            items.append(
                {
                    "id": group["id"],
                    "name": group["name"],
                    "coverImageUrl": group["coverImageUrl"],
                    "memberCount": len(group["memberIds"]),
                    "activeGroupBuyCount": 0,
                    "myRoles": clone(user["roles"]),
                }
            )

        return {"items": items}

    def build_group_home(self, group_id: str, user: dict[str, Any]) -> dict[str, Any]:
        group = self.require_visible_group(user, group_id)
        leader = self.get_user_by_id(group["leaderId"])

        return {
            "group": {
                "id": group["id"],
                "name": group["name"],
                "description": group["description"],
                "coverImageUrl": group["coverImageUrl"],
                "leader": {
                    "id": group["leaderId"],
                    "displayName": leader["displayName"] if leader else "团长",
                },
                "memberCount": len(group["memberIds"]),
                "myRoles": clone(user["roles"]),
            },
            "capabilities": {
                "canEditGroup": has_role(user, "admin"),
                "canEnterAdmin": has_role(user, ["group_buy_maintainer", "stock_keeper", "admin"]),
                "canCreateGroupBuy": has_permission(user, "group_buy:create"),
            },
            "summary": {
                "activeGroupBuyCount": 0,
                "myPendingPaymentCount": 0,
                "myDispatchableCount": 0,
            },
        }

    def build_admin_capabilities(self, group_id: str, user: dict[str, Any]) -> dict[str, Any]:
        self.require_visible_group(user, group_id)
        return {
            "modules": [
                {
                    "key": "goods_catalog",
                    "title": "鍟嗗搧鍥鹃壌",
                    "description": "缁存姢鍟嗗搧璧勬枡銆佸埆鍚嶅拰涓诲浘",
                    "enabled": has_permission(user, "goods:view"),
                },
                {
                    "key": "group_buys",
                    "title": "拼团管理",
                    "description": "新建、编辑和查看拼团",
                    "enabled": has_role(user, ["group_buy_maintainer", "admin"]),
                },
                {
                    "key": "records",
                    "title": "拼单记录",
                    "description": "查看成员认领和状态流转",
                    "enabled": has_role(user, ["group_buy_maintainer", "admin"]),
                },
                {
                    "key": "payments",
                    "title": "费用付款",
                    "description": "维护尾款、国际费和付款状态",
                    "enabled": has_role(user, ["group_buy_maintainer", "admin"]),
                },
                {
                    "key": "order_logistics",
                    "title": "下单转运",
                    "description": "维护下单截图、国际批次和费用分摊",
                    "enabled": has_role(user, ["group_buy_maintainer", "admin"]),
                },
                {
                    "key": "warehouse",
                    "title": "囤货排发",
                    "description": "入库、排发和国内快递",
                    "enabled": has_role(user, ["stock_keeper", "admin"]),
                },
                {
                    "key": "audit",
                    "title": "审计日志",
                    "description": "查看异常和角色变更记录",
                    "enabled": has_role(user, "admin"),
                },
            ]
        }

    def register_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        display_name = normalize_text(payload.get("displayName"), "展示名", 2)
        qq_number = normalize_text(payload.get("qqNumber"), "QQ 号", 5)
        group_nickname = normalize_text(payload.get("groupNickname"), "群昵称", 2)
        password = normalize_text(payload.get("password"), "密码", 6)
        confirm_password = normalize_text(payload.get("confirmPassword"), "确认密码", 6)

        if password != confirm_password:
            raise AppError(400, "两次输入的密码不一致", "VALIDATION_FAILED")

        duplicated = next(
            (
                user
                for user in self.state["users"]
                if user["account"] == qq_number or user["qqNumber"] == qq_number
            ),
            None,
        )
        if duplicated is not None:
            raise AppError(400, "这个 QQ 号已被使用，可直接登录或联系管理员", "DUPLICATED_OPERATION")

        user_id = self.next_id("user", "user")
        user = create_seed_user(
            user_id=user_id,
            group_id="group_1",
            account=qq_number,
            password=password,
            display_name=display_name,
            qq_number=qq_number,
            group_nickname=group_nickname,
            roles=["member"],
        )

        self.state["users"].append(user)
        default_group = self.get_group_by_id("group_1")
        if default_group and user["id"] not in default_group["memberIds"]:
            default_group["memberIds"].append(user["id"])
            default_group["updatedAt"] = utc_now_iso()

        self.audit_service.log(
            actor_user_id=None,
            action="user.register",
            object_type="user",
            object_id=user["id"],
            before=None,
            after=self.get_user_snapshot(user),
            reason="前端注册",
        )
        self.persist()
        return {"ok": True}

    def login(self, payload: dict[str, Any]) -> dict[str, Any]:
        account = normalize_text(payload.get("account"), "账号")
        password = normalize_text(payload.get("password"), "密码", 6)

        user = next(
            (
                item
                for item in self.state["users"]
                if item["status"] == "active"
                and (item["account"] == account or item["qqNumber"] == account)
            ),
            None,
        )
        if user is None or not verify_password(password, user["passwordMeta"]):
            raise AppError(
                401,
                "账号或密码不正确。开发种子账号包括 member / maintainer / stock / admin。",
                "UNAUTHORIZED",
            )

        session_token = secrets.token_urlsafe(24)
        expires_at = int(datetime.now(timezone.utc).timestamp() * 1000) + self.config.session_ttl_ms
        self.sessions[session_token] = {"userId": user["id"], "expiresAt": expires_at}

        return {
            "userId": user["id"],
            "displayName": user["displayName"],
            "roles": clone(user["roles"]),
            "next": "/app/groups",
            "sessionToken": session_token,
        }

    def get_user_by_session_token(self, session_token: str | None) -> dict[str, Any] | None:
        if not session_token:
            return None

        self.cleanup_expired_sessions()
        session = self.sessions.get(session_token)
        if session is None:
            return None

        return self.get_user_by_id(session["userId"])

    def logout(self, session_token: str | None) -> dict[str, Any]:
        if session_token:
            self.sessions.pop(session_token, None)
        return {"ok": True}

    def read_me(self, user: dict[str, Any]) -> dict[str, Any]:
        return self.get_user_snapshot(user)

    def update_me(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        target = self.get_user_by_id(user["id"])
        if target is None:
            raise AppError(404, "用户不存在", "NOT_FOUND")

        next_display_name = normalize_text(payload.get("displayName"), "展示名", 2)
        next_group_nickname = normalize_text(payload.get("groupNickname"), "群昵称", 2)
        before = self.get_user_snapshot(target)

        if target["groupNickname"] != next_group_nickname:
            self.state["userAliases"].append(
                {
                    "id": self.next_id("userAlias", "alias"),
                    "userId": target["id"],
                    "alias": target["groupNickname"],
                    "type": "group_nickname",
                    "createdAt": utc_now_iso(),
                }
            )

        target["displayName"] = next_display_name
        target["groupNickname"] = next_group_nickname
        target["updatedAt"] = utc_now_iso()

        self.audit_service.log(
            actor_user_id=user["id"],
            action="user.update_profile",
            object_type="user",
            object_id=target["id"],
            before=before,
            after=self.get_user_snapshot(target),
            reason="用户更新个人资料",
        )
        self.persist()
        return {"ok": True}


def create_legacy_json_runtime(config: Config) -> LegacyJsonRuntime:
    data_file: Path = config.data_file
    data_file.parent.mkdir(parents=True, exist_ok=True)
    needs_persist = False

    if data_file.exists():
        state = json.loads(data_file.read_text(encoding="utf-8"))
        created_fresh_data = False
    else:
        state = create_initial_data(config)
        created_fresh_data = True
        data_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if remove_group_buy_management_state(state):
        needs_persist = True
    if ensure_file_audit_state(state):
        needs_persist = True
    if remove_order_logistics_state(state):
        needs_persist = True
    if remove_transfer_exception_state(state):
        needs_persist = True
    if ensure_warehouse_dispatch_state(state):
        needs_persist = True

    store = LegacyJsonRuntime(config, state, created_fresh_data)
    if needs_persist and not created_fresh_data:
        store.persist()
    return store


# 兼容旧测试和迁移期导入。新代码请使用 LegacyJsonRuntime / AppContext。
Store = LegacyJsonRuntime
create_store = create_legacy_json_runtime
