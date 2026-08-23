"""Control DB schema and migration unit tests."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from gateway_backend.infrastructure.control_db import migrations
from gateway_backend.infrastructure.control_db.migrations import (
    OPERATIONS_SCHEMA_COMPONENT,
    OPERATIONS_SCHEMA_VERSION,
    bootstrap_control_schema,
)
from gateway_backend.operations import UnsupportedSchemaVersion

pytestmark = pytest.mark.unit

MIGRATION_TIME = datetime(2024, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
EXPECTED_MIGRATION_TIME_US = 1_704_164_645_678_901


def _connection() -> sqlite3.Connection:
    return sqlite3.connect(":memory:", isolation_level=None)


def test_fresh_bootstrap_creates_ledger_tables_constraints_and_indexes() -> None:
    connection = _connection()
    bootstrap_control_schema(connection, now=lambda: MIGRATION_TIME)

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
    }
    assert tables == {"control_schema_migrations", "operation_records", "step_records"}

    ledger = connection.execute(
        "SELECT component, version, applied_at_us FROM control_schema_migrations"
    ).fetchone()
    assert ledger == (
        OPERATIONS_SCHEMA_COMPONENT,
        OPERATIONS_SCHEMA_VERSION,
        EXPECTED_MIGRATION_TIME_US,
    )

    operation_columns = [row[1] for row in connection.execute("PRAGMA table_info(operation_records)")]
    assert operation_columns == [
        "operation_id",
        "contract_version",
        "optimistic_version",
        "job_kind",
        "job_contract_version",
        "job_payload",
        "job_payload_ref",
        "business_refs",
        "artifact_refs",
        "repository_operation_id",
        "checkpoint_ref",
        "ready_closure_ref",
        "status",
        "diagnostic",
        "cancel_requested",
        "created_at_us",
        "updated_at_us",
        "completed_at_us",
    ]
    step_columns = [row[1] for row in connection.execute("PRAGMA table_info(step_records)")]
    assert step_columns == [
        "step_id",
        "operation_id",
        "contract_version",
        "optimistic_version",
        "step_name",
        "attempt_count",
        "status",
        "diagnostic",
        "cancel_requested",
        "retry_not_before_us",
        "worker_id",
        "lease_token",
        "lease_expires_at_us",
        "checkpoint_ref",
        "prior_output_refs",
        "created_at_us",
        "updated_at_us",
        "started_at_us",
        "completed_at_us",
        "eligible_at_us",
    ]

    foreign_key = connection.execute("PRAGMA foreign_key_list(step_records)").fetchone()
    assert foreign_key[2:7] == (
        "operation_records",
        "operation_id",
        "operation_id",
        "NO ACTION",
        "RESTRICT",
    )

    index_names = {
        row[1]
        for row in connection.execute("PRAGMA index_list(step_records)")
    }
    assert {
        "sqlite_autoindex_step_records_1",
        "sqlite_autoindex_step_records_2",
        "step_records_one_active_per_operation",
        "step_records_claim_order",
    } <= index_names
    operation_index_names = {
        row[1]
        for row in connection.execute("PRAGMA index_list(operation_records)")
    }
    assert "operation_records_status_readback" in operation_index_names

    ddl = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'step_records'"
    ).fetchone()[0]
    assert "UNIQUE (operation_id, step_name)" in ddl
    assert "FOREIGN KEY (operation_id)" in ddl

    active_index_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'step_records_one_active_per_operation'"
    ).fetchone()[0]
    assert "PENDING" in active_index_sql
    assert "RUNNING" in active_index_sql
    assert "RETRY_WAIT" in active_index_sql
    assert "MANUAL_RECOVERY_REQUIRED" in active_index_sql


def test_repeat_bootstrap_is_noop_and_does_not_resample_clock() -> None:
    connection = _connection()
    calls = 0

    def now() -> datetime:
        nonlocal calls
        calls += 1
        return MIGRATION_TIME

    bootstrap_control_schema(connection, now=now)
    bootstrap_control_schema(connection, now=now)

    assert calls == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM control_schema_migrations WHERE component = ?",
        (OPERATIONS_SCHEMA_COMPONENT,),
    ).fetchone()[0] == 1


def test_v0_ledger_baseline_advances_to_v1() -> None:
    connection = _connection()
    connection.execute(
        """
        CREATE TABLE control_schema_migrations (
            component TEXT NOT NULL,
            version INTEGER NOT NULL,
            applied_at_us INTEGER NOT NULL,
            PRIMARY KEY(component, version)
        )
        """
    )
    connection.execute(
        "INSERT INTO control_schema_migrations VALUES (?, ?, ?)",
        (OPERATIONS_SCHEMA_COMPONENT, 0, 0),
    )

    bootstrap_control_schema(connection, now=lambda: MIGRATION_TIME)

    assert connection.execute(
        "SELECT version FROM control_schema_migrations WHERE component = ? ORDER BY version",
        (OPERATIONS_SCHEMA_COMPONENT,),
    ).fetchall() == [(0,), (1,)]
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'operation_records'"
    ).fetchone()[0] == "operation_records"


def test_higher_schema_version_is_rejected_without_creating_operations_tables() -> None:
    connection = _connection()
    connection.execute(
        """
        CREATE TABLE control_schema_migrations (
            component TEXT NOT NULL,
            version INTEGER NOT NULL,
            applied_at_us INTEGER NOT NULL,
            PRIMARY KEY(component, version)
        )
        """
    )
    connection.execute(
        "INSERT INTO control_schema_migrations VALUES (?, ?, ?)",
        (OPERATIONS_SCHEMA_COMPONENT, OPERATIONS_SCHEMA_VERSION + 1, 0),
    )

    with pytest.raises(UnsupportedSchemaVersion):
        bootstrap_control_schema(connection, now=lambda: MIGRATION_TIME)

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert tables == {"control_schema_migrations"}


def test_failed_v1_migration_rolls_back_ledger_and_ddl(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _connection()

    def fail(_connection: sqlite3.Connection) -> None:
        _connection.execute(
            "CREATE TABLE migration_probe(value INTEGER NOT NULL)"
        )
        raise RuntimeError("synthetic migration failure")

    monkeypatch.setattr(migrations, "_apply_operations_v1", fail)
    with pytest.raises(RuntimeError, match="synthetic migration failure"):
        bootstrap_control_schema(connection, now=lambda: MIGRATION_TIME)

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert tables == set()


def test_migration_clock_must_be_aware_utc() -> None:
    connection = _connection()
    with pytest.raises(ValueError, match="aware UTC"):
        bootstrap_control_schema(
            connection,
            now=lambda: datetime(2024, 1, 2, 3, 4, 5),
        )

    assert not connection.in_transaction
