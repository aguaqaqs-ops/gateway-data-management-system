"""Forward-only Operations schema migration owned by the control DB boundary."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from gateway_backend.operations import StoreBusy, UnsupportedSchemaVersion

OPERATIONS_SCHEMA_COMPONENT = "operations"
OPERATIONS_SCHEMA_VERSION = 1

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_SQLITE_INT_MIN = -(2**63)
_SQLITE_INT_MAX = 2**63 - 1

_OPERATION_STATUSES = (
    "'QUEUED'",
    "'RUNNING'",
    "'SUCCEEDED'",
    "'FAILED'",
    "'CANCELLED'",
    "'SUPERSEDED'",
    "'MANUAL_RECOVERY_REQUIRED'",
)
_STEP_STATUSES = (
    "'PENDING'",
    "'RUNNING'",
    "'RETRY_WAIT'",
    "'SUCCEEDED'",
    "'FAILED'",
    "'CANCELLED'",
    "'MANUAL_RECOVERY_REQUIRED'",
)
_ACTIVE_STEP_STATUSES = (
    "'PENDING'",
    "'RUNNING'",
    "'RETRY_WAIT'",
    "'MANUAL_RECOVERY_REQUIRED'",
)
_CLAIMABLE_STEP_STATUSES = ("'PENDING'", "'RETRY_WAIT'")


def bootstrap_control_schema(
    connection: sqlite3.Connection,
    *,
    now: Callable[[], datetime],
) -> None:
    """Apply the Operations schema atomically if the component is not at v1."""

    if connection.in_transaction:
        raise ValueError("schema bootstrap requires a connection outside a transaction")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(_MIGRATION_LEDGER_DDL)
        current_version = _current_component_version(connection)
        if current_version > OPERATIONS_SCHEMA_VERSION:
            raise UnsupportedSchemaVersion(
                f"component {OPERATIONS_SCHEMA_COMPONENT!r} is newer than supported schema"
            )
        if current_version == OPERATIONS_SCHEMA_VERSION:
            connection.execute("COMMIT")
            return
        if current_version != 0:
            raise RuntimeError("unsupported migration history")
        _apply_operations_v1(connection)
        applied_at_us = _datetime_to_epoch_us(now())
        connection.execute(
            "INSERT INTO control_schema_migrations(component, version, applied_at_us) VALUES (?, ?, ?)",
            (OPERATIONS_SCHEMA_COMPONENT, OPERATIONS_SCHEMA_VERSION, applied_at_us),
        )
        connection.execute("COMMIT")
    except UnsupportedSchemaVersion:
        _rollback_if_needed(connection)
        raise
    except sqlite3.OperationalError as exc:
        _rollback_if_needed(connection)
        if "busy" in str(exc).lower() or "locked" in str(exc).lower():
            raise StoreBusy("control DB is busy") from None
        raise
    except BaseException:
        _rollback_if_needed(connection)
        raise


def _apply_operations_v1(connection: sqlite3.Connection) -> None:
    statements = _operations_v1_statements()
    for statement in statements:
        connection.execute(statement)


def _current_component_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) FROM control_schema_migrations WHERE component = ?",
        (OPERATIONS_SCHEMA_COMPONENT,),
    ).fetchone()
    version = row[0]
    if version is None:
        return 0
    if type(version) is not int or version < 0:
        raise RuntimeError("migration ledger contains an invalid version")
    return version


def _rollback_if_needed(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.execute("ROLLBACK")


def _datetime_to_epoch_us(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("migration clock must return aware UTC datetime")
    delta = value - _EPOCH
    micros = (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    if micros < _SQLITE_INT_MIN or micros > _SQLITE_INT_MAX:
        raise ValueError("timestamp is outside SQLite INTEGER range")
    return micros


_MIGRATION_LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS control_schema_migrations (
    component TEXT NOT NULL
        CHECK (typeof(component) = 'text' AND length(component) > 0),
    version INTEGER NOT NULL
        CHECK (typeof(version) = 'integer' AND version > 0),
    applied_at_us INTEGER NOT NULL
        CHECK (typeof(applied_at_us) = 'integer'),
    PRIMARY KEY (component, version)
)
"""


def _operations_v1_statements() -> tuple[str, ...]:
    operation_statuses = ", ".join(_OPERATION_STATUSES)
    step_statuses = ", ".join(_STEP_STATUSES)
    active_step_statuses = ", ".join(_ACTIVE_STEP_STATUSES)
    claimable_step_statuses = ", ".join(_CLAIMABLE_STEP_STATUSES)
    return (
        f"""
        CREATE TABLE operation_records (
            operation_id TEXT NOT NULL PRIMARY KEY
                CHECK (typeof(operation_id) = 'text' AND length(operation_id) BETWEEN 1 AND 255),
            contract_version TEXT NOT NULL
                CHECK (typeof(contract_version) = 'text' AND length(contract_version) BETWEEN 1 AND 128),
            optimistic_version INTEGER NOT NULL
                CHECK (typeof(optimistic_version) = 'integer' AND optimistic_version >= 0),
            job_kind TEXT NOT NULL
                CHECK (typeof(job_kind) = 'text' AND length(job_kind) BETWEEN 1 AND 128),
            job_contract_version TEXT NOT NULL
                CHECK (typeof(job_contract_version) = 'text' AND length(job_contract_version) BETWEEN 1 AND 128),
            job_payload BLOB
                CHECK (job_payload IS NULL OR typeof(job_payload) = 'blob'),
            job_payload_ref BLOB
                CHECK (job_payload_ref IS NULL OR typeof(job_payload_ref) = 'blob'),
            business_refs BLOB NOT NULL
                CHECK (typeof(business_refs) = 'blob'),
            artifact_refs BLOB NOT NULL
                CHECK (typeof(artifact_refs) = 'blob'),
            repository_operation_id TEXT
                CHECK (repository_operation_id IS NULL OR
                       (typeof(repository_operation_id) = 'text' AND length(repository_operation_id) BETWEEN 1 AND 255)),
            checkpoint_ref BLOB
                CHECK (checkpoint_ref IS NULL OR typeof(checkpoint_ref) = 'blob'),
            ready_closure_ref BLOB
                CHECK (ready_closure_ref IS NULL OR typeof(ready_closure_ref) = 'blob'),
            status TEXT NOT NULL
                CHECK (typeof(status) = 'text' AND status IN ({operation_statuses})),
            diagnostic BLOB
                CHECK (diagnostic IS NULL OR typeof(diagnostic) = 'blob'),
            cancel_requested INTEGER NOT NULL
                CHECK (typeof(cancel_requested) = 'integer' AND cancel_requested IN (0, 1)),
            created_at_us INTEGER NOT NULL
                CHECK (typeof(created_at_us) = 'integer'),
            updated_at_us INTEGER NOT NULL
                CHECK (typeof(updated_at_us) = 'integer'),
            completed_at_us INTEGER
                CHECK (completed_at_us IS NULL OR typeof(completed_at_us) = 'integer')
        )
        """,
        f"""
        CREATE TABLE step_records (
            step_id TEXT NOT NULL PRIMARY KEY
                CHECK (typeof(step_id) = 'text' AND length(step_id) BETWEEN 1 AND 255),
            operation_id TEXT NOT NULL
                CHECK (typeof(operation_id) = 'text' AND length(operation_id) BETWEEN 1 AND 255),
            contract_version TEXT NOT NULL
                CHECK (typeof(contract_version) = 'text' AND length(contract_version) BETWEEN 1 AND 128),
            optimistic_version INTEGER NOT NULL
                CHECK (typeof(optimistic_version) = 'integer' AND optimistic_version >= 0),
            step_name TEXT NOT NULL
                CHECK (typeof(step_name) = 'text' AND length(step_name) BETWEEN 1 AND 128),
            attempt_count INTEGER NOT NULL
                CHECK (typeof(attempt_count) = 'integer' AND attempt_count >= 0),
            status TEXT NOT NULL
                CHECK (typeof(status) = 'text' AND status IN ({step_statuses})),
            diagnostic BLOB
                CHECK (diagnostic IS NULL OR typeof(diagnostic) = 'blob'),
            cancel_requested INTEGER NOT NULL
                CHECK (typeof(cancel_requested) = 'integer' AND cancel_requested IN (0, 1)),
            retry_not_before_us INTEGER
                CHECK (retry_not_before_us IS NULL OR typeof(retry_not_before_us) = 'integer'),
            worker_id TEXT
                CHECK (worker_id IS NULL OR (typeof(worker_id) = 'text' AND length(worker_id) BETWEEN 1 AND 255)),
            lease_token TEXT
                CHECK (lease_token IS NULL OR (typeof(lease_token) = 'text' AND length(lease_token) BETWEEN 1 AND 255)),
            lease_expires_at_us INTEGER
                CHECK (lease_expires_at_us IS NULL OR typeof(lease_expires_at_us) = 'integer'),
            checkpoint_ref BLOB
                CHECK (checkpoint_ref IS NULL OR typeof(checkpoint_ref) = 'blob'),
            prior_output_refs BLOB NOT NULL
                CHECK (typeof(prior_output_refs) = 'blob'),
            created_at_us INTEGER NOT NULL
                CHECK (typeof(created_at_us) = 'integer'),
            updated_at_us INTEGER NOT NULL
                CHECK (typeof(updated_at_us) = 'integer'),
            started_at_us INTEGER
                CHECK (started_at_us IS NULL OR typeof(started_at_us) = 'integer'),
            completed_at_us INTEGER
                CHECK (completed_at_us IS NULL OR typeof(completed_at_us) = 'integer'),
            eligible_at_us INTEGER
                CHECK (eligible_at_us IS NULL OR typeof(eligible_at_us) = 'integer'),
            UNIQUE (operation_id, step_name),
            FOREIGN KEY (operation_id) REFERENCES operation_records(operation_id) ON DELETE RESTRICT
        )
        """,
        f"""
        CREATE UNIQUE INDEX step_records_one_active_per_operation
        ON step_records(operation_id)
        WHERE status IN ({active_step_statuses})
        """,
        f"""
        CREATE INDEX step_records_claim_order
        ON step_records(status, eligible_at_us, created_at_us, step_id)
        WHERE status IN ({claimable_step_statuses})
        """,
        """
        CREATE INDEX operation_records_status_readback
        ON operation_records(status, updated_at_us, operation_id)
        """,
    )
