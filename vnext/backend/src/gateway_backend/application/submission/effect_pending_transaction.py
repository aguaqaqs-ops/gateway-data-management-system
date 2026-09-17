"""T2 crossing transaction: PREPARED -> EFFECT_PENDING with prepare checkpoint facts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from gateway_backend.application.submission.contracts import PrepareImportCheckpoint
from gateway_backend.application.submission.ports import SubmitControlTransaction
from gateway_backend.domain.submission.models import (
    BackendArtifactRef,
    RepositoryArtifactRef,
    SubmitAttempt,
    SubmitAttemptState,
)
from gateway_backend.domain.submission.policies import transition_attempt_state


@dataclass(frozen=True, slots=True)
class EffectPendingTransactionRequest:
    submit_attempt_id: str
    checkpoint: PrepareImportCheckpoint
    repository_artifact_ref: RepositoryArtifactRef
    effect_pending_at: datetime
    expected_attempt_version: int


@dataclass(frozen=True, slots=True)
class EffectPendingTransactionResult:
    attempt: SubmitAttempt


def mark_submit_attempt_effect_pending(
    *,
    request: EffectPendingTransactionRequest,
    unit_of_work: SubmitControlTransaction,
) -> EffectPendingTransactionResult:
    attempt = unit_of_work.submission.get_submit_attempt(request.submit_attempt_id)
    if attempt is None:
        raise ValueError("submit attempt is missing")
    if attempt.state is not SubmitAttemptState.PREPARED:
        raise ValueError("effect pending crossing requires PREPARED attempt")

    manifest_ref = request.checkpoint.canonicalization_manifest_ref
    updated = transition_attempt_state(
        attempt,
        target=SubmitAttemptState.EFFECT_PENDING,
        optimistic_version=attempt.optimistic_version + 1,
        effect_pending_at=request.effect_pending_at,
        canonicalization_manifest_ref=manifest_ref.artifact_id,
        canonicalization_manifest_digest=request.checkpoint.canonicalization_manifest_digest,
        repository_import_artifact_ref=request.checkpoint.backend_import_artifact_ref,
        repository_artifact_ref=request.repository_artifact_ref,
    )
    _assert_backend_ref(updated.repository_import_artifact_ref, request.checkpoint.backend_import_artifact_ref)
    unit_of_work.submission.cas_update_attempt(
        updated,
        expected_version=request.expected_attempt_version,
    )
    return EffectPendingTransactionResult(attempt=updated)


@dataclass(frozen=True, slots=True)
class BindRepositoryOperationRequest:
    submit_attempt_id: str
    repository_operation_id: str
    expected_attempt_version: int


def bind_repository_operation_identity(
    *,
    request: BindRepositoryOperationRequest,
    unit_of_work: SubmitControlTransaction,
) -> SubmitAttempt:
    attempt = unit_of_work.submission.get_submit_attempt(request.submit_attempt_id)
    if attempt is None:
        raise ValueError("submit attempt is missing")
    if attempt.state is not SubmitAttemptState.EFFECT_PENDING:
        raise ValueError("repository operation binding requires EFFECT_PENDING attempt")
    if attempt.repository_artifact_ref is None:
        raise ValueError("repository operation binding requires repository artifact ref")
    updated = replace(
        attempt,
        repository_operation_id=request.repository_operation_id,
        optimistic_version=attempt.optimistic_version + 1,
    )
    unit_of_work.submission.cas_update_attempt(
        updated,
        expected_version=request.expected_attempt_version,
    )
    return updated


def _assert_backend_ref(
    actual: BackendArtifactRef | None,
    expected: BackendArtifactRef,
) -> None:
    if actual is None or actual != expected:
        raise ValueError("repository import artifact ref does not match prepare checkpoint")
