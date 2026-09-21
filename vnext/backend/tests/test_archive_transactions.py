"""Archive Start transaction tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import pytest

from gateway_backend.application.archive.errors import (
    ActiveSubmitAttempt,
    ArchiveAnomalyUnresolved,
    ArchiveConfirmationRequired,
)
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


def test_start_archive_dual_sibling_writes_both_dispositions(db_path: Path) -> None:
    from tests.support.archive_fixtures import (
        prepare_dual_sibling_start,
        seed_approved_dual_sibling_archive,
        start_archive_for_seed,
    )

    dual_seed = seed_approved_dual_sibling_archive(db_path)
    confirmation_sequence, resolution_sequence = prepare_dual_sibling_start(dual_seed, now=TS_ARCHIVE)
    result = start_archive_for_seed(
        dual_seed.primary,
        confirmation_sequence=confirmation_sequence,
        anomaly_resolution_sequences=((dual_seed.anomaly_subject_digest, resolution_sequence),),
        now=TS_ARCHIVE,
    )
    assert result.replay is False
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        primary_disposition = unit_of_work.archive.list_dispositions_for_submission(
            dual_seed.primary.submission_id
        )
        sibling_disposition = unit_of_work.archive.list_dispositions_for_submission(
            dual_seed.sibling_submission_id
        )
    assert primary_disposition[0].disposition is ArchiveDispositionKind.ARCHIVED_BASELINE
    assert sibling_disposition[0].disposition is ArchiveDispositionKind.CLOSED_NOT_ARCHIVED


def test_start_archive_prefers_active_attempt_over_candidate_set_conflict(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_backend.application.archive.contracts import ArchiveAuditReferenceInput
    from gateway_backend.application.archive.start import start_archive
    from gateway_backend.domain.submission.ports import ArchiveActiveAttemptFacts
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
            command=StartArchiveCommand(
                context=seed.archiver_context,
                idempotency_key="start-with-active-and-stale-digest",
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


def test_start_archive_rejects_unresolved_sibling_anomaly(db_path: Path) -> None:
    from gateway_backend.application.archive.contracts import ArchiveAuditReferenceInput
    from gateway_backend.application.archive.start import start_archive
    from tests.support.archive_fixtures import seed_approved_dual_sibling_archive

    dual_seed = seed_approved_dual_sibling_archive(db_path)
    confirmation_sequence = append_selection_confirmation(dual_seed.primary, now=TS_ARCHIVE)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=dual_seed.primary.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    with pytest.raises(ArchiveAnomalyUnresolved):
        start_archive(
            command=StartArchiveCommand(
                context=dual_seed.primary.archiver_context,
                idempotency_key="start-without-resolution",
                expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
                expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
                candidate_set_digest=dual_seed.primary.candidate_set_digest,
                selected_ref=dual_seed.primary.selected_ref,
                confirmation_refs=(
                    ArchiveAuditReferenceInput(
                        subject_digest=dual_seed.primary.selection_subject_digest,
                        sequence=confirmation_sequence,
                    ),
                ),
                anomaly_resolution_refs=(),
            ),
            scope_resolution=scope_resolution,
            unit_of_work_factory=_uow_factory(db_path),
            now=TS_ARCHIVE,
        )


def test_start_archive_rejects_orphan_repository_occupancy(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC

    from gateway_backend.application.archive.contracts import ArchiveAuditReferenceInput
    from gateway_backend.application.archive.errors import ArchiveIntegrityFailure
    from gateway_backend.application.archive.start import start_archive
    from gateway_backend.domain.submission.models import RepositorySubmitOccupancy
    from gateway_backend.infrastructure.control_db.sqlite_submission import SQLiteSubmissionRepository

    seed = seed_approved_archive_candidate(db_path)
    confirmation_sequence = append_selection_confirmation(seed, now=TS_ARCHIVE)
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        submission = unit_of_work.submission.get_submission(seed.submission_id)
        assert submission is not None
    orphan = RepositorySubmitOccupancy(
        repository_id=seed.repository_id,
        workspace_id=submission.workspace_id,
        submit_attempt_id="attempt-orphan",
        business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version,
        acquired_at=datetime(2024, 1, 1, tzinfo=UTC),
    )

    def orphan_occupancy(
        self: SQLiteSubmissionRepository,
        repository_id: str,
    ) -> RepositorySubmitOccupancy | None:
        if repository_id == seed.repository_id:
            return orphan
        return None

    def no_active_attempts(
        self: SQLiteSubmissionRepository,
        repository_id: str,
    ) -> tuple[object, ...]:
        return ()

    monkeypatch.setattr(SQLiteSubmissionRepository, "get_repository_occupancy", orphan_occupancy)
    monkeypatch.setattr(SQLiteSubmissionRepository, "list_active_submit_attempts", no_active_attempts)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    with pytest.raises(ArchiveIntegrityFailure):
        start_archive(
            command=StartArchiveCommand(
                context=seed.archiver_context,
                idempotency_key="start-with-orphan-occupancy",
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
            unit_of_work_factory=_uow_factory(db_path),
            now=TS_ARCHIVE,
        )


def test_start_archive_rejects_mismatched_active_attempt_and_occupancy(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_backend.application.archive.contracts import ArchiveAuditReferenceInput
    from gateway_backend.application.archive.errors import ArchiveIntegrityFailure
    from gateway_backend.application.archive.start import start_archive
    from gateway_backend.domain.submission.models import RepositorySubmitOccupancy
    from gateway_backend.domain.submission.ports import ArchiveActiveAttemptFacts
    from gateway_backend.infrastructure.control_db.sqlite_submission import SQLiteSubmissionRepository

    seed = seed_approved_archive_candidate(db_path)
    confirmation_sequence = append_selection_confirmation(seed, now=TS_ARCHIVE)
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        submission = unit_of_work.submission.get_submission(seed.submission_id)
        assert submission is not None
    occupancy = RepositorySubmitOccupancy(
        repository_id=seed.repository_id,
        workspace_id=submission.workspace_id,
        submit_attempt_id="attempt-occupancy-b",
        business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version,
        acquired_at=datetime(2024, 1, 1, tzinfo=UTC),
    )

    def active_attempts(
        self: SQLiteSubmissionRepository,
        repository_id: str,
    ) -> tuple[ArchiveActiveAttemptFacts, ...]:
        if repository_id == seed.repository_id:
            return (
                ArchiveActiveAttemptFacts(submit_attempt_id="attempt-active-a", state="PREPARED"),
            )
        return ()

    def mismatched_occupancy(
        self: SQLiteSubmissionRepository,
        repository_id: str,
    ) -> RepositorySubmitOccupancy | None:
        if repository_id == seed.repository_id:
            return occupancy
        return None

    monkeypatch.setattr(SQLiteSubmissionRepository, "list_active_submit_attempts", active_attempts)
    monkeypatch.setattr(SQLiteSubmissionRepository, "get_repository_occupancy", mismatched_occupancy)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    with pytest.raises(ArchiveIntegrityFailure):
        start_archive(
            command=StartArchiveCommand(
                context=seed.archiver_context,
                idempotency_key="start-with-mismatched-occupancy",
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
            unit_of_work_factory=_uow_factory(db_path),
            now=TS_ARCHIVE,
        )
