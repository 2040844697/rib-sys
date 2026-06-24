from __future__ import annotations

import json
import re
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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
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

            raise AppError(404, "接口不存在", "NOT_FOUND")
        except AppError as exc:
            self._write_json(
                exc.status,
                {"code": exc.code, "message": str(exc), "details": exc.details},
            )
        except Exception as exc:  # pragma: no cover - fallback safety
            print("[ribsys-api] unexpected error", exc)
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
