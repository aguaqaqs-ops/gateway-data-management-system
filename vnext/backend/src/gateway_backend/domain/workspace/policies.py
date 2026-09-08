"""Workspace domain policies and invariant checks."""

from __future__ import annotations

from collections.abc import Mapping

from gateway_backend.domain.workspace.errors import (
    OpenWorkspaceConflict,
    PermissionDenied,
    ScopeForbidden,
    UploadClosureInvalid,
    WorkspaceNotOpen,
    WorkspaceVersionConflict,
)
from gateway_backend.domain.workspace.models import (
    BaselineHead,
    IdentityContext,
    InputCompleteness,
    PreviewResult,
    SourceArtifactRole,
    Workspace,
    WorkspaceScope,
    WorkspaceState,
)


def scope_from_context(context: IdentityContext) -> WorkspaceScope:
    return WorkspaceScope(
        owner_actor_id=context.actor_id,
        gateway_device_external_key=context.gateway_device_external_key,
        business_project_id=context.business_project_id,
    )


def assert_exact_scope(workspace: Workspace, context: IdentityContext) -> None:
    expected = scope_from_context(context)
    if workspace.scope != expected:
        raise ScopeForbidden


def assert_permission(context: IdentityContext, permission: str) -> None:
    if permission not in context.permissions:
        raise PermissionDenied(permission)


def assert_open_uniqueness(
    existing_open: Workspace | None,
    *,
    scope: WorkspaceScope,
    workspace_id: str,
) -> None:
    if existing_open is None:
        return
    if existing_open.scope != scope:
        raise OpenWorkspaceConflict
    if existing_open.workspace_id != workspace_id:
        raise OpenWorkspaceConflict


def assert_workspace_open(workspace: Workspace) -> None:
    if workspace.state is not WorkspaceState.OPEN:
        raise WorkspaceNotOpen


def assert_workspace_version_cas(workspace: Workspace, expected_version: int) -> None:
    if workspace.optimistic_version != expected_version:
        raise WorkspaceVersionConflict(
            expected=expected_version,
            actual=workspace.optimistic_version,
        )


def validate_upload_role_closure(
    input_completeness: InputCompleteness,
    source_artifacts: Mapping[SourceArtifactRole, object],
) -> None:
    roles = frozenset(source_artifacts)
    if input_completeness is InputCompleteness.FULL:
        expected = frozenset({SourceArtifactRole.INITIAL, SourceArtifactRole.MODIFIED})
        if roles != expected:
            raise UploadClosureInvalid(
                "FULL input_completeness requires exactly INITIAL and MODIFIED roles"
            )
        return
    if input_completeness is InputCompleteness.MODIFIED_ONLY:
        if roles != frozenset({SourceArtifactRole.MODIFIED}):
            raise UploadClosureInvalid(
                "MODIFIED_ONLY input_completeness requires exactly MODIFIED role"
            )
        return
    raise UploadClosureInvalid("input_completeness must be FULL or MODIFIED_ONLY")


def derive_preview_staleness(result: PreviewResult, current_head: BaselineHead) -> bool:
    return (
        result.business_baseline_node_id != current_head.business_baseline_node_id
        or result.business_baseline_commit_id != current_head.business_baseline_commit_id
        or result.baseline_head_version != current_head.baseline_head_version
    )
