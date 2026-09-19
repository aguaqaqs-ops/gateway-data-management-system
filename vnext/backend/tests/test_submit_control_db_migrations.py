"""Submit workspace schema v3 migration review tests."""

from __future__ import annotations

import sqlite3

import pytest

from gateway_backend.infrastructure.control_db import migrations
from gateway_backend.infrastructure.control_db.migrations import (
    OPERATIONS_SCHEMA_COMPONENT,
    WORKSPACE_SCHEMA_COMPONENT,
    WORKSPACE_SCHEMA_VERSION,
    _apply_workspace_v2,
    bootstrap_control_schema,
    bootstrap_workspace_schema,
)
from gateway_backend.operations import UnsupportedSchemaVersion

pytestmark = pytest.mark.unit


def _connection() -> sqlite3.Connection:
    return sqlite3.connect(":memory:", isolation_level=None)


def test_workspace_v3_bootstrap_creates_submit_tables() -> None:
    from datetime import UTC, datetime

    migration_time = datetime(2024, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
    connection = _connection()
    bootstrap_control_schema(connection, now=lambda: migration_time)
    bootstrap_workspace_schema(connection, now=lambda: migration_time)

    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {
        "submit_attempt_records",
        "submit_idempotency_records",
        "submission_records",
        "workspace_submit_occupancy_records",
        "repository_submit_occupancy_records",
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

    occupancy_columns = [
        row[1] for row in connection.execute("PRAGMA table_info(workspace_submit_occupancy_records)")
    ]
    assert occupancy_columns == [
        "workspace_id",
        "active_submit_attempt_id",
        "active_submission_id",
    ]

    attempt_fk = connection.execute(
        "PRAGMA foreign_key_list(submit_attempt_records)"
    ).fetchall()
    assert {row[2] for row in attempt_fk} >= {"workspace_records", "operation_records"}


def test_repeat_workspace_v3_bootstrap_is_noop() -> None:
    from datetime import UTC, datetime

    migration_time = datetime(2024, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
    connection = _connection()
    bootstrap_control_schema(connection, now=lambda: migration_time)
    bootstrap_workspace_schema(connection, now=lambda: migration_time)
    bootstrap_workspace_schema(connection, now=lambda: migration_time)
    assert connection.execute(
        "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
        (WORKSPACE_SCHEMA_COMPONENT,),
    ).fetchone()[0] == WORKSPACE_SCHEMA_VERSION


def test_failed_workspace_v3_migration_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import UTC, datetime

    migration_time = datetime(2024, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
    connection = _connection()
    bootstrap_control_schema(connection, now=lambda: migration_time)
    connection.execute("BEGIN IMMEDIATE")
    migrations._apply_workspace_v1(connection)
    connection.execute(
        "INSERT INTO control_schema_migrations(component, version, applied_at_us) VALUES (?, ?, ?)",
        (WORKSPACE_SCHEMA_COMPONENT, 1, 1_704_164_645_678_901),
    )
    connection.execute("COMMIT")
    migrations._apply_workspace_v2(connection)
    connection.execute(
        "INSERT INTO control_schema_migrations(component, version, applied_at_us) VALUES (?, ?, ?)",
        (WORKSPACE_SCHEMA_COMPONENT, 2, 1_704_164_645_678_901),
    )

    def fail(_connection: sqlite3.Connection) -> None:
        _connection.execute("CREATE TABLE submit_probe(value INTEGER NOT NULL)")
        raise RuntimeError("synthetic submit migration failure")

    monkeypatch.setattr(migrations, "_apply_workspace_v3", fail)
    with pytest.raises(RuntimeError, match="synthetic submit migration failure"):
        bootstrap_workspace_schema(connection, now=lambda: migration_time)

    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert "submit_probe" not in tables
    assert connection.execute(
        "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
        (WORKSPACE_SCHEMA_COMPONENT,),
    ).fetchone()[0] == 2


def test_newer_workspace_v3_schema_version_is_rejected() -> None:
    from datetime import UTC, datetime

    migration_time = datetime(2024, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
    connection = _connection()
    bootstrap_control_schema(connection, now=lambda: migration_time)
    bootstrap_workspace_schema(connection, now=lambda: migration_time)
    connection.execute(
        "INSERT INTO control_schema_migrations(component, version, applied_at_us) VALUES (?, ?, ?)",
        (WORKSPACE_SCHEMA_COMPONENT, WORKSPACE_SCHEMA_VERSION + 1, 1_704_164_645_678_901),
    )
    with pytest.raises(UnsupportedSchemaVersion):
        bootstrap_workspace_schema(connection, now=lambda: migration_time)


def test_historical_workspace_v2_reopens_to_v3() -> None:
    from datetime import UTC, datetime

    migration_time = datetime(2024, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
    connection = _connection()
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

    bootstrap_workspace_schema(connection, now=lambda: migration_time)
    assert connection.execute(
        "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
        (WORKSPACE_SCHEMA_COMPONENT,),
    ).fetchone()[0] == WORKSPACE_SCHEMA_VERSION
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'submit_attempt_records'"
    ).fetchone() is not None


def _seed_workspace_v2(connection: sqlite3.Connection, *, migration_time_us: int) -> None:
    from datetime import UTC, datetime

    migration_time = datetime(2024, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
    bootstrap_control_schema(connection, now=lambda: migration_time)
    connection.execute("BEGIN IMMEDIATE")
    migrations._apply_workspace_v1(connection)
    connection.execute(
        "INSERT INTO control_schema_migrations(component, version, applied_at_us) VALUES (?, ?, ?)",
        (WORKSPACE_SCHEMA_COMPONENT, 1, migration_time_us),
    )
    connection.execute("COMMIT")
    _apply_workspace_v2(connection)
    connection.execute(
        "INSERT INTO control_schema_migrations(component, version, applied_at_us) VALUES (?, ?, ?)",
        (WORKSPACE_SCHEMA_COMPONENT, 2, migration_time_us),
    )


def test_corrupted_workspace_v2_foreign_keys_reject_v3_upgrade() -> None:
    from datetime import UTC, datetime

    migration_time = datetime(2024, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
    connection = _connection()
    _seed_workspace_v2(connection, migration_time_us=1_704_164_645_678_901)
    connection.execute(
        """
        INSERT INTO workspace_records (
            workspace_id, owner_actor_id, gateway_device_external_key, business_project_id,
            repository_id, state, generation, optimistic_version, current_upload_revision_id,
            current_preview_result_id, created_at_us, updated_at_us, closed_at_us
        ) VALUES (?, ?, ?, ?, ?, 'OPEN', 1, 0, NULL, NULL, 1, 1, NULL)
        """,
        ("ws-1", "actor-1", "device-1", "project-1", "repo-1"),
    )
    connection.execute(
        """
        INSERT INTO upload_revision_records (
            upload_revision_id, workspace_id, generation, input_completeness, source_artifacts,
            idempotency_key, request_fingerprint, created_by, created_at_us
        ) VALUES (?, ?, 1, 'FULL', ?, ?, ?, ?, 1)
        """,
        ("ur-1", "ws-1", b"[]", "upload-key-1", "sha256:fp", "actor-1"),
    )
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute("DELETE FROM workspace_records WHERE workspace_id = ?", ("ws-1",))
    connection.execute("PRAGMA foreign_keys=ON")

    with pytest.raises(RuntimeError, match="foreign key check failure"):
        bootstrap_workspace_schema(connection, now=lambda: migration_time)

    assert connection.execute(
        "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
        (WORKSPACE_SCHEMA_COMPONENT,),
    ).fetchone()[0] == 2
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'submit_attempt_records'"
    ).fetchone() is None
