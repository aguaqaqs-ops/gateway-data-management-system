"""Deterministic version_manager overlap rule over canonical snapshot tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gateway_shared_kernel import (
    AnomalyScalar,
    BinaryScalar,
    BitScalar,
    BooleanScalar,
    DateScalar,
    DateTimeScalar,
    DecimalScalar,
    DigestRef,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    TimeDurationScalar,
    TimestampScalar,
    UnsignedIntegerScalar,
    canonicalize_identifier,
    raw_blob_digest,
)
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.project_identity.contracts import (
    PROJECT_IDENTITY_RULE_VERSION,
    PROJECT_IDENTITY_SCHEMA_VERSION,
    ProjectIdentityAssessment,
    ProjectIdentityInput,
    ProjectIdentityStatus,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    DegradedReason,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.snapshot_materialization import SqlSetValue

_VERSION_MANAGER_TABLE = "version_manager"
_EXCLUDED_COLUMN = "no"


@dataclass(frozen=True, slots=True)
class _EntrySet:
    columns: tuple[str, ...]
    row_count: int
    entries: frozenset[bytes]
    digest: DigestRef


def assess_project_identity(
    before: ProjectIdentityInput,
    current: ProjectIdentityInput,
) -> ProjectIdentityAssessment:
    if type(before) is not ProjectIdentityInput or type(current) is not ProjectIdentityInput:
        raise TypeError("before and current must be ProjectIdentityInput")

    before_entries, before_fault = _read_entry_set(before)
    current_entries, current_fault = _read_entry_set(current)
    diagnostics = set(before_fault + current_fault)
    comparable_columns: tuple[str, ...] = ()
    matched_entry_count = 0

    if before_entries is not None and current_entries is not None:
        if before_entries.columns != current_entries.columns:
            diagnostics.add("COMPARABLE_COLUMN_SET_MISMATCH")
        else:
            comparable_columns = before_entries.columns
            matched_entry_count = len(before_entries.entries & current_entries.entries)

    if diagnostics:
        status = ProjectIdentityStatus.UNVERIFIABLE
    elif matched_entry_count:
        status = ProjectIdentityStatus.SAME_PROJECT
    else:
        status = ProjectIdentityStatus.DIFFERENT_PROJECT

    before_row_count = 0 if before_entries is None else before_entries.row_count
    current_row_count = 0 if current_entries is None else current_entries.row_count
    before_distinct_entry_count = 0 if before_entries is None else len(before_entries.entries)
    current_distinct_entry_count = 0 if current_entries is None else len(current_entries.entries)
    fields: dict[str, object] = {
        "schema_version": PROJECT_IDENTITY_SCHEMA_VERSION,
        "rule_version": PROJECT_IDENTITY_RULE_VERSION,
        "before_snapshot_digest": before.snapshot_digest.value,
        "current_snapshot_digest": current.snapshot_digest.value,
        "status": status.value,
        "comparable_columns": list(comparable_columns),
        "before_row_count": before_row_count,
        "current_row_count": current_row_count,
        "before_distinct_entry_count": before_distinct_entry_count,
        "current_distinct_entry_count": current_distinct_entry_count,
        "matched_entry_count": matched_entry_count,
        "before_entry_set_digest": (
            None if before_entries is None else before_entries.digest.value
        ),
        "current_entry_set_digest": (
            None if current_entries is None else current_entries.digest.value
        ),
        "diagnostics": sorted(diagnostics),
    }
    digest = raw_blob_digest(canonicalize_json_value(fields))
    return ProjectIdentityAssessment(
        schema_version=PROJECT_IDENTITY_SCHEMA_VERSION,
        rule_version=PROJECT_IDENTITY_RULE_VERSION,
        before_snapshot_digest=before.snapshot_digest,
        current_snapshot_digest=current.snapshot_digest,
        status=status,
        assessment_digest=digest,
        comparable_columns=comparable_columns,
        before_row_count=before_row_count,
        current_row_count=current_row_count,
        before_distinct_entry_count=before_distinct_entry_count,
        current_distinct_entry_count=current_distinct_entry_count,
        matched_entry_count=matched_entry_count,
        before_entry_set_digest=(
            None if before_entries is None else before_entries.digest
        ),
        current_entry_set_digest=(
            None if current_entries is None else current_entries.digest
        ),
        diagnostics=tuple(sorted(diagnostics)),
    )


def _read_entry_set(
    identity_input: ProjectIdentityInput,
) -> tuple[_EntrySet | None, tuple[str, ...]]:
    if identity_input.table_set is None:
        return None, ("TABLE_SET_UNAVAILABLE",)
    table = next(
        (
            item
            for item in identity_input.table_set.tables
            if canonicalize_identifier(item.descriptor.table_name) == _VERSION_MANAGER_TABLE
        ),
        None,
    )
    if table is None:
        return None, ("VERSION_MANAGER_TABLE_MISSING",)
    descriptor = table.descriptor
    if descriptor.degraded_reason is DegradedReason.TABLE_FAILED or table.reader is None:
        return None, ("VERSION_MANAGER_TABLE_UNREADABLE",)
    if descriptor.row_count == 0:
        return None, ("VERSION_MANAGER_TABLE_EMPTY",)

    try:
        column_indexes = _identity_column_indexes(descriptor)
    except ValueError:
        return None, ("VERSION_MANAGER_COLUMNS_UNUSABLE",)
    if not column_indexes:
        return None, ("VERSION_MANAGER_HAS_NO_IDENTITY_COLUMNS",)

    columns = tuple(sorted(column_indexes, key=lambda item: item.encode("utf-8")))
    entries: set[bytes] = set()
    actual_row_count = 0
    reader = None
    try:
        reader = table.reader.reopen()
        for row in reader.iter_rows():
            if len(row) != len(descriptor.columns):
                raise ValueError("version_manager row width differs from its descriptor")
            values = [
                {
                    "column": name,
                    "value": _cell_document(row[column_indexes[name]]),
                }
                for name in columns
            ]
            entries.add(canonicalize_json_value(values))
            actual_row_count += 1
        if actual_row_count != descriptor.row_count:
            raise ValueError("version_manager row count differs from its descriptor")
    except Exception:
        return None, ("VERSION_MANAGER_READ_FAILED",)
    finally:
        if reader is not None:
            try:
                reader.close()
            except Exception:
                entries.clear()
                actual_row_count = -1
    if actual_row_count <= 0:
        return None, ("VERSION_MANAGER_READ_FAILED",)

    digest = raw_blob_digest(
        canonicalize_json_value(
            {
                "schema": "project-identity-entry-set/v1",
                "columns": list(columns),
                "entries": [entry.hex() for entry in sorted(entries)],
            }
        )
    )
    return (
        _EntrySet(
            columns=columns,
            row_count=actual_row_count,
            entries=frozenset(entries),
            digest=digest,
        ),
        (),
    )


def _identity_column_indexes(descriptor: SnapshotTableDescriptor) -> dict[str, int]:
    result: dict[str, int] = {}
    for index, column in enumerate(descriptor.columns):
        name = canonicalize_identifier(column.name)
        if name in result:
            raise ValueError("version_manager has duplicate canonical column names")
        if name != _EXCLUDED_COLUMN:
            result[name] = index
    return result


def _cell_document(cell: object) -> dict[str, Any]:
    if isinstance(cell, SqlSetValue):
        return {"kind": "set", "members": list(cell.members)}
    if isinstance(cell, NullScalar):
        return {"kind": cell.kind}
    if isinstance(cell, BooleanScalar):
        return {"kind": cell.kind, "value": cell.value}
    if isinstance(cell, (SignedIntegerScalar, UnsignedIntegerScalar, DecimalScalar)):
        return {"kind": cell.kind, "value": cell.decimal}
    if isinstance(cell, (Float32Scalar, Float64Scalar)):
        return {"kind": cell.kind, "value": cell.bits_hex}
    if isinstance(
        cell,
        (StringScalar, DateScalar, DateTimeScalar, TimestampScalar, TimeDurationScalar),
    ):
        return {"kind": cell.kind, "value": cell.text}
    if isinstance(cell, (BinaryScalar, BitScalar)):
        return {"kind": cell.kind, "value": cell.raw_bytes.hex()}
    if isinstance(cell, AnomalyScalar):
        return {"kind": cell.kind, "value": dict(cell.envelope)}
    raise ValueError("version_manager contains an unsupported cell")


__all__ = ["assess_project_identity"]
