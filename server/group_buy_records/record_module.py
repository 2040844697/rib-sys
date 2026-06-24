from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any, Callable

from ..config import Config
from ..db_access import connect
from ..errors import AppError
from ..file_audit import DatabaseAuditService
from .group_buy_record_repo import GroupBuyRecordRepository


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
TRANSFER_RECORD_SOURCE = "transfer"
CHARGE_TYPE_INITIAL_GOODS = "initial_goods"
CHARGE_TYPE_INTERNATIONAL = "international"
CHARGE_TYPE_DOMESTIC_SHIPPING = "domestic_shipping"
CHARGE_TYPE_ALIASES = {
    "goods": CHARGE_TYPE_INITIAL_GOODS,
}
ALLOWED_CHARGE_TYPES = {
    CHARGE_TYPE_INITIAL_GOODS,
    CHARGE_TYPE_INTERNATIONAL,
    CHARGE_TYPE_DOMESTIC_SHIPPING,
}
ALLOWED_PAYMENT_TYPES = {"goods", "international"}


def clone(value: Any) -> Any:
    return copy.deepcopy(value)


def ensure_group_buy_record_state(state: dict[str, Any]) -> bool:
    # 团购记录已迁移到 DB，旧 JSON 不再补主记录状态。
    changed = False
    if "groupBuyRecords" in state:
        state.pop("groupBuyRecords", None)
        changed = True
    counters = state.setdefault("counters", {})
    if "groupBuyRecord" in counters:
        counters.pop("groupBuyRecord", None)
        changed = True
    return changed


def _status_priority(status: str | None) -> int:
    # 展示状态排序值保留在主表，列表可直接排序。
    if not status:
        return GROUP_BUY_RECORD_STATUS_PRIORITY[GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT]
    return GROUP_BUY_RECORD_STATUS_PRIORITY.get(
        status,
        GROUP_BUY_RECORD_STATUS_PRIORITY[GROUP_BUY_RECORD_STATUS_ORDERED],
    )


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


def _normalize_positive_int(value: Any, field_name: str) -> int:
    # 统一校验正整数数量。
    if isinstance(value, bool) or not isinstance(value, int):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    if value <= 0:
        raise AppError(400, f"{field_name}必须大于 0", "VALIDATION_FAILED")
    return value


def _payload_get(payload: dict[str, Any], *keys: str) -> tuple[bool, Any]:
    # 兼容 camelCase 和 snake_case 入参。
    for key in keys:
        if key in payload:
            return True, payload[key]
    return False, None


class GroupBuyRecordsModule:
    def __init__(
        self,
        config: Config,
        *,
        repository: GroupBuyRecordRepository | None = None,
        audit_service: DatabaseAuditService | None = None,
        has_permission_by_user_id: Callable[[str, str], bool] | None = None,
        has_group_access: Callable[[str, str], bool] | None = None,
        get_user_snapshot_by_id: Callable[[str], dict[str, Any] | None] | None = None,
        create_charge: Callable[..., dict[str, Any]] | None = None,
    ):
        self.config = config
        self.repo = repository or GroupBuyRecordRepository(config)
        self.audit_service = audit_service
        self.has_permission_by_user_id = has_permission_by_user_id
        self.has_group_access = has_group_access
        self.get_user_snapshot_by_id = get_user_snapshot_by_id
        self.create_charge = create_charge

    def require_record(self, group_buy_record_id: str) -> dict[str, Any]:
        # 对外读取单条拼单记录。
        with connect(self.config) as conn:
            record = self._require_record_in_connection(conn, group_buy_record_id)
            record = self._attach_derived_fields_in_connection(conn, record)
            conn.rollback()
        return record

    def list_member_records(self, *, group_buy_id: str, member_user_id: str) -> list[dict[str, Any]]:
        # 列出成员在某拼团下的记录摘要。
        with connect(self.config) as conn:
            records = self.repo.list_member_records(
                conn,
                group_buy_id=group_buy_id,
                member_user_id=member_user_id,
            )
            summaries = [self._build_record_summary_in_connection(conn, record) for record in records]
            conn.rollback()
        return summaries

    def count_member_records_by_status(self, *, member_user_id: str, status: str) -> int:
        # 统计成员指定状态记录数量。
        with connect(self.config) as conn:
            result = self.repo.count_member_records_by_status(
                conn,
                member_user_id=member_user_id,
                status=status,
            )
            conn.rollback()
        return result

    def get_claimed_quantity(self, group_buy_item_id: str) -> int:
        # 按商品汇总已认领数量。
        with connect(self.config) as conn:
            result = self.repo.get_claimed_quantity(conn, group_buy_item_id)
            conn.rollback()
        return result

    def list_group_buy_record_ids_by_charge(self, charge_id: str) -> list[str]:
        # 按费用反查记录 ID。
        with connect(self.config) as conn:
            result = self.repo.list_record_ids_by_charge(conn, charge_id)
            conn.rollback()
        return result

    def list_group_buy_record_ids_by_charge_in_connection(self, conn, charge_id: str) -> list[str]:
        # 供费用模块在同一事务中反查记录 ID。
        return self.repo.list_record_ids_by_charge(conn, charge_id)

    def refresh_record_status(self, record: dict[str, Any]) -> dict[str, Any]:
        # 兼容旧下游回调：传入记录后按 DB 事实刷新状态。
        with connect(self.config) as conn:
            refreshed = self._recalculate_record_status_in_connection(
                conn,
                record["id"],
                actor_user_id=None,
                reason="刷新拼单记录状态",
                write_audit=False,
            )
            conn.commit()
        record.update(refreshed)
        return record

    def create_record(self, actor_user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 成员或维护人认领商品，事务内扣库存、建记录、建首款并重算状态。
        actor_user_id = _normalize_required_text(actor_user.get("id"), "actorUserId")
        return self.create_record_for_user(actor_user_id, payload)

    def create_record_for_user(self, actor_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        # AppContext 使用 user_id 调用 DB 版创建流程。
        raw_group_buy_id = payload.get("groupBuyId") if "groupBuyId" in payload else payload.get("group_buy_id")
        payload_group_buy_id = _normalize_optional_text(raw_group_buy_id, "拼单")
        group_buy_item_id = _normalize_required_text(
            payload.get("groupBuyItemId")
            if "groupBuyItemId" in payload
            else payload.get("group_buy_item_id"),
            "拼单商品",
        )
        member_user_id = _normalize_optional_text(
            payload.get("memberUserId")
            if "memberUserId" in payload
            else payload.get("member_user_id"),
            "成员",
        ) or actor_user_id
        quantity = _normalize_positive_int(payload.get("quantity"), "数量")
        note = _normalize_optional_text(payload.get("note"), "备注")
        source = _normalize_optional_text(payload.get("source"), "source")
        if source is None:
            source = DEFAULT_RECORD_SOURCE if actor_user_id == member_user_id else "maintainer_create"

        with connect(self.config) as conn:
            group_buy_item = self._require_group_buy_item_in_connection(conn, group_buy_item_id, lock=True)
            group_buy_id = group_buy_item["groupBuyId"]
            if payload_group_buy_id is not None and payload_group_buy_id != group_buy_id:
                raise AppError(400, "拼单商品不属于当前拼单", "VALIDATION_FAILED")
            group_buy = self._require_group_buy_in_connection(conn, group_buy_id, lock=True)
            self._assert_group_access(actor_user_id, group_buy["groupId"])
            self._require_user(member_user_id, "成员")
            self._assert_can_create_for_member(actor_user_id, member_user_id)
            if group_buy["status"] not in CLAIMABLE_GROUP_BUY_STATUSES:
                raise AppError(400, "当前拼单状态暂时不能认领", "INVALID_STATUS")
            if quantity > group_buy_item["availableQuantity"]:
                raise AppError(400, "可认领数量不足", "INSUFFICIENT_STOCK")

            item_after_claim = self.repo.update_group_buy_item_claimed_delta(
                conn,
                group_buy_item_id=group_buy_item_id,
                delta_quantity=quantity,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="group_buy_item.claim_stock",
                object_type="group_buy_item",
                object_id=group_buy_item_id,
                before=group_buy_item,
                after=item_after_claim,
                reason=f"成员 {member_user_id} 认领 {quantity} 件",
            )

            existing_record = self.repo.get_record_for_member(
                conn,
                group_buy_item_id=group_buy_item_id,
                member_user_id=member_user_id,
                lock=True,
            )
            if existing_record is None:
                record = self.repo.create_record(
                    conn,
                    group_buy_id=group_buy_id,
                    group_buy_item_id=group_buy_item_id,
                    member_user_id=member_user_id,
                    quantity=quantity,
                    status=GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT,
                    status_priority=_status_priority(GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT),
                    note=note,
                    source=source,
                )
                self._audit(
                    conn,
                    actor_user_id=actor_user_id,
                    action="record.create",
                    object_type="group_buy_record",
                    object_id=record["id"],
                    before=None,
                    after=record,
                    reason="成员认领商品" if actor_user_id == member_user_id else "维护人代成员建单",
                )
            else:
                before = clone(existing_record)
                record = self.repo.update_record_quantity(
                    conn,
                    group_buy_record_id=existing_record["id"],
                    quantity=existing_record["quantity"] + quantity,
                )
                self._audit(
                    conn,
                    actor_user_id=actor_user_id,
                    action="record.update_quantity",
                    object_type="group_buy_record",
                    object_id=record["id"],
                    before=before,
                    after=record,
                    reason="成员追加认领" if actor_user_id == member_user_id else "维护人代成员追加认领",
                )

            if record.get("goodsChargeId") is None:
                charge_id = self._create_initial_goods_charge(
                    conn,
                    record,
                    group_buy=group_buy,
                    item=group_buy_item,
                    quantity_for_charge=quantity,
                    actor_user_id=actor_user_id,
                )
                if charge_id:
                    record = self.repo.link_charge(
                        conn,
                        group_buy_record_id=record["id"],
                        charge_type=CHARGE_TYPE_INITIAL_GOODS,
                        charge_id=charge_id,
                    )
                    self._audit(
                        conn,
                        actor_user_id=actor_user_id,
                        action="record.link_charge",
                        object_type="group_buy_record",
                        object_id=record["id"],
                        before={**record, "goodsChargeId": None},
                        after=record,
                        reason="关联商品首款费用",
                    )

            record = self._recalculate_record_status_in_connection(
                conn,
                record["id"],
                actor_user_id=actor_user_id,
                reason="认领后重新计算状态",
                write_audit=True,
            )
            conn.commit()

        return {
            "groupBuyRecordId": record["id"],
            "recordId": record["id"],
            "status": record["status"],
            "displayStatus": record["displayStatus"],
            "quantity": record["quantity"],
            "availableQuantity": item_after_claim["availableQuantity"],
        }

    def create_transfer_record(
        self,
        *,
        source_record: dict[str, Any],
        to_user_id: str,
        quantity: int,
        transfer_id: str,
        actor_user_id: str,
        note: str | None,
    ) -> dict[str, Any]:
        # 审核转单时创建受让方记录，付款凭证不从原记录继承。
        with connect(self.config) as conn:
            created = self.create_transfer_record_in_connection(
                conn,
                source_record=source_record,
                to_user_id=to_user_id,
                quantity=quantity,
                transfer_id=transfer_id,
                actor_user_id=actor_user_id,
                note=note,
            )
            conn.commit()
        return created

    def create_transfer_record_in_connection(
        self,
        conn,
        *,
        source_record: dict[str, Any],
        to_user_id: str,
        quantity: int,
        transfer_id: str,
        actor_user_id: str,
        note: str | None,
    ) -> dict[str, Any]:
        # 供转单模块在同一事务内创建受让记录。
        self._require_user(to_user_id, "转入成员")
        existing_target_record = self.repo.get_record_for_member(
            conn,
            group_buy_item_id=source_record["groupBuyItemId"],
            member_user_id=to_user_id,
            lock=True,
        )
        if existing_target_record is not None:
            raise AppError(400, "受让成员已认领同一商品，当前不支持转单合并记录", "DUPLICATED_OPERATION")
        status = self._calculate_status(
            source_record,
            self._require_group_buy_in_connection(conn, source_record["groupBuyId"]),
            self.repo.get_record_facts(conn, source_record["id"]),
        )
        record = self.repo.create_transfer_record(
            conn,
            source_record=source_record,
            to_user_id=to_user_id,
            quantity=quantity,
            transfer_id=transfer_id,
            status=status,
            status_priority=_status_priority(status),
            note=note,
        )
        record = self._recalculate_record_status_in_connection(
            conn,
            record["id"],
            actor_user_id=actor_user_id,
            reason=note or "转单生成受让记录",
            write_audit=False,
        )
        self._audit(
            conn,
            actor_user_id=actor_user_id,
            action="record.transfer_in",
            object_type="group_buy_record",
            object_id=record["id"],
            before=None,
            after=record,
            reason=note or "转单生成受让记录",
        )
        return record

    def update_record_quantity(self, actor_user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 手动修改记录数量，同时修正商品库存汇总。
        actor_user_id = _normalize_required_text(actor_user.get("id"), "actorUserId")
        record_id = _normalize_required_text(
            payload.get("groupBuyRecordId")
            if "groupBuyRecordId" in payload
            else payload.get("group_buy_record_id"),
            "拼单记录",
        )
        quantity = _normalize_positive_int(payload.get("quantity"), "数量")
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)

        with connect(self.config) as conn:
            record = self._require_record_in_connection(conn, record_id, lock=True)
            self._assert_can_manage_record(actor_user_id, record)
            item = self._require_group_buy_item_in_connection(conn, record["groupBuyItemId"], lock=True)
            delta = quantity - record["quantity"]
            if delta:
                self.repo.update_group_buy_item_claimed_delta(
                    conn,
                    group_buy_item_id=item["id"],
                    delta_quantity=delta,
                )
            before = clone(record)
            updated = self.repo.update_record_quantity(conn, group_buy_record_id=record_id, quantity=quantity)
            updated = self._recalculate_record_status_in_connection(
                conn,
                record_id,
                actor_user_id=actor_user_id,
                reason=reason,
                write_audit=False,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="record.update_quantity",
                object_type="group_buy_record",
                object_id=record_id,
                before=before,
                after=updated,
                reason=reason,
            )
            conn.commit()
        return {"groupBuyRecordId": record_id, "quantity": updated["quantity"], "status": updated["status"]}

    def link_charge(self, payload: dict[str, Any], *, actor_user_id: str | None = None) -> dict[str, Any]:
        # 关联商品首款、国际款或国内运费后重算展示状态。
        record_id = _normalize_required_text(
            payload.get("groupBuyRecordId")
            if "groupBuyRecordId" in payload
            else payload.get("group_buy_record_id"),
            "拼单记录",
        )
        raw_charge_type = _normalize_required_text(
            payload.get("chargeType") if "chargeType" in payload else payload.get("charge_type"),
            "chargeType",
        )
        charge_type = CHARGE_TYPE_ALIASES.get(raw_charge_type, raw_charge_type)
        if charge_type not in ALLOWED_CHARGE_TYPES:
            raise AppError(400, "chargeType 不支持", "VALIDATION_FAILED")
        charge_id = _normalize_required_text(
            payload.get("chargeId") if "chargeId" in payload else payload.get("charge_id"),
            "费用",
        )

        with connect(self.config) as conn:
            before = self._require_record_in_connection(conn, record_id, lock=True)
            self.repo.require_charge(conn, charge_id)
            linked = self.repo.link_charge(
                conn,
                group_buy_record_id=record_id,
                charge_type=charge_type,
                charge_id=charge_id,
            )
            after = self._recalculate_record_status_in_connection(
                conn,
                record_id,
                actor_user_id=actor_user_id,
                reason=f"关联 {charge_type} 费用后重算状态",
                write_audit=False,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="record.link_charge",
                object_type="group_buy_record",
                object_id=record_id,
                before=before,
                after=after,
                reason=f"关联 {charge_type} 费用",
            )
            conn.commit()
        return {"groupBuyRecordId": linked["id"], "status": after["status"]}

    def link_charge_in_connection(
        self,
        conn,
        *,
        group_buy_record_id: str,
        charge_type: str,
        charge_id: str,
        actor_user_id: str | None,
        reason: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # 供其他 DB 模块在现有事务中关联费用。
        before = self._require_record_in_connection(conn, group_buy_record_id, lock=True)
        self.repo.link_charge(
            conn,
            group_buy_record_id=group_buy_record_id,
            charge_type=charge_type,
            charge_id=charge_id,
        )
        after = self._recalculate_record_status_in_connection(
            conn,
            group_buy_record_id,
            actor_user_id=actor_user_id,
            reason=reason,
            write_audit=False,
        )
        return before, after

    def link_payment_proof(self, payload: dict[str, Any], *, actor_user_id: str | None = None) -> dict[str, Any]:
        # 关联确认后的付款凭证，并按 charges.status 重新计算状态。
        record_id = _normalize_required_text(
            payload.get("groupBuyRecordId")
            if "groupBuyRecordId" in payload
            else payload.get("group_buy_record_id"),
            "拼单记录",
        )
        payment_type = _normalize_required_text(
            payload.get("paymentType") if "paymentType" in payload else payload.get("payment_type"),
            "paymentType",
        )
        if payment_type not in ALLOWED_PAYMENT_TYPES:
            raise AppError(400, "paymentType 不支持", "VALIDATION_FAILED")
        proof_id = _normalize_required_text(
            payload.get("paymentProofId")
            if "paymentProofId" in payload
            else payload.get("payment_proof_id"),
            "付款凭证",
        )

        with connect(self.config) as conn:
            before, after = self.link_payment_proof_in_connection(
                conn,
                group_buy_record_id=record_id,
                payment_type=payment_type,
                payment_proof_id=proof_id,
                actor_user_id=actor_user_id,
                reason=f"关联 {payment_type} 付款凭证",
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="record.link_payment_proof",
                object_type="group_buy_record",
                object_id=record_id,
                before=before,
                after=after,
                reason=f"关联 {payment_type} 付款凭证",
            )
            conn.commit()
        return {"groupBuyRecordId": record_id, "status": after["status"]}

    def link_payment_proof_in_connection(
        self,
        conn,
        *,
        group_buy_record_id: str,
        payment_type: str,
        payment_proof_id: str,
        actor_user_id: str | None,
        reason: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # 供费用确认流程在同一事务内关联凭证并重算状态。
        before = self._require_record_in_connection(conn, group_buy_record_id, lock=True)
        self.repo.require_payment_proof(conn, payment_proof_id)
        self.repo.link_payment_proof(
            conn,
            group_buy_record_id=group_buy_record_id,
            payment_type=payment_type,
            payment_proof_id=payment_proof_id,
        )
        after = self._recalculate_record_status_in_connection(
            conn,
            group_buy_record_id,
            actor_user_id=actor_user_id,
            reason=reason,
            write_audit=False,
        )
        return before, after

    def mark_ordered(self, payload: dict[str, Any], *, actor_user_id: str | None = None) -> dict[str, Any]:
        # 下单事实由订单截图表提供，这里只触发状态重算。
        record_ids = self._normalize_record_id_list(payload.get("groupBuyRecordIds"))
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)
        return self._recalculate_many(record_ids, actor_user_id=actor_user_id, reason=reason, action="record.mark_ordered")

    def mark_ordered_in_connection(
        self,
        conn,
        record_ids: list[str],
        *,
        actor_user_id: str | None,
        reason: str,
    ) -> dict[str, Any]:
        # 给订单物流模块在同一事务里触发下单状态重算。
        return self._recalculate_many_in_connection(
            conn,
            record_ids,
            actor_user_id=actor_user_id,
            reason=reason,
            action="record.mark_ordered",
        )

    def mark_stocked(self, payload: dict[str, Any], *, actor_user_id: str | None = None) -> dict[str, Any]:
        # 入库事实由 stock_items 提供，这里只触发状态重算。
        record_ids = self._normalize_record_id_list(payload.get("groupBuyRecordIds"))
        return self._recalculate_many(record_ids, actor_user_id=actor_user_id, reason="国内囤货入库", action="record.mark_stocked")

    def mark_stocked_in_connection(
        self,
        conn,
        record_ids: list[str],
        *,
        actor_user_id: str | None,
        reason: str,
    ) -> dict[str, Any]:
        # 给仓库/订单物流在同一事务里触发入库状态重算。
        return self._recalculate_many_in_connection(
            conn,
            record_ids,
            actor_user_id=actor_user_id,
            reason=reason,
            action="record.mark_stocked",
        )

    def enter_transfer_flow(self, payload: dict[str, Any], *, actor_user_id: str | None = None) -> dict[str, Any]:
        # 转运流程事实由国际批次关联提供，这里只触发状态重算。
        record_ids = self._normalize_record_id_list(payload.get("groupBuyRecordIds"))
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)
        return self._recalculate_many(record_ids, actor_user_id=actor_user_id, reason=reason, action="record.enter_transfer_flow")

    def enter_transfer_flow_in_connection(
        self,
        conn,
        record_ids: list[str],
        *,
        actor_user_id: str | None,
        reason: str,
    ) -> dict[str, Any]:
        # 给订单物流模块在同一事务里触发转运状态重算。
        return self._recalculate_many_in_connection(
            conn,
            record_ids,
            actor_user_id=actor_user_id,
            reason=reason,
            action="record.enter_transfer_flow",
        )

    def mark_dispatch_requested(self, payload: dict[str, Any], *, actor_user_id: str | None = None) -> dict[str, Any]:
        # 排发申请 ID 是主表关键外键，写入后重算状态。
        record_ids = self._normalize_record_id_list(payload.get("groupBuyRecordIds"))
        dispatch_request_id = _normalize_required_text(
            payload.get("dispatchRequestId")
            if "dispatchRequestId" in payload
            else payload.get("dispatch_request_id"),
            "排发申请",
        )
        updated_count = 0
        with connect(self.config) as conn:
            for record_id in record_ids:
                before = self._require_record_in_connection(conn, record_id, lock=True)
                if self.repo.dispatch_request_exists(conn, dispatch_request_id):
                    self.repo.mark_dispatch_requested(
                        conn,
                        group_buy_record_id=record_id,
                        dispatch_request_id=dispatch_request_id,
                    )
                after = self._recalculate_record_status_in_connection(
                    conn,
                    record_id,
                    actor_user_id=actor_user_id,
                    reason="创建排发申请",
                    write_audit=False,
                    fact_overrides={"dispatchRequested": True},
                )
                self._audit(
                    conn,
                    actor_user_id=actor_user_id,
                    action="record.mark_dispatch_requested",
                    object_type="group_buy_record",
                    object_id=record_id,
                    before=before,
                    after=after,
                    reason="创建排发申请",
                )
                updated_count += 1
            conn.commit()
        return {"updatedCount": updated_count}

    def mark_dispatched(self, payload: dict[str, Any], *, actor_user_id: str | None = None) -> dict[str, Any]:
        # 发货事实由排发和国内快递表提供，这里只触发状态重算。
        record_ids = self._normalize_record_id_list(payload.get("groupBuyRecordIds"))
        return self._recalculate_many(record_ids, actor_user_id=actor_user_id, reason="录入国内快递", action="record.mark_dispatched")

    def mark_completed(self, payload: dict[str, Any], *, actor_user_id: str | None = None) -> dict[str, Any]:
        # 完结事实由排发申请/库存状态提供，这里只触发状态重算。
        record_ids = self._normalize_record_id_list(payload.get("groupBuyRecordIds"))
        return self._recalculate_many(record_ids, actor_user_id=actor_user_id, reason="排发完成", action="record.mark_completed")

    def mark_dispatch_requested_in_connection(
        self,
        conn,
        record_ids: list[str],
        *,
        dispatch_request_id: str,
        actor_user_id: str | None,
        reason: str,
    ) -> dict[str, Any]:
        # 给仓库排发模块在同一事务里写入排发申请 ID 并重算状态。
        updated_count = 0
        for record_id in record_ids:
            before = self._require_record_in_connection(conn, record_id, lock=True)
            self.repo.mark_dispatch_requested(
                conn,
                group_buy_record_id=record_id,
                dispatch_request_id=dispatch_request_id,
            )
            after = self._recalculate_record_status_in_connection(
                conn,
                record_id,
                actor_user_id=actor_user_id,
                reason=reason,
                write_audit=False,
                fact_overrides={"dispatchRequested": True},
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="record.mark_dispatch_requested",
                object_type="group_buy_record",
                object_id=record_id,
                before=before,
                after=after,
                reason=reason,
            )
            updated_count += 1
        return {"updatedCount": updated_count}

    def mark_dispatched_in_connection(
        self,
        conn,
        record_ids: list[str],
        *,
        actor_user_id: str | None,
        reason: str,
    ) -> dict[str, Any]:
        # 给仓库排发模块在同一事务里触发已发货状态重算。
        return self._recalculate_many_in_connection(
            conn,
            record_ids,
            actor_user_id=actor_user_id,
            reason=reason,
            action="record.mark_dispatched",
        )

    def mark_completed_in_connection(
        self,
        conn,
        record_ids: list[str],
        *,
        actor_user_id: str | None,
        reason: str,
    ) -> dict[str, Any]:
        # 给仓库排发模块在同一事务里触发完成状态重算。
        return self._recalculate_many_in_connection(
            conn,
            record_ids,
            actor_user_id=actor_user_id,
            reason=reason,
            action="record.mark_completed",
        )

    def mark_transfer_pending_in_connection(
        self,
        conn,
        *,
        group_buy_record_id: str,
        transfer_id: str,
        actor_user_id: str,
        reason: str,
    ) -> dict[str, Any]:
        # 转单申请创建后写入当前 transfer_id。
        before = self._require_record_in_connection(conn, group_buy_record_id, lock=True)
        self.repo.update_transfer_link(conn, group_buy_record_id=group_buy_record_id, transfer_id=transfer_id)
        after = self._recalculate_record_status_in_connection(
            conn,
            group_buy_record_id,
            actor_user_id=actor_user_id,
            reason=reason,
            write_audit=False,
        )
        self._audit(
            conn,
            actor_user_id=actor_user_id,
            action="record.request_transfer",
            object_type="group_buy_record",
            object_id=group_buy_record_id,
            before=before,
            after=after,
            reason=reason,
        )
        return after

    def release_transfer_pending_in_connection(
        self,
        conn,
        *,
        group_buy_record_id: str,
        transfer_id: str,
        actor_user_id: str,
        reason: str,
    ) -> dict[str, Any]:
        # 转单被驳回或转出完成后清空当前 transfer_id。
        before = self._require_record_in_connection(conn, group_buy_record_id, lock=True)
        if before.get("transferId") != transfer_id:
            return before
        self.repo.update_transfer_link(conn, group_buy_record_id=group_buy_record_id, transfer_id=None)
        after = self._recalculate_record_status_in_connection(
            conn,
            group_buy_record_id,
            actor_user_id=actor_user_id,
            reason=reason,
            write_audit=False,
        )
        self._audit(
            conn,
            actor_user_id=actor_user_id,
            action="record.reject_transfer",
            object_type="group_buy_record",
            object_id=group_buy_record_id,
            before=before,
            after=after,
            reason=reason,
        )
        return after

    def transfer_out_in_connection(
        self,
        conn,
        *,
        group_buy_record_id: str,
        transfer_id: str,
        quantity: int,
        actor_user_id: str,
        reason: str,
    ) -> dict[str, Any]:
        # 审核通过后扣减原记录数量，并释放被转出的商品库存占用。
        before = self._require_record_in_connection(conn, group_buy_record_id, lock=True)
        remaining_quantity = before["quantity"] - quantity
        if remaining_quantity < 0:
            raise AppError(400, "转单数量不能超过原记录数量", "VALIDATION_FAILED")
        if remaining_quantity == 0:
            raise AppError(400, "现有数据库约束不支持全量转出，请至少保留 1 件在原记录", "VALIDATION_FAILED")
        updated = self.repo.update_record_quantity(
            conn,
            group_buy_record_id=group_buy_record_id,
            quantity=remaining_quantity,
        )
        self.repo.update_transfer_link(conn, group_buy_record_id=group_buy_record_id, transfer_id=None)
        after = self._recalculate_record_status_in_connection(
            conn,
            group_buy_record_id,
            actor_user_id=actor_user_id,
            reason=reason,
            write_audit=False,
        )
        self._audit(
            conn,
            actor_user_id=actor_user_id,
            action="record.transfer_out",
            object_type="group_buy_record",
            object_id=group_buy_record_id,
            before=before,
            after=after,
            reason=reason,
        )
        return after

    def mark_exception(self, group_buy_record_id: str, *, actor_user_id: str, exception_reason: str, note: str | None) -> dict[str, Any]:
        # DB 版异常标记入口，供 AppContext 接入。
        with connect(self.config) as conn:
            before = self._require_record_in_connection(conn, group_buy_record_id, lock=True)
            updated = self.repo.update_exception(
                conn,
                group_buy_record_id=group_buy_record_id,
                is_exception=True,
                exception_reason=exception_reason,
                note=note,
            )
            after = self._recalculate_record_status_in_connection(
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
        return {"groupBuyRecordId": updated["id"], "isException": after["isException"]}

    def resolve_exception(self, group_buy_record_id: str, *, actor_user_id: str, resolution: str, note: str | None) -> dict[str, Any]:
        # DB 版异常解决入口，供 AppContext 接入。
        with connect(self.config) as conn:
            before = self._require_record_in_connection(conn, group_buy_record_id, lock=True)
            if not before.get("isException"):
                raise AppError(400, "拼单记录当前没有异常需要解决", "INVALID_STATUS")
            updated = self.repo.update_exception(
                conn,
                group_buy_record_id=group_buy_record_id,
                is_exception=False,
                exception_reason=None,
                note=note,
            )
            after = self._recalculate_record_status_in_connection(
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
        return {"groupBuyRecordId": updated["id"], "isException": after["isException"]}

    def recalculate_display_status(self, payload: dict[str, Any], *, actor_user_id: str | None = None) -> dict[str, Any]:
        # 主动按事实重算单条记录展示状态。
        record_id = _normalize_required_text(
            payload.get("groupBuyRecordId")
            if "groupBuyRecordId" in payload
            else payload.get("group_buy_record_id"),
            "拼单记录",
        )
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)
        with connect(self.config) as conn:
            before = self._require_record_in_connection(conn, record_id, lock=True)
            after = self._recalculate_record_status_in_connection(
                conn,
                record_id,
                actor_user_id=actor_user_id,
                reason=reason,
                write_audit=False,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="record.recalculate_status",
                object_type="group_buy_record",
                object_id=record_id,
                before=before,
                after=after,
                reason=reason,
            )
            conn.commit()
        return {
            "groupBuyRecordId": record_id,
            "oldStatus": before["status"],
            "newStatus": after["status"],
            "statusPriority": after["statusPriority"],
            "isDispatchable": self._is_dispatchable_in_connection(conn=None, record=after),
        }

    def build_record_summary(self, record: dict[str, Any]) -> dict[str, Any]:
        # 构建记录摘要；若记录来自 DB，会再查事实补充可排发状态。
        with connect(self.config) as conn:
            summary = self._build_record_summary_in_connection(conn, record)
            conn.rollback()
        return summary

    def _audit(self, conn, *, actor_user_id: str | None, action: str, object_type: str, object_id: str, before: Any, after: Any, reason: str | None) -> None:
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

    def _require_user(self, user_id: str, field_name: str) -> None:
        # 校验用户存在。
        if self.get_user_snapshot_by_id is not None and self.get_user_snapshot_by_id(user_id) is None:
            raise AppError(404, f"{field_name}不存在", "NOT_FOUND")

    def _assert_group_access(self, actor_user_id: str, group_id: str) -> None:
        # 校验用户可访问团购所属群。
        if self.has_group_access is not None and not self.has_group_access(actor_user_id, group_id):
            raise AppError(404, "拼团不存在", "NOT_FOUND")

    def _has_permission(self, actor_user_id: str, permission: str) -> bool:
        # 权限回调缺省时保持迁移期宽松。
        if self.has_permission_by_user_id is None:
            return True
        return self.has_permission_by_user_id(actor_user_id, permission)

    def _assert_can_create_for_member(self, actor_user_id: str, member_user_id: str) -> None:
        # 普通成员只能给自己认领，维护人可以代成员建单。
        if actor_user_id == member_user_id:
            if not self._has_permission(actor_user_id, "record:create_self"):
                raise AppError(403, "当前账号没有认领权限", "FORBIDDEN")
            return
        if not self._has_permission(actor_user_id, "record:create_for_member"):
            raise AppError(403, "当前账号没有代成员建单的权限", "FORBIDDEN")

    def _assert_can_manage_record(self, actor_user_id: str, record: dict[str, Any]) -> None:
        # 判断是否可修改指定记录。
        if actor_user_id == record["memberUserId"] and self._has_permission(actor_user_id, "record:create_self"):
            return
        if self._has_permission(actor_user_id, "record:create_for_member"):
            return
        raise AppError(403, "当前账号没有修改拼单记录的权限", "FORBIDDEN")

    def _require_group_buy_in_connection(self, conn, group_buy_id: str, *, lock: bool = False) -> dict[str, Any]:
        # 事务内读取团购。
        group_buy = self.repo.get_group_buy_by_id(conn, group_buy_id, lock=lock)
        if group_buy is None:
            raise AppError(404, "拼团不存在", "NOT_FOUND")
        return group_buy

    def _require_group_buy_item_in_connection(self, conn, group_buy_item_id: str, *, lock: bool = False) -> dict[str, Any]:
        # 事务内读取团购商品。
        item = self.repo.get_group_buy_item_by_id(conn, group_buy_item_id, lock=lock)
        if item is None:
            raise AppError(404, "拼团商品不存在", "NOT_FOUND")
        return item

    def _require_record_in_connection(self, conn, group_buy_record_id: str, *, lock: bool = False) -> dict[str, Any]:
        # 事务内读取拼单记录。
        record = self.repo.get_record_by_id(conn, group_buy_record_id, lock=lock)
        if record is None:
            raise AppError(404, "拼单记录不存在", "NOT_FOUND")
        return record

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

    def _create_initial_goods_charge(
        self,
        conn,
        record: dict[str, Any],
        *,
        group_buy: dict[str, Any],
        item: dict[str, Any],
        quantity_for_charge: int,
        actor_user_id: str,
    ) -> str | None:
        # 在认领事务里创建商品首款费用。
        if self.create_charge is None or not group_buy.get("ownerUserId"):
            return None
        unit_price = Decimal(str(item["unitPriceCny"]))
        amount_cny = f"{(unit_price * Decimal(quantity_for_charge)).quantize(Decimal('0.00'))}"
        result = self.create_charge(
            conn,
            {
                "type": CHARGE_TYPE_INITIAL_GOODS,
                "payerUserId": record["memberUserId"],
                "payeeUserId": group_buy["ownerUserId"],
                "bizType": "group_buy_record",
                "bizId": record["id"],
                "amountCny": amount_cny,
                "paymentChannelId": group_buy.get("paymentChannelId"),
                "snapshot": {
                    "groupBuyRecordId": record["id"],
                    "groupBuyId": record["groupBuyId"],
                    "groupBuyItemId": record["groupBuyItemId"],
                    "quantity": quantity_for_charge,
                    "unitPriceCny": item["unitPriceCny"],
                },
                "note": "商品首款",
                "actorUserId": actor_user_id,
            },
        )
        return result.get("chargeId")

    def _needs_international_fee(self, group_buy: dict[str, Any]) -> bool:
        # 判断团购类型是否需要国际款。
        return group_buy.get("type") not in GROUP_BUY_TYPES_WITHOUT_INTERNATIONAL

    def _needs_transfer(self, group_buy: dict[str, Any]) -> bool:
        # 需要国际款的类型默认也需要转运流程。
        return self._needs_international_fee(group_buy)

    def _needs_domestic_stock(self, group_buy: dict[str, Any]) -> bool:
        # 群友出物不强制国内入库。
        return group_buy.get("type") not in GROUP_BUY_TYPES_WITHOUT_STOCKING

    def _calculate_status(self, record: dict[str, Any], group_buy: dict[str, Any], facts: dict[str, Any]) -> str:
        # 按数据库事实推导当前展示状态。
        if facts["isTransferPending"]:
            return GROUP_BUY_RECORD_STATUS_TRANSFERRING
        if facts["isCompleted"]:
            return GROUP_BUY_RECORD_STATUS_COMPLETED
        if facts["isDispatched"]:
            return GROUP_BUY_RECORD_STATUS_DISPATCHED
        if facts["dispatchRequested"] or record.get("dispatchRequestId"):
            return GROUP_BUY_RECORD_STATUS_DISPATCH_REQUESTED
        if not facts["goodsPaidConfirmed"]:
            return GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT
        if self._needs_international_fee(group_buy) and not facts["internationalPaidConfirmed"]:
            return GROUP_BUY_RECORD_STATUS_PENDING_INTERNATIONAL_PAYMENT
        if self._needs_transfer(group_buy) and not facts["hasInternationalBatch"]:
            return GROUP_BUY_RECORD_STATUS_PENDING_TRANSFER
        if self._needs_domestic_stock(group_buy) and not facts["isStocked"]:
            return GROUP_BUY_RECORD_STATUS_PENDING_STOCK
        if self._is_ready_for_dispatch_status(record, group_buy, facts):
            return GROUP_BUY_RECORD_STATUS_DISPATCHABLE
        if facts["isOrdered"]:
            return GROUP_BUY_RECORD_STATUS_ORDERED
        return GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT

    def _is_ready_for_dispatch_status(self, record: dict[str, Any], group_buy: dict[str, Any], facts: dict[str, Any]) -> bool:
        # 判断记录是否已满足可排发的全部事实条件。
        if record.get("isException"):
            return False
        if facts["isTransferPending"]:
            return False
        if facts["dispatchRequested"] or facts["isDispatched"] or facts["isCompleted"] or record.get("dispatchRequestId"):
            return False
        if not facts["isOrdered"]:
            return False
        if not facts["goodsPaidConfirmed"]:
            return False
        if self._needs_international_fee(group_buy) and not facts["internationalPaidConfirmed"]:
            return False
        if self._needs_transfer(group_buy) and not facts["hasInternationalBatch"]:
            return False
        if self._needs_domestic_stock(group_buy) and not facts["isStocked"]:
            return False
        return True

    def _is_dispatchable_in_connection(self, conn, record: dict[str, Any]) -> bool:
        # 查询事实并判断是否可排发。
        if conn is None:
            with connect(self.config) as owned_conn:
                result = self._is_dispatchable_in_connection(owned_conn, record)
                owned_conn.rollback()
            return result
        group_buy = self._require_group_buy_in_connection(conn, record["groupBuyId"])
        facts = self.repo.get_record_facts(conn, record["id"])
        return self._is_ready_for_dispatch_status(record, group_buy, facts)

    def _recalculate_record_status_in_connection(
        self,
        conn,
        group_buy_record_id: str,
        *,
        actor_user_id: str | None,
        reason: str,
        write_audit: bool,
        fact_overrides: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        # 读取事实、计算状态并回写主表状态字段。
        before = self._require_record_in_connection(conn, group_buy_record_id, lock=True)
        group_buy = self._require_group_buy_in_connection(conn, before["groupBuyId"])
        facts = self.repo.get_record_facts(conn, group_buy_record_id)
        if fact_overrides:
            facts.update(fact_overrides)
        next_status = self._calculate_status(before, group_buy, facts)
        after = self.repo.update_status(
            conn,
            group_buy_record_id=group_buy_record_id,
            status=next_status,
            status_priority=_status_priority(next_status),
        )
        if write_audit:
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="record.recalculate_status",
                object_type="group_buy_record",
                object_id=group_buy_record_id,
                before=before,
                after=after,
                reason=reason,
            )
        return after

    def _recalculate_many(self, record_ids: list[str], *, actor_user_id: str | None, reason: str, action: str) -> dict[str, Any]:
        # 批量重算记录状态并写审计日志。
        with connect(self.config) as conn:
            result = self._recalculate_many_in_connection(
                conn,
                record_ids,
                actor_user_id=actor_user_id,
                reason=reason,
                action=action,
            )
            conn.commit()
        return result

    def _recalculate_many_in_connection(
        self,
        conn,
        record_ids: list[str],
        *,
        actor_user_id: str | None,
        reason: str,
        action: str,
    ) -> dict[str, Any]:
        # 在调用方事务内批量重算记录状态并写审计日志。
        fact_overrides_by_action = {
            "record.mark_ordered": {"isOrdered": True},
            "record.enter_transfer_flow": {"hasInternationalBatch": True},
            "record.mark_stocked": {"isStocked": True},
            "record.mark_dispatched": {"isDispatched": True},
            "record.mark_completed": {"isCompleted": True},
        }
        fact_overrides = fact_overrides_by_action.get(action)
        updated_count = 0
        for record_id in record_ids:
            before = self._require_record_in_connection(conn, record_id, lock=True)
            after = self._recalculate_record_status_in_connection(
                conn,
                record_id,
                actor_user_id=actor_user_id,
                reason=reason,
                write_audit=False,
                fact_overrides=fact_overrides,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action=action,
                object_type="group_buy_record",
                object_id=record_id,
                before=before,
                after=after,
                reason=reason,
            )
            updated_count += 1
        return {"updatedCount": updated_count}

    def _build_record_summary_in_connection(self, conn, record: dict[str, Any]) -> dict[str, Any]:
        # 给前端和下游模块构建包含 isDispatchable 的摘要。
        record = self._attach_derived_fields_in_connection(conn, record)
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
            "isDispatchable": self._is_dispatchable_in_connection(conn, record),
            "createdAt": record["createdAt"],
            "updatedAt": record["updatedAt"],
        }

    def _attach_derived_fields_in_connection(self, conn, record: dict[str, Any]) -> dict[str, Any]:
        # 迁移期 DTO 兼容字段，只从事实表推导，不写回 group_buy_records。
        group_buy = self._require_group_buy_in_connection(conn, record["groupBuyId"])
        facts = self.repo.get_record_facts(conn, record["id"])
        next_record = clone(record)
        next_record.update(
            {
                "goodsPaidConfirmed": facts["goodsPaidConfirmed"],
                "internationalPaidConfirmed": facts["internationalPaidConfirmed"],
                "needsInternationalFee": self._needs_international_fee(group_buy),
                "needsTransfer": self._needs_transfer(group_buy),
                "enteredTransferFlow": facts["hasInternationalBatch"],
                "needsDomesticStock": self._needs_domestic_stock(group_buy),
                "isOrdered": facts["isOrdered"],
                "isStocked": facts["isStocked"],
                "isTransferPending": facts["isTransferPending"],
                "isCompleted": facts["isCompleted"],
                "isTransferredOut": False,
                "transferredOutAt": None,
                "warehouseUserId": None,
                "stockedAt": None,
                "shipmentId": None,
                "completedAt": None,
                "orderedSourceObjectType": None,
                "orderedSourceObjectId": None,
                "orderedReason": None,
            }
        )
        return next_record
