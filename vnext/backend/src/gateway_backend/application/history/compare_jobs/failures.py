"""History compare failure, ruleset mismatch, and cancellation publication."""

from __future__ import annotations

import dataclasses

from collections.abc import Callable
from datetime import datetime
from gateway_backend.application.history.contracts import (
    HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
    HistoryCompareDiagnosticCode,
)
from gateway_backend.application.history.ports import (
    HistoryControlTransaction as HistoryCompareControlTransaction,
)
from gateway_backend.application.job_steps import (
    make_cancelled_terminal_builder,
    publish_stopped_compute_cancelled as publish_stopped_compute_cancelled_step,
    terminal_step,
    with_resource_failure_terminal,
)
from gateway_backend.capabilities.table_rules import (
    comparison_rule_set,
    migrated_table_ruleset_snapshot,
)
from gateway_backend.capabilities.table_rules.contracts import ComparisonRuleSet
from gateway_backend.operations.contracts import (
    OperationDiagnostic,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession as LeaseSessionPort,
)

from gateway_backend.application.history.compare_jobs.checkpoint import (
    _active_history_compare_transaction,
    _release_history_compare_step_protection,
)
from gateway_backend.application.history.compare_jobs.payload import (
    HistoryCompareJobError,
    HistoryCompareJobPayload,
    HistoryCompareRulesetVersionMismatch,
)

def _assert_runtime_ruleset(payload: HistoryCompareJobPayload) -> ComparisonRuleSet:
    if payload.comparison_contract_version != HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION:
        raise HistoryCompareRulesetVersionMismatch(
            "frozen comparison contract does not match runtime"
        )
    active_rules = comparison_rule_set(migrated_table_ruleset_snapshot())
    digest = active_rules.ruleset_digest
    if digest is None:
        raise HistoryCompareRulesetVersionMismatch("runtime comparison ruleset digest is missing")
    if digest.value != payload.comparison_ruleset_digest:
        raise HistoryCompareRulesetVersionMismatch(
            "frozen comparison ruleset digest does not match runtime ruleset"
        )
    return active_rules

def _publish_ruleset_mismatch_failure(
    *,
    lease_session: LeaseSession,
    operation: OperationRecord,
    step: StepRecord,
    message: str,
    control: ExecutionControl,
) -> None:
    def builder(
        current_operation: OperationRecord,
        current_step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_history_compare_transaction.get()
        if transaction is None:
            raise HistoryCompareJobError("history compare ruleset transaction is not bound")
        _release_history_compare_step_protection(
            transaction, operation_id=current_operation.operation_id
        )
        diagnostic = OperationDiagnostic(
            code=HistoryCompareDiagnosticCode.HISTORY_RULESET_VERSION_MISMATCH.value,
            message=message[:255],
        )
        failed_step = terminal_step(
            current_step,
            transaction_now,
            status=StepStatus.FAILED,
            diagnostic=diagnostic,
        )
        terminal_operation = dataclasses.replace(
            current_operation,
            status=OperationStatus.FAILED,
            diagnostic=diagnostic,
            updated_at=transaction_now,
            completed_at=transaction_now,
            optimistic_version=current_operation.optimistic_version + 1,
        )
        return failed_step, terminal_operation

    lease_session.refresh_control()
    if control.cancel_requested:
        lease_session.publish_operation(_make_cancelled_terminal_builder())
        return
    lease_session.publish_operation(builder)

def _publish_commit_unavailable_failure(
    *,
    lease_session: LeaseSessionPort,
    operation: OperationRecord,
    step: StepRecord,
    message: str,
    diagnostic_code: str | None = None,
    control: ExecutionControl,
) -> None:
    def builder(
        current_operation: OperationRecord,
        current_step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_history_compare_transaction.get()
        if transaction is None:
            raise HistoryCompareJobError("history compare failure transaction is not bound")
        _release_history_compare_step_protection(
            transaction, operation_id=current_operation.operation_id
        )
        diagnostic = OperationDiagnostic(
            code=diagnostic_code or HistoryCompareDiagnosticCode.HISTORY_COMMIT_UNAVAILABLE.value,
            message=message[:255],
        )
        failed_step = terminal_step(
            current_step,
            transaction_now,
            status=StepStatus.FAILED,
            diagnostic=diagnostic,
        )
        terminal_operation = dataclasses.replace(
            current_operation,
            status=OperationStatus.FAILED,
            diagnostic=diagnostic,
            updated_at=transaction_now,
            completed_at=transaction_now,
            optimistic_version=current_operation.optimistic_version + 1,
        )
        return failed_step, terminal_operation

    lease_session.refresh_control()
    if control.cancel_requested:
        lease_session.publish_operation(_make_cancelled_terminal_builder())
        return
    lease_session.publish_operation(builder)

def _publish_history_compare_resource_failure(
    operation: OperationRecord,
    step: StepRecord,
    control: ExecutionControl,
    lease_session: LeaseSessionPort,
    error: MemoryError,
) -> None:
    _publish_commit_unavailable_failure(
        lease_session=lease_session,
        operation=operation,
        step=step,
        diagnostic_code="RESOURCE_LIMIT_EXCEEDED",
        message=str(error) or "operation memory budget exceeded",
        control=control,
    )

def _with_resource_failure_terminal(handler: ClaimedExecutor) -> ClaimedExecutor:
    return with_resource_failure_terminal(
        handler,
        on_memory_error=_publish_history_compare_resource_failure,
    )

def publish_stopped_compute_cancelled(lease_session: LeaseSessionPort) -> ExecutorAcknowledgment:
    return publish_stopped_compute_cancelled_step(lease_session, _make_cancelled_terminal_builder)

def _release_cancelled_history_compare_protection(
    transaction: HistoryCompareControlTransaction, operation: OperationRecord
) -> None:
    _release_history_compare_step_protection(transaction, operation_id=operation.operation_id)

def _make_cancelled_terminal_builder() -> Callable[
    [OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]
]:
    return make_cancelled_terminal_builder(
        active_transaction=_active_history_compare_transaction.get,
        transaction_missing=lambda: HistoryCompareJobError(
            "history compare cancellation transaction is not bound"
        ),
        release_protection=_release_cancelled_history_compare_protection,
    )


__all__ = [
    "publish_stopped_compute_cancelled",
]
