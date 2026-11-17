"""Submit normal step recovery and operator recovery wiring."""

from __future__ import annotations

from datetime import (
    UTC,
    datetime,
)
from gateway_backend.application.payloads import (
    CheckpointDecodeError,
    PayloadDecodeError,
)
from gateway_backend.application.recovery import (
    DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH,
    DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
    DIAGNOSTIC_RECONCILE_TIMEOUT,
    RecoveryOutcome,
    RecoveryOutcomeDisposition,
    RecoveryPort,
)
from gateway_backend.application.submission.abort_transaction import (
    AbortSubmitTransactionRequest,
    abort_submit_transaction,
)
from gateway_backend.application.submission.contracts import (
    MatchingAbortProof,
    RepositoryOperationTerminalStatus,
)
from gateway_backend.application.submission.errors import (
    AbortProofNotSatisfied,
    FinalizeBindingMismatch,
    FinalizeRecoveryRequired,
    RepositoryUploadMetadataMismatch,
    RepositoryWriteTimeoutError,
    RepositoryWriteTransportError,
)
from gateway_backend.application.submission.import_builder import SubmitImportBuilderError
from gateway_backend.application.submission.job_payload import (
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_SUBMIT,
)
from gateway_backend.application.submission.ports import (
    RepositoryAbortEvidencePort,
    SubmitControlUnitOfWorkFactory,
)
from gateway_backend.operations.contracts import (
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)
from gateway_backend.operations.recovery import (
    OperatorRecoveryCommand,
    OperatorRecoveryRequest,
    RecoveryCapabilityLookup,
    build_authorized_operator_recovery,
)
from gateway_backend.operations.state import TransitionDisposition
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession,
    WriteUnitOfWorkFactory,
)
from typing import cast

from gateway_backend.application.submit_jobs.await_result import build_await_import_result_handler
from gateway_backend.application.submit_jobs.failures import _make_cancelled_terminal_builder
from gateway_backend.application.submit_jobs.payload import (
    OperatorRecoveryApplicationPort,
    SubmitJobError,
    SubmitRuntimeDependencies,
    _EXTERNAL_EFFECT_IDENTITY_MISMATCH_CHECKPOINT_CODE,
    _submit_attempt_id_from_operation,
)
from gateway_backend.application.submit_jobs.submit import (
    _submit_may_invoke_handler_without_checkpoint,
    build_submit_import_handler,
)

def build_submit_recovery_port(deps: SubmitRuntimeDependencies) -> RecoveryPort:
    submit_handler = build_submit_import_handler(deps)
    await_handler = build_await_import_result_handler(deps)

    class _SubmitRecoveryPort:
        def recover(
            self,
            operation: OperationRecord,
            step: StepRecord,
            control: ExecutionControl,
            lease_session: LeaseSession,
        ) -> RecoveryOutcome:
            if step.step_name == SUBMIT_STEP_SUBMIT:
                return _recover_external_effect_step(
                    deps=deps,
                    handler=submit_handler,
                    operation=operation,
                    step=step,
                    control=control,
                    lease_session=lease_session,
                )
            if step.step_name == SUBMIT_STEP_AWAIT:
                return _recover_external_effect_step(
                    deps=deps,
                    handler=await_handler,
                    operation=operation,
                    step=step,
                    control=control,
                    lease_session=lease_session,
                )
            return RecoveryOutcome(
                disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
                diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
                reason="submit recovery requires submit_import or await_import_result",
            )

    return cast(RecoveryPort, _SubmitRecoveryPort())

def build_submit_operator_recovery_port(
    *,
    write_uow_factory: WriteUnitOfWorkFactory,
    capability_lookup: RecoveryCapabilityLookup,
    submit_control_uow_factory: SubmitControlUnitOfWorkFactory,
    abort_evidence: RepositoryAbortEvidencePort,
    submit_deps: SubmitRuntimeDependencies,
) -> OperatorRecoveryApplicationPort:
    del submit_deps
    authorized = build_authorized_operator_recovery(
        write_uow_factory=write_uow_factory,
        capability_lookup=capability_lookup,
    )

    class _SubmitOperatorRecoveryPort:
        def execute_recovery(self, request: OperatorRecoveryRequest) -> TransitionDisposition:
            disposition = authorized.execute(request)
            if request.command is not OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE:
                return disposition
            with submit_control_uow_factory(read_only=True) as unit_of_work:
                operation = unit_of_work.operations.get_operation(request.operation_id)
                submit_attempt_id = _submit_attempt_id_from_operation(operation)
                attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
                if attempt is None:
                    raise ValueError("submit attempt is missing")
                if attempt.repository_operation_id is None:
                    raise ValueError(
                        "matching repository operation identity is required for business abort"
                    )
                stable_failure_code = abort_evidence.resolve_stable_failure_code(
                    repository_id=attempt.repository_id,
                    repository_operation_id=attempt.repository_operation_id,
                )
                proof = MatchingAbortProof(
                    repository_id=attempt.repository_id,
                    repository_operation_id=attempt.repository_operation_id,
                    terminal_status=RepositoryOperationTerminalStatus.FAILED,
                    stable_failure_code=stable_failure_code,
                )
            abort_submit_transaction(
                request=AbortSubmitTransactionRequest(
                    submit_attempt_id=submit_attempt_id,
                    proof=proof,
                    aborted_at=datetime.now(UTC),
                ),
                evidence=abort_evidence,
                unit_of_work_factory=submit_control_uow_factory,
            )
            return disposition

    return cast(OperatorRecoveryApplicationPort, _SubmitOperatorRecoveryPort())

def _map_handler_failure_to_recovery_outcome(
    exc: BaseException,
) -> RecoveryOutcome | None:
    if (
        isinstance(exc, CheckpointDecodeError)
        and exc.code == _EXTERNAL_EFFECT_IDENTITY_MISMATCH_CHECKPOINT_CODE
    ):
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH,
            reason=str(exc),
        )
    if isinstance(exc, (RepositoryWriteTimeoutError, TimeoutError)):
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_RECONCILE_TIMEOUT,
            reason=str(exc),
        )
    if isinstance(exc, RepositoryWriteTransportError):
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.RECONCILE_PENDING,
            diagnostic_code=DIAGNOSTIC_RECONCILE_TIMEOUT,
            reason=str(exc),
        )
    if isinstance(exc, RepositoryUploadMetadataMismatch):
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            reason=str(exc),
        )
    if isinstance(
        exc,
        (
            SubmitJobError,
            CheckpointDecodeError,
            PayloadDecodeError,
            SubmitImportBuilderError,
            FinalizeBindingMismatch,
            AbortProofNotSatisfied,
            FinalizeRecoveryRequired,
            ValueError,
        ),
    ):
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            reason=str(exc),
        )
    return None

def _recover_external_effect_step(
    *,
    deps: SubmitRuntimeDependencies,
    handler: ClaimedExecutor,
    operation: OperationRecord,
    step: StepRecord,
    control: ExecutionControl,
    lease_session: LeaseSession,
) -> RecoveryOutcome:
    if operation.status is OperationStatus.SUCCEEDED and step.status is StepStatus.SUCCEEDED:
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.PUBLISHED,
            diagnostic_code=None,
            reason=None,
        )

    lease_session.refresh_control()
    if step.checkpoint_ref is None and control.cancel_requested:
        lease_session.publish_operation(_make_cancelled_terminal_builder())
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.CANCELLED,
            diagnostic_code=None,
            reason=None,
        )

    if step.checkpoint_ref is None and not _submit_may_invoke_handler_without_checkpoint(
        deps,
        operation,
        step,
    ):
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            reason="submit external-effect recovery requires a durable checkpoint",
        )

    try:
        acknowledgment = handler(operation, step, control, lease_session)
    except Exception as exc:
        outcome = _map_handler_failure_to_recovery_outcome(exc)
        if outcome is None:
            raise
        return outcome

    if acknowledgment is ExecutorAcknowledgment.PUBLISHED:
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.PUBLISHED,
            diagnostic_code=None,
            reason=None,
        )
    return RecoveryOutcome(
        disposition=RecoveryOutcomeDisposition.RECONCILE_PENDING,
        diagnostic_code=None,
        reason=None,
    )


__all__ = [
    "build_submit_recovery_port",
    "build_submit_operator_recovery_port",
]
