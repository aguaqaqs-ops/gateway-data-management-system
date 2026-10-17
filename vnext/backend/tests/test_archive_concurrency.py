"""Archive concurrency barrier tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest

from gateway_backend.application.archive.contracts import ArchiveAuditReferenceInput
from gateway_backend.application.archive.errors import ActiveSubmitAttempt
from gateway_backend.application.archive.start import StartArchiveCommand, start_archive
from gateway_backend.application.submission.errors import ArchiveClosed
from gateway_backend.application.submission.review_transaction import apply_review_transaction
from gateway_backend.domain.archive.models import ArchiveConfirmationAction
from gateway_backend.domain.submission.ports import ArchiveActiveAttemptFacts
from gateway_backend.domain.submission.review import ReviewAction
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.archive_fixtures import (
    ArchiveSeed,
    append_selection_confirmation,
    archive_seed_from_review_seed,
    seed_approved_archive_candidate,
    start_archive_for_seed,
)
from gateway_backend.application.archive.audit import (
    AppendArchiveConfirmationCommand,
    append_archive_confirmation,
)
from tests.test_review_transactions import (
    TS2,
    _apply_command,
    _apply_review,
    _scope_resolution,
    _seed_pending_review_submission,
    _uow_factory,
)
from tests.test_submit_transactions import BASELINE_HEAD

pytestmark = pytest.mark.unit

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

    def active_attempts(
        self: SQLiteSubmissionRepository,
        repository_id: str,
    ) -> tuple[ArchiveActiveAttemptFacts, ...]:
        return (ArchiveActiveAttemptFacts(submit_attempt_id="attempt-active-1", state="PREPARED"),)

    monkeypatch.setattr(SQLiteSubmissionRepository, "list_active_submit_attempts", active_attempts)
    with pytest.raises(ActiveSubmitAttempt):
        start_archive(
            command=_start_command(seed, confirmation_sequence),
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
    start_archive(
        command=_start_command(seed, confirmation_sequence),
        unit_of_work_factory=_uow_factory(db_path),
        now=TS_ARCHIVE,
    )
    with pytest.raises(ArchiveClosed):
        apply_review_transaction(
            command=_apply_command(
                review_seed,
                action=ReviewAction.RETURN_FOR_REVISION,
                reason="too late",
                expected_review_version=1,
                idempotency_key="return-after-archive",
            ),
            scope_resolution=_scope_resolution(review_seed),
            unit_of_work_factory=_uow_factory(db_path),
            now=TS2,
        )


def _run_barrier_race(
    db_path: Path,
    *,
    first: Any,
    second: Any,
) -> tuple[object, object]:
    barrier = Barrier(2)
    outcomes: list[object] = []

    def run(callable_obj: Any) -> None:
        barrier.wait()
        try:
            outcomes.append(callable_obj())
        except Exception as exc:
            outcomes.append(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run, first), executor.submit(run, second)]
        for future in futures:
            future.result()
    assert len(outcomes) == 2
    return outcomes[0], outcomes[1]


def test_concurrent_archive_start_and_review_return_produce_single_winner(db_path: Path) -> None:
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-concurrent"),
    )
    seed = archive_seed_from_review_seed(review_seed)
    confirmation_sequence = append_selection_confirmation(seed, now=TS_ARCHIVE)

    def do_start() -> object:
        return start_archive(
            command=_start_command(seed, confirmation_sequence),
            unit_of_work_factory=_uow_factory(db_path),
            now=TS_ARCHIVE,
        )

    def do_return() -> object:
        return apply_review_transaction(
            command=_apply_command(
                review_seed,
                action=ReviewAction.RETURN_FOR_REVISION,
                reason="race return",
                expected_review_version=1,
                idempotency_key="return-race",
            ),
            scope_resolution=_scope_resolution(review_seed),
            unit_of_work_factory=_uow_factory(db_path),
            now=TS2,
        )

    first, second = _run_barrier_race(db_path, first=do_start, second=do_return)
    from gateway_backend.application.archive.errors import CandidateSetConflict
    from gateway_backend.application.archive.start import StartArchiveResult
    from gateway_backend.application.submission.review_contracts import ApplyReviewResult
    from gateway_backend.domain.submission.review import ReviewStatus

    start_successes = [
        item
        for item in (first, second)
        if isinstance(item, StartArchiveResult) and item.replay is False
    ]
    review_successes = [item for item in (first, second) if isinstance(item, ApplyReviewResult)]
    assert len(start_successes) + len(review_successes) == 1

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        plan_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_plan_records"
        ).fetchone()[0]
        review_status = unit_of_work.connection.execute(
            "SELECT status FROM review_projection_records WHERE submission_id = ?",
            (review_seed.submission_id,),
        ).fetchone()[0]

    if start_successes:
        assert plan_count == 1
        assert review_status == ReviewStatus.APPROVED.value
        assert any(isinstance(item, ArchiveClosed) for item in (first, second))
    else:
        assert plan_count == 0
        assert review_status == ReviewStatus.RETURNED_FOR_REVISION.value
        assert any(
            isinstance(item, (ArchiveClosed, CandidateSetConflict)) for item in (first, second)
        )


def test_concurrent_dual_archive_keys_commit_one_plan(db_path: Path) -> None:
    seed = seed_approved_archive_candidate(db_path)
    confirmation_sequence = append_selection_confirmation(seed, now=TS_ARCHIVE)

    def start_with_key(key: str) -> object:
        return start_archive(
            command=StartArchiveCommand(
                context=seed.archiver_context,
                idempotency_key=key,
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
            unit_of_work_factory=_uow_factory(db_path),
            now=TS_ARCHIVE,
        )

    first, second = _run_barrier_race(
        db_path,
        first=lambda: start_with_key("archive-key-a"),
        second=lambda: start_with_key("archive-key-b"),
    )
    successes = [item for item in (first, second) if not isinstance(item, Exception)]
    assert len(successes) == 1
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        plan_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_plan_records"
        ).fetchone()[0]
    assert plan_count == 1


def test_concurrent_accept_submit_and_archive_start_linearized(db_path: Path) -> None:
    from gateway_backend.application.submission.accept_transaction import accept_submit_transaction
    from gateway_backend.application.submission.errors import BaselineVersionConflict
    from gateway_backend.application.archive.start import StartArchiveResult
    from tests.support.workspace_fixtures import FixedScopeResolutionPort
    from tests.test_submit_transactions import (
        RecordingMainResolvePort,
        _accept_command,
        _preflight,
        _submit_job_registry,
        seed_submit_ready_workspace,
    )

    archive_seed = seed_approved_archive_candidate(db_path)
    confirmation_sequence = append_selection_confirmation(archive_seed, now=TS_ARCHIVE)
    submit_seed = seed_submit_ready_workspace(
        db_path,
        repository_id=archive_seed.repository_id,
        actor_id="actor-accept-race",
    )

    def do_accept() -> object:
        return accept_submit_transaction(
            command=_accept_command(submit_seed, idempotency_key="accept-race"),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=submit_seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(db_path),
            job_registry=_submit_job_registry(),
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(submit_seed),
            now=TS_ARCHIVE,
        )

    def do_start() -> object:
        return start_archive(
            command=_start_command(archive_seed, confirmation_sequence),
            unit_of_work_factory=_uow_factory(db_path),
            now=TS_ARCHIVE,
        )

    first, second = _run_barrier_race(db_path, first=do_accept, second=do_start)
    start_successes = [
        item
        for item in (first, second)
        if isinstance(item, StartArchiveResult) and item.replay is False
    ]

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        plan_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_plan_records"
        ).fetchone()[0]
        active_attempt_count = unit_of_work.connection.execute(
            """
            SELECT COUNT(*)
            FROM submit_attempt_records
            WHERE repository_id = ?
              AND state IN ('PREPARED', 'EFFECT_PENDING')
            """,
            (archive_seed.repository_id,),
        ).fetchone()[0]

    if start_successes:
        assert plan_count == 1
        assert any(isinstance(item, BaselineVersionConflict) for item in (first, second))
    else:
        assert plan_count == 0
        assert active_attempt_count >= 1
        assert any(isinstance(item, ActiveSubmitAttempt) for item in (first, second))


def test_concurrent_revoke_and_start_are_linearized(db_path: Path) -> None:
    seed = seed_approved_archive_candidate(db_path)
    confirm = append_archive_confirmation(
        command=AppendArchiveConfirmationCommand(
            context=seed.archiver_context,
            idempotency_key="confirm-before-revoke-race",
            expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
            expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
            selected=seed.selected_ref,
            candidate_set_digest=seed.candidate_set_digest,
            subject_digest=seed.selection_subject_digest,
            expected_sequence=0,
            action=ArchiveConfirmationAction.CONFIRM,
            reason="confirm archive selection",
        ),
        unit_of_work_factory=_uow_factory(db_path),
        now=TS_ARCHIVE,
    )

    def do_revoke() -> object:
        return append_archive_confirmation(
            command=AppendArchiveConfirmationCommand(
                context=seed.archiver_context,
                idempotency_key="revoke-race",
                expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
                expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
                selected=seed.selected_ref,
                candidate_set_digest=seed.candidate_set_digest,
                subject_digest=seed.selection_subject_digest,
                expected_sequence=confirm.sequence,
                action=ArchiveConfirmationAction.REVOKE,
                reason="revoke selection",
            ),
            unit_of_work_factory=_uow_factory(db_path),
            now=TS_ARCHIVE,
        )

    def do_start() -> object:
        return start_archive_for_seed(seed, confirmation_sequence=confirm.sequence, now=TS_ARCHIVE)

    first, second = _run_barrier_race(db_path, first=do_revoke, second=do_start)
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        plan_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_plan_records"
        ).fetchone()[0]
    from gateway_backend.application.archive.start import StartArchiveResult

    started = [
        outcome
        for outcome in (first, second)
        if isinstance(outcome, StartArchiveResult) and outcome.replay is False
    ]
    if started:
        assert plan_count == 1
    else:
        assert plan_count == 0
