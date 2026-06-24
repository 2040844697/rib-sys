from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from .auth import AuthModule, ensure_identity_seed
from .charge_payment import ChargePaymentModule, ChargePaymentRepository
from .config import Config
from .db_access import connect
from .db_access import to_iso
from .errors import AppError
from .file_audit import DatabaseAuditService, DatabaseFileService
from .group_buy_management import GroupBuyModule, GroupBuyRepository
from .group_buy_records import GroupBuyRecordRepository, GroupBuyRecordsModule
from .goods_catalog import GoodsCatalogModule, GoodsCatalogRepository
from .order_logistics import OrderLogisticsModule, OrderLogisticsRepository
from .store import Store, create_store, has_permission
from .transfer_exception import TransferExceptionModule


class AppContext:
    """Application composition root for gradually replacing legacy JSON modules."""

    def __init__(self, config: Config):
        self.config = config
        self.runtime: Store = create_store(config)
        self.auth = AuthModule(config)
        self.identity_bootstrap = ensure_identity_seed(config, audit_store=self.runtime)

        if self.config.database_url:
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
        else:
            self.audit_service = self.runtime.audit_service
            self.file_service = self.runtime.file_service

        self.goods_catalog_module = GoodsCatalogModule(
            self.config,
            repository=GoodsCatalogRepository(self.config),
            file_service=self.file_service,
            audit_service=self.audit_service,
        )
        self.charge_payment_module = self._build_charge_payment_module()
        self.group_buy_records_module = self._build_group_buy_records_module()
        self.group_buy_management_module = self._build_group_buy_management_module()
        self.order_logistics_module = self._build_order_logistics_module()
        self.transfer_exception_module = self._build_transfer_exception_module()
        self.warehouse_dispatch_module = getattr(self.runtime, "warehouse_dispatch_module", None)
        self._wire_group_buy_record_dependencies()
        self._wire_charge_payment_dependencies()

    def _dict_row(self):
        from psycopg.rows import dict_row

        return dict_row

    def _build_stock_item_snapshot(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        # 将 stock_items 行转成可写审计 JSON 的快照。
        if row is None:
            return None
        return {
            "id": row["id"],
            "warehouseUserId": row["warehouse_user_id"],
            "groupBuyRecordId": row["group_buy_record_id"],
            "quantity": row["quantity"],
            "status": row["status"],
            "stockedAt": to_iso(row.get("stocked_at")),
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

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
            stock_in_batch=self._stock_in_international_batch_db,
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
                self.charge_payment_module.create_charge_from_related_module
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
        if self.warehouse_dispatch_module is not None:
            self.warehouse_dispatch_module.require_group_buy_record = self.group_buy_records_module.require_record
            self.warehouse_dispatch_module.build_group_buy_record_summary = (
                self.group_buy_records_module.build_record_summary
            )
            self.warehouse_dispatch_module.mark_stocked = self.group_buy_records_module.mark_stocked
            self.warehouse_dispatch_module.mark_dispatch_requested = (
                self.group_buy_records_module.mark_dispatch_requested
            )
            self.warehouse_dispatch_module.mark_dispatched = self.group_buy_records_module.mark_dispatched
            self.warehouse_dispatch_module.mark_completed = self.group_buy_records_module.mark_completed
            self.warehouse_dispatch_module.link_charge = self.group_buy_records_module.link_charge
        if self.transfer_exception_module is not None:
            self.transfer_exception_module.transfer_requests.group_buy_records = self.group_buy_records_module
            self.transfer_exception_module.record_exceptions.group_buy_records = self.group_buy_records_module

    @property
    def startup_info(self) -> dict[str, Any]:
        return {
            **self.runtime.startup_info,
            "dataBackend": "database" if self.config.database_url else "legacy_json",
            "usesLegacyJsonStore": True,
        }

    def read_user_from_session(self, session_token: str | None) -> dict[str, Any] | None:
        user = self.auth.get_user_by_session_token(session_token) if self.auth.is_enabled() else None
        if user is not None:
            return user
        return self.runtime.get_user_by_session_token(session_token)

    def get_user_snapshot_by_id(self, user_id: str) -> dict[str, Any] | None:
        if self.auth.is_enabled():
            with connect(self.config) as conn:
                user = self.auth.repo.get_user_by_id(conn, user_id)
                conn.rollback()
                return user
        return self.runtime.get_user_snapshot_by_id(user_id)

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

    def _normalize_required_text(self, value: Any, field_name: str, min_length: int = 1) -> str:
        # AppContext 层少量 DB 编排使用的文本校验。
        normalized = value.strip() if isinstance(value, str) else ""
        if len(normalized) < min_length:
            raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
        return normalized

    def _normalize_optional_text(self, value: Any, field_name: str) -> str | None:
        # AppContext 层少量 DB 编排使用的可选文本校验。
        if value is None:
            return None
        if not isinstance(value, str):
            raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
        normalized = value.strip()
        return normalized or None

    def _normalize_positive_int(self, value: Any, field_name: str) -> int:
        # AppContext 层少量 DB 编排使用的正整数校验。
        if isinstance(value, bool) or not isinstance(value, int):
            raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
        if value <= 0:
            raise AppError(400, f"{field_name}必须大于 0", "VALIDATION_FAILED")
        return value

    def on_charge_confirmed(
        self,
        charge_id: str,
        *,
        proof_id: str | None,
        actor_user_id: str | None,
    ) -> dict[str, Any]:
        if self.warehouse_dispatch_module is None:
            return {"updatedCount": 0}
        result = self.warehouse_dispatch_module.confirm_charge(
            charge_id,
            proof_id=proof_id,
            actor_user_id=actor_user_id,
        )
        if result.get("updatedCount"):
            self.runtime.persist()
        return result

    def assert_goods_permission(self, user: dict[str, Any], permission: str) -> None:
        if not has_permission(user, permission):
            raise AppError(403, "current user does not have goods permission", "FORBIDDEN")

    def assert_order_logistics_permission(self, actor_user_id: str) -> None:
        user = self.get_user_snapshot_by_id(actor_user_id)
        if user is None:
            raise AppError(404, "用户不存在", "NOT_FOUND")
        if not has_permission(user, "group_buy:update_any"):
            raise AppError(403, "当前账号没有下单转运维护权限", "FORBIDDEN")

    def _assert_can_manage_warehouse(self, actor_user_id: str, warehouse_user_id: str) -> None:
        user = self.get_user_snapshot_by_id(actor_user_id)
        if user is None:
            raise AppError(404, "用户不存在", "NOT_FOUND")
        if "admin" in user.get("roles", []):
            return
        if not self.has_permission_by_user_id(actor_user_id, "dispatch:process_assigned"):
            raise AppError(403, "当前账号没有处理囤货排发的权限", "FORBIDDEN")
        if actor_user_id != warehouse_user_id:
            raise AppError(403, "当前账号只能处理分配给自己的囤货点", "FORBIDDEN")

    def health(self) -> dict[str, Any]:
        health = self.auth.get_health() if self.auth.is_enabled() else self.runtime.get_health()
        return {
            **health,
            "dataBackend": self.startup_info["dataBackend"],
            "usesLegacyJsonStore": True,
        }

    def login(
        self,
        payload: dict[str, Any],
        *,
        created_ip: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        if self.auth.is_enabled():
            return self.auth.login(
                payload,
                created_ip=created_ip,
                user_agent=user_agent,
                audit_store=self.runtime,
            )
        return self.runtime.login(payload)

    def register_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.auth.is_enabled():
            return self.auth.register_user(
                payload,
                shadow_store=self.runtime,
                audit_store=self.runtime,
            )
        return self.runtime.register_user(payload)

    def logout(self, session_token: str | None) -> dict[str, Any]:
        if self.auth.is_enabled():
            return self.auth.logout(session_token, audit_store=self.runtime)
        return self.runtime.logout(session_token)

    def build_bootstrap(self, current_user: dict[str, Any]) -> dict[str, Any]:
        if self.auth.is_enabled():
            return self.auth.build_bootstrap(current_user)
        return self.runtime.build_bootstrap(current_user)

    def build_groups(self, user: dict[str, Any]) -> dict[str, Any]:
        result = self.runtime.build_groups(user)
        if self.group_buy_management_module is not None:
            for group in result.get("items", []):
                active_group_buys = self.group_buy_management_module.build_group_buys(
                    group["id"],
                    user["id"],
                    {"status": "进行中", "keyword": None},
                )
                group["activeGroupBuyCount"] = active_group_buys["total"]
        return result

    def build_group_home(self, group_id: str, user: dict[str, Any]) -> dict[str, Any]:
        result = self.runtime.build_group_home(group_id, user)
        if self.group_buy_management_module is not None:
            active_group_buys = self.group_buy_management_module.build_group_buys(
                group_id,
                user["id"],
                {"status": "进行中", "keyword": None},
            )
            result["summary"]["activeGroupBuyCount"] = active_group_buys["total"]
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

    def _stock_in_international_batch_db(
        self,
        batch_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        # 国际批次入库的 DB 适配层：只写 stock_items 事实，不接管排发主体流程。
        batch = self._require_order_logistics_module().require_international_batch(batch_id)
        if batch["status"] == "stocked":
            raise AppError(400, "国际批次已经完成入库", "DUPLICATED_OPERATION")
        if batch["status"] != "arrived_domestic":
            raise AppError(400, "只有已到国内的批次才能入库", "INVALID_STATUS")

        warehouse_user_id = self._normalize_required_text(batch.get("warehouseUserId"), "warehouseUserId")
        stocked_at = self._normalize_required_text(
            payload.get("stockedAt") if "stockedAt" in payload else payload.get("stocked_at"),
            "stockedAt",
        )
        try:
            stocked_at = datetime.fromisoformat(stocked_at.replace("Z", "+00:00")).isoformat()
        except ValueError as exc:
            raise AppError(400, "stockedAt不是合法时间", "VALIDATION_FAILED") from exc
        note = self._normalize_optional_text(payload.get("note"), "note")
        self._assert_can_manage_warehouse(actor_user_id, warehouse_user_id)

        record_ids = self._require_order_logistics_module().list_batch_record_ids(batch_id)
        if not record_ids:
            raise AppError(400, "空批次不能入库", "VALIDATION_FAILED")

        stock_item_ids: list[str] = []
        with connect(self.config) as conn:
            before_batch = self._require_order_logistics_module()._require_international_batch_in_connection(
                conn,
                batch_id,
                lock=True,
            )
            if before_batch["status"] == "stocked":
                raise AppError(400, "国际批次已经完成入库", "DUPLICATED_OPERATION")
            if before_batch["status"] != "arrived_domestic":
                raise AppError(400, "只有已到国内的批次才能入库", "INVALID_STATUS")

            for record_id in record_ids:
                record = self._require_group_buy_records_module()._require_record_in_connection(
                    conn,
                    record_id,
                    lock=True,
                )
                with conn.cursor(row_factory=self._dict_row()) as cur:
                    cur.execute(
                        """
                        SELECT *
                        FROM stock_items
                        WHERE group_buy_record_id = %s
                        LIMIT 1
                        FOR UPDATE
                        """,
                        (record_id,),
                    )
                    before_stock_item = cur.fetchone()
                    if before_stock_item is None:
                        stock_item_id = f"stock_item_{secrets.token_hex(8)}"
                        cur.execute(
                            """
                            INSERT INTO stock_items (
                              id, warehouse_user_id, group_buy_record_id,
                              quantity, status, stocked_at
                            )
                            VALUES (%s, %s, %s, %s, 'in_stock', %s)
                            RETURNING id
                            """,
                            (
                                stock_item_id,
                                warehouse_user_id,
                                record_id,
                                record["quantity"],
                                stocked_at,
                            ),
                        )
                    else:
                        if before_stock_item["status"] in {"reserved", "shipped", "completed"}:
                            raise AppError(400, "已有排发流程的库存不能重复入库", "DUPLICATED_OPERATION")
                        stock_item_id = before_stock_item["id"]
                        cur.execute(
                            """
                            UPDATE stock_items
                            SET warehouse_user_id = %s,
                                quantity = %s,
                                status = 'in_stock',
                                stocked_at = %s,
                                updated_at = NOW()
                            WHERE id = %s
                            RETURNING id
                            """,
                            (
                                warehouse_user_id,
                                record["quantity"],
                                stocked_at,
                                stock_item_id,
                            ),
                        )
                    stock_item_ids.append(cur.fetchone()["id"])

                self.audit_service.log_in_connection(
                    conn,
                    actor_user_id=actor_user_id,
                    action="stock_item.stock_in",
                    object_type="stock_item",
                    object_id=stock_item_ids[-1],
                    before=self._build_stock_item_snapshot(before_stock_item),
                    after={
                        "id": stock_item_ids[-1],
                        "warehouseUserId": warehouse_user_id,
                        "groupBuyRecordId": record_id,
                        "quantity": record["quantity"],
                        "status": "in_stock",
                        "stockedAt": stocked_at,
                    },
                    reason=note or "国际批次转国内入库",
                )

            self._require_group_buy_records_module().mark_stocked_in_connection(
                conn,
                record_ids,
                actor_user_id=actor_user_id,
                reason=note or "国际批次转国内入库",
            )
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    """
                    UPDATE international_batches
                    SET status = 'stocked',
                        stocked_at = %s,
                        note = COALESCE(%s, note),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (stocked_at, note, batch_id),
                )
            after_batch = self._require_order_logistics_module()._require_international_batch_in_connection(
                conn,
                batch_id,
            )
            self.audit_service.log_in_connection(
                conn,
                actor_user_id=actor_user_id,
                action="international_batch.stock_in",
                object_type="international_batch",
                object_id=batch_id,
                before=before_batch,
                after={
                    **after_batch,
                    "groupBuyRecordIds": record_ids,
                    "stockItemIds": stock_item_ids,
                },
                reason=note or "国际批次转国内入库",
            )
            conn.commit()

        return {"batchId": batch_id, "status": "stocked", "stockItemIds": stock_item_ids}

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
        # 入库入口转交订单物流模块，再由其调用仓库排发 DB 依赖。
        return self._require_order_logistics_module().stock_in_batch_records(
            user["id"],
            batch_id,
            payload,
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
        # 迁移期供下单转运模块校验团购存在性，仍然只读 DB 团购表。
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
        if self.auth.is_enabled():
            return self.auth.read_me(current_user)
        return self.runtime.read_me(current_user)

    def update_me(self, current_user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        if self.auth.is_enabled():
            return self.auth.update_me(
                current_user,
                {
                    **payload,
                    "__shadowStore": self.runtime,
                },
                audit_store=self.runtime,
            )
        return self.runtime.update_me(current_user, payload)

    def create_upload_object(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        return self.file_service.create_upload_object(
            uploaded_by=user["id"],
            bucket=payload.get("bucket"),
            object_key=payload.get("objectKey"),
            url=payload.get("url"),
            content_type=payload.get("contentType"),
            size_bytes=payload.get("sizeBytes"),
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

    def create_payment_channel(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        return self._require_charge_payment_module().create_payment_channel(user["id"], payload)

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
        # 转单申请由 transfer_exception 模块内的 DB workflow 处理。
        return self._require_transfer_exception_module().request_transfer(user, payload)

    def approve_transfer(
        self,
        user: dict[str, Any],
        transfer_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 转单通过由 transfer_exception 模块内的 DB workflow 处理。
        return self._require_transfer_exception_module().approve_transfer(user["id"], transfer_id, payload)

    def reject_transfer(
        self,
        user: dict[str, Any],
        transfer_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 转单驳回由 transfer_exception 模块内的 DB workflow 处理。
        return self._require_transfer_exception_module().reject_transfer(user["id"], transfer_id, payload)

    def mark_record_exception(
        self,
        user: dict[str, Any],
        group_buy_record_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 异常标记由 transfer_exception 模块内的 DB workflow 处理。
        return self._require_transfer_exception_module().mark_record_exception(user["id"], group_buy_record_id, payload)

    def resolve_record_exception(
        self,
        user: dict[str, Any],
        group_buy_record_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 异常解决由 transfer_exception 模块内的 DB workflow 处理。
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

    def __getattr__(self, name: str) -> Any:
        return getattr(self.runtime, name)
