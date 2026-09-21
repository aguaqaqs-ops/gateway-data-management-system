"""Archive journey helpers for unit tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from gateway_backend.application.archive.audit import (
    AppendArchiveAnomalyResolutionCommand,
    AppendArchiveConfirmationCommand,
    append_archive_anomaly_resolution,
    append_archive_confirmation,
)
from gateway_backend.application.archive.contracts import (
    ArchiveAuditReferenceInput,
    ArchiveSelectedRef,
    compute_anomaly_subject_digest,
    compute_selection_subject_digest,
)
from gateway_backend.application.archive.queries import (
    APPROVED_SIBLING_EXCLUDED_ISSUE,
    PERMISSION_ARCHIVE_SUBMISSION,
    get_archive_candidates,
)
from gateway_backend.application.archive.start import (
    StartArchiveCommand,
    StartArchiveResult,
    start_archive,
)
from gateway_backend.domain.archive.models import (
    ArchiveAnomalyResolutionAction,
    ArchiveConfirmationAction,
)
from gateway_backend.domain.submission.review import ReviewAction
from gateway_backend.domain.workspace.models import IdentityContext
from tests.support.workspace_fixtures import FixedScopeResolutionPort, make_identity
from tests.test_review_transactions import (
    ReviewSeed,
    _apply_command,
    _apply_review,
    _seed_additional_pending_review_submission,
    _seed_pending_review_submission,
    _uow_factory,
)
from tests.test_submit_transactions import BASELINE_HEAD

TS_ARCHIVE = datetime(2024, 7, 1, 12, 0, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class ArchiveSeed:
    db_path: Path
    submission_id: str
    repository_id: str
    archiver_context: IdentityContext
    selected_ref: ArchiveSelectedRef
    candidate_set_digest: str
    selection_subject_digest: str


@dataclass(frozen=True, slots=True)
class DualSiblingArchiveSeed:
    db_path: Path
    primary: ArchiveSeed
    sibling_submission_id: str
    sibling_candidate_digest: str
    anomaly_subject_digest: str


def _archiver_context(device_key: str, project_id: str) -> IdentityContext:
    return make_identity(
        actor_id="archiver-1",
        device_key=device_key,
        project_id=project_id,
        permissions=frozenset({PERMISSION_ARCHIVE_SUBMISSION}),
    )


def archive_seed_from_review_seed(review_seed: ReviewSeed) -> ArchiveSeed:
    archiver_context = _archiver_context(
        review_seed.reviewer_context.gateway_device_external_key,
        review_seed.reviewer_context.business_project_id,
    )
    scope_resolution = FixedScopeResolutionPort(
        repository_id=review_seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    candidates = get_archive_candidates(
        context=archiver_context,
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(review_seed.db_path),
    )
    assert len(candidates.candidates) == 1
    selected_ref = ArchiveSelectedRef(
        submission_id=candidates.candidates[0].submission_id,
        expected_candidate_digest=candidates.candidates[0].expected_candidate_digest,
    )
    selection_subject_digest = compute_selection_subject_digest(
        candidate_set_digest=candidates.candidate_set_digest,
        selected_submission_id=selected_ref.submission_id,
        expected_candidate_digest=selected_ref.expected_candidate_digest,
    )
    return ArchiveSeed(
        db_path=review_seed.db_path,
        submission_id=review_seed.submission_id,
        repository_id=review_seed.repository_id,
        archiver_context=archiver_context,
        selected_ref=selected_ref,
        candidate_set_digest=candidates.candidate_set_digest,
        selection_subject_digest=selection_subject_digest,
    )


def seed_approved_archive_candidate(db_path: Path) -> ArchiveSeed:
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-archive"),
    )
    return archive_seed_from_review_seed(review_seed)


def seed_approved_dual_sibling_archive(db_path: Path) -> DualSiblingArchiveSeed:
    primary_review = _seed_pending_review_submission(db_path)
    _apply_review(
        primary_review,
        _apply_command(primary_review, action=ReviewAction.APPROVE, idempotency_key="approve-primary"),
    )
    sibling_review = _seed_additional_pending_review_submission(
        db_path,
        submission_id="sub-2",
        device_key=primary_review.reviewer_context.gateway_device_external_key,
        repository_id=primary_review.repository_id,
        project_id=primary_review.reviewer_context.business_project_id,
    )
    _apply_review(
        sibling_review,
        _apply_command(sibling_review, action=ReviewAction.APPROVE, idempotency_key="approve-sibling"),
    )
    archiver_context = _archiver_context(
        primary_review.reviewer_context.gateway_device_external_key,
        primary_review.reviewer_context.business_project_id,
    )
    scope_resolution = FixedScopeResolutionPort(
        repository_id=primary_review.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    candidates = get_archive_candidates(
        context=archiver_context,
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(db_path),
    )
    assert len(candidates.candidates) == 2
    primary_ref = next(
        candidate
        for candidate in candidates.candidates
        if candidate.submission_id == primary_review.submission_id
    )
    sibling_ref = next(
        candidate
        for candidate in candidates.candidates
        if candidate.submission_id == sibling_review.submission_id
    )
    selection_subject_digest = compute_selection_subject_digest(
        candidate_set_digest=candidates.candidate_set_digest,
        selected_submission_id=primary_ref.submission_id,
        expected_candidate_digest=primary_ref.expected_candidate_digest,
    )
    primary = ArchiveSeed(
        db_path=db_path,
        submission_id=primary_ref.submission_id,
        repository_id=primary_review.repository_id,
        archiver_context=archiver_context,
        selected_ref=ArchiveSelectedRef(
            submission_id=primary_ref.submission_id,
            expected_candidate_digest=primary_ref.expected_candidate_digest,
        ),
        candidate_set_digest=candidates.candidate_set_digest,
        selection_subject_digest=selection_subject_digest,
    )
    anomaly_subject_digest = compute_anomaly_subject_digest(
        selection_subject_digest=primary.selection_subject_digest,
        issue_code=APPROVED_SIBLING_EXCLUDED_ISSUE,
        sibling_submission_id=sibling_ref.submission_id,
        sibling_candidate_digest=sibling_ref.expected_candidate_digest,
    )
    return DualSiblingArchiveSeed(
        db_path=db_path,
        primary=primary,
        sibling_submission_id=sibling_ref.submission_id,
        sibling_candidate_digest=sibling_ref.expected_candidate_digest,
        anomaly_subject_digest=anomaly_subject_digest,
    )


def append_selection_confirmation(
    seed: ArchiveSeed,
    *,
    idempotency_key: str = "confirm-key-1",
    now: datetime = TS_ARCHIVE,
) -> int:
    scope_resolution = FixedScopeResolutionPort(
        repository_id=seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    result = append_archive_confirmation(
        command=AppendArchiveConfirmationCommand(
            context=seed.archiver_context,
            idempotency_key=idempotency_key,
            expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
            expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
            selected=seed.selected_ref,
            candidate_set_digest=seed.candidate_set_digest,
            subject_digest=seed.selection_subject_digest,
            expected_sequence=0,
            action=ArchiveConfirmationAction.CONFIRM,
            reason="confirm archive selection",
        ),
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(seed.db_path),
        now=now,
    )
    return result.sequence


def append_anomaly_resolution(
    seed: ArchiveSeed,
    *,
    anomaly_subject_digest: str,
    sibling_submission_id: str,
    sibling_candidate_digest: str,
    idempotency_key: str = "resolve-key-1",
    now: datetime = TS_ARCHIVE,
) -> int:
    scope_resolution = FixedScopeResolutionPort(
        repository_id=seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    result = append_archive_anomaly_resolution(
        command=AppendArchiveAnomalyResolutionCommand(
            context=seed.archiver_context,
            idempotency_key=idempotency_key,
            expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
            expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
            selected=seed.selected_ref,
            candidate_set_digest=seed.candidate_set_digest,
            subject_digest=anomaly_subject_digest,
            expected_sequence=0,
            action=ArchiveAnomalyResolutionAction.ACKNOWLEDGE_EXCLUSION,
            reason="acknowledge sibling exclusion",
            issue_code=APPROVED_SIBLING_EXCLUDED_ISSUE,
            sibling_submission_id=sibling_submission_id,
            sibling_candidate_digest=sibling_candidate_digest,
        ),
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(seed.db_path),
        now=now,
    )
    return result.sequence


def start_archive_for_seed(
    seed: ArchiveSeed,
    *,
    idempotency_key: str = "archive-start-1",
    confirmation_sequence: int,
    anomaly_resolution_sequences: tuple[tuple[str, int], ...] = (),
    now: datetime = TS_ARCHIVE,
) -> StartArchiveResult:
    scope_resolution = FixedScopeResolutionPort(
        repository_id=seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    return start_archive(
        command=StartArchiveCommand(
            context=seed.archiver_context,
            idempotency_key=idempotency_key,
            expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
            expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
            candidate_set_digest=seed.candidate_set_digest,
            selected_ref=seed.selected_ref,
            confirmation_refs=(
                ArchiveAuditReferenceInput(
                    subject_digest=seed.selection_subject_digest,
                    sequence=confirmation_sequence,
                ),
            ),
            anomaly_resolution_refs=tuple(
                ArchiveAuditReferenceInput(subject_digest=subject_digest, sequence=sequence)
                for subject_digest, sequence in anomaly_resolution_sequences
            ),
        ),
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(seed.db_path),
        now=now,
    )


def prepare_dual_sibling_start(
    dual_seed: DualSiblingArchiveSeed,
    *,
    now: datetime = TS_ARCHIVE,
) -> tuple[int, int]:
    confirmation_sequence = append_selection_confirmation(dual_seed.primary, now=now)
    resolution_sequence = append_anomaly_resolution(
        dual_seed.primary,
        anomaly_subject_digest=dual_seed.anomaly_subject_digest,
        sibling_submission_id=dual_seed.sibling_submission_id,
        sibling_candidate_digest=dual_seed.sibling_candidate_digest,
        now=now,
    )
    return confirmation_sequence, resolution_sequence
