"""Archive Start transaction tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
import pytest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.archive.errors import (
    ActiveSubmitAttempt,
    ArchiveAnomalyUnresolved,
    ArchiveConfirmationRequired,
)
from gateway_backend.application.archive.audit import (
    AppendArchiveAnomalyResolutionCommand,
    append_archive_anomaly_resolution,
)
from gateway_backend.application.archive.queries import (
    PROJECT_IDENTITY_EXCEPTION_ISSUE,
    preview_archive_plan,
)
from gateway_backend.application.archive.start import StartArchiveCommand
from gateway_backend.application.submission.errors import IdempotencyConflict
from gateway_backend.domain.archive.models import (
    ArchiveAnomalyResolutionAction,
    ArchiveDispositionKind,
    ArchiveSubjectKind,
)
from gateway_backend.domain.submission.models import (
    IdentityConfirmationAction,
    SubmitIdentityConfirmation,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.sqlite_baseline import get_current_head_from_connection
from gateway_backend.infrastructure.control_db.sqlite_submission import _encode_identity_confirmations
from tests.support.archive_fixtures import (
    assert_archive_durable_state_unchanged,
    append_selection_confirmation,
    seed_approved_archive_candidate,
    start_archive_for_seed,
)
from tests.test_review_transactions import _uow_factory
from tests.test_submit_transactions import BASELINE_HEAD

pytestmark = pytest.mark.unit

TS_ARCHIVE = datetime(2024, 7, 1, 12, 0, 0, tzinfo=UTC)


def test_identity_exception_requires_reasoned_resolution_before_archive(db_path: Path) -> None:
    seed = seed_approved_archive_candidate(db_path)
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        submission = unit_of_work.submission.get_submission(seed.submission_id)
        assert submission is not None
        preview_result = unit_of_work.workspace.get_preview_result(submission.preview_result_id)
        assert preview_result is not None
    confirmation = SubmitIdentityConfirmation(
        action=IdentityConfirmationAction.ACCEPT_DATASET_REPLACEMENT,
        assessment_set_digest=preview_result.identity_assessment_set_digest.value,
        reason="approved dataset replacement",
        actor_id="submitter-1",
        confirmed_at=TS_ARCHIVE,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        binding_row = unit_of_work.connection.execute(
            "SELECT binding FROM preview_result_records WHERE preview_result_id = ?",
            (submission.preview_result_id,),
        ).fetchone()
        assert binding_row is not None
        binding = json.loads(binding_row["binding"])
        binding["digests"]["bundle_digest"] = "sha256:" + "a" * 64
        unit_of_work.connection.execute(
            "UPDATE preview_result_records SET binding = ? WHERE preview_result_id = ?",
            (canonicalize_json_value(binding), submission.preview_result_id),
        )
        encoded_confirmations = _encode_identity_confirmations((confirmation,))
        unit_of_work.connection.execute(
            "UPDATE submit_attempt_records SET identity_confirmations = ? WHERE submit_attempt_id = ?",
            (encoded_confirmations, submission.submit_attempt_id),
        )
        unit_of_work.connection.execute(
            "UPDATE submission_records SET identity_confirmations = ? WHERE submission_id = ?",
            (encoded_confirmations, seed.submission_id),
        )

    preview = preview_archive_plan(
        context=seed.archiver_context,
        selected_ref=seed.selected_ref,
        unit_of_work_factory=_uow_factory(db_path),
    )
    assert len(preview.anomalies) == 1
    anomaly = preview.anomalies[0]
    assert anomaly.subject_kind is ArchiveSubjectKind.PROJECT_IDENTITY_EXCEPTION
    assert anomaly.issue_code == PROJECT_IDENTITY_EXCEPTION_ISSUE
    assert anomaly.target_submission_id == seed.submission_id
    assert anomaly.target_candidate_digest == seed.selected_ref.expected_candidate_digest

    confirmation_sequence = append_selection_confirmation(seed)
    with pytest.raises(ArchiveAnomalyUnresolved, match="archive anomaly is unresolved"):
        start_archive_for_seed(
            seed,
            confirmation_sequence=confirmation_sequence,
            now=TS_ARCHIVE,
        )

    resolution = append_archive_anomaly_resolution(
        command=AppendArchiveAnomalyResolutionCommand(
            context=seed.archiver_context,
            idempotency_key="identity-exception-resolution",
            expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
            expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
            selected=seed.selected_ref,
            candidate_set_digest=seed.candidate_set_digest,
            subject_digest=anomaly.subject_digest,
            expected_sequence=0,
            action=ArchiveAnomalyResolutionAction.ACKNOWLEDGE_IDENTITY_EXCEPTION,
            reason="reviewed project identity change",
            subject_kind=ArchiveSubjectKind.PROJECT_IDENTITY_EXCEPTION,
            issue_code=PROJECT_IDENTITY_EXCEPTION_ISSUE,
            target_submission_id=seed.submission_id,
            target_candidate_digest=seed.selected_ref.expected_candidate_digest,
        ),
        unit_of_work_factory=_uow_factory(db_path),
        now=TS_ARCHIVE,
    )
    result = start_archive_for_seed(
        seed,
        confirmation_sequence=confirmation_sequence,
        anomaly_resolution_sequences=((anomaly.subject_digest, resolution.sequence),),
        now=TS_ARCHIVE,
    )
    assert result.selected_submission_id == seed.submission_id


def test_get_archive_candidates_rejects_workspace_generation_mismatch(db_path: Path) -> None:
    from gateway_backend.application.archive.errors import ArchiveIntegrityFailure
    from gateway_backend.application.archive.queries import get_archive_candidates

    seed = seed_approved_archive_candidate(db_path)
    submission = None
    workspace_version = 0
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        submission = unit_of_work.submission.get_submission(seed.submission_id)
        assert submission is not None
        workspace = unit_of_work.workspace.get_workspace(submission.workspace_id)
        assert workspace is not None
        workspace_version = workspace.optimistic_version
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            "UPDATE workspace_records SET generation = 99 WHERE workspace_id = ?",
            (submission.workspace_id,),
        )
    with pytest.raises(ArchiveIntegrityFailure):
        get_archive_candidates(
            context=seed.archiver_context,
            unit_of_work_factory=_uow_factory(db_path),
        )
    assert_archive_durable_state_unchanged(
        db_path,
        repository_id=seed.repository_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version,
        expected_workspace_versions={submission.workspace_id: workspace_version},
    )


def test_get_archive_candidates_rejects_workspace_project_mismatch(db_path: Path) -> None:
    from gateway_backend.application.archive.errors import ArchiveIntegrityFailure
    from gateway_backend.application.archive.queries import get_archive_candidates

    seed = seed_approved_archive_candidate(db_path)
    submission = None
    workspace_version = 0
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        submission = unit_of_work.submission.get_submission(seed.submission_id)
        assert submission is not None
        workspace = unit_of_work.workspace.get_workspace(submission.workspace_id)
        assert workspace is not None
        workspace_version = workspace.optimistic_version
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            "UPDATE workspace_records SET business_project_id = 'project-other' WHERE workspace_id = ?",
            (submission.workspace_id,),
        )
    with pytest.raises(ArchiveIntegrityFailure, match="repository scope does not match candidate workspace"):
        get_archive_candidates(
            context=seed.archiver_context,
            unit_of_work_factory=_uow_factory(db_path),
        )
    assert_archive_durable_state_unchanged(
        db_path,
        repository_id=seed.repository_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version,
        expected_workspace_versions={submission.workspace_id: workspace_version},
    )


def test_start_archive_rejects_review_event_to_status_tampering(db_path: Path) -> None:
    from gateway_backend.application.archive.contracts import ArchiveAuditReferenceInput
    from gateway_backend.application.archive.errors import ArchiveIntegrityFailure
    from gateway_backend.application.archive.start import start_archive

    seed = seed_approved_archive_candidate(db_path)
    confirmation_sequence = append_selection_confirmation(seed, now=TS_ARCHIVE)
    submission = None
    workspace_version = 0
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        submission = unit_of_work.submission.get_submission(seed.submission_id)
        assert submission is not None
        workspace = unit_of_work.workspace.get_workspace(submission.workspace_id)
        assert workspace is not None
        workspace_version = workspace.optimistic_version
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            """
            UPDATE review_event_records
            SET to_status = 'REJECTED'
            WHERE submission_id = ? AND sequence = 1
            """,
            (seed.submission_id,),
        )
    with pytest.raises(ArchiveIntegrityFailure, match="to_status does not match transition policy"):
        start_archive(
            command=StartArchiveCommand(
                context=seed.archiver_context,
                idempotency_key="start-with-tampered-review",
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
    assert_archive_durable_state_unchanged(
        db_path,
        repository_id=seed.repository_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version,
        expected_workspace_versions={submission.workspace_id: workspace_version},
    )


@pytest.mark.parametrize(
    "tamper_sql",
    [
        pytest.param(
            "DELETE FROM review_projection_records WHERE submission_id = ?",
            id="missing_projection",
        ),
        pytest.param(
            """
            UPDATE review_projection_records
            SET status = 'REJECTED'
            WHERE submission_id = ?
            """,
            id="projection_event_mismatch",
        ),
    ],
)
def test_start_archive_rejects_tampered_sibling_projection(
    db_path: Path,
    tamper_sql: str,
) -> None:
    from gateway_backend.application.archive.contracts import ArchiveAuditReferenceInput
    from gateway_backend.application.archive.errors import ArchiveIntegrityFailure
    from gateway_backend.application.archive.start import start_archive
    from tests.support.archive_fixtures import seed_approved_dual_sibling_archive

    dual_seed = seed_approved_dual_sibling_archive(db_path)
    confirmation_sequence = append_selection_confirmation(dual_seed.primary, now=TS_ARCHIVE)
    workspace_versions: dict[str, int] = {}
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        for submission_id in (
            dual_seed.primary.submission_id,
            dual_seed.target_submission_id,
        ):
            submission = unit_of_work.submission.get_submission(submission_id)
            assert submission is not None
            workspace = unit_of_work.workspace.get_workspace(submission.workspace_id)
            assert workspace is not None
            workspace_versions[workspace.workspace_id] = workspace.optimistic_version
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            tamper_sql,
            (dual_seed.target_submission_id,),
        )
    with pytest.raises(ArchiveIntegrityFailure):
        start_archive(
            command=StartArchiveCommand(
                context=dual_seed.primary.archiver_context,
                idempotency_key="start-with-tampered-sibling",
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
            unit_of_work_factory=_uow_factory(db_path),
            now=TS_ARCHIVE,
        )
    assert_archive_durable_state_unchanged(
        db_path,
        repository_id=dual_seed.primary.repository_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version,
        expected_workspace_versions=workspace_versions,
    )


def test_start_archive_rejects_missing_review_state(db_path: Path) -> None:
    from gateway_backend.application.archive.contracts import ArchiveAuditReferenceInput
    from gateway_backend.application.archive.errors import ArchiveIntegrityFailure
    from gateway_backend.application.archive.start import start_archive
    from tests.support.archive_fixtures import (
        delete_submission_review_state,
        seed_approved_dual_sibling_archive,
    )

    dual_seed = seed_approved_dual_sibling_archive(db_path)
    confirmation_sequence = append_selection_confirmation(dual_seed.primary, now=TS_ARCHIVE)
    workspace_versions: dict[str, int] = {}
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        for submission_id in (
            dual_seed.primary.submission_id,
            dual_seed.target_submission_id,
        ):
            submission = unit_of_work.submission.get_submission(submission_id)
            assert submission is not None
            workspace = unit_of_work.workspace.get_workspace(submission.workspace_id)
            assert workspace is not None
            workspace_versions[workspace.workspace_id] = workspace.optimistic_version
    delete_submission_review_state(db_path, dual_seed.target_submission_id)
    with pytest.raises(ArchiveIntegrityFailure, match="review projection is missing"):
        start_archive(
            command=StartArchiveCommand(
                context=dual_seed.primary.archiver_context,
                idempotency_key="start-with-missing-review-state",
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
            unit_of_work_factory=_uow_factory(db_path),
            now=TS_ARCHIVE,
        )
    assert_archive_durable_state_unchanged(
        db_path,
        repository_id=dual_seed.primary.repository_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version,
        expected_workspace_versions=workspace_versions,
    )


def test_start_archive_replay_requires_transaction_fresh_enabled_mapping(db_path: Path) -> None:
    from gateway_backend.application.archive.contracts import ArchiveAuditReferenceInput
    from gateway_backend.application.archive.start import start_archive
    from gateway_backend.domain.workspace.errors import ScopeResolutionError
    from tests.support.baseline_fixtures import upsert_provisioned_mapping_row

    seed = seed_approved_archive_candidate(db_path)
    confirmation_sequence = append_selection_confirmation(seed, now=TS_ARCHIVE)
    start_archive_for_seed(
        seed,
        idempotency_key="replay-mapping-key",
        confirmation_sequence=confirmation_sequence,
        now=TS_ARCHIVE,
    )
    upsert_provisioned_mapping_row(
        seed.db_path,
        device_key=seed.archiver_context.gateway_device_external_key,
        project_id=seed.archiver_context.business_project_id,
        repository_id=seed.repository_id,
        enabled=False,
    )
    with pytest.raises(ScopeResolutionError):
        start_archive(
            command=StartArchiveCommand(
                context=seed.archiver_context,
                idempotency_key="replay-mapping-key",
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


def test_start_archive_triple_sibling_accepts_digest_sorted_resolution_refs(db_path: Path) -> None:
    import json

    from gateway_backend.application.archive.contracts import compute_anomaly_subject_digest
    from tests.support.archive_fixtures import (
        append_anomaly_resolution,
        append_selection_confirmation,
        seed_triple_approved_sibling_archive,
        start_archive_for_seed,
    )

    primary, sibling_refs = seed_triple_approved_sibling_archive(db_path)
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        primary_submission = unit_of_work.submission.get_submission(primary.submission_id)
        assert primary_submission is not None
        primary_workspace = unit_of_work.workspace.get_workspace(primary_submission.workspace_id)
        assert primary_workspace is not None
        accepted_version = primary_workspace.optimistic_version
        workspace_id = primary_workspace.workspace_id
    confirmation_sequence = append_selection_confirmation(primary, now=TS_ARCHIVE)
    resolution_sequences: list[tuple[str, int]] = []
    for sibling_ref in sibling_refs:
        anomaly_subject_digest = compute_anomaly_subject_digest(
            selection_subject_digest=primary.selection_subject_digest,
            issue_code="APPROVED_SIBLING_EXCLUDED",
            target_submission_id=sibling_ref.submission_id,
            target_candidate_digest=sibling_ref.expected_candidate_digest,
        )
        resolution_sequence = append_anomaly_resolution(
            primary,
            anomaly_subject_digest=anomaly_subject_digest,
            target_submission_id=sibling_ref.submission_id,
            target_candidate_digest=sibling_ref.expected_candidate_digest,
            idempotency_key=f"resolve-{sibling_ref.submission_id}",
            now=TS_ARCHIVE,
        )
        resolution_sequences.append((anomaly_subject_digest, resolution_sequence))
    resolution_sequences.sort(key=lambda item: item[0])
    result = start_archive_for_seed(
        primary,
        confirmation_sequence=confirmation_sequence,
        anomaly_resolution_sequences=tuple(resolution_sequences),
        now=TS_ARCHIVE,
    )
    assert result.replay is False
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        row = unit_of_work.connection.execute(
            "SELECT frozen_input_json FROM archive_plan_records WHERE plan_id = ?",
            (result.archive_plan_id,),
        ).fetchone()
        assert row is not None
        frozen_input = json.loads(row[0])
        assert len(frozen_input["candidate_refs"]) == 3
        assert len(frozen_input["workspace_acceptance_bindings"]) == 3
        binding = next(
            item
            for item in frozen_input["workspace_acceptance_bindings"]
            if item["submission_id"] == primary.submission_id
        )
        assert binding["workspace_id"] == workspace_id
        assert binding["optimistic_version"] == accepted_version
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        workspace_after_start = unit_of_work.workspace.get_workspace(workspace_id)
        assert workspace_after_start is not None
        version_after_start = workspace_after_start.optimistic_version
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            "UPDATE workspace_records SET optimistic_version = optimistic_version + 1 WHERE workspace_id = ?",
            (workspace_id,),
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(workspace_id)
        assert workspace is not None
        assert workspace.optimistic_version == version_after_start + 1
        row_after = unit_of_work.connection.execute(
            "SELECT frozen_input_json FROM archive_plan_records WHERE plan_id = ?",
            (result.archive_plan_id,),
        ).fetchone()
        assert row_after is not None
        frozen_after = json.loads(row_after[0])
        binding_after = next(
            item
            for item in frozen_after["workspace_acceptance_bindings"]
            if item["submission_id"] == primary.submission_id
        )
        assert binding_after["optimistic_version"] == accepted_version


def test_start_archive_requires_confirmation_before_plan_is_written(db_path: Path) -> None:
    seed = seed_approved_archive_candidate(db_path)
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
            dual_seed.target_submission_id
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
            unit_of_work_factory=_uow_factory(db_path),
            now=TS_ARCHIVE,
        )


def test_start_archive_rejects_unresolved_sibling_anomaly(db_path: Path) -> None:
    from gateway_backend.application.archive.contracts import ArchiveAuditReferenceInput
    from gateway_backend.application.archive.start import start_archive
    from tests.support.archive_fixtures import seed_approved_dual_sibling_archive

    dual_seed = seed_approved_dual_sibling_archive(db_path)
    confirmation_sequence = append_selection_confirmation(dual_seed.primary, now=TS_ARCHIVE)
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
            unit_of_work_factory=_uow_factory(db_path),
            now=TS_ARCHIVE,
        )
