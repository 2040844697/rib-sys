from __future__ import annotations

import json
import secrets
from typing import Any

from ..config import Config
from ..db_access import to_iso


def _json_array(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return json.loads(value)
    return list(value)


class GoodsCatalogRepository:
    def __init__(self, config: Config):
        self.config = config

    def _dict_row(self):
        try:
            from psycopg.rows import dict_row
        except ModuleNotFoundError:
            return None

        return dict_row

    def _build_goods_record(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "seriesName": row.get("series_name"),
            "aliases": _json_array(row.get("aliases")),
            "characterNames": _json_array(row.get("character_names")),
            "sku": row.get("sku"),
            "description": row.get("description"),
            "mainImageId": row.get("main_image_id"),
            "mainImageUrl": row.get("main_image_url"),
            "lengthMm": row.get("length_mm"),
            "widthMm": row.get("width_mm"),
            "weightGram": row.get("weight_gram"),
            "releasePriceJpy": row.get("release_price_jpy"),
            "suggestedPriceJpy": row.get("suggested_price_jpy"),
            "domesticSpotSuggestedPriceCny": row.get("domestic_spot_suggested_price_cny"),
            "status": row["status"],
            "imageCount": row.get("image_count", 0) or 0,
            "createdAt": to_iso(row.get("created_at")),
            "updatedAt": to_iso(row.get("updated_at")),
        }

    def _build_goods_image_record(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "goodsId": row["goods_id"],
            "fileObjectId": row.get("file_object_id"),
            "imageUrl": row["image_url"],
            "sortOrder": row.get("sort_order", 0),
            "isPrimary": bool(row.get("is_primary")),
            "uploadedBy": row.get("uploaded_by"),
            "createdAt": to_iso(row.get("created_at")),
        }

    def get_goods_by_id(self, conn, goods_id: str, *, lock: bool = False) -> dict[str, Any] | None:
        lock_sql = "FOR UPDATE" if lock else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM goods
                WHERE id = %s
                LIMIT 1
                {lock_sql}
                """,
                (goods_id,),
            )
            row = cur.fetchone()
        return self._build_goods_record(row) if row else None

    def get_goods_image_by_id(
        self,
        conn,
        goods_image_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any] | None:
        lock_sql = "FOR UPDATE" if lock else ""
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT *
                FROM goods_images
                WHERE id = %s
                LIMIT 1
                {lock_sql}
                """,
                (goods_image_id,),
            )
            row = cur.fetchone()
        return self._build_goods_image_record(row) if row else None

    def list_goods_images(self, conn, goods_id: str) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                SELECT *
                FROM goods_images
                WHERE goods_id = %s
                ORDER BY sort_order ASC, created_at ASC, id ASC
                """,
                (goods_id,),
            )
            rows = cur.fetchall()
        return [self._build_goods_image_record(row) for row in rows]

    def create_goods(self, conn, fields: dict[str, Any]) -> dict[str, Any]:
        goods_id = f"goods_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO goods (
                  id,
                  name,
                  series_name,
                  aliases,
                  character_names,
                  sku,
                  description,
                  length_mm,
                  width_mm,
                  weight_gram,
                  release_price_jpy,
                  suggested_price_jpy,
                  domestic_spot_suggested_price_cny,
                  status,
                  created_at,
                  updated_at
                )
                VALUES (
                  %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                )
                RETURNING *
                """,
                (
                    goods_id,
                    fields["name"],
                    fields["series_name"],
                    json.dumps(fields["aliases"], ensure_ascii=False),
                    json.dumps(fields["character_names"], ensure_ascii=False),
                    fields["sku"],
                    fields["description"],
                    fields["length_mm"],
                    fields["width_mm"],
                    fields["weight_gram"],
                    fields["release_price_jpy"],
                    fields["suggested_price_jpy"],
                    fields["domestic_spot_suggested_price_cny"],
                    fields["status"],
                ),
            )
            row = cur.fetchone()
        return self._build_goods_record(row)

    def update_goods(self, conn, *, goods_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        set_fragments: list[str] = []
        params: list[Any] = []
        for column, value in updates.items():
            if column in {"aliases", "character_names"}:
                set_fragments.append(f"{column} = %s::jsonb")
                params.append(json.dumps(value, ensure_ascii=False))
            else:
                set_fragments.append(f"{column} = %s")
                params.append(value)

        set_fragments.append("updated_at = NOW()")
        params.append(goods_id)

        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                UPDATE goods
                SET {", ".join(set_fragments)}
                WHERE id = %s
                RETURNING *
                """,
                params,
            )
            row = cur.fetchone()
        return self._build_goods_record(row)

    def create_goods_image(
        self,
        conn,
        *,
        goods_id: str,
        file_object_id: str | None,
        image_url: str,
        sort_order: int,
        is_primary: bool,
        uploaded_by: str,
    ) -> dict[str, Any]:
        goods_image_id = f"goods_image_{secrets.token_hex(8)}"
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                INSERT INTO goods_images (
                  id,
                  goods_id,
                  file_object_id,
                  image_url,
                  sort_order,
                  is_primary,
                  uploaded_by,
                  created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING *
                """,
                (
                    goods_image_id,
                    goods_id,
                    file_object_id,
                    image_url,
                    sort_order,
                    is_primary,
                    uploaded_by,
                ),
            )
            row = cur.fetchone()
        return self._build_goods_image_record(row)

    def clear_primary_images(self, conn, *, goods_id: str) -> None:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE goods_images
                SET is_primary = FALSE
                WHERE goods_id = %s
                """,
                (goods_id,),
            )

    def set_goods_image_primary(self, conn, *, goods_image_id: str) -> dict[str, Any]:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE goods_images
                SET is_primary = TRUE
                WHERE id = %s
                RETURNING *
                """,
                (goods_image_id,),
            )
            row = cur.fetchone()
        return self._build_goods_image_record(row)

    def update_main_image(
        self,
        conn,
        *,
        goods_id: str,
        goods_image_id: str,
    ) -> dict[str, Any]:
        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                """
                UPDATE goods
                SET main_image_id = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (goods_image_id, goods_id),
            )
            row = cur.fetchone()
        return self._build_goods_record(row)

    def search_goods(
        self,
        conn,
        *,
        keyword: str | None,
        series_name: str | None,
        alias: str | None,
        character_name: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        conditions: list[str] = []
        params: list[Any] = []

        if keyword:
            pattern = f"%{keyword}%"
            conditions.append(
                """
                /* keyword */ (
                  g.name ILIKE %s
                  OR COALESCE(g.series_name, '') ILIKE %s
                  OR COALESCE(g.sku, '') ILIKE %s
                  OR EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(g.aliases) AS alias_item(value)
                    WHERE alias_item.value ILIKE %s
                  )
                  OR EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(g.character_names) AS character_item(value)
                    WHERE character_item.value ILIKE %s
                  )
                )
                """
            )
            params.extend([pattern, pattern, pattern, pattern, pattern])
        if series_name:
            conditions.append("/* seriesName */ COALESCE(g.series_name, '') ILIKE %s")
            params.append(f"%{series_name}%")
        if alias:
            conditions.append(
                """
                /* alias */ EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements_text(g.aliases) AS alias_item(value)
                  WHERE alias_item.value ILIKE %s
                )
                """
            )
            params.append(f"%{alias}%")
        if character_name:
            conditions.append(
                """
                /* characterName */ EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements_text(g.character_names) AS character_item(value)
                  WHERE character_item.value ILIKE %s
                )
                """
            )
            params.append(f"%{character_name}%")
        if status:
            conditions.append("/* status */ g.status = %s")
            params.append(status)

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        offset = (page - 1) * page_size

        with conn.cursor(row_factory=self._dict_row()) as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM goods g
                {where_sql}
                """,
                params,
            )
            total = cur.fetchone()["total"]

            cur.execute(
                f"""
                SELECT
                  g.*,
                  main_image.image_url AS main_image_url,
                  COUNT(goods_image.id)::INTEGER AS image_count
                FROM goods g
                LEFT JOIN goods_images main_image ON main_image.id = g.main_image_id
                LEFT JOIN goods_images goods_image ON goods_image.goods_id = g.id
                {where_sql}
                GROUP BY g.id, main_image.image_url
                ORDER BY g.updated_at DESC, g.created_at DESC, g.id DESC
                LIMIT %s OFFSET %s
                """,
                [*params, page_size, offset],
            )
            rows = cur.fetchall()

        return {
            "items": [self._build_goods_record(row) for row in rows],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }
