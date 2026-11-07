"""Minimal closure checks for successful frozen archive reads and command replay."""
from __future__ import annotations

import json

from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.archive.business_validation import (
    ARCHIVE_BUSINESS_RULE, ArchiveBusinessCandidate, derive_archive_business_validation,
)
from gateway_backend.application.archive.contracts import (
    ArchiveAuditReferenceInput, compute_archive_digest, compute_candidate_set_digest,
    ArchiveCandidateRef, compute_start_request_fingerprint, assert_resolution_event_integrity, assert_confirmation_event_integrity,
    compute_selection_subject_digest,
)
from gateway_backend.application.archive.errors import ArchiveIntegrityFailure, ArchiveRequestValidation
from gateway_backend.application.archive.ports import ArchiveControlTransaction
from gateway_backend.application.archive.snapshot import load_archive_submission, _load_baseline_configuration, compute_submission_candidate_digest
from gateway_backend.domain.submission.policies import assert_submission_attempt_binding
from gateway_backend.domain.submission.errors import SubmissionBindingConflict, ReviewClosureViolation
from gateway_backend.domain.archive.models import ArchiveConfirmationAction
from gateway_backend.domain.archive.models import (
    ArchivePlan, ArchiveResult, SubmissionDispositionKind, SubmissionDispositionSourceKind,
    ArchiveSubjectKind, affirmative_resolution_action,
)
from gateway_backend.domain.workspace.models import BaselineHead, ResolvedScope


def assert_archive_result_integrity(uow: ArchiveControlTransaction, plan: ArchivePlan, result: ArchiveResult) -> None:
    try:
        frozen = json.loads(plan.frozen_input_json)
        if frozen["schema"] != "backend-vnext/archive-frozen-input/v2" or result.plan_id != plan.plan_id:
            raise ValueError("archive frozen input identity mismatch")
        selected = frozen["selected"]
        if (selected["submission_id"], selected["expected_candidate_digest"], frozen["candidate_set_digest"],
            frozen["expected_baseline_node_id"], frozen["expected_baseline_head_version"]) != (
            plan.selected_submission_id, plan.selected_candidate_digest, plan.candidate_set_digest,
            plan.old_baseline_node_id, plan.old_baseline_head_version):
            raise ValueError("archive plan/request binding mismatch")
        confirmations = tuple(ArchiveAuditReferenceInput(**item) for item in frozen["confirmation_refs"])
        resolutions = tuple(ArchiveAuditReferenceInput(**item) for item in frozen["anomaly_resolution_refs"])
        if tuple((item.subject_digest, item.sequence) for item in confirmations) != tuple((item.subject_digest, item.sequence) for item in plan.confirmation_refs) or tuple((item.subject_digest, item.sequence) for item in resolutions) != tuple((item.subject_digest, item.sequence) for item in plan.anomaly_resolution_refs):
            raise ValueError("archive frozen audit references mismatch")
        fingerprint = compute_start_request_fingerprint(repository_id=plan.repository_id,
            gateway_device_external_key=plan.gateway_device_external_key, business_project_id=plan.business_project_id,
            expected_baseline_node_id=plan.old_baseline_node_id, expected_baseline_head_version=plan.old_baseline_head_version,
            candidate_set_digest=plan.candidate_set_digest, selected_submission_id=plan.selected_submission_id,
            expected_candidate_digest=plan.selected_candidate_digest, confirmation_refs=confirmations, anomaly_resolution_refs=resolutions)
        if fingerprint != plan.request_fingerprint:
            raise ValueError("archive request fingerprint mismatch")
        refs = tuple(ArchiveCandidateRef(**item) for item in frozen["candidate_refs"])
        facts_by_id = {item["submission_id"]: item["configuration_facts_digest"] for item in frozen["configuration_facts"]}
        if len(refs) != len(facts_by_id) or {item.submission_id for item in refs} != set(facts_by_id):
            raise ValueError("archive frozen candidate facts mismatch")
        if len(confirmations) != 1 or confirmations[0].subject_digest != compute_selection_subject_digest(
            candidate_set_digest=plan.candidate_set_digest, selected_submission_id=plan.selected_submission_id,
            expected_candidate_digest=plan.selected_candidate_digest):
            raise ValueError("archive original selection confirmation mismatch")
        confirmation = uow.archive.get_confirmation_event(plan.repository_id, confirmations[0].subject_digest, confirmations[0].sequence)
        if confirmation is None or confirmation.action is not ArchiveConfirmationAction.CONFIRM or (
            confirmation.repository_id, confirmation.gateway_device_external_key, confirmation.business_project_id) != (
            plan.repository_id, plan.gateway_device_external_key, plan.business_project_id):
            raise ValueError("archive original confirmation is missing or not affirmative")
        assert_confirmation_event_integrity(confirmation)
        candidates = []
        for ref in refs:
            submission = load_archive_submission(uow, ref.submission_id, repository_id=plan.repository_id)
            if submission is None or submission.configuration_facts.facts_digest != facts_by_id[ref.submission_id]:
                raise ValueError("archive immutable candidate facts mismatch")
            attempt = uow.submission.get_submit_attempt(submission.submit_attempt_id)
            projection = uow.review.get_projection(submission.submission_id)
            if attempt is None or projection is None:
                raise ValueError("archive immutable submission source is missing")
            assert_submission_attempt_binding(attempt=attempt, submission=submission)
            if compute_submission_candidate_digest(submission, gateway_device_external_key=plan.gateway_device_external_key,
                business_project_id=plan.business_project_id, review_status=projection.status,
                review_sequence=projection.latest_sequence) != ref.expected_candidate_digest:
                raise ValueError("archive immutable candidate identity mismatch")
            if submission.submission_id == plan.selected_submission_id and submission.repository_commit_id != plan.selected_repository_commit_id:
                raise ValueError("archive immutable selected commit mismatch")
            candidates.append(ArchiveBusinessCandidate(ref.submission_id, ref.expected_candidate_digest, submission.configuration_facts))
        old_scope = ResolvedScope(plan.repository_id, BaselineHead(plan.old_baseline_node_id,
            plan.old_baseline_commit_id, plan.old_baseline_head_version))
        baseline, baseline_digest = _load_baseline_configuration(uow, old_scope)
        if compute_candidate_set_digest(repository_id=plan.repository_id,
            gateway_device_external_key=plan.gateway_device_external_key, business_project_id=plan.business_project_id,
            baseline_node_id=plan.old_baseline_node_id, baseline_commit_id=plan.old_baseline_commit_id,
            baseline_head_version=plan.old_baseline_head_version, candidates=refs,
            baseline_facts_digest=baseline_digest, business_rule_id=ARCHIVE_BUSINESS_RULE) != plan.candidate_set_digest:
            raise ValueError("archive candidate set digest mismatch")
        validation = derive_archive_business_validation(candidates=tuple(candidates), baseline=baseline, baseline_facts_digest=baseline_digest)
        if canonicalize_json_value(validation.to_document()) != canonicalize_json_value(frozen["business_validation"]):
            raise ValueError("archive frozen business diagnostics mismatch")
        subjects = {item["subject_digest"]: item["subject"] for item in frozen["anomaly_subjects"]}
        if len(subjects) != len(resolutions) or set(subjects) != {item.subject_digest for item in resolutions}:
            raise ValueError("archive frozen subject references mismatch")
        for audit_ref in resolutions:
            event = uow.archive.get_resolution_event(plan.repository_id, audit_ref.subject_digest, audit_ref.sequence)
            if event is None or (event.repository_id, event.gateway_device_external_key, event.business_project_id) != (
                plan.repository_id, plan.gateway_device_external_key, plan.business_project_id):
                raise ValueError("archive resolution reference is missing")
            assert_resolution_event_integrity(event)
            if event.action is not affirmative_resolution_action(event.subject_kind) or canonicalize_json_value(subjects[audit_ref.subject_digest]) != canonicalize_json_value(json.loads(event.subject_payload_json)):
                raise ValueError("archive resolution source mismatch")
            kind = "anomaly" if event.subject_kind is ArchiveSubjectKind.APPROVED_SIBLING_EXCLUDED else (
                "project-identity-exception" if event.subject_kind is ArchiveSubjectKind.PROJECT_IDENTITY_EXCEPTION else "business-anomaly")
            if compute_archive_digest(kind, subjects[audit_ref.subject_digest]) != audit_ref.subject_digest:
                raise ValueError("archive frozen subject digest mismatch")
        dispositions = {item.submission_id: item for item in result.dispositions}
        if set(dispositions) != set(facts_by_id) or len(dispositions) != len(result.dispositions):
            raise ValueError("archive result disposition set mismatch")
        for sid, disposition in dispositions.items():
            expected = SubmissionDispositionKind.ARCHIVED_BASELINE if sid == plan.selected_submission_id else SubmissionDispositionKind.CLOSED_NOT_ARCHIVED
            if disposition.disposition is not expected or disposition.source_kind is not SubmissionDispositionSourceKind.ARCHIVE or disposition.result_id != result.result_id or (disposition.repository_id, disposition.gateway_device_external_key, disposition.business_project_id) != (plan.repository_id, plan.gateway_device_external_key, plan.business_project_id):
                raise ValueError("archive result disposition source mismatch")
        node = uow.baseline.get_node(result.baseline_node_id)
        if node is None or (node.repository_id, node.parent_node_id, node.source_submission_id, node.commit_id) != (
            plan.repository_id, plan.old_baseline_node_id, plan.selected_submission_id, plan.selected_repository_commit_id):
            raise ValueError("archive result baseline binding mismatch")
    except (ValueError, TypeError, KeyError, ArchiveRequestValidation, SubmissionBindingConflict, ReviewClosureViolation) as exc:
        raise ArchiveIntegrityFailure("stored archive plan/result facts are invalid") from exc
