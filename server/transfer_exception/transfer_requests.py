from __future__ import annotations

from typing import Any, Callable

from ..config import Config
from ..db_access import connect
from ..errors import AppError
from .transfer_exception_repo import TransferExceptionRepository
from .transfer_inputs import clone, normalize_optional_text, normalize_required_text, normalize_transfer_items, payload_get
from .transfer_state import TRANSFER_STATUS_PENDING


class TransferRequestWorkflow:
    def __init__(
        self,
        config: Config,
        *,
        repository: TransferExceptionRepository | None = None,
        audit_service: Any | None = None,
        group_buy_records: Any | None = None,
        has_permission_by_user_id: Callable[[str, str], bool],
        get_user_snapshot_by_id: Callable[[str], dict[str, Any] | None],
        has_group_access_by_user_id: Callable[[str, str], bool],
    ):
        # 注入 DB 仓库、审计和拼单记录模块，转单流程不再访问 JSON state。
        self.config = config
        self.repo = repository or TransferExceptionRepository(config)
        self.audit_service = audit_service
        self.group_buy_records = group_buy_records
        self.has_permission_by_user_id = has_permission_by_user_id
        self.get_user_snapshot_by_id = get_user_snapshot_by_id
        self.has_group_access_by_user_id = has_group_access_by_user_id

    def request_transfer(self, actor_user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 创建转单申请、明细，并把源记录标记为转单中。
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

        module = self._require_group_buy_records()
        with connect(self.config) as conn:
            records_by_id: dict[str, dict[str, Any]] = {}
            for item in items:
                record = module._require_record_in_connection(conn, item["groupBuyRecordId"], lock=True)
                record = module._attach_derived_fields_in_connection(conn, record)
                self._assert_transferable_record(
                    record,
                    from_user_id=from_user_id,
                    quantity=item["quantity"],
                )
                group_buy = module._require_group_buy_in_connection(conn, record["groupBuyId"])
                if not self.has_group_access_by_user_id(to_user_id, group_buy["groupId"]):
                    raise AppError(400, "转入成员不在当前拼团所属群组中", "VALIDATION_FAILED")
                records_by_id[record["id"]] = record

            transfer = self.repo.create_transfer(
                conn,
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                requested_by=actor_user["id"],
                reason=reason,
            )
            transfer_items = [
                self.repo.create_transfer_item(
                    conn,
                    transfer_id=transfer["id"],
                    group_buy_record_id=item["groupBuyRecordId"],
                    quantity=item["quantity"],
                )
                for item in items
            ]

            for item in transfer_items:
                before = records_by_id[item["groupBuyRecordId"]]
                self.repo.mark_record_transfer_pending(
                    conn,
                    group_buy_record_id=item["groupBuyRecordId"],
                    transfer_id=transfer["id"],
                )
                after = module._recalculate_record_status_in_connection(
                    conn,
                    item["groupBuyRecordId"],
                    actor_user_id=actor_user["id"],
                    reason=reason,
                    write_audit=False,
                )
                self._audit(
                    conn,
                    actor_user_id=actor_user["id"],
                    action="record.request_transfer",
                    object_type="group_buy_record",
                    object_id=item["groupBuyRecordId"],
                    before=before,
                    after=after,
                    reason=reason,
                )

            self._audit(
                conn,
                actor_user_id=actor_user["id"],
                action="transfer.request",
                object_type="transfer",
                object_id=transfer["id"],
                before=None,
                after={**clone(transfer), "items": clone(transfer_items)},
                reason=reason,
            )
            conn.commit()
        return {"transferId": transfer["id"], "status": transfer["status"]}

    def approve_transfer(
        self,
        actor_user_id: str,
        transfer_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 审核通过转单：创建受让记录、扣减源记录、更新申请状态。
        self._assert_can_review_transfer(actor_user_id)
        note = normalize_optional_text(payload.get("note"), "note")
        module = self._require_group_buy_records()
        new_group_buy_record_ids: list[str] = []

        with connect(self.config) as conn:
            transfer = self.repo.get_transfer_for_update(conn, transfer_id)
            if transfer["status"] != TRANSFER_STATUS_PENDING:
                raise AppError(400, "当前转单申请状态不能审核通过", "INVALID_STATUS")
            transfer_items = self.repo.list_transfer_items(conn, transfer_id, lock=True)
            if not transfer_items:
                raise AppError(400, "空转单申请不能审核通过", "VALIDATION_FAILED")

            for item in transfer_items:
                record = module._require_record_in_connection(conn, item["groupBuyRecordId"], lock=True)
                record = module._attach_derived_fields_in_connection(conn, record)
                self._assert_transferable_record(
                    record,
                    from_user_id=transfer["fromUserId"],
                    quantity=item["quantity"],
                    expected_transfer_id=transfer_id,
                )
                group_buy = module._require_group_buy_in_connection(conn, record["groupBuyId"])
                if not self.has_group_access_by_user_id(transfer["toUserId"], group_buy["groupId"]):
                    raise AppError(400, "转入成员不在当前拼团所属群组中", "VALIDATION_FAILED")

            for item in transfer_items:
                source_record = module._require_record_in_connection(conn, item["groupBuyRecordId"], lock=True)
                created = module.create_transfer_record_in_connection(
                    conn,
                    source_record=source_record,
                    to_user_id=transfer["toUserId"],
                    quantity=item["quantity"],
                    transfer_id=transfer_id,
                    actor_user_id=actor_user_id,
                    note=note or transfer["reason"],
                )
                new_group_buy_record_ids.append(created["id"])
                module.transfer_out_in_connection(
                    conn,
                    group_buy_record_id=source_record["id"],
                    transfer_id=transfer_id,
                    quantity=item["quantity"],
                    actor_user_id=actor_user_id,
                    reason=note or transfer["reason"],
                )

            after_transfer = self.repo.approve_transfer(
                conn,
                transfer_id=transfer_id,
                approved_by=actor_user_id,
                note=note,
            )
            for new_record_id in new_group_buy_record_ids:
                module._recalculate_record_status_in_connection(
                    conn,
                    new_record_id,
                    actor_user_id=actor_user_id,
                    reason=note or transfer["reason"],
                    write_audit=False,
                )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="transfer.approve",
                object_type="transfer",
                object_id=transfer_id,
                before=transfer,
                after={**clone(after_transfer), "newGroupBuyRecordIds": clone(new_group_buy_record_ids)},
                reason=note or transfer["reason"],
            )
            conn.commit()
        return {"transferId": transfer_id, "newGroupBuyRecordIds": new_group_buy_record_ids}

    def reject_transfer(
        self,
        actor_user_id: str,
        transfer_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 驳回转单：释放源记录转单中状态，并记录驳回信息。
        self._assert_can_review_transfer(actor_user_id)
        _, raw_reject_reason = payload_get(payload, "rejectReason", "reject_reason")
        reject_reason = normalize_required_text(raw_reject_reason, "rejectReason", 2)
        module = self._require_group_buy_records()

        with connect(self.config) as conn:
            transfer = self.repo.get_transfer_for_update(conn, transfer_id)
            if transfer["status"] != TRANSFER_STATUS_PENDING:
                raise AppError(400, "当前转单申请状态不能驳回", "INVALID_STATUS")
            transfer_items = self.repo.list_transfer_items(conn, transfer_id, lock=True)
            if not transfer_items:
                raise AppError(400, "空转单申请不能驳回", "VALIDATION_FAILED")

            for item in transfer_items:
                before = module._require_record_in_connection(conn, item["groupBuyRecordId"], lock=True)
                self.repo.release_record_transfer_pending(
                    conn,
                    group_buy_record_id=item["groupBuyRecordId"],
                    transfer_id=transfer_id,
                )
                after = module._recalculate_record_status_in_connection(
                    conn,
                    item["groupBuyRecordId"],
                    actor_user_id=actor_user_id,
                    reason=reject_reason,
                    write_audit=False,
                )
                self._audit(
                    conn,
                    actor_user_id=actor_user_id,
                    action="record.reject_transfer",
                    object_type="group_buy_record",
                    object_id=item["groupBuyRecordId"],
                    before=before,
                    after=after,
                    reason=reject_reason,
                )

            after_transfer = self.repo.reject_transfer(
                conn,
                transfer_id=transfer_id,
                rejected_by=actor_user_id,
                reject_reason=reject_reason,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="transfer.reject",
                object_type="transfer",
                object_id=transfer_id,
                before=transfer,
                after=after_transfer,
                reason=reject_reason,
            )
            conn.commit()
        return {"transferId": transfer_id, "status": "rejected"}

    def _assert_can_request_transfer(
        self,
        actor_user_id: str,
        from_user_id: str,
        to_user_id: str,
    ) -> None:
        # 成员本人或受让人可提交，维护人可代成员提交。
        if actor_user_id in {from_user_id, to_user_id}:
            return
        if self.has_permission_by_user_id(actor_user_id, "record:create_for_member"):
            return
        raise AppError(403, "当前账号没有代成员提交转单申请的权限", "FORBIDDEN")

    def _assert_can_review_transfer(self, actor_user_id: str) -> None:
        # 复用维护人建单权限作为转单审核权限。
        if self.has_permission_by_user_id(actor_user_id, "record:create_for_member"):
            return
        raise AppError(403, "当前账号没有审核转单的权限", "FORBIDDEN")

    def _assert_transferable_record(
        self,
        record: dict[str, Any],
        *,
        from_user_id: str,
        quantity: int,
        expected_transfer_id: str | None = None,
    ) -> None:
        # 校验源记录归属、数量和流程阶段是否允许转单。
        if record["memberUserId"] != from_user_id:
            raise AppError(400, "转出记录不属于指定成员", "VALIDATION_FAILED")
        if quantity >= record["quantity"]:
            raise AppError(400, "现有数据库约束不支持全量转出，请至少保留 1 件在原记录", "VALIDATION_FAILED")
        if expected_transfer_id is None:
            if record.get("transferId"):
                raise AppError(400, "记录已经在转单流程中", "DUPLICATED_OPERATION")
        elif record.get("transferId") != expected_transfer_id:
            raise AppError(400, "记录和转单申请不匹配", "INVALID_STATUS")
        if (
            record.get("isOrdered")
            or record.get("enteredTransferFlow")
            or record.get("isStocked")
            or record.get("warehouseUserId")
        ):
            raise AppError(400, "已进入下单或转运流程的记录暂不支持转单", "INVALID_STATUS")
        if record.get("dispatchRequestId") or record.get("shipmentId") or record.get("isCompleted"):
            raise AppError(400, "已进入排发流程的记录暂不支持转单", "INVALID_STATUS")

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
            before=before,
            after=after,
            reason=reason,
        )

    def _require_group_buy_records(self) -> Any:
        # 转单流程必须依赖 DB 版拼单记录模块。
        if self.group_buy_records is None:
            raise RuntimeError("group_buy_records dependency is required for transfer workflow.")
        return self.group_buy_records

    def _require_user(self, user_id: str, field_name: str) -> None:
        # 校验转出/转入用户存在。
        if self.get_user_snapshot_by_id(user_id) is None:
            raise AppError(404, f"{field_name}对应用户不存在", "NOT_FOUND")
