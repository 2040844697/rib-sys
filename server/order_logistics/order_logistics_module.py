from __future__ import annotations

import copy
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from ..errors import AppError


INTERNATIONAL_BATCH_STATUS_DRAFT = "draft"
INTERNATIONAL_BATCH_STATUS_PREPARING = "preparing"
INTERNATIONAL_BATCH_STATUS_SHIPPED = "shipped"
INTERNATIONAL_BATCH_STATUS_TAXED = "taxed"
INTERNATIONAL_BATCH_STATUS_ARRIVED_DOMESTIC = "arrived_domestic"
INTERNATIONAL_BATCH_STATUS_STOCKED = "stocked"
INTERNATIONAL_BATCH_STATUS_CLOSED = "closed"
ALLOWED_INTERNATIONAL_BATCH_STATUSES = {
    INTERNATIONAL_BATCH_STATUS_DRAFT,
    INTERNATIONAL_BATCH_STATUS_PREPARING,
    INTERNATIONAL_BATCH_STATUS_SHIPPED,
    INTERNATIONAL_BATCH_STATUS_TAXED,
    INTERNATIONAL_BATCH_STATUS_ARRIVED_DOMESTIC,
    INTERNATIONAL_BATCH_STATUS_STOCKED,
    INTERNATIONAL_BATCH_STATUS_CLOSED,
}
OPEN_INTERNATIONAL_BATCH_STATUSES = (
    ALLOWED_INTERNATIONAL_BATCH_STATUSES - {INTERNATIONAL_BATCH_STATUS_CLOSED}
)
TRANSFER_STARTED_BATCH_STATUSES = {
    INTERNATIONAL_BATCH_STATUS_PREPARING,
    INTERNATIONAL_BATCH_STATUS_SHIPPED,
    INTERNATIONAL_BATCH_STATUS_TAXED,
    INTERNATIONAL_BATCH_STATUS_ARRIVED_DOMESTIC,
    INTERNATIONAL_BATCH_STATUS_STOCKED,
}
SHIPPING_MUTABLE_BATCH_STATUSES = {
    INTERNATIONAL_BATCH_STATUS_DRAFT,
    INTERNATIONAL_BATCH_STATUS_PREPARING,
    INTERNATIONAL_BATCH_STATUS_SHIPPED,
    INTERNATIONAL_BATCH_STATUS_TAXED,
}
SHIPPING_STATUS_TRANSITIONS = {
    INTERNATIONAL_BATCH_STATUS_DRAFT: {
        INTERNATIONAL_BATCH_STATUS_PREPARING,
        INTERNATIONAL_BATCH_STATUS_SHIPPED,
        INTERNATIONAL_BATCH_STATUS_CLOSED,
    },
    INTERNATIONAL_BATCH_STATUS_PREPARING: {
        INTERNATIONAL_BATCH_STATUS_SHIPPED,
        INTERNATIONAL_BATCH_STATUS_TAXED,
        INTERNATIONAL_BATCH_STATUS_CLOSED,
    },
    INTERNATIONAL_BATCH_STATUS_SHIPPED: {
        INTERNATIONAL_BATCH_STATUS_TAXED,
        INTERNATIONAL_BATCH_STATUS_CLOSED,
    },
    INTERNATIONAL_BATCH_STATUS_TAXED: {
        INTERNATIONAL_BATCH_STATUS_CLOSED,
    },
}


def clone(value: Any) -> Any:
    return copy.deepcopy(value)


def ensure_order_logistics_state(state: dict[str, Any]) -> bool:
    changed = False

    counters = state.setdefault("counters", {})
    order_screenshots = state.setdefault("orderScreenshots", [])
    international_batches = state.setdefault("internationalBatches", [])
    international_batch_records = state.setdefault("internationalBatchRecords", [])
    international_fee_allocations = state.setdefault("internationalFeeAllocations", [])

    defaults = {
        "orderScreenshot": len(order_screenshots),
        "internationalBatch": len(international_batches),
        "internationalBatchRecord": len(international_batch_records),
        "internationalFeeAllocation": len(international_fee_allocations),
    }
    for counter_key, counter_value in defaults.items():
        if counter_key not in counters:
            counters[counter_key] = counter_value
            changed = True

    for screenshot in order_screenshots:
        if "fileObjectId" not in screenshot:
            screenshot["fileObjectId"] = None
            changed = True
        if "orderedAt" not in screenshot:
            screenshot["orderedAt"] = None
            changed = True
        if "website" not in screenshot:
            screenshot["website"] = None
            changed = True
        if "websiteOrderNo" not in screenshot:
            screenshot["websiteOrderNo"] = None
            changed = True
        if "note" not in screenshot:
            screenshot["note"] = None
            changed = True
        if "updatedAt" not in screenshot:
            screenshot["updatedAt"] = screenshot.get("createdAt")
            changed = True

    for batch in international_batches:
        batch_defaults = {
            "status": INTERNATIONAL_BATCH_STATUS_DRAFT,
            "warehouseUserId": None,
            "internationalTrackingNo": None,
            "totalWeightGram": None,
            "shippingFeeCny": None,
            "taxFeeCny": None,
            "otherFeeCny": None,
            "shippedAt": None,
            "arrivedDomesticAt": None,
            "stockedAt": None,
            "note": None,
            "updatedAt": batch.get("createdAt"),
        }
        for key, value in batch_defaults.items():
            if key not in batch:
                batch[key] = clone(value)
                changed = True

    for relation in international_batch_records:
        if "createdAt" not in relation:
            relation["createdAt"] = None
            changed = True

    for allocation in international_fee_allocations:
        if "note" not in allocation:
            allocation["note"] = None
            changed = True
        if "chargeId" not in allocation:
            allocation["chargeId"] = None
            changed = True
        if "createdAt" not in allocation:
            allocation["createdAt"] = None
            changed = True

    return changed


def _normalize_required_text(value: Any, field_name: str, min_length: int = 1) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if len(normalized) < min_length:
        raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
    return normalized


def _normalize_optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    normalized = value.strip()
    return normalized or None


def _normalize_non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    if value < 0:
        raise AppError(400, f"{field_name}不能小于 0", "VALIDATION_FAILED")
    return value


def _normalize_bool(value: Any, field_name: str, default_value: bool = False) -> bool:
    if value is None:
        return default_value
    if not isinstance(value, bool):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    return value


def _normalize_price_cny(value: Any, field_name: str) -> str:
    if isinstance(value, bool) or value in {None, ""}:
        raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED") from exc
    if amount < 0:
        raise AppError(400, f"{field_name}不能小于 0", "VALIDATION_FAILED")
    return f"{amount.quantize(Decimal('0.00'))}"


def _parse_amount(amount_text: str) -> Decimal:
    return Decimal(amount_text)


def _normalize_datetime_text(
    value: Any,
    field_name: str,
    *,
    required: bool,
) -> str | None:
    if value in {None, ""}:
        if required:
            raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
        return None
    if not isinstance(value, str):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")

    normalized = value.strip()
    if not normalized:
        if required:
            raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
        return None

    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).isoformat()
    except ValueError as exc:
        raise AppError(400, f"{field_name}不是合法时间", "VALIDATION_FAILED") from exc


def _payload_get(payload: dict[str, Any], *keys: str) -> tuple[bool, Any]:
    for key in keys:
        if key in payload:
            return True, payload[key]
    return False, None


class OrderLogisticsModule:
    def __init__(
        self,
        *,
        state: dict[str, Any],
        next_id: Callable[[str, str], str],
        audit_log: Callable[..., Any],
        now_iso: Callable[[], str],
        assert_manage_permission: Callable[[str], None],
        get_group_buy_for_write: Callable[[str, str], dict[str, Any]],
        get_user_snapshot_by_id: Callable[[str], dict[str, Any] | None],
        require_active_file_object: Callable[[str], dict[str, Any]],
        mark_ordered: Callable[..., dict[str, Any]],
        enter_transfer_flow: Callable[..., dict[str, Any]],
        link_charge: Callable[..., dict[str, Any]],
        create_charge: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        stock_in_batch: Callable[..., dict[str, Any]] | None = None,
    ):
        self.state = state
        self.next_id = next_id
        self.audit_log = audit_log
        self.now_iso = now_iso
        self.assert_manage_permission = assert_manage_permission
        self.get_group_buy_for_write = get_group_buy_for_write
        self.get_user_snapshot_by_id = get_user_snapshot_by_id
        self.require_active_file_object = require_active_file_object
        self.mark_ordered = mark_ordered
        self.enter_transfer_flow = enter_transfer_flow
        self.link_charge = link_charge
        self.create_charge = create_charge
        self.stock_in_batch = stock_in_batch

    def require_order_screenshot(self, order_screenshot_id: str) -> dict[str, Any]:
        screenshot = next(
            (
                item
                for item in self.state.get("orderScreenshots", [])
                if item["id"] == order_screenshot_id
            ),
            None,
        )
        if screenshot is None:
            raise AppError(404, "下单截图不存在", "NOT_FOUND")
        return screenshot

    def require_international_batch(self, batch_id: str) -> dict[str, Any]:
        batch = next(
            (
                item
                for item in self.state.get("internationalBatches", [])
                if item["id"] == batch_id
            ),
            None,
        )
        if batch is None:
            raise AppError(404, "国际批次不存在", "NOT_FOUND")
        return batch

    def require_group_buy_record(self, group_buy_record_id: str) -> dict[str, Any]:
        record = next(
            (
                item
                for item in self.state.get("groupBuyRecords", [])
                if item["id"] == group_buy_record_id
            ),
            None,
        )
        if record is None:
            raise AppError(404, "拼单记录不存在", "NOT_FOUND")
        return record

    def list_batch_record_links(self, batch_id: str) -> list[dict[str, Any]]:
        return [
            clone(item)
            for item in self.state.get("internationalBatchRecords", [])
            if item["batchId"] == batch_id
        ]

    def list_batch_record_ids(self, batch_id: str) -> list[str]:
        return [
            relation["groupBuyRecordId"]
            for relation in self.state.get("internationalBatchRecords", [])
            if relation["batchId"] == batch_id
        ]

    def list_batch_allocations(self, batch_id: str) -> list[dict[str, Any]]:
        return [
            clone(item)
            for item in self.state.get("internationalFeeAllocations", [])
            if item["batchId"] == batch_id
        ]

    def build_batch_snapshot(self, batch: dict[str, Any]) -> dict[str, Any]:
        return {
            **clone(batch),
            "recordIds": self.list_batch_record_ids(batch["id"]),
            "allocationIds": [item["id"] for item in self.list_batch_allocations(batch["id"])],
        }

    def _normalize_record_id_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            raise AppError(400, "groupBuyRecordIds格式不正确", "VALIDATION_FAILED")

        record_ids: list[str] = []
        for item in value:
            record_id = _normalize_required_text(item, "拼单记录")
            if record_id not in record_ids:
                record_ids.append(record_id)

        if not record_ids:
            raise AppError(400, "groupBuyRecordIds不能为空", "VALIDATION_FAILED")
        return record_ids

    def _assert_batch_mutable(self, batch: dict[str, Any]) -> None:
        if batch["status"] == INTERNATIONAL_BATCH_STATUS_CLOSED:
            raise AppError(400, "已关闭的国际批次不允许继续修改", "INVALID_STATUS")

    def _assert_shipping_status_transition(self, old_status: str, new_status: str) -> None:
        if new_status not in SHIPPING_MUTABLE_BATCH_STATUSES | {INTERNATIONAL_BATCH_STATUS_CLOSED}:
            raise AppError(400, "该状态请通过专门流程修改", "INVALID_STATUS")
        if old_status not in SHIPPING_STATUS_TRANSITIONS:
            raise AppError(400, "当前批次状态不允许更新物流信息", "INVALID_STATUS")
        if new_status not in SHIPPING_STATUS_TRANSITIONS[old_status]:
            raise AppError(
                400,
                f"国际批次状态不允许从 {old_status} 变更为 {new_status}",
                "INVALID_STATUS",
            )

    def _ensure_transfer_flow_for_batch(self, batch: dict[str, Any], *, actor_user_id: str, reason: str) -> None:
        if batch["status"] not in TRANSFER_STARTED_BATCH_STATUSES:
            return

        record_ids = self.list_batch_record_ids(batch["id"])
        if not record_ids:
            return

        self.enter_transfer_flow(
            {
                "groupBuyRecordIds": record_ids,
                "reason": reason,
            },
            actor_user_id=actor_user_id,
        )

    def add_order_screenshot(self, actor_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.assert_manage_permission(actor_user_id)

        group_buy_id = _normalize_required_text(
            payload.get("groupBuyId") if "groupBuyId" in payload else payload.get("group_buy_id"),
            "拼团",
        )
        self.get_group_buy_for_write(actor_user_id, group_buy_id)

        has_file_object_id, raw_file_object_id = _payload_get(
            payload,
            "fileObjectId",
            "file_object_id",
        )
        file_object_id = (
            _normalize_optional_text(raw_file_object_id, "fileObjectId") if has_file_object_id else None
        )
        screenshot_url = _normalize_required_text(
            payload.get("screenshotUrl")
            if "screenshotUrl" in payload
            else payload.get("screenshot_url"),
            "screenshotUrl",
        )
        if file_object_id:
            file_object = self.require_active_file_object(file_object_id)
            if file_object.get("bucket") != "orders":
                raise AppError(400, "下单截图只能关联 orders bucket 文件", "VALIDATION_FAILED")
            if file_object.get("url") != screenshot_url:
                raise AppError(400, "下单截图 URL 与文件对象不一致", "VALIDATION_FAILED")

        record = {
            "id": self.next_id("orderScreenshot", "order_screenshot"),
            "groupBuyId": group_buy_id,
            "uploadedBy": actor_user_id,
            "fileObjectId": file_object_id,
            "screenshotUrl": screenshot_url,
            "isOrdered": _normalize_bool(
                payload.get("isOrdered")
                if "isOrdered" in payload
                else payload.get("is_ordered"),
                "isOrdered",
                default_value=False,
            ),
            "orderedAt": _normalize_datetime_text(
                payload.get("orderedAt")
                if "orderedAt" in payload
                else payload.get("ordered_at"),
                "orderedAt",
                required=False,
            ),
            "website": _normalize_optional_text(payload.get("website"), "website"),
            "websiteOrderNo": _normalize_optional_text(
                payload.get("websiteOrderNo")
                if "websiteOrderNo" in payload
                else payload.get("website_order_no"),
                "websiteOrderNo",
            ),
            "note": _normalize_optional_text(payload.get("note"), "note"),
            "createdAt": self.now_iso(),
            "updatedAt": self.now_iso(),
        }
        self.state["orderScreenshots"].append(record)

        self.audit_log(
            actor_user_id=actor_user_id,
            action="order_screenshot.create",
            object_type="order_screenshot",
            object_id=record["id"],
            before=None,
            after=clone(record),
            reason="上传下单截图",
        )
        return {"orderScreenshotId": record["id"]}

    def mark_records_ordered(self, actor_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.assert_manage_permission(actor_user_id)

        record_ids = self._normalize_record_id_list(
            payload.get("groupBuyRecordIds")
            if "groupBuyRecordIds" in payload
            else payload.get("group_buy_record_ids")
        )
        order_screenshot_id = _normalize_required_text(
            payload.get("orderScreenshotId")
            if "orderScreenshotId" in payload
            else payload.get("order_screenshot_id"),
            "下单截图",
        )
        ordered_at = _normalize_datetime_text(
            payload.get("orderedAt")
            if "orderedAt" in payload
            else payload.get("ordered_at"),
            "orderedAt",
            required=True,
        )
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)

        screenshot = self.require_order_screenshot(order_screenshot_id)
        before = clone(screenshot)
        for record_id in record_ids:
            record = self.require_group_buy_record(record_id)
            if record["groupBuyId"] != screenshot["groupBuyId"]:
                raise AppError(400, "下单截图只能覆盖同一拼团的拼单记录", "VALIDATION_FAILED")

        screenshot["isOrdered"] = True
        screenshot["orderedAt"] = ordered_at
        screenshot["updatedAt"] = self.now_iso()

        result = self.mark_ordered(
            {
                "groupBuyRecordIds": record_ids,
                "sourceObjectType": "order_screenshot",
                "sourceObjectId": order_screenshot_id,
                "reason": reason,
            },
            actor_user_id=actor_user_id,
        )
        self.audit_log(
            actor_user_id=actor_user_id,
            action="order_screenshot.mark_records_ordered",
            object_type="order_screenshot",
            object_id=order_screenshot_id,
            before=before,
            after={
                **clone(screenshot),
                "groupBuyRecordIds": record_ids,
            },
            reason=reason,
        )
        return {"updatedCount": result["updatedCount"]}

    def create_international_batch(self, actor_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.assert_manage_permission(actor_user_id)

        forwarder_name = _normalize_required_text(
            payload.get("forwarderName")
            if "forwarderName" in payload
            else payload.get("forwarder_name"),
            "forwarderName",
            2,
        )
        batch_no = _normalize_required_text(
            payload.get("batchNo") if "batchNo" in payload else payload.get("batch_no"),
            "batchNo",
        )
        duplicated = next(
            (
                item
                for item in self.state.get("internationalBatches", [])
                if item["batchNo"] == batch_no
            ),
            None,
        )
        if duplicated is not None:
            raise AppError(400, "国际批次编号不能重复", "DUPLICATED_OPERATION")

        warehouse_user_id = _normalize_optional_text(
            payload.get("warehouseUserId")
            if "warehouseUserId" in payload
            else payload.get("warehouse_user_id"),
            "warehouseUserId",
        )
        if warehouse_user_id and self.get_user_snapshot_by_id(warehouse_user_id) is None:
            raise AppError(404, "囤货人不存在", "NOT_FOUND")

        batch = {
            "id": self.next_id("internationalBatch", "intl_batch"),
            "forwarderName": forwarder_name,
            "batchNo": batch_no,
            "status": INTERNATIONAL_BATCH_STATUS_DRAFT,
            "warehouseUserId": warehouse_user_id,
            "internationalTrackingNo": _normalize_optional_text(
                payload.get("internationalTrackingNo")
                if "internationalTrackingNo" in payload
                else payload.get("international_tracking_no"),
                "internationalTrackingNo",
            ),
            "totalWeightGram": None,
            "shippingFeeCny": None,
            "taxFeeCny": None,
            "otherFeeCny": None,
            "shippedAt": None,
            "arrivedDomesticAt": None,
            "stockedAt": None,
            "note": _normalize_optional_text(payload.get("note"), "note"),
            "createdBy": actor_user_id,
            "createdAt": self.now_iso(),
            "updatedAt": self.now_iso(),
        }
        self.state["internationalBatches"].append(batch)

        self.audit_log(
            actor_user_id=actor_user_id,
            action="international_batch.create",
            object_type="international_batch",
            object_id=batch["id"],
            before=None,
            after=self.build_batch_snapshot(batch),
            reason="创建国际批次",
        )
        return {"batchId": batch["id"], "status": batch["status"]}

    def add_records_to_batch(
        self,
        actor_user_id: str,
        batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.assert_manage_permission(actor_user_id)

        batch = self.require_international_batch(batch_id)
        self._assert_batch_mutable(batch)
        record_ids = self._normalize_record_id_list(
            payload.get("groupBuyRecordIds")
            if "groupBuyRecordIds" in payload
            else payload.get("group_buy_record_ids")
        )
        before = self.build_batch_snapshot(batch)

        for record_id in record_ids:
            record = self.require_group_buy_record(record_id)
            if not record.get("isOrdered"):
                raise AppError(400, "未标记已下单的记录不能加入国际批次", "INVALID_STATUS")

            duplicated_link = next(
                (
                    relation
                    for relation in self.state["internationalBatchRecords"]
                    if relation["groupBuyRecordId"] == record_id
                ),
                None,
            )
            if duplicated_link is None:
                continue

            linked_batch = self.require_international_batch(duplicated_link["batchId"])
            if linked_batch["id"] == batch_id:
                raise AppError(400, "拼单记录已在当前国际批次中", "DUPLICATED_OPERATION")
            if linked_batch["status"] != INTERNATIONAL_BATCH_STATUS_CLOSED:
                raise AppError(400, "拼单记录已在未关闭的国际批次中", "DUPLICATED_OPERATION")

        for record_id in record_ids:
            self.state["internationalBatchRecords"].append(
                {
                    "id": self.next_id("internationalBatchRecord", "intl_batch_record"),
                    "batchId": batch_id,
                    "groupBuyRecordId": record_id,
                    "createdAt": self.now_iso(),
                }
            )

        self._ensure_transfer_flow_for_batch(
            batch,
            actor_user_id=actor_user_id,
            reason="加入国际批次并进入转运流程",
        )
        batch["updatedAt"] = self.now_iso()

        self.audit_log(
            actor_user_id=actor_user_id,
            action="international_batch.add_records",
            object_type="international_batch",
            object_id=batch_id,
            before=before,
            after=self.build_batch_snapshot(batch),
            reason="加入国际批次记录",
        )
        return {
            "batchId": batch_id,
            "recordCount": len(self.list_batch_record_ids(batch_id)),
            "addedCount": len(record_ids),
        }

    def update_batch_shipping(
        self,
        actor_user_id: str,
        batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.assert_manage_permission(actor_user_id)

        batch = self.require_international_batch(batch_id)
        self._assert_batch_mutable(batch)
        before = self.build_batch_snapshot(batch)

        has_tracking_no, raw_tracking_no = _payload_get(
            payload,
            "internationalTrackingNo",
            "international_tracking_no",
        )
        has_shipped_at, raw_shipped_at = _payload_get(payload, "shippedAt", "shipped_at")
        has_status, raw_status = _payload_get(payload, "status")
        has_note, raw_note = _payload_get(payload, "note")

        next_tracking_no = (
            _normalize_optional_text(raw_tracking_no, "internationalTrackingNo")
            if has_tracking_no
            else batch.get("internationalTrackingNo")
        )
        next_shipped_at = (
            _normalize_datetime_text(raw_shipped_at, "shippedAt", required=False)
            if has_shipped_at
            else batch.get("shippedAt")
        )
        next_note = _normalize_optional_text(raw_note, "note") if has_note else batch.get("note")
        next_status = batch["status"]
        if has_status:
            next_status = _normalize_required_text(raw_status, "status")
            if next_status not in ALLOWED_INTERNATIONAL_BATCH_STATUSES:
                raise AppError(400, "国际批次状态不支持", "VALIDATION_FAILED")
            if next_status in {
                INTERNATIONAL_BATCH_STATUS_ARRIVED_DOMESTIC,
                INTERNATIONAL_BATCH_STATUS_STOCKED,
            }:
                raise AppError(400, "请通过专门流程更新到达或入库状态", "INVALID_STATUS")
            self._assert_shipping_status_transition(batch["status"], next_status)
        elif has_shipped_at and batch["status"] == INTERNATIONAL_BATCH_STATUS_DRAFT:
            next_status = INTERNATIONAL_BATCH_STATUS_SHIPPED

        if (
            next_tracking_no == batch.get("internationalTrackingNo")
            and next_shipped_at == batch.get("shippedAt")
            and next_status == batch["status"]
            and next_note == batch.get("note")
        ):
            raise AppError(400, "没有可更新的物流字段", "VALIDATION_FAILED")

        batch["internationalTrackingNo"] = next_tracking_no
        batch["shippedAt"] = next_shipped_at
        batch["status"] = next_status
        batch["note"] = next_note
        batch["updatedAt"] = self.now_iso()

        self._ensure_transfer_flow_for_batch(
            batch,
            actor_user_id=actor_user_id,
            reason="国际批次物流状态推进",
        )
        self.audit_log(
            actor_user_id=actor_user_id,
            action="international_batch.update_shipping",
            object_type="international_batch",
            object_id=batch_id,
            before=before,
            after=self.build_batch_snapshot(batch),
            reason="更新国际物流信息",
        )
        return {"batchId": batch_id, "status": batch["status"]}

    def record_batch_arrived_domestic(
        self,
        actor_user_id: str,
        batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.assert_manage_permission(actor_user_id)

        batch = self.require_international_batch(batch_id)
        self._assert_batch_mutable(batch)
        if batch["status"] in {
            INTERNATIONAL_BATCH_STATUS_ARRIVED_DOMESTIC,
            INTERNATIONAL_BATCH_STATUS_STOCKED,
        }:
            raise AppError(400, "国际批次已经记录到达国内", "DUPLICATED_OPERATION")

        before = self.build_batch_snapshot(batch)
        batch["arrivedDomesticAt"] = _normalize_datetime_text(
            payload.get("arrivedDomesticAt")
            if "arrivedDomesticAt" in payload
            else payload.get("arrived_domestic_at"),
            "arrivedDomesticAt",
            required=True,
        )
        note = _normalize_optional_text(payload.get("note"), "note")
        if note is not None:
            batch["note"] = note
        batch["status"] = INTERNATIONAL_BATCH_STATUS_ARRIVED_DOMESTIC
        batch["updatedAt"] = self.now_iso()

        record_ids = self.list_batch_record_ids(batch_id)
        self.audit_log(
            actor_user_id=actor_user_id,
            action="international_batch.record_arrived_domestic",
            object_type="international_batch",
            object_id=batch_id,
            before=before,
            after=self.build_batch_snapshot(batch),
            reason="记录国际批次到达国内",
        )
        return {
            "batchId": batch_id,
            "status": batch["status"],
            "groupBuyRecordIds": record_ids,
        }

    def stock_in_batch_records(
        self,
        actor_user_id: str,
        batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.assert_manage_permission(actor_user_id)
        if self.stock_in_batch is None:
            raise RuntimeError("Warehouse stock-in dependency is required.")
        return self.stock_in_batch(batch_id, payload, actor_user_id=actor_user_id)

    def record_batch_fees(
        self,
        actor_user_id: str,
        batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.assert_manage_permission(actor_user_id)

        batch = self.require_international_batch(batch_id)
        self._assert_batch_mutable(batch)
        if self.list_batch_allocations(batch_id):
            raise AppError(400, "国际批次费用已经录入，暂不支持重复生成", "DUPLICATED_OPERATION")

        batch_record_ids = self.list_batch_record_ids(batch_id)
        if not batch_record_ids:
            raise AppError(400, "空批次不能录入国际费用", "VALIDATION_FAILED")

        batch_records = [self.require_group_buy_record(record_id) for record_id in batch_record_ids]
        batch_member_user_ids = {record["memberUserId"] for record in batch_records}
        for record in batch_records:
            if record.get("internationalChargeId"):
                raise AppError(400, "批次内已有记录关联国际费用，不能重复生成", "DUPLICATED_OPERATION")

        allocation_items = (
            payload.get("allocationItems")
            if "allocationItems" in payload
            else payload.get("allocation_items")
        )
        if not isinstance(allocation_items, list) or not allocation_items:
            raise AppError(400, "allocationItems格式不正确", "VALIDATION_FAILED")

        total_weight_gram = _normalize_non_negative_int(
            payload.get("totalWeightGram")
            if "totalWeightGram" in payload
            else payload.get("total_weight_gram"),
            "totalWeightGram",
        )
        shipping_fee_cny = _normalize_price_cny(
            payload.get("shippingFeeCny")
            if "shippingFeeCny" in payload
            else payload.get("shipping_fee_cny"),
            "shippingFeeCny",
        )
        tax_fee_cny = _normalize_price_cny(
            payload.get("taxFeeCny") if "taxFeeCny" in payload else payload.get("tax_fee_cny"),
            "taxFeeCny",
        )
        other_fee_cny = _normalize_price_cny(
            payload.get("otherFeeCny")
            if "otherFeeCny" in payload
            else payload.get("other_fee_cny"),
            "otherFeeCny",
        )
        global_note = _normalize_optional_text(payload.get("note"), "note")

        normalized_allocations: list[dict[str, Any]] = []
        seen_user_ids: set[str] = set()
        for index, item in enumerate(allocation_items):
            if not isinstance(item, dict):
                raise AppError(400, f"allocationItems[{index}]格式不正确", "VALIDATION_FAILED")

            user_id = _normalize_required_text(
                item.get("userId") if "userId" in item else item.get("user_id"),
                f"allocationItems[{index}].userId",
            )
            if user_id in seen_user_ids:
                raise AppError(400, "同一成员不能重复分摊国际费用", "DUPLICATED_OPERATION")
            if user_id not in batch_member_user_ids:
                raise AppError(400, "费用分摊成员必须来自当前国际批次", "VALIDATION_FAILED")
            if self.get_user_snapshot_by_id(user_id) is None:
                raise AppError(404, "费用分摊成员不存在", "NOT_FOUND")

            weight_gram = _normalize_non_negative_int(
                item.get("weightGram") if "weightGram" in item else item.get("weight_gram"),
                f"allocationItems[{index}].weightGram",
            )
            item_shipping_fee = _normalize_price_cny(
                item.get("shippingFeeCny")
                if "shippingFeeCny" in item
                else item.get("shipping_fee_cny"),
                f"allocationItems[{index}].shippingFeeCny",
            )
            item_tax_fee = _normalize_price_cny(
                item.get("taxFeeCny") if "taxFeeCny" in item else item.get("tax_fee_cny"),
                f"allocationItems[{index}].taxFeeCny",
            )
            item_other_fee = _normalize_price_cny(
                item.get("otherFeeCny")
                if "otherFeeCny" in item
                else item.get("other_fee_cny"),
                f"allocationItems[{index}].otherFeeCny",
            )
            item_adjustment = _normalize_price_cny(
                item.get("adjustmentCny")
                if "adjustmentCny" in item
                else item.get("adjustment_cny")
                or "0",
                f"allocationItems[{index}].adjustmentCny",
            )
            item_total = _normalize_price_cny(
                item.get("totalCny") if "totalCny" in item else item.get("total_cny"),
                f"allocationItems[{index}].totalCny",
            )
            item_note = _normalize_optional_text(item.get("note"), f"allocationItems[{index}].note")

            expected_total = (
                _parse_amount(item_shipping_fee)
                + _parse_amount(item_tax_fee)
                + _parse_amount(item_other_fee)
                + _parse_amount(item_adjustment)
            )
            if expected_total.quantize(Decimal("0.00")) != _parse_amount(item_total):
                raise AppError(400, "分摊明细 totalCny 与各项费用不一致", "VALIDATION_FAILED")
            if _parse_amount(item_adjustment) != Decimal("0.00") and not (item_note or global_note):
                raise AppError(400, "存在人工调整时必须填写说明", "VALIDATION_FAILED")

            seen_user_ids.add(user_id)
            normalized_allocations.append(
                {
                    "userId": user_id,
                    "weightGram": weight_gram,
                    "shippingFeeCny": item_shipping_fee,
                    "taxFeeCny": item_tax_fee,
                    "otherFeeCny": item_other_fee,
                    "adjustmentCny": item_adjustment,
                    "totalCny": item_total,
                    "note": item_note,
                }
            )

        if seen_user_ids != batch_member_user_ids:
            raise AppError(400, "国际费用分摊必须覆盖批次内全部成员", "VALIDATION_FAILED")

        allocation_weight = sum(item["weightGram"] for item in normalized_allocations)
        if total_weight_gram > 0 and allocation_weight > total_weight_gram:
            raise AppError(400, "分摊重量不能大于批次总重量", "VALIDATION_FAILED")

        batch_total = _parse_amount(shipping_fee_cny) + _parse_amount(tax_fee_cny) + _parse_amount(other_fee_cny)
        allocation_total = sum(_parse_amount(item["totalCny"]) for item in normalized_allocations)
        adjustment_total = sum(_parse_amount(item["adjustmentCny"]) for item in normalized_allocations)
        if (batch_total + adjustment_total).quantize(Decimal("0.00")) != allocation_total:
            raise AppError(400, "国际费用分摊总额与批次费用不一致", "VALIDATION_FAILED")

        before = self.build_batch_snapshot(batch)
        batch["totalWeightGram"] = total_weight_gram
        batch["shippingFeeCny"] = shipping_fee_cny
        batch["taxFeeCny"] = tax_fee_cny
        batch["otherFeeCny"] = other_fee_cny
        if global_note is not None:
            batch["note"] = global_note
        if _parse_amount(tax_fee_cny) > Decimal("0.00") and batch["status"] in {
            INTERNATIONAL_BATCH_STATUS_PREPARING,
            INTERNATIONAL_BATCH_STATUS_SHIPPED,
        }:
            batch["status"] = INTERNATIONAL_BATCH_STATUS_TAXED
        batch["updatedAt"] = self.now_iso()

        allocation_ids: list[str] = []
        charge_ids: list[str] = []
        payee_user_id = _normalize_optional_text(
            payload.get("payeeUserId")
            if "payeeUserId" in payload
            else payload.get("payee_user_id"),
            "payeeUserId",
        )
        payment_channel_id = _normalize_optional_text(
            payload.get("paymentChannelId")
            if "paymentChannelId" in payload
            else payload.get("payment_channel_id"),
            "paymentChannelId",
        )
        if payee_user_id and self.get_user_snapshot_by_id(payee_user_id) is None:
            raise AppError(404, "国际费用收款人不存在", "NOT_FOUND")

        for item in normalized_allocations:
            allocation_id = self.next_id("internationalFeeAllocation", "intl_fee_allocation")
            charge_id = None
            if self.create_charge is not None and payee_user_id and _parse_amount(item["totalCny"]) > Decimal("0.00"):
                charge = self.create_charge(
                    {
                        "type": "international",
                        "payerUserId": item["userId"],
                        "payeeUserId": payee_user_id,
                        "bizType": "international_batch",
                        "bizId": batch_id,
                        "amountCny": item["totalCny"],
                        "paymentChannelId": payment_channel_id,
                        "snapshot": {
                            "batchId": batch_id,
                            "batchNo": batch["batchNo"],
                            "forwarderName": batch["forwarderName"],
                            "allocationId": allocation_id,
                        },
                        "note": item["note"] or global_note,
                    }
                )
                charge_id = charge.get("chargeId")
                if charge_id:
                    charge_ids.append(charge_id)
                    for record in batch_records:
                        if record["memberUserId"] != item["userId"]:
                            continue
                        self.link_charge(
                            {
                                "groupBuyRecordId": record["id"],
                                "chargeType": "international",
                                "chargeId": charge_id,
                            },
                            actor_user_id=actor_user_id,
                        )

            self.state["internationalFeeAllocations"].append(
                {
                    "id": allocation_id,
                    "batchId": batch_id,
                    "userId": item["userId"],
                    "weightGram": item["weightGram"],
                    "shippingFeeCny": item["shippingFeeCny"],
                    "taxFeeCny": item["taxFeeCny"],
                    "otherFeeCny": item["otherFeeCny"],
                    "adjustmentCny": item["adjustmentCny"],
                    "totalCny": item["totalCny"],
                    "note": item["note"],
                    "chargeId": charge_id,
                    "createdAt": self.now_iso(),
                }
            )
            allocation_ids.append(allocation_id)

        self.audit_log(
            actor_user_id=actor_user_id,
            action="international_batch.record_fees",
            object_type="international_batch",
            object_id=batch_id,
            before=before,
            after={
                **self.build_batch_snapshot(batch),
                "chargeIds": charge_ids,
            },
            reason="录入国际费用分摊",
        )
        return {
            "batchId": batch_id,
            "allocationIds": allocation_ids,
            "chargeIds": charge_ids,
        }
