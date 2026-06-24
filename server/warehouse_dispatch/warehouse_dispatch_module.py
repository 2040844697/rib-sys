from __future__ import annotations

import copy
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from ..errors import AppError


STOCK_ITEM_STATUS_IN_STOCK = "in_stock"
STOCK_ITEM_STATUS_RESERVED = "reserved"
STOCK_ITEM_STATUS_SHIPPED = "shipped"
STOCK_ITEM_STATUS_COMPLETED = "completed"
ALLOWED_STOCK_ITEM_STATUSES = {
    STOCK_ITEM_STATUS_IN_STOCK,
    STOCK_ITEM_STATUS_RESERVED,
    STOCK_ITEM_STATUS_SHIPPED,
    STOCK_ITEM_STATUS_COMPLETED,
}

DISPATCH_REQUEST_STATUS_SUBMITTED = "submitted"
DISPATCH_REQUEST_STATUS_REVIEWING = "reviewing"
DISPATCH_REQUEST_STATUS_PACKED = "packed"
DISPATCH_REQUEST_STATUS_DOMESTIC_FEE_PENDING = "domestic_fee_pending"
DISPATCH_REQUEST_STATUS_DOMESTIC_FEE_CONFIRMED = "domestic_fee_confirmed"
DISPATCH_REQUEST_STATUS_SHIPPED = "shipped"
DISPATCH_REQUEST_STATUS_COMPLETED = "completed"
DISPATCH_REQUEST_STATUS_CANCELLED = "cancelled"
ALLOWED_DISPATCH_REQUEST_STATUSES = {
    DISPATCH_REQUEST_STATUS_SUBMITTED,
    DISPATCH_REQUEST_STATUS_REVIEWING,
    DISPATCH_REQUEST_STATUS_PACKED,
    DISPATCH_REQUEST_STATUS_DOMESTIC_FEE_PENDING,
    DISPATCH_REQUEST_STATUS_DOMESTIC_FEE_CONFIRMED,
    DISPATCH_REQUEST_STATUS_SHIPPED,
    DISPATCH_REQUEST_STATUS_COMPLETED,
    DISPATCH_REQUEST_STATUS_CANCELLED,
}

INTERNATIONAL_BATCH_STATUS_ARRIVED_DOMESTIC = "arrived_domestic"
INTERNATIONAL_BATCH_STATUS_STOCKED = "stocked"

DOMESTIC_FEE_MODE_PREPAID = "prepaid"
DOMESTIC_FEE_MODE_COD = "cod"
DOMESTIC_FEE_MODE_WAIVED = "waived"
ALLOWED_DOMESTIC_FEE_MODES = {
    DOMESTIC_FEE_MODE_PREPAID,
    DOMESTIC_FEE_MODE_COD,
    DOMESTIC_FEE_MODE_WAIVED,
}


def clone(value: Any) -> Any:
    return copy.deepcopy(value)


def ensure_warehouse_dispatch_state(state: dict[str, Any]) -> bool:
    changed = False

    counters = state.setdefault("counters", {})
    stock_items = state.setdefault("stockItems", [])
    dispatch_requests = state.setdefault("dispatchRequests", [])
    dispatch_items = state.setdefault("dispatchItems", [])
    domestic_shipments = state.setdefault("domesticShipments", [])

    defaults = {
        "stockItem": len(stock_items),
        "dispatchRequest": len(dispatch_requests),
        "dispatchItem": len(dispatch_items),
        "domesticShipment": len(domestic_shipments),
    }
    for counter_key, counter_value in defaults.items():
        if counter_key not in counters:
            counters[counter_key] = counter_value
            changed = True

    for stock_item in stock_items:
        stock_defaults = {
            "memberUserId": None,
            "groupBuyId": None,
            "groupBuyItemId": None,
            "availableQuantity": stock_item.get("quantity", 0),
            "status": STOCK_ITEM_STATUS_IN_STOCK,
            "dispatchRequestId": None,
            "shipmentId": None,
            "completedAt": None,
            "note": None,
            "updatedAt": stock_item.get("createdAt"),
        }
        for key, value in stock_defaults.items():
            if key not in stock_item:
                stock_item[key] = clone(value)
                changed = True
        if stock_item.get("status") not in ALLOWED_STOCK_ITEM_STATUSES:
            stock_item["status"] = STOCK_ITEM_STATUS_IN_STOCK
            changed = True

    for dispatch_request in dispatch_requests:
        request_defaults = {
            "status": DISPATCH_REQUEST_STATUS_SUBMITTED,
            "note": None,
            "submittedAt": dispatch_request.get("createdAt"),
            "packedAt": None,
            "shippedAt": None,
            "completedAt": None,
            "shippingFeeCny": None,
            "feeMode": None,
            "paymentChannelId": None,
            "domesticChargeId": None,
            "domesticFeeRecordedAt": None,
            "domesticFeeConfirmedAt": None,
            "domesticFeeConfirmedProofId": None,
            "domesticShipmentId": None,
            "updatedAt": dispatch_request.get("createdAt"),
        }
        for key, value in request_defaults.items():
            if key not in dispatch_request:
                dispatch_request[key] = clone(value)
                changed = True
        if dispatch_request.get("status") not in ALLOWED_DISPATCH_REQUEST_STATUSES:
            dispatch_request["status"] = DISPATCH_REQUEST_STATUS_SUBMITTED
            changed = True

    for dispatch_item in dispatch_items:
        if "createdAt" not in dispatch_item:
            dispatch_item["createdAt"] = None
            changed = True

    for shipment in domestic_shipments:
        shipment_defaults = {
            "shippingFeeCny": None,
            "feeMode": None,
            "note": None,
            "updatedAt": shipment.get("createdAt"),
        }
        for key, value in shipment_defaults.items():
            if key not in shipment:
                shipment[key] = clone(value)
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


def _normalize_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    if value <= 0:
        raise AppError(400, f"{field_name}必须大于 0", "VALIDATION_FAILED")
    return value


def _normalize_page_int(value: Any, field_name: str, default_value: int) -> int:
    if value in {None, ""}:
        return default_value
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return default_value
        if not normalized.isdigit():
            raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
        return max(int(normalized), 1)
    if isinstance(value, int) and not isinstance(value, bool):
        return max(value, 1)
    raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")


def _normalize_price_cny(value: Any, field_name: str, *, allow_zero: bool) -> str:
    if isinstance(value, bool) or value in {None, ""}:
        raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED") from exc
    if amount < 0:
        raise AppError(400, f"{field_name}不能小于 0", "VALIDATION_FAILED")
    if not allow_zero and amount == Decimal("0"):
        raise AppError(400, f"{field_name}必须大于 0", "VALIDATION_FAILED")
    return f"{amount.quantize(Decimal('0.00'))}"


def _normalize_datetime_text(value: Any, field_name: str) -> str:
    normalized = _normalize_required_text(value, field_name)
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).isoformat()
    except ValueError as exc:
        raise AppError(400, f"{field_name}不是合法时间", "VALIDATION_FAILED") from exc


class WarehouseDispatchModule:
    def __init__(
        self,
        *,
        state: dict[str, Any],
        next_id: Callable[[str, str], str],
        audit_log: Callable[..., Any],
        now_iso: Callable[[], str],
        has_permission_by_user_id: Callable[[str, str], bool],
        get_user_snapshot_by_id: Callable[[str], dict[str, Any] | None],
        require_group_buy_record: Callable[[str], dict[str, Any]],
        build_group_buy_record_summary: Callable[[dict[str, Any]], dict[str, Any]],
        mark_stocked: Callable[..., dict[str, Any]],
        mark_dispatch_requested: Callable[..., dict[str, Any]],
        mark_dispatched: Callable[..., dict[str, Any]],
        mark_completed: Callable[..., dict[str, Any]],
        link_charge: Callable[..., dict[str, Any]],
        create_charge: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ):
        self.state = state
        self.next_id = next_id
        self.audit_log = audit_log
        self.now_iso = now_iso
        self.has_permission_by_user_id = has_permission_by_user_id
        self.get_user_snapshot_by_id = get_user_snapshot_by_id
        self.require_group_buy_record = require_group_buy_record
        self.build_group_buy_record_summary = build_group_buy_record_summary
        self.mark_stocked = mark_stocked
        self.mark_dispatch_requested = mark_dispatch_requested
        self.mark_dispatched = mark_dispatched
        self.mark_completed = mark_completed
        self.link_charge = link_charge
        self.create_charge = create_charge

    def require_stock_item(self, stock_item_id: str) -> dict[str, Any]:
        stock_item = next(
            (item for item in self.state.get("stockItems", []) if item["id"] == stock_item_id),
            None,
        )
        if stock_item is None:
            raise AppError(404, "库存记录不存在", "NOT_FOUND")
        return stock_item

    def require_dispatch_request(self, dispatch_request_id: str) -> dict[str, Any]:
        dispatch_request = next(
            (item for item in self.state.get("dispatchRequests", []) if item["id"] == dispatch_request_id),
            None,
        )
        if dispatch_request is None:
            raise AppError(404, "排发申请不存在", "NOT_FOUND")
        return dispatch_request

    def list_dispatch_items(self, dispatch_request_id: str) -> list[dict[str, Any]]:
        return [
            clone(item)
            for item in self.state.get("dispatchItems", [])
            if item["dispatchRequestId"] == dispatch_request_id
        ]

    def list_request_stock_items(self, dispatch_request_id: str) -> list[dict[str, Any]]:
        return [
            stock_item
            for stock_item in self.state.get("stockItems", [])
            if stock_item.get("dispatchRequestId") == dispatch_request_id
        ]

    def build_dispatch_request_snapshot(self, dispatch_request: dict[str, Any]) -> dict[str, Any]:
        return {
            **clone(dispatch_request),
            "items": self.list_dispatch_items(dispatch_request["id"]),
        }

    def list_dispatchable_items(self, payload: dict[str, Any], *, actor_user_id: str) -> dict[str, Any]:
        member_user_id = _normalize_required_text(
            payload.get("memberUserId")
            if "memberUserId" in payload
            else payload.get("member_user_id")
            or actor_user_id,
            "memberUserId",
        )
        warehouse_user_id = _normalize_optional_text(
            payload.get("warehouseUserId")
            if "warehouseUserId" in payload
            else payload.get("warehouse_user_id"),
            "warehouseUserId",
        )
        page = _normalize_page_int(payload.get("page"), "page", 1)
        page_size = min(_normalize_page_int(payload.get("pageSize") or payload.get("page_size"), "pageSize", 20), 100)

        if actor_user_id != member_user_id:
            if warehouse_user_id is None:
                raise AppError(400, "查看他人的可排发商品时必须指定 warehouseUserId", "VALIDATION_FAILED")
            self._assert_can_manage_warehouse(actor_user_id, warehouse_user_id)

        items: list[dict[str, Any]] = []
        for stock_item in self.state.get("stockItems", []):
            if stock_item["status"] != STOCK_ITEM_STATUS_IN_STOCK:
                continue
            if stock_item["memberUserId"] != member_user_id:
                continue
            if warehouse_user_id is not None and stock_item["warehouseUserId"] != warehouse_user_id:
                continue

            record = self.require_group_buy_record(stock_item["groupBuyRecordId"])
            record_summary = self.build_group_buy_record_summary(record)
            if not record_summary["isDispatchable"]:
                continue

            items.append(
                {
                    "stockItemId": stock_item["id"],
                    "groupBuyRecordId": stock_item["groupBuyRecordId"],
                    "groupBuyId": stock_item["groupBuyId"],
                    "groupBuyItemId": stock_item["groupBuyItemId"],
                    "memberUserId": stock_item["memberUserId"],
                    "warehouseUserId": stock_item["warehouseUserId"],
                    "quantity": stock_item["quantity"],
                    "status": record_summary["status"],
                    "displayStatus": record_summary["displayStatus"],
                    "isDispatchable": record_summary["isDispatchable"],
                    "stockedAt": stock_item["stockedAt"],
                    "updatedAt": stock_item["updatedAt"],
                }
            )

        items.sort(key=lambda item: (item["stockedAt"] or "", item["stockItemId"]))
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "items": items[start:end],
            "total": len(items),
            "page": page,
            "pageSize": page_size,
        }

    def stock_in_records(
        self,
        payload: dict[str, Any],
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        warehouse_user_id = _normalize_required_text(
            payload.get("warehouseUserId")
            if "warehouseUserId" in payload
            else payload.get("warehouse_user_id"),
            "warehouseUserId",
        )
        group_buy_record_ids = self._normalize_record_id_list(
            payload.get("groupBuyRecordIds") if "groupBuyRecordIds" in payload else payload.get("group_buy_record_ids")
        )
        stocked_at = _normalize_datetime_text(
            payload.get("stockedAt") if "stockedAt" in payload else payload.get("stocked_at"),
            "stockedAt",
        )
        note = _normalize_optional_text(payload.get("note"), "note")

        self._assert_can_manage_warehouse(actor_user_id, warehouse_user_id)
        self._require_user(warehouse_user_id, "warehouseUserId")

        before_items: dict[str, Any] = {}
        stock_item_ids: list[str] = []
        touched_stock_items: list[dict[str, Any]] = []
        now = self.now_iso()

        for record_id in group_buy_record_ids:
            record = self.require_group_buy_record(record_id)
            stock_item = next(
                (item for item in self.state["stockItems"] if item["groupBuyRecordId"] == record_id),
                None,
            )
            if stock_item is None:
                stock_item = {
                    "id": self.next_id("stockItem", "stock_item"),
                    "warehouseUserId": warehouse_user_id,
                    "groupBuyRecordId": record_id,
                    "memberUserId": record["memberUserId"],
                    "groupBuyId": record["groupBuyId"],
                    "groupBuyItemId": record["groupBuyItemId"],
                    "quantity": record["quantity"],
                    "availableQuantity": record["quantity"],
                    "status": STOCK_ITEM_STATUS_IN_STOCK,
                    "stockedAt": stocked_at,
                    "dispatchRequestId": None,
                    "shipmentId": None,
                    "completedAt": None,
                    "note": note,
                    "createdAt": now,
                    "updatedAt": now,
                }
                self.state["stockItems"].append(stock_item)
                before_snapshot = None
            else:
                before_snapshot = clone(stock_item)
                if stock_item["status"] in {
                    STOCK_ITEM_STATUS_RESERVED,
                    STOCK_ITEM_STATUS_SHIPPED,
                    STOCK_ITEM_STATUS_COMPLETED,
                }:
                    raise AppError(400, "已有排发流程的库存不能重复入库", "DUPLICATED_OPERATION")
                stock_item["warehouseUserId"] = warehouse_user_id
                stock_item["memberUserId"] = record["memberUserId"]
                stock_item["groupBuyId"] = record["groupBuyId"]
                stock_item["groupBuyItemId"] = record["groupBuyItemId"]
                stock_item["quantity"] = record["quantity"]
                stock_item["availableQuantity"] = record["quantity"]
                stock_item["status"] = STOCK_ITEM_STATUS_IN_STOCK
                stock_item["stockedAt"] = stocked_at
                stock_item["note"] = note
                stock_item["updatedAt"] = now

            before_items[stock_item["id"]] = before_snapshot
            touched_stock_items.append(stock_item)
            stock_item_ids.append(stock_item["id"])

        self.mark_stocked(
            {
                "groupBuyRecordIds": group_buy_record_ids,
                "warehouseUserId": warehouse_user_id,
                "stockedAt": stocked_at,
            },
            actor_user_id=actor_user_id,
        )

        for stock_item in touched_stock_items:
            self.audit_log(
                actor_user_id=actor_user_id,
                action="stock_item.stock_in",
                object_type="stock_item",
                object_id=stock_item["id"],
                before=before_items[stock_item["id"]],
                after=clone(stock_item),
                reason=note or "国内囤货入库",
            )

        return {"stockItemIds": stock_item_ids}

    def stock_in_international_batch(
        self,
        batch_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        batch = self._require_international_batch(batch_id)
        if batch["status"] == INTERNATIONAL_BATCH_STATUS_STOCKED:
            raise AppError(400, "国际批次已经完成入库", "DUPLICATED_OPERATION")
        if batch["status"] != INTERNATIONAL_BATCH_STATUS_ARRIVED_DOMESTIC:
            raise AppError(400, "只有已到国内的批次才能入库", "INVALID_STATUS")

        warehouse_user_id = _normalize_required_text(batch.get("warehouseUserId"), "warehouseUserId")
        record_ids = self._list_batch_record_ids(batch_id)
        if not record_ids:
            raise AppError(400, "空批次不能入库", "VALIDATION_FAILED")

        stocked_at = _normalize_datetime_text(
            payload.get("stockedAt") if "stockedAt" in payload else payload.get("stocked_at"),
            "stockedAt",
        )
        note = _normalize_optional_text(payload.get("note"), "note")

        before = {
            **clone(batch),
            "groupBuyRecordIds": record_ids,
        }
        result = self.stock_in_records(
            {
                "warehouseUserId": warehouse_user_id,
                "groupBuyRecordIds": record_ids,
                "stockedAt": stocked_at,
                "note": note,
            },
            actor_user_id=actor_user_id,
        )

        batch["status"] = INTERNATIONAL_BATCH_STATUS_STOCKED
        batch["stockedAt"] = stocked_at
        if note is not None:
            batch["note"] = note
        batch["updatedAt"] = self.now_iso()

        self.audit_log(
            actor_user_id=actor_user_id,
            action="international_batch.stock_in",
            object_type="international_batch",
            object_id=batch_id,
            before=before,
            after={
                **clone(batch),
                "groupBuyRecordIds": record_ids,
                "stockItemIds": result["stockItemIds"],
            },
            reason=note or "国际批次转国内入库",
        )
        return {
            "batchId": batch_id,
            "status": batch["status"],
            "stockItemIds": result["stockItemIds"],
        }

    def create_dispatch_request(
        self,
        payload: dict[str, Any],
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        requester_user_id = _normalize_required_text(
            payload.get("requesterUserId")
            if "requesterUserId" in payload
            else payload.get("requester_user_id")
            or actor_user_id,
            "requesterUserId",
        )
        warehouse_user_id = _normalize_required_text(
            payload.get("warehouseUserId")
            if "warehouseUserId" in payload
            else payload.get("warehouse_user_id"),
            "warehouseUserId",
        )
        receiver_name = _normalize_required_text(
            payload.get("receiverName") if "receiverName" in payload else payload.get("receiver_name"),
            "receiverName",
            2,
        )
        receiver_phone = _normalize_required_text(
            payload.get("receiverPhone") if "receiverPhone" in payload else payload.get("receiver_phone"),
            "receiverPhone",
            6,
        )
        receiver_address = _normalize_required_text(
            payload.get("receiverAddress")
            if "receiverAddress" in payload
            else payload.get("receiver_address"),
            "receiverAddress",
            4,
        )
        note = _normalize_optional_text(payload.get("note"), "note")

        self._assert_can_request_dispatch(actor_user_id, requester_user_id)
        self._require_user(requester_user_id, "requesterUserId")
        self._require_user(warehouse_user_id, "warehouseUserId")

        raw_items = payload.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise AppError(400, "items格式不正确", "VALIDATION_FAILED")

        selected_stock_items: list[dict[str, Any]] = []
        selected_record_ids: list[str] = []
        dispatch_item_payloads: list[dict[str, Any]] = []
        seen_stock_item_ids: set[str] = set()
        for index, item in enumerate(raw_items):
            if not isinstance(item, dict):
                raise AppError(400, f"items[{index}]格式不正确", "VALIDATION_FAILED")

            stock_item_id = _normalize_required_text(
                item.get("stockItemId") if "stockItemId" in item else item.get("stock_item_id"),
                f"items[{index}].stockItemId",
            )
            if stock_item_id in seen_stock_item_ids:
                raise AppError(400, "同一库存不能重复加入排发申请", "DUPLICATED_OPERATION")

            stock_item = self.require_stock_item(stock_item_id)
            if stock_item["warehouseUserId"] != warehouse_user_id:
                raise AppError(400, "排发申请不能混合多个囤货人", "VALIDATION_FAILED")
            if stock_item["memberUserId"] != requester_user_id:
                raise AppError(403, "只能申请自己的可排发商品", "FORBIDDEN")
            if stock_item["status"] != STOCK_ITEM_STATUS_IN_STOCK or stock_item.get("dispatchRequestId"):
                raise AppError(400, "库存已被其他排发申请占用", "DUPLICATED_OPERATION")

            quantity = _normalize_positive_int(item.get("quantity"), f"items[{index}].quantity")
            # 第一版仍以整条拼单记录作为排发单位，避免一条记录同时处于多个排发状态。
            if quantity != stock_item["quantity"]:
                raise AppError(400, "当前版本暂不支持部分数量排发，请按整条库存申请", "VALIDATION_FAILED")

            if "groupBuyRecordId" in item or "group_buy_record_id" in item:
                group_buy_record_id = _normalize_required_text(
                    item.get("groupBuyRecordId") if "groupBuyRecordId" in item else item.get("group_buy_record_id"),
                    f"items[{index}].groupBuyRecordId",
                )
                if group_buy_record_id != stock_item["groupBuyRecordId"]:
                    raise AppError(400, "库存与拼单记录不匹配", "VALIDATION_FAILED")

            record = self.require_group_buy_record(stock_item["groupBuyRecordId"])
            record_summary = self.build_group_buy_record_summary(record)
            if not record_summary["isDispatchable"]:
                raise AppError(400, "存在不可排发记录，不能创建排发申请", "NOT_DISPATCHABLE")

            seen_stock_item_ids.add(stock_item_id)
            selected_stock_items.append(stock_item)
            selected_record_ids.append(stock_item["groupBuyRecordId"])
            dispatch_item_payloads.append(
                {
                    "stockItemId": stock_item["id"],
                    "groupBuyRecordId": stock_item["groupBuyRecordId"],
                    "quantity": quantity,
                }
            )

        now = self.now_iso()
        dispatch_request = {
            "id": self.next_id("dispatchRequest", "dispatch_request"),
            "requesterUserId": requester_user_id,
            "warehouseUserId": warehouse_user_id,
            "status": DISPATCH_REQUEST_STATUS_SUBMITTED,
            "receiverName": receiver_name,
            "receiverPhone": receiver_phone,
            "receiverAddress": receiver_address,
            "note": note,
            "submittedAt": now,
            "packedAt": None,
            "shippedAt": None,
            "completedAt": None,
            "shippingFeeCny": None,
            "feeMode": None,
            "paymentChannelId": None,
            "domesticChargeId": None,
            "domesticFeeRecordedAt": None,
            "domesticFeeConfirmedAt": None,
            "domesticFeeConfirmedProofId": None,
            "domesticShipmentId": None,
            "createdAt": now,
            "updatedAt": now,
        }
        self.state["dispatchRequests"].append(dispatch_request)

        created_item_ids: list[str] = []
        for stock_item, item_payload in zip(selected_stock_items, dispatch_item_payloads, strict=False):
            before = clone(stock_item)
            stock_item["status"] = STOCK_ITEM_STATUS_RESERVED
            stock_item["availableQuantity"] = 0
            stock_item["dispatchRequestId"] = dispatch_request["id"]
            stock_item["updatedAt"] = now

            dispatch_item = {
                "id": self.next_id("dispatchItem", "dispatch_item"),
                "dispatchRequestId": dispatch_request["id"],
                "stockItemId": item_payload["stockItemId"],
                "groupBuyRecordId": item_payload["groupBuyRecordId"],
                "quantity": item_payload["quantity"],
                "createdAt": now,
            }
            self.state["dispatchItems"].append(dispatch_item)
            created_item_ids.append(dispatch_item["id"])

            self.audit_log(
                actor_user_id=actor_user_id,
                action="stock_item.reserve_for_dispatch",
                object_type="stock_item",
                object_id=stock_item["id"],
                before=before,
                after=clone(stock_item),
                reason=note or "创建排发申请",
            )

        self.mark_dispatch_requested(
            {
                "groupBuyRecordIds": selected_record_ids,
                "dispatchRequestId": dispatch_request["id"],
            },
            actor_user_id=actor_user_id,
        )

        self.audit_log(
            actor_user_id=actor_user_id,
            action="dispatch_request.create",
            object_type="dispatch_request",
            object_id=dispatch_request["id"],
            before=None,
            after={
                **self.build_dispatch_request_snapshot(dispatch_request),
                "dispatchItemIds": created_item_ids,
            },
            reason=note or "成员创建排发申请",
        )
        return {
            "dispatchRequestId": dispatch_request["id"],
            "status": dispatch_request["status"],
        }

    def mark_dispatch_packed(
        self,
        dispatch_request_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        dispatch_request = self.require_dispatch_request(dispatch_request_id)
        self._assert_can_manage_warehouse(actor_user_id, dispatch_request["warehouseUserId"])
        if dispatch_request["status"] in {
            DISPATCH_REQUEST_STATUS_SHIPPED,
            DISPATCH_REQUEST_STATUS_COMPLETED,
            DISPATCH_REQUEST_STATUS_CANCELLED,
        }:
            raise AppError(400, "当前排发申请状态不能再打包", "INVALID_STATUS")

        packed_at = _normalize_datetime_text(
            payload.get("packedAt") if "packedAt" in payload else payload.get("packed_at"),
            "packedAt",
        )
        note = _normalize_optional_text(payload.get("note"), "note")
        before = self.build_dispatch_request_snapshot(dispatch_request)

        dispatch_request["packedAt"] = packed_at
        if note is not None:
            dispatch_request["note"] = note
        dispatch_request["status"] = DISPATCH_REQUEST_STATUS_PACKED
        dispatch_request["updatedAt"] = self.now_iso()

        self.audit_log(
            actor_user_id=actor_user_id,
            action="dispatch_request.mark_packed",
            object_type="dispatch_request",
            object_id=dispatch_request_id,
            before=before,
            after=self.build_dispatch_request_snapshot(dispatch_request),
            reason=note or "标记已打包",
        )
        return {
            "dispatchRequestId": dispatch_request_id,
            "status": dispatch_request["status"],
        }

    def record_domestic_fee(
        self,
        dispatch_request_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        dispatch_request = self.require_dispatch_request(dispatch_request_id)
        self._assert_can_manage_warehouse(actor_user_id, dispatch_request["warehouseUserId"])
        if not dispatch_request.get("packedAt"):
            raise AppError(400, "请先完成打包，再录入国内运费", "INVALID_STATUS")
        if dispatch_request["status"] in {
            DISPATCH_REQUEST_STATUS_SHIPPED,
            DISPATCH_REQUEST_STATUS_COMPLETED,
            DISPATCH_REQUEST_STATUS_CANCELLED,
        }:
            raise AppError(400, "当前排发申请状态不能录入国内运费", "INVALID_STATUS")
        if dispatch_request.get("feeMode") is not None:
            raise AppError(400, "国内运费已经录入，暂不支持重复生成", "DUPLICATED_OPERATION")

        shipping_fee_cny = _normalize_price_cny(
            payload.get("shippingFeeCny") if "shippingFeeCny" in payload else payload.get("shipping_fee_cny"),
            "shippingFeeCny",
            allow_zero=True,
        )
        fee_mode = _normalize_required_text(
            payload.get("feeMode") if "feeMode" in payload else payload.get("fee_mode"),
            "feeMode",
        )
        if fee_mode not in ALLOWED_DOMESTIC_FEE_MODES:
            raise AppError(400, "feeMode 不支持", "VALIDATION_FAILED")
        payment_channel_id = _normalize_optional_text(
            payload.get("paymentChannelId")
            if "paymentChannelId" in payload
            else payload.get("payment_channel_id"),
            "paymentChannelId",
        )
        note = _normalize_optional_text(payload.get("note"), "note")
        before = self.build_dispatch_request_snapshot(dispatch_request)

        charge_id = None
        charge_amount = Decimal(shipping_fee_cny)
        if fee_mode == DOMESTIC_FEE_MODE_PREPAID and charge_amount > Decimal("0.00"):
            if self.create_charge is None:
                raise RuntimeError("Charge creation dependency is required.")
            charge = self.create_charge(
                {
                    "actorUserId": actor_user_id,
                    "type": "domestic_shipping",
                    "payerUserId": dispatch_request["requesterUserId"],
                    "payeeUserId": dispatch_request["warehouseUserId"],
                    "bizType": "dispatch_request",
                    "bizId": dispatch_request_id,
                    "amountCny": shipping_fee_cny,
                    "paymentChannelId": payment_channel_id,
                    "snapshot": {
                        "dispatchRequestId": dispatch_request_id,
                        "warehouseUserId": dispatch_request["warehouseUserId"],
                        "requesterUserId": dispatch_request["requesterUserId"],
                        "stockItemIds": [item["stockItemId"] for item in self.list_dispatch_items(dispatch_request_id)],
                    },
                    "note": note or "国内运费",
                }
            )
            charge_id = charge.get("chargeId")
            for dispatch_item in self.list_dispatch_items(dispatch_request_id):
                self.link_charge(
                    {
                        "groupBuyRecordId": dispatch_item["groupBuyRecordId"],
                        "chargeType": "domestic_shipping",
                        "chargeId": charge_id,
                    },
                    actor_user_id=actor_user_id,
                )

        dispatch_request["shippingFeeCny"] = shipping_fee_cny
        dispatch_request["feeMode"] = fee_mode
        dispatch_request["paymentChannelId"] = payment_channel_id
        dispatch_request["domesticChargeId"] = charge_id
        dispatch_request["domesticFeeRecordedAt"] = self.now_iso()
        if note is not None:
            dispatch_request["note"] = note

        if fee_mode == DOMESTIC_FEE_MODE_PREPAID and charge_id is not None:
            dispatch_request["status"] = DISPATCH_REQUEST_STATUS_DOMESTIC_FEE_PENDING
        elif fee_mode == DOMESTIC_FEE_MODE_COD:
            dispatch_request["status"] = DISPATCH_REQUEST_STATUS_PACKED
        else:
            dispatch_request["status"] = DISPATCH_REQUEST_STATUS_DOMESTIC_FEE_CONFIRMED
            dispatch_request["domesticFeeConfirmedAt"] = self.now_iso()

        dispatch_request["updatedAt"] = self.now_iso()

        self.audit_log(
            actor_user_id=actor_user_id,
            action="dispatch_request.record_domestic_fee",
            object_type="dispatch_request",
            object_id=dispatch_request_id,
            before=before,
            after=self.build_dispatch_request_snapshot(dispatch_request),
            reason=note or "录入国内运费",
        )
        return {
            "dispatchRequestId": dispatch_request_id,
            "chargeId": charge_id,
        }

    def record_domestic_shipment(
        self,
        dispatch_request_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        dispatch_request = self.require_dispatch_request(dispatch_request_id)
        self._assert_can_manage_warehouse(actor_user_id, dispatch_request["warehouseUserId"])
        if not dispatch_request.get("packedAt"):
            raise AppError(400, "请先完成打包，再录入国内快递", "INVALID_STATUS")
        if dispatch_request.get("domesticShipmentId") is not None:
            raise AppError(400, "国内快递已经录入", "DUPLICATED_OPERATION")
        if dispatch_request["status"] in {
            DISPATCH_REQUEST_STATUS_COMPLETED,
            DISPATCH_REQUEST_STATUS_CANCELLED,
        }:
            raise AppError(400, "当前排发申请状态不能录入国内快递", "INVALID_STATUS")
        if dispatch_request.get("feeMode") is None:
            raise AppError(400, "请先录入国内运费模式，再填写快递信息", "INVALID_STATUS")
        if dispatch_request["feeMode"] == DOMESTIC_FEE_MODE_PREPAID and dispatch_request["status"] != DISPATCH_REQUEST_STATUS_DOMESTIC_FEE_CONFIRMED:
            raise AppError(400, "预付运费尚未确认，不能直接发货", "INVALID_STATUS")

        carrier = _normalize_required_text(payload.get("carrier"), "carrier", 2)
        tracking_no = _normalize_required_text(
            payload.get("trackingNo") if "trackingNo" in payload else payload.get("tracking_no"),
            "trackingNo",
            2,
        )
        shipped_at = _normalize_datetime_text(
            payload.get("shippedAt") if "shippedAt" in payload else payload.get("shipped_at"),
            "shippedAt",
        )
        note = _normalize_optional_text(payload.get("note"), "note")
        before = self.build_dispatch_request_snapshot(dispatch_request)
        now = self.now_iso()

        shipment = {
            "id": self.next_id("domesticShipment", "domestic_shipment"),
            "dispatchRequestId": dispatch_request_id,
            "carrier": carrier,
            "trackingNo": tracking_no,
            "shippingFeeCny": dispatch_request.get("shippingFeeCny"),
            "feeMode": dispatch_request.get("feeMode"),
            "shippedAt": shipped_at,
            "note": note,
            "createdAt": now,
            "updatedAt": now,
        }
        self.state["domesticShipments"].append(shipment)

        dispatch_request["domesticShipmentId"] = shipment["id"]
        dispatch_request["shippedAt"] = shipped_at
        dispatch_request["status"] = DISPATCH_REQUEST_STATUS_SHIPPED
        if note is not None:
            dispatch_request["note"] = note
        dispatch_request["updatedAt"] = now

        group_buy_record_ids: list[str] = []
        for stock_item in self.list_request_stock_items(dispatch_request_id):
            before_stock_item = clone(stock_item)
            stock_item["status"] = STOCK_ITEM_STATUS_SHIPPED
            stock_item["availableQuantity"] = 0
            stock_item["shipmentId"] = shipment["id"]
            stock_item["updatedAt"] = now
            group_buy_record_ids.append(stock_item["groupBuyRecordId"])
            self.audit_log(
                actor_user_id=actor_user_id,
                action="stock_item.mark_shipped",
                object_type="stock_item",
                object_id=stock_item["id"],
                before=before_stock_item,
                after=clone(stock_item),
                reason=note or "录入国内快递",
            )

        self.mark_dispatched(
            {
                "groupBuyRecordIds": group_buy_record_ids,
                "dispatchRequestId": dispatch_request_id,
                "shipmentId": shipment["id"],
            },
            actor_user_id=actor_user_id,
        )

        self.audit_log(
            actor_user_id=actor_user_id,
            action="dispatch_request.record_domestic_shipment",
            object_type="dispatch_request",
            object_id=dispatch_request_id,
            before=before,
            after={
                **self.build_dispatch_request_snapshot(dispatch_request),
                "domesticShipment": clone(shipment),
            },
            reason=note or "录入国内快递",
        )
        return {
            "domesticShipmentId": shipment["id"],
            "dispatchRequestId": dispatch_request_id,
            "status": dispatch_request["status"],
        }

    def complete_dispatch_request(
        self,
        dispatch_request_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        dispatch_request = self.require_dispatch_request(dispatch_request_id)
        self._assert_can_complete_dispatch(actor_user_id, dispatch_request)
        if dispatch_request["status"] == DISPATCH_REQUEST_STATUS_COMPLETED:
            raise AppError(400, "排发申请已经完成", "DUPLICATED_OPERATION")
        if dispatch_request["status"] != DISPATCH_REQUEST_STATUS_SHIPPED:
            raise AppError(400, "只有已发货的排发申请才能完结", "INVALID_STATUS")

        completed_at = _normalize_datetime_text(
            payload.get("completedAt") if "completedAt" in payload else payload.get("completed_at"),
            "completedAt",
        )
        note = _normalize_optional_text(payload.get("note"), "note")
        before = self.build_dispatch_request_snapshot(dispatch_request)
        now = self.now_iso()

        dispatch_request["completedAt"] = completed_at
        dispatch_request["status"] = DISPATCH_REQUEST_STATUS_COMPLETED
        if note is not None:
            dispatch_request["note"] = note
        dispatch_request["updatedAt"] = now

        group_buy_record_ids: list[str] = []
        for stock_item in self.list_request_stock_items(dispatch_request_id):
            before_stock_item = clone(stock_item)
            stock_item["status"] = STOCK_ITEM_STATUS_COMPLETED
            stock_item["completedAt"] = completed_at
            stock_item["availableQuantity"] = 0
            stock_item["updatedAt"] = now
            group_buy_record_ids.append(stock_item["groupBuyRecordId"])
            self.audit_log(
                actor_user_id=actor_user_id,
                action="stock_item.complete_dispatch",
                object_type="stock_item",
                object_id=stock_item["id"],
                before=before_stock_item,
                after=clone(stock_item),
                reason=note or "排发完成",
            )

        self.mark_completed(
            {
                "groupBuyRecordIds": group_buy_record_ids,
                "dispatchRequestId": dispatch_request_id,
                "completedAt": completed_at,
            },
            actor_user_id=actor_user_id,
        )

        self.audit_log(
            actor_user_id=actor_user_id,
            action="dispatch_request.complete",
            object_type="dispatch_request",
            object_id=dispatch_request_id,
            before=before,
            after=self.build_dispatch_request_snapshot(dispatch_request),
            reason=note or "排发已完成",
        )
        return {
            "dispatchRequestId": dispatch_request_id,
            "status": dispatch_request["status"],
        }

    def confirm_charge(
        self,
        charge_id: str,
        *,
        proof_id: str | None,
        actor_user_id: str | None,
    ) -> dict[str, Any]:
        dispatch_request = next(
            (
                item
                for item in self.state.get("dispatchRequests", [])
                if item.get("domesticChargeId") == charge_id
            ),
            None,
        )
        if dispatch_request is None:
            return {"updatedCount": 0}

        before = self.build_dispatch_request_snapshot(dispatch_request)
        dispatch_request["status"] = DISPATCH_REQUEST_STATUS_DOMESTIC_FEE_CONFIRMED
        dispatch_request["domesticFeeConfirmedAt"] = self.now_iso()
        dispatch_request["domesticFeeConfirmedProofId"] = proof_id
        dispatch_request["updatedAt"] = self.now_iso()

        self.audit_log(
            actor_user_id=actor_user_id,
            action="dispatch_request.confirm_domestic_fee",
            object_type="dispatch_request",
            object_id=dispatch_request["id"],
            before=before,
            after=self.build_dispatch_request_snapshot(dispatch_request),
            reason="国内运费付款已确认",
        )
        return {
            "updatedCount": 1,
            "dispatchRequestId": dispatch_request["id"],
            "status": dispatch_request["status"],
        }

    def _assert_can_manage_warehouse(self, actor_user_id: str, warehouse_user_id: str) -> None:
        actor = self.get_user_snapshot_by_id(actor_user_id)
        if actor is None:
            raise AppError(404, "用户不存在", "NOT_FOUND")
        if "admin" in actor["roles"]:
            return
        if not self.has_permission_by_user_id(actor_user_id, "dispatch:process_assigned"):
            raise AppError(403, "当前账号没有处理囤货排发的权限", "FORBIDDEN")
        if actor_user_id != warehouse_user_id:
            raise AppError(403, "当前账号只能处理分配给自己的囤货点", "FORBIDDEN")

    def _assert_can_request_dispatch(self, actor_user_id: str, requester_user_id: str) -> None:
        if actor_user_id == requester_user_id:
            if not self.has_permission_by_user_id(actor_user_id, "dispatch:create_self"):
                raise AppError(403, "当前账号没有创建排发申请的权限", "FORBIDDEN")
            return
        if not self.has_permission_by_user_id(actor_user_id, "dispatch:process_assigned"):
            raise AppError(403, "当前账号不能代成员创建排发申请", "FORBIDDEN")

    def _assert_can_complete_dispatch(self, actor_user_id: str, dispatch_request: dict[str, Any]) -> None:
        if actor_user_id == dispatch_request["requesterUserId"]:
            return
        self._assert_can_manage_warehouse(actor_user_id, dispatch_request["warehouseUserId"])

    def _normalize_record_id_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            raise AppError(400, "groupBuyRecordIds格式不正确", "VALIDATION_FAILED")
        record_ids: list[str] = []
        for item in value:
            record_id = _normalize_required_text(item, "groupBuyRecordId")
            if record_id not in record_ids:
                record_ids.append(record_id)
        if not record_ids:
            raise AppError(400, "groupBuyRecordIds不能为空", "VALIDATION_FAILED")
        return record_ids

    def _require_user(self, user_id: str, field_name: str) -> None:
        if self.get_user_snapshot_by_id(user_id) is None:
            raise AppError(404, f"{field_name}对应用户不存在", "NOT_FOUND")

    def _require_international_batch(self, batch_id: str) -> dict[str, Any]:
        batch = next(
            (item for item in self.state.get("internationalBatches", []) if item["id"] == batch_id),
            None,
        )
        if batch is None:
            raise AppError(404, "国际批次不存在", "NOT_FOUND")
        return batch

    def _list_batch_record_ids(self, batch_id: str) -> list[str]:
        return [
            relation["groupBuyRecordId"]
            for relation in self.state.get("internationalBatchRecords", [])
            if relation["batchId"] == batch_id
        ]
