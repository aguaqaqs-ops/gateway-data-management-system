"""Stable abort proof guards for SubmitAttempt business abort."""

from __future__ import annotations

from gateway_backend.application.submission.contracts import MatchingAbortProof
from gateway_backend.application.submission.errors import AbortProofNotSatisfied
from gateway_backend.application.submission.ports import RepositoryAbortEvidencePort
from gateway_backend.domain.submission.models import SubmitAttempt

ALLOWED_ABORT_CODES = frozenset(
    {
        "IMPORT_REJECTED",
        "EXPECTED_COMMIT_MISMATCH",
        "VERIFICATION_FAILED_NOT_PUBLISHED",
    }
)


def validate_abort_proof(
    *,
    attempt: SubmitAttempt,
    proof: MatchingAbortProof,
    evidence: RepositoryAbortEvidencePort,
) -> None:
    if attempt.repository_operation_id is None:
        raise AbortProofNotSatisfied(
            "matching repository operation identity is required for business abort"
        )
    if proof.repository_operation_id != attempt.repository_operation_id:
        raise AbortProofNotSatisfied(
            "abort proof repository operation identity must match attempt"
        )
    if proof.repository_id != attempt.repository_id:
        raise AbortProofNotSatisfied("abort proof repository scope must match attempt")
    if proof.stable_failure_code not in ALLOWED_ABORT_CODES:
        raise AbortProofNotSatisfied(
            f"abort code {proof.stable_failure_code!r} is not an allowed not-published stable failure"
        )
    evidence.validate_matching_stable_failure(attempt=attempt, proof=proof)
