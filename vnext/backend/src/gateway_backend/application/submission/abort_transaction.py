"""Stable abort SQLite transaction orchestration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from gateway_backend.application.submission.abort import validate_abort_proof
from gateway_backend.application.submission.contracts import MatchingAbortProof
from gateway_backend.application.submission.ports import (
    RepositoryAbortEvidencePort,
    SubmitControlTransaction,
    SubmitControlUnitOfWorkFactory,
)
from gateway_backend.domain.submission.models import SubmitAttempt, SubmitAttemptState
from gateway_backend.domain.submission.policies import transition_attempt_state
from gateway_backend.operations import (
    OperationDiagnostic,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
    WritePrecondition,
)

_ACTIVE_STEP_STATUSES = frozenset(
    {
        StepStatus.PENDING,
        StepStatus.RUNNING,
        StepStatus.RETRY_WAIT,
        StepStatus.MANUAL_RECOVERY_REQUIRED,
    }
)


@dataclass(frozen=True, slots=True)
class AbortSubmitTransactionRequest:
    submit_attempt_id: str
    proof: MatchingAbortProof
    aborted_at: datetime
    worker_id: str | None = None
    lease_token: str | None = None
    expected_attempt_version: int | None = None
    expected_await_step_version: int | None = None
    expected_operation_version: int | None = None


@dataclass(frozen=True, slots=True)
class AbortSubmitTransactionResult:
    attempt: SubmitAttempt
    replay: bool


def abort_submit_transaction(
    *,
    request: AbortSubmitTransactionRequest,
    evidence: RepositoryAbortEvidencePort,
    unit_of_work_factory: SubmitControlUnitOfWorkFactory,
) -> AbortSubmitTransactionResult:
    with unit_of_work_factory(read_only=True) as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(request.submit_attempt_id)
        if attempt is None:
            raise ValueError("submit attempt is missing")
        if attempt.state is SubmitAttemptState.ABORTED:
            return AbortSubmitTransactionResult(attempt=attempt, replay=True)
        if attempt.state is not SubmitAttemptState.EFFECT_PENDING:
            raise ValueError("abort requires EFFECT_PENDING attempt")

    validate_abort_proof(attempt=attempt, proof=request.proof, evidence=evidence)

    with unit_of_work_factory(read_only=False) as unit_of_work:
        return _abort_submit_in_transaction(request=request, unit_of_work=unit_of_work)


def _abort_submit_in_transaction(
    *,
    request: AbortSubmitTransactionRequest,
    unit_of_work: SubmitControlTransaction,
) -> AbortSubmitTransactionResult:
    attempt = unit_of_work.submission.get_submit_attempt(request.submit_attempt_id)
    if attempt is None:
        raise ValueError("submit attempt is missing")
    if attempt.state is SubmitAttemptState.ABORTED:
        return AbortSubmitTransactionResult(attempt=attempt, replay=True)
    if attempt.state is not SubmitAttemptState.EFFECT_PENDING:
        raise ValueError("abort requires EFFECT_PENDING attempt")

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
        expected_version=(
            request.expected_attempt_version
            if request.expected_attempt_version is not None
            else attempt.optimistic_version
        ),
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
    unit_of_work.submission.delete_workspace_occupancy(
        attempt.workspace_id,
        expected_submit_attempt_id=attempt.submit_attempt_id,
    )
    unit_of_work.submission.delete_repository_occupancy(
        repository_id=attempt.repository_id,
        workspace_id=attempt.workspace_id,
        submit_attempt_id=attempt.submit_attempt_id,
        business_baseline_node_id=attempt.business_baseline_node_id,
        baseline_head_version=attempt.baseline_head_version,
    )
    unit_of_work.clear_artifact_protection(
        owner_kind="submit-attempt",
        owner_id=attempt.submit_attempt_id,
    )
    from gateway_backend.application.submit_jobs import release_submit_checkpoint_protection

    release_submit_checkpoint_protection(unit_of_work, operation_id=attempt.operation_id)

    operation = unit_of_work.operations.get_operation(attempt.operation_id)
    steps, _cursor = unit_of_work.operations.list_steps(attempt.operation_id)
    _fail_active_step_if_needed(
        unit_of_work,
        steps=steps,
        request=request,
        abort_code=request.proof.stable_failure_code,
    )
    _fail_operation_if_needed(
        unit_of_work,
        request=request,
        operation=operation,
        abort_code=request.proof.stable_failure_code,
    )
    return AbortSubmitTransactionResult(attempt=aborted_attempt, replay=False)


def _fail_active_step_if_needed(
    unit_of_work: SubmitControlTransaction,
    *,
    steps: tuple[StepRecord, ...],
    request: AbortSubmitTransactionRequest,
    abort_code: str,
) -> None:
    active_step = next((step for step in steps if step.status in _ACTIVE_STEP_STATUSES), None)
    if active_step is None:
        return
    transaction_now = unit_of_work.transaction_now
    if active_step.status is StepStatus.RUNNING:
        terminal_status = StepStatus.FAILED
        diagnostic = OperationDiagnostic(code=abort_code, message="submit attempt aborted")
    else:
        terminal_status = StepStatus.CANCELLED
        diagnostic = OperationDiagnostic(code=abort_code, message="submit attempt aborted")
    failed_step = replace(
        active_step,
        status=terminal_status,
        diagnostic=diagnostic,
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
            expected_optimistic_version=(
                request.expected_await_step_version
                if request.expected_await_step_version is not None
                else active_step.optimistic_version
            ),
            worker_id=request.worker_id,
            lease_token=request.lease_token,
        ),
        require_live_lease=active_step.status is StepStatus.RUNNING,
    )


def _fail_operation_if_needed(
    unit_of_work: SubmitControlTransaction,
    *,
    request: AbortSubmitTransactionRequest,
    operation: OperationRecord,
    abort_code: str,
) -> None:
    if operation.status.is_final_terminal():
        return
    transaction_now = unit_of_work.transaction_now
    if operation.status is OperationStatus.RUNNING:
        terminal_status = OperationStatus.FAILED
    else:
        terminal_status = OperationStatus.CANCELLED
    failed_operation = replace(
        operation,
        status=terminal_status,
        diagnostic=OperationDiagnostic(code=abort_code, message="submit attempt aborted"),
        completed_at=transaction_now,
        updated_at=transaction_now,
        optimistic_version=operation.optimistic_version + 1,
    )
    unit_of_work.operations.compare_and_set_operation(
        failed_operation,
        WritePrecondition(
            expected_optimistic_version=(
                request.expected_operation_version
                if request.expected_operation_version is not None
                else operation.optimistic_version
            ),
            worker_id=None,
            lease_token=None,
        ),
    )
