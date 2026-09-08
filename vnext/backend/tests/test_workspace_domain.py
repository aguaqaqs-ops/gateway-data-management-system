"""Workspace domain scope, OPEN uniqueness and generation policy tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from dataclasses import replace

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
    InputCompleteness,
    PreviewResult,
    PreviewResultDigests,
    SourceArtifactBinding,
    SourceArtifactRole,
    WorkspaceReadModelLabel,
    WorkspaceState,
    derive_read_model_label,
)
from gateway_backend.domain.workspace.policies import (
    assert_exact_scope,
    assert_open_uniqueness,
    assert_permission,
    assert_workspace_open,
    assert_workspace_version_cas,
    derive_preview_staleness,
    scope_from_context,
    validate_upload_role_closure,
)
from tests.support.workspace_fixtures import make_baseline_head, make_identity, seed_open_workspace

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

BINDING = SourceArtifactBinding(
    artifact_id="artifact-1",
    media_type="application/gzip",
    size_bytes=10,
    raw_sha256="sha256:abc",
)

SCOPE_MISMATCH_CASES = (
    ("actor-2", "device-1", "project-1"),
    ("actor-1", "device-2", "project-1"),
    ("actor-1", "device-1", "project-2"),
)

UPLOAD_ROLE_CLOSURE_FAULTS: tuple[
    tuple[InputCompleteness, dict[SourceArtifactRole, SourceArtifactBinding], str],
    ...,
] = (
    (
        InputCompleteness.FULL,
        {SourceArtifactRole.MODIFIED: BINDING},
        "FULL input_completeness requires exactly INITIAL and MODIFIED roles",
    ),
    (
        InputCompleteness.FULL,
        {SourceArtifactRole.INITIAL: BINDING},
        "FULL input_completeness requires exactly INITIAL and MODIFIED roles",
    ),
    (
        InputCompleteness.MODIFIED_ONLY,
        {
            SourceArtifactRole.INITIAL: BINDING,
            SourceArtifactRole.MODIFIED: BINDING,
        },
        "MODIFIED_ONLY input_completeness requires exactly MODIFIED role",
    ),
    (
        InputCompleteness.MODIFIED_ONLY,
        {},
        "MODIFIED_ONLY input_completeness requires exactly MODIFIED role",
    ),
)


def test_scope_from_context_uses_actor_as_owner() -> None:
    context = make_identity()
    scope = scope_from_context(context)
    assert scope.owner_actor_id == context.actor_id
    assert scope.gateway_device_external_key == context.gateway_device_external_key
    assert scope.business_project_id == context.business_project_id


@pytest.mark.parametrize(
    ("actor_id", "device_key", "project_id"),
    SCOPE_MISMATCH_CASES,
)
def test_assert_exact_scope_rejects_cross_scope_access(
    actor_id: str,
    device_key: str,
    project_id: str,
) -> None:
    from tests.support.workspace_fixtures import InMemoryWorkspaceRepository

    repository = InMemoryWorkspaceRepository()
    workspace = seed_open_workspace(repository)
    context = make_identity(actor_id=actor_id, device_key=device_key, project_id=project_id)
    with pytest.raises(ScopeForbidden):
        assert_exact_scope(workspace, context)


def test_assert_permission_requires_membership() -> None:
    context = make_identity(permissions=frozenset({"workspace_read"}))
    assert_permission(context, "workspace_read")
    with pytest.raises(PermissionDenied, match="upload_submit_workspace"):
        assert_permission(context, "upload_submit_workspace")


def test_open_workspace_uniqueness_rejects_second_workspace_id() -> None:
    from tests.support.workspace_fixtures import InMemoryWorkspaceRepository

    repository = InMemoryWorkspaceRepository()
    existing = seed_open_workspace(repository, workspace_id="ws-1")
    with pytest.raises(OpenWorkspaceConflict):
        assert_open_uniqueness(
            existing,
            scope=existing.scope,
            workspace_id="ws-2",
        )


def test_in_memory_repository_enforces_open_scope_uniqueness() -> None:
    from tests.support.workspace_fixtures import InMemoryWorkspaceRepository

    repository = InMemoryWorkspaceRepository()
    first = seed_open_workspace(repository, workspace_id="ws-1")
    duplicate = first.__class__(
        workspace_id="ws-2",
        owner_actor_id=first.owner_actor_id,
        gateway_device_external_key=first.gateway_device_external_key,
        business_project_id=first.business_project_id,
        repository_id=first.repository_id,
        state=WorkspaceState.OPEN,
        generation=0,
        optimistic_version=0,
        current_upload_revision_id=None,
        current_preview_result_id=None,
        created_at=TS0,
        updated_at=TS0,
    )
    with pytest.raises(OpenWorkspaceConflict):
        repository.save_workspace(duplicate, expected_version=0)


def test_assert_workspace_version_cas_rejects_stale_expected_version() -> None:
    from tests.support.workspace_fixtures import InMemoryWorkspaceRepository

    repository = InMemoryWorkspaceRepository()
    workspace = seed_open_workspace(repository, optimistic_version=3)
    with pytest.raises(WorkspaceVersionConflict, match="expected workspace version 2"):
        assert_workspace_version_cas(workspace, 2)


def test_assert_workspace_open_rejects_closed_state() -> None:
    from tests.support.workspace_fixtures import InMemoryWorkspaceRepository

    repository = InMemoryWorkspaceRepository()
    workspace = seed_open_workspace(repository)
    closed = replace(
        workspace,
        state=WorkspaceState.CLOSED,
        closed_at=TS0,
    )
    with pytest.raises(WorkspaceNotOpen):
        assert_workspace_open(closed)


@pytest.mark.parametrize(
    ("input_completeness", "roles", "message"),
    UPLOAD_ROLE_CLOSURE_FAULTS,
)
def test_validate_upload_role_closure_rejects_invalid_maps(
    input_completeness: InputCompleteness,
    roles: dict[SourceArtifactRole, SourceArtifactBinding],
    message: str,
) -> None:
    with pytest.raises(UploadClosureInvalid, match=message):
        validate_upload_role_closure(input_completeness, roles)


def test_validate_upload_role_closure_accepts_full_and_modified_only() -> None:
    validate_upload_role_closure(
        InputCompleteness.FULL,
        {
            SourceArtifactRole.INITIAL: BINDING,
            SourceArtifactRole.MODIFIED: BINDING,
        },
    )
    validate_upload_role_closure(
        InputCompleteness.MODIFIED_ONLY,
        {SourceArtifactRole.MODIFIED: BINDING},
    )


def test_derive_read_model_label_reflects_current_pointers() -> None:
    from tests.support.workspace_fixtures import InMemoryWorkspaceRepository

    repository = InMemoryWorkspaceRepository()
    empty = seed_open_workspace(repository)
    assert derive_read_model_label(empty) is WorkspaceReadModelLabel.EMPTY

    input_ready = replace(empty, current_upload_revision_id="ur-1")
    assert derive_read_model_label(input_ready) is WorkspaceReadModelLabel.INPUT_READY

    preview_ready = replace(input_ready, current_preview_result_id="pr-1")
    assert derive_read_model_label(preview_ready) is WorkspaceReadModelLabel.PREVIEW_READY


def _preview_result(*, head_version: int = 1, commit_id: str = "commit-1") -> PreviewResult:
    return PreviewResult(
        preview_result_id="pr-1",
        workspace_id="ws-1",
        upload_revision_id="ur-1",
        generation=1,
        repository_id="repo-1",
        business_baseline_node_id="node-1",
        business_baseline_commit_id=commit_id,
        baseline_head_version=head_version,
        ruleset_version="rules-1",
        contract_version="contract-1",
        provider_versions={"comparison": "v1"},
        digests=PreviewResultDigests(
            source_digest="d-source",
            input_digest="d-input",
            snapshot_digest="d-snapshot",
            comparison_digest="d-comparison",
            risk_digest="d-risk",
            surface_digest="d-surface",
            bundle_digest="d-bundle",
        ),
        bundle_artifact_id="bundle-1",
        ready_closure_artifact_id="closure-1",
        operation_id="op-1",
        created_at=TS0,
    )


@pytest.mark.parametrize(
    ("current_head", "expected_stale"),
    (
        (make_baseline_head(version=1, commit_id="commit-1"), False),
        (make_baseline_head(version=2, commit_id="commit-1"), True),
        (make_baseline_head(version=1, commit_id="commit-2"), True),
        (
            BaselineHead(
                business_baseline_node_id="node-2",
                business_baseline_commit_id="commit-1",
                baseline_head_version=1,
            ),
            True,
        ),
    ),
)
def test_derive_preview_staleness_compares_frozen_baseline_binding(
    current_head: BaselineHead,
    expected_stale: bool,
) -> None:
    result = _preview_result()
    assert derive_preview_staleness(result, current_head) is expected_stale
