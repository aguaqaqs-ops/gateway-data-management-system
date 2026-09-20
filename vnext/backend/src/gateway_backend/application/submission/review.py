"""Review application services."""

from __future__ import annotations

from dataclasses import dataclass

from gateway_backend.application.submission.errors import (
    IdempotencyConflict,
    ReviewIntegrityFailure,
    ReviewWorkspaceOccupancyConflict,
)
from gateway_backend.application.submission.review_contracts import (
    ApplyReviewCommand,
    ApplyReviewResult,
    ReviewFacts,
    build_apply_review_request_fingerprint_from_command,
    compute_review_apply_request_fingerprint,
)
from gateway_backend.application.submission.ports import (
    ReviewApplyTransaction,
    WorkspaceControlUnitOfWorkFactory,
)
from gateway_backend.domain.submission.errors import ReviewClosureViolation
from gateway_backend.domain.submission.models import Submission, WorkspaceSubmitOccupancy
from gateway_backend.domain.submission.review import (
    ReviewAction,
    ReviewEvent,
    ReviewIdempotencyRecord,
    ReviewProjection,
    review_action_for_event_kind,
)
from gateway_backend.domain.workspace.errors import ScopeForbidden, ScopeResolutionError, WorkspaceNotOpen
from gateway_backend.domain.workspace.models import IdentityContext, ResolvedScope, Workspace
from gateway_backend.domain.workspace.policies import assert_permission, assert_workspace_open
from gateway_backend.domain.workspace.ports import ScopeResolutionPort

PERMISSION_REVIEW_SUBMISSION = "review_submission"

_RELEASE_ACTIONS = frozenset(
    {
        ReviewAction.REJECT,
        ReviewAction.RETURN_FOR_REVISION,
        ReviewAction.WITHDRAW,
    }
)


@dataclass(frozen=True, slots=True)
class ReviewScopeFacts:
    submission: Submission
    workspace: Workspace
    projection: ReviewProjection
    events: tuple[ReviewEvent, ...]
    occupancy: WorkspaceSubmitOccupancy | None


def is_review_release_action(action: ReviewAction) -> bool:
    return action in _RELEASE_ACTIONS


def assert_review_scope(
    submission: Submission,
    workspace: Workspace,
    resolved_scope: ResolvedScope,
    context: IdentityContext,
) -> None:
    if context.gateway_device_external_key != workspace.gateway_device_external_key:
        raise ScopeForbidden
    if context.business_project_id != workspace.business_project_id:
        raise ScopeForbidden
    if resolved_scope.repository_id != workspace.repository_id:
        raise ScopeForbidden
    if submission.repository_id != workspace.repository_id:
        raise ScopeForbidden
    if submission.workspace_id != workspace.workspace_id:
        raise ScopeForbidden


def assert_review_workspace_bindings(
    submission: Submission,
    workspace: Workspace,
    occupancy: WorkspaceSubmitOccupancy | None,
) -> None:
    try:
        assert_workspace_open(workspace)
    except WorkspaceNotOpen:
        raise ReviewWorkspaceOccupancyConflict("workspace is not open") from None
    if workspace.generation != submission.workspace_generation:
        raise ReviewWorkspaceOccupancyConflict(
            "workspace generation does not match submission"
        )
    if workspace.current_upload_revision_id != submission.upload_revision_id:
        raise ReviewWorkspaceOccupancyConflict(
            "workspace upload revision does not match submission"
        )
    if workspace.current_preview_result_id != submission.preview_result_id:
        raise ReviewWorkspaceOccupancyConflict(
            "workspace preview result does not match submission"
        )
    if occupancy is None or occupancy.active_submission_id != submission.submission_id:
        raise ReviewWorkspaceOccupancyConflict(
            "workspace submit occupancy does not match submission"
        )


def rebuild_apply_review_result_from_event(
    event: ReviewEvent,
    *,
    request_fingerprint: str,
) -> ApplyReviewResult:
    projection = ReviewProjection(
        submission_id=event.submission_id,
        status=event.to_status,
        optimistic_version=event.sequence,
        latest_sequence=event.sequence,
        updated_by=event.actor_id,
        updated_at=event.occurred_at,
    )
    return ApplyReviewResult(
        event=event,
        projection=projection,
        request_fingerprint=request_fingerprint,
        replay=True,
    )


def verify_idempotency_replay(
    record: ReviewIdempotencyRecord,
    *,
    command: ApplyReviewCommand,
    record_workspace: Workspace,
    request_workspace: Workspace,
    request_repository_id: str,
    events: tuple[ReviewEvent, ...],
) -> ApplyReviewResult:
    bound_event = next((event for event in events if event.sequence == record.event_sequence), None)
    if bound_event is None:
        raise ReviewIntegrityFailure("review idempotency record points to a missing event")
    if bound_event.submission_id != record.submission_id:
        raise ReviewIntegrityFailure(
            "review idempotency record submission_id does not match bound event"
        )
    if record.business_project_id != record_workspace.business_project_id:
        raise ReviewIntegrityFailure(
            "review idempotency record business project does not match workspace"
        )
    action = review_action_for_event_kind(bound_event.event_kind)
    if action is None:
        raise ReviewIntegrityFailure("review idempotency record is bound to a non-user event")
    if bound_event.sequence < 1:
        raise ReviewIntegrityFailure("review idempotency record is bound to a seed event")
    replay_fingerprint = compute_review_apply_request_fingerprint(
        action=action,
        business_project_id=record.business_project_id,
        expected_review_version=bound_event.sequence - 1,
        gateway_device_external_key=record_workspace.gateway_device_external_key,
        reason=bound_event.reason,
        repository_id=record_workspace.repository_id,
        submission_id=record.submission_id,
        workspace_id=record_workspace.workspace_id,
    )
    if replay_fingerprint != record.request_fingerprint:
        raise ReviewIntegrityFailure("review idempotency record fingerprint does not match event")
    if record.submission_id != command.submission_id:
        raise IdempotencyConflict(idempotency_key=command.idempotency_key)
    request_fingerprint = build_apply_review_request_fingerprint_from_command(
        command=command,
        workspace_id=request_workspace.workspace_id,
        repository_id=request_repository_id,
    )
    if record.request_fingerprint != request_fingerprint:
        raise IdempotencyConflict(idempotency_key=command.idempotency_key)
    return rebuild_apply_review_result_from_event(
        bound_event,
        request_fingerprint=record.request_fingerprint,
    )


def resolve_fresh_provisioned_scope(
    unit_of_work: ReviewApplyTransaction,
    context: IdentityContext,
) -> ResolvedScope:
    try:
        return unit_of_work.resolve_provisioned_scope(
            gateway_device_external_key=context.gateway_device_external_key,
            business_project_id=context.business_project_id,
        )
    except ScopeResolutionError:
        raise ScopeForbidden from None


def assert_fresh_scope_matches(fresh_scope: ResolvedScope, expected_scope: ResolvedScope) -> None:
    if fresh_scope.repository_id != expected_scope.repository_id:
        raise ScopeForbidden
    if fresh_scope.baseline_head != expected_scope.baseline_head:
        raise ScopeForbidden


def load_review_scope_facts(
    unit_of_work: ReviewApplyTransaction,
    *,
    context: IdentityContext,
    submission_id: str,
    resolved_scope: ResolvedScope | None = None,
) -> ReviewScopeFacts:
    fresh_scope = resolved_scope or resolve_fresh_provisioned_scope(unit_of_work, context)
    submission = unit_of_work.submission.get_submission(submission_id)
    if submission is None:
        raise ScopeForbidden
    workspace = unit_of_work.workspace.get_workspace(submission.workspace_id)
    if workspace is None:
        raise ScopeForbidden
    assert_review_scope(submission, workspace, fresh_scope, context)
    try:
        projection = unit_of_work.review.get_projection(submission_id)
        events = unit_of_work.review.list_events(submission_id)
    except ReviewClosureViolation as exc:
        raise ReviewIntegrityFailure(exc.reason) from exc
    if projection is None:
        raise ReviewIntegrityFailure("review projection is missing")
    occupancy = unit_of_work.submission.get_workspace_occupancy(workspace.workspace_id)
    return ReviewScopeFacts(
        submission=submission,
        workspace=workspace,
        projection=projection,
        events=events,
        occupancy=occupancy,
    )


def get_review_facts(
    *,
    context: IdentityContext,
    submission_id: str,
    scope_resolution: ScopeResolutionPort,
    unit_of_work_factory: WorkspaceControlUnitOfWorkFactory,
) -> ReviewFacts:
    assert_permission(context, PERMISSION_REVIEW_SUBMISSION)
    resolved = scope_resolution.resolve(context)
    with unit_of_work_factory(read_only=True) as unit_of_work:
        fresh_scope = resolve_fresh_provisioned_scope(unit_of_work, context)
        assert_fresh_scope_matches(fresh_scope, resolved)
        facts = load_review_scope_facts(
            unit_of_work,
            context=context,
            submission_id=submission_id,
            resolved_scope=fresh_scope,
        )
        return ReviewFacts(projection=facts.projection, events=facts.events)
