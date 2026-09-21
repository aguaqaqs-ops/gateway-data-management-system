"""Baseline authority and v5 migration tests."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway_backend.infrastructure.control_db import migrations
from gateway_backend.infrastructure.control_db.database import (
    connect_control_db,
    initialize_and_verify_control_db,
)
from gateway_backend.application.submission.contracts import SUBMIT_JOB_CONTRACT_VERSION
from gateway_backend.infrastructure.control_db.migrations import (
    WORKSPACE_SCHEMA_COMPONENT,
    WORKSPACE_SCHEMA_VERSION,
    _apply_workspace_v4,
    bootstrap_control_schema,
    bootstrap_workspace_schema,
)
from gateway_backend.infrastructure.control_db.sqlite_baseline import get_current_head_from_connection
from gateway_backend.infrastructure.control_db.sqlite_mapping import seed_provisioned_mappings
from gateway_backend.operations import OPERATION_RUNTIME_CONTRACT_VERSION
from tests.support.baseline_fixtures import apply_baseline_head_state, seed_provisioned_mapping_with_head
from tests.support.workspace_fixtures import make_baseline_head

pytestmark = pytest.mark.unit

MIGRATION_TIME = datetime(2024, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
EXPECTED_MIGRATION_TIME_US = 1_704_164_645_678_901
INITIAL_BASELINE_HEAD = make_baseline_head(version=0, commit_id="commit-base")
BASELINE_HEAD = make_baseline_head(version=3, commit_id="commit-base")


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.row_factory = sqlite3.Row
    return connection


def _bootstrap_to_v4(connection: sqlite3.Connection) -> None:
    bootstrap_control_schema(connection, now=lambda: MIGRATION_TIME)
    connection.execute("BEGIN IMMEDIATE")
    for version, apply in (
        (1, migrations._apply_workspace_v1),
        (2, migrations._apply_workspace_v2),
        (3, migrations._apply_workspace_v3),
        (4, _apply_workspace_v4),
    ):
        apply(connection)
        connection.execute(
            "INSERT INTO control_schema_migrations(component, version, applied_at_us) VALUES (?, ?, ?)",
            (WORKSPACE_SCHEMA_COMPONENT, version, EXPECTED_MIGRATION_TIME_US),
        )
    connection.execute("COMMIT")


def _insert_v4_mapping(
    connection: sqlite3.Connection,
    *,
    device_key: str = "device-1",
    project_id: str = "project-1",
    repository_id: str = "repo-1",
    node_id: str = "node-1",
    commit_id: str = "commit-base",
    head_version: int = 0,
    enabled: int = 1,
) -> None:
    connection.execute(
        """
        INSERT INTO provisioned_scope_mappings (
            gateway_device_external_key, business_project_id, repository_id,
            business_baseline_node_id, business_baseline_commit_id, baseline_head_version, enabled
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (device_key, project_id, repository_id, node_id, commit_id, head_version, enabled),
    )


def test_v5_bootstrap_creates_baseline_tables_and_rebuilds_mapping() -> None:
    connection = _connection()
    bootstrap_control_schema(connection, now=lambda: MIGRATION_TIME)
    bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)

    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {"baseline_node_records", "baseline_head_records"} <= tables

    mapping_columns = [
        row[1] for row in connection.execute("PRAGMA table_info(provisioned_scope_mappings)")
    ]
    assert mapping_columns == [
        "gateway_device_external_key",
        "business_project_id",
        "repository_id",
        "enabled",
    ]

    unique_repo_index = connection.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'provisioned_scope_mappings_one_repository'"
    ).fetchone()[0]
    assert "UNIQUE" in unique_repo_index


def test_v4_mapping_migrates_initial_identity_and_current_head() -> None:
    connection = _connection()
    _bootstrap_to_v4(connection)
    _insert_v4_mapping(connection, head_version=0)

    bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)

    head = get_current_head_from_connection(connection, "repo-1")
    assert head == INITIAL_BASELINE_HEAD
    initial_row = connection.execute(
        """
        SELECT node_id, commit_id, kind
        FROM baseline_node_records
        WHERE repository_id = ? AND kind = 'INITIAL'
        """,
        ("repo-1",),
    ).fetchone()
    assert initial_row is not None
    assert initial_row["node_id"] == "node-1"
    assert initial_row["commit_id"] == "commit-base"
    assert initial_row["kind"] == "INITIAL"


def test_v5_migration_rejects_nonzero_mapping_head_version() -> None:
    connection = _connection()
    _bootstrap_to_v4(connection)
    _insert_v4_mapping(connection, head_version=3)

    with pytest.raises(RuntimeError, match="initial baseline head version 0"):
        bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)

    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert "baseline_node_records" not in tables
    assert connection.execute(
        "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
        (WORKSPACE_SCHEMA_COMPONENT,),
    ).fetchone()[0] == 4


def _insert_v4_preview_with_baseline_binding(
    connection: sqlite3.Connection,
    *,
    node_id: str,
    commit_id: str = "commit-base",
    head_version: int = 0,
) -> None:
    binding = json.dumps(
        {
            "business_baseline_node_id": node_id,
            "business_baseline_commit_id": commit_id,
            "baseline_head_version": head_version,
            "ruleset_version": "ruleset-1",
            "contract_version": "contract-1",
            "provider_versions": {"comparison": "v1"},
            "digests": {
                "source_digest": "d-source",
                "input_digest": "d-input",
                "snapshot_digest": "d-snapshot",
                "comparison_digest": "d-comparison",
                "risk_digest": "d-risk",
                "surface_digest": "d-surface",
                "bundle_digest": "d-bundle",
            },
            "bundle_artifact_id": "bundle-1",
            "ready_closure_artifact_id": "closure-1",
        }
    ).encode("utf-8")
    connection.execute(
        """
        INSERT INTO workspace_records (
            workspace_id, owner_actor_id, gateway_device_external_key, business_project_id,
            repository_id, state, generation, optimistic_version, current_upload_revision_id,
            current_preview_result_id, created_at_us, updated_at_us
        ) VALUES (
            'ws-1', 'actor-1', 'device-1', 'project-1', 'repo-1', 'OPEN', 1, 1, 'ur-1', 'pr-1', 0, 0
        )
        """
    )
    connection.execute(
        """
        INSERT INTO upload_revision_records (
            upload_revision_id, workspace_id, generation, input_completeness,
            source_artifacts, idempotency_key, request_fingerprint, created_by, created_at_us
        ) VALUES (
            'ur-1', 'ws-1', 1, 'MODIFIED_ONLY', ?, 'upload-key', 'fp-upload', 'actor-1', 0
        )
        """,
        (b"{}",),
    )
    connection.execute(
        """
        INSERT INTO preview_result_records (
            preview_result_id, workspace_id, upload_revision_id, generation, repository_id,
            binding, operation_id, created_at_us
        ) VALUES ('pr-1', 'ws-1', 'ur-1', 1, 'repo-1', ?, 'op-preview-1', 0)
        """,
        (binding,),
    )


def _insert_v4_operation_record(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    job_kind: str = "backend-vnext/preview",
    job_contract_version: str = "backend-vnext/preview/v1",
    created_at_us: int = 0,
) -> None:
    connection.execute(
        """
        INSERT INTO operation_records (
            operation_id, contract_version, optimistic_version, job_kind, job_contract_version,
            job_payload, job_payload_ref, business_refs, artifact_refs, repository_operation_id,
            checkpoint_ref, ready_closure_ref, status, diagnostic, cancel_requested,
            created_at_us, updated_at_us, completed_at_us
        ) VALUES (?, ?, 0, ?, ?, ?, NULL, ?, ?, NULL, NULL, NULL, 'SUCCEEDED', NULL, 0, ?, ?, ?)
        """,
        (
            operation_id,
            OPERATION_RUNTIME_CONTRACT_VERSION,
            job_kind,
            job_contract_version,
            b"{}",
            b"[]",
            b"[]",
            created_at_us,
            created_at_us,
            created_at_us,
        ),
    )


def _insert_v4_preview_idempotency_without_result(
    connection: sqlite3.Connection,
    *,
    node_id: str,
    head_version: int = 0,
) -> None:
    connection.execute(
        """
        INSERT INTO workspace_records (
            workspace_id, owner_actor_id, gateway_device_external_key, business_project_id,
            repository_id, state, generation, optimistic_version, current_upload_revision_id,
            current_preview_result_id, created_at_us, updated_at_us
        ) VALUES (
            'ws-1', 'actor-1', 'device-1', 'project-1', 'repo-1', 'OPEN', 1, 1, 'ur-1', NULL, 0, 0
        )
        """
    )
    connection.execute(
        """
        INSERT INTO upload_revision_records (
            upload_revision_id, workspace_id, generation, input_completeness,
            source_artifacts, idempotency_key, request_fingerprint, created_by, created_at_us
        ) VALUES (
            'ur-1', 'ws-1', 1, 'MODIFIED_ONLY', ?, 'upload-key', 'fp-upload', 'actor-1', 0
        )
        """,
        (b"{}",),
    )
    _insert_v4_operation_record(connection, operation_id="op-preview-1")
    connection.execute(
        """
        INSERT INTO preview_idempotency_records (
            workspace_id, idempotency_key, request_fingerprint, operation_id,
            upload_revision_id, generation, business_baseline_node_id, baseline_head_version
        ) VALUES ('ws-1', 'preview-key', 'fp-preview', 'op-preview-1', 'ur-1', 1, ?, ?)
        """,
        (node_id, head_version),
    )


def _insert_v4_submission_history(
    connection: sqlite3.Connection,
    *,
    node_id: str = "node-1",
    commit_id: str = "commit-base",
    head_version: int = 0,
    submission_id: str = "sub-1",
    submit_attempt_id: str = "attempt-1",
) -> None:
    connection.execute(
        """
        INSERT INTO workspace_records (
            workspace_id, owner_actor_id, gateway_device_external_key, business_project_id,
            repository_id, state, generation, optimistic_version, current_upload_revision_id,
            current_preview_result_id, created_at_us, updated_at_us, closed_at_us
        ) VALUES (?, 'actor-1', 'device-1', 'project-1', 'repo-1', 'OPEN', 1, 0, NULL, NULL, 0, 0, NULL)
        """,
        (f"ws-{submission_id}",),
    )
    _insert_v4_operation_record(
        connection,
        operation_id=f"op-{submit_attempt_id}",
        job_kind="backend-vnext/submit",
        job_contract_version=SUBMIT_JOB_CONTRACT_VERSION,
    )
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
            ?, ?, 1, 'ur-1', 'pr-1', 'repo-1', ?, ?, ?, 'commit-main',
            'sha256:canonical', 'd-source', 'd-snapshot', ?, ?, 'closure-1', 'd-closure',
            'manifest-1', 'sha256:manifest', NULL, NULL, NULL, NULL, 'main', 'STRUCTURAL',
            'REJECT', 'REBUILD_ALWAYS', 'accept-key', 'sha256:fp', 'upload-key', 'import-key',
            ?, 'FINALIZED', ?, 1, 'actor-1', 0, 0, 0, NULL, NULL
        )
        """,
        (
            submit_attempt_id,
            f"ws-{submission_id}",
            node_id,
            commit_id,
            head_version,
            b"[]",
            b"[]",
            f"op-{submit_attempt_id}",
            submission_id,
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
            ?, ?, ?, 1, 'ur-1', 'pr-1', 'repo-1', ?, ?, 'commit-new',
            'sha256:canonical', ?, 'manifest-1', 'sha256:manifest', 'sha256:package',
            'repo-artifact-1', 'STRUCTURAL', 'STRUCTURAL', 'REJECT', 'main', 'actor-1', 0
        )
        """,
        (submission_id, submit_attempt_id, f"ws-{submission_id}", node_id, commit_id, b"[]"),
    )
    connection.execute(
        """
        INSERT INTO review_projection_records (
            submission_id, status, optimistic_version, latest_sequence,
            updated_by, updated_at_us
        ) VALUES (?, 'PENDING', 0, 0, 'actor-1', 0)
        """,
        (submission_id,),
    )


def test_v5_migration_rejects_unexplainable_preview_baseline_reference() -> None:
    connection = _connection()
    _bootstrap_to_v4(connection)
    _insert_v4_mapping(connection, head_version=0)
    _insert_v4_preview_with_baseline_binding(connection, node_id="unknown-base")

    with pytest.raises(RuntimeError, match="unexplainable baseline node reference"):
        bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)

    assert connection.execute(
        "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
        (WORKSPACE_SCHEMA_COMPONENT,),
    ).fetchone()[0] == 4


def test_v5_migration_rejects_unexplainable_preview_idempotency_without_result() -> None:
    connection = _connection()
    _bootstrap_to_v4(connection)
    _insert_v4_mapping(connection, head_version=0)
    _insert_v4_preview_idempotency_without_result(connection, node_id="unknown-base")

    with pytest.raises(RuntimeError, match="unexplainable baseline node reference"):
        bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)

    assert connection.execute(
        "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
        (WORKSPACE_SCHEMA_COMPONENT,),
    ).fetchone()[0] == 4


def test_v5_migration_rejects_unexplainable_submission_baseline_reference() -> None:
    connection = _connection()
    _bootstrap_to_v4(connection)
    _insert_v4_mapping(connection, head_version=0)
    _insert_v4_submission_history(connection, node_id="unknown-base")

    with pytest.raises(RuntimeError, match="unexplainable baseline node reference"):
        bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)

    assert connection.execute(
        "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
        (WORKSPACE_SCHEMA_COMPONENT,),
    ).fetchone()[0] == 4


def test_v5_migration_preserves_submit_review_history_on_file_db(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    connection = connect_control_db(db_path)
    _bootstrap_to_v4(connection)
    _insert_v4_mapping(connection, head_version=0)
    _insert_v4_submission_history(connection)
    connection.close()

    reopened = connect_control_db(db_path)
    try:
        bootstrap_workspace_schema(reopened, now=lambda: MIGRATION_TIME)
        assert reopened.execute(
            "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
            (WORKSPACE_SCHEMA_COMPONENT,),
        ).fetchone()[0] == WORKSPACE_SCHEMA_VERSION
        assert reopened.execute("SELECT COUNT(*) FROM submission_records").fetchone()[0] == 1
        assert reopened.execute("SELECT COUNT(*) FROM review_projection_records").fetchone()[0] == 1
        head = get_current_head_from_connection(reopened, "repo-1")
        assert head == INITIAL_BASELINE_HEAD
    finally:
        reopened.close()


def test_v5_baseline_head_rejects_cross_repository_node_reference() -> None:
    connection = _connection()
    _bootstrap_to_v4(connection)
    _insert_v4_mapping(
        connection,
        device_key="device-1",
        project_id="project-1",
        repository_id="repo-1",
        node_id="node-1",
        head_version=0,
    )
    _insert_v4_mapping(
        connection,
        device_key="device-2",
        project_id="project-2",
        repository_id="repo-2",
        node_id="node-2",
        head_version=0,
    )

    bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)

    connection.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            UPDATE baseline_head_records
            SET node_id = 'node-2'
            WHERE repository_id = 'repo-1'
            """
        )
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_v5_migration_rejects_cross_scope_repository_sharing() -> None:
    connection = _connection()
    _bootstrap_to_v4(connection)
    _insert_v4_mapping(connection, device_key="device-1", project_id="project-1", repository_id="repo-shared")
    _insert_v4_mapping(
        connection,
        device_key="device-2",
        project_id="project-2",
        repository_id="repo-shared",
        enabled=0,
    )

    with pytest.raises(RuntimeError, match="cross-scope repository sharing"):
        bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)


def test_failed_v5_migration_rolls_back_to_v4(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _connection()
    _bootstrap_to_v4(connection)
    _insert_v4_mapping(connection)

    def fail(_connection: sqlite3.Connection, _migration_rows: tuple[dict[str, object], ...]) -> None:
        _connection.execute("CREATE TABLE baseline_probe(value INTEGER NOT NULL)")
        raise RuntimeError("synthetic baseline migration failure")

    monkeypatch.setattr(migrations, "_migrate_v5_baseline_authority", fail)
    with pytest.raises(RuntimeError, match="synthetic baseline migration failure"):
        bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)

    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert "baseline_probe" not in tables
    assert "baseline_node_records" not in tables
    assert connection.execute(
        "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
        (WORKSPACE_SCHEMA_COMPONENT,),
    ).fetchone()[0] == 4
    mapping_columns = [
        row[1] for row in connection.execute("PRAGMA table_info(provisioned_scope_mappings)")
    ]
    assert "business_baseline_node_id" in mapping_columns


def test_seed_restart_does_not_regress_advanced_head(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_and_verify_control_db(db_path, now=lambda: MIGRATION_TIME)
    seed_provisioned_mapping_with_head(
        db_path,
        repository_id="repo-1",
        baseline_head=BASELINE_HEAD,
    )
    advanced = make_baseline_head(version=7, commit_id=BASELINE_HEAD.business_baseline_commit_id)
    apply_baseline_head_state(db_path, repository_id="repo-1", baseline_head=advanced)

    mapping_file = tmp_path / "provisioned-mapping.json"
    mapping_file.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "gateway_device_external_key": "device-1",
                        "business_project_id": "project-1",
                        "repository_id": "repo-1",
                        "business_baseline_node_id": BASELINE_HEAD.business_baseline_node_id,
                        "business_baseline_commit_id": BASELINE_HEAD.business_baseline_commit_id,
                        "baseline_head_version": 0,
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    seed_provisioned_mappings(db_path, mapping_file)

    connection = connect_control_db(db_path)
    try:
        head = get_current_head_from_connection(connection, "repo-1")
        assert head.baseline_head_version == 7
        assert head.business_baseline_commit_id == BASELINE_HEAD.business_baseline_commit_id
    finally:
        connection.close()


def test_seed_rejects_cross_scope_repository_reassignment(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_and_verify_control_db(db_path, now=lambda: MIGRATION_TIME)
    seed_provisioned_mapping_with_head(
        db_path,
        device_key="device-1",
        project_id="project-1",
        repository_id="repo-1",
        baseline_head=make_baseline_head(version=0, commit_id="commit-1"),
    )

    mapping_file = tmp_path / "reassign.json"
    mapping_file.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "gateway_device_external_key": "device-2",
                        "business_project_id": "project-2",
                        "repository_id": "repo-1",
                        "business_baseline_node_id": "node-1",
                        "business_baseline_commit_id": "commit-1",
                        "baseline_head_version": 0,
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="already owned by a different scope"):
        seed_provisioned_mappings(db_path, mapping_file)


def test_workspace_v5_creates_archive_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_and_verify_control_db(db_path, now=lambda: MIGRATION_TIME)
    connection = connect_control_db(db_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name LIKE 'archive_%'
                ORDER BY name
                """
            ).fetchall()
        }
    finally:
        connection.close()
    assert tables == {
        "archive_anomaly_resolution_events",
        "archive_confirmation_events",
        "archive_disposition_records",
        "archive_plan_records",
        "archive_result_records",
    }


def test_workspace_v5_creates_archive_disposition_selected_unique_index(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_and_verify_control_db(db_path, now=lambda: MIGRATION_TIME)
    connection = connect_control_db(db_path)
    try:
        index_row = connection.execute(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'index'
              AND name = 'archive_disposition_records_one_selected_per_result'
            """
        ).fetchone()
    finally:
        connection.close()
    assert index_row is not None
    assert "WHERE disposition = 'ARCHIVED_BASELINE'" in index_row["sql"]
