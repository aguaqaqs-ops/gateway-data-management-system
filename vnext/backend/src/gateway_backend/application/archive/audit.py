"""Archive audit append transactions."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from gateway_backend.application.archive.contracts import (
    ArchiveSelectedRef,
    compute_anomaly_subject_digest,
    compute_confirmation_request_fingerprint,
    compute_resolution_request_fingerprint,
    compute_selection_subject_digest,
    validate_archive_digest,
    validate_utf8_id,
    validate_utf8_reason,
)
from gateway_backend.application.archive.errors import ArchiveAuditVersionConflict
from gateway_backend.application.archive.ports import ArchiveControlUnitOfWorkFactory
from gateway_backend.application.archive.queries import PERMISSION_ARCHIVE_SUBMISSION
from gateway_backend.application.archive.snapshot import load_archive_candidate_snapshot
from gateway_backend.application.submission.errors import BaselineVersionConflict, IdempotencyConflict
from gateway_backend.domain.archive.models import (
    ArchiveAnomalyResolutionAction,
    ArchiveAnomalyResolutionEvent,
    ArchiveConfirmationAction,
    ArchiveConfirmationEvent,
    ArchiveSubjectKind,
)
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.domain.workspace.policies import assert_permission
from gateway_backend.domain.workspace.ports import ScopeResolutionPort


@dataclass(frozen=True, slots=True)
class AppendArchiveConfirmationCommand:
    context: IdentityContext
    idempotency_key: str
    expected_baseline_node_id: str
    expected_baseline_head_version: int
    selected: ArchiveSelectedRef
    candidate_set_digest: str
    subject_digest: str
    expected_sequence: int
    action: ArchiveConfirmationAction
    reason: str


@dataclass(frozen=True, slots=True)
class AppendArchiveAnomalyResolutionCommand:
    context: IdentityContext
    idempotency_key: str
    expected_baseline_node_id: str
    expected_baseline_head_version: int
    selected: ArchiveSelectedRef
    candidate_set_digest: str
    subject_digest: str
    expected_sequence: int
    action: ArchiveAnomalyResolutionAction
    reason: str
    issue_code: str
    sibling_submission_id: str
    sibling_candidate_digest: str


@dataclass(frozen=True, slots=True)
class AppendArchiveAuditResult:
    event_id: str
    sequence: int
    replay: bool


def append_archive_confirmation(
    *,
    command: AppendArchiveConfirmationCommand,
    scope_resolution: ScopeResolutionPort,
    unit_of_work_factory: ArchiveControlUnitOfWorkFactory,
    now: datetime,
) -> AppendArchiveAuditResult:
    assert_permission(command.context, PERMISSION_ARCHIVE_SUBMISSION)
    resolved = scope_resolution.resolve(command.context)
    with unit_of_work_factory(read_only=False) as unit_of_work:
        existing = unit_of_work.archive.find_confirmation_idempotency(
            resolved.repository_id,
            command.idempotency_key,
        )
        request_fingerprint = compute_confirmation_request_fingerprint(
            repository_id=resolved.repository_id,
            gateway_device_external_key=command.context.gateway_device_external_key,
            business_project_id=command.context.business_project_id,
            expected_baseline_node_id=command.expected_baseline_node_id,
            expected_baseline_head_version=command.expected_baseline_head_version,
            selected_submission_id=command.selected.submission_id,
            expected_candidate_digest=command.selected.expected_candidate_digest,
            candidate_set_digest=command.candidate_set_digest,
            subject_digest=command.subject_digest,
            expected_sequence=command.expected_sequence,
            action=command.action,
            reason=command.reason,
            actor_id=command.context.actor_id,
        )
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                raise IdempotencyConflict(idempotency_key=command.idempotency_key)
            return AppendArchiveAuditResult(
                event_id=existing.event_id,
                sequence=existing.sequence,
                replay=True,
            )
        snapshot = load_archive_candidate_snapshot(unit_of_work, command.context, resolved)
        if (
            snapshot.baseline_node_id != command.expected_baseline_node_id
            or snapshot.baseline_head_version != command.expected_baseline_head_version
        ):
            raise BaselineVersionConflict("expected baseline head does not match current head")
        if snapshot.candidate_set_digest != command.candidate_set_digest:
            raise BaselineVersionConflict("candidate set digest does not match current snapshot")
        expected_selection_digest = compute_selection_subject_digest(
            candidate_set_digest=snapshot.candidate_set_digest,
            selected_submission_id=command.selected.submission_id,
            expected_candidate_digest=command.selected.expected_candidate_digest,
        )
        if command.subject_digest != expected_selection_digest:
            raise BaselineVersionConflict("subject digest does not match current selection")
        latest_sequence = unit_of_work.archive.get_latest_confirmation_sequence(
            snapshot.repository_id,
            command.subject_digest,
        )
        if command.expected_sequence != latest_sequence:
            raise ArchiveAuditVersionConflict(expected=command.expected_sequence, actual=latest_sequence)
        next_sequence = latest_sequence + 1
        payload = {
            "action": command.action.value,
            "candidate_set_digest": command.candidate_set_digest,
            "expected_baseline_head_version": command.expected_baseline_head_version,
            "expected_baseline_node_id": command.expected_baseline_node_id,
            "expected_sequence": command.expected_sequence,
            "reason": validate_utf8_reason(command.reason),
            "selected": {
                "expected_candidate_digest": command.selected.expected_candidate_digest,
                "submission_id": command.selected.submission_id,
            },
            "subject_digest": command.subject_digest,
        }
        event = ArchiveConfirmationEvent(
            event_id=str(uuid.uuid4()),
            repository_id=snapshot.repository_id,
            gateway_device_external_key=command.context.gateway_device_external_key,
            business_project_id=command.context.business_project_id,
            subject_kind=ArchiveSubjectKind.CONFIRM_SELECTION,
            subject_digest=command.subject_digest,
            sequence=next_sequence,
            action=command.action,
            reason=validate_utf8_reason(command.reason),
            actor_id=command.context.actor_id,
            occurred_at=now,
            idempotency_key=validate_utf8_id(command.idempotency_key, field_name="idempotency_key"),
            request_fingerprint=request_fingerprint,
            request_payload_json=json.dumps(payload, separators=(",", ":"), sort_keys=True),
        )
        unit_of_work.archive.append_confirmation(event)
        return AppendArchiveAuditResult(
            event_id=event.event_id,
            sequence=event.sequence,
            replay=False,
        )


def append_archive_anomaly_resolution(
    *,
    command: AppendArchiveAnomalyResolutionCommand,
    scope_resolution: ScopeResolutionPort,
    unit_of_work_factory: ArchiveControlUnitOfWorkFactory,
    now: datetime,
) -> AppendArchiveAuditResult:
    assert_permission(command.context, PERMISSION_ARCHIVE_SUBMISSION)
    resolved = scope_resolution.resolve(command.context)
    with unit_of_work_factory(read_only=False) as unit_of_work:
        existing = unit_of_work.archive.find_resolution_idempotency(
            resolved.repository_id,
            command.idempotency_key,
        )
        request_fingerprint = compute_resolution_request_fingerprint(
            repository_id=resolved.repository_id,
            gateway_device_external_key=command.context.gateway_device_external_key,
            business_project_id=command.context.business_project_id,
            expected_baseline_node_id=command.expected_baseline_node_id,
            expected_baseline_head_version=command.expected_baseline_head_version,
            selected_submission_id=command.selected.submission_id,
            expected_candidate_digest=command.selected.expected_candidate_digest,
            candidate_set_digest=command.candidate_set_digest,
            subject_digest=command.subject_digest,
            expected_sequence=command.expected_sequence,
            action=command.action,
            reason=command.reason,
            actor_id=command.context.actor_id,
            issue_code=command.issue_code,
            sibling_submission_id=command.sibling_submission_id,
            sibling_candidate_digest=command.sibling_candidate_digest,
        )
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                raise IdempotencyConflict(idempotency_key=command.idempotency_key)
            return AppendArchiveAuditResult(
                event_id=existing.event_id,
                sequence=existing.sequence,
                replay=True,
            )
        snapshot = load_archive_candidate_snapshot(unit_of_work, command.context, resolved)
        if (
            snapshot.baseline_node_id != command.expected_baseline_node_id
            or snapshot.baseline_head_version != command.expected_baseline_head_version
        ):
            raise BaselineVersionConflict("expected baseline head does not match current head")
        if snapshot.candidate_set_digest != command.candidate_set_digest:
            raise BaselineVersionConflict("candidate set digest does not match current snapshot")
        selection_subject_digest = compute_selection_subject_digest(
            candidate_set_digest=snapshot.candidate_set_digest,
            selected_submission_id=command.selected.submission_id,
            expected_candidate_digest=command.selected.expected_candidate_digest,
        )
        expected_subject_digest = compute_anomaly_subject_digest(
            selection_subject_digest=selection_subject_digest,
            issue_code=command.issue_code,
            sibling_submission_id=command.sibling_submission_id,
            sibling_candidate_digest=command.sibling_candidate_digest,
        )
        if command.subject_digest != expected_subject_digest:
            raise BaselineVersionConflict("subject digest does not match current anomaly")
        latest_sequence = unit_of_work.archive.get_latest_resolution_sequence(
            snapshot.repository_id,
            command.subject_digest,
        )
        if command.expected_sequence != latest_sequence:
            raise ArchiveAuditVersionConflict(expected=command.expected_sequence, actual=latest_sequence)
        next_sequence = latest_sequence + 1
        payload = {
            "action": command.action.value,
            "candidate_set_digest": command.candidate_set_digest,
            "expected_baseline_head_version": command.expected_baseline_head_version,
            "expected_baseline_node_id": command.expected_baseline_node_id,
            "expected_sequence": command.expected_sequence,
            "issue_code": command.issue_code,
            "reason": validate_utf8_reason(command.reason),
            "selected": {
                "expected_candidate_digest": command.selected.expected_candidate_digest,
                "submission_id": command.selected.submission_id,
            },
            "sibling_candidate_digest": command.sibling_candidate_digest,
            "sibling_submission_id": command.sibling_submission_id,
            "subject_digest": command.subject_digest,
        }
        event = ArchiveAnomalyResolutionEvent(
            event_id=str(uuid.uuid4()),
            repository_id=snapshot.repository_id,
            gateway_device_external_key=command.context.gateway_device_external_key,
            business_project_id=command.context.business_project_id,
            subject_kind=ArchiveSubjectKind.APPROVED_SIBLING_EXCLUDED,
            subject_digest=command.subject_digest,
            sequence=next_sequence,
            action=command.action,
            issue_code=command.issue_code,
            sibling_submission_id=command.sibling_submission_id,
            sibling_candidate_digest=validate_archive_digest(
                command.sibling_candidate_digest,
                field_name="sibling_candidate_digest",
            ),
            reason=validate_utf8_reason(command.reason),
            actor_id=command.context.actor_id,
            occurred_at=now,
            idempotency_key=validate_utf8_id(command.idempotency_key, field_name="idempotency_key"),
            request_fingerprint=request_fingerprint,
            request_payload_json=json.dumps(payload, separators=(",", ":"), sort_keys=True),
        )
        unit_of_work.archive.append_anomaly_resolution(event)
        return AppendArchiveAuditResult(
            event_id=event.event_id,
            sequence=event.sequence,
            replay=False,
        )
