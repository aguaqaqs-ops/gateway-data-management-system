"""Review apply SQLite transaction orchestration."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from gateway_backend.application.submission.errors import (
    ArchiveClosed,
    ReviewIntegrityFailure,
    ReviewWorkspaceOccupancyConflict,
)
from gateway_backend.application.submission.review import (
    PERMISSION_REVIEW_SUBMISSION,
    assert_fresh_scope_matches,
    assert_review_workspace_bindings,
    is_review_release_action,
    load_review_scope_facts,
    resolve_fresh_provisioned_scope,
    verify_idempotency_replay,
)
from gateway_backend.application.submission.review_contracts import (
    ApplyReviewCommand,
    ApplyReviewResult,
    build_apply_review_request_fingerprint_from_command,
    validate_apply_review_command,
)
from gateway_backend.application.submission.ports import (
    ReviewApplyControlUnitOfWorkFactory,
    ReviewApplyTransaction,
)
from gateway_backend.domain.submission.errors import (
    ReviewClosureViolation,
    ReviewVersionConflict,
    SubmitOccupancyConflict,
)
from gateway_backend.domain.submission.review import (
    ReviewEvent,
    ReviewIdempotencyRecord,
    ReviewProjection,
    resolve_review_transition,
    validate_review_reason,
)
from gateway_backend.domain.workspace.models import ResolvedScope, Workspace
from gateway_backend.domain.workspace.policies import assert_permission
from gateway_backend.domain.workspace.ports import ScopeResolutionPort


def apply_review_transaction(
    *,
    command: ApplyReviewCommand,
    scope_resolution: ScopeResolutionPort,
    unit_of_work_factory: ReviewApplyControlUnitOfWorkFactory,
    now: datetime,
) -> ApplyReviewResult:
    validate_apply_review_command(command)
    assert_permission(command.context, PERMISSION_REVIEW_SUBMISSION)
    resolved = scope_resolution.resolve(command.context)
    with unit_of_work_factory(read_only=False) as unit_of_work:
        return _apply_review_in_control_transaction(
            command=command,
            unit_of_work=unit_of_work,
            resolved=resolved,
            now=now,
        )


def _apply_review_in_control_transaction(
    *,
    command: ApplyReviewCommand,
    unit_of_work: ReviewApplyTransaction,
    resolved: ResolvedScope,
    now: datetime,
) -> ApplyReviewResult:
    fresh_scope = resolve_fresh_provisioned_scope(unit_of_work, command.context)
    assert_fresh_scope_matches(fresh_scope, resolved)
    facts = load_review_scope_facts(
        unit_of_work,
        context=command.context,
        submission_id=command.submission_id,
        resolved_scope=fresh_scope,
    )
    try:
        existing = unit_of_work.review.find_idempotency(
            command.context.business_project_id,
            command.idempotency_key,
        )
    except ReviewClosureViolation as exc:
        raise ReviewIntegrityFailure(exc.reason) from exc
    if existing is not None:
        record_events: tuple[ReviewEvent, ...]
        record_workspace: Workspace
        if existing.submission_id == command.submission_id:
            record_events = facts.events
            record_workspace = facts.workspace
        else:
            try:
                record_events = unit_of_work.review.list_events(existing.submission_id)
            except ReviewClosureViolation as exc:
                raise ReviewIntegrityFailure(exc.reason) from exc
            record_submission = unit_of_work.submission.get_submission(existing.submission_id)
            if record_submission is None:
                raise ReviewIntegrityFailure(
                    "review idempotency record points to a missing submission"
                )
            maybe_workspace = unit_of_work.workspace.get_workspace(record_submission.workspace_id)
            if maybe_workspace is None:
                raise ReviewIntegrityFailure(
                    "review idempotency record points to a missing workspace"
                )
            record_workspace = maybe_workspace
        return verify_idempotency_replay(
            existing,
            command=command,
            record_workspace=record_workspace,
            request_workspace=facts.workspace,
            request_repository_id=fresh_scope.repository_id,
            events=record_events,
        )

    request_fingerprint = build_apply_review_request_fingerprint_from_command(
        command=command,
        workspace_id=facts.workspace.workspace_id,
        repository_id=fresh_scope.repository_id,
    )
    if unit_of_work.is_submission_closed(command.submission_id):
        raise ArchiveClosed()
    if facts.projection.optimistic_version != command.expected_review_version:
        raise ReviewVersionConflict(
            expected=command.expected_review_version,
            actual=facts.projection.optimistic_version,
        )
    event_kind, to_status = resolve_review_transition(facts.projection.status, command.action)
    validated_reason = validate_review_reason(command.action, command.reason)
    assert_review_workspace_bindings(
        facts.submission,
        facts.workspace,
        facts.occupancy,
    )
    next_sequence = facts.projection.latest_sequence + 1
    event = ReviewEvent(
        submission_id=command.submission_id,
        sequence=next_sequence,
        event_kind=event_kind,
        from_status=facts.projection.status,
        to_status=to_status,
        reason=validated_reason,
        actor_id=command.context.actor_id,
        occurred_at=now,
    )
    projection = ReviewProjection(
        submission_id=command.submission_id,
        status=to_status,
        optimistic_version=next_sequence,
        latest_sequence=next_sequence,
        updated_by=command.context.actor_id,
        updated_at=now,
    )
    try:
        unit_of_work.review.append_event(event)
        unit_of_work.review.cas_projection(
            projection,
            expected_version=facts.projection.optimistic_version,
        )
        unit_of_work.review.insert_idempotency(
            ReviewIdempotencyRecord(
                business_project_id=command.context.business_project_id,
                submission_id=command.submission_id,
                idempotency_key=command.idempotency_key,
                request_fingerprint=request_fingerprint,
                event_sequence=next_sequence,
            )
        )
        if is_review_release_action(command.action):
            _release_workspace_for_review(
                unit_of_work,
                workspace=facts.workspace,
                submission_id=facts.submission.submission_id,
                now=now,
            )
    except ReviewClosureViolation as exc:
        raise ReviewIntegrityFailure(exc.reason) from exc
    except SubmitOccupancyConflict as exc:
        raise ReviewWorkspaceOccupancyConflict(exc.reason) from exc
    return ApplyReviewResult(
        event=event,
        projection=projection,
        request_fingerprint=request_fingerprint,
        replay=False,
    )


def _release_workspace_for_review(
    unit_of_work: ReviewApplyTransaction,
    *,
    workspace: Workspace,
    submission_id: str,
    now: datetime,
) -> None:
    # WorkspaceVersionConflict is unreachable here: occupancy bindings were verified
    # against the same workspace optimistic_version before this CAS.
    updated_workspace = replace(
        workspace,
        current_upload_revision_id=None,
        current_preview_result_id=None,
        optimistic_version=workspace.optimistic_version + 1,
        updated_at=now,
    )
    unit_of_work.workspace.save_workspace(
        updated_workspace,
        expected_version=workspace.optimistic_version,
    )
    unit_of_work.submission.delete_workspace_submission_occupancy(
        workspace.workspace_id,
        expected_submission_id=submission_id,
    )
