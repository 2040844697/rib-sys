from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation
from typing import Any

from ..config import Config
from ..db_access import connect
from ..errors import AppError
from .goods_catalog_repo import GoodsCatalogRepository


GOODS_STATUS_ENABLED = "enabled"
GOODS_STATUS_DISABLED = "disabled"
GOODS_STATUS_DRAFT = "draft"
ALLOWED_GOODS_STATUSES = {
    GOODS_STATUS_ENABLED,
    GOODS_STATUS_DISABLED,
    GOODS_STATUS_DRAFT,
}
DEFAULT_GOODS_PAGE_SIZE = 20
MAX_GOODS_PAGE_SIZE = 100


def clone(value: Any) -> Any:
    return copy.deepcopy(value)


def _normalize_required_text(value: Any, field_name: str, min_length: int = 1) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if len(normalized) < min_length:
        raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
    return normalized


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AppError(400, "字段格式不正确", "VALIDATION_FAILED")
    normalized = value.strip()
    return normalized or None


def _normalize_optional_int(value: Any, field_name: str) -> int | None:
    if value in {None, ""}:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    if value < 0:
        raise AppError(400, f"{field_name}不能小于 0", "VALIDATION_FAILED")
    return value


def _normalize_bool(value: Any, field_name: str, default_value: bool = False) -> bool:
    if value is None:
        return default_value
    if not isinstance(value, bool):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    return value


def _normalize_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")

    normalized_items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
        normalized = item.strip()
        if normalized and normalized not in normalized_items:
            normalized_items.append(normalized)
    return normalized_items


def _normalize_status(value: Any, *, required: bool, default_value: str | None = None) -> str | None:
    if value is None:
        if required:
            raise AppError(400, "status 填写不完整", "VALIDATION_FAILED")
        return default_value

    normalized = _normalize_required_text(value, "status")
    if normalized not in ALLOWED_GOODS_STATUSES:
        raise AppError(
            400,
            f"status 仅支持 {', '.join(sorted(ALLOWED_GOODS_STATUSES))}",
            "VALIDATION_FAILED",
        )
    return normalized


def _normalize_page_number(value: Any, field_name: str, default_value: int) -> int:
    if value in {None, ""}:
        return default_value

    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED") from exc

    if number <= 0:
        raise AppError(400, f"{field_name}必须大于 0", "VALIDATION_FAILED")
    return number


def _normalize_price_cny_to_cent(value: Any, field_name: str) -> int | None:
    if value in {None, ""}:
        return None
    if isinstance(value, bool):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")

    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED") from exc

    if amount < 0:
        raise AppError(400, f"{field_name}不能小于 0", "VALIDATION_FAILED")

    cents = amount * Decimal("100")
    if cents != cents.to_integral_value():
        raise AppError(400, f"{field_name}最多支持两位小数", "VALIDATION_FAILED")
    return int(cents)


def _format_price_cny_from_cent(value: int | None) -> str | None:
    if value is None:
        return None
    amount = Decimal(value) / Decimal("100")
    return format(amount.quantize(Decimal("0.01")), "f")


def _payload_get(payload: dict[str, Any], *keys: str) -> tuple[bool, Any]:
    for key in keys:
        if key in payload:
            return True, payload[key]
    return False, None


class GoodsCatalogModule:
    def __init__(
        self,
        config: Config,
        *,
        repository: GoodsCatalogRepository | None = None,
        file_service: Any,
        audit_service: Any,
    ):
        self.config = config
        self.repo = repository or GoodsCatalogRepository(config)
        self.file_service = file_service
        self.audit_service = audit_service

    def _assert_database_enabled(self) -> None:
        if not self.config.database_url:
            raise AppError(503, "商品图鉴模块需要数据库后端", "DATABASE_REQUIRED")

    def _require_goods(self, conn, goods_id: str, *, lock: bool = False) -> dict[str, Any]:
        goods = self.repo.get_goods_by_id(conn, goods_id, lock=lock)
        if goods is None:
            raise AppError(404, "商品不存在", "NOT_FOUND")
        return goods

    def _require_goods_image(
        self,
        conn,
        goods_image_id: str,
        *,
        lock: bool = False,
    ) -> dict[str, Any]:
        goods_image = self.repo.get_goods_image_by_id(conn, goods_image_id, lock=lock)
        if goods_image is None:
            raise AppError(404, "商品图片不存在", "NOT_FOUND")
        return goods_image

    def _require_goods_file_object(self, conn, file_object_id: str) -> dict[str, Any]:
        # 复用 DB 版文件对象校验，并把读取放进当前事务，避免图片记录和文件状态不一致。
        try:
            file_object = self.file_service.require_active_file_object(file_object_id, conn=conn)
        except TypeError:
            file_object = self.file_service.require_active_file_object(file_object_id)

        if file_object.get("bucket") != "goods":
            raise AppError(400, "商品图片只能关联 goods bucket 文件", "VALIDATION_FAILED")
        return file_object

    def _log_audit_in_connection(
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
        if not hasattr(self.audit_service, "log_in_connection"):
            raise RuntimeError("Database audit service is required for goods catalog.")
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

    def _build_goods_summary(self, goods: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": goods["id"],
            "name": goods["name"],
            "seriesName": goods.get("seriesName"),
            "aliases": clone(goods.get("aliases") or []),
            "characterNames": clone(goods.get("characterNames") or []),
            "sku": goods.get("sku"),
            "description": goods.get("description"),
            "mainImageId": goods.get("mainImageId"),
            "mainImageUrl": goods.get("mainImageUrl"),
            "lengthMm": goods.get("lengthMm"),
            "widthMm": goods.get("widthMm"),
            "weightGram": goods.get("weightGram"),
            "releasePriceJpy": goods.get("releasePriceJpy"),
            "suggestedPriceJpy": goods.get("suggestedPriceJpy"),
            "domesticSpotSuggestedPriceCny": _format_price_cny_from_cent(
                goods.get("domesticSpotSuggestedPriceCny")
            ),
            "status": goods["status"],
            "imageCount": goods.get("imageCount", 0),
            "createdAt": goods["createdAt"],
            "updatedAt": goods["updatedAt"],
        }

    def _build_goods_detail(self, conn, goods: dict[str, Any]) -> dict[str, Any]:
        images = self.repo.list_goods_images(conn, goods["id"])
        main_image_url = None
        if goods.get("mainImageId"):
            main_image = next(
                (image for image in images if image["id"] == goods["mainImageId"]),
                None,
            )
            main_image_url = main_image["imageUrl"] if main_image else None

        summary = self._build_goods_summary(
            {
                **goods,
                "mainImageUrl": main_image_url,
                "imageCount": len(images),
            }
        )
        summary["images"] = images
        return summary

    def _build_goods_snapshot(self, conn, goods: dict[str, Any]) -> dict[str, Any]:
        detail = self._build_goods_detail(conn, goods)
        return {
            "goodsId": goods["id"],
            "name": goods["name"],
            "seriesName": goods.get("seriesName"),
            "aliases": clone(goods.get("aliases") or []),
            "characterNames": clone(goods.get("characterNames") or []),
            "description": goods.get("description"),
            "mainImageUrl": detail["mainImageUrl"],
            "lengthMm": goods.get("lengthMm"),
            "widthMm": goods.get("widthMm"),
            "weightGram": goods.get("weightGram"),
            "releasePriceJpy": goods.get("releasePriceJpy"),
            "suggestedPriceJpy": goods.get("suggestedPriceJpy"),
            "domesticSpotSuggestedPriceCny": _format_price_cny_from_cent(
                goods.get("domesticSpotSuggestedPriceCny")
            ),
        }

    def _build_primary_state(self, conn, goods: dict[str, Any]) -> dict[str, Any]:
        return {
            "goodsId": goods["id"],
            "mainImageId": goods.get("mainImageId"),
            "images": [
                {"id": image["id"], "isPrimary": image["isPrimary"]}
                for image in self.repo.list_goods_images(conn, goods["id"])
            ],
        }

    def _set_primary_image(self, conn, *, goods: dict[str, Any], target_image: dict[str, Any]) -> dict[str, Any]:
        if target_image["goodsId"] != goods["id"]:
            raise AppError(400, "主图必须来自当前商品的图片列表", "VALIDATION_FAILED")

        # 先清空再设置目标图片，保证同一商品在事务提交后只有一张主图。
        self.repo.clear_primary_images(conn, goods_id=goods["id"])
        self.repo.set_goods_image_primary(conn, goods_image_id=target_image["id"])
        return self.repo.update_main_image(
            conn,
            goods_id=goods["id"],
            goods_image_id=target_image["id"],
        )

    def create_goods(self, *, actor_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_database_enabled()
        fields = {
            "name": _normalize_required_text(payload.get("name"), "name"),
            "series_name": _normalize_optional_text(payload.get("seriesName")),
            "aliases": _normalize_string_list(payload.get("aliases"), "aliases"),
            "character_names": _normalize_string_list(
                payload.get("characterNames"),
                "characterNames",
            ),
            "sku": _normalize_optional_text(payload.get("sku")),
            "description": _normalize_optional_text(payload.get("description")),
            "length_mm": _normalize_optional_int(payload.get("lengthMm"), "lengthMm"),
            "width_mm": _normalize_optional_int(payload.get("widthMm"), "widthMm"),
            "weight_gram": _normalize_optional_int(payload.get("weightGram"), "weightGram"),
            "release_price_jpy": _normalize_optional_int(
                payload.get("releasePriceJpy"),
                "releasePriceJpy",
            ),
            "suggested_price_jpy": _normalize_optional_int(
                payload.get("suggestedPriceJpy"),
                "suggestedPriceJpy",
            ),
            "domestic_spot_suggested_price_cny": _normalize_price_cny_to_cent(
                payload.get("domesticSpotSuggestedPriceCny"),
                "domesticSpotSuggestedPriceCny",
            ),
            "status": _normalize_status(
                payload.get("status"),
                required=False,
                default_value=GOODS_STATUS_ENABLED,
            ),
        }

        with connect(self.config) as conn:
            record = self.repo.create_goods(conn, fields)
            self._log_audit_in_connection(
                conn,
                actor_user_id=actor_user_id,
                action="goods.create",
                object_type="goods",
                object_id=record["id"],
                before=None,
                after=self._build_goods_detail(conn, record),
                reason="创建商品图鉴",
            )
            conn.commit()
        return {"goodsId": record["id"]}

    def update_goods(
        self,
        *,
        actor_user_id: str,
        goods_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_database_enabled()
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)

        field_updaters = [
            ("name", "name", ("name",), lambda value: _normalize_required_text(value, "name")),
            ("seriesName", "series_name", ("seriesName", "series_name"), _normalize_optional_text),
            ("aliases", "aliases", ("aliases",), lambda value: _normalize_string_list(value, "aliases")),
            (
                "characterNames",
                "character_names",
                ("characterNames", "character_names"),
                lambda value: _normalize_string_list(value, "characterNames"),
            ),
            ("sku", "sku", ("sku",), _normalize_optional_text),
            ("description", "description", ("description",), _normalize_optional_text),
            ("lengthMm", "length_mm", ("lengthMm", "length_mm"), lambda value: _normalize_optional_int(value, "lengthMm")),
            ("widthMm", "width_mm", ("widthMm", "width_mm"), lambda value: _normalize_optional_int(value, "widthMm")),
            ("weightGram", "weight_gram", ("weightGram", "weight_gram"), lambda value: _normalize_optional_int(value, "weightGram")),
            (
                "releasePriceJpy",
                "release_price_jpy",
                ("releasePriceJpy", "release_price_jpy"),
                lambda value: _normalize_optional_int(value, "releasePriceJpy"),
            ),
            (
                "suggestedPriceJpy",
                "suggested_price_jpy",
                ("suggestedPriceJpy", "suggested_price_jpy"),
                lambda value: _normalize_optional_int(value, "suggestedPriceJpy"),
            ),
            (
                "domesticSpotSuggestedPriceCny",
                "domestic_spot_suggested_price_cny",
                ("domesticSpotSuggestedPriceCny", "domestic_spot_suggested_price_cny"),
                lambda value: _normalize_price_cny_to_cent(value, "domesticSpotSuggestedPriceCny"),
            ),
            ("status", "status", ("status",), lambda value: _normalize_status(value, required=True)),
        ]

        with connect(self.config) as conn:
            goods = self._require_goods(conn, goods_id, lock=True)
            before = self._build_goods_detail(conn, goods)
            updates: dict[str, Any] = {}
            updated_fields: list[str] = []

            for field_name, column_name, aliases, normalizer in field_updaters:
                has_value, raw_value = _payload_get(payload, *aliases)
                if not has_value:
                    continue
                next_value = normalizer(raw_value)
                if goods.get(field_name) != next_value:
                    updates[column_name] = next_value
                    updated_fields.append(field_name)

            if not updated_fields:
                raise AppError(400, "没有可更新的字段", "VALIDATION_FAILED")

            updated = self.repo.update_goods(conn, goods_id=goods["id"], updates=updates)
            self._log_audit_in_connection(
                conn,
                actor_user_id=actor_user_id,
                action="goods.update",
                object_type="goods",
                object_id=goods["id"],
                before=before,
                after=self._build_goods_detail(conn, updated),
                reason=reason,
            )
            conn.commit()
        return {"goodsId": goods_id, "updatedFields": updated_fields}

    def add_goods_image(
        self,
        *,
        actor_user_id: str,
        goods_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_database_enabled()
        has_file_object_id, raw_file_object_id = _payload_get(
            payload,
            "fileObjectId",
            "file_object_id",
        )
        file_object_id = _normalize_optional_text(raw_file_object_id) if has_file_object_id else None
        image_url = _normalize_required_text(
            payload.get("imageUrl") if "imageUrl" in payload else payload.get("image_url"),
            "imageUrl",
        )
        sort_order = (
            _normalize_optional_int(
                payload.get("sortOrder") if "sortOrder" in payload else payload.get("sort_order"),
                "sortOrder",
            )
            or 0
        )
        is_primary = _normalize_bool(
            payload.get("isPrimary") if "isPrimary" in payload else payload.get("is_primary"),
            "isPrimary",
            default_value=False,
        )

        with connect(self.config) as conn:
            goods = self._require_goods(conn, goods_id, lock=True)
            if file_object_id:
                self._require_goods_file_object(conn, file_object_id)

            created = self.repo.create_goods_image(
                conn,
                goods_id=goods["id"],
                file_object_id=file_object_id,
                image_url=image_url,
                sort_order=sort_order,
                is_primary=False,
                uploaded_by=actor_user_id,
            )

            if is_primary:
                self._set_primary_image(conn, goods=goods, target_image=created)
                created = self._require_goods_image(conn, created["id"])

            self._log_audit_in_connection(
                conn,
                actor_user_id=actor_user_id,
                action="goods_image.create",
                object_type="goods_image",
                object_id=created["id"],
                before=None,
                after=created,
                reason="添加商品图片",
            )
            conn.commit()
        return {"goodsImageId": created["id"], "imageUrl": created["imageUrl"]}

    def set_primary_goods_image(
        self,
        *,
        actor_user_id: str,
        goods_id: str,
        goods_image_id: str,
    ) -> dict[str, Any]:
        self._assert_database_enabled()
        with connect(self.config) as conn:
            goods = self._require_goods(conn, goods_id, lock=True)
            target_image = self._require_goods_image(conn, goods_image_id, lock=True)
            before = self._build_primary_state(conn, goods)
            updated_goods = self._set_primary_image(conn, goods=goods, target_image=target_image)
            after = self._build_primary_state(conn, updated_goods)
            self._log_audit_in_connection(
                conn,
                actor_user_id=actor_user_id,
                action="goods_image.set_primary",
                object_type="goods",
                object_id=goods["id"],
                before=before,
                after=after,
                reason="设置商品主图",
            )
            conn.commit()
        return {"goodsId": goods_id, "mainImageId": goods_image_id}

    def get_goods_snapshot(self, goods_id: str) -> dict[str, Any]:
        self._assert_database_enabled()
        with connect(self.config) as conn:
            goods = self._require_goods(conn, goods_id)
            snapshot = self._build_goods_snapshot(conn, goods)
            conn.rollback()
        return snapshot

    def search_goods(self, filters: dict[str, Any]) -> dict[str, Any]:
        self._assert_database_enabled()
        _, keyword_value = _payload_get(filters, "keyword")
        _, series_name_value = _payload_get(filters, "seriesName", "series_name")
        _, alias_value = _payload_get(filters, "alias")
        _, character_name_value = _payload_get(filters, "characterName", "character_name")
        _, status_value = _payload_get(filters, "status")
        _, page_value = _payload_get(filters, "page")
        _, page_size_value = _payload_get(filters, "pageSize", "page_size")

        keyword = _normalize_optional_text(keyword_value)
        series_name = _normalize_optional_text(series_name_value)
        alias = _normalize_optional_text(alias_value)
        character_name = _normalize_optional_text(character_name_value)
        status = _normalize_status(status_value, required=False)
        page = _normalize_page_number(page_value, "page", 1)
        page_size = _normalize_page_number(page_size_value, "pageSize", DEFAULT_GOODS_PAGE_SIZE)
        if page_size > MAX_GOODS_PAGE_SIZE:
            raise AppError(
                400,
                f"pageSize 不能超过 {MAX_GOODS_PAGE_SIZE}",
                "VALIDATION_FAILED",
            )

        with connect(self.config) as conn:
            result = self.repo.search_goods(
                conn,
                keyword=keyword,
                series_name=series_name,
                alias=alias,
                character_name=character_name,
                status=status,
                page=page,
                page_size=page_size,
            )
            conn.rollback()

        return {
            **result,
            "items": [self._build_goods_summary(item) for item in result["items"]],
        }
