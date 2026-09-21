"""Archive journey helpers for unit tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from gateway_backend.application.archive.audit import (
    AppendArchiveConfirmationCommand,
    append_archive_confirmation,
)
from gateway_backend.application.archive.contracts import (
    ArchiveAuditReferenceInput,
    ArchiveSelectedRef,
    compute_selection_subject_digest,
)
from gateway_backend.application.archive.queries import (
    PERMISSION_ARCHIVE_SUBMISSION,
    get_archive_candidates,
)
from gateway_backend.application.archive.start import (
    StartArchiveCommand,
    StartArchiveResult,
    start_archive,
)
from gateway_backend.domain.archive.models import ArchiveConfirmationAction
from gateway_backend.domain.submission.review import ReviewAction
from gateway_backend.domain.workspace.models import IdentityContext
from tests.support.workspace_fixtures import FixedScopeResolutionPort, make_identity
from tests.test_review_transactions import (
    ReviewSeed,
    _apply_command,
    _apply_review,
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


def start_archive_for_seed(
    seed: ArchiveSeed,
    *,
    idempotency_key: str = "archive-start-1",
    confirmation_sequence: int,
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
            anomaly_resolution_refs=(),
        ),
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(seed.db_path),
        now=now,
    )
