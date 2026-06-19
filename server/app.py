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

    from server.config import load_config
    from server.errors import AppError
    from server.store import create_store
else:
    from .config import load_config
    from .errors import AppError
    from .store import create_store


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG = load_config(ROOT_DIR)
STORE = create_store(CONFIG)


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
        user = STORE.get_user_by_session_token(read_session_token(self.headers))
        if user is None:
            raise AppError(401, "请先登录", "UNAUTHORIZED")
        return user

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
                self._write_json(HTTPStatus.OK, STORE.get_health())
                return

            if self.command == "POST" and path == "/api/auth/login":
                self._write_json(HTTPStatus.OK, STORE.login(self._read_json_body()))
                return

            if self.command == "POST" and path == "/api/auth/register":
                self._write_json(HTTPStatus.OK, STORE.register_user(self._read_json_body()))
                return

            if self.command == "POST" and path == "/api/auth/logout":
                self._write_json(HTTPStatus.OK, STORE.logout(read_session_token(self.headers)))
                return

            if self.command == "GET" and path == "/api/app/bootstrap":
                self._write_json(HTTPStatus.OK, STORE.build_bootstrap(self._require_user()))
                return

            if self.command == "GET" and path == "/api/app/groups":
                self._write_json(HTTPStatus.OK, STORE.build_groups(self._require_user()))
                return

            match = re.fullmatch(r"/api/app/groups/([^/]+)/home", path)
            if self.command == "GET" and match:
                self._write_json(
                    HTTPStatus.OK,
                    STORE.build_group_home(match.group(1), self._require_user()),
                )
                return

            match = re.fullmatch(r"/api/app/groups/([^/]+)/group-buys", path)
            if self.command == "GET" and match:
                self._write_json(
                    HTTPStatus.OK,
                    STORE.build_group_buys(
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
                result = STORE.build_admin_capabilities(match.group(1), self._require_user())
                if not any(module["enabled"] for module in result["modules"]):
                    raise AppError(403, "你当前是普通成员，暂时不能进入管理台", "FORBIDDEN")
                self._write_json(HTTPStatus.OK, result)
                return

            match = re.fullmatch(r"/api/app/group-buys/([^/]+)/detail", path)
            if self.command == "GET" and match:
                self._write_json(
                    HTTPStatus.OK,
                    STORE.build_group_buy_detail(match.group(1), self._require_user()),
                )
                return

            if self.command == "POST" and path == "/api/group-buy-records":
                self._write_json(
                    HTTPStatus.OK,
                    STORE.claim_group_buy_item(self._require_user(), self._read_json_body()),
                )
                return

            if self.command == "POST" and path == "/api/group-buys":
                self._write_json(
                    HTTPStatus.OK,
                    STORE.create_group_buy(self._require_user(), self._read_json_body()),
                )
                return

            if self.command == "GET" and path == "/api/me":
                self._write_json(HTTPStatus.OK, STORE.read_me(self._require_user()))
                return

            if self.command == "PATCH" and path == "/api/me":
                self._write_json(
                    HTTPStatus.OK,
                    STORE.update_me(self._require_user(), self._read_json_body()),
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
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"code": "INTERNAL_ERROR", "message": "服务内部错误"},
            )


def main() -> None:
    server = ThreadingHTTPServer((CONFIG.host, CONFIG.port), ApiHandler)
    server.daemon_threads = True

    print(f"[ribsys-api] listening on http://{CONFIG.host}:{CONFIG.port}")
    print(f"[ribsys-api] data file: {CONFIG.data_file}")
    if STORE.startup_info["createdFreshData"]:
        print("[ribsys-api] first start detected, seed data has been written.")
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
