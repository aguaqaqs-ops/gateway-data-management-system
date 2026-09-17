"""Submission application ports."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from gateway_repository_contracts import VersionedOperation

from gateway_backend.application.submission.contracts import MatchingAbortProof
from gateway_backend.domain.submission.models import RepositoryArtifactRef
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.models import (
    RepositorySubmitOccupancy,
    SubmitAcceptanceRecord,
    SubmitAttempt,
    Submission,
    WorkspaceSubmitOccupancy,
)
from gateway_backend.domain.workspace.models import BaselineHead, ResolvedScope
from gateway_backend.domain.workspace.ports import WorkspaceRepository
from gateway_backend.operations import OperationStore


class SubmitControlTransaction(Protocol):
    @property
    def submission(self) -> SubmitTransactionRepository: ...

    @property
    def workspace(self) -> WorkspaceRepository: ...

    @property
    def operations(self) -> OperationStore: ...

    @property
    def transaction_now(self) -> datetime: ...

    def set_artifact_protection(
        self,
        refs: tuple[ArtifactRef, ...],
        *,
        owner_kind: str,
        owner_id: str,
        intent: str,
    ) -> bool: ...

    def clear_artifact_protection(self, *, owner_kind: str, owner_id: str) -> int: ...

    def list_artifact_protection_for_owner(
        self,
        *,
        owner_kind: str,
        owner_id: str,
    ) -> frozenset[str]: ...

    def resolve_provisioned_scope(
        self,
        *,
        gateway_device_external_key: str,
        business_project_id: str,
    ) -> ResolvedScope:
        """Read transaction-fresh provisioned mapping/BaselineHead for one scope key."""


class SubmitControlUnitOfWorkFactory(Protocol):
    def __call__(
        self,
        *,
        read_only: bool = False,
    ) -> AbstractContextManager[SubmitControlTransaction]: ...


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


class SubmitTransactionRepository(SubmissionRepository, SubmitOccupancyReadPort, Protocol):
    def insert_attempt_prepared(self, attempt: SubmitAttempt) -> None:
        """Insert one PREPARED SubmitAttempt."""

    def insert_idempotency(self, record: SubmitAcceptanceRecord) -> None:
        """Insert one submit idempotency row."""

    def insert_submission(self, submission: Submission) -> None:
        """Insert one immutable Submission."""

    def cas_update_attempt(
        self,
        attempt: SubmitAttempt,
        *,
        expected_version: int,
    ) -> SubmitAttempt:
        """Update one SubmitAttempt with optimistic-version CAS."""

    def insert_workspace_attempt_occupancy(
        self,
        *,
        workspace_id: str,
        submit_attempt_id: str,
    ) -> None:
        """Insert workspace Attempt occupancy pointer."""

    def switch_workspace_occupancy_to_submission(
        self,
        *,
        workspace_id: str,
        submit_attempt_id: str,
        submission_id: str,
    ) -> None:
        """Atomically switch workspace occupancy from Attempt to Submission."""

    def delete_workspace_occupancy(
        self,
        workspace_id: str,
        *,
        expected_submit_attempt_id: str,
    ) -> None:
        """Delete workspace submit occupancy row when it still points at this Attempt."""

    def insert_repository_occupancy(self, occupancy: RepositorySubmitOccupancy) -> None:
        """Insert repository submit occupancy row."""

    def delete_repository_occupancy(
        self,
        *,
        repository_id: str,
        workspace_id: str,
        submit_attempt_id: str,
        business_baseline_node_id: str,
        baseline_head_version: int,
    ) -> None:
        """Delete repository submit occupancy row when owner facts still match."""


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
    def resolve_stable_failure_code(
        self,
        *,
        repository_id: str,
        repository_operation_id: str,
    ) -> str:
        """Return the repository FAILED operation stable failure code."""

    def validate_matching_stable_failure(
        self,
        *,
        attempt: SubmitAttempt,
        proof: MatchingAbortProof,
    ) -> None:
        """Verify repository-scoped FAILED evidence matches the bound Attempt."""


class RepositoryWritePort(Protocol):
    def upload_artifact(
        self,
        *,
        repository_id: str,
        idempotency_key: str,
        media_type: str,
        raw_sha256: str,
        body: bytes,
    ) -> RepositoryArtifactRef: ...

    def submit_versioned_import(
        self,
        *,
        repository_id: str,
        idempotency_key: str,
        artifact_ref: RepositoryArtifactRef,
        expected_commit_id: str,
    ) -> str: ...

    def get_operation(
        self,
        *,
        repository_id: str,
        operation_id: str,
    ) -> VersionedOperation: ...

    def wait_operation(
        self,
        *,
        repository_id: str,
        operation_id: str,
        deadline_seconds: float | None = None,
    ) -> VersionedOperation: ...
