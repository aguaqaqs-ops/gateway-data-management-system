"""Preview binding validation and derived stale read model."""

from __future__ import annotations

from gateway_backend.application.workspace.contracts import (
    PreviewReadState,
    StartPreviewCommand,
    StartPreviewValidationResult,
)
from gateway_backend.application.workspace.errors import IdempotencyConflict, PreviewBindingConflict
from gateway_backend.domain.workspace.errors import ScopeForbidden
from gateway_backend.domain.workspace.models import IdentityContext, PreviewResult
from gateway_backend.domain.workspace.policies import (
    assert_exact_scope,
    assert_permission,
    assert_workspace_open,
    assert_workspace_version_cas,
    derive_preview_staleness,
)
from gateway_backend.domain.workspace.ports import (
    BaselineHeadReadPort,
    ScopeResolutionPort,
    WorkspaceRepository,
)

PERMISSION_PREVIEW_WORKSPACE = "preview_workspace"
PERMISSION_WORKSPACE_READ = "workspace_read"


def validate_start_preview_binding(
    *,
    command: StartPreviewCommand,
    scope_resolution: ScopeResolutionPort,
    repository: WorkspaceRepository,
) -> StartPreviewValidationResult:
    assert_permission(command.context, PERMISSION_PREVIEW_WORKSPACE)
    resolved = scope_resolution.resolve(command.context)
    workspace = repository.get_workspace(command.workspace_id)
    if workspace is None:
        raise ScopeForbidden
    assert_exact_scope(workspace, command.context)
    assert_workspace_open(workspace)

    prior = repository.find_preview_idempotency(command.workspace_id, command.idempotency_key)
    if prior is not None:
        if prior.request_fingerprint != command.request_fingerprint:
            raise IdempotencyConflict(idempotency_key=command.idempotency_key)
        upload_revision = repository.get_upload_revision(prior.upload_revision_id)
        if upload_revision is None:
            raise PreviewBindingConflict("upload revision is missing")
        return StartPreviewValidationResult(
            workspace=workspace,
            upload_revision=upload_revision,
            baseline_head=resolved.baseline_head,
            replay=True,
            prior_acceptance=prior,
        )

    assert_workspace_version_cas(workspace, command.expected_workspace_version)

    if workspace.current_upload_revision_id != command.upload_revision_id:
        raise PreviewBindingConflict("upload_revision_id does not match current workspace input")
    if workspace.generation != command.generation:
        raise PreviewBindingConflict("generation does not match current workspace generation")

    upload_revision = repository.get_upload_revision(command.upload_revision_id)
    if upload_revision is None:
        raise PreviewBindingConflict("upload revision is missing")
    if upload_revision.workspace_id != workspace.workspace_id:
        raise PreviewBindingConflict("upload revision belongs to a different workspace")
    if upload_revision.generation != command.generation:
        raise PreviewBindingConflict("upload revision generation does not match request")

    baseline_head = resolved.baseline_head
    if baseline_head.business_baseline_node_id != command.expected_baseline_node_id:
        raise PreviewBindingConflict("expected baseline node does not match current BaselineHead")
    if baseline_head.baseline_head_version != command.expected_baseline_head_version:
        raise PreviewBindingConflict("expected baseline head version does not match current head")

    return StartPreviewValidationResult(
        workspace=workspace,
        upload_revision=upload_revision,
        baseline_head=baseline_head,
        replay=False,
        prior_acceptance=None,
    )


def build_preview_read_state(
    *,
    result: PreviewResult,
    baseline_head_read: BaselineHeadReadPort,
    context_permission_checked: bool = False,
) -> PreviewReadState:
    del context_permission_checked  # caller performs current-session authorization in S3
    current_head = baseline_head_read.get_current_head(result.repository_id)
    derived_stale = derive_preview_staleness(result, current_head)
    return PreviewReadState(
        result=result,
        derived_stale=derived_stale,
        submit_forbidden=derived_stale,
    )


def read_preview_result(
    *,
    context: IdentityContext,
    preview_result_id: str,
    workspace_id: str,
    repository: WorkspaceRepository,
    baseline_head_read: BaselineHeadReadPort,
) -> PreviewReadState:
    assert_permission(context, PERMISSION_WORKSPACE_READ)
    workspace = repository.get_workspace(workspace_id)
    if workspace is None:
        raise ScopeForbidden
    assert_exact_scope(workspace, context)
    result = repository.get_preview_result(preview_result_id)
    if result is None or result.workspace_id != workspace_id:
        raise ScopeForbidden
    return build_preview_read_state(result=result, baseline_head_read=baseline_head_read)
