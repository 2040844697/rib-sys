from __future__ import annotations

from typing import Any

from .auth import AuthModule, ensure_identity_seed
from .charge_payment import ChargePaymentModule, ChargePaymentRepository
from .config import Config
from .db_access import connect
from .errors import AppError
from .file_audit import DatabaseAuditService, DatabaseFileService
from .group_buy_management import GroupBuyModule, GroupBuyRepository
from .group_buy_records import GroupBuyRecordRepository, GroupBuyRecordsModule
from .goods_catalog import GoodsCatalogModule, GoodsCatalogRepository
from .order_logistics import OrderLogisticsModule, OrderLogisticsRepository
from .store import Store, create_store, has_permission
from .transfer_exception import TransferExceptionModule
from .warehouse_dispatch import WarehouseDispatchModule, WarehouseDispatchRepository


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
        return self._require_warehouse_dispatch_module().list_dispatchable_items(
            filters,
            actor_user_id=user["id"],
        )

    def create_dispatch_request(self, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 创建排发申请入口，写 dispatch_requests 和 dispatch_items。
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
        # 杞崟鐢宠鐢?transfer_exception 妯″潡鍐呯殑 DB workflow 澶勭悊銆?
        return self._require_transfer_exception_module().request_transfer(user, payload)

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

    def __getattr__(self, name: str) -> Any:
        return getattr(self.runtime, name)
