"""File-backed SQLite control DB integration tests."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

import pytest

from gateway_backend.infrastructure.control_db import (
    ControlDbUnitOfWork,
    connect_control_db,
    initialize_control_db,
)
from gateway_backend.infrastructure.control_db.migrations import bootstrap_control_schema

pytestmark = pytest.mark.integration

MIGRATION_TIME = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_file_backed_profile_and_schema_survive_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path, now=lambda: MIGRATION_TIME)

    connection = connect_control_db(db_path)
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
    assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5_000
    connection.close()

    reopened = connect_control_db(db_path)
    try:
        assert reopened.execute(
            "SELECT version FROM control_schema_migrations WHERE component = 'operations'"
        ).fetchone()[0] == 1
        assert reopened.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'step_records'"
        ).fetchone()[0] == "step_records"
    finally:
        reopened.close()


def test_unit_of_work_commits_and_rolls_back_on_same_connection(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_control_db(db_path, now=lambda: MIGRATION_TIME)

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute("CREATE TABLE uow_probe(value INTEGER NOT NULL)")
        unit_of_work.connection.execute("INSERT INTO uow_probe VALUES (1)")

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        assert unit_of_work.connection.execute("SELECT value FROM uow_probe").fetchone()[0] == 1

    with pytest.raises(RuntimeError):
        with ControlDbUnitOfWork(db_path) as unit_of_work:
            unit_of_work.connection.execute("INSERT INTO uow_probe VALUES (2)")
            raise RuntimeError("synthetic rollback")

    with connect_control_db(db_path) as connection:
        values = [row[0] for row in connection.execute("SELECT value FROM uow_probe ORDER BY value")]
    assert values == [1]


def test_missing_parent_is_not_created(tmp_path: Path) -> None:
    missing_parent = tmp_path / "not-created"
    with pytest.raises(ValueError, match="parent directory"):
        connect_control_db(missing_parent / "control.sqlite3")
    assert not missing_parent.exists()


def test_two_connections_can_bootstrap_the_same_file_once(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    barrier = Barrier(2)

    def bootstrap_from_independent_connection() -> None:
        barrier.wait()
        connection = connect_control_db(db_path)
        try:
            bootstrap_control_schema(connection, now=lambda: MIGRATION_TIME)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _item: bootstrap_from_independent_connection(), (1, 2)))

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM control_schema_migrations WHERE component = 'operations'"
        ).fetchone()[0] == 1
    finally:
        connection.close()
