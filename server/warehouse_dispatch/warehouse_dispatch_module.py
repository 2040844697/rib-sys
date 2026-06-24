from __future__ import annotations

import copy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from ..config import Config
from ..db_access import connect
from ..errors import AppError
from .warehouse_dispatch_repo import WarehouseDispatchRepository


STOCK_ITEM_STATUS_IN_STOCK = "in_stock"
STOCK_ITEM_STATUS_RESERVED = "reserved"
STOCK_ITEM_STATUS_SHIPPED = "shipped"
STOCK_ITEM_STATUS_COMPLETED = "completed"

DISPATCH_REQUEST_STATUS_SUBMITTED = "submitted"
DISPATCH_REQUEST_STATUS_REVIEWING = "reviewing"
DISPATCH_REQUEST_STATUS_PACKED = "packed"
DISPATCH_REQUEST_STATUS_DOMESTIC_FEE_PENDING = "domestic_fee_pending"
DISPATCH_REQUEST_STATUS_DOMESTIC_FEE_CONFIRMED = "domestic_fee_confirmed"
DISPATCH_REQUEST_STATUS_SHIPPED = "shipped"
DISPATCH_REQUEST_STATUS_COMPLETED = "completed"
DISPATCH_REQUEST_STATUS_CANCELLED = "cancelled"

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
    # 深拷贝用于审计快照，避免后续更新污染 before/after。
    return copy.deepcopy(value)


def _payload_get(payload: dict[str, Any], *keys: str) -> tuple[bool, Any]:
    # 兼容 camelCase 和 snake_case 入参。
    for key in keys:
        if key in payload:
            return True, payload[key]
    return False, None


def _normalize_required_text(value: Any, field_name: str, min_length: int = 1) -> str:
    # 校验必填文本字段。
    normalized = value.strip() if isinstance(value, str) else ""
    if len(normalized) < min_length:
        raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
    return normalized


def _normalize_optional_text(value: Any, field_name: str) -> str | None:
    # 校验可选文本字段，空字符串统一视为 None。
    if value is None:
        return None
    if not isinstance(value, str):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    normalized = value.strip()
    return normalized or None


def _normalize_positive_int(value: Any, field_name: str) -> int:
    # 校验正整数数量。
    if isinstance(value, bool) or not isinstance(value, int):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    if value <= 0:
        raise AppError(400, f"{field_name}必须大于 0", "VALIDATION_FAILED")
    return value


def _normalize_page_int(value: Any, field_name: str, default_value: int) -> int:
    # 校验分页页码和页大小。
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
    # 校验 API 层传入的人民币元字符串，数据库层再转换为分。
    if isinstance(value, bool) or value in {None, ""}:
        raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED") from exc

    quantized = amount.quantize(Decimal("0.00"))
    if amount != quantized:
        raise AppError(400, f"{field_name}最多保留两位小数", "VALIDATION_FAILED")
    if amount < 0:
        raise AppError(400, f"{field_name}不能小于 0", "VALIDATION_FAILED")
    if not allow_zero and amount == Decimal("0.00"):
        raise AppError(400, f"{field_name}必须大于 0", "VALIDATION_FAILED")
    return f"{quantized:.2f}"


def _normalize_datetime_text(value: Any, field_name: str) -> str:
    # 校验 ISO 时间文本并规范成 isoformat 字符串。
    normalized = _normalize_required_text(value, field_name)
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).isoformat()
    except ValueError as exc:
        raise AppError(400, f"{field_name}不是合法时间", "VALIDATION_FAILED") from exc


def _now_iso() -> str:
    # 生成 UTC ISO 时间，供需要由业务层写入的时间字段使用。
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class WarehouseDispatchModule:
    def __init__(
        self,
        config: Config,
        *,
        repository: WarehouseDispatchRepository | None = None,
        audit_service: Any | None = None,
        has_permission_by_user_id: Callable[[str, str], bool],
        get_user_snapshot_by_id: Callable[[str], dict[str, Any] | None],
        require_group_buy_record: Callable[[str], dict[str, Any]],
        build_group_buy_record_summary: Callable[[dict[str, Any]], dict[str, Any]],
        mark_stocked_in_connection: Callable[..., dict[str, Any]] | None = None,
        mark_dispatch_requested_in_connection: Callable[..., dict[str, Any]] | None = None,
        mark_dispatched_in_connection: Callable[..., dict[str, Any]] | None = None,
        mark_completed_in_connection: Callable[..., dict[str, Any]] | None = None,
        link_charge_in_connection: Callable[..., tuple[dict[str, Any], dict[str, Any]]] | None = None,
        create_charge: Callable[..., dict[str, Any]] | None = None,
    ):
        # 装配数据库仓储和跨模块依赖，仓库/排发自身不再持有 JSON state。
        self.config = config
        self.repo = repository or WarehouseDispatchRepository(config)
        self.audit_service = audit_service
        self.has_permission_by_user_id = has_permission_by_user_id
        self.get_user_snapshot_by_id = get_user_snapshot_by_id
        self.require_group_buy_record = require_group_buy_record
        self.build_group_buy_record_summary = build_group_buy_record_summary
        self.mark_stocked_in_connection = mark_stocked_in_connection
        self.mark_dispatch_requested_in_connection = mark_dispatch_requested_in_connection
        self.mark_dispatched_in_connection = mark_dispatched_in_connection
        self.mark_completed_in_connection = mark_completed_in_connection
        self.link_charge_in_connection = link_charge_in_connection
        self.create_charge = create_charge

    def require_stock_item(self, stock_item_id: str) -> dict[str, Any]:
        # 对外读取单条库存记录。
        with connect(self.config) as conn:
            stock_item = self.repo.get_stock_item_by_id(conn, stock_item_id)
            conn.rollback()
        if stock_item is None:
            raise AppError(404, "库存记录不存在", "NOT_FOUND")
        return stock_item

    def require_dispatch_request(self, dispatch_request_id: str) -> dict[str, Any]:
        # 对外读取单条排发申请。
        with connect(self.config) as conn:
            dispatch_request = self.repo.get_dispatch_request_by_id(conn, dispatch_request_id)
            conn.rollback()
        if dispatch_request is None:
            raise AppError(404, "排发申请不存在", "NOT_FOUND")
        return dispatch_request

    def list_dispatch_items(self, dispatch_request_id: str) -> list[dict[str, Any]]:
        # 对外列出排发申请明细。
        with connect(self.config) as conn:
            items = self.repo.list_dispatch_items(conn, dispatch_request_id)
            conn.rollback()
        return items

    def list_request_stock_items(self, dispatch_request_id: str) -> list[dict[str, Any]]:
        # 对外列出排发申请关联的库存记录。
        with connect(self.config) as conn:
            items = self.repo.list_request_stock_items(conn, dispatch_request_id)
            conn.rollback()
        return items

    def build_dispatch_request_snapshot(
        self,
        dispatch_request: dict[str, Any],
        *,
        conn=None,
    ) -> dict[str, Any]:
        # 构建排发申请审计快照，明细从 dispatch_items 推导。
        if conn is not None:
            items = self.repo.list_dispatch_items(conn, dispatch_request["id"])
        else:
            items = self.list_dispatch_items(dispatch_request["id"])
        return {**clone(dispatch_request), "items": items}

    def list_dispatchable_items(self, payload: dict[str, Any], *, actor_user_id: str) -> dict[str, Any]:
        # 查询当前成员可创建排发申请的库存列表。
        has_member_user_id, raw_member_user_id = _payload_get(payload, "memberUserId", "member_user_id")
        member_user_id = _normalize_required_text(
            raw_member_user_id if has_member_user_id else actor_user_id,
            "memberUserId",
        )
        _, raw_warehouse_user_id = _payload_get(payload, "warehouseUserId", "warehouse_user_id")
        warehouse_user_id = _normalize_optional_text(raw_warehouse_user_id, "warehouseUserId")
        page = _normalize_page_int(payload.get("page"), "page", 1)
        page_size = min(
            _normalize_page_int(
                payload.get("pageSize") if "pageSize" in payload else payload.get("page_size"),
                "pageSize",
                20,
            ),
            100,
        )

        if actor_user_id != member_user_id:
            if warehouse_user_id is None:
                raise AppError(400, "查看他人的可排发商品时必须指定 warehouseUserId", "VALIDATION_FAILED")
            self._assert_can_manage_warehouse(actor_user_id, warehouse_user_id)

        with connect(self.config) as conn:
            candidates = self.repo.list_dispatchable_stock_items(
                conn,
                member_user_id=member_user_id,
                warehouse_user_id=warehouse_user_id,
            )
            conn.rollback()

        items: list[dict[str, Any]] = []
        for stock_item in candidates:
            record = self.require_group_buy_record(stock_item["groupBuyRecordId"])
            record_summary = self.build_group_buy_record_summary(record)
            if not record_summary["isDispatchable"]:
                continue
            items.append(
                {
                    "stockItemId": stock_item["id"],
                    "groupBuyRecordId": stock_item["groupBuyRecordId"],
                    "groupBuyId": record_summary["groupBuyId"],
                    "groupBuyItemId": record_summary["groupBuyItemId"],
                    "memberUserId": record_summary["memberUserId"],
                    "warehouseUserId": stock_item["warehouseUserId"],
                    "quantity": stock_item["quantity"],
                    "status": record_summary["status"],
                    "displayStatus": record_summary["displayStatus"],
                    "isDispatchable": record_summary["isDispatchable"],
                    "stockedAt": stock_item["stockedAt"],
                    "updatedAt": stock_item["updatedAt"],
                }
            )

        start = (page - 1) * page_size
        end = start + page_size
        return {
            "items": items[start:end],
            "total": len(items),
            "page": page,
            "pageSize": page_size,
        }

    def stock_in_records(self, payload: dict[str, Any], *, actor_user_id: str) -> dict[str, Any]:
        # 将指定拼单记录入库到 stock_items，并触发拼单记录状态重算。
        warehouse_user_id = _normalize_required_text(
            payload.get("warehouseUserId")
            if "warehouseUserId" in payload
            else payload.get("warehouse_user_id"),
            "warehouseUserId",
        )
        group_buy_record_ids = self._normalize_record_id_list(
            payload.get("groupBuyRecordIds")
            if "groupBuyRecordIds" in payload
            else payload.get("group_buy_record_ids")
        )
        stocked_at = _normalize_datetime_text(
            payload.get("stockedAt") if "stockedAt" in payload else payload.get("stocked_at"),
            "stockedAt",
        )
        note = _normalize_optional_text(payload.get("note"), "note")

        self._require_user(warehouse_user_id, "warehouseUserId")
        self._assert_can_manage_warehouse(actor_user_id, warehouse_user_id)

        with connect(self.config) as conn:
            result = self._stock_in_records_in_connection(
                conn,
                warehouse_user_id=warehouse_user_id,
                group_buy_record_ids=group_buy_record_ids,
                stocked_at=stocked_at,
                note=note,
                actor_user_id=actor_user_id,
                reason=note or "国内囤货入库",
            )
            conn.commit()
        return result

    def stock_in_international_batch(
        self,
        batch_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        # 将已到国内的国际批次整体入库，并更新批次状态为 stocked。
        stocked_at = _normalize_datetime_text(
            payload.get("stockedAt") if "stockedAt" in payload else payload.get("stocked_at"),
            "stockedAt",
        )
        note = _normalize_optional_text(payload.get("note"), "note")
        reason = note or "国际批次转国内入库"

        with connect(self.config) as conn:
            batch = self.repo.get_international_batch_for_update(conn, batch_id)
            if batch is None:
                raise AppError(404, "国际批次不存在", "NOT_FOUND")
            if batch["status"] == INTERNATIONAL_BATCH_STATUS_STOCKED:
                raise AppError(400, "国际批次已经完成入库", "DUPLICATED_OPERATION")
            if batch["status"] != INTERNATIONAL_BATCH_STATUS_ARRIVED_DOMESTIC:
                raise AppError(400, "只有已到国内的批次才能入库", "INVALID_STATUS")

            warehouse_user_id = _normalize_required_text(batch.get("warehouseUserId"), "warehouseUserId")
            self._require_user(warehouse_user_id, "warehouseUserId")
            self._assert_can_manage_warehouse(actor_user_id, warehouse_user_id)

            record_ids = self.repo.list_international_batch_record_ids(conn, batch_id)
            if not record_ids:
                raise AppError(400, "空批次不能入库", "VALIDATION_FAILED")

            before = {**clone(batch), "groupBuyRecordIds": clone(record_ids)}
            result = self._stock_in_records_in_connection(
                conn,
                warehouse_user_id=warehouse_user_id,
                group_buy_record_ids=record_ids,
                stocked_at=stocked_at,
                note=note,
                actor_user_id=actor_user_id,
                reason=reason,
            )
            after_batch = self.repo.mark_international_batch_stocked(
                conn,
                batch_id,
                stocked_at=stocked_at,
                note=note,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="international_batch.stock_in",
                object_type="international_batch",
                object_id=batch_id,
                before=before,
                after={
                    **after_batch,
                    "groupBuyRecordIds": clone(record_ids),
                    "stockItemIds": clone(result["stockItemIds"]),
                },
                reason=reason,
            )
            conn.commit()

        return {"batchId": batch_id, "status": after_batch["status"], "stockItemIds": result["stockItemIds"]}

    def create_dispatch_request(self, payload: dict[str, Any], *, actor_user_id: str) -> dict[str, Any]:
        # 创建排发申请，写主表和明细，并将所选库存标记为 reserved。
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
        requested_items = self._normalize_dispatch_request_items(payload.get("items"))

        with connect(self.config) as conn:
            selected_stock_items: list[dict[str, Any]] = []
            selected_records: list[dict[str, Any]] = []
            selected_record_ids: list[str] = []
            normalized_items: list[dict[str, Any]] = []

            for item in requested_items:
                stock_item = self.repo.get_stock_item_by_id(conn, item["stockItemId"], lock=True)
                if stock_item is None:
                    raise AppError(404, "库存记录不存在", "NOT_FOUND")
                if stock_item["warehouseUserId"] != warehouse_user_id:
                    raise AppError(400, "排发申请不能混合多个囤货人", "VALIDATION_FAILED")
                if stock_item["status"] != STOCK_ITEM_STATUS_IN_STOCK:
                    raise AppError(400, "库存已经被其他排发申请占用", "DUPLICATED_OPERATION")

                record = self.repo.get_group_buy_record_by_id(conn, stock_item["groupBuyRecordId"], lock=True)
                if record is None:
                    raise AppError(404, "拼单记录不存在", "NOT_FOUND")
                if record["memberUserId"] != requester_user_id:
                    raise AppError(403, "只能申请自己的可排发商品", "FORBIDDEN")
                if item.get("groupBuyRecordId") is not None and item["groupBuyRecordId"] != record["id"]:
                    raise AppError(400, "库存与拼单记录不匹配", "VALIDATION_FAILED")

                quantity = item.get("quantity") or stock_item["quantity"]
                if quantity != stock_item["quantity"]:
                    raise AppError(400, "当前版本暂不支持部分数量排发，请按整条库存申请", "VALIDATION_FAILED")

                record_summary = self.build_group_buy_record_summary(record)
                if not record_summary["isDispatchable"]:
                    raise AppError(400, "存在不可排发记录，不能创建排发申请", "NOT_DISPATCHABLE")

                selected_stock_items.append(stock_item)
                selected_records.append(record)
                selected_record_ids.append(record["id"])
                normalized_items.append(
                    {
                        "stockItemId": stock_item["id"],
                        "groupBuyRecordId": record["id"],
                        "quantity": quantity,
                    }
                )

            submitted_at = _now_iso()
            dispatch_request = self.repo.create_dispatch_request(
                conn,
                requester_user_id=requester_user_id,
                warehouse_user_id=warehouse_user_id,
                status=DISPATCH_REQUEST_STATUS_SUBMITTED,
                receiver_name=receiver_name,
                receiver_phone=receiver_phone,
                receiver_address=receiver_address,
                submitted_at=submitted_at,
                note=note,
            )

            created_item_ids: list[str] = []
            for stock_item, item_payload in zip(selected_stock_items, normalized_items, strict=False):
                before_stock_item = clone(stock_item)
                dispatch_item = self.repo.create_dispatch_item(
                    conn,
                    dispatch_request_id=dispatch_request["id"],
                    stock_item_id=item_payload["stockItemId"],
                    group_buy_record_id=item_payload["groupBuyRecordId"],
                    quantity=item_payload["quantity"],
                )
                created_item_ids.append(dispatch_item["id"])
                after_stock_item = self.repo.mark_stock_item_reserved(conn, stock_item["id"])
                self._audit(
                    conn,
                    actor_user_id=actor_user_id,
                    action="stock_item.reserve_for_dispatch",
                    object_type="stock_item",
                    object_id=stock_item["id"],
                    before=before_stock_item,
                    after=after_stock_item,
                    reason=note or "创建排发申请",
                )

            self._mark_dispatch_requested(
                conn,
                selected_record_ids,
                dispatch_request_id=dispatch_request["id"],
                actor_user_id=actor_user_id,
                reason=note or "创建排发申请",
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="dispatch_request.create",
                object_type="dispatch_request",
                object_id=dispatch_request["id"],
                before=None,
                after={
                    **self.build_dispatch_request_snapshot(dispatch_request, conn=conn),
                    "dispatchItemIds": created_item_ids,
                },
                reason=note or "成员创建排发申请",
            )
            conn.commit()

        return {"dispatchRequestId": dispatch_request["id"], "status": dispatch_request["status"]}

    def mark_dispatch_packed(
        self,
        dispatch_request_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        # 仓库将排发申请标记为已打包。
        packed_at = _normalize_datetime_text(
            payload.get("packedAt") if "packedAt" in payload else payload.get("packed_at"),
            "packedAt",
        )
        note = _normalize_optional_text(payload.get("note"), "note")

        with connect(self.config) as conn:
            dispatch_request = self._require_dispatch_request_in_connection(conn, dispatch_request_id, lock=True)
            self._assert_can_manage_warehouse(actor_user_id, dispatch_request["warehouseUserId"])
            if dispatch_request["status"] in {
                DISPATCH_REQUEST_STATUS_SHIPPED,
                DISPATCH_REQUEST_STATUS_COMPLETED,
                DISPATCH_REQUEST_STATUS_CANCELLED,
            }:
                raise AppError(400, "当前排发申请状态不能再打包", "INVALID_STATUS")

            before = self.build_dispatch_request_snapshot(dispatch_request, conn=conn)
            after = self.repo.mark_dispatch_packed(
                conn,
                dispatch_request_id,
                packed_at=packed_at,
                note=note,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="dispatch_request.mark_packed",
                object_type="dispatch_request",
                object_id=dispatch_request_id,
                before=before,
                after=self.build_dispatch_request_snapshot(after, conn=conn),
                reason=note or "标记已打包",
            )
            conn.commit()

        return {"dispatchRequestId": dispatch_request_id, "status": after["status"]}

    def record_domestic_fee(
        self,
        dispatch_request_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        # 录入国内运费，预付且金额大于 0 时创建费用单并关联拼单记录。
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

        with connect(self.config) as conn:
            dispatch_request = self._require_dispatch_request_in_connection(conn, dispatch_request_id, lock=True)
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

            before = self.build_dispatch_request_snapshot(dispatch_request, conn=conn)
            dispatch_items = self.repo.list_dispatch_items(conn, dispatch_request_id)
            charge_id = None
            amount = Decimal(shipping_fee_cny)

            if fee_mode == DOMESTIC_FEE_MODE_PREPAID and amount > Decimal("0.00"):
                charge = self._create_charge(
                    conn,
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
                            "stockItemIds": [item["stockItemId"] for item in dispatch_items],
                        },
                        "note": note or "国内运费",
                    },
                )
                charge_id = charge.get("chargeId")
                for dispatch_item in dispatch_items:
                    record_before, record_after = self._link_charge(
                        conn,
                        group_buy_record_id=dispatch_item["groupBuyRecordId"],
                        charge_type="domestic_shipping",
                        charge_id=charge_id,
                        actor_user_id=actor_user_id,
                        reason=note or "关联国内运费",
                    )
                    self._audit(
                        conn,
                        actor_user_id=actor_user_id,
                        action="record.link_charge",
                        object_type="group_buy_record",
                        object_id=dispatch_item["groupBuyRecordId"],
                        before=record_before,
                        after=record_after,
                        reason=note or "关联国内运费",
                    )

            confirmed_at = None
            if fee_mode == DOMESTIC_FEE_MODE_PREPAID and charge_id is not None:
                status = DISPATCH_REQUEST_STATUS_DOMESTIC_FEE_PENDING
            elif fee_mode == DOMESTIC_FEE_MODE_COD:
                status = DISPATCH_REQUEST_STATUS_PACKED
            else:
                status = DISPATCH_REQUEST_STATUS_DOMESTIC_FEE_CONFIRMED
                confirmed_at = _now_iso()

            after = self.repo.record_domestic_fee(
                conn,
                dispatch_request_id,
                shipping_fee_cny=shipping_fee_cny,
                fee_mode=fee_mode,
                payment_channel_id=payment_channel_id,
                domestic_charge_id=charge_id,
                status=status,
                confirmed_at=confirmed_at,
                note=note,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="dispatch_request.record_domestic_fee",
                object_type="dispatch_request",
                object_id=dispatch_request_id,
                before=before,
                after=self.build_dispatch_request_snapshot(after, conn=conn),
                reason=note or "录入国内运费",
            )
            conn.commit()

        return {"dispatchRequestId": dispatch_request_id, "chargeId": charge_id}

    def record_domestic_shipment(
        self,
        dispatch_request_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        # 录入国内快递，推进排发申请和库存为 shipped。
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

        with connect(self.config) as conn:
            dispatch_request = self._require_dispatch_request_in_connection(conn, dispatch_request_id, lock=True)
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
            if (
                dispatch_request["feeMode"] == DOMESTIC_FEE_MODE_PREPAID
                and dispatch_request["status"] != DISPATCH_REQUEST_STATUS_DOMESTIC_FEE_CONFIRMED
            ):
                raise AppError(400, "预付运费尚未确认，不能直接发货", "INVALID_STATUS")

            before = self.build_dispatch_request_snapshot(dispatch_request, conn=conn)
            shipment = self.repo.create_domestic_shipment(
                conn,
                dispatch_request_id=dispatch_request_id,
                carrier=carrier,
                tracking_no=tracking_no,
                shipping_fee_cny=dispatch_request.get("shippingFeeCny"),
                fee_mode=dispatch_request["feeMode"],
                shipped_at=shipped_at,
                note=note,
            )
            after_request = self.repo.mark_dispatch_shipped(
                conn,
                dispatch_request_id,
                domestic_shipment_id=shipment["id"],
                shipped_at=shipped_at,
                note=note,
            )

            group_buy_record_ids: list[str] = []
            for stock_item in self.repo.list_request_stock_items(conn, dispatch_request_id):
                before_stock_item = self._require_stock_item_in_connection(conn, stock_item["id"], lock=True)
                after_stock_item = self.repo.mark_stock_item_shipped(conn, stock_item["id"])
                group_buy_record_ids.append(stock_item["groupBuyRecordId"])
                self._audit(
                    conn,
                    actor_user_id=actor_user_id,
                    action="stock_item.mark_shipped",
                    object_type="stock_item",
                    object_id=stock_item["id"],
                    before=before_stock_item,
                    after=after_stock_item,
                    reason=note or "录入国内快递",
                )

            self._mark_dispatched(
                conn,
                group_buy_record_ids,
                actor_user_id=actor_user_id,
                reason=note or "录入国内快递",
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="dispatch_request.record_domestic_shipment",
                object_type="dispatch_request",
                object_id=dispatch_request_id,
                before=before,
                after={
                    **self.build_dispatch_request_snapshot(after_request, conn=conn),
                    "domesticShipment": shipment,
                },
                reason=note or "录入国内快递",
            )
            conn.commit()

        return {
            "domesticShipmentId": shipment["id"],
            "dispatchRequestId": dispatch_request_id,
            "status": after_request["status"],
        }

    def complete_dispatch_request(
        self,
        dispatch_request_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        # 完成已发货的排发申请，推进库存和拼单记录为完成。
        completed_at = _normalize_datetime_text(
            payload.get("completedAt") if "completedAt" in payload else payload.get("completed_at"),
            "completedAt",
        )
        note = _normalize_optional_text(payload.get("note"), "note")

        with connect(self.config) as conn:
            dispatch_request = self._require_dispatch_request_in_connection(conn, dispatch_request_id, lock=True)
            self._assert_can_complete_dispatch(actor_user_id, dispatch_request)
            if dispatch_request["status"] == DISPATCH_REQUEST_STATUS_COMPLETED:
                raise AppError(400, "排发申请已经完成", "DUPLICATED_OPERATION")
            if dispatch_request["status"] != DISPATCH_REQUEST_STATUS_SHIPPED:
                raise AppError(400, "只有已发货的排发申请才能完结", "INVALID_STATUS")

            before = self.build_dispatch_request_snapshot(dispatch_request, conn=conn)
            after_request = self.repo.complete_dispatch_request(
                conn,
                dispatch_request_id,
                completed_at=completed_at,
                note=note,
            )

            group_buy_record_ids: list[str] = []
            for stock_item in self.repo.list_request_stock_items(conn, dispatch_request_id):
                before_stock_item = self._require_stock_item_in_connection(conn, stock_item["id"], lock=True)
                after_stock_item = self.repo.mark_stock_item_completed(conn, stock_item["id"])
                group_buy_record_ids.append(stock_item["groupBuyRecordId"])
                self._audit(
                    conn,
                    actor_user_id=actor_user_id,
                    action="stock_item.complete_dispatch",
                    object_type="stock_item",
                    object_id=stock_item["id"],
                    before=before_stock_item,
                    after=after_stock_item,
                    reason=note or "排发完成",
                )

            self._mark_completed(
                conn,
                group_buy_record_ids,
                actor_user_id=actor_user_id,
                reason=note or "排发完成",
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="dispatch_request.complete",
                object_type="dispatch_request",
                object_id=dispatch_request_id,
                before=before,
                after=self.build_dispatch_request_snapshot(after_request, conn=conn),
                reason=note or "排发已完成",
            )
            conn.commit()

        return {"dispatchRequestId": dispatch_request_id, "status": after_request["status"]}

    def confirm_charge(
        self,
        charge_id: str,
        *,
        proof_id: str | None,
        actor_user_id: str | None,
    ) -> dict[str, Any]:
        # 费用模块确认付款后回调，独立事务版本。
        with connect(self.config) as conn:
            result = self.confirm_charge_in_connection(
                conn,
                charge_id,
                proof_id=proof_id,
                actor_user_id=actor_user_id,
            )
            conn.commit()
        return result

    def confirm_charge_in_connection(
        self,
        conn,
        charge_id: str,
        *,
        proof_id: str | None,
        actor_user_id: str | None,
    ) -> dict[str, Any]:
        # 费用模块确认付款后回调，同事务版本，避免引用未提交的付款凭证。
        dispatch_request = self.repo.get_dispatch_request_by_domestic_charge_id(conn, charge_id, lock=True)
        if dispatch_request is None:
            return {"updatedCount": 0}

        before = self.build_dispatch_request_snapshot(dispatch_request, conn=conn)
        after = self.repo.confirm_domestic_fee(
            conn,
            dispatch_request["id"],
            proof_id=proof_id,
        )
        self._audit(
            conn,
            actor_user_id=actor_user_id,
            action="dispatch_request.confirm_domestic_fee",
            object_type="dispatch_request",
            object_id=dispatch_request["id"],
            before=before,
            after=self.build_dispatch_request_snapshot(after, conn=conn),
            reason="国内运费付款已确认",
        )
        return {"updatedCount": 1, "dispatchRequestId": dispatch_request["id"], "status": after["status"]}

    def _stock_in_records_in_connection(
        self,
        conn,
        *,
        warehouse_user_id: str,
        group_buy_record_ids: list[str],
        stocked_at: str,
        note: str | None,
        actor_user_id: str,
        reason: str,
    ) -> dict[str, Any]:
        # 在调用方事务内完成多条拼单记录入库。
        stock_item_ids: list[str] = []
        for record_id in group_buy_record_ids:
            record = self.repo.get_group_buy_record_by_id(conn, record_id, lock=True)
            if record is None:
                raise AppError(404, "拼单记录不存在", "NOT_FOUND")
            before_stock_item, after_stock_item = self.repo.create_or_refresh_stock_item(
                conn,
                warehouse_user_id=warehouse_user_id,
                group_buy_record_id=record_id,
                quantity=record["quantity"],
                stocked_at=stocked_at,
            )
            stock_item_ids.append(after_stock_item["id"])
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="stock_item.stock_in",
                object_type="stock_item",
                object_id=after_stock_item["id"],
                before=before_stock_item,
                after=after_stock_item,
                reason=reason,
            )

        self._mark_stocked(
            conn,
            group_buy_record_ids,
            actor_user_id=actor_user_id,
            reason=reason,
        )
        return {"stockItemIds": stock_item_ids}

    def _normalize_record_id_list(self, value: Any) -> list[str]:
        # 校验并去重拼单记录 ID 列表。
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

    def _normalize_dispatch_request_items(self, value: Any) -> list[dict[str, Any]]:
        # 校验排发申请明细，数量缺省时后续按整条库存处理。
        if not isinstance(value, list) or not value:
            raise AppError(400, "items格式不正确", "VALIDATION_FAILED")

        result: list[dict[str, Any]] = []
        seen_stock_item_ids: set[str] = set()
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise AppError(400, f"items[{index}]格式不正确", "VALIDATION_FAILED")
            stock_item_id = _normalize_required_text(
                item.get("stockItemId") if "stockItemId" in item else item.get("stock_item_id"),
                f"items[{index}].stockItemId",
            )
            if stock_item_id in seen_stock_item_ids:
                raise AppError(400, "同一库存不能重复加入排发申请", "DUPLICATED_OPERATION")
            seen_stock_item_ids.add(stock_item_id)

            group_buy_record_id = None
            if "groupBuyRecordId" in item or "group_buy_record_id" in item:
                group_buy_record_id = _normalize_required_text(
                    item.get("groupBuyRecordId")
                    if "groupBuyRecordId" in item
                    else item.get("group_buy_record_id"),
                    f"items[{index}].groupBuyRecordId",
                )

            quantity = None
            if "quantity" in item:
                quantity = _normalize_positive_int(item.get("quantity"), f"items[{index}].quantity")
            result.append(
                {
                    "stockItemId": stock_item_id,
                    "groupBuyRecordId": group_buy_record_id,
                    "quantity": quantity,
                }
            )
        return result

    def _require_stock_item_in_connection(self, conn, stock_item_id: str, *, lock: bool = False) -> dict[str, Any]:
        # 在事务内读取库存记录。
        stock_item = self.repo.get_stock_item_by_id(conn, stock_item_id, lock=lock)
        if stock_item is None:
            raise AppError(404, "库存记录不存在", "NOT_FOUND")
        return stock_item

    def _require_dispatch_request_in_connection(
        self,
        conn,
        dispatch_request_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any]:
        # 在事务内读取排发申请。
        dispatch_request = self.repo.get_dispatch_request_by_id(conn, dispatch_request_id, lock=lock)
        if dispatch_request is None:
            raise AppError(404, "排发申请不存在", "NOT_FOUND")
        return dispatch_request

    def _require_user(self, user_id: str, field_name: str) -> None:
        # 校验用户存在。
        if self.get_user_snapshot_by_id(user_id) is None:
            raise AppError(404, f"{field_name}对应用户不存在", "NOT_FOUND")

    def _assert_can_manage_warehouse(self, actor_user_id: str, warehouse_user_id: str) -> None:
        # 校验仓库处理权限；非管理员只能处理分配给自己的囤货点。
        actor = self.get_user_snapshot_by_id(actor_user_id)
        if actor is None:
            raise AppError(404, "用户不存在", "NOT_FOUND")
        if not self.has_permission_by_user_id(actor_user_id, "dispatch:process_assigned"):
            raise AppError(403, "当前账号没有处理囤货排发的权限", "FORBIDDEN")
        if "admin" not in actor.get("roles", []) and actor_user_id != warehouse_user_id:
            raise AppError(403, "当前账号只能处理分配给自己的囤货点", "FORBIDDEN")

    def _assert_can_request_dispatch(self, actor_user_id: str, requester_user_id: str) -> None:
        # 校验创建排发申请权限。
        if actor_user_id == requester_user_id:
            if not self.has_permission_by_user_id(actor_user_id, "dispatch:create_self"):
                raise AppError(403, "当前账号没有创建排发申请的权限", "FORBIDDEN")
            return
        if not self.has_permission_by_user_id(actor_user_id, "dispatch:process_assigned"):
            raise AppError(403, "当前账号不能代成员创建排发申请", "FORBIDDEN")

    def _assert_can_complete_dispatch(self, actor_user_id: str, dispatch_request: dict[str, Any]) -> None:
        # 校验完结排发申请权限，成员本人和仓库处理人均可完结。
        if actor_user_id == dispatch_request["requesterUserId"]:
            return
        self._assert_can_manage_warehouse(actor_user_id, dispatch_request["warehouseUserId"])

    def _create_charge(self, conn, payload: dict[str, Any]) -> dict[str, Any]:
        # 在当前事务内调用费用模块创建国内运费费用单。
        if self.create_charge is None:
            raise RuntimeError("Charge creation dependency is required.")
        return self.create_charge(conn, payload)

    def _link_charge(
        self,
        conn,
        *,
        group_buy_record_id: str,
        charge_type: str,
        charge_id: str,
        actor_user_id: str | None,
        reason: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # 在当前事务内将费用单关联回拼单记录。
        if self.link_charge_in_connection is None:
            raise RuntimeError("Group buy record link_charge dependency is required.")
        return self.link_charge_in_connection(
            conn,
            group_buy_record_id=group_buy_record_id,
            charge_type=charge_type,
            charge_id=charge_id,
            actor_user_id=actor_user_id,
            reason=reason,
        )

    def _mark_stocked(
        self,
        conn,
        record_ids: list[str],
        *,
        actor_user_id: str | None,
        reason: str,
    ) -> None:
        # 在当前事务内触发拼单记录入库状态重算。
        if self.mark_stocked_in_connection is None:
            raise RuntimeError("Group buy record mark_stocked dependency is required.")
        self.mark_stocked_in_connection(
            conn,
            record_ids,
            actor_user_id=actor_user_id,
            reason=reason,
        )

    def _mark_dispatch_requested(
        self,
        conn,
        record_ids: list[str],
        *,
        dispatch_request_id: str,
        actor_user_id: str | None,
        reason: str,
    ) -> None:
        # 在当前事务内触发拼单记录已申请排发状态重算。
        if self.mark_dispatch_requested_in_connection is None:
            raise RuntimeError("Group buy record mark_dispatch_requested dependency is required.")
        self.mark_dispatch_requested_in_connection(
            conn,
            record_ids,
            dispatch_request_id=dispatch_request_id,
            actor_user_id=actor_user_id,
            reason=reason,
        )

    def _mark_dispatched(
        self,
        conn,
        record_ids: list[str],
        *,
        actor_user_id: str | None,
        reason: str,
    ) -> None:
        # 在当前事务内触发拼单记录已排发状态重算。
        if self.mark_dispatched_in_connection is None:
            raise RuntimeError("Group buy record mark_dispatched dependency is required.")
        self.mark_dispatched_in_connection(
            conn,
            record_ids,
            actor_user_id=actor_user_id,
            reason=reason,
        )

    def _mark_completed(
        self,
        conn,
        record_ids: list[str],
        *,
        actor_user_id: str | None,
        reason: str,
    ) -> None:
        # 在当前事务内触发拼单记录完成状态重算。
        if self.mark_completed_in_connection is None:
            raise RuntimeError("Group buy record mark_completed dependency is required.")
        self.mark_completed_in_connection(
            conn,
            record_ids,
            actor_user_id=actor_user_id,
            reason=reason,
        )

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
        # 统一写数据库审计日志。
        if self.audit_service is None:
            return
        self.audit_service.log_in_connection(
            conn,
            actor_user_id=actor_user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before=before,
            after=after,
            reason=reason,
        )
