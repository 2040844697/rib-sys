from __future__ import annotations

import copy
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from ..config import Config
from ..db_access import connect
from ..errors import AppError
from ..file_audit import DatabaseAuditService
from .order_logistics_repo import OrderLogisticsRepository


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


def _normalize_required_text(value: Any, field_name: str, min_length: int = 1) -> str:
    # 统一校验必填文本字段。
    normalized = value.strip() if isinstance(value, str) else ""
    if len(normalized) < min_length:
        raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
    return normalized


def _normalize_optional_text(value: Any, field_name: str) -> str | None:
    # 统一校验可选文本字段。
    if value is None:
        return None
    if not isinstance(value, str):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    normalized = value.strip()
    return normalized or None


def _normalize_non_negative_int(value: Any, field_name: str) -> int:
    # 统一校验非负整数。
    if isinstance(value, bool) or not isinstance(value, int):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    if value < 0:
        raise AppError(400, f"{field_name}不能小于 0", "VALIDATION_FAILED")
    return value


def _normalize_bool(value: Any, field_name: str, default_value: bool = False) -> bool:
    # 统一校验布尔字段。
    if value is None:
        return default_value
    if not isinstance(value, bool):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    return value


def _normalize_price_cny(value: Any, field_name: str) -> str:
    # API 金额入参使用字符串，内部全程使用 Decimal，禁止 float。
    if isinstance(value, bool) or value is None or value == "":
        raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED") from exc
    if amount < 0:
        raise AppError(400, f"{field_name}不能小于 0", "VALIDATION_FAILED")
    return f"{amount.quantize(Decimal('0.00'))}"


def _normalize_adjustment_cny(value: Any, field_name: str) -> str:
    # 人工调整可正可负，但仍必须是两位小数金额。
    if isinstance(value, bool) or value is None or value == "":
        raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED") from exc
    return f"{amount.quantize(Decimal('0.00'))}"


def _parse_amount(amount_text: str) -> Decimal:
    # 已规范化金额字符串转 Decimal。
    return Decimal(amount_text)


def _normalize_datetime_text(
    value: Any,
    field_name: str,
    *,
    required: bool,
) -> str | None:
    # 校验 ISO 时间文本，允许 Z 结尾。
    if value is None or value == "":
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
    # 兼容 camelCase 和 snake_case 入参。
    for key in keys:
        if key in payload:
            return True, payload[key]
    return False, None


class OrderLogisticsModule:
    def __init__(
        self,
        config: Config,
        *,
        repository: OrderLogisticsRepository | None = None,
        audit_service: DatabaseAuditService | None = None,
        assert_manage_permission: Callable[[str], None] | None = None,
        get_group_buy_for_write: Callable[[str, str], dict[str, Any]] | None = None,
        get_user_snapshot_by_id: Callable[[str], dict[str, Any] | None] | None = None,
        require_active_file_object: Callable[..., dict[str, Any]] | None = None,
        require_group_buy_record: Callable[[str], dict[str, Any]] | None = None,
        mark_ordered: Callable[..., dict[str, Any]] | None = None,
        mark_ordered_in_connection: Callable[..., dict[str, Any]] | None = None,
        enter_transfer_flow: Callable[..., dict[str, Any]] | None = None,
        enter_transfer_flow_in_connection: Callable[..., dict[str, Any]] | None = None,
        link_charge: Callable[..., dict[str, Any]] | None = None,
        link_charge_in_connection: Callable[..., tuple[dict[str, Any], dict[str, Any]]] | None = None,
        create_charge: Callable[..., dict[str, Any]] | None = None,
        stock_in_batch: Callable[..., dict[str, Any]] | None = None,
    ):
        self.config = config
        self.repo = repository or OrderLogisticsRepository(config)
        self.audit_service = audit_service
        self.assert_manage_permission = assert_manage_permission
        self.get_group_buy_for_write = get_group_buy_for_write
        self.get_user_snapshot_by_id = get_user_snapshot_by_id
        self.require_active_file_object = require_active_file_object
        self.require_group_buy_record = require_group_buy_record
        self.mark_ordered = mark_ordered
        self.mark_ordered_in_connection = mark_ordered_in_connection
        self.enter_transfer_flow = enter_transfer_flow
        self.enter_transfer_flow_in_connection = enter_transfer_flow_in_connection
        self.link_charge = link_charge
        self.link_charge_in_connection = link_charge_in_connection
        self.create_charge = create_charge
        self.stock_in_batch = stock_in_batch

    def require_order_screenshot(self, order_screenshot_id: str) -> dict[str, Any]:
        # 对外读取下单截图。
        with connect(self.config) as conn:
            screenshot = self._require_order_screenshot_in_connection(conn, order_screenshot_id)
            conn.rollback()
        return screenshot

    def require_international_batch(self, batch_id: str) -> dict[str, Any]:
        # 对外读取国际批次。
        with connect(self.config) as conn:
            batch = self._require_international_batch_in_connection(conn, batch_id)
            conn.rollback()
        return batch

    def list_batch_record_links(self, batch_id: str) -> list[dict[str, Any]]:
        # 对外列出批次记录关联。
        with connect(self.config) as conn:
            result = self.repo.list_batch_record_links(conn, batch_id)
            conn.rollback()
        return result

    def list_batch_record_ids(self, batch_id: str) -> list[str]:
        # 对外列出批次下的记录 ID。
        with connect(self.config) as conn:
            result = self.repo.list_batch_record_ids(conn, batch_id)
            conn.rollback()
        return result

    def list_batch_allocations(self, batch_id: str) -> list[dict[str, Any]]:
        # 对外列出批次费用分摊。
        with connect(self.config) as conn:
            result = self.repo.list_batch_allocations(conn, batch_id)
            conn.rollback()
        return result

    def build_batch_snapshot(self, batch: dict[str, Any]) -> dict[str, Any]:
        # 构建审计用批次快照。
        with connect(self.config) as conn:
            result = self._build_batch_snapshot_in_connection(conn, batch)
            conn.rollback()
        return result

    def add_order_screenshot(self, actor_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        # 新增下单截图，并校验 orders bucket 文件对象。
        self._assert_manage_permission(actor_user_id)

        group_buy_id = _normalize_required_text(
            payload.get("groupBuyId") if "groupBuyId" in payload else payload.get("group_buy_id"),
            "拼团",
        )
        self._get_group_buy_for_write(actor_user_id, group_buy_id)

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
        is_ordered = _normalize_bool(
            payload.get("isOrdered") if "isOrdered" in payload else payload.get("is_ordered"),
            "isOrdered",
            default_value=False,
        )
        ordered_at = _normalize_datetime_text(
            payload.get("orderedAt") if "orderedAt" in payload else payload.get("ordered_at"),
            "orderedAt",
            required=False,
        )

        with connect(self.config) as conn:
            if file_object_id:
                file_object = self._require_active_file_object(file_object_id, conn=conn)
                if file_object.get("bucket") != "orders":
                    raise AppError(400, "下单截图只能关联 orders bucket 文件", "VALIDATION_FAILED")
                if file_object.get("url") != screenshot_url:
                    raise AppError(400, "下单截图 URL 与文件对象不一致", "VALIDATION_FAILED")

            screenshot = self.repo.create_order_screenshot(
                conn,
                group_buy_id=group_buy_id,
                uploaded_by=actor_user_id,
                file_object_id=file_object_id,
                screenshot_url=screenshot_url,
                is_ordered=is_ordered,
                ordered_at=ordered_at,
                website=_normalize_optional_text(payload.get("website"), "website"),
                website_order_no=_normalize_optional_text(
                    payload.get("websiteOrderNo")
                    if "websiteOrderNo" in payload
                    else payload.get("website_order_no"),
                    "websiteOrderNo",
                ),
                note=_normalize_optional_text(payload.get("note"), "note"),
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="order_screenshot.create",
                object_type="order_screenshot",
                object_id=screenshot["id"],
                before=None,
                after=screenshot,
                reason="上传下单截图",
            )
            conn.commit()
        return {"orderScreenshotId": screenshot["id"]}

    def mark_records_ordered(self, actor_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        # 标记批量记录已下单，下单事实由截图和审计表达。
        self._assert_manage_permission(actor_user_id)

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
            payload.get("orderedAt") if "orderedAt" in payload else payload.get("ordered_at"),
            "orderedAt",
            required=True,
        )
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)

        with connect(self.config) as conn:
            screenshot = self._require_order_screenshot_in_connection(
                conn,
                order_screenshot_id,
                lock=True,
            )
            before = clone(screenshot)
            records = [self._require_group_buy_record(record_id) for record_id in record_ids]
            group_buy_ids = {record["groupBuyId"] for record in records}
            if group_buy_ids != {screenshot["groupBuyId"]}:
                raise AppError(400, "下单截图只能覆盖同一拼团的拼单记录", "VALIDATION_FAILED")

            screenshot = self.repo.mark_order_screenshot_ordered(
                conn,
                order_screenshot_id,
                ordered_at=ordered_at or "",
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="order_screenshot.mark_records_ordered",
                object_type="order_screenshot",
                object_id=order_screenshot_id,
                before=before,
                after={**clone(screenshot), "groupBuyRecordIds": record_ids},
                reason=reason,
            )
            updated_count = self._mark_ordered_in_connection(
                conn,
                record_ids,
                actor_user_id=actor_user_id,
                reason=reason,
            )
            conn.commit()
        return {"updatedCount": updated_count}

    def create_international_batch(self, actor_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        # 创建国际转运批次。
        self._assert_manage_permission(actor_user_id)

        forwarder_name = _normalize_required_text(
            payload.get("forwarderName")
            if "forwarderName" in payload
            else payload.get("forwarder_name"),
            "forwarderName",
            2,
        )
        batch_no = _normalize_optional_text(
            payload.get("batchNo") if "batchNo" in payload else payload.get("batch_no"),
            "batchNo",
        )
        warehouse_user_id = _normalize_optional_text(
            payload.get("warehouseUserId")
            if "warehouseUserId" in payload
            else payload.get("warehouse_user_id"),
            "warehouseUserId",
        )
        if warehouse_user_id and self._get_user_snapshot_by_id(warehouse_user_id) is None:
            raise AppError(404, "warehouseUserId对应用户不存在", "NOT_FOUND")

        with connect(self.config) as conn:
            batch = self.repo.create_international_batch(
                conn,
                forwarder_name=forwarder_name,
                batch_no=batch_no,
                status=INTERNATIONAL_BATCH_STATUS_DRAFT,
                warehouse_user_id=warehouse_user_id,
                international_tracking_no=_normalize_optional_text(
                    payload.get("internationalTrackingNo")
                    if "internationalTrackingNo" in payload
                    else payload.get("international_tracking_no"),
                    "internationalTrackingNo",
                ),
                note=_normalize_optional_text(payload.get("note"), "note"),
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="international_batch.create",
                object_type="international_batch",
                object_id=batch["id"],
                before=None,
                after=self._build_batch_snapshot_in_connection(conn, batch),
                reason="创建国际批次",
            )
            conn.commit()
        return {"batchId": batch["id"], "status": batch["status"]}

    def add_records_to_batch(
        self,
        actor_user_id: str,
        batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 将拼单记录加入未关闭国际批次。
        self._assert_manage_permission(actor_user_id)

        record_ids = self._normalize_record_id_list(
            payload.get("groupBuyRecordIds")
            if "groupBuyRecordIds" in payload
            else payload.get("group_buy_record_ids")
        )

        with connect(self.config) as conn:
            batch = self._require_international_batch_in_connection(conn, batch_id, lock=True)
            self._assert_batch_mutable(batch)
            before = self._build_batch_snapshot_in_connection(conn, batch)

            existing_ids = set(self.repo.list_batch_record_ids(conn, batch_id))
            to_add: list[str] = []
            for record_id in record_ids:
                record = self._require_group_buy_record(record_id)
                if not record.get("isOrdered"):
                    raise AppError(400, "未标记已下单的记录不能加入国际批次", "INVALID_STATUS")

                open_link = self.repo.find_open_batch_link_by_record_id(conn, record_id)
                if open_link is not None:
                    if open_link["batchId"] == batch_id:
                        raise AppError(400, "拼单记录已在当前国际批次中", "DUPLICATED_OPERATION")
                    raise AppError(400, "拼单记录已在未关闭的国际批次中", "DUPLICATED_OPERATION")
                if record_id not in existing_ids:
                    to_add.append(record_id)

            if not to_add:
                raise AppError(400, "没有可加入的拼单记录", "VALIDATION_FAILED")

            self.repo.add_batch_record_links(conn, batch_id=batch_id, group_buy_record_ids=to_add)
            after = self._build_batch_snapshot_in_connection(conn, batch)
            if batch["status"] in TRANSFER_STARTED_BATCH_STATUSES:
                self._enter_transfer_flow_in_connection(
                    conn,
                    after["recordIds"],
                    actor_user_id=actor_user_id,
                    reason="加入国际批次并进入转运流程",
                )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="international_batch.add_records",
                object_type="international_batch",
                object_id=batch_id,
                before=before,
                after=after,
                reason="加入国际批次记录",
            )
            conn.commit()

        return {
            "batchId": batch_id,
            "recordCount": len(after["recordIds"]),
            "addedCount": len(to_add),
        }

    def update_batch_shipping(
        self,
        actor_user_id: str,
        batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 更新国际物流信息，并校验状态流转。
        self._assert_manage_permission(actor_user_id)

        with connect(self.config) as conn:
            batch = self._require_international_batch_in_connection(conn, batch_id, lock=True)
            self._assert_batch_mutable(batch)
            before = self._build_batch_snapshot_in_connection(conn, batch)

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

            updated = self.repo.update_international_batch_shipping(
                conn,
                batch_id,
                international_tracking_no=next_tracking_no,
                shipped_at=next_shipped_at,
                status=next_status,
                note=next_note,
            )
            after = self._build_batch_snapshot_in_connection(conn, updated)
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="international_batch.update_shipping",
                object_type="international_batch",
                object_id=batch_id,
                before=before,
                after=after,
                reason="更新国际物流信息",
            )
            if updated["status"] in TRANSFER_STARTED_BATCH_STATUSES:
                self._enter_transfer_flow_in_connection(
                    conn,
                    after["recordIds"],
                    actor_user_id=actor_user_id,
                    reason="国际批次物流状态推进",
                )
            conn.commit()
        return {"batchId": batch_id, "status": updated["status"]}

    def record_batch_arrived_domestic(
        self,
        actor_user_id: str,
        batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 记录国际批次到达国内，到货不等于入库。
        self._assert_manage_permission(actor_user_id)

        with connect(self.config) as conn:
            batch = self._require_international_batch_in_connection(conn, batch_id, lock=True)
            self._assert_batch_mutable(batch)
            if batch["status"] in {
                INTERNATIONAL_BATCH_STATUS_ARRIVED_DOMESTIC,
                INTERNATIONAL_BATCH_STATUS_STOCKED,
            }:
                raise AppError(400, "国际批次已经记录到达国内", "DUPLICATED_OPERATION")

            before = self._build_batch_snapshot_in_connection(conn, batch)
            updated = self.repo.record_batch_arrived_domestic(
                conn,
                batch_id,
                arrived_domestic_at=_normalize_datetime_text(
                    payload.get("arrivedDomesticAt")
                    if "arrivedDomesticAt" in payload
                    else payload.get("arrived_domestic_at"),
                    "arrivedDomesticAt",
                    required=True,
                )
                or "",
                status=INTERNATIONAL_BATCH_STATUS_ARRIVED_DOMESTIC,
                note=_normalize_optional_text(payload.get("note"), "note"),
            )
            record_ids = self.repo.list_batch_record_ids(conn, batch_id)
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="international_batch.record_arrived_domestic",
                object_type="international_batch",
                object_id=batch_id,
                before=before,
                after=self._build_batch_snapshot_in_connection(conn, updated),
                reason="记录国际批次到达国内",
            )
            conn.commit()
        return {
            "batchId": batch_id,
            "status": updated["status"],
            "groupBuyRecordIds": record_ids,
        }

    def stock_in_batch_records(
        self,
        actor_user_id: str,
        batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 入库由仓库排发 DB 模块负责，本模块只转调用。
        self._assert_manage_permission(actor_user_id)
        if self.stock_in_batch is None:
            raise RuntimeError("Warehouse stock-in database dependency is required.")
        return self.stock_in_batch(batch_id, payload, actor_user_id=actor_user_id)

    def record_batch_fees(
        self,
        actor_user_id: str,
        batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 事务内录入批次费用、分摊、费用单和记录关联。
        self._assert_manage_permission(actor_user_id)

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
        payee_user_id = _normalize_optional_text(
            payload.get("payeeUserId") if "payeeUserId" in payload else payload.get("payee_user_id"),
            "payeeUserId",
        )
        payment_channel_id = _normalize_optional_text(
            payload.get("paymentChannelId")
            if "paymentChannelId" in payload
            else payload.get("payment_channel_id"),
            "paymentChannelId",
        )
        if payee_user_id and self._get_user_snapshot_by_id(payee_user_id) is None:
            raise AppError(404, "国际费用收款人不存在", "NOT_FOUND")

        with connect(self.config) as conn:
            batch = self._require_international_batch_in_connection(conn, batch_id, lock=True)
            self._assert_batch_mutable(batch)
            if self.repo.list_batch_allocations(conn, batch_id):
                raise AppError(400, "国际批次费用已经录入，暂不支持重复生成", "DUPLICATED_OPERATION")

            batch_record_ids = self.repo.list_batch_record_ids(conn, batch_id)
            if not batch_record_ids:
                raise AppError(400, "空批次不能录入国际费用", "VALIDATION_FAILED")

            batch_records = [self._require_group_buy_record(record_id) for record_id in batch_record_ids]
            batch_member_user_ids = {record["memberUserId"] for record in batch_records}
            for record in batch_records:
                if record.get("internationalChargeId"):
                    raise AppError(400, "批次内已有记录关联国际费用，不能重复生成", "DUPLICATED_OPERATION")

            normalized_allocations = self._normalize_allocation_items(
                allocation_items,
                batch_member_user_ids=batch_member_user_ids,
                global_note=global_note,
            )
            self._assert_allocation_totals(
                normalized_allocations,
                total_weight_gram=total_weight_gram,
                shipping_fee_cny=shipping_fee_cny,
                tax_fee_cny=tax_fee_cny,
                other_fee_cny=other_fee_cny,
            )

            next_status = batch["status"]
            if _parse_amount(tax_fee_cny) > Decimal("0.00") and batch["status"] in {
                INTERNATIONAL_BATCH_STATUS_PREPARING,
                INTERNATIONAL_BATCH_STATUS_SHIPPED,
            }:
                next_status = INTERNATIONAL_BATCH_STATUS_TAXED
            before = self._build_batch_snapshot_in_connection(conn, batch)
            batch = self.repo.update_batch_fee_summary(
                conn,
                batch_id,
                total_weight_gram=total_weight_gram,
                shipping_fee_cny=shipping_fee_cny,
                tax_fee_cny=tax_fee_cny,
                other_fee_cny=other_fee_cny,
                status=next_status,
                note=global_note,
            )

            allocation_ids: list[str] = []
            charge_ids: list[str] = []
            records_by_member: dict[str, list[dict[str, Any]]] = {}
            for record in batch_records:
                records_by_member.setdefault(record["memberUserId"], []).append(record)

            for item in normalized_allocations:
                charge_id = None
                if payee_user_id and _parse_amount(item["totalCny"]) > Decimal("0.00"):
                    charge = self._create_charge(
                        conn,
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
                                "userId": item["userId"],
                            },
                            "note": item["note"] or global_note,
                            "actorUserId": actor_user_id,
                        },
                    )
                    charge_id = charge.get("chargeId")
                    if charge_id:
                        charge_ids.append(charge_id)

                allocation = self.repo.create_fee_allocation(
                    conn,
                    batch_id=batch_id,
                    user_id=item["userId"],
                    weight_gram=item["weightGram"],
                    shipping_fee_cny=item["shippingFeeCny"],
                    tax_fee_cny=item["taxFeeCny"],
                    other_fee_cny=item["otherFeeCny"],
                    adjustment_cny=item["adjustmentCny"],
                    total_cny=item["totalCny"],
                    note=item["note"],
                    charge_id=charge_id,
                )
                allocation_ids.append(allocation["id"])

                if charge_id:
                    for record in records_by_member.get(item["userId"], []):
                        before_record, after_record = self._link_charge_in_connection(
                            conn,
                            group_buy_record_id=record["id"],
                            charge_type="international",
                            charge_id=charge_id,
                            actor_user_id=actor_user_id,
                            reason="关联国际费用",
                        )
                        self._audit(
                            conn,
                            actor_user_id=actor_user_id,
                            action="record.link_charge",
                            object_type="group_buy_record",
                            object_id=record["id"],
                            before=before_record,
                            after=after_record,
                            reason="关联 international 费用",
                        )

            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="international_batch.record_fees",
                object_type="international_batch",
                object_id=batch_id,
                before=before,
                after={
                    **self._build_batch_snapshot_in_connection(conn, batch),
                    "chargeIds": charge_ids,
                },
                reason="录入国际费用分摊",
            )
            conn.commit()
        return {
            "batchId": batch_id,
            "allocationIds": allocation_ids,
            "chargeIds": charge_ids,
        }

    def _require_order_screenshot_in_connection(
        self,
        conn,
        order_screenshot_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any]:
        # 事务内读取下单截图。
        screenshot = self.repo.get_order_screenshot_by_id(conn, order_screenshot_id, lock=lock)
        if screenshot is None:
            raise AppError(404, "下单截图不存在", "NOT_FOUND")
        return screenshot

    def _require_international_batch_in_connection(
        self,
        conn,
        batch_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any]:
        # 事务内读取国际批次。
        batch = self.repo.get_international_batch_by_id(conn, batch_id, lock=lock)
        if batch is None:
            raise AppError(404, "国际批次不存在", "NOT_FOUND")
        return batch

    def _build_batch_snapshot_in_connection(self, conn, batch: dict[str, Any]) -> dict[str, Any]:
        # 在同一事务里构建批次、记录和分摊快照。
        return {
            **clone(batch),
            "recordIds": self.repo.list_batch_record_ids(conn, batch["id"]),
            "allocationIds": [
                item["id"] for item in self.repo.list_batch_allocations(conn, batch["id"])
            ],
        }

    def _normalize_record_id_list(self, value: Any) -> list[str]:
        # 校验批量记录 ID。
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

    def _normalize_allocation_items(
        self,
        allocation_items: list[Any],
        *,
        batch_member_user_ids: set[str],
        global_note: str | None,
    ) -> list[dict[str, Any]]:
        # 校验国际费用分摊成员和单项金额。
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
            if self._get_user_snapshot_by_id(user_id) is None:
                raise AppError(404, "费用分摊成员不存在", "NOT_FOUND")

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
            item_adjustment = _normalize_adjustment_cny(
                item.get("adjustmentCny")
                if "adjustmentCny" in item
                else item.get("adjustment_cny") or "0",
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
                    "weightGram": _normalize_non_negative_int(
                        item.get("weightGram") if "weightGram" in item else item.get("weight_gram"),
                        f"allocationItems[{index}].weightGram",
                    ),
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
        return normalized_allocations

    def _assert_allocation_totals(
        self,
        normalized_allocations: list[dict[str, Any]],
        *,
        total_weight_gram: int,
        shipping_fee_cny: str,
        tax_fee_cny: str,
        other_fee_cny: str,
    ) -> None:
        # 校验批次总费用与成员分摊总费用一致。
        allocation_weight = sum(item["weightGram"] for item in normalized_allocations)
        if total_weight_gram > 0 and allocation_weight > total_weight_gram:
            raise AppError(400, "分摊重量不能大于批次总重量", "VALIDATION_FAILED")

        batch_total = _parse_amount(shipping_fee_cny) + _parse_amount(tax_fee_cny) + _parse_amount(other_fee_cny)
        allocation_total = sum(_parse_amount(item["totalCny"]) for item in normalized_allocations)
        adjustment_total = sum(_parse_amount(item["adjustmentCny"]) for item in normalized_allocations)
        if (batch_total + adjustment_total).quantize(Decimal("0.00")) != allocation_total:
            raise AppError(400, "国际费用分摊总额与批次费用不一致", "VALIDATION_FAILED")

    def _assert_batch_mutable(self, batch: dict[str, Any]) -> None:
        # 关闭批次不允许继续修改。
        if batch["status"] == INTERNATIONAL_BATCH_STATUS_CLOSED:
            raise AppError(400, "已关闭的国际批次不允许继续修改", "INVALID_STATUS")

    def _assert_shipping_status_transition(self, old_status: str, new_status: str) -> None:
        # 校验国际物流状态流转。
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

    def _ensure_transfer_flow_for_batch(
        self,
        batch: dict[str, Any],
        *,
        actor_user_id: str,
        reason: str,
    ) -> None:
        # 批次进入转运阶段后触发记录状态重算。
        if batch["status"] not in TRANSFER_STARTED_BATCH_STATUSES:
            return
        record_ids = self.list_batch_record_ids(batch["id"])
        if not record_ids:
            return
        self._enter_transfer_flow(
            {
                "groupBuyRecordIds": record_ids,
                "reason": reason,
            },
            actor_user_id=actor_user_id,
        )

    def _assert_manage_permission(self, actor_user_id: str) -> None:
        # 校验下单物流维护权限。
        if self.assert_manage_permission is None:
            return
        self.assert_manage_permission(actor_user_id)

    def _get_group_buy_for_write(self, actor_user_id: str, group_buy_id: str) -> dict[str, Any]:
        # 调用团购管理 DB 模块校验拼团可写。
        if self.get_group_buy_for_write is None:
            raise RuntimeError("Group buy write dependency is required.")
        return self.get_group_buy_for_write(actor_user_id, group_buy_id)

    def _get_user_snapshot_by_id(self, user_id: str) -> dict[str, Any] | None:
        # 校验用户存在。
        if self.get_user_snapshot_by_id is None:
            return None
        return self.get_user_snapshot_by_id(user_id)

    def _require_active_file_object(self, file_object_id: str, *, conn) -> dict[str, Any]:
        # 调用 DB 文件服务校验文件对象。
        if self.require_active_file_object is None:
            raise RuntimeError("File object dependency is required.")
        return self.require_active_file_object(file_object_id, conn=conn)

    def _require_group_buy_record(self, group_buy_record_id: str) -> dict[str, Any]:
        # 调用拼单记录 DB 模块读取记录。
        if self.require_group_buy_record is None:
            raise RuntimeError("Group buy record dependency is required.")
        return self.require_group_buy_record(group_buy_record_id)

    def _mark_ordered(self, payload: dict[str, Any], *, actor_user_id: str) -> dict[str, Any]:
        # 调用拼单记录模块重算下单状态。
        if self.mark_ordered is None:
            raise RuntimeError("mark_ordered dependency is required.")
        return self.mark_ordered(payload, actor_user_id=actor_user_id)

    def _mark_ordered_in_connection(
        self,
        conn,
        record_ids: list[str],
        *,
        actor_user_id: str,
        reason: str,
    ) -> int:
        # 在下单截图事务里重算记录状态，避免截图和状态半成功。
        if self.mark_ordered_in_connection is None:
            self._mark_ordered(
                {"groupBuyRecordIds": record_ids, "reason": reason},
                actor_user_id=actor_user_id,
            )
            return len(record_ids)
        return self.mark_ordered_in_connection(
            conn,
            record_ids,
            actor_user_id=actor_user_id,
            reason=reason,
        )["updatedCount"]

    def _enter_transfer_flow(self, payload: dict[str, Any], *, actor_user_id: str) -> dict[str, Any]:
        # 调用拼单记录模块重算转运状态。
        if self.enter_transfer_flow is None:
            raise RuntimeError("enter_transfer_flow dependency is required.")
        return self.enter_transfer_flow(payload, actor_user_id=actor_user_id)

    def _enter_transfer_flow_in_connection(
        self,
        conn,
        record_ids: list[str],
        *,
        actor_user_id: str,
        reason: str,
    ) -> int:
        # 在批次物流事务里重算转运状态。
        if not record_ids:
            return 0
        if self.enter_transfer_flow_in_connection is None:
            self._enter_transfer_flow(
                {"groupBuyRecordIds": record_ids, "reason": reason},
                actor_user_id=actor_user_id,
            )
            return len(record_ids)
        return self.enter_transfer_flow_in_connection(
            conn,
            record_ids,
            actor_user_id=actor_user_id,
            reason=reason,
        )["updatedCount"]

    def _link_charge(self, payload: dict[str, Any], *, actor_user_id: str) -> dict[str, Any]:
        # 调用拼单记录模块关联国际费用。
        if self.link_charge is None:
            raise RuntimeError("link_charge dependency is required.")
        return self.link_charge(payload, actor_user_id=actor_user_id)

    def _link_charge_in_connection(
        self,
        conn,
        *,
        group_buy_record_id: str,
        charge_type: str,
        charge_id: str,
        actor_user_id: str,
        reason: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # 在国际费用事务里关联费用，避免分摊和记录外键半成功。
        if self.link_charge_in_connection is None:
            raise RuntimeError("link_charge_in_connection dependency is required.")
        return self.link_charge_in_connection(
            conn,
            group_buy_record_id=group_buy_record_id,
            charge_type=charge_type,
            charge_id=charge_id,
            actor_user_id=actor_user_id,
            reason=reason,
        )

    def _create_charge(self, conn, payload: dict[str, Any]) -> dict[str, Any]:
        # 调用费用模块在当前事务里创建国际费用。
        if self.create_charge is None:
            raise RuntimeError("Charge creation database dependency is required.")
        return self.create_charge(conn, payload)

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
