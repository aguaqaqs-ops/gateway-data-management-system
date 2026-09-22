"""Archive bounded read queries."""

from __future__ import annotations

from dataclasses import dataclass

from gateway_backend.application.archive.contracts import (
    ArchiveCandidateRef,
    ArchiveSelectedRef,
    compute_anomaly_subject_digest,
    compute_selection_subject_digest,
)
from gateway_backend.application.archive.errors import (
    ArchiveAnomalyUnresolved,
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
    ArchiveAnomalyResolutionAction,
    ArchiveConfirmationAction,
    ArchivePlan,
    ArchiveResult,
)
from gateway_backend.domain.workspace.models import BaselineHead, IdentityContext
from gateway_backend.domain.workspace.policies import assert_permission

PERMISSION_ARCHIVE_SUBMISSION = "archive_submission"
APPROVED_SIBLING_EXCLUDED_ISSUE = "APPROVED_SIBLING_EXCLUDED"


@dataclass(frozen=True, slots=True)
class ArchiveCandidatesResult:
    head: BaselineHead
    candidates: tuple[ArchiveCandidateRef, ...]
    candidate_set_digest: str
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArchivePreviewAnomaly:
    issue_code: str
    sibling_submission_id: str
    sibling_candidate_digest: str
    subject_digest: str


@dataclass(frozen=True, slots=True)
class ArchivePreviewDisposition:
    submission_id: str
    disposition: str


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
        return ArchiveCandidatesResult(
            head=snapshot.resolved_scope.baseline_head,
            candidates=snapshot.candidates,
            candidate_set_digest=snapshot.candidate_set_digest,
            blockers=tuple(blockers),
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
        anomalies = _derive_anomalies(snapshot, selected, selection_subject_digest)
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
            sibling_submission_id=candidate.submission_id,
            sibling_candidate_digest=candidate.expected_candidate_digest,
        )
        anomalies.append(
            ArchivePreviewAnomaly(
                issue_code=APPROVED_SIBLING_EXCLUDED_ISSUE,
                sibling_submission_id=candidate.submission_id,
                sibling_candidate_digest=candidate.expected_candidate_digest,
                subject_digest=subject_digest,
            )
        )
    return tuple(anomalies)


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
    subject_digest: str,
) -> bool:
    sequence = unit_of_work.archive.get_latest_resolution_sequence(repository_id, subject_digest)
    if sequence == 0:
        return False
    event = unit_of_work.archive.get_resolution_event(repository_id, subject_digest, sequence)
    if event is None:
        return False
    return event.action is ArchiveAnomalyResolutionAction.ACKNOWLEDGE_EXCLUSION


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
            anomaly.subject_digest,
        ):
            raise ArchiveAnomalyUnresolved("approved sibling exclusion is unresolved")
