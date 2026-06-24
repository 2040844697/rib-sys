from __future__ import annotations

import json
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ..config import Config
from ..db_access import to_iso
from ..errors import AppError
from ..group_buy_records.record_module import (
    GROUP_BUY_RECORD_STATUS_DISPATCH_REQUESTED,
    GROUP_BUY_RECORD_STATUS_ORDERED,
    GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT,
    GROUP_BUY_RECORD_STATUS_PENDING_INTERNATIONAL_PAYMENT,
    GROUP_BUY_RECORD_STATUS_PENDING_TRANSFER,
    GROUP_BUY_RECORD_STATUS_PRIORITY,
    GROUP_BUY_RECORD_STATUS_TRANSFERRING,
    GROUP_BUY_TYPES_WITHOUT_INTERNATIONAL,
)


CENT = Decimal("0.01")


def cny_to_cent(value: str, field_name: str = "amountCny") -> int:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AppError(400, f"{field_name} format is invalid", "VALIDATION_FAILED") from exc

    quantized = amount.quantize(CENT)
    if amount != quantized:
        raise AppError(400, f"{field_name} must have at most 2 decimals", "VALIDATION_FAILED")
    return int(quantized * 100)


def cent_to_cny(value: int | None) -> str | None:
    if value is None:
        return None
    sign = "-" if value < 0 else ""
    cents = abs(int(value))
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def _json_from_db(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def _status_priority(status: str) -> int:
    return GROUP_BUY_RECORD_STATUS_PRIORITY.get(
        status,
        GROUP_BUY_RECORD_STATUS_PRIORITY[GROUP_BUY_RECORD_STATUS_ORDERED],
    )


class ChargePaymentRepository:
    def __init__(self, config: Config):
        self.config = config

    def _dict_row(self):
        try:
            from psycopg.rows import dict_row
        except ModuleNotFoundError:
            return None

        return dict_row

    def _build_payment_channel(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "ownerUserId": row["owner_user_id"],
            "type": row["type"],
            "displayName": row["display_name"],
            "qrFileObjectId": row.get("qr_file_object_id"),
            "qrImageUrl": row.get("qr_image_url"),
            "accountText": row.get("account_text"),
            "note": row.get("note"),
            "status": row["status"],
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

    def _build_charge(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "type": row["type"],
            "payerUserId": row["payer_user_id"],
            "payeeUserId": row["payee_user_id"],
            "bizType": row["biz_type"],
            "bizId": row["biz_id"],
            "amountCny": cent_to_cny(row["amount_cny"]),
            "paymentChannelId": row.get("payment_channel_id"),
            "snapshot": _json_from_db(row.get("snapshot_json")),
            "note": row.get("note"),
            "status": row["status"],
            "submittedProofId": row.get("submitted_proof_id"),
            "confirmedProofId": row.get("confirmed_proof_id"),
            "cancelledReason": row.get("cancelled_reason"),
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

    def _build_payment_proof(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "submittedBy": row["submitted_by"],
            "fromUserId": row["from_user_id"],
            "toUserId": row["to_user_id"],
            "amountCny": cent_to_cny(row["amount_cny"]),
            "paidAt": to_iso(row.get("paid_at")),
            "proofFileObjectId": row.get("proof_file_object_id"),
            "proofImageUrl": row.get("proof_image_url"),
            "note": row.get("note"),
            "status": row["status"],
            "reviewedBy": row.get("reviewed_by"),
            "reviewedAt": to_iso(row.get("reviewed_at")),
            "reviewNote": row.get("review_note"),
            "rejectReason": row.get("reject_reason"),
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

    def _build_payment_proof_allocation(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "proofId": row["proof_id"],
            "chargeId": row["charge_id"],
            "allocatedAmountCny": cent_to_cny(row["allocated_amount_cny"]),
            "createdAt": to_iso(row.get("created_at")),
        }

    def _build_charge_adjustment(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "chargeId": row["charge_id"],
            "sourceChargeId": row.get("source_charge_id"),
            "deltaCny": cent_to_cny(row["delta_cny"]),
            "reason": row["reason"],
            "sourceType": row.get("source_type"),
            "sourceId": row.get("source_id"),
            "createdBy": row.get("approved_by"),
            "approvedBy": row.get("approved_by"),
            "createdAt": to_iso(row.get("created_at")),
        }

    def _build_group_buy_record(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "groupBuyId": row["group_buy_id"],
            "groupBuyItemId": row["group_buy_item_id"],
            "memberUserId": row["member_user_id"],
            "status": row["status"],
            "quantity": row["quantity"],
            "goodsChargeId": row.get("goods_charge_id"),
            "goodsPaymentRecordId": row.get("goods_payment_record_id"),
            "internationalChargeId": row.get("international_charge_id"),
            "internationalPaymentRecordId": row.get("international_payment_record_id"),
            "domesticShippingChargeId": row.get("domestic_shipping_charge_id"),
            "dispatchRequestId": row.get("dispatch_request_id"),
            "transferId": row.get("transfer_id"),
            "isException": bool(row.get("is_exception")),
            "exceptionReason": row.get("exception_reason"),
            "statusPriority": row.get("status_priority"),
            "note": row.get("note"),
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

    def count_pending_charges_for_user(self, conn, payer_user_id: str) -> int:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM charges
                WHERE payer_user_id = %s
                  AND status = 'pending'
                """,
                (payer_user_id,),
            )
            return int(cur.fetchone()["total"])

    def get_payment_channel_by_id(
        self,
        conn,
        payment_channel_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any] | None:
        lock_sql = "FOR UPDATE" if lock else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM payment_channels
                WHERE id = %s
                LIMIT 1
                {lock_sql}
                """,
                (payment_channel_id,),
            )
            row = cur.fetchone()
        return self._build_payment_channel(row) if row else None

    def get_charge_by_id(self, conn, charge_id: str, *, lock: bool = False) -> dict[str, Any] | None:
        lock_sql = "FOR UPDATE" if lock else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM charges
                WHERE id = %s
                LIMIT 1
                {lock_sql}
                """,
                (charge_id,),
            )
            row = cur.fetchone()
        return self._build_charge(row) if row else None

    def get_payment_proof_by_id(
        self,
        conn,
        proof_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any] | None:
        lock_sql = "FOR UPDATE" if lock else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM payment_proofs
                WHERE id = %s
                LIMIT 1
                {lock_sql}
                """,
                (proof_id,),
            )
            row = cur.fetchone()
        return self._build_payment_proof(row) if row else None

    def list_payment_proof_allocations(self, conn, proof_id: str) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM payment_proof_allocations
                WHERE proof_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (proof_id,),
            )
            rows = cur.fetchall()
        return [self._build_payment_proof_allocation(row) for row in rows]

    def create_payment_channel(self, conn, fields: dict[str, Any]) -> dict[str, Any]:
        payment_channel_id = f"payment_channel_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO payment_channels (
                  id,
                  owner_user_id,
                  type,
                  display_name,
                  qr_file_object_id,
                  qr_image_url,
                  account_text,
                  note,
                  status,
                  created_at,
                  updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', NOW(), NOW())
                RETURNING *
                """,
                (
                    payment_channel_id,
                    fields["owner_user_id"],
                    fields["type"],
                    fields["display_name"],
                    fields["qr_file_object_id"],
                    fields["qr_image_url"],
                    fields["account_text"],
                    fields["note"],
                ),
            )
            row = cur.fetchone()
        return self._build_payment_channel(row)

    def create_charge(self, conn, fields: dict[str, Any]) -> dict[str, Any]:
        charge_id = f"charge_{secrets.token_hex(8)}"
        snapshot = fields["snapshot"] if fields["snapshot"] is not None else {}
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO charges (
                  id,
                  type,
                  payer_user_id,
                  payee_user_id,
                  biz_type,
                  biz_id,
                  amount_cny,
                  status,
                  payment_channel_id,
                  note,
                  snapshot_json,
                  submitted_proof_id,
                  confirmed_proof_id,
                  cancelled_reason,
                  created_at,
                  updated_at
                )
                VALUES (
                  %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s::jsonb, NULL, NULL, NULL, NOW(), NOW()
                )
                RETURNING *
                """,
                (
                    charge_id,
                    fields["type"],
                    fields["payer_user_id"],
                    fields["payee_user_id"],
                    fields["biz_type"],
                    fields["biz_id"],
                    cny_to_cent(fields["amount_cny"], "amountCny"),
                    fields["payment_channel_id"],
                    fields["note"],
                    json.dumps(snapshot, ensure_ascii=False),
                ),
            )
            row = cur.fetchone()
        return self._build_charge(row)

    def update_charge(self, conn, *, charge_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "status",
            "submitted_proof_id",
            "confirmed_proof_id",
            "cancelled_reason",
        }
        set_fragments: list[str] = []
        params: list[Any] = []
        for column, value in updates.items():
            if column not in allowed:
                raise RuntimeError(f"Unsupported charge update column: {column}")
            set_fragments.append(f"{column} = %s")
            params.append(value)
        set_fragments.append("updated_at = NOW()")
        params.append(charge_id)

        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                UPDATE charges
                SET {", ".join(set_fragments)}
                WHERE id = %s
                RETURNING *
                """,
                params,
            )
            row = cur.fetchone()
        return self._build_charge(row)

    def create_payment_proof(self, conn, fields: dict[str, Any]) -> dict[str, Any]:
        proof_id = f"payment_proof_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO payment_proofs (
                  id,
                  submitted_by,
                  from_user_id,
                  to_user_id,
                  amount_cny,
                  paid_at,
                  proof_file_object_id,
                  proof_image_url,
                  note,
                  status,
                  reviewed_by,
                  reviewed_at,
                  review_note,
                  reject_reason,
                  created_at,
                  updated_at
                )
                VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, 'submitted', NULL, NULL, NULL, NULL, NOW(), NOW()
                )
                RETURNING *
                """,
                (
                    proof_id,
                    fields["submitted_by"],
                    fields["from_user_id"],
                    fields["to_user_id"],
                    cny_to_cent(fields["amount_cny"], "amountCny"),
                    fields["paid_at"],
                    fields["proof_file_object_id"],
                    fields["proof_image_url"],
                    fields["note"],
                ),
            )
            row = cur.fetchone()
        return self._build_payment_proof(row)

    def update_payment_proof(
        self,
        conn,
        *,
        proof_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        allowed = {
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "reject_reason",
        }
        set_fragments: list[str] = []
        params: list[Any] = []
        for column, value in updates.items():
            if column not in allowed:
                raise RuntimeError(f"Unsupported payment proof update column: {column}")
            set_fragments.append(f"{column} = %s")
            params.append(value)
        set_fragments.append("updated_at = NOW()")
        params.append(proof_id)

        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                UPDATE payment_proofs
                SET {", ".join(set_fragments)}
                WHERE id = %s
                RETURNING *
                """,
                params,
            )
            row = cur.fetchone()
        return self._build_payment_proof(row)

    def create_payment_proof_allocation(
        self,
        conn,
        *,
        proof_id: str,
        charge_id: str,
        allocated_amount_cny: str,
    ) -> dict[str, Any]:
        allocation_id = f"payment_proof_allocation_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO payment_proof_allocations (
                  id,
                  proof_id,
                  charge_id,
                  allocated_amount_cny,
                  created_at
                )
                VALUES (%s, %s, %s, %s, NOW())
                RETURNING *
                """,
                (
                    allocation_id,
                    proof_id,
                    charge_id,
                    cny_to_cent(allocated_amount_cny, "allocatedAmountCny"),
                ),
            )
            row = cur.fetchone()
        return self._build_payment_proof_allocation(row)

    def create_charge_adjustment(self, conn, fields: dict[str, Any]) -> dict[str, Any]:
        adjustment_id = f"charge_adjustment_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO charge_adjustments (
                  id,
                  charge_id,
                  source_charge_id,
                  delta_cny,
                  reason,
                  source_type,
                  source_id,
                  approved_by,
                  created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING *
                """,
                (
                    adjustment_id,
                    fields["charge_id"],
                    fields["source_charge_id"],
                    cny_to_cent(fields["delta_cny"], "deltaCny"),
                    fields["reason"],
                    fields["source_type"],
                    fields["source_id"],
                    fields["approved_by"],
                ),
            )
            row = cur.fetchone()
        return self._build_charge_adjustment(row)

    def list_group_buy_record_ids_by_charge(self, conn, charge_id: str) -> list[str]:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT id
                FROM group_buy_records
                WHERE goods_charge_id = %s
                   OR international_charge_id = %s
                   OR domestic_shipping_charge_id = %s
                   OR id = (
                     SELECT biz_id
                     FROM charges
                     WHERE id = %s
                       AND biz_type = 'group_buy_record'
                     LIMIT 1
                   )
                ORDER BY created_at ASC, id ASC
                """,
                (charge_id, charge_id, charge_id, charge_id),
            )
            return [row["id"] for row in cur.fetchall()]

    def _get_group_buy_type_for_record(self, conn, record: dict[str, Any]) -> str | None:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT type
                FROM group_buys
                WHERE id = %s
                LIMIT 1
                """,
                (record["groupBuyId"],),
            )
            row = cur.fetchone()
        return row["type"] if row else None

    def _next_group_buy_record_status(self, conn, record: dict[str, Any]) -> str:
        if record.get("transferId"):
            return GROUP_BUY_RECORD_STATUS_TRANSFERRING
        if record.get("dispatchRequestId"):
            return GROUP_BUY_RECORD_STATUS_DISPATCH_REQUESTED
        if not record.get("goodsPaymentRecordId"):
            return GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT

        group_buy_type = self._get_group_buy_type_for_record(conn, record)
        needs_international_fee = (
            bool(record.get("internationalChargeId"))
            or bool(record.get("internationalPaymentRecordId"))
            or group_buy_type not in GROUP_BUY_TYPES_WITHOUT_INTERNATIONAL
        )
        if needs_international_fee and not record.get("internationalPaymentRecordId"):
            return GROUP_BUY_RECORD_STATUS_PENDING_INTERNATIONAL_PAYMENT
        if needs_international_fee:
            return GROUP_BUY_RECORD_STATUS_PENDING_TRANSFER
        return GROUP_BUY_RECORD_STATUS_ORDERED

    def link_group_buy_record_payment_proof(
        self,
        conn,
        *,
        group_buy_record_id: str,
        payment_type: str,
        payment_proof_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM group_buy_records
                WHERE id = %s
                LIMIT 1
                FOR UPDATE
                """,
                (group_buy_record_id,),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "group buy record not found", "NOT_FOUND")

        before = self._build_group_buy_record(row)
        draft = dict(before)
        if payment_type == "goods":
            draft["goodsPaymentRecordId"] = payment_proof_id
            payment_column = "goods_payment_record_id"
        else:
            draft["internationalPaymentRecordId"] = payment_proof_id
            payment_column = "international_payment_record_id"

        next_status = self._next_group_buy_record_status(conn, draft)
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                UPDATE group_buy_records
                SET {payment_column} = %s,
                    status = %s,
                    status_priority = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (
                    payment_proof_id,
                    next_status,
                    _status_priority(next_status),
                    group_buy_record_id,
                ),
            )
            after_row = cur.fetchone()
        return before, self._build_group_buy_record(after_row)
