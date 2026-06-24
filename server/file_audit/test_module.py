from __future__ import annotations

import unittest
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from unittest.mock import patch

from server.errors import AppError
from server.file_audit import DatabaseAuditService, DatabaseFileService


@dataclass
class DummyConfig:
    database_url: str = "postgresql://unit-test"


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.queries.append((sql, params))
        normalized = " ".join(sql.split()).lower()
        params = params or []

        if "insert into file_objects" in normalized:
            file_object = {
                "id": params[0],
                "bucket": params[1],
                "object_key": params[2],
                "url": params[3],
                "content_type": params[4],
                "size_bytes": params[5],
                "uploaded_by": params[6],
                "status": params[7],
                "created_at": self.conn.now,
                "updated_at": self.conn.now,
            }
            self.conn.file_objects[file_object["id"]] = file_object
            self._result = file_object
            return

        if "insert into audit_logs" in normalized:
            audit_log = {
                "id": params[0],
                "actor_user_id": params[1],
                "action": params[2],
                "object_type": params[3],
                "object_id": params[4],
                "before_json": params[5],
                "after_json": params[6],
                "reason": params[7],
                "created_at": self.conn.now,
            }
            self.conn.audit_logs.insert(0, audit_log)
            self._result = audit_log
            return

        if "select count(*) as total from audit_logs" in normalized:
            self._result = {"total": len(self.conn.audit_logs)}
            return

        if "select * from audit_logs" in normalized:
            self._result = list(self.conn.audit_logs)
            return

        if "select * from file_objects" in normalized:
            self._result = self.conn.file_objects.get(params[0])
            return

        if "update file_objects" in normalized:
            file_object = self.conn.file_objects[params[1]]
            file_object = {
                **file_object,
                "status": params[0],
                "updated_at": self.conn.now,
            }
            self.conn.file_objects[params[1]] = file_object
            self._result = file_object
            return

        raise AssertionError(f"Unexpected SQL: {sql}")

    def fetchone(self):
        if isinstance(self._result, list):
            return self._result[0] if self._result else None
        return self._result

    def fetchall(self):
        if isinstance(self._result, list):
            return self._result
        return [] if self._result is None else [self._result]


class FakeConnection:
    def __init__(self):
        self.now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
        self.file_objects = {}
        self.audit_logs = []
        self.queries = []
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, row_factory=None):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class DatabaseFileAuditModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = FakeConnection()
        self.users = {
            "user_admin": {
                "id": "user_admin",
                "account": "admin",
                "displayName": "管理员莓莓",
                "qqNumber": "445566",
                "groupNickname": "莓莓",
                "roles": ["member", "admin"],
            }
        }
        self.audit_service = DatabaseAuditService(
            config=DummyConfig(),
            can_list_logs=lambda user: "admin" in user["roles"],
            get_user_snapshot_by_id=self.users.get,
        )
        self.file_service = DatabaseFileService(
            config=DummyConfig(),
            audit_service=self.audit_service,
            get_user_snapshot_by_id=self.users.get,
        )

    @contextmanager
    def patched_connect(self):
        with patch("server.file_audit.audit_logs.connect", return_value=self.conn), patch(
            "server.file_audit.file_objects.connect",
            return_value=self.conn,
        ):
            yield

    def test_create_upload_object_inserts_file_object_and_audit_log(self) -> None:
        with self.patched_connect():
            result = self.file_service.create_upload_object(
                uploaded_by="user_admin",
                bucket="orders",
                object_key="2026/06/demo.png",
                url="https://files.example.com/orders/2026/06/demo.png",
                content_type="image/png",
                size_bytes=2048,
            )

        self.assertTrue(self.conn.committed)
        self.assertEqual(result["fileObject"]["status"], "active")
        self.assertEqual(result["fileObject"]["uploadedByUser"]["id"], "user_admin")
        self.assertEqual(len(self.conn.file_objects), 1)
        self.assertEqual(self.conn.audit_logs[0]["action"], "file_object.create")
        self.assertTrue(
            any("INSERT INTO file_objects" in sql for sql, _ in self.conn.queries),
        )
        self.assertTrue(
            any("INSERT INTO audit_logs" in sql for sql, _ in self.conn.queries),
        )

    def test_create_upload_object_requires_existing_user(self) -> None:
        with self.patched_connect(), self.assertRaises(AppError) as context:
            self.file_service.create_upload_object(
                uploaded_by="missing_user",
                bucket="orders",
                object_key="demo.png",
                url="https://files.example.com/orders/demo.png",
            )

        self.assertEqual(context.exception.code, "NOT_FOUND")

    def test_void_file_object_updates_status_and_writes_audit(self) -> None:
        with self.patched_connect():
            created = self.file_service.create_upload_object(
                uploaded_by="user_admin",
                bucket="payments",
                object_key="proofs/a.png",
                url="https://files.example.com/payments/proofs/a.png",
            )
            self.conn.committed = False
            result = self.file_service.void_file_object(
                actor_user_id="user_admin",
                file_object_id=created["fileObjectId"],
                reason="凭证上传错了",
            )

        self.assertTrue(self.conn.committed)
        self.assertEqual(result["status"], "voided")
        self.assertEqual(self.conn.file_objects[created["fileObjectId"]]["status"], "voided")
        self.assertEqual(self.conn.audit_logs[0]["action"], "file_object.void")
        self.assertTrue(
            any("UPDATE file_objects" in sql for sql, _ in self.conn.queries),
        )

    def test_require_active_file_object_reads_database_row(self) -> None:
        with self.patched_connect():
            created = self.file_service.create_upload_object(
                uploaded_by="user_admin",
                bucket="misc",
                object_key="attachments/demo.txt",
                url="https://files.example.com/misc/attachments/demo.txt",
            )
            result = self.file_service.require_active_file_object(created["fileObjectId"])

        self.assertEqual(result["id"], created["fileObjectId"])
        self.assertEqual(result["uploadedByUser"]["id"], "user_admin")
        self.assertTrue(
            any("FROM file_objects" in sql for sql, _ in self.conn.queries),
        )

    def test_list_logs_queries_audit_logs_and_attaches_actor_user(self) -> None:
        with self.patched_connect():
            self.audit_service.log(
                actor_user_id="user_admin",
                action="custom.audit",
                object_type="demo",
                object_id="demo_1",
                before=None,
                after={"value": "x"},
                reason="测试",
            )
            result = self.audit_service.list_logs(
                self.users["user_admin"],
                {"action": "custom.audit", "page": "1", "pageSize": "10"},
            )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["actorUser"]["id"], "user_admin")
        self.assertEqual(result["items"][0]["after"], {"value": "x"})
        self.assertIsInstance(json.loads(self.conn.audit_logs[0]["after_json"]), dict)
        self.assertTrue(
            any("FROM audit_logs" in sql for sql, _ in self.conn.queries),
        )

    def test_member_cannot_list_audit_logs(self) -> None:
        member = {"id": "user_member", "roles": ["member"]}
        with self.patched_connect(), self.assertRaises(AppError) as context:
            self.audit_service.list_logs(member, {})

        self.assertEqual(context.exception.code, "FORBIDDEN")


if __name__ == "__main__":
    unittest.main()
