"""Transactional control-store lifecycle for service-state SQLite."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Self

from gateway_repository_service.mutation_store import configure_connection

CONTROL_DB_USER_VERSION = 16

ColumnShape = tuple[tuple[str, str, int, str | None, int], ...]

_ADMIN_CLI_REQUIRED_TABLES: frozenset[str] = frozenset(
    {
        "mutation_idempotency",
        "synchronous_mutation_effects",
        "artifact_lifecycle",
        "repository_import_operations",
        "repository_import_recovery_audit",
        "artifact_residual",
    }
)

_ADMIN_CLI_REQUIRED_INDEXES: dict[str, tuple[str, ...]] = {
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

_ADMIN_CLI_REQUIRED_TRIGGER_NAMES: frozenset[str] = frozenset(
    {
        "prevent_succeeded_when_terminal",
        "prevent_terminal_when_succeeded",
        "prevent_insert_succeeded_when_terminal",
        "prevent_insert_terminal_when_succeeded",
        "artifact_lifecycle_forbid_cleanup_seq_update",
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


_MIGRATION_V8_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE repository_import_operations_v8 (
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
        UNIQUE (repository_scope, key_hash)
    )
    """,
    """
    INSERT INTO repository_import_operations_v8
    SELECT * FROM repository_import_operations
    """,
    """
    DROP TABLE repository_import_operations
    """,
    """
    ALTER TABLE repository_import_operations_v8
    RENAME TO repository_import_operations
    """,
    """
    CREATE INDEX repository_import_operations_claim_idx
    ON repository_import_operations (repository_scope, status, enqueue_sequence)
    """,
    """
    CREATE INDEX repository_import_operations_artifact_idx
    ON repository_import_operations (artifact_id)
    """,
)


_MIGRATION_V9_STATEMENTS: tuple[str, ...] = (
    """
    ALTER TABLE artifact_lifecycle
    ADD COLUMN bytes_delete_intent_at TEXT NULL
    """,
    """
    ALTER TABLE artifact_lifecycle
    ADD COLUMN bytes_delete_dev INTEGER NULL
    """,
    """
    ALTER TABLE artifact_lifecycle
    ADD COLUMN bytes_delete_ino INTEGER NULL
    """,
    """
    ALTER TABLE artifact_lifecycle
    ADD COLUMN bytes_delete_phase TEXT NULL
    """,
)


_MIGRATION_V10_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE artifact_lifecycle_v10 (
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
        bytes_delete_intent_at TEXT NULL,
        bytes_delete_dev INTEGER NULL,
        bytes_delete_ino INTEGER NULL,
        bytes_delete_phase TEXT NULL,
        CHECK (
            (
                bytes_delete_intent_at IS NULL
                AND bytes_delete_dev IS NULL
                AND bytes_delete_ino IS NULL
                AND bytes_delete_phase IS NULL
            )
            OR (
                bytes_delete_intent_at IS NOT NULL
                AND bytes_delete_dev IS NOT NULL
                AND bytes_delete_ino IS NOT NULL
                AND bytes_delete_phase IN ('quarantined', 'detached')
            )
        )
    )
    """,
    """
    INSERT INTO artifact_lifecycle_v10 (
        artifact_id,
        repository_scope,
        media_type,
        size_bytes,
        raw_sha256,
        created_at,
        updated_at,
        consumed_by_operation_id,
        consumed_at,
        bytes_deleted_at,
        bytes_delete_intent_at,
        bytes_delete_dev,
        bytes_delete_ino,
        bytes_delete_phase
    )
    SELECT
        artifact_id,
        repository_scope,
        media_type,
        size_bytes,
        raw_sha256,
        created_at,
        updated_at,
        consumed_by_operation_id,
        consumed_at,
        bytes_deleted_at,
        bytes_delete_intent_at,
        bytes_delete_dev,
        bytes_delete_ino,
        bytes_delete_phase
    FROM artifact_lifecycle
    """,
    """
    DROP TABLE artifact_lifecycle
    """,
    """
    ALTER TABLE artifact_lifecycle_v10 RENAME TO artifact_lifecycle
    """,
    """
    CREATE INDEX artifact_lifecycle_repository_scope_idx
    ON artifact_lifecycle (repository_scope)
    """,
)


_MIGRATION_V11_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE artifact_lifecycle_v11 (
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
        bytes_delete_intent_at TEXT NULL,
        bytes_delete_dev INTEGER NULL,
        bytes_delete_ino INTEGER NULL,
        bytes_delete_phase TEXT NULL,
        bytes_delete_generation TEXT NULL,
        bytes_deleted_receipt_dev INTEGER NULL,
        bytes_deleted_receipt_ino INTEGER NULL,
        bytes_deleted_receipt_generation TEXT NULL,
        CHECK (
            (
                bytes_delete_intent_at IS NULL
                AND bytes_delete_dev IS NULL
                AND bytes_delete_ino IS NULL
                AND bytes_delete_phase IS NULL
                AND bytes_delete_generation IS NULL
            )
            OR (
                bytes_delete_intent_at IS NOT NULL
                AND bytes_delete_dev IS NOT NULL
                AND bytes_delete_ino IS NOT NULL
                AND bytes_delete_phase IN ('quarantined', 'detached')
                AND bytes_delete_generation IS NOT NULL
            )
        ),
        CHECK (
            (
                bytes_deleted_receipt_dev IS NULL
                AND bytes_deleted_receipt_ino IS NULL
                AND bytes_deleted_receipt_generation IS NULL
            )
            OR (
                bytes_deleted_at IS NOT NULL
                AND bytes_deleted_receipt_dev IS NOT NULL
                AND bytes_deleted_receipt_ino IS NOT NULL
                AND bytes_deleted_receipt_generation IS NOT NULL
            )
        )
    )
    """,
    """
    INSERT INTO artifact_lifecycle_v11 (
        artifact_id,
        repository_scope,
        media_type,
        size_bytes,
        raw_sha256,
        created_at,
        updated_at,
        consumed_by_operation_id,
        consumed_at,
        bytes_deleted_at,
        bytes_delete_intent_at,
        bytes_delete_dev,
        bytes_delete_ino,
        bytes_delete_phase,
        bytes_delete_generation,
        bytes_deleted_receipt_dev,
        bytes_deleted_receipt_ino,
        bytes_deleted_receipt_generation
    )
    SELECT
        artifact_id,
        repository_scope,
        media_type,
        size_bytes,
        raw_sha256,
        created_at,
        updated_at,
        consumed_by_operation_id,
        consumed_at,
        bytes_deleted_at,
        bytes_delete_intent_at,
        bytes_delete_dev,
        bytes_delete_ino,
        bytes_delete_phase,
        CASE
            WHEN bytes_delete_intent_at IS NOT NULL
            THEN lower(hex(randomblob(16)))
            ELSE NULL
        END,
        NULL,
        NULL,
        NULL
    FROM artifact_lifecycle
    """,
    """
    DROP TABLE artifact_lifecycle
    """,
    """
    ALTER TABLE artifact_lifecycle_v11 RENAME TO artifact_lifecycle
    """,
    """
    CREATE INDEX artifact_lifecycle_repository_scope_idx
    ON artifact_lifecycle (repository_scope)
    """,
)


_MIGRATION_V12_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE artifact_lifecycle_v12 (
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
        bytes_delete_intent_at TEXT NULL,
        bytes_delete_dev INTEGER NULL,
        bytes_delete_ino INTEGER NULL,
        bytes_delete_phase TEXT NULL,
        bytes_delete_generation TEXT NULL,
        bytes_deleted_receipt_dev INTEGER NULL,
        bytes_deleted_receipt_ino INTEGER NULL,
        bytes_deleted_receipt_generation TEXT NULL,
        CHECK (
            (
                bytes_delete_intent_at IS NULL
                AND bytes_delete_dev IS NULL
                AND bytes_delete_ino IS NULL
                AND bytes_delete_phase IS NULL
                AND bytes_delete_generation IS NULL
            )
            OR (
                bytes_delete_intent_at IS NOT NULL
                AND bytes_delete_dev IS NOT NULL
                AND bytes_delete_ino IS NOT NULL
                AND bytes_delete_phase IN ('quarantined', 'detached')
                AND bytes_delete_generation IS NOT NULL
            )
        ),
        CHECK (
            (
                bytes_deleted_receipt_dev IS NULL
                AND bytes_deleted_receipt_ino IS NULL
                AND bytes_deleted_receipt_generation IS NULL
            )
            OR (
                bytes_deleted_at IS NOT NULL
                AND bytes_deleted_receipt_dev IS NOT NULL
                AND bytes_deleted_receipt_ino IS NOT NULL
                AND bytes_deleted_receipt_generation IS NOT NULL
            )
        ),
        CHECK (
            bytes_deleted_at IS NULL
            OR (
                bytes_delete_intent_at IS NULL
                AND bytes_delete_dev IS NULL
                AND bytes_delete_ino IS NULL
                AND bytes_delete_phase IS NULL
                AND bytes_delete_generation IS NULL
            )
        )
    )
    """,
    """
    INSERT INTO artifact_lifecycle_v12 (
        artifact_id,
        repository_scope,
        media_type,
        size_bytes,
        raw_sha256,
        created_at,
        updated_at,
        consumed_by_operation_id,
        consumed_at,
        bytes_deleted_at,
        bytes_delete_intent_at,
        bytes_delete_dev,
        bytes_delete_ino,
        bytes_delete_phase,
        bytes_delete_generation,
        bytes_deleted_receipt_dev,
        bytes_deleted_receipt_ino,
        bytes_deleted_receipt_generation
    )
    SELECT
        artifact_id,
        repository_scope,
        media_type,
        size_bytes,
        raw_sha256,
        created_at,
        updated_at,
        consumed_by_operation_id,
        consumed_at,
        bytes_deleted_at,
        bytes_delete_intent_at,
        bytes_delete_dev,
        bytes_delete_ino,
        bytes_delete_phase,
        bytes_delete_generation,
        bytes_deleted_receipt_dev,
        bytes_deleted_receipt_ino,
        bytes_deleted_receipt_generation
    FROM artifact_lifecycle
    """,
    """
    DROP TABLE artifact_lifecycle
    """,
    """
    ALTER TABLE artifact_lifecycle_v12 RENAME TO artifact_lifecycle
    """,
    """
    CREATE INDEX artifact_lifecycle_repository_scope_idx
    ON artifact_lifecycle (repository_scope)
    """,
)


_MIGRATION_V13_STATEMENTS: tuple[str, ...] = (
    """
    CREATE INDEX artifact_lifecycle_cleanup_keyset_idx
    ON artifact_lifecycle (created_at, artifact_id)
    WHERE bytes_deleted_at IS NULL
    """,
)


_MIGRATION_V14_STATEMENTS: tuple[str, ...] = (
    """
    ALTER TABLE artifact_lifecycle ADD COLUMN cleanup_seq INTEGER
    """,
    """
    UPDATE artifact_lifecycle SET cleanup_seq = rowid WHERE cleanup_seq IS NULL
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
    CREATE TRIGGER artifact_lifecycle_assign_cleanup_seq
    AFTER INSERT ON artifact_lifecycle
    FOR EACH ROW
    WHEN NEW.cleanup_seq IS NULL
    BEGIN
        UPDATE artifact_lifecycle
        SET cleanup_seq = (
            SELECT COALESCE(MAX(cleanup_seq), 0) + 1 FROM artifact_lifecycle
        )
        WHERE artifact_id = NEW.artifact_id AND cleanup_seq IS NULL;
    END
    """,
    """
    CREATE TABLE artifact_residual (
        residual_id INTEGER PRIMARY KEY AUTOINCREMENT,
        artifact_id TEXT NOT NULL,
        repository_scope TEXT NOT NULL,
        kind TEXT NOT NULL CHECK (
            kind IN ('deleting', 'detach', 'verify', 'stage', 'stage_child')
        ),
        name TEXT NOT NULL,
        parent_name TEXT NOT NULL DEFAULT '',
        dev INTEGER NOT NULL,
        ino INTEGER NOT NULL,
        generation TEXT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (artifact_id, kind, name, parent_name)
    )
    """,
)


_MIGRATION_V15_STATEMENTS: tuple[str, ...] = (
    """
    DROP TRIGGER IF EXISTS artifact_lifecycle_assign_cleanup_seq
    """,
    """
    DROP INDEX IF EXISTS artifact_lifecycle_cleanup_seq_uidx
    """,
    """
    DROP INDEX IF EXISTS artifact_lifecycle_cleanup_seq_idx
    """,
    """
    DROP INDEX IF EXISTS artifact_lifecycle_cleanup_keyset_idx
    """,
    """
    DROP INDEX IF EXISTS artifact_lifecycle_repository_scope_idx
    """,
    """
    CREATE TABLE artifact_lifecycle_v15 (
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
        bytes_delete_intent_at TEXT NULL,
        bytes_delete_dev INTEGER NULL,
        bytes_delete_ino INTEGER NULL,
        bytes_delete_phase TEXT NULL,
        bytes_delete_generation TEXT NULL,
        bytes_deleted_receipt_dev INTEGER NULL,
        bytes_deleted_receipt_ino INTEGER NULL,
        bytes_deleted_receipt_generation TEXT NULL,
        cleanup_seq INTEGER NOT NULL CHECK (
            typeof(cleanup_seq) = 'integer' AND cleanup_seq > 0
        ),
        CHECK (
            (
                bytes_delete_intent_at IS NULL
                AND bytes_delete_dev IS NULL
                AND bytes_delete_ino IS NULL
                AND bytes_delete_phase IS NULL
                AND bytes_delete_generation IS NULL
            )
            OR (
                bytes_delete_intent_at IS NOT NULL
                AND bytes_delete_dev IS NOT NULL
                AND bytes_delete_ino IS NOT NULL
                AND bytes_delete_phase IN ('quarantined', 'detached')
                AND bytes_delete_generation IS NOT NULL
            )
        ),
        CHECK (
            (
                bytes_deleted_receipt_dev IS NULL
                AND bytes_deleted_receipt_ino IS NULL
                AND bytes_deleted_receipt_generation IS NULL
            )
            OR (
                bytes_deleted_at IS NOT NULL
                AND bytes_deleted_receipt_dev IS NOT NULL
                AND bytes_deleted_receipt_ino IS NOT NULL
                AND bytes_deleted_receipt_generation IS NOT NULL
            )
        ),
        CHECK (
            bytes_deleted_at IS NULL
            OR (
                bytes_delete_intent_at IS NULL
                AND bytes_delete_dev IS NULL
                AND bytes_delete_ino IS NULL
                AND bytes_delete_phase IS NULL
                AND bytes_delete_generation IS NULL
            )
        )
    )
    """,
    """
    INSERT INTO artifact_lifecycle_v15 (
        artifact_id,
        repository_scope,
        media_type,
        size_bytes,
        raw_sha256,
        created_at,
        updated_at,
        consumed_by_operation_id,
        consumed_at,
        bytes_deleted_at,
        bytes_delete_intent_at,
        bytes_delete_dev,
        bytes_delete_ino,
        bytes_delete_phase,
        bytes_delete_generation,
        bytes_deleted_receipt_dev,
        bytes_deleted_receipt_ino,
        bytes_deleted_receipt_generation,
        cleanup_seq
    )
    SELECT
        artifact_id,
        repository_scope,
        media_type,
        size_bytes,
        raw_sha256,
        created_at,
        updated_at,
        consumed_by_operation_id,
        consumed_at,
        bytes_deleted_at,
        bytes_delete_intent_at,
        bytes_delete_dev,
        bytes_delete_ino,
        bytes_delete_phase,
        bytes_delete_generation,
        bytes_deleted_receipt_dev,
        bytes_deleted_receipt_ino,
        bytes_deleted_receipt_generation,
        rowid
    FROM artifact_lifecycle
    """,
    """
    DROP TABLE artifact_lifecycle
    """,
    """
    ALTER TABLE artifact_lifecycle_v15 RENAME TO artifact_lifecycle
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
)


_MIGRATION_V16_ADD_MANUAL_RECOVERY_COLUMN = """
    ALTER TABLE repository_import_operations
    ADD COLUMN manual_recovery_required INTEGER NOT NULL DEFAULT 0
        CHECK (manual_recovery_required IN (0, 1))
"""

_MIGRATION_V16_MANUAL_BARRIER_INDEX = """
    CREATE INDEX repository_import_operations_manual_barrier_idx
    ON repository_import_operations (repository_scope)
    WHERE manual_recovery_required = 1
"""

_MALFORMED_FAILED_IMPORT_EVIDENCE_MESSAGE = (
    "malformed FAILED import evidence blocks migration; "
    "operator intervention is required before migration"
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


def _admin_cli_ddl_signature(sql: str) -> str:
    return sql.strip()


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


def _sqlite_master_ddl(
    connection: sqlite3.Connection,
    *,
    object_type: str,
    object_name: str,
) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = ? AND name = ?",
        (object_type, object_name),
    ).fetchone()
    if row is None or row[0] is None:
        raise ControlDbError(
            f"reference control database schema is missing {object_type} {object_name}"
        )
    return _admin_cli_ddl_signature(str(row[0]))


@lru_cache(maxsize=1)
def _admin_cli_reference_schema() -> tuple[
    dict[str, ColumnShape],
    dict[str, tuple[str, ...]],
    dict[str, str],
    dict[str, str],
    dict[str, str],
]:
    connection = sqlite3.connect(":memory:")
    configure_connection(connection)
    connection.execute("PRAGMA foreign_keys = ON")
    ControlStore._migrate(connection, expected_version=CONTROL_DB_USER_VERSION)
    column_shapes = {
        table_name: _table_column_shape(connection, table_name)
        for table_name in sorted(_ADMIN_CLI_REQUIRED_TABLES)
    }
    index_columns = {
        index_name: _index_column_names(connection, index_name)
        for index_name in sorted(_ADMIN_CLI_REQUIRED_INDEXES)
    }
    table_ddl = {
        table_name: _sqlite_master_ddl(connection, object_type="table", object_name=table_name)
        for table_name in sorted(_ADMIN_CLI_REQUIRED_TABLES)
    }
    index_ddl = {
        index_name: _sqlite_master_ddl(connection, object_type="index", object_name=index_name)
        for index_name in sorted(_ADMIN_CLI_REQUIRED_INDEXES)
    }
    trigger_sql: dict[str, str] = {}
    for trigger_name in sorted(_ADMIN_CLI_REQUIRED_TRIGGER_NAMES):
        trigger_sql[trigger_name] = _sqlite_master_ddl(
            connection,
            object_type="trigger",
            object_name=trigger_name,
        )
    connection.close()
    return column_shapes, index_columns, trigger_sql, table_ddl, index_ddl


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
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise ControlDbError("control database is unreadable") from exc
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
        except sqlite3.Error as exc:
            raise ControlDbError("control database is unreadable") from exc
        finally:
            connection.close()

    @classmethod
    def open_readonly(cls, path: Path, *, expected_version: int) -> Self:
        cls.preflight_exact_version(path, expected_version=expected_version)
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
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
        if allow_migration:
            path.parent.mkdir(parents=True, exist_ok=True)
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
                user_version = cls._migrate(connection, expected_version=expected_version)
                cls._verify_synchronous_full(connection)
            else:
                cls._require_wal_mode(connection)
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
                cls._require_synchronous_full(connection)
            cls._verify_foreign_keys(connection)
            return cls(path=path, connection=connection, user_version=user_version)
        except sqlite3.Error as exc:
            connection.close()
            raise ControlDbError("control database is unreadable") from exc
        except Exception:
            connection.close()
            raise

    @staticmethod
    def _verify_admin_schema(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        present_tables = {str(row[0]) for row in rows}
        missing_tables = _ADMIN_CLI_REQUIRED_TABLES.difference(present_tables)
        if missing_tables:
            missing = ", ".join(sorted(missing_tables))
            raise ControlDbError(
                f"control database schema is missing required tables: {missing}"
            )

        reference_columns, reference_indexes, reference_triggers, reference_table_ddl, reference_index_ddl = (
            _admin_cli_reference_schema()
        )
        for table_name, expected_shape in reference_columns.items():
            actual_shape = _table_column_shape(connection, table_name)
            if actual_shape != expected_shape:
                raise ControlDbError(
                    f"control database schema has invalid column shape on {table_name}"
                )

        for table_name, expected_ddl in reference_table_ddl.items():
            row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            ).fetchone()
            if row is None or row[0] is None:
                raise ControlDbError(
                    f"control database schema is missing required table DDL: {table_name}"
                )
            actual_ddl = _admin_cli_ddl_signature(str(row[0]))
            if actual_ddl != expected_ddl:
                raise ControlDbError(
                    f"control database schema has invalid table DDL on {table_name}"
                )

        for index_name, expected_columns in reference_indexes.items():
            index_row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?",
                (index_name,),
            ).fetchone()
            if index_row is None:
                raise ControlDbError(
                    f"control database schema is missing required index: {index_name}"
                )
            actual_columns = _index_column_names(connection, index_name)
            if actual_columns != expected_columns:
                raise ControlDbError(
                    f"control database schema has invalid index columns on {index_name}"
                )

        for index_name, expected_ddl in reference_index_ddl.items():
            row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
                (index_name,),
            ).fetchone()
            if row is None or row[0] is None:
                raise ControlDbError(
                    f"control database schema is missing required index DDL: {index_name}"
                )
            actual_ddl = _admin_cli_ddl_signature(str(row[0]))
            if actual_ddl != expected_ddl:
                raise ControlDbError(
                    f"control database schema has invalid index DDL on {index_name}"
                )

        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()
        if journal_mode is None or str(journal_mode[0]).upper() != "WAL":
            raise ControlDbError("control database WAL mode is unavailable")

        for trigger_name, expected_sql in reference_triggers.items():
            row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
                (trigger_name,),
            ).fetchone()
            if row is None or row[0] is None:
                raise ControlDbError(
                    f"control database schema is missing required triggers: {trigger_name}"
                )
            actual_sql = _admin_cli_ddl_signature(str(row[0]))
            if actual_sql != expected_sql:
                raise ControlDbError(
                    f"control database schema has invalid trigger body: {trigger_name}"
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
    def _validate_artifact_delete_intent_rows(connection: sqlite3.Connection) -> None:
        """Fail closed when intent columns are partial or illegally shaped."""

        from gateway_repository_service.artifact_retention import parse_durable_timestamp

        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(artifact_lifecycle)").fetchall()
        }
        required = {
            "bytes_delete_intent_at",
            "bytes_delete_dev",
            "bytes_delete_ino",
            "bytes_delete_phase",
        }
        if not required.issubset(columns):
            return

        has_generation = "bytes_delete_generation" in columns
        has_bytes_deleted_at = "bytes_deleted_at" in columns

        select_columns = [
            "bytes_delete_intent_at",
            "bytes_delete_dev",
            "bytes_delete_ino",
            "bytes_delete_phase",
        ]
        if has_generation:
            select_columns.append("bytes_delete_generation")
        if has_bytes_deleted_at:
            select_columns.append("bytes_deleted_at")

        rows = connection.execute(
            f"SELECT {', '.join(select_columns)} FROM artifact_lifecycle"
        ).fetchall()

        def malformed() -> None:
            raise ControlDbError(
                "malformed artifact delete intent blocks migration; "
                "operator intervention is required before migration"
            )

        for row in rows:
            intent_at = row[0]
            intent_dev = row[1]
            intent_ino = row[2]
            phase = row[3]
            column_index = 4
            generation = row[column_index] if has_generation else None
            if has_generation:
                column_index += 1
            bytes_deleted_at = row[column_index] if has_bytes_deleted_at else None

            intent_fields: list[object | None] = [intent_at, intent_dev, intent_ino, phase]
            if has_generation:
                intent_fields.append(generation)

            intent_present = any(field is not None for field in intent_fields)
            if intent_present:
                if not all(field is not None for field in intent_fields):
                    malformed()
                if phase not in ("quarantined", "detached"):
                    malformed()
                if parse_durable_timestamp(str(intent_at)) is None:
                    malformed()
            elif any(field is not None for field in intent_fields):
                malformed()

            if has_bytes_deleted_at and bytes_deleted_at is not None:
                if any(field is not None for field in intent_fields):
                    malformed()

    @staticmethod
    def _manual_recovery_required_for_failed_error_json(error_json: object) -> int:
        from pydantic import ValidationError

        from gateway_repository_contracts import SimpleError
        from gateway_repository_service.versioned_import.models import (
            MANUAL_RECOVERY_REQUIRED_CODE,
            ORDINARY_TERMINAL_ERROR_CODES,
        )

        if error_json is None:
            raise ControlDbError(_MALFORMED_FAILED_IMPORT_EVIDENCE_MESSAGE)
        try:
            parsed = json.loads(str(error_json))
            error = SimpleError.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            raise ControlDbError(_MALFORMED_FAILED_IMPORT_EVIDENCE_MESSAGE) from exc
        if error.code == MANUAL_RECOVERY_REQUIRED_CODE:
            return 1
        if error.code in ORDINARY_TERMINAL_ERROR_CODES:
            return 0
        raise ControlDbError(_MALFORMED_FAILED_IMPORT_EVIDENCE_MESSAGE)

    @staticmethod
    def _backfill_manual_recovery_required(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT operation_id, error_json
            FROM repository_import_operations
            WHERE status = 'FAILED'
            """
        ).fetchall()
        for row in rows:
            flag = ControlStore._manual_recovery_required_for_failed_error_json(row["error_json"])
            connection.execute(
                """
                UPDATE repository_import_operations
                SET manual_recovery_required = ?
                WHERE operation_id = ?
                """,
                (flag, str(row["operation_id"])),
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
        if target_version == 8:
            ControlStore._execute_statements(connection, _MIGRATION_V8_STATEMENTS)
            return
        if target_version == 9:
            ControlStore._execute_statements(connection, _MIGRATION_V9_STATEMENTS)
            return
        if target_version == 10:
            ControlStore._validate_artifact_delete_intent_rows(connection)
            ControlStore._execute_statements(connection, _MIGRATION_V10_STATEMENTS)
            return
        if target_version == 11:
            ControlStore._validate_artifact_delete_intent_rows(connection)
            ControlStore._execute_statements(connection, _MIGRATION_V11_STATEMENTS)
            return
        if target_version == 12:
            ControlStore._validate_artifact_delete_intent_rows(connection)
            ControlStore._execute_statements(connection, _MIGRATION_V12_STATEMENTS)
            return
        if target_version == 13:
            ControlStore._execute_statements(connection, _MIGRATION_V13_STATEMENTS)
            return
        if target_version == 14:
            ControlStore._execute_statements(connection, _MIGRATION_V14_STATEMENTS)
            return
        if target_version == 15:
            ControlStore._execute_statements(connection, _MIGRATION_V15_STATEMENTS)
            return
        if target_version == 16:
            connection.execute(_MIGRATION_V16_ADD_MANUAL_RECOVERY_COLUMN)
            ControlStore._backfill_manual_recovery_required(connection)
            connection.execute(_MIGRATION_V16_MANUAL_BARRIER_INDEX)
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
