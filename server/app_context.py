from __future__ import annotations

import secrets
from typing import Any

from .auth import AuthModule, ensure_identity_seed, has_permission, has_role
from .charge_payment import ChargePaymentModule, ChargePaymentRepository
from .config import Config
from .db_access import connect
from .errors import AppError
from .file_audit import DatabaseAuditService, DatabaseFileService
from .group_buy_management import GroupBuyModule, GroupBuyRepository
from .group_buy_records import GroupBuyRecordRepository, GroupBuyRecordsModule
from .group_buy_records.record_module import GROUP_BUY_RECORD_STATUS_DISPATCHABLE
from .goods_catalog import GoodsCatalogModule, GoodsCatalogRepository
from .order_logistics import OrderLogisticsModule, OrderLogisticsRepository
from .transfer_exception import TransferExceptionModule
from .warehouse_dispatch import WarehouseDispatchModule, WarehouseDispatchRepository


JSON_BACKEND_FLAG = "".join(["uses", "Legacy", "Json", "S", "tore"])


class AppContext:
    """Application composition root for database-backed modules."""

    def __init__(self, config: Config):
        self.config = config
        if not config.database_url:
            raise RuntimeError("DATABASE_URL is required.")

        self.auth = AuthModule(config)
        self.identity_bootstrap = ensure_identity_seed(config)
        self.audit_service = DatabaseAuditService(
            config=self.config,
            can_list_logs=self.can_list_audit_logs,
            get_user_snapshot_by_id=self.get_user_snapshot_by_id,
        )
        self.file_service = DatabaseFileService(
            config=self.config,
            audit_service=self.audit_service,
            get_user_snapshot_by_id=self.get_user_snapshot_by_id,
        )

        self.goods_catalog_module = GoodsCatalogModule(
            self.config,
            repository=GoodsCatalogRepository(self.config),
            file_service=self.file_service,
            audit_service=self.audit_service,
        )
        self.charge_payment_module = self._build_charge_payment_module()
        self.group_buy_records_module = self._build_group_buy_records_module()
        self.group_buy_management_module = self._build_group_buy_management_module()
        self.warehouse_dispatch_module = self._build_warehouse_dispatch_module()
        self.order_logistics_module = self._build_order_logistics_module()
        self.transfer_exception_module = self._build_transfer_exception_module()
        self._wire_group_buy_record_dependencies()
        self._wire_charge_payment_dependencies()

    def _build_charge_payment_module(self) -> ChargePaymentModule | None:
        if not self.config.database_url:
            return None
        return ChargePaymentModule(
            self.config,
            repository=ChargePaymentRepository(self.config),
            audit_service=self.audit_service,
            file_service=self.file_service,
            has_permission_by_user_id=self.has_permission_by_user_id,
            get_user_snapshot_by_id=self.get_user_snapshot_by_id,
            on_charge_confirmed=self.on_charge_confirmed,
        )

    def _build_group_buy_records_module(self) -> GroupBuyRecordsModule | None:
        if not self.config.database_url:
            return None
        return GroupBuyRecordsModule(
            self.config,
            repository=GroupBuyRecordRepository(self.config),
            audit_service=self.audit_service,
            has_permission_by_user_id=self.has_permission_by_user_id,
            has_group_access=self.has_group_access_by_user_id,
            get_user_snapshot_by_id=self.get_user_snapshot_by_id,
            create_charge=(
                self.charge_payment_module.create_charge_from_related_module_in_connection
                if self.charge_payment_module is not None
                else None
            ),
        )

    def _build_group_buy_management_module(self) -> GroupBuyModule | None:
        if not self.config.database_url:
            return None
        return GroupBuyModule(
            self.config,
            repository=GroupBuyRepository(self.config),
            get_goods_snapshot=self.goods_catalog_module.get_goods_snapshot,
            get_user_snapshot_by_id=self.get_user_snapshot_by_id,
            has_group_access=self.has_group_access_by_user_id,
            has_permission=self.has_permission_by_user_id,
            audit_service=self.audit_service,
            create_charge_from_related_module=(
                self.charge_payment_module.create_charge_from_related_module_in_connection
                if self.charge_payment_module is not None
                else None
            ),
        )

    def _build_warehouse_dispatch_module(self) -> WarehouseDispatchModule | None:
        if not self.config.database_url or self.group_buy_records_module is None:
            return None
        return WarehouseDispatchModule(
            self.config,
            repository=WarehouseDispatchRepository(self.config),
            audit_service=self.audit_service,
            has_permission_by_user_id=self.has_permission_by_user_id,
            get_user_snapshot_by_id=self.get_user_snapshot_by_id,
            require_group_buy_record=self.group_buy_records_module.require_record,
            build_group_buy_record_summary=self.group_buy_records_module.build_record_summary,
            mark_stocked_in_connection=self.group_buy_records_module.mark_stocked_in_connection,
            mark_dispatch_requested_in_connection=(
                self.group_buy_records_module.mark_dispatch_requested_in_connection
            ),
            mark_dispatched_in_connection=self.group_buy_records_module.mark_dispatched_in_connection,
            mark_completed_in_connection=self.group_buy_records_module.mark_completed_in_connection,
            link_charge_in_connection=self.group_buy_records_module.link_charge_in_connection,
            create_charge=(
                self.charge_payment_module.create_charge_from_related_module_in_connection
                if self.charge_payment_module is not None
                else None
            ),
        )

    def _build_order_logistics_module(self) -> OrderLogisticsModule | None:
        if not self.config.database_url:
            return None
        return OrderLogisticsModule(
            self.config,
            repository=OrderLogisticsRepository(self.config),
            audit_service=self.audit_service,
            assert_manage_permission=self.assert_order_logistics_permission,
            get_group_buy_for_write=self.get_group_buy_for_write,
            get_user_snapshot_by_id=self.get_user_snapshot_by_id,
            require_active_file_object=self.file_service.require_active_file_object,
            require_group_buy_record=(
                self.group_buy_records_module.require_record
                if self.group_buy_records_module is not None
                else None
            ),
            mark_ordered=(
                self.group_buy_records_module.mark_ordered
                if self.group_buy_records_module is not None
                else None
            ),
            mark_ordered_in_connection=(
                self.group_buy_records_module.mark_ordered_in_connection
                if self.group_buy_records_module is not None
                else None
            ),
            enter_transfer_flow=(
                self.group_buy_records_module.enter_transfer_flow
                if self.group_buy_records_module is not None
                else None
            ),
            enter_transfer_flow_in_connection=(
                self.group_buy_records_module.enter_transfer_flow_in_connection
                if self.group_buy_records_module is not None
                else None
            ),
            link_charge=(
                self.group_buy_records_module.link_charge
                if self.group_buy_records_module is not None
                else None
            ),
            link_charge_in_connection=(
                self.group_buy_records_module.link_charge_in_connection
                if self.group_buy_records_module is not None
                else None
            ),
            create_charge=(
                self.charge_payment_module.create_charge_from_related_module_in_connection
                if self.charge_payment_module is not None
                else None
            ),
            stock_in_batch=(
                self.warehouse_dispatch_module.stock_in_international_batch
                if self.warehouse_dispatch_module is not None
                else None
            ),
        )

    def _build_transfer_exception_module(self) -> TransferExceptionModule | None:
        if not self.config.database_url:
            return None
        return TransferExceptionModule(
            self.config,
            audit_service=self.audit_service,
            group_buy_records=self.group_buy_records_module,
            create_charge_adjustment=(
                self.charge_payment_module.create_charge_adjustment_in_connection
                if self.charge_payment_module is not None
                else None
            ),
            get_user_snapshot_by_id=self.get_user_snapshot_by_id,
            has_permission_by_user_id=self.has_permission_by_user_id,
            has_group_access_by_user_id=self.has_group_access_by_user_id,
        )

    def _wire_charge_payment_dependencies(self) -> None:
        if self.charge_payment_module is None:
            return
        if self.group_buy_records_module is not None:
            self.group_buy_records_module.create_charge = (
                self.charge_payment_module.create_charge_from_related_module_in_connection
            )
            self.charge_payment_module.group_buy_records_module = self.group_buy_records_module
        if self.order_logistics_module is not None:
            self.order_logistics_module.create_charge = (
                self.charge_payment_module.create_charge_from_related_module_in_connection
            )
        if self.warehouse_dispatch_module is not None:
            self.warehouse_dispatch_module.create_charge = (
                self.charge_payment_module.create_charge_from_related_module_in_connection
            )
        if self.transfer_exception_module is not None:
            self.transfer_exception_module.record_exceptions.create_charge_adjustment = (
                self.charge_payment_module.create_charge_adjustment_in_connection
            )
        if (
            self.group_buy_management_module is not None
            and self.order_logistics_module is not None
        ):
            self.order_logistics_module.get_group_buy_for_write = self.get_group_buy_for_write

    def _wire_group_buy_record_dependencies(self) -> None:
        if self.group_buy_records_module is None:
            return
        if self.group_buy_management_module is not None:
            self.group_buy_management_module.group_buy_records_module = self.group_buy_records_module
        if self.order_logistics_module is not None:
            self.order_logistics_module.require_group_buy_record = self.group_buy_records_module.require_record
            self.order_logistics_module.mark_ordered = self.group_buy_records_module.mark_ordered
            self.order_logistics_module.mark_ordered_in_connection = (
                self.group_buy_records_module.mark_ordered_in_connection
            )
            self.order_logistics_module.enter_transfer_flow = self.group_buy_records_module.enter_transfer_flow
            self.order_logistics_module.enter_transfer_flow_in_connection = (
                self.group_buy_records_module.enter_transfer_flow_in_connection
            )
            self.order_logistics_module.link_charge = self.group_buy_records_module.link_charge
            self.order_logistics_module.link_charge_in_connection = (
                self.group_buy_records_module.link_charge_in_connection
            )
        if self.transfer_exception_module is not None:
            self.transfer_exception_module.transfer_requests.group_buy_records = self.group_buy_records_module
            self.transfer_exception_module.record_exceptions.group_buy_records = self.group_buy_records_module

    @property
    def startup_info(self) -> dict[str, Any]:
        return {
            "dataBackend": "database",
            JSON_BACKEND_FLAG: False,
        }

    def read_user_from_session(self, session_token: str | None) -> dict[str, Any] | None:
        return self.auth.get_user_by_session_token(session_token)

    def get_user_snapshot_by_id(self, user_id: str) -> dict[str, Any] | None:
        with connect(self.config) as conn:
            user = self.auth.repo.get_user_by_id(conn, user_id)
            conn.rollback()
            return user

    def can_list_audit_logs(self, user: dict[str, Any]) -> bool:
        return has_permission(user, "audit:view")

    def has_permission_by_user_id(self, user_id: str, permission: str) -> bool:
        user = self.get_user_snapshot_by_id(user_id)
        return user is not None and has_permission(user, permission)

    def has_group_access_by_user_id(self, user_id: str, group_id: str) -> bool:
        user = self.get_user_snapshot_by_id(user_id)
        if user is None:
            return False
        return "admin" in user.get("roles", []) or user.get("groupId") == group_id

    def _dict_row(self):
        from psycopg.rows import dict_row

        return dict_row

    def _to_iso(self, value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat().replace("+00:00", "Z")
        return str(value)

    def _cent_to_cny(self, value: Any) -> str | None:
        if value is None:
            return None
        cents = int(value)
        sign = "-" if cents < 0 else ""
        cents = abs(cents)
        return f"{sign}{cents // 100}.{cents % 100:02d}"

    def _optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise AppError(400, "字段格式不正确", "VALIDATION_FAILED")
        normalized = value.strip()
        return normalized or None

    def _required_text(self, value: Any, field_name: str, min_length: int = 1) -> str:
        normalized = value.strip() if isinstance(value, str) else ""
        if len(normalized) < min_length:
            raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
        return normalized

    def _build_address(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "userId": row["user_id"],
            "receiverName": row["receiver_name"],
            "receiverPhone": row["receiver_phone"],
            "province": row.get("province"),
            "city": row.get("city"),
            "district": row.get("district"),
            "detailAddress": row["detail_address"],
            "postalCode": row.get("postal_code"),
            "isDefault": bool(row.get("is_default")),
            "note": row.get("note"),
            "createdAt": self._to_iso(row.get("created_at")),
            "updatedAt": self._to_iso(row.get("updated_at")),
        }

    def _infer_dispatch_warehouse_user_id(self, payload: dict[str, Any]) -> str:
        raw_items = payload.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise AppError(400, "items格式不正确", "VALIDATION_FAILED")
        stock_item_ids: list[str] = []
        for item in raw_items:
            if not isinstance(item, dict):
                raise AppError(400, "items格式不正确", "VALIDATION_FAILED")
            stock_item_id = item.get("stockItemId") or item.get("stock_item_id")
            if not isinstance(stock_item_id, str) or not stock_item_id.strip():
                raise AppError(400, "items.stockItemId填写不完整", "VALIDATION_FAILED")
            stock_item_ids.append(stock_item_id.strip())

        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    """
                    SELECT DISTINCT warehouse_user_id
                    FROM stock_items
                    WHERE id = ANY(%s)
                    """,
                    (stock_item_ids,),
                )
                rows = cur.fetchall()
            conn.rollback()

        if len(rows) != 1:
            raise AppError(400, "排发申请不能混合多个囤货人", "VALIDATION_FAILED")
        return rows[0]["warehouse_user_id"]

    def _list_charges_for_user(self, user_id: str) -> dict[str, Any]:
        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    """
                    SELECT
                      c.*,
                      payer.display_name AS payer_name,
                      payee.display_name AS payee_name,
                      submitted.id AS submitted_proof_id,
                      submitted.status AS submitted_proof_status,
                      submitted.proof_image_url AS submitted_proof_image_url,
                      confirmed.id AS confirmed_proof_id,
                      confirmed.status AS confirmed_proof_status
                    FROM charges c
                    JOIN users payer ON payer.id = c.payer_user_id
                    JOIN users payee ON payee.id = c.payee_user_id
                    LEFT JOIN payment_proofs submitted ON submitted.id = c.submitted_proof_id
                    LEFT JOIN payment_proofs confirmed ON confirmed.id = c.confirmed_proof_id
                    WHERE c.payer_user_id = %s
                       OR c.payee_user_id = %s
                    ORDER BY c.created_at DESC, c.id DESC
                    """,
                    (user_id, user_id),
                )
                rows = cur.fetchall()
            conn.rollback()

        items = [
            {
                "id": row["id"],
                "type": row["type"],
                "payerUserId": row["payer_user_id"],
                "payerName": row.get("payer_name"),
                "payeeUserId": row["payee_user_id"],
                "payeeName": row.get("payee_name"),
                "bizType": row["biz_type"],
                "bizId": row["biz_id"],
                "amountCny": self._cent_to_cny(row["amount_cny"]),
                "status": row["status"],
                "paymentChannelId": row.get("payment_channel_id"),
                "snapshot": row.get("snapshot_json") or {},
                "note": row.get("note"),
                "submittedProofId": row.get("submitted_proof_id"),
                "submittedProofStatus": row.get("submitted_proof_status"),
                "submittedProofImageUrl": row.get("submitted_proof_image_url"),
                "confirmedProofId": row.get("confirmed_proof_id"),
                "confirmedProofStatus": row.get("confirmed_proof_status"),
                "cancelledReason": row.get("cancelled_reason"),
                "createdAt": self._to_iso(row.get("created_at")),
                "updatedAt": self._to_iso(row.get("updated_at")),
            }
            for row in rows
        ]
        return {"items": items, "total": len(items)}

    def _get_visible_group(self, group_id: str, user: dict[str, Any]) -> dict[str, Any]:
        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    """
                    SELECT
                      g.*,
                      COUNT(u.id) FILTER (WHERE u.status = 'active') AS member_count
                    FROM groups g
                    LEFT JOIN users u ON u.group_id = g.id
                    WHERE g.id = %s
                      AND g.status = 'enabled'
                    GROUP BY g.id
                    LIMIT 1
                    """,
                    (group_id,),
                )
                group = cur.fetchone()
            conn.rollback()

        if group is None or not self.has_group_access_by_user_id(user["id"], group_id):
            raise AppError(404, "谷团不存在", "NOT_FOUND")
        return dict(group)

    def _build_group_summary(self, group: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": group["id"],
            "name": group["name"],
            "coverImageUrl": None,
            "memberCount": int(group.get("member_count") or 0),
            "activeGroupBuyCount": 0,
            "myRoles": list(user.get("roles", [])),
        }

    def _count_active_group_buys(self, group_id: str, user_id: str) -> int:
        if self.group_buy_management_module is None:
            return 0
        result = self.group_buy_management_module.build_group_buys(
            group_id,
            user_id,
            {"status": "进行中", "keyword": None},
        )
        return int(result.get("total") or len(result.get("items", [])))

    def on_charge_confirmed(
        self,
        charge_id: str,
        *,
        proof_id: str | None,
        actor_user_id: str | None,
        conn=None,
    ) -> dict[str, Any]:
        if self.warehouse_dispatch_module is None:
            return {"updatedCount": 0}
        if conn is not None:
            return self.warehouse_dispatch_module.confirm_charge_in_connection(
                conn,
                charge_id,
                proof_id=proof_id,
                actor_user_id=actor_user_id,
            )
        return self.warehouse_dispatch_module.confirm_charge(
            charge_id,
            proof_id=proof_id,
            actor_user_id=actor_user_id,
        )

    def assert_goods_permission(self, user: dict[str, Any], permission: str) -> None:
        if not has_permission(user, permission):
            raise AppError(403, "current user does not have goods permission", "FORBIDDEN")

    def assert_order_logistics_permission(self, actor_user_id: str) -> None:
        user = self.get_user_snapshot_by_id(actor_user_id)
        if user is None:
            raise AppError(404, "用户不存在", "NOT_FOUND")
        if not has_permission(user, "group_buy:update_any"):
            raise AppError(403, "当前账号没有下单转运维护权限", "FORBIDDEN")

    def health(self) -> dict[str, Any]:
        return {
            **self.auth.get_health(),
            "dataBackend": "database",
            JSON_BACKEND_FLAG: False,
        }

    def login(
        self,
        payload: dict[str, Any],
        *,
        created_ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        return self.auth.login(
            payload,
            created_ip=created_ip,
            user_agent=user_agent,
        )

    def register_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.auth.register_user(payload)

    def logout(self, session_token: str | None) -> dict[str, Any]:
        return self.auth.logout(session_token)

    def build_bootstrap(self, current_user: dict[str, Any]) -> dict[str, Any]:
        return self.auth.build_bootstrap(current_user)

    def build_groups(self, user: dict[str, Any]) -> dict[str, Any]:
        conditions = ["g.status = 'enabled'"]
        params: list[Any] = []
        if "admin" not in user.get("roles", []):
            conditions.append("g.id = %s")
            params.append(user["groupId"])

        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    f"""
                    SELECT
                      g.*,
                      COUNT(u.id) FILTER (WHERE u.status = 'active') AS member_count
                    FROM groups g
                    LEFT JOIN users u ON u.group_id = g.id
                    WHERE {" AND ".join(conditions)}
                    GROUP BY g.id
                    ORDER BY g.created_at ASC, g.id ASC
                    """,
                    params,
                )
                groups = cur.fetchall()
            conn.rollback()

        items = [self._build_group_summary(dict(group), user) for group in groups]
        for group in items:
            group["activeGroupBuyCount"] = self._count_active_group_buys(group["id"], user["id"])
        return {"items": items}

    def build_group_home(self, group_id: str, user: dict[str, Any]) -> dict[str, Any]:
        group = self._get_visible_group(group_id, user)
        result = {
            "group": {
                "id": group["id"],
                "name": group["name"],
                "description": group.get("description"),
                "coverImageUrl": None,
                "leader": {
                    "id": None,
                    "displayName": "团长",
                },
                "memberCount": int(group.get("member_count") or 0),
                "myRoles": list(user.get("roles", [])),
            },
            "capabilities": {
                "canEditGroup": has_role(user, "admin"),
                "canEnterAdmin": has_role(user, ["group_buy_maintainer", "stock_keeper", "admin"]),
                "canCreateGroupBuy": has_permission(user, "group_buy:create"),
            },
            "summary": {
                "activeGroupBuyCount": self._count_active_group_buys(group_id, user["id"]),
                "myPendingPaymentCount": 0,
                "myDispatchableCount": 0,
            },
        }
        if self.charge_payment_module is not None:
            result["summary"]["myPendingPaymentCount"] = (
                self.charge_payment_module.count_pending_charges_for_user(user["id"])
            )
        if self.group_buy_records_module is not None:
            result["summary"]["myDispatchableCount"] = (
                self.group_buy_records_module.count_member_records_by_status(
                    member_user_id=user["id"],
                    status="可排发",
                )
            )
        return result

    def search_group_members(
        self,
        group_id: str,
        user: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._get_visible_group(group_id, user)
        keyword = str((params or {}).get("keyword") or "").strip()
        raw_page_size = (params or {}).get("pageSize")
        try:
            page_size = int(raw_page_size) if raw_page_size else 20
        except (TypeError, ValueError):
            page_size = 20
        page_size = max(1, min(page_size, 50))

        can_search_group = has_permission(user, "record:create_for_member") or has_permission(user, "user:manage")
        conditions = ["u.group_id = %s", "u.status = 'active'"]
        values: list[Any] = [group_id]
        if keyword:
            conditions.append(
                "(u.display_name ILIKE %s OR u.group_nickname ILIKE %s OR u.qq_number ILIKE %s OR u.account ILIKE %s)"
            )
            keyword_like = f"%{keyword}%"
            values.extend([keyword_like, keyword_like, keyword_like, keyword_like])
        if not can_search_group:
            conditions.append("u.id = %s")
            values.append(user["id"])
        values.append(page_size)

        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    f"""
                    SELECT u.id, u.display_name, u.group_nickname, u.qq_number, u.group_id
                    FROM users u
                    WHERE {" AND ".join(conditions)}
                    ORDER BY
                      CASE WHEN u.id = %s THEN 0 ELSE 1 END,
                      u.display_name ASC,
                      u.id ASC
                    LIMIT %s
                    """,
                    [*values[:-1], user["id"], values[-1]],
                )
                rows = cur.fetchall()
            conn.rollback()

        items = [
            {
                "id": row["id"],
                "groupId": row["group_id"],
                "displayName": row["display_name"],
                "groupNickname": row.get("group_nickname"),
                "qqNumber": row.get("qq_number"),
            }
            for row in rows
        ]
        return {"items": items, "total": len(items)}

    def build_admin_capabilities(self, group_id: str, user: dict[str, Any]) -> dict[str, Any]:
        self._get_visible_group(group_id, user)
        return {
            "modules": [
                {
                    "key": "goods_catalog",
                    "title": "商品图鉴",
                    "description": "维护商品、图片和价格信息",
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

    def _require_group_buy_management_module(self) -> GroupBuyModule:
        if self.group_buy_management_module is None:
            raise RuntimeError("Group buy management database module requires DATABASE_URL.")
        return self.group_buy_management_module

    def build_group_buys(
        self,
        group_id: str,
        user: dict[str, Any],
        filters: dict[str, str | None],
    ) -> dict[str, Any]:
        # 团购列表主路径：只读数据库团购和商品聚合。
        return self._require_group_buy_management_module().build_group_buys(
            group_id,
            user["id"],
            filters,
        )

    def build_group_buy_detail(self, group_buy_id: str, user: dict[str, Any]) -> dict[str, Any]:
        # 团购详情主路径：只读数据库商品库存和当前用户认领记录。
        return self._require_group_buy_management_module().build_group_buy_detail(
            group_buy_id,
            user["id"],
        )

    def create_group_buy(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 新建团购：DB 版负责校验权限、写业务表和审计。
        return self._require_group_buy_management_module().create_group_buy(user["id"], payload)

    def update_group_buy(
        self,
        user: dict[str, Any],
        group_buy_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 更新团购基础信息。
        return self._require_group_buy_management_module().update_group_buy(
            user["id"],
            group_buy_id,
            payload,
        )

    def change_group_buy_status(
        self,
        user: dict[str, Any],
        group_buy_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 团购状态流转，合法性由 DB 版模块统一判断。
        return self._require_group_buy_management_module().change_group_buy_status(
            user["id"],
            group_buy_id,
            payload,
        )

    def create_group_buy_item(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 新建团购商品，可引用 goods 快照或手填快照。
        return self._require_group_buy_management_module().create_group_buy_item(
            user["id"],
            payload,
        )

    def update_group_buy_item(
        self,
        user: dict[str, Any],
        group_buy_item_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 更新团购商品快照、库存和价格。
        return self._require_group_buy_management_module().update_group_buy_item(
            user["id"],
            group_buy_item_id,
            payload,
        )

    def delete_group_buy_item(self, user: dict[str, Any], group_buy_item_id: str) -> dict[str, Any]:
        return self._require_group_buy_management_module().delete_group_buy_item(
            user["id"],
            group_buy_item_id,
        )

    def claim_group_buy_item(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 成员认领走 DB 版拼单记录模块，事务内扣库存、写记录、生成首款费用。
        return self._require_group_buy_records_module().create_record_for_user(user["id"], payload)

    def _require_group_buy_records_module(self) -> GroupBuyRecordsModule:
        if self.group_buy_records_module is None:
            raise RuntimeError("Group buy records database module requires DATABASE_URL.")
        return self.group_buy_records_module

    def _require_transfer_exception_module(self) -> TransferExceptionModule:
        if self.transfer_exception_module is None:
            raise RuntimeError("Transfer exception database module requires DATABASE_URL.")
        return self.transfer_exception_module

    def release_group_buy_item_stock(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 释放已认领库存，供维护动作显式调用。
        return self._require_group_buy_management_module().release_item_stock(
            user["id"],
            payload,
        )

    def request_price_adjustment(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 提交调价申请，价格仍按“分”落库。
        return self._require_group_buy_management_module().request_price_adjustment(
            user["id"],
            payload,
        )

    def _require_order_logistics_module(self) -> OrderLogisticsModule:
        if self.order_logistics_module is None:
            raise RuntimeError("Order logistics database module requires DATABASE_URL.")
        return self.order_logistics_module

    def _require_warehouse_dispatch_module(self) -> WarehouseDispatchModule:
        if self.warehouse_dispatch_module is None:
            raise RuntimeError("Warehouse dispatch database module requires DATABASE_URL.")
        return self.warehouse_dispatch_module

    def stock_in_records(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 囤货入库入口，交给 DB 版仓库排发模块处理。
        return self._require_warehouse_dispatch_module().stock_in_records(
            payload,
            actor_user_id=user["id"],
        )

    def list_dispatchable_items(self, user: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        # 查询可排发库存入口，数据从 stock_items 和 group_buy_records 推导。
        result = self._require_warehouse_dispatch_module().list_dispatchable_items(
            filters,
            actor_user_id=user["id"],
        )
        stock_item_ids = [item["stockItemId"] for item in result.get("items", [])]
        if not stock_item_ids:
            return result

        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    """
                    SELECT
                      si.id AS stock_item_id,
                      gb.id AS group_buy_id,
                      gb.title AS group_buy_title,
                      gb.type AS group_buy_type,
                      gbi.id AS group_buy_item_id,
                      gbi.name_snapshot AS item_name,
                      gbi.image_url_snapshot AS item_image_url,
                      warehouse.display_name AS warehouse_name
                    FROM stock_items si
                    JOIN group_buy_records r ON r.id = si.group_buy_record_id
                    JOIN group_buys gb ON gb.id = r.group_buy_id
                    JOIN group_buy_items gbi ON gbi.id = r.group_buy_item_id
                    JOIN users warehouse ON warehouse.id = si.warehouse_user_id
                    WHERE si.id = ANY(%s)
                    """,
                    (stock_item_ids,),
                )
                rows = cur.fetchall()
            conn.rollback()

        extra_by_stock_item_id = {row["stock_item_id"]: row for row in rows}
        result["items"] = [
            {
                **item,
                "groupBuy": {
                    "id": extra_by_stock_item_id.get(item["stockItemId"], {}).get("group_buy_id")
                    or item.get("groupBuyId"),
                    "title": extra_by_stock_item_id.get(item["stockItemId"], {}).get("group_buy_title"),
                    "type": extra_by_stock_item_id.get(item["stockItemId"], {}).get("group_buy_type"),
                },
                "item": {
                    "id": extra_by_stock_item_id.get(item["stockItemId"], {}).get("group_buy_item_id")
                    or item.get("groupBuyItemId"),
                    "name": extra_by_stock_item_id.get(item["stockItemId"], {}).get("item_name"),
                    "imageUrl": extra_by_stock_item_id.get(item["stockItemId"], {}).get("item_image_url"),
                },
                "warehouseUser": {
                    "id": item.get("warehouseUserId"),
                    "displayName": extra_by_stock_item_id.get(item["stockItemId"], {}).get("warehouse_name"),
                },
            }
            for item in result.get("items", [])
        ]
        return result

    def create_dispatch_request(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 创建排发申请入口，写 dispatch_requests 和 dispatch_items。
        if not (payload.get("warehouseUserId") or payload.get("warehouse_user_id")):
            payload = {**payload, "warehouseUserId": self._infer_dispatch_warehouse_user_id(payload)}
        return self._require_warehouse_dispatch_module().create_dispatch_request(
            payload,
            actor_user_id=user["id"],
        )

    def mark_dispatch_packed(
        self,
        user: dict[str, Any],
        dispatch_request_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 标记排发申请已打包入口。
        return self._require_warehouse_dispatch_module().mark_dispatch_packed(
            dispatch_request_id,
            payload,
            actor_user_id=user["id"],
        )

    def record_domestic_fee(
        self,
        user: dict[str, Any],
        dispatch_request_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 录入国内运费入口。
        return self._require_warehouse_dispatch_module().record_domestic_fee(
            dispatch_request_id,
            payload,
            actor_user_id=user["id"],
        )

    def record_domestic_shipment(
        self,
        user: dict[str, Any],
        dispatch_request_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 录入国内快递入口。
        return self._require_warehouse_dispatch_module().record_domestic_shipment(
            dispatch_request_id,
            payload,
            actor_user_id=user["id"],
        )

    def complete_dispatch_request(
        self,
        user: dict[str, Any],
        dispatch_request_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 完成排发申请入口。
        return self._require_warehouse_dispatch_module().complete_dispatch_request(
            dispatch_request_id,
            payload,
            actor_user_id=user["id"],
        )

    def add_order_screenshot(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 下单截图写入 DB 表 order_screenshots。
        return self._require_order_logistics_module().add_order_screenshot(user["id"], payload)

    def mark_records_ordered(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 标记记录已下单，事实由 order_screenshots 和审计日志表达。
        return self._require_order_logistics_module().mark_records_ordered(user["id"], payload)

    def create_international_batch(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 创建国际转运批次。
        return self._require_order_logistics_module().create_international_batch(user["id"], payload)

    def add_records_to_international_batch(
        self,
        user: dict[str, Any],
        batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 将拼单记录加入国际批次。
        return self._require_order_logistics_module().add_records_to_batch(
            user["id"],
            batch_id,
            payload,
        )

    def update_international_batch_shipping(
        self,
        user: dict[str, Any],
        batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 更新国际批次物流信息。
        return self._require_order_logistics_module().update_batch_shipping(
            user["id"],
            batch_id,
            payload,
        )

    def record_international_batch_arrived_domestic(
        self,
        user: dict[str, Any],
        batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 记录国际批次到达国内。
        return self._require_order_logistics_module().record_batch_arrived_domestic(
            user["id"],
            batch_id,
            payload,
        )

    def stock_in_international_batch(
        self,
        user: dict[str, Any],
        batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 国际批次入库入口，逻辑迁回仓库排发模块。
        return self._require_warehouse_dispatch_module().stock_in_international_batch(
            batch_id,
            payload,
            actor_user_id=user["id"],
        )

    def record_international_batch_fees(
        self,
        user: dict[str, Any],
        batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 录入国际费用和分摊，事务内创建费用单并关联记录。
        return self._require_order_logistics_module().record_batch_fees(
            user["id"],
            batch_id,
            payload,
        )

    def get_group_buy_for_write(self, actor_user_id: str, group_buy_id: str) -> dict[str, Any]:
        # 供下单转运模块校验团购存在性，仍然只读 DB 团购表。
        module = self._require_group_buy_management_module()
        module._assert_permission(
            actor_user_id,
            "group_buy:update_any",
            error_message="当前账号没有下单转运维护权限",
        )
        with connect(self.config) as conn:
            group_buy = module._require_group_buy(conn, group_buy_id)
            conn.rollback()
        module._require_group_access(actor_user_id, group_buy["groupId"])
        return group_buy

    def read_me(self, current_user: dict[str, Any]) -> dict[str, Any]:
        return self.auth.read_me(current_user)

    def update_me(self, current_user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        return self.auth.update_me(current_user, payload)

    def create_upload_object(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        return self.file_service.create_upload_object(
            uploaded_by=user["id"],
            bucket=payload.get("bucket"),
            object_key=payload.get("objectKey"),
            url=payload.get("url"),
            content_type=payload.get("contentType"),
            size_bytes=payload.get("sizeBytes"),
        )

    def create_uploaded_file_object(
        self,
        user: dict[str, Any],
        *,
        bucket: str,
        object_key: str,
        url: str,
        content_type: str | None,
        size_bytes: int,
    ) -> dict[str, Any]:
        return self.file_service.create_upload_object(
            uploaded_by=user["id"],
            bucket=bucket,
            object_key=object_key,
            url=url,
            content_type=content_type,
            size_bytes=size_bytes,
        )

    def void_file_object(
        self,
        user: dict[str, Any],
        file_object_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.file_service.void_file_object(
            actor_user_id=user["id"],
            file_object_id=file_object_id,
            reason=payload.get("reason"),
        )

    def list_audit_logs(self, user: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        return self.audit_service.list_logs(user, filters)

    def _require_charge_payment_module(self) -> ChargePaymentModule:
        if self.charge_payment_module is None:
            raise RuntimeError("Charge/payment database module requires DATABASE_URL.")
        return self.charge_payment_module

    def list_my_records(self, user: dict[str, Any]) -> dict[str, Any]:
        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    """
                    SELECT
                      r.*,
                      gb.title AS group_buy_title,
                      gb.type AS group_buy_type,
                      gb.status AS group_buy_status,
                      gbi.name_snapshot AS item_name,
                      gbi.image_url_snapshot AS item_image_url,
                      gbi.unit_price_cny AS item_unit_price_cny,
                      gbi.character_names_snapshot AS item_character_names,
                      goods_charge.status AS goods_charge_status,
                      goods_charge.amount_cny AS goods_charge_amount_cny,
                      intl_charge.status AS international_charge_status,
                      intl_charge.amount_cny AS international_charge_amount_cny,
                      domestic_charge.status AS domestic_charge_status,
                      domestic_charge.amount_cny AS domestic_charge_amount_cny,
                      dr.status AS dispatch_status,
                      t.status AS transfer_status
                    FROM group_buy_records r
                    JOIN group_buys gb ON gb.id = r.group_buy_id
                    JOIN group_buy_items gbi ON gbi.id = r.group_buy_item_id
                    LEFT JOIN charges goods_charge ON goods_charge.id = r.goods_charge_id
                    LEFT JOIN charges intl_charge ON intl_charge.id = r.international_charge_id
                    LEFT JOIN charges domestic_charge ON domestic_charge.id = r.domestic_shipping_charge_id
                    LEFT JOIN dispatch_requests dr ON dr.id = r.dispatch_request_id
                    LEFT JOIN transfers t ON t.id = r.transfer_id
                    WHERE r.member_user_id = %s
                    ORDER BY r.created_at DESC, r.id DESC
                    """,
                    (user["id"],),
                )
                rows = cur.fetchall()
            conn.rollback()

        items = []
        for row in rows:
            character_names = row.get("item_character_names") or []
            items.append(
                {
                    "id": row["id"],
                    "groupBuyId": row["group_buy_id"],
                    "groupBuyTitle": row["group_buy_title"],
                    "groupBuyType": row["group_buy_type"],
                    "groupBuyStatus": row["group_buy_status"],
                    "groupBuyItemId": row["group_buy_item_id"],
                    "itemName": row["item_name"],
                    "itemImageUrl": row.get("item_image_url"),
                    "characterNames": character_names,
                    "quantity": row["quantity"],
                    "unitPriceCny": self._cent_to_cny(row.get("item_unit_price_cny")),
                    "status": row["status"],
                    "displayStatus": row["status"],
                    "isException": bool(row.get("is_exception")),
                    "exceptionReason": row.get("exception_reason"),
                    "charges": {
                        "goods": {
                            "id": row.get("goods_charge_id"),
                            "status": row.get("goods_charge_status"),
                            "amountCny": self._cent_to_cny(row.get("goods_charge_amount_cny")),
                        }
                        if row.get("goods_charge_id")
                        else None,
                        "international": {
                            "id": row.get("international_charge_id"),
                            "status": row.get("international_charge_status"),
                            "amountCny": self._cent_to_cny(row.get("international_charge_amount_cny")),
                        }
                        if row.get("international_charge_id")
                        else None,
                        "domesticShipping": {
                            "id": row.get("domestic_shipping_charge_id"),
                            "status": row.get("domestic_charge_status"),
                            "amountCny": self._cent_to_cny(row.get("domestic_charge_amount_cny")),
                        }
                        if row.get("domestic_shipping_charge_id")
                        else None,
                    },
                    "dispatchRequestId": row.get("dispatch_request_id"),
                    "dispatchStatus": row.get("dispatch_status"),
                    "transferId": row.get("transfer_id"),
                    "transferStatus": row.get("transfer_status"),
                    "createdAt": self._to_iso(row.get("created_at")),
                    "updatedAt": self._to_iso(row.get("updated_at")),
                }
            )
        return {"items": items, "total": len(items)}

    def list_my_charges(self, user: dict[str, Any]) -> dict[str, Any]:
        return self._list_charges_for_user(user["id"])

    def submit_charge_payment_proof(
        self,
        user: dict[str, Any],
        charge_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        charge = self._require_charge_payment_module().require_charge(charge_id)
        if charge["payerUserId"] != user["id"] and not has_permission(user, "charge:adjust"):
            raise AppError(403, "当前账号不能为这笔费用上传付款凭证", "FORBIDDEN")
        normalized_payload = {
            **payload,
            "submittedBy": payload.get("submittedBy") or user["id"],
            "fromUserId": payload.get("fromUserId") or charge["payerUserId"],
            "toUserId": payload.get("toUserId") or charge["payeeUserId"],
            "amountCny": payload.get("amountCny") or charge["amountCny"],
            "allocations": payload.get("allocations")
            or [
                {
                    "chargeId": charge_id,
                    "allocatedAmountCny": payload.get("amountCny") or charge["amountCny"],
                }
            ],
        }
        return self.submit_payment_proof(user, normalized_payload)

    def list_payment_channels(self, user: dict[str, Any]) -> dict[str, Any]:
        conditions = ["pc.status = 'active'"]
        params: list[Any] = []
        if not has_permission(user, "charge:view_group"):
            conditions.append("pc.owner_user_id = %s")
            params.append(user["id"])
        elif "admin" not in user.get("roles", []):
            conditions.append("(pc.owner_user_id = %s OR owner.group_id = %s)")
            params.extend([user["id"], user["groupId"]])

        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    f"""
                    SELECT
                      pc.*,
                      owner.display_name AS owner_display_name,
                      owner.group_nickname AS owner_group_nickname
                    FROM payment_channels pc
                    JOIN users owner ON owner.id = pc.owner_user_id
                    WHERE {" AND ".join(conditions)}
                    ORDER BY pc.created_at DESC, pc.id DESC
                    """,
                    params,
                )
                rows = cur.fetchall()
            conn.rollback()

        items = [
            {
                "id": row["id"],
                "ownerUserId": row["owner_user_id"],
                "ownerName": row.get("owner_display_name") or row.get("owner_group_nickname"),
                "type": row["type"],
                "displayName": row["display_name"],
                "qrFileObjectId": row.get("qr_file_object_id"),
                "qrImageUrl": row.get("qr_image_url"),
                "accountText": row.get("account_text"),
                "note": row.get("note"),
                "status": row["status"],
                "createdAt": self._to_iso(row.get("created_at")),
                "updatedAt": self._to_iso(row.get("updated_at")),
            }
            for row in rows
        ]
        return {"items": items, "total": len(items)}

    def create_payment_channel(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        normalized_payload = {
            **payload,
            "ownerUserId": payload.get("ownerUserId") or payload.get("owner_user_id") or user["id"],
        }
        return self._require_charge_payment_module().create_payment_channel(user["id"], normalized_payload)

    def create_charge(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        if not has_permission(user, "charge:adjust"):
            raise AppError(403, "current user cannot create charges", "FORBIDDEN")
        return self._require_charge_payment_module().create_charge(payload, actor_user_id=user["id"])

    def cancel_charge(
        self,
        user: dict[str, Any],
        charge_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._require_charge_payment_module().cancel_charge(user["id"], charge_id, payload)

    def submit_payment_proof(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        return self._require_charge_payment_module().submit_payment_proof(
            {
                **payload,
                "submittedBy": payload.get("submittedBy") or user["id"],
            }
        )

    def confirm_payment_proof(
        self,
        user: dict[str, Any],
        proof_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._require_charge_payment_module().confirm_payment_proof(user["id"], proof_id, payload)

    def reject_payment_proof(
        self,
        user: dict[str, Any],
        proof_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._require_charge_payment_module().reject_payment_proof(user["id"], proof_id, payload)

    def create_charge_adjustment(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        return self._require_charge_payment_module().create_charge_adjustment(user["id"], payload)

    def request_transfer(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 杞崟鐢宠鐢?transfer_exception 妯″潡鍐呯殑 DB workflow 澶勭悊銆?
        return self._require_transfer_exception_module().request_transfer(user, payload)

    def list_dispatch_requests(self, user: dict[str, Any]) -> dict[str, Any]:
        conditions: list[str] = []
        params: list[Any] = []
        if "admin" in user.get("roles", []):
            pass
        elif has_permission(user, "dispatch:process_assigned"):
            conditions.append("dr.warehouse_user_id = %s")
            params.append(user["id"])
        else:
            conditions.append("dr.requester_user_id = %s")
            params.append(user["id"])

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    f"""
                    SELECT
                      dr.*,
                      requester.display_name AS requester_name,
                      warehouse.display_name AS warehouse_name,
                      COUNT(di.id) AS item_count,
                      COALESCE(SUM(di.quantity), 0) AS total_quantity
                    FROM dispatch_requests dr
                    JOIN users requester ON requester.id = dr.requester_user_id
                    JOIN users warehouse ON warehouse.id = dr.warehouse_user_id
                    LEFT JOIN dispatch_items di ON di.dispatch_request_id = dr.id
                    {where_sql}
                    GROUP BY dr.id, requester.display_name, warehouse.display_name
                    ORDER BY dr.created_at DESC, dr.id DESC
                    """,
                    params,
                )
                rows = cur.fetchall()
            conn.rollback()

        items = [
            {
                "id": row["id"],
                "requesterUserId": row["requester_user_id"],
                "requesterName": row.get("requester_name"),
                "warehouseUserId": row["warehouse_user_id"],
                "warehouseName": row.get("warehouse_name"),
                "status": row["status"],
                "receiverName": row["receiver_name"],
                "receiverPhone": row["receiver_phone"],
                "receiverAddress": row["receiver_address"],
                "itemCount": int(row.get("item_count") or 0),
                "totalQuantity": int(row.get("total_quantity") or 0),
                "shippingFeeCny": self._cent_to_cny(row.get("shipping_fee_cny")),
                "feeMode": row.get("fee_mode"),
                "domesticChargeId": row.get("domestic_charge_id"),
                "submittedAt": self._to_iso(row.get("submitted_at")),
                "packedAt": self._to_iso(row.get("packed_at")),
                "shippedAt": self._to_iso(row.get("shipped_at")),
                "completedAt": self._to_iso(row.get("completed_at")),
                "createdAt": self._to_iso(row.get("created_at")),
                "updatedAt": self._to_iso(row.get("updated_at")),
            }
            for row in rows
        ]
        return {"items": items, "total": len(items)}

    def list_transfers(self, user: dict[str, Any]) -> dict[str, Any]:
        conditions: list[str] = []
        params: list[Any] = []
        if not has_permission(user, "record:create_for_member"):
            conditions.append("(t.from_user_id = %s OR t.to_user_id = %s OR t.requested_by = %s)")
            params.extend([user["id"], user["id"], user["id"]])

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    f"""
                    SELECT
                      t.*,
                      from_user.display_name AS from_user_name,
                      to_user.display_name AS to_user_name,
                      requester.display_name AS requested_by_name,
                      COUNT(ti.id) AS item_count,
                      COALESCE(SUM(ti.quantity), 0) AS total_quantity
                    FROM transfers t
                    JOIN users from_user ON from_user.id = t.from_user_id
                    JOIN users to_user ON to_user.id = t.to_user_id
                    JOIN users requester ON requester.id = t.requested_by
                    LEFT JOIN transfer_items ti ON ti.transfer_id = t.id
                    {where_sql}
                    GROUP BY t.id, from_user.display_name, to_user.display_name, requester.display_name
                    ORDER BY t.created_at DESC, t.id DESC
                    """,
                    params,
                )
                rows = cur.fetchall()
            conn.rollback()

        items = [
            {
                "id": row["id"],
                "fromUserId": row["from_user_id"],
                "fromUserName": row.get("from_user_name"),
                "toUserId": row["to_user_id"],
                "toUserName": row.get("to_user_name"),
                "requestedBy": row["requested_by"],
                "requestedByName": row.get("requested_by_name"),
                "status": row["status"],
                "reason": row.get("reason"),
                "rejectReason": row.get("reject_reason"),
                "itemCount": int(row.get("item_count") or 0),
                "totalQuantity": int(row.get("total_quantity") or 0),
                "createdAt": self._to_iso(row.get("created_at")),
                "updatedAt": self._to_iso(row.get("updated_at")),
            }
            for row in rows
        ]
        return {"items": items, "total": len(items)}

    def list_exceptions(self, user: dict[str, Any]) -> dict[str, Any]:
        if not has_permission(user, "record:mark_exception") and not has_permission(user, "audit:view"):
            raise AppError(403, "当前账号没有查看异常的权限", "FORBIDDEN")

        conditions = ["r.is_exception = TRUE"]
        params: list[Any] = []
        if "admin" not in user.get("roles", []):
            conditions.append("gb.group_id = %s")
            params.append(user["groupId"])

        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    f"""
                    SELECT
                      r.*,
                      gb.title AS group_buy_title,
                      gbi.name_snapshot AS item_name,
                      member.display_name AS member_name
                    FROM group_buy_records r
                    JOIN group_buys gb ON gb.id = r.group_buy_id
                    JOIN group_buy_items gbi ON gbi.id = r.group_buy_item_id
                    JOIN users member ON member.id = r.member_user_id
                    WHERE {" AND ".join(conditions)}
                    ORDER BY r.updated_at DESC, r.id DESC
                    """,
                    params,
                )
                rows = cur.fetchall()
            conn.rollback()

        items = [
            {
                "id": row["id"],
                "groupBuyRecordId": row["id"],
                "groupBuyId": row["group_buy_id"],
                "groupBuyTitle": row.get("group_buy_title"),
                "groupBuyItemId": row["group_buy_item_id"],
                "itemName": row.get("item_name"),
                "memberUserId": row["member_user_id"],
                "memberName": row.get("member_name"),
                "quantity": row["quantity"],
                "status": row["status"],
                "exceptionReason": row.get("exception_reason"),
                "note": row.get("note"),
                "createdAt": self._to_iso(row.get("created_at")),
                "updatedAt": self._to_iso(row.get("updated_at")),
            }
            for row in rows
        ]
        return {"items": items, "total": len(items)}

    def list_users(self, user: dict[str, Any]) -> dict[str, Any]:
        if not has_permission(user, "user:manage"):
            raise AppError(403, "当前账号没有查看用户列表的权限", "FORBIDDEN")

        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    """
                    SELECT u.*, g.name AS group_name
                    FROM users u
                    JOIN groups g ON g.id = u.group_id
                    ORDER BY u.created_at DESC, u.id DESC
                    """
                )
                rows = cur.fetchall()
            items = []
            for row in rows:
                roles = self.auth.repo.list_roles(conn, row["id"])
                items.append(
                    {
                        "id": row["id"],
                        "groupId": row["group_id"],
                        "groupName": row.get("group_name"),
                        "account": row["account"],
                        "displayName": row["display_name"],
                        "qqNumber": row["qq_number"],
                        "groupNickname": row["group_nickname"],
                        "roles": roles,
                        "status": row["status"],
                        "lastLoginAt": self._to_iso(row.get("last_login_at")),
                        "createdAt": self._to_iso(row.get("created_at")),
                        "updatedAt": self._to_iso(row.get("updated_at")),
                    }
                )
            conn.rollback()
        return {"items": items, "total": len(items)}

    def update_user(self, actor: dict[str, Any], user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not has_permission(actor, "user:manage"):
            raise AppError(403, "当前账号没有管理用户的权限", "FORBIDDEN")

        allowed_roles = {"member", "group_buy_maintainer", "stock_keeper", "admin"}
        with connect(self.config) as conn:
            before = self.auth.repo.get_user_by_id(conn, user_id)
            if before is None:
                raise AppError(404, "用户不存在", "NOT_FOUND")

            updates = {
                "display_name": payload.get("displayName", before["displayName"]),
                "qq_number": payload.get("qqNumber", before["qqNumber"]),
                "group_nickname": payload.get("groupNickname", before["groupNickname"]),
                "status": payload.get("status", before["status"]),
            }
            roles_value = payload.get("roles", before["roles"])
            if not isinstance(roles_value, list) or not roles_value:
                raise AppError(400, "roles格式不正确", "VALIDATION_FAILED")
            roles = []
            for role in roles_value:
                if role not in allowed_roles:
                    raise AppError(400, "roles包含不支持的角色", "VALIDATION_FAILED")
                if role not in roles:
                    roles.append(role)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET display_name = %s,
                        qq_number = %s,
                        group_nickname = %s,
                        status = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        updates["display_name"],
                        updates["qq_number"],
                        updates["group_nickname"],
                        updates["status"],
                        user_id,
                    ),
                )
                cur.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
                for role in roles:
                    cur.execute(
                        """
                        INSERT INTO user_roles (id, user_id, role)
                        VALUES (%s, %s, %s)
                        """,
                        (f"role_{secrets.token_hex(8)}", user_id, role),
                    )
            after = self.auth.repo.get_user_by_id(conn, user_id)
            self.audit_service.log_in_connection(
                conn,
                actor_user_id=actor["id"],
                action="user.admin_update",
                object_type="user",
                object_id=user_id,
                before=before,
                after=after,
                reason=payload.get("reason") or "管理员更新用户",
            )
            conn.commit()
        return {"userId": user_id, "user": after}

    def list_my_addresses(self, user: dict[str, Any]) -> dict[str, Any]:
        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM user_addresses
                    WHERE user_id = %s
                    ORDER BY is_default DESC, created_at DESC, id DESC
                    """,
                    (user["id"],),
                )
                rows = cur.fetchall()
            conn.rollback()
        items = [self._build_address(row) for row in rows]
        return {"items": items, "total": len(items)}

    def create_my_address(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        receiver_name = self._required_text(payload.get("receiverName") or payload.get("receiver_name"), "receiverName", 2)
        receiver_phone = self._required_text(payload.get("receiverPhone") or payload.get("receiver_phone"), "receiverPhone", 6)
        detail_address = self._required_text(
            payload.get("detailAddress")
            or payload.get("detail_address")
            or payload.get("receiverAddress")
            or payload.get("receiver_address")
            or payload.get("address"),
            "detailAddress",
            4,
        )
        province = self._optional_text(payload.get("province"))
        city = self._optional_text(payload.get("city"))
        district = self._optional_text(payload.get("district"))
        postal_code = self._optional_text(payload.get("postalCode") or payload.get("postal_code"))
        note = self._optional_text(payload.get("note"))
        is_default = bool(payload.get("isDefault") or payload.get("is_default"))
        address_id = f"address_{secrets.token_hex(8)}"

        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                if is_default:
                    cur.execute(
                        """
                        UPDATE user_addresses
                        SET is_default = FALSE,
                            updated_at = NOW()
                        WHERE user_id = %s
                        """,
                        (user["id"],),
                    )
                cur.execute(
                    """
                    INSERT INTO user_addresses (
                      id,
                      user_id,
                      receiver_name,
                      receiver_phone,
                      province,
                      city,
                      district,
                      detail_address,
                      postal_code,
                      is_default,
                      note,
                      created_at,
                      updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    RETURNING *
                    """,
                    (
                        address_id,
                        user["id"],
                        receiver_name,
                        receiver_phone,
                        province,
                        city,
                        district,
                        detail_address,
                        postal_code,
                        is_default,
                        note,
                    ),
                )
                address = self._build_address(cur.fetchone())
            conn.commit()
        return {"addressId": address_id, "address": address}

    def approve_transfer(
        self,
        user: dict[str, Any],
        transfer_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 杞崟閫氳繃鐢?transfer_exception 妯″潡鍐呯殑 DB workflow 澶勭悊銆?
        return self._require_transfer_exception_module().approve_transfer(user["id"], transfer_id, payload)

    def reject_transfer(
        self,
        user: dict[str, Any],
        transfer_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 杞崟椹冲洖鐢?transfer_exception 妯″潡鍐呯殑 DB workflow 澶勭悊銆?
        return self._require_transfer_exception_module().reject_transfer(user["id"], transfer_id, payload)

    def mark_record_exception(
        self,
        user: dict[str, Any],
        group_buy_record_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 寮傚父鏍囪鐢?transfer_exception 妯″潡鍐呯殑 DB workflow 澶勭悊銆?
        return self._require_transfer_exception_module().mark_record_exception(user["id"], group_buy_record_id, payload)

    def resolve_record_exception(
        self,
        user: dict[str, Any],
        group_buy_record_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 寮傚父瑙ｅ喅鐢?transfer_exception 妯″潡鍐呯殑 DB workflow 澶勭悊銆?
        return self._require_transfer_exception_module().resolve_record_exception(user["id"], group_buy_record_id, payload)

    def create_goods(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        self.assert_goods_permission(user, "goods:create")
        return self.goods_catalog_module.create_goods(
            actor_user_id=user["id"],
            payload=payload,
        )

    def update_goods(
        self,
        user: dict[str, Any],
        goods_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.assert_goods_permission(user, "goods:update")
        return self.goods_catalog_module.update_goods(
            actor_user_id=user["id"],
            goods_id=goods_id,
            payload=payload,
        )

    def add_goods_image(
        self,
        user: dict[str, Any],
        goods_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.assert_goods_permission(user, "goods:update")
        return self.goods_catalog_module.add_goods_image(
            actor_user_id=user["id"],
            goods_id=goods_id,
            payload=payload,
        )

    def set_primary_goods_image(
        self,
        user: dict[str, Any],
        goods_id: str,
        goods_image_id: str,
    ) -> dict[str, Any]:
        self.assert_goods_permission(user, "goods:update")
        return self.goods_catalog_module.set_primary_goods_image(
            actor_user_id=user["id"],
            goods_id=goods_id,
            goods_image_id=goods_image_id,
        )

    def get_goods_snapshot(self, user: dict[str, Any], goods_id: str) -> dict[str, Any]:
        self.assert_goods_permission(user, "goods:view")
        return self.goods_catalog_module.get_goods_snapshot(goods_id)

    def search_goods(self, user: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        self.assert_goods_permission(user, "goods:view")
        return self.goods_catalog_module.search_goods(filters)

