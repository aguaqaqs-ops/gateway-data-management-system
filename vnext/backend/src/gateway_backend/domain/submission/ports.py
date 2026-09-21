"""Submission domain read ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from gateway_backend.domain.submission.models import SubmitAttempt, Submission
from gateway_backend.domain.submission.review import (
    ReviewEvent,
    ReviewIdempotencyRecord,
    ReviewProjection,
    ReviewStatus,
)


@dataclass(frozen=True, slots=True)
class ArchiveCandidateFacts:
    submission: Submission
    review_status: ReviewStatus
    review_sequence: int
    closed_by_archive: bool


@dataclass(frozen=True, slots=True)
class ArchiveActiveAttemptFacts:
    submit_attempt_id: str
    state: str


class ArchiveCandidateReadPort(Protocol):
    def list_archive_candidate_facts(
        self,
        repository_id: str,
        *,
        baseline_node_id: str,
        baseline_commit_id: str,
    ) -> tuple[ArchiveCandidateFacts, ...]:
        """Return bounded submission/review facts for archive candidate evaluation."""

    def list_active_submit_attempts(self, repository_id: str) -> tuple[ArchiveActiveAttemptFacts, ...]:
        """Return non-terminal submit attempts for one repository."""


class SubmitAttemptReadPort(Protocol):
    def get_submit_attempt(self, submit_attempt_id: str) -> SubmitAttempt | None:
        """Load one SubmitAttempt by id."""


class SubmissionReadPort(Protocol):
    def get_submission(self, submission_id: str) -> Submission | None:
        """Load one Submission by id."""

    def get_submission_by_attempt(self, submit_attempt_id: str) -> Submission | None:
        """Load the Submission bound to one SubmitAttempt, if any."""


class ReviewReadPort(Protocol):
    def get_projection(self, submission_id: str) -> ReviewProjection | None:
        """Load current ReviewProjection for one Submission.

        Raises ReviewClosureViolation when stored projection/event closure is inconsistent.
        """

    def list_events(self, submission_id: str) -> tuple[ReviewEvent, ...]:
        """Return Review events ordered by ascending sequence.

        Raises ReviewClosureViolation when stored projection/event closure is inconsistent.
        """

    def find_idempotency(
        self,
        business_project_id: str,
        idempotency_key: str,
    ) -> ReviewIdempotencyRecord | None:
        """Return durable Review idempotency row when present."""


class ReviewWritePort(Protocol):
    def insert_seed(self, event: ReviewEvent, projection: ReviewProjection) -> None:
        """Insert immutable seed event and initial projection."""

    def append_event(self, event: ReviewEvent) -> None:
        """Append one immutable Review event."""

    def cas_projection(
        self,
        projection: ReviewProjection,
        *,
        expected_version: int,
    ) -> ReviewProjection:
        """Update ReviewProjection with optimistic-version CAS."""

    def insert_idempotency(self, record: ReviewIdempotencyRecord) -> None:
        """Insert one Review idempotency row."""
