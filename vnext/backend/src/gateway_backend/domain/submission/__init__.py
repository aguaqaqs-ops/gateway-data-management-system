"""SubmitAttempt and Submission domain contracts."""

from gateway_backend.domain.submission.errors import (
    InvalidSubmitAttemptTransition,
    SubmissionBindingConflict,
    SubmitAttemptInvariantViolation,
    SubmitAttemptVersionConflict,
    SubmissionDomainError,
    SubmitOccupancyConflict,
)
from gateway_backend.domain.submission.models import (
    BackendArtifactRef,
    BuilderMutationPolicy,
    RepositoryArtifactRef,
    RepositorySubmitOccupancy,
    SubmitAcceptanceRecord,
    SubmitAttempt,
    SubmitAttemptState,
    Submission,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
    WorkspaceSubmitOccupancy,
    derive_preview_canonical_business_digest,
)
from gateway_backend.domain.submission.policies import (
    assert_submission_attempt_binding,
    assert_submit_attempt_invariants,
    transition_attempt_state,
)

__all__ = [
    "BackendArtifactRef",
    "BuilderMutationPolicy",
    "InvalidSubmitAttemptTransition",
    "RepositoryArtifactRef",
    "RepositorySubmitOccupancy",
    "Submission",
    "SubmissionBindingConflict",
    "SubmissionDomainError",
    "SubmitAcceptanceRecord",
    "SubmitAttempt",
    "SubmitAttemptInvariantViolation",
    "SubmitAttemptState",
    "SubmitAttemptVersionConflict",
    "SubmitOccupancyConflict",
    "SubmitTargetRef",
    "SubmitUnknownTypePolicy",
    "SubmitVerificationPolicy",
    "WorkspaceSubmitOccupancy",
    "assert_submission_attempt_binding",
    "assert_submit_attempt_invariants",
    "derive_preview_canonical_business_digest",
    "transition_attempt_state",
]
