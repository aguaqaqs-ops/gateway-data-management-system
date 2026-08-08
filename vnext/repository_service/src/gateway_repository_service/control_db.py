"""Transactional control-store lifecycle for service-state SQLite."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from gateway_repository_service.mutation_store import configure_connection

CONTROL_DB_USER_VERSION = 7

_ADMIN_CLI_REQUIRED_TABLES: frozenset[str] = frozenset(
    {
        "mutation_idempotency",
        "synchronous_mutation_effects",
        "artifact_lifecycle",
        "repository_import_operations",
        "repository_import_recovery_audit",
    }
)

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

_MIGRATION_V4_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TRIGGER prevent_succeeded_when_terminal
    BEFORE UPDATE ON synchronous_mutation_effects
    FOR EACH ROW
    WHEN NEW.status = 'SUCCEEDED'
    BEGIN
        SELECT RAISE(ABORT, 'terminal-not-published effects cannot succeed')
        WHERE EXISTS (
            SELECT 1
            FROM mutation_idempotency
            WHERE id = NEW.idempotency_id
              AND terminal_not_published = 1
        );
    END
    """,
    """
    CREATE TRIGGER prevent_terminal_when_succeeded
    BEFORE UPDATE ON mutation_idempotency
    FOR EACH ROW
    WHEN NEW.terminal_not_published = 1
    BEGIN
        SELECT RAISE(ABORT, 'succeeded effects cannot be marked terminal-not-published')
        WHERE EXISTS (
            SELECT 1
            FROM synchronous_mutation_effects
            WHERE idempotency_id = NEW.id
              AND status = 'SUCCEEDED'
        );
    END
    """,
)


_MIGRATION_V6_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE artifact_lifecycle (
        artifact_id TEXT PRIMARY KEY,
        repository_scope TEXT NOT NULL,
        media_type TEXT NOT NULL,
        size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
        raw_sha256 TEXT NOT NULL CHECK (length(raw_sha256) = 64),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX artifact_lifecycle_repository_scope_idx
    ON artifact_lifecycle (repository_scope)
    """,
)


_MIGRATION_V7_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE repository_import_operations (
        operation_id TEXT PRIMARY KEY,
        repository_scope TEXT NOT NULL,
        key_hash BLOB NOT NULL CHECK (length(key_hash) = 32),
        request_fingerprint BLOB NOT NULL,
        artifact_id TEXT NOT NULL,
        artifact_media_type TEXT NOT NULL,
        artifact_size_bytes INTEGER NOT NULL CHECK (artifact_size_bytes >= 0),
        artifact_raw_sha256 TEXT NOT NULL CHECK (length(artifact_raw_sha256) = 64),
        target_ref TEXT NOT NULL CHECK (target_ref = 'main'),
        expected_commit_id TEXT NOT NULL,
        requested_verification_policy TEXT NOT NULL,
        unknown_type_policy TEXT NOT NULL,
        status TEXT NOT NULL CHECK (
            status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')
        ),
        private_ref_name TEXT NOT NULL,
        operation_marker TEXT NOT NULL,
        canonicalization_manifest_digest TEXT NULL,
        automatic_replay_count INTEGER NOT NULL DEFAULT 0 CHECK (automatic_replay_count IN (0, 1)),
        enqueue_sequence INTEGER NOT NULL,
        result_json TEXT NULL,
        error_json TEXT NULL,
        created_at TEXT NOT NULL,
        started_at TEXT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT NULL,
        UNIQUE (repository_scope, key_hash)
    )
    """,
    """
    CREATE INDEX repository_import_operations_claim_idx
    ON repository_import_operations (repository_scope, status, enqueue_sequence)
    """,
    """
    CREATE INDEX repository_import_operations_artifact_idx
    ON repository_import_operations (artifact_id)
    """,
    """
    CREATE TABLE repository_import_recovery_audit (
        audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation_id TEXT NOT NULL,
        action TEXT NOT NULL CHECK (
            action IN ('INSPECT_APPLY_SUCCESS', 'INSPECT_APPLY_NOT_PUBLISHED')
        ),
        prior_status TEXT NOT NULL,
        prior_code TEXT NULL,
        final_status TEXT NOT NULL,
        final_code TEXT NULL,
        evidence_summary_json TEXT NOT NULL,
        applied_at TEXT NOT NULL
    )
    """,
    """
    ALTER TABLE artifact_lifecycle
    ADD COLUMN consumed_by_operation_id TEXT NULL
    """,
    """
    ALTER TABLE artifact_lifecycle
    ADD COLUMN consumed_at TEXT NULL
    """,
    """
    ALTER TABLE artifact_lifecycle
    ADD COLUMN bytes_deleted_at TEXT NULL
    """,
)


_MIGRATION_V5_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TRIGGER prevent_insert_succeeded_when_terminal
    BEFORE INSERT ON synchronous_mutation_effects
    FOR EACH ROW
    WHEN NEW.status = 'SUCCEEDED'
    BEGIN
        SELECT RAISE(ABORT, 'terminal-not-published effects cannot succeed')
        WHERE EXISTS (
            SELECT 1
            FROM mutation_idempotency
            WHERE id = NEW.idempotency_id
              AND terminal_not_published = 1
        );
    END
    """,
    """
    CREATE TRIGGER prevent_insert_terminal_when_succeeded
    BEFORE INSERT ON mutation_idempotency
    FOR EACH ROW
    WHEN NEW.terminal_not_published = 1
    BEGIN
        SELECT RAISE(ABORT, 'succeeded effects cannot be marked terminal-not-published')
        WHERE EXISTS (
            SELECT 1
            FROM synchronous_mutation_effects
            WHERE idempotency_id = NEW.id
              AND status = 'SUCCEEDED'
        );
    END
    """,
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
    transaction_lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def preflight_exact_version(cls, path: Path, *, expected_version: int) -> None:
        if not path.is_file():
            raise ControlDbError("control database does not exist")
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if user_version > expected_version:
                raise ControlDbNewerVersionError(
                    f"control database user_version {user_version} is newer than "
                    f"supported {expected_version}"
                )
            if user_version < expected_version:
                raise ControlDbError(
                    f"control database user_version {user_version} is older than "
                    f"supported {expected_version}"
                )
            if user_version != expected_version:
                raise ControlDbError(
                    f"control database user_version {user_version} is unsupported"
                )
            cls._verify_admin_schema(connection)
        finally:
            connection.close()

    @classmethod
    def open(
        cls,
        path: Path,
        *,
        expected_version: int,
        busy_timeout_ms: int,
        allow_migration: bool = True,
    ) -> Self:
        if allow_migration:
            path.parent.mkdir(parents=True, exist_ok=True)
        elif not path.is_file():
            raise ControlDbError("control database does not exist")
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
            if allow_migration:
                user_version = cls._migrate(connection, expected_version=expected_version)
            else:
                user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if user_version > expected_version:
                    raise ControlDbNewerVersionError(
                        f"control database user_version {user_version} is newer than "
                        f"supported {expected_version}"
                    )
                if user_version != expected_version:
                    raise ControlDbError(
                        f"control database user_version {user_version} is unsupported"
                    )
                cls._verify_admin_schema(connection)
            cls._verify_synchronous_full(connection)
            cls._verify_foreign_keys(connection)
            return cls(path=path, connection=connection, user_version=user_version)
        except Exception:
            connection.close()
            raise

    @staticmethod
    def _verify_admin_schema(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        present = {str(row[0]) for row in rows}
        missing = _ADMIN_CLI_REQUIRED_TABLES.difference(present)
        if missing:
            missing_tables = ", ".join(sorted(missing))
            raise ControlDbError(
                f"control database schema is missing required tables: {missing_tables}"
            )

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
    def _validate_no_terminal_succeeded_contradictions(connection: sqlite3.Connection) -> None:
        row = connection.execute(
            """
            SELECT COUNT(*) AS contradiction_count
            FROM mutation_idempotency AS m
            INNER JOIN synchronous_mutation_effects AS e ON e.idempotency_id = m.id
            WHERE m.terminal_not_published = 1
              AND e.status = 'SUCCEEDED'
            """
        ).fetchone()
        if row is not None and int(row[0]) > 0:
            raise ControlDbError(
                "control database has terminal-not-published succeeded contradictions; "
                "operator intervention is required before migration"
            )

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
        if target_version == 4:
            ControlStore._execute_statements(connection, _MIGRATION_V4_STATEMENTS)
            return
        if target_version == 5:
            ControlStore._validate_no_terminal_succeeded_contradictions(connection)
            ControlStore._execute_statements(connection, _MIGRATION_V5_STATEMENTS)
            return
        if target_version == 6:
            ControlStore._execute_statements(connection, _MIGRATION_V6_STATEMENTS)
            return
        if target_version == 7:
            ControlStore._execute_statements(connection, _MIGRATION_V7_STATEMENTS)
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
