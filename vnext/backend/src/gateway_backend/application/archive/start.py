"""StartArchive transaction orchestration."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, replace
from datetime import datetime

from gateway_backend.application.archive.contracts import (
    ArchiveAuditReferenceInput,
    ArchiveSelectedRef,
    compute_selection_subject_digest,
    compute_start_request_fingerprint,
    validate_utf8_id,
)
from gateway_backend.application.archive.errors import (
    CandidateBindingConflict,
    CandidateSetConflict,
)
from gateway_backend.application.archive.ports import (
    ArchiveControlTransaction,
    ArchiveControlUnitOfWorkFactory,
)
from gateway_backend.application.archive.queries import (
    PERMISSION_ARCHIVE_SUBMISSION,
    ArchivePreviewAnomaly,
    _derive_anomalies,
    _validate_audit_for_start,
)
from gateway_backend.application.archive.snapshot import (
    ArchiveCandidateSnapshot,
    assert_repository_submit_gate,
    load_archive_candidate_snapshot,
)
from gateway_backend.application.submission.errors import BaselineVersionConflict, IdempotencyConflict
from gateway_backend.domain.archive.models import (
    ArchiveAnomalyResolutionAction,
    ArchiveAuditReference,
    ArchiveConfirmationAction,
    ArchiveDisposition,
    ArchiveDispositionKind,
    ArchivePlan,
    ArchiveResult,
)
from gateway_backend.domain.baseline.models import BaselineNode, BaselineNodeKind
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.domain.workspace.policies import assert_permission
from gateway_backend.domain.workspace.ports import ScopeResolutionPort


@dataclass(frozen=True, slots=True)
class StartArchiveCommand:
    context: IdentityContext
    idempotency_key: str
    expected_baseline_node_id: str
    expected_baseline_head_version: int
    candidate_set_digest: str
    selected_ref: ArchiveSelectedRef
    confirmation_refs: tuple[ArchiveAuditReferenceInput, ...]
    anomaly_resolution_refs: tuple[ArchiveAuditReferenceInput, ...]


@dataclass(frozen=True, slots=True)
class StartArchiveResult:
    archive_plan_id: str
    archive_result_id: str
    baseline_node_id: str
    baseline_commit_id: str
    baseline_head_version: int
    selected_submission_id: str
    dispositions: tuple[ArchiveDisposition, ...]
    released_workspace_ids: tuple[str, ...]
    archived_by: str
    archived_at: datetime
    replay: bool


def start_archive(
    *,
    command: StartArchiveCommand,
    scope_resolution: ScopeResolutionPort,
    unit_of_work_factory: ArchiveControlUnitOfWorkFactory,
    now: datetime,
) -> StartArchiveResult:
    assert_permission(command.context, PERMISSION_ARCHIVE_SUBMISSION)
    resolved = scope_resolution.resolve(command.context)
    with unit_of_work_factory(read_only=False) as unit_of_work:
        existing_plan = unit_of_work.archive.find_start_plan_by_key(
            resolved.repository_id,
            command.context.gateway_device_external_key,
            command.context.business_project_id,
            command.idempotency_key,
        )
        request_fingerprint = compute_start_request_fingerprint(
            repository_id=resolved.repository_id,
            gateway_device_external_key=command.context.gateway_device_external_key,
            business_project_id=command.context.business_project_id,
            expected_baseline_node_id=command.expected_baseline_node_id,
            expected_baseline_head_version=command.expected_baseline_head_version,
            candidate_set_digest=command.candidate_set_digest,
            selected_submission_id=command.selected_ref.submission_id,
            expected_candidate_digest=command.selected_ref.expected_candidate_digest,
            confirmation_refs=command.confirmation_refs,
            anomaly_resolution_refs=command.anomaly_resolution_refs,
        )
        if existing_plan is not None:
            if existing_plan.request_fingerprint != request_fingerprint:
                raise IdempotencyConflict(idempotency_key=command.idempotency_key)
            existing_result = unit_of_work.archive.get_result_by_plan_id(existing_plan.plan_id)
            if existing_result is None:
                raise RuntimeError("archive plan exists without matching result")
            selected_submission = unit_of_work.submission.get_submission(
                existing_plan.selected_submission_id
            )
            if selected_submission is None:
                raise RuntimeError("archived submission is missing")
            return StartArchiveResult(
                archive_plan_id=existing_plan.plan_id,
                archive_result_id=existing_result.result_id,
                baseline_node_id=existing_result.baseline_node_id,
                baseline_commit_id=selected_submission.repository_commit_id,
                baseline_head_version=existing_plan.old_baseline_head_version + 1,
                selected_submission_id=existing_plan.selected_submission_id,
                dispositions=existing_result.dispositions,
                released_workspace_ids=_released_workspace_ids(
                    unit_of_work,
                    existing_result.dispositions,
                ),
                archived_by=existing_plan.accepted_by,
                archived_at=existing_result.archived_at,
                replay=True,
            )

        snapshot = load_archive_candidate_snapshot(unit_of_work, command.context, resolved)
        if (
            snapshot.baseline_node_id != command.expected_baseline_node_id
            or snapshot.baseline_head_version != command.expected_baseline_head_version
        ):
            raise BaselineVersionConflict("expected baseline head does not match current head")
        if snapshot.candidate_set_digest != command.candidate_set_digest:
            raise CandidateSetConflict()
        assert_repository_submit_gate(unit_of_work, snapshot.repository_id)
        if not any(
            candidate.submission_id == command.selected_ref.submission_id
            and candidate.expected_candidate_digest == command.selected_ref.expected_candidate_digest
            for candidate in snapshot.candidates
        ):
            raise CandidateBindingConflict("selected candidate reference is unknown or stale")

        selection_subject_digest = compute_selection_subject_digest(
            candidate_set_digest=snapshot.candidate_set_digest,
            selected_submission_id=command.selected_ref.submission_id,
            expected_candidate_digest=command.selected_ref.expected_candidate_digest,
        )
        anomalies = _derive_anomalies(snapshot, command.selected_ref, selection_subject_digest)
        _validate_audit_for_start(
            unit_of_work,
            snapshot=snapshot,
            selected=command.selected_ref,
            selection_subject_digest=selection_subject_digest,
            anomalies=anomalies,
            confirmation_refs=command.confirmation_refs,
            anomaly_resolution_refs=command.anomaly_resolution_refs,
        )
        _validate_audit_refs(
            unit_of_work,
            repository_id=snapshot.repository_id,
            selection_subject_digest=selection_subject_digest,
            anomalies=anomalies,
            confirmation_refs=command.confirmation_refs,
            anomaly_resolution_refs=command.anomaly_resolution_refs,
        )

        selected_submission = unit_of_work.submission.get_submission(command.selected_ref.submission_id)
        if selected_submission is None:
            raise CandidateBindingConflict("selected submission is missing")

        plan_id = str(uuid.uuid4())
        result_id = str(uuid.uuid4())
        baseline_node_id = str(uuid.uuid4())
        head_record = unit_of_work.baseline.get_head_record(snapshot.repository_id)
        if head_record is None:
            raise RuntimeError("baseline head is missing")
        archived_node = BaselineNode(
            node_id=baseline_node_id,
            repository_id=snapshot.repository_id,
            gateway_device_external_key=command.context.gateway_device_external_key,
            business_project_id=command.context.business_project_id,
            commit_id=selected_submission.repository_commit_id,
            kind=BaselineNodeKind.ARCHIVED_SUBMISSION,
            parent_node_id=head_record.node_id,
            source_submission_id=selected_submission.submission_id,
            created_at=now,
        )
        new_head = unit_of_work.baseline.save_archived_node_and_cas_head(
            archived_node,
            expected_head=head_record,
            new_head_node_id=baseline_node_id,
            new_head_version=head_record.optimistic_version + 1,
        )
        dispositions = _build_dispositions(snapshot, command.selected_ref)
        confirmation_audit_refs = tuple(
            ArchiveAuditReference(subject_digest=ref.subject_digest, sequence=ref.sequence)
            for ref in command.confirmation_refs
        )
        anomaly_audit_refs = tuple(
            ArchiveAuditReference(subject_digest=ref.subject_digest, sequence=ref.sequence)
            for ref in command.anomaly_resolution_refs
        )
        frozen_input = {
            "candidate_set_digest": snapshot.candidate_set_digest,
            "confirmation_refs": [
                {"sequence": ref.sequence, "subject_digest": ref.subject_digest}
                for ref in command.confirmation_refs
            ],
            "anomaly_resolution_refs": [
                {"sequence": ref.sequence, "subject_digest": ref.subject_digest}
                for ref in command.anomaly_resolution_refs
            ],
            "expected_baseline_head_version": command.expected_baseline_head_version,
            "expected_baseline_node_id": command.expected_baseline_node_id,
            "selected": {
                "expected_candidate_digest": command.selected_ref.expected_candidate_digest,
                "submission_id": command.selected_ref.submission_id,
            },
        }
        plan = ArchivePlan(
            plan_id=plan_id,
            repository_id=snapshot.repository_id,
            gateway_device_external_key=command.context.gateway_device_external_key,
            business_project_id=command.context.business_project_id,
            idempotency_key=validate_utf8_id(command.idempotency_key, field_name="idempotency_key"),
            request_fingerprint=request_fingerprint,
            accepted_by=command.context.actor_id,
            accepted_at=now,
            old_baseline_node_id=head_record.node_id,
            old_baseline_commit_id=snapshot.baseline_commit_id,
            old_baseline_head_version=head_record.optimistic_version,
            candidate_set_digest=snapshot.candidate_set_digest,
            selected_submission_id=command.selected_ref.submission_id,
            selected_candidate_digest=command.selected_ref.expected_candidate_digest,
            selected_repository_commit_id=selected_submission.repository_commit_id,
            confirmation_refs=confirmation_audit_refs,
            anomaly_resolution_refs=anomaly_audit_refs,
            frozen_input_json=json.dumps(frozen_input, separators=(",", ":"), sort_keys=True),
        )
        result = ArchiveResult(
            result_id=result_id,
            plan_id=plan_id,
            baseline_node_id=baseline_node_id,
            archived_at=now,
            dispositions=dispositions,
        )
        unit_of_work.archive.insert_plan_result_and_dispositions(plan, result, dispositions)
        released_workspace_ids = _release_workspaces_for_archive(
            unit_of_work,
            snapshot=snapshot,
            selected_submission_id=command.selected_ref.submission_id,
            now=now,
        )
        return StartArchiveResult(
            archive_plan_id=plan_id,
            archive_result_id=result_id,
            baseline_node_id=baseline_node_id,
            baseline_commit_id=selected_submission.repository_commit_id,
            baseline_head_version=new_head.optimistic_version,
            selected_submission_id=command.selected_ref.submission_id,
            dispositions=dispositions,
            released_workspace_ids=released_workspace_ids,
            archived_by=command.context.actor_id,
            archived_at=now,
            replay=False,
        )


def _build_dispositions(
    snapshot: ArchiveCandidateSnapshot,
    selected: ArchiveSelectedRef,
) -> tuple[ArchiveDisposition, ...]:
    dispositions: list[ArchiveDisposition] = []
    for candidate in snapshot.candidates:
        if candidate.submission_id == selected.submission_id:
            dispositions.append(
                ArchiveDisposition(
                    submission_id=candidate.submission_id,
                    disposition=ArchiveDispositionKind.ARCHIVED_BASELINE,
                )
            )
        else:
            dispositions.append(
                ArchiveDisposition(
                    submission_id=candidate.submission_id,
                    disposition=ArchiveDispositionKind.CLOSED_NOT_ARCHIVED,
                )
            )
    return tuple(dispositions)


def _validate_audit_refs(
    unit_of_work: ArchiveControlTransaction,
    *,
    repository_id: str,
    selection_subject_digest: str,
    anomalies: tuple[ArchivePreviewAnomaly, ...],
    confirmation_refs: tuple[ArchiveAuditReferenceInput, ...],
    anomaly_resolution_refs: tuple[ArchiveAuditReferenceInput, ...],
) -> None:
    if len(confirmation_refs) != 1:
        raise CandidateBindingConflict("exactly one confirmation audit reference is required")
    confirmation_ref = confirmation_refs[0]
    if confirmation_ref.subject_digest != selection_subject_digest:
        raise CandidateBindingConflict("confirmation audit reference subject mismatch")
    latest_confirmation_sequence = unit_of_work.archive.get_latest_confirmation_sequence(
        repository_id,
        selection_subject_digest,
    )
    if confirmation_ref.sequence != latest_confirmation_sequence:
        raise CandidateBindingConflict("confirmation audit reference sequence is stale")
    confirmation_event = unit_of_work.archive.get_confirmation_event(
        repository_id,
        selection_subject_digest,
        confirmation_ref.sequence,
    )
    if confirmation_event is None or confirmation_event.action is not ArchiveConfirmationAction.CONFIRM:
        raise CandidateBindingConflict("confirmation audit reference is not affirmative")
    if len(anomaly_resolution_refs) != len(anomalies):
        raise CandidateBindingConflict("anomaly resolution audit references are incomplete")
    for anomaly, resolution_ref in zip(anomalies, anomaly_resolution_refs, strict=True):
        if resolution_ref.subject_digest != anomaly.subject_digest:
            raise CandidateBindingConflict("anomaly resolution audit reference subject mismatch")
        latest_sequence = unit_of_work.archive.get_latest_resolution_sequence(
            repository_id,
            anomaly.subject_digest,
        )
        if resolution_ref.sequence != latest_sequence:
            raise CandidateBindingConflict("anomaly resolution audit reference sequence is stale")
        resolution_event = unit_of_work.archive.get_resolution_event(
            repository_id,
            anomaly.subject_digest,
            resolution_ref.sequence,
        )
        if (
            resolution_event is None
            or resolution_event.action is not ArchiveAnomalyResolutionAction.ACKNOWLEDGE_EXCLUSION
        ):
            raise CandidateBindingConflict("anomaly resolution audit reference is not affirmative")


def _release_workspaces_for_archive(
    unit_of_work: ArchiveControlTransaction,
    *,
    snapshot: ArchiveCandidateSnapshot,
    selected_submission_id: str,
    now: datetime,
) -> tuple[str, ...]:
    released: list[str] = []
    for candidate in snapshot.candidates:
        submission = unit_of_work.submission.get_submission(candidate.submission_id)
        if submission is None:
            continue
        workspace = unit_of_work.workspace.get_workspace(submission.workspace_id)
        if workspace is None:
            continue
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
            expected_submission_id=submission.submission_id,
        )
        released.append(workspace.workspace_id)
    return tuple(released)


def _released_workspace_ids(
    unit_of_work: ArchiveControlTransaction,
    dispositions: tuple[ArchiveDisposition, ...],
) -> tuple[str, ...]:
    workspace_ids: list[str] = []
    for disposition in dispositions:
        submission = unit_of_work.submission.get_submission(disposition.submission_id)
        if submission is None:
            continue
        workspace_ids.append(submission.workspace_id)
    return tuple(workspace_ids)
