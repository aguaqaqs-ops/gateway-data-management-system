"""Repository abort evidence adapter for stable failure proof validation."""

from __future__ import annotations

from dataclasses import dataclass

from gateway_backend.application.submission.contracts import (
    ALLOWED_ABORT_CODES,
    RepositoryImportOperationStatus,
)
from gateway_backend.application.submission.contracts import MatchingAbortProof
from gateway_backend.application.submission.errors import AbortProofNotSatisfied
from gateway_backend.domain.submission.models import SubmitAttempt
from gateway_backend.infrastructure.repository_write.http import HttpRepositoryWriteClient


@dataclass(frozen=True, slots=True)
class HttpRepositoryAbortEvidencePort:
    client: HttpRepositoryWriteClient

    def resolve_stable_failure_code(
        self,
        *,
        repository_id: str,
        repository_operation_id: str,
    ) -> str:
        operation = self.client.get_operation(
            repository_id=repository_id,
            operation_id=repository_operation_id,
        )
        if operation.status is not RepositoryImportOperationStatus.FAILED:
            raise AbortProofNotSatisfied("repository operation is not FAILED")
        if operation.error is None:
            raise AbortProofNotSatisfied("repository FAILED operation is missing error evidence")
        if operation.error.code not in ALLOWED_ABORT_CODES:
            raise AbortProofNotSatisfied(
                f"repository failure code {operation.error.code!r} is not an allowed stable abort"
            )
        return operation.error.code

    def validate_matching_stable_failure(
        self,
        *,
        attempt: SubmitAttempt,
        proof: MatchingAbortProof,
    ) -> None:
        operation = self.client.get_operation(
            repository_id=proof.repository_id,
            operation_id=proof.repository_operation_id,
        )
        if str(operation.operation_id) != proof.repository_operation_id:
            raise AbortProofNotSatisfied("repository operation identity does not match proof")
        if operation.status is not RepositoryImportOperationStatus.FAILED:
            raise AbortProofNotSatisfied("repository operation is not FAILED")
        if operation.error is None:
            raise AbortProofNotSatisfied("repository FAILED operation is missing error evidence")
        if operation.error.code not in ALLOWED_ABORT_CODES:
            raise AbortProofNotSatisfied(
                f"repository failure code {operation.error.code!r} is not an allowed stable abort"
            )
        if proof.stable_failure_code != operation.error.code:
            raise AbortProofNotSatisfied("abort proof stable failure code does not match repository")


__all__ = ["HttpRepositoryAbortEvidencePort"]
