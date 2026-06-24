from __future__ import annotations

from typing import Any

from .auth import AuthModule, ensure_identity_seed
from .charge_payment import ChargePaymentModule, ChargePaymentRepository
from .config import Config
from .db_access import connect
from .errors import AppError
from .file_audit import DatabaseAuditService, DatabaseFileService
from .goods_catalog import GoodsCatalogModule, GoodsCatalogRepository
from .store import Store, create_store, has_permission


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

        self._wire_file_audit_dependencies()

        self.goods_catalog_module = GoodsCatalogModule(
            self.config,
            repository=GoodsCatalogRepository(self.config),
            file_service=self.file_service,
            audit_service=self.audit_service,
        )
        self.group_buy_records_module = getattr(self.runtime, "group_buy_records_module", None)
        self.charge_payment_module = self._build_charge_payment_module()
        self.order_logistics_module = getattr(self.runtime, "order_logistics_module", None)
        self.transfer_exception_module = getattr(self.runtime, "transfer_exception_module", None)
        self.warehouse_dispatch_module = getattr(self.runtime, "warehouse_dispatch_module", None)
        self._wire_charge_payment_dependencies()

    def _wire_file_audit_dependencies(self) -> None:
        if hasattr(self.runtime, "order_logistics_module"):
            self.runtime.order_logistics_module.require_active_file_object = (
                self.file_service.require_active_file_object
            )

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

    def _wire_charge_payment_dependencies(self) -> None:
        if self.charge_payment_module is None:
            return
        if self.group_buy_records_module is not None:
            self.group_buy_records_module.create_charge = (
                self.charge_payment_module.create_charge_from_related_module
            )
        if self.order_logistics_module is not None:
            self.order_logistics_module.create_charge = (
                self.charge_payment_module.create_charge_from_related_module
            )
        if self.warehouse_dispatch_module is not None:
            self.warehouse_dispatch_module.create_charge = (
                self.charge_payment_module.create_charge_from_related_module
            )
        if (
            self.transfer_exception_module is not None
            and hasattr(self.transfer_exception_module, "record_exceptions")
        ):
            self.transfer_exception_module.record_exceptions.create_charge_adjustment = (
                self.charge_payment_module.create_charge_adjustment
            )

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

    def build_group_home(self, group_id: str, user: dict[str, Any]) -> dict[str, Any]:
        result = self.runtime.build_group_home(group_id, user)
        if self.charge_payment_module is not None:
            result["summary"]["myPendingPaymentCount"] = (
                self.charge_payment_module.count_pending_charges_for_user(user["id"])
            )
        return result

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
