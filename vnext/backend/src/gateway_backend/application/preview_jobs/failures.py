"""Preview job failure, ruleset mismatch, and cancellation publication."""

from __future__ import annotations

import dataclasses

from collections.abc import (
    Callable,
    Mapping,
)
from datetime import datetime
from gateway_backend.application.job_steps import (
    make_cancelled_terminal_builder,
    publish_stopped_compute_cancelled as publish_stopped_compute_cancelled_step,
    terminal_step,
    with_resource_failure_terminal,
)
from gateway_backend.application.workspace.ports import (
    WorkspaceControlTransaction as PreviewControlTransaction,
)
from gateway_backend.capabilities.table_rules import (
    comparison_rule_set,
    migrated_table_ruleset_snapshot,
)
from gateway_backend.capabilities.table_rules.contracts import ComparisonRuleSet
from gateway_backend.operations.contracts import (
    OperationDiagnostic,
    OperationDiagnosticDetail,
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

from gateway_backend.application.preview_jobs.checkpoint import (
    _MaterializedPreviewInputs,
    _active_preview_transaction,
    _materialized_preview_inputs_from_checkpoint,
    _release_preview_step_protection,
)
from gateway_backend.application.preview_jobs.payload import (
    PreviewJobError,
    PreviewJobPayload,
    PreviewRuntimeDependencies,
)


def _active_preview_ruleset() -> ComparisonRuleSet:
    return comparison_rule_set(migrated_table_ruleset_snapshot())


def _publish_preview_ruleset_mismatch_if_needed(
    *,
    payload: PreviewJobPayload,
    operation: OperationRecord,
    step: StepRecord,
    lease_session: LeaseSession,
    control: ExecutionControl,
) -> bool:
    active_rules = _active_preview_ruleset()
    if (
        active_rules.ruleset_digest is not None
        and active_rules.ruleset_digest.value == payload.comparison_ruleset_digest
    ):
        return False
    _publish_preview_ruleset_mismatch_failure(
        payload=payload,
        operation=operation,
        step=step,
        lease_session=lease_session,
        control=control,
    )
    return True


def _publish_preview_ruleset_mismatch_failure(
    *,
    payload: PreviewJobPayload,
    operation: OperationRecord,
    step: StepRecord,
    lease_session: LeaseSession,
    control: ExecutionControl,
) -> None:
    del payload

    def builder(
        current_operation: OperationRecord,
        current_step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_preview_transaction.get()
        if transaction is None:
            raise PreviewJobError("preview ruleset transaction is not bound")
        _release_preview_step_protection(
            transaction,
            operation_id=current_operation.operation_id,
            clear_operation_owner=True,
        )
        diagnostic = OperationDiagnostic(
            code="PREVIEW_RULESET_VERSION_MISMATCH",
            message="frozen comparison ruleset digest does not match runtime ruleset",
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


def _publish_preview_materialization_failure(
    *,
    operation: OperationRecord,
    step: StepRecord,
    lease_session: LeaseSessionPort,
    diagnostic_code: str,
    message: str,
    diagnostic_details: tuple[OperationDiagnosticDetail, ...] | None,
    diagnostic_omitted_count: int,
    control: ExecutionControl,
) -> None:
    def builder(
        current_operation: OperationRecord,
        current_step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_preview_transaction.get()
        if transaction is None:
            raise PreviewJobError("preview materialization transaction is not bound")
        _release_preview_step_protection(
            transaction,
            operation_id=current_operation.operation_id,
            clear_operation_owner=True,
        )
        diagnostic = OperationDiagnostic(
            code=diagnostic_code,
            message=message[:255],
            details=diagnostic_details,
            omitted_count=(diagnostic_omitted_count if diagnostic_details is not None else None),
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


def _restore_preview_inputs_or_publish_failure(
    job_state: Mapping[str, object],
    *,
    repository_id: str,
    deps: PreviewRuntimeDependencies,
    operation: OperationRecord,
    step: StepRecord,
    lease_session: LeaseSession,
    control: ExecutionControl,
) -> _MaterializedPreviewInputs | None:
    try:
        return _materialized_preview_inputs_from_checkpoint(
            job_state, deps.artifact_store, repository_id=repository_id, dependencies=deps
        )
    except PreviewJobError as exc:
        if exc.diagnostic_code is None:
            raise
        _publish_preview_materialization_failure(
            operation=operation,
            step=step,
            lease_session=lease_session,
            diagnostic_code=exc.diagnostic_code,
            message=str(exc),
            diagnostic_details=exc.diagnostic_details,
            diagnostic_omitted_count=exc.diagnostic_omitted_count,
            control=control,
        )
        return None


def _publish_preview_resource_failure(
    operation: OperationRecord,
    step: StepRecord,
    control: ExecutionControl,
    lease_session: LeaseSessionPort,
    error: MemoryError,
) -> None:
    _publish_preview_materialization_failure(
        operation=operation,
        step=step,
        lease_session=lease_session,
        diagnostic_code="RESOURCE_LIMIT_EXCEEDED",
        message=str(error) or "operation memory budget exceeded",
        diagnostic_details=None,
        diagnostic_omitted_count=0,
        control=control,
    )


def _with_resource_failure_terminal(handler: ClaimedExecutor) -> ClaimedExecutor:
    return with_resource_failure_terminal(
        handler,
        on_memory_error=_publish_preview_resource_failure,
    )


def publish_stopped_compute_cancelled(lease_session: LeaseSessionPort) -> ExecutorAcknowledgment:
    return publish_stopped_compute_cancelled_step(lease_session, _make_cancelled_terminal_builder)


def _release_cancelled_preview_protection(
    transaction: PreviewControlTransaction, operation: OperationRecord
) -> None:
    _release_preview_step_protection(
        transaction,
        operation_id=operation.operation_id,
        clear_operation_owner=True,
    )


def _make_cancelled_terminal_builder() -> Callable[
    [OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]
]:
    return make_cancelled_terminal_builder(
        active_transaction=_active_preview_transaction.get,
        transaction_missing=lambda: PreviewJobError(
            "preview cancellation transaction is not bound"
        ),
        release_protection=_release_cancelled_preview_protection,
    )


__all__ = [
    "publish_stopped_compute_cancelled",
]
