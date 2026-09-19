"""SQLite row mapping and transaction-scoped review repository adapter."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from gateway_backend.domain.submission.errors import (
    InvalidReviewReason,
    ReviewClosureViolation,
    ReviewVersionConflict,
)
from gateway_backend.domain.submission.review import (
    ReviewEvent,
    ReviewEventKind,
    ReviewIdempotencyRecord,
    ReviewProjection,
    ReviewStatus,
    validate_review_closure,
)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_SQLITE_INT_MIN = -(2**63)
_SQLITE_INT_MAX = 2**63 - 1


class SQLiteReviewRepository:
    """Concrete review participant bound to one already-open transaction."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        transaction_now: datetime,
        read_only: bool = False,
    ) -> None:
        if not connection.in_transaction:
            raise RuntimeError("SQLiteReviewRepository requires an active transaction")
        if type(read_only) is not bool:
            raise ValueError("read_only must be a bool")
        _validate_utc_datetime(transaction_now, "transaction_now")
        self._connection = connection
        self._transaction_now = transaction_now
        self._read_only = read_only

    def get_projection(self, submission_id: str) -> ReviewProjection | None:
        try:
            projection = self._load_projection_unchecked(submission_id)
            events = self._load_events_unchecked(submission_id)
            if projection is None:
                if events:
                    raise ReviewClosureViolation("review projection is missing")
                return None
            validate_review_closure(projection, events)
        except (ReviewClosureViolation, ValueError, OverflowError, KeyError, InvalidReviewReason) as exc:
            raise _map_read_error(exc) from exc
        return projection

    def list_events(self, submission_id: str) -> tuple[ReviewEvent, ...]:
        try:
            projection = self._load_projection_unchecked(submission_id)
            events = self._load_events_unchecked(submission_id)
            if projection is None:
                if events:
                    raise ReviewClosureViolation("review projection is missing")
                return events
            validate_review_closure(projection, events)
        except (ReviewClosureViolation, ValueError, OverflowError, KeyError, InvalidReviewReason) as exc:
            raise _map_read_error(exc) from exc
        return events

    def find_idempotency(
        self,
        business_project_id: str,
        idempotency_key: str,
    ) -> ReviewIdempotencyRecord | None:
        row = self._connection.execute(
            """
            SELECT
                r.business_project_id,
                r.submission_id,
                r.idempotency_key,
                r.request_fingerprint,
                r.event_sequence,
                e.event_kind,
                w.business_project_id AS workspace_project_id
            FROM review_idempotency_records AS r
            LEFT JOIN review_event_records AS e
                ON r.submission_id = e.submission_id AND r.event_sequence = e.sequence
            LEFT JOIN submission_records AS s
                ON r.submission_id = s.submission_id
            LEFT JOIN workspace_records AS w
                ON s.workspace_id = w.workspace_id
            WHERE r.business_project_id = ? AND r.idempotency_key = ?
            """,
            (business_project_id, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        try:
            record = ReviewIdempotencyRecord(
                business_project_id=row[0],
                submission_id=row[1],
                idempotency_key=row[2],
                request_fingerprint=row[3],
                event_sequence=row[4],
            )
            event_kind = row[5]
            workspace_project_id = row[6]
            if event_kind is None:
                raise ReviewClosureViolation("review idempotency record points to a missing event")
            if event_kind == ReviewEventKind.SUBMISSION_FINALIZED.value or record.event_sequence < 1:
                raise ReviewClosureViolation("review idempotency record is bound to a seed event")
            if workspace_project_id is None:
                raise ReviewClosureViolation("review idempotency record has no owning workspace")
            if record.business_project_id != workspace_project_id:
                raise ReviewClosureViolation(
                    "review idempotency record business_project_id does not match workspace"
                )
        except (ReviewClosureViolation, ValueError, OverflowError, KeyError, InvalidReviewReason) as exc:
            raise _map_read_error(exc) from exc
        return record

    def insert_seed(self, event: ReviewEvent, projection: ReviewProjection) -> None:
        self._require_writable()
        if event.sequence != 0 or projection.optimistic_version != 0 or projection.latest_sequence != 0:
            raise ValueError("review seed requires sequence and version 0")
        if event.event_kind is not ReviewEventKind.SUBMISSION_FINALIZED:
            raise ValueError("review seed requires SUBMISSION_FINALIZED event")
        if event.submission_id != projection.submission_id:
            raise ValueError("review seed event and projection submission_id must match")
        try:
            self._connection.execute(
                """
                INSERT INTO review_event_records (
                    submission_id, sequence, event_kind, from_status, to_status,
                    reason, actor_id, occurred_at_us
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _event_to_row(event),
            )
            self._connection.execute(
                """
                INSERT INTO review_projection_records (
                    submission_id, status, optimistic_version, latest_sequence,
                    updated_by, updated_at_us
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                _projection_to_row(projection),
            )
        except sqlite3.IntegrityError as exc:
            raise ReviewClosureViolation("review seed already exists or violates constraints") from exc

    def append_event(self, event: ReviewEvent) -> None:
        self._require_writable()
        latest_sequence = self._connection.execute(
            """
            SELECT COALESCE(MAX(sequence), -1)
            FROM review_event_records
            WHERE submission_id = ?
            """,
            (event.submission_id,),
        ).fetchone()[0]
        if type(latest_sequence) is not int:
            raise ReviewClosureViolation("review event sequence lookup returned invalid data")
        if latest_sequence < 0:
            raise ReviewClosureViolation("review event stream has no seed")
        if event.sequence != latest_sequence + 1:
            raise ReviewClosureViolation("review event sequence is not contiguous")
        try:
            self._connection.execute(
                """
                INSERT INTO review_event_records (
                    submission_id, sequence, event_kind, from_status, to_status,
                    reason, actor_id, occurred_at_us
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _event_to_row(event),
            )
        except sqlite3.IntegrityError as exc:
            raise ReviewClosureViolation("review event append violates constraints") from exc

    def cas_projection(
        self,
        projection: ReviewProjection,
        *,
        expected_version: int,
    ) -> ReviewProjection:
        self._require_writable()
        updated = self._connection.execute(
            """
            UPDATE review_projection_records
            SET status = ?, optimistic_version = ?, latest_sequence = ?,
                updated_by = ?, updated_at_us = ?
            WHERE submission_id = ? AND optimistic_version = ?
            """,
            (
                projection.status.value,
                projection.optimistic_version,
                projection.latest_sequence,
                projection.updated_by,
                _datetime_to_epoch_us(projection.updated_at),
                projection.submission_id,
                expected_version,
            ),
        )
        if updated.rowcount != 1:
            current = self._load_projection_unchecked(projection.submission_id)
            if current is None:
                raise ReviewClosureViolation("review projection is missing")
            raise ReviewVersionConflict(
                expected=expected_version,
                actual=current.optimistic_version,
            )
        return projection

    def insert_idempotency(self, record: ReviewIdempotencyRecord) -> None:
        self._require_writable()
        try:
            self._connection.execute(
                """
                INSERT INTO review_idempotency_records (
                    business_project_id, idempotency_key, submission_id,
                    request_fingerprint, event_sequence
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.business_project_id,
                    record.idempotency_key,
                    record.submission_id,
                    record.request_fingerprint,
                    record.event_sequence,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ReviewClosureViolation("review idempotency insert violates constraints") from exc

    def _load_projection_unchecked(self, submission_id: str) -> ReviewProjection | None:
        row = self._connection.execute(
            """
            SELECT submission_id, status, optimistic_version, latest_sequence,
                   updated_by, updated_at_us
            FROM review_projection_records
            WHERE submission_id = ?
            """,
            (submission_id,),
        ).fetchone()
        if row is None:
            return None
        return _projection_from_row(row)

    def _load_events_unchecked(self, submission_id: str) -> tuple[ReviewEvent, ...]:
        rows = self._connection.execute(
            """
            SELECT submission_id, sequence, event_kind, from_status, to_status,
                   reason, actor_id, occurred_at_us
            FROM review_event_records
            WHERE submission_id = ?
            ORDER BY sequence ASC
            """,
            (submission_id,),
        ).fetchall()
        return tuple(_event_from_row(row) for row in rows)

    def _require_writable(self) -> None:
        if self._read_only:
            raise RuntimeError("review repository is read-only in this transaction")


def _map_read_error(exc: BaseException) -> ReviewClosureViolation:
    if isinstance(exc, ReviewClosureViolation):
        return exc
    return ReviewClosureViolation(str(exc))


def _event_to_row(event: ReviewEvent) -> tuple[object, ...]:
    return (
        event.submission_id,
        event.sequence,
        event.event_kind.value,
        event.from_status.value if event.from_status is not None else None,
        event.to_status.value,
        event.reason,
        event.actor_id,
        _datetime_to_epoch_us(event.occurred_at),
    )


def _projection_to_row(projection: ReviewProjection) -> tuple[object, ...]:
    return (
        projection.submission_id,
        projection.status.value,
        projection.optimistic_version,
        projection.latest_sequence,
        projection.updated_by,
        _datetime_to_epoch_us(projection.updated_at),
    )


def _event_from_row(row: sqlite3.Row) -> ReviewEvent:
    from_status_raw = row[3]
    from_status = None
    if from_status_raw is not None:
        from_status = ReviewStatus(str(from_status_raw))
    return ReviewEvent(
        submission_id=_required_text(row, 0),
        sequence=_required_int(row, 1),
        event_kind=ReviewEventKind(_required_text(row, 2)),
        from_status=from_status,
        to_status=ReviewStatus(_required_text(row, 4)),
        reason=_optional_text(row, 5),
        actor_id=_required_text(row, 6),
        occurred_at=_epoch_us_to_datetime(_required_int(row, 7)),
    )


def _projection_from_row(row: sqlite3.Row) -> ReviewProjection:
    return ReviewProjection(
        submission_id=_required_text(row, 0),
        status=ReviewStatus(_required_text(row, 1)),
        optimistic_version=_required_int(row, 2),
        latest_sequence=_required_int(row, 3),
        updated_by=_required_text(row, 4),
        updated_at=_epoch_us_to_datetime(_required_int(row, 5)),
    )


def _required_text(row: sqlite3.Row, key: int) -> str:
    value = row[key]
    if type(value) is not str or not value:
        raise ValueError(f"{key!r} must be a non-empty string")
    return value


def _optional_text(row: sqlite3.Row, key: int) -> str | None:
    value = row[key]
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError(f"{key!r} must be a string or None")
    return value


def _required_int(row: sqlite3.Row, key: int) -> int:
    value = row[key]
    if type(value) is not int:
        raise ValueError(f"{key!r} must be an integer")
    return value


def _datetime_to_epoch_us(value: datetime) -> int:
    _validate_utc_datetime(value, "timestamp")
    delta = value - _EPOCH
    micros = (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    if micros < _SQLITE_INT_MIN or micros > _SQLITE_INT_MAX:
        raise ValueError("timestamp is outside SQLite INTEGER range")
    return micros


def _epoch_us_to_datetime(value: int) -> datetime:
    if type(value) is not int:
        raise ValueError("epoch microseconds must be an integer")
    return _EPOCH + timedelta(microseconds=value)


def _validate_utc_datetime(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must be an aware UTC datetime")
