from __future__ import annotations

from typing import Any, Callable

from ..errors import AppError
from .transfer_inputs import clone, normalize_optional_text, normalize_required_text, payload_get


class RecordExceptionWorkflow:
    def __init__(
        self,
        *,
        audit_log: Callable[..., Any],
        now_iso: Callable[[], str],
        has_permission_by_user_id: Callable[[str, str], bool],
        require_group_buy_record: Callable[[str], dict[str, Any]],
        refresh_record_status: Callable[[dict[str, Any]], dict[str, Any]],
        create_charge_adjustment: Callable[[str, dict[str, Any]], dict[str, Any]],
    ):
        self.audit_log = audit_log
        self.now_iso = now_iso
        self.has_permission_by_user_id = has_permission_by_user_id
        self.require_group_buy_record = require_group_buy_record
        self.refresh_record_status = refresh_record_status
        self.create_charge_adjustment = create_charge_adjustment

    def mark_record_exception(
        self,
        actor_user_id: str,
        group_buy_record_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_can_handle_exception(actor_user_id)
        _, raw_exception_reason = payload_get(payload, "exceptionReason", "exception_reason")
        exception_reason = normalize_required_text(raw_exception_reason, "exceptionReason", 2)
        note = normalize_optional_text(payload.get("note"), "note")

        record = self.require_group_buy_record(group_buy_record_id)
        before = clone(record)
        record["isException"] = True
        record["exceptionReason"] = exception_reason
        if note is not None:
            record["note"] = note
        record["updatedAt"] = self.now_iso()
        self.refresh_record_status(record)
        self.audit_log(
            actor_user_id=actor_user_id,
            action="record.mark_exception",
            object_type="group_buy_record",
            object_id=record["id"],
            before=before,
            after=clone(record),
            reason=exception_reason,
        )
        return {"groupBuyRecordId": record["id"], "isException": record["isException"]}

    def resolve_record_exception(
        self,
        actor_user_id: str,
        group_buy_record_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_can_handle_exception(actor_user_id)
        resolution = normalize_required_text(payload.get("resolution"), "resolution", 2)
        note = normalize_optional_text(payload.get("note"), "note")

        record = self.require_group_buy_record(group_buy_record_id)
        if not record.get("isException"):
            raise AppError(400, "拼单记录当前没有异常需要解决", "INVALID_STATUS")

        before = clone(record)
        adjustment_payload = self._build_adjustment_payload(
            payload,
            record_id=record["id"],
            resolution=resolution,
        )
        charge_adjustment_id = None
        if adjustment_payload is not None:
            result = self.create_charge_adjustment(actor_user_id, adjustment_payload)
            charge_adjustment_id = result["chargeAdjustmentId"]

        record["isException"] = False
        record["exceptionReason"] = None
        if note is not None:
            record["note"] = note
        record["updatedAt"] = self.now_iso()
        self.refresh_record_status(record)
        self.audit_log(
            actor_user_id=actor_user_id,
            action="record.resolve_exception",
            object_type="group_buy_record",
            object_id=record["id"],
            before=before,
            after=clone(record),
            reason=resolution,
        )

        response = {"groupBuyRecordId": record["id"], "isException": record["isException"]}
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
        if self.has_permission_by_user_id(actor_user_id, "record:mark_exception"):
            return
        raise AppError(403, "当前账号没有处理异常记录的权限", "FORBIDDEN")
