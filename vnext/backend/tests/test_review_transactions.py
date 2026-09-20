"""Review application transaction matrix tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import pytest

from gateway_backend.application.submission.errors import (
    IdempotencyConflict,
    ReviewIntegrityFailure,
    ReviewWorkspaceOccupancyConflict,
)
from gateway_backend.application.submission.review import (
    PERMISSION_REVIEW_SUBMISSION,
    get_review_facts,
    verify_idempotency_replay,
)
from gateway_backend.application.submission.ports import WorkspaceControlUnitOfWorkFactory
from gateway_backend.application.submission.review_contracts import ApplyReviewCommand, ApplyReviewResult
from gateway_backend.application.submission.review_transaction import apply_review_transaction
from gateway_backend.domain.submission.errors import (
    InvalidReviewTransition,
    ReviewClosureViolation,
    ReviewVersionConflict,
    SubmitOccupancyConflict,
)
from gateway_backend.domain.submission.models import Submission
from gateway_backend.domain.submission.review import ReviewAction, ReviewEventKind, ReviewStatus
from gateway_backend.domain.workspace.errors import PermissionDenied, ScopeForbidden
from gateway_backend.application.workspace.services import create_or_get_workspace
from gateway_backend.domain.workspace.models import (
    IdentityContext,
    InputCompleteness,
    SourceArtifactBinding,
    SourceArtifactRole,
    UploadRevision,
    WorkspaceState,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from tests.support.workspace_fixtures import FixedScopeResolutionPort, make_identity
from tests.test_submit_transactions import (
    BASELINE_HEAD,
    SubmitSeed,
    TS0,
    TS1,
    _finalize_facts,
    _preview_result,
    _protected_preview_refs,
    _read_finalize_versions,
    _seed_effect_pending_attempt,
    _upsert_provisioned_mapping_row,
    seed_submit_ready_workspace,
)
from gateway_backend.application.submission.finalize_transaction import (
    FinalizeSubmitTransactionRequest,
    finalize_submit_transaction,
)

pytestmark = pytest.mark.unit

TS2 = datetime(2024, 6, 1, 13, 0, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class ReviewSeed:
    db_path: Path
    submission_id: str
    workspace_id: str
    repository_id: str
    reviewer_context: IdentityContext
    submission: Submission


def _reviewer_context(seed_device: str, seed_project: str) -> IdentityContext:
    return make_identity(
        actor_id="reviewer-1",
        device_key=seed_device,
        project_id=seed_project,
        permissions=frozenset({PERMISSION_REVIEW_SUBMISSION}),
    )


def _seed_pending_review_submission(db_path: Path) -> ReviewSeed:
    submit_seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, submit_seed)
    attempt_version, await_version, operation_version = _read_finalize_versions(db_path, attempt)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        finalize_submit_transaction(
            request=FinalizeSubmitTransactionRequest(
                submit_attempt_id=attempt.submit_attempt_id,
                facts=_finalize_facts(submit_seed),
                submission_id="sub-1",
                created_at=TS1,
                expected_attempt_version=attempt_version,
                expected_await_step_version=await_version,
                expected_operation_version=operation_version,
                worker_id="worker-test",
                lease_token="lease-test",
            ),
            unit_of_work=unit_of_work,
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        submission = unit_of_work.submission.get_submission("sub-1")
        assert submission is not None
    return ReviewSeed(
        db_path=db_path,
        submission_id="sub-1",
        workspace_id=submit_seed.workspace.workspace_id,
        repository_id=submit_seed.workspace.repository_id,
        reviewer_context=_reviewer_context(
            submit_seed.workspace.gateway_device_external_key,
            submit_seed.workspace.business_project_id,
        ),
        submission=submission,
    )


def _seed_additional_pending_review_submission(
    db_path: Path,
    *,
    submission_id: str,
    device_key: str,
    repository_id: str,
    project_id: str,
) -> ReviewSeed:
    _upsert_provisioned_mapping_row(
        db_path,
        device_key=device_key,
        project_id=project_id,
        repository_id=repository_id,
    )
    scope_resolution = FixedScopeResolutionPort(
        repository_id=repository_id,
        baseline_head=BASELINE_HEAD,
    )
    context = make_identity(
        device_key=device_key,
        project_id=project_id,
        permissions=frozenset({"upload_submit_workspace", "workspace_read"}),
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        created = create_or_get_workspace(
            context=context,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
            created_at=TS0,
        )
        workspace = created.workspace
        upload_revision_id = f"ur-{submission_id}"
        preview_result_id = f"pr-{submission_id}"
        upload_revision = UploadRevision(
            upload_revision_id=upload_revision_id,
            workspace_id=workspace.workspace_id,
            generation=1,
            input_completeness=InputCompleteness.FULL,
            source_artifacts={
                SourceArtifactRole.INITIAL: SourceArtifactBinding(
                    artifact_id="initial-1",
                    media_type="application/gzip",
                    size_bytes=1,
                    raw_sha256="sha256:initial",
                ),
                SourceArtifactRole.MODIFIED: SourceArtifactBinding(
                    artifact_id="modified-1",
                    media_type="application/gzip",
                    size_bytes=2,
                    raw_sha256="sha256:modified",
                ),
            },
            idempotency_key=f"upload-key-{submission_id}",
            request_fingerprint=f"fp-upload-{submission_id}",
            created_by="actor-1",
            created_at=TS0,
        )
        preview = replace(
            _preview_result(workspace.workspace_id),
            preview_result_id=preview_result_id,
            upload_revision_id=upload_revision_id,
            repository_id=repository_id,
            operation_id=f"op-preview-{submission_id}",
        )
        unit_of_work.workspace.save_upload_revision(upload_revision)
        unit_of_work.workspace.save_preview_result(preview)
        updated_workspace = replace(
            workspace,
            repository_id=repository_id,
            generation=1,
            optimistic_version=workspace.optimistic_version + 1,
            current_upload_revision_id=upload_revision_id,
            current_preview_result_id=preview_result_id,
            updated_at=TS1,
        )
        unit_of_work.workspace.save_workspace(
            updated_workspace,
            expected_version=workspace.optimistic_version,
        )
        preview_operation_id = f"op-preview-{submission_id}"
        protected_refs = _protected_preview_refs()
        unit_of_work.set_artifact_protection(
            protected_refs,
            owner_kind="current-preview",
            owner_id=updated_workspace.workspace_id,
            intent="current-preview",
        )
        unit_of_work.set_artifact_protection(
            protected_refs[:2],
            owner_kind="preview-operation",
            owner_id=preview_operation_id,
            intent="preview-operation",
        )
    submit_seed = SubmitSeed(
        db_path=db_path,
        workspace=updated_workspace,
        upload_revision=upload_revision,
        preview_result=preview,
        preview_operation_id=preview_operation_id,
        protected_refs=protected_refs,
    )
    attempt = _seed_effect_pending_attempt(db_path, submit_seed)
    attempt_version, await_version, operation_version = _read_finalize_versions(db_path, attempt)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        finalize_submit_transaction(
            request=FinalizeSubmitTransactionRequest(
                submit_attempt_id=attempt.submit_attempt_id,
                facts=_finalize_facts(submit_seed),
                submission_id=submission_id,
                created_at=TS1,
                expected_attempt_version=attempt_version,
                expected_await_step_version=await_version,
                expected_operation_version=operation_version,
                worker_id="worker-test",
                lease_token="lease-test",
            ),
            unit_of_work=unit_of_work,
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        submission = unit_of_work.submission.get_submission(submission_id)
        assert submission is not None
    return ReviewSeed(
        db_path=db_path,
        submission_id=submission_id,
        workspace_id=updated_workspace.workspace_id,
        repository_id=repository_id,
        reviewer_context=_reviewer_context(device_key, project_id),
        submission=submission,
    )


def _apply_command(
    seed: ReviewSeed,
    *,
    action: ReviewAction = ReviewAction.APPROVE,
    reason: str | None = None,
    expected_review_version: int = 0,
    idempotency_key: str = "review-key-1",
    actor_id: str | None = None,
    submission_id: str | None = None,
) -> ApplyReviewCommand:
    context = seed.reviewer_context
    if actor_id is not None:
        context = replace(context, actor_id=actor_id)
    return ApplyReviewCommand(
        context=context,
        submission_id=submission_id or seed.submission_id,
        expected_review_version=expected_review_version,
        action=action,
        reason=reason,
        idempotency_key=idempotency_key,
    )


def _uow_factory(db_path: Path) -> WorkspaceControlUnitOfWorkFactory:
    def factory(*, read_only: bool = False) -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(db_path, read_only=read_only)

    return factory


def _scope_resolution(seed: ReviewSeed) -> FixedScopeResolutionPort:
    return FixedScopeResolutionPort(
        repository_id=seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )


def _apply_review(
    seed: ReviewSeed,
    command: ApplyReviewCommand,
    *,
    now: datetime = TS2,
) -> ApplyReviewResult:
    return apply_review_transaction(
        command=command,
        scope_resolution=_scope_resolution(seed),
        unit_of_work_factory=_uow_factory(seed.db_path),
        now=now,
    )


REVIEW_TRANSITION_CASES = (
    (ReviewAction.APPROVE, ReviewStatus.APPROVED, False),
    (ReviewAction.REJECT, ReviewStatus.REJECTED, True),
    (ReviewAction.RETURN_FOR_REVISION, ReviewStatus.RETURNED_FOR_REVISION, True),
    (ReviewAction.WITHDRAW, ReviewStatus.WITHDRAWN, True),
)

REVIEW_DENIED_TERMINAL_CASES = (
    (ReviewStatus.REJECTED, ReviewAction.APPROVE),
    (ReviewStatus.RETURNED_FOR_REVISION, ReviewAction.APPROVE),
    (ReviewStatus.WITHDRAWN, ReviewAction.APPROVE),
)

OCCUPANCY_MISMATCH_CASES = (
    ("generation", "generation"),
    ("upload_revision_id", "current_upload_revision_id"),
    ("preview_result_id", "current_preview_result_id"),
)


@pytest.fixture
def review_seed(db_path: Path) -> ReviewSeed:
    return _seed_pending_review_submission(db_path)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "control.db"
    initialize_control_db(path)
    return path


@pytest.mark.parametrize(("action", "expected_status", "releases"), REVIEW_TRANSITION_CASES)
def test_apply_review_pending_transitions(
    review_seed: ReviewSeed,
    action: ReviewAction,
    expected_status: ReviewStatus,
    releases: bool,
) -> None:
    reason = "needs changes" if action in {ReviewAction.REJECT, ReviewAction.RETURN_FOR_REVISION} else None
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        workspace_before = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
        assert workspace_before is not None
        workspace_version_before = workspace_before.optimistic_version
    result = _apply_review(
        review_seed,
        _apply_command(
            review_seed,
            action=action,
            reason=reason,
            idempotency_key=f"key-{action.value}",
        ),
    )
    assert result.projection.status is expected_status
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
        occupancy = unit_of_work.submission.get_workspace_occupancy(review_seed.workspace_id)
        submission = unit_of_work.submission.get_submission(review_seed.submission_id)
    assert workspace is not None
    assert submission == review_seed.submission
    if releases:
        assert workspace.current_upload_revision_id is None
        assert workspace.current_preview_result_id is None
        assert occupancy is None
        assert workspace.optimistic_version == workspace_version_before + 1
    else:
        assert workspace.current_upload_revision_id == review_seed.submission.upload_revision_id
        assert workspace.current_preview_result_id == review_seed.submission.preview_result_id
        assert occupancy is not None
        assert occupancy.active_submission_id == review_seed.submission_id


def test_apply_review_approved_return_releases_workspace(review_seed: ReviewSeed) -> None:
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-key"),
    )
    result = _apply_review(
        review_seed,
        _apply_command(
            review_seed,
            action=ReviewAction.RETURN_FOR_REVISION,
            reason="return for edits",
            expected_review_version=1,
            idempotency_key="return-key",
        ),
    )
    assert result.projection.status is ReviewStatus.RETURNED_FOR_REVISION
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        occupancy = unit_of_work.submission.get_workspace_occupancy(review_seed.workspace_id)
        workspace = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
    assert occupancy is None
    assert workspace is not None
    assert workspace.current_upload_revision_id is None


@pytest.mark.parametrize(("status", "action"), REVIEW_DENIED_TERMINAL_CASES)
def test_apply_review_rejects_terminal_transition(
    review_seed: ReviewSeed,
    status: ReviewStatus,
    action: ReviewAction,
) -> None:
    release_action = ReviewAction.REJECT if status is ReviewStatus.REJECTED else ReviewAction.WITHDRAW
    if status is ReviewStatus.RETURNED_FOR_REVISION:
        release_action = ReviewAction.RETURN_FOR_REVISION
    _apply_review(
        review_seed,
        _apply_command(
            review_seed,
            action=release_action,
            reason="terminal setup" if release_action is not ReviewAction.WITHDRAW else None,
            idempotency_key=f"setup-{status.value}",
        ),
    )
    with pytest.raises(InvalidReviewTransition):
        _apply_review(
            review_seed,
            _apply_command(
                review_seed,
                action=action,
                expected_review_version=1,
                idempotency_key="terminal-deny",
            ),
        )


def test_apply_review_rejects_stale_expected_version(review_seed: ReviewSeed) -> None:
    with pytest.raises(ReviewVersionConflict):
        _apply_review(
            review_seed,
            _apply_command(review_seed, expected_review_version=9),
        )
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        events = unit_of_work.review.list_events(review_seed.submission_id)
        projection = unit_of_work.review.get_projection(review_seed.submission_id)
    assert len(events) == 1
    assert projection is not None
    assert projection.optimistic_version == 0


@pytest.mark.parametrize(("submission_field", "workspace_field"), OCCUPANCY_MISMATCH_CASES)
def test_apply_review_rejects_occupancy_binding_mismatch(
    review_seed: ReviewSeed,
    submission_field: str,
    workspace_field: str,
) -> None:
    with ControlDbUnitOfWork(review_seed.db_path) as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
        assert workspace is not None
        if submission_field == "generation":
            mutated = replace(workspace, generation=workspace.generation + 1)
        elif workspace_field == "current_upload_revision_id":
            mutated = replace(workspace, current_upload_revision_id="ur-other")
        else:
            mutated = replace(workspace, current_preview_result_id="pr-other")
        unit_of_work.workspace.save_workspace(
            mutated,
            expected_version=workspace.optimistic_version,
        )
    with pytest.raises(ReviewWorkspaceOccupancyConflict) as exc_info:
        _apply_review(review_seed, _apply_command(review_seed))
    assert exc_info.value.stable_code == "WORKSPACE_OCCUPANCY_CONFLICT"
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        projection = unit_of_work.review.get_projection(review_seed.submission_id)
        events = unit_of_work.review.list_events(review_seed.submission_id)
    assert projection is not None
    assert projection.optimistic_version == 0
    assert len(events) == 1


def test_apply_review_rejects_closed_workspace(review_seed: ReviewSeed) -> None:
    with ControlDbUnitOfWork(review_seed.db_path) as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
        assert workspace is not None
        closed = replace(workspace, state=WorkspaceState.CLOSED)
        unit_of_work.workspace.save_workspace(
            closed,
            expected_version=workspace.optimistic_version,
        )
    with pytest.raises(ReviewWorkspaceOccupancyConflict) as exc_info:
        _apply_review(review_seed, _apply_command(review_seed))
    assert exc_info.value.reason == "workspace is not open"
    assert exc_info.value.stable_code == "WORKSPACE_OCCUPANCY_CONFLICT"


def test_apply_review_rejects_missing_occupancy(review_seed: ReviewSeed) -> None:
    with ControlDbUnitOfWork(review_seed.db_path) as unit_of_work:
        unit_of_work.submission.delete_workspace_submission_occupancy(
            review_seed.workspace_id,
            expected_submission_id=review_seed.submission_id,
        )
    with pytest.raises(ReviewWorkspaceOccupancyConflict):
        _apply_review(review_seed, _apply_command(review_seed))


def test_apply_review_idempotency_replay_is_write_free(review_seed: ReviewSeed) -> None:
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        workspace_before = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
        assert workspace_before is not None
        workspace_version_before = workspace_before.optimistic_version
        upload_before = workspace_before.current_upload_revision_id
        preview_before = workspace_before.current_preview_result_id
    command = _apply_command(review_seed, idempotency_key="replay-key")
    first = _apply_review(review_seed, command)
    replay = _apply_review(
        review_seed,
        _apply_command(
            review_seed,
            actor_id="reviewer-2",
            expected_review_version=0,
            idempotency_key="replay-key",
        ),
    )
    assert first.replay is False
    assert replay.replay is True
    assert replay.event == first.event
    assert replay.projection == first.projection
    assert replay.request_fingerprint == first.request_fingerprint
    assert replay.event.actor_id == "reviewer-1"
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        events = unit_of_work.review.list_events(review_seed.submission_id)
        rows = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_idempotency_records WHERE idempotency_key = ?",
            ("replay-key",),
        ).fetchone()[0]
        workspace_after = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
    assert len(events) == 2
    assert rows == 1
    assert workspace_after is not None
    assert workspace_after.optimistic_version == workspace_version_before
    assert workspace_after.current_upload_revision_id == upload_before
    assert workspace_after.current_preview_result_id == preview_before


def test_apply_review_fails_closed_on_corrupted_idempotency_fingerprint(
    review_seed: ReviewSeed,
) -> None:
    command = _apply_command(review_seed, idempotency_key="corrupt-fp-key")
    _apply_review(review_seed, command)
    corrupted_fingerprint = "sha256:" + ("a" * 64)
    with ControlDbUnitOfWork(review_seed.db_path) as unit_of_work:
        workspace_before = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
        assert workspace_before is not None
        unit_of_work.connection.execute(
            """
            UPDATE review_idempotency_records
            SET request_fingerprint = ?
            WHERE idempotency_key = ?
            """,
            (corrupted_fingerprint, "corrupt-fp-key"),
        )
    with pytest.raises(ReviewIntegrityFailure) as exc_info:
        _apply_review(review_seed, command)
    assert exc_info.value.stable_code == "REVIEW_INTEGRITY_FAILURE"
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        events = unit_of_work.review.list_events(review_seed.submission_id)
        projection = unit_of_work.review.get_projection(review_seed.submission_id)
        workspace_after = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
        idempotency_rows = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_idempotency_records WHERE idempotency_key = ?",
            ("corrupt-fp-key",),
        ).fetchone()[0]
    assert len(events) == 2
    assert projection is not None
    assert projection.optimistic_version == 1
    assert idempotency_rows == 1
    assert workspace_after == workspace_before


def test_apply_review_idempotency_conflict_on_different_fingerprint(review_seed: ReviewSeed) -> None:
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="conflict-key"),
    )
    with pytest.raises(IdempotencyConflict):
        _apply_review(
            review_seed,
            _apply_command(
                review_seed,
                action=ReviewAction.REJECT,
                reason="reject later",
                expected_review_version=0,
                idempotency_key="conflict-key",
            ),
        )


def test_apply_review_idempotency_conflict_on_cross_submission(review_seed: ReviewSeed) -> None:
    _apply_review(
        review_seed,
        _apply_command(review_seed, idempotency_key="shared-project-key"),
    )
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        record = unit_of_work.review.find_idempotency(
            review_seed.reviewer_context.business_project_id,
            "shared-project-key",
        )
        events = unit_of_work.review.list_events(review_seed.submission_id)
        workspace = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
        assert record is not None
        assert workspace is not None
    with pytest.raises(IdempotencyConflict):
        verify_idempotency_replay(
            record,
            command=_apply_command(
                review_seed,
                submission_id="sub-2",
                idempotency_key="shared-project-key",
            ),
            record_workspace=workspace,
            request_workspace=workspace,
            request_repository_id=review_seed.repository_id,
            events=events,
        )


CROSS_SUBMISSION_IDEMPOTENCY_CONFLICT_CASES = (
    ("different_device_same_project", "device-2", "repo-1"),
    ("different_repository_same_project", "device-2", "repo-2"),
)


@pytest.mark.parametrize(
    ("case_id", "device_key", "repository_id"),
    CROSS_SUBMISSION_IDEMPOTENCY_CONFLICT_CASES,
    ids=[case[0] for case in CROSS_SUBMISSION_IDEMPOTENCY_CONFLICT_CASES],
)
def test_apply_review_idempotency_conflict_on_cross_submission_via_transaction(
    review_seed: ReviewSeed,
    case_id: str,
    device_key: str,
    repository_id: str,
) -> None:
    idempotency_key = f"shared-cross-key-{case_id}"
    _apply_review(
        review_seed,
        _apply_command(review_seed, idempotency_key=idempotency_key),
    )
    second_seed = _seed_additional_pending_review_submission(
        review_seed.db_path,
        submission_id="sub-2",
        device_key=device_key,
        repository_id=repository_id,
        project_id=review_seed.reviewer_context.business_project_id,
    )
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        first_events = unit_of_work.review.list_events(review_seed.submission_id)
        first_projection = unit_of_work.review.get_projection(review_seed.submission_id)
        second_events = unit_of_work.review.list_events(second_seed.submission_id)
        idempotency_rows = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_idempotency_records",
        ).fetchone()[0]
    with pytest.raises(IdempotencyConflict):
        apply_review_transaction(
            command=_apply_command(
                second_seed,
                idempotency_key=idempotency_key,
            ),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(review_seed.db_path),
            now=TS2,
        )
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        events_after = unit_of_work.review.list_events(review_seed.submission_id)
        projection_after = unit_of_work.review.get_projection(review_seed.submission_id)
        second_events_after = unit_of_work.review.list_events(second_seed.submission_id)
        idempotency_rows_after = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_idempotency_records",
        ).fetchone()[0]
    assert len(events_after) == len(first_events)
    assert projection_after == first_projection
    assert second_events_after == second_events
    assert idempotency_rows_after == idempotency_rows


def test_apply_review_cross_submission_fails_closed_on_record_submission_closure_damage(
    review_seed: ReviewSeed,
) -> None:
    idempotency_key = "shared-cross-closure-key"
    _apply_review(
        review_seed,
        _apply_command(review_seed, idempotency_key=idempotency_key),
    )
    second_seed = _seed_additional_pending_review_submission(
        review_seed.db_path,
        submission_id="sub-2",
        device_key="device-2",
        repository_id="repo-2",
        project_id=review_seed.reviewer_context.business_project_id,
    )
    with ControlDbUnitOfWork(review_seed.db_path) as unit_of_work:
        unit_of_work.connection.execute(
            """
            UPDATE review_projection_records
            SET status = 'PENDING', optimistic_version = 0, latest_sequence = 0
            WHERE submission_id = ?
            """,
            (review_seed.submission_id,),
        )
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        with pytest.raises(ReviewClosureViolation):
            unit_of_work.review.list_events(review_seed.submission_id)
        first_event_rows = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_event_records WHERE submission_id = ?",
            (review_seed.submission_id,),
        ).fetchone()[0]
        first_projection_rows = unit_of_work.connection.execute(
            "SELECT optimistic_version FROM review_projection_records WHERE submission_id = ?",
            (review_seed.submission_id,),
        ).fetchone()
        second_events = unit_of_work.review.list_events(second_seed.submission_id)
        idempotency_rows = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_idempotency_records",
        ).fetchone()[0]
    with pytest.raises(ReviewIntegrityFailure) as exc_info:
        apply_review_transaction(
            command=_apply_command(
                second_seed,
                idempotency_key=idempotency_key,
            ),
            scope_resolution=FixedScopeResolutionPort(
                repository_id="repo-2",
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(review_seed.db_path),
            now=TS2,
        )
    assert exc_info.value.stable_code == "REVIEW_INTEGRITY_FAILURE"
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        second_events_after = unit_of_work.review.list_events(second_seed.submission_id)
        event_rows_after = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_event_records WHERE submission_id = ?",
            (review_seed.submission_id,),
        ).fetchone()[0]
        projection_row_after = unit_of_work.connection.execute(
            "SELECT optimistic_version FROM review_projection_records WHERE submission_id = ?",
            (review_seed.submission_id,),
        ).fetchone()
        idempotency_rows_after = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_idempotency_records",
        ).fetchone()[0]
    assert event_rows_after == first_event_rows
    assert projection_row_after == first_projection_rows
    assert second_events_after == second_events
    assert idempotency_rows_after == idempotency_rows


def test_apply_review_replay_returns_original_result_after_later_mutation(
    review_seed: ReviewSeed,
) -> None:
    approve = _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-replay"),
    )
    _apply_review(
        review_seed,
        _apply_command(
            review_seed,
            action=ReviewAction.RETURN_FOR_REVISION,
            reason="return later",
            expected_review_version=1,
            idempotency_key="return-later",
        ),
    )
    replay = _apply_review(
        review_seed,
        _apply_command(
            review_seed,
            action=ReviewAction.APPROVE,
            expected_review_version=0,
            idempotency_key="approve-replay",
        ),
    )
    assert replay.replay is True
    assert replay.event.sequence == approve.event.sequence
    assert replay.projection.status is ReviewStatus.APPROVED
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        projection = unit_of_work.review.get_projection(review_seed.submission_id)
    assert projection is not None
    assert projection.status is ReviewStatus.RETURNED_FOR_REVISION


def test_apply_review_archive_race_barrier_blocks_return_without_occupancy(
    review_seed: ReviewSeed,
) -> None:
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-race"),
    )
    with ControlDbUnitOfWork(review_seed.db_path) as unit_of_work:
        unit_of_work.submission.delete_workspace_submission_occupancy(
            review_seed.workspace_id,
            expected_submission_id=review_seed.submission_id,
        )
    with pytest.raises(ReviewWorkspaceOccupancyConflict):
        _apply_review(
            review_seed,
            _apply_command(
                review_seed,
                action=ReviewAction.RETURN_FOR_REVISION,
                reason="too late",
                expected_review_version=1,
                idempotency_key="return-race",
            ),
        )
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        projection = unit_of_work.review.get_projection(review_seed.submission_id)
        events = unit_of_work.review.list_events(review_seed.submission_id)
    assert projection is not None
    assert projection.status is ReviewStatus.APPROVED
    assert len(events) == 2


def test_apply_review_integrity_failure_on_projection_event_divergence(
    review_seed: ReviewSeed,
) -> None:
    with ControlDbUnitOfWork(review_seed.db_path) as unit_of_work:
        unit_of_work.connection.execute(
            "UPDATE review_projection_records SET status = 'APPROVED' WHERE submission_id = ?",
            (review_seed.submission_id,),
        )
    with pytest.raises(ReviewIntegrityFailure):
        _apply_review(review_seed, _apply_command(review_seed))


def test_apply_review_fails_closed_on_seed_bound_idempotency_record(review_seed: ReviewSeed) -> None:
    with ControlDbUnitOfWork(review_seed.db_path) as unit_of_work:
        workspace_before = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
        assert workspace_before is not None
        unit_of_work.connection.execute(
            """
            INSERT INTO review_idempotency_records (
                business_project_id, idempotency_key, submission_id,
                request_fingerprint, event_sequence
            ) VALUES (?, 'seed-bound-key', ?, 'sha256:fp', 0)
            """,
            (
                review_seed.reviewer_context.business_project_id,
                review_seed.submission_id,
            ),
        )
    with pytest.raises(ReviewIntegrityFailure) as exc_info:
        _apply_review(
            review_seed,
            _apply_command(review_seed, idempotency_key="seed-bound-key"),
        )
    assert exc_info.value.stable_code == "REVIEW_INTEGRITY_FAILURE"
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        projection = unit_of_work.review.get_projection(review_seed.submission_id)
        events = unit_of_work.review.list_events(review_seed.submission_id)
        workspace_after = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
        occupancy = unit_of_work.submission.get_workspace_occupancy(review_seed.workspace_id)
        idempotency_rows = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_idempotency_records WHERE idempotency_key = ?",
            ("seed-bound-key",),
        ).fetchone()[0]
    assert projection is not None
    assert projection.optimistic_version == 0
    assert len(events) == 1
    assert idempotency_rows == 1
    assert workspace_after == workspace_before
    assert occupancy is not None
    assert occupancy.active_submission_id == review_seed.submission_id


def test_apply_review_rolls_back_when_cas_projection_fails(review_seed: ReviewSeed) -> None:
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        original_workspace = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
        assert original_workspace is not None
    with patch(
        "gateway_backend.infrastructure.control_db.sqlite_review.SQLiteReviewRepository.cas_projection",
        side_effect=ReviewVersionConflict(expected=0, actual=99),
    ):
        with pytest.raises(ReviewVersionConflict):
            _apply_review(
                review_seed,
                _apply_command(review_seed, action=ReviewAction.REJECT, reason="rollback"),
            )
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        projection = unit_of_work.review.get_projection(review_seed.submission_id)
        events = unit_of_work.review.list_events(review_seed.submission_id)
        workspace = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
        idempotency_rows = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_idempotency_records",
        ).fetchone()[0]
    assert projection is not None
    assert projection.optimistic_version == 0
    assert len(events) == 1
    assert idempotency_rows == 0
    assert workspace == original_workspace


def test_apply_review_rolls_back_when_release_occupancy_delete_fails(review_seed: ReviewSeed) -> None:
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        original_workspace = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
        assert original_workspace is not None
    with patch(
        "gateway_backend.infrastructure.control_db.sqlite_submission.SQLiteSubmissionRepository.delete_workspace_submission_occupancy",
        side_effect=SubmitOccupancyConflict("workspace submission occupancy delete failed"),
    ):
        with pytest.raises(ReviewWorkspaceOccupancyConflict):
            _apply_review(
                review_seed,
                _apply_command(review_seed, action=ReviewAction.REJECT, reason="rollback"),
            )
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        projection = unit_of_work.review.get_projection(review_seed.submission_id)
        events = unit_of_work.review.list_events(review_seed.submission_id)
        workspace = unit_of_work.workspace.get_workspace(review_seed.workspace_id)
        occupancy = unit_of_work.submission.get_workspace_occupancy(review_seed.workspace_id)
        idempotency_rows = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_idempotency_records",
        ).fetchone()[0]
    assert projection is not None
    assert projection.optimistic_version == 0
    assert len(events) == 1
    assert idempotency_rows == 0
    assert workspace == original_workspace
    assert occupancy is not None
    assert occupancy.active_submission_id == review_seed.submission_id


def test_get_review_facts_fails_closed_on_corrupted_event_reason(review_seed: ReviewSeed) -> None:
    _apply_review(
        review_seed,
        _apply_command(
            review_seed,
            action=ReviewAction.REJECT,
            reason="needs work",
            idempotency_key="reject-facts",
        ),
    )
    with ControlDbUnitOfWork(review_seed.db_path) as unit_of_work:
        unit_of_work.connection.execute(
            """
            UPDATE review_event_records
            SET reason = NULL
            WHERE submission_id = ? AND sequence = 1
            """,
            (review_seed.submission_id,),
        )
    with pytest.raises(ReviewIntegrityFailure) as exc_info:
        get_review_facts(
            context=review_seed.reviewer_context,
            submission_id=review_seed.submission_id,
            scope_resolution=_scope_resolution(review_seed),
            unit_of_work_factory=_uow_factory(review_seed.db_path),
        )
    assert exc_info.value.stable_code == "REVIEW_INTEGRITY_FAILURE"


def test_apply_review_replay_fails_closed_on_corrupted_event_reason(review_seed: ReviewSeed) -> None:
    command = _apply_command(
        review_seed,
        action=ReviewAction.REJECT,
        reason="needs work",
        idempotency_key="reject-replay",
    )
    _apply_review(review_seed, command)
    with ControlDbUnitOfWork(review_seed.db_path) as unit_of_work:
        unit_of_work.connection.execute(
            """
            UPDATE review_event_records
            SET reason = NULL
            WHERE submission_id = ? AND sequence = 1
            """,
            (review_seed.submission_id,),
        )
    with pytest.raises(ReviewIntegrityFailure) as exc_info:
        _apply_review(review_seed, command)
    assert exc_info.value.stable_code == "REVIEW_INTEGRITY_FAILURE"


@pytest.mark.serial
def test_apply_review_concurrent_commands_produce_one_commit_and_stable_conflict(
    review_seed: ReviewSeed,
) -> None:
    barrier = Barrier(2)
    outcomes: list[ApplyReviewResult | ReviewVersionConflict] = []

    def attempt(idempotency_key: str) -> None:
        barrier.wait()
        command = _apply_command(
            review_seed,
            action=ReviewAction.APPROVE,
            idempotency_key=idempotency_key,
        )
        try:
            outcomes.append(_apply_review(review_seed, command))
        except ReviewVersionConflict as exc:
            outcomes.append(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(attempt, "concurrent-a"),
            executor.submit(attempt, "concurrent-b"),
        ]
        for future in futures:
            future.result()

    successes = [outcome for outcome in outcomes if isinstance(outcome, ApplyReviewResult)]
    conflicts = [outcome for outcome in outcomes if isinstance(outcome, ReviewVersionConflict)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert successes[0].replay is False
    with ControlDbUnitOfWork(review_seed.db_path, read_only=True) as unit_of_work:
        events = unit_of_work.review.list_events(review_seed.submission_id)
        projection = unit_of_work.review.get_projection(review_seed.submission_id)
        idempotency_rows = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_idempotency_records",
        ).fetchone()[0]
    assert len(events) == 2
    assert projection is not None
    assert projection.optimistic_version == 1
    assert idempotency_rows == 1


def test_apply_review_second_command_gets_version_conflict_after_approve(
    review_seed: ReviewSeed,
) -> None:
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="first"),
    )
    with pytest.raises(ReviewVersionConflict):
        _apply_review(
            review_seed,
            _apply_command(
                review_seed,
                action=ReviewAction.APPROVE,
                expected_review_version=0,
                idempotency_key="second",
            ),
        )


def test_get_review_facts_requires_permission_before_object_read(review_seed: ReviewSeed) -> None:
    denied = replace(review_seed.reviewer_context, permissions=frozenset())
    with pytest.raises(PermissionDenied):
        get_review_facts(
            context=denied,
            submission_id=review_seed.submission_id,
            scope_resolution=_scope_resolution(review_seed),
            unit_of_work_factory=_uow_factory(review_seed.db_path),
        )


def test_get_review_facts_returns_ordered_events(review_seed: ReviewSeed) -> None:
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="facts-approve"),
    )
    facts = get_review_facts(
        context=review_seed.reviewer_context,
        submission_id=review_seed.submission_id,
        scope_resolution=_scope_resolution(review_seed),
        unit_of_work_factory=_uow_factory(review_seed.db_path),
    )
    assert facts.projection.status is ReviewStatus.APPROVED
    assert [event.sequence for event in facts.events] == [0, 1]
    assert facts.events[0].event_kind is ReviewEventKind.SUBMISSION_FINALIZED
    assert facts.events[1].event_kind is ReviewEventKind.APPROVED


def test_get_review_facts_rejects_cross_scope_submission(db_path: Path) -> None:
    seed = _seed_pending_review_submission(db_path)
    other_context = make_identity(
        actor_id="reviewer-2",
        device_key="device-other",
        project_id=seed.reviewer_context.business_project_id,
        permissions=frozenset({PERMISSION_REVIEW_SUBMISSION}),
    )
    with pytest.raises(ScopeForbidden):
        get_review_facts(
            context=other_context,
            submission_id=seed.submission_id,
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
        )
