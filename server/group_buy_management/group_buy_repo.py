from __future__ import annotations

import json
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ..config import Config
from ..errors import AppError


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


CENT = Decimal("0.01")


def _json_from_db(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def _to_cent(amount_cny: str) -> int:
    try:
        amount = Decimal(str(amount_cny))
    except (InvalidOperation, ValueError) as exc:
        raise AppError(400, "金额格式不正确", "VALIDATION_FAILED") from exc
    quantized = amount.quantize(CENT)
    if amount != quantized:
        raise AppError(400, "金额最多支持两位小数", "VALIDATION_FAILED")
    return int(quantized * 100)


def _from_cent(amount_cny_cent: int) -> str:
    cents = abs(int(amount_cny_cent))
    sign = "-" if amount_cny_cent < 0 else ""
    return f"{sign}{cents // 100}.{cents % 100:02d}"


class GroupBuyRepository:
    def __init__(self, config: Config):
        self.config = config

    def _dict_row(self):
        from psycopg.rows import dict_row

        return dict_row

    def _build_group_buy_list_item(self, row: dict[str, Any]) -> dict[str, Any]:
        # 列表 DTO 在团购快照基础上补齐商品聚合和当前用户认领数。
        return {
            **self._build_group_buy_snapshot(row),
            "itemCount": int(row.get("item_count") or 0),
            "availableQuantity": int(row.get("available_quantity") or 0),
            "myRecordCount": int(row.get("my_record_count") or 0),
            "coverImageUrl": row.get("cover_image_url"),
        }

    def _build_group_buy_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "groupId": row["group_id"],
            "type": row["type"],
            "title": row["title"],
            "description": row["description"],
            "status": row["status"],
            "ownerUserId": row["owner_user_id"],
            "closeAt": _iso_or_none(row["close_at"]),
            "paymentChannelId": row["payment_channel_id"],
            "warehouseUserId": row["warehouse_user_id"],
            "createdAt": _iso_or_none(row["created_at"]),
            "updatedAt": _iso_or_none(row["updated_at"]),
        }

    def _build_group_buy_item_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        aliases = _json_from_db(row["alias_snapshot"]) or []
        character_names = _json_from_db(row["character_names_snapshot"]) or []
        return {
            "id": row["id"],
            "groupBuyId": row["group_buy_id"],
            "goodsId": row["goods_id"],
            "name": row["name_snapshot"],
            "aliases": aliases,
            "characterName": character_names[0] if character_names else None,
            "characterNames": character_names,
            "description": row["description_snapshot"],
            "imageUrl": row["image_url_snapshot"],
            "unitPriceCny": _from_cent(row["unit_price_cny"]),
            "releasePriceJpy": row["release_price_jpy_snapshot"],
            "suggestedPriceJpy": row["suggested_price_jpy_snapshot"],
            "domesticSpotSuggestedPriceCny": (
                _from_cent(row["domestic_spot_suggested_price_cny_snapshot"])
                if row["domestic_spot_suggested_price_cny_snapshot"] is not None
                else None
            ),
            "lengthMm": row["length_mm_snapshot"],
            "widthMm": row["width_mm_snapshot"],
            "weightGram": row["weight_gram_snapshot"],
            "totalQuantity": row["total_quantity"],
            "reservedQuantity": row["reserved_quantity"],
            "claimedQuantity": row["claimed_quantity"],
            "availableQuantity": row["available_quantity"],
            "status": row["status"],
            "note": row["note"],
            "createdAt": _iso_or_none(row["created_at"]),
            "updatedAt": _iso_or_none(row["updated_at"]),
        }

    def _build_group_buy_record_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
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
            "createdAt": _iso_or_none(row.get("created_at")),
            "updatedAt": _iso_or_none(row.get("updated_at")),
        }

    def get_group_buy_by_id(
        self,
        conn,
        group_buy_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any] | None:
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
        return self._build_group_buy_snapshot(row) if row else None

    def get_group_buy_item_by_id(
        self,
        conn,
        group_buy_item_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any] | None:
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
        return self._build_group_buy_item_snapshot(row) if row else None

    def list_group_buys(
        self,
        conn,
        *,
        group_id: str,
        member_user_id: str,
        statuses: list[str] | None,
        keyword: str | None,
    ) -> list[dict[str, Any]]:
        # 列表查询只从 DB 聚合，不再读取旧 JSON 中的团购和商品。
        conditions = ["gb.group_id = %s"]
        params: list[Any] = [group_id]
        if statuses:
            conditions.append("gb.status = ANY(%s)")
            params.append(statuses)
        if keyword:
            conditions.append("(LOWER(gb.title) LIKE %s OR LOWER(gb.type) LIKE %s)")
            like_keyword = f"%{keyword.lower()}%"
            params.extend([like_keyword, like_keyword])

        where_sql = " AND ".join(conditions)
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT
                  gb.*,
                  COALESCE(item_stats.item_count, 0) AS item_count,
                  COALESCE(item_stats.available_quantity, 0) AS available_quantity,
                  item_stats.cover_image_url,
                  COALESCE(member_records.my_record_count, 0) AS my_record_count
                FROM group_buys gb
                LEFT JOIN (
                  SELECT
                    group_buy_id,
                    COUNT(*) AS item_count,
                    COALESCE(SUM(available_quantity), 0) AS available_quantity,
                    (ARRAY_AGG(image_url_snapshot ORDER BY created_at ASC, id ASC)
                      FILTER (
                        WHERE image_url_snapshot IS NOT NULL
                          AND image_url_snapshot <> ''
                      ))[1] AS cover_image_url
                  FROM group_buy_items
                  GROUP BY group_buy_id
                ) item_stats ON item_stats.group_buy_id = gb.id
                LEFT JOIN (
                  SELECT group_buy_id, COALESCE(SUM(quantity), 0) AS my_record_count
                  FROM group_buy_records
                  WHERE member_user_id = %s
                  GROUP BY group_buy_id
                ) member_records ON member_records.group_buy_id = gb.id
                WHERE {where_sql}
                ORDER BY gb.created_at DESC, gb.id DESC
                """,
                [member_user_id, *params],
            )
            rows = cur.fetchall()
        return [self._build_group_buy_list_item(row) for row in rows]

    def list_group_buy_items(self, conn, group_buy_id: str) -> list[dict[str, Any]]:
        # 详情页按商品创建顺序展示当前数据库库存快照。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM group_buy_items
                WHERE group_buy_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (group_buy_id,),
            )
            rows = cur.fetchall()
        return [self._build_group_buy_item_snapshot(row) for row in rows]

    def list_member_records(
        self,
        conn,
        *,
        group_buy_id: str,
        member_user_id: str,
    ) -> list[dict[str, Any]]:
        # 详情页只返回当前用户自己的认领记录摘要。
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
        return [self._build_group_buy_record_snapshot(row) for row in rows]

    def get_group_buy_record_for_member(
        self,
        conn,
        *,
        group_buy_item_id: str,
        member_user_id: str,
        lock: bool = False,
    ) -> dict[str, Any] | None:
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
        return self._build_group_buy_record_snapshot(row) if row else None

    def create_group_buy(
        self,
        conn,
        *,
        group_id: str,
        type_: str,
        title: str,
        description: str | None,
        status: str,
        owner_user_id: str,
        close_at: datetime | None,
        payment_channel_id: str | None,
        warehouse_user_id: str | None,
    ) -> dict[str, Any]:
        group_buy_id = f"gb_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO group_buys (
                  id,
                  group_id,
                  type,
                  title,
                  description,
                  status,
                  owner_user_id,
                  close_at,
                  payment_channel_id,
                  warehouse_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    group_buy_id,
                    group_id,
                    type_,
                    title,
                    description,
                    status,
                    owner_user_id,
                    close_at,
                    payment_channel_id,
                    warehouse_user_id,
                ),
            )
            row = cur.fetchone()
        return self._build_group_buy_snapshot(row)

    def update_group_buy(
        self,
        conn,
        *,
        group_buy_id: str,
        type_: str,
        title: str,
        description: str | None,
        close_at: datetime | None,
        payment_channel_id: str | None,
        warehouse_user_id: str | None,
    ) -> dict[str, Any]:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE group_buys
                SET type = %s,
                    title = %s,
                    description = %s,
                    close_at = %s,
                    payment_channel_id = %s,
                    warehouse_user_id = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (
                    type_,
                    title,
                    description,
                    close_at,
                    payment_channel_id,
                    warehouse_user_id,
                    group_buy_id,
                ),
            )
            row = cur.fetchone()
        return self._build_group_buy_snapshot(row)

    def change_group_buy_status(
        self,
        conn,
        *,
        group_buy_id: str,
        new_status: str,
    ) -> dict[str, Any]:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE group_buys
                SET status = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (new_status, group_buy_id),
            )
            row = cur.fetchone()
        return self._build_group_buy_snapshot(row)

    def create_group_buy_item(
        self,
        conn,
        *,
        group_buy_id: str,
        goods_id: str | None,
        name_snapshot: str,
        alias_snapshot: list[str],
        character_names_snapshot: list[str],
        description_snapshot: str | None,
        image_url_snapshot: str | None,
        unit_price_cny: str,
        release_price_jpy_snapshot: int | None,
        suggested_price_jpy_snapshot: int | None,
        domestic_spot_suggested_price_cny_snapshot: str | None,
        length_mm_snapshot: int | None,
        width_mm_snapshot: int | None,
        weight_gram_snapshot: int | None,
        total_quantity: int,
        reserved_quantity: int,
        claimed_quantity: int,
        available_quantity: int,
        note: str | None,
    ) -> dict[str, Any]:
        group_buy_item_id = f"gbi_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO group_buy_items (
                  id,
                  group_buy_id,
                  goods_id,
                  name_snapshot,
                  alias_snapshot,
                  character_names_snapshot,
                  description_snapshot,
                  image_url_snapshot,
                  unit_price_cny,
                  release_price_jpy_snapshot,
                  suggested_price_jpy_snapshot,
                  domestic_spot_suggested_price_cny_snapshot,
                  length_mm_snapshot,
                  width_mm_snapshot,
                  weight_gram_snapshot,
                  total_quantity,
                  reserved_quantity,
                  claimed_quantity,
                  available_quantity,
                  note
                )
                VALUES (
                  %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING *
                """,
                (
                    group_buy_item_id,
                    group_buy_id,
                    goods_id,
                    name_snapshot,
                    json.dumps(alias_snapshot, ensure_ascii=False),
                    json.dumps(character_names_snapshot, ensure_ascii=False),
                    description_snapshot,
                    image_url_snapshot,
                    _to_cent(unit_price_cny),
                    release_price_jpy_snapshot,
                    suggested_price_jpy_snapshot,
                    (
                        _to_cent(domestic_spot_suggested_price_cny_snapshot)
                        if domestic_spot_suggested_price_cny_snapshot is not None
                        else None
                    ),
                    length_mm_snapshot,
                    width_mm_snapshot,
                    weight_gram_snapshot,
                    total_quantity,
                    reserved_quantity,
                    claimed_quantity,
                    available_quantity,
                    note,
                ),
            )
            row = cur.fetchone()
        return self._build_group_buy_item_snapshot(row)

    def update_group_buy_item(
        self,
        conn,
        *,
        group_buy_item_id: str,
        goods_id: str | None,
        name_snapshot: str,
        alias_snapshot: list[str],
        character_names_snapshot: list[str],
        description_snapshot: str | None,
        image_url_snapshot: str | None,
        unit_price_cny: str,
        release_price_jpy_snapshot: int | None,
        suggested_price_jpy_snapshot: int | None,
        domestic_spot_suggested_price_cny_snapshot: str | None,
        length_mm_snapshot: int | None,
        width_mm_snapshot: int | None,
        weight_gram_snapshot: int | None,
        total_quantity: int,
        reserved_quantity: int,
        claimed_quantity: int,
        available_quantity: int,
        note: str | None,
    ) -> dict[str, Any]:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE group_buy_items
                SET goods_id = %s,
                    name_snapshot = %s,
                    alias_snapshot = %s::jsonb,
                    character_names_snapshot = %s::jsonb,
                    description_snapshot = %s,
                    image_url_snapshot = %s,
                    unit_price_cny = %s,
                    release_price_jpy_snapshot = %s,
                    suggested_price_jpy_snapshot = %s,
                    domestic_spot_suggested_price_cny_snapshot = %s,
                    length_mm_snapshot = %s,
                    width_mm_snapshot = %s,
                    weight_gram_snapshot = %s,
                    total_quantity = %s,
                    reserved_quantity = %s,
                    claimed_quantity = %s,
                    available_quantity = %s,
                    note = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (
                    goods_id,
                    name_snapshot,
                    json.dumps(alias_snapshot, ensure_ascii=False),
                    json.dumps(character_names_snapshot, ensure_ascii=False),
                    description_snapshot,
                    image_url_snapshot,
                    _to_cent(unit_price_cny),
                    release_price_jpy_snapshot,
                    suggested_price_jpy_snapshot,
                    (
                        _to_cent(domestic_spot_suggested_price_cny_snapshot)
                        if domestic_spot_suggested_price_cny_snapshot is not None
                        else None
                    ),
                    length_mm_snapshot,
                    width_mm_snapshot,
                    weight_gram_snapshot,
                    total_quantity,
                    reserved_quantity,
                    claimed_quantity,
                    available_quantity,
                    note,
                    group_buy_item_id,
                ),
            )
            row = cur.fetchone()
        return self._build_group_buy_item_snapshot(row)

    def update_group_buy_item_quantities(
        self,
        conn,
        *,
        group_buy_item_id: str,
        reserved_quantity: int,
        claimed_quantity: int,
        available_quantity: int,
    ) -> dict[str, Any]:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE group_buy_items
                SET reserved_quantity = %s,
                    claimed_quantity = %s,
                    available_quantity = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (
                    reserved_quantity,
                    claimed_quantity,
                    available_quantity,
                    group_buy_item_id,
                ),
            )
            row = cur.fetchone()
        return self._build_group_buy_item_snapshot(row)

    def create_group_buy_record(
        self,
        conn,
        *,
        group_buy_id: str,
        group_buy_item_id: str,
        member_user_id: str,
        status: str,
        quantity: int,
        status_priority: int,
        note: str | None,
    ) -> dict[str, Any]:
        # 成员第一次认领商品时创建 DB 版拼单记录。
        group_buy_record_id = f"record_{secrets.token_hex(8)}"
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
                  note
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    group_buy_record_id,
                    group_buy_id,
                    group_buy_item_id,
                    member_user_id,
                    status,
                    quantity,
                    status_priority,
                    note,
                ),
            )
            row = cur.fetchone()
        return self._build_group_buy_record_snapshot(row)

    def update_group_buy_record_quantity(
        self,
        conn,
        *,
        group_buy_record_id: str,
        quantity: int,
        status: str,
        status_priority: int,
    ) -> dict[str, Any]:
        # 同一成员重复认领同一商品时追加数量，而不是创建重复记录。
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE group_buy_records
                SET quantity = %s,
                    status = %s,
                    status_priority = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (
                    quantity,
                    status,
                    status_priority,
                    group_buy_record_id,
                ),
            )
            row = cur.fetchone()
        return self._build_group_buy_record_snapshot(row)

    def link_group_buy_record_charge(
        self,
        conn,
        *,
        group_buy_record_id: str,
        charge_type: str,
        charge_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # 费用模块创建首款后，把 charge_id 写回认领记录。
        column_by_type = {
            "initial_goods": "goods_charge_id",
            "international": "international_charge_id",
            "domestic_shipping": "domestic_shipping_charge_id",
        }
        column_name = column_by_type.get(charge_type)
        if column_name is None:
            raise RuntimeError(f"Unsupported group buy record charge type: {charge_type}")

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
            before_row = cur.fetchone()
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
            after_row = cur.fetchone()
        return (
            self._build_group_buy_record_snapshot(before_row),
            self._build_group_buy_record_snapshot(after_row),
        )

    def create_price_adjustment(
        self,
        conn,
        *,
        group_buy_id: str,
        group_buy_item_id: str,
        old_price_cny: str,
        new_price_cny: str,
        impact_scope: str,
        reason: str,
        status: str,
        requested_by: str,
    ) -> dict[str, Any]:
        price_adjustment_id = f"price_adjustment_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO price_adjustments (
                  id,
                  group_buy_id,
                  group_buy_item_id,
                  old_price_cny,
                  new_price_cny,
                  impact_scope,
                  reason,
                  status,
                  requested_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    price_adjustment_id,
                    group_buy_id,
                    group_buy_item_id,
                    _to_cent(old_price_cny),
                    _to_cent(new_price_cny),
                    impact_scope,
                    reason,
                    status,
                    requested_by,
                ),
            )
            row = cur.fetchone()
        return {
            "id": row["id"],
            "groupBuyId": row["group_buy_id"],
            "groupBuyItemId": row["group_buy_item_id"],
            "oldPriceCny": _from_cent(row["old_price_cny"]),
            "newPriceCny": _from_cent(row["new_price_cny"]),
            "impactScope": row["impact_scope"],
            "reason": row["reason"],
            "status": row["status"],
            "requestedBy": row["requested_by"],
            "createdAt": _iso_or_none(row["created_at"]),
        }
