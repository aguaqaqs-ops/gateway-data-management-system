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
    ArchiveCandidateRef,
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
from gateway_backend.application.submission.contracts import SUBMIT_JOB_CONTRACT_VERSION
from gateway_backend.operations.contracts import OPERATION_RUNTIME_CONTRACT_VERSION
from gateway_backend.domain.archive.models import (
    ArchiveAnomalyResolutionAction,
    ArchiveConfirmationAction,
)
from gateway_backend.domain.submission.review import ReviewAction
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.workspace_fixtures import make_identity
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


def delete_submission_review_state(db_path: Path, submission_id: str) -> None:
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            "DELETE FROM review_idempotency_records WHERE submission_id = ?",
            (submission_id,),
        )
        unit_of_work.connection.execute(
            "DELETE FROM review_event_records WHERE submission_id = ?",
            (submission_id,),
        )
        unit_of_work.connection.execute(
            "DELETE FROM review_projection_records WHERE submission_id = ?",
            (submission_id,),
        )


def assert_archive_durable_state_unchanged(
    db_path: Path,
    *,
    repository_id: str,
    baseline_head_version: int,
    expected_workspace_versions: dict[str, int] | None = None,
) -> None:
    from gateway_backend.infrastructure.control_db.sqlite_baseline import get_current_head_from_connection

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        plan_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_plan_records"
        ).fetchone()[0]
        result_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_result_records"
        ).fetchone()[0]
        disposition_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_disposition_records"
        ).fetchone()[0]
        head = get_current_head_from_connection(unit_of_work.connection, repository_id)
        assert plan_count == 0
        assert result_count == 0
        assert disposition_count == 0
        assert head.baseline_head_version == baseline_head_version
        if expected_workspace_versions is not None:
            for workspace_id, expected_version in expected_workspace_versions.items():
                workspace = unit_of_work.workspace.get_workspace(workspace_id)
                assert workspace is not None
                assert workspace.optimistic_version == expected_version


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
    candidates = get_archive_candidates(
        context=archiver_context,
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


def _insert_bulk_approved_archive_candidate_rows(
    db_path: Path,
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
    additional_count: int,
    start_index: int = 2,
) -> None:
    node_id = BASELINE_HEAD.business_baseline_node_id
    commit_id = BASELINE_HEAD.business_baseline_commit_id
    head_version = BASELINE_HEAD.baseline_head_version
    workspace_rows: list[tuple[object, ...]] = []
    operation_rows: list[tuple[object, ...]] = []
    attempt_rows: list[tuple[object, ...]] = []
    submission_rows: list[tuple[object, ...]] = []
    review_projection_rows: list[tuple[object, ...]] = []
    review_event_rows: list[tuple[object, ...]] = []
    occupancy_rows: list[tuple[object, ...]] = []
    for offset in range(additional_count):
        index = start_index + offset
        submission_id = f"sub-bulk-{index}"
        attempt_id = f"attempt-bulk-{index}"
        workspace_id = f"ws-bulk-{index}"
        operation_id = f"op-bulk-{index}"
        workspace_rows.append(
            (
                workspace_id,
                f"actor-bulk-{index}",
                gateway_device_external_key,
                business_project_id,
                repository_id,
            )
        )
        operation_rows.append(
            (
                operation_id,
                OPERATION_RUNTIME_CONTRACT_VERSION,
                "backend-vnext/submit",
                SUBMIT_JOB_CONTRACT_VERSION,
                b"{}",
                b"[]",
                b"[]",
            )
        )
        attempt_rows.append(
            (
                attempt_id,
                workspace_id,
                repository_id,
                node_id,
                commit_id,
                head_version,
                b"[]",
                "canonical-closure-1",
                "sha256:canonical-closure",
                operation_id,
                submission_id,
            )
        )
        submission_rows.append(
            (
                submission_id,
                attempt_id,
                workspace_id,
                repository_id,
                node_id,
                commit_id,
                b"[]",
            )
        )
        review_projection_rows.append((submission_id,))
        review_event_rows.append(
            (
                submission_id,
                0,
                "SUBMISSION_FINALIZED",
                None,
                "PENDING",
                "seed",
            )
        )
        review_event_rows.append(
            (
                submission_id,
                1,
                "APPROVED",
                "PENDING",
                "APPROVED",
                "approved for archive bulk fixture",
            )
        )
        occupancy_rows.append((workspace_id, submission_id))
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        connection = unit_of_work.connection
        connection.executemany(
            """
            INSERT INTO workspace_records (
                workspace_id, owner_actor_id, gateway_device_external_key, business_project_id,
                repository_id, state, generation, optimistic_version, current_upload_revision_id,
                current_preview_result_id, created_at_us, updated_at_us, closed_at_us
            ) VALUES (?, ?, ?, ?, ?, 'OPEN', 1, 1, 'ur-1', 'pr-1', 0, 0, NULL)
            """,
            workspace_rows,
        )
        connection.executemany(
            """
            INSERT INTO operation_records (
                operation_id, contract_version, optimistic_version, job_kind, job_contract_version,
                job_payload, job_payload_ref, business_refs, artifact_refs, repository_operation_id,
                checkpoint_ref, ready_closure_ref, status, diagnostic, cancel_requested,
                created_at_us, updated_at_us, completed_at_us
            ) VALUES (?, ?, 0, ?, ?, ?, NULL, ?, ?, NULL, NULL, NULL, 'SUCCEEDED', NULL, 0, 0, 0, 0)
            """,
            operation_rows,
        )
        connection.executemany(
            """
            INSERT INTO submit_attempt_records (
                submit_attempt_id, workspace_id, workspace_generation, upload_revision_id,
                preview_result_id, repository_id, business_baseline_node_id,
                business_baseline_commit_id, baseline_head_version, repository_expected_commit_id,
                canonical_business_digest, source_digest, snapshot_digest, source_artifact_refs,
                canonical_table_set_closure_ref, canonical_table_set_closure_digest,
                preview_ready_closure_ref, preview_ready_closure_digest,
                canonicalization_manifest_ref, canonicalization_manifest_digest,
                repository_import_artifact_ref, repository_artifact_ref, repository_operation_id,
                repository_operation_evidence, requested_target_ref, requested_verification_policy,
                requested_unknown_type_policy, builder_mutation_policy, accept_idempotency_key,
                accept_request_fingerprint, repository_upload_idempotency_key,
                repository_import_idempotency_key, operation_id, state, submission_id,
                optimistic_version, created_by, created_at_us, effect_pending_at_us,
                finalized_at_us, aborted_at_us, abort_code
            ) VALUES (
                ?, ?, 1, 'ur-1', 'pr-1', ?, ?, ?, ?, 'commit-main',
                'sha256:canonical', 'd-source', 'd-snapshot', ?, ?, ?, 'closure-1', 'd-closure',
                'manifest-1', 'sha256:manifest', NULL, NULL, NULL, NULL, 'main', 'STRUCTURAL',
                'REJECT', 'REBUILD_ALWAYS', 'accept-key', 'sha256:fp', 'upload-key', 'import-key',
                ?, 'FINALIZED', ?, 1, 'actor-1', 0, 0, 0, NULL, NULL
            )
            """,
            attempt_rows,
        )
        connection.executemany(
            """
            INSERT INTO submission_records (
                submission_id, submit_attempt_id, workspace_id, workspace_generation,
                upload_revision_id, preview_result_id, repository_id, based_on_baseline_node_id,
                business_baseline_commit_id, repository_commit_id, canonical_business_digest,
                source_artifact_refs, canonicalization_manifest_ref,
                canonicalization_manifest_digest, repository_import_artifact_raw_sha256,
                repository_artifact_id, requested_verification_policy,
                completed_verification_policy, requested_unknown_type_policy, target_ref,
                created_by, created_at_us
            ) VALUES (
                ?, ?, ?, 1, 'ur-1', 'pr-1', ?, ?, ?, 'commit-new',
                'sha256:canonical', ?, 'manifest-1', 'sha256:manifest', 'sha256:package',
                'repo-artifact-1', 'STRUCTURAL', 'STRUCTURAL', 'REJECT', 'main', 'actor-1', 0
            )
            """,
            submission_rows,
        )
        connection.executemany(
            """
            INSERT INTO review_projection_records (
                submission_id, status, optimistic_version, latest_sequence,
                updated_by, updated_at_us
            ) VALUES (?, 'APPROVED', 1, 1, 'actor-1', 1)
            """,
            review_projection_rows,
        )
        connection.executemany(
            """
            INSERT INTO review_event_records (
                submission_id, sequence, event_kind, from_status, to_status,
                reason, actor_id, occurred_at_us
            ) VALUES (?, ?, ?, ?, ?, ?, 'actor-1', ?)
            """,
            [
                (
                    submission_id,
                    sequence,
                    event_kind,
                    from_status,
                    to_status,
                    reason,
                    sequence,
                )
                for submission_id, sequence, event_kind, from_status, to_status, reason in review_event_rows
            ],
        )
        connection.executemany(
            """
            INSERT INTO workspace_submit_occupancy_records (
                workspace_id, active_submit_attempt_id, active_submission_id
            ) VALUES (?, NULL, ?)
            """,
            occupancy_rows,
        )


def _insert_bulk_rejected_archive_candidate_rows(
    db_path: Path,
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
    count: int,
    start_index: int = 2,
) -> None:
    node_id = BASELINE_HEAD.business_baseline_node_id
    commit_id = BASELINE_HEAD.business_baseline_commit_id
    head_version = BASELINE_HEAD.baseline_head_version
    workspace_rows: list[tuple[object, ...]] = []
    operation_rows: list[tuple[object, ...]] = []
    attempt_rows: list[tuple[object, ...]] = []
    submission_rows: list[tuple[object, ...]] = []
    review_projection_rows: list[tuple[object, ...]] = []
    review_event_rows: list[tuple[object, ...]] = []
    occupancy_rows: list[tuple[object, ...]] = []
    for offset in range(count):
        index = start_index + offset
        submission_id = f"sub-rejected-{index}"
        attempt_id = f"attempt-rejected-{index}"
        workspace_id = f"ws-rejected-{index}"
        operation_id = f"op-rejected-{index}"
        workspace_rows.append(
            (
                workspace_id,
                f"actor-rejected-{index}",
                gateway_device_external_key,
                business_project_id,
                repository_id,
            )
        )
        operation_rows.append(
            (
                operation_id,
                OPERATION_RUNTIME_CONTRACT_VERSION,
                "backend-vnext/submit",
                SUBMIT_JOB_CONTRACT_VERSION,
                b"{}",
                b"[]",
                b"[]",
            )
        )
        attempt_rows.append(
            (
                attempt_id,
                workspace_id,
                repository_id,
                node_id,
                commit_id,
                head_version,
                b"[]",
                "canonical-closure-1",
                "sha256:canonical-closure",
                operation_id,
                submission_id,
            )
        )
        submission_rows.append(
            (
                submission_id,
                attempt_id,
                workspace_id,
                repository_id,
                node_id,
                commit_id,
                b"[]",
            )
        )
        review_projection_rows.append((submission_id,))
        review_event_rows.append(
            (
                submission_id,
                0,
                "SUBMISSION_FINALIZED",
                None,
                "PENDING",
                "seed",
            )
        )
        review_event_rows.append(
            (
                submission_id,
                1,
                "REJECTED",
                "PENDING",
                "REJECTED",
                "rejected for archive history fixture",
            )
        )
        occupancy_rows.append((workspace_id, submission_id))
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        connection = unit_of_work.connection
        connection.executemany(
            """
            INSERT INTO workspace_records (
                workspace_id, owner_actor_id, gateway_device_external_key, business_project_id,
                repository_id, state, generation, optimistic_version, current_upload_revision_id,
                current_preview_result_id, created_at_us, updated_at_us, closed_at_us
            ) VALUES (?, ?, ?, ?, ?, 'OPEN', 1, 1, 'ur-1', 'pr-1', 0, 0, NULL)
            """,
            workspace_rows,
        )
        connection.executemany(
            """
            INSERT INTO operation_records (
                operation_id, contract_version, optimistic_version, job_kind, job_contract_version,
                job_payload, job_payload_ref, business_refs, artifact_refs, repository_operation_id,
                checkpoint_ref, ready_closure_ref, status, diagnostic, cancel_requested,
                created_at_us, updated_at_us, completed_at_us
            ) VALUES (?, ?, 0, ?, ?, ?, NULL, ?, ?, NULL, NULL, NULL, 'SUCCEEDED', NULL, 0, 0, 0, 0)
            """,
            operation_rows,
        )
        connection.executemany(
            """
            INSERT INTO submit_attempt_records (
                submit_attempt_id, workspace_id, workspace_generation, upload_revision_id,
                preview_result_id, repository_id, business_baseline_node_id,
                business_baseline_commit_id, baseline_head_version, repository_expected_commit_id,
                canonical_business_digest, source_digest, snapshot_digest, source_artifact_refs,
                canonical_table_set_closure_ref, canonical_table_set_closure_digest,
                preview_ready_closure_ref, preview_ready_closure_digest,
                canonicalization_manifest_ref, canonicalization_manifest_digest,
                repository_import_artifact_ref, repository_artifact_ref, repository_operation_id,
                repository_operation_evidence, requested_target_ref, requested_verification_policy,
                requested_unknown_type_policy, builder_mutation_policy, accept_idempotency_key,
                accept_request_fingerprint, repository_upload_idempotency_key,
                repository_import_idempotency_key, operation_id, state, submission_id,
                optimistic_version, created_by, created_at_us, effect_pending_at_us,
                finalized_at_us, aborted_at_us, abort_code
            ) VALUES (
                ?, ?, 1, 'ur-1', 'pr-1', ?, ?, ?, ?, 'commit-main',
                'sha256:canonical', 'd-source', 'd-snapshot', ?, ?, ?, 'closure-1', 'd-closure',
                'manifest-1', 'sha256:manifest', NULL, NULL, NULL, NULL, 'main', 'STRUCTURAL',
                'REJECT', 'REBUILD_ALWAYS', 'accept-key', 'sha256:fp', 'upload-key', 'import-key',
                ?, 'FINALIZED', ?, 1, 'actor-1', 0, 0, 0, NULL, NULL
            )
            """,
            attempt_rows,
        )
        connection.executemany(
            """
            INSERT INTO submission_records (
                submission_id, submit_attempt_id, workspace_id, workspace_generation,
                upload_revision_id, preview_result_id, repository_id, based_on_baseline_node_id,
                business_baseline_commit_id, repository_commit_id, canonical_business_digest,
                source_artifact_refs, canonicalization_manifest_ref,
                canonicalization_manifest_digest, repository_import_artifact_raw_sha256,
                repository_artifact_id, requested_verification_policy,
                completed_verification_policy, requested_unknown_type_policy, target_ref,
                created_by, created_at_us
            ) VALUES (
                ?, ?, ?, 1, 'ur-1', 'pr-1', ?, ?, ?, 'commit-new',
                'sha256:canonical', ?, 'manifest-1', 'sha256:manifest', 'sha256:package',
                'repo-artifact-1', 'STRUCTURAL', 'STRUCTURAL', 'REJECT', 'main', 'actor-1', 0
            )
            """,
            submission_rows,
        )
        connection.executemany(
            """
            INSERT INTO review_projection_records (
                submission_id, status, optimistic_version, latest_sequence,
                updated_by, updated_at_us
            ) VALUES (?, 'REJECTED', 1, 1, 'actor-1', 1)
            """,
            review_projection_rows,
        )
        connection.executemany(
            """
            INSERT INTO review_event_records (
                submission_id, sequence, event_kind, from_status, to_status,
                reason, actor_id, occurred_at_us
            ) VALUES (?, ?, ?, ?, ?, ?, 'actor-1', ?)
            """,
            [
                (
                    submission_id,
                    sequence,
                    event_kind,
                    from_status,
                    to_status,
                    reason,
                    sequence,
                )
                for submission_id, sequence, event_kind, from_status, to_status, reason in review_event_rows
            ],
        )
        connection.executemany(
            """
            INSERT INTO workspace_submit_occupancy_records (
                workspace_id, active_submit_attempt_id, active_submission_id
            ) VALUES (?, NULL, ?)
            """,
            occupancy_rows,
        )


def seed_bulk_approved_archive_candidates(db_path: Path, *, count: int) -> ArchiveSeed:
    seed = seed_approved_archive_candidate(db_path)
    if count > 1:
        _insert_bulk_approved_archive_candidate_rows(
            db_path,
            repository_id=seed.repository_id,
            gateway_device_external_key=seed.archiver_context.gateway_device_external_key,
            business_project_id=seed.archiver_context.business_project_id,
            additional_count=count - 1,
        )
    return seed


def seed_triple_approved_sibling_archive(
    db_path: Path,
) -> tuple[ArchiveSeed, tuple[ArchiveCandidateRef, ...]]:
    primary_review = _seed_pending_review_submission(db_path)
    _apply_review(
        primary_review,
        _apply_command(primary_review, action=ReviewAction.APPROVE, idempotency_key="approve-primary"),
    )
    sibling_ids = ("sub-2", "sub-3")
    sibling_reviews = []
    for submission_id in sibling_ids:
        sibling_review = _seed_additional_pending_review_submission(
            db_path,
            submission_id=submission_id,
            device_key=primary_review.reviewer_context.gateway_device_external_key,
            repository_id=primary_review.repository_id,
            project_id=primary_review.reviewer_context.business_project_id,
        )
        _apply_review(
            sibling_review,
            _apply_command(
                sibling_review,
                action=ReviewAction.APPROVE,
                idempotency_key=f"approve-{submission_id}",
            ),
        )
        sibling_reviews.append(sibling_review)
    archiver_context = _archiver_context(
        primary_review.reviewer_context.gateway_device_external_key,
        primary_review.reviewer_context.business_project_id,
    )
    candidates = get_archive_candidates(
        context=archiver_context,
        unit_of_work_factory=_uow_factory(db_path),
    )
    assert len(candidates.candidates) == 3
    primary_ref = next(
        candidate
        for candidate in candidates.candidates
        if candidate.submission_id == primary_review.submission_id
    )
    sibling_refs = tuple(
        next(candidate for candidate in candidates.candidates if candidate.submission_id == submission_id)
        for submission_id in sibling_ids
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
    return primary, sibling_refs


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
    candidates = get_archive_candidates(
        context=archiver_context,
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
