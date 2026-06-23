from __future__ import annotations

import copy
from typing import Any, Callable

from ..errors import AppError


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


def ensure_goods_catalog_state(state: dict[str, Any]) -> bool:
    # 兼容旧数据，按需补齐商品图鉴结构和主图关系。
    changed = False

    counters = state.setdefault("counters", {})
    goods_list = state.setdefault("goods", [])
    goods_images = state.setdefault("goodsImages", [])

    if "goods" not in counters:
        counters["goods"] = len(goods_list)
        changed = True
    if "goodsImage" not in counters:
        counters["goodsImage"] = len(goods_images)
        changed = True

    for goods in goods_list:
        if "aliases" not in goods:
            goods["aliases"] = []
            changed = True
        if "characterNames" not in goods:
            goods["characterNames"] = []
            changed = True
        if "status" not in goods:
            goods["status"] = GOODS_STATUS_ENABLED
            changed = True
        if "mainImageId" not in goods:
            goods["mainImageId"] = None
            changed = True
        if "updatedAt" not in goods:
            goods["updatedAt"] = goods.get("createdAt")
            changed = True

    for image in goods_images:
        if "fileObjectId" not in image:
            image["fileObjectId"] = None
            changed = True
        if "sortOrder" not in image:
            image["sortOrder"] = 0
            changed = True
        if "isPrimary" not in image:
            image["isPrimary"] = False
            changed = True

    images_by_goods: dict[str, list[dict[str, Any]]] = {}
    for image in goods_images:
        images_by_goods.setdefault(image["goodsId"], []).append(image)

    for goods in goods_list:
        related_images = images_by_goods.get(goods["id"], [])
        primary_images = [image for image in related_images if image.get("isPrimary")]

        if goods.get("mainImageId") and not any(
            image["id"] == goods["mainImageId"] for image in related_images
        ):
            goods["mainImageId"] = None
            changed = True

        if goods.get("mainImageId") is None and primary_images:
            goods["mainImageId"] = primary_images[0]["id"]
            changed = True

        if goods.get("mainImageId"):
            for image in related_images:
                should_be_primary = image["id"] == goods["mainImageId"]
                if image.get("isPrimary") != should_be_primary:
                    image["isPrimary"] = should_be_primary
                    changed = True

    return changed


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


def _payload_get(payload: dict[str, Any], *keys: str) -> tuple[bool, Any]:
    for key in keys:
        if key in payload:
            return True, payload[key]
    return False, None


class GoodsCatalogModule:
    def __init__(
        self,
        *,
        state: dict[str, Any],
        next_id: Callable[[str, str], str],
        audit_log: Callable[..., dict[str, Any]],
        now_iso: Callable[[], str],
    ):
        self.state = state
        self.next_id = next_id
        self.audit_log = audit_log
        self.now_iso = now_iso

    def require_goods(self, goods_id: str) -> dict[str, Any]:
        goods = next((item for item in self.state["goods"] if item["id"] == goods_id), None)
        if goods is None:
            raise AppError(404, "商品不存在", "NOT_FOUND")
        return goods

    def require_goods_image(self, goods_image_id: str) -> dict[str, Any]:
        goods_image = next(
            (item for item in self.state["goodsImages"] if item["id"] == goods_image_id),
            None,
        )
        if goods_image is None:
            raise AppError(404, "商品图片不存在", "NOT_FOUND")
        return goods_image

    def require_active_file_object(self, file_object_id: str) -> dict[str, Any]:
        file_object = next(
            (item for item in self.state.get("fileObjects", []) if item["id"] == file_object_id),
            None,
        )
        if file_object is None:
            raise AppError(404, "文件对象不存在", "NOT_FOUND")
        if file_object.get("status") == "voided":
            raise AppError(400, "文件对象已作废", "VALIDATION_FAILED")
        if file_object.get("bucket") != "goods":
            raise AppError(400, "商品图片只能关联 goods bucket 文件", "VALIDATION_FAILED")
        return file_object

    def list_goods_images(self, goods_id: str) -> list[dict[str, Any]]:
        items = [
            clone(image)
            for image in self.state["goodsImages"]
            if image["goodsId"] == goods_id
        ]
        return sorted(items, key=lambda item: (item["sortOrder"], item["createdAt"], item["id"]))

    def build_goods_summary(self, goods: dict[str, Any]) -> dict[str, Any]:
        images = self.list_goods_images(goods["id"])
        main_image_url = None
        if goods.get("mainImageId"):
            main_image = next(
                (image for image in images if image["id"] == goods["mainImageId"]),
                None,
            )
            main_image_url = main_image["imageUrl"] if main_image else None

        return {
            "id": goods["id"],
            "name": goods["name"],
            "seriesName": goods.get("seriesName"),
            "aliases": clone(goods["aliases"]),
            "characterNames": clone(goods["characterNames"]),
            "sku": goods.get("sku"),
            "description": goods.get("description"),
            "mainImageId": goods.get("mainImageId"),
            "mainImageUrl": main_image_url,
            "lengthMm": goods.get("lengthMm"),
            "widthMm": goods.get("widthMm"),
            "weightGram": goods.get("weightGram"),
            "releasePriceJpy": goods.get("releasePriceJpy"),
            "suggestedPriceJpy": goods.get("suggestedPriceJpy"),
            "domesticSpotSuggestedPriceCny": goods.get("domesticSpotSuggestedPriceCny"),
            "status": goods["status"],
            "imageCount": len(images),
            "createdAt": goods["createdAt"],
            "updatedAt": goods["updatedAt"],
        }

    def build_goods_detail(self, goods: dict[str, Any]) -> dict[str, Any]:
        summary = self.build_goods_summary(goods)
        summary["images"] = self.list_goods_images(goods["id"])
        return summary

    def build_goods_snapshot(self, goods: dict[str, Any]) -> dict[str, Any]:
        summary = self.build_goods_summary(goods)
        return {
            "goodsId": goods["id"],
            "name": goods["name"],
            "seriesName": goods.get("seriesName"),
            "aliases": clone(goods["aliases"]),
            "characterNames": clone(goods["characterNames"]),
            "description": goods.get("description"),
            "mainImageUrl": summary["mainImageUrl"],
            "lengthMm": goods.get("lengthMm"),
            "widthMm": goods.get("widthMm"),
            "weightGram": goods.get("weightGram"),
            "releasePriceJpy": goods.get("releasePriceJpy"),
            "suggestedPriceJpy": goods.get("suggestedPriceJpy"),
            "domesticSpotSuggestedPriceCny": goods.get("domesticSpotSuggestedPriceCny"),
        }

    def _build_primary_state(self, goods: dict[str, Any]) -> dict[str, Any]:
        return {
            "goodsId": goods["id"],
            "mainImageId": goods.get("mainImageId"),
            "images": [
                {"id": image["id"], "isPrimary": image["isPrimary"]}
                for image in self.list_goods_images(goods["id"])
            ],
        }

    def _set_primary_image(self, goods: dict[str, Any], goods_image_id: str) -> None:
        # 先统一清空再设新主图，避免出现多主图。
        target_image = self.require_goods_image(goods_image_id)
        if target_image["goodsId"] != goods["id"]:
            raise AppError(400, "主图必须来自当前商品的图片列表", "VALIDATION_FAILED")

        for image in self.state["goodsImages"]:
            if image["goodsId"] == goods["id"]:
                image["isPrimary"] = image["id"] == goods_image_id

        goods["mainImageId"] = goods_image_id
        goods["updatedAt"] = self.now_iso()

    def create_goods(self, *, actor_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        timestamp = self.now_iso()
        record = {
            "id": self.next_id("goods", "goods"),
            "name": _normalize_required_text(payload.get("name"), "name"),
            "seriesName": _normalize_optional_text(payload.get("seriesName")),
            "aliases": _normalize_string_list(payload.get("aliases"), "aliases"),
            "characterNames": _normalize_string_list(
                payload.get("characterNames"),
                "characterNames",
            ),
            "sku": _normalize_optional_text(payload.get("sku")),
            "description": _normalize_optional_text(payload.get("description")),
            "mainImageId": None,
            "lengthMm": _normalize_optional_int(payload.get("lengthMm"), "lengthMm"),
            "widthMm": _normalize_optional_int(payload.get("widthMm"), "widthMm"),
            "weightGram": _normalize_optional_int(payload.get("weightGram"), "weightGram"),
            "releasePriceJpy": _normalize_optional_int(
                payload.get("releasePriceJpy"),
                "releasePriceJpy",
            ),
            "suggestedPriceJpy": _normalize_optional_int(
                payload.get("suggestedPriceJpy"),
                "suggestedPriceJpy",
            ),
            "domesticSpotSuggestedPriceCny": _normalize_optional_int(
                payload.get("domesticSpotSuggestedPriceCny"),
                "domesticSpotSuggestedPriceCny",
            ),
            "status": _normalize_status(
                payload.get("status"),
                required=False,
                default_value=GOODS_STATUS_ENABLED,
            ),
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }
        self.state["goods"].append(record)

        self.audit_log(
            actor_user_id=actor_user_id,
            action="goods.create",
            object_type="goods",
            object_id=record["id"],
            before=None,
            after=self.build_goods_detail(record),
            reason="创建商品图鉴",
        )
        return {"goodsId": record["id"]}

    def update_goods(
        self,
        *,
        actor_user_id: str,
        goods_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        goods = self.require_goods(goods_id)
        before = self.build_goods_detail(goods)
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)
        updated_fields: list[str] = []

        field_updaters: list[tuple[str, tuple[str, ...], Callable[[Any], Any]]] = [
            ("name", ("name",), lambda value: _normalize_required_text(value, "name")),
            ("seriesName", ("seriesName", "series_name"), _normalize_optional_text),
            ("aliases", ("aliases",), lambda value: _normalize_string_list(value, "aliases")),
            (
                "characterNames",
                ("characterNames", "character_names"),
                lambda value: _normalize_string_list(value, "characterNames"),
            ),
            ("sku", ("sku",), _normalize_optional_text),
            ("description", ("description",), _normalize_optional_text),
            ("lengthMm", ("lengthMm", "length_mm"), lambda value: _normalize_optional_int(value, "lengthMm")),
            ("widthMm", ("widthMm", "width_mm"), lambda value: _normalize_optional_int(value, "widthMm")),
            ("weightGram", ("weightGram", "weight_gram"), lambda value: _normalize_optional_int(value, "weightGram")),
            (
                "releasePriceJpy",
                ("releasePriceJpy", "release_price_jpy"),
                lambda value: _normalize_optional_int(value, "releasePriceJpy"),
            ),
            (
                "suggestedPriceJpy",
                ("suggestedPriceJpy", "suggested_price_jpy"),
                lambda value: _normalize_optional_int(value, "suggestedPriceJpy"),
            ),
            (
                "domesticSpotSuggestedPriceCny",
                ("domesticSpotSuggestedPriceCny", "domestic_spot_suggested_price_cny"),
                lambda value: _normalize_optional_int(value, "domesticSpotSuggestedPriceCny"),
            ),
            ("status", ("status",), lambda value: _normalize_status(value, required=True)),
        ]

        for field_name, aliases, normalizer in field_updaters:
            has_value, raw_value = _payload_get(payload, *aliases)
            if not has_value:
                continue
            next_value = normalizer(raw_value)
            if goods.get(field_name) != next_value:
                goods[field_name] = next_value
                updated_fields.append(field_name)

        if not updated_fields:
            raise AppError(400, "没有可更新的字段", "VALIDATION_FAILED")

        goods["updatedAt"] = self.now_iso()

        self.audit_log(
            actor_user_id=actor_user_id,
            action="goods.update",
            object_type="goods",
            object_id=goods["id"],
            before=before,
            after=self.build_goods_detail(goods),
            reason=reason,
        )
        return {"goodsId": goods["id"], "updatedFields": updated_fields}

    def add_goods_image(
        self,
        *,
        actor_user_id: str,
        goods_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        goods = self.require_goods(goods_id)
        has_file_object_id, raw_file_object_id = _payload_get(
            payload,
            "fileObjectId",
            "file_object_id",
        )
        file_object_id = _normalize_optional_text(raw_file_object_id) if has_file_object_id else None
        if file_object_id:
            self.require_active_file_object(file_object_id)

        record = {
            "id": self.next_id("goodsImage", "goods_image"),
            "goodsId": goods["id"],
            "fileObjectId": file_object_id,
            "imageUrl": _normalize_required_text(
                payload.get("imageUrl") if "imageUrl" in payload else payload.get("image_url"),
                "imageUrl",
            ),
            "sortOrder": _normalize_optional_int(
                payload.get("sortOrder") if "sortOrder" in payload else payload.get("sort_order"),
                "sortOrder",
            )
            or 0,
            "isPrimary": False,
            "uploadedBy": actor_user_id,
            "createdAt": self.now_iso(),
        }
        self.state["goodsImages"].append(record)

        if _normalize_bool(
            payload.get("isPrimary") if "isPrimary" in payload else payload.get("is_primary"),
            "isPrimary",
            default_value=False,
        ):
            self._set_primary_image(goods, record["id"])

        self.audit_log(
            actor_user_id=actor_user_id,
            action="goods_image.create",
            object_type="goods_image",
            object_id=record["id"],
            before=None,
            after=clone(record),
            reason="添加商品图片",
        )
        return {"goodsImageId": record["id"], "imageUrl": record["imageUrl"]}

    def set_primary_goods_image(
        self,
        *,
        actor_user_id: str,
        goods_id: str,
        goods_image_id: str,
    ) -> dict[str, Any]:
        goods = self.require_goods(goods_id)
        if goods.get("mainImageId") == goods_image_id:
            self.require_goods_image(goods_image_id)
            return {"goodsId": goods["id"], "mainImageId": goods_image_id}

        before = self._build_primary_state(goods)
        self._set_primary_image(goods, goods_image_id)
        after = self._build_primary_state(goods)

        self.audit_log(
            actor_user_id=actor_user_id,
            action="goods_image.set_primary",
            object_type="goods",
            object_id=goods["id"],
            before=before,
            after=after,
            reason="设置商品主图",
        )
        return {"goodsId": goods["id"], "mainImageId": goods_image_id}

    def get_goods_snapshot(self, goods_id: str) -> dict[str, Any]:
        goods = self.require_goods(goods_id)
        return self.build_goods_snapshot(goods)

    def search_goods(self, filters: dict[str, Any]) -> dict[str, Any]:
        _, keyword_value = _payload_get(filters, "keyword")
        _, series_name_value = _payload_get(filters, "seriesName", "series_name")
        _, alias_value = _payload_get(filters, "alias")
        _, character_name_value = _payload_get(filters, "characterName", "character_name")
        _, status_value = _payload_get(filters, "status")
        _, page_value = _payload_get(filters, "page")
        _, page_size_value = _payload_get(filters, "pageSize", "page_size")

        keyword = (_normalize_optional_text(keyword_value) or "").lower()
        series_name = (_normalize_optional_text(series_name_value) or "").lower()
        alias = (_normalize_optional_text(alias_value) or "").lower()
        character_name = (_normalize_optional_text(character_name_value) or "").lower()
        status = _normalize_status(status_value, required=False)
        page = _normalize_page_number(page_value, "page", 1)
        page_size = _normalize_page_number(page_size_value, "pageSize", DEFAULT_GOODS_PAGE_SIZE)
        if page_size > MAX_GOODS_PAGE_SIZE:
            raise AppError(
                400,
                f"pageSize 不能超过 {MAX_GOODS_PAGE_SIZE}",
                "VALIDATION_FAILED",
            )

        items: list[dict[str, Any]] = []
        for goods in self.state["goods"]:
            if status and goods["status"] != status:
                continue

            searchable_fields = [
                goods["name"],
                goods.get("seriesName") or "",
                goods.get("sku") or "",
                *(goods.get("aliases") or []),
                *(goods.get("characterNames") or []),
            ]
            searchable_text = " ".join(searchable_fields).lower()

            if keyword and keyword not in searchable_text:
                continue
            if series_name and series_name not in (goods.get("seriesName") or "").lower():
                continue
            if alias and not any(alias in item.lower() for item in goods.get("aliases") or []):
                continue
            if character_name and not any(
                character_name in item.lower() for item in goods.get("characterNames") or []
            ):
                continue

            items.append(self.build_goods_summary(goods))

        items = sorted(
            items,
            key=lambda item: (item["updatedAt"], item["createdAt"], item["id"]),
            reverse=True,
        )
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size

        return {
            "items": items[start:end],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }
