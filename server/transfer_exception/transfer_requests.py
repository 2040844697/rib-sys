from __future__ import annotations

from typing import Any, Callable

from ..errors import AppError
from .record_links import TransferRecordLinks
from .transfer_inputs import (
    clone,
    normalize_optional_text,
    normalize_required_text,
    normalize_transfer_items,
    payload_get,
)
from .transfer_state import (
    TRANSFER_STATUS_APPROVED,
    TRANSFER_STATUS_PENDING,
    TRANSFER_STATUS_REJECTED,
)


class TransferRequestWorkflow:
    def __init__(
        self,
        *,
        state: dict[str, Any],
        next_id: Callable[[str, str], str],
        audit_log: Callable[..., Any],
        now_iso: Callable[[], str],
        has_permission_by_user_id: Callable[[str, str], bool],
        get_user_snapshot_by_id: Callable[[str], dict[str, Any] | None],
        record_links: TransferRecordLinks,
    ):
        self.state = state
        self.next_id = next_id
        self.audit_log = audit_log
        self.now_iso = now_iso
        self.has_permission_by_user_id = has_permission_by_user_id
        self.get_user_snapshot_by_id = get_user_snapshot_by_id
        self.record_links = record_links

    def require_transfer(self, transfer_id: str) -> dict[str, Any]:
        transfer = next(
            (item for item in self.state.get("transfers", []) if item["id"] == transfer_id),
            None,
        )
        if transfer is None:
            raise AppError(404, "转单申请不存在", "NOT_FOUND")
        return transfer

    def list_transfer_items(self, transfer_id: str) -> list[dict[str, Any]]:
        return [
            item
            for item in self.state.get("transferItems", [])
            if item["transferId"] == transfer_id
        ]

    def request_transfer(self, actor_user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        has_from_user_id, raw_from_user_id = payload_get(payload, "fromUserId", "from_user_id")
        from_user_id = normalize_required_text(
            raw_from_user_id if has_from_user_id else actor_user["id"],
            "fromUserId",
        )
        _, raw_to_user_id = payload_get(payload, "toUserId", "to_user_id")
        to_user_id = normalize_required_text(raw_to_user_id, "toUserId")
        reason = normalize_required_text(payload.get("reason"), "reason", 2)
        items = normalize_transfer_items(payload.get("items"))

        self._assert_can_request_transfer(actor_user["id"], from_user_id, to_user_id)
        self._require_user(from_user_id, "fromUserId")
        self._require_user(to_user_id, "toUserId")
        if from_user_id == to_user_id:
            raise AppError(400, "转入成员不能和转出成员相同", "VALIDATION_FAILED")

        for item in items:
            record = self.record_links.require_group_buy_record(item["groupBuyRecordId"])
            self.record_links.assert_transferable_record(
                record,
                from_user_id=from_user_id,
                quantity=item["quantity"],
            )
            self.record_links.assert_target_user_in_group(record["groupBuyId"], to_user_id)

        transfer_id = self.next_id("transfer", "transfer")
        now = self.now_iso()
        transfer = {
            "id": transfer_id,
            "fromUserId": from_user_id,
            "toUserId": to_user_id,
            "requestedBy": actor_user["id"],
            "approvedBy": None,
            "approvedAt": None,
            "rejectedBy": None,
            "rejectedAt": None,
            "rejectReason": None,
            "status": TRANSFER_STATUS_PENDING,
            "reason": reason,
            "note": None,
            "createdAt": now,
            "updatedAt": now,
        }
        self.state["transfers"].append(transfer)

        for item in items:
            record = self.record_links.require_group_buy_record(item["groupBuyRecordId"])
            self.state["transferItems"].append(
                {
                    "id": self.next_id("transferItem", "transfer_item"),
                    "transferId": transfer_id,
                    "groupBuyRecordId": record["id"],
                    "quantity": item["quantity"],
                    "createdAt": now,
                }
            )
            self.record_links.mark_transfer_pending(
                record=record,
                transfer_id=transfer_id,
                actor_user_id=actor_user["id"],
                reason=reason,
            )

        self.audit_log(
            actor_user_id=actor_user["id"],
            action="transfer.request",
            object_type="transfer",
            object_id=transfer_id,
            before=None,
            after={**clone(transfer), "items": clone(items)},
            reason=reason,
        )
        return {"transferId": transfer_id, "status": transfer["status"]}

    def approve_transfer(
        self,
        actor_user_id: str,
        transfer_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_can_review_transfer(actor_user_id)
        transfer = self.require_transfer(transfer_id)
        if transfer["status"] != TRANSFER_STATUS_PENDING:
            raise AppError(400, "当前转单申请状态不能审核通过", "INVALID_STATUS")

        note = normalize_optional_text(payload.get("note"), "note")
        transfer_items = self.list_transfer_items(transfer_id)
        if not transfer_items:
            raise AppError(400, "空转单申请不能审核通过", "VALIDATION_FAILED")

        for item in transfer_items:
            source_record = self.record_links.require_group_buy_record(item["groupBuyRecordId"])
            self.record_links.assert_transferable_record(
                source_record,
                from_user_id=transfer["fromUserId"],
                quantity=item["quantity"],
                expected_transfer_id=transfer_id,
            )
            self.record_links.assert_target_user_in_group(source_record["groupBuyId"], transfer["toUserId"])

        before_transfer = clone(transfer)
        new_group_buy_record_ids: list[str] = []
        for item in transfer_items:
            created = self.record_links.approve_transfer_item(
                transfer=transfer,
                transfer_item=item,
                actor_user_id=actor_user_id,
                note=note,
            )
            new_group_buy_record_ids.append(created["id"])

        now = self.now_iso()
        transfer["status"] = TRANSFER_STATUS_APPROVED
        transfer["approvedBy"] = actor_user_id
        transfer["approvedAt"] = now
        transfer["note"] = note
        transfer["updatedAt"] = now
        self.audit_log(
            actor_user_id=actor_user_id,
            action="transfer.approve",
            object_type="transfer",
            object_id=transfer_id,
            before=before_transfer,
            after={**clone(transfer), "newGroupBuyRecordIds": clone(new_group_buy_record_ids)},
            reason=note or transfer["reason"],
        )
        return {"transferId": transfer_id, "newGroupBuyRecordIds": new_group_buy_record_ids}

    def reject_transfer(
        self,
        actor_user_id: str,
        transfer_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_can_review_transfer(actor_user_id)
        transfer = self.require_transfer(transfer_id)
        if transfer["status"] != TRANSFER_STATUS_PENDING:
            raise AppError(400, "当前转单申请状态不能驳回", "INVALID_STATUS")

        _, raw_reject_reason = payload_get(payload, "rejectReason", "reject_reason")
        reject_reason = normalize_required_text(raw_reject_reason, "rejectReason", 2)
        before_transfer = clone(transfer)

        for item in self.list_transfer_items(transfer_id):
            record = self.record_links.require_group_buy_record(item["groupBuyRecordId"])
            self.record_links.release_transfer_pending(
                record=record,
                transfer_id=transfer_id,
                actor_user_id=actor_user_id,
                reason=reject_reason,
            )

        now = self.now_iso()
        transfer["status"] = TRANSFER_STATUS_REJECTED
        transfer["rejectedBy"] = actor_user_id
        transfer["rejectedAt"] = now
        transfer["rejectReason"] = reject_reason
        transfer["updatedAt"] = now
        self.audit_log(
            actor_user_id=actor_user_id,
            action="transfer.reject",
            object_type="transfer",
            object_id=transfer_id,
            before=before_transfer,
            after=clone(transfer),
            reason=reject_reason,
        )
        return {"transferId": transfer_id, "status": transfer["status"]}

    def _assert_can_request_transfer(
        self,
        actor_user_id: str,
        from_user_id: str,
        to_user_id: str,
    ) -> None:
        if actor_user_id in {from_user_id, to_user_id}:
            return
        if self.has_permission_by_user_id(actor_user_id, "record:create_for_member"):
            return
        raise AppError(403, "当前账号没有代成员提交转单申请的权限", "FORBIDDEN")

    def _assert_can_review_transfer(self, actor_user_id: str) -> None:
        if self.has_permission_by_user_id(actor_user_id, "record:create_for_member"):
            return
        raise AppError(403, "当前账号没有审核转单的权限", "FORBIDDEN")

    def _require_user(self, user_id: str, field_name: str) -> None:
        if self.get_user_snapshot_by_id(user_id) is None:
            raise AppError(404, f"{field_name}对应用户不存在", "NOT_FOUND")
