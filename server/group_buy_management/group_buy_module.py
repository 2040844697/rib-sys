from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from ..config import Config
from ..db_access import connect
from ..errors import AppError
from ..file_audit import DatabaseAuditService
from .group_buy_repo import GroupBuyRepository


GROUP_BUY_STATUS_WAITING = "等待开团"
GROUP_BUY_STATUS_ACTIVE = "拼拼拼"
GROUP_BUY_STATUS_SPLIT = "已切"
GROUP_BUY_STATUS_CLOSED = "已截团"
GROUP_BUY_STATUS_COMPLETED = "已完成"
GROUP_BUY_STATUS_CANCELLED = "已取消"

ALLOWED_GROUP_BUY_TYPES = {
    "群内开谷",
    "群内切煤",
    "国外全新",
    "国外二手",
    "群友出物",
    "国内现货",
    "补款",
    "补寄",
    "现货加开",
}
ALLOWED_GROUP_BUY_STATUSES = {
    GROUP_BUY_STATUS_WAITING,
    GROUP_BUY_STATUS_ACTIVE,
    GROUP_BUY_STATUS_SPLIT,
    GROUP_BUY_STATUS_CLOSED,
    GROUP_BUY_STATUS_COMPLETED,
    GROUP_BUY_STATUS_CANCELLED,
}
GROUP_BUY_STATUS_TRANSITIONS = {
    GROUP_BUY_STATUS_WAITING: {
        GROUP_BUY_STATUS_ACTIVE,
        GROUP_BUY_STATUS_CANCELLED,
    },
    GROUP_BUY_STATUS_ACTIVE: {
        GROUP_BUY_STATUS_SPLIT,
        GROUP_BUY_STATUS_CLOSED,
        GROUP_BUY_STATUS_CANCELLED,
    },
    GROUP_BUY_STATUS_SPLIT: {
        GROUP_BUY_STATUS_CLOSED,
        GROUP_BUY_STATUS_CANCELLED,
    },
    GROUP_BUY_STATUS_CLOSED: {
        GROUP_BUY_STATUS_COMPLETED,
        GROUP_BUY_STATUS_CANCELLED,
    },
    GROUP_BUY_STATUS_COMPLETED: set(),
    GROUP_BUY_STATUS_CANCELLED: set(),
}
CLAIMABLE_GROUP_BUY_STATUSES = {
    GROUP_BUY_STATUS_ACTIVE,
    GROUP_BUY_STATUS_SPLIT,
}
PRICE_ADJUSTMENT_STATUS_PENDING_REVIEW = "pending_review"
GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT = "未肾"
GROUP_BUY_RECORD_STATUS_ORDERED = "已下单"
GROUP_BUY_RECORD_STATUS_PRIORITY = {
    "转单中": 1,
    "已完结": 2,
    "已排发": 3,
    "已申请排发": 4,
    GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT: 5,
    "未补国际": 6,
    "未转寄": 7,
    "未到货": 8,
    "可排发": 9,
    GROUP_BUY_RECORD_STATUS_ORDERED: 10,
}
CHARGE_TYPE_INITIAL_GOODS = "initial_goods"


def _normalize_required_text(value: Any, field_name: str, min_length: int = 1) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if len(normalized) < min_length:
        raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
    return normalized


def _normalize_optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    normalized = value.strip()
    return normalized or None


def _normalize_non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    if value < 0:
        raise AppError(400, f"{field_name}不能小于 0", "VALIDATION_FAILED")
    return value


def _normalize_positive_int(value: Any, field_name: str) -> int:
    normalized = _normalize_non_negative_int(value, field_name)
    if normalized <= 0:
        raise AppError(400, f"{field_name}必须大于 0", "VALIDATION_FAILED")
    return normalized


def _normalize_optional_int(value: Any, field_name: str) -> int | None:
    if value in {None, ""}:
        return None
    return _normalize_non_negative_int(value, field_name)


def _normalize_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")

    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
        normalized = item.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _normalize_group_buy_type(value: Any) -> str:
    normalized = _normalize_required_text(value, "拼单类型")
    if normalized not in ALLOWED_GROUP_BUY_TYPES:
        raise AppError(
            400,
            f"拼单类型仅支持 {', '.join(sorted(ALLOWED_GROUP_BUY_TYPES))}",
            "VALIDATION_FAILED",
        )
    return normalized


def _normalize_group_buy_status(value: Any) -> str:
    normalized = _normalize_required_text(value, "拼单状态")
    if normalized not in ALLOWED_GROUP_BUY_STATUSES:
        raise AppError(
            400,
            f"拼单状态仅支持 {', '.join(sorted(ALLOWED_GROUP_BUY_STATUSES))}",
            "VALIDATION_FAILED",
        )
    return normalized


def _normalize_price_cny(value: Any, field_name: str) -> str:
    if isinstance(value, bool) or value in {None, ""}:
        raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED") from exc
    quantized = amount.quantize(Decimal("0.00"))
    if amount != quantized:
        raise AppError(400, f"{field_name}最多支持两位小数", "VALIDATION_FAILED")
    if amount < 0:
        raise AppError(400, f"{field_name}不能小于 0", "VALIDATION_FAILED")
    return f"{quantized}"


def _multiply_price_cny(unit_price_cny: str, quantity: int) -> str:
    # 金额始终以 Decimal 计算，避免 float 让“分”语义漂移。
    amount = Decimal(str(unit_price_cny)) * Decimal(quantity)
    return f"{amount.quantize(Decimal('0.00'))}"


def _status_priority(status: str | None) -> int:
    return GROUP_BUY_RECORD_STATUS_PRIORITY.get(
        status or "",
        GROUP_BUY_RECORD_STATUS_PRIORITY[GROUP_BUY_RECORD_STATUS_ORDERED],
    )


def _parse_datetime(value: Any, field_name: str) -> datetime | None:
    text = _normalize_optional_text(value, field_name)
    if text is None:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED") from exc


def _normalize_optional_bool(value: Any, field_name: str, default_value: bool) -> bool:
    if value is None:
        return default_value
    if isinstance(value, bool):
        return value
    raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")


def _normalize_advanced_settings(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise AppError(400, "advancedSettings格式不正确", "VALIDATION_FAILED")
    allowed_keys = {
        "remindBeforeStart",
        "showParticipantCount",
        "showTotalAmount",
        "showClaimedQuantity",
        "coverImages",
    }
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if key not in allowed_keys:
            continue
        if key == "coverImages":
            if not isinstance(item, list):
                raise AppError(400, "advancedSettings.coverImages格式不正确", "VALIDATION_FAILED")
            images: list[dict[str, str | None]] = []
            for image in item:
                if not isinstance(image, dict):
                    raise AppError(400, "advancedSettings.coverImages格式不正确", "VALIDATION_FAILED")
                url = _normalize_required_text(image.get("url"), "活动图片")
                images.append(
                    {
                        "fileObjectId": _normalize_optional_text(
                            image.get("fileObjectId")
                            if "fileObjectId" in image
                            else image.get("file_object_id"),
                            "活动图片文件",
                        ),
                        "url": url,
                        "name": _normalize_optional_text(image.get("name"), "活动图片名称"),
                    }
                )
            normalized[key] = images
            continue
        if not isinstance(item, bool):
            raise AppError(400, f"advancedSettings.{key}格式不正确", "VALIDATION_FAILED")
        normalized[key] = item
    return normalized


def _payload_get(payload: dict[str, Any], *keys: str) -> tuple[bool, Any]:
    for key in keys:
        if key in payload:
            return True, payload[key]
    return False, None


class GroupBuyModule:
    def __init__(
        self,
        config: Config,
        *,
        repository: GroupBuyRepository | None = None,
        get_goods_snapshot=None,
        get_user_snapshot_by_id=None,
        has_group_access=None,
        has_permission=None,
        audit_service: DatabaseAuditService | None = None,
        create_charge_from_related_module: Callable[..., dict[str, Any]] | None = None,
    ):
        self.config = config
        self.repo = repository or GroupBuyRepository(config)
        self.get_goods_snapshot = get_goods_snapshot
        self.get_user_snapshot_by_id = get_user_snapshot_by_id
        self.has_group_access = has_group_access
        self.has_permission = has_permission
        self.audit_service = audit_service
        self.create_charge_from_related_module = create_charge_from_related_module
        self.group_buy_records_module = None

    def _assert_database_enabled(self) -> None:
        if not self.config.database_url:
            raise RuntimeError("DATABASE_URL is required for group buy management module.")

    def _audit(
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
        # 统一走 file_audit 的数据库审计服务，仓储只负责团购业务表。
        if self.audit_service is None:
            return
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

    def _require_group_access(self, actor_user_id: str, group_id: str) -> None:
        if self.has_group_access is None:
            return
        if not self.has_group_access(actor_user_id, group_id):
            raise AppError(404, "谷团不存在", "NOT_FOUND")

    def _assert_permission(
        self,
        actor_user_id: str,
        permission: str,
        *,
        error_message: str,
    ) -> None:
        if self.has_permission is None:
            return
        if not self.has_permission(actor_user_id, permission):
            raise AppError(403, error_message, "FORBIDDEN")

    def _require_group_buy(self, conn, group_buy_id: str) -> dict[str, Any]:
        group_buy = self.repo.get_group_buy_by_id(conn, group_buy_id)
        if group_buy is None:
            raise AppError(404, "拼单不存在", "NOT_FOUND")
        return group_buy

    def _require_group_buy_item(self, conn, group_buy_item_id: str) -> dict[str, Any]:
        group_buy_item = self.repo.get_group_buy_item_by_id(conn, group_buy_item_id)
        if group_buy_item is None:
            raise AppError(404, "拼单商品不存在", "NOT_FOUND")
        return group_buy_item

    def _require_group_buy_item_for_update(self, conn, group_buy_item_id: str) -> dict[str, Any]:
        group_buy_item = self.repo.get_group_buy_item_by_id(conn, group_buy_item_id, lock=True)
        if group_buy_item is None:
            raise AppError(404, "拼单商品不存在", "NOT_FOUND")
        return group_buy_item

    def _assert_group_buy_mutable(self, group_buy: dict[str, Any]) -> None:
        if group_buy["status"] in {GROUP_BUY_STATUS_COMPLETED, GROUP_BUY_STATUS_CANCELLED}:
            raise AppError(400, "已完成或已取消的拼单暂不允许修改", "INVALID_STATUS")

    def _can_edit_group_buy(self, actor_user_id: str, group_buy: dict[str, Any]) -> bool:
        if self.has_permission is None:
            return True
        if self.has_permission(actor_user_id, "group_buy:update_any"):
            return True
        return group_buy["ownerUserId"] == actor_user_id and self.has_permission(
            actor_user_id,
            "group_buy:update_own",
        )

    def _can_create_record_for_member(self, actor_user_id: str, member_user_id: str) -> bool:
        if actor_user_id == member_user_id:
            return self.has_permission is None or self.has_permission(actor_user_id, "record:create_self")
        return self.has_permission is None or self.has_permission(actor_user_id, "record:create_for_member")

    def _require_member_in_group(self, member_user_id: str, group_id: str) -> None:
        if self.get_user_snapshot_by_id is None:
            return
        member = self.get_user_snapshot_by_id(member_user_id)
        if member is None:
            raise AppError(404, "成员不存在", "NOT_FOUND")
        if "admin" not in member.get("roles", []) and member.get("groupId") != group_id:
            raise AppError(400, "成员不属于当前谷团", "VALIDATION_FAILED")

    def _normalize_status_filter(self, status_filter: str | None) -> list[str] | None:
        # 前端筛选项沿用旧接口语义，DB 查询时转换成明确状态列表。
        if not status_filter or status_filter == "全部":
            return None
        if status_filter == "进行中":
            return sorted(CLAIMABLE_GROUP_BUY_STATUSES)
        if status_filter == "未开始":
            return [GROUP_BUY_STATUS_WAITING]
        return [_normalize_group_buy_status(status_filter)]

    def _build_item_snapshot_from_goods(self, goods_id: str) -> dict[str, Any]:
        if self.get_goods_snapshot is None:
            raise RuntimeError("Goods snapshot dependency is required.")
        snapshot = self.get_goods_snapshot(goods_id)
        character_names = list(snapshot.get("characterNames") or [])
        return {
            "goodsId": goods_id,
            "name": snapshot.get("name"),
            "aliases": list(snapshot.get("aliases") or []),
            "characterNames": character_names,
            "description": snapshot.get("description"),
            "imageUrl": snapshot.get("mainImageUrl"),
            "releasePriceJpy": snapshot.get("releasePriceJpy"),
            "suggestedPriceJpy": snapshot.get("suggestedPriceJpy"),
            "domesticSpotSuggestedPriceCny": (
                _normalize_price_cny(snapshot.get("domesticSpotSuggestedPriceCny"), "国内现货建议价")
                if snapshot.get("domesticSpotSuggestedPriceCny") is not None
                else None
            ),
            "lengthMm": snapshot.get("lengthMm"),
            "widthMm": snapshot.get("widthMm"),
            "weightGram": snapshot.get("weightGram"),
        }

    def _build_manual_item_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        aliases = _normalize_string_list(payload.get("aliases"), "别名")
        character_names = _normalize_string_list(
            payload.get("characterNames")
            if "characterNames" in payload
            else payload.get("character_names"),
            "角色名列表",
        )
        name = _normalize_optional_text(payload.get("name"), "商品名称")
        note = _normalize_optional_text(payload.get("note"), "备注")
        if not name and not note:
            raise AppError(
                400,
                "手填商品时至少需要商品名称，或用备注让成员能识别商品",
                "VALIDATION_FAILED",
            )
        return {
            "goodsId": None,
            "name": name or note,
            "aliases": aliases,
            "characterNames": character_names,
            "description": _normalize_optional_text(payload.get("description"), "商品描述"),
            "imageUrl": _normalize_optional_text(
                payload.get("imageUrl") if "imageUrl" in payload else payload.get("image_url"),
                "商品图片",
            ),
            "releasePriceJpy": _normalize_optional_int(
                payload.get("releasePriceJpy")
                if "releasePriceJpy" in payload
                else payload.get("release_price_jpy"),
                "发售价",
            ),
            "suggestedPriceJpy": _normalize_optional_int(
                payload.get("suggestedPriceJpy")
                if "suggestedPriceJpy" in payload
                else payload.get("suggested_price_jpy"),
                "建议价",
            ),
            "domesticSpotSuggestedPriceCny": (
                _normalize_price_cny(
                    payload.get("domesticSpotSuggestedPriceCny")
                    if "domesticSpotSuggestedPriceCny" in payload
                    else payload.get("domestic_spot_suggested_price_cny"),
                    "国内现货建议价",
                )
                if (
                    "domesticSpotSuggestedPriceCny" in payload
                    or "domestic_spot_suggested_price_cny" in payload
                )
                else None
            ),
            "lengthMm": _normalize_optional_int(
                payload.get("lengthMm") if "lengthMm" in payload else payload.get("length_mm"),
                "长度",
            ),
            "widthMm": _normalize_optional_int(
                payload.get("widthMm") if "widthMm" in payload else payload.get("width_mm"),
                "宽度",
            ),
            "weightGram": _normalize_optional_int(
                payload.get("weightGram")
                if "weightGram" in payload
                else payload.get("weight_gram"),
                "重量",
            ),
        }

    def _assert_status_transition(self, old_status: str, new_status: str) -> None:
        if new_status not in GROUP_BUY_STATUS_TRANSITIONS.get(old_status, set()):
            raise AppError(
                400,
                f"拼单状态不允许从 {old_status} 变更为 {new_status}",
                "INVALID_STATUS",
            )

    def build_group_buys(
        self,
        group_id: str,
        actor_user_id: str,
        filters: dict[str, str | None],
    ) -> dict[str, Any]:
        self._assert_database_enabled()
        self._require_group_access(actor_user_id, group_id)
        statuses = self._normalize_status_filter(filters.get("status"))
        keyword = _normalize_optional_text(filters.get("keyword"), "keyword")

        with connect(self.config) as conn:
            items = self.repo.list_group_buys(
                conn,
                group_id=group_id,
                member_user_id=actor_user_id,
                statuses=statuses,
                keyword=keyword,
            )
            conn.rollback()

        return {"items": items, "total": len(items)}

    def build_group_buy_detail(self, group_buy_id: str, actor_user_id: str) -> dict[str, Any]:
        self._assert_database_enabled()

        with connect(self.config) as conn:
            group_buy = self._require_group_buy(conn, group_buy_id)
            self._require_group_access(actor_user_id, group_buy["groupId"])
            items = self.repo.list_group_buy_items(conn, group_buy_id)
            if self.group_buy_records_module is None:
                my_records = self.repo.list_member_records(
                    conn,
                    group_buy_id=group_buy_id,
                    member_user_id=actor_user_id,
                )
            else:
                my_records = self.group_buy_records_module.list_member_records(
                    group_buy_id=group_buy_id,
                    member_user_id=actor_user_id,
                )
            conn.rollback()

        return {
            "groupBuy": {
                "id": group_buy["id"],
                "groupId": group_buy["groupId"],
                "title": group_buy["title"],
                "type": group_buy["type"],
                "status": group_buy["status"],
                "description": group_buy["description"],
                "startAt": group_buy.get("startAt"),
                "closeAt": group_buy["closeAt"],
                "coverFileObjectId": group_buy.get("coverFileObjectId"),
                "coverImageUrl": group_buy.get("coverImageUrl"),
                "claimMode": group_buy.get("claimMode"),
                "canCancelClaim": group_buy.get("canCancelClaim"),
                "saleMode": group_buy.get("saleMode"),
                "allowTransfer": group_buy.get("allowTransfer"),
                "advancedSettings": group_buy.get("advancedSettings") or {},
                "paymentChannelId": group_buy["paymentChannelId"],
                "warehouseUserId": group_buy["warehouseUserId"],
            },
            "items": [
                {
                    **item,
                    "status": "可拼" if item["availableQuantity"] > 0 else "已满",
                }
                for item in items
            ],
            "myRecords": [
                {
                    "id": record["id"],
                    "groupBuyItemId": record["groupBuyItemId"],
                    "quantity": record["quantity"],
                    "displayStatus": record["displayStatus"],
                    "isException": record["isException"],
                }
                for record in my_records
            ],
            "capabilities": {
                "canClaim": (
                    self.has_permission is None
                    or self.has_permission(actor_user_id, "record:create_self")
                )
                and group_buy["status"] in CLAIMABLE_GROUP_BUY_STATUSES,
                "canEdit": self._can_edit_group_buy(actor_user_id, group_buy),
                "canUploadOrderScreenshot": self.has_permission is None
                or self.has_permission(actor_user_id, "group_buy:update_any"),
                "canManageRecords": self.has_permission is None
                or self.has_permission(actor_user_id, "record:view_group"),
            },
        }

    def create_group_buy(self, actor_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_database_enabled()
        self._assert_permission(actor_user_id, "group_buy:create", error_message="当前账号没有创建拼单的权限")

        group_id = _normalize_required_text(
            payload.get("groupId") if "groupId" in payload else payload.get("group_id"),
            "所属谷团",
        )
        self._require_group_access(actor_user_id, group_id)

        with connect(self.config) as conn:
            created = self.repo.create_group_buy(
                conn,
                group_id=group_id,
                type_=_normalize_group_buy_type(payload.get("type")),
                title=_normalize_required_text(payload.get("title"), "拼单标题", 2),
                description=_normalize_optional_text(payload.get("description"), "拼单说明"),
                status=GROUP_BUY_STATUS_WAITING,
                owner_user_id=actor_user_id,
                start_at=_parse_datetime(
                    payload.get("startAt") if "startAt" in payload else payload.get("start_at"),
                    "开始时间",
                ),
                close_at=_parse_datetime(
                    payload.get("closeAt") if "closeAt" in payload else payload.get("close_at"),
                    "截团时间",
                ),
                cover_file_object_id=_normalize_optional_text(
                    payload.get("coverFileObjectId")
                    if "coverFileObjectId" in payload
                    else payload.get("cover_file_object_id"),
                    "活动主图文件",
                ),
                cover_image_url=_normalize_optional_text(
                    payload.get("coverImageUrl")
                    if "coverImageUrl" in payload
                    else payload.get("cover_image_url"),
                    "活动主图",
                ),
                claim_mode=_normalize_optional_text(
                    payload.get("claimMode") if "claimMode" in payload else payload.get("claim_mode"),
                    "拼谷类型",
                ),
                can_cancel_claim=_normalize_optional_bool(
                    payload.get("canCancelClaim")
                    if "canCancelClaim" in payload
                    else payload.get("can_cancel_claim"),
                    "是否允许撤排",
                    False,
                ),
                sale_mode=_normalize_optional_text(
                    payload.get("saleMode") if "saleMode" in payload else payload.get("sale_mode"),
                    "售卖方式",
                ),
                allow_transfer=_normalize_optional_bool(
                    payload.get("allowTransfer")
                    if "allowTransfer" in payload
                    else payload.get("allow_transfer"),
                    "是否允许转单",
                    True,
                ),
                advanced_settings=_normalize_advanced_settings(
                    payload.get("advancedSettings")
                    if "advancedSettings" in payload
                    else payload.get("advanced_settings")
                ),
                payment_channel_id=_normalize_optional_text(
                    payload.get("paymentChannelId")
                    if "paymentChannelId" in payload
                    else payload.get("payment_channel_id"),
                    "默认收款渠道",
                ),
                warehouse_user_id=_normalize_optional_text(
                    payload.get("warehouseUserId")
                    if "warehouseUserId" in payload
                    else payload.get("warehouse_user_id"),
                    "默认囤货人",
                ),
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="group_buy.create",
                object_type="group_buy",
                object_id=created["id"],
                before=None,
                after=created,
                reason="创建拼单",
            )
            conn.commit()
        return {"groupBuyId": created["id"], "status": created["status"]}

    def update_group_buy(
        self,
        actor_user_id: str,
        group_buy_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_database_enabled()
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)

        with connect(self.config) as conn:
            group_buy = self._require_group_buy(conn, group_buy_id)
            self._require_group_access(actor_user_id, group_buy["groupId"])
            self._assert_group_buy_mutable(group_buy)
            if not self._can_edit_group_buy(actor_user_id, group_buy):
                raise AppError(403, "当前账号没有编辑拼单的权限", "FORBIDDEN")

            updated = self.repo.update_group_buy(
                conn,
                group_buy_id=group_buy_id,
                type_=_normalize_group_buy_type(payload.get("type") or group_buy["type"]),
                title=_normalize_required_text(
                    payload.get("title", group_buy["title"]),
                    "拼单标题",
                    2,
                ),
                description=_normalize_optional_text(
                    payload.get("description", group_buy["description"]),
                    "拼单说明",
                ),
                start_at=_parse_datetime(
                    payload.get("startAt", group_buy.get("startAt")),
                    "开始时间",
                ),
                close_at=_parse_datetime(
                    payload.get("closeAt", group_buy["closeAt"]),
                    "截团时间",
                ),
                cover_file_object_id=_normalize_optional_text(
                    payload.get("coverFileObjectId", group_buy.get("coverFileObjectId")),
                    "活动主图文件",
                ),
                cover_image_url=_normalize_optional_text(
                    payload.get("coverImageUrl", group_buy.get("coverImageUrl")),
                    "活动主图",
                ),
                claim_mode=_normalize_optional_text(
                    payload.get("claimMode", group_buy.get("claimMode")),
                    "拼谷类型",
                ),
                can_cancel_claim=_normalize_optional_bool(
                    payload.get("canCancelClaim", group_buy.get("canCancelClaim")),
                    "是否允许撤排",
                    False,
                ),
                sale_mode=_normalize_optional_text(
                    payload.get("saleMode", group_buy.get("saleMode")),
                    "售卖方式",
                ),
                allow_transfer=_normalize_optional_bool(
                    payload.get("allowTransfer", group_buy.get("allowTransfer")),
                    "是否允许转单",
                    True,
                ),
                advanced_settings=_normalize_advanced_settings(
                    payload.get("advancedSettings", group_buy.get("advancedSettings") or {})
                ),
                payment_channel_id=_normalize_optional_text(
                    payload.get("paymentChannelId", group_buy["paymentChannelId"]),
                    "默认收款渠道",
                ),
                warehouse_user_id=_normalize_optional_text(
                    payload.get("warehouseUserId", group_buy["warehouseUserId"]),
                    "默认囤货人",
                ),
            )
            updated_fields = [
                key
                for key in (
                    "type",
                    "title",
                    "description",
                    "startAt",
                    "closeAt",
                    "coverFileObjectId",
                    "coverImageUrl",
                    "claimMode",
                    "canCancelClaim",
                    "saleMode",
                    "allowTransfer",
                    "advancedSettings",
                    "paymentChannelId",
                    "warehouseUserId",
                )
                if updated.get(key) != group_buy.get(key)
            ]
            if not updated_fields:
                raise AppError(400, "没有可更新的字段", "VALIDATION_FAILED")

            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="group_buy.update",
                object_type="group_buy",
                object_id=group_buy_id,
                before=group_buy,
                after=updated,
                reason=reason,
            )
            conn.commit()
        return {"groupBuyId": group_buy_id, "updatedFields": updated_fields}

    def change_group_buy_status(
        self,
        actor_user_id: str,
        group_buy_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_database_enabled()
        new_status = _normalize_group_buy_status(
            payload.get("newStatus") if "newStatus" in payload else payload.get("status")
        )
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)

        with connect(self.config) as conn:
            group_buy = self._require_group_buy(conn, group_buy_id)
            self._require_group_access(actor_user_id, group_buy["groupId"])

            required_permission = (
                "group_buy:cancel"
                if new_status == GROUP_BUY_STATUS_CANCELLED
                else "group_buy:update_any"
            )
            self._assert_permission(
                actor_user_id,
                required_permission,
                error_message="当前账号没有修改拼单状态的权限",
            )

            if group_buy["status"] == new_status:
                raise AppError(400, "拼单状态没有变化", "VALIDATION_FAILED")
            self._assert_status_transition(group_buy["status"], new_status)

            updated = self.repo.change_group_buy_status(
                conn,
                group_buy_id=group_buy_id,
                new_status=new_status,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="group_buy.change_status",
                object_type="group_buy",
                object_id=group_buy_id,
                before=group_buy,
                after=updated,
                reason=reason,
            )
            conn.commit()
        return {
            "groupBuyId": group_buy_id,
            "oldStatus": group_buy["status"],
            "newStatus": updated["status"],
        }

    def create_group_buy_item(
        self,
        actor_user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_database_enabled()
        group_buy_id = _normalize_required_text(
            payload.get("groupBuyId") if "groupBuyId" in payload else payload.get("group_buy_id"),
            "拼单",
        )
        goods_id = _normalize_optional_text(
            payload.get("goodsId") if "goodsId" in payload else payload.get("goods_id"),
            "商品图鉴",
        )
        total_quantity = _normalize_positive_int(
            payload.get("totalQuantity")
            if "totalQuantity" in payload
            else payload.get("total_quantity"),
            "总库存",
        )
        reserved_quantity = _normalize_non_negative_int(
            payload.get("reservedQuantity")
            if "reservedQuantity" in payload
            else payload.get("reserved_quantity", 0),
            "预留库存",
        )
        if reserved_quantity > total_quantity:
            raise AppError(400, "预留库存不能大于总库存", "VALIDATION_FAILED")

        if goods_id:
            # 引用图鉴时，快照字段只在创建时复制一份，不回写图鉴本体。
            snapshot = self._build_item_snapshot_from_goods(goods_id)
        else:
            snapshot = self._build_manual_item_snapshot(payload)

        with connect(self.config) as conn:
            group_buy = self._require_group_buy(conn, group_buy_id)
            self._require_group_access(actor_user_id, group_buy["groupId"])
            self._assert_group_buy_mutable(group_buy)
            if not self._can_edit_group_buy(actor_user_id, group_buy):
                raise AppError(403, "当前账号没有维护拼单商品的权限", "FORBIDDEN")

            created = self.repo.create_group_buy_item(
                conn,
                group_buy_id=group_buy_id,
                goods_id=snapshot.get("goodsId"),
                name_snapshot=snapshot["name"],
                alias_snapshot=snapshot.get("aliases") or [],
                character_names_snapshot=snapshot.get("characterNames") or [],
                description_snapshot=snapshot.get("description"),
                image_url_snapshot=snapshot.get("imageUrl"),
                unit_price_cny=_normalize_price_cny(
                    payload.get("unitPriceCny")
                    if "unitPriceCny" in payload
                    else payload.get("unit_price_cny"),
                    "单价",
                ),
                release_price_jpy_snapshot=snapshot.get("releasePriceJpy"),
                suggested_price_jpy_snapshot=snapshot.get("suggestedPriceJpy"),
                domestic_spot_suggested_price_cny_snapshot=snapshot.get(
                    "domesticSpotSuggestedPriceCny"
                ),
                length_mm_snapshot=snapshot.get("lengthMm"),
                width_mm_snapshot=snapshot.get("widthMm"),
                weight_gram_snapshot=snapshot.get("weightGram"),
                total_quantity=total_quantity,
                reserved_quantity=reserved_quantity,
                claimed_quantity=0,
                available_quantity=total_quantity - reserved_quantity,
                note=_normalize_optional_text(payload.get("note"), "备注"),
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="group_buy_item.create",
                object_type="group_buy_item",
                object_id=created["id"],
                before=None,
                after=created,
                reason="创建拼单商品库存",
            )
            conn.commit()
        return {
            "groupBuyItemId": created["id"],
            "availableQuantity": created["availableQuantity"],
        }

    def update_group_buy_item(
        self,
        actor_user_id: str,
        group_buy_item_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_database_enabled()
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)

        with connect(self.config) as conn:
            group_buy_item = self._require_group_buy_item(conn, group_buy_item_id)
            group_buy = self._require_group_buy(conn, group_buy_item["groupBuyId"])
            self._require_group_access(actor_user_id, group_buy["groupId"])
            self._assert_group_buy_mutable(group_buy)
            if not self._can_edit_group_buy(actor_user_id, group_buy):
                raise AppError(403, "当前账号没有维护拼单商品的权限", "FORBIDDEN")

            has_goods_id, raw_goods_id = _payload_get(payload, "goodsId", "goods_id")
            if has_goods_id:
                next_goods_id = _normalize_optional_text(raw_goods_id, "商品图鉴")
                snapshot = (
                    self._build_item_snapshot_from_goods(next_goods_id)
                    if next_goods_id
                    else self._build_manual_item_snapshot(
                        {
                            **payload,
                            "name": group_buy_item["name"],
                            "aliases": group_buy_item["aliases"],
                            "characterNames": group_buy_item["characterNames"],
                            "description": group_buy_item["description"],
                            "imageUrl": group_buy_item["imageUrl"],
                            "note": group_buy_item["note"],
                        }
                    )
                )
            else:
                snapshot = {
                    "goodsId": group_buy_item["goodsId"],
                    "name": _normalize_optional_text(
                        payload.get("name", group_buy_item["name"]),
                        "商品名称",
                    )
                    or group_buy_item["note"],
                    "aliases": _normalize_string_list(
                        payload.get("aliases", group_buy_item["aliases"]),
                        "别名",
                    ),
                    "characterNames": _normalize_string_list(
                        payload.get("characterNames", group_buy_item["characterNames"]),
                        "角色名列表",
                    ),
                    "description": _normalize_optional_text(
                        payload.get("description", group_buy_item["description"]),
                        "商品描述",
                    ),
                    "imageUrl": _normalize_optional_text(
                        payload.get("imageUrl", group_buy_item["imageUrl"]),
                        "商品图片",
                    ),
                    "releasePriceJpy": _normalize_optional_int(
                        payload.get("releasePriceJpy", group_buy_item["releasePriceJpy"]),
                        "发售价",
                    ),
                    "suggestedPriceJpy": _normalize_optional_int(
                        payload.get("suggestedPriceJpy", group_buy_item["suggestedPriceJpy"]),
                        "建议价",
                    ),
                    "domesticSpotSuggestedPriceCny": (
                        _normalize_price_cny(
                            payload.get(
                                "domesticSpotSuggestedPriceCny",
                                group_buy_item["domesticSpotSuggestedPriceCny"],
                            ),
                            "国内现货建议价",
                        )
                        if (
                            payload.get("domesticSpotSuggestedPriceCny")
                            or group_buy_item["domesticSpotSuggestedPriceCny"] is not None
                        )
                        else None
                    ),
                    "lengthMm": _normalize_optional_int(
                        payload.get("lengthMm", group_buy_item["lengthMm"]),
                        "长度",
                    ),
                    "widthMm": _normalize_optional_int(
                        payload.get("widthMm", group_buy_item["widthMm"]),
                        "宽度",
                    ),
                    "weightGram": _normalize_optional_int(
                        payload.get("weightGram", group_buy_item["weightGram"]),
                        "重量",
                    ),
                }

            if not snapshot["name"] and not group_buy_item["note"]:
                raise AppError(
                    400,
                    "商品快照至少需要名称，或用备注让成员能识别商品",
                    "VALIDATION_FAILED",
                )

            unit_price_cny = (
                _normalize_price_cny(payload["unitPriceCny"], "单价")
                if "unitPriceCny" in payload
                else group_buy_item["unitPriceCny"]
            )
            if group_buy_item["claimedQuantity"] > 0 and unit_price_cny != group_buy_item["unitPriceCny"]:
                raise AppError(
                    400,
                    "已有人认领后修改价格，需要先提交调价申请",
                    "VALIDATION_FAILED",
                )

            total_quantity = (
                _normalize_positive_int(payload["totalQuantity"], "总库存")
                if "totalQuantity" in payload
                else group_buy_item["totalQuantity"]
            )
            reserved_quantity = (
                _normalize_non_negative_int(payload["reservedQuantity"], "预留库存")
                if "reservedQuantity" in payload
                else group_buy_item["reservedQuantity"]
            )
            if total_quantity < group_buy_item["claimedQuantity"] + reserved_quantity:
                raise AppError(
                    400,
                    "总库存不能小于已认领数量与预留库存之和",
                    "VALIDATION_FAILED",
                )

            updated = self.repo.update_group_buy_item(
                conn,
                group_buy_item_id=group_buy_item_id,
                goods_id=snapshot.get("goodsId"),
                name_snapshot=snapshot["name"],
                alias_snapshot=snapshot["aliases"],
                character_names_snapshot=snapshot["characterNames"],
                description_snapshot=snapshot["description"],
                image_url_snapshot=snapshot["imageUrl"],
                unit_price_cny=unit_price_cny,
                release_price_jpy_snapshot=snapshot["releasePriceJpy"],
                suggested_price_jpy_snapshot=snapshot["suggestedPriceJpy"],
                domestic_spot_suggested_price_cny_snapshot=snapshot["domesticSpotSuggestedPriceCny"],
                length_mm_snapshot=snapshot["lengthMm"],
                width_mm_snapshot=snapshot["widthMm"],
                weight_gram_snapshot=snapshot["weightGram"],
                total_quantity=total_quantity,
                reserved_quantity=reserved_quantity,
                claimed_quantity=group_buy_item["claimedQuantity"],
                # 数据库里把 available_quantity 落成冗余字段，读列表时不用反复现算。
                available_quantity=total_quantity - reserved_quantity - group_buy_item["claimedQuantity"],
                note=_normalize_optional_text(
                    payload.get("note", group_buy_item["note"]),
                    "备注",
                ),
            )
            updated_fields = [
                key
                for key in (
                    "goodsId",
                    "name",
                    "aliases",
                    "characterNames",
                    "description",
                    "imageUrl",
                    "unitPriceCny",
                    "releasePriceJpy",
                    "suggestedPriceJpy",
                    "domesticSpotSuggestedPriceCny",
                    "lengthMm",
                    "widthMm",
                    "weightGram",
                    "totalQuantity",
                    "reservedQuantity",
                    "note",
                )
                if updated.get(key) != group_buy_item.get(key)
            ]
            if not updated_fields:
                raise AppError(400, "没有可更新的字段", "VALIDATION_FAILED")

            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="group_buy_item.update",
                object_type="group_buy_item",
                object_id=group_buy_item_id,
                before=group_buy_item,
                after=updated,
                reason=reason,
            )
            conn.commit()
        return {"groupBuyItemId": group_buy_item_id, "updatedFields": updated_fields}

    def delete_group_buy_item(self, actor_user_id: str, group_buy_item_id: str) -> dict[str, Any]:
        self._assert_database_enabled()

        with connect(self.config) as conn:
            group_buy_item = self._require_group_buy_item(conn, group_buy_item_id)
            group_buy = self._require_group_buy(conn, group_buy_item["groupBuyId"])
            self._require_group_access(actor_user_id, group_buy["groupId"])
            self._assert_group_buy_mutable(group_buy)
            if not self._can_edit_group_buy(actor_user_id, group_buy):
                raise AppError(403, "当前账号没有维护拼单商品的权限", "FORBIDDEN")
            if group_buy_item["claimedQuantity"] > 0:
                raise AppError(400, "已有成员认领的谷子不能直接删除", "GROUP_BUY_ITEM_CLAIMED")

            if not self.repo.delete_group_buy_item(conn, group_buy_item_id):
                raise AppError(404, "拼单商品不存在", "NOT_FOUND")
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="group_buy_item.delete",
                object_type="group_buy_item",
                object_id=group_buy_item_id,
                before=group_buy_item,
                after=None,
                reason="删除未认领谷子",
            )
            conn.commit()
        return {"ok": True, "groupBuyItemId": group_buy_item_id}

    def claim_group_buy_item(
        self,
        actor_user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 认领记录主流程迁移到 group_buy_records 模块，避免重复维护记录状态逻辑。
        if self.group_buy_records_module is not None:
            return self.group_buy_records_module.create_record_for_user(actor_user_id, payload)

        self._assert_database_enabled()
        group_buy_item_id = _normalize_required_text(
            payload.get("groupBuyItemId")
            if "groupBuyItemId" in payload
            else payload.get("group_buy_item_id"),
            "拼单商品",
        )
        payload_group_buy_id = _normalize_optional_text(
            payload.get("groupBuyId") if "groupBuyId" in payload else payload.get("group_buy_id"),
            "拼单",
        )
        member_user_id = _normalize_optional_text(
            payload.get("memberUserId")
            if "memberUserId" in payload
            else payload.get("member_user_id"),
            "成员",
        ) or actor_user_id
        quantity = _normalize_positive_int(payload.get("quantity"), "数量")
        note = _normalize_optional_text(payload.get("note"), "备注")

        with connect(self.config) as conn:
            group_buy_item = self._require_group_buy_item_for_update(conn, group_buy_item_id)
            group_buy = self._require_group_buy(conn, group_buy_item["groupBuyId"])
            if payload_group_buy_id is not None and payload_group_buy_id != group_buy["id"]:
                raise AppError(400, "拼单商品不属于当前拼单", "VALIDATION_FAILED")
            self._require_group_access(actor_user_id, group_buy["groupId"])
            self._require_member_in_group(member_user_id, group_buy["groupId"])
            if not self._can_create_record_for_member(actor_user_id, member_user_id):
                raise AppError(403, "当前账号没有创建拼单记录的权限", "FORBIDDEN")
            if group_buy["status"] not in CLAIMABLE_GROUP_BUY_STATUSES:
                raise AppError(400, "当前拼单状态暂时不能认领", "INVALID_STATUS")
            if quantity > group_buy_item["availableQuantity"]:
                raise AppError(400, "可认领数量不足", "INSUFFICIENT_STOCK")

            item_after_claim = self.repo.update_group_buy_item_quantities(
                conn,
                group_buy_item_id=group_buy_item_id,
                reserved_quantity=group_buy_item["reservedQuantity"],
                claimed_quantity=group_buy_item["claimedQuantity"] + quantity,
                available_quantity=group_buy_item["availableQuantity"] - quantity,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="group_buy_item.claim_stock",
                object_type="group_buy_item",
                object_id=group_buy_item_id,
                before=group_buy_item,
                after=item_after_claim,
                reason=f"成员 {member_user_id} 认领 {quantity} 件",
            )

            existing_record = self.repo.get_group_buy_record_for_member(
                conn,
                group_buy_item_id=group_buy_item_id,
                member_user_id=member_user_id,
                lock=True,
            )
            if existing_record is None:
                record = self.repo.create_group_buy_record(
                    conn,
                    group_buy_id=group_buy["id"],
                    group_buy_item_id=group_buy_item_id,
                    member_user_id=member_user_id,
                    status=GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT,
                    quantity=quantity,
                    status_priority=_status_priority(GROUP_BUY_RECORD_STATUS_PENDING_GOODS_PAYMENT),
                    note=note,
                )
                self._audit(
                    conn,
                    actor_user_id=actor_user_id,
                    action="record.create",
                    object_type="group_buy_record",
                    object_id=record["id"],
                    before=None,
                    after=record,
                    reason="成员认领商品" if actor_user_id == member_user_id else "维护人代成员建单",
                )
            else:
                record_before = existing_record
                record = self.repo.update_group_buy_record_quantity(
                    conn,
                    group_buy_record_id=existing_record["id"],
                    quantity=existing_record["quantity"] + quantity,
                    status=existing_record["status"],
                    status_priority=_status_priority(existing_record["status"]),
                )
                self._audit(
                    conn,
                    actor_user_id=actor_user_id,
                    action="record.update_quantity",
                    object_type="group_buy_record",
                    object_id=record["id"],
                    before=record_before,
                    after=record,
                    reason="成员追加认领" if actor_user_id == member_user_id else "维护人代成员追加认领",
                )

            if (
                self.create_charge_from_related_module is not None
                and record.get("goodsChargeId") is None
                and group_buy.get("ownerUserId")
            ):
                charge = self.create_charge_from_related_module(
                    conn,
                    {
                        "type": CHARGE_TYPE_INITIAL_GOODS,
                        "payerUserId": member_user_id,
                        "payeeUserId": group_buy["ownerUserId"],
                        "bizType": "group_buy_record",
                        "bizId": record["id"],
                        "amountCny": _multiply_price_cny(group_buy_item["unitPriceCny"], quantity),
                        "paymentChannelId": group_buy["paymentChannelId"],
                        "snapshot": {
                            "groupBuyRecordId": record["id"],
                            "groupBuyId": group_buy["id"],
                            "groupBuyItemId": group_buy_item_id,
                            "quantity": quantity,
                            "unitPriceCny": group_buy_item["unitPriceCny"],
                        },
                        "note": "商品首款",
                        "actorUserId": actor_user_id,
                    },
                )
                record_before_link, record = self.repo.link_group_buy_record_charge(
                    conn,
                    group_buy_record_id=record["id"],
                    charge_type=CHARGE_TYPE_INITIAL_GOODS,
                    charge_id=charge["chargeId"],
                )
                self._audit(
                    conn,
                    actor_user_id=actor_user_id,
                    action="record.link_charge",
                    object_type="group_buy_record",
                    object_id=record["id"],
                    before=record_before_link,
                    after=record,
                    reason="关联商品首款费用",
                )

            conn.commit()

        return {
            "groupBuyRecordId": record["id"],
            "recordId": record["id"],
            "status": record["status"],
            "displayStatus": record["displayStatus"],
            "quantity": record["quantity"],
            "availableQuantity": item_after_claim["availableQuantity"],
        }

    def reserve_or_claim_item_stock(
        self,
        actor_user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_database_enabled()
        group_buy_item_id = _normalize_required_text(
            payload.get("groupBuyItemId")
            if "groupBuyItemId" in payload
            else payload.get("group_buy_item_id"),
            "拼单商品",
        )
        member_user_id = _normalize_required_text(
            payload.get("memberUserId")
            if "memberUserId" in payload
            else payload.get("member_user_id"),
            "成员",
        )
        quantity = _normalize_positive_int(payload.get("quantity"), "数量")
        force = bool(payload.get("force"))
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)

        with connect(self.config) as conn:
            group_buy_item = self._require_group_buy_item(conn, group_buy_item_id)
            group_buy = self._require_group_buy(conn, group_buy_item["groupBuyId"])
            self._require_group_access(actor_user_id, group_buy["groupId"])
            if not force and group_buy["status"] not in CLAIMABLE_GROUP_BUY_STATUSES:
                raise AppError(400, "当前拼单状态暂时不能认领", "INVALID_STATUS")

            if force:
                self._assert_permission(
                    actor_user_id,
                    "group_buy:update_any",
                    error_message="当前账号没有强制调整库存的权限",
                )

            available_quantity = group_buy_item["availableQuantity"]
            if quantity > available_quantity:
                raise AppError(400, "可认领数量不足", "INSUFFICIENT_STOCK")

            updated = self.repo.update_group_buy_item_quantities(
                conn,
                group_buy_item_id=group_buy_item_id,
                reserved_quantity=group_buy_item["reservedQuantity"],
                claimed_quantity=group_buy_item["claimedQuantity"] + quantity,
                # 占库存时同步维护 claimed / available，避免记录模块外再做一层补算。
                available_quantity=available_quantity - quantity,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="group_buy_item.claim_stock",
                object_type="group_buy_item",
                object_id=group_buy_item_id,
                before=group_buy_item,
                after=updated,
                reason=f"{reason}（成员 {member_user_id}）",
            )
            conn.commit()
        return {
            "groupBuyItemId": group_buy_item_id,
            "claimedQuantity": updated["claimedQuantity"],
            "availableQuantity": updated["availableQuantity"],
        }

    def release_item_stock(
        self,
        actor_user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_database_enabled()
        group_buy_item_id = _normalize_required_text(
            payload.get("groupBuyItemId")
            if "groupBuyItemId" in payload
            else payload.get("group_buy_item_id"),
            "拼单商品",
        )
        quantity = _normalize_positive_int(payload.get("quantity"), "数量")
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)

        with connect(self.config) as conn:
            group_buy_item = self._require_group_buy_item(conn, group_buy_item_id)
            group_buy = self._require_group_buy(conn, group_buy_item["groupBuyId"])
            self._require_group_access(actor_user_id, group_buy["groupId"])
            if not self._can_edit_group_buy(actor_user_id, group_buy):
                raise AppError(403, "当前账号没有调整库存的权限", "FORBIDDEN")

            if quantity > group_buy_item["claimedQuantity"]:
                raise AppError(400, "释放数量不能大于已认领数量", "VALIDATION_FAILED")

            updated = self.repo.update_group_buy_item_quantities(
                conn,
                group_buy_item_id=group_buy_item_id,
                reserved_quantity=group_buy_item["reservedQuantity"],
                claimed_quantity=group_buy_item["claimedQuantity"] - quantity,
                available_quantity=group_buy_item["availableQuantity"] + quantity,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="group_buy_item.release_stock",
                object_type="group_buy_item",
                object_id=group_buy_item_id,
                before=group_buy_item,
                after=updated,
                reason=reason,
            )
            conn.commit()
        return {
            "groupBuyItemId": group_buy_item_id,
            "availableQuantity": updated["availableQuantity"],
        }

    def request_price_adjustment(
        self,
        actor_user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_database_enabled()
        group_buy_item_id = _normalize_required_text(
            payload.get("groupBuyItemId")
            if "groupBuyItemId" in payload
            else payload.get("group_buy_item_id"),
            "拼单商品",
        )
        new_price_cny = _normalize_price_cny(
            payload.get("newPriceCny")
            if "newPriceCny" in payload
            else payload.get("new_price_cny"),
            "新单价",
        )
        impact_scope = _normalize_required_text(
            payload.get("impactScope")
            if "impactScope" in payload
            else payload.get("impact_scope"),
            "影响范围",
        )
        reason = _normalize_required_text(payload.get("reason"), "reason", 2)

        with connect(self.config) as conn:
            group_buy_item = self._require_group_buy_item(conn, group_buy_item_id)
            group_buy = self._require_group_buy(conn, group_buy_item["groupBuyId"])
            self._require_group_access(actor_user_id, group_buy["groupId"])
            if not self._can_edit_group_buy(actor_user_id, group_buy):
                raise AppError(403, "当前账号没有申请调价的权限", "FORBIDDEN")

            if new_price_cny == group_buy_item["unitPriceCny"]:
                raise AppError(400, "新单价和当前单价一致", "VALIDATION_FAILED")

            created = self.repo.create_price_adjustment(
                conn,
                group_buy_id=group_buy["id"],
                group_buy_item_id=group_buy_item_id,
                old_price_cny=group_buy_item["unitPriceCny"],
                new_price_cny=new_price_cny,
                impact_scope=impact_scope,
                reason=reason,
                status=PRICE_ADJUSTMENT_STATUS_PENDING_REVIEW,
                requested_by=actor_user_id,
            )
            self._audit(
                conn,
                actor_user_id=actor_user_id,
                action="price_adjustment.request",
                object_type="price_adjustment",
                object_id=created["id"],
                before=None,
                after=created,
                reason=reason,
            )
            conn.commit()
        return {
            "priceAdjustmentId": created["id"],
            "status": created["status"],
        }
