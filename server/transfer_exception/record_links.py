from __future__ import annotations

from typing import Any, Callable

from ..errors import AppError
from .transfer_inputs import clone


class TransferRecordLinks:
    def __init__(
        self,
        *,
        state: dict[str, Any],
        audit_log: Callable[..., Any],
        now_iso: Callable[[], str],
        require_group_buy_record: Callable[[str], dict[str, Any]],
        refresh_record_status: Callable[[dict[str, Any]], dict[str, Any]],
        create_record_for_transfer: Callable[..., dict[str, Any]],
    ):
        self.state = state
        self.audit_log = audit_log
        self.now_iso = now_iso
        self.require_group_buy_record = require_group_buy_record
        self.refresh_record_status = refresh_record_status
        self.create_record_for_transfer = create_record_for_transfer

    def assert_transferable_record(
        self,
        record: dict[str, Any],
        *,
        from_user_id: str,
        quantity: int,
        expected_transfer_id: str | None = None,
    ) -> None:
        if record["memberUserId"] != from_user_id:
            raise AppError(400, "转出记录不属于指定成员", "VALIDATION_FAILED")
        if record.get("isTransferredOut"):
            raise AppError(400, "已转出的记录不能再次转单", "INVALID_STATUS")
        if quantity > record["quantity"]:
            raise AppError(400, "转单数量不能超过原记录数量", "VALIDATION_FAILED")

        if expected_transfer_id is None:
            if record.get("isTransferPending") or record.get("transferId"):
                raise AppError(400, "记录已经在转单流程中", "DUPLICATED_OPERATION")
        elif record.get("transferId") != expected_transfer_id or not record.get("isTransferPending"):
            raise AppError(400, "记录和转单申请不匹配", "INVALID_STATUS")

        # 第一版先禁止已经进入履约后段的记录转单，避免费用和库存归属被拆散。
        if record.get("isOrdered") or record.get("enteredTransferFlow") or record.get("warehouseUserId"):
            raise AppError(400, "已进入下单或转运流程的记录暂不支持转单", "INVALID_STATUS")
        if record.get("dispatchRequestId") or record.get("shipmentId") or record.get("isCompleted"):
            raise AppError(400, "已进入排发流程的记录暂不支持转单", "INVALID_STATUS")

    def assert_target_user_in_group(self, group_buy_id: str, to_user_id: str) -> None:
        group_buy = next(
            (item for item in self.state.get("groupBuys", []) if item["id"] == group_buy_id),
            None,
        )
        if group_buy is None:
            raise AppError(404, "拼团不存在", "NOT_FOUND")

        group = next(
            (item for item in self.state.get("groups", []) if item["id"] == group_buy["groupId"]),
            None,
        )
        if group is None or to_user_id not in group.get("memberIds", []):
            raise AppError(400, "转入成员不在当前拼团所属群组中", "VALIDATION_FAILED")

    def mark_transfer_pending(
        self,
        *,
        record: dict[str, Any],
        transfer_id: str,
        actor_user_id: str,
        reason: str,
    ) -> None:
        before = clone(record)
        record["transferId"] = transfer_id
        record["isTransferPending"] = True
        record["updatedAt"] = self.now_iso()
        self.refresh_record_status(record)
        self.audit_log(
            actor_user_id=actor_user_id,
            action="record.request_transfer",
            object_type="group_buy_record",
            object_id=record["id"],
            before=before,
            after=clone(record),
            reason=reason,
        )

    def release_transfer_pending(
        self,
        *,
        record: dict[str, Any],
        transfer_id: str,
        actor_user_id: str,
        reason: str,
    ) -> None:
        if record.get("transferId") != transfer_id and not record.get("isTransferPending"):
            return

        before = clone(record)
        record["transferId"] = None
        record["isTransferPending"] = False
        record["updatedAt"] = self.now_iso()
        self.refresh_record_status(record)
        self.audit_log(
            actor_user_id=actor_user_id,
            action="record.reject_transfer",
            object_type="group_buy_record",
            object_id=record["id"],
            before=before,
            after=clone(record),
            reason=reason,
        )

    def approve_transfer_item(
        self,
        *,
        transfer: dict[str, Any],
        transfer_item: dict[str, Any],
        actor_user_id: str,
        note: str | None,
    ) -> dict[str, Any]:
        source_record = self.require_group_buy_record(transfer_item["groupBuyRecordId"])
        self.assert_transferable_record(
            source_record,
            from_user_id=transfer["fromUserId"],
            quantity=transfer_item["quantity"],
            expected_transfer_id=transfer["id"],
        )

        created = self.create_record_for_transfer(
            source_record=source_record,
            to_user_id=transfer["toUserId"],
            quantity=transfer_item["quantity"],
            transfer_id=transfer["id"],
            actor_user_id=actor_user_id,
            note=note or transfer["reason"],
        )

        before = clone(source_record)
        now = self.now_iso()
        remaining_quantity = source_record["quantity"] - transfer_item["quantity"]
        if remaining_quantity < 0:
            raise AppError(400, "转单数量不能超过原记录数量", "VALIDATION_FAILED")

        source_record["quantity"] = remaining_quantity
        source_record["transferId"] = None
        source_record["isTransferPending"] = False
        source_record["updatedAt"] = now
        if remaining_quantity == 0:
            source_record["isTransferredOut"] = True
            source_record["transferredOutAt"] = now
        self.refresh_record_status(source_record)

        self.audit_log(
            actor_user_id=actor_user_id,
            action="record.transfer_out",
            object_type="group_buy_record",
            object_id=source_record["id"],
            before=before,
            after=clone(source_record),
            reason=note or transfer["reason"],
        )
        return created
