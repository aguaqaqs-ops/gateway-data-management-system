from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ...core.digests import DigestRef
from ...core.diagnostics import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from ...core.scalar_encoding import normalize_snapshot_row
from ..snapshot_materialization.models import (
    SnapshotTable,
    SnapshotTableColumn,
    SnapshotTableDescriptor,
)
from ..table_rules import enters_comparison_for_static_role
from .digest import (
    ProjectionLogicalDigestParts,
    build_projection_logical_digest_parts,
    build_projection_schema_digest,
)
from .models import ProjectionSchema, ProjectionTable, TableRulesetTableRule


@dataclass(frozen=True, slots=True)
class ProjectionRowsReader:
    projection_schema: ProjectionSchema
    columns: tuple[SnapshotTableColumn, ...]
    rows: tuple[tuple[object, ...], ...]
    projection_logical_digest_parts: ProjectionLogicalDigestParts | None = None

    def iter_rows(self):
        yield from self.rows

    def close(self) -> None:
        return None


@dataclass(frozen=True, slots=True)
class ProjectionBuilder:
    def project(
        self,
        table: SnapshotTable,
        *,
        source_snapshot_digest: DigestRef | str,
        projection_schema: ProjectionSchema,
        row_identity_columns: Sequence[str] | None = None,
        reader: object | None = None,
        artifact_ref: object | None = None,
        diagnostics: tuple[DiagnosticRecord, ...] = (),
    ) -> ProjectionTable:
        if not isinstance(table, SnapshotTable):
            raise TypeError("table must be a SnapshotTable")
        if not isinstance(projection_schema, ProjectionSchema):
            raise TypeError("projection_schema must be a ProjectionSchema")
        table_reader = reader or table.reader
        descriptor = table.descriptor
        descriptor_columns = tuple(descriptor.columns)
        selected_column_names = tuple(projection_schema.selected_columns)
        selected_columns = _selected_columns(descriptor, selected_column_names)
        selected_indexes = _selected_column_indexes(descriptor_columns, selected_columns)
        projected_rows = tuple(
            _project_raw_row_fast(
                raw_row=raw_row,
                columns=descriptor_columns,
                selected_indexes=selected_indexes,
            )
            for raw_row in table_reader.iter_rows()
        )
        if row_identity_columns is None:
            row_identity_columns = projection_schema.effective_compare_key
        projection_logical_digest = None
        projection_logical_digest_parts = None
        if row_identity_columns:
            projection_logical_digest_parts = build_projection_logical_digest_parts(
                rows=projected_rows,
                columns=selected_columns,
                projection_schema_digest=projection_schema.projection_schema_digest,
                row_identity_columns=tuple(row_identity_columns),
                scalar_encoding_version=projection_schema.scalar_encoding_version,
            )
            projection_logical_digest = projection_logical_digest_parts.projection_logical_digest
        projection_reader = ProjectionRowsReader(
            projection_schema=projection_schema,
            columns=selected_columns,
            rows=projected_rows,
            projection_logical_digest_parts=projection_logical_digest_parts,
        )
        return ProjectionTable(
            source_snapshot_digest=source_snapshot_digest,
            source_raw_content_digest=descriptor.raw_content_digest,
            source_table_name=descriptor.table_name,
            projection_schema=projection_schema,
            row_count=len(projected_rows),
            projection_logical_digest=projection_logical_digest,
            reader=projection_reader,
            artifact_ref=artifact_ref,
            diagnostics=diagnostics,
        )


def build_projection_schema(
    *,
    table_name: str,
    before_descriptor: SnapshotTableDescriptor | None = None,
    current_descriptor: SnapshotTableDescriptor | None = None,
    table_rule: TableRulesetTableRule | None = None,
    table_ruleset_version: str,
    projection_contract_version: str,
    scalar_encoding_version: str,
) -> ProjectionSchema:
    canonical_table_name = canonical_identifier(table_name)
    before_columns = _descriptor_column_names(before_descriptor)
    current_columns = _descriptor_column_names(current_descriptor)
    ignored_columns = tuple(table_rule.ignored_columns if table_rule is not None else ())
    ignored_set = set(ignored_columns)

    if before_columns and current_columns:
        shared_columns = tuple(sorted(set(before_columns).intersection(current_columns)))
        selected_source_columns = shared_columns
    else:
        selected_source_columns = tuple(sorted(set(before_columns or current_columns)))
    selected_columns = tuple(column for column in selected_source_columns if column not in ignored_set)
    selected_columns = _include_ordered_position_columns(
        selected_columns=selected_columns,
        selected_source_columns=selected_source_columns,
        table_rule=table_rule,
    )

    before_only_columns = tuple(sorted(set(before_columns) - set(current_columns) - ignored_set))
    current_only_columns = tuple(sorted(set(current_columns) - set(before_columns) - ignored_set))

    effective_compare_key = _resolve_effective_compare_key(
        table_rule=table_rule,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        ignored_set=ignored_set,
        selected_columns=set(selected_columns),
    )
    return ProjectionSchema(
        table_name=canonical_table_name,
        selected_columns=selected_columns,
        ignored_columns=ignored_columns,
        before_only_columns=before_only_columns,
        current_only_columns=current_only_columns,
        effective_compare_key=effective_compare_key,
        table_ruleset_version=table_ruleset_version,
        projection_contract_version=projection_contract_version,
        scalar_encoding_version=scalar_encoding_version,
        projection_schema_digest=build_projection_schema_digest(
            table_name=canonical_table_name,
            selected_columns=selected_columns,
            ignored_columns=ignored_columns,
            effective_compare_key=effective_compare_key,
            table_ruleset_version=table_ruleset_version,
            projection_contract_version=projection_contract_version,
            scalar_encoding_version=scalar_encoding_version,
        ),
    )


def project_rows(
    rows: Sequence[Sequence[object]],
    *,
    descriptor: SnapshotTableDescriptor,
    projection_schema: ProjectionSchema,
) -> tuple[tuple[object, ...], ...]:
    descriptor_columns = tuple(descriptor.columns)
    selected_columns = _selected_columns(descriptor, projection_schema.selected_columns)
    selected_indexes = _selected_column_indexes(descriptor_columns, selected_columns)
    return tuple(
        _project_raw_row_fast(
            raw_row=raw_row,
            columns=descriptor_columns,
            selected_indexes=selected_indexes,
        )
        for raw_row in rows
    )


def _descriptor_column_names(descriptor: SnapshotTableDescriptor | None) -> tuple[str, ...]:
    if descriptor is None:
        return ()
    return tuple(column.name for column in descriptor.columns)


def _selected_columns(
    descriptor: SnapshotTableDescriptor,
    selected_column_names: Sequence[str],
) -> tuple[SnapshotTableColumn, ...]:
    descriptor_columns = {column.name: column for column in descriptor.columns}
    selected_columns: list[SnapshotTableColumn] = []
    for column_name in selected_column_names:
        canonical_column_name = canonical_identifier(column_name)
        try:
            selected_columns.append(descriptor_columns[canonical_column_name])
        except KeyError as exc:
            raise ValueError(f"projection schema references missing column: {canonical_column_name}") from exc
    return tuple(selected_columns)


def _project_row(
    *,
    row: Sequence[object],
    columns: Sequence[SnapshotTableColumn],
    selected_columns: Sequence[SnapshotTableColumn],
) -> tuple[object, ...]:
    column_indexes = {column.name: index for index, column in enumerate(columns)}
    projected_values: list[object] = []
    for column in selected_columns:
        column_index = column_indexes[column.name]
        projected_values.append(row[column_index])
    return tuple(projected_values)


def _selected_column_indexes(
    columns: Sequence[SnapshotTableColumn],
    selected_columns: Sequence[SnapshotTableColumn],
) -> tuple[int, ...]:
    column_indexes = {column.name: index for index, column in enumerate(columns)}
    return tuple(column_indexes[column.name] for column in selected_columns)


def _project_raw_row_fast(
    *,
    raw_row: Sequence[object],
    columns: Sequence[SnapshotTableColumn],
    selected_indexes: Sequence[int],
) -> tuple[object, ...]:
    if isinstance(raw_row, tuple):
        row = raw_row
    elif isinstance(raw_row, list):
        row = raw_row
    elif isinstance(raw_row, Mapping):
        row = normalize_snapshot_row(raw_row, columns)
    else:
        row = normalize_snapshot_row(raw_row, columns)
    return tuple(row[index] for index in selected_indexes)


def _resolve_effective_compare_key(
    *,
    table_rule: TableRulesetTableRule | None,
    before_descriptor: SnapshotTableDescriptor | None,
    current_descriptor: SnapshotTableDescriptor | None,
    ignored_set: set[str],
    selected_columns: set[str],
) -> tuple[str, ...]:
    if table_rule is not None and not enters_comparison_for_static_role(table_rule.static_role):
        return ()
    if table_rule is not None and table_rule.compare_key_columns:
        candidate = tuple(canonical_identifier(column) for column in table_rule.compare_key_columns)
    else:
        before_key = tuple(before_descriptor.compare_key_columns) if before_descriptor is not None else ()
        current_key = tuple(current_descriptor.compare_key_columns) if current_descriptor is not None else ()
        candidate = before_key if before_key and before_key == current_key else before_key or current_key
    if not candidate:
        return ()
    if any(column in ignored_set for column in candidate):
        return ()
    if not set(candidate).issubset(selected_columns):
        return ()
    return tuple(candidate)


def _include_ordered_position_columns(
    *,
    selected_columns: Sequence[str],
    selected_source_columns: Sequence[str],
    table_rule: TableRulesetTableRule | None,
) -> tuple[str, ...]:
    result = list(selected_columns)
    if table_rule is None:
        return tuple(result)
    if str(table_rule.static_role).upper() not in {"ORDERED", "ORDERED_DIFF", "ORDERED_TABLE_COMPARE"}:
        return tuple(result)
    source_set = set(selected_source_columns)
    if "no" in source_set and "no" not in result:
        result.append("no")
    return tuple(result)


__all__ = [
    "ProjectionBuilder",
    "ProjectionRowsReader",
    "build_projection_schema",
    "project_rows",
]
