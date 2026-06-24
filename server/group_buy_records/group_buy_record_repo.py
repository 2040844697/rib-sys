from __future__ import annotations

import secrets
from typing import Any

from ..db_access import to_iso
from ..errors import AppError


CHARGE_STATUS_CONFIRMED = "confirmed"
DISPATCH_REQUEST_STATUS_SHIPPED = "shipped"
DISPATCH_REQUEST_STATUS_COMPLETED = "completed"
STOCK_ITEM_STATUS_COMPLETED = "completed"


class GroupBuyRecordRepository:
    def __init__(self, config):
        self.config = config

    def _dict_row(self):
        from psycopg.rows import dict_row

        return dict_row

    def _build_group_buy(self, row: dict[str, Any]) -> dict[str, Any]:
        # 将团购表字段转换成前端仍在使用的 camelCase 快照。
        return {
            "id": row["id"],
            "groupId": row["group_id"],
            "type": row["type"],
            "title": row["title"],
            "description": row["description"],
            "status": row["status"],
            "ownerUserId": row["owner_user_id"],
            "closeAt": to_iso(row.get("close_at")),
            "paymentChannelId": row.get("payment_channel_id"),
            "warehouseUserId": row.get("warehouse_user_id"),
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

    def _build_group_buy_item(self, row: dict[str, Any]) -> dict[str, Any]:
        # 将团购商品库存和价格快照统一转换成模块内部格式。
        return {
            "id": row["id"],
            "groupBuyId": row["group_buy_id"],
            "goodsId": row["goods_id"],
            "name": row["name_snapshot"],
            "unitPriceCny": self._from_cent(row["unit_price_cny"]),
            "totalQuantity": row["total_quantity"],
            "reservedQuantity": row["reserved_quantity"],
            "claimedQuantity": row["claimed_quantity"],
            "availableQuantity": row["available_quantity"],
            "status": row["status"],
            "note": row.get("note"),
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

    def _build_record(self, row: dict[str, Any]) -> dict[str, Any]:
        # 主记录只承载归属、数量、关键外键和当前展示状态。
        return {
            "id": row["id"],
            "groupBuyId": row["group_buy_id"],
            "groupBuyItemId": row["group_buy_item_id"],
            "memberUserId": row["member_user_id"],
            "status": row["status"],
            "displayStatus": row["status"],
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
            "source": row.get("source") or "member_claim",
            "sourceRecordId": row.get("source_record_id"),
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

    def _build_facts(self, row: dict[str, Any]) -> dict[str, Any]:
        # 状态事实来自各业务表查询结果，不在 group_buy_records 重复存布尔列。
        return {
            "goodsPaidConfirmed": bool(row.get("goods_paid_confirmed")),
            "internationalPaidConfirmed": bool(row.get("international_paid_confirmed")),
            "isOrdered": bool(row.get("is_ordered")),
            "isStocked": bool(row.get("is_stocked")),
            "dispatchRequested": bool(row.get("dispatch_requested")),
            "isDispatched": bool(row.get("is_dispatched")),
            "isCompleted": bool(row.get("is_completed")),
            "isTransferPending": bool(row.get("is_transfer_pending")),
            "hasInternationalBatch": bool(row.get("has_international_batch")),
        }

    def _from_cent(self, amount_cny_cent: int) -> str:
        # 金额在 DB 里按分保存，输出保持两位小数字符串。
        cents = abs(int(amount_cny_cent))
        sign = "-" if amount_cny_cent < 0 else ""
        return f"{sign}{cents // 100}.{cents % 100:02d}"

    def get_group_buy_by_id(self, conn, group_buy_id: str, *, lock: bool = False) -> dict[str, Any] | None:
        # 读取团购，创建认领时可加锁防止状态并发变化。
        lock_sql = "FOR UPDATE" if lock else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM group_buys
                WHERE id = %s
                LIMIT 1
                {lock_sql}
                """,
                (group_buy_id,),
            )
            row = cur.fetchone()
        return self._build_group_buy(row) if row else None

    def get_group_buy_item_by_id(self, conn, group_buy_item_id: str, *, lock: bool = False) -> dict[str, Any] | None:
        # 读取团购商品，认领和改数量时锁定库存行。
        lock_sql = "FOR UPDATE" if lock else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM group_buy_items
                WHERE id = %s
                LIMIT 1
                {lock_sql}
                """,
                (group_buy_item_id,),
            )
            row = cur.fetchone()
        return self._build_group_buy_item(row) if row else None

    def get_record_by_id(self, conn, group_buy_record_id: str, *, lock: bool = False) -> dict[str, Any] | None:
        # 按 ID 读取拼单记录。
        lock_sql = "FOR UPDATE" if lock else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM group_buy_records
                WHERE id = %s
                LIMIT 1
                {lock_sql}
                """,
                (group_buy_record_id,),
            )
            row = cur.fetchone()
        return self._build_record(row) if row else None

    def get_record_for_member(
        self,
        conn,
        *,
        group_buy_item_id: str,
        member_user_id: str,
        lock: bool = False,
    ) -> dict[str, Any] | None:
        # 查找同一成员同一商品的现有记录，用于认领合并。
        lock_sql = "FOR UPDATE" if lock else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM group_buy_records
                WHERE group_buy_item_id = %s
                  AND member_user_id = %s
                LIMIT 1
                {lock_sql}
                """,
                (group_buy_item_id, member_user_id),
            )
            row = cur.fetchone()
        return self._build_record(row) if row else None

    def list_member_records(self, conn, *, group_buy_id: str, member_user_id: str) -> list[dict[str, Any]]:
        # 查询成员在某团购下的认领记录。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM group_buy_records
                WHERE group_buy_id = %s
                  AND member_user_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (group_buy_id, member_user_id),
            )
            rows = cur.fetchall()
        return [self._build_record(row) for row in rows]

    def count_member_records_by_status(self, conn, *, member_user_id: str, status: str) -> int:
        # 统计成员指定展示状态的记录数。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM group_buy_records
                WHERE member_user_id = %s
                  AND status = %s
                """,
                (member_user_id, status),
            )
            row = cur.fetchone()
        return int(row["total"])

    def get_claimed_quantity(self, conn, group_buy_item_id: str) -> int:
        # 从记录表汇总已认领数量，供库存校验兜底。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(quantity), 0) AS quantity
                FROM group_buy_records
                WHERE group_buy_item_id = %s
                """,
                (group_buy_item_id,),
            )
            row = cur.fetchone()
        return int(row["quantity"])

    def list_record_ids_by_charge(self, conn, charge_id: str) -> list[str]:
        # 按费用 ID 反查关联的拼单记录。
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
            rows = cur.fetchall()
        return [row["id"] for row in rows]

    def create_record(
        self,
        conn,
        *,
        group_buy_id: str,
        group_buy_item_id: str,
        member_user_id: str,
        quantity: int,
        status: str,
        status_priority: int,
        note: str | None,
        source: str,
        source_record_id: str | None = None,
        transfer_id: str | None = None,
    ) -> dict[str, Any]:
        # 新建主记录，默认不写任何流程布尔事实。
        record_id = f"record_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO group_buy_records (
                  id,
                  group_buy_id,
                  group_buy_item_id,
                  member_user_id,
                  status,
                  quantity,
                  status_priority,
                  note,
                  source,
                  source_record_id,
                  transfer_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    record_id,
                    group_buy_id,
                    group_buy_item_id,
                    member_user_id,
                    status,
                    quantity,
                    status_priority,
                    note,
                    source,
                    source_record_id,
                    transfer_id,
                ),
            )
            row = cur.fetchone()
        return self._build_record(row)

    def update_record_quantity(self, conn, *, group_buy_record_id: str, quantity: int) -> dict[str, Any]:
        # 更新认领数量，不改变流程事实。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE group_buy_records
                SET quantity = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (quantity, group_buy_record_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "拼单记录不存在", "NOT_FOUND")
        return self._build_record(row)

    def update_group_buy_item_claimed_delta(
        self,
        conn,
        *,
        group_buy_item_id: str,
        delta_quantity: int,
    ) -> dict[str, Any]:
        # 按认领变化量维护 claimed_quantity / available_quantity。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE group_buy_items
                SET claimed_quantity = claimed_quantity + %s,
                    available_quantity = available_quantity - %s,
                    updated_at = NOW()
                WHERE id = %s
                  AND claimed_quantity + %s >= 0
                  AND available_quantity - %s >= 0
                RETURNING *
                """,
                (
                    delta_quantity,
                    delta_quantity,
                    group_buy_item_id,
                    delta_quantity,
                    delta_quantity,
                ),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(400, "可认领数量不足", "INSUFFICIENT_STOCK")
        return self._build_group_buy_item(row)

    def link_charge(
        self,
        conn,
        *,
        group_buy_record_id: str,
        charge_type: str,
        charge_id: str,
    ) -> dict[str, Any]:
        # 将费用外键写回主记录。
        column_by_type = {
            "initial_goods": "goods_charge_id",
            "goods": "goods_charge_id",
            "international": "international_charge_id",
            "domestic_shipping": "domestic_shipping_charge_id",
        }
        column_name = column_by_type.get(charge_type)
        if column_name is None:
            raise AppError(400, "chargeType 不支持", "VALIDATION_FAILED")
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                UPDATE group_buy_records
                SET {column_name} = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (charge_id, group_buy_record_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "拼单记录不存在", "NOT_FOUND")
        return self._build_record(row)

    def link_payment_proof(
        self,
        conn,
        *,
        group_buy_record_id: str,
        payment_type: str,
        payment_proof_id: str,
    ) -> dict[str, Any]:
        # 将最终确认的付款凭证外键写回主记录。
        column_by_type = {
            "goods": "goods_payment_record_id",
            "international": "international_payment_record_id",
        }
        column_name = column_by_type.get(payment_type)
        if column_name is None:
            raise AppError(400, "paymentType 不支持", "VALIDATION_FAILED")
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                UPDATE group_buy_records
                SET {column_name} = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (payment_proof_id, group_buy_record_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "拼单记录不存在", "NOT_FOUND")
        return self._build_record(row)

    def update_status(self, conn, *, group_buy_record_id: str, status: str, status_priority: int) -> dict[str, Any]:
        # 回写计算后的展示状态和排序优先级。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE group_buy_records
                SET status = %s,
                    status_priority = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (status, status_priority, group_buy_record_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "拼单记录不存在", "NOT_FOUND")
        return self._build_record(row)

    def mark_dispatch_requested(
        self,
        conn,
        *,
        group_buy_record_id: str,
        dispatch_request_id: str,
    ) -> dict[str, Any]:
        # 排发申请仍作为关键外键保存在主记录。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE group_buy_records
                SET dispatch_request_id = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (dispatch_request_id, group_buy_record_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "拼单记录不存在", "NOT_FOUND")
        return self._build_record(row)

    def dispatch_request_exists(self, conn, dispatch_request_id: str) -> bool:
        # 迁移期判断排发申请是否已经落在 DB 表中，避免写入悬空外键。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT 1
                FROM dispatch_requests
                WHERE id = %s
                LIMIT 1
                """,
                (dispatch_request_id,),
            )
            return cur.fetchone() is not None

    def update_transfer_link(
        self,
        conn,
        *,
        group_buy_record_id: str,
        transfer_id: str | None,
    ) -> dict[str, Any]:
        # 转单中状态只保存当前 transfer_id 外键。
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

    def update_exception(
        self,
        conn,
        *,
        group_buy_record_id: str,
        is_exception: bool,
        exception_reason: str | None,
        note: str | None,
    ) -> dict[str, Any]:
        # 异常标记是记录自身的人工处理状态，保留在主表。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE group_buy_records
                SET is_exception = %s,
                    exception_reason = %s,
                    note = COALESCE(%s, note),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (is_exception, exception_reason, note, group_buy_record_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "拼单记录不存在", "NOT_FOUND")
        return self._build_record(row)

    def create_transfer_record(
        self,
        conn,
        *,
        source_record: dict[str, Any],
        to_user_id: str,
        quantity: int,
        transfer_id: str,
        status: str,
        status_priority: int,
        note: str | None,
    ) -> dict[str, Any]:
        # 转单受让方记录只继承业务归属，不继承原付款凭证。
        return self.create_record(
            conn,
            group_buy_id=source_record["groupBuyId"],
            group_buy_item_id=source_record["groupBuyItemId"],
            member_user_id=to_user_id,
            quantity=quantity,
            status=status,
            status_priority=status_priority,
            note=note,
            source="transfer",
            source_record_id=source_record["id"],
            transfer_id=transfer_id,
        )

    def get_record_facts(self, conn, group_buy_record_id: str) -> dict[str, Any]:
        # 汇总费用、下单、批次、入库、排发和转单事实用于状态计算。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT
                  EXISTS (
                    SELECT 1
                    FROM charges c
                    WHERE c.id = r.goods_charge_id
                      AND c.status = %s
                  ) AS goods_paid_confirmed,
                  EXISTS (
                    SELECT 1
                    FROM charges c
                    WHERE c.id = r.international_charge_id
                      AND c.status = %s
                  ) AS international_paid_confirmed,
                  EXISTS (
                    SELECT 1
                    FROM audit_logs al
                    WHERE al.object_type = 'group_buy_record'
                      AND al.object_id = r.id
                      AND al.action = 'record.mark_ordered'
                  ) AS is_ordered,
                  EXISTS (
                    SELECT 1
                    FROM international_batch_records ibr
                    WHERE ibr.group_buy_record_id = r.id
                  )
                    OR EXISTS (
                      SELECT 1
                      FROM audit_logs al
                      WHERE al.object_type = 'group_buy_record'
                        AND al.object_id = r.id
                        AND al.action = 'record.enter_transfer_flow'
                    ) AS has_international_batch,
                  EXISTS (
                    SELECT 1
                    FROM stock_items si
                    WHERE si.group_buy_record_id = r.id
                      AND si.quantity > 0
                  )
                    OR EXISTS (
                      SELECT 1
                      FROM audit_logs al
                      WHERE al.object_type = 'group_buy_record'
                        AND al.object_id = r.id
                        AND al.action = 'record.mark_stocked'
                    ) AS is_stocked,
                  r.dispatch_request_id IS NOT NULL
                    OR EXISTS (
                      SELECT 1
                      FROM dispatch_items di
                      WHERE di.group_buy_record_id = r.id
                    )
                    OR EXISTS (
                      SELECT 1
                      FROM audit_logs al
                      WHERE al.object_type = 'group_buy_record'
                        AND al.object_id = r.id
                        AND al.action = 'record.mark_dispatch_requested'
                    ) AS dispatch_requested,
                  EXISTS (
                    SELECT 1
                    FROM dispatch_items di
                    JOIN dispatch_requests dr ON dr.id = di.dispatch_request_id
                    WHERE di.group_buy_record_id = r.id
                      AND dr.status = %s
                  )
                    OR EXISTS (
                      SELECT 1
                      FROM dispatch_items di
                      JOIN domestic_shipments ds ON ds.dispatch_request_id = di.dispatch_request_id
                      WHERE di.group_buy_record_id = r.id
                    )
                    OR EXISTS (
                      SELECT 1
                      FROM audit_logs al
                      WHERE al.object_type = 'group_buy_record'
                        AND al.object_id = r.id
                        AND al.action = 'record.mark_dispatched'
                    ) AS is_dispatched,
                  EXISTS (
                    SELECT 1
                    FROM dispatch_items di
                    JOIN dispatch_requests dr ON dr.id = di.dispatch_request_id
                    WHERE di.group_buy_record_id = r.id
                      AND dr.status = %s
                  )
                    OR EXISTS (
                      SELECT 1
                      FROM stock_items si
                      WHERE si.group_buy_record_id = r.id
                        AND si.status = %s
                    )
                    OR EXISTS (
                      SELECT 1
                      FROM audit_logs al
                      WHERE al.object_type = 'group_buy_record'
                        AND al.object_id = r.id
                        AND al.action = 'record.mark_completed'
                    ) AS is_completed,
                  r.transfer_id IS NOT NULL
                    AND EXISTS (
                      SELECT 1
                      FROM transfers t
                      WHERE t.id = r.transfer_id
                        AND t.status = 'pending'
                    ) AS is_transfer_pending
                FROM group_buy_records r
                WHERE r.id = %s
                LIMIT 1
                """,
                (
                    CHARGE_STATUS_CONFIRMED,
                    CHARGE_STATUS_CONFIRMED,
                    DISPATCH_REQUEST_STATUS_SHIPPED,
                    DISPATCH_REQUEST_STATUS_COMPLETED,
                    STOCK_ITEM_STATUS_COMPLETED,
                    group_buy_record_id,
                ),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "拼单记录不存在", "NOT_FOUND")
        return self._build_facts(row)

    def require_charge(self, conn, charge_id: str) -> dict[str, Any]:
        # 校验费用存在，并返回类型和状态供关联逻辑使用。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT id, type, status
                FROM charges
                WHERE id = %s
                LIMIT 1
                """,
                (charge_id,),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "费用不存在", "NOT_FOUND")
        return {"id": row["id"], "type": row["type"], "status": row["status"]}

    def require_payment_proof(self, conn, proof_id: str) -> dict[str, Any]:
        # 校验付款凭证存在。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT id, status
                FROM payment_proofs
                WHERE id = %s
                LIMIT 1
                """,
                (proof_id,),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "付款凭证不存在", "NOT_FOUND")
        return {"id": row["id"], "status": row["status"]}
