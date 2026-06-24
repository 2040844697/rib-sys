from __future__ import annotations

from typing import Any

from .transfer_inputs import clone


TRANSFER_STATUS_PENDING = "pending"
TRANSFER_STATUS_APPROVED = "approved"
TRANSFER_STATUS_REJECTED = "rejected"
ALLOWED_TRANSFER_STATUSES = {
    TRANSFER_STATUS_PENDING,
    TRANSFER_STATUS_APPROVED,
    TRANSFER_STATUS_REJECTED,
}


def ensure_transfer_exception_state(state: dict[str, Any]) -> bool:
    changed = False

    counters = state.setdefault("counters", {})
    transfers = state.setdefault("transfers", [])
    transfer_items = state.setdefault("transferItems", [])

    counter_defaults = {
        "transfer": len(transfers),
        "transferItem": len(transfer_items),
    }
    for counter_key, counter_value in counter_defaults.items():
        if counter_key not in counters:
            counters[counter_key] = counter_value
            changed = True

    for transfer in transfers:
        defaults = {
            "approvedBy": None,
            "approvedAt": None,
            "rejectedBy": None,
            "rejectedAt": None,
            "rejectReason": None,
            "note": None,
            "status": TRANSFER_STATUS_PENDING,
            "updatedAt": transfer.get("createdAt"),
        }
        for key, value in defaults.items():
            if key not in transfer:
                transfer[key] = clone(value)
                changed = True
        if transfer.get("status") not in ALLOWED_TRANSFER_STATUSES:
            transfer["status"] = TRANSFER_STATUS_PENDING
            changed = True

    for item in transfer_items:
        defaults = {
            "createdAt": None,
        }
        for key, value in defaults.items():
            if key not in item:
                item[key] = clone(value)
                changed = True

    return changed
