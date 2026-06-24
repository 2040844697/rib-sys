from __future__ import annotations

import copy
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from ..config import Config
from ..db_access import connect
from ..errors import AppError
from ..file_audit import DatabaseAuditService, DatabaseFileService
from .charge_payment_repo import ChargePaymentRepository, cny_to_cent


CHARGE_STATUS_PENDING = "pending"
CHARGE_STATUS_SUBMITTED = "submitted"
CHARGE_STATUS_CONFIRMED = "confirmed"
CHARGE_STATUS_CANCELLED = "cancelled"
ALLOWED_CHARGE_STATUSES = {
    CHARGE_STATUS_PENDING,
    CHARGE_STATUS_SUBMITTED,
    CHARGE_STATUS_CONFIRMED,
    CHARGE_STATUS_CANCELLED,
}

PAYMENT_PROOF_STATUS_SUBMITTED = "submitted"
PAYMENT_PROOF_STATUS_CONFIRMED = "confirmed"
PAYMENT_PROOF_STATUS_REJECTED = "rejected"
ALLOWED_PAYMENT_PROOF_STATUSES = {
    PAYMENT_PROOF_STATUS_SUBMITTED,
    PAYMENT_PROOF_STATUS_CONFIRMED,
    PAYMENT_PROOF_STATUS_REJECTED,
}

PAYMENT_CHANNEL_STATUS_ACTIVE = "active"
PAYMENT_CHANNEL_STATUS_VOIDED = "voided"
ALLOWED_PAYMENT_CHANNEL_STATUSES = {
    PAYMENT_CHANNEL_STATUS_ACTIVE,
    PAYMENT_CHANNEL_STATUS_VOIDED,
}

CHARGE_TYPE_INITIAL_GOODS = "initial_goods"
CHARGE_TYPE_INTERNATIONAL = "international"
CHARGE_TYPE_DOMESTIC_SHIPPING = "domestic_shipping"
CHARGE_TYPE_ADJUSTMENT = "adjustment"
CHARGE_TYPE_REFUND = "refund"
ALLOWED_CHARGE_TYPES = {
    CHARGE_TYPE_INITIAL_GOODS,
    CHARGE_TYPE_INTERNATIONAL,
    CHARGE_TYPE_DOMESTIC_SHIPPING,
    CHARGE_TYPE_ADJUSTMENT,
    CHARGE_TYPE_REFUND,
}
CHARGE_TYPE_ALIASES = {
    "goods": CHARGE_TYPE_INITIAL_GOODS,
}
CHARGE_TYPE_TO_PAYMENT_TYPE = {
    CHARGE_TYPE_INITIAL_GOODS: "goods",
    CHARGE_TYPE_INTERNATIONAL: "international",
}


def clone(value: Any) -> Any:
    return copy.deepcopy(value)


def _normalize_required_text(value: Any, field_name: str, min_length: int = 1) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if len(normalized) < min_length:
        raise AppError(400, f"{field_name} is required", "VALIDATION_FAILED")
    return normalized


def _normalize_optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AppError(400, f"{field_name} format is invalid", "VALIDATION_FAILED")
    normalized = value.strip()
    return normalized or None


def _normalize_price_cny(
    value: Any,
    field_name: str,
    *,
    allow_zero: bool = False,
    allow_negative: bool = False,
) -> str:
    if isinstance(value, bool) or value in {None, ""}:
        raise AppError(400, f"{field_name} is required", "VALIDATION_FAILED")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AppError(400, f"{field_name} format is invalid", "VALIDATION_FAILED") from exc

    quantized = amount.quantize(Decimal("0.00"))
    if amount != quantized:
        raise AppError(400, f"{field_name} must have at most 2 decimals", "VALIDATION_FAILED")
    amount = quantized
    if allow_negative:
        if not allow_zero and amount == Decimal("0.00"):
            raise AppError(400, f"{field_name} cannot be 0", "VALIDATION_FAILED")
    else:
        if amount < 0:
            raise AppError(400, f"{field_name} cannot be negative", "VALIDATION_FAILED")
        if not allow_zero and amount == Decimal("0.00"):
            raise AppError(400, f"{field_name} must be greater than 0", "VALIDATION_FAILED")
    return f"{amount:.2f}"


def _normalize_datetime_text(value: Any, field_name: str) -> datetime:
    text = _normalize_required_text(value, field_name)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppError(400, f"{field_name} must be a valid datetime", "VALIDATION_FAILED") from exc


def _payload_get(payload: dict[str, Any], *keys: str) -> tuple[bool, Any]:
    for key in keys:
        if key in payload:
            return True, payload[key]
    return False, None


class ChargePaymentModule:
    def __init__(
        self,
        config: Config,
        *,
        repository: ChargePaymentRepository,
        audit_service: DatabaseAuditService,
        file_service: DatabaseFileService,
        has_permission_by_user_id: Callable[[str, str], bool],
        get_user_snapshot_by_id: Callable[[str], dict[str, Any] | None],
        on_charge_confirmed: Callable[..., dict[str, Any]] | None = None,
    ):
        self.config = config
        self.repository = repository
        self.audit_service = audit_service
        self.file_service = file_service
        self.has_permission_by_user_id = has_permission_by_user_id
        self.get_user_snapshot_by_id = get_user_snapshot_by_id
        self.on_charge_confirmed = on_charge_confirmed

    def count_pending_charges_for_user(self, payer_user_id: str) -> int:
        with connect(self.config) as conn:
            result = self.repository.count_pending_charges_for_user(conn, payer_user_id)
            conn.rollback()
        return result

    def require_payment_channel(self, payment_channel_id: str) -> dict[str, Any]:
        with connect(self.config) as conn:
            payment_channel = self.repository.get_payment_channel_by_id(conn, payment_channel_id)
            conn.rollback()
        if payment_channel is None:
            raise AppError(404, "payment channel not found", "NOT_FOUND")
        return payment_channel

    def require_charge(self, charge_id: str) -> dict[str, Any]:
        with connect(self.config) as conn:
            charge = self.repository.get_charge_by_id(conn, charge_id)
            conn.rollback()
        if charge is None:
            raise AppError(404, "charge not found", "NOT_FOUND")
        return charge

    def require_payment_proof(self, proof_id: str) -> dict[str, Any]:
        with connect(self.config) as conn:
            proof = self.repository.get_payment_proof_by_id(conn, proof_id)
            conn.rollback()
        if proof is None:
            raise AppError(404, "payment proof not found", "NOT_FOUND")
        return proof

    def list_payment_proof_allocations(self, proof_id: str) -> list[dict[str, Any]]:
        with connect(self.config) as conn:
            allocations = self.repository.list_payment_proof_allocations(conn, proof_id)
            conn.rollback()
        return allocations

    def create_charge_from_related_module(self, payload: dict[str, Any]) -> dict[str, Any]:
        actor_user_id = None
        if "actorUserId" in payload or "actor_user_id" in payload:
            _, raw_actor_user_id = _payload_get(payload, "actorUserId", "actor_user_id")
            actor_user_id = _normalize_optional_text(raw_actor_user_id, "actorUserId")

        normalized_payload = dict(payload)
        normalized_payload.pop("actorUserId", None)
        normalized_payload.pop("actor_user_id", None)
        return self.create_charge(normalized_payload, actor_user_id=actor_user_id)

    def create_charge_from_related_module_in_connection(
        self,
        conn,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 给其他 DB 模块在同一事务里创建费用，避免业务记录和费用记录半成功。
        actor_user_id = None
        if "actorUserId" in payload or "actor_user_id" in payload:
            _, raw_actor_user_id = _payload_get(payload, "actorUserId", "actor_user_id")
            actor_user_id = _normalize_optional_text(raw_actor_user_id, "actorUserId")

        normalized_payload = dict(payload)
        normalized_payload.pop("actorUserId", None)
        normalized_payload.pop("actor_user_id", None)
        return self.create_charge_in_connection(
            conn,
            normalized_payload,
            actor_user_id=actor_user_id,
        )

    def create_payment_channel(self, actor_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        owner_user_id = _normalize_required_text(
            payload.get("ownerUserId") if "ownerUserId" in payload else payload.get("owner_user_id"),
            "ownerUserId",
        )
        self._require_user(owner_user_id, "ownerUserId")
        self._require_user(actor_user_id, "actorUserId")
        if actor_user_id != owner_user_id and not self.has_permission_by_user_id(actor_user_id, "charge:adjust"):
            raise AppError(403, "current user cannot manage this payment channel", "FORBIDDEN")

        has_qr_file_object_id, raw_qr_file_object_id = _payload_get(
            payload,
            "qrFileObjectId",
            "qr_file_object_id",
        )
        qr_file_object_id = (
            _normalize_optional_text(raw_qr_file_object_id, "qrFileObjectId")
            if has_qr_file_object_id
            else None
        )
        qr_image_url = _normalize_optional_text(
            payload.get("qrImageUrl") if "qrImageUrl" in payload else payload.get("qr_image_url"),
            "qrImageUrl",
        )
        account_text = _normalize_optional_text(
            payload.get("accountText") if "accountText" in payload else payload.get("account_text"),
            "accountText",
        )
        if not qr_image_url and not account_text:
            raise AppError(400, "payment channel requires qrImageUrl or accountText", "VALIDATION_FAILED")

        with connect(self.config) as conn:
            if qr_file_object_id is not None:
                file_object = self.file_service.require_active_file_object(qr_file_object_id, conn=conn)
                if file_object.get("bucket") != "channels":
                    raise AppError(400, "payment channel QR file must be in channels bucket", "VALIDATION_FAILED")
                if qr_image_url and file_object.get("url") != qr_image_url:
                    raise AppError(400, "qrImageUrl does not match file object URL", "VALIDATION_FAILED")
                qr_image_url = qr_image_url or file_object.get("url")

            payment_channel = self.repository.create_payment_channel(
                conn,
                {
                    "owner_user_id": owner_user_id,
                    "type": _normalize_required_text(payload.get("type"), "type"),
                    "display_name": _normalize_required_text(
                        payload.get("displayName") if "displayName" in payload else payload.get("display_name"),
                        "displayName",
                        2,
                    ),
                    "qr_file_object_id": qr_file_object_id,
                    "qr_image_url": qr_image_url,
                    "account_text": account_text,
                    "note": _normalize_optional_text(payload.get("note"), "note"),
                },
            )
            self.audit_service.log_in_connection(
                conn,
                actor_user_id=actor_user_id,
                action="payment_channel.create",
                object_type="payment_channel",
                object_id=payment_channel["id"],
                before=None,
                after=payment_channel,
                reason="create payment channel",
            )
            conn.commit()

        return {"paymentChannelId": payment_channel["id"]}

    def create_charge(
        self,
        payload: dict[str, Any],
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        with connect(self.config) as conn:
            result = self.create_charge_in_connection(
                conn,
                payload,
                actor_user_id=actor_user_id,
            )
            conn.commit()

        return result

    def create_charge_in_connection(
        self,
        conn,
        payload: dict[str, Any],
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        # 费用创建本体不提交事务，调用方决定何时 commit。
        charge_type = self._normalize_charge_type(payload.get("type"))
        payer_user_id = _normalize_required_text(
            payload.get("payerUserId") if "payerUserId" in payload else payload.get("payer_user_id"),
            "payerUserId",
        )
        payee_user_id = _normalize_required_text(
            payload.get("payeeUserId") if "payeeUserId" in payload else payload.get("payee_user_id"),
            "payeeUserId",
        )
        self._require_user(payer_user_id, "payerUserId")
        self._require_user(payee_user_id, "payeeUserId")
        amount_cny = _normalize_price_cny(
            payload.get("amountCny") if "amountCny" in payload else payload.get("amount_cny"),
            "amountCny",
        )
        snapshot = self._normalize_snapshot(payload)

        charge = self.repository.create_charge(
            conn,
            {
                "type": charge_type,
                "payer_user_id": payer_user_id,
                "payee_user_id": payee_user_id,
                "biz_type": _normalize_required_text(
                    payload.get("bizType") if "bizType" in payload else payload.get("biz_type"),
                    "bizType",
                ),
                "biz_id": _normalize_required_text(
                    payload.get("bizId") if "bizId" in payload else payload.get("biz_id"),
                    "bizId",
                ),
                "amount_cny": amount_cny,
                "payment_channel_id": _normalize_optional_text(
                    payload.get("paymentChannelId")
                    if "paymentChannelId" in payload
                    else payload.get("payment_channel_id"),
                    "paymentChannelId",
                ),
                "snapshot": snapshot,
                "note": _normalize_optional_text(payload.get("note"), "note"),
            },
        )
        self.audit_service.log_in_connection(
            conn,
            actor_user_id=actor_user_id,
            action="charge.create",
            object_type="charge",
            object_id=charge["id"],
            before=None,
            after=charge,
            reason="create charge",
        )

        return {
            "chargeId": charge["id"],
            "status": charge["status"],
            "amountCny": charge["amountCny"],
        }

    def cancel_charge(self, actor_user_id: str, charge_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_permission(
            actor_user_id,
            "charge:adjust",
            error_message="current user cannot cancel charges",
        )
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)
        with connect(self.config) as conn:
            charge = self._require_charge_in_connection(conn, charge_id, lock=True)
            if charge["status"] == CHARGE_STATUS_CANCELLED:
                raise AppError(400, "charge is already cancelled", "DUPLICATED_OPERATION")
            if charge["status"] == CHARGE_STATUS_CONFIRMED:
                raise AppError(400, "confirmed charge cannot be cancelled directly", "INVALID_STATUS")
            if charge["status"] == CHARGE_STATUS_SUBMITTED:
                raise AppError(400, "submitted charge cannot be cancelled directly", "INVALID_STATUS")

            before = clone(charge)
            after = self.repository.update_charge(
                conn,
                charge_id=charge_id,
                updates={
                    "status": CHARGE_STATUS_CANCELLED,
                    "cancelled_reason": reason,
                },
            )
            self.audit_service.log_in_connection(
                conn,
                actor_user_id=actor_user_id,
                action="charge.cancel",
                object_type="charge",
                object_id=charge_id,
                before=before,
                after=after,
                reason=reason,
            )
            conn.commit()

        return {"chargeId": charge_id, "status": after["status"]}

    def submit_payment_proof(self, payload: dict[str, Any]) -> dict[str, Any]:
        submitted_by = _normalize_required_text(
            payload.get("submittedBy") if "submittedBy" in payload else payload.get("submitted_by"),
            "submittedBy",
        )
        from_user_id = _normalize_required_text(
            payload.get("fromUserId") if "fromUserId" in payload else payload.get("from_user_id"),
            "fromUserId",
        )
        to_user_id = _normalize_required_text(
            payload.get("toUserId") if "toUserId" in payload else payload.get("to_user_id"),
            "toUserId",
        )
        self._require_user(submitted_by, "submittedBy")
        self._require_user(from_user_id, "fromUserId")
        self._require_user(to_user_id, "toUserId")
        if submitted_by != from_user_id and not self.has_permission_by_user_id(submitted_by, "charge:adjust"):
            raise AppError(403, "current user cannot submit payment for this member", "FORBIDDEN")

        has_proof_file_object_id, raw_proof_file_object_id = _payload_get(
            payload,
            "proofFileObjectId",
            "proof_file_object_id",
        )
        proof_file_object_id = (
            _normalize_optional_text(raw_proof_file_object_id, "proofFileObjectId")
            if has_proof_file_object_id
            else None
        )
        proof_image_url = _normalize_optional_text(
            payload.get("proofImageUrl")
            if "proofImageUrl" in payload
            else payload.get("proof_image_url"),
            "proofImageUrl",
        )
        amount_cny = _normalize_price_cny(
            payload.get("amountCny") if "amountCny" in payload else payload.get("amount_cny"),
            "amountCny",
        )
        paid_at = _normalize_datetime_text(
            payload.get("paidAt") if "paidAt" in payload else payload.get("paid_at"),
            "paidAt",
        )

        with connect(self.config) as conn:
            if proof_file_object_id is not None:
                file_object = self.file_service.require_active_file_object(proof_file_object_id, conn=conn)
                if file_object.get("bucket") != "payments":
                    raise AppError(400, "payment proof file must be in payments bucket", "VALIDATION_FAILED")
                if proof_image_url and file_object.get("url") != proof_image_url:
                    raise AppError(400, "proofImageUrl does not match file object URL", "VALIDATION_FAILED")
                proof_image_url = proof_image_url or file_object.get("url")
            if proof_image_url is None:
                raise AppError(400, "proofImageUrl is required", "VALIDATION_FAILED")

            allocations, allocation_total_cent = self._normalize_proof_allocations(
                conn,
                payload.get("allocations") if "allocations" in payload else payload.get("allocation_items"),
                from_user_id=from_user_id,
                to_user_id=to_user_id,
            )
            if allocation_total_cent != cny_to_cent(amount_cny, "amountCny"):
                raise AppError(400, "payment amount must equal allocation total", "VALIDATION_FAILED")

            proof = self.repository.create_payment_proof(
                conn,
                {
                    "submitted_by": submitted_by,
                    "from_user_id": from_user_id,
                    "to_user_id": to_user_id,
                    "amount_cny": amount_cny,
                    "paid_at": paid_at,
                    "proof_file_object_id": proof_file_object_id,
                    "proof_image_url": proof_image_url,
                    "note": _normalize_optional_text(payload.get("note"), "note"),
                },
            )

            for allocation in allocations:
                charge = allocation["charge"]
                charge_before = clone(charge)
                self.repository.create_payment_proof_allocation(
                    conn,
                    proof_id=proof["id"],
                    charge_id=charge["id"],
                    allocated_amount_cny=allocation["allocatedAmountCny"],
                )
                charge_after = self.repository.update_charge(
                    conn,
                    charge_id=charge["id"],
                    updates={
                        "status": CHARGE_STATUS_SUBMITTED,
                        "submitted_proof_id": proof["id"],
                    },
                )
                self.audit_service.log_in_connection(
                    conn,
                    actor_user_id=submitted_by,
                    action="charge.submit_proof",
                    object_type="charge",
                    object_id=charge["id"],
                    before=charge_before,
                    after=charge_after,
                    reason=f"submit payment proof {proof['id']}",
                )

            self.audit_service.log_in_connection(
                conn,
                actor_user_id=submitted_by,
                action="payment_proof.submit",
                object_type="payment_proof",
                object_id=proof["id"],
                before=None,
                after={
                    **proof,
                    "chargeIds": [allocation["charge"]["id"] for allocation in allocations],
                },
                reason="submit payment proof",
            )
            conn.commit()

        return {"proofId": proof["id"], "status": proof["status"]}

    def confirm_payment_proof(
        self,
        actor_user_id: str,
        proof_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_permission(
            actor_user_id,
            "charge:confirm_payment",
            error_message="current user cannot confirm payment",
        )
        review_note = _normalize_optional_text(payload.get("note"), "note")

        with connect(self.config) as conn:
            proof = self._require_payment_proof_in_connection(conn, proof_id, lock=True)
            if proof["status"] != PAYMENT_PROOF_STATUS_SUBMITTED:
                raise AppError(400, "payment proof cannot be confirmed in current status", "INVALID_STATUS")

            proof_before = clone(proof)
            proof_after = self.repository.update_payment_proof(
                conn,
                proof_id=proof_id,
                updates={
                    "status": PAYMENT_PROOF_STATUS_CONFIRMED,
                    "reviewed_by": actor_user_id,
                    "reviewed_at": datetime.now().astimezone(),
                    "review_note": review_note,
                    "reject_reason": None,
                },
            )

            confirmed_charge_ids: list[str] = []
            linked_record_ids: set[str] = set()
            for allocation in self.repository.list_payment_proof_allocations(conn, proof_id):
                charge = self._require_charge_in_connection(conn, allocation["chargeId"], lock=True)
                if charge["status"] != CHARGE_STATUS_SUBMITTED or charge.get("submittedProofId") != proof_id:
                    raise AppError(400, "charge and payment proof status mismatch", "INVALID_STATUS")

                charge_before = clone(charge)
                charge_after = self.repository.update_charge(
                    conn,
                    charge_id=charge["id"],
                    updates={
                        "status": CHARGE_STATUS_CONFIRMED,
                        "confirmed_proof_id": proof_id,
                    },
                )
                confirmed_charge_ids.append(charge["id"])

                self.audit_service.log_in_connection(
                    conn,
                    actor_user_id=actor_user_id,
                    action="charge.confirm_payment",
                    object_type="charge",
                    object_id=charge["id"],
                    before=charge_before,
                    after=charge_after,
                    reason=review_note or "confirm payment proof",
                )

                payment_type = CHARGE_TYPE_TO_PAYMENT_TYPE.get(charge["type"])
                if payment_type is not None:
                    record_ids = self.repository.list_group_buy_record_ids_by_charge(conn, charge["id"])
                    for record_id in record_ids:
                        record_before, record_after = self.repository.link_group_buy_record_payment_proof(
                            conn,
                            group_buy_record_id=record_id,
                            payment_type=payment_type,
                            payment_proof_id=proof_id,
                        )
                        linked_record_ids.add(record_id)
                        self.audit_service.log_in_connection(
                            conn,
                            actor_user_id=actor_user_id,
                            action="record.link_payment_proof",
                            object_type="group_buy_record",
                            object_id=record_id,
                            before=record_before,
                            after=record_after,
                            reason=f"link {payment_type} payment proof",
                        )

                if self.on_charge_confirmed is not None:
                    self.on_charge_confirmed(
                        charge["id"],
                        proof_id=proof_id,
                        actor_user_id=actor_user_id,
                    )

            self.audit_service.log_in_connection(
                conn,
                actor_user_id=actor_user_id,
                action="payment_proof.confirm",
                object_type="payment_proof",
                object_id=proof_id,
                before=proof_before,
                after={
                    **proof_after,
                    "confirmedChargeIds": clone(confirmed_charge_ids),
                    "linkedRecordIds": sorted(linked_record_ids),
                },
                reason=review_note or "confirm payment proof",
            )
            conn.commit()

        return {"proofId": proof_id, "confirmedChargeIds": confirmed_charge_ids}

    def reject_payment_proof(
        self,
        actor_user_id: str,
        proof_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_permission(
            actor_user_id,
            "charge:confirm_payment",
            error_message="current user cannot reject payment",
        )
        reject_reason = _normalize_required_text(
            payload.get("rejectReason") if "rejectReason" in payload else payload.get("reject_reason"),
            "rejectReason",
            2,
        )

        with connect(self.config) as conn:
            proof = self._require_payment_proof_in_connection(conn, proof_id, lock=True)
            if proof["status"] != PAYMENT_PROOF_STATUS_SUBMITTED:
                raise AppError(400, "payment proof cannot be rejected in current status", "INVALID_STATUS")

            proof_before = clone(proof)
            proof_after = self.repository.update_payment_proof(
                conn,
                proof_id=proof_id,
                updates={
                    "status": PAYMENT_PROOF_STATUS_REJECTED,
                    "reviewed_by": actor_user_id,
                    "reviewed_at": datetime.now().astimezone(),
                    "review_note": None,
                    "reject_reason": reject_reason,
                },
            )

            for allocation in self.repository.list_payment_proof_allocations(conn, proof_id):
                charge = self._require_charge_in_connection(conn, allocation["chargeId"], lock=True)
                if charge["status"] == CHARGE_STATUS_CONFIRMED:
                    raise AppError(400, "confirmed charge cannot be reverted by rejecting proof", "INVALID_STATUS")
                charge_before = clone(charge)
                charge_after = self.repository.update_charge(
                    conn,
                    charge_id=charge["id"],
                    updates={
                        "status": CHARGE_STATUS_PENDING,
                        "submitted_proof_id": None,
                    },
                )
                self.audit_service.log_in_connection(
                    conn,
                    actor_user_id=actor_user_id,
                    action="charge.reject_proof",
                    object_type="charge",
                    object_id=charge["id"],
                    before=charge_before,
                    after=charge_after,
                    reason=reject_reason,
                )

            self.audit_service.log_in_connection(
                conn,
                actor_user_id=actor_user_id,
                action="payment_proof.reject",
                object_type="payment_proof",
                object_id=proof_id,
                before=proof_before,
                after=proof_after,
                reason=reject_reason,
            )
            conn.commit()

        return {"proofId": proof_id, "status": proof_after["status"]}

    def create_charge_adjustment(self, actor_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_permission(
            actor_user_id,
            "charge:adjust",
            error_message="current user cannot create charge adjustments",
        )
        charge_id = _normalize_required_text(
            payload.get("chargeId") if "chargeId" in payload else payload.get("charge_id"),
            "chargeId",
        )
        source_charge_id = _normalize_optional_text(
            payload.get("sourceChargeId")
            if "sourceChargeId" in payload
            else payload.get("source_charge_id"),
            "sourceChargeId",
        )

        with connect(self.config) as conn:
            self._require_charge_in_connection(conn, charge_id)
            if source_charge_id is not None:
                self._require_charge_in_connection(conn, source_charge_id)

            # The existing table only has approved_by. During this migration it stores
            # the actor who created the adjustment, equivalent to the legacy createdBy field.
            adjustment = self.repository.create_charge_adjustment(
                conn,
                {
                    "charge_id": charge_id,
                    "source_charge_id": source_charge_id,
                    "delta_cny": _normalize_price_cny(
                        payload.get("deltaCny") if "deltaCny" in payload else payload.get("delta_cny"),
                        "deltaCny",
                        allow_negative=True,
                    ),
                    "reason": _normalize_required_text(payload.get("reason"), "reason", 2),
                    "source_type": _normalize_required_text(
                        payload.get("sourceType") if "sourceType" in payload else payload.get("source_type"),
                        "sourceType",
                    ),
                    "source_id": _normalize_required_text(
                        payload.get("sourceId") if "sourceId" in payload else payload.get("source_id"),
                        "sourceId",
                    ),
                    "approved_by": actor_user_id,
                },
            )
            self.audit_service.log_in_connection(
                conn,
                actor_user_id=actor_user_id,
                action="charge_adjustment.create",
                object_type="charge_adjustment",
                object_id=adjustment["id"],
                before=None,
                after=adjustment,
                reason=adjustment["reason"],
            )
            conn.commit()

        return {"chargeAdjustmentId": adjustment["id"]}

    def _assert_permission(self, actor_user_id: str, permission: str, *, error_message: str) -> None:
        if not self.has_permission_by_user_id(actor_user_id, permission):
            raise AppError(403, error_message, "FORBIDDEN")

    def _normalize_charge_type(self, value: Any) -> str:
        normalized = _normalize_required_text(value, "type")
        normalized = CHARGE_TYPE_ALIASES.get(normalized, normalized)
        if normalized not in ALLOWED_CHARGE_TYPES:
            raise AppError(
                400,
                f"type only supports {', '.join(sorted(ALLOWED_CHARGE_TYPES))}",
                "VALIDATION_FAILED",
            )
        return normalized

    def _normalize_snapshot(self, payload: dict[str, Any]) -> Any:
        has_snapshot, raw_snapshot = _payload_get(payload, "snapshot", "snapshotJson", "snapshot_json")
        if not has_snapshot:
            return None
        try:
            json.dumps(raw_snapshot, ensure_ascii=False)
        except TypeError as exc:
            raise AppError(400, "snapshotJson must be valid JSON data", "VALIDATION_FAILED") from exc
        return clone(raw_snapshot)

    def _normalize_proof_allocations(
        self,
        conn,
        allocations_value: Any,
        *,
        from_user_id: str,
        to_user_id: str,
    ) -> tuple[list[dict[str, Any]], int]:
        if not isinstance(allocations_value, list) or not allocations_value:
            raise AppError(400, "allocations format is invalid", "VALIDATION_FAILED")

        normalized_allocations: list[dict[str, Any]] = []
        seen_charge_ids: set[str] = set()
        allocation_total_cent = 0
        for index, item in enumerate(allocations_value):
            if not isinstance(item, dict):
                raise AppError(400, f"allocations[{index}] format is invalid", "VALIDATION_FAILED")

            charge_id = _normalize_required_text(
                item.get("chargeId") if "chargeId" in item else item.get("charge_id"),
                f"allocations[{index}].chargeId",
            )
            if charge_id in seen_charge_ids:
                raise AppError(400, "same charge cannot be allocated twice", "DUPLICATED_OPERATION")
            charge = self._require_charge_in_connection(conn, charge_id, lock=True)
            if charge["status"] != CHARGE_STATUS_PENDING:
                raise AppError(400, "charge cannot submit payment proof in current status", "INVALID_STATUS")
            if charge["payerUserId"] != from_user_id or charge["payeeUserId"] != to_user_id:
                raise AppError(400, "payment proof parties do not match charge parties", "VALIDATION_FAILED")

            allocated_amount_cny = _normalize_price_cny(
                item.get("allocatedAmountCny")
                if "allocatedAmountCny" in item
                else item.get("allocated_amount_cny"),
                f"allocations[{index}].allocatedAmountCny",
            )
            if allocated_amount_cny != charge["amountCny"]:
                raise AppError(400, "payment proof must cover the whole charge for now", "VALIDATION_FAILED")

            seen_charge_ids.add(charge_id)
            allocation_total_cent += cny_to_cent(allocated_amount_cny, "allocatedAmountCny")
            normalized_allocations.append(
                {
                    "charge": charge,
                    "allocatedAmountCny": allocated_amount_cny,
                }
            )

        return normalized_allocations, allocation_total_cent

    def _require_user(self, user_id: str, field_name: str) -> None:
        if self.get_user_snapshot_by_id(user_id) is None:
            raise AppError(404, f"{field_name} user does not exist", "NOT_FOUND")

    def _require_charge_in_connection(
        self,
        conn,
        charge_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any]:
        charge = self.repository.get_charge_by_id(conn, charge_id, lock=lock)
        if charge is None:
            raise AppError(404, "charge not found", "NOT_FOUND")
        return charge

    def _require_payment_proof_in_connection(
        self,
        conn,
        proof_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any]:
        proof = self.repository.get_payment_proof_by_id(conn, proof_id, lock=lock)
        if proof is None:
            raise AppError(404, "payment proof not found", "NOT_FOUND")
        return proof
