"""Shared archive candidate snapshot helpers."""

from __future__ import annotations

from dataclasses import dataclass

from gateway_backend.application.archive.business_validation import (
    ARCHIVE_BUSINESS_RULE, ArchiveBusinessCandidate, ArchiveBusinessValidation, derive_archive_business_validation,
)
from gateway_backend.domain.baseline.models import BaselineNodeKind
from gateway_backend.domain.configuration_facts import ConfigurationSideFacts
from gateway_backend.domain.submission.models import Submission
from gateway_backend.domain.submission.policies import assert_submission_attempt_binding
from gateway_backend.domain.submission.errors import SubmissionBindingConflict
from gateway_backend.application.archive.closure import assert_archive_candidate_integrity
from gateway_backend.application.archive.contracts import (
    ARCHIVE_MAX_CANDIDATES,
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
from gateway_backend.application.archive.ports import ArchiveControlTransaction
from gateway_backend.domain.submission.errors import (
    ArchiveCandidateReadBoundExceeded,
    ReviewClosureViolation,
)
from gateway_backend.domain.submission.ports import ArchiveCandidateFacts
from gateway_backend.domain.submission.review import ReviewStatus
from gateway_backend.domain.workspace.models import IdentityContext, ResolvedScope


@dataclass(frozen=True, slots=True)
class ArchiveCandidateRead:
    submission_id: str
    expected_candidate_digest: str
    review_version: int


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
    candidate_reads: tuple[ArchiveCandidateRead, ...]
    candidate_set_digest: str
    active_attempt_ids: tuple[str, ...]
    pending_submission_ids: tuple[str, ...]
    business_candidates: tuple[ArchiveBusinessCandidate, ...]
    business_validation: ArchiveBusinessValidation


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
    except (ValueError, TypeError, KeyError) as exc:
        raise ArchiveIntegrityFailure("candidate configuration facts are invalid") from exc
    candidate_refs: list[ArchiveCandidateRef] = []
    candidate_reads: list[ArchiveCandidateRead] = []
    business_candidates: list[ArchiveBusinessCandidate] = []
    for fact in facts:
        try:
            projection = unit_of_work.review.get_projection(fact.submission.submission_id)
        except ReviewClosureViolation as exc:
            raise ArchiveIntegrityFailure(str(exc)) from exc
        if projection is None:
            raise ArchiveIntegrityFailure("review projection is missing")
        if projection.status is not ReviewStatus.APPROVED:
            continue
        approved_fact = ArchiveCandidateFacts(
            submission=fact.submission,
            review_status=projection.status,
            review_sequence=projection.latest_sequence,
        )
        assert_archive_candidate_integrity(
            unit_of_work,
            context=context,
            resolved_scope=fresh_scope,
            fact=approved_fact,
        )
        candidate_digest = compute_submission_candidate_digest(approved_fact.submission,
            gateway_device_external_key=context.gateway_device_external_key, business_project_id=context.business_project_id,
            review_status=projection.status, review_sequence=projection.latest_sequence)
        business_candidates.append(ArchiveBusinessCandidate(approved_fact.submission.submission_id,
            candidate_digest, approved_fact.submission.configuration_facts))
        candidate_refs.append(
            ArchiveCandidateRef(
                submission_id=approved_fact.submission.submission_id,
                expected_candidate_digest=candidate_digest,
            )
        )
        candidate_reads.append(ArchiveCandidateRead(
            submission_id=approved_fact.submission.submission_id,
            expected_candidate_digest=candidate_digest,
            review_version=projection.optimistic_version,
        ))
    if len(candidate_refs) > ARCHIVE_MAX_CANDIDATES:
        raise ArchiveScopeLimitExceeded()
    baseline_side, baseline_facts_digest = _load_baseline_configuration(unit_of_work, fresh_scope)
    for candidate in business_candidates:
        configuration = candidate.configuration_facts
        if (configuration.baseline_is_initial != (baseline_side is None)
            or configuration.baseline_head_version != head.baseline_head_version):
            raise ArchiveIntegrityFailure("candidate configuration baseline applicability/version mismatch")
        if baseline_side is not None and (configuration.baseline_content_identity != baseline_side.content_identity
            or configuration.baseline_source_submission_id != fresh_scope_node_source(unit_of_work, head.business_baseline_node_id)
            or (configuration.initial_origin == "BASELINE_REUSED" and configuration.initial != baseline_side)):
            raise ArchiveIntegrityFailure("candidate configuration baseline source binding mismatch")
    validation = derive_archive_business_validation(candidates=tuple(business_candidates),
        baseline=baseline_side, baseline_facts_digest=baseline_facts_digest)
    candidate_set_digest = compute_candidate_set_digest(
        repository_id=fresh_scope.repository_id,
        gateway_device_external_key=context.gateway_device_external_key,
        business_project_id=context.business_project_id,
        baseline_node_id=head.business_baseline_node_id,
        baseline_commit_id=head.business_baseline_commit_id,
        baseline_head_version=head.baseline_head_version,
        candidates=tuple(candidate_refs),
        baseline_facts_digest=baseline_facts_digest, business_rule_id=ARCHIVE_BUSINESS_RULE,
    )
    try:
        pending_facts = unit_of_work.submission.list_pending_review_facts(
            fresh_scope.repository_id,
            baseline_node_id=head.business_baseline_node_id,
            baseline_commit_id=head.business_baseline_commit_id,
        )
    except ArchiveCandidateReadBoundExceeded:
        raise ArchiveScopeLimitExceeded() from None
    except (ValueError, TypeError, KeyError) as exc:
        raise ArchiveIntegrityFailure("pending configuration facts are invalid") from exc
    pending_ids: list[str] = []
    for fact in pending_facts:
        try:
            projection = unit_of_work.review.get_projection(fact.submission.submission_id)
        except ReviewClosureViolation as exc:
            raise ArchiveIntegrityFailure(str(exc)) from exc
        if projection is None:
            raise ArchiveIntegrityFailure("review projection is missing")
        if projection.status is not ReviewStatus.PENDING:
            continue
        assert_archive_candidate_integrity(
            unit_of_work, context=context, resolved_scope=fresh_scope, fact=fact,
        )
        pending_ids.append(fact.submission.submission_id)
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
        candidate_reads=tuple(candidate_reads),
        candidate_set_digest=candidate_set_digest,
        active_attempt_ids=tuple(item.submit_attempt_id for item in active_attempts),
        pending_submission_ids=tuple(pending_ids),
        business_candidates=tuple(business_candidates), business_validation=validation,
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


def load_archive_submission(unit_of_work: ArchiveControlTransaction, submission_id: str, *,
        workspace_id: str | None = None, repository_id: str | None = None) -> Submission | None:
    try:
        return unit_of_work.submission.get_submission(submission_id,
            workspace_id=workspace_id, repository_id=repository_id)
    except (ValueError, TypeError, KeyError) as exc:
        raise ArchiveIntegrityFailure("submission configuration facts are invalid") from exc


def fresh_scope_node_source(unit_of_work: ArchiveControlTransaction, node_id: str) -> str | None:
    node = unit_of_work.baseline.get_node(node_id)
    if node is None:
        raise ArchiveIntegrityFailure("baseline node is missing")
    return node.source_submission_id


def _load_baseline_configuration(unit_of_work: ArchiveControlTransaction,
        scope: ResolvedScope) -> tuple[ConfigurationSideFacts | None, str | None]:
    head = scope.baseline_head
    node = unit_of_work.baseline.get_node(head.business_baseline_node_id)
    if node is None or node.repository_id != scope.repository_id or node.commit_id != head.business_baseline_commit_id:
        raise ArchiveIntegrityFailure("baseline configuration node binding mismatch")
    if node.kind is BaselineNodeKind.INITIAL:
        return None, None
    if node.source_submission_id is None:
        raise ArchiveIntegrityFailure("baseline source submission is missing")
    source = load_archive_submission(unit_of_work, node.source_submission_id, repository_id=scope.repository_id)
    if source is None or source.repository_commit_id != node.commit_id:
        raise ArchiveIntegrityFailure("baseline source submission binding mismatch")
    workspace = unit_of_work.workspace.get_workspace(source.workspace_id)
    if workspace is None or (workspace.gateway_device_external_key, workspace.business_project_id, workspace.repository_id) != (
        node.gateway_device_external_key, node.business_project_id, scope.repository_id):
        raise ArchiveIntegrityFailure("baseline source submission scope mismatch")
    try:
        attempt = unit_of_work.submission.get_submit_attempt(source.submit_attempt_id)
        if attempt is None:
            raise ArchiveIntegrityFailure("baseline source attempt is missing")
        assert_submission_attempt_binding(attempt=attempt, submission=source)
    except (ValueError, TypeError, KeyError, SubmissionBindingConflict) as exc:
        raise ArchiveIntegrityFailure("baseline source facts binding mismatch") from exc
    return source.configuration_facts.modified, source.configuration_facts.facts_digest


def compute_submission_candidate_digest(submission: Submission, *, gateway_device_external_key: str,
        business_project_id: str, review_status: ReviewStatus, review_sequence: int) -> str:
    return compute_candidate_digest(
            repository_id=submission.repository_id,
            gateway_device_external_key=gateway_device_external_key,
            business_project_id=business_project_id,
            workspace_id=submission.workspace_id,
            workspace_generation=submission.workspace_generation,
            submission_id=submission.submission_id,
            submit_attempt_id=submission.submit_attempt_id,
            upload_revision_id=submission.upload_revision_id,
            preview_result_id=submission.preview_result_id,
            based_on_baseline_node_id=submission.based_on_baseline_node_id,
            business_baseline_commit_id=submission.business_baseline_commit_id,
            repository_commit_id=submission.repository_commit_id,
            canonical_business_digest=submission.canonical_business_digest,
            configuration_facts_digest=submission.configuration_facts.facts_digest,
            canonicalization_manifest_ref=submission.canonicalization_manifest_ref,
            canonicalization_manifest_digest=submission.canonicalization_manifest_digest,
            source_artifact_refs=submission.source_artifact_refs,
            requested_verification_policy=submission.requested_verification_policy.value,
            completed_verification_policy=submission.completed_verification_policy.value,
            review_status=review_status_to_archive_value(review_status),
            review_sequence=review_sequence,
        )
