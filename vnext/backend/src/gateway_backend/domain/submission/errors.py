"""Submission domain invariant errors."""

from __future__ import annotations


class SubmissionDomainError(Exception):
    """Base error for submission domain invariants."""


class InvalidSubmitAttemptTransition(SubmissionDomainError):
    """Raised when a SubmitAttempt state transition is not allowed."""

    def __init__(self, *, current: str, target: str) -> None:
        super().__init__(f"cannot transition SubmitAttempt from {current!r} to {target!r}")
        self.current = current
        self.target = target


class SubmitAttemptInvariantViolation(SubmissionDomainError):
    """Raised when SubmitAttempt field co-presence or state binding is invalid."""


class SubmissionBindingConflict(SubmissionDomainError):
    """Raised when Submission facts do not match the bound SubmitAttempt."""


class SubmitAttemptVersionConflict(SubmissionDomainError):
    """SubmitAttempt optimistic version CAS failed."""

    stable_code = "SUBMIT_ATTEMPT_VERSION_CONFLICT"

    def __init__(self, *, expected: int, actual: int) -> None:
        super().__init__(
            f"submit attempt optimistic version conflict: expected {expected}, actual {actual}"
        )
        self.expected = expected
        self.actual = actual


class ArchiveCandidateReadBoundExceeded(SubmissionDomainError):
    """Archive candidate bounded read exceeded the supported SQL fetch limit."""


class SubmitOccupancyConflict(SubmissionDomainError):
    """Workspace or repository submit occupancy is already held or owner CAS failed."""

    stable_code = "SUBMIT_OCCUPANCY_CONFLICT"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InvalidReviewTransition(SubmissionDomainError):
    """Raised when a Review status transition is not allowed."""

    stable_code = "REVIEW_TRANSITION_CONFLICT"

    def __init__(self, *, current: str, action: str) -> None:
        super().__init__(f"cannot apply review action {action!r} from status {current!r}")
        self.current = current
        self.action = action


class InvalidReviewReason(SubmissionDomainError):
    """Raised when a Review reason violates the bounded plain-text contract."""

    stable_code = "INVALID_REVIEW_REASON"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InvalidReviewIdempotencyKey(SubmissionDomainError):
    """Raised when an Idempotency-Key violates the Review wire contract."""

    stable_code = "INVALID_IDEMPOTENCY_KEY"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ReviewVersionConflict(SubmissionDomainError):
    """Review projection optimistic version does not match the command."""

    stable_code = "REVIEW_VERSION_CONFLICT"

    def __init__(self, *, expected: int, actual: int) -> None:
        super().__init__(
            f"review optimistic version conflict: expected {expected}, actual {actual}"
        )
        self.expected = expected
        self.actual = actual


class ReviewClosureViolation(SubmissionDomainError):
    """Review projection/event/idempotency closure is inconsistent or incomplete."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
