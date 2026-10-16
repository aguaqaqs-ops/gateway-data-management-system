"""SQLite persistence for History compare acceptance records."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from gateway_backend.application.history.contracts import (
    HistoryCompareAcceptanceRecord,
    nodes_json_from_bindings,
    parse_nodes_json,
)


def _datetime_to_epoch_us(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    epoch = value.astimezone(UTC)
    return int(epoch.timestamp() * 1_000_000) + epoch.microsecond


def _epoch_us_to_datetime(value: int) -> datetime:
    seconds, micros = divmod(value, 1_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=micros)


def _acceptance_from_row(row: sqlite3.Row) -> HistoryCompareAcceptanceRecord:
    return HistoryCompareAcceptanceRecord(
        acceptance_id=row["acceptance_id"],
        gateway_device_external_key=row["gateway_device_external_key"],
        business_project_id=row["business_project_id"],
        repository_id=row["repository_id"],
        idempotency_key=row["idempotency_key"],
        request_fingerprint=row["request_fingerprint"],
        comparison_ruleset_digest=row["comparison_ruleset_digest"],
        nodes=parse_nodes_json(row["nodes_json"]),
        operation_id=row["operation_id"],
        created_at=_epoch_us_to_datetime(row["created_at_us"]),
    )


def find_acceptance_by_idempotency(
    connection: sqlite3.Connection,
    *,
    gateway_device_external_key: str,
    business_project_id: str,
    idempotency_key: str,
) -> HistoryCompareAcceptanceRecord | None:
    row = connection.execute(
        """
        SELECT *
        FROM history_compare_acceptance_records
        WHERE gateway_device_external_key = ?
          AND business_project_id = ?
          AND idempotency_key = ?
        """,
        (gateway_device_external_key, business_project_id, idempotency_key),
    ).fetchone()
    if row is None:
        return None
    return _acceptance_from_row(row)


def get_acceptance_by_operation_id(
    connection: sqlite3.Connection,
    operation_id: str,
) -> HistoryCompareAcceptanceRecord | None:
    row = connection.execute(
        """
        SELECT *
        FROM history_compare_acceptance_records
        WHERE operation_id = ?
        """,
        (operation_id,),
    ).fetchone()
    if row is None:
        return None
    return _acceptance_from_row(row)


def save_acceptance(connection: sqlite3.Connection, record: HistoryCompareAcceptanceRecord) -> None:
    connection.execute(
        """
        INSERT INTO history_compare_acceptance_records (
            acceptance_id,
            gateway_device_external_key,
            business_project_id,
            repository_id,
            idempotency_key,
            request_fingerprint,
            comparison_ruleset_digest,
            nodes_json,
            operation_id,
            created_at_us
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.acceptance_id,
            record.gateway_device_external_key,
            record.business_project_id,
            record.repository_id,
            record.idempotency_key,
            record.request_fingerprint,
            record.comparison_ruleset_digest,
            nodes_json_from_bindings(record.nodes),
            record.operation_id,
            _datetime_to_epoch_us(record.created_at),
        ),
    )


def resolve_node_ref(
    connection: sqlite3.Connection,
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
    ref_kind: str,
    ref_id: str,
) -> str | None:
    if ref_kind == "baseline_node":
        row = connection.execute(
            """
            SELECT commit_id
            FROM baseline_node_records
            WHERE repository_id = ?
              AND gateway_device_external_key = ?
              AND business_project_id = ?
              AND node_id = ?
            """,
            (repository_id, gateway_device_external_key, business_project_id, ref_id),
        ).fetchone()
    elif ref_kind == "submission":
        row = connection.execute(
            """
            SELECT repository_commit_id AS commit_id
            FROM submission_records
            WHERE repository_id = ?
              AND submission_id = ?
            """,
            (repository_id, ref_id),
        ).fetchone()
    else:
        return None
    if row is None:
        return None
    commit_id = row["commit_id"]
    return str(commit_id) if type(commit_id) is str and commit_id else None


class SQLiteHistoryCompareRepository:
    """History compare acceptance adapter for one control DB transaction."""

    def __init__(self, connection: sqlite3.Connection, *, read_only: bool) -> None:
        self._connection = connection
        self._read_only = read_only

    def _require_writable(self) -> None:
        if self._read_only:
            raise RuntimeError("history compare repository is read-only")

    def find_acceptance_by_idempotency(
        self,
        *,
        gateway_device_external_key: str,
        business_project_id: str,
        idempotency_key: str,
    ) -> HistoryCompareAcceptanceRecord | None:
        return find_acceptance_by_idempotency(
            self._connection,
            gateway_device_external_key=gateway_device_external_key,
            business_project_id=business_project_id,
            idempotency_key=idempotency_key,
        )

    def get_acceptance_by_operation_id(self, operation_id: str) -> HistoryCompareAcceptanceRecord | None:
        return get_acceptance_by_operation_id(self._connection, operation_id)

    def save_acceptance(self, record: HistoryCompareAcceptanceRecord) -> None:
        self._require_writable()
        save_acceptance(self._connection, record)

    def resolve_node_ref(
        self,
        *,
        repository_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
        ref_kind: str,
        ref_id: str,
    ) -> str | None:
        return resolve_node_ref(
            self._connection,
            repository_id=repository_id,
            gateway_device_external_key=gateway_device_external_key,
            business_project_id=business_project_id,
            ref_kind=ref_kind,
            ref_id=ref_id,
        )

__all__ = [
    "SQLiteHistoryCompareRepository",
    "find_acceptance_by_idempotency",
    "get_acceptance_by_operation_id",
    "resolve_node_ref",
    "save_acceptance",
]
