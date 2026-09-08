"""Upload application role closure, idempotency and generation CAS tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gateway_backend.application.workspace.contracts import AcceptUploadCommand
from gateway_backend.application.workspace.errors import IdempotencyConflict
from gateway_backend.application.workspace.services import accept_upload, create_or_get_workspace
from gateway_backend.domain.workspace.errors import WorkspaceVersionConflict
from gateway_backend.domain.workspace.models import InputCompleteness, SourceArtifactBinding, SourceArtifactRole
from tests.support.workspace_fixtures import (
    FixedScopeResolutionPort,
    InMemoryWorkspaceRepository,
    make_baseline_head,
    make_identity,
    seed_open_workspace,
)

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
TS1 = datetime(2024, 6, 1, 12, 5, 0, tzinfo=UTC)

INITIAL_BINDING = SourceArtifactBinding(
    artifact_id="initial-1",
    media_type="application/gzip",
    size_bytes=11,
    raw_sha256="sha256:initial",
)
MODIFIED_BINDING = SourceArtifactBinding(
    artifact_id="modified-1",
    media_type="application/gzip",
    size_bytes=12,
    raw_sha256="sha256:modified",
)


def _accept_command(
    *,
    workspace_id: str,
    expected_workspace_version: int,
    idempotency_key: str = "upload-key-1",
    input_completeness: InputCompleteness = InputCompleteness.FULL,
    preview_result_id: str | None = None,
) -> AcceptUploadCommand:
    del preview_result_id
    return AcceptUploadCommand(
        context=make_identity(),
        workspace_id=workspace_id,
        expected_workspace_version=expected_workspace_version,
        idempotency_key=idempotency_key,
        input_completeness=input_completeness,
        source_artifacts={
            SourceArtifactRole.INITIAL: INITIAL_BINDING,
            SourceArtifactRole.MODIFIED: MODIFIED_BINDING,
        },
        now=TS1,
    )


def test_create_or_get_workspace_is_idempotent_for_exact_scope() -> None:
    repository = InMemoryWorkspaceRepository()
    scope_resolution = FixedScopeResolutionPort(baseline_head=make_baseline_head())
    context = make_identity()

    created = create_or_get_workspace(
        context=context,
        scope_resolution=scope_resolution,
        repository=repository,
        created_at=TS0,
    )
    replay = create_or_get_workspace(
        context=context,
        scope_resolution=scope_resolution,
        repository=repository,
        created_at=TS0,
    )

    assert created.replay is False
    assert replay.replay is True
    assert replay.workspace.workspace_id == created.workspace.workspace_id


def test_accept_upload_publishes_revision_and_increments_generation() -> None:
    repository = InMemoryWorkspaceRepository()
    scope_resolution = FixedScopeResolutionPort(baseline_head=make_baseline_head())
    workspace = seed_open_workspace(repository)
    command = _accept_command(workspace_id=workspace.workspace_id, expected_workspace_version=0)

    result = accept_upload(
        command=command,
        scope_resolution=scope_resolution,
        repository=repository,
    )

    assert result.replay is False
    assert result.revision.generation == 1
    assert result.workspace.generation == 1
    assert result.workspace.optimistic_version == 1
    assert result.workspace.current_upload_revision_id == result.revision.upload_revision_id
    assert result.workspace.current_preview_result_id is None


def test_accept_upload_same_key_replays_existing_revision() -> None:
    repository = InMemoryWorkspaceRepository()
    scope_resolution = FixedScopeResolutionPort(baseline_head=make_baseline_head())
    workspace = seed_open_workspace(repository)
    command = _accept_command(workspace_id=workspace.workspace_id, expected_workspace_version=0)

    first = accept_upload(command=command, scope_resolution=scope_resolution, repository=repository)
    replay = accept_upload(
        command=_accept_command(
            workspace_id=workspace.workspace_id,
            expected_workspace_version=0,
        ),
        scope_resolution=scope_resolution,
        repository=repository,
    )

    assert replay.replay is True
    assert replay.revision.upload_revision_id == first.revision.upload_revision_id


def test_accept_upload_same_key_different_fingerprint_conflicts() -> None:
    repository = InMemoryWorkspaceRepository()
    scope_resolution = FixedScopeResolutionPort(baseline_head=make_baseline_head())
    workspace = seed_open_workspace(repository)
    first_command = _accept_command(workspace_id=workspace.workspace_id, expected_workspace_version=0)
    accept_upload(command=first_command, scope_resolution=scope_resolution, repository=repository)

    conflicting = AcceptUploadCommand(
        context=make_identity(),
        workspace_id=workspace.workspace_id,
        expected_workspace_version=1,
        idempotency_key="upload-key-1",
        input_completeness=InputCompleteness.MODIFIED_ONLY,
        source_artifacts={SourceArtifactRole.MODIFIED: MODIFIED_BINDING},
        now=TS1,
    )
    with pytest.raises(IdempotencyConflict, match="upload-key-1"):
        accept_upload(
            command=conflicting,
            scope_resolution=scope_resolution,
            repository=repository,
        )


def test_accept_upload_stale_workspace_version_does_not_create_revision() -> None:
    repository = InMemoryWorkspaceRepository()
    scope_resolution = FixedScopeResolutionPort(baseline_head=make_baseline_head())
    workspace = seed_open_workspace(repository, optimistic_version=2)
    command = _accept_command(workspace_id=workspace.workspace_id, expected_workspace_version=1)

    with pytest.raises(WorkspaceVersionConflict):
        accept_upload(command=command, scope_resolution=scope_resolution, repository=repository)
    assert repository.find_upload_idempotency(workspace.workspace_id, "upload-key-1") is None


def test_accept_upload_clears_current_preview_pointer() -> None:
    repository = InMemoryWorkspaceRepository()
    scope_resolution = FixedScopeResolutionPort(baseline_head=make_baseline_head())
    workspace = seed_open_workspace(
        repository,
        optimistic_version=1,
        generation=1,
        current_upload_revision_id="ur-old",
        current_preview_result_id="pr-old",
    )
    command = _accept_command(workspace_id=workspace.workspace_id, expected_workspace_version=1)

    result = accept_upload(command=command, scope_resolution=scope_resolution, repository=repository)

    assert result.workspace.current_preview_result_id is None
    assert result.workspace.generation == 2


UPLOAD_ROLE_CLOSURE_FAULTS = (
    (
        InputCompleteness.FULL,
        {SourceArtifactRole.MODIFIED: MODIFIED_BINDING},
    ),
    (
        InputCompleteness.MODIFIED_ONLY,
        {
            SourceArtifactRole.INITIAL: INITIAL_BINDING,
            SourceArtifactRole.MODIFIED: MODIFIED_BINDING,
        },
    ),
)


@pytest.mark.parametrize(("input_completeness", "roles"), UPLOAD_ROLE_CLOSURE_FAULTS)
def test_accept_upload_rejects_invalid_role_closure_before_persisting(
    input_completeness: InputCompleteness,
    roles: dict[SourceArtifactRole, SourceArtifactBinding],
) -> None:
    repository = InMemoryWorkspaceRepository()
    scope_resolution = FixedScopeResolutionPort(baseline_head=make_baseline_head())
    workspace = seed_open_workspace(repository)
    command = AcceptUploadCommand(
        context=make_identity(),
        workspace_id=workspace.workspace_id,
        expected_workspace_version=0,
        idempotency_key="upload-key-closure",
        input_completeness=input_completeness,
        source_artifacts=roles,
        now=TS1,
    )
    from gateway_backend.domain.workspace.errors import UploadClosureInvalid

    with pytest.raises(UploadClosureInvalid):
        accept_upload(command=command, scope_resolution=scope_resolution, repository=repository)
