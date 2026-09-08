"""Preview application frozen binding and derived stale read-model tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from gateway_backend.application.workspace.contracts import StartPreviewCommand
from gateway_backend.application.workspace.errors import IdempotencyConflict, PreviewBindingConflict
from gateway_backend.application.workspace.preview import (
    build_preview_read_state,
    read_preview_result,
    validate_start_preview_binding,
)
from gateway_backend.domain.workspace.models import (
    BaselineHead,
    InputCompleteness,
    PreviewResult,
    PreviewResultDigests,
    SourceArtifactBinding,
    SourceArtifactRole,
    UploadRevision,
    Workspace,
)
from tests.support.workspace_fixtures import (
    FixedScopeResolutionPort,
    InMemoryWorkspaceRepository,
    MutableBaselineHeadReadPort,
    make_baseline_head,
    make_identity,
    seed_open_workspace,
)

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
TS1 = datetime(2024, 6, 1, 12, 10, 0, tzinfo=UTC)

BASELINE_HEAD = make_baseline_head(version=3, commit_id="commit-base")


def _seed_uploaded_workspace(
    repository: InMemoryWorkspaceRepository,
) -> tuple[Workspace, UploadRevision]:
    workspace = seed_open_workspace(repository, optimistic_version=1, generation=1)
    revision = UploadRevision(
        upload_revision_id="ur-1",
        workspace_id=workspace.workspace_id,
        generation=1,
        input_completeness=InputCompleteness.FULL,
        source_artifacts={
            SourceArtifactRole.INITIAL: SourceArtifactBinding(
                artifact_id="initial-1",
                media_type="application/gzip",
                size_bytes=1,
                raw_sha256="sha256:initial",
            ),
            SourceArtifactRole.MODIFIED: SourceArtifactBinding(
                artifact_id="modified-1",
                media_type="application/gzip",
                size_bytes=2,
                raw_sha256="sha256:modified",
            ),
        },
        idempotency_key="upload-key",
        request_fingerprint="fp-upload",
        created_by="actor-1",
        created_at=TS0,
    )
    repository.save_upload_revision(revision)
    updated = replace(workspace, current_upload_revision_id=revision.upload_revision_id)
    repository.save_workspace(updated, expected_version=workspace.optimistic_version)
    return updated, revision


def _preview_result(*, generation: int = 1) -> PreviewResult:
    return PreviewResult(
        preview_result_id="pr-1",
        workspace_id="ws-1",
        upload_revision_id="ur-1",
        generation=generation,
        repository_id="repo-1",
        business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version,
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
        created_at=TS1,
    )


def _start_preview_command(
    *,
    workspace_id: str,
    expected_workspace_version: int,
    generation: int = 1,
    upload_revision_id: str = "ur-1",
    idempotency_key: str = "preview-key-1",
) -> StartPreviewCommand:
    return StartPreviewCommand(
        context=make_identity(),
        workspace_id=workspace_id,
        expected_workspace_version=expected_workspace_version,
        upload_revision_id=upload_revision_id,
        generation=generation,
        expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
        idempotency_key=idempotency_key,
        request_fingerprint="fp-preview",
    )


def test_validate_start_preview_binding_accepts_current_workspace_input() -> None:
    repository = InMemoryWorkspaceRepository()
    workspace, revision = _seed_uploaded_workspace(repository)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=workspace.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    command = _start_preview_command(
        workspace_id=workspace.workspace_id,
        expected_workspace_version=workspace.optimistic_version,
    )

    result = validate_start_preview_binding(
        command=command,
        scope_resolution=scope_resolution,
        repository=repository,
    )

    assert result.replay is False
    assert result.upload_revision.upload_revision_id == revision.upload_revision_id
    assert result.baseline_head == BASELINE_HEAD


PREVIEW_BINDING_FAULTS = (
    (1, 2, "generation does not match current workspace generation"),
    (2, 1, "expected baseline head version does not match current head"),
)


@pytest.mark.parametrize(
    ("expected_baseline_head_version", "generation", "message"),
    PREVIEW_BINDING_FAULTS,
)
def test_validate_start_preview_binding_rejects_stale_or_mismatched_binding(
    expected_baseline_head_version: int,
    generation: int,
    message: str,
) -> None:
    repository = InMemoryWorkspaceRepository()
    workspace, _revision = _seed_uploaded_workspace(repository)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=workspace.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    command = StartPreviewCommand(
        context=make_identity(),
        workspace_id=workspace.workspace_id,
        expected_workspace_version=workspace.optimistic_version,
        upload_revision_id="ur-1",
        generation=generation,
        expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        expected_baseline_head_version=expected_baseline_head_version,
        idempotency_key="preview-key-binding",
        request_fingerprint="fp-preview",
    )
    with pytest.raises(PreviewBindingConflict, match=message):
        validate_start_preview_binding(
            command=command,
            scope_resolution=scope_resolution,
            repository=repository,
        )


def test_validate_start_preview_binding_replays_prior_preview_idempotency() -> None:
    repository = InMemoryWorkspaceRepository()
    workspace, _revision = _seed_uploaded_workspace(repository)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=workspace.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    prior = _preview_result()
    repository.save_preview_result(prior)
    repository.register_preview_idempotency(
        workspace_id=workspace.workspace_id,
        idempotency_key="preview-key-1",
        preview_result_id=prior.preview_result_id,
    )
    command = _start_preview_command(
        workspace_id=workspace.workspace_id,
        expected_workspace_version=workspace.optimistic_version,
    )

    result = validate_start_preview_binding(
        command=command,
        scope_resolution=scope_resolution,
        repository=repository,
    )

    assert result.replay is True
    assert result.prior_result == prior


def test_validate_start_preview_binding_conflicts_on_reused_preview_key_with_different_input() -> None:
    repository = InMemoryWorkspaceRepository()
    workspace, _revision = _seed_uploaded_workspace(repository)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=workspace.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    prior = _preview_result(generation=99)
    repository.save_preview_result(prior)
    repository.register_preview_idempotency(
        workspace_id=workspace.workspace_id,
        idempotency_key="preview-key-1",
        preview_result_id=prior.preview_result_id,
    )
    command = _start_preview_command(
        workspace_id=workspace.workspace_id,
        expected_workspace_version=workspace.optimistic_version,
    )

    with pytest.raises(IdempotencyConflict, match="preview-key-1"):
        validate_start_preview_binding(
            command=command,
            scope_resolution=scope_resolution,
            repository=repository,
        )


DERIVED_STALE_CASES = (
    (BASELINE_HEAD, False),
    (make_baseline_head(version=4, commit_id="commit-base"), True),
    (make_baseline_head(version=3, commit_id="commit-new"), True),
)


@pytest.mark.parametrize(("current_head", "expected_stale"), DERIVED_STALE_CASES)
def test_build_preview_read_state_derives_staleness_without_mutating_result(
    current_head: BaselineHead,
    expected_stale: bool,
) -> None:
    result = _preview_result()
    baseline_head_read = MutableBaselineHeadReadPort(heads={"repo-1": current_head})

    read_state = build_preview_read_state(
        result=result,
        baseline_head_read=baseline_head_read,
    )

    assert read_state.derived_stale is expected_stale
    assert read_state.submit_forbidden is expected_stale
    assert read_state.result is result


def test_read_preview_result_reauthorizes_scope_before_deriving_stale() -> None:
    repository = InMemoryWorkspaceRepository()
    workspace = seed_open_workspace(repository)
    result = replace(_preview_result(), workspace_id=workspace.workspace_id)
    repository.save_preview_result(result)
    baseline_head_read = MutableBaselineHeadReadPort(heads={"repo-1": BASELINE_HEAD})

    read_state = read_preview_result(
        context=make_identity(),
        preview_result_id=result.preview_result_id,
        workspace_id=workspace.workspace_id,
        repository=repository,
        baseline_head_read=baseline_head_read,
    )

    assert read_state.derived_stale is False
