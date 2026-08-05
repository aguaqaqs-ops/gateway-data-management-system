"""Transactional control-store lifecycle for service-state SQLite."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from gateway_repository_service.mutation_store import configure_connection

_MIGRATION_V2_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE mutation_idempotency (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mutation_kind TEXT NOT NULL CHECK (
            mutation_kind IN ('create_repository', 'upload_artifact')
        ),
        repository_scope TEXT NOT NULL DEFAULT '',
        key_hash BLOB NOT NULL CHECK (length(key_hash) = 32),
        request_fingerprint BLOB NOT NULL,
        terminal_not_published INTEGER NOT NULL DEFAULT 0 CHECK (terminal_not_published IN (0, 1)),
        created_at TEXT NOT NULL,
        UNIQUE (mutation_kind, repository_scope, key_hash)
    )
    """,
    """
    CREATE TABLE synchronous_mutation_effects (
        effect_id INTEGER PRIMARY KEY AUTOINCREMENT,
        idempotency_id INTEGER NOT NULL UNIQUE REFERENCES mutation_idempotency(id),
        resource_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('PENDING', 'SUCCEEDED')),
        response_status INTEGER,
        response_body TEXT,
        updated_at TEXT NOT NULL
    )
    """,
)

_MIGRATION_V3_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE mutation_idempotency_v3 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mutation_kind TEXT NOT NULL CHECK (
            mutation_kind IN ('create_repository', 'upload_artifact')
        ),
        repository_scope TEXT NOT NULL DEFAULT '',
        key_hash BLOB NOT NULL CHECK (length(key_hash) = 32),
        request_fingerprint BLOB NOT NULL,
        terminal_not_published INTEGER NOT NULL DEFAULT 0 CHECK (terminal_not_published IN (0, 1)),
        created_at TEXT NOT NULL,
        CHECK (
            (mutation_kind = 'create_repository' AND repository_scope = '')
            OR (mutation_kind = 'upload_artifact' AND repository_scope != '')
        ),
        UNIQUE (mutation_kind, repository_scope, key_hash)
    )
    """,
    """
    CREATE TABLE synchronous_mutation_effects_v3 (
        effect_id INTEGER PRIMARY KEY AUTOINCREMENT,
        idempotency_id INTEGER NOT NULL UNIQUE REFERENCES mutation_idempotency_v3(id),
        resource_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('PENDING', 'SUCCEEDED')),
        response_status INTEGER,
        response_body TEXT,
        updated_at TEXT NOT NULL,
        CHECK (
            (status = 'PENDING' AND response_status IS NULL AND response_body IS NULL)
            OR (status = 'SUCCEEDED' AND response_status = 201 AND response_body IS NOT NULL)
        )
    )
    """,
    """
    INSERT INTO mutation_idempotency_v3 (
        id,
        mutation_kind,
        repository_scope,
        key_hash,
        request_fingerprint,
        terminal_not_published,
        created_at
    )
    SELECT
        id,
        mutation_kind,
        repository_scope,
        key_hash,
        request_fingerprint,
        terminal_not_published,
        created_at
    FROM mutation_idempotency
    """,
    """
    INSERT INTO synchronous_mutation_effects_v3 (
        effect_id,
        idempotency_id,
        resource_id,
        status,
        response_status,
        response_body,
        updated_at
    )
    SELECT
        effect_id,
        idempotency_id,
        resource_id,
        status,
        response_status,
        response_body,
        updated_at
    FROM synchronous_mutation_effects
    """,
    "DROP TABLE synchronous_mutation_effects",
    "DROP TABLE mutation_idempotency",
    "ALTER TABLE mutation_idempotency_v3 RENAME TO mutation_idempotency",
    "ALTER TABLE synchronous_mutation_effects_v3 RENAME TO synchronous_mutation_effects",
)


class ControlDbError(RuntimeError):
    """Raised when the control database cannot be opened or migrated."""


class ControlDbNewerVersionError(ControlDbError):
    """Raised when on-disk user_version exceeds the supported version."""


@dataclass
class ControlStore:
    path: Path
    connection: sqlite3.Connection
    user_version: int

    @classmethod
    def open(
        cls,
        path: Path,
        *,
        expected_version: int,
        busy_timeout_ms: int,
    ) -> Self:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            path,
            timeout=busy_timeout_ms / 1000.0,
            check_same_thread=False,
        )
        configure_connection(connection)
        try:
            connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
            connection.execute("PRAGMA foreign_keys = ON")
            cls._ensure_wal_mode(connection)
            user_version = cls._migrate(connection, expected_version=expected_version)
            cls._verify_synchronous_full(connection)
            cls._verify_foreign_keys(connection)
            return cls(path=path, connection=connection, user_version=user_version)
        except Exception:
            connection.close()
            raise

    @staticmethod
    def _ensure_wal_mode(connection: sqlite3.Connection) -> None:
        journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()
        if journal_mode is None or str(journal_mode[0]).upper() != "WAL":
            raise ControlDbError("control database WAL mode is unavailable")

    @staticmethod
    def _verify_synchronous_full(connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA synchronous = FULL")
        synchronous = connection.execute("PRAGMA synchronous").fetchone()
        if synchronous is None or int(synchronous[0]) != 2:
            raise ControlDbError("control database synchronous mode is invalid")

    @staticmethod
    def _verify_foreign_keys(connection: sqlite3.Connection) -> None:
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
        if foreign_keys is None or int(foreign_keys[0]) != 1:
            raise ControlDbError("control database foreign keys are disabled")

    @staticmethod
    def _migrate(connection: sqlite3.Connection, *, expected_version: int) -> int:
        current = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current > expected_version:
            raise ControlDbNewerVersionError(
                f"control database user_version {current} is newer than supported {expected_version}"
            )
        if current == expected_version:
            return current

        connection.execute("BEGIN IMMEDIATE")
        try:
            replay_current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if replay_current > expected_version:
                raise ControlDbNewerVersionError(
                    "control database user_version changed during migration"
                )
            while replay_current < expected_version:
                next_version = replay_current + 1
                ControlStore._apply_migration_step(connection, next_version)
                connection.execute(f"PRAGMA user_version = {next_version}")
                replay_current = next_version
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return expected_version

    @staticmethod
    def _execute_statements(connection: sqlite3.Connection, statements: tuple[str, ...]) -> None:
        for statement in statements:
            connection.execute(statement)

    @staticmethod
    def _apply_migration_step(connection: sqlite3.Connection, target_version: int) -> None:
        if target_version == 1:
            return
        if target_version == 2:
            ControlStore._execute_statements(connection, _MIGRATION_V2_STATEMENTS)
            return
        if target_version == 3:
            ControlStore._execute_statements(connection, _MIGRATION_V3_STATEMENTS)
            return
        raise ControlDbError(f"unsupported control database migration target {target_version}")

    def close(self) -> None:
        self.connection.close()

    def is_open(self) -> bool:
        try:
            self.connection.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            return False
        return True
