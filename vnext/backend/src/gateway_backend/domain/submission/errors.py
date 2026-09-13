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
