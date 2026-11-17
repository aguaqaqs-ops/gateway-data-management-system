"""Transactional control-store lifecycle for service-state SQLite.

The control DB has one baseline schema and no in-place upgrade, downgrade, or
backfill path. Empty databases receive the baseline DDL; any existing database
must match both ``PRAGMA user_version`` and the exact ``sqlite_master``
structure produced by that baseline, or opening fails closed before writes.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Self

from gateway_repository_service.mutation_store import configure_connection

CONTROL_DB_USER_VERSION = 16

ColumnShape = tuple[tuple[str, str, int, str | None, int], ...]
_StructureRow = tuple[str, str, str, str | None]

_STRUCTURE_QUERY = """
    SELECT type, name, tbl_name, sql
    FROM sqlite_master
    WHERE substr(name, 1, 7) != 'sqlite_'
    ORDER BY type, name
"""

_BASELINE_TABLES: frozenset[str] = frozenset(
    {
        "mutation_idempotency",
        "synchronous_mutation_effects",
        "artifact_lifecycle",
        "repository_import_operations",
        "repository_import_recovery_audit",
    }
)

_BASELINE_INDEXES: dict[str, tuple[str, ...]] = {
    "repository_import_operations_claim_idx": (
        "repository_scope",
        "status",
        "enqueue_sequence",
    ),
    "repository_import_operations_artifact_idx": ("artifact_id",),
    "repository_import_operations_manual_barrier_idx": ("repository_scope",),
    "artifact_lifecycle_repository_scope_idx": ("repository_scope",),
    "artifact_lifecycle_cleanup_keyset_idx": ("created_at", "artifact_id"),
    "artifact_lifecycle_cleanup_seq_idx": ("cleanup_seq",),
    "artifact_lifecycle_cleanup_seq_uidx": ("cleanup_seq",),
}

_BASELINE_TRIGGER_NAMES: frozenset[str] = frozenset(
    {
        "prevent_succeeded_when_terminal",
        "prevent_terminal_when_succeeded",
        "prevent_insert_succeeded_when_terminal",
        "prevent_insert_terminal_when_succeeded",
        "artifact_lifecycle_forbid_cleanup_seq_update",
    }
)

_BASELINE_STATEMENTS: tuple[str, ...] = (
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
        CHECK (
            (mutation_kind = 'create_repository' AND repository_scope = '')
            OR (mutation_kind = 'upload_artifact' AND repository_scope != '')
        ),
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
        updated_at TEXT NOT NULL,
        CHECK (
            (status = 'PENDING' AND response_status IS NULL AND response_body IS NULL)
            OR (status = 'SUCCEEDED' AND response_status = 201 AND response_body IS NOT NULL)
        )
    )
    """,
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
    """
    CREATE TABLE artifact_lifecycle (
        artifact_id TEXT PRIMARY KEY,
        repository_scope TEXT NOT NULL,
        media_type TEXT NOT NULL,
        size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
        raw_sha256 TEXT NOT NULL CHECK (length(raw_sha256) = 64),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        consumed_by_operation_id TEXT NULL,
        consumed_at TEXT NULL,
        bytes_deleted_at TEXT NULL,
        cleanup_seq INTEGER NOT NULL CHECK (
            typeof(cleanup_seq) = 'integer' AND cleanup_seq > 0
        )
    )
    """,
    """
    CREATE UNIQUE INDEX artifact_lifecycle_cleanup_seq_uidx
    ON artifact_lifecycle (cleanup_seq)
    """,
    """
    CREATE INDEX artifact_lifecycle_cleanup_seq_idx
    ON artifact_lifecycle (cleanup_seq)
    WHERE bytes_deleted_at IS NULL
    """,
    """
    CREATE INDEX artifact_lifecycle_cleanup_keyset_idx
    ON artifact_lifecycle (created_at, artifact_id)
    WHERE bytes_deleted_at IS NULL
    """,
    """
    CREATE INDEX artifact_lifecycle_repository_scope_idx
    ON artifact_lifecycle (repository_scope)
    """,
    """
    CREATE TRIGGER artifact_lifecycle_forbid_cleanup_seq_update
    BEFORE UPDATE OF cleanup_seq ON artifact_lifecycle
    BEGIN
        SELECT RAISE(ABORT, 'cleanup_seq is immutable');
    END
    """,
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
            status IN ('ADMISSION_PENDING', 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')
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
        manual_recovery_required INTEGER NOT NULL DEFAULT 0 CHECK (manual_recovery_required IN (0, 1)),
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
    CREATE INDEX repository_import_operations_manual_barrier_idx
    ON repository_import_operations (repository_scope)
    WHERE manual_recovery_required = 1
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
)

_MISMATCH_NAME_LIMIT = 8


class ControlDbError(RuntimeError):
    """Raised when the control database cannot be opened or fails schema verification."""


class ControlDbNewerVersionError(ControlDbError):
    """Raised when on-disk user_version exceeds the supported version."""


@dataclass(frozen=True)
class WalCheckpointResult:
    """Result of ``PRAGMA wal_checkpoint`` with busy and frame counts."""

    busy: int
    log: int
    checkpointed: int

    def is_quiescent(self) -> bool:
        return self.busy == 0 and self.log == self.checkpointed


@dataclass(frozen=True)
class _ReferenceSchema:
    structure: tuple[_StructureRow, ...]
    column_shapes: dict[str, ColumnShape]
    index_columns: dict[str, tuple[str, ...]]


def _table_column_shape(connection: sqlite3.Connection, table_name: str) -> ColumnShape:
    rows = connection.execute(f"PRAGMA table_xinfo({table_name})").fetchall()
    visible_rows = [row for row in rows if int(row[6]) == 0]
    return tuple(
        (
            str(row[1]),
            str(row[2]),
            int(row[3]),
            None if row[4] is None else str(row[4]),
            int(row[5]),
        )
        for row in sorted(visible_rows, key=lambda row: int(row[0]))
    )


def _index_column_names(connection: sqlite3.Connection, index_name: str) -> tuple[str, ...]:
    rows = connection.execute(f"PRAGMA index_xinfo({index_name})").fetchall()
    key_rows = [row for row in rows if int(row[5]) == 1]
    return tuple(str(row[2]) for row in sorted(key_rows, key=lambda row: int(row[0])))


def _ddl_signature(sql: str) -> str:
    return sql.strip()


def _read_structure(connection: sqlite3.Connection) -> tuple[_StructureRow, ...]:
    rows = connection.execute(_STRUCTURE_QUERY).fetchall()
    return tuple(
        (
            str(row[0]),
            str(row[1]),
            str(row[2]),
            None if row[3] is None else _ddl_signature(str(row[3])),
        )
        for row in rows
    )


def _shown_names(names: list[str]) -> str:
    if not names:
        return "none"
    shown = ", ".join(names[:_MISMATCH_NAME_LIMIT])
    if len(names) > _MISMATCH_NAME_LIMIT:
        shown += f" and {len(names) - _MISMATCH_NAME_LIMIT} more"
    return shown


@lru_cache(maxsize=1)
def _reference_schema() -> _ReferenceSchema:
    connection = sqlite3.connect(":memory:")
    configure_connection(connection)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        ControlStore._execute_statements(connection, _BASELINE_STATEMENTS)
        structure = _read_structure(connection)
        column_shapes = {
            table_name: _table_column_shape(connection, table_name)
            for table_name in sorted(_BASELINE_TABLES)
        }
        index_columns = {
            index_name: _index_column_names(connection, index_name)
            for index_name in sorted(_BASELINE_INDEXES)
        }
        present_triggers = {
            name for kind, name, _tbl, _sql in structure if kind == "trigger"
        }
        if present_triggers != _BASELINE_TRIGGER_NAMES:
            raise ControlDbError("reference control database schema trigger mismatch")
    finally:
        connection.close()
    return _ReferenceSchema(
        structure=structure,
        column_shapes=column_shapes,
        index_columns=index_columns,
    )


@dataclass
class ControlStore:
    path: Path
    connection: sqlite3.Connection
    user_version: int
    transaction_lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def preflight_exact_version(
        cls,
        path: Path,
        *,
        expected_version: int,
        immutable: bool = False,
    ) -> None:
        cls._validate_expected_version(expected_version)
        if not path.is_file():
            raise ControlDbError("control database does not exist")
        if immutable:
            try:
                with path.open("rb") as handle:
                    header = handle.read(20)
            except OSError as exc:
                raise ControlDbError("control database is unreadable") from exc
            if len(header) < 20 or header[:16] != b"SQLite format 3\x00":
                raise ControlDbError("control database is unreadable")
            if header[18:20] != b"\x02\x02":
                raise ControlDbError("control database WAL mode is unavailable")
        immutable_query = "&immutable=1" if immutable else ""
        try:
            connection = sqlite3.connect(
                f"{path.resolve().as_uri()}?mode=ro{immutable_query}",
                uri=True,
            )
        except sqlite3.Error as exc:
            raise ControlDbError("control database is unreadable") from exc
        try:
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            cls._verify_user_version(user_version, expected_version=expected_version)
            cls._verify_schema(connection, require_wal_mode=not immutable)
        except sqlite3.Error as exc:
            raise ControlDbError("control database is unreadable") from exc
        finally:
            connection.close()

    @classmethod
    def open_readonly(cls, path: Path, *, expected_version: int) -> Self:
        cls.preflight_exact_version(
            path,
            expected_version=expected_version,
            immutable=True,
        )
        try:
            connection = sqlite3.connect(
                f"{path.resolve().as_uri()}?mode=ro&immutable=1",
                uri=True,
            )
        except sqlite3.Error as exc:
            raise ControlDbError("control database is unreadable") from exc
        configure_connection(connection)
        try:
            connection.execute("PRAGMA query_only = ON")
            return cls(path=path, connection=connection, user_version=expected_version)
        except sqlite3.Error as exc:
            connection.close()
            raise ControlDbError("control database is unreadable") from exc

    @classmethod
    def open(
        cls,
        path: Path,
        *,
        expected_version: int,
        busy_timeout_ms: int,
        allow_migration: bool = True,
    ) -> Self:
        cls._validate_expected_version(expected_version)
        if allow_migration:
            path.parent.mkdir(parents=True, exist_ok=True)
            cls._preflight_existing_file_readonly(
                path,
                expected_version=expected_version,
                busy_timeout_ms=busy_timeout_ms,
            )
        elif not path.is_file():
            raise ControlDbError("control database does not exist")

        try:
            connection = sqlite3.connect(
                path,
                timeout=busy_timeout_ms / 1000.0,
                check_same_thread=False,
            )
        except sqlite3.Error as exc:
            raise ControlDbError("control database is unreadable") from exc
        configure_connection(connection)
        try:
            connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
            connection.execute("PRAGMA foreign_keys = ON")
            if allow_migration:
                cls._ensure_wal_mode(connection)
                user_version = cls._initialize_or_verify_baseline(
                    connection,
                    expected_version=expected_version,
                )
                cls._verify_synchronous_full(connection)
            else:
                cls._require_wal_mode(connection)
                user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                cls._verify_user_version(user_version, expected_version=expected_version)
                cls._verify_schema(connection, require_wal_mode=True)
                cls._require_synchronous_full(connection)
            cls._verify_foreign_keys(connection)
            return cls(path=path, connection=connection, user_version=user_version)
        except sqlite3.Error as exc:
            connection.close()
            raise ControlDbError("control database is unreadable") from exc
        except Exception:
            connection.close()
            raise

    @classmethod
    def _preflight_existing_file_readonly(
        cls,
        path: Path,
        *,
        expected_version: int,
        busy_timeout_ms: int,
    ) -> None:
        if not path.is_file() or path.stat().st_size == 0:
            return
        try:
            ro_connection = sqlite3.connect(
                f"{path.resolve().as_uri()}?mode=ro",
                uri=True,
                timeout=busy_timeout_ms / 1000.0,
            )
        except sqlite3.Error as exc:
            raise ControlDbError("control database is unreadable") from exc
        try:
            ro_connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
            user_version = int(ro_connection.execute("PRAGMA user_version").fetchone()[0])
            structure = _read_structure(ro_connection)
            if user_version == 0 and not structure:
                return
            cls._verify_user_version(user_version, expected_version=expected_version)
            cls._verify_schema(ro_connection, require_wal_mode=False)
        except sqlite3.Error as exc:
            raise ControlDbError("control database is unreadable") from exc
        finally:
            ro_connection.close()

    @staticmethod
    def _validate_expected_version(expected_version: int) -> None:
        if expected_version != CONTROL_DB_USER_VERSION:
            raise ControlDbError(
                f"control database expected_version {expected_version} does not match "
                f"baseline {CONTROL_DB_USER_VERSION}"
            )

    @staticmethod
    def _verify_user_version(user_version: int, *, expected_version: int) -> None:
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

    @classmethod
    def _initialize_or_verify_baseline(
        cls,
        connection: sqlite3.Connection,
        *,
        expected_version: int,
    ) -> int:
        connection.execute("BEGIN IMMEDIATE")
        try:
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            existing = _read_structure(connection)
            if current == 0 and not existing:
                cls._execute_statements(connection, _BASELINE_STATEMENTS)
                connection.execute(f"PRAGMA user_version = {expected_version}")
                cls._verify_schema(connection, require_wal_mode=True)
                connection.commit()
                return expected_version
            cls._verify_user_version(current, expected_version=expected_version)
            cls._verify_schema(connection, require_wal_mode=True)
            connection.commit()
            return current
        except Exception:
            connection.rollback()
            raise

    @staticmethod
    def _verify_schema(
        connection: sqlite3.Connection,
        *,
        require_wal_mode: bool = True,
    ) -> None:
        if require_wal_mode:
            ControlStore._require_wal_mode(connection)

        reference = _reference_schema()
        actual_structure = _read_structure(connection)
        if actual_structure != reference.structure:
            actual_by_key = {
                (kind, name): (tbl_name, sql)
                for kind, name, tbl_name, sql in actual_structure
            }
            expected_by_key = {
                (kind, name): (tbl_name, sql)
                for kind, name, tbl_name, sql in reference.structure
            }
            unexpected = sorted(
                {name for _kind, name in actual_by_key.keys() - expected_by_key.keys()}
            )
            missing_or_changed = sorted(
                {
                    name
                    for (_kind, name), value in expected_by_key.items()
                    if actual_by_key.get((_kind, name)) != value
                }
            )
            raise ControlDbError(
                "control database schema does not match baseline "
                f"(unexpected: {_shown_names(unexpected)}; "
                f"missing or changed: {_shown_names(missing_or_changed)})"
            )

        for table_name, expected_shape in reference.column_shapes.items():
            actual_shape = _table_column_shape(connection, table_name)
            if actual_shape != expected_shape:
                raise ControlDbError(
                    f"control database schema has invalid column shape on {table_name}"
                )

        for index_name, expected_columns in reference.index_columns.items():
            actual_columns = _index_column_names(connection, index_name)
            if actual_columns != expected_columns:
                raise ControlDbError(
                    f"control database schema has invalid index columns on {index_name}"
                )

        foreign_key_rows = connection.execute(
            "PRAGMA foreign_key_list(synchronous_mutation_effects)"
        ).fetchall()
        has_idempotency_fk = any(
            str(row[2]) == "mutation_idempotency"
            and str(row[3]) == "idempotency_id"
            and str(row[4]) == "id"
            for row in foreign_key_rows
        )
        if not has_idempotency_fk:
            raise ControlDbError(
                "control database schema is missing required foreign key on "
                "synchronous_mutation_effects.idempotency_id"
            )

    @staticmethod
    def _require_wal_mode(connection: sqlite3.Connection) -> None:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()
        if journal_mode is None or str(journal_mode[0]).upper() != "WAL":
            raise ControlDbError("control database WAL mode is unavailable")

    @staticmethod
    def _ensure_wal_mode(connection: sqlite3.Connection) -> None:
        journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()
        if journal_mode is None or str(journal_mode[0]).upper() != "WAL":
            raise ControlDbError("control database WAL mode is unavailable")

    @staticmethod
    def _require_synchronous_full(connection: sqlite3.Connection) -> None:
        synchronous = connection.execute("PRAGMA synchronous").fetchone()
        if synchronous is None or int(synchronous[0]) != 2:
            raise ControlDbError("control database synchronous mode is invalid")

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
    def _execute_statements(connection: sqlite3.Connection, statements: tuple[str, ...]) -> None:
        for statement in statements:
            connection.execute(statement)

    def checkpoint_wal_truncate(self) -> WalCheckpointResult:
        try:
            row = self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        except sqlite3.Error as exc:
            raise ControlDbError("control database checkpoint failed") from exc
        if row is None or len(row) < 3:
            raise ControlDbError("control database checkpoint failed")
        return WalCheckpointResult(
            busy=int(row[0]),
            log=int(row[1]),
            checkpointed=int(row[2]),
        )

    def verify_readonly_integrity(self) -> None:
        try:
            rows = self.connection.execute("PRAGMA integrity_check").fetchall()
        except sqlite3.Error as exc:
            raise ControlDbError("control database integrity check failed") from exc
        if len(rows) != 1 or str(rows[0][0]) != "ok":
            raise ControlDbError("control database integrity check failed")
        try:
            foreign_key_rows = self.connection.execute("PRAGMA foreign_key_check").fetchall()
        except sqlite3.Error as exc:
            raise ControlDbError("control database foreign-key check failed") from exc
        if foreign_key_rows:
            raise ControlDbError("control database foreign-key check failed")

    def close(self) -> None:
        self.connection.close()

    def is_open(self) -> bool:
        try:
            self.connection.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            return False
        return True
