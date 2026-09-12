"""Workspace business ports consumed by application services."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from gateway_backend.domain.workspace.models import (
    BaselineHead,
    IdentityContext,
    PreviewAcceptanceRecord,
    PreviewResult,
    ResolvedScope,
    UploadRevision,
    Workspace,
    WorkspaceScope,
)


@runtime_checkable
class ScopeResolutionPort(Protocol):
    def resolve(self, context: IdentityContext) -> ResolvedScope:
        """Resolve the current session to a provisioned repository and BaselineHead."""


@runtime_checkable
class BaselineHeadReadPort(Protocol):
    def get_current_head(self, repository_id: str) -> BaselineHead:
        """Read the current BaselineHead for one repository."""


@runtime_checkable
class WorkspaceRepository(Protocol):
    def find_open_by_scope(self, scope: WorkspaceScope) -> Workspace | None:
        """Return the OPEN workspace for an exact scope, if present."""

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        """Load one workspace by id."""

    def get_upload_revision(self, upload_revision_id: str) -> UploadRevision | None:
        """Load one upload revision by id."""

    def get_preview_result(self, preview_result_id: str) -> PreviewResult | None:
        """Load one preview result by id."""

    def find_upload_idempotency(
        self,
        workspace_id: str,
        idempotency_key: str,
    ) -> UploadRevision | None:
        """Return a prior upload revision for the same workspace idempotency key."""

    def find_preview_idempotency(
        self,
        workspace_id: str,
        idempotency_key: str,
    ) -> PreviewAcceptanceRecord | None:
        """Return a prior preview acceptance for the same workspace idempotency key."""

    def list_preview_acceptances(self, workspace_id: str) -> tuple[PreviewAcceptanceRecord, ...]:
        """Return preview acceptances recorded for one workspace."""

    def save_preview_acceptance(self, record: PreviewAcceptanceRecord) -> None:
        """Persist preview acceptance idempotency bound to an Operation id."""

    def save_workspace(self, workspace: Workspace, *, expected_version: int) -> Workspace:
        """Persist workspace state with optimistic-version CAS."""

    def save_upload_revision(self, revision: UploadRevision) -> None:
        """Persist one immutable upload revision."""

    def save_preview_result(self, result: PreviewResult) -> None:
        """Persist one immutable preview result."""
