"""Shared business-table fingerprint set for history compare zero-write assertions."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork

HISTORY_ZERO_WRITE_TABLES = (
    "submission_records",
    "review_projection_records",
    "review_event_records",
    "baseline_node_records",
    "baseline_head_records",
    "archive_disposition_records",
    "workspace_records",
    "provisioned_scope_mappings",
    "upload_revision_records",
    "submit_attempt_records",
    "workspace_submit_occupancy_records",
    "repository_submit_occupancy_records",
    "archive_plan_records",
    "archive_result_records",
    "archive_confirmation_events",
    "archive_anomaly_resolution_events",
)


def table_fingerprint(connection: sqlite3.Connection, table: str) -> tuple[int, str]:
    count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    rows = connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
    payload = tuple(tuple(row) for row in rows)
    digest = hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()
    return (count, digest)


def capture_business_table_state(db_path: Path) -> dict[str, tuple[int, str]]:
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        connection = unit_of_work.connection
        return {table: table_fingerprint(connection, table) for table in HISTORY_ZERO_WRITE_TABLES}
