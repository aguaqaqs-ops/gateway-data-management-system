"""Control DB schema: creation, repeat verification without writes, and fail-closed rejection."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from gateway_backend.infrastructure.control_db import schema
from gateway_backend.infrastructure.control_db.control_db_connect import connect_control_db
from gateway_backend.infrastructure.control_db.database import initialize_control_db
from gateway_backend.infrastructure.control_db.schema import (
    CONTROL_DB_SCHEMA_STATEMENTS,
    bootstrap_control_db_schema,
)
from gateway_backend.operations import UnsupportedSchemaVersion

pytestmark = pytest.mark.unit

EXPECTED_TABLES = frozenset(
    {
        "archive_anomaly_resolution_events",
        "archive_confirmation_events",
        "archive_disposition_records",
        "archive_plan_records",
        "archive_result_records",
        "artifact_protection_intents",
        "baseline_head_records",
        "baseline_node_records",
        "history_compare_acceptance_records",
        "history_compare_integrity_records",
        "operation_records",
        "preview_idempotency_records",
        "preview_result_records",
        "provisioned_scope_mappings",
        "repository_submit_occupancy_records",
        "review_event_records",
        "review_idempotency_records",
        "review_projection_records",
        "step_records",
        "submission_records",
        "submit_attempt_records",
        "submit_idempotency_records",
        "upload_idempotency_records",
        "upload_revision_records",
        "workspace_records",
        "workspace_submit_occupancy_records",
    }
)
EXPECTED_INDEXES = frozenset(
    {
        "archive_anomaly_resolution_events_subject",
        "archive_confirmation_events_subject",
        "archive_disposition_records_one_selected_per_result",
        "archive_disposition_records_result_id",
        "archive_plan_records_start_key",
        "baseline_node_records_one_initial_per_repository",
        "baseline_node_records_repository_node",
        "history_compare_acceptance_scope_idempotency",
        "history_compare_integrity_pending_commit",
        "operation_records_status_readback",
        "provisioned_scope_mappings_one_active_device",
        "provisioned_scope_mappings_one_repository",
        "step_records_claim_order",
        "step_records_one_active_per_operation",
        "submission_records_archive_candidate_lookup",
        "submit_attempt_records_repository_state",
        "workspace_records_open_exact_scope",
    }
)
ARCHIVE_TABLES = frozenset(
    {
        "archive_anomaly_resolution_events",
        "archive_confirmation_events",
        "archive_disposition_records",
        "archive_plan_records",
        "archive_result_records",
    }
)


def _memory_connection() -> sqlite3.Connection:
    return sqlite3.connect(":memory:", isolation_level=None)


def _object_names(connection: sqlite3.Connection, kind: str) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ? AND substr(name, 1, 7) != 'sqlite_'",
        (kind,),
    ).fetchall()
    return {row[0] for row in rows}


def _create_control_db(path: Path, statements: tuple[str, ...] = CONTROL_DB_SCHEMA_STATEMENTS) -> None:
    connection = connect_control_db(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        for statement in statements:
            connection.execute(statement)
        connection.execute("COMMIT")
    finally:
        connection.close()


def _run_sql(path: Path, *statements: str) -> None:
    connection = connect_control_db(path)
    try:
        for statement in statements:
            connection.execute(statement)
    finally:
        connection.close()


def _replace_in_statement(marker: str, old: str, new: str) -> tuple[str, ...]:
    matches = [statement for statement in CONTROL_DB_SCHEMA_STATEMENTS if marker in statement]
    assert len(matches) == 1, marker
    replaced = matches[0].replace(old, new, 1)
    assert replaced != matches[0], old
    return tuple(replaced if statement == matches[0] else statement for statement in CONTROL_DB_SCHEMA_STATEMENTS)


def test_empty_control_db_gets_every_table_and_index() -> None:
    connection = _memory_connection()
    bootstrap_control_db_schema(connection)

    assert _object_names(connection, "table") == EXPECTED_TABLES
    assert _object_names(connection, "index") == EXPECTED_INDEXES
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_empty_database_file_is_initialized_as_a_new_control_db(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    db_path.touch()

    initialize_control_db(db_path)

    connection = connect_control_db(db_path)
    try:
        assert _object_names(connection, "table") == EXPECTED_TABLES
    finally:
        connection.close()


def test_repeat_bootstrap_writes_nothing(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path)
    before = db_path.read_bytes()

    connection = connect_control_db(db_path)
    try:
        changes_before = connection.total_changes
        bootstrap_control_db_schema(connection)
        bootstrap_control_db_schema(connection)
        assert connection.total_changes == changes_before
    finally:
        connection.close()

    assert db_path.read_bytes() == before


def test_failed_schema_statement_rolls_back_every_object(monkeypatch: pytest.MonkeyPatch) -> None:
    broken = (*CONTROL_DB_SCHEMA_STATEMENTS, "CREATE TABLE broken_probe (value INTEGER NOT NULL")
    monkeypatch.setattr(schema, "CONTROL_DB_SCHEMA_STATEMENTS", broken)
    connection = _memory_connection()

    with pytest.raises(sqlite3.OperationalError):
        bootstrap_control_db_schema(connection)

    assert not connection.in_transaction
    assert _object_names(connection, "table") == set()


def test_archive_tables_and_selected_disposition_index_are_created() -> None:
    connection = _memory_connection()
    bootstrap_control_db_schema(connection)

    assert {name for name in _object_names(connection, "table") if name.startswith("archive_")} == ARCHIVE_TABLES
    index_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'archive_disposition_records_one_selected_per_result'"
    ).fetchone()[0]
    assert "WHERE disposition = 'ARCHIVED_BASELINE'" in index_sql


def test_baseline_head_rejects_node_of_another_repository() -> None:
    connection = _memory_connection()
    bootstrap_control_db_schema(connection)
    connection.execute("PRAGMA foreign_keys = ON")
    for repository_id, node_id, device_key, project_id in (
        ("repo-1", "node-1", "device-1", "project-1"),
        ("repo-2", "node-2", "device-2", "project-2"),
    ):
        connection.execute(
            """
            INSERT INTO baseline_node_records (
                node_id, repository_id, gateway_device_external_key, business_project_id,
                commit_id, kind, parent_node_id, source_submission_id, created_at_us
            ) VALUES (?, ?, ?, ?, 'commit-base', 'INITIAL', NULL, NULL, 1704164645678901)
            """,
            (node_id, repository_id, device_key, project_id),
        )
        connection.execute(
            "INSERT INTO baseline_head_records (repository_id, node_id, optimistic_version) VALUES (?, ?, 0)",
            (repository_id, node_id),
        )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE baseline_head_records SET node_id = 'node-2' WHERE repository_id = 'repo-1'"
        )
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def _with_extra_table(path: Path) -> None:
    _create_control_db(path)
    _run_sql(path, "CREATE TABLE unexpected_probe (value INTEGER NOT NULL)")


def _with_dropped_table(path: Path) -> None:
    _create_control_db(path)
    _run_sql(path, "DROP TABLE step_records")


def _with_dropped_index(path: Path) -> None:
    _create_control_db(path)
    _run_sql(path, "DROP INDEX workspace_records_open_exact_scope")


def _with_extra_index(path: Path) -> None:
    _create_control_db(path)
    _run_sql(path, "CREATE INDEX unexpected_probe_index ON operation_records(status)")


def _with_changed_column(path: Path) -> None:
    _create_control_db(path, _replace_in_statement("CREATE TABLE workspace_records", "owner_actor_id TEXT NOT NULL", "owner_actor_id TEXT"))


def _with_old_migration_ledger(path: Path) -> None:
    _create_control_db(path)
    _run_sql(
        path,
        "CREATE TABLE control_schema_migrations (component TEXT NOT NULL, version INTEGER NOT NULL, "
        "applied_at_us INTEGER NOT NULL)",
    )


def _with_unrelated_sqlite_file(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE unrelated_notes (note TEXT NOT NULL)")
        connection.commit()
    finally:
        connection.close()


MISMATCH_CASES: tuple[tuple[str, Callable[[Path], None], str], ...] = (
    ("extra_table", _with_extra_table, "unexpected_probe"),
    ("dropped_table", _with_dropped_table, "step_records"),
    ("changed_column_definition", _with_changed_column, "workspace_records"),
    ("dropped_index", _with_dropped_index, "workspace_records_open_exact_scope"),
    ("extra_index", _with_extra_index, "unexpected_probe_index"),
    ("old_migration_ledger", _with_old_migration_ledger, "control_schema_migrations"),
    ("unrelated_sqlite_file", _with_unrelated_sqlite_file, "unrelated_notes"),
)


@pytest.mark.parametrize(
    ("build", "mismatched_object"),
    [(build, mismatched) for _case, build, mismatched in MISMATCH_CASES],
    ids=[case for case, _build, _mismatched in MISMATCH_CASES],
)
def test_control_db_with_a_different_structure_is_rejected_and_not_modified(
    tmp_path: Path,
    build: Callable[[Path], None],
    mismatched_object: str,
) -> None:
    db_path = tmp_path / "control.sqlite3"
    build(db_path)
    before = db_path.read_bytes()

    with pytest.raises(UnsupportedSchemaVersion) as exc_info:
        initialize_control_db(db_path)

    message = str(exc_info.value)
    assert mismatched_object in message
    assert "delete the local control DB" in message
    assert db_path.read_bytes() == before


def test_file_that_is_not_sqlite_is_rejected_and_not_modified(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    db_path.write_bytes(b"not-a-sqlite-database")

    with pytest.raises(UnsupportedSchemaVersion, match="not a readable SQLite database"):
        initialize_control_db(db_path)

    assert db_path.read_bytes() == b"not-a-sqlite-database"
