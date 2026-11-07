"""Archive bounded read queries."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any
from typing import Literal

from gateway_backend.application.archive.contracts import (
    ArchiveCandidateRef,
    ArchiveSelectedRef,
    ARCHIVE_MAX_ANOMALY_REFS,
    assert_resolution_event_integrity,
    compute_archive_digest,
    compute_anomaly_subject_digest,
    compute_identity_exception_subject_digest,
    compute_selection_subject_digest,
    validate_archive_digest,
    validate_archive_sequence,
    validate_non_negative_int,
)
from gateway_backend.application.archive.errors import (
    ArchiveAnomalyUnresolved,
    ArchiveIntegrityFailure,
    ArchiveRequestValidation,
    ArchiveConfirmationRequired,
    ArchiveResultNotFound,
    CandidateBindingConflict,
)
from gateway_backend.application.archive.contracts import ArchiveAuditReferenceInput
from gateway_backend.application.archive.ports import (
    ArchiveControlTransaction,
    ArchiveControlUnitOfWorkFactory,
)
from gateway_backend.application.archive.snapshot import (
    ArchiveCandidateSnapshot,
    collect_repository_submit_blockers,
    load_archive_candidate_snapshot,
)
from gateway_backend.domain.archive.models import (
    ArchiveAnomalyResolutionEvent,
    ArchiveConfirmationAction,
    ArchiveConfirmationEvent,
    ArchivePlan,
    ArchiveResult,
    ArchiveSubjectKind,
    affirmative_resolution_action,
)
from gateway_backend.application.archive.business_validation import ArchiveBusinessValidation
from gateway_backend.domain.workspace.models import BaselineHead, IdentityContext
from gateway_backend.domain.workspace.policies import assert_permission

PERMISSION_ARCHIVE_SUBMISSION = "archive_submission"
APPROVED_SIBLING_EXCLUDED_ISSUE = "APPROVED_SIBLING_EXCLUDED"
PROJECT_IDENTITY_EXCEPTION_ISSUE = "PROJECT_IDENTITY_EXCEPTION"
ARCHIVE_AUDIT_EVENTS_MAX_LIMIT = 100


@dataclass(frozen=True, slots=True)
class ArchiveCandidatesResult:
    head: BaselineHead
    candidates: tuple[ArchiveCandidateRef, ...]
    candidate_set_digest: str
    blockers: tuple[str, ...]
    pending_submission_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArchivePreviewAnomaly:
    subject_kind: ArchiveSubjectKind
    issue_code: str
    target_submission_id: str
    target_candidate_digest: str
    subject_digest: str
    affected_submission_ids: tuple[str, ...] = ()
    side: str | None = None
    relations: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
    detected_status: str = "DETECTED"
    resolution_status: str = "UNRESOLVED"
    latest_sequence: int = 0
    accepted_by: str | None = None
    accepted_at: datetime | None = None
    reason: str | None = None
    subject_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ArchivePreviewDisposition:
    submission_id: str
    disposition: Literal["ARCHIVED_BASELINE", "CLOSED_NOT_ARCHIVED"]


@dataclass(frozen=True, slots=True)
class ArchivePreviewWorkspaceRelease:
    workspace_id: str
    submission_id: str


@dataclass(frozen=True, slots=True)
class GetArchiveResultResult:
    plan: ArchivePlan
    archive_result: ArchiveResult
    selected_repository_commit_id: str


@dataclass(frozen=True, slots=True)
class ListArchiveAuditEventsResult:
    events: tuple[ArchiveConfirmationEvent | ArchiveAnomalyResolutionEvent, ...]
    next_after_sequence: int | None


@dataclass(frozen=True, slots=True)
class PreviewArchivePlanResult:
    head: BaselineHead
    candidate_set_digest: str
    selected: ArchiveSelectedRef | None
    selection_subject_digest: str | None
    confirmation_requirements: tuple[str, ...]
    anomalies: tuple[ArchivePreviewAnomaly, ...]
    audit_valid: bool
    dispositions: tuple[ArchivePreviewDisposition, ...]
    workspace_releases: tuple[ArchivePreviewWorkspaceRelease, ...]
    can_start: bool
    blockers: tuple[str, ...]
    pending_submission_ids: tuple[str, ...]
    business_validation: ArchiveBusinessValidation


def get_archive_candidates(
    *,
    context: IdentityContext,
    unit_of_work_factory: ArchiveControlUnitOfWorkFactory,
) -> ArchiveCandidatesResult:
    assert_permission(context, PERMISSION_ARCHIVE_SUBMISSION)
    with unit_of_work_factory(read_only=True) as unit_of_work:
        fresh_scope = unit_of_work.resolve_provisioned_scope(
            gateway_device_external_key=context.gateway_device_external_key,
            business_project_id=context.business_project_id,
        )
        snapshot = load_archive_candidate_snapshot(unit_of_work, context, fresh_scope)
        blockers = list(collect_repository_submit_blockers(unit_of_work, snapshot.repository_id))
        if snapshot.pending_submission_ids:
            blockers.append("ARCHIVE_PENDING_REVIEW")
        return ArchiveCandidatesResult(
            head=snapshot.resolved_scope.baseline_head,
            candidates=snapshot.candidates,
            candidate_set_digest=snapshot.candidate_set_digest,
            blockers=tuple(blockers),
            pending_submission_ids=snapshot.pending_submission_ids,
        )


def preview_archive_plan(
    *,
    context: IdentityContext,
    selected_ref: ArchiveSelectedRef | None,
    unit_of_work_factory: ArchiveControlUnitOfWorkFactory,
) -> PreviewArchivePlanResult:
    assert_permission(context, PERMISSION_ARCHIVE_SUBMISSION)
    with unit_of_work_factory(read_only=True) as unit_of_work:
        fresh_scope = unit_of_work.resolve_provisioned_scope(
            gateway_device_external_key=context.gateway_device_external_key,
            business_project_id=context.business_project_id,
        )
        snapshot = load_archive_candidate_snapshot(unit_of_work, context, fresh_scope)
        blockers = list(collect_repository_submit_blockers(unit_of_work, snapshot.repository_id))
        if snapshot.pending_submission_ids:
            blockers.append("ARCHIVE_PENDING_REVIEW")
        selected: ArchiveSelectedRef | None = None
        selection_subject_digest: str | None = None
        if selected_ref is not None:
            if not _candidate_ref_matches(snapshot.candidates, selected_ref):
                raise CandidateBindingConflict("selected candidate reference is unknown or stale")
            selected = selected_ref
            selection_subject_digest = compute_selection_subject_digest(
                candidate_set_digest=snapshot.candidate_set_digest,
                selected_submission_id=selected.submission_id,
                expected_candidate_digest=selected.expected_candidate_digest,
            )
        anomalies = _derive_anomalies(
            unit_of_work,
            snapshot,
            selected,
            selection_subject_digest,
        )
        confirmation_requirements = (
            (selection_subject_digest,) if selection_subject_digest is not None else ()
        )
        audit_valid = False
        if selected is not None and selection_subject_digest is not None:
            try:
                _validate_audit_for_start(
                    unit_of_work,
                    snapshot=snapshot,
                    selected=selected,
                    selection_subject_digest=selection_subject_digest,
                    anomalies=anomalies,
                    confirmation_refs=(),
                    anomaly_resolution_refs=(),
                )
                audit_valid = True
            except (ArchiveConfirmationRequired, ArchiveAnomalyUnresolved):
                audit_valid = False
        dispositions = _derive_dispositions(snapshot, selected)
        workspace_releases = _derive_workspace_releases(unit_of_work, snapshot, selected)
        can_start = (
            selected is not None
            and not blockers
            and audit_valid
        )
        return PreviewArchivePlanResult(
            head=snapshot.resolved_scope.baseline_head,
            candidate_set_digest=snapshot.candidate_set_digest,
            selected=selected,
            selection_subject_digest=selection_subject_digest,
            confirmation_requirements=confirmation_requirements,
            anomalies=anomalies,
            audit_valid=audit_valid,
            dispositions=dispositions,
            workspace_releases=workspace_releases,
            can_start=can_start,
            blockers=tuple(blockers),
            pending_submission_ids=snapshot.pending_submission_ids,
            business_validation=snapshot.business_validation,
        )


def list_archive_audit_events(
    *,
    context: IdentityContext,
    subject_kind: ArchiveSubjectKind,
    subject_digest: str,
    after_sequence: int,
    limit: int,
    unit_of_work_factory: ArchiveControlUnitOfWorkFactory,
) -> ListArchiveAuditEventsResult:
    assert_permission(context, PERMISSION_ARCHIVE_SUBMISSION)
    validated_digest = validate_archive_digest(subject_digest, field_name="subject_digest")
    validated_after = validate_archive_sequence(after_sequence, field_name="after_sequence")
    validated_limit = validate_non_negative_int(limit, field_name="limit")
    if validated_limit < 1 or validated_limit > ARCHIVE_AUDIT_EVENTS_MAX_LIMIT:
        raise ArchiveRequestValidation("limit must be between 1 and 100")
    with unit_of_work_factory(read_only=True) as unit_of_work:
        fresh_scope = unit_of_work.resolve_provisioned_scope(
            gateway_device_external_key=context.gateway_device_external_key,
            business_project_id=context.business_project_id,
        )
        if subject_kind is ArchiveSubjectKind.CONFIRM_SELECTION:
            confirmation_events = unit_of_work.archive.list_confirmation_events(
                fresh_scope.repository_id,
                context.gateway_device_external_key,
                context.business_project_id,
                validated_digest,
                validated_after,
                validated_limit,
            )
            events: tuple[ArchiveConfirmationEvent | ArchiveAnomalyResolutionEvent, ...] = (
                confirmation_events
            )
        else:
            resolution_events = unit_of_work.archive.list_resolution_events(
                fresh_scope.repository_id,
                context.gateway_device_external_key,
                context.business_project_id,
                validated_digest,
                validated_after,
                validated_limit,
            )
            for event in resolution_events:
                assert_resolution_event_integrity(event)
            events = resolution_events
        next_after_sequence: int | None = None
        if len(events) == validated_limit:
            next_after_sequence = events[-1].sequence
        return ListArchiveAuditEventsResult(
            events=events,
            next_after_sequence=next_after_sequence,
        )


def get_archive_result(
    *,
    context: IdentityContext,
    archive_result_id: str,
    unit_of_work_factory: ArchiveControlUnitOfWorkFactory,
) -> GetArchiveResultResult:
    assert_permission(context, PERMISSION_ARCHIVE_SUBMISSION)
    with unit_of_work_factory(read_only=True) as unit_of_work:
        fresh_scope = unit_of_work.resolve_provisioned_scope(
            gateway_device_external_key=context.gateway_device_external_key,
            business_project_id=context.business_project_id,
        )
        result = unit_of_work.archive.get_result_by_id(archive_result_id)
        if result is None:
            raise ArchiveResultNotFound(archive_result_id=archive_result_id)
        plan = unit_of_work.archive.get_plan_by_id(result.plan_id)
        if plan is None:
            raise ArchiveResultNotFound(archive_result_id=archive_result_id)
        if (
            plan.repository_id != fresh_scope.repository_id
            or plan.gateway_device_external_key != context.gateway_device_external_key
            or plan.business_project_id != context.business_project_id
        ):
            raise ArchiveResultNotFound(archive_result_id=archive_result_id)
        return GetArchiveResultResult(
            plan=plan,
            archive_result=result,
            selected_repository_commit_id=plan.selected_repository_commit_id,
        )


def _candidate_ref_matches(
    candidates: tuple[ArchiveCandidateRef, ...],
    selected_ref: ArchiveSelectedRef,
) -> bool:
    for candidate in candidates:
        if (
            candidate.submission_id == selected_ref.submission_id
            and candidate.expected_candidate_digest == selected_ref.expected_candidate_digest
        ):
            return True
    return False


def _derive_anomalies(
    unit_of_work: ArchiveControlTransaction,
    snapshot: ArchiveCandidateSnapshot,
    selected: ArchiveSelectedRef | None,
    selection_subject_digest: str | None,
) -> tuple[ArchivePreviewAnomaly, ...]:
    if selected is None or selection_subject_digest is None:
        return ()
    anomalies: list[ArchivePreviewAnomaly] = []
    for candidate in snapshot.candidates:
        if candidate.submission_id == selected.submission_id:
            continue
        subject_digest = compute_anomaly_subject_digest(
            selection_subject_digest=selection_subject_digest,
            issue_code=APPROVED_SIBLING_EXCLUDED_ISSUE,
            target_submission_id=candidate.submission_id,
            target_candidate_digest=candidate.expected_candidate_digest,
        )
        anomalies.append(
            ArchivePreviewAnomaly(
                subject_kind=ArchiveSubjectKind.APPROVED_SIBLING_EXCLUDED,
                issue_code=APPROVED_SIBLING_EXCLUDED_ISSUE,
                target_submission_id=candidate.submission_id,
                target_candidate_digest=candidate.expected_candidate_digest,
                subject_digest=subject_digest,
                affected_submission_ids=(candidate.submission_id,),
                subject_payload={"selection_subject_digest": selection_subject_digest,
                    "issue_code": APPROVED_SIBLING_EXCLUDED_ISSUE,
                    "target_submission_id": candidate.submission_id,
                    "target_candidate_digest": candidate.expected_candidate_digest},
            )
        )
    selected_submission = unit_of_work.submission.get_submission(selected.submission_id)
    if selected_submission is None:
        raise ArchiveIntegrityFailure("selected candidate submission is missing")
    if selected_submission.identity_confirmations:
        preview_result = unit_of_work.workspace.get_preview_result(
            selected_submission.preview_result_id
        )
        if preview_result is None:
            raise ArchiveIntegrityFailure("identity confirmation preview result is missing")
        confirmed_assessment_digests = {
            confirmation.assessment_set_digest
            for confirmation in selected_submission.identity_confirmations
        }
        expected_assessment_digest = preview_result.identity_assessment_set_digest.value
        if confirmed_assessment_digests != {expected_assessment_digest}:
            raise ArchiveIntegrityFailure(
                "submission identity confirmations do not match its preview assessment"
            )
        subject_digest = compute_identity_exception_subject_digest(
            submission_id=selected_submission.submission_id,
            candidate_digest=selected.expected_candidate_digest,
            preview_bundle_digest=preview_result.digests.bundle_digest,
            assessment_set_digest=expected_assessment_digest,
            selection_subject_digest=selection_subject_digest,
        )
        anomalies.append(
            ArchivePreviewAnomaly(
                subject_kind=ArchiveSubjectKind.PROJECT_IDENTITY_EXCEPTION,
                issue_code=PROJECT_IDENTITY_EXCEPTION_ISSUE,
                target_submission_id=selected_submission.submission_id,
                target_candidate_digest=selected.expected_candidate_digest,
                subject_digest=subject_digest,
                affected_submission_ids=(selected_submission.submission_id,),
                subject_payload={"selection_subject_digest": selection_subject_digest,
                    "submission_id": selected_submission.submission_id,
                    "candidate_digest": selected.expected_candidate_digest,
                    "preview_bundle_digest": preview_result.digests.bundle_digest,
                    "assessment_set_digest": expected_assessment_digest},
            )
        )
    candidates_by_id = {item.submission_id: item for item in snapshot.business_candidates}
    for issue in snapshot.business_validation.issues:
        target_id = issue.affected_submission_ids[0]
        payload = {"selection_subject_digest": selection_subject_digest,
            "rule_id": snapshot.business_validation.rule_id,
            **issue.to_document(),
            "affected_candidates": [{"submission_id": member,
                "candidate_digest": candidates_by_id[member].candidate_digest,
                "configuration_facts_digest": candidates_by_id[member].configuration_facts.facts_digest}
                for member in issue.affected_submission_ids]}
        anomalies.append(ArchivePreviewAnomaly(subject_kind=issue.subject_kind,
            issue_code=issue.issue_code, target_submission_id=target_id,
            target_candidate_digest=candidates_by_id[target_id].candidate_digest,
            subject_digest=compute_archive_digest("business-anomaly", payload),
            affected_submission_ids=issue.affected_submission_ids, side=issue.side,
            relations=issue.relations, details=issue.details,
            detected_status="UNEXPLAINED" if issue.subject_kind is ArchiveSubjectKind.CONFIGURATION_SOURCE else "DETECTED",
            subject_payload=payload))
    if len(anomalies) > ARCHIVE_MAX_ANOMALY_REFS or len({item.subject_digest for item in anomalies}) != len(anomalies):
        raise ArchiveIntegrityFailure("archive anomaly set violates the rule budget")
    return tuple(_with_resolution(unit_of_work, snapshot.repository_id, item) for item in anomalies)


def _derive_dispositions(
    snapshot: ArchiveCandidateSnapshot,
    selected: ArchiveSelectedRef | None,
) -> tuple[ArchivePreviewDisposition, ...]:
    if selected is None:
        return ()
    dispositions: list[ArchivePreviewDisposition] = []
    for candidate in snapshot.candidates:
        if candidate.submission_id == selected.submission_id:
            dispositions.append(
                ArchivePreviewDisposition(
                    submission_id=candidate.submission_id,
                    disposition="ARCHIVED_BASELINE",
                )
            )
        else:
            dispositions.append(
                ArchivePreviewDisposition(
                    submission_id=candidate.submission_id,
                    disposition="CLOSED_NOT_ARCHIVED",
                )
            )
    return tuple(dispositions)


def _derive_workspace_releases(
    unit_of_work: ArchiveControlTransaction,
    snapshot: ArchiveCandidateSnapshot,
    selected: ArchiveSelectedRef | None,
) -> tuple[ArchivePreviewWorkspaceRelease, ...]:
    if selected is None:
        return ()
    releases: list[ArchivePreviewWorkspaceRelease] = []
    for candidate in snapshot.candidates:
        submission = unit_of_work.submission.get_submission(candidate.submission_id)
        if submission is None:
            continue
        releases.append(
            ArchivePreviewWorkspaceRelease(
                workspace_id=submission.workspace_id,
                submission_id=submission.submission_id,
            )
        )
    return tuple(releases)


def _latest_confirmation_is_affirmative(
    unit_of_work: ArchiveControlTransaction,
    repository_id: str,
    subject_digest: str,
) -> bool:
    sequence = unit_of_work.archive.get_latest_confirmation_sequence(repository_id, subject_digest)
    if sequence == 0:
        return False
    event = unit_of_work.archive.get_confirmation_event(repository_id, subject_digest, sequence)
    if event is None:
        return False
    return event.action is ArchiveConfirmationAction.CONFIRM


def _latest_resolution_is_affirmative(
    unit_of_work: ArchiveControlTransaction,
    repository_id: str,
    subject_kind: ArchiveSubjectKind,
    subject_digest: str,
) -> bool:
    sequence = unit_of_work.archive.get_latest_resolution_sequence(repository_id, subject_digest)
    if sequence == 0:
        return False
    event = unit_of_work.archive.get_resolution_event(repository_id, subject_digest, sequence)
    if event is not None:
        assert_resolution_event_integrity(event)
    if event is None or event.subject_kind is not subject_kind:
        return False
    expected_action = affirmative_resolution_action(subject_kind)
    return event.action is expected_action


def _validate_audit_for_start(
    unit_of_work: ArchiveControlTransaction,
    *,
    snapshot: ArchiveCandidateSnapshot,
    selected: ArchiveSelectedRef,
    selection_subject_digest: str,
    anomalies: tuple[ArchivePreviewAnomaly, ...],
    confirmation_refs: tuple[ArchiveAuditReferenceInput, ...],
    anomaly_resolution_refs: tuple[ArchiveAuditReferenceInput, ...],
) -> None:
    if not _latest_confirmation_is_affirmative(
        unit_of_work,
        snapshot.repository_id,
        selection_subject_digest,
    ):
        raise ArchiveConfirmationRequired("selection confirmation is required")
    for anomaly in anomalies:
        if not _latest_resolution_is_affirmative(
            unit_of_work,
            snapshot.repository_id,
            anomaly.subject_kind,
            anomaly.subject_digest,
        ):
            raise ArchiveAnomalyUnresolved("archive anomaly is unresolved")


def _with_resolution(unit_of_work: ArchiveControlTransaction, repository_id: str,
        anomaly: ArchivePreviewAnomaly) -> ArchivePreviewAnomaly:
    sequence = unit_of_work.archive.get_latest_resolution_sequence(repository_id, anomaly.subject_digest)
    event = None if not sequence else unit_of_work.archive.get_resolution_event(
        repository_id, anomaly.subject_digest, sequence)
    if event is not None:
        assert_resolution_event_integrity(event)
    accepted = event is not None and event.subject_kind is anomaly.subject_kind and event.action is affirmative_resolution_action(anomaly.subject_kind)
    return replace(anomaly, latest_sequence=sequence,
        resolution_status="ACCEPTED" if accepted else "REVOKED" if event is not None else "UNRESOLVED",
        accepted_by=event.actor_id if accepted and event is not None else None,
        accepted_at=event.occurred_at if accepted and event is not None else None,
        reason=event.reason if event is not None else None)
