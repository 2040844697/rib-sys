from __future__ import annotations

import secrets
from typing import Any

from ..db_access import to_iso
from ..errors import AppError


class TransferExceptionRepository:
    def __init__(self, config):
        # 保存配置，保持 repository 与其他 DB 模块的构造方式一致。
        self.config = config

    def _dict_row(self):
        # 让 psycopg 以 dict 形式返回行，便于统一转换字段名。
        from psycopg.rows import dict_row

        return dict_row

    def _build_transfer(self, row: dict[str, Any]) -> dict[str, Any]:
        # 将 transfers 行转换成模块内部和前端沿用的 camelCase 快照。
        return {
            "id": row["id"],
            "fromUserId": row["from_user_id"],
            "toUserId": row["to_user_id"],
            "requestedBy": row["requested_by"],
            "approvedBy": row.get("approved_by"),
            "approvedAt": to_iso(row.get("approved_at")),
            "rejectedBy": row.get("rejected_by"),
            "rejectedAt": to_iso(row.get("rejected_at")),
            "rejectReason": row.get("reject_reason"),
            "status": row["status"],
            "reason": row.get("reason"),
            "note": row.get("note"),
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

    def _build_transfer_item(self, row: dict[str, Any]) -> dict[str, Any]:
        # 将 transfer_items 行转换成业务流程使用的字段名。
        return {
            "id": row["id"],
            "transferId": row["transfer_id"],
            "groupBuyRecordId": row["group_buy_record_id"],
            "quantity": row["quantity"],
            "createdAt": to_iso(row.get("created_at")),
        }

    def _build_record(self, row: dict[str, Any]) -> dict[str, Any]:
        # 只转换转单/异常流程需要的记录字段，完整摘要交给 group_buy_records 模块。
        return {
            "id": row["id"],
            "groupBuyId": row["group_buy_id"],
            "groupBuyItemId": row["group_buy_item_id"],
            "memberUserId": row["member_user_id"],
            "status": row["status"],
            "displayStatus": row["status"],
            "quantity": row["quantity"],
            "transferId": row.get("transfer_id"),
            "isException": bool(row.get("is_exception")),
            "exceptionReason": row.get("exception_reason"),
            "statusPriority": row.get("status_priority"),
            "note": row.get("note"),
            "source": row.get("source") or "member_claim",
            "sourceRecordId": row.get("source_record_id"),
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

    def get_transfer_for_update(self, conn, transfer_id: str) -> dict[str, Any]:
        # 锁定转单申请，保证审核和驳回不会并发处理同一申请。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM transfers
                WHERE id = %s
                LIMIT 1
                FOR UPDATE
                """,
                (transfer_id,),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "转单申请不存在", "NOT_FOUND")
        return self._build_transfer(row)

    def list_transfer_items(self, conn, transfer_id: str, *, lock: bool = False) -> list[dict[str, Any]]:
        # 读取转单明细；审核流程可加锁避免明细被并发修改。
        lock_sql = "FOR UPDATE" if lock else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM transfer_items
                WHERE transfer_id = %s
                ORDER BY created_at ASC, id ASC
                {lock_sql}
                """,
                (transfer_id,),
            )
            rows = cur.fetchall()
        return [self._build_transfer_item(row) for row in rows]

    def create_transfer(
        self,
        conn,
        *,
        from_user_id: str,
        to_user_id: str,
        requested_by: str,
        reason: str,
    ) -> dict[str, Any]:
        # 创建转单申请主表记录。
        transfer_id = f"transfer_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO transfers (
                  id,
                  from_user_id,
                  to_user_id,
                  status,
                  reason,
                  requested_by,
                  created_at,
                  updated_at
                )
                VALUES (%s, %s, %s, 'pending', %s, %s, NOW(), NOW())
                RETURNING *
                """,
                (transfer_id, from_user_id, to_user_id, reason, requested_by),
            )
            row = cur.fetchone()
        return self._build_transfer(row)

    def create_transfer_item(
        self,
        conn,
        *,
        transfer_id: str,
        group_buy_record_id: str,
        quantity: int,
    ) -> dict[str, Any]:
        # 创建转单申请明细，保存源记录和转出数量。
        transfer_item_id = f"transfer_item_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO transfer_items (
                  id,
                  transfer_id,
                  group_buy_record_id,
                  quantity,
                  created_at
                )
                VALUES (%s, %s, %s, %s, NOW())
                RETURNING *
                """,
                (transfer_item_id, transfer_id, group_buy_record_id, quantity),
            )
            row = cur.fetchone()
        return self._build_transfer_item(row)

    def approve_transfer(
        self,
        conn,
        *,
        transfer_id: str,
        approved_by: str,
        note: str | None,
    ) -> dict[str, Any]:
        # 将转单申请更新为已通过，并保存审核人和备注。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE transfers
                SET status = 'approved',
                    approved_by = %s,
                    approved_at = NOW(),
                    note = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (approved_by, note, transfer_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "转单申请不存在", "NOT_FOUND")
        return self._build_transfer(row)

    def reject_transfer(
        self,
        conn,
        *,
        transfer_id: str,
        rejected_by: str,
        reject_reason: str,
    ) -> dict[str, Any]:
        # 将转单申请更新为已驳回，并保存驳回信息。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE transfers
                SET status = 'rejected',
                    rejected_by = %s,
                    rejected_at = NOW(),
                    reject_reason = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (rejected_by, reject_reason, transfer_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "转单申请不存在", "NOT_FOUND")
        return self._build_transfer(row)

    def mark_record_transfer_pending(
        self,
        conn,
        *,
        group_buy_record_id: str,
        transfer_id: str,
    ) -> dict[str, Any]:
        # 将源拼单记录挂到待审核转单申请上。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE group_buy_records
                SET transfer_id = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (transfer_id, group_buy_record_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "拼单记录不存在", "NOT_FOUND")
        return self._build_record(row)

    def release_record_transfer_pending(
        self,
        conn,
        *,
        group_buy_record_id: str,
        transfer_id: str,
    ) -> dict[str, Any]:
        # 驳回或通过后释放源记录的转单挂起标记。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE group_buy_records
                SET transfer_id = NULL,
                    updated_at = NOW()
                WHERE id = %s
                  AND transfer_id = %s
                RETURNING *
                """,
                (group_buy_record_id, transfer_id),
            )
            row = cur.fetchone()
        if row is None:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM group_buy_records
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (group_buy_record_id,),
                )
                row = cur.fetchone()
        if row is None:
            raise AppError(404, "拼单记录不存在", "NOT_FOUND")
        return self._build_record(row)

    def mark_record_exception(
        self,
        conn,
        *,
        group_buy_record_id: str,
        exception_reason: str,
        note: str | None,
    ) -> dict[str, Any]:
        # 写入异常标记和异常原因。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE group_buy_records
                SET is_exception = TRUE,
                    exception_reason = %s,
                    note = COALESCE(%s, note),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (exception_reason, note, group_buy_record_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "拼单记录不存在", "NOT_FOUND")
        return self._build_record(row)

    def resolve_record_exception(
        self,
        conn,
        *,
        group_buy_record_id: str,
        note: str | None,
    ) -> dict[str, Any]:
        # 清除异常标记和异常原因。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE group_buy_records
                SET is_exception = FALSE,
                    exception_reason = NULL,
                    note = COALESCE(%s, note),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (note, group_buy_record_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "拼单记录不存在", "NOT_FOUND")
        return self._build_record(row)
