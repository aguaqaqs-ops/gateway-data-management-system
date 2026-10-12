"""Control DB ports owned by Archive use cases."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from gateway_backend.application.control_transactions import ControlTransaction
from gateway_backend.domain.archive.ports import ArchiveRepository
from gateway_backend.domain.baseline.ports import BaselineRepository
from gateway_backend.domain.submission.models import (
    RepositorySubmitOccupancy,
    SubmitAttempt,
    Submission,
    WorkspaceSubmitOccupancy,
)
from gateway_backend.domain.submission.ports import (
    ArchiveActiveAttemptFacts,
    ArchiveCandidateFacts,
)
from gateway_backend.domain.submission.review import ReviewProjection
from gateway_backend.domain.workspace.models import ResolvedScope
from gateway_backend.domain.workspace.ports import WorkspaceRepository


class ArchiveClosureReadPort(Protocol):
    def is_submission_closed(self, submission_id: str) -> bool:
        """Return whether one submission appears in any ArchiveResult disposition."""


class ArchiveSubmissionPort(Protocol):
    def get_submission(self, submission_id: str) -> Submission | None: ...

    def get_submit_attempt(self, submit_attempt_id: str) -> SubmitAttempt | None: ...

    def get_workspace_occupancy(self, workspace_id: str) -> WorkspaceSubmitOccupancy | None: ...

    def get_repository_occupancy(self, repository_id: str) -> RepositorySubmitOccupancy | None: ...

    def delete_workspace_submission_occupancy(
        self,
        workspace_id: str,
        *,
        expected_submission_id: str,
    ) -> None: ...

    def list_archive_candidate_facts(
        self,
        repository_id: str,
        *,
        baseline_node_id: str,
        baseline_commit_id: str,
    ) -> tuple[ArchiveCandidateFacts, ...]: ...

    def list_active_submit_attempts(self, repository_id: str) -> tuple[ArchiveActiveAttemptFacts, ...]: ...


class ArchiveReviewPort(Protocol):
    def get_projection(self, submission_id: str) -> ReviewProjection | None: ...


class ArchiveControlTransaction(ControlTransaction, ArchiveClosureReadPort, Protocol):
    @property
    def archive(self) -> ArchiveRepository: ...

    @property
    def baseline(self) -> BaselineRepository: ...

    @property
    def submission(self) -> ArchiveSubmissionPort: ...

    @property
    def review(self) -> ArchiveReviewPort: ...

    @property
    def workspace(self) -> WorkspaceRepository: ...

    def resolve_provisioned_scope(
        self,
        *,
        gateway_device_external_key: str,
        business_project_id: str,
    ) -> ResolvedScope: ...


class ArchiveControlUnitOfWorkFactory(Protocol):
    def __call__(
        self,
        *,
        read_only: bool = False,
    ) -> AbstractContextManager[ArchiveControlTransaction]: ...
