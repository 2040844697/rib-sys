from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from server.config import load_config
from server.errors import AppError
from server.store import Store, create_initial_data


class FileAuditModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root_dir = Path(self.temp_dir.name)
        self.config = load_config(root_dir)
        self.state = create_initial_data(self.config)
        self.store = Store(self.config, self.state, False)
        self.admin = self.store.get_user_by_id("user_admin")
        self.member = self.store.get_user_by_id("user_member")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_upload_object_records_file_and_audit(self) -> None:
        result = self.store.create_upload_object(
            self.admin,
            {
                "bucket": "orders",
                "objectKey": "2026/06/demo.png",
                "url": "https://files.example.com/orders/2026/06/demo.png",
                "contentType": "image/png",
                "sizeBytes": 2048,
            },
        )

        self.assertEqual(result["fileObject"]["status"], "active")
        self.assertEqual(len(self.store.state["fileObjects"]), 1)
        self.assertEqual(self.store.state["auditLogs"][-1]["action"], "file_object.create")

    def test_void_file_object_writes_audit(self) -> None:
        created = self.store.create_upload_object(
            self.admin,
            {
                "bucket": "payments",
                "objectKey": "proofs/a.png",
                "url": "https://files.example.com/payments/proofs/a.png",
            },
        )

        result = self.store.void_file_object(
            self.admin,
            created["fileObjectId"],
            {"reason": "凭证上传错了"},
        )

        self.assertEqual(result["status"], "voided")
        self.assertEqual(self.store.state["auditLogs"][-1]["action"], "file_object.void")

    def test_duplicate_bucket_and_object_key_is_rejected(self) -> None:
        payload = {
            "bucket": "goods",
            "objectKey": "images/item-1.jpg",
            "url": "https://files.example.com/goods/images/item-1.jpg",
        }
        self.store.create_upload_object(self.admin, payload)

        with self.assertRaises(AppError) as context:
            self.store.create_upload_object(self.admin, copy.deepcopy(payload))

        self.assertEqual(context.exception.code, "DUPLICATED_OPERATION")

    def test_member_cannot_list_audit_logs(self) -> None:
        with self.assertRaises(AppError) as context:
            self.store.list_audit_logs(self.member, {})

        self.assertEqual(context.exception.code, "FORBIDDEN")

    def test_admin_can_filter_audit_logs(self) -> None:
        self.store.create_upload_object(
            self.admin,
            {
                "bucket": "misc",
                "objectKey": "attachments/demo.txt",
                "url": "https://files.example.com/misc/attachments/demo.txt",
            },
        )
        self.store.update_me(
            self.member,
            {"displayName": "成员A新", "groupNickname": "A新昵称"},
        )

        result = self.store.list_audit_logs(
            self.admin,
            {"action": "file_object.create", "page": "1", "pageSize": "10"},
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["action"], "file_object.create")

    def test_audit_snapshot_is_trimmed(self) -> None:
        large_after = {
            "description": "x" * 800,
            "items": list(range(30)),
            "nested": {"level1": {"level2": {"level3": {"level4": "too deep"}}}},
        }

        self.store.audit_service.log(
            actor_user_id=self.admin["id"],
            action="custom.audit",
            object_type="demo",
            object_id="demo_1",
            before=None,
            after=large_after,
            reason="测试裁剪",
        )

        audit_log = self.store.state["auditLogs"][-1]
        self.assertTrue(audit_log["after"]["description"].endswith("...[truncated]"))
        self.assertIn("more items", audit_log["after"]["items"][-1])
        self.assertEqual(
            audit_log["after"]["nested"]["level1"]["level2"]["level3"],
            "[truncated]",
        )


if __name__ == "__main__":
    unittest.main()
