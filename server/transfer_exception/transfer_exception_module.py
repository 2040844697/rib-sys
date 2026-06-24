from __future__ import annotations

from typing import Any, Callable

from ..config import Config
from .record_exceptions import RecordExceptionWorkflow
from .transfer_exception_repo import TransferExceptionRepository
from .transfer_requests import TransferRequestWorkflow


class TransferExceptionModule:
    def __init__(
        self,
        config: Config,
        *,
        repository: TransferExceptionRepository | None = None,
        audit_service: Any | None = None,
        group_buy_records: Any | None = None,
        create_charge_adjustment: Callable[[Any, str, dict[str, Any]], dict[str, Any]] | None = None,
        get_user_snapshot_by_id: Callable[[str], dict[str, Any] | None],
        has_permission_by_user_id: Callable[[str, str], bool],
        has_group_access_by_user_id: Callable[[str, str], bool],
    ):
        # 模块只负责装配 DB workflow，外部接口保持原来的五个方法。
        repo = repository or TransferExceptionRepository(config)
        self.transfer_requests = TransferRequestWorkflow(
            config,
            repository=repo,
            audit_service=audit_service,
            group_buy_records=group_buy_records,
            has_permission_by_user_id=has_permission_by_user_id,
            get_user_snapshot_by_id=get_user_snapshot_by_id,
            has_group_access_by_user_id=has_group_access_by_user_id,
        )
        self.record_exceptions = RecordExceptionWorkflow(
            config,
            repository=repo,
            audit_service=audit_service,
            group_buy_records=group_buy_records,
            has_permission_by_user_id=has_permission_by_user_id,
            create_charge_adjustment=create_charge_adjustment,
        )

    def request_transfer(self, actor_user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        # 对外保持转单申请入口不变。
        return self.transfer_requests.request_transfer(actor_user, payload)

    def approve_transfer(
        self,
        actor_user_id: str,
        transfer_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 对外保持转单通过入口不变。
        return self.transfer_requests.approve_transfer(actor_user_id, transfer_id, payload)

    def reject_transfer(
        self,
        actor_user_id: str,
        transfer_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 对外保持转单驳回入口不变。
        return self.transfer_requests.reject_transfer(actor_user_id, transfer_id, payload)

    def mark_record_exception(
        self,
        actor_user_id: str,
        group_buy_record_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 对外保持异常标记入口不变。
        return self.record_exceptions.mark_record_exception(actor_user_id, group_buy_record_id, payload)

    def resolve_record_exception(
        self,
        actor_user_id: str,
        group_buy_record_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        # 对外保持异常解决入口不变。
        return self.record_exceptions.resolve_record_exception(actor_user_id, group_buy_record_id, payload)
