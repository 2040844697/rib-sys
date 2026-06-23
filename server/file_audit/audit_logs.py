from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Callable

from ..errors import AppError


DEFAULT_AUDIT_PAGE_SIZE = 20
MAX_AUDIT_PAGE_SIZE = 100
MAX_AUDIT_STRING_LENGTH = 500
MAX_AUDIT_COLLECTION_ITEMS = 20
MAX_AUDIT_DICT_FIELDS = 30
MAX_AUDIT_DEPTH = 4


def clone(value: Any) -> Any:
    return copy.deepcopy(value)


def normalize_required_text(value: Any, field_name: str, min_length: int = 1) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if len(normalized) < min_length:
        raise AppError(400, f"{field_name}填写不完整", "VALIDATION_FAILED")
    return normalized


def normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AppError(400, "字段格式不正确", "VALIDATION_FAILED")
    normalized = value.strip()
    return normalized or None


def normalize_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED")
    if value < 0:
        raise AppError(400, f"{field_name}不能小于 0", "VALIDATION_FAILED")
    return value


def normalize_page_number(value: Any, field_name: str, default_value: int) -> int:
    if value in {None, ""}:
        return default_value

    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise AppError(400, f"{field_name}格式不正确", "VALIDATION_FAILED") from exc

    if number <= 0:
        raise AppError(400, f"{field_name}必须大于 0", "VALIDATION_FAILED")

    return number


def parse_iso_datetime(value: str | None, field_name: str) -> datetime | None:
    if value is None:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppError(400, f"{field_name}不是合法时间", "VALIDATION_FAILED") from exc


def trim_snapshot(value: Any, depth: int = 0) -> Any:
    # 审计只保留关键层级，避免把超大对象直接写进 JSON 日志。
    if depth >= MAX_AUDIT_DEPTH:
        return "[truncated]"

    if isinstance(value, str):
        if len(value) <= MAX_AUDIT_STRING_LENGTH:
            return value
        return value[:MAX_AUDIT_STRING_LENGTH] + "...[truncated]"

    if isinstance(value, list):
        items = [trim_snapshot(item, depth + 1) for item in value[:MAX_AUDIT_COLLECTION_ITEMS]]
        if len(value) > MAX_AUDIT_COLLECTION_ITEMS:
            items.append(f"...[{len(value) - MAX_AUDIT_COLLECTION_ITEMS} more items]")
        return items

    if isinstance(value, dict):
        trimmed: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_AUDIT_DICT_FIELDS:
                trimmed["__truncated_fields__"] = len(value) - MAX_AUDIT_DICT_FIELDS
                break
            trimmed[str(key)] = trim_snapshot(item, depth + 1)
        return trimmed

    return clone(value)


class AuditService:
    def __init__(
        self,
        *,
        state: dict[str, Any],
        next_id: Callable[[str, str], str],
        can_list_logs: Callable[[dict[str, Any]], bool],
        can_view_log: Callable[[dict[str, Any], dict[str, Any]], bool],
        get_user_snapshot_by_id: Callable[[str], dict[str, Any] | None],
    ):
        self.state = state
        self.next_id = next_id
        self.can_list_logs = can_list_logs
        self.can_view_log = can_view_log
        self.get_user_snapshot_by_id = get_user_snapshot_by_id

    def log(
        self,
        *,
        actor_user_id: str | None,
        action: str,
        object_type: str,
        object_id: str,
        before: Any,
        after: Any,
        reason: str | None,
    ) -> dict[str, Any]:
        record = {
            "id": self.next_id("auditLog", "audit"),
            "actorUserId": actor_user_id or "system",
            "action": normalize_required_text(action, "操作类型"),
            "objectType": normalize_required_text(object_type, "对象类型"),
            "objectId": normalize_required_text(object_id, "对象 ID"),
            "before": trim_snapshot(before) if before is not None else None,
            "after": trim_snapshot(after) if after is not None else None,
            "reason": normalize_optional_text(reason),
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        self.state["auditLogs"].append(record)
        return clone(record)

    def list_logs(self, viewer: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        if not self.can_list_logs(viewer):
            raise AppError(403, "当前账号没有查看审计日志的权限", "FORBIDDEN")

        object_type = normalize_optional_text(filters.get("objectType"))
        object_id = normalize_optional_text(filters.get("objectId"))
        actor_user_id = normalize_optional_text(filters.get("actorUserId"))
        action = normalize_optional_text(filters.get("action"))
        created_from = parse_iso_datetime(
            normalize_optional_text(filters.get("createdFrom")),
            "createdFrom",
        )
        created_to = parse_iso_datetime(
            normalize_optional_text(filters.get("createdTo")),
            "createdTo",
        )
        page = normalize_page_number(filters.get("page"), "page", 1)
        page_size = normalize_page_number(
            filters.get("pageSize"),
            "pageSize",
            DEFAULT_AUDIT_PAGE_SIZE,
        )
        if page_size > MAX_AUDIT_PAGE_SIZE:
            raise AppError(400, f"pageSize 不能超过 {MAX_AUDIT_PAGE_SIZE}", "VALIDATION_FAILED")

        items: list[dict[str, Any]] = []
        for log in reversed(self.state["auditLogs"]):
            if not self.can_view_log(viewer, log):
                continue
            if object_type and log["objectType"] != object_type:
                continue
            if object_id and log["objectId"] != object_id:
                continue
            if actor_user_id and log["actorUserId"] != actor_user_id:
                continue
            if action and log["action"] != action:
                continue

            created_at = parse_iso_datetime(log.get("createdAt"), "createdAt")
            if created_from and created_at and created_at < created_from:
                continue
            if created_to and created_at and created_at > created_to:
                continue

            items.append(
                {
                    **clone(log),
                    "actorUser": self.get_user_snapshot_by_id(log["actorUserId"])
                    if log["actorUserId"] != "system"
                    else None,
                }
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
