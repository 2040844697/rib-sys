from __future__ import annotations

import secrets
from decimal import Decimal
from typing import Any

from ..db_access import to_iso
from ..errors import AppError


class OrderLogisticsRepository:
    def __init__(self, config):
        self.config = config

    def _dict_row(self):
        from psycopg.rows import dict_row

        return dict_row

    def _from_cent(self, amount_cny_cent: int | None) -> str | None:
        # 金额在 DB 存分，对外仍保持两位小数字符串。
        if amount_cny_cent is None:
            return None
        cents = abs(int(amount_cny_cent))
        sign = "-" if amount_cny_cent < 0 else ""
        return f"{sign}{cents // 100}.{cents % 100:02d}"

    def _to_cent(self, amount_cny: str | Decimal | int) -> int:
        # Repository 只接收上层已校验金额，统一转为分入库。
        return int((Decimal(str(amount_cny)) * Decimal("100")).to_integral_exact())

    def _build_order_screenshot(self, row: dict[str, Any]) -> dict[str, Any]:
        # 将下单截图行转成模块和前端沿用的 camelCase。
        return {
            "id": row["id"],
            "groupBuyId": row["group_buy_id"],
            "uploadedBy": row["uploaded_by"],
            "fileObjectId": row.get("screenshot_file_object_id"),
            "screenshotUrl": row["screenshot_url"],
            "isOrdered": bool(row["is_ordered"]),
            "orderedAt": to_iso(row.get("ordered_at")),
            "website": row.get("website"),
            "websiteOrderNo": row.get("website_order_no"),
            "note": row.get("note"),
            "createdAt": to_iso(row.get("created_at")),
        }

    def _build_international_batch(self, row: dict[str, Any]) -> dict[str, Any]:
        # 将国际批次行转成模块和前端沿用的 camelCase。
        return {
            "id": row["id"],
            "forwarderName": row["forwarder_name"],
            "batchNo": row.get("batch_no"),
            "status": row["status"],
            "warehouseUserId": row.get("warehouse_user_id"),
            "internationalTrackingNo": row.get("international_tracking_no"),
            "totalWeightGram": row.get("total_weight_gram"),
            "shippingFeeCny": self._from_cent(row.get("shipping_fee_cny")),
            "taxFeeCny": self._from_cent(row.get("tax_fee_cny")),
            "otherFeeCny": self._from_cent(row.get("other_fee_cny")),
            "shippedAt": to_iso(row.get("shipped_at")),
            "arrivedDomesticAt": to_iso(row.get("arrived_domestic_at")),
            "stockedAt": to_iso(row.get("stocked_at")),
            "note": row.get("note"),
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

    def _build_batch_record_link(self, row: dict[str, Any]) -> dict[str, Any]:
        # 将批次记录关联行转成 camelCase。
        return {
            "id": row["id"],
            "batchId": row["batch_id"],
            "groupBuyRecordId": row["group_buy_record_id"],
            "createdAt": to_iso(row.get("created_at")),
        }

    def _build_fee_allocation(self, row: dict[str, Any]) -> dict[str, Any]:
        # 将国际费用分摊行转成 camelCase，并把金额分转成字符串。
        return {
            "id": row["id"],
            "batchId": row["batch_id"],
            "userId": row["user_id"],
            "weightGram": row.get("weight_gram"),
            "shippingFeeCny": self._from_cent(row["shipping_fee_cny"]),
            "taxFeeCny": self._from_cent(row["tax_fee_cny"]),
            "otherFeeCny": self._from_cent(row["other_fee_cny"]),
            "adjustmentCny": self._from_cent(row["adjustment_cny"]),
            "totalCny": self._from_cent(row["total_cny"]),
            "note": row.get("note"),
            "chargeId": row.get("charge_id"),
            "createdAt": to_iso(row.get("created_at")),
        }

    def get_order_screenshot_by_id(
        self,
        conn,
        order_screenshot_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any] | None:
        # 按 ID 读取下单截图，可在标记已下单时加锁。
        lock_sql = "FOR UPDATE" if lock else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM order_screenshots
                WHERE id = %s
                LIMIT 1
                {lock_sql}
                """,
                (order_screenshot_id,),
            )
            row = cur.fetchone()
        return self._build_order_screenshot(row) if row else None

    def create_order_screenshot(
        self,
        conn,
        *,
        group_buy_id: str,
        uploaded_by: str,
        file_object_id: str | None,
        screenshot_url: str,
        is_ordered: bool,
        ordered_at: str | None,
        website: str | None,
        website_order_no: str | None,
        note: str | None,
    ) -> dict[str, Any]:
        # 新建下单截图记录。
        screenshot_id = f"order_screenshot_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO order_screenshots (
                  id, group_buy_id, uploaded_by, screenshot_file_object_id,
                  screenshot_url, is_ordered, ordered_at, website, website_order_no, note
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    screenshot_id,
                    group_buy_id,
                    uploaded_by,
                    file_object_id,
                    screenshot_url,
                    is_ordered,
                    ordered_at,
                    website,
                    website_order_no,
                    note,
                ),
            )
            row = cur.fetchone()
        return self._build_order_screenshot(row)

    def mark_order_screenshot_ordered(
        self,
        conn,
        order_screenshot_id: str,
        *,
        ordered_at: str,
    ) -> dict[str, Any]:
        # 标记下单截图已经覆盖下单事实。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE order_screenshots
                SET is_ordered = TRUE,
                    ordered_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (ordered_at, order_screenshot_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "下单截图不存在", "NOT_FOUND")
        return self._build_order_screenshot(row)

    def get_international_batch_by_id(
        self,
        conn,
        batch_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any] | None:
        # 按 ID 读取国际批次，可在写流程中加锁。
        lock_sql = "FOR UPDATE" if lock else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM international_batches
                WHERE id = %s
                LIMIT 1
                {lock_sql}
                """,
                (batch_id,),
            )
            row = cur.fetchone()
        return self._build_international_batch(row) if row else None

    def create_international_batch(
        self,
        conn,
        *,
        forwarder_name: str,
        batch_no: str | None,
        status: str,
        warehouse_user_id: str | None,
        international_tracking_no: str | None,
        note: str | None,
    ) -> dict[str, Any]:
        # 新建国际批次。
        batch_id = f"intl_batch_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO international_batches (
                  id, forwarder_name, batch_no, status, warehouse_user_id,
                  international_tracking_no, note
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    batch_id,
                    forwarder_name,
                    batch_no,
                    status,
                    warehouse_user_id,
                    international_tracking_no,
                    note,
                ),
            )
            row = cur.fetchone()
        return self._build_international_batch(row)

    def update_international_batch_shipping(
        self,
        conn,
        batch_id: str,
        *,
        international_tracking_no: str | None,
        shipped_at: str | None,
        status: str,
        note: str | None,
    ) -> dict[str, Any]:
        # 更新国际批次物流字段和状态。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE international_batches
                SET international_tracking_no = %s,
                    shipped_at = %s,
                    status = %s,
                    note = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (international_tracking_no, shipped_at, status, note, batch_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "国际批次不存在", "NOT_FOUND")
        return self._build_international_batch(row)

    def record_batch_arrived_domestic(
        self,
        conn,
        batch_id: str,
        *,
        arrived_domestic_at: str,
        status: str,
        note: str | None,
    ) -> dict[str, Any]:
        # 记录国际批次到达国内。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE international_batches
                SET arrived_domestic_at = %s,
                    status = %s,
                    note = COALESCE(%s, note),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (arrived_domestic_at, status, note, batch_id),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "国际批次不存在", "NOT_FOUND")
        return self._build_international_batch(row)

    def update_batch_fee_summary(
        self,
        conn,
        batch_id: str,
        *,
        total_weight_gram: int,
        shipping_fee_cny: str,
        tax_fee_cny: str,
        other_fee_cny: str,
        status: str,
        note: str | None,
    ) -> dict[str, Any]:
        # 回写批次费用汇总，金额字段按分入库。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE international_batches
                SET total_weight_gram = %s,
                    shipping_fee_cny = %s,
                    tax_fee_cny = %s,
                    other_fee_cny = %s,
                    status = %s,
                    note = COALESCE(%s, note),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (
                    total_weight_gram,
                    self._to_cent(shipping_fee_cny),
                    self._to_cent(tax_fee_cny),
                    self._to_cent(other_fee_cny),
                    status,
                    note,
                    batch_id,
                ),
            )
            row = cur.fetchone()
        if row is None:
            raise AppError(404, "国际批次不存在", "NOT_FOUND")
        return self._build_international_batch(row)

    def list_batch_record_links(self, conn, batch_id: str) -> list[dict[str, Any]]:
        # 查询批次下全部记录关联。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM international_batch_records
                WHERE batch_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (batch_id,),
            )
            rows = cur.fetchall()
        return [self._build_batch_record_link(row) for row in rows]

    def list_batch_record_ids(self, conn, batch_id: str) -> list[str]:
        # 查询批次下全部拼单记录 ID。
        return [link["groupBuyRecordId"] for link in self.list_batch_record_links(conn, batch_id)]

    def add_batch_record_links(
        self,
        conn,
        *,
        batch_id: str,
        group_buy_record_ids: list[str],
    ) -> list[dict[str, Any]]:
        # 批量写入批次和拼单记录关联。
        links: list[dict[str, Any]] = []
        for record_id in group_buy_record_ids:
            link_id = f"intl_batch_record_{secrets.token_hex(8)}"
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    """
                    INSERT INTO international_batch_records (
                      id, batch_id, group_buy_record_id
                    )
                    VALUES (%s, %s, %s)
                    RETURNING *
                    """,
                    (link_id, batch_id, record_id),
                )
                row = cur.fetchone()
            links.append(self._build_batch_record_link(row))
        return links

    def find_open_batch_link_by_record_id(
        self,
        conn,
        group_buy_record_id: str,
    ) -> dict[str, Any] | None:
        # 查找记录是否已在未关闭国际批次中。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT ibr.*
                FROM international_batch_records ibr
                JOIN international_batches ib ON ib.id = ibr.batch_id
                WHERE ibr.group_buy_record_id = %s
                  AND ib.status <> 'closed'
                ORDER BY ibr.created_at ASC, ibr.id ASC
                LIMIT 1
                """,
                (group_buy_record_id,),
            )
            row = cur.fetchone()
        return self._build_batch_record_link(row) if row else None

    def list_batch_allocations(self, conn, batch_id: str) -> list[dict[str, Any]]:
        # 查询批次费用分摊。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM international_fee_allocations
                WHERE batch_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (batch_id,),
            )
            rows = cur.fetchall()
        return [self._build_fee_allocation(row) for row in rows]

    def create_fee_allocation(
        self,
        conn,
        *,
        batch_id: str,
        user_id: str,
        weight_gram: int,
        shipping_fee_cny: str,
        tax_fee_cny: str,
        other_fee_cny: str,
        adjustment_cny: str,
        total_cny: str,
        note: str | None,
        charge_id: str | None,
    ) -> dict[str, Any]:
        # 写入单条国际费用分摊，并记录生成的 charge_id。
        allocation_id = f"intl_fee_allocation_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO international_fee_allocations (
                  id, batch_id, user_id, weight_gram, shipping_fee_cny,
                  tax_fee_cny, other_fee_cny, adjustment_cny, total_cny,
                  note, charge_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    allocation_id,
                    batch_id,
                    user_id,
                    weight_gram,
                    self._to_cent(shipping_fee_cny),
                    self._to_cent(tax_fee_cny),
                    self._to_cent(other_fee_cny),
                    self._to_cent(adjustment_cny),
                    self._to_cent(total_cny),
                    note,
                    charge_id,
                ),
            )
            row = cur.fetchone()
        return self._build_fee_allocation(row)
