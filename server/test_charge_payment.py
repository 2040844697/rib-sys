from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from server.charge_payment.charge_payment_module import ChargePaymentModule
from server.charge_payment.charge_payment_repo import cent_to_cny, cny_to_cent
from server.errors import AppError


class FakeConnection:
    def __init__(self, repo):
        self.repo = repo
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        self.repo.connections.append(self)
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.rolled_back = True
        return False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakeAuditService:
    def __init__(self):
        self.records: list[dict[str, Any]] = []

    def log_in_connection(self, conn, **record):
        self.records.append(record)
        return record


class FakeFileService:
    def __init__(self):
        self.file_objects: dict[str, dict[str, Any]] = {}

    def require_active_file_object(self, file_object_id: str, conn=None) -> dict[str, Any]:
        if file_object_id not in self.file_objects:
            raise AppError(404, "file not found", "NOT_FOUND")
        return dict(self.file_objects[file_object_id])


class FakeChargePaymentRepository:
    def __init__(self):
        self.connections: list[FakeConnection] = []
        self.payment_channels: dict[str, dict[str, Any]] = {}
        self.charges: dict[str, dict[str, Any]] = {}
        self.payment_proofs: dict[str, dict[str, Any]] = {}
        self.allocations: list[dict[str, Any]] = []
        self.charge_adjustments: dict[str, dict[str, Any]] = {}
        self.group_buy_charge_links: dict[str, list[str]] = {}
        self.group_buy_payment_links: list[dict[str, Any]] = []
        self.next_ids: dict[str, int] = {}

    def next_id(self, prefix: str) -> str:
        self.next_ids[prefix] = self.next_ids.get(prefix, 0) + 1
        return f"{prefix}_{self.next_ids[prefix]}"

    def count_pending_charges_for_user(self, conn, payer_user_id: str) -> int:
        return sum(
            1
            for charge in self.charges.values()
            if charge["payerUserId"] == payer_user_id and charge["status"] == "pending"
        )

    def get_payment_channel_by_id(self, conn, payment_channel_id: str, *, lock: bool = False):
        return self.payment_channels.get(payment_channel_id)

    def get_charge_by_id(self, conn, charge_id: str, *, lock: bool = False):
        return self.charges.get(charge_id)

    def get_payment_proof_by_id(self, conn, proof_id: str, *, lock: bool = False):
        return self.payment_proofs.get(proof_id)

    def list_payment_proof_allocations(self, conn, proof_id: str):
        return [allocation for allocation in self.allocations if allocation["proofId"] == proof_id]

    def create_payment_channel(self, conn, fields):
        payment_channel = {
            "id": self.next_id("payment_channel"),
            "ownerUserId": fields["owner_user_id"],
            "type": fields["type"],
            "displayName": fields["display_name"],
            "qrFileObjectId": fields["qr_file_object_id"],
            "qrImageUrl": fields["qr_image_url"],
            "accountText": fields["account_text"],
            "note": fields["note"],
            "status": "active",
        }
        self.payment_channels[payment_channel["id"]] = payment_channel
        return payment_channel

    def create_charge(self, conn, fields):
        charge = {
            "id": self.next_id("charge"),
            "type": fields["type"],
            "payerUserId": fields["payer_user_id"],
            "payeeUserId": fields["payee_user_id"],
            "bizType": fields["biz_type"],
            "bizId": fields["biz_id"],
            "amountCny": fields["amount_cny"],
            "paymentChannelId": fields["payment_channel_id"],
            "snapshot": fields["snapshot"],
            "note": fields["note"],
            "status": "pending",
            "submittedProofId": None,
            "confirmedProofId": None,
            "cancelledReason": None,
        }
        self.charges[charge["id"]] = charge
        return charge

    def update_charge(self, conn, *, charge_id: str, updates):
        charge = self.charges[charge_id]
        for key, value in updates.items():
            if key == "submitted_proof_id":
                charge["submittedProofId"] = value
            elif key == "confirmed_proof_id":
                charge["confirmedProofId"] = value
            elif key == "cancelled_reason":
                charge["cancelledReason"] = value
            else:
                charge[key] = value
        return dict(charge)

    def create_payment_proof(self, conn, fields):
        proof = {
            "id": self.next_id("payment_proof"),
            "submittedBy": fields["submitted_by"],
            "fromUserId": fields["from_user_id"],
            "toUserId": fields["to_user_id"],
            "amountCny": fields["amount_cny"],
            "paidAt": fields["paid_at"],
            "proofFileObjectId": fields["proof_file_object_id"],
            "proofImageUrl": fields["proof_image_url"],
            "note": fields["note"],
            "status": "submitted",
            "reviewedBy": None,
            "reviewedAt": None,
            "reviewNote": None,
            "rejectReason": None,
        }
        self.payment_proofs[proof["id"]] = proof
        return proof

    def update_payment_proof(self, conn, *, proof_id: str, updates):
        proof = self.payment_proofs[proof_id]
        for key, value in updates.items():
            if key == "reviewed_by":
                proof["reviewedBy"] = value
            elif key == "reviewed_at":
                proof["reviewedAt"] = value
            elif key == "review_note":
                proof["reviewNote"] = value
            elif key == "reject_reason":
                proof["rejectReason"] = value
            else:
                proof[key] = value
        return dict(proof)

    def create_payment_proof_allocation(self, conn, *, proof_id, charge_id, allocated_amount_cny):
        allocation = {
            "id": self.next_id("payment_proof_allocation"),
            "proofId": proof_id,
            "chargeId": charge_id,
            "allocatedAmountCny": allocated_amount_cny,
        }
        self.allocations.append(allocation)
        return allocation

    def create_charge_adjustment(self, conn, fields):
        adjustment = {
            "id": self.next_id("charge_adjustment"),
            "chargeId": fields["charge_id"],
            "sourceChargeId": fields["source_charge_id"],
            "deltaCny": fields["delta_cny"],
            "reason": fields["reason"],
            "sourceType": fields["source_type"],
            "sourceId": fields["source_id"],
            "createdBy": fields["approved_by"],
        }
        self.charge_adjustments[adjustment["id"]] = adjustment
        return adjustment

    def list_group_buy_record_ids_by_charge(self, conn, charge_id: str) -> list[str]:
        return self.group_buy_charge_links.get(charge_id, [])

    def link_group_buy_record_payment_proof(self, conn, *, group_buy_record_id, payment_type, payment_proof_id):
        before = {"id": group_buy_record_id}
        after = {
            "id": group_buy_record_id,
            "paymentType": payment_type,
            "paymentProofId": payment_proof_id,
        }
        self.group_buy_payment_links.append(after)
        return before, after


@dataclass
class FakeConfig:
    database_url: str = "postgresql://example/db"


class ChargePaymentModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = FakeChargePaymentRepository()
        self.audit_service = FakeAuditService()
        self.file_service = FakeFileService()
        self.users = {
            "user_member": {"id": "user_member", "roles": ["member"]},
            "user_maintainer": {"id": "user_maintainer", "roles": ["group_buy_maintainer"]},
            "user_admin": {"id": "user_admin", "roles": ["admin"]},
        }
        self.module = ChargePaymentModule(
            FakeConfig(),
            repository=self.repo,
            audit_service=self.audit_service,
            file_service=self.file_service,
            has_permission_by_user_id=self.has_permission_by_user_id,
            get_user_snapshot_by_id=self.users.get,
        )
        self.connect_patch = patch(
            "server.charge_payment.charge_payment_module.connect",
            lambda config: FakeConnection(self.repo),
        )
        self.connect_patch.start()

    def tearDown(self) -> None:
        self.connect_patch.stop()

    def has_permission_by_user_id(self, user_id: str, permission: str) -> bool:
        user = self.users.get(user_id)
        if user is None:
            return False
        if "admin" in user["roles"]:
            return True
        return user_id == "user_maintainer" and permission in {
            "charge:adjust",
            "charge:confirm_payment",
        }

    def create_charge(self, amount_cny: str = "28.00", type_: str = "initial_goods") -> dict[str, Any]:
        return self.module.create_charge(
            {
                "type": type_,
                "payerUserId": "user_member",
                "payeeUserId": "user_admin",
                "bizType": "group_buy_record",
                "bizId": "record_1",
                "amountCny": amount_cny,
            },
            actor_user_id="user_maintainer",
        )

    def submit_proof(self, charge_id: str, amount_cny: str = "28.00") -> dict[str, Any]:
        self.file_service.file_objects["file_payment"] = {
            "id": "file_payment",
            "bucket": "payments",
            "url": "https://files.example.com/payments/proof.png",
        }
        return self.module.submit_payment_proof(
            {
                "submittedBy": "user_member",
                "fromUserId": "user_member",
                "toUserId": "user_admin",
                "amountCny": amount_cny,
                "paidAt": "2026-06-24T09:00:00+08:00",
                "proofFileObjectId": "file_payment",
                "proofImageUrl": "https://files.example.com/payments/proof.png",
                "allocations": [
                    {
                        "chargeId": charge_id,
                        "allocatedAmountCny": "28.00",
                    }
                ],
            }
        )

    def test_create_payment_channel(self) -> None:
        result = self.module.create_payment_channel(
            "user_maintainer",
            {
                "ownerUserId": "user_maintainer",
                "type": "qq",
                "displayName": "Maintainer QQ",
                "accountText": "223344",
            },
        )

        created = self.module.require_payment_channel(result["paymentChannelId"])
        self.assertEqual(created["status"], "active")
        self.assertEqual(self.audit_service.records[-1]["action"], "payment_channel.create")

    def test_payment_channel_file_must_be_channels_bucket(self) -> None:
        self.file_service.file_objects["file_wrong"] = {
            "id": "file_wrong",
            "bucket": "payments",
            "url": "https://files.example.com/wrong.png",
        }

        with self.assertRaises(AppError):
            self.module.create_payment_channel(
                "user_maintainer",
                {
                    "ownerUserId": "user_maintainer",
                    "type": "qq",
                    "displayName": "Maintainer QQ",
                    "qrFileObjectId": "file_wrong",
                },
            )

    def test_create_charge_and_cancel_pending_charge(self) -> None:
        result = self.create_charge()
        charge = self.module.require_charge(result["chargeId"])

        self.assertEqual(charge["status"], "pending")
        self.assertEqual(charge["amountCny"], "28.00")

        cancelled = self.module.cancel_charge(
            "user_maintainer",
            charge["id"],
            {"reason": "duplicate"},
        )
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.module.require_charge(charge["id"])["cancelledReason"], "duplicate")

    def test_submit_payment_proof(self) -> None:
        charge = self.create_charge()
        proof = self.submit_proof(charge["chargeId"])

        self.assertEqual(proof["status"], "submitted")
        self.assertEqual(self.module.require_charge(charge["chargeId"])["status"], "submitted")
        self.assertEqual(self.module.require_charge(charge["chargeId"])["submittedProofId"], proof["proofId"])
        self.assertTrue(any(connection.committed for connection in self.repo.connections))

    def test_payment_proof_file_must_be_payments_bucket(self) -> None:
        charge = self.create_charge()
        self.file_service.file_objects["file_channel"] = {
            "id": "file_channel",
            "bucket": "channels",
            "url": "https://files.example.com/channels/qr.png",
        }

        with self.assertRaises(AppError):
            self.module.submit_payment_proof(
                {
                    "submittedBy": "user_member",
                    "fromUserId": "user_member",
                    "toUserId": "user_admin",
                    "amountCny": "28.00",
                    "paidAt": "2026-06-24T09:00:00+08:00",
                    "proofFileObjectId": "file_channel",
                    "allocations": [
                        {
                            "chargeId": charge["chargeId"],
                            "allocatedAmountCny": "28.00",
                        }
                    ],
                }
            )

    def test_proof_amount_must_equal_allocation_total(self) -> None:
        charge = self.create_charge()
        self.file_service.file_objects["file_payment"] = {
            "id": "file_payment",
            "bucket": "payments",
            "url": "https://files.example.com/payments/proof.png",
        }

        with self.assertRaises(AppError):
            self.module.submit_payment_proof(
                {
                    "submittedBy": "user_member",
                    "fromUserId": "user_member",
                    "toUserId": "user_admin",
                    "amountCny": "29.00",
                    "paidAt": "2026-06-24T09:00:00+08:00",
                    "proofFileObjectId": "file_payment",
                    "allocations": [
                        {
                            "chargeId": charge["chargeId"],
                            "allocatedAmountCny": "28.00",
                        }
                    ],
                }
            )

    def test_confirm_payment_marks_charge_confirmed(self) -> None:
        charge = self.create_charge()
        self.repo.group_buy_charge_links[charge["chargeId"]] = ["record_1"]
        proof = self.submit_proof(charge["chargeId"])

        result = self.module.confirm_payment_proof(
            "user_maintainer",
            proof["proofId"],
            {"note": "matched"},
        )

        confirmed_charge = self.module.require_charge(charge["chargeId"])
        confirmed_proof = self.module.require_payment_proof(proof["proofId"])
        self.assertEqual(result["confirmedChargeIds"], [charge["chargeId"]])
        self.assertEqual(confirmed_charge["status"], "confirmed")
        self.assertEqual(confirmed_charge["confirmedProofId"], proof["proofId"])
        self.assertEqual(confirmed_proof["status"], "confirmed")
        self.assertEqual(confirmed_proof["reviewNote"], "matched")
        self.assertEqual(self.repo.group_buy_payment_links[0]["paymentProofId"], proof["proofId"])

    def test_reject_payment_restores_charge_pending(self) -> None:
        charge = self.create_charge()
        proof = self.submit_proof(charge["chargeId"])

        result = self.module.reject_payment_proof(
            "user_maintainer",
            proof["proofId"],
            {"rejectReason": "unclear"},
        )

        rejected_proof = self.module.require_payment_proof(proof["proofId"])
        reverted_charge = self.module.require_charge(charge["chargeId"])
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(rejected_proof["rejectReason"], "unclear")
        self.assertEqual(reverted_charge["status"], "pending")
        self.assertIsNone(reverted_charge["submittedProofId"])

    def test_create_charge_adjustment(self) -> None:
        charge = self.create_charge()
        result = self.module.create_charge_adjustment(
            "user_maintainer",
            {
                "chargeId": charge["chargeId"],
                "sourceChargeId": charge["chargeId"],
                "deltaCny": "-3.00",
                "reason": "manual correction",
                "sourceType": "manual_review",
                "sourceId": "review_1",
            },
        )

        adjustment = self.repo.charge_adjustments[result["chargeAdjustmentId"]]
        self.assertEqual(adjustment["deltaCny"], "-3.00")
        self.assertEqual(adjustment["createdBy"], "user_maintainer")

    def test_cny_decimal_amount_converts_to_cents(self) -> None:
        self.assertEqual(cny_to_cent("128.50"), 12850)
        self.assertEqual(cent_to_cny(12850), "128.50")
        self.assertEqual(cny_to_cent("-3.00"), -300)

    def test_audit_logs_written_to_database_service(self) -> None:
        self.create_charge()

        self.assertEqual(self.audit_service.records[-1]["action"], "charge.create")
        self.assertEqual(self.audit_service.records[-1]["object_type"], "charge")


if __name__ == "__main__":
    unittest.main()
