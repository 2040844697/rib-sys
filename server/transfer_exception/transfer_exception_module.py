from __future__ import annotations

from typing import Any, Callable

from .record_exceptions import RecordExceptionWorkflow
from .record_links import TransferRecordLinks
from .transfer_requests import TransferRequestWorkflow
from .transfer_state import ensure_transfer_exception_state


class TransferExceptionModule:
    def __init__(
        self,
        *,
        state: dict[str, Any],
        next_id: Callable[[str, str], str],
        audit_log: Callable[..., Any],
        now_iso: Callable[[], str],
        has_permission_by_user_id: Callable[[str, str], bool],
        get_user_snapshot_by_id: Callable[[str], dict[str, Any] | None],
        require_group_buy_record: Callable[[str], dict[str, Any]],
        refresh_record_status: Callable[[dict[str, Any]], dict[str, Any]],
        create_record_for_transfer: Callable[..., dict[str, Any]],
        create_charge_adjustment: Callable[[str, dict[str, Any]], dict[str, Any]],
    ):
        record_links = TransferRecordLinks(
            state=state,
            audit_log=audit_log,
            now_iso=now_iso,
            require_group_buy_record=require_group_buy_record,
            refresh_record_status=refresh_record_status,
            create_record_for_transfer=create_record_for_transfer,
        )
        self.transfer_requests = TransferRequestWorkflow(
            state=state,
            next_id=next_id,
            audit_log=audit_log,
            now_iso=now_iso,
            has_permission_by_user_id=has_permission_by_user_id,
            get_user_snapshot_by_id=get_user_snapshot_by_id,
            record_links=record_links,
        )
        self.record_exceptions = RecordExceptionWorkflow(
            audit_log=audit_log,
            now_iso=now_iso,
            has_permission_by_user_id=has_permission_by_user_id,
            require_group_buy_record=require_group_buy_record,
            refresh_record_status=refresh_record_status,
            create_charge_adjustment=create_charge_adjustment,
        )

    def request_transfer(self, actor_user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        return self.transfer_requests.request_transfer(actor_user, payload)

    def approve_transfer(
        self,
        actor_user_id: str,
        transfer_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.transfer_requests.approve_transfer(actor_user_id, transfer_id, payload)

    def reject_transfer(
        self,
        actor_user_id: str,
        transfer_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.transfer_requests.reject_transfer(actor_user_id, transfer_id, payload)

    def mark_record_exception(
        self,
        actor_user_id: str,
        group_buy_record_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.record_exceptions.mark_record_exception(actor_user_id, group_buy_record_id, payload)

    def resolve_record_exception(
        self,
        actor_user_id: str,
        group_buy_record_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.record_exceptions.resolve_record_exception(actor_user_id, group_buy_record_id, payload)
