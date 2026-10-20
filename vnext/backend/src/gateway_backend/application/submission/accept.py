"""AcceptSubmit pre-transaction validation."""

from __future__ import annotations

from dataclasses import dataclass

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
    ProjectIdentityConfirmationMismatch,
    ProjectIdentityConfirmationRequired,
    SubmitOccupancyConflict,
)
from gateway_backend.application.submission.ports import (
    RepositoryMainResolvePort,
    SubmitControlTransaction,
    SubmitOccupancyReadPort,
    SubmissionRepository,
)
from gateway_backend.domain.workspace.errors import ScopeForbidden, ScopeResolutionError
from gateway_backend.domain.workspace.models import (
    BaselineHead,
    PreviewResult,
    ResolvedScope,
    UploadRevision,
    Workspace,
    ProjectIdentityStatus,
)
from gateway_backend.domain.submission.models import IdentityConfirmationAction
from gateway_backend.domain.workspace.policies import (
    assert_exact_scope,
    assert_permission,
    assert_workspace_open,
    assert_workspace_version_cas,
    derive_preview_staleness,
)
from gateway_backend.domain.workspace.ports import ScopeResolutionPort, WorkspaceRepository

PERMISSION_UPLOAD_SUBMIT = "upload_submit_workspace"


@dataclass(frozen=True, slots=True)
class AcceptPreflightLoadedFacts:
    workspace: Workspace
    upload_revision: UploadRevision
    preview_result: PreviewResult
    resolved_repository_id: str
    baseline_head: BaselineHead
    workspace_occupancy_held: bool
    repository_occupancy_held: bool
    preview_ready_closure_digest: str
    current_storage_projection_ruleset_digest: str


def validate_accept_submit(
    *,
    command: AcceptSubmitCommand,
    scope_resolution: ScopeResolutionPort,
    workspace_repository: WorkspaceRepository,
    submission_repository: SubmissionRepository,
    occupancy: SubmitOccupancyReadPort,
    main_resolve: RepositoryMainResolvePort | None = None,
    current_storage_projection_ruleset_digest: str,
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
    if derive_preview_staleness(
        preview_result,
        baseline_head,
        current_storage_projection_ruleset_digest,
    ):
        raise PreviewDerivedStale

    preview_digest = preview_canonical_business_digest(preview_result)
    if preview_result.canonical.baseline_canonical_state_digest.value == preview_digest:
        raise NoCanonicalChange

    _assert_identity_confirmations(command, preview_result)

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
    frozen_baseline_head = BaselineHead(
        business_baseline_node_id=prior_attempt.business_baseline_node_id,
        business_baseline_commit_id=prior_attempt.business_baseline_commit_id,
        baseline_head_version=prior_attempt.baseline_head_version,
    )
    return AcceptSubmitValidationResult(
        workspace=workspace,
        upload_revision=upload_revision,
        preview_result=preview_result,
        baseline_head=frozen_baseline_head,
        repository_expected_commit_id=prior_attempt.repository_expected_commit_id,
        canonical_business_digest=prior_attempt.canonical_business_digest,
        accept_request_fingerprint=replay_fingerprint,
        replay=True,
        prior_attempt=prior_attempt,
    )


def load_new_accept_preflight_facts(
    *,
    command: AcceptSubmitCommand,
    workspace_repository: WorkspaceRepository,
    occupancy: SubmitOccupancyReadPort,
    resolved_repository_id: str,
    baseline_head: BaselineHead,
    preview_ready_closure_digest: str,
    current_storage_projection_ruleset_digest: str,
) -> AcceptPreflightLoadedFacts:
    """Load control-DB facts for new-key accepts inside a SQLite read transaction."""
    workspace = workspace_repository.get_workspace(command.workspace_id)
    if workspace is None:
        raise ScopeForbidden
    upload_revision = _load_upload_revision(workspace_repository, command)
    preview_result = _load_preview_result(workspace_repository, command, upload_revision, workspace)
    workspace_occupancy = occupancy.get_workspace_occupancy(workspace.workspace_id)
    repository_occupancy = occupancy.get_repository_occupancy(workspace.repository_id)
    return AcceptPreflightLoadedFacts(
        workspace=workspace,
        upload_revision=upload_revision,
        preview_result=preview_result,
        resolved_repository_id=resolved_repository_id,
        baseline_head=baseline_head,
        workspace_occupancy_held=workspace_occupancy is not None,
        repository_occupancy_held=repository_occupancy is not None,
        preview_ready_closure_digest=preview_ready_closure_digest,
        current_storage_projection_ruleset_digest=current_storage_projection_ruleset_digest,
    )


def evaluate_new_accept_preflight_local_guards(
    *,
    command: AcceptSubmitCommand,
    loaded: AcceptPreflightLoadedFacts,
) -> None:
    """Pure local §6.1 guards that do not require baseline/main port I/O."""
    workspace = loaded.workspace
    assert_exact_scope(workspace, command.context)
    _assert_resolved_repository_matches_workspace(loaded.resolved_repository_id, workspace)
    assert_workspace_open(workspace)
    assert_workspace_version_cas(workspace, command.expected_workspace_version)
    _assert_preview_binding(workspace, command)
    _assert_baseline_binding(command, loaded.baseline_head)
    if derive_preview_staleness(
        loaded.preview_result,
        loaded.baseline_head,
        loaded.current_storage_projection_ruleset_digest,
    ):
        raise PreviewDerivedStale


def assert_accept_preflight_post_noop_guards(
    *,
    loaded: AcceptPreflightLoadedFacts,
) -> None:
    """§6.1 occupancy/closure guards after NO_CANONICAL_CHANGE is excluded."""
    if loaded.workspace_occupancy_held:
        raise SubmitOccupancyConflict("workspace submit occupancy is already held")
    if loaded.repository_occupancy_held:
        raise SubmitOccupancyConflict("repository submit occupancy is already held")
    assert_preview_ready_closure_digest(loaded.preview_ready_closure_digest)


def assert_no_canonical_change(*, loaded: AcceptPreflightLoadedFacts) -> None:
    preview_digest = preview_canonical_business_digest(loaded.preview_result)
    if loaded.preview_result.canonical.baseline_canonical_state_digest.value == preview_digest:
        raise NoCanonicalChange


def _assert_identity_confirmations(
    command: AcceptSubmitCommand,
    preview_result: PreviewResult,
) -> None:
    required_actions: set[IdentityConfirmationAction] = set()
    if any(pair.status is ProjectIdentityStatus.DIFFERENT_PROJECT for pair in preview_result.identity_pairs):
        required_actions.add(IdentityConfirmationAction.ACCEPT_DATASET_REPLACEMENT)
    if any(pair.status is ProjectIdentityStatus.UNVERIFIABLE for pair in preview_result.identity_pairs):
        required_actions.add(IdentityConfirmationAction.ACCEPT_UNVERIFIABLE_DETAILED_RESULT)

    supplied = {item.action: item for item in command.identity_confirmations}
    if not required_actions.issubset(supplied):
        raise ProjectIdentityConfirmationRequired
    if set(supplied) != required_actions or any(
        item.assessment_set_digest != preview_result.identity_assessment_set_digest.value
        for item in supplied.values()
    ):
        raise ProjectIdentityConfirmationMismatch


def evaluate_new_accept_preflight(
    *,
    command: AcceptSubmitCommand,
    loaded: AcceptPreflightLoadedFacts,
) -> None:
    """Pure preflight guards after control-DB facts are materialized."""
    evaluate_new_accept_preflight_local_guards(command=command, loaded=loaded)
    assert_no_canonical_change(loaded=loaded)
    _assert_identity_confirmations(command, loaded.preview_result)
    assert_accept_preflight_post_noop_guards(loaded=loaded)


def validate_accept_submit_with_frozen(
    *,
    command: AcceptSubmitCommand,
    unit_of_work: SubmitControlTransaction,
    preflight_baseline_head: BaselineHead,
    repository_expected_commit_id: str,
    current_storage_projection_ruleset_digest: str,
    preview_ready_closure_digest: str,
) -> AcceptSubmitValidationResult:
    workspace_repository = unit_of_work.workspace
    submission_repository = unit_of_work.submission
    occupancy = unit_of_work.submission
    fresh_scope = _resolve_fresh_provisioned_scope(unit_of_work, command)

    prior_record = submission_repository.find_submit_idempotency(
        command.workspace_id,
        command.idempotency_key,
    )
    if prior_record is not None:
        workspace = workspace_repository.get_workspace(command.workspace_id)
        if workspace is None:
            raise ScopeForbidden
        assert_exact_scope(workspace, command.context)
        _assert_fresh_mapping_authorization(fresh_scope, workspace)
        replay = try_accept_submit_replay(
            command=command,
            workspace_repository=workspace_repository,
            submission_repository=submission_repository,
            resolved_repository_id=fresh_scope.repository_id,
            baseline_head=preflight_baseline_head,
        )
        if replay is None:
            raise PreviewBindingConflict("submit replay validation failed")
        return replay

    baseline_head = fresh_scope.baseline_head

    workspace = workspace_repository.get_workspace(command.workspace_id)
    if workspace is None:
        raise ScopeForbidden
    assert_exact_scope(workspace, command.context)
    _assert_fresh_mapping_authorization(fresh_scope, workspace)
    assert_workspace_open(workspace)
    assert_workspace_version_cas(workspace, command.expected_workspace_version)
    _assert_preview_binding(workspace, command)
    upload_revision = _load_upload_revision(workspace_repository, command)
    preview_result = _load_preview_result(workspace_repository, command, upload_revision, workspace)
    _assert_baseline_binding(command, baseline_head)
    _assert_baseline_heads_match(baseline_head, preflight_baseline_head)
    _assert_preview_baseline_binding(preview_result, baseline_head)
    if derive_preview_staleness(
        preview_result,
        baseline_head,
        current_storage_projection_ruleset_digest,
    ):
        raise PreviewDerivedStale

    preview_digest = preview_canonical_business_digest(preview_result)
    if preview_result.canonical.baseline_canonical_state_digest.value == preview_digest:
        raise NoCanonicalChange

    _assert_identity_confirmations(command, preview_result)

    _assert_no_submit_occupancy(occupancy, workspace.workspace_id, workspace.repository_id)
    assert_preview_ready_closure_digest(preview_ready_closure_digest)
    request_fingerprint = compute_new_accept_fingerprint(
        command=command,
        workspace=workspace,
        preview_result=preview_result,
        upload_revision=upload_revision,
        baseline_head=baseline_head,
        repository_expected_commit_id=repository_expected_commit_id,
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


def _resolve_fresh_provisioned_scope(
    unit_of_work: SubmitControlTransaction,
    command: AcceptSubmitCommand,
) -> ResolvedScope:
    try:
        return unit_of_work.resolve_provisioned_scope(
            gateway_device_external_key=command.context.gateway_device_external_key,
            business_project_id=command.context.business_project_id,
        )
    except ScopeResolutionError:
        raise ScopeForbidden


def _assert_fresh_mapping_authorization(fresh_scope: ResolvedScope, workspace: Workspace) -> None:
    _assert_resolved_repository_matches_workspace(fresh_scope.repository_id, workspace)


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


def _assert_baseline_heads_match(current: BaselineHead, expected: BaselineHead) -> None:
    if current.business_baseline_node_id != expected.business_baseline_node_id:
        raise BaselineVersionConflict("current BaselineHead node does not match preflight Head")
    if current.business_baseline_commit_id != expected.business_baseline_commit_id:
        raise BaselineVersionConflict("current BaselineHead commit does not match preflight Head")
    if current.baseline_head_version != expected.baseline_head_version:
        raise BaselineVersionConflict("current BaselineHead version does not match preflight Head")


def _assert_preview_baseline_binding(preview_result: PreviewResult, baseline_head: BaselineHead) -> None:
    if preview_result.business_baseline_node_id != baseline_head.business_baseline_node_id:
        raise PreviewBindingConflict("preview baseline node does not match current BaselineHead")
    if preview_result.business_baseline_commit_id != baseline_head.business_baseline_commit_id:
        raise PreviewBindingConflict("preview baseline commit does not match current BaselineHead")
    if preview_result.baseline_head_version != baseline_head.baseline_head_version:
        raise PreviewBindingConflict("preview baseline version does not match current BaselineHead")


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
