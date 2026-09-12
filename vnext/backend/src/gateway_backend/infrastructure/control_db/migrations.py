"""Forward-only control DB schema migrations owned by the control DB boundary."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from gateway_backend.operations import StoreBusy, UnsupportedSchemaVersion

OPERATIONS_SCHEMA_COMPONENT = "operations"
OPERATIONS_SCHEMA_VERSION = 1
WORKSPACE_SCHEMA_COMPONENT = "workspace"
WORKSPACE_SCHEMA_VERSION = 2

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
_WORKSPACE_STATES = ("'OPEN'", "'CLOSED'")
_INPUT_COMPLETENESS = ("'FULL'", "'MODIFIED_ONLY'")


def bootstrap_control_schema(
    connection: sqlite3.Connection,
    *,
    now: Callable[[], datetime],
) -> None:
    """Apply Operations schema steps until the component reaches the supported version."""

    _bootstrap_component_schema(
        connection,
        component=OPERATIONS_SCHEMA_COMPONENT,
        target_version=OPERATIONS_SCHEMA_VERSION,
        steps={1: _apply_operations_v1},
        now=now,
    )


def bootstrap_workspace_schema(
    connection: sqlite3.Connection,
    *,
    now: Callable[[], datetime],
) -> None:
    """Apply Workspace schema steps until the component reaches the supported version."""

    _bootstrap_component_schema(
        connection,
        component=WORKSPACE_SCHEMA_COMPONENT,
        target_version=WORKSPACE_SCHEMA_VERSION,
        steps={1: _apply_workspace_v1, 2: _apply_workspace_v2},
        now=now,
    )


def _bootstrap_component_schema(
    connection: sqlite3.Connection,
    *,
    component: str,
    target_version: int,
    steps: Mapping[int, Callable[[sqlite3.Connection], None]],
    now: Callable[[], datetime],
) -> None:
    if connection.in_transaction:
        raise ValueError("schema bootstrap requires a connection outside a transaction")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(_MIGRATION_LEDGER_DDL)
        current_version = _current_component_version(connection, component)
        if current_version > target_version:
            raise UnsupportedSchemaVersion(
                f"component {component!r} is newer than supported schema"
            )
        if current_version == target_version:
            connection.execute("COMMIT")
            return
        while current_version < target_version:
            next_version = current_version + 1
            apply = steps.get(next_version)
            if apply is None:
                raise RuntimeError("unsupported migration history")
            apply(connection)
            applied_at_us = _datetime_to_epoch_us(now())
            connection.execute(
                "INSERT INTO control_schema_migrations(component, version, applied_at_us) VALUES (?, ?, ?)",
                (component, next_version, applied_at_us),
            )
            current_version = next_version
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


def _apply_workspace_v1(connection: sqlite3.Connection) -> None:
    statements = _workspace_v1_statements()
    for statement in statements:
        connection.execute(statement)
    _assert_workspace_bootstrap_integrity(connection)


def _apply_workspace_v2(connection: sqlite3.Connection) -> None:
    connection.execute(_PREVIEW_IDEMPOTENCY_V2_DDL)
    _copy_preview_idempotency_to_v2(connection)
    connection.execute("DROP TABLE preview_idempotency_records")
    connection.execute(
        "ALTER TABLE preview_idempotency_records_v2 RENAME TO preview_idempotency_records"
    )
    for statement in _workspace_v2_statements():
        connection.execute(statement)


def _assert_workspace_bootstrap_integrity(connection: sqlite3.Connection) -> None:
    duplicate_open = connection.execute(
        """
        SELECT owner_actor_id, gateway_device_external_key, business_project_id, COUNT(*) AS open_count
        FROM workspace_records
        WHERE state = 'OPEN'
        GROUP BY owner_actor_id, gateway_device_external_key, business_project_id
        HAVING open_count > 1
        """
    ).fetchone()
    if duplicate_open is not None:
        raise RuntimeError("workspace bootstrap found multiple OPEN rows for one exact scope")


def _current_component_version(connection: sqlite3.Connection, component: str) -> int:
    row = connection.execute(
        "SELECT MAX(version) FROM control_schema_migrations WHERE component = ?",
        (component,),
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


def _workspace_v1_statements() -> tuple[str, ...]:
    workspace_states = ", ".join(_WORKSPACE_STATES)
    input_completeness = ", ".join(_INPUT_COMPLETENESS)
    return (
        f"""
        CREATE TABLE workspace_records (
            workspace_id TEXT NOT NULL PRIMARY KEY
                CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
            owner_actor_id TEXT NOT NULL
                CHECK (typeof(owner_actor_id) = 'text' AND length(owner_actor_id) BETWEEN 1 AND 255),
            gateway_device_external_key TEXT NOT NULL
                CHECK (typeof(gateway_device_external_key) = 'text'
                       AND length(gateway_device_external_key) BETWEEN 1 AND 255),
            business_project_id TEXT NOT NULL
                CHECK (typeof(business_project_id) = 'text'
                       AND length(business_project_id) BETWEEN 1 AND 255),
            repository_id TEXT NOT NULL
                CHECK (typeof(repository_id) = 'text' AND length(repository_id) BETWEEN 1 AND 255),
            state TEXT NOT NULL
                CHECK (typeof(state) = 'text' AND state IN ({workspace_states})),
            generation INTEGER NOT NULL
                CHECK (typeof(generation) = 'integer' AND generation >= 0),
            optimistic_version INTEGER NOT NULL
                CHECK (typeof(optimistic_version) = 'integer' AND optimistic_version >= 0),
            current_upload_revision_id TEXT
                CHECK (current_upload_revision_id IS NULL OR
                       (typeof(current_upload_revision_id) = 'text'
                        AND length(current_upload_revision_id) BETWEEN 1 AND 255)),
            current_preview_result_id TEXT
                CHECK (current_preview_result_id IS NULL OR
                       (typeof(current_preview_result_id) = 'text'
                        AND length(current_preview_result_id) BETWEEN 1 AND 255)),
            created_at_us INTEGER NOT NULL
                CHECK (typeof(created_at_us) = 'integer'),
            updated_at_us INTEGER NOT NULL
                CHECK (typeof(updated_at_us) = 'integer'),
            closed_at_us INTEGER
                CHECK (closed_at_us IS NULL OR typeof(closed_at_us) = 'integer')
        )
        """,
        """
        CREATE UNIQUE INDEX workspace_records_open_exact_scope
        ON workspace_records(owner_actor_id, gateway_device_external_key, business_project_id)
        WHERE state = 'OPEN'
        """,
        f"""
        CREATE TABLE upload_revision_records (
            upload_revision_id TEXT NOT NULL PRIMARY KEY
                CHECK (typeof(upload_revision_id) = 'text'
                       AND length(upload_revision_id) BETWEEN 1 AND 255),
            workspace_id TEXT NOT NULL
                CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
            generation INTEGER NOT NULL
                CHECK (typeof(generation) = 'integer' AND generation >= 0),
            input_completeness TEXT NOT NULL
                CHECK (typeof(input_completeness) = 'text'
                       AND input_completeness IN ({input_completeness})),
            source_artifacts BLOB NOT NULL
                CHECK (typeof(source_artifacts) = 'blob'),
            idempotency_key TEXT NOT NULL
                CHECK (typeof(idempotency_key) = 'text'
                       AND length(idempotency_key) BETWEEN 1 AND 255),
            request_fingerprint TEXT NOT NULL
                CHECK (typeof(request_fingerprint) = 'text'
                       AND length(request_fingerprint) BETWEEN 1 AND 512),
            created_by TEXT NOT NULL
                CHECK (typeof(created_by) = 'text' AND length(created_by) BETWEEN 1 AND 255),
            created_at_us INTEGER NOT NULL
                CHECK (typeof(created_at_us) = 'integer'),
            UNIQUE (workspace_id, generation),
            FOREIGN KEY (workspace_id) REFERENCES workspace_records(workspace_id) ON DELETE RESTRICT
        )
        """,
        """
        CREATE TABLE upload_idempotency_records (
            workspace_id TEXT NOT NULL
                CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
            idempotency_key TEXT NOT NULL
                CHECK (typeof(idempotency_key) = 'text'
                       AND length(idempotency_key) BETWEEN 1 AND 255),
            request_fingerprint TEXT NOT NULL
                CHECK (typeof(request_fingerprint) = 'text'
                       AND length(request_fingerprint) BETWEEN 1 AND 512),
            upload_revision_id TEXT NOT NULL
                CHECK (typeof(upload_revision_id) = 'text'
                       AND length(upload_revision_id) BETWEEN 1 AND 255),
            PRIMARY KEY (workspace_id, idempotency_key),
            FOREIGN KEY (workspace_id) REFERENCES workspace_records(workspace_id) ON DELETE RESTRICT,
            FOREIGN KEY (upload_revision_id) REFERENCES upload_revision_records(upload_revision_id)
                ON DELETE RESTRICT
        )
        """,
        """
        CREATE TABLE preview_result_records (
            preview_result_id TEXT NOT NULL PRIMARY KEY
                CHECK (typeof(preview_result_id) = 'text'
                       AND length(preview_result_id) BETWEEN 1 AND 255),
            workspace_id TEXT NOT NULL
                CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
            upload_revision_id TEXT NOT NULL
                CHECK (typeof(upload_revision_id) = 'text'
                       AND length(upload_revision_id) BETWEEN 1 AND 255),
            generation INTEGER NOT NULL
                CHECK (typeof(generation) = 'integer' AND generation >= 0),
            repository_id TEXT NOT NULL
                CHECK (typeof(repository_id) = 'text' AND length(repository_id) BETWEEN 1 AND 255),
            binding BLOB NOT NULL
                CHECK (typeof(binding) = 'blob'),
            operation_id TEXT NOT NULL UNIQUE
                CHECK (typeof(operation_id) = 'text' AND length(operation_id) BETWEEN 1 AND 255),
            created_at_us INTEGER NOT NULL
                CHECK (typeof(created_at_us) = 'integer'),
            FOREIGN KEY (workspace_id) REFERENCES workspace_records(workspace_id) ON DELETE RESTRICT,
            FOREIGN KEY (upload_revision_id) REFERENCES upload_revision_records(upload_revision_id)
                ON DELETE RESTRICT
        )
        """,
        """
        CREATE TABLE preview_idempotency_records (
            workspace_id TEXT NOT NULL
                CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
            idempotency_key TEXT NOT NULL
                CHECK (typeof(idempotency_key) = 'text'
                       AND length(idempotency_key) BETWEEN 1 AND 255),
            request_fingerprint TEXT NOT NULL
                CHECK (typeof(request_fingerprint) = 'text'
                       AND length(request_fingerprint) BETWEEN 1 AND 512),
            preview_result_id TEXT NOT NULL
                CHECK (typeof(preview_result_id) = 'text'
                       AND length(preview_result_id) BETWEEN 1 AND 255),
            PRIMARY KEY (workspace_id, idempotency_key),
            FOREIGN KEY (workspace_id) REFERENCES workspace_records(workspace_id) ON DELETE RESTRICT,
            FOREIGN KEY (preview_result_id) REFERENCES preview_result_records(preview_result_id)
                ON DELETE RESTRICT
        )
        """,
        """
        CREATE TABLE artifact_protection_intents (
            artifact_id TEXT NOT NULL
                CHECK (typeof(artifact_id) = 'text' AND length(artifact_id) BETWEEN 1 AND 255),
            owner_kind TEXT NOT NULL
                CHECK (typeof(owner_kind) = 'text' AND length(owner_kind) BETWEEN 1 AND 128),
            owner_id TEXT NOT NULL
                CHECK (typeof(owner_id) = 'text' AND length(owner_id) BETWEEN 1 AND 255),
            intent TEXT NOT NULL
                CHECK (typeof(intent) = 'text' AND length(intent) BETWEEN 1 AND 128),
            recorded_at_us INTEGER NOT NULL
                CHECK (typeof(recorded_at_us) = 'integer'),
            PRIMARY KEY (artifact_id, owner_kind, owner_id)
        )
        """,
    )


_PREVIEW_IDEMPOTENCY_V2_DDL = """
CREATE TABLE preview_idempotency_records_v2 (
    workspace_id TEXT NOT NULL
        CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
    idempotency_key TEXT NOT NULL
        CHECK (typeof(idempotency_key) = 'text'
               AND length(idempotency_key) BETWEEN 1 AND 255),
    request_fingerprint TEXT NOT NULL
        CHECK (typeof(request_fingerprint) = 'text'
               AND length(request_fingerprint) BETWEEN 1 AND 512),
    operation_id TEXT NOT NULL
        CHECK (typeof(operation_id) = 'text'
               AND length(operation_id) BETWEEN 1 AND 255),
    upload_revision_id TEXT NOT NULL
        CHECK (typeof(upload_revision_id) = 'text'
               AND length(upload_revision_id) BETWEEN 1 AND 255),
    generation INTEGER NOT NULL
        CHECK (typeof(generation) = 'integer' AND generation >= 0),
    business_baseline_node_id TEXT NOT NULL
        CHECK (typeof(business_baseline_node_id) = 'text'
               AND length(business_baseline_node_id) BETWEEN 1 AND 255),
    baseline_head_version INTEGER NOT NULL
        CHECK (typeof(baseline_head_version) = 'integer' AND baseline_head_version >= 0),
    PRIMARY KEY (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id) REFERENCES workspace_records(workspace_id) ON DELETE RESTRICT,
    FOREIGN KEY (operation_id) REFERENCES operation_records(operation_id) ON DELETE RESTRICT,
    FOREIGN KEY (upload_revision_id) REFERENCES upload_revision_records(upload_revision_id)
        ON DELETE RESTRICT
)
"""


def _workspace_v2_statements() -> tuple[str, ...]:
    return (
        """
        CREATE TABLE provisioned_scope_mappings (
            gateway_device_external_key TEXT NOT NULL
                CHECK (typeof(gateway_device_external_key) = 'text'
                       AND length(gateway_device_external_key) BETWEEN 1 AND 255),
            business_project_id TEXT NOT NULL
                CHECK (typeof(business_project_id) = 'text'
                       AND length(business_project_id) BETWEEN 1 AND 255),
            repository_id TEXT NOT NULL
                CHECK (typeof(repository_id) = 'text' AND length(repository_id) BETWEEN 1 AND 255),
            business_baseline_node_id TEXT NOT NULL
                CHECK (typeof(business_baseline_node_id) = 'text'
                       AND length(business_baseline_node_id) BETWEEN 1 AND 255),
            business_baseline_commit_id TEXT NOT NULL
                CHECK (typeof(business_baseline_commit_id) = 'text'
                       AND length(business_baseline_commit_id) BETWEEN 1 AND 255),
            baseline_head_version INTEGER NOT NULL
                CHECK (typeof(baseline_head_version) = 'integer' AND baseline_head_version >= 0),
            enabled INTEGER NOT NULL
                CHECK (typeof(enabled) = 'integer' AND enabled IN (0, 1)),
            PRIMARY KEY (gateway_device_external_key, business_project_id)
        )
        """,
        """
        CREATE UNIQUE INDEX provisioned_scope_mappings_one_active_device
            ON provisioned_scope_mappings(gateway_device_external_key)
            WHERE enabled = 1
        """,
    )


def _copy_preview_idempotency_to_v2(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT
            idempotency.workspace_id,
            idempotency.idempotency_key,
            idempotency.request_fingerprint,
            result.operation_id,
            result.upload_revision_id,
            result.generation,
            result.binding
        FROM preview_idempotency_records AS idempotency
        LEFT JOIN preview_result_records AS result
            ON result.preview_result_id = idempotency.preview_result_id
        """
    ).fetchall()
    for row in rows:
        operation_id = row[3]
        upload_revision_id = row[4]
        generation = row[5]
        binding_blob = row[6]
        if (
            type(operation_id) is not str
            or type(upload_revision_id) is not str
            or type(generation) is not int
            or not isinstance(binding_blob, bytes)
        ):
            raise RuntimeError("workspace v2 migration found dangling preview idempotency")
        node_id, head_version = _preview_binding_fields(binding_blob)
        connection.execute(
            """
            INSERT INTO preview_idempotency_records_v2 (
                workspace_id, idempotency_key, request_fingerprint, operation_id,
                upload_revision_id, generation, business_baseline_node_id, baseline_head_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row[0],
                row[1],
                row[2],
                operation_id,
                upload_revision_id,
                generation,
                node_id,
                head_version,
            ),
        )


def _preview_binding_fields(binding_blob: bytes) -> tuple[str, int]:
    try:
        binding = json.loads(binding_blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("workspace v2 migration found undecodable preview binding") from exc
    if type(binding) is not dict:
        raise RuntimeError("workspace v2 migration found undecodable preview binding")
    node_id = binding.get("business_baseline_node_id")
    head_version = binding.get("baseline_head_version")
    if type(node_id) is not str or not node_id or type(head_version) is not int:
        raise RuntimeError("workspace v2 migration found undecodable preview binding")
    return node_id, head_version

