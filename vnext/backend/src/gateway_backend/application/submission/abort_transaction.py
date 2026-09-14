"""Stable abort SQLite transaction orchestration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from gateway_backend.application.submission.abort import validate_abort_proof
from gateway_backend.application.submission.contracts import MatchingAbortProof
from gateway_backend.application.submission.job_payload import SUBMIT_STEP_AWAIT
from gateway_backend.application.submission.ports import RepositoryAbortEvidencePort
from gateway_backend.domain.submission.models import SubmitAttempt, SubmitAttemptState
from gateway_backend.domain.submission.policies import transition_attempt_state
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.operations import (
    OperationDiagnostic,
    OperationStatus,
    StepStatus,
    WritePrecondition,
)


@dataclass(frozen=True, slots=True)
class AbortSubmitTransactionRequest:
    submit_attempt_id: str
    proof: MatchingAbortProof
    aborted_at: datetime


@dataclass(frozen=True, slots=True)
class AbortSubmitTransactionResult:
    attempt: SubmitAttempt
    replay: bool


def abort_submit_transaction(
    *,
    request: AbortSubmitTransactionRequest,
    evidence: RepositoryAbortEvidencePort,
    unit_of_work: ControlDbUnitOfWork,
) -> AbortSubmitTransactionResult:
    attempt = unit_of_work.submission.get_submit_attempt(request.submit_attempt_id)
    if attempt is None:
        raise ValueError("submit attempt is missing")
    if attempt.state is SubmitAttemptState.ABORTED:
        return AbortSubmitTransactionResult(attempt=attempt, replay=True)
    if attempt.state not in {SubmitAttemptState.PREPARED, SubmitAttemptState.EFFECT_PENDING}:
        raise ValueError("abort requires PREPARED or EFFECT_PENDING attempt")

    validate_abort_proof(attempt=attempt, proof=request.proof, evidence=evidence)

    workspace = unit_of_work.workspace.get_workspace(attempt.workspace_id)
    if workspace is None:
        raise ValueError("workspace is missing")

    aborted_attempt = transition_attempt_state(
        attempt,
        target=SubmitAttemptState.ABORTED,
        optimistic_version=attempt.optimistic_version + 1,
        aborted_at=request.aborted_at,
        abort_code=request.proof.stable_failure_code,
    )
    unit_of_work.submission.cas_update_attempt(
        aborted_attempt,
        expected_version=attempt.optimistic_version,
    )

    updated_workspace = replace(
        workspace,
        optimistic_version=workspace.optimistic_version + 1,
        updated_at=request.aborted_at,
    )
    unit_of_work.workspace.save_workspace(
        updated_workspace,
        expected_version=workspace.optimistic_version,
    )
    unit_of_work.submission.delete_workspace_occupancy(attempt.workspace_id)
    unit_of_work.submission.delete_repository_occupancy(attempt.repository_id)
    unit_of_work.clear_artifact_protection(
        owner_kind="submit-attempt",
        owner_id=attempt.submit_attempt_id,
    )

    operation = unit_of_work.operations.get_operation(attempt.operation_id)
    steps, _cursor = unit_of_work.operations.list_steps(attempt.operation_id)
    active_step = next(
        (
            step
            for step in steps
            if step.status
            in {StepStatus.PENDING, StepStatus.RUNNING, StepStatus.RETRY_WAIT, StepStatus.MANUAL_RECOVERY_REQUIRED}
        ),
        None,
    )
    if active_step is None:
        active_step = next((step for step in steps if step.step_name == SUBMIT_STEP_AWAIT), steps[-1])

    transaction_now = unit_of_work.transaction_now
    abort_diagnostic = OperationDiagnostic(
        code=request.proof.stable_failure_code,
        message="submit attempt aborted",
    )
    failed_step = replace(
        active_step,
        status=StepStatus.FAILED,
        diagnostic=abort_diagnostic,
        completed_at=transaction_now,
        updated_at=transaction_now,
        worker_id=None,
        lease_token=None,
        lease_expires_at=None,
        optimistic_version=active_step.optimistic_version + 1,
    )
    unit_of_work.operations.compare_and_set_step(
        failed_step,
        WritePrecondition(
            expected_optimistic_version=active_step.optimistic_version,
            worker_id=active_step.worker_id,
            lease_token=active_step.lease_token,
        ),
        require_live_lease=active_step.status is StepStatus.RUNNING,
    )
    failed_operation = replace(
        operation,
        status=OperationStatus.FAILED,
        diagnostic=abort_diagnostic,
        completed_at=transaction_now,
        updated_at=transaction_now,
        optimistic_version=operation.optimistic_version + 1,
    )
    unit_of_work.operations.compare_and_set_operation(
        failed_operation,
        WritePrecondition(
            expected_optimistic_version=operation.optimistic_version,
            worker_id=None,
            lease_token=None,
        ),
    )
    return AbortSubmitTransactionResult(attempt=aborted_attempt, replay=False)
