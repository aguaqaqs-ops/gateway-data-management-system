"""Review SQLite persistence tests."""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway_backend.domain.submission.errors import ReviewClosureViolation, ReviewVersionConflict
from gateway_backend.domain.submission.review import (
    ReviewAction,
    ReviewEvent,
    ReviewEventKind,
    ReviewIdempotencyRecord,
    ReviewProjection,
    ReviewStatus,
    build_seed_projection,
    resolve_review_transition,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from gateway_backend.infrastructure.control_db.schema import CONTROL_DB_SCHEMA_STATEMENTS
from gateway_backend.application.submission.contracts import SUBMIT_JOB_CONTRACT_VERSION
from gateway_backend.operations import OPERATION_RUNTIME_CONTRACT_VERSION

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
TS1 = datetime(2024, 6, 1, 12, 30, 0, tzinfo=UTC)


def _table_sql(table: str) -> str:
    matches = [statement for statement in CONTROL_DB_SCHEMA_STATEMENTS if f"CREATE TABLE {table} (" in statement]
    assert len(matches) == 1, table
    return " ".join(matches[0].split())


def _in_list_literals(table_sql: str, column: str) -> set[str]:
    match = re.search(rf"\b{column} IN \(([^)]*)\)", table_sql)
    assert match is not None, column
    return {item.strip().strip("'") for item in match.group(1).split(",")}


def test_review_schema_enums_match_domain_literals() -> None:
    projection_sql = _table_sql("review_projection_records")
    event_sql = _table_sql("review_event_records")
    assert _in_list_literals(projection_sql, "status") == {status.value for status in ReviewStatus}
    assert _in_list_literals(event_sql, "event_kind") == {kind.value for kind in ReviewEventKind}


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "control.db"
    initialize_control_db(path)
    return path


def test_sqlite_review_repository_round_trips_seed(db_path: Path) -> None:
    event, projection = build_seed_projection(
        submission_id="sub-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            """
            INSERT INTO workspace_records (
                workspace_id, owner_actor_id, gateway_device_external_key, business_project_id,
                repository_id, state, generation, optimistic_version, current_upload_revision_id,
                current_preview_result_id, created_at_us, updated_at_us, closed_at_us
            ) VALUES ('ws-1', 'actor-1', 'device-1', 'project-1', 'repo-1', 'OPEN', 1, 0, NULL, NULL, 1, 1, NULL)
            """
        )
        _insert_operation_record(unit_of_work.connection, operation_id="op-1")
        unit_of_work.connection.execute(
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
                'sa-1', 'ws-1', 1, 'ur-1', 'pr-1', 'repo-1', 'node-1', 'commit-base', 1, 'commit-main',
                'sha256:canonical', 'd-source', 'd-snapshot', ?, ?, ?, 'closure-1', 'd-closure',
                'manifest-1', 'sha256:manifest', NULL, NULL, NULL, NULL, 'main', 'STRUCTURAL',
                'REJECT', 'ADAPTIVE_PATCH', 'accept-key', 'sha256:fp', 'upload-key', 'import-key',
                'op-1', 'FINALIZED', 'sub-1', 1, 'actor-1', 1, 1, 1, NULL, NULL
            )
            """,
            (b"[]", "canonical-closure-1", "sha256:canonical-closure"),
        )
        unit_of_work.connection.execute(
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
                'sub-1', 'sa-1', 'ws-1', 1, 'ur-1', 'pr-1', 'repo-1', 'node-1', 'commit-base',
                'commit-new', 'sha256:canonical', ?, 'manifest-1', 'sha256:manifest',
                'sha256:package', 'repo-artifact-1', 'STRUCTURAL', 'STRUCTURAL', 'REJECT', 'main',
                'actor-1', 1
            )
            """,
            (b"[]",),
        )
        unit_of_work.review.insert_seed(event, projection)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        loaded_projection = unit_of_work.review.get_projection("sub-1")
        loaded_events = unit_of_work.review.list_events("sub-1")

    assert loaded_projection == projection
    assert loaded_events == (event,)


def test_sqlite_review_repository_append_cas_and_idempotency(db_path: Path) -> None:
    seed_event, seed_projection = build_seed_projection(
        submission_id="sub-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    event_kind, to_status = resolve_review_transition(ReviewStatus.PENDING, ReviewAction.APPROVE)
    approved_event = ReviewEvent(
        submission_id="sub-1",
        sequence=1,
        event_kind=event_kind,
        from_status=ReviewStatus.PENDING,
        to_status=to_status,
        reason=None,
        actor_id="reviewer-1",
        occurred_at=TS1,
    )
    approved_projection = ReviewProjection(
        submission_id="sub-1",
        status=to_status,
        optimistic_version=1,
        latest_sequence=1,
        updated_by="reviewer-1",
        updated_at=TS1,
    )
    idempotency = ReviewIdempotencyRecord(
        business_project_id="project-1",
        submission_id="sub-1",
        idempotency_key="review-key-1",
        request_fingerprint="sha256:fp",
        event_sequence=1,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        _seed_submission_row(unit_of_work.connection)
        unit_of_work.review.insert_seed(seed_event, seed_projection)
        unit_of_work.review.append_event(approved_event)
        unit_of_work.review.cas_projection(approved_projection, expected_version=0)
        unit_of_work.review.insert_idempotency(idempotency)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        loaded = unit_of_work.review.find_idempotency("project-1", "review-key-1")
        events = unit_of_work.review.list_events("sub-1")

    assert loaded == idempotency
    assert len(events) == 2
    assert events[1].reason is None
    assert events[1].from_status is ReviewStatus.PENDING


def test_sqlite_review_repository_cas_projection_conflict(db_path: Path) -> None:
    seed_event, seed_projection = build_seed_projection(
        submission_id="sub-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        _seed_submission_row(unit_of_work.connection)
        unit_of_work.review.insert_seed(seed_event, seed_projection)

    stale_projection = ReviewProjection(
        submission_id="sub-1",
        status=ReviewStatus.APPROVED,
        optimistic_version=1,
        latest_sequence=1,
        updated_by="actor-2",
        updated_at=TS1,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        with pytest.raises(ReviewVersionConflict):
            unit_of_work.review.cas_projection(stale_projection, expected_version=1)


@pytest.mark.parametrize(
    ("mutation_sql", "read_method"),
    [
        (
            "UPDATE review_projection_records SET status = 'APPROVED' WHERE submission_id = 'sub-1'",
            "get_projection",
        ),
        (
            "DELETE FROM review_event_records WHERE submission_id = 'sub-1'",
            "list_events",
        ),
    ],
)
def test_sqlite_review_repository_closure_violation_on_read(
    db_path: Path,
    mutation_sql: str,
    read_method: str,
) -> None:
    seed_event, seed_projection = build_seed_projection(
        submission_id="sub-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        _seed_submission_row(unit_of_work.connection)
        unit_of_work.review.insert_seed(seed_event, seed_projection)
        unit_of_work.connection.execute(mutation_sql)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        with pytest.raises(ReviewClosureViolation):
            if read_method == "get_projection":
                unit_of_work.review.get_projection("sub-1")
            else:
                unit_of_work.review.list_events("sub-1")


@pytest.mark.parametrize(
    ("reason", "should_accept"),
    [
        ("汉" * 1365, True),
        ("汉" * 1365 + "a", True),
        ("汉" * 1366, False),
    ],
)
def test_review_event_reason_byte_bound_uses_blob_length(
    db_path: Path,
    reason: str,
    should_accept: bool,
) -> None:
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        _seed_submission_row(unit_of_work.connection)
        if should_accept:
            unit_of_work.connection.execute(
                """
                INSERT INTO review_event_records (
                    submission_id, sequence, event_kind, from_status, to_status,
                    reason, actor_id, occurred_at_us
                ) VALUES ('sub-1', 1, 'APPROVED', 'PENDING', 'APPROVED', ?, 'actor-1', 1)
                """,
                (reason,),
            )
        else:
            with pytest.raises(sqlite3.IntegrityError):
                unit_of_work.connection.execute(
                    """
                    INSERT INTO review_event_records (
                        submission_id, sequence, event_kind, from_status, to_status,
                        reason, actor_id, occurred_at_us
                    ) VALUES ('sub-1', 1, 'APPROVED', 'PENDING', 'APPROVED', ?, 'actor-1', 1)
                    """,
                    (reason,),
                )


def test_sqlite_review_repository_read_fails_when_projection_missing_but_events_exist(
    db_path: Path,
) -> None:
    seed_event, seed_projection = build_seed_projection(
        submission_id="sub-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        _seed_submission_row(unit_of_work.connection)
        unit_of_work.review.insert_seed(seed_event, seed_projection)
        unit_of_work.connection.execute(
            "DELETE FROM review_projection_records WHERE submission_id = ?",
            ("sub-1",),
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        with pytest.raises(ReviewClosureViolation, match="review projection is missing"):
            unit_of_work.review.get_projection("sub-1")
        with pytest.raises(ReviewClosureViolation, match="review projection is missing"):
            unit_of_work.review.list_events("sub-1")


def test_sqlite_review_repository_maps_empty_reason_to_closure_violation(
    db_path: Path,
) -> None:
    seed_event, seed_projection = build_seed_projection(
        submission_id="sub-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        _seed_submission_row(unit_of_work.connection)
        unit_of_work.review.insert_seed(seed_event, seed_projection)
        unit_of_work.connection.execute(
            """
            UPDATE review_event_records
            SET reason = ''
            WHERE submission_id = 'sub-1' AND sequence = 0
            """
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        with pytest.raises(ReviewClosureViolation, match="reason exceeds bounded size"):
            unit_of_work.review.get_projection("sub-1")
        with pytest.raises(ReviewClosureViolation, match="reason exceeds bounded size"):
            unit_of_work.review.list_events("sub-1")


def test_sqlite_review_repository_maps_invalid_transition_chain_to_closure_violation(
    db_path: Path,
) -> None:
    seed_event, seed_projection = build_seed_projection(
        submission_id="sub-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        _seed_submission_row(unit_of_work.connection)
        unit_of_work.review.insert_seed(seed_event, seed_projection)
        seed_us = unit_of_work.connection.execute(
            """
            SELECT occurred_at_us
            FROM review_event_records
            WHERE submission_id = 'sub-1' AND sequence = 0
            """
        ).fetchone()[0]
        unit_of_work.connection.execute(
            """
            INSERT INTO review_event_records (
                submission_id, sequence, event_kind, from_status, to_status,
                reason, actor_id, occurred_at_us
            ) VALUES ('sub-1', 1, 'APPROVED', 'REJECTED', 'APPROVED', NULL, 'actor-1', ?)
            """,
            (seed_us + 1,),
        )
        unit_of_work.connection.execute(
            """
            UPDATE review_projection_records
            SET status = 'APPROVED', optimistic_version = 1, latest_sequence = 1,
                updated_by = 'actor-1', updated_at_us = ?
            WHERE submission_id = 'sub-1'
            """,
            (seed_us + 1,),
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        with pytest.raises(
            ReviewClosureViolation,
            match="review event from_status does not match previous to_status",
        ):
            unit_of_work.review.get_projection("sub-1")


def test_sqlite_review_repository_cas_projection_missing_row(db_path: Path) -> None:
    stale_projection = ReviewProjection(
        submission_id="sub-1",
        status=ReviewStatus.PENDING,
        optimistic_version=0,
        latest_sequence=0,
        updated_by="actor-1",
        updated_at=TS0,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        _seed_submission_row(unit_of_work.connection)
        with pytest.raises(ReviewClosureViolation, match="review projection is missing"):
            unit_of_work.review.cas_projection(stale_projection, expected_version=0)


def test_sqlite_review_repository_append_rejects_empty_stream(db_path: Path) -> None:
    approve_event = ReviewEvent(
        submission_id="sub-1",
        sequence=1,
        event_kind=ReviewEventKind.APPROVED,
        from_status=ReviewStatus.PENDING,
        to_status=ReviewStatus.APPROVED,
        reason=None,
        actor_id="reviewer-1",
        occurred_at=TS1,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        _seed_submission_row(unit_of_work.connection)
        with pytest.raises(ReviewClosureViolation, match="no seed"):
            unit_of_work.review.append_event(approve_event)
        assert unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_event_records WHERE submission_id = ?",
            ("sub-1",),
        ).fetchone()[0] == 0


def test_sqlite_review_repository_append_rejects_sequence_gap(db_path: Path) -> None:
    seed_event, seed_projection = build_seed_projection(
        submission_id="sub-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    gap_event = ReviewEvent(
        submission_id="sub-1",
        sequence=5,
        event_kind=ReviewEventKind.APPROVED,
        from_status=ReviewStatus.PENDING,
        to_status=ReviewStatus.APPROVED,
        reason=None,
        actor_id="reviewer-1",
        occurred_at=TS1,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        _seed_submission_row(unit_of_work.connection)
        unit_of_work.review.insert_seed(seed_event, seed_projection)
        with pytest.raises(ReviewClosureViolation, match="not contiguous"):
            unit_of_work.review.append_event(gap_event)
        assert unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_event_records WHERE submission_id = ?",
            ("sub-1",),
        ).fetchone()[0] == 1


def test_sqlite_review_repository_find_idempotency_rejects_seed_binding(db_path: Path) -> None:
    seed_event, seed_projection = build_seed_projection(
        submission_id="sub-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        _seed_submission_row(unit_of_work.connection)
        unit_of_work.review.insert_seed(seed_event, seed_projection)
        unit_of_work.connection.execute(
            """
            INSERT INTO review_idempotency_records (
                business_project_id, idempotency_key, submission_id,
                request_fingerprint, event_sequence
            ) VALUES ('project-1', 'review-key-seed', 'sub-1', 'sha256:fp', 0)
            """
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        with pytest.raises(ReviewClosureViolation, match="seed event"):
            unit_of_work.review.find_idempotency("project-1", "review-key-seed")


def test_sqlite_review_repository_maps_unknown_status_to_closure_violation(
    db_path: Path,
) -> None:
    seed_event, seed_projection = build_seed_projection(
        submission_id="sub-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        _seed_submission_row(unit_of_work.connection)
        unit_of_work.review.insert_seed(seed_event, seed_projection)
        unit_of_work.connection.execute("PRAGMA ignore_check_constraints=ON")
        unit_of_work.connection.execute(
            "UPDATE review_projection_records SET status = 'SUPERSEDED' WHERE submission_id = 'sub-1'"
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        with pytest.raises(ReviewClosureViolation, match="SUPERSEDED"):
            unit_of_work.review.get_projection("sub-1")


def test_sqlite_review_repository_maps_int64_timestamp_to_closure_violation(
    db_path: Path,
) -> None:
    seed_event, seed_projection = build_seed_projection(
        submission_id="sub-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        _seed_submission_row(unit_of_work.connection)
        unit_of_work.review.insert_seed(seed_event, seed_projection)
        unit_of_work.connection.execute(
            """
            UPDATE review_event_records
            SET occurred_at_us = ?
            WHERE submission_id = 'sub-1' AND sequence = 0
            """,
            (9223372036854775807,),
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        with pytest.raises(ReviewClosureViolation, match="out of range"):
            unit_of_work.review.get_projection("sub-1")


def _insert_operation_record(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    created_at_us: int = 1,
) -> None:
    connection.execute(
        """
        INSERT INTO operation_records (
            operation_id, contract_version, optimistic_version, job_kind, job_contract_version,
            job_payload, job_payload_ref, business_refs, artifact_refs, repository_operation_id,
            checkpoint_ref, ready_closure_ref, status, diagnostic, cancel_requested,
            created_at_us, updated_at_us, completed_at_us
        ) VALUES (?, ?, 0, 'backend-vnext/submit', ?, ?, NULL, ?, ?, NULL, NULL, NULL, 'SUCCEEDED', NULL, 0, ?, ?, ?)
        """,
        (
            operation_id,
            OPERATION_RUNTIME_CONTRACT_VERSION,
            SUBMIT_JOB_CONTRACT_VERSION,
            b"{}",
            b"[]",
            b"[]",
            created_at_us,
            created_at_us,
            created_at_us,
        ),
    )


def _seed_submission_row(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO workspace_records (
            workspace_id, owner_actor_id, gateway_device_external_key, business_project_id,
            repository_id, state, generation, optimistic_version, current_upload_revision_id,
            current_preview_result_id, created_at_us, updated_at_us, closed_at_us
        ) VALUES ('ws-1', 'actor-1', 'device-1', 'project-1', 'repo-1', 'OPEN', 1, 0, NULL, NULL, 1, 1, NULL)
        """
    )
    _insert_operation_record(connection, operation_id="op-1")
    connection.execute(
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
            'sa-1', 'ws-1', 1, 'ur-1', 'pr-1', 'repo-1', 'node-1', 'commit-base', 1, 'commit-main',
            'sha256:canonical', 'd-source', 'd-snapshot', ?, ?, ?, 'closure-1', 'd-closure',
            'manifest-1', 'sha256:manifest', NULL, NULL, NULL, NULL, 'main', 'STRUCTURAL',
            'REJECT', 'ADAPTIVE_PATCH', 'accept-key', 'sha256:fp', 'upload-key', 'import-key',
            'op-1', 'FINALIZED', 'sub-1', 1, 'actor-1', 1, 1, 1, NULL, NULL
        )
        """,
        (b"[]", "canonical-closure-1", "sha256:canonical-closure"),
    )
    connection.execute(
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
            'sub-1', 'sa-1', 'ws-1', 1, 'ur-1', 'pr-1', 'repo-1', 'node-1', 'commit-base',
            'commit-new', 'sha256:canonical', ?, 'manifest-1', 'sha256:manifest',
            'sha256:package', 'repo-artifact-1', 'STRUCTURAL', 'STRUCTURAL', 'REJECT', 'main',
            'actor-1', 1
        )
        """,
        (b"[]",),
    )
