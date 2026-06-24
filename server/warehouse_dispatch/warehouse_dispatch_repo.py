from __future__ import annotations

import secrets
from decimal import Decimal, InvalidOperation
from typing import Any

from ..db_access import to_iso
from ..errors import AppError


CENT = Decimal("0.01")


def cny_to_cent(value: str | Decimal | int | None, field_name: str = "amountCny") -> int | None:
    # 将 API 使用的元字符串转换为数据库存储的分。
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED") from exc
    quantized = amount.quantize(CENT)
    if amount != quantized:
        raise AppError(400, f"{field_name}最多保留两位小数", "VALIDATION_FAILED")
    return int(quantized * 100)


def cent_to_cny(value: int | None) -> str | None:
    # 将数据库中的分转换为两位小数元字符串。
    if value is None:
        return None
    sign = "-" if value < 0 else ""
    cents = abs(int(value))
    return f"{sign}{cents // 100}.{cents % 100:02d}"


class WarehouseDispatchRepository:
    def __init__(self, config):
        # 保存配置，保持与其他 DB repository 的构造方式一致。
        self.config = config

    def _dict_row(self):
        # 统一使用 dict row，减少字段转换时的位置依赖。
        from psycopg.rows import dict_row

        return dict_row

    def _build_stock_item(self, row: dict[str, Any]) -> dict[str, Any]:
        # 将 stock_items 行转换为模块内部沿用的 camelCase 快照。
        return {
            "id": row["id"],
            "warehouseUserId": row["warehouse_user_id"],
            "groupBuyRecordId": row["group_buy_record_id"],
            "quantity": row["quantity"],
            "status": row["status"],
            "stockedAt": to_iso(row.get("stocked_at")),
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

    def _build_dispatch_request(self, row: dict[str, Any]) -> dict[str, Any]:
        # 将 dispatch_requests 行转换为对外接口沿用的 camelCase 快照。
        return {
            "id": row["id"],
            "requesterUserId": row["requester_user_id"],
            "warehouseUserId": row["warehouse_user_id"],
            "status": row["status"],
            "receiverName": row["receiver_name"],
            "receiverPhone": row["receiver_phone"],
            "receiverAddress": row["receiver_address"],
            "note": row.get("note"),
            "submittedAt": to_iso(row.get("submitted_at")),
            "packedAt": to_iso(row.get("packed_at")),
            "shippedAt": to_iso(row.get("shipped_at")),
            "completedAt": to_iso(row.get("completed_at")),
            "shippingFeeCny": cent_to_cny(row.get("shipping_fee_cny")),
            "feeMode": row.get("fee_mode"),
            "paymentChannelId": row.get("payment_channel_id"),
            "domesticChargeId": row.get("domestic_charge_id"),
            "domesticFeeRecordedAt": to_iso(row.get("domestic_fee_recorded_at")),
            "domesticFeeConfirmedAt": to_iso(row.get("domestic_fee_confirmed_at")),
            "domesticFeeConfirmedProofId": row.get("domestic_fee_confirmed_proof_id"),
            "domesticShipmentId": row.get("domestic_shipment_id"),
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

    def _build_dispatch_item(self, row: dict[str, Any]) -> dict[str, Any]:
        # 将 dispatch_items 行转换为排发明细快照。
        return {
            "id": row["id"],
            "dispatchRequestId": row["dispatch_request_id"],
            "stockItemId": row["stock_item_id"],
            "groupBuyRecordId": row["group_buy_record_id"],
            "quantity": row["quantity"],
            "createdAt": to_iso(row.get("created_at")),
        }

    def _build_domestic_shipment(self, row: dict[str, Any]) -> dict[str, Any]:
        # 将 domestic_shipments 行转换为国内快递快照。
        return {
            "id": row["id"],
            "dispatchRequestId": row["dispatch_request_id"],
            "carrier": row.get("carrier"),
            "trackingNo": row.get("tracking_no"),
            "shippingFeeCny": cent_to_cny(row.get("shipping_fee_cny")),
            "feeMode": row["fee_mode"],
            "shippedAt": to_iso(row.get("shipped_at")),
            "note": row.get("note"),
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

    def _build_international_batch(self, row: dict[str, Any]) -> dict[str, Any]:
        # 将 international_batches 行转换为入库流程需要的批次快照。
        return {
            "id": row["id"],
            "forwarderName": row["forwarder_name"],
            "batchNo": row.get("batch_no"),
            "status": row["status"],
            "warehouseUserId": row.get("warehouse_user_id"),
            "internationalTrackingNo": row.get("international_tracking_no"),
            "totalWeightGram": row.get("total_weight_gram"),
            "shippingFeeCny": cent_to_cny(row.get("shipping_fee_cny")),
            "taxFeeCny": cent_to_cny(row.get("tax_fee_cny")),
            "otherFeeCny": cent_to_cny(row.get("other_fee_cny")),
            "shippedAt": to_iso(row.get("shipped_at")),
            "arrivedDomesticAt": to_iso(row.get("arrived_domestic_at")),
            "stockedAt": to_iso(row.get("stocked_at")),
            "note": row.get("note"),
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

    def _build_dispatchable_stock_item(self, row: dict[str, Any]) -> dict[str, Any]:
        # 将库存和拼单记录的联查行转换为可排发候选快照。
        return {
            **self._build_stock_item(row),
            "memberUserId": row["record_member_user_id"],
            "groupBuyId": row["record_group_buy_id"],
            "groupBuyItemId": row["record_group_buy_item_id"],
            "recordStatus": row["record_status"],
        }

    def _build_group_buy_record(self, row: dict[str, Any]) -> dict[str, Any]:
        # 将 group_buy_records 行转换为仓库流程需要的拼单记录快照。
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

    def get_stock_item_by_id(self, conn, stock_item_id: str, *, lock: bool = False) -> dict[str, Any] | None:
        # 按 ID 读取库存记录，可在写流程中加行锁。
        lock_sql = "FOR UPDATE" if lock else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM stock_items
                WHERE id = %s
                LIMIT 1
                {lock_sql}
                """,
                (stock_item_id,),
            )
            row = cur.fetchone()
        return self._build_stock_item(row) if row else None

    def get_group_buy_record_by_id(
        self,
        conn,
        group_buy_record_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any] | None:
        # 读取拼单记录，写流程中用于锁定排发相关记录。
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
        return self._build_group_buy_record(row) if row else None

    def get_dispatch_request_by_id(
        self,
        conn,
        dispatch_request_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any] | None:
        # 按 ID 读取排发申请，可在写流程中加行锁。
        lock_sql = "FOR UPDATE" if lock else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM dispatch_requests
                WHERE id = %s
                LIMIT 1
                {lock_sql}
                """,
                (dispatch_request_id,),
            )
            row = cur.fetchone()
        return self._build_dispatch_request(row) if row else None

    def get_dispatch_request_by_domestic_charge_id(
        self,
        conn,
        charge_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any] | None:
        # 通过国内运费费用单反查排发申请。
        lock_sql = "FOR UPDATE" if lock else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM dispatch_requests
                WHERE domestic_charge_id = %s
                LIMIT 1
                {lock_sql}
                """,
                (charge_id,),
            )
            row = cur.fetchone()
        return self._build_dispatch_request(row) if row else None

    def list_dispatch_items(self, conn, dispatch_request_id: str) -> list[dict[str, Any]]:
        # 列出排发申请下的明细行。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM dispatch_items
                WHERE dispatch_request_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (dispatch_request_id,),
            )
            rows = cur.fetchall()
        return [self._build_dispatch_item(row) for row in rows]

    def list_request_stock_items(self, conn, dispatch_request_id: str) -> list[dict[str, Any]]:
        # 通过 dispatch_items 推导排发申请关联的库存记录。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT si.*
                FROM dispatch_items di
                JOIN stock_items si ON si.id = di.stock_item_id
                WHERE di.dispatch_request_id = %s
                ORDER BY di.created_at ASC, di.id ASC
                """,
                (dispatch_request_id,),
            )
            rows = cur.fetchall()
        return [self._build_stock_item(row) for row in rows]

    def list_dispatchable_stock_items(
        self,
        conn,
        *,
        member_user_id: str,
        warehouse_user_id: str | None,
    ) -> list[dict[str, Any]]:
        # 列出状态为 in_stock 且归属指定成员/囤货人的库存候选。
        filters = ["si.status = 'in_stock'", "r.member_user_id = %s"]
        params: list[Any] = [member_user_id]
        if warehouse_user_id is not None:
            filters.append("si.warehouse_user_id = %s")
            params.append(warehouse_user_id)

        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT
                  si.*,
                  r.member_user_id AS record_member_user_id,
                  r.group_buy_id AS record_group_buy_id,
                  r.group_buy_item_id AS record_group_buy_item_id,
                  r.status AS record_status
                FROM stock_items si
                JOIN group_buy_records r ON r.id = si.group_buy_record_id
                WHERE {" AND ".join(filters)}
                ORDER BY si.stocked_at ASC NULLS LAST, si.id ASC
                """,
                params,
            )
            rows = cur.fetchall()
        return [self._build_dispatchable_stock_item(row) for row in rows]

    def create_or_refresh_stock_item(
        self,
        conn,
        *,
        warehouse_user_id: str,
        group_buy_record_id: str,
        quantity: int,
        stocked_at: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        # 为拼单记录创建或刷新一条库存事实，已有排发流程时拒绝刷新。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM stock_items
                WHERE group_buy_record_id = %s
                LIMIT 1
                FOR UPDATE
                """,
                (group_buy_record_id,),
            )
            before_row = cur.fetchone()
            before = self._build_stock_item(before_row) if before_row else None

            if before_row is None:
                stock_item_id = f"stock_item_{secrets.token_hex(8)}"
                cur.execute(
                    """
                    INSERT INTO stock_items (
                      id, warehouse_user_id, group_buy_record_id,
                      quantity, status, stocked_at
                    )
                    VALUES (%s, %s, %s, %s, 'in_stock', %s)
                    RETURNING *
                    """,
                    (stock_item_id, warehouse_user_id, group_buy_record_id, quantity, stocked_at),
                )
            else:
                if before_row["status"] in {"reserved", "shipped", "completed"}:
                    raise AppError(400, "已有排发流程的库存不能重复入库", "DUPLICATED_OPERATION")
                cur.execute(
                    """
                    UPDATE stock_items
                    SET warehouse_user_id = %s,
                        quantity = %s,
                        status = 'in_stock',
                        stocked_at = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (warehouse_user_id, quantity, stocked_at, before_row["id"]),
                )
            after_row = cur.fetchone()
        return before, self._build_stock_item(after_row)

    def mark_stock_item_reserved(self, conn, stock_item_id: str) -> dict[str, Any]:
        # 将库存标记为已被排发申请占用。
        return self._update_stock_item_status(conn, stock_item_id, "reserved")

    def mark_stock_item_shipped(self, conn, stock_item_id: str) -> dict[str, Any]:
        # 将库存标记为已国内发货。
        return self._update_stock_item_status(conn, stock_item_id, "shipped")

    def mark_stock_item_completed(self, conn, stock_item_id: str) -> dict[str, Any]:
        # 将库存标记为排发完成。
        return self._update_stock_item_status(conn, stock_item_id, "completed")

    def _update_stock_item_status(self, conn, stock_item_id: str, status: str) -> dict[str, Any]:
        # 统一更新库存状态并返回最新快照。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE stock_items
                SET status = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (status, stock_item_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "库存记录不存在", "NOT_FOUND")
        return self._build_stock_item(row)

    def create_dispatch_request(
        self,
        conn,
        *,
        requester_user_id: str,
        warehouse_user_id: str,
        status: str,
        receiver_name: str,
        receiver_phone: str,
        receiver_address: str,
        submitted_at: str,
        note: str | None,
    ) -> dict[str, Any]:
        # 创建排发申请主表记录。
        dispatch_request_id = f"dispatch_request_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO dispatch_requests (
                  id, requester_user_id, warehouse_user_id, status,
                  receiver_name, receiver_phone, receiver_address,
                  note, submitted_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    dispatch_request_id,
                    requester_user_id,
                    warehouse_user_id,
                    status,
                    receiver_name,
                    receiver_phone,
                    receiver_address,
                    note,
                    submitted_at,
                ),
            )
            row = cur.fetchone()
        return self._build_dispatch_request(row)

    def create_dispatch_item(
        self,
        conn,
        *,
        dispatch_request_id: str,
        stock_item_id: str,
        group_buy_record_id: str,
        quantity: int,
    ) -> dict[str, Any]:
        # 创建排发申请明细行。
        dispatch_item_id = f"dispatch_item_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO dispatch_items (
                  id, dispatch_request_id, stock_item_id, group_buy_record_id, quantity
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (dispatch_item_id, dispatch_request_id, stock_item_id, group_buy_record_id, quantity),
            )
            row = cur.fetchone()
        return self._build_dispatch_item(row)

    def mark_dispatch_packed(
        self,
        conn,
        dispatch_request_id: str,
        *,
        packed_at: str,
        note: str | None,
    ) -> dict[str, Any]:
        # 记录打包时间并将排发申请推进到 packed。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE dispatch_requests
                SET packed_at = %s,
                    status = 'packed',
                    note = COALESCE(%s, note),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (packed_at, note, dispatch_request_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "排发申请不存在", "NOT_FOUND")
        return self._build_dispatch_request(row)

    def record_domestic_fee(
        self,
        conn,
        dispatch_request_id: str,
        *,
        shipping_fee_cny: str,
        fee_mode: str,
        payment_channel_id: str | None,
        domestic_charge_id: str | None,
        status: str,
        confirmed_at: str | None,
        note: str | None,
    ) -> dict[str, Any]:
        # 记录国内运费模式、金额和关联费用单。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE dispatch_requests
                SET shipping_fee_cny = %s,
                    fee_mode = %s,
                    payment_channel_id = %s,
                    domestic_charge_id = %s,
                    domestic_fee_recorded_at = NOW(),
                    domestic_fee_confirmed_at = %s,
                    status = %s,
                    note = COALESCE(%s, note),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (
                    cny_to_cent(shipping_fee_cny, "shippingFeeCny"),
                    fee_mode,
                    payment_channel_id,
                    domestic_charge_id,
                    confirmed_at,
                    status,
                    note,
                    dispatch_request_id,
                ),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "排发申请不存在", "NOT_FOUND")
        return self._build_dispatch_request(row)

    def create_domestic_shipment(
        self,
        conn,
        *,
        dispatch_request_id: str,
        carrier: str,
        tracking_no: str,
        shipping_fee_cny: str | None,
        fee_mode: str,
        shipped_at: str,
        note: str | None,
    ) -> dict[str, Any]:
        # 创建国内快递记录。
        shipment_id = f"domestic_shipment_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO domestic_shipments (
                  id, dispatch_request_id, carrier, tracking_no,
                  shipping_fee_cny, fee_mode, shipped_at, note
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    shipment_id,
                    dispatch_request_id,
                    carrier,
                    tracking_no,
                    cny_to_cent(shipping_fee_cny, "shippingFeeCny"),
                    fee_mode,
                    shipped_at,
                    note,
                ),
            )
            row = cur.fetchone()
        return self._build_domestic_shipment(row)

    def mark_dispatch_shipped(
        self,
        conn,
        dispatch_request_id: str,
        *,
        domestic_shipment_id: str,
        shipped_at: str,
        note: str | None,
    ) -> dict[str, Any]:
        # 将排发申请更新为已发货并关联国内快递。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE dispatch_requests
                SET domestic_shipment_id = %s,
                    shipped_at = %s,
                    status = 'shipped',
                    note = COALESCE(%s, note),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (domestic_shipment_id, shipped_at, note, dispatch_request_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "排发申请不存在", "NOT_FOUND")
        return self._build_dispatch_request(row)

    def complete_dispatch_request(
        self,
        conn,
        dispatch_request_id: str,
        *,
        completed_at: str,
        note: str | None,
    ) -> dict[str, Any]:
        # 将排发申请更新为已完成。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE dispatch_requests
                SET completed_at = %s,
                    status = 'completed',
                    note = COALESCE(%s, note),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (completed_at, note, dispatch_request_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "排发申请不存在", "NOT_FOUND")
        return self._build_dispatch_request(row)

    def confirm_domestic_fee(
        self,
        conn,
        dispatch_request_id: str,
        *,
        proof_id: str | None,
    ) -> dict[str, Any]:
        # 确认预付国内运费已完成付款。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE dispatch_requests
                SET status = 'domestic_fee_confirmed',
                    domestic_fee_confirmed_at = NOW(),
                    domestic_fee_confirmed_proof_id = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (proof_id, dispatch_request_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "排发申请不存在", "NOT_FOUND")
        return self._build_dispatch_request(row)

    def get_international_batch_for_update(self, conn, batch_id: str) -> dict[str, Any] | None:
        # 加锁读取国际批次，供到国内后入库使用。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM international_batches
                WHERE id = %s
                LIMIT 1
                FOR UPDATE
                """,
                (batch_id,),
            )
            row = cur.fetchone()
        return self._build_international_batch(row) if row else None

    def list_international_batch_record_ids(self, conn, batch_id: str) -> list[str]:
        # 列出国际批次下关联的拼单记录 ID。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT group_buy_record_id
                FROM international_batch_records
                WHERE batch_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (batch_id,),
            )
            rows = cur.fetchall()
        return [row["group_buy_record_id"] for row in rows]

    def mark_international_batch_stocked(
        self,
        conn,
        batch_id: str,
        *,
        stocked_at: str,
        note: str | None,
    ) -> dict[str, Any]:
        # 将国际批次标记为已完成国内入库。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE international_batches
                SET status = 'stocked',
                    stocked_at = %s,
                    note = COALESCE(%s, note),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (stocked_at, note, batch_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "国际批次不存在", "NOT_FOUND")
        return self._build_international_batch(row)
