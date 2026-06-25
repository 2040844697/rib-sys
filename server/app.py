from __future__ import annotations

import json
import mimetypes
import re
import secrets
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

if __package__ in {None, ""}:
    ROOT_DIR = Path(__file__).resolve().parent.parent
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))

    from server.app_context import AppContext
    from server.config import load_config
    from server.db_bootstrap import describe_database_target, initialize_database_schema
    from server.errors import AppError
else:
    from .app_context import AppContext
    from .config import load_config
    from .db_bootstrap import describe_database_target, initialize_database_schema
    from .errors import AppError

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG = load_config(ROOT_DIR)
UPLOAD_ROOT = ROOT_DIR / "public" / "uploads"
ALLOWED_UPLOAD_BUCKETS = {"goods", "payments", "orders", "channels", "misc"}


def _initialize_database_bootstrap():
    if not CONFIG.database_url:
        raise RuntimeError("DATABASE_URL is required.")

    print(
        "[ribsys-api] config sources: "
        f"DATABASE_URL={CONFIG.database_url_source}, "
        f"RIBSYS_INIT_DB_ON_STARTUP={CONFIG.init_db_on_startup_source}"
    )
    print(
        "[ribsys-api] database bootstrap config: "
        f"target={describe_database_target(CONFIG)}, "
        f"initOnStartup={CONFIG.init_db_on_startup}, "
        f"initSql={CONFIG.db_init_sql_file}"
    )

    return initialize_database_schema(CONFIG)


DB_BOOTSTRAP = _initialize_database_bootstrap()
APP_CONTEXT = AppContext(CONFIG)


def read_session_token(headers) -> str | None:
    return headers.get("X-Session-Token") or headers.get("X-Mock-Session")


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "RibSysPython/0.1"

    def log_message(self, format: str, *args) -> None:
        print(f"[ribsys-api] {self.address_string()} - {format % args}")

    def _write_json(self, status: int, payload: Any) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Accept, Content-Type, X-Session-Token, X-Mock-Session",
        )
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _write_empty(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Accept, Content-Type, X-Session-Token, X-Mock-Session",
        )
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.end_headers()

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        if content_length > 1024 * 1024:
            raise AppError(413, "请求体过大", "PAYLOAD_TOO_LARGE")

        raw = self.rfile.read(content_length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise AppError(400, "请求体不是合法 JSON", "INVALID_JSON") from exc

    def _read_upload_body(self, current_user: dict[str, Any]) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("application/json"):
            return APP_CONTEXT.create_upload_object(current_user, self._read_json_body())

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise AppError(400, "上传文件不能为空", "VALIDATION_FAILED")
        if content_length > 10 * 1024 * 1024:
            raise AppError(413, "上传文件过大", "PAYLOAD_TOO_LARGE")

        bucket = "misc"
        filename = "upload.bin"
        file_content_type = self.headers.get("X-Upload-Content-Type")
        raw = b""

        if content_type.startswith("multipart/form-data"):
            import cgi

            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": content_type,
                    "CONTENT_LENGTH": str(content_length),
                },
            )
            bucket_field = form["bucket"] if "bucket" in form else None
            if bucket_field is not None and not bucket_field.filename:
                bucket = str(bucket_field.value or "misc")
            file_field = form["file"] if "file" in form else None
            if file_field is None or not file_field.filename:
                raise AppError(400, "multipart 请求需要包含 file 字段", "VALIDATION_FAILED")
            filename = Path(file_field.filename).name or filename
            file_content_type = file_field.type or file_content_type
            raw = file_field.file.read()
        else:
            bucket = self.headers.get("X-Upload-Bucket") or "misc"
            filename = self.headers.get("X-Upload-Filename") or filename
            filename = Path(filename).name
            raw = self.rfile.read(content_length)

        if not raw:
            raise AppError(400, "上传文件不能为空", "VALIDATION_FAILED")
        if bucket not in ALLOWED_UPLOAD_BUCKETS:
            raise AppError(400, "bucket 不在允许范围内", "VALIDATION_FAILED")

        suffix = Path(filename).suffix
        if not file_content_type:
            file_content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        safe_user_id = re.sub(r"[^A-Za-z0-9_.-]", "_", current_user["id"])
        object_key = f"{safe_user_id}/{secrets.token_hex(12)}{suffix}"
        target_path = UPLOAD_ROOT / bucket / object_key
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(raw)
        url = "/uploads/" + "/".join([bucket, *object_key.split("/")])

        return APP_CONTEXT.create_uploaded_file_object(
            current_user,
            bucket=bucket,
            object_key=object_key,
            url=url,
            content_type=file_content_type,
            size_bytes=len(raw),
        )

    def _require_user(self) -> dict[str, Any]:
        session_token = read_session_token(self.headers)
        user = APP_CONTEXT.read_user_from_session(session_token)
        if user is None:
            raise AppError(401, "请先登录", "UNAUTHORIZED")
        return user

    def _client_ip(self) -> str | None:
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0] if self.client_address else None

    def do_OPTIONS(self) -> None:
        self._write_empty(HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def do_PATCH(self) -> None:
        self._dispatch()

    def do_DELETE(self) -> None:
        self._dispatch()

    def _dispatch(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        try:
            if self.command == "GET" and path == "/":
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "service": "RibSys API",
                        "message": "这是后端 API 服务，请访问 /api/* 接口。",
                        "health": "/api/health",
                    },
                )
                return

            if self.command == "GET" and path == "/favicon.ico":
                self._write_empty(HTTPStatus.NO_CONTENT)
                return

            if path == "/api/auth/login" and self.command != "POST":
                raise AppError(
                    405,
                    "登录接口只支持 POST，请用 JSON 提交 account 和 password。",
                    "METHOD_NOT_ALLOWED",
                    {"allowedMethods": ["POST"]},
                )

            if self.command == "GET" and path == "/api/health":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.health(),
                )
                return

            if self.command == "POST" and path == "/api/auth/login":
                payload = self._read_json_body()
                result = APP_CONTEXT.login(
                    payload,
                    created_ip=self._client_ip(),
                    user_agent=self.headers.get("User-Agent"),
                )
                self._write_json(HTTPStatus.OK, result)
                return

            if self.command == "POST" and path == "/api/auth/register":
                payload = self._read_json_body()
                result = APP_CONTEXT.register_user(payload)
                self._write_json(HTTPStatus.OK, result)
                return

            if self.command == "POST" and path == "/api/auth/logout":
                session_token = read_session_token(self.headers)
                result = APP_CONTEXT.logout(session_token)
                self._write_json(HTTPStatus.OK, result)
                return

            if self.command == "GET" and path == "/api/app/bootstrap":
                current_user = self._require_user()
                result = APP_CONTEXT.build_bootstrap(current_user)
                self._write_json(HTTPStatus.OK, result)
                return

            if self.command == "GET" and path == "/api/app/me/records":
                self._write_json(HTTPStatus.OK, APP_CONTEXT.list_my_records(self._require_user()))
                return

            if self.command == "GET" and path == "/api/app/groups":
                self._write_json(HTTPStatus.OK, APP_CONTEXT.build_groups(self._require_user()))
                return

            match = re.fullmatch(r"/api/app/groups/([^/]+)/home", path)
            if self.command == "GET" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.build_group_home(match.group(1), self._require_user()),
                )
                return

            match = re.fullmatch(r"/api/app/groups/([^/]+)/group-buys", path)
            if self.command == "GET" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.build_group_buys(
                        match.group(1),
                        self._require_user(),
                        {
                            "status": query.get("status", [None])[0],
                            "keyword": query.get("keyword", [None])[0],
                        },
                    ),
                )
                return

            match = re.fullmatch(r"/api/app/groups/([^/]+)/admin-capabilities", path)
            if self.command == "GET" and match:
                result = APP_CONTEXT.build_admin_capabilities(match.group(1), self._require_user())
                if not any(module["enabled"] for module in result["modules"]):
                    raise AppError(403, "你当前是普通成员，暂时不能进入管理台", "FORBIDDEN")
                self._write_json(HTTPStatus.OK, result)
                return

            match = re.fullmatch(r"/api/app/group-buys/([^/]+)/detail", path)
            if self.command == "GET" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.build_group_buy_detail(match.group(1), self._require_user()),
                )
                return

            if self.command == "POST" and path == "/api/group-buy-records":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.claim_group_buy_item(self._require_user(), self._read_json_body()),
                )
                return

            if self.command == "POST" and path == "/api/group-buys":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.create_group_buy(self._require_user(), self._read_json_body()),
                )
                return

            match = re.fullmatch(r"/api/group-buys/([^/]+)", path)
            if self.command == "PATCH" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.update_group_buy(
                        self._require_user(),
                        match.group(1),
                        self._read_json_body(),
                    ),
                )
                return

            match = re.fullmatch(r"/api/group-buys/([^/]+)/status", path)
            if self.command == "POST" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.change_group_buy_status(
                        self._require_user(),
                        match.group(1),
                        self._read_json_body(),
                    ),
                )
                return

            if self.command == "POST" and path == "/api/group-buy-items":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.create_group_buy_item(self._require_user(), self._read_json_body()),
                )
                return

            match = re.fullmatch(r"/api/group-buy-items/([^/]+)", path)
            if self.command == "PATCH" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.update_group_buy_item(
                        self._require_user(),
                        match.group(1),
                        self._read_json_body(),
                    ),
                )
                return

            match = re.fullmatch(r"/api/group-buy-items/([^/]+)", path)
            if self.command == "DELETE" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.delete_group_buy_item(
                        self._require_user(),
                        match.group(1),
                    ),
                )
                return

            if self.command == "POST" and path == "/api/group-buy-items/release-stock":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.release_group_buy_item_stock(
                        self._require_user(),
                        self._read_json_body(),
                    ),
                )
                return

            if self.command == "POST" and path == "/api/price-adjustments":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.request_price_adjustment(
                        self._require_user(),
                        self._read_json_body(),
                    ),
                )
                return

            if self.command == "POST" and path == "/api/order-screenshots":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.add_order_screenshot(self._require_user(), self._read_json_body()),
                )
                return

            if self.command == "POST" and path == "/api/group-buy-records/mark-ordered":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.mark_records_ordered(self._require_user(), self._read_json_body()),
                )
                return

            if self.command == "POST" and path == "/api/international-batches":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.create_international_batch(self._require_user(), self._read_json_body()),
                )
                return

            match = re.fullmatch(r"/api/international-batches/([^/]+)/records", path)
            if self.command == "POST" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.add_records_to_international_batch(
                        self._require_user(),
                        match.group(1),
                        self._read_json_body(),
                    ),
                )
                return

            match = re.fullmatch(r"/api/international-batches/([^/]+)/shipping", path)
            if self.command == "PATCH" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.update_international_batch_shipping(
                        self._require_user(),
                        match.group(1),
                        self._read_json_body(),
                    ),
                )
                return

            match = re.fullmatch(r"/api/international-batches/([^/]+)/arrive-domestic", path)
            if self.command == "POST" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.record_international_batch_arrived_domestic(
                        self._require_user(),
                        match.group(1),
                        self._read_json_body(),
                    ),
                )
                return

            match = re.fullmatch(r"/api/international-batches/([^/]+)/fees", path)
            if self.command == "POST" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.record_international_batch_fees(
                        self._require_user(),
                        match.group(1),
                        self._read_json_body(),
                    ),
                )
                return

            if self.command == "POST" and path == "/api/file-objects":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.create_upload_object(self._require_user(), self._read_json_body()),
                )
                return

            if self.command == "POST" and path == "/api/file-uploads":
                current_user = self._require_user()
                self._write_json(HTTPStatus.OK, self._read_upload_body(current_user))
                return

            match = re.fullmatch(r"/api/file-objects/([^/]+)/void", path)
            if self.command == "POST" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.void_file_object(
                        self._require_user(),
                        match.group(1),
                        self._read_json_body(),
                    ),
                )
                return

            if self.command == "GET" and path == "/api/audit-logs":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.list_audit_logs(
                        self._require_user(),
                        {
                            "objectType": query.get("object_type", [None])[0],
                            "objectId": query.get("object_id", [None])[0],
                            "actorUserId": query.get("actor_user_id", [None])[0],
                            "action": query.get("action", [None])[0],
                            "createdFrom": query.get("created_from", [None])[0],
                            "createdTo": query.get("created_to", [None])[0],
                            "page": query.get("page", [None])[0],
                            "pageSize": query.get("page_size", [None])[0],
                        },
                    ),
                )
                return

            if self.command == "GET" and path == "/api/goods":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.search_goods(
                        self._require_user(),
                        {
                            "keyword": query.get("keyword", [None])[0],
                            "seriesName": query.get("series_name", [None])[0]
                            or query.get("seriesName", [None])[0],
                            "alias": query.get("alias", [None])[0],
                            "characterName": query.get("character_name", [None])[0]
                            or query.get("characterName", [None])[0],
                            "status": query.get("status", [None])[0],
                            "page": query.get("page", [None])[0],
                            "pageSize": query.get("page_size", [None])[0]
                            or query.get("pageSize", [None])[0],
                        },
                    ),
                )
                return

            if self.command == "POST" and path == "/api/goods":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.create_goods(self._require_user(), self._read_json_body()),
                )
                return

            match = re.fullmatch(r"/api/goods/([^/]+)", path)
            if self.command == "PATCH" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.update_goods(
                        self._require_user(),
                        match.group(1),
                        self._read_json_body(),
                    ),
                )
                return

            match = re.fullmatch(r"/api/goods/([^/]+)/images", path)
            if self.command == "POST" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.add_goods_image(
                        self._require_user(),
                        match.group(1),
                        self._read_json_body(),
                    ),
                )
                return

            match = re.fullmatch(r"/api/goods/([^/]+)/images/([^/]+)/primary", path)
            if self.command == "POST" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.set_primary_goods_image(
                        self._require_user(),
                        match.group(1),
                        match.group(2),
                    ),
                )
                return

            match = re.fullmatch(r"/api/goods/([^/]+)/snapshot", path)
            if self.command == "GET" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.get_goods_snapshot(self._require_user(), match.group(1)),
                )
                return

            if self.command == "GET" and path == "/api/me":
                current_user = self._require_user()
                result = APP_CONTEXT.read_me(current_user)
                self._write_json(HTTPStatus.OK, result)
                return

            if self.command == "PATCH" and path == "/api/me":
                current_user = self._require_user()
                payload = self._read_json_body()
                result = APP_CONTEXT.update_me(current_user, payload)
                self._write_json(HTTPStatus.OK, result)
                return

            if self.command == "GET" and path == "/api/my/charges":
                self._write_json(HTTPStatus.OK, APP_CONTEXT.list_my_charges(self._require_user()))
                return

            match = re.fullmatch(r"/api/charges/([^/]+)/payment-proofs", path)
            if self.command == "POST" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.submit_charge_payment_proof(
                        self._require_user(),
                        match.group(1),
                        self._read_json_body(),
                    ),
                )
                return

            if self.command == "GET" and path == "/api/payment-channels":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.list_payment_channels(self._require_user()),
                )
                return

            if self.command == "POST" and path == "/api/payment-channels":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.create_payment_channel(self._require_user(), self._read_json_body()),
                )
                return

            if self.command == "GET" and path == "/api/my/dispatchable-items":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.list_dispatchable_items(
                        self._require_user(),
                        {
                            "memberUserId": query.get("member_user_id", [None])[0]
                            or query.get("memberUserId", [None])[0],
                            "warehouseUserId": query.get("warehouse_user_id", [None])[0]
                            or query.get("warehouseUserId", [None])[0],
                            "page": query.get("page", [None])[0],
                            "pageSize": query.get("page_size", [None])[0]
                            or query.get("pageSize", [None])[0],
                        },
                    ),
                )
                return

            if self.command == "GET" and path == "/api/dispatch-requests":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.list_dispatch_requests(self._require_user()),
                )
                return

            if self.command == "POST" and path == "/api/dispatch-requests":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.create_dispatch_request(self._require_user(), self._read_json_body()),
                )
                return

            if self.command == "GET" and path == "/api/transfers":
                self._write_json(HTTPStatus.OK, APP_CONTEXT.list_transfers(self._require_user()))
                return

            if self.command == "POST" and path == "/api/transfers":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.request_transfer(self._require_user(), self._read_json_body()),
                )
                return

            match = re.fullmatch(r"/api/transfers/([^/]+)/approve", path)
            if self.command == "POST" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.approve_transfer(
                        self._require_user(),
                        match.group(1),
                        self._read_json_body(),
                    ),
                )
                return

            match = re.fullmatch(r"/api/transfers/([^/]+)/reject", path)
            if self.command == "POST" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.reject_transfer(
                        self._require_user(),
                        match.group(1),
                        self._read_json_body(),
                    ),
                )
                return

            if self.command == "GET" and path == "/api/exceptions":
                self._write_json(HTTPStatus.OK, APP_CONTEXT.list_exceptions(self._require_user()))
                return

            if self.command == "GET" and path == "/api/users":
                self._write_json(HTTPStatus.OK, APP_CONTEXT.list_users(self._require_user()))
                return

            match = re.fullmatch(r"/api/users/([^/]+)", path)
            if self.command == "PATCH" and match:
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.update_user(
                        self._require_user(),
                        match.group(1),
                        self._read_json_body(),
                    ),
                )
                return

            if self.command == "GET" and path == "/api/me/addresses":
                self._write_json(HTTPStatus.OK, APP_CONTEXT.list_my_addresses(self._require_user()))
                return

            if self.command == "POST" and path == "/api/me/addresses":
                self._write_json(
                    HTTPStatus.OK,
                    APP_CONTEXT.create_my_address(self._require_user(), self._read_json_body()),
                )
                return

            raise AppError(404, "接口不存在", "NOT_FOUND")
        except AppError as exc:
            self._write_json(
                exc.status,
                {"code": exc.code, "message": str(exc), "details": exc.details},
            )
        except Exception as exc:  # pragma: no cover - fallback safety
            print("[ribsys-api] unexpected error", exc)
            import traceback

            traceback.print_exc()
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"code": "INTERNAL_ERROR", "message": "服务内部错误"},
            )


def main() -> None:
    server = ThreadingHTTPServer((CONFIG.host, CONFIG.port), ApiHandler)
    server.daemon_threads = True

    print(f"[ribsys-api] listening on http://{CONFIG.host}:{CONFIG.port}")
    print(f"[ribsys-api] data backend: {APP_CONTEXT.startup_info['dataBackend']}")
    suffix = DB_BOOTSTRAP.checksum[:12] if DB_BOOTSTRAP.checksum else "-"
    print(
        f"[ribsys-api] database bootstrap: {DB_BOOTSTRAP.reason} "
        f"(applied={DB_BOOTSTRAP.applied}, checksum={suffix})"
    )
    print(
        "[ribsys-api] identity bootstrap: "
        f"seededAdmin={APP_CONTEXT.identity_bootstrap['seededAdmin']}, "
        f"seededDemoUsers={APP_CONTEXT.identity_bootstrap['seededDemoUsers']}"
    )
    print(
        "[ribsys-api] seed accounts: member / maintainer / stock / admin "
        "(default password 123456 unless overridden by env)."
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        print("[ribsys-api] shutting down...")
        server.server_close()


if __name__ == "__main__":
    main()
