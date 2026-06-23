from __future__ import annotations

import json
import secrets
from datetime import datetime
from typing import Any

from ..config import Config


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _to_cent(amount_cny: str) -> int:
    whole, decimal = amount_cny.split(".")
    return int(whole) * 100 + int(decimal)


def _from_cent(amount_cny_cent: int) -> str:
    return f"{amount_cny_cent / 100:.2f}"


class GroupBuyRepository:
    def __init__(self, config: Config):
        self.config = config

    def _dict_row(self):
        from psycopg.rows import dict_row

        return dict_row

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
        aliases = row["alias_snapshot"] or []
        character_names = row["character_names_snapshot"] or []
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

    def get_group_buy_by_id(self, conn, group_buy_id: str) -> dict[str, Any] | None:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM group_buys
                WHERE id = %s
                LIMIT 1
                """,
                (group_buy_id,),
            )
            row = cur.fetchone()
        return self._build_group_buy_snapshot(row) if row else None

    def get_group_buy_item_by_id(self, conn, group_buy_item_id: str) -> dict[str, Any] | None:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM group_buy_items
                WHERE id = %s
                LIMIT 1
                """,
                (group_buy_item_id,),
            )
            row = cur.fetchone()
        return self._build_group_buy_item_snapshot(row) if row else None

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

    def create_audit_log(
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
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_logs (
                  id,
                  actor_user_id,
                  action,
                  object_type,
                  object_id,
                  before_json,
                  after_json,
                  reason,
                  created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, NOW())
                """,
                (
                    f"audit_{secrets.token_hex(8)}",
                    actor_user_id,
                    action,
                    object_type,
                    object_id,
                    None if before is None else json.dumps(before, ensure_ascii=False),
                    None if after is None else json.dumps(after, ensure_ascii=False),
                    reason,
                ),
            )
