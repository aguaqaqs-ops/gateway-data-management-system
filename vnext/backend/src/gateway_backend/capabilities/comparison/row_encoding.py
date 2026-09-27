"""Shared row encoding helpers for standard and ordered comparison."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable

from gateway_shared_kernel import (
    BinaryScalar,
    BitScalar,
    BooleanScalar,
    CanonicalEncodingError,
    CollectionSemantics,
    DateScalar,
    DateTimeScalar,
    DeclaredType,
    DeclaredTypeKind,
    DigestKind,
    DigestRef,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    TimeDurationScalar,
    TimestampScalar,
    TypedScalar,
    UnsignedIntegerScalar,
    canonicalize_identifier,
    encode_collection,
    encode_typed_scalar,
    raw_blob_digest,
    semantic_digest,
)
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_shared_kernel.uleb128 import encode_uleb128

from gateway_backend.capabilities.comparison.contracts import (
    ComparisonRecord,
    ComparisonRecordKind,
    ComparisonSchemaChanges,
    ComparisonSummary,
    ComparisonTableFact,
    ComparisonTablePolicy,
    ComparisonTableStatus,
)
from gateway_backend.capabilities.comparison.errors import StandardComparisonError
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    SnapshotColumnDescriptor,
    SnapshotTable,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.snapshot_materialization.sql_declared_types import (
    SqlDeclaredTypeMappingError,
    declared_type_for_sql_spelling,
)

_TYPED_SCALAR_TYPES = (
    NullScalar,
    BooleanScalar,
    SignedIntegerScalar,
    UnsignedIntegerScalar,
    StringScalar,
    BinaryScalar,
    BitScalar,
    DateScalar,
    DateTimeScalar,
    TimestampScalar,
    TimeDurationScalar,
    Float32Scalar,
    Float64Scalar,
)

@dataclass(frozen=True, slots=True)
class _EncodedRow:
    values: tuple[tuple[str, object], ...]
    frames: tuple[tuple[str, bytes], ...]

    def frame_map(self) -> dict[str, bytes]:
        return dict(self.frames)

    def value_map(self) -> dict[str, object]:
        return dict(self.values)


@dataclass(frozen=True, slots=True)
class _SchemaView:
    before_columns: dict[str, SnapshotColumnDescriptor]
    current_columns: dict[str, SnapshotColumnDescriptor]
    before_only: tuple[str, ...]
    current_only: tuple[str, ...]
    selected: tuple[str, ...]
    incompatible: tuple[str, ...]
    before_key: tuple[str, ...]
    current_key: tuple[str, ...]
    key_changed: bool
    key_invalid: bool

def _schema_view(
    before: SnapshotTableDescriptor,
    current: SnapshotTableDescriptor,
    policy: ComparisonTablePolicy,
) -> _SchemaView:
    before_columns = _column_map(before)
    current_columns = _column_map(current)
    before_names = set(before_columns)
    current_names = set(current_columns)
    before_only = tuple(sorted(before_names - current_names))
    current_only = tuple(sorted(current_names - before_names))
    selected = tuple(sorted((before_names & current_names) - set(policy.ignored_columns)))
    incompatible = tuple(
        column
        for column in selected
        if _column_signature(before_columns[column]) != _column_signature(current_columns[column])
    )
    before_key = tuple(canonicalize_identifier(item) for item in before.compare_key_columns)
    current_key = tuple(canonicalize_identifier(item) for item in current.compare_key_columns)
    key_invalid = (
        len(set(before_key)) != len(before_key)
        or len(set(current_key)) != len(current_key)
        or any(item not in before_columns for item in before_key)
        or any(item not in current_columns for item in current_key)
        or any(item not in selected for item in before_key)
        or any(item not in selected for item in current_key)
        or any(item in incompatible for item in before_key)
        or any(item in incompatible for item in current_key)
    )
    return _SchemaView(
        before_columns=before_columns,
        current_columns=current_columns,
        before_only=before_only,
        current_only=current_only,
        selected=selected,
        incompatible=incompatible,
        before_key=before_key,
        current_key=current_key,
        key_changed=before_key != current_key,
        key_invalid=key_invalid,
    )


def _schema_diagnostics(schema: _SchemaView, policy: ComparisonTablePolicy) -> list[str]:
    diagnostics: list[str] = []
    if any(item not in policy.ignored_columns for item in schema.before_only):
        diagnostics.append("BEFORE_ONLY_COLUMNS")
    if any(item not in policy.ignored_columns for item in schema.current_only):
        diagnostics.append("CURRENT_ONLY_COLUMNS")
    if schema.incompatible:
        diagnostics.append("INCOMPATIBLE_SELECTED_COLUMNS")
    if schema.key_changed:
        diagnostics.append("EFFECTIVE_KEY_CHANGED")
    if any(item in policy.ignored_columns for item in schema.before_key + schema.current_key):
        diagnostics.append("EFFECTIVE_KEY_IGNORED")
    return diagnostics


def _ignored_values_changed(
    before: SnapshotTableDescriptor,
    current: SnapshotTableDescriptor,
    policy: ComparisonTablePolicy,
) -> bool:
    return (
        bool(policy.ignored_columns)
        and before.raw_content_digest is not None
        and current.raw_content_digest is not None
        and before.raw_content_digest != current.raw_content_digest
    )


def _schema_only_fact(
    table_name: str,
    before: SnapshotTableDescriptor,
    current: SnapshotTableDescriptor,
    changes: ComparisonSchemaChanges,
    diagnostics: list[str],
) -> ComparisonTableFact:
    if not diagnostics:
        diagnostics = ["NO_SELECTED_COLUMNS"]
    record = _schema_record(table_name, diagnostics, changes.selected_columns)
    return ComparisonTableFact(
        table_name=table_name,
        status=ComparisonTableStatus.SCHEMA_ONLY_CHANGED,
        before_descriptor=before,
        current_descriptor=current,
        schema_changes=changes,
        row_count_before=before.row_count,
        row_count_current=current.row_count,
        records=(record,),
        diagnostics=tuple(diagnostics),
    )


def _read_rows(
    table: SnapshotTable | None,
    descriptor: SnapshotTableDescriptor,
    selected: tuple[str, ...],
) -> tuple[_EncodedRow, ...]:
    if table is None or table.reader is None:
        raise StandardComparisonError("TABLE_READER_UNAVAILABLE")
    columns = tuple(descriptor.columns)
    selected_set = set(selected)
    rows: list[_EncodedRow] = []
    reader = table.reader
    try:
        for raw_row in reader.iter_rows():
            if type(raw_row) is not tuple or len(raw_row) != len(columns):
                raise StandardComparisonError("ROW_SHAPE_MISMATCH")
            values: list[tuple[str, object]] = []
            frames: list[tuple[str, bytes]] = []
            for column, cell in zip(columns, raw_row, strict=True):
                name = canonicalize_identifier(column.name)
                if name not in selected_set:
                    continue
                values.append((name, cell))
                frames.append((name, _encode_cell(column, cell)))
            rows.append(
                _EncodedRow(
                    values=tuple(sorted(values)),
                    frames=tuple(sorted(frames)),
                )
            )
    finally:
        reader.close()
    return tuple(rows)


def _key_index(
    rows: tuple[_EncodedRow, ...],
    key_columns: tuple[str, ...],
    table_name: str,
) -> dict[bytes, _EncodedRow]:
    result: dict[bytes, _EncodedRow] = {}
    for row in rows:
        key = _row_frame(row.frame_map(), key_columns)
        if key in result:
            raise StandardComparisonError(f"DUPLICATE_EFFECTIVE_KEY:{table_name}")
        result[key] = row
    return result


def _row_record(
    table_name: str,
    kind: ComparisonRecordKind,
    row: _EncodedRow,
    selected: tuple[str, ...],
    *,
    current: bool,
    identity_columns: tuple[str, ...] | None = None,
) -> ComparisonRecord:
    values = tuple((name, row.value_map()[name]) for name in selected if name in row.value_map())
    return ComparisonRecord(
        table_name=table_name,
        record_kind=kind,
        row_identity=_row_digest(row, identity_columns or selected),
        before_values=values if not current else (),
        current_values=values if current else (),
    )


def _schema_record(
    table_name: str,
    diagnostics: Iterable[str],
    selected: tuple[str, ...],
) -> ComparisonRecord:
    return ComparisonRecord(
        table_name=table_name,
        record_kind=ComparisonRecordKind.SCHEMA_CHANGE,
        changed_columns=selected,
        diagnostics=tuple(diagnostics),
    )


def _record_sort_key(record: ComparisonRecord) -> tuple[str, str, tuple[str, ...]]:
    return (
        record.record_kind.value,
        "" if record.row_identity is None else record.row_identity.value,
        record.changed_columns,
    )


def _row_digest(row: _EncodedRow, columns: tuple[str, ...]) -> DigestRef:
    return semantic_digest(DigestKind.ROW, _row_frame(row.frame_map(), columns)).digest_ref


def _row_frame(frames: dict[str, bytes], columns: tuple[str, ...]) -> bytes:
    encoded = bytearray(encode_uleb128(len(columns)))
    for name in sorted(columns, key=lambda item: item.encode("utf-8")):
        name_bytes = name.encode("utf-8")
        frame = frames[name]
        encoded.extend(encode_uleb128(len(name_bytes)))
        encoded.extend(name_bytes)
        encoded.extend(frame)
    return bytes(encoded)


def _encode_cell(column: SnapshotColumnDescriptor, cell: object) -> bytes:
    if type(cell).__name__ == "SqlSetValue":
        members = getattr(cell, "members", None)
        if type(members) is not tuple or any(type(item) is not str for item in members):
            raise StandardComparisonError("SET_VALUE_INVALID")
        string_type = DeclaredType(kind=DeclaredTypeKind.STRING)
        return encode_collection(
            CollectionSemantics.SEQUENCE,
            items=tuple(
                encode_typed_scalar(string_type, StringScalar(item)).scalar_frame
                for item in members
            ),
        ).collection_frame
    if not isinstance(cell, _TYPED_SCALAR_TYPES):
        raise StandardComparisonError("SCALAR_VALUE_INVALID")
    if isinstance(cell, NullScalar):
        return encode_typed_scalar(
            DeclaredType(kind=DeclaredTypeKind.NULL), cell
        ).scalar_frame
    declared = _declared_type(column.scalar_type, cell)
    try:
        return encode_typed_scalar(declared, cell).scalar_frame
    except (CanonicalEncodingError, TypeError, ValueError) as exc:
        raise StandardComparisonError("SCALAR_TYPE_MISMATCH") from exc


def _declared_type(spelling: str | None, cell: TypedScalar) -> DeclaredType:
    if spelling is None or spelling == "":
        return _infer_declared_type(cell)
    try:
        return declared_type_for_sql_spelling(spelling)
    except SqlDeclaredTypeMappingError:
        raise StandardComparisonError("SCALAR_TYPE_UNKNOWN") from None


def _infer_declared_type(cell: TypedScalar) -> DeclaredType:
    if isinstance(cell, NullScalar):
        return DeclaredType(kind=DeclaredTypeKind.NULL)
    if isinstance(cell, BooleanScalar):
        return DeclaredType(kind=DeclaredTypeKind.BOOLEAN)
    if isinstance(cell, SignedIntegerScalar):
        return DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=64)
    if isinstance(cell, UnsignedIntegerScalar):
        return DeclaredType(kind=DeclaredTypeKind.UNSIGNED_INTEGER, bits=64)
    if isinstance(cell, Float32Scalar):
        return DeclaredType(kind=DeclaredTypeKind.FLOAT32)
    if isinstance(cell, Float64Scalar):
        return DeclaredType(kind=DeclaredTypeKind.FLOAT64)
    if isinstance(cell, StringScalar):
        return DeclaredType(kind=DeclaredTypeKind.STRING)
    if isinstance(cell, BinaryScalar):
        return DeclaredType(kind=DeclaredTypeKind.BINARY)
    if isinstance(cell, BitScalar):
        return DeclaredType(kind=DeclaredTypeKind.BIT, bit_width=max(1, len(cell.raw_bytes) * 8))
    if isinstance(cell, DateScalar):
        return DeclaredType(kind=DeclaredTypeKind.DATE)
    if isinstance(cell, DateTimeScalar):
        return DeclaredType(kind=DeclaredTypeKind.DATETIME)
    if isinstance(cell, TimestampScalar):
        return DeclaredType(kind=DeclaredTypeKind.TIMESTAMP)
    if isinstance(cell, TimeDurationScalar):
        return DeclaredType(kind=DeclaredTypeKind.TIME_DURATION)
    raise StandardComparisonError("SCALAR_TYPE_UNKNOWN")


def _column_map(descriptor: SnapshotTableDescriptor) -> dict[str, SnapshotColumnDescriptor]:
    result: dict[str, SnapshotColumnDescriptor] = {}
    for column in descriptor.columns:
        name = canonicalize_identifier(column.name)
        if name in result:
            raise StandardComparisonError("CANONICAL_COLUMN_COLLISION")
        result[name] = column
    return result


def _column_signature(column: SnapshotColumnDescriptor) -> tuple[str | None, bool]:
    return (None if column.scalar_type is None else column.scalar_type.upper(), column.nullable)


def _can_table_early_exit(
    before: SnapshotTableDescriptor,
    current: SnapshotTableDescriptor,
    policy: ComparisonTablePolicy,
) -> bool:
    return (
        before.compare_schema_digest == current.compare_schema_digest
        and before.row_count == current.row_count
        and before.raw_content_digest is not None
        and before.raw_content_digest == current.raw_content_digest
        and policy.table_name == canonicalize_identifier(before.table_name)
    )


def _empty_schema_changes(
    before: SnapshotTableDescriptor,
    current: SnapshotTableDescriptor,
) -> ComparisonSchemaChanges:
    key = tuple(canonicalize_identifier(item) for item in before.compare_key_columns)
    return ComparisonSchemaChanges(
        selected_columns=tuple(sorted(set(_column_map(before)) & set(_column_map(current)))),
        effective_compare_key_before=key,
        effective_compare_key_current=tuple(
            canonicalize_identifier(item) for item in current.compare_key_columns
        ),
    )


def _schema_changes_from_view(schema: _SchemaView) -> ComparisonSchemaChanges:
    return ComparisonSchemaChanges(
        before_only_columns=schema.before_only,
        current_only_columns=schema.current_only,
        selected_columns=schema.selected,
        effective_compare_key_before=schema.before_key,
        effective_compare_key_current=schema.current_key,
        effective_compare_key_changed=schema.key_changed,
        incompatible_columns=schema.incompatible,
    )


def _with_table_digest(fact: ComparisonTableFact) -> ComparisonTableFact:
    return replace(
        fact,
        table_fact_digest=raw_blob_digest(
            canonicalize_json_value(_table_digest_payload(fact))
        ),
    )


def _table_digest_payload(fact: ComparisonTableFact) -> dict[str, object]:
    before_columns = (
        _column_map(fact.before_descriptor) if fact.before_descriptor is not None else {}
    )
    current_columns = (
        _column_map(fact.current_descriptor) if fact.current_descriptor is not None else {}
    )
    return {
        "table_name": fact.table_name,
        "status": fact.status.value,
        "schema_changes": {
            "before_only": list(fact.schema_changes.before_only_columns),
            "current_only": list(fact.schema_changes.current_only_columns),
            "selected": list(fact.schema_changes.selected_columns),
            "key_before": list(fact.schema_changes.effective_compare_key_before),
            "key_current": list(fact.schema_changes.effective_compare_key_current),
            "key_changed": fact.schema_changes.effective_compare_key_changed,
            "incompatible": list(fact.schema_changes.incompatible_columns),
        },
        "row_count_before": fact.row_count_before,
        "row_count_current": fact.row_count_current,
        "row_added_count": fact.row_added_count,
        "row_deleted_count": fact.row_deleted_count,
        "row_modified_count": fact.row_modified_count,
        "suppressed_added_count": fact.suppressed_added_count,
        "suppressed_deleted_count": fact.suppressed_deleted_count,
        "records": [
            _record_digest_payload(record, before_columns, current_columns)
            for record in fact.records
        ],
        "ordered_extension": _ordered_extension_digest_payload(
            fact.ordered_extension, before_columns, current_columns
        ),
        "blank_extension": _blank_extension_digest_payload(fact.blank_extension),
    }


def _record_digest_payload(
    record: ComparisonRecord,
    before_columns: dict[str, SnapshotColumnDescriptor],
    current_columns: dict[str, SnapshotColumnDescriptor],
) -> dict[str, object]:
    return {
        "kind": record.record_kind.value,
        "row_identity": None if record.row_identity is None else record.row_identity.value,
        "changed_columns": list(record.changed_columns),
        "before_values": [
            [
                name,
                _value_digest_payload(value, before_columns.get(name)),
            ]
            for name, value in record.before_values
        ],
        "current_values": [
            [
                name,
                _value_digest_payload(value, current_columns.get(name)),
            ]
            for name, value in record.current_values
        ],
        "field_changes": [
            {
                "column": item.column_name,
                "before": _value_digest_payload(
                    item.before_value,
                    before_columns.get(item.column_name),
                ),
                "current": _value_digest_payload(
                    item.current_value,
                    current_columns.get(item.column_name),
                ),
            }
            for item in record.field_changes
        ],
    }


def _ordered_policy_payload(policy: Any) -> dict[str, object] | None:
    if policy is None:
        return None
    return {
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "order_key": list(policy.order_key),
        "row_identity_key": None if policy.row_identity_key is None else list(policy.row_identity_key),
        "stable_key_candidates": list(policy.stable_key_candidates),
        "value_columns": list(policy.value_columns),
        "ignored_columns": list(policy.ignored_columns),
        "blank_row_policy": policy.blank_row_policy.value,
        "move_policy": policy.move_policy,
        "ambiguity_policy": policy.ambiguity_policy,
        "tail_change_policy": policy.tail_change_policy,
        "table_processing_mode_policy": policy.table_processing_mode_policy,
        "policy_digest": None if policy.policy_digest is None else policy.policy_digest.value,
    }


def _ordered_extension_digest_payload(
    extension: Any,
    before_columns: dict[str, SnapshotColumnDescriptor],
    current_columns: dict[str, SnapshotColumnDescriptor],
) -> dict[str, object] | None:
    if extension is None:
        return None
    return {
        "contract_version": extension.contract_version,
        "status": extension.status.value,
        "summary": {
            "row_added": extension.ordered_summary.row_added_count,
            "row_deleted": extension.ordered_summary.row_deleted_count,
            "row_modified": extension.ordered_summary.row_modified_count,
            "row_moved": extension.ordered_summary.row_moved_count,
            "position_changed": extension.ordered_summary.position_changed_count,
            "degraded": extension.ordered_summary.degraded_count,
        },
        "before_ordered_digest": (
            None if extension.before_ordered_digest is None else extension.before_ordered_digest.value
        ),
        "current_ordered_digest": (
            None if extension.current_ordered_digest is None else extension.current_ordered_digest.value
        ),
        "replay_guarantee": extension.replay_guarantee.value,
        "table_processing_mode": (
            None if extension.table_processing_mode is None else extension.table_processing_mode.value
        ),
        "policy_digest": None if extension.policy_digest is None else extension.policy_digest.value,
        "records": [
            {
                "record_kind": record.record_kind.value,
                "semantic_kind": record.semantic_kind.value,
                "entity_key_kind": record.entity_key_kind.value,
                "row_identity": None if record.row_identity is None else record.row_identity.value,
                "before_position": record.before_position,
                "current_position": record.current_position,
                "changed_columns": list(record.changed_columns),
                "before_values": [
                    [name, _value_digest_payload(value, before_columns.get(name))]
                    for name, value in record.before_values
                ],
                "current_values": [
                    [name, _value_digest_payload(value, current_columns.get(name))]
                    for name, value in record.current_values
                ],
            }
            for record in extension.records
        ],
    }


def _blank_extension_digest_payload(extension: Any) -> dict[str, object] | None:
    if extension is None:
        return None
    return {
        "contract_version": extension.contract_version,
        "status": extension.status.value,
        "summary": {
            "inserted": extension.blank_summary.interval_inserted_count,
            "deleted": extension.blank_summary.interval_deleted_count,
            "changed": extension.blank_summary.blank_changed_count,
            "degraded": extension.blank_summary.degraded_count,
        },
        "before_occupancy_digest": (
            None
            if extension.before_occupancy_digest is None
            else extension.before_occupancy_digest.value
        ),
        "current_occupancy_digest": (
            None
            if extension.current_occupancy_digest is None
            else extension.current_occupancy_digest.value
        ),
        "replay_guarantee": extension.replay_guarantee.value,
        "records": [
            {
                "record_kind": record.record_kind.value,
                "semantic_kind": record.semantic_kind.value,
                "entity_key_kind": record.entity_key_kind.value,
                "interval": {
                    "before_start": record.interval.before_start,
                    "before_end": record.interval.before_end,
                    "current_start": record.interval.current_start,
                    "current_end": record.interval.current_end,
                    "row_count": record.interval.row_count,
                    "interval_digest": (
                        None
                        if record.interval.interval_digest is None
                        else record.interval.interval_digest.value
                    ),
                },
                "before_occupancy": record.before_occupancy,
                "current_occupancy": record.current_occupancy,
            }
            for record in extension.records
        ],
    }


def _value_digest_payload(
    value: object,
    column: SnapshotColumnDescriptor | None,
) -> str:
    if isinstance(value, _TYPED_SCALAR_TYPES):
        if column is None:
            return encode_typed_scalar(_infer_declared_type(value), value).scalar_frame.hex()
        return _encode_cell(column, value).hex()
    if type(value).__name__ == "SqlSetValue":
        members = getattr(value, "members", ())
        string_type = DeclaredType(kind=DeclaredTypeKind.STRING)
        return encode_collection(
            CollectionSemantics.SEQUENCE,
            items=tuple(
                encode_typed_scalar(string_type, StringScalar(item)).scalar_frame
                for item in members
            ),
        ).collection_frame.hex()
    raise StandardComparisonError("SCALAR_VALUE_INVALID")


def _summary_payload(summary: ComparisonSummary) -> dict[str, object]:
    return {
        "status": summary.status.value,
        "table_count": summary.table_count,
        "unchanged_table_count": summary.unchanged_table_count,
        "changed_table_count": summary.changed_table_count,
        "added_table_count": summary.added_table_count,
        "deleted_table_count": summary.deleted_table_count,
        "schema_changed_table_count": summary.schema_changed_table_count,
        "degraded_table_count": summary.degraded_table_count,
        "row_added_count": summary.row_added_count,
        "row_deleted_count": summary.row_deleted_count,
        "row_modified_count": summary.row_modified_count,
        "suppressed_added_count": summary.suppressed_added_count,
        "suppressed_deleted_count": summary.suppressed_deleted_count,
    }


def _digest_from_key(key: bytes) -> DigestRef:
    return semantic_digest(DigestKind.ROW, key).digest_ref
