"""SQLite row mapping skeleton for R1 operation and step records.

The complete transaction-scoped OperationStore behavior is intentionally added in S2a.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from gateway_shared_kernel import CanonicalEncodingError
from gateway_shared_kernel.jcs import canonicalize_jcs, canonicalize_json_value

from gateway_backend.operations import (
    CorruptPersistedRecord,
    OperationRecord,
    StepRecord,
    StepStatus,
    operation_record_from_document,
    step_record_from_document,
)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_SQLITE_INT_MIN = -(2**63)
_SQLITE_INT_MAX = 2**63 - 1


def operation_record_to_row(record: OperationRecord) -> dict[str, object]:
    document = record.to_document()
    return {
        "operation_id": record.operation_id,
        "contract_version": record.contract_version,
        "optimistic_version": record.optimistic_version,
        "job_kind": record.job_kind,
        "job_contract_version": record.job_contract_version,
        "job_payload": record.job_payload,
        "job_payload_ref": _optional_json_blob(document["job_payload_ref"]),
        "business_refs": _json_blob(document["business_refs"]),
        "artifact_refs": _json_blob(document["artifact_refs"]),
        "repository_operation_id": record.repository_operation_id,
        "checkpoint_ref": _optional_json_blob(document["checkpoint_ref"]),
        "ready_closure_ref": _optional_json_blob(document["ready_closure_ref"]),
        "status": record.status.value,
        "diagnostic": _optional_json_blob(document["diagnostic"]),
        "cancel_requested": int(record.cancel_requested),
        "created_at_us": _datetime_to_epoch_us(record.created_at),
        "updated_at_us": _datetime_to_epoch_us(record.updated_at),
        "completed_at_us": (
            _datetime_to_epoch_us(record.completed_at) if record.completed_at is not None else None
        ),
    }


def step_record_to_row(record: StepRecord) -> dict[str, object]:
    document = record.to_document()
    eligible_at_us: int | None
    if record.status is StepStatus.PENDING:
        eligible_at_us = _datetime_to_epoch_us(record.created_at)
    elif record.status is StepStatus.RETRY_WAIT:
        if record.retry_not_before is None:
            raise ValueError("RETRY_WAIT step requires retry_not_before")
        eligible_at_us = _datetime_to_epoch_us(record.retry_not_before)
    else:
        eligible_at_us = None
    return {
        "step_id": record.step_id,
        "operation_id": record.operation_id,
        "contract_version": record.contract_version,
        "optimistic_version": record.optimistic_version,
        "step_name": record.step_name,
        "attempt_count": record.attempt_count,
        "status": record.status.value,
        "diagnostic": _optional_json_blob(document["diagnostic"]),
        "cancel_requested": int(record.cancel_requested),
        "retry_not_before_us": (
            _datetime_to_epoch_us(record.retry_not_before)
            if record.retry_not_before is not None
            else None
        ),
        "worker_id": record.worker_id,
        "lease_token": record.lease_token,
        "lease_expires_at_us": (
            _datetime_to_epoch_us(record.lease_expires_at)
            if record.lease_expires_at is not None
            else None
        ),
        "checkpoint_ref": _optional_json_blob(document["checkpoint_ref"]),
        "prior_output_refs": _json_blob(document["prior_output_refs"]),
        "created_at_us": _datetime_to_epoch_us(record.created_at),
        "updated_at_us": _datetime_to_epoch_us(record.updated_at),
        "started_at_us": (
            _datetime_to_epoch_us(record.started_at) if record.started_at is not None else None
        ),
        "completed_at_us": (
            _datetime_to_epoch_us(record.completed_at) if record.completed_at is not None else None
        ),
        "eligible_at_us": eligible_at_us,
    }


def operation_record_from_row(row: Mapping[str, object]) -> OperationRecord:
    try:
        document = {
            "artifact_refs": _json_value(row, "artifact_refs", list),
            "business_refs": _json_value(row, "business_refs", list),
            "cancel_requested": _bool_value(row, "cancel_requested"),
            "checkpoint_ref": _optional_json_value(row, "checkpoint_ref"),
            "completed_at": _optional_timestamp(row, "completed_at_us"),
            "contract_version": _text_value(row, "contract_version"),
            "created_at": _timestamp(row, "created_at_us"),
            "diagnostic": _optional_json_value(row, "diagnostic"),
            "document_type": "operation",
            "job_contract_version": _text_value(row, "job_contract_version"),
            "job_kind": _text_value(row, "job_kind"),
            "job_payload": _optional_json_value(row, "job_payload"),
            "job_payload_ref": _optional_json_value(row, "job_payload_ref"),
            "operation_id": _text_value(row, "operation_id"),
            "optimistic_version": _non_negative_int(row, "optimistic_version"),
            "ready_closure_ref": _optional_json_value(row, "ready_closure_ref"),
            "repository_operation_id": _optional_text_value(row, "repository_operation_id"),
            "status": _text_value(row, "status"),
            "updated_at": _timestamp(row, "updated_at_us"),
        }
        return operation_record_from_document(document)
    except CorruptPersistedRecord:
        raise
    except (CanonicalEncodingError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise CorruptPersistedRecord("operation row failed R1 readback") from exc


def step_record_from_row(row: Mapping[str, object]) -> StepRecord:
    try:
        status = _text_value(row, "status")
        created_at = _timestamp_value(row, "created_at_us")
        retry_not_before = _optional_timestamp_value(row, "retry_not_before_us")
        eligible_at_us = _optional_int(row, "eligible_at_us")
        expected_eligible_at_us = _expected_eligible_at_us(status, created_at, retry_not_before)
        if eligible_at_us != expected_eligible_at_us:
            raise ValueError("eligible_at_us does not match persisted step status")
        document = {
            "attempt_count": _non_negative_int(row, "attempt_count"),
            "cancel_requested": _bool_value(row, "cancel_requested"),
            "checkpoint_ref": _optional_json_value(row, "checkpoint_ref"),
            "completed_at": _optional_timestamp(row, "completed_at_us"),
            "contract_version": _text_value(row, "contract_version"),
            "created_at": _format_utc_timestamp(created_at),
            "diagnostic": _optional_json_value(row, "diagnostic"),
            "document_type": "step",
            "lease_expires_at": _optional_timestamp(row, "lease_expires_at_us"),
            "lease_token": _optional_text_value(row, "lease_token"),
            "operation_id": _text_value(row, "operation_id"),
            "optimistic_version": _non_negative_int(row, "optimistic_version"),
            "prior_output_refs": _json_value(row, "prior_output_refs", list),
            "retry_not_before": (
                _format_utc_timestamp(retry_not_before) if retry_not_before is not None else None
            ),
            "started_at": _optional_timestamp(row, "started_at_us"),
            "status": status,
            "step_id": _text_value(row, "step_id"),
            "step_name": _text_value(row, "step_name"),
            "updated_at": _timestamp(row, "updated_at_us"),
            "worker_id": _optional_text_value(row, "worker_id"),
        }
        return step_record_from_document(document)
    except CorruptPersistedRecord:
        raise
    except (CanonicalEncodingError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise CorruptPersistedRecord("step row failed R1 readback") from exc


def _json_blob(value: object) -> bytes:
    return canonicalize_json_value(value)


def _optional_json_blob(value: object) -> bytes | None:
    return None if value is None else _json_blob(value)


def _json_value(
    row: Mapping[str, object],
    key: str,
    expected_type: type[Any] | tuple[type[Any], ...],
) -> object:
    raw = _blob_value(row, key)
    try:
        canonical = canonicalize_jcs(raw)
    except CanonicalEncodingError:
        raise
    if canonical != raw:
        raise ValueError(f"{key} is not canonical JSON")
    value = json.loads(canonical)
    if not isinstance(value, expected_type):
        raise ValueError(f"{key} has the wrong JSON root type")
    return value


def _optional_json_value(row: Mapping[str, object], key: str) -> object | None:
    raw = row[key]
    if raw is None:
        return None
    return _json_value(row, key, (dict, list))


def _blob_value(row: Mapping[str, object], key: str) -> bytes:
    value = row[key]
    if type(value) is not bytes:
        raise ValueError(f"{key} must be a BLOB")
    return value


def _text_value(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if type(value) is not str:
        raise ValueError(f"{key} must be TEXT")
    return value


def _optional_text_value(row: Mapping[str, object], key: str) -> str | None:
    value = row[key]
    if value is None:
        return None
    return _text_value(row, key)


def _non_negative_int(row: Mapping[str, object], key: str) -> int:
    value = _required_int(row, key)
    if value < 0:
        raise ValueError(f"{key} must be non-negative")
    return value


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if type(value) is not int:
        raise ValueError(f"{key} must be INTEGER")
    return value


def _optional_int(row: Mapping[str, object], key: str) -> int | None:
    value = row[key]
    if value is None:
        return None
    return _required_int(row, key)


def _bool_value(row: Mapping[str, object], key: str) -> bool:
    value = _required_int(row, key)
    if value not in (0, 1):
        raise ValueError(f"{key} must be 0 or 1")
    return bool(value)


def _timestamp(row: Mapping[str, object], key: str) -> str:
    return _format_utc_timestamp(_timestamp_value(row, key))


def _timestamp_value(row: Mapping[str, object], key: str) -> datetime:
    return _epoch_us_to_datetime(_required_int(row, key))


def _optional_timestamp(row: Mapping[str, object], key: str) -> str | None:
    value = _optional_timestamp_value(row, key)
    return None if value is None else _format_utc_timestamp(value)


def _optional_timestamp_value(row: Mapping[str, object], key: str) -> datetime | None:
    value = _optional_int(row, key)
    return None if value is None else _epoch_us_to_datetime(value)


def _datetime_to_epoch_us(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must use UTC")
    delta = value - _EPOCH
    micros = (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    if micros < _SQLITE_INT_MIN or micros > _SQLITE_INT_MAX:
        raise ValueError("timestamp is outside SQLite INTEGER range")
    return micros


def _epoch_us_to_datetime(value: int) -> datetime:
    if type(value) is not int or value < _SQLITE_INT_MIN or value > _SQLITE_INT_MAX:
        raise ValueError("timestamp must be a SQLite INTEGER")
    seconds, micros = divmod(value, 1_000_000)
    return _EPOCH + timedelta(seconds=seconds, microseconds=micros)


def _format_utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must use UTC")
    fraction = f"{value.microsecond:06d}".rstrip("0")
    suffix = f".{fraction}" if fraction else ""
    return f"{value:%Y-%m-%dT%H:%M:%S}{suffix}Z"


def _expected_eligible_at_us(
    status: str,
    created_at: datetime,
    retry_not_before: datetime | None,
) -> int | None:
    if status == StepStatus.PENDING.value:
        return _datetime_to_epoch_us(created_at)
    if status == StepStatus.RETRY_WAIT.value:
        if retry_not_before is None:
            raise ValueError("RETRY_WAIT step requires retry_not_before")
        return _datetime_to_epoch_us(retry_not_before)
    return None
