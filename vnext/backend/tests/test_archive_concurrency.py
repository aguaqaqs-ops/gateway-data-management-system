"""Archive concurrency barrier tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway_backend.application.archive.errors import ActiveSubmitAttempt
from gateway_backend.application.archive.start import start_archive
from gateway_backend.application.archive.contracts import ArchiveAuditReferenceInput
from gateway_backend.application.submission.review_transaction import apply_review_transaction
from gateway_backend.domain.submission.review import ReviewAction
from gateway_backend.application.archive.start import StartArchiveCommand
from gateway_backend.domain.submission.ports import ArchiveActiveAttemptFacts
from tests.support.archive_fixtures import (
    ArchiveSeed,
    append_selection_confirmation,
    archive_seed_from_review_seed,
    seed_approved_archive_candidate,
)
from tests.support.workspace_fixtures import FixedScopeResolutionPort
from tests.test_review_transactions import (
    TS2,
    _apply_command,
    _apply_review,
    _seed_pending_review_submission,
    _uow_factory,
)
from tests.test_submit_transactions import BASELINE_HEAD

pytestmark = [pytest.mark.unit, pytest.mark.serial]

TS_ARCHIVE = datetime(2024, 7, 1, 12, 0, 0, tzinfo=UTC)


def _start_command(seed: ArchiveSeed, confirmation_sequence: int) -> StartArchiveCommand:
    return StartArchiveCommand(
        context=seed.archiver_context,
        idempotency_key="archive-start-1",
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
    )


def test_archive_start_blocks_when_active_submit_attempt_exists(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_backend.infrastructure.control_db.sqlite_submission import SQLiteSubmissionRepository

    seed = seed_approved_archive_candidate(db_path)
    confirmation_sequence = append_selection_confirmation(seed, now=TS_ARCHIVE)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )

    def active_attempts(
        self: SQLiteSubmissionRepository,
        repository_id: str,
    ) -> tuple[ArchiveActiveAttemptFacts, ...]:
        return (ArchiveActiveAttemptFacts(submit_attempt_id="attempt-active-1", state="PREPARED"),)

    monkeypatch.setattr(SQLiteSubmissionRepository, "list_active_submit_attempts", active_attempts)
    with pytest.raises(ActiveSubmitAttempt):
        start_archive(
            command=_start_command(seed, confirmation_sequence),
            scope_resolution=scope_resolution,
            unit_of_work_factory=_uow_factory(db_path),
            now=TS_ARCHIVE,
        )


def test_review_return_loses_race_when_archive_commits_first(db_path: Path) -> None:
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-race"),
    )
    seed = archive_seed_from_review_seed(review_seed)
    confirmation_sequence = append_selection_confirmation(seed, now=TS_ARCHIVE)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    start_archive(
        command=_start_command(seed, confirmation_sequence),
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(db_path),
        now=TS_ARCHIVE,
    )
    from gateway_backend.application.submission.errors import ArchiveClosed

    with pytest.raises(ArchiveClosed):
        apply_review_transaction(
            command=_apply_command(
                review_seed,
                action=ReviewAction.RETURN_FOR_REVISION,
                reason="too late",
                expected_review_version=1,
                idempotency_key="return-after-archive",
            ),
            scope_resolution=scope_resolution,
            unit_of_work_factory=_uow_factory(db_path),
            now=TS2,
        )
