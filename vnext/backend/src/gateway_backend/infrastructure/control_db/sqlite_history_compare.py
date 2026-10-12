"""SQLite persistence for History compare acceptance and integrity records."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from gateway_backend.application.history.contracts import (
    HistoryCompareAcceptanceRecord,
    HistoryCompareIntegrityRecord,
    IntegrityAcknowledgementStatus,
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


def _integrity_from_row(row: sqlite3.Row) -> HistoryCompareIntegrityRecord:
    commit_refs_raw = json.loads(row["commit_refs_json"])
    affected_tables_raw = json.loads(row["affected_tables_json"])
    if type(commit_refs_raw) is not list:
        raise ValueError("commit_refs_json must decode to a list")
    if type(affected_tables_raw) is not list:
        raise ValueError("affected_tables_json must decode to a list")
    commit_refs = tuple(
        {
            "commit_id": str(item["commit_id"]),
            **(
                {"ref_kind": str(item["ref_kind"]), "ref_id": str(item["ref_id"])}
                if item.get("ref_kind") is not None and item.get("ref_id") is not None
                else {}
            ),
        }
        for item in commit_refs_raw
        if type(item) is dict and type(item.get("commit_id")) is str
    )
    affected_tables = tuple(str(item) for item in affected_tables_raw if type(item) is str)
    resolution_reference = row["resolution_reference"]
    return HistoryCompareIntegrityRecord(
        incident_id=row["incident_id"],
        operation_id=row["operation_id"],
        repository_id=row["repository_id"],
        commit_refs=commit_refs,
        failure_class=row["failure_class"],
        expected_digest=row["expected_digest"],
        observed_digest=row["observed_digest"],
        affected_tables=affected_tables,
        recommended_action=row["recommended_action"],
        first_seen_at=_epoch_us_to_datetime(row["first_seen_at_us"]),
        last_seen_at=_epoch_us_to_datetime(row["last_seen_at_us"]),
        acknowledgement_status=IntegrityAcknowledgementStatus(row["acknowledgement_status"]),
        resolution_reference=None if resolution_reference is None else str(resolution_reference),
        created_at=_epoch_us_to_datetime(row["created_at_us"]),
        updated_at=_epoch_us_to_datetime(row["updated_at_us"]),
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


def has_pending_integrity_for_commit(
    connection: sqlite3.Connection,
    *,
    repository_id: str,
    commit_id: str,
) -> bool:
    rows = connection.execute(
        """
        SELECT commit_refs_json
        FROM history_compare_integrity_records
        WHERE repository_id = ?
          AND acknowledgement_status = 'PENDING'
        """,
        (repository_id,),
    ).fetchall()
    for row in rows:
        refs = json.loads(row["commit_refs_json"])
        if type(refs) is not list:
            continue
        for item in refs:
            if type(item) is dict and item.get("commit_id") == commit_id:
                return True
    return False


def save_integrity_record(connection: sqlite3.Connection, record: HistoryCompareIntegrityRecord) -> None:
    connection.execute(
        """
        INSERT INTO history_compare_integrity_records (
            incident_id,
            operation_id,
            repository_id,
            commit_refs_json,
            failure_class,
            expected_digest,
            observed_digest,
            affected_tables_json,
            recommended_action,
            first_seen_at_us,
            last_seen_at_us,
            acknowledgement_status,
            resolution_reference,
            created_at_us,
            updated_at_us
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.incident_id,
            record.operation_id,
            record.repository_id,
            json.dumps(list(record.commit_refs), separators=(",", ":"), sort_keys=True),
            record.failure_class,
            record.expected_digest,
            record.observed_digest,
            json.dumps(list(record.affected_tables), separators=(",", ":")),
            record.recommended_action,
            _datetime_to_epoch_us(record.first_seen_at),
            _datetime_to_epoch_us(record.last_seen_at),
            record.acknowledgement_status.value,
            record.resolution_reference,
            _datetime_to_epoch_us(record.created_at),
            _datetime_to_epoch_us(record.updated_at),
        ),
    )


def get_integrity_by_operation_id(
    connection: sqlite3.Connection,
    operation_id: str,
) -> HistoryCompareIntegrityRecord | None:
    row = connection.execute(
        """
        SELECT *
        FROM history_compare_integrity_records
        WHERE operation_id = ?
        """,
        (operation_id,),
    ).fetchone()
    if row is None:
        return None
    return _integrity_from_row(row)


def acknowledge_integrity(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    resolution_reference: str,
    updated_at: datetime,
) -> HistoryCompareIntegrityRecord:
    existing = get_integrity_by_operation_id(connection, operation_id)
    if existing is None:
        raise ValueError("integrity record is missing")
    if (
        existing.acknowledgement_status is IntegrityAcknowledgementStatus.ACKNOWLEDGED
        and existing.resolution_reference == resolution_reference
    ):
        return existing
    if (
        existing.acknowledgement_status is IntegrityAcknowledgementStatus.ACKNOWLEDGED
        and existing.resolution_reference != resolution_reference
    ):
        from gateway_backend.application.history.errors import HistoryCompareIntegrityAckConflict

        raise HistoryCompareIntegrityAckConflict("integrity resolution_reference conflict")
    connection.execute(
        """
        UPDATE history_compare_integrity_records
        SET acknowledgement_status = 'ACKNOWLEDGED',
            resolution_reference = ?,
            updated_at_us = ?
        WHERE operation_id = ?
        """,
        (resolution_reference, _datetime_to_epoch_us(updated_at), operation_id),
    )
    updated = get_integrity_by_operation_id(connection, operation_id)
    if updated is None:
        raise ValueError("integrity record disappeared after ack")
    return updated


class SQLiteHistoryCompareRepository:
    """History compare acceptance/integrity adapter for one control DB transaction."""

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

    def has_pending_integrity_for_commit(self, *, repository_id: str, commit_id: str) -> bool:
        return has_pending_integrity_for_commit(
            self._connection,
            repository_id=repository_id,
            commit_id=commit_id,
        )

    def save_integrity_record(self, record: HistoryCompareIntegrityRecord) -> None:
        self._require_writable()
        save_integrity_record(self._connection, record)

    def get_integrity_by_operation_id(self, operation_id: str) -> HistoryCompareIntegrityRecord | None:
        return get_integrity_by_operation_id(self._connection, operation_id)

    def acknowledge_integrity(
        self,
        *,
        operation_id: str,
        resolution_reference: str,
        updated_at: datetime,
    ) -> HistoryCompareIntegrityRecord:
        self._require_writable()
        return acknowledge_integrity(
            self._connection,
            operation_id=operation_id,
            resolution_reference=resolution_reference,
            updated_at=updated_at,
        )


__all__ = [
    "SQLiteHistoryCompareRepository",
    "acknowledge_integrity",
    "find_acceptance_by_idempotency",
    "get_acceptance_by_operation_id",
    "get_integrity_by_operation_id",
    "has_pending_integrity_for_commit",
    "resolve_node_ref",
    "save_acceptance",
    "save_integrity_record",
]
