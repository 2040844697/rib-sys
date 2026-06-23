from __future__ import annotations

from typing import Any, Callable

from ..errors import AppError
from .audit_logs import (
    AuditService,
    clone,
    normalize_optional_text,
    normalize_positive_int,
    normalize_required_text,
)


ALLOWED_FILE_BUCKETS = {"goods", "payments", "orders", "channels", "misc"}
FILE_OBJECT_ACTIVE = "active"
FILE_OBJECT_VOIDED = "voided"


def ensure_file_audit_state(state: dict[str, Any]) -> bool:
    changed = False

    counters = state.setdefault("counters", {})
    file_objects = state.setdefault("fileObjects", [])
    audit_logs = state.setdefault("auditLogs", [])

    if "fileObject" not in counters:
        counters["fileObject"] = len(file_objects)
        changed = True
    if "auditLog" not in counters:
        counters["auditLog"] = len(audit_logs)
        changed = True

    for file_object in file_objects:
        if "status" not in file_object:
            file_object["status"] = FILE_OBJECT_ACTIVE
            changed = True
        if "updatedAt" not in file_object:
            file_object["updatedAt"] = file_object.get("createdAt")
            changed = True

    return changed


class FileService:
    def __init__(
        self,
        *,
        state: dict[str, Any],
        next_id: Callable[[str, str], str],
        audit_service: AuditService,
        get_user_snapshot_by_id: Callable[[str], dict[str, Any] | None],
        now_iso: Callable[[], str],
    ):
        self.state = state
        self.next_id = next_id
        self.audit_service = audit_service
        self.get_user_snapshot_by_id = get_user_snapshot_by_id
        self.now_iso = now_iso

    def require_active_file_object(self, file_object_id: str) -> dict[str, Any]:
        file_object = next(
            (item for item in self.state["fileObjects"] if item["id"] == file_object_id),
            None,
        )
        if file_object is None:
            raise AppError(404, "文件对象不存在", "NOT_FOUND")
        if file_object.get("status") == FILE_OBJECT_VOIDED:
            raise AppError(400, "文件对象已经作废", "VALIDATION_FAILED")
        return clone(file_object)

    def create_upload_object(
        self,
        *,
        uploaded_by: str,
        bucket: Any,
        object_key: Any,
        url: Any,
        content_type: Any = None,
        size_bytes: Any = None,
    ) -> dict[str, Any]:
        normalized_bucket = normalize_required_text(bucket, "bucket")
        if normalized_bucket not in ALLOWED_FILE_BUCKETS:
            raise AppError(400, "bucket 不在允许范围内", "VALIDATION_FAILED")

        uploaded_by_user = self.get_user_snapshot_by_id(uploaded_by)
        if uploaded_by_user is None:
            raise AppError(404, "上传用户不存在", "NOT_FOUND")

        normalized_object_key = normalize_required_text(object_key, "objectKey")
        normalized_url = normalize_required_text(url, "url")
        normalized_content_type = normalize_optional_text(content_type)
        normalized_size_bytes = (
            normalize_positive_int(size_bytes, "sizeBytes") if size_bytes is not None else None
        )

        duplicated = next(
            (
                item
                for item in self.state["fileObjects"]
                if item["bucket"] == normalized_bucket and item["objectKey"] == normalized_object_key
            ),
            None,
        )
        if duplicated is not None:
            raise AppError(400, "同一个 bucket 和 objectKey 已经登记过", "DUPLICATED_OPERATION")

        timestamp = self.now_iso()
        record = {
            "id": self.next_id("fileObject", "file"),
            "bucket": normalized_bucket,
            "objectKey": normalized_object_key,
            "url": normalized_url,
            "contentType": normalized_content_type,
            "sizeBytes": normalized_size_bytes,
            "uploadedBy": uploaded_by,
            "status": FILE_OBJECT_ACTIVE,
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }
        self.state["fileObjects"].append(record)

        self.audit_service.log(
            actor_user_id=uploaded_by,
            action="file_object.create",
            object_type="file_object",
            object_id=record["id"],
            before=None,
            after=record,
            reason="登记上传文件",
        )

        return {
            "fileObjectId": record["id"],
            "url": record["url"],
            "fileObject": {
                **clone(record),
                "uploadedByUser": uploaded_by_user,
            },
        }

    def void_file_object(
        self,
        *,
        actor_user_id: str,
        file_object_id: str,
        reason: Any,
    ) -> dict[str, Any]:
        normalized_reason = normalize_required_text(reason, "reason", 2)
        record = next(
            (item for item in self.state["fileObjects"] if item["id"] == file_object_id),
            None,
        )
        if record is None:
            raise AppError(404, "文件对象不存在", "NOT_FOUND")

        if record["status"] == FILE_OBJECT_VOIDED:
            raise AppError(400, "文件对象已经作废", "DUPLICATED_OPERATION")

        before = clone(record)
        record["status"] = FILE_OBJECT_VOIDED
        record["updatedAt"] = self.now_iso()

        self.audit_service.log(
            actor_user_id=actor_user_id,
            action="file_object.void",
            object_type="file_object",
            object_id=record["id"],
            before=before,
            after=record,
            reason=normalized_reason,
        )

        return {
            "fileObjectId": record["id"],
            "status": record["status"],
        }
