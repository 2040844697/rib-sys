from __future__ import annotations

import copy
from typing import Any

from ..errors import AppError


def clone(value: Any) -> Any:
    return copy.deepcopy(value)


def payload_get(payload: dict[str, Any], *keys: str) -> tuple[bool, Any]:
    for key in keys:
        if key in payload:
            return True, payload[key]
    return False, None


def normalize_required_text(value: Any, field_name: str, min_length: int = 1) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if len(normalized) < min_length:
        raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
    return normalized


def normalize_optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    normalized = value.strip()
    return normalized or None


def normalize_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    if value <= 0:
        raise AppError(400, f"{field_name}必须大于 0", "VALIDATION_FAILED")
    return value


def normalize_transfer_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise AppError(400, "items格式不正确", "VALIDATION_FAILED")

    items: list[dict[str, Any]] = []
    seen_record_ids: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise AppError(400, f"items[{index}]格式不正确", "VALIDATION_FAILED")

        _, raw_record_id = payload_get(
            item,
            "groupBuyRecordId",
            "group_buy_record_id",
            "participationItemId",
            "participation_item_id",
        )
        record_id = normalize_required_text(raw_record_id, f"items[{index}].groupBuyRecordId")
        if record_id in seen_record_ids:
            raise AppError(400, "同一拼单记录不能重复转单", "DUPLICATED_OPERATION")

        items.append(
            {
                "groupBuyRecordId": record_id,
                "quantity": normalize_positive_int(item.get("quantity"), f"items[{index}].quantity"),
            }
        )
        seen_record_ids.add(record_id)

    return items
