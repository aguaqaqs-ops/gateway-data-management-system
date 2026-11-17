"""Submit job failure, abort, manual recovery, and cancellation publication."""

from __future__ import annotations

import dataclasses

from collections.abc import Callable
from datetime import datetime
from gateway_backend.application.checkpoints import CheckpointPublicationError
from gateway_backend.application.job_steps import (
    make_cancelled_terminal_builder,
    publish_stopped_compute_cancelled as publish_stopped_compute_cancelled_step,
    with_resource_failure_terminal,
)
from gateway_backend.application.recovery import DIAGNOSTIC_RECONCILE_TIMEOUT
from gateway_backend.application.submission.abort_transaction import (
    AbortPreparedSubmitRequest,
    abort_prepared_submit_in_control_transaction,
)
from gateway_backend.application.submission.errors import SubmitImportPublicationError
from gateway_backend.operations.contracts import (
    OperationDiagnostic,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)
from gateway_backend.operations.recovery import (
    DIAGNOSTIC_WAIT_UPPER_BOUND_EXCEEDED,
    RecoveryCapabilityValue,
    RecoveryPolicyOutcomeDisposition,
    transition_for_outcome,
)
from gateway_backend.operations.state import operator_recovery_session_active
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession,
    LeaseSession as LeaseSessionPort,
)

from gateway_backend.application.submit_jobs.checkpoint import _active_submit_transaction
from gateway_backend.application.submit_jobs.payload import (
    SubmitJobError,
    _MAX_PREPARE_PROJECTION_MESSAGE_BYTES,
    _submit_attempt_id_from_operation,
)


def _publish_counted_reconcile_pending(
    *,
    step: StepRecord,
    control: ExecutionControl,
    lease_session: LeaseSession,
    now: datetime,
    diagnostic_code: str,
    reason: str,
) -> ExecutorAcknowledgment:
    intent = transition_for_outcome(
        RecoveryPolicyOutcomeDisposition.RECONCILE_PENDING,
        capability=RecoveryCapabilityValue.EXTERNAL_EFFECT,
        attempt_count=step.attempt_count,
        effect_boundary_crossed=True,
        cancel_requested=control.cancel_requested,
        now=now,
        jitter=lambda base, _cap: base,
        operator_recovery_session=operator_recovery_session_active(step),
    )
    if intent.step_target is StepStatus.RETRY_WAIT:
        diagnostic = OperationDiagnostic(code=diagnostic_code.upper(), message=reason)
    else:
        diagnostic = OperationDiagnostic(
            code=DIAGNOSTIC_RECONCILE_TIMEOUT.upper(),
            message=f"recovery session budget exhausted: {reason}",
        )
    return lease_session.publish_recovery_release(intent, diagnostic=diagnostic)


def _publish_wait_upper_bound_exceeded(
    *,
    step: StepRecord,
    lease_session: LeaseSession,
    now: datetime,
) -> ExecutorAcknowledgment:
    return _publish_manual_recovery(
        step=step,
        lease_session=lease_session,
        now=now,
        diagnostic_code=DIAGNOSTIC_WAIT_UPPER_BOUND_EXCEEDED,
        reason="Repository import wait exceeded its upper bound (超出等待上界)",
    )


def _publish_manual_recovery(
    *,
    step: StepRecord,
    lease_session: LeaseSession,
    now: datetime,
    diagnostic_code: str,
    reason: str,
) -> ExecutorAcknowledgment:
    intent = transition_for_outcome(
        RecoveryPolicyOutcomeDisposition.MANUAL_RECOVERY,
        capability=RecoveryCapabilityValue.EXTERNAL_EFFECT,
        attempt_count=step.attempt_count,
        effect_boundary_crossed=True,
        cancel_requested=False,
        now=now,
        jitter=lambda base, _cap: base,
    )
    diagnostic = OperationDiagnostic(code=diagnostic_code.upper(), message=reason)
    return lease_session.publish_recovery_release(intent, diagnostic=diagnostic)


def _prepare_projection_failure_diagnostic(
    exc: SubmitImportPublicationError,
) -> OperationDiagnostic:
    message = str(exc)
    encoded = message.encode("utf-8")
    if len(encoded) > _MAX_PREPARE_PROJECTION_MESSAGE_BYTES:
        message = encoded[:_MAX_PREPARE_PROJECTION_MESSAGE_BYTES].decode("utf-8", errors="ignore")
    code = "UNSUPPORTED_TABLE" if "UNSUPPORTED_TABLE" in message else "STORAGE_PROJECTION_FAILED"
    return OperationDiagnostic(code=code, message=message)


def _make_prepare_projection_failure_builder(
    diagnostic: OperationDiagnostic,
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]]:
    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_submit_transaction.get()
        if transaction is None:
            raise SubmitJobError("submit prepare failure transaction is not bound")
        submit_attempt_id = _submit_attempt_id_from_operation(operation)
        abort_prepared_submit_in_control_transaction(
            request=AbortPreparedSubmitRequest(
                submit_attempt_id=submit_attempt_id,
                abort_code=diagnostic.code,
                aborted_at=transaction_now,
            ),
            unit_of_work=transaction,
        )
        terminal_step = dataclasses.replace(
            step,
            status=StepStatus.FAILED,
            diagnostic=diagnostic,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=step.optimistic_version + 1,
        )
        terminal_operation = dataclasses.replace(
            operation,
            status=OperationStatus.FAILED,
            diagnostic=diagnostic,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
        )
        return terminal_step, terminal_operation

    return builder


def _publish_prepare_terminal_abort(
    lease_session: LeaseSession,
    diagnostic: OperationDiagnostic,
) -> None:
    lease_session.publish_operation(_make_prepare_projection_failure_builder(diagnostic))


def _publish_prepare_projection_failure(
    lease_session: LeaseSession,
    exc: SubmitImportPublicationError,
) -> None:
    _publish_prepare_terminal_abort(
        lease_session,
        _prepare_projection_failure_diagnostic(exc),
    )


_PREPARE_CHECKPOINT_BINDING_DIAGNOSTIC = OperationDiagnostic(
    code="CHECKPOINT_ATTEMPT_BINDING_MISMATCH",
    message="prepare checkpoint attempt_id does not match submit payload",
)


def _publish_prepare_binding_failure(lease_session: LeaseSession) -> None:
    _publish_prepare_terminal_abort(lease_session, _PREPARE_CHECKPOINT_BINDING_DIAGNOSTIC)


def _publish_submit_resource_failure(
    operation: OperationRecord,
    step: StepRecord,
    control: ExecutionControl,
    lease_session: LeaseSession,
    error: MemoryError,
) -> None:
    del operation, step
    lease_session.refresh_control()
    if control.cancel_requested:
        lease_session.publish_operation(_make_cancelled_terminal_builder())
    else:
        _publish_prepare_terminal_abort(
            lease_session,
            OperationDiagnostic(
                code="RESOURCE_LIMIT_EXCEEDED",
                message=(str(error) or "operation memory budget exceeded")[:255],
            ),
        )


def _with_resource_failure_terminal(handler: ClaimedExecutor) -> ClaimedExecutor:
    return with_resource_failure_terminal(
        handler,
        on_memory_error=_publish_submit_resource_failure,
    )


def publish_stopped_compute_cancelled(lease_session: LeaseSessionPort) -> ExecutorAcknowledgment:
    return publish_stopped_compute_cancelled_step(lease_session, _make_cancelled_terminal_builder)


def _make_cancelled_terminal_builder() -> Callable[
    [OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]
]:
    return make_cancelled_terminal_builder(
        active_transaction=_active_submit_transaction.get,
        transaction_missing=lambda: SubmitJobError("submit cancellation transaction is not bound"),
    )


def _make_manual_recovery_terminal_builder(
    repository_operation_id: str | None,
    *,
    diagnostic: OperationDiagnostic,
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]]:
    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        if operation.ready_closure_ref is not None:
            raise CheckpointPublicationError(
                "ready_closure_ref is already set",
                code="CLOSURE_ALREADY_SET",
            )
        terminal_step = dataclasses.replace(
            step,
            status=StepStatus.MANUAL_RECOVERY_REQUIRED,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            updated_at=transaction_now,
            optimistic_version=step.optimistic_version + 1,
            diagnostic=diagnostic,
        )
        terminal_operation = dataclasses.replace(
            operation,
            status=OperationStatus.MANUAL_RECOVERY_REQUIRED,
            repository_operation_id=repository_operation_id,
            updated_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
            diagnostic=diagnostic,
        )
        return terminal_step, terminal_operation

    return builder


__all__ = [
    "publish_stopped_compute_cancelled",
]
