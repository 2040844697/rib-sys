from __future__ import annotations

import unittest
from dataclasses import dataclass
from unittest.mock import patch

from server.errors import AppError
from server.goods_catalog import GoodsCatalogModule


@dataclass
class DummyConfig:
    database_url: str = "postgresql://unit-test"


class FakeConnection:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class FakeGoodsCatalogRepository:
    def __init__(self) -> None:
        self.goods: dict[str, dict] = {}
        self.images: dict[str, dict] = {}
        self.next_goods = 1
        self.next_image = 1

    def get_goods_by_id(self, conn, goods_id: str, *, lock: bool = False):
        return self.goods.get(goods_id)

    def get_goods_image_by_id(self, conn, goods_image_id: str, *, lock: bool = False):
        return self.images.get(goods_image_id)

    def list_goods_images(self, conn, goods_id: str):
        return sorted(
            [image for image in self.images.values() if image["goodsId"] == goods_id],
            key=lambda image: (image["sortOrder"], image["createdAt"], image["id"]),
        )

    def create_goods(self, conn, fields: dict):
        goods_id = f"goods_{self.next_goods}"
        self.next_goods += 1
        record = {
            "id": goods_id,
            "name": fields["name"],
            "seriesName": fields["series_name"],
            "aliases": fields["aliases"],
            "characterNames": fields["character_names"],
            "sku": fields["sku"],
            "description": fields["description"],
            "mainImageId": None,
            "mainImageUrl": None,
            "lengthMm": fields["length_mm"],
            "widthMm": fields["width_mm"],
            "weightGram": fields["weight_gram"],
            "releasePriceJpy": fields["release_price_jpy"],
            "suggestedPriceJpy": fields["suggested_price_jpy"],
            "domesticSpotSuggestedPriceCny": fields["domestic_spot_suggested_price_cny"],
            "status": fields["status"],
            "imageCount": 0,
            "createdAt": "2026-06-24T00:00:00Z",
            "updatedAt": "2026-06-24T00:00:00Z",
        }
        self.goods[goods_id] = record
        return record

    def update_goods(self, conn, *, goods_id: str, updates: dict):
        record = self.goods[goods_id]
        column_to_field = {
            "series_name": "seriesName",
            "character_names": "characterNames",
            "length_mm": "lengthMm",
            "width_mm": "widthMm",
            "weight_gram": "weightGram",
            "release_price_jpy": "releasePriceJpy",
            "suggested_price_jpy": "suggestedPriceJpy",
            "domestic_spot_suggested_price_cny": "domesticSpotSuggestedPriceCny",
        }
        for column, value in updates.items():
            record[column_to_field.get(column, column)] = value
        record["updatedAt"] = "2026-06-24T00:01:00Z"
        return record

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
    ):
        image_id = f"goods_image_{self.next_image}"
        self.next_image += 1
        record = {
            "id": image_id,
            "goodsId": goods_id,
            "fileObjectId": file_object_id,
            "imageUrl": image_url,
            "sortOrder": sort_order,
            "isPrimary": is_primary,
            "uploadedBy": uploaded_by,
            "createdAt": f"2026-06-24T00:0{self.next_image}:00Z",
        }
        self.images[image_id] = record
        return record

    def clear_primary_images(self, conn, *, goods_id: str) -> None:
        for image in self.images.values():
            if image["goodsId"] == goods_id:
                image["isPrimary"] = False

    def set_goods_image_primary(self, conn, *, goods_image_id: str):
        self.images[goods_image_id]["isPrimary"] = True
        return self.images[goods_image_id]

    def update_main_image(self, conn, *, goods_id: str, goods_image_id: str):
        goods = self.goods[goods_id]
        goods["mainImageId"] = goods_image_id
        goods["mainImageUrl"] = self.images[goods_image_id]["imageUrl"]
        goods["updatedAt"] = "2026-06-24T00:02:00Z"
        return goods

    def search_goods(
        self,
        conn,
        *,
        keyword,
        series_name,
        alias,
        character_name,
        status,
        page,
        page_size,
    ):
        items = []
        for goods in self.goods.values():
            images = self.list_goods_images(conn, goods["id"])
            item = {
                **goods,
                "imageCount": len(images),
                "mainImageUrl": (
                    self.images[goods["mainImageId"]]["imageUrl"]
                    if goods.get("mainImageId")
                    else None
                ),
            }
            text = " ".join(
                [
                    item["name"],
                    item.get("seriesName") or "",
                    item.get("sku") or "",
                    *item.get("aliases", []),
                    *item.get("characterNames", []),
                ]
            ).lower()
            if keyword and keyword.lower() not in text:
                continue
            if series_name and series_name.lower() not in (item.get("seriesName") or "").lower():
                continue
            if alias and not any(alias.lower() in value.lower() for value in item["aliases"]):
                continue
            if character_name and not any(
                character_name.lower() in value.lower() for value in item["characterNames"]
            ):
                continue
            if status and item["status"] != status:
                continue
            items.append(item)

        return {
            "items": items[(page - 1) * page_size : page * page_size],
            "total": len(items),
            "page": page,
            "pageSize": page_size,
        }


class FakeFileService:
    def __init__(self) -> None:
        self.file_objects = {
            "file_goods": {"id": "file_goods", "bucket": "goods", "status": "active"},
            "file_orders": {"id": "file_orders", "bucket": "orders", "status": "active"},
        }

    def require_active_file_object(self, file_object_id: str, conn=None):
        return self.file_objects[file_object_id]


class FakeAuditService:
    def __init__(self) -> None:
        self.logs: list[dict] = []

    def log_in_connection(self, conn, **kwargs):
        self.logs.append(kwargs)
        return {"id": f"audit_{len(self.logs)}", **kwargs}


class GoodsCatalogModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = FakeConnection()
        self.repo = FakeGoodsCatalogRepository()
        self.file_service = FakeFileService()
        self.audit_service = FakeAuditService()
        self.module = GoodsCatalogModule(
            DummyConfig(),
            repository=self.repo,
            file_service=self.file_service,
            audit_service=self.audit_service,
        )

    def patch_connect(self):
        return patch("server.goods_catalog.goods_catalog_module.connect", return_value=self.conn)

    def test_create_update_search_and_audit_goods(self) -> None:
        with self.patch_connect():
            created = self.module.create_goods(
                actor_user_id="user_admin",
                payload={
                    "name": "Touka badge",
                    "seriesName": "Summer goods",
                    "aliases": ["badge"],
                    "characterNames": ["Touka"],
                },
            )
            updated = self.module.update_goods(
                actor_user_id="user_admin",
                goods_id=created["goodsId"],
                payload={
                    "domesticSpotSuggestedPriceCny": "28.50",
                    "status": "draft",
                    "reason": "补充价格",
                },
            )
            result = self.module.search_goods(
                {
                    "keyword": "Touka",
                    "seriesName": "Summer",
                    "alias": "badge",
                    "characterName": "Touka",
                    "status": "draft",
                }
            )

        self.assertEqual(updated["updatedFields"], ["domesticSpotSuggestedPriceCny", "status"])
        self.assertEqual(result["items"][0]["domesticSpotSuggestedPriceCny"], "28.50")
        self.assertEqual(self.repo.goods[created["goodsId"]]["domesticSpotSuggestedPriceCny"], 2850)
        self.assertEqual([log["action"] for log in self.audit_service.logs], ["goods.create", "goods.update"])

    def test_add_goods_image_and_set_primary(self) -> None:
        with self.patch_connect():
            created = self.module.create_goods(
                actor_user_id="user_admin",
                payload={"name": "Polaroid"},
            )
            first = self.module.add_goods_image(
                actor_user_id="user_admin",
                goods_id=created["goodsId"],
                payload={
                    "fileObjectId": "file_goods",
                    "imageUrl": "https://files.example.com/goods/a.jpg",
                    "sortOrder": 10,
                },
            )
            second = self.module.add_goods_image(
                actor_user_id="user_admin",
                goods_id=created["goodsId"],
                payload={
                    "imageUrl": "https://files.example.com/goods/b.jpg",
                    "isPrimary": True,
                },
            )
            switched = self.module.set_primary_goods_image(
                actor_user_id="user_admin",
                goods_id=created["goodsId"],
                goods_image_id=first["goodsImageId"],
            )

        self.assertEqual(switched["mainImageId"], first["goodsImageId"])
        self.assertTrue(self.repo.images[first["goodsImageId"]]["isPrimary"])
        self.assertFalse(self.repo.images[second["goodsImageId"]]["isPrimary"])
        self.assertEqual(self.repo.goods[created["goodsId"]]["mainImageId"], first["goodsImageId"])
        self.assertEqual(self.audit_service.logs[-1]["action"], "goods_image.set_primary")

    def test_rejects_non_goods_bucket_file_object(self) -> None:
        with self.patch_connect():
            created = self.module.create_goods(
                actor_user_id="user_admin",
                payload={"name": "Acrylic stand"},
            )
            with self.assertRaises(AppError) as context:
                self.module.add_goods_image(
                    actor_user_id="user_admin",
                    goods_id=created["goodsId"],
                    payload={
                        "fileObjectId": "file_orders",
                        "imageUrl": "https://files.example.com/orders/a.jpg",
                    },
                )

        self.assertEqual(context.exception.code, "VALIDATION_FAILED")


if __name__ == "__main__":
    unittest.main()
