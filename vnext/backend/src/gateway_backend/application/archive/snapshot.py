"""Shared archive candidate snapshot helpers."""

from __future__ import annotations

from dataclasses import dataclass

from gateway_backend.application.archive.contracts import (
    ArchiveCandidateRef,
    compute_candidate_digest,
    compute_candidate_set_digest,
    review_status_to_archive_value,
)
from gateway_backend.application.archive.errors import (
    ActiveSubmitAttempt,
    ArchiveIntegrityFailure,
    ArchiveScopeLimitExceeded,
)
from gateway_backend.domain.submission.errors import ArchiveCandidateReadBoundExceeded
from gateway_backend.application.archive.ports import ArchiveControlTransaction
from gateway_backend.domain.submission.review import ReviewStatus
from gateway_backend.domain.workspace.models import IdentityContext, ResolvedScope


@dataclass(frozen=True, slots=True)
class ArchiveCandidateSnapshot:
    resolved_scope: ResolvedScope
    repository_id: str
    gateway_device_external_key: str
    business_project_id: str
    baseline_node_id: str
    baseline_commit_id: str
    baseline_head_version: int
    candidates: tuple[ArchiveCandidateRef, ...]
    candidate_set_digest: str
    active_attempt_ids: tuple[str, ...]


def load_archive_candidate_snapshot(
    unit_of_work: ArchiveControlTransaction,
    context: IdentityContext,
    resolved_scope: ResolvedScope,
) -> ArchiveCandidateSnapshot:
    fresh_scope = unit_of_work.resolve_provisioned_scope(
        gateway_device_external_key=context.gateway_device_external_key,
        business_project_id=context.business_project_id,
    )
    if fresh_scope.repository_id != resolved_scope.repository_id:
        raise ArchiveIntegrityFailure("repository scope mismatch")
    head = fresh_scope.baseline_head
    try:
        facts = unit_of_work.submission.list_archive_candidate_facts(
            fresh_scope.repository_id,
            baseline_node_id=head.business_baseline_node_id,
            baseline_commit_id=head.business_baseline_commit_id,
        )
    except ArchiveCandidateReadBoundExceeded:
        raise ArchiveScopeLimitExceeded() from None
    candidate_refs: list[ArchiveCandidateRef] = []
    for fact in facts:
        if fact.closed_by_archive:
            continue
        if fact.review_status is not ReviewStatus.APPROVED:
            continue
        candidate_digest = compute_candidate_digest(
            repository_id=fact.submission.repository_id,
            gateway_device_external_key=context.gateway_device_external_key,
            business_project_id=context.business_project_id,
            workspace_id=fact.submission.workspace_id,
            workspace_generation=fact.submission.workspace_generation,
            submission_id=fact.submission.submission_id,
            submit_attempt_id=fact.submission.submit_attempt_id,
            upload_revision_id=fact.submission.upload_revision_id,
            preview_result_id=fact.submission.preview_result_id,
            based_on_baseline_node_id=fact.submission.based_on_baseline_node_id,
            business_baseline_commit_id=fact.submission.business_baseline_commit_id,
            repository_commit_id=fact.submission.repository_commit_id,
            canonical_business_digest=fact.submission.canonical_business_digest,
            canonicalization_manifest_ref=fact.submission.canonicalization_manifest_ref,
            canonicalization_manifest_digest=fact.submission.canonicalization_manifest_digest,
            source_artifact_refs=fact.submission.source_artifact_refs,
            requested_verification_policy=fact.submission.requested_verification_policy.value,
            completed_verification_policy=fact.submission.completed_verification_policy.value,
            review_status=review_status_to_archive_value(fact.review_status),
            review_sequence=fact.review_sequence,
        )
        candidate_refs.append(
            ArchiveCandidateRef(
                submission_id=fact.submission.submission_id,
                expected_candidate_digest=candidate_digest,
            )
        )
    candidate_set_digest = compute_candidate_set_digest(
        repository_id=fresh_scope.repository_id,
        gateway_device_external_key=context.gateway_device_external_key,
        business_project_id=context.business_project_id,
        baseline_node_id=head.business_baseline_node_id,
        baseline_commit_id=head.business_baseline_commit_id,
        baseline_head_version=head.baseline_head_version,
        candidates=tuple(candidate_refs),
    )
    active_attempts = unit_of_work.submission.list_active_submit_attempts(fresh_scope.repository_id)
    return ArchiveCandidateSnapshot(
        resolved_scope=fresh_scope,
        repository_id=fresh_scope.repository_id,
        gateway_device_external_key=context.gateway_device_external_key,
        business_project_id=context.business_project_id,
        baseline_node_id=head.business_baseline_node_id,
        baseline_commit_id=head.business_baseline_commit_id,
        baseline_head_version=head.baseline_head_version,
        candidates=tuple(candidate_refs),
        candidate_set_digest=candidate_set_digest,
        active_attempt_ids=tuple(item.submit_attempt_id for item in active_attempts),
    )


def collect_repository_submit_blockers(
    unit_of_work: ArchiveControlTransaction,
    repository_id: str,
) -> tuple[str, ...]:
    active_attempts = unit_of_work.submission.list_active_submit_attempts(repository_id)
    occupancy = unit_of_work.submission.get_repository_occupancy(repository_id)
    if active_attempts and occupancy is not None:
        active_ids = {item.submit_attempt_id for item in active_attempts}
        if occupancy.submit_attempt_id not in active_ids:
            return ("ARCHIVE_INTEGRITY_FAILURE",)
    if active_attempts:
        return ("ACTIVE_SUBMIT_ATTEMPT",)
    if occupancy is not None:
        return ("ARCHIVE_INTEGRITY_FAILURE",)
    return ()


def assert_repository_submit_gate(
    unit_of_work: ArchiveControlTransaction,
    repository_id: str,
) -> None:
    blockers = collect_repository_submit_blockers(unit_of_work, repository_id)
    if "ACTIVE_SUBMIT_ATTEMPT" in blockers:
        raise ActiveSubmitAttempt()
    if "ARCHIVE_INTEGRITY_FAILURE" in blockers:
        raise ArchiveIntegrityFailure("repository submit occupancy is inconsistent")
