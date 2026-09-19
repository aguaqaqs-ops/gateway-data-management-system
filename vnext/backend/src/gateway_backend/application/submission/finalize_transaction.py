"""T3 finalize SQLite transaction orchestration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from gateway_backend.application.submission.contracts import (
    FinalizeSubmitCommand,
    FinalizeSubmitResult,
    MatchingFinalizeFacts,
)
from gateway_backend.application.submission.errors import (
    FinalizeRecoveryRequired,
    ReviewIntegrityFailure,
)
from gateway_backend.application.submission.finalize import finalize_submit
from gateway_backend.application.submission.job_payload import SUBMIT_STEP_AWAIT
from gateway_backend.application.submission.ports import WorkspaceControlTransaction
from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.errors import ReviewClosureViolation
from gateway_backend.domain.submission.models import SubmitAttempt, SubmitAttemptState, Submission
from gateway_backend.domain.submission.review import build_seed_projection
from gateway_backend.operations import (
    OperationStatus,
    StepStatus,
    WritePrecondition,
)


@dataclass(frozen=True, slots=True)
class FinalizeSubmitTransactionRequest:
    submit_attempt_id: str
    facts: MatchingFinalizeFacts
    submission_id: str
    created_at: datetime
    expected_attempt_version: int
    expected_await_step_version: int
    expected_operation_version: int
    worker_id: str | None = None
    lease_token: str | None = None
    defer_operation_terminal: bool = False


def finalize_submit_transaction(
    *,
    request: FinalizeSubmitTransactionRequest,
    unit_of_work: WorkspaceControlTransaction,
) -> FinalizeSubmitResult:
    attempt = unit_of_work.submission.get_submit_attempt(request.submit_attempt_id)
    if attempt is None:
        raise ValueError("submit attempt is missing")
    if attempt.state is not SubmitAttemptState.EFFECT_PENDING:
        existing = unit_of_work.submission.get_submission_by_attempt(request.submit_attempt_id)
        if existing is not None and attempt.state is SubmitAttemptState.FINALIZED:
            result = finalize_submit(
                command=FinalizeSubmitCommand(
                    attempt=attempt,
                    facts=request.facts,
                    submission_id=existing.submission_id,
                    created_at=request.created_at,
                ),
                existing_submission=existing,
            )
            _assert_finalized_closure(
                unit_of_work,
                attempt=result.attempt,
                submission=result.submission,
            )
            _assert_finalize_review_closure(unit_of_work, result.submission.submission_id)
            return result
        raise ValueError("finalize requires EFFECT_PENDING attempt")

    workspace = unit_of_work.workspace.get_workspace(attempt.workspace_id)
    if workspace is None:
        raise ValueError("workspace is missing")

    existing_submission = unit_of_work.submission.get_submission_by_attempt(request.submit_attempt_id)
    result = finalize_submit(
        command=FinalizeSubmitCommand(
            attempt=attempt,
            facts=request.facts,
            submission_id=request.submission_id,
            created_at=request.created_at,
        ),
        existing_submission=existing_submission,
    )
    if not result.replay:
        unit_of_work.submission.insert_submission(result.submission)
        _insert_finalize_review_seed(unit_of_work, result.submission)
    else:
        _assert_finalize_review_closure(unit_of_work, result.submission.submission_id)

    finalized_attempt = replace(
        result.attempt,
        optimistic_version=attempt.optimistic_version + 1,
    )
    unit_of_work.submission.cas_update_attempt(
        finalized_attempt,
        expected_version=request.expected_attempt_version,
    )

    updated_workspace = replace(
        workspace,
        optimistic_version=workspace.optimistic_version + 1,
        updated_at=request.created_at,
    )
    unit_of_work.workspace.save_workspace(
        updated_workspace,
        expected_version=workspace.optimistic_version,
    )
    unit_of_work.submission.switch_workspace_occupancy_to_submission(
        workspace_id=attempt.workspace_id,
        submit_attempt_id=attempt.submit_attempt_id,
        submission_id=result.submission.submission_id,
    )
    unit_of_work.submission.delete_repository_occupancy(
        repository_id=attempt.repository_id,
        workspace_id=attempt.workspace_id,
        submit_attempt_id=attempt.submit_attempt_id,
        business_baseline_node_id=attempt.business_baseline_node_id,
        baseline_head_version=attempt.baseline_head_version,
    )

    _transfer_finalize_protection(unit_of_work, attempt=finalized_attempt)
    from gateway_backend.application.submit_jobs import release_submit_checkpoint_protection

    release_submit_checkpoint_protection(unit_of_work, operation_id=attempt.operation_id)

    if not request.defer_operation_terminal:
        operation = unit_of_work.operations.get_operation(attempt.operation_id)
        steps, _cursor = unit_of_work.operations.list_steps(attempt.operation_id)
        await_step = next((step for step in steps if step.step_name == SUBMIT_STEP_AWAIT), None)
        if await_step is None:
            raise ValueError("await_import_result step is missing")
        transaction_now = unit_of_work.transaction_now
        terminal_step = replace(
            await_step,
            status=StepStatus.SUCCEEDED,
            completed_at=transaction_now,
            updated_at=transaction_now,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            optimistic_version=await_step.optimistic_version + 1,
        )
        unit_of_work.operations.compare_and_set_step(
            terminal_step,
            WritePrecondition(
                expected_optimistic_version=request.expected_await_step_version,
                worker_id=request.worker_id,
                lease_token=request.lease_token,
            ),
            require_live_lease=await_step.status is StepStatus.RUNNING,
        )
        terminal_operation = replace(
            operation,
            status=OperationStatus.SUCCEEDED,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
        )
        unit_of_work.operations.compare_and_set_operation(
            terminal_operation,
            WritePrecondition(
                expected_optimistic_version=request.expected_operation_version,
                worker_id=None,
                lease_token=None,
            ),
        )
    return result


def _insert_finalize_review_seed(
    unit_of_work: WorkspaceControlTransaction,
    submission: Submission,
) -> None:
    event, projection = build_seed_projection(
        submission_id=submission.submission_id,
        actor_id=submission.created_by,
        occurred_at=submission.created_at,
    )
    try:
        unit_of_work.review.insert_seed(event, projection)
    except ReviewClosureViolation as exc:
        raise ReviewIntegrityFailure(exc.reason) from exc


def _assert_finalize_review_closure(
    unit_of_work: WorkspaceControlTransaction,
    submission_id: str,
) -> None:
    try:
        projection = unit_of_work.review.get_projection(submission_id)
    except ReviewClosureViolation as exc:
        raise ReviewIntegrityFailure(exc.reason) from exc
    if projection is None:
        raise ReviewIntegrityFailure("review projection is missing")


def _assert_finalized_closure(
    unit_of_work: WorkspaceControlTransaction,
    *,
    attempt: SubmitAttempt,
    submission: Submission,
) -> None:
    occupancy = unit_of_work.submission.get_workspace_occupancy(attempt.workspace_id)
    if occupancy is None or occupancy.active_submission_id != submission.submission_id:
        raise FinalizeRecoveryRequired(
            "workspace occupancy is not bound to the finalized submission"
        )
    repository_occupancy = unit_of_work.submission.get_repository_occupancy(attempt.repository_id)
    if repository_occupancy is not None:
        raise FinalizeRecoveryRequired("repository occupancy is still held after finalize")
    operation = unit_of_work.operations.get_operation(attempt.operation_id)
    if operation.status is not OperationStatus.SUCCEEDED:
        raise FinalizeRecoveryRequired("operation is not SUCCEEDED")
    steps, _cursor = unit_of_work.operations.list_steps(attempt.operation_id)
    await_step = next((step for step in steps if step.step_name == SUBMIT_STEP_AWAIT), None)
    if await_step is None or await_step.status is not StepStatus.SUCCEEDED:
        raise FinalizeRecoveryRequired("await_import_result is not SUCCEEDED")


def _transfer_finalize_protection(
    unit_of_work: WorkspaceControlTransaction,
    *,
    attempt: SubmitAttempt,
) -> None:
    unit_of_work.clear_artifact_protection(
        owner_kind="submit-attempt",
        owner_id=attempt.submit_attempt_id,
    )
    source_refs = tuple(
        ArtifactRef(
            artifact_id=artifact_id,
            media_type="application/octet-stream",
            size_bytes=0,
            raw_sha256=DigestRef("sha256:0000000000000000000000000000000000000000000000000000000000000000"),
        )
        for artifact_id in attempt.source_artifact_refs
    )
    if source_refs:
        unit_of_work.set_artifact_protection(
            source_refs,
            owner_kind="source-package",
            owner_id=attempt.submit_attempt_id,
            intent="source-package",
        )
    manifest_digest = attempt.canonicalization_manifest_digest
    if attempt.canonicalization_manifest_ref is not None and manifest_digest is not None:
        unit_of_work.set_artifact_protection(
            (
                ArtifactRef(
                    artifact_id=attempt.canonicalization_manifest_ref,
                    media_type="application/json",
                    size_bytes=0,
                    raw_sha256=DigestRef(manifest_digest),
                ),
            ),
            owner_kind="canonicalization-manifest",
            owner_id=attempt.submit_attempt_id,
            intent="canonicalization-manifest",
        )
