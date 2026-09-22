"""SQLite row mapping and transaction-scoped archive repository adapter."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from gateway_backend.domain.archive.models import (
    ArchiveAnomalyResolutionAction,
    ArchiveAnomalyResolutionEvent,
    ArchiveAuditReference,
    ArchiveConfirmationAction,
    ArchiveConfirmationEvent,
    ArchiveDisposition,
    ArchiveDispositionKind,
    ArchivePlan,
    ArchiveResult,
    ArchiveSubjectKind,
)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class SQLiteArchiveRepository:
    """Concrete archive participant bound to one already-open transaction."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        transaction_now: datetime,
        read_only: bool = False,
    ) -> None:
        if not connection.in_transaction:
            raise RuntimeError("SQLiteArchiveRepository requires an active transaction")
        if type(read_only) is not bool:
            raise ValueError("read_only must be a bool")
        _validate_utc_datetime(transaction_now, "transaction_now")
        self._connection = connection
        self._transaction_now = transaction_now
        self._read_only = read_only

    def get_latest_confirmation_sequence(
        self,
        repository_id: str,
        subject_digest: str,
    ) -> int:
        row = self._connection.execute(
            """
            SELECT MAX(sequence) AS latest_sequence
            FROM archive_confirmation_events
            WHERE repository_id = ? AND subject_digest = ?
            """,
            (repository_id, subject_digest),
        ).fetchone()
        if row is None or row["latest_sequence"] is None:
            return 0
        return int(row["latest_sequence"])

    def get_latest_resolution_sequence(
        self,
        repository_id: str,
        subject_digest: str,
    ) -> int:
        row = self._connection.execute(
            """
            SELECT MAX(sequence) AS latest_sequence
            FROM archive_anomaly_resolution_events
            WHERE repository_id = ? AND subject_digest = ?
            """,
            (repository_id, subject_digest),
        ).fetchone()
        if row is None or row["latest_sequence"] is None:
            return 0
        return int(row["latest_sequence"])

    def append_confirmation(self, event: ArchiveConfirmationEvent) -> None:
        self._require_writable()
        self._connection.execute(
            """
            INSERT INTO archive_confirmation_events (
                event_id, repository_id, gateway_device_external_key, business_project_id,
                subject_kind, subject_digest, sequence, action, reason, actor_id,
                occurred_at_us, idempotency_key, request_fingerprint, request_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.repository_id,
                event.gateway_device_external_key,
                event.business_project_id,
                event.subject_kind.value,
                event.subject_digest,
                event.sequence,
                event.action.value,
                event.reason,
                event.actor_id,
                _datetime_to_epoch_us(event.occurred_at),
                event.idempotency_key,
                event.request_fingerprint,
                event.request_payload_json,
            ),
        )

    def append_anomaly_resolution(self, event: ArchiveAnomalyResolutionEvent) -> None:
        self._require_writable()
        self._connection.execute(
            """
            INSERT INTO archive_anomaly_resolution_events (
                event_id, repository_id, gateway_device_external_key, business_project_id,
                subject_kind, subject_digest, sequence, action, issue_code,
                sibling_submission_id, sibling_candidate_digest, reason, actor_id,
                occurred_at_us, idempotency_key, request_fingerprint, request_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.repository_id,
                event.gateway_device_external_key,
                event.business_project_id,
                event.subject_kind.value,
                event.subject_digest,
                event.sequence,
                event.action.value,
                event.issue_code,
                event.sibling_submission_id,
                event.sibling_candidate_digest,
                event.reason,
                event.actor_id,
                _datetime_to_epoch_us(event.occurred_at),
                event.idempotency_key,
                event.request_fingerprint,
                event.request_payload_json,
            ),
        )

    def find_confirmation_idempotency(
        self,
        repository_id: str,
        idempotency_key: str,
    ) -> ArchiveConfirmationEvent | None:
        row = self._connection.execute(
            """
            SELECT *
            FROM archive_confirmation_events
            WHERE repository_id = ? AND idempotency_key = ?
            """,
            (repository_id, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        return _confirmation_from_row(row)

    def find_resolution_idempotency(
        self,
        repository_id: str,
        idempotency_key: str,
    ) -> ArchiveAnomalyResolutionEvent | None:
        row = self._connection.execute(
            """
            SELECT *
            FROM archive_anomaly_resolution_events
            WHERE repository_id = ? AND idempotency_key = ?
            """,
            (repository_id, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        return _resolution_from_row(row)

    def get_confirmation_event(
        self,
        repository_id: str,
        subject_digest: str,
        sequence: int,
    ) -> ArchiveConfirmationEvent | None:
        row = self._connection.execute(
            """
            SELECT *
            FROM archive_confirmation_events
            WHERE repository_id = ? AND subject_digest = ? AND sequence = ?
            """,
            (repository_id, subject_digest, sequence),
        ).fetchone()
        if row is None:
            return None
        return _confirmation_from_row(row)

    def get_resolution_event(
        self,
        repository_id: str,
        subject_digest: str,
        sequence: int,
    ) -> ArchiveAnomalyResolutionEvent | None:
        row = self._connection.execute(
            """
            SELECT *
            FROM archive_anomaly_resolution_events
            WHERE repository_id = ? AND subject_digest = ? AND sequence = ?
            """,
            (repository_id, subject_digest, sequence),
        ).fetchone()
        if row is None:
            return None
        return _resolution_from_row(row)

    def find_start_plan_by_key(
        self,
        repository_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
        idempotency_key: str,
    ) -> ArchivePlan | None:
        row = self._connection.execute(
            """
            SELECT *
            FROM archive_plan_records
            WHERE repository_id = ?
              AND gateway_device_external_key = ?
              AND business_project_id = ?
              AND idempotency_key = ?
            """,
            (repository_id, gateway_device_external_key, business_project_id, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        return _plan_from_row(row)

    def get_result_by_plan_id(self, plan_id: str) -> ArchiveResult | None:
        row = self._connection.execute(
            """
            SELECT result_id, plan_id, baseline_node_id, archived_at_us
            FROM archive_result_records
            WHERE plan_id = ?
            """,
            (plan_id,),
        ).fetchone()
        if row is None:
            return None
        return self._result_from_row(row)

    def get_plan_by_id(self, plan_id: str) -> ArchivePlan | None:
        row = self._connection.execute(
            """
            SELECT *
            FROM archive_plan_records
            WHERE plan_id = ?
            """,
            (plan_id,),
        ).fetchone()
        if row is None:
            return None
        return _plan_from_row(row)

    def get_result_by_id(self, result_id: str) -> ArchiveResult | None:
        row = self._connection.execute(
            """
            SELECT result_id, plan_id, baseline_node_id, archived_at_us
            FROM archive_result_records
            WHERE result_id = ?
            """,
            (result_id,),
        ).fetchone()
        if row is None:
            return None
        return self._result_from_row(row)

    def list_dispositions_for_submission(self, submission_id: str) -> tuple[ArchiveDisposition, ...]:
        rows = self._connection.execute(
            """
            SELECT submission_id, disposition
            FROM archive_disposition_records
            WHERE submission_id = ?
            ORDER BY submission_id
            """,
            (submission_id,),
        ).fetchall()
        return tuple(
            ArchiveDisposition(
                submission_id=row["submission_id"],
                disposition=ArchiveDispositionKind(row["disposition"]),
            )
            for row in rows
        )

    def is_submission_closed(self, submission_id: str) -> bool:
        row = self._connection.execute(
            """
            SELECT 1
            FROM archive_disposition_records
            WHERE submission_id = ?
            LIMIT 1
            """,
            (submission_id,),
        ).fetchone()
        return row is not None

    def insert_plan_result_and_dispositions(
        self,
        plan: ArchivePlan,
        result: ArchiveResult,
        dispositions: tuple[ArchiveDisposition, ...],
    ) -> None:
        self._require_writable()
        confirmation_refs_json = json.dumps(
            [
                {"subject_digest": ref.subject_digest, "sequence": ref.sequence}
                for ref in plan.confirmation_refs
            ],
            separators=(",", ":"),
            sort_keys=True,
        )
        anomaly_refs_json = json.dumps(
            [
                {"subject_digest": ref.subject_digest, "sequence": ref.sequence}
                for ref in plan.anomaly_resolution_refs
            ],
            separators=(",", ":"),
            sort_keys=True,
        )
        self._connection.execute(
            """
            INSERT INTO archive_plan_records (
                plan_id, repository_id, gateway_device_external_key, business_project_id,
                idempotency_key, request_fingerprint, accepted_by, accepted_at_us,
                old_baseline_node_id, old_baseline_commit_id, old_baseline_head_version,
                candidate_set_digest, selected_submission_id, selected_candidate_digest,
                selected_repository_commit_id, confirmation_refs_json,
                anomaly_resolution_refs_json, frozen_input_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan.plan_id,
                plan.repository_id,
                plan.gateway_device_external_key,
                plan.business_project_id,
                plan.idempotency_key,
                plan.request_fingerprint,
                plan.accepted_by,
                _datetime_to_epoch_us(plan.accepted_at),
                plan.old_baseline_node_id,
                plan.old_baseline_commit_id,
                plan.old_baseline_head_version,
                plan.candidate_set_digest,
                plan.selected_submission_id,
                plan.selected_candidate_digest,
                plan.selected_repository_commit_id,
                confirmation_refs_json,
                anomaly_refs_json,
                plan.frozen_input_json,
            ),
        )
        self._connection.execute(
            """
            INSERT INTO archive_result_records (
                result_id, plan_id, baseline_node_id, archived_at_us
            ) VALUES (?, ?, ?, ?)
            """,
            (
                result.result_id,
                result.plan_id,
                result.baseline_node_id,
                _datetime_to_epoch_us(result.archived_at),
            ),
        )
        for disposition in dispositions:
            self._connection.execute(
                """
                INSERT INTO archive_disposition_records (
                    submission_id, result_id, disposition
                ) VALUES (?, ?, ?)
                """,
                (disposition.submission_id, result.result_id, disposition.disposition.value),
            )

    def _result_from_row(self, row: sqlite3.Row) -> ArchiveResult:
        dispositions = self._connection.execute(
            """
            SELECT submission_id, disposition
            FROM archive_disposition_records
            WHERE result_id = ?
            ORDER BY submission_id
            """,
            (row["result_id"],),
        ).fetchall()
        return ArchiveResult(
            result_id=row["result_id"],
            plan_id=row["plan_id"],
            baseline_node_id=row["baseline_node_id"],
            archived_at=_epoch_us_to_datetime(row["archived_at_us"]),
            dispositions=tuple(
                ArchiveDisposition(
                    submission_id=item["submission_id"],
                    disposition=ArchiveDispositionKind(item["disposition"]),
                )
                for item in dispositions
            ),
        )

    def _require_writable(self) -> None:
        if self._read_only:
            raise RuntimeError("archive repository is read-only")


def _plan_from_row(row: sqlite3.Row) -> ArchivePlan:
    confirmation_refs = tuple(
        ArchiveAuditReference(
            subject_digest=item["subject_digest"],
            sequence=item["sequence"],
        )
        for item in json.loads(row["confirmation_refs_json"])
    )
    anomaly_resolution_refs = tuple(
        ArchiveAuditReference(
            subject_digest=item["subject_digest"],
            sequence=item["sequence"],
        )
        for item in json.loads(row["anomaly_resolution_refs_json"])
    )
    return ArchivePlan(
        plan_id=row["plan_id"],
        repository_id=row["repository_id"],
        gateway_device_external_key=row["gateway_device_external_key"],
        business_project_id=row["business_project_id"],
        idempotency_key=row["idempotency_key"],
        request_fingerprint=row["request_fingerprint"],
        accepted_by=row["accepted_by"],
        accepted_at=_epoch_us_to_datetime(row["accepted_at_us"]),
        old_baseline_node_id=row["old_baseline_node_id"],
        old_baseline_commit_id=row["old_baseline_commit_id"],
        old_baseline_head_version=row["old_baseline_head_version"],
        candidate_set_digest=row["candidate_set_digest"],
        selected_submission_id=row["selected_submission_id"],
        selected_candidate_digest=row["selected_candidate_digest"],
        selected_repository_commit_id=row["selected_repository_commit_id"],
        confirmation_refs=confirmation_refs,
        anomaly_resolution_refs=anomaly_resolution_refs,
        frozen_input_json=row["frozen_input_json"],
    )


def _confirmation_from_row(row: sqlite3.Row) -> ArchiveConfirmationEvent:
    return ArchiveConfirmationEvent(
        event_id=row["event_id"],
        repository_id=row["repository_id"],
        gateway_device_external_key=row["gateway_device_external_key"],
        business_project_id=row["business_project_id"],
        subject_kind=ArchiveSubjectKind(row["subject_kind"]),
        subject_digest=row["subject_digest"],
        sequence=row["sequence"],
        action=ArchiveConfirmationAction(row["action"]),
        reason=row["reason"],
        actor_id=row["actor_id"],
        occurred_at=_epoch_us_to_datetime(row["occurred_at_us"]),
        idempotency_key=row["idempotency_key"],
        request_fingerprint=row["request_fingerprint"],
        request_payload_json=row["request_payload_json"],
    )


def _resolution_from_row(row: sqlite3.Row) -> ArchiveAnomalyResolutionEvent:
    return ArchiveAnomalyResolutionEvent(
        event_id=row["event_id"],
        repository_id=row["repository_id"],
        gateway_device_external_key=row["gateway_device_external_key"],
        business_project_id=row["business_project_id"],
        subject_kind=ArchiveSubjectKind(row["subject_kind"]),
        subject_digest=row["subject_digest"],
        sequence=row["sequence"],
        action=ArchiveAnomalyResolutionAction(row["action"]),
        issue_code=row["issue_code"],
        sibling_submission_id=row["sibling_submission_id"],
        sibling_candidate_digest=row["sibling_candidate_digest"],
        reason=row["reason"],
        actor_id=row["actor_id"],
        occurred_at=_epoch_us_to_datetime(row["occurred_at_us"]),
        idempotency_key=row["idempotency_key"],
        request_fingerprint=row["request_fingerprint"],
        request_payload_json=row["request_payload_json"],
    )


def _validate_utc_datetime(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must be an aware UTC datetime")


def _datetime_to_epoch_us(value: datetime) -> int:
    delta = value - _EPOCH
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def _epoch_us_to_datetime(value: int) -> datetime:
    seconds, micros = divmod(value, 1_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=micros)


__all__ = ["SQLiteArchiveRepository"]
