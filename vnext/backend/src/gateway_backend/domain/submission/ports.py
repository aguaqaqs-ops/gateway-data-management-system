"""Submission domain read ports."""

from __future__ import annotations

from typing import Protocol

from gateway_backend.domain.submission.models import SubmitAttempt, Submission


class SubmitAttemptReadPort(Protocol):
    def get_submit_attempt(self, submit_attempt_id: str) -> SubmitAttempt | None:
        """Load one SubmitAttempt by id."""


class SubmissionReadPort(Protocol):
    def get_submission(self, submission_id: str) -> Submission | None:
        """Load one Submission by id."""

    def get_submission_by_attempt(self, submit_attempt_id: str) -> Submission | None:
        """Load the Submission bound to one SubmitAttempt, if any."""
