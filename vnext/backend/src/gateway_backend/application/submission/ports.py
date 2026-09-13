"""Submission application ports."""

from __future__ import annotations

from typing import Protocol

from gateway_backend.application.submission.contracts import (
    MatchingAbortProof,
    RepositorySubmitOccupancy,
    SubmitAcceptanceRecord,
    WorkspaceSubmitOccupancy,
)
from gateway_backend.domain.submission.models import SubmitAttempt, Submission
from gateway_backend.domain.workspace.models import BaselineHead


class SubmissionRepository(Protocol):
    def find_submit_idempotency(
        self,
        workspace_id: str,
        idempotency_key: str,
    ) -> SubmitAcceptanceRecord | None:
        """Return durable submit idempotency row when present."""

    def get_submit_attempt(self, submit_attempt_id: str) -> SubmitAttempt | None:
        """Load one SubmitAttempt."""

    def get_submission(self, submission_id: str) -> Submission | None:
        """Load one Submission."""

    def get_submission_by_attempt(self, submit_attempt_id: str) -> Submission | None:
        """Load Submission bound to one SubmitAttempt."""


class SubmitOccupancyReadPort(Protocol):
    def get_workspace_occupancy(self, workspace_id: str) -> WorkspaceSubmitOccupancy | None:
        """Return workspace submit occupancy projection when occupied."""

    def get_repository_occupancy(self, repository_id: str) -> RepositorySubmitOccupancy | None:
        """Return repository submit occupancy projection when occupied."""


class BaselineCanonicalDigestPort(Protocol):
    def get_baseline_canonical_digest(
        self,
        *,
        repository_id: str,
        baseline_head: BaselineHead,
    ) -> str:
        """Return current business-base canonical digest for NO_CANONICAL_CHANGE guard."""


class RepositoryMainResolvePort(Protocol):
    def resolve_main_expected_commit(self, *, repository_id: str) -> str:
        """Resolve current Repository main head commit id for a new AcceptSubmit."""


class RepositoryAbortEvidencePort(Protocol):
    def validate_matching_stable_failure(
        self,
        *,
        attempt: SubmitAttempt,
        proof: MatchingAbortProof,
    ) -> None:
        """Verify repository-scoped FAILED evidence matches the bound Attempt."""
