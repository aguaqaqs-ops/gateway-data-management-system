"""Workspace schema migration review tests."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from gateway_backend.infrastructure.control_db import migrations
from gateway_backend.infrastructure.control_db.migrations import (
    OPERATIONS_SCHEMA_COMPONENT,
    WORKSPACE_SCHEMA_COMPONENT,
    WORKSPACE_SCHEMA_VERSION,
    bootstrap_control_schema,
    bootstrap_workspace_schema,
)
from gateway_backend.operations import UnsupportedSchemaVersion

pytestmark = pytest.mark.unit

MIGRATION_TIME = datetime(2024, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
EXPECTED_MIGRATION_TIME_US = 1_704_164_645_678_901


def _connection() -> sqlite3.Connection:
    return sqlite3.connect(":memory:", isolation_level=None)


def test_workspace_bootstrap_creates_tables_constraints_and_indexes() -> None:
    connection = _connection()
    bootstrap_control_schema(connection, now=lambda: MIGRATION_TIME)
    bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
    }
    assert {
        "artifact_protection_intents",
        "control_schema_migrations",
        "operation_records",
        "preview_idempotency_records",
        "preview_result_records",
        "step_records",
        "upload_idempotency_records",
        "upload_revision_records",
        "workspace_records",
    } <= tables

    ledger_rows = connection.execute(
        "SELECT component, version FROM control_schema_migrations ORDER BY component, version"
    ).fetchall()
    assert ledger_rows == [
        (OPERATIONS_SCHEMA_COMPONENT, 1),
        (WORKSPACE_SCHEMA_COMPONENT, WORKSPACE_SCHEMA_VERSION),
    ]

    open_index_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'workspace_records_open_exact_scope'"
    ).fetchone()[0]
    assert "state = 'OPEN'" in open_index_sql

    upload_fk = connection.execute("PRAGMA foreign_key_list(upload_revision_records)").fetchone()
    assert upload_fk[2] == "workspace_records"


def test_repeat_workspace_bootstrap_is_noop() -> None:
    connection = _connection()
    bootstrap_control_schema(connection, now=lambda: MIGRATION_TIME)
    bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)
    bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)
    assert connection.execute(
        "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
        (WORKSPACE_SCHEMA_COMPONENT,),
    ).fetchone()[0] == 1


def test_failed_workspace_migration_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _connection()
    bootstrap_control_schema(connection, now=lambda: MIGRATION_TIME)

    def fail(_connection: sqlite3.Connection) -> None:
        _connection.execute("CREATE TABLE workspace_probe(value INTEGER NOT NULL)")
        raise RuntimeError("synthetic workspace migration failure")

    monkeypatch.setattr(migrations, "_apply_workspace_v1", fail)
    with pytest.raises(RuntimeError, match="synthetic workspace migration failure"):
        bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)

    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert "workspace_probe" not in tables
    assert connection.execute(
        "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
        (WORKSPACE_SCHEMA_COMPONENT,),
    ).fetchone()[0] == 0


def test_newer_workspace_schema_version_is_rejected() -> None:
    connection = _connection()
    bootstrap_control_schema(connection, now=lambda: MIGRATION_TIME)
    bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)
    connection.execute(
        "INSERT INTO control_schema_migrations(component, version, applied_at_us) VALUES (?, ?, ?)",
        (WORKSPACE_SCHEMA_COMPONENT, WORKSPACE_SCHEMA_VERSION + 1, EXPECTED_MIGRATION_TIME_US),
    )
    with pytest.raises(UnsupportedSchemaVersion):
        bootstrap_workspace_schema(connection, now=lambda: MIGRATION_TIME)
