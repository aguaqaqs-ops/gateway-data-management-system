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
from gateway_backend.infrastructure.control_db.migrations import (
    WORKSPACE_SCHEMA_COMPONENT,
    _apply_workspace_v4,
    bootstrap_control_schema,
    bootstrap_workspace_schema,
)
from gateway_backend.infrastructure.control_db.sqlite_baseline import get_current_head_from_connection
from gateway_backend.infrastructure.control_db.sqlite_mapping import seed_provisioned_mappings
from tests.support.baseline_fixtures import apply_baseline_head_state, seed_provisioned_mapping_with_head
from tests.support.workspace_fixtures import make_baseline_head

pytestmark = pytest.mark.unit

MIGRATION_TIME = datetime(2024, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
EXPECTED_MIGRATION_TIME_US = 1_704_164_645_678_901
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
    head_version: int = 3,
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
    _insert_v4_mapping(connection)

    bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)

    head = get_current_head_from_connection(connection, "repo-1")
    assert head == BASELINE_HEAD
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
