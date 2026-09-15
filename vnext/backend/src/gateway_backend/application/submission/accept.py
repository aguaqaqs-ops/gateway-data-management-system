"""AcceptSubmit pre-transaction validation."""

from __future__ import annotations

from gateway_backend.application.submission.contracts import (
    AcceptSubmitCommand,
    AcceptSubmitValidationResult,
    assert_preview_ready_closure_digest,
    compute_new_accept_fingerprint,
    compute_replay_accept_fingerprint,
    preview_canonical_business_digest,
)
from gateway_backend.application.submission.errors import (
    BaselineVersionConflict,
    IdempotencyConflict,
    NoCanonicalChange,
    PreviewBindingConflict,
    PreviewDerivedStale,
    SubmitOccupancyConflict,
)
from gateway_backend.application.submission.ports import (
    BaselineCanonicalDigestPort,
    RepositoryMainResolvePort,
    SubmitOccupancyReadPort,
    SubmissionRepository,
)
from gateway_backend.domain.workspace.errors import ScopeForbidden
from gateway_backend.domain.workspace.models import BaselineHead, PreviewResult, UploadRevision, Workspace
from gateway_backend.domain.workspace.policies import (
    assert_exact_scope,
    assert_permission,
    assert_workspace_open,
    assert_workspace_version_cas,
    derive_preview_staleness,
)
from gateway_backend.domain.workspace.ports import ScopeResolutionPort, WorkspaceRepository

PERMISSION_UPLOAD_SUBMIT = "upload_submit_workspace"


def validate_accept_submit(
    *,
    command: AcceptSubmitCommand,
    scope_resolution: ScopeResolutionPort,
    workspace_repository: WorkspaceRepository,
    submission_repository: SubmissionRepository,
    occupancy: SubmitOccupancyReadPort,
    baseline_digest: BaselineCanonicalDigestPort,
    main_resolve: RepositoryMainResolvePort | None = None,
    snapshot_table_artifact_refs: tuple[str, ...] = (),
    preview_ready_closure_digest: str,
) -> AcceptSubmitValidationResult:
    assert_permission(command.context, PERMISSION_UPLOAD_SUBMIT)
    resolved = scope_resolution.resolve(command.context)
    replay = try_accept_submit_replay(
        command=command,
        workspace_repository=workspace_repository,
        submission_repository=submission_repository,
        resolved_repository_id=resolved.repository_id,
        baseline_head=resolved.baseline_head,
    )
    if replay is not None:
        return replay

    workspace = workspace_repository.get_workspace(command.workspace_id)
    if workspace is None:
        raise ScopeForbidden
    assert_exact_scope(workspace, command.context)
    _assert_resolved_repository_matches_workspace(resolved.repository_id, workspace)
    assert_workspace_open(workspace)
    assert_workspace_version_cas(workspace, command.expected_workspace_version)
    _assert_preview_binding(workspace, command)
    upload_revision = _load_upload_revision(workspace_repository, command)
    preview_result = _load_preview_result(workspace_repository, command, upload_revision, workspace)
    baseline_head = resolved.baseline_head
    _assert_baseline_binding(command, baseline_head)
    if derive_preview_staleness(preview_result, baseline_head):
        raise PreviewDerivedStale

    preview_digest = preview_canonical_business_digest(preview_result)
    baseline_canonical_digest = baseline_digest.get_baseline_canonical_digest(
        repository_id=workspace.repository_id,
        baseline_head=baseline_head,
    )
    if preview_digest == baseline_canonical_digest:
        raise NoCanonicalChange

    _assert_no_submit_occupancy(occupancy, workspace.workspace_id, workspace.repository_id)
    assert_preview_ready_closure_digest(preview_ready_closure_digest)

    if main_resolve is None:
        raise PreviewBindingConflict("repository main resolve port is required for new accepts")
    repository_expected_commit_id = main_resolve.resolve_main_expected_commit(
        repository_id=workspace.repository_id
    )
    request_fingerprint = compute_new_accept_fingerprint(
        command=command,
        workspace=workspace,
        preview_result=preview_result,
        upload_revision=upload_revision,
        baseline_head=baseline_head,
        repository_expected_commit_id=repository_expected_commit_id,
        snapshot_table_artifact_refs=snapshot_table_artifact_refs,
        preview_ready_closure_digest=preview_ready_closure_digest,
    )
    return AcceptSubmitValidationResult(
        workspace=workspace,
        upload_revision=upload_revision,
        preview_result=preview_result,
        baseline_head=baseline_head,
        repository_expected_commit_id=repository_expected_commit_id,
        canonical_business_digest=preview_digest,
        accept_request_fingerprint=request_fingerprint,
        replay=False,
        prior_attempt=None,
    )


def try_accept_submit_replay(
    *,
    command: AcceptSubmitCommand,
    workspace_repository: WorkspaceRepository,
    submission_repository: SubmissionRepository,
    resolved_repository_id: str,
    baseline_head: BaselineHead,
) -> AcceptSubmitValidationResult | None:
    workspace = workspace_repository.get_workspace(command.workspace_id)
    if workspace is None:
        raise ScopeForbidden
    assert_exact_scope(workspace, command.context)
    _assert_resolved_repository_matches_workspace(resolved_repository_id, workspace)

    prior_record = submission_repository.find_submit_idempotency(
        command.workspace_id,
        command.idempotency_key,
    )
    if prior_record is None:
        return None
    prior_attempt = submission_repository.get_submit_attempt(prior_record.submit_attempt_id)
    if prior_attempt is None:
        raise PreviewBindingConflict("submit attempt is missing")
    _assert_replay_binding_matches_attempt(command, prior_attempt)
    replay_fingerprint = compute_replay_accept_fingerprint(
        command=command,
        attempt=prior_attempt,
        workspace=workspace,
    )
    if replay_fingerprint != prior_record.request_fingerprint:
        raise IdempotencyConflict(idempotency_key=command.idempotency_key)
    upload_revision = workspace_repository.get_upload_revision(prior_attempt.upload_revision_id)
    if upload_revision is None:
        raise PreviewBindingConflict("upload revision is missing")
    preview_result = workspace_repository.get_preview_result(prior_attempt.preview_result_id)
    if preview_result is None:
        raise PreviewBindingConflict("preview result is missing")
    _assert_preview_repository_matches_workspace(preview_result, workspace)
    return AcceptSubmitValidationResult(
        workspace=workspace,
        upload_revision=upload_revision,
        preview_result=preview_result,
        baseline_head=baseline_head,
        repository_expected_commit_id=prior_attempt.repository_expected_commit_id,
        canonical_business_digest=prior_attempt.canonical_business_digest,
        accept_request_fingerprint=replay_fingerprint,
        replay=True,
        prior_attempt=prior_attempt,
    )


def preflight_new_accept_submit(
    *,
    command: AcceptSubmitCommand,
    workspace_repository: WorkspaceRepository,
    occupancy: SubmitOccupancyReadPort,
    resolved_repository_id: str,
    baseline_head: BaselineHead,
    baseline_digest: BaselineCanonicalDigestPort,
    snapshot_table_artifact_refs: tuple[str, ...] = (),
    preview_ready_closure_digest: str,
) -> str:
    """Read-only §6.1 steps 3-5 guards for new-key accepts (no writer lock)."""
    workspace = workspace_repository.get_workspace(command.workspace_id)
    if workspace is None:
        raise ScopeForbidden
    assert_exact_scope(workspace, command.context)
    _assert_resolved_repository_matches_workspace(resolved_repository_id, workspace)
    assert_workspace_open(workspace)
    assert_workspace_version_cas(workspace, command.expected_workspace_version)
    _assert_preview_binding(workspace, command)
    upload_revision = _load_upload_revision(workspace_repository, command)
    preview_result = _load_preview_result(workspace_repository, command, upload_revision, workspace)
    _assert_baseline_binding(command, baseline_head)
    if derive_preview_staleness(preview_result, baseline_head):
        raise PreviewDerivedStale

    preview_digest = preview_canonical_business_digest(preview_result)
    baseline_canonical_digest = baseline_digest.get_baseline_canonical_digest(
        repository_id=workspace.repository_id,
        baseline_head=baseline_head,
    )
    if preview_digest == baseline_canonical_digest:
        raise NoCanonicalChange

    _assert_no_submit_occupancy(occupancy, workspace.workspace_id, workspace.repository_id)
    assert_preview_ready_closure_digest(preview_ready_closure_digest)
    return baseline_canonical_digest


def validate_accept_submit_with_frozen(
    *,
    command: AcceptSubmitCommand,
    workspace_repository: WorkspaceRepository,
    submission_repository: SubmissionRepository,
    occupancy: SubmitOccupancyReadPort,
    resolved_repository_id: str,
    baseline_head: BaselineHead,
    baseline_canonical_digest: str,
    repository_expected_commit_id: str,
    snapshot_table_artifact_refs: tuple[str, ...] = (),
    preview_ready_closure_digest: str,
) -> AcceptSubmitValidationResult:
    replay = try_accept_submit_replay(
        command=command,
        workspace_repository=workspace_repository,
        submission_repository=submission_repository,
        resolved_repository_id=resolved_repository_id,
        baseline_head=baseline_head,
    )
    if replay is not None:
        return replay

    workspace = workspace_repository.get_workspace(command.workspace_id)
    if workspace is None:
        raise ScopeForbidden
    assert_exact_scope(workspace, command.context)
    _assert_resolved_repository_matches_workspace(resolved_repository_id, workspace)
    assert_workspace_open(workspace)
    assert_workspace_version_cas(workspace, command.expected_workspace_version)
    _assert_preview_binding(workspace, command)
    upload_revision = _load_upload_revision(workspace_repository, command)
    preview_result = _load_preview_result(workspace_repository, command, upload_revision, workspace)
    _assert_baseline_binding(command, baseline_head)
    if derive_preview_staleness(preview_result, baseline_head):
        raise PreviewDerivedStale

    preview_digest = preview_canonical_business_digest(preview_result)
    if preview_digest == baseline_canonical_digest:
        raise NoCanonicalChange

    _assert_no_submit_occupancy(occupancy, workspace.workspace_id, workspace.repository_id)
    assert_preview_ready_closure_digest(preview_ready_closure_digest)
    request_fingerprint = compute_new_accept_fingerprint(
        command=command,
        workspace=workspace,
        preview_result=preview_result,
        upload_revision=upload_revision,
        baseline_head=baseline_head,
        repository_expected_commit_id=repository_expected_commit_id,
        snapshot_table_artifact_refs=snapshot_table_artifact_refs,
        preview_ready_closure_digest=preview_ready_closure_digest,
    )
    return AcceptSubmitValidationResult(
        workspace=workspace,
        upload_revision=upload_revision,
        preview_result=preview_result,
        baseline_head=baseline_head,
        repository_expected_commit_id=repository_expected_commit_id,
        canonical_business_digest=preview_digest,
        accept_request_fingerprint=request_fingerprint,
        replay=False,
        prior_attempt=None,
    )


def _assert_resolved_repository_matches_workspace(
    resolved_repository_id: str,
    workspace: Workspace,
) -> None:
    if resolved_repository_id != workspace.repository_id:
        raise ScopeForbidden


def _assert_preview_repository_matches_workspace(
    preview_result: PreviewResult,
    workspace: Workspace,
) -> None:
    if preview_result.repository_id != workspace.repository_id:
        raise PreviewBindingConflict("preview result repository does not match workspace")


def _assert_replay_binding_matches_attempt(
    command: AcceptSubmitCommand,
    attempt: object,
) -> None:
    from gateway_backend.domain.submission.models import SubmitAttempt

    if not isinstance(attempt, SubmitAttempt):
        raise TypeError("attempt must be SubmitAttempt")
    if command.upload_revision_id != attempt.upload_revision_id:
        raise IdempotencyConflict(idempotency_key=command.idempotency_key)
    if command.preview_result_id != attempt.preview_result_id:
        raise IdempotencyConflict(idempotency_key=command.idempotency_key)
    if command.generation != attempt.workspace_generation:
        raise IdempotencyConflict(idempotency_key=command.idempotency_key)
    if command.expected_baseline_node_id != attempt.business_baseline_node_id:
        raise IdempotencyConflict(idempotency_key=command.idempotency_key)
    if command.expected_baseline_head_version != attempt.baseline_head_version:
        raise IdempotencyConflict(idempotency_key=command.idempotency_key)


def _assert_preview_binding(workspace: Workspace, command: AcceptSubmitCommand) -> None:
    if workspace.current_upload_revision_id != command.upload_revision_id:
        raise PreviewBindingConflict("upload_revision_id does not match current workspace input")
    if workspace.current_preview_result_id != command.preview_result_id:
        raise PreviewBindingConflict("preview_result_id does not match current workspace preview")
    if workspace.generation != command.generation:
        raise PreviewBindingConflict("generation does not match current workspace generation")


def _load_upload_revision(
    workspace_repository: WorkspaceRepository,
    command: AcceptSubmitCommand,
) -> UploadRevision:
    upload_revision = workspace_repository.get_upload_revision(command.upload_revision_id)
    if upload_revision is None:
        raise PreviewBindingConflict("upload revision is missing")
    if upload_revision.workspace_id != command.workspace_id:
        raise PreviewBindingConflict("upload revision belongs to a different workspace")
    if upload_revision.generation != command.generation:
        raise PreviewBindingConflict("upload revision generation does not match request")
    return upload_revision


def _load_preview_result(
    workspace_repository: WorkspaceRepository,
    command: AcceptSubmitCommand,
    upload_revision: UploadRevision,
    workspace: Workspace,
) -> PreviewResult:
    preview_result = workspace_repository.get_preview_result(command.preview_result_id)
    if preview_result is None:
        raise PreviewBindingConflict("preview result is missing")
    if preview_result.workspace_id != command.workspace_id:
        raise PreviewBindingConflict("preview result belongs to a different workspace")
    if preview_result.upload_revision_id != upload_revision.upload_revision_id:
        raise PreviewBindingConflict("preview result upload revision does not match request")
    if preview_result.generation != command.generation:
        raise PreviewBindingConflict("preview result generation does not match request")
    _assert_preview_repository_matches_workspace(preview_result, workspace)
    return preview_result


def _assert_baseline_binding(command: AcceptSubmitCommand, baseline_head: object) -> None:
    from gateway_backend.domain.workspace.models import BaselineHead

    if not isinstance(baseline_head, BaselineHead):
        raise TypeError("baseline_head must be BaselineHead")
    if baseline_head.business_baseline_node_id != command.expected_baseline_node_id:
        raise BaselineVersionConflict("expected baseline node does not match current BaselineHead")
    if baseline_head.baseline_head_version != command.expected_baseline_head_version:
        raise BaselineVersionConflict(
            "expected baseline head version does not match current BaselineHead"
        )


def _assert_no_submit_occupancy(
    occupancy: SubmitOccupancyReadPort,
    workspace_id: str,
    repository_id: str,
) -> None:
    workspace_occupancy = occupancy.get_workspace_occupancy(workspace_id)
    if workspace_occupancy is not None:
        raise SubmitOccupancyConflict("workspace submit occupancy is already held")
    repository_occupancy = occupancy.get_repository_occupancy(repository_id)
    if repository_occupancy is not None:
        raise SubmitOccupancyConflict("repository submit occupancy is already held")
