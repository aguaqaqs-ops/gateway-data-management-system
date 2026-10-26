"""Reference ordered and blank comparison kernel.

The kernel is deliberately table-local and consumes only public comparison/snapshot contracts.  It
uses stable keys for entity matching, ``no`` for ordered facts, and never treats a physical pseudo gid
as a cross-snapshot business identity.
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from gateway_shared_kernel import (
    DigestKind,
    DigestRef,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    UnsignedIntegerScalar,
    raw_blob_digest,
    semantic_digest,
)
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.comparison.contracts import (
    ArtifactScope,
    BlankExtension,
    BlankRecord,
    BlankRecordKind,
    BlankSemanticKind,
    BlankSummary,
    ComparisonRecord,
    ComparisonRecordKind,
    ComparisonSchemaChanges,
    ComparisonTableFact,
    _ComparisonTablePolicy,
    ComparisonTableStatus,
    SchemaChangeSource,
    FieldChange,
    GID_PSEUDO_MAX,
    GID_PSEUDO_MIN,
    GID_REAL_MAX,
    GID_REAL_MIN,
    OrderedExtension,
    OrderedInterval,
    OrderedRecord,
    OrderedRecordKind,
    OrderedSemanticKind,
    OrderedStatus,
    OrderedSummary,
    OrderedTablePolicy,
    OrderedTableProcessingMode,
    ReplayGuarantee,
    TableComparisonTask,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BlankRowProvenance,
    SnapshotColumnDescriptor,
    SnapshotTable,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.comparison.errors import StandardComparisonError
from gateway_backend.capabilities.comparison.row_encoding import (
    _EncodedRow,
    _can_table_early_exit,
    _encode_cell,
    _ignored_values_changed,
    _row_digest,
    _schema_changes_from_view,
    _schema_view,
)


class OrderedComparisonError(StandardComparisonError):
    """A deterministic table-local ordered failure."""


@dataclass(frozen=True, slots=True)
class _OrderedRow:
    encoded: _EncodedRow
    position: int
    stable_key: bytes | None
    stable_identity: DigestRef | None
    blank: bool


@dataclass(frozen=True, slots=True)
class _BlankGap:
    count: int
    start: int
    end: int


def compare_ordered_task(task: TableComparisonTask) -> ComparisonTableFact:
    """Compare one ordered table while preserving standard facts for real stable rows."""

    if type(task.policy) is not _ComparisonTablePolicy or task.policy.ordered_policy is None:
        raise OrderedComparisonError("ORDERED_POLICY_MISSING")
    policy = task.policy
    ordered_policy = policy.ordered_policy
    assert ordered_policy is not None
    before = task.before_descriptor
    current = task.current_descriptor
    if before is None and current is None:
        raise OrderedComparisonError("TABLE_TASK_HAS_NO_SIDE")

    if before is None:
        try:
            return _compare_single_side(task, current, task.current_table, added=True, policy=policy)
        except StandardComparisonError as exc:
            assert current is not None
            return _degraded_fact(
                task,
                None,
                current,
                _single_side_schema_changes(current, added=True, policy=policy),
                (str(exc),),
            )
    if current is None:
        try:
            return _compare_single_side(task, before, task.before_table, added=False, policy=policy)
        except StandardComparisonError as exc:
            return _degraded_fact(
                task,
                before,
                None,
                _single_side_schema_changes(before, added=False, policy=policy),
                (str(exc),),
            )

    schema = _schema_view(before, current, policy)
    schema_changes = _schema_changes_from_view(schema, policy)
    diagnostics = _ordered_schema_diagnostics(before, current, ordered_policy, schema)
    if diagnostics:
        return _degraded_fact(task, before, current, schema_changes, diagnostics)

    if _can_table_early_exit(before, current, policy):
        try:
            current_rows = _read_ordered_rows(
                task.current_table,
                current,
                schema.selected,
                ordered_policy,
            )
        except StandardComparisonError as exc:
            return _degraded_fact(task, before, current, schema_changes, (str(exc),))
        return _build_fact(
            table_name=task.table_name,
            before_descriptor=before,
            current_descriptor=current,
            before_rows=current_rows,
            current_rows=current_rows,
            selected=schema.selected,
            policy=policy,
            ordered_policy=ordered_policy,
            artifact_scope=task.artifact_scope,
            schema_changes=schema_changes,
            schema_diagnostics=(),
        )

    try:
        before_rows = _read_ordered_rows(task.before_table, before, schema.selected, ordered_policy)
        current_rows = _read_ordered_rows(task.current_table, current, schema.selected, ordered_policy)
    except StandardComparisonError as exc:
        diagnostics = (str(exc),)
        return _degraded_fact(task, before, current, schema_changes, diagnostics)
    return _build_fact(
        table_name=task.table_name,
        before_descriptor=before,
        current_descriptor=current,
        before_rows=before_rows,
        current_rows=current_rows,
        selected=schema.selected,
        policy=policy,
        ordered_policy=ordered_policy,
        artifact_scope=task.artifact_scope,
        schema_changes=schema_changes,
        schema_diagnostics=(),
    )


def _compare_single_side(
    task: TableComparisonTask,
    descriptor: SnapshotTableDescriptor | None,
    table: SnapshotTable | None,
    *,
    added: bool,
    policy: _ComparisonTablePolicy,
) -> ComparisonTableFact:
    if descriptor is None:
        raise OrderedComparisonError("TABLE_DESCRIPTOR_MISSING")
    assert policy.ordered_policy is not None
    schema_changes = _single_side_schema_changes(descriptor, added=added, policy=policy)
    selected = schema_changes.selected_columns
    rows = _read_ordered_rows(table, descriptor, selected, policy.ordered_policy)
    empty: tuple[_OrderedRow, ...] = ()
    return _build_fact(
        table_name=task.table_name,
        before_descriptor=None if added else descriptor,
        current_descriptor=descriptor if added else None,
        before_rows=empty if added else rows,
        current_rows=rows if added else empty,
        selected=selected,
        policy=policy,
        ordered_policy=policy.ordered_policy,
        artifact_scope=task.artifact_scope,
        schema_changes=schema_changes,
        schema_diagnostics=(),
    )


def _ordered_schema_diagnostics(
    before: SnapshotTableDescriptor,
    current: SnapshotTableDescriptor,
    policy: OrderedTablePolicy,
    schema: Any,
) -> tuple[str, ...]:
    before_names = {column.name for column in before.columns}
    current_names = {column.name for column in current.columns}
    required = set(policy.order_key)
    if policy.row_identity_key is not None:
        required.update(policy.row_identity_key)
    missing = sorted((required - before_names) | (required - current_names))
    diagnostics: list[str] = []
    if missing:
        diagnostics.append("ORDERED_REQUIRED_COLUMN_MISSING")
    if schema.incompatible:
        diagnostics.append("INCOMPATIBLE_SELECTED_COLUMNS")
    if schema.selected == ():
        diagnostics.append("NO_SELECTED_COLUMNS")
    if policy.row_identity_key is None:
        diagnostics.append("ROW_IDENTITY_MISSING")
    return tuple(dict.fromkeys(diagnostics))


def _degraded_fact(
    task: TableComparisonTask,
    before: SnapshotTableDescriptor | None,
    current: SnapshotTableDescriptor | None,
    schema_changes: ComparisonSchemaChanges,
    diagnostics: tuple[str, ...],
) -> ComparisonTableFact:
    return ComparisonTableFact(
        table_name=task.table_name,
        status=ComparisonTableStatus.DEGRADED,
        before_descriptor=before,
        current_descriptor=current,
        schema_changes=schema_changes,
        row_count_before=None if before is None else before.row_count,
        row_count_current=None if current is None else current.row_count,
        records=(
            ComparisonRecord(
                table_name=task.table_name,
                record_kind=ComparisonRecordKind.TABLE_DEGRADED,
                diagnostics=diagnostics,
            ),
        ),
        diagnostics=diagnostics,
        ordered_extension=OrderedExtension(
            status=OrderedStatus.DEGRADED,
            ordered_summary=OrderedSummary(degraded_count=1),
            replay_guarantee=ReplayGuarantee.UNSUPPORTED,
            table_processing_mode=OrderedTableProcessingMode.DEGRADED,
            diagnostics=diagnostics,
            policy_digest=task.policy.ordered_policy.policy_digest if task.policy and task.policy.ordered_policy else None,
        ),
        blank_extension=BlankExtension(
            status=OrderedStatus.DEGRADED,
            blank_summary=BlankSummary(degraded_count=1),
            replay_guarantee=ReplayGuarantee.UNSUPPORTED,
            diagnostics=diagnostics,
        ),
    )


def _single_side_schema_changes(
    descriptor: SnapshotTableDescriptor,
    *,
    added: bool,
    policy: _ComparisonTablePolicy,
) -> ComparisonSchemaChanges:
    selected = tuple(sorted(column.name for column in descriptor.columns))
    return ComparisonSchemaChanges(
        current_only_columns=selected if added else (),
        before_only_columns=() if added else selected,
        selected_columns=selected,
        effective_compare_key_current=policy.effective_key_current if added else (),
        effective_compare_key_before=() if added else policy.effective_key_before,
        change_source=SchemaChangeSource.SOURCE_SCHEMA,
    )


def _read_ordered_rows(
    table: SnapshotTable | None,
    descriptor: SnapshotTableDescriptor,
    selected: tuple[str, ...],
    policy: OrderedTablePolicy,
) -> tuple[_OrderedRow, ...]:
    if table is None or table.reader is None:
        raise OrderedComparisonError("TABLE_READER_UNAVAILABLE")
    if table.ordered_metadata is None:
        raise OrderedComparisonError("BLANK_PROVENANCE_MISSING")
    by_name = {column.name: (index, column) for index, column in enumerate(descriptor.columns)}
    order_column = _single_column(policy.order_key, "ORDER_KEY_UNSUPPORTED")
    stable_column = (
        None if policy.row_identity_key is None else _single_column(policy.row_identity_key, "ROW_IDENTITY_UNSUPPORTED")
    )
    order_index, order_descriptor = by_name[order_column]
    stable_index_and_descriptor = None if stable_column is None else by_name[stable_column]
    selected_set = set(selected)
    required_set = set(policy.order_key) | set(policy.row_identity_key or ())
    rows: list[_OrderedRow] = []
    reader = table.reader.reopen()
    try:
        for raw_row in reader.iter_rows():
            if type(raw_row) is not tuple or len(raw_row) != len(descriptor.columns):
                raise OrderedComparisonError("ROW_SHAPE_MISMATCH")
            position = _parse_position(raw_row[order_index], order_descriptor)
            values: list[tuple[str, object]] = []
            frames: list[tuple[str, bytes]] = []
            for column, cell in zip(descriptor.columns, raw_row, strict=True):
                if column.name not in selected_set and column.name not in required_set:
                    continue
                values.append((column.name, cell))
                frames.append((column.name, _encode_cell(column, cell)))
            encoded = _EncodedRow(tuple(sorted(values)), tuple(sorted(frames)))
            stable_value: int | None = None
            if stable_index_and_descriptor is not None:
                stable_index, stable_descriptor = stable_index_and_descriptor
                stable_value = _parse_stable(raw_row[stable_index], table.ordered_metadata.blank_provenance)
                blank = stable_value is None
                if blank:
                    stable_key = None
                    stable_identity = None
                else:
                    assert stable_column is not None
                    stable_key = _encode_cell(stable_descriptor, raw_row[stable_index])
                    stable_identity = _row_digest(encoded, (stable_column,))
            else:
                stable_key = None
                stable_identity = None
                blank = False
            rows.append(
                _OrderedRow(
                    encoded=encoded,
                    position=position,
                    stable_key=stable_key,
                    stable_identity=stable_identity,
                    blank=blank,
                )
            )
    finally:
        reader.close()
    positions = [row.position for row in rows]
    if len(set(positions)) != len(positions):
        raise OrderedComparisonError("ORDER_KEY_DUPLICATE")
    if any(position < 1 for position in positions):
        raise OrderedComparisonError("ORDER_KEY_INVALID")
    rows.sort(key=lambda row: row.position)
    identities = [row.stable_key for row in rows if not row.blank]
    if len(set(identities)) != len(identities):
        raise OrderedComparisonError("ROW_IDENTITY_DUPLICATE")
    return tuple(rows)


def _single_column(columns: tuple[str, ...], diagnostic: str) -> str:
    if len(columns) != 1:
        raise OrderedComparisonError(diagnostic)
    return columns[0]


def _parse_position(cell: object, descriptor: SnapshotColumnDescriptor) -> int:
    value = _integer(cell)
    if value is None or value < 1:
        raise OrderedComparisonError("ORDER_KEY_MISSING")
    del descriptor
    return value


def _parse_stable(cell: object, provenance: BlankRowProvenance) -> int | None:
    value = _integer(cell)
    if provenance is BlankRowProvenance.SOURCE_MISSING_STABLE_KEY:
        if value is None or value == 0:
            return None
        if GID_REAL_MIN <= value <= GID_REAL_MAX:
            return value
        if GID_PSEUDO_MIN <= value <= GID_PSEUDO_MAX:
            raise OrderedComparisonError("SOURCE_RESERVED_PSEUDO_GID")
        raise OrderedComparisonError("SOURCE_GID_INVALID")
    if provenance is BlankRowProvenance.CANONICAL_PSEUDO_GID:
        if value is None or value == 0:
            raise OrderedComparisonError("CANONICAL_BLANK_PROVENANCE_INVALID")
        if GID_PSEUDO_MIN <= value <= GID_PSEUDO_MAX:
            return None
        if GID_REAL_MIN <= value <= GID_REAL_MAX:
            return value
        raise OrderedComparisonError("CANONICAL_GID_INVALID")
    raise OrderedComparisonError("BLANK_PROVENANCE_INVALID")


def _integer(cell: object) -> int | None:
    if isinstance(cell, NullScalar):
        return None
    if isinstance(cell, StringScalar):
        if cell.text == "":
            return None
        raise OrderedComparisonError("ORDERED_INTEGER_INVALID")
    if isinstance(cell, (SignedIntegerScalar, UnsignedIntegerScalar)):
        try:
            return int(cell.decimal, 10)
        except ValueError as exc:
            raise OrderedComparisonError("ORDERED_INTEGER_INVALID") from exc
    raise OrderedComparisonError("ORDERED_INTEGER_INVALID")


def _build_fact(
    *,
    table_name: str,
    before_descriptor: SnapshotTableDescriptor | None,
    current_descriptor: SnapshotTableDescriptor | None,
    before_rows: tuple[_OrderedRow, ...],
    current_rows: tuple[_OrderedRow, ...],
    selected: tuple[str, ...],
    policy: _ComparisonTablePolicy,
    ordered_policy: OrderedTablePolicy,
    artifact_scope: ArtifactScope,
    schema_changes: ComparisonSchemaChanges,
    schema_diagnostics: tuple[str, ...],
) -> ComparisonTableFact:
    before_real = {row.stable_key: row for row in before_rows if not row.blank and row.stable_key is not None}
    current_real = {row.stable_key: row for row in current_rows if not row.blank and row.stable_key is not None}
    added_keys = sorted(current_real.keys() - before_real.keys())
    deleted_keys = sorted(before_real.keys() - current_real.keys())
    common_keys = sorted(before_real.keys() & current_real.keys())
    compare_excluded_columns = set(policy.compare_excluded_columns)
    candidate_value_columns = ordered_policy.value_columns or tuple(
        column
        for column in selected
        if column not in set(ordered_policy.order_key)
        and column not in set(ordered_policy.row_identity_key or ())
    )
    value_columns = tuple(
        column for column in candidate_value_columns if column not in compare_excluded_columns
    )
    standard_records: list[ComparisonRecord] = []
    ordered_records: list[OrderedRecord] = []
    modified_keys: list[bytes] = []
    for key in added_keys:
        row = current_real[key]
        if artifact_scope is ArtifactScope.ALL_CHANGES:
            standard_records.append(_standard_row_record(table_name, ComparisonRecordKind.ROW_ADDED, row, selected, True, policy))
            ordered_records.append(
                OrderedRecord(
                    table_name=table_name,
                    record_kind=OrderedRecordKind.ROW_ADDED,
                    semantic_kind=OrderedSemanticKind.DATA_INSERT,
                    row_identity=row.stable_identity,
                    current_position=row.position,
                    current_values=_values(row, value_columns),
                )
            )
    for key in deleted_keys:
        row = before_real[key]
        if artifact_scope is ArtifactScope.ALL_CHANGES:
            standard_records.append(_standard_row_record(table_name, ComparisonRecordKind.ROW_DELETED, row, selected, False, policy))
            ordered_records.append(
                OrderedRecord(
                    table_name=table_name,
                    record_kind=OrderedRecordKind.ROW_DELETED,
                    semantic_kind=OrderedSemanticKind.DATA_DELETE,
                    row_identity=row.stable_identity,
                    before_position=row.position,
                    before_values=_values(row, value_columns),
                )
            )
    for key in common_keys:
        before_row = before_real[key]
        current_row = current_real[key]
        changed = tuple(
            column
            for column in value_columns
            if before_row.encoded.frame_map()[column] != current_row.encoded.frame_map()[column]
        )
        if not changed:
            continue
        modified_keys.append(key)
        assert before_row.stable_identity is not None
        field_changes = tuple(
            FieldChange(
                table_name=table_name,
                row_identity=before_row.stable_identity,
                column_name=column,
                before_value=before_row.encoded.value_map()[column],
                current_value=current_row.encoded.value_map()[column],
            )
            for column in changed
        )
        standard_records.append(
            ComparisonRecord(
                table_name=table_name,
                record_kind=ComparisonRecordKind.ROW_MODIFIED,
                row_identity=before_row.stable_identity,
                changed_columns=changed,
                before_values=_values(before_row, changed),
                current_values=_values(current_row, changed),
                field_changes=field_changes,
            )
        )
        ordered_records.append(
            OrderedRecord(
                table_name=table_name,
                record_kind=OrderedRecordKind.ROW_MODIFIED,
                semantic_kind=OrderedSemanticKind.CONTENT_UPDATE,
                row_identity=before_row.stable_identity,
                before_position=before_row.position,
                current_position=current_row.position,
                before_values=_values(before_row, changed),
                current_values=_values(current_row, changed),
                changed_columns=changed,
            )
        )

    common_keys_in_before_order = [
        row.stable_key
        for row in before_rows
        if row.stable_key is not None and row.stable_key in current_real
    ]
    backbone = frozenset(
        common_keys_in_before_order[index]
        for index in _backbone_indices([current_real[key].position for key in common_keys_in_before_order])
    )
    moved_keys = {key for key in common_keys if key not in backbone}
    for key in sorted(moved_keys):
        before_row = before_real[key]
        current_row = current_real[key]
        ordered_records.append(
            OrderedRecord(
                table_name=table_name,
                record_kind=OrderedRecordKind.ROW_MOVED,
                semantic_kind=OrderedSemanticKind.MOVE,
                row_identity=before_row.stable_identity,
                before_position=before_row.position,
                current_position=current_row.position,
            )
        )
    position_changed_keys = {
        key for key in backbone if before_real[key].position != current_real[key].position
    }

    blank_extension = _blank_extension(
        table_name,
        before_rows,
        current_rows,
        backbone=backbone,
        include_records=artifact_scope is ArtifactScope.ALL_CHANGES,
    )
    ordered_summary = OrderedSummary(
        row_added_count=len(added_keys),
        row_deleted_count=len(deleted_keys),
        row_modified_count=len(modified_keys),
        row_moved_count=len(moved_keys),
        position_changed_count=len(position_changed_keys),
    )
    ordered_changed = bool(ordered_records) or bool(added_keys or deleted_keys or position_changed_keys)
    blank_changed = blank_extension.status is OrderedStatus.CHANGED
    schema_changed = (
        before_descriptor is not None
        and current_descriptor is not None
        and before_descriptor.business_schema_digest != current_descriptor.business_schema_digest
    )
    status = ComparisonTableStatus.MODIFIED if ordered_changed or blank_changed else (
        ComparisonTableStatus.SCHEMA_ONLY_CHANGED if schema_changed else ComparisonTableStatus.UNCHANGED
    )
    if before_descriptor is None:
        status = ComparisonTableStatus.ADDED_TABLE
    elif current_descriptor is None:
        status = ComparisonTableStatus.DELETED_TABLE
    table_processing_mode = _processing_mode(
        moved=bool(moved_keys),
        shifted=bool(position_changed_keys),
        segment=bool(added_keys or deleted_keys) or blank_changed,
        modified=bool(modified_keys),
    )
    ordered_extension = OrderedExtension(
        status=(
            OrderedStatus.CHANGED
            if table_processing_mode is not None
            else OrderedStatus.UNCHANGED
        ),
        ordered_summary=ordered_summary,
        records=tuple(sorted(ordered_records, key=_ordered_sort_key)),
        before_ordered_digest=_ordered_digest(before_rows, ordered_policy, table_name),
        current_ordered_digest=_ordered_digest(current_rows, ordered_policy, table_name),
        replay_guarantee=ReplayGuarantee.EXACT,
        table_processing_mode=table_processing_mode,
        diagnostics=schema_diagnostics,
        policy_digest=ordered_policy.policy_digest,
    )
    diagnostics = tuple(schema_diagnostics)
    content_changed = (
        status is ComparisonTableStatus.UNCHANGED
        and before_descriptor is not None
        and current_descriptor is not None
        and _ignored_values_changed(before_descriptor, current_descriptor, policy)
    )
    return ComparisonTableFact(
        table_name=table_name,
        status=status,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        schema_changes=schema_changes,
        row_count_before=None if before_descriptor is None else before_descriptor.row_count,
        row_count_current=None if current_descriptor is None else current_descriptor.row_count,
        row_added_count=len(added_keys),
        row_deleted_count=len(deleted_keys),
        row_modified_count=len(modified_keys),
        suppressed_added_count=len(added_keys) if artifact_scope is ArtifactScope.UPDATE_ONLY else 0,
        suppressed_deleted_count=len(deleted_keys) if artifact_scope is ArtifactScope.UPDATE_ONLY else 0,
        records=tuple(sorted(standard_records, key=_standard_sort_key)),
        diagnostics=diagnostics,
        content_changed=content_changed,
        ordered_extension=ordered_extension,
        blank_extension=blank_extension,
    )


def _standard_row_record(
    table_name: str,
    kind: ComparisonRecordKind,
    row: _OrderedRow,
    selected: tuple[str, ...],
    current: bool,
    policy: _ComparisonTablePolicy,
) -> ComparisonRecord:
    values = _values(row, selected)
    return ComparisonRecord(
        table_name=table_name,
        record_kind=kind,
        row_identity=row.stable_identity,
        before_values=() if current else values,
        current_values=values if current else (),
        diagnostics=() if not policy.ordered_policy else ("ORDERED_PROVIDER",),
    )


def _values(row: _OrderedRow, columns: tuple[str, ...]) -> tuple[tuple[str, object], ...]:
    value_map = row.encoded.value_map()
    return tuple((column, value_map[column]) for column in columns if column in value_map)


def _blank_gaps(
    rows: tuple[_OrderedRow, ...], anchors: frozenset[bytes] | None
) -> dict[tuple[str | None, str | None], _BlankGap]:
    """Blank rows grouped by the anchor pair that bounds them.

    ``anchors`` holds the stable keys of the rows that bound intervals.  ``None`` makes every real row an
    anchor, which describes one side's own blank distribution.  Real rows outside ``anchors`` do not split
    blank segments.
    """

    gaps: dict[tuple[str | None, str | None], _BlankGap] = {}
    before_anchor: str | None = None
    count = 0
    start = 0
    end = 0
    for row in rows:
        if row.blank:
            if count == 0:
                start = row.position
            count += 1
            end = row.position
            continue
        if anchors is not None and row.stable_key not in anchors:
            continue
        assert row.stable_identity is not None
        after_anchor = row.stable_identity.value
        if count:
            gaps[(before_anchor, after_anchor)] = _BlankGap(count=count, start=start, end=end)
        before_anchor = after_anchor
        count = 0
    if count:
        gaps[(before_anchor, None)] = _BlankGap(count=count, start=start, end=end)
    return gaps


def _blank_extension(
    table_name: str,
    before_rows: tuple[_OrderedRow, ...],
    current_rows: tuple[_OrderedRow, ...],
    *,
    backbone: frozenset[bytes],
    include_records: bool,
) -> BlankExtension:
    before_gaps = _blank_gaps(before_rows, backbone)
    current_gaps = _blank_gaps(current_rows, backbone)
    keys = sorted(set(before_gaps) | set(current_gaps), key=lambda item: (item[0] or "", item[1] or ""))
    records: list[BlankRecord] = []
    inserted_count = 0
    deleted_count = 0
    for key in keys:
        before = before_gaps.get(key)
        current = current_gaps.get(key)
        before_count = 0 if before is None else before.count
        current_count = 0 if current is None else current.count
        if before_count == current_count:
            continue
        selected_count = current_count if current is not None else before_count
        interval = OrderedInterval(
            before_start=None if before is None else before.start,
            before_end=None if before is None else before.end,
            current_start=None if current is None else current.start,
            current_end=None if current is None else current.end,
            row_count=abs(current_count - before_count),
            interval_digest=_blank_interval_digest(key, selected_count),
        )
        if before_count > current_count:
            deleted_count += 1
            records.append(
                BlankRecord(
                    table_name=table_name,
                    record_kind=BlankRecordKind.DELETE_INTERVAL,
                    semantic_kind=BlankSemanticKind.DELETE_INTERVAL,
                    interval=interval,
                    before_occupancy=before_count,
                    current_occupancy=current_count,
                )
            )
        else:
            inserted_count += 1
            records.append(
                BlankRecord(
                    table_name=table_name,
                    record_kind=BlankRecordKind.INSERT_INTERVAL,
                    semantic_kind=BlankSemanticKind.INSERT_INTERVAL,
                    interval=interval,
                    before_occupancy=before_count,
                    current_occupancy=current_count,
                )
            )
    return BlankExtension(
        status=(
            OrderedStatus.CHANGED
            if inserted_count or deleted_count
            else OrderedStatus.UNCHANGED
        ),
        blank_summary=BlankSummary(
            interval_inserted_count=inserted_count,
            interval_deleted_count=deleted_count,
            blank_changed_count=inserted_count + deleted_count,
        ),
        records=tuple(records) if include_records else (),
        before_occupancy_digest=_occupancy_digest(_blank_gaps(before_rows, None)),
        current_occupancy_digest=_occupancy_digest(_blank_gaps(current_rows, None)),
    )


def _blank_interval_digest(key: tuple[str | None, str | None], count: int) -> DigestRef:
    return raw_blob_digest(canonicalize_json_value({"before": key[0], "after": key[1], "count": count}))


def _occupancy_digest(gaps: dict[tuple[str | None, str | None], _BlankGap]) -> DigestRef:
    payload = [
        {"before": key[0], "after": key[1], "count": gap.count}
        for key, gap in sorted(gaps.items(), key=lambda item: (item[0][0] or "", item[0][1] or ""))
    ]
    return raw_blob_digest(canonicalize_json_value(payload))


def _ordered_digest(
    rows: tuple[_OrderedRow, ...], policy: OrderedTablePolicy, table_name: str
) -> DigestRef:
    payload = {
        "kind": "ordered-logical-digest",
        "contract_version": policy.policy_version,
        "table_name": table_name,
        "rows": [
            {
                "stable": row.stable_identity.value if row.stable_identity is not None else None,
                "position": row.position,
                "blank": row.blank,
                "content": (
                    semantic_digest(DigestKind.ROW, _row_content_frame(row, policy)).digest_ref.value
                    if not row.blank
                    else None
                ),
            }
            for row in rows
        ],
    }
    return raw_blob_digest(canonicalize_json_value(payload))


def _row_content_frame(row: _OrderedRow, policy: OrderedTablePolicy) -> bytes:
    values = row.encoded.frame_map()
    columns = policy.value_columns or tuple(
        name
        for name, _ in row.encoded.values
        if name not in set(policy.order_key) and name not in set(policy.row_identity_key or ())
    )
    return b"".join(values[name] for name in columns if name in values)


def _backbone_indices(positions: Sequence[int]) -> tuple[int, ...]:
    """Indices of a longest increasing subsequence; among equal-length choices the earliest indices win.

    ``positions`` are the current-side positions of the common rows in before order, all distinct.
    ``reach[i]`` is the length of the longest increasing run that starts at ``i``; patience sorting over the
    reversed, negated sequence computes it in O(n log n).  Walking the lengths from the longest down, each pick
    is the first index after the previous pick whose reach equals the remaining length.  That is the
    lexicographically smallest index sequence among all longest subsequences.
    """

    if not positions:
        return ()
    reach = [0] * len(positions)
    tails: list[int] = []
    for index in range(len(positions) - 1, -1, -1):
        value = -positions[index]
        slot = bisect.bisect_left(tails, value)
        if slot == len(tails):
            tails.append(value)
        else:
            tails[slot] = value
        reach[index] = slot + 1
    longest = max(reach)
    levels: list[list[int]] = [[] for _ in range(longest + 1)]
    for index, length in enumerate(reach):
        levels[length].append(index)
    chosen: list[int] = []
    previous = -1
    for length in range(longest, 0, -1):
        candidates = levels[length]
        pick = candidates[bisect.bisect_right(candidates, previous)]
        chosen.append(pick)
        previous = pick
    return tuple(chosen)


def _processing_mode(
    *, moved: bool, shifted: bool, segment: bool, modified: bool
) -> OrderedTableProcessingMode | None:
    """Table mode from the first matching rule: moves, shifts, tail segments, then local patches."""

    if moved:
        return OrderedTableProcessingMode.REORDER_COMPLEX
    if shifted:
        return OrderedTableProcessingMode.SHIFT_REPAIRED
    if segment and not modified:
        return OrderedTableProcessingMode.TAIL_SEGMENT
    if modified:
        return OrderedTableProcessingMode.LOCAL_PATCH
    return None


def _ordered_sort_key(record: OrderedRecord) -> tuple[str, int, str]:
    return (
        record.record_kind.value,
        record.current_position or record.before_position or 0,
        "" if record.row_identity is None else record.row_identity.value,
    )


def _standard_sort_key(record: ComparisonRecord) -> tuple[str, str, tuple[str, ...]]:
    return (
        record.record_kind.value,
        "" if record.row_identity is None else record.row_identity.value,
        record.changed_columns,
    )
