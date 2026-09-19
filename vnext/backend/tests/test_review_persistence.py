"""Review workspace schema v4 migration and SQLite persistence tests."""

from __future__ import annotations

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
from gateway_backend.infrastructure.control_db import migrations
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from gateway_backend.infrastructure.control_db.migrations import (
    OPERATIONS_SCHEMA_COMPONENT,
    WORKSPACE_SCHEMA_COMPONENT,
    WORKSPACE_SCHEMA_VERSION,
    _apply_workspace_v2,
    _apply_workspace_v3,
    bootstrap_control_schema,
    bootstrap_workspace_schema,
)
from gateway_backend.application.submission.contracts import SUBMIT_JOB_CONTRACT_VERSION
from gateway_backend.operations import OPERATION_RUNTIME_CONTRACT_VERSION, UnsupportedSchemaVersion

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
TS1 = datetime(2024, 6, 1, 12, 30, 0, tzinfo=UTC)


def _connection() -> sqlite3.Connection:
    return sqlite3.connect(":memory:", isolation_level=None)


def _migration_time() -> datetime:
    return datetime(2024, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)


def _seed_workspace_v3(connection: sqlite3.Connection) -> None:
    migration_time = _migration_time()
    bootstrap_control_schema(connection, now=lambda: migration_time)
    connection.execute("BEGIN IMMEDIATE")
    migrations._apply_workspace_v1(connection)
    connection.execute(
        "INSERT INTO control_schema_migrations(component, version, applied_at_us) VALUES (?, ?, ?)",
        (WORKSPACE_SCHEMA_COMPONENT, 1, 1_704_164_645_678_901),
    )
    connection.execute("COMMIT")
    _apply_workspace_v2(connection)
    connection.execute(
        "INSERT INTO control_schema_migrations(component, version, applied_at_us) VALUES (?, ?, ?)",
        (WORKSPACE_SCHEMA_COMPONENT, 2, 1_704_164_645_678_901),
    )
    _apply_workspace_v3(connection)
    connection.execute(
        "INSERT INTO control_schema_migrations(component, version, applied_at_us) VALUES (?, ?, ?)",
        (WORKSPACE_SCHEMA_COMPONENT, 3, 1_704_164_645_678_901),
    )


def _insert_minimal_submission(
    connection: sqlite3.Connection,
    *,
    submission_id: str,
    submit_attempt_id: str,
    created_by: str = "actor-1",
    created_at_us: int = 1_718_000_000_000_000,
) -> None:
    connection.execute(
        """
        INSERT INTO workspace_records (
            workspace_id, owner_actor_id, gateway_device_external_key, business_project_id,
            repository_id, state, generation, optimistic_version, current_upload_revision_id,
            current_preview_result_id, created_at_us, updated_at_us, closed_at_us
        ) VALUES (?, ?, ?, ?, ?, 'OPEN', 1, 0, NULL, NULL, ?, ?, NULL)
        """,
        (f"ws-{submission_id}", created_by, "device-1", "project-1", "repo-1", 1, 1),
    )
    _insert_operation_record(connection, operation_id=f"op-{submit_attempt_id}", created_at_us=created_at_us)
    connection.execute(
        """
        INSERT INTO submit_attempt_records (
            submit_attempt_id, workspace_id, workspace_generation, upload_revision_id,
            preview_result_id, repository_id, business_baseline_node_id,
            business_baseline_commit_id, baseline_head_version, repository_expected_commit_id,
            canonical_business_digest, source_digest, snapshot_digest, source_artifact_refs,
            snapshot_table_artifact_refs, preview_ready_closure_ref, preview_ready_closure_digest,
            canonicalization_manifest_ref, canonicalization_manifest_digest,
            repository_import_artifact_ref, repository_artifact_ref, repository_operation_id,
            repository_operation_evidence, requested_target_ref, requested_verification_policy,
            requested_unknown_type_policy, builder_mutation_policy, accept_idempotency_key,
            accept_request_fingerprint, repository_upload_idempotency_key,
            repository_import_idempotency_key, operation_id, state, submission_id,
            optimistic_version, created_by, created_at_us, effect_pending_at_us,
            finalized_at_us, aborted_at_us, abort_code
        ) VALUES (
            ?, ?, 1, 'ur-1', 'pr-1', 'repo-1', 'node-1', 'commit-base', 1, 'commit-main',
            'sha256:canonical', 'd-source', 'd-snapshot', ?, ?, 'closure-1', 'd-closure',
            'manifest-1', 'sha256:manifest', NULL, NULL, NULL, NULL, 'main', 'STRUCTURAL',
            'REJECT', 'REBUILD_ALWAYS', 'accept-key', 'sha256:fp', 'upload-key', 'import-key',
            ?, 'FINALIZED', ?, 1, ?, ?, ?, ?, NULL, NULL
        )
        """,
        (
            submit_attempt_id,
            f"ws-{submission_id}",
            b"[]",
            b"[]",
            f"op-{submit_attempt_id}",
            submission_id,
            created_by,
            created_at_us,
            created_at_us,
            created_at_us,
        ),
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
            ?, ?, ?, 1, 'ur-1', 'pr-1', 'repo-1', 'node-1', 'commit-base', 'commit-new',
            'sha256:canonical', ?, 'manifest-1', 'sha256:manifest', 'sha256:package',
            'repo-artifact-1', 'STRUCTURAL', 'STRUCTURAL', 'REJECT', 'main', ?, ?
        )
        """,
        (submission_id, submit_attempt_id, f"ws-{submission_id}", b"[]", created_by, created_at_us),
    )


def test_workspace_v4_bootstrap_creates_review_tables() -> None:
    connection = _connection()
    bootstrap_control_schema(connection, now=_migration_time)
    bootstrap_workspace_schema(connection, now=_migration_time)

    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {
        "review_event_records",
        "review_projection_records",
        "review_idempotency_records",
    } <= tables
    ledger_rows = connection.execute(
        "SELECT component, version FROM control_schema_migrations ORDER BY component, version"
    ).fetchall()
    assert ledger_rows == [
        (OPERATIONS_SCHEMA_COMPONENT, 1),
        (WORKSPACE_SCHEMA_COMPONENT, 1),
        (WORKSPACE_SCHEMA_COMPONENT, 2),
        (WORKSPACE_SCHEMA_COMPONENT, 3),
        (WORKSPACE_SCHEMA_COMPONENT, WORKSPACE_SCHEMA_VERSION),
    ]


def test_repeat_workspace_v4_bootstrap_is_noop() -> None:
    connection = _connection()
    bootstrap_control_schema(connection, now=_migration_time)
    bootstrap_workspace_schema(connection, now=_migration_time)
    bootstrap_workspace_schema(connection, now=_migration_time)
    assert connection.execute(
        "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
        (WORKSPACE_SCHEMA_COMPONENT,),
    ).fetchone()[0] == WORKSPACE_SCHEMA_VERSION


def test_failed_workspace_v4_migration_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _connection()
    _seed_workspace_v3(connection)

    def fail(_connection: sqlite3.Connection) -> None:
        _connection.execute("CREATE TABLE review_probe(value INTEGER NOT NULL)")
        raise RuntimeError("synthetic review migration failure")

    monkeypatch.setattr(migrations, "_apply_workspace_v4", fail)
    with pytest.raises(RuntimeError, match="synthetic review migration failure"):
        bootstrap_workspace_schema(connection, now=_migration_time)

    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert "review_probe" not in tables
    assert "review_event_records" not in tables
    assert connection.execute(
        "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
        (WORKSPACE_SCHEMA_COMPONENT,),
    ).fetchone()[0] == 3


def test_newer_workspace_v4_schema_version_is_rejected() -> None:
    connection = _connection()
    bootstrap_control_schema(connection, now=_migration_time)
    bootstrap_workspace_schema(connection, now=_migration_time)
    connection.execute(
        "INSERT INTO control_schema_migrations(component, version, applied_at_us) VALUES (?, ?, ?)",
        (WORKSPACE_SCHEMA_COMPONENT, WORKSPACE_SCHEMA_VERSION + 1, 1_704_164_645_678_901),
    )
    with pytest.raises(UnsupportedSchemaVersion):
        bootstrap_workspace_schema(connection, now=_migration_time)


def test_historical_workspace_v3_reopens_to_v4() -> None:
    connection = _connection()
    _seed_workspace_v3(connection)
    bootstrap_workspace_schema(connection, now=_migration_time)
    assert connection.execute(
        "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
        (WORKSPACE_SCHEMA_COMPONENT,),
    ).fetchone()[0] == WORKSPACE_SCHEMA_VERSION
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'review_event_records'"
    ).fetchone() is not None


def test_workspace_v4_backfill_creates_seed_per_submission() -> None:
    connection = _connection()
    _seed_workspace_v3(connection)
    _insert_minimal_submission(connection, submission_id="sub-1", submit_attempt_id="sa-1")
    _insert_minimal_submission(
        connection,
        submission_id="sub-2",
        submit_attempt_id="sa-2",
        created_by="actor-2",
        created_at_us=1_718_000_000_000_001,
    )
    submission_rows = connection.execute("SELECT * FROM submission_records ORDER BY submission_id").fetchall()
    connection.execute(
        """
        INSERT INTO workspace_submit_occupancy_records (
            workspace_id, active_submit_attempt_id, active_submission_id
        ) VALUES ('ws-sub-1', NULL, 'sub-1')
        """
    )
    connection.execute(
        """
        INSERT INTO workspace_submit_occupancy_records (
            workspace_id, active_submit_attempt_id, active_submission_id
        ) VALUES ('ws-sub-2', NULL, 'sub-2')
        """
    )
    occupancy_rows = connection.execute(
        "SELECT * FROM workspace_submit_occupancy_records ORDER BY workspace_id"
    ).fetchall()
    bootstrap_workspace_schema(connection, now=_migration_time)

    assert connection.execute("SELECT COUNT(*) FROM review_event_records").fetchone()[0] == 2
    assert connection.execute("SELECT COUNT(*) FROM review_projection_records").fetchone()[0] == 2
    assert connection.execute("SELECT COUNT(*) FROM review_idempotency_records").fetchone()[0] == 0
    event = connection.execute(
        """
        SELECT sequence, event_kind, from_status, to_status, actor_id, occurred_at_us
        FROM review_event_records WHERE submission_id = 'sub-1'
        """
    ).fetchone()
    assert event == (0, "SUBMISSION_FINALIZED", None, "PENDING", "actor-1", 1_718_000_000_000_000)
    projection = connection.execute(
        """
        SELECT status, optimistic_version, latest_sequence, updated_by, updated_at_us
        FROM review_projection_records WHERE submission_id = 'sub-2'
        """
    ).fetchone()
    assert projection == ("PENDING", 0, 0, "actor-2", 1_718_000_000_000_001)
    assert connection.execute("SELECT * FROM submission_records ORDER BY submission_id").fetchall() == submission_rows
    assert connection.execute(
        "SELECT * FROM workspace_submit_occupancy_records ORDER BY workspace_id"
    ).fetchall() == occupancy_rows


def test_review_migration_enums_match_domain_literals() -> None:
    migration_statuses = {item.strip("'") for item in migrations._REVIEW_STATUSES}
    migration_kinds = {item.strip("'") for item in migrations._REVIEW_EVENT_KINDS}
    assert migration_statuses == {status.value for status in ReviewStatus}
    assert migration_kinds == {kind.value for kind in ReviewEventKind}


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
                snapshot_table_artifact_refs, preview_ready_closure_ref, preview_ready_closure_digest,
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
                'sha256:canonical', 'd-source', 'd-snapshot', ?, ?, 'closure-1', 'd-closure',
                'manifest-1', 'sha256:manifest', NULL, NULL, NULL, NULL, 'main', 'STRUCTURAL',
                'REJECT', 'REBUILD_ALWAYS', 'accept-key', 'sha256:fp', 'upload-key', 'import-key',
                'op-1', 'FINALIZED', 'sub-1', 1, 'actor-1', 1, 1, 1, NULL, NULL
            )
            """,
            (b"[]", b"[]"),
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
            snapshot_table_artifact_refs, preview_ready_closure_ref, preview_ready_closure_digest,
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
            'sha256:canonical', 'd-source', 'd-snapshot', ?, ?, 'closure-1', 'd-closure',
            'manifest-1', 'sha256:manifest', NULL, NULL, NULL, NULL, 'main', 'STRUCTURAL',
            'REJECT', 'REBUILD_ALWAYS', 'accept-key', 'sha256:fp', 'upload-key', 'import-key',
            'op-1', 'FINALIZED', 'sub-1', 1, 'actor-1', 1, 1, 1, NULL, NULL
        )
        """,
        (b"[]", b"[]"),
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
