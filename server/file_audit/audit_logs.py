from __future__ import annotations

import copy
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Callable

from ..config import Config
from ..db_access import connect, to_iso
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


def _audit_actor_to_db(actor_user_id: str | None) -> str | None:
    return None if actor_user_id in {None, "system"} else actor_user_id


def _audit_actor_from_db(actor_user_id: str | None) -> str:
    return actor_user_id or "system"


def _json_from_db(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _build_audit_log(row: dict[str, Any], actor_user: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": row["id"],
        "actorUserId": _audit_actor_from_db(row.get("actor_user_id")),
        "action": row["action"],
        "objectType": row["object_type"],
        "objectId": row["object_id"],
        "before": _json_from_db(row.get("before_json")),
        "after": _json_from_db(row.get("after_json")),
        "reason": row.get("reason"),
        "createdAt": to_iso(row.get("created_at")),
        "actorUser": actor_user,
    }


class AuditService:
    """Legacy JSON audit service kept for the migration period."""

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


class DatabaseAuditService:
    def __init__(
        self,
        *,
        config: Config,
        can_list_logs: Callable[[dict[str, Any]], bool],
        get_user_snapshot_by_id: Callable[[str], dict[str, Any] | None],
    ):
        self.config = config
        self.can_list_logs = can_list_logs
        self.get_user_snapshot_by_id = get_user_snapshot_by_id

    def _dict_row(self):
        try:
            from psycopg.rows import dict_row
        except ModuleNotFoundError:
            return None

        return dict_row

    def log_in_connection(
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
    ) -> dict[str, Any]:
        before_json = trim_snapshot(before) if before is not None else None
        after_json = trim_snapshot(after) if after is not None else None

        with conn.cursor(row_factory=self._dict_row()) as cur:
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
                RETURNING *
                """,
                (
                    f"audit_{secrets.token_hex(8)}",
                    _audit_actor_to_db(actor_user_id),
                    normalize_required_text(action, "操作类型"),
                    normalize_required_text(object_type, "对象类型"),
                    normalize_required_text(object_id, "对象 ID"),
                    None if before_json is None else json.dumps(before_json, ensure_ascii=False),
                    None if after_json is None else json.dumps(after_json, ensure_ascii=False),
                    normalize_optional_text(reason),
                ),
            )
            row = cur.fetchone()

        actor_user_id_from_db = row.get("actor_user_id")
        actor_user = (
            self.get_user_snapshot_by_id(actor_user_id_from_db)
            if actor_user_id_from_db
            else None
        )
        return _build_audit_log(row, actor_user=actor_user)

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
        with connect(self.config) as conn:
            record = self.log_in_connection(
                conn,
                actor_user_id=actor_user_id,
                action=action,
                object_type=object_type,
                object_id=object_id,
                before=before,
                after=after,
                reason=reason,
            )
            conn.commit()
        return record

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

        conditions: list[str] = []
        params: list[Any] = []

        if object_type:
            conditions.append("object_type = %s")
            params.append(object_type)
        if object_id:
            conditions.append("object_id = %s")
            params.append(object_id)
        if actor_user_id:
            if actor_user_id == "system":
                conditions.append("actor_user_id IS NULL")
            else:
                conditions.append("actor_user_id = %s")
                params.append(actor_user_id)
        if action:
            conditions.append("action = %s")
            params.append(action)
        if created_from:
            conditions.append("created_at >= %s")
            params.append(created_from)
        if created_to:
            conditions.append("created_at <= %s")
            params.append(created_to)

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        offset = (page - 1) * page_size

        with connect(self.config, row_factory=self._dict_row()) as conn:
            with conn.cursor(row_factory=self._dict_row()) as cur:
                cur.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM audit_logs
                    {where_sql}
                    """,
                    params,
                )
                total = cur.fetchone()["total"]

                cur.execute(
                    f"""
                    SELECT *
                    FROM audit_logs
                    {where_sql}
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s OFFSET %s
                    """,
                    [*params, page_size, offset],
                )
                rows = cur.fetchall()
            conn.rollback()

        items = []
        for row in rows:
            actor_user_id_from_db = row.get("actor_user_id")
            actor_user = (
                self.get_user_snapshot_by_id(actor_user_id_from_db)
                if actor_user_id_from_db
                else None
            )
            items.append(_build_audit_log(row, actor_user=actor_user))

        return {
            "items": items,
            "total": total,
            "page": page,
            "pageSize": page_size,
        }
