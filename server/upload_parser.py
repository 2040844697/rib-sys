from __future__ import annotations

from email.parser import BytesParser
from email.policy import default as email_policy
from pathlib import Path

from .errors import AppError


def parse_multipart_upload(content_type: str, body: bytes) -> tuple[str, str, str | None, bytes]:
    message = BytesParser(policy=email_policy).parsebytes(
        b"Content-Type: " + content_type.encode("utf-8") + b"\r\n"
        b"MIME-Version: 1.0\r\n\r\n"
        + body
    )
    if not message.is_multipart():
        raise AppError(400, "multipart 请求格式不正确", "VALIDATION_FAILED")

    bucket = "misc"
    filename = "upload.bin"
    file_content_type: str | None = None
    raw = b""

    for part in message.iter_parts():
        field_name = part.get_param("name", header="content-disposition")
        if field_name == "bucket":
            payload = part.get_payload(decode=True) or b""
            bucket = payload.decode(part.get_content_charset() or "utf-8", errors="replace") or "misc"
            continue

        if field_name != "file":
            continue

        part_filename = part.get_filename()
        if not part_filename:
            raise AppError(400, "multipart 请求需要包含 file 字段", "VALIDATION_FAILED")
        filename = Path(part_filename).name or filename
        file_content_type = part.get_content_type()
        raw = part.get_payload(decode=True) or b""

    if not raw:
        raise AppError(400, "multipart 请求需要包含 file 字段", "VALIDATION_FAILED")
    return bucket, filename, file_content_type, raw
