"""In-memory workspace fixtures for focused unit tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from gateway_backend.domain.workspace.errors import WorkspaceVersionConflict
from gateway_backend.domain.workspace.models import (
    BaselineHead,
    IdentityContext,
    PreviewAcceptanceRecord,
    PreviewResult,
    ResolvedScope,
    UploadRevision,
    Workspace,
    WorkspaceScope,
    WorkspaceState,
)

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


@dataclass
class FixedScopeResolutionPort:
    repository_id: str = "repo-1"
    baseline_head: BaselineHead | None = None

    def resolve(self, context: IdentityContext) -> ResolvedScope:
        del context
        if self.baseline_head is None:
            from gateway_backend.domain.workspace.errors import ScopeResolutionError

            raise ScopeResolutionError("baseline head missing")
        return ResolvedScope(
            repository_id=self.repository_id,
            baseline_head=self.baseline_head,
        )


@dataclass
class MutableBaselineHeadReadPort:
    heads: dict[str, BaselineHead]

    def get_current_head(self, repository_id: str) -> BaselineHead:
        head = self.heads.get(repository_id)
        if head is None:
            raise KeyError(repository_id)
        return head


class InMemoryWorkspaceRepository:
    def __init__(self) -> None:
        self._workspaces: dict[str, Workspace] = {}
        self._open_by_scope: dict[WorkspaceScope, str] = {}
        self._upload_revisions: dict[str, UploadRevision] = {}
        self._preview_results: dict[str, PreviewResult] = {}
        self._upload_idempotency: dict[tuple[str, str], str] = {}
        self._preview_idempotency: dict[tuple[str, str], PreviewAcceptanceRecord] = {}

    def find_open_by_scope(self, scope: WorkspaceScope) -> Workspace | None:
        workspace_id = self._open_by_scope.get(scope)
        if workspace_id is None:
            return None
        workspace = self._workspaces[workspace_id]
        if workspace.state is not WorkspaceState.OPEN:
            return None
        return workspace

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        return self._workspaces.get(workspace_id)

    def get_upload_revision(self, upload_revision_id: str) -> UploadRevision | None:
        return self._upload_revisions.get(upload_revision_id)

    def get_preview_result(self, preview_result_id: str) -> PreviewResult | None:
        return self._preview_results.get(preview_result_id)

    def find_upload_idempotency(
        self,
        workspace_id: str,
        idempotency_key: str,
    ) -> UploadRevision | None:
        revision_id = self._upload_idempotency.get((workspace_id, idempotency_key))
        if revision_id is None:
            return None
        return self._upload_revisions.get(revision_id)

    def find_preview_idempotency(
        self,
        workspace_id: str,
        idempotency_key: str,
    ) -> PreviewAcceptanceRecord | None:
        return self._preview_idempotency.get((workspace_id, idempotency_key))

    def save_workspace(self, workspace: Workspace, *, expected_version: int) -> Workspace:
        current = self._workspaces.get(workspace.workspace_id)
        if current is not None and current.optimistic_version != expected_version:
            raise WorkspaceVersionConflict(
                expected=expected_version,
                actual=current.optimistic_version,
            )
        if current is None and expected_version != workspace.optimistic_version:
            raise WorkspaceVersionConflict(
                expected=expected_version,
                actual=workspace.optimistic_version,
            )
        if workspace.state is WorkspaceState.OPEN:
            existing_scope_id = self._open_by_scope.get(workspace.scope)
            if existing_scope_id is not None and existing_scope_id != workspace.workspace_id:
                from gateway_backend.domain.workspace.errors import OpenWorkspaceConflict

                raise OpenWorkspaceConflict
            self._open_by_scope[workspace.scope] = workspace.workspace_id
        else:
            if self._open_by_scope.get(workspace.scope) == workspace.workspace_id:
                del self._open_by_scope[workspace.scope]
        self._workspaces[workspace.workspace_id] = workspace
        return workspace

    def save_upload_revision(self, revision: UploadRevision) -> None:
        self._upload_revisions[revision.upload_revision_id] = revision
        self._upload_idempotency[(revision.workspace_id, revision.idempotency_key)] = (
            revision.upload_revision_id
        )

    def save_preview_result(self, result: PreviewResult) -> None:
        self._preview_results[result.preview_result_id] = result

    def save_preview_acceptance(self, record: PreviewAcceptanceRecord) -> None:
        self._preview_idempotency[(record.workspace_id, record.idempotency_key)] = record

    def register_preview_idempotency(
        self,
        *,
        workspace_id: str,
        idempotency_key: str,
        request_fingerprint: str,
        operation_id: str,
        upload_revision_id: str,
        generation: int,
        business_baseline_node_id: str,
        baseline_head_version: int,
    ) -> None:
        self.save_preview_acceptance(
            PreviewAcceptanceRecord(
                workspace_id=workspace_id,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                operation_id=operation_id,
                upload_revision_id=upload_revision_id,
                generation=generation,
                business_baseline_node_id=business_baseline_node_id,
                baseline_head_version=baseline_head_version,
            )
        )


def make_identity(
    *,
    actor_id: str = "actor-1",
    device_key: str = "device-1",
    project_id: str = "project-1",
    permissions: frozenset[str] | None = None,
) -> IdentityContext:
    return IdentityContext(
        actor_id=actor_id,
        gateway_device_external_key=device_key,
        business_project_id=project_id,
        permissions=permissions
        or frozenset({"workspace_read", "upload_submit_workspace", "preview_workspace"}),
    )


def make_baseline_head(*, version: int = 1, commit_id: str = "commit-1") -> BaselineHead:
    return BaselineHead(
        business_baseline_node_id="node-1",
        business_baseline_commit_id=commit_id,
        baseline_head_version=version,
    )


def seed_open_workspace(
    repository: InMemoryWorkspaceRepository,
    *,
    workspace_id: str = "ws-1",
    actor_id: str = "actor-1",
    device_key: str = "device-1",
    project_id: str = "project-1",
    repository_id: str = "repo-1",
    generation: int = 0,
    optimistic_version: int = 0,
    current_upload_revision_id: str | None = None,
    current_preview_result_id: str | None = None,
) -> Workspace:
    workspace = Workspace(
        workspace_id=workspace_id,
        owner_actor_id=actor_id,
        gateway_device_external_key=device_key,
        business_project_id=project_id,
        repository_id=repository_id,
        state=WorkspaceState.OPEN,
        generation=generation,
        optimistic_version=optimistic_version,
        current_upload_revision_id=current_upload_revision_id,
        current_preview_result_id=current_preview_result_id,
        created_at=TS0,
        updated_at=TS0,
    )
    repository.save_workspace(workspace, expected_version=optimistic_version)
    return workspace


def bump_workspace_preview_pointer(
    repository: InMemoryWorkspaceRepository,
    workspace: Workspace,
    *,
    preview_result_id: str,
) -> Workspace:
    updated = replace(
        workspace,
        current_preview_result_id=preview_result_id,
        optimistic_version=workspace.optimistic_version + 1,
        updated_at=TS0,
    )
    return repository.save_workspace(updated, expected_version=workspace.optimistic_version)
