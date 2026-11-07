"""Close one approved submission and release its exact Workspace in one transaction."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from gateway_backend.application.archive.contracts import compute_close_request_fingerprint, validate_utf8_id, validate_non_negative_int
from gateway_backend.application.archive.errors import ArchiveIntegrityFailure, SubmissionClosureNotFound
from gateway_backend.application.archive.ports import ArchiveControlUnitOfWorkFactory
from gateway_backend.application.archive.queries import PERMISSION_ARCHIVE_SUBMISSION
from gateway_backend.application.archive.snapshot import load_archive_submission
from gateway_backend.application.submission.errors import ArchiveClosed, BaselineVersionConflict, IdempotencyConflict
from gateway_backend.application.submission.review import assert_review_scope, assert_review_workspace_bindings
from gateway_backend.domain.archive.models import (
    ManualSubmissionClosure, SubmissionDisposition, SubmissionDispositionKind, SubmissionDispositionSourceKind,
)
from gateway_backend.domain.submission.errors import InvalidReviewTransition, ReviewClosureViolation, ReviewVersionConflict
from gateway_backend.domain.submission.models import Submission
from gateway_backend.domain.submission.review import ReviewStatus
from gateway_backend.domain.workspace.errors import ScopeForbidden
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.domain.workspace.policies import assert_permission


@dataclass(frozen=True, slots=True)
class CloseSubmissionCommand:
    context: IdentityContext
    submission_id: str
    idempotency_key: str
    expected_review_version: int
    expected_baseline_node_id: str
    expected_baseline_head_version: int
    reason: str


@dataclass(frozen=True, slots=True)
class CloseSubmissionResult:
    disposition: SubmissionDisposition
    replay: bool


def close_submission(*, command: CloseSubmissionCommand,
        unit_of_work_factory: ArchiveControlUnitOfWorkFactory, now: datetime) -> CloseSubmissionResult:
    assert_permission(command.context, PERMISSION_ARCHIVE_SUBMISSION)
    validate_utf8_id(command.idempotency_key, field_name="idempotency_key")
    with unit_of_work_factory(read_only=False) as uow:
        scope = uow.resolve_provisioned_scope(gateway_device_external_key=command.context.gateway_device_external_key,
            business_project_id=command.context.business_project_id)
        binding = uow.submission.get_submission_access_binding(command.submission_id)
        workspace = None if binding is None else uow.workspace.get_workspace(binding.workspace_id)
        if binding is None or workspace is None:
            raise SubmissionClosureNotFound()
        try:
            assert_review_scope(binding, workspace, scope, command.context)
        except ScopeForbidden:
            raise SubmissionClosureNotFound() from None
        fingerprint = compute_close_request_fingerprint(repository_id=scope.repository_id,
            gateway_device_external_key=command.context.gateway_device_external_key,
            business_project_id=command.context.business_project_id, submission_id=command.submission_id,
            expected_review_version=command.expected_review_version,
            expected_baseline_node_id=command.expected_baseline_node_id,
            expected_baseline_head_version=command.expected_baseline_head_version, reason=command.reason)
        try:
            existing = uow.archive.find_manual_close_by_key(scope.repository_id,
                command.context.gateway_device_external_key, command.context.business_project_id, command.idempotency_key)
        except (ValueError, TypeError, KeyError) as exc:
            raise ArchiveIntegrityFailure("manual closure facts are invalid") from exc
        if existing is not None:
            stored_closure = existing.manual_closure
            stored_submission = None if stored_closure is None else load_archive_submission(uow,
                existing.submission_id, workspace_id=stored_closure.workspace_id, repository_id=scope.repository_id)
            if stored_submission is None:
                raise ArchiveIntegrityFailure("manual closure source submission is missing")
            _assert_manual_close_binding(existing, stored_submission)
            if existing.submission_id != command.submission_id:
                raise IdempotencyConflict(idempotency_key=command.idempotency_key)
        submission = load_archive_submission(uow, command.submission_id,
            workspace_id=workspace.workspace_id, repository_id=scope.repository_id)
        if submission is None:
            raise SubmissionClosureNotFound()
        if existing is not None:
            _assert_manual_close_binding(existing, submission)
            closure = existing.manual_closure
            if closure is None or closure.request_fingerprint != fingerprint:
                raise IdempotencyConflict(idempotency_key=command.idempotency_key)
            return CloseSubmissionResult(existing, True)
        head = scope.baseline_head
        if (head.business_baseline_node_id, head.baseline_head_version) != (
            command.expected_baseline_node_id, command.expected_baseline_head_version):
            raise BaselineVersionConflict("expected baseline head does not match current head")
        if uow.archive.is_submission_closed(submission.submission_id):
            raise ArchiveClosed()
        try:
            projection = uow.review.get_projection(submission.submission_id)
        except ReviewClosureViolation as exc:
            raise ArchiveIntegrityFailure("manual close review facts are invalid") from exc
        if projection is None:
            raise ArchiveIntegrityFailure("manual close review projection is missing")
        if projection.optimistic_version != command.expected_review_version:
            raise ReviewVersionConflict(expected=command.expected_review_version, actual=projection.optimistic_version)
        if projection.status is not ReviewStatus.APPROVED:
            raise InvalidReviewTransition(current=projection.status.value, action="CLOSE_NOT_ARCHIVED")
        occupancy = uow.submission.get_workspace_occupancy(workspace.workspace_id)
        assert_review_workspace_bindings(submission, workspace, occupancy)
        closure = ManualSubmissionClosure(command.context.actor_id, now, command.reason,
            command.idempotency_key, fingerprint, command.expected_review_version,
            command.expected_baseline_node_id, command.expected_baseline_head_version,
            workspace.workspace_id, workspace.generation, submission.upload_revision_id,
            submission.preview_result_id, workspace.optimistic_version, submission.configuration_facts.facts_digest)
        disposition = SubmissionDisposition(submission.submission_id, SubmissionDispositionKind.CLOSED_NOT_ARCHIVED,
            SubmissionDispositionSourceKind.MANUAL_CLOSE, None, scope.repository_id,
            command.context.gateway_device_external_key, command.context.business_project_id, closure)
        uow.archive.insert_manual_close(disposition)
        uow.workspace.save_workspace(replace(workspace, current_upload_revision_id=None,
            current_preview_result_id=None, optimistic_version=validate_non_negative_int(workspace.optimistic_version + 1, field_name="next_workspace_version"), updated_at=now),
            expected_version=workspace.optimistic_version)
        uow.submission.delete_workspace_submission_occupancy(workspace.workspace_id,
            expected_submission_id=submission.submission_id)
        return CloseSubmissionResult(disposition, False)


def _assert_manual_close_binding(record: SubmissionDisposition, submission: Submission) -> None:
    closure = record.manual_closure
    if closure is None:
        raise ArchiveIntegrityFailure("manual closure source is missing")
    if (record.submission_id, record.repository_id, closure.workspace_id, closure.workspace_generation,
        closure.upload_revision_id, closure.preview_result_id, closure.configuration_facts_digest) != (
        submission.submission_id, submission.repository_id, submission.workspace_id, submission.workspace_generation,
        submission.upload_revision_id, submission.preview_result_id, submission.configuration_facts.facts_digest):
        raise ArchiveIntegrityFailure("manual closure submission facts binding mismatch")
    try:
        fingerprint = compute_close_request_fingerprint(repository_id=record.repository_id,
            gateway_device_external_key=record.gateway_device_external_key, business_project_id=record.business_project_id,
            submission_id=record.submission_id, expected_review_version=closure.expected_review_version,
            expected_baseline_node_id=closure.expected_baseline_node_id,
            expected_baseline_head_version=closure.expected_baseline_head_version, reason=closure.reason)
    except (ValueError, TypeError) as exc:
        raise ArchiveIntegrityFailure("manual closure request identity is invalid") from exc
    if fingerprint != closure.request_fingerprint:
        raise ArchiveIntegrityFailure("manual closure request fingerprint mismatch")
