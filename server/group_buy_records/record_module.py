from __future__ import annotations

import copy
from typing import Any, Callable

from ..errors import AppError


GROUP_BUY_RECORD_STATUS_ORDERED = "已下单"
GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT = "未肾"
GROUP_BUY_RECORD_STATUS_PENDING_TRANSFER = "未转寄"
GROUP_BUY_RECORD_STATUS_PENDING_STOCK = "未到货"
GROUP_BUY_RECORD_STATUS_PENDING_INTERNATIONAL_PAYMENT = "未补国际"
GROUP_BUY_RECORD_STATUS_DISPATCHABLE = "可排发"
GROUP_BUY_RECORD_STATUS_DISPATCH_REQUESTED = "已申请排发"
GROUP_BUY_RECORD_STATUS_DISPATCHED = "已排发"
GROUP_BUY_RECORD_STATUS_TRANSFERRING = "转单中"
GROUP_BUY_RECORD_STATUS_COMPLETED = "已完结"

CLAIMABLE_GROUP_BUY_STATUSES = {"拼拼拼", "已切"}
GROUP_BUY_TYPES_WITHOUT_INTERNATIONAL = {"国内现货", "群友出物", "补寄"}
GROUP_BUY_TYPES_WITHOUT_STOCKING = {"群友出物"}
GROUP_BUY_RECORD_STATUS_PRIORITY = {
    GROUP_BUY_RECORD_STATUS_TRANSFERRING: 1,
    GROUP_BUY_RECORD_STATUS_COMPLETED: 2,
    GROUP_BUY_RECORD_STATUS_DISPATCHED: 3,
    GROUP_BUY_RECORD_STATUS_DISPATCH_REQUESTED: 4,
    GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT: 5,
    GROUP_BUY_RECORD_STATUS_PENDING_INTERNATIONAL_PAYMENT: 6,
    GROUP_BUY_RECORD_STATUS_PENDING_TRANSFER: 7,
    GROUP_BUY_RECORD_STATUS_PENDING_STOCK: 8,
    GROUP_BUY_RECORD_STATUS_DISPATCHABLE: 9,
    GROUP_BUY_RECORD_STATUS_ORDERED: 10,
}
DEFAULT_RECORD_SOURCE = "member_claim"
ALLOWED_CHARGE_TYPES = {"goods", "international", "domestic_shipping"}
ALLOWED_PAYMENT_TYPES = {"goods", "international"}


def clone(value: Any) -> Any:
    return copy.deepcopy(value)


def ensure_group_buy_record_state(state: dict[str, Any]) -> bool:
    changed = False

    counters = state.setdefault("counters", {})
    records = state.setdefault("groupBuyRecords", [])
    if "groupBuyRecord" not in counters:
        counters["groupBuyRecord"] = len(records)
        changed = True

    for record in records:
        if "memberUserId" not in record and "ownerId" in record:
            record["memberUserId"] = record["ownerId"]
            changed = True
        if "status" not in record and "displayStatus" in record:
            record["status"] = record["displayStatus"]
            changed = True
        if not record.get("status"):
            record["status"] = GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT
            changed = True
        if record.get("statusPriority") != _status_priority(record["status"]):
            record["statusPriority"] = _status_priority(record["status"])
            changed = True

        defaults = {
            "goodsChargeId": None,
            "goodsPaymentRecordId": None,
            "internationalChargeId": None,
            "internationalPaymentRecordId": None,
            "domesticShippingChargeId": None,
            "dispatchRequestId": None,
            "transferId": None,
            "exceptionReason": None,
            "note": None,
            "source": DEFAULT_RECORD_SOURCE,
            "orderedSourceObjectType": None,
            "orderedSourceObjectId": None,
            "orderedReason": None,
            "warehouseUserId": None,
            "stockedAt": None,
            "shipmentId": None,
            "goodsPaidConfirmed": _infer_goods_paid(record),
            "needsInternationalFee": _infer_needs_international_fee(record),
            "internationalPaidConfirmed": _infer_international_paid(record),
            "needsTransfer": _infer_needs_transfer(record),
            "enteredTransferFlow": _infer_entered_transfer_flow(record),
            "needsDomesticStock": _infer_needs_domestic_stock(record),
            "isOrdered": _infer_is_ordered(record),
            "isStocked": _infer_is_stocked(record),
            "isTransferPending": _infer_is_transfer_pending(record),
            "isCompleted": _infer_is_completed(record),
            "isException": bool(record.get("isException", False)),
        }
        for key, value in defaults.items():
            if key not in record:
                record[key] = clone(value)
                changed = True

        if "ownerId" in record:
            record.pop("ownerId", None)
            changed = True
        if "displayStatus" in record:
            record.pop("displayStatus", None)
            changed = True

    return changed


def _status_priority(status: str | None) -> int:
    if not status:
        return GROUP_BUY_RECORD_STATUS_PRIORITY[GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT]
    return GROUP_BUY_RECORD_STATUS_PRIORITY.get(
        status,
        GROUP_BUY_RECORD_STATUS_PRIORITY[GROUP_BUY_RECORD_STATUS_ORDERED],
    )


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


def _payload_get(payload: dict[str, Any], *keys: str) -> tuple[bool, Any]:
    for key in keys:
        if key in payload:
            return True, payload[key]
    return False, None


def _infer_is_ordered(record: dict[str, Any]) -> bool:
    if record.get("orderedSourceObjectId") or record.get("orderedSourceObjectType"):
        return True
    return record.get("status") in {
        GROUP_BUY_RECORD_STATUS_PENDING_INTERNATIONAL_PAYMENT,
        GROUP_BUY_RECORD_STATUS_PENDING_TRANSFER,
        GROUP_BUY_RECORD_STATUS_PENDING_STOCK,
        GROUP_BUY_RECORD_STATUS_DISPATCHABLE,
        GROUP_BUY_RECORD_STATUS_DISPATCH_REQUESTED,
        GROUP_BUY_RECORD_STATUS_DISPATCHED,
        GROUP_BUY_RECORD_STATUS_COMPLETED,
        GROUP_BUY_RECORD_STATUS_ORDERED,
    }


def _infer_goods_paid(record: dict[str, Any]) -> bool:
    if record.get("goodsPaymentRecordId"):
        return True
    return record.get("status") in {
        GROUP_BUY_RECORD_STATUS_PENDING_INTERNATIONAL_PAYMENT,
        GROUP_BUY_RECORD_STATUS_PENDING_TRANSFER,
        GROUP_BUY_RECORD_STATUS_PENDING_STOCK,
        GROUP_BUY_RECORD_STATUS_DISPATCHABLE,
        GROUP_BUY_RECORD_STATUS_DISPATCH_REQUESTED,
        GROUP_BUY_RECORD_STATUS_DISPATCHED,
        GROUP_BUY_RECORD_STATUS_COMPLETED,
    }


def _infer_needs_international_fee(record: dict[str, Any]) -> bool:
    return record.get("status") in {
        GROUP_BUY_RECORD_STATUS_PENDING_INTERNATIONAL_PAYMENT,
        GROUP_BUY_RECORD_STATUS_PENDING_TRANSFER,
        GROUP_BUY_RECORD_STATUS_PENDING_STOCK,
        GROUP_BUY_RECORD_STATUS_DISPATCHABLE,
        GROUP_BUY_RECORD_STATUS_DISPATCH_REQUESTED,
        GROUP_BUY_RECORD_STATUS_DISPATCHED,
        GROUP_BUY_RECORD_STATUS_COMPLETED,
    }


def _infer_international_paid(record: dict[str, Any]) -> bool:
    if record.get("internationalPaymentRecordId"):
        return True
    return record.get("status") in {
        GROUP_BUY_RECORD_STATUS_PENDING_STOCK,
        GROUP_BUY_RECORD_STATUS_DISPATCHABLE,
        GROUP_BUY_RECORD_STATUS_DISPATCH_REQUESTED,
        GROUP_BUY_RECORD_STATUS_DISPATCHED,
        GROUP_BUY_RECORD_STATUS_COMPLETED,
    }


def _infer_needs_transfer(record: dict[str, Any]) -> bool:
    return record.get("status") in {
        GROUP_BUY_RECORD_STATUS_PENDING_TRANSFER,
        GROUP_BUY_RECORD_STATUS_PENDING_STOCK,
        GROUP_BUY_RECORD_STATUS_DISPATCHABLE,
        GROUP_BUY_RECORD_STATUS_DISPATCH_REQUESTED,
        GROUP_BUY_RECORD_STATUS_DISPATCHED,
        GROUP_BUY_RECORD_STATUS_COMPLETED,
    }


def _infer_entered_transfer_flow(record: dict[str, Any]) -> bool:
    return record.get("status") in {
        GROUP_BUY_RECORD_STATUS_PENDING_STOCK,
        GROUP_BUY_RECORD_STATUS_DISPATCHABLE,
        GROUP_BUY_RECORD_STATUS_DISPATCH_REQUESTED,
        GROUP_BUY_RECORD_STATUS_DISPATCHED,
        GROUP_BUY_RECORD_STATUS_COMPLETED,
    }


def _infer_needs_domestic_stock(record: dict[str, Any]) -> bool:
    return record.get("status") in {
        GROUP_BUY_RECORD_STATUS_PENDING_STOCK,
        GROUP_BUY_RECORD_STATUS_DISPATCHABLE,
        GROUP_BUY_RECORD_STATUS_DISPATCH_REQUESTED,
        GROUP_BUY_RECORD_STATUS_DISPATCHED,
        GROUP_BUY_RECORD_STATUS_COMPLETED,
    }


def _infer_is_stocked(record: dict[str, Any]) -> bool:
    return record.get("status") in {
        GROUP_BUY_RECORD_STATUS_DISPATCHABLE,
        GROUP_BUY_RECORD_STATUS_DISPATCH_REQUESTED,
        GROUP_BUY_RECORD_STATUS_DISPATCHED,
        GROUP_BUY_RECORD_STATUS_COMPLETED,
    }


def _infer_is_transfer_pending(record: dict[str, Any]) -> bool:
    return record.get("status") == GROUP_BUY_RECORD_STATUS_TRANSFERRING


def _infer_is_completed(record: dict[str, Any]) -> bool:
    return record.get("status") == GROUP_BUY_RECORD_STATUS_COMPLETED


class GroupBuyRecordsModule:
    def __init__(
        self,
        *,
        state: dict[str, Any],
        next_id: Callable[[str, str], str],
        audit_log: Callable[..., Any],
        now_iso: Callable[[], str],
        has_permission: Callable[[dict[str, Any], str], bool],
        can_view_group_buy: Callable[[dict[str, Any], dict[str, Any]], bool],
    ):
        self.state = state
        self.next_id = next_id
        self.audit_log = audit_log
        self.now_iso = now_iso
        self.has_permission = has_permission
        self.can_view_group_buy = can_view_group_buy

    def require_record(self, group_buy_record_id: str) -> dict[str, Any]:
        record = next(
            (item for item in self.state["groupBuyRecords"] if item["id"] == group_buy_record_id),
            None,
        )
        if record is None:
            raise AppError(404, "拼单记录不存在", "NOT_FOUND")
        return record

    def list_member_records(
        self,
        *,
        group_buy_id: str,
        member_user_id: str,
    ) -> list[dict[str, Any]]:
        records = [
            self.build_record_summary(record)
            for record in self.state["groupBuyRecords"]
            if record["groupBuyId"] == group_buy_id and record["memberUserId"] == member_user_id
        ]
        return sorted(records, key=lambda item: (item["createdAt"], item["id"]))

    def count_member_records_by_status(self, *, member_user_id: str, status: str) -> int:
        return sum(
            1
            for record in self.state["groupBuyRecords"]
            if record["memberUserId"] == member_user_id and record["status"] == status
        )

    def get_claimed_quantity(self, group_buy_item_id: str) -> int:
        return sum(
            record["quantity"]
            for record in self.state["groupBuyRecords"]
            if record["groupBuyItemId"] == group_buy_item_id
        )

    def create_record(self, actor_user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        group_buy_id = _normalize_required_text(
            payload.get("groupBuyId") if "groupBuyId" in payload else payload.get("group_buy_id"),
            "拼单",
        )
        group_buy_item_id = _normalize_required_text(
            payload.get("groupBuyItemId")
            if "groupBuyItemId" in payload
            else payload.get("group_buy_item_id"),
            "拼单商品",
        )
        member_user_id = _normalize_required_text(
            payload.get("memberUserId")
            if "memberUserId" in payload
            else payload.get("member_user_id")
            or actor_user["id"],
            "成员",
        )
        quantity = _normalize_positive_int(payload.get("quantity"), "数量")
        source = _normalize_optional_text(payload.get("source"), "source") or DEFAULT_RECORD_SOURCE

        group_buy = self._require_visible_group_buy(actor_user, group_buy_id)
        if group_buy["status"] not in CLAIMABLE_GROUP_BUY_STATUSES:
            raise AppError(400, "当前拼团状态暂时不能认领", "INVALID_STATUS")

        self._assert_can_create_for_member(actor_user, member_user_id)
        item = self._require_group_buy_item(group_buy_item_id)
        if item["groupBuyId"] != group_buy_id:
            raise AppError(400, "拼单商品不属于当前拼单", "VALIDATION_FAILED")

        available_quantity = item["totalQuantity"] - self.get_claimed_quantity(group_buy_item_id)
        if quantity > available_quantity:
            raise AppError(400, "可认领数量不足", "INSUFFICIENT_STOCK")

        existing_record = next(
            (
                record
                for record in self.state["groupBuyRecords"]
                if record["groupBuyId"] == group_buy_id
                and record["groupBuyItemId"] == group_buy_item_id
                and record["memberUserId"] == member_user_id
            ),
            None,
        )
        if existing_record is not None:
            before = clone(existing_record)
            existing_record["quantity"] += quantity
            existing_record["source"] = source
            self._refresh_record_status(existing_record, group_buy=group_buy)
            existing_record["updatedAt"] = self.now_iso()
            self.audit_log(
                actor_user_id=actor_user["id"],
                action="record.update_quantity",
                object_type="group_buy_record",
                object_id=existing_record["id"],
                before=before,
                after=clone(existing_record),
                reason="成员追加认领" if actor_user["id"] == member_user_id else "维护人代成员追加认领",
            )
            return {
                "groupBuyRecordId": existing_record["id"],
                "recordId": existing_record["id"],
                "status": existing_record["status"],
                "displayStatus": existing_record["status"],
                "quantity": existing_record["quantity"],
            }

        record = {
            "id": self.next_id("groupBuyRecord", "record"),
            "groupBuyId": group_buy_id,
            "groupBuyItemId": group_buy_item_id,
            "memberUserId": member_user_id,
            "status": GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT,
            "quantity": quantity,
            "goodsChargeId": None,
            "goodsPaymentRecordId": None,
            "internationalChargeId": None,
            "internationalPaymentRecordId": None,
            "domesticShippingChargeId": None,
            "dispatchRequestId": None,
            "transferId": None,
            "isException": False,
            "exceptionReason": None,
            "statusPriority": _status_priority(GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT),
            "note": None,
            "source": source,
            # 这些字段暂时由拼单记录模块自己维护，后续接入费用/转运模块时直接复用。
            "goodsPaidConfirmed": False,
            "needsInternationalFee": self._needs_international_fee(group_buy),
            "internationalPaidConfirmed": not self._needs_international_fee(group_buy),
            "needsTransfer": self._needs_transfer(group_buy),
            "enteredTransferFlow": False,
            "needsDomesticStock": self._needs_domestic_stock(group_buy),
            "isOrdered": False,
            "orderedSourceObjectType": None,
            "orderedSourceObjectId": None,
            "orderedReason": None,
            "warehouseUserId": None,
            "stockedAt": None,
            "isStocked": False,
            "shipmentId": None,
            "isTransferPending": False,
            "isCompleted": False,
            "createdAt": self.now_iso(),
            "updatedAt": self.now_iso(),
        }
        self._refresh_record_status(record, group_buy=group_buy)
        self.state["groupBuyRecords"].append(record)

        self.audit_log(
            actor_user_id=actor_user["id"],
            action="record.create",
            object_type="group_buy_record",
            object_id=record["id"],
            before=None,
            after=clone(record),
            reason="成员认领商品" if actor_user["id"] == member_user_id else "维护人代成员建单",
        )
        return {
            "groupBuyRecordId": record["id"],
            "recordId": record["id"],
            "status": record["status"],
            "displayStatus": record["status"],
            "quantity": record["quantity"],
        }

    def update_record_quantity(
        self,
        actor_user: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        group_buy_record_id = _normalize_required_text(
            payload.get("groupBuyRecordId")
            if "groupBuyRecordId" in payload
            else payload.get("group_buy_record_id"),
            "拼单记录",
        )
        new_quantity = _normalize_positive_int(
            payload.get("newQuantity") if "newQuantity" in payload else payload.get("new_quantity"),
            "数量",
        )
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)

        record = self.require_record(group_buy_record_id)
        group_buy = self._require_group_buy(record["groupBuyId"])
        self._assert_can_manage_record(actor_user, record)
        self._assert_record_mutable(actor_user, record)
        if new_quantity == record["quantity"]:
            raise AppError(400, "数量没有变化", "VALIDATION_FAILED")

        item = self._require_group_buy_item(record["groupBuyItemId"])
        quantity_delta = new_quantity - record["quantity"]
        if quantity_delta > 0:
            available_quantity = item["totalQuantity"] - self.get_claimed_quantity(item["id"])
            if quantity_delta > available_quantity:
                raise AppError(400, "可认领数量不足", "INSUFFICIENT_STOCK")

        before = clone(record)
        old_quantity = record["quantity"]
        record["quantity"] = new_quantity
        self._refresh_record_status(record, group_buy=group_buy)
        record["updatedAt"] = self.now_iso()
        self.audit_log(
            actor_user_id=actor_user["id"],
            action="record.update_quantity",
            object_type="group_buy_record",
            object_id=record["id"],
            before=before,
            after=clone(record),
            reason=reason,
        )
        return {
            "groupBuyRecordId": record["id"],
            "oldQuantity": old_quantity,
            "newQuantity": record["quantity"],
        }

    def link_charge(
        self,
        payload: dict[str, Any],
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        group_buy_record_id = _normalize_required_text(
            payload.get("groupBuyRecordId")
            if "groupBuyRecordId" in payload
            else payload.get("group_buy_record_id"),
            "拼单记录",
        )
        charge_type = _normalize_required_text(
            payload.get("chargeType") if "chargeType" in payload else payload.get("charge_type"),
            "费用类型",
        )
        charge_id = _normalize_required_text(
            payload.get("chargeId") if "chargeId" in payload else payload.get("charge_id"),
            "费用",
        )
        if charge_type not in ALLOWED_CHARGE_TYPES:
            raise AppError(400, "费用类型不支持", "VALIDATION_FAILED")

        record = self.require_record(group_buy_record_id)
        before = clone(record)

        if charge_type == "goods":
            record["goodsChargeId"] = charge_id
        elif charge_type == "international":
            record["internationalChargeId"] = charge_id
            record["needsInternationalFee"] = True
            record["internationalPaidConfirmed"] = False
        else:
            record["domesticShippingChargeId"] = charge_id

        self._refresh_record_status(record, group_buy=self._require_group_buy(record["groupBuyId"]))
        record["updatedAt"] = self.now_iso()
        self.audit_log(
            actor_user_id=actor_user_id,
            action="record.link_charge",
            object_type="group_buy_record",
            object_id=record["id"],
            before=before,
            after=clone(record),
            reason=f"关联 {charge_type} 费用",
        )
        return {"groupBuyRecordId": record["id"]}

    def link_payment_proof(
        self,
        payload: dict[str, Any],
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        group_buy_record_id = _normalize_required_text(
            payload.get("groupBuyRecordId")
            if "groupBuyRecordId" in payload
            else payload.get("group_buy_record_id"),
            "拼单记录",
        )
        payment_type = _normalize_required_text(
            payload.get("paymentType")
            if "paymentType" in payload
            else payload.get("payment_type"),
            "付款类型",
        )
        payment_proof_id = _normalize_required_text(
            payload.get("paymentProofId")
            if "paymentProofId" in payload
            else payload.get("payment_proof_id"),
            "付款凭证",
        )
        if payment_type not in ALLOWED_PAYMENT_TYPES:
            raise AppError(400, "付款类型不支持", "VALIDATION_FAILED")

        record = self.require_record(group_buy_record_id)
        before = clone(record)

        if payment_type == "goods":
            record["goodsPaymentRecordId"] = payment_proof_id
            record["goodsPaidConfirmed"] = True
        else:
            record["internationalPaymentRecordId"] = payment_proof_id
            record["needsInternationalFee"] = True
            record["internationalPaidConfirmed"] = True

        self._refresh_record_status(record, group_buy=self._require_group_buy(record["groupBuyId"]))
        record["updatedAt"] = self.now_iso()
        self.audit_log(
            actor_user_id=actor_user_id,
            action="record.link_payment_proof",
            object_type="group_buy_record",
            object_id=record["id"],
            before=before,
            after=clone(record),
            reason=f"关联 {payment_type} 付款凭证",
        )
        return {"groupBuyRecordId": record["id"]}

    def mark_ordered(
        self,
        payload: dict[str, Any],
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        group_buy_record_ids = self._normalize_record_id_list(payload.get("groupBuyRecordIds"))
        source_object_type = _normalize_required_text(
            payload.get("sourceObjectType")
            if "sourceObjectType" in payload
            else payload.get("source_object_type"),
            "来源类型",
        )
        source_object_id = _normalize_required_text(
            payload.get("sourceObjectId")
            if "sourceObjectId" in payload
            else payload.get("source_object_id"),
            "来源对象",
        )
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)

        updated_count = 0
        for record_id in group_buy_record_ids:
            record = self.require_record(record_id)
            before = clone(record)
            record["isOrdered"] = True
            record["orderedSourceObjectType"] = source_object_type
            record["orderedSourceObjectId"] = source_object_id
            record["orderedReason"] = reason
            self._refresh_record_status(record, group_buy=self._require_group_buy(record["groupBuyId"]))
            record["updatedAt"] = self.now_iso()
            self.audit_log(
                actor_user_id=actor_user_id,
                action="record.mark_ordered",
                object_type="group_buy_record",
                object_id=record["id"],
                before=before,
                after=clone(record),
                reason=reason,
            )
            updated_count += 1

        return {"updatedCount": updated_count}

    def mark_stocked(
        self,
        payload: dict[str, Any],
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        group_buy_record_ids = self._normalize_record_id_list(payload.get("groupBuyRecordIds"))
        warehouse_user_id = _normalize_required_text(
            payload.get("warehouseUserId")
            if "warehouseUserId" in payload
            else payload.get("warehouse_user_id"),
            "囤货人",
        )
        stocked_at = _normalize_required_text(
            payload.get("stockedAt") if "stockedAt" in payload else payload.get("stocked_at"),
            "入库时间",
        )

        updated_count = 0
        for record_id in group_buy_record_ids:
            record = self.require_record(record_id)
            before = clone(record)
            record["warehouseUserId"] = warehouse_user_id
            record["stockedAt"] = stocked_at
            record["isOrdered"] = True
            record["enteredTransferFlow"] = True
            record["isStocked"] = True
            self._refresh_record_status(record, group_buy=self._require_group_buy(record["groupBuyId"]))
            record["updatedAt"] = self.now_iso()
            self.audit_log(
                actor_user_id=actor_user_id,
                action="record.mark_stocked",
                object_type="group_buy_record",
                object_id=record["id"],
                before=before,
                after=clone(record),
                reason="国内囤货入库",
            )
            updated_count += 1

        return {"updatedCount": updated_count}

    def enter_transfer_flow(
        self,
        payload: dict[str, Any],
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        group_buy_record_ids = self._normalize_record_id_list(payload.get("groupBuyRecordIds"))
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)

        updated_count = 0
        for record_id in group_buy_record_ids:
            record = self.require_record(record_id)
            if record.get("enteredTransferFlow"):
                continue

            before = clone(record)
            record["enteredTransferFlow"] = True
            self._refresh_record_status(record, group_buy=self._require_group_buy(record["groupBuyId"]))
            record["updatedAt"] = self.now_iso()
            self.audit_log(
                actor_user_id=actor_user_id,
                action="record.enter_transfer_flow",
                object_type="group_buy_record",
                object_id=record["id"],
                before=before,
                after=clone(record),
                reason=reason,
            )
            updated_count += 1

        return {"updatedCount": updated_count}

    def mark_dispatch_requested(
        self,
        payload: dict[str, Any],
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        group_buy_record_ids = self._normalize_record_id_list(payload.get("groupBuyRecordIds"))
        dispatch_request_id = _normalize_required_text(
            payload.get("dispatchRequestId")
            if "dispatchRequestId" in payload
            else payload.get("dispatch_request_id"),
            "排发申请",
        )

        updated_count = 0
        for record_id in group_buy_record_ids:
            record = self.require_record(record_id)
            before = clone(record)
            record["dispatchRequestId"] = dispatch_request_id
            self._refresh_record_status(record, group_buy=self._require_group_buy(record["groupBuyId"]))
            record["updatedAt"] = self.now_iso()
            self.audit_log(
                actor_user_id=actor_user_id,
                action="record.mark_dispatch_requested",
                object_type="group_buy_record",
                object_id=record["id"],
                before=before,
                after=clone(record),
                reason="创建排发申请",
            )
            updated_count += 1

        return {"updatedCount": updated_count}

    def mark_dispatched(
        self,
        payload: dict[str, Any],
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        group_buy_record_ids = self._normalize_record_id_list(payload.get("groupBuyRecordIds"))
        dispatch_request_id = _normalize_required_text(
            payload.get("dispatchRequestId")
            if "dispatchRequestId" in payload
            else payload.get("dispatch_request_id"),
            "排发申请",
        )
        shipment_id = _normalize_required_text(
            payload.get("shipmentId") if "shipmentId" in payload else payload.get("shipment_id"),
            "快递单",
        )

        updated_count = 0
        for record_id in group_buy_record_ids:
            record = self.require_record(record_id)
            before = clone(record)
            record["dispatchRequestId"] = dispatch_request_id
            record["shipmentId"] = shipment_id
            self._refresh_record_status(record, group_buy=self._require_group_buy(record["groupBuyId"]))
            record["updatedAt"] = self.now_iso()
            self.audit_log(
                actor_user_id=actor_user_id,
                action="record.mark_dispatched",
                object_type="group_buy_record",
                object_id=record["id"],
                before=before,
                after=clone(record),
                reason="录入国内快递",
            )
            updated_count += 1

        return {"updatedCount": updated_count}

    def mark_exception(
        self,
        actor_user: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.has_permission(actor_user, "record:mark_exception"):
            raise AppError(403, "当前账号没有标记异常的权限", "FORBIDDEN")

        group_buy_record_id = _normalize_required_text(
            payload.get("groupBuyRecordId")
            if "groupBuyRecordId" in payload
            else payload.get("group_buy_record_id"),
            "拼单记录",
        )
        exception_reason = _normalize_required_text(
            payload.get("exceptionReason")
            if "exceptionReason" in payload
            else payload.get("exception_reason"),
            "异常原因",
            2,
        )
        note = _normalize_optional_text(payload.get("note"), "note")

        record = self.require_record(group_buy_record_id)
        before = clone(record)
        record["isException"] = True
        record["exceptionReason"] = exception_reason
        if note is not None:
            record["note"] = note
        self._refresh_record_status(record, group_buy=self._require_group_buy(record["groupBuyId"]))
        record["updatedAt"] = self.now_iso()
        self.audit_log(
            actor_user_id=actor_user["id"],
            action="record.mark_exception",
            object_type="group_buy_record",
            object_id=record["id"],
            before=before,
            after=clone(record),
            reason=exception_reason,
        )
        return {
            "groupBuyRecordId": record["id"],
            "isException": record["isException"],
        }

    def recalculate_display_status(
        self,
        payload: dict[str, Any],
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        group_buy_record_id = _normalize_required_text(
            payload.get("groupBuyRecordId")
            if "groupBuyRecordId" in payload
            else payload.get("group_buy_record_id"),
            "拼单记录",
        )
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)

        record = self.require_record(group_buy_record_id)
        before = clone(record)
        old_status = record["status"]
        self._refresh_record_status(record, group_buy=self._require_group_buy(record["groupBuyId"]))
        record["updatedAt"] = self.now_iso()
        self.audit_log(
            actor_user_id=actor_user_id,
            action="record.recalculate_status",
            object_type="group_buy_record",
            object_id=record["id"],
            before=before,
            after=clone(record),
            reason=reason,
        )
        return {
            "groupBuyRecordId": record["id"],
            "oldStatus": old_status,
            "newStatus": record["status"],
            "statusPriority": record["statusPriority"],
            "isDispatchable": self._is_dispatchable(record),
        }

    def build_record_summary(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": record["id"],
            "groupBuyId": record["groupBuyId"],
            "groupBuyItemId": record["groupBuyItemId"],
            "memberUserId": record["memberUserId"],
            "quantity": record["quantity"],
            "status": record["status"],
            "displayStatus": record["status"],
            "statusPriority": record["statusPriority"],
            "isException": bool(record["isException"]),
            "exceptionReason": record.get("exceptionReason"),
            "isDispatchable": self._is_dispatchable(record),
            "createdAt": record["createdAt"],
            "updatedAt": record["updatedAt"],
        }

    def _require_group_buy(self, group_buy_id: str) -> dict[str, Any]:
        group_buy = next(
            (item for item in self.state.get("groupBuys", []) if item["id"] == group_buy_id),
            None,
        )
        if group_buy is None:
            raise AppError(404, "拼团不存在", "NOT_FOUND")
        return group_buy

    def _require_visible_group_buy(
        self,
        actor_user: dict[str, Any],
        group_buy_id: str,
    ) -> dict[str, Any]:
        group_buy = self._require_group_buy(group_buy_id)
        if not self.can_view_group_buy(actor_user, group_buy):
            raise AppError(404, "拼团不存在", "NOT_FOUND")
        return group_buy

    def _require_group_buy_item(self, group_buy_item_id: str) -> dict[str, Any]:
        item = next(
            (entry for entry in self.state.get("groupBuyItems", []) if entry["id"] == group_buy_item_id),
            None,
        )
        if item is None:
            raise AppError(404, "拼团商品不存在", "NOT_FOUND")
        return item

    def _assert_can_create_for_member(
        self,
        actor_user: dict[str, Any],
        member_user_id: str,
    ) -> None:
        if actor_user["id"] == member_user_id:
            if not self.has_permission(actor_user, "record:create_self"):
                raise AppError(403, "当前账号没有认领权限", "FORBIDDEN")
            return
        if not self.has_permission(actor_user, "record:create_for_member"):
            raise AppError(403, "当前账号没有代成员建单的权限", "FORBIDDEN")

    def _assert_can_manage_record(self, actor_user: dict[str, Any], record: dict[str, Any]) -> None:
        if actor_user["id"] == record["memberUserId"] and self.has_permission(actor_user, "record:create_self"):
            return
        if self.has_permission(actor_user, "record:create_for_member"):
            return
        raise AppError(403, "当前账号没有修改拼单记录的权限", "FORBIDDEN")

    def _assert_record_mutable(self, actor_user: dict[str, Any], record: dict[str, Any]) -> None:
        if record["status"] == GROUP_BUY_RECORD_STATUS_COMPLETED and actor_user["id"] == record["memberUserId"]:
            raise AppError(400, "已完结记录暂不允许普通修改", "INVALID_STATUS")

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

    def _needs_international_fee(self, group_buy: dict[str, Any]) -> bool:
        return group_buy.get("type") not in GROUP_BUY_TYPES_WITHOUT_INTERNATIONAL

    def _needs_transfer(self, group_buy: dict[str, Any]) -> bool:
        return self._needs_international_fee(group_buy)

    def _needs_domestic_stock(self, group_buy: dict[str, Any]) -> bool:
        return group_buy.get("type") not in GROUP_BUY_TYPES_WITHOUT_STOCKING

    def _refresh_record_status(self, record: dict[str, Any], *, group_buy: dict[str, Any]) -> None:
        # 展示状态先按文档固定优先级计算，后续费用/转运模块接入时只需要补齐影子字段即可。
        if record.get("isTransferPending") or record.get("transferId"):
            next_status = GROUP_BUY_RECORD_STATUS_TRANSFERRING
        elif record.get("isCompleted"):
            next_status = GROUP_BUY_RECORD_STATUS_COMPLETED
        elif record.get("shipmentId"):
            next_status = GROUP_BUY_RECORD_STATUS_DISPATCHED
        elif record.get("dispatchRequestId"):
            next_status = GROUP_BUY_RECORD_STATUS_DISPATCH_REQUESTED
        elif not record.get("goodsPaidConfirmed", False):
            next_status = GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT
        elif record.get("needsInternationalFee", self._needs_international_fee(group_buy)) and not record.get(
            "internationalPaidConfirmed",
            False,
        ):
            next_status = GROUP_BUY_RECORD_STATUS_PENDING_INTERNATIONAL_PAYMENT
        elif record.get("needsTransfer", self._needs_transfer(group_buy)) and not record.get(
            "enteredTransferFlow",
            False,
        ):
            next_status = GROUP_BUY_RECORD_STATUS_PENDING_TRANSFER
        elif record.get("needsDomesticStock", self._needs_domestic_stock(group_buy)) and not record.get(
            "isStocked",
            False,
        ):
            next_status = GROUP_BUY_RECORD_STATUS_PENDING_STOCK
        elif self._is_ready_for_dispatch_status(record):
            next_status = GROUP_BUY_RECORD_STATUS_DISPATCHABLE
        elif record.get("isOrdered"):
            next_status = GROUP_BUY_RECORD_STATUS_ORDERED
        else:
            next_status = GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT

        record["status"] = next_status
        record["statusPriority"] = _status_priority(next_status)

    def _is_dispatchable(self, record: dict[str, Any]) -> bool:
        if record.get("isException"):
            return False
        if record.get("isTransferPending") or record.get("transferId"):
            return False
        if record.get("dispatchRequestId") or record.get("shipmentId") or record.get("isCompleted"):
            return False
        if not record.get("isOrdered"):
            return False
        if not record.get("goodsPaidConfirmed"):
            return False
        if record.get("needsInternationalFee") and not record.get("internationalPaidConfirmed"):
            return False
        if record.get("needsTransfer") and not record.get("enteredTransferFlow"):
            return False
        if record.get("needsDomesticStock") and not record.get("isStocked"):
            return False
        return True

    def _is_ready_for_dispatch_status(self, record: dict[str, Any]) -> bool:
        if record.get("dispatchRequestId") or record.get("shipmentId") or record.get("isCompleted"):
            return False
        if record.get("isTransferPending") or record.get("transferId"):
            return False
        if not record.get("isOrdered"):
            return False
        if not record.get("goodsPaidConfirmed"):
            return False
        if record.get("needsInternationalFee") and not record.get("internationalPaidConfirmed"):
            return False
        if record.get("needsTransfer") and not record.get("enteredTransferFlow"):
            return False
        if record.get("needsDomesticStock") and not record.get("isStocked"):
            return False
        return True
