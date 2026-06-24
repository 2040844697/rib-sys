from __future__ import annotations

from typing import Any, Callable

from ..config import Config
from ..db_access import connect
from ..errors import AppError
from .transfer_exception_repo import TransferExceptionRepository
from .transfer_inputs import clone, normalize_optional_text, normalize_required_text, payload_get


class RecordExceptionWorkflow:
    def __init__(
        self,
        config: Config,
        *,
        repository: TransferExceptionRepository | None = None,
        audit_service: Any | None = None,
        group_buy_records: Any | None = None,
        has_permission_by_user_id: Callable[[str, str], bool],
        create_charge_adjustment: Callable[[Any, str, dict[str, Any]], dict[str, Any]] | None,
    ):
        # 注入 DB 仓库、审计和费用调整入口，异常流程直接写 group_buy_records 字段。
        self.config = config
        self.repo = repository or TransferExceptionRepository(config)
        self.audit_service = audit_service
        self.group_buy_records = group_buy_records
        self.has_permission_by_user_id = has_permission_by_user_id
        self.create_charge_adjustment = create_charge_adjustment

    def mark_record_exception(
        self,
        actor_user_id: str,
        group_buy_record_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 标记拼单记录异常，写入异常原因并重算展示状态。
        self._assert_can_handle_exception(actor_user_id)
        _, raw_exception_reason = payload_get(payload, "exceptionReason", "exception_reason")
        exception_reason = normalize_required_text(raw_exception_reason, "exceptionReason", 2)
        note = normalize_optional_text(payload.get("note"), "note")
        module = self._require_group_buy_records()

        with connect(self.config) as conn:
            before = module._require_record_in_connection(conn, group_buy_record_id, lock=True)
            self.repo.mark_record_exception(
                conn,
                group_buy_record_id=group_buy_record_id,
                exception_reason=exception_reason,
                note=note,
            )
            after = module._recalculate_record_status_in_connection(
                conn,
                group_buy_record_id,
                actor_user_id=actor_user_id,
                reason=exception_reason,
                write_audit=False,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="record.mark_exception",
                object_type="group_buy_record",
                object_id=group_buy_record_id,
                before=before,
                after=after,
                reason=exception_reason,
            )
            conn.commit()
        return {"groupBuyRecordId": group_buy_record_id, "isException": after["isException"]}

    def resolve_record_exception(
        self,
        actor_user_id: str,
        group_buy_record_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 解决异常，可选创建费用调整，然后清除异常标记并重算状态。
        self._assert_can_handle_exception(actor_user_id)
        resolution = normalize_required_text(payload.get("resolution"), "resolution", 2)
        note = normalize_optional_text(payload.get("note"), "note")
        module = self._require_group_buy_records()

        with connect(self.config) as conn:
            before = module._require_record_in_connection(conn, group_buy_record_id, lock=True)
            if not before.get("isException"):
                raise AppError(400, "拼单记录当前没有异常需要解决", "INVALID_STATUS")

            adjustment_payload = self._build_adjustment_payload(
                payload,
                record_id=group_buy_record_id,
                resolution=resolution,
            )
            charge_adjustment_id = None
            if adjustment_payload is not None:
                if self.create_charge_adjustment is None:
                    raise RuntimeError("create_charge_adjustment dependency is required.")
                result = self.create_charge_adjustment(conn, actor_user_id, adjustment_payload)
                charge_adjustment_id = result["chargeAdjustmentId"]

            self.repo.resolve_record_exception(
                conn,
                group_buy_record_id=group_buy_record_id,
                note=note,
            )
            after = module._recalculate_record_status_in_connection(
                conn,
                group_buy_record_id,
                actor_user_id=actor_user_id,
                reason=resolution,
                write_audit=False,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="record.resolve_exception",
                object_type="group_buy_record",
                object_id=group_buy_record_id,
                before=before,
                after=after,
                reason=resolution,
            )
            conn.commit()

        response = {"groupBuyRecordId": group_buy_record_id, "isException": after["isException"]}
        if charge_adjustment_id is not None:
            response["chargeAdjustmentId"] = charge_adjustment_id
        return response

    def _build_adjustment_payload(
        self,
        payload: dict[str, Any],
        *,
        record_id: str,
        resolution: str,
    ) -> dict[str, Any] | None:
        # 兼容顶层调价字段和 chargeAdjustment 嵌套入参。
        adjustment = payload.get("chargeAdjustment")
        if adjustment is None:
            has_charge_id, _ = payload_get(payload, "chargeId", "charge_id")
            has_delta, _ = payload_get(payload, "deltaCny", "delta_cny")
            if not has_charge_id and not has_delta:
                return None
            adjustment = payload
        if not isinstance(adjustment, dict):
            raise AppError(400, "chargeAdjustment格式不正确", "VALIDATION_FAILED")

        _, raw_charge_id = payload_get(adjustment, "chargeId", "charge_id")
        _, raw_source_charge_id = payload_get(adjustment, "sourceChargeId", "source_charge_id")
        _, raw_delta_cny = payload_get(adjustment, "deltaCny", "delta_cny")
        return {
            "chargeId": normalize_required_text(raw_charge_id, "chargeId"),
            "sourceChargeId": normalize_optional_text(raw_source_charge_id, "sourceChargeId"),
            "deltaCny": normalize_required_text(raw_delta_cny, "deltaCny"),
            "reason": normalize_optional_text(adjustment.get("reason"), "reason") or resolution,
            "sourceType": "record_exception",
            "sourceId": record_id,
        }

    def _assert_can_handle_exception(self, actor_user_id: str) -> None:
        # 异常处理统一使用 record:mark_exception 权限。
        if self.has_permission_by_user_id(actor_user_id, "record:mark_exception"):
            return
        raise AppError(403, "当前账号没有处理异常记录的权限", "FORBIDDEN")

    def _audit(
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
        # 统一写入数据库审计日志。
        if self.audit_service is None:
            return
        self.audit_service.log_in_connection(
            conn,
            actor_user_id=actor_user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before=clone(before),
            after=clone(after),
            reason=reason,
        )

    def _require_group_buy_records(self) -> Any:
        # 异常处理必须依赖 DB 版拼单记录模块。
        if self.group_buy_records is None:
            raise RuntimeError("group_buy_records dependency is required for record exception workflow.")
        return self.group_buy_records
