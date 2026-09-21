"""Archive Start transaction tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import pytest

from gateway_backend.application.archive.errors import ArchiveConfirmationRequired
from gateway_backend.application.archive.start import StartArchiveCommand
from gateway_backend.application.submission.errors import IdempotencyConflict
from gateway_backend.domain.archive.models import ArchiveDispositionKind
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.sqlite_baseline import get_current_head_from_connection
from tests.support.archive_fixtures import (
    append_selection_confirmation,
    seed_approved_archive_candidate,
    start_archive_for_seed,
)
from tests.support.workspace_fixtures import FixedScopeResolutionPort
from tests.test_review_transactions import _uow_factory
from tests.test_submit_transactions import BASELINE_HEAD

pytestmark = pytest.mark.unit

TS_ARCHIVE = datetime(2024, 7, 1, 12, 0, 0, tzinfo=UTC)


def test_start_archive_requires_confirmation_before_plan_is_written(db_path: Path) -> None:
    seed = seed_approved_archive_candidate(db_path)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    from gateway_backend.application.archive.start import start_archive
    from gateway_backend.application.archive.contracts import ArchiveAuditReferenceInput

    with pytest.raises(ArchiveConfirmationRequired):
        start_archive(
            command=StartArchiveCommand(
                context=seed.archiver_context,
                idempotency_key="start-without-confirm",
                expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
                expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
                candidate_set_digest=seed.candidate_set_digest,
                selected_ref=seed.selected_ref,
                confirmation_refs=(
                    ArchiveAuditReferenceInput(
                        subject_digest=seed.selection_subject_digest,
                        sequence=1,
                    ),
                ),
                anomaly_resolution_refs=(),
            ),
            scope_resolution=scope_resolution,
            unit_of_work_factory=_uow_factory(db_path),
            now=TS_ARCHIVE,
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        plan_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_plan_records"
        ).fetchone()[0]
    assert plan_count == 0


def test_start_archive_persists_plan_result_head_and_releases_workspace(db_path: Path) -> None:
    seed = seed_approved_archive_candidate(db_path)
    confirmation_sequence = append_selection_confirmation(seed, now=TS_ARCHIVE)
    result = start_archive_for_seed(
        seed,
        confirmation_sequence=confirmation_sequence,
        now=TS_ARCHIVE,
    )
    assert result.replay is False
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        head = get_current_head_from_connection(unit_of_work.connection, seed.repository_id)
        assert head.baseline_head_version == BASELINE_HEAD.baseline_head_version + 1
        assert head.business_baseline_commit_id == result.baseline_commit_id
        disposition = unit_of_work.archive.list_dispositions_for_submission(seed.submission_id)
        assert len(disposition) == 1
        assert disposition[0].disposition is ArchiveDispositionKind.ARCHIVED_BASELINE
        submission = unit_of_work.submission.get_submission(seed.submission_id)
        assert submission is not None
        occupancy = unit_of_work.submission.get_workspace_occupancy(submission.workspace_id)
        assert occupancy is None


def test_start_archive_replay_returns_existing_result_after_head_advances(db_path: Path) -> None:
    seed = seed_approved_archive_candidate(db_path)
    confirmation_sequence = append_selection_confirmation(seed, now=TS_ARCHIVE)
    first = start_archive_for_seed(
        seed,
        confirmation_sequence=confirmation_sequence,
        now=TS_ARCHIVE,
    )
    replay = start_archive_for_seed(
        seed,
        confirmation_sequence=confirmation_sequence,
        now=TS_ARCHIVE,
    )
    assert replay.replay is True
    assert replay.archive_plan_id == first.archive_plan_id
    assert replay.archive_result_id == first.archive_result_id


def test_start_archive_rejects_conflicting_idempotency_fingerprint(db_path: Path) -> None:
    seed = seed_approved_archive_candidate(db_path)
    confirmation_sequence = append_selection_confirmation(seed, now=TS_ARCHIVE)
    start_archive_for_seed(seed, confirmation_sequence=confirmation_sequence, now=TS_ARCHIVE)
    from gateway_backend.application.archive.start import start_archive
    from gateway_backend.application.archive.contracts import ArchiveAuditReferenceInput

    scope_resolution = FixedScopeResolutionPort(
        repository_id=seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    with pytest.raises(IdempotencyConflict):
        start_archive(
            command=StartArchiveCommand(
                context=seed.archiver_context,
                idempotency_key="archive-start-1",
                expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
                expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
                candidate_set_digest="sha256:" + "f" * 64,
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
            unit_of_work_factory=_uow_factory(db_path),
            now=TS_ARCHIVE,
        )


def test_start_archive_rolls_back_when_late_write_fails(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway_backend.domain.archive.models import ArchiveDisposition, ArchivePlan, ArchiveResult
    from gateway_backend.infrastructure.control_db.sqlite_archive import SQLiteArchiveRepository

    seed = seed_approved_archive_candidate(db_path)
    confirmation_sequence = append_selection_confirmation(seed, now=TS_ARCHIVE)

    original_insert = SQLiteArchiveRepository.insert_plan_result_and_dispositions

    def failing_insert(
        self: SQLiteArchiveRepository,
        plan: ArchivePlan,
        result: ArchiveResult,
        dispositions: tuple[ArchiveDisposition, ...],
    ) -> None:
        original_insert(self, plan, result, dispositions)
        raise RuntimeError("simulated late write failure")

    monkeypatch.setattr(
        SQLiteArchiveRepository,
        "insert_plan_result_and_dispositions",
        failing_insert,
    )
    with pytest.raises(RuntimeError, match="simulated late write failure"):
        start_archive_for_seed(seed, confirmation_sequence=confirmation_sequence, now=TS_ARCHIVE)
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        plan_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_plan_records"
        ).fetchone()[0]
    assert plan_count == 0
