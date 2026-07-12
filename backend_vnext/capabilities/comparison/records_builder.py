from __future__ import annotations

from collections.abc import Sequence

from ...artifacts import (
    ArtifactRef,
    LocalArtifactStore,
    RecordsArtifact,
    RecordsArtifactManifest,
    records_parquet_content,
    store_records_artifact,
)
from ...core.diagnostics import DiagnosticRecord
from ...core.digests import DigestRef, canonical_json_bytes
from ...core.identifiers import canonical_identifier
from ..snapshot_materialization.models import SnapshotTableDescriptor
from .models import (
    ComparisonComputeInput,
    ComparisonRecord,
    ComparisonRecordKind,
    ComparisonRowDiffDetailPolicy,
    ProjectionTable,
)
from .projection import ProjectionRowsReader


def _build_row_diff_records(
    *,
    table_name: str,
    projection_schema: object,
    before_projection: ProjectionTable,
    current_projection: ProjectionTable,
    before_descriptor: SnapshotTableDescriptor | None,
    current_descriptor: SnapshotTableDescriptor | None,
    comparison_input: ComparisonComputeInput,
) -> list[ComparisonRecord]:
    before_index, before_duplicate = _index_projection_rows(before_projection)
    current_index, current_duplicate = _index_projection_rows(current_projection)
    if before_duplicate is not None or current_duplicate is not None:
        return []
    selected_columns = tuple(getattr(projection_schema, "selected_columns", ()))
    row_identity_columns = tuple(getattr(projection_schema, "effective_compare_key", ()))
    records: list[ComparisonRecord] = []
    before_keys = set(before_index)
    current_keys = set(current_index)
    for row_identity in sorted(before_keys | current_keys, key=canonical_json_bytes):
        before_row = before_index.get(row_identity)
        current_row = current_index.get(row_identity)
        if before_row is None and current_row is not None:
            records.append(
                _build_modified_or_side_record(
                    table_name=table_name,
                    record_kind=ComparisonRecordKind.ROW_ADDED,
                    row_identity=row_identity,
                    changed_columns=None,
                    before_row=None,
                    current_row=current_row,
                    selected_columns=selected_columns,
                    row_diff_detail_policy=comparison_input.comparison_options.row_diff_detail_policy,
                )
            )
            continue
        if current_row is None and before_row is not None:
            records.append(
                _build_modified_or_side_record(
                    table_name=table_name,
                    record_kind=ComparisonRecordKind.ROW_DELETED,
                    row_identity=row_identity,
                    changed_columns=None,
                    before_row=before_row,
                    current_row=None,
                    selected_columns=selected_columns,
                    row_diff_detail_policy=comparison_input.comparison_options.row_diff_detail_policy,
                )
            )
            continue
        if before_row != current_row and before_row is not None and current_row is not None:
            changed_columns = tuple(
                column_name
                for column_name, before_value, current_value in zip(selected_columns, before_row, current_row)
                if before_value != current_value
            )
            records.append(
                _build_modified_or_side_record(
                    table_name=table_name,
                    record_kind=ComparisonRecordKind.ROW_MODIFIED,
                    row_identity=row_identity,
                    changed_columns=changed_columns,
                    before_row=before_row,
                    current_row=current_row,
                    selected_columns=selected_columns,
                    row_diff_detail_policy=comparison_input.comparison_options.row_diff_detail_policy,
                )
            )
    return records


def _build_side_record(
    *,
    table_name: str,
    record_kind: ComparisonRecordKind,
    row_identity: tuple[object, ...],
    values: tuple[object, ...],
    row_diff_detail_policy: ComparisonRowDiffDetailPolicy | str,
    side: str,
) -> ComparisonRecord:
    detail_policy = ComparisonRowDiffDetailPolicy(row_diff_detail_policy)
    if detail_policy is ComparisonRowDiffDetailPolicy.FULL_BEFORE_AFTER_VALUES:
        return ComparisonRecord(
            table_name=table_name,
            record_kind=record_kind,
            row_identity=row_identity,
            before_values=values if side == "before" else None,
            current_values=values if side == "current" else None,
        )
    return ComparisonRecord(
        table_name=table_name,
        record_kind=record_kind,
        row_identity=row_identity,
    )


def _build_modified_or_side_record(
    *,
    table_name: str,
    record_kind: ComparisonRecordKind,
    row_identity: tuple[object, ...],
    changed_columns: tuple[str, ...] | None,
    before_row: tuple[object, ...] | None,
    current_row: tuple[object, ...] | None,
    selected_columns: Sequence[str],
    row_diff_detail_policy: ComparisonRowDiffDetailPolicy | str,
) -> ComparisonRecord:
    detail_policy = ComparisonRowDiffDetailPolicy(row_diff_detail_policy)
    if detail_policy is ComparisonRowDiffDetailPolicy.COUNTS_ONLY:
        return ComparisonRecord(
            table_name=table_name,
            record_kind=record_kind,
            row_identity=row_identity,
        )
    if detail_policy is ComparisonRowDiffDetailPolicy.CHANGED_COLUMNS:
        return ComparisonRecord(
            table_name=table_name,
            record_kind=record_kind,
            row_identity=row_identity,
            changed_columns=changed_columns,
        )
    return ComparisonRecord(
        table_name=table_name,
        record_kind=record_kind,
        row_identity=row_identity,
        changed_columns=changed_columns,
        before_values=before_row,
        current_values=current_row,
    )


def _iter_projection_rows(
    projection: ProjectionTable,
    compare_key_columns: Sequence[str],
) -> list[tuple[tuple[object, ...], tuple[object, ...]]]:
    rows_reader = projection.reader
    if not isinstance(rows_reader, ProjectionRowsReader):
        return []
    selected_columns = rows_reader.columns
    key_indexes = tuple(
        selected_columns.index(next(column for column in selected_columns if column.name == canonical_identifier(column_name)))
        for column_name in compare_key_columns
    )
    rows: list[tuple[tuple[object, ...], tuple[object, ...]]] = []
    for row in rows_reader.rows:
        row_identity = tuple(row[index] for index in key_indexes)
        rows.append((row_identity, row))
    return rows


def _index_projection_rows(
    projection: ProjectionTable,
) -> tuple[dict[tuple[object, ...], tuple[object, ...]], tuple[object, ...] | None]:
    rows_reader = projection.reader
    if not isinstance(rows_reader, ProjectionRowsReader):
        return {}, None
    compare_key = tuple(projection.projection_schema.effective_compare_key)
    if not compare_key:
        return {}, None
    selected_columns = rows_reader.columns
    column_index = {column.name: index for index, column in enumerate(selected_columns)}
    key_indexes = []
    for key_column in compare_key:
        try:
            key_indexes.append(column_index[canonical_identifier(key_column)])
        except KeyError:
            return {}, None
    rows_by_key: dict[tuple[object, ...], tuple[object, ...]] = {}
    duplicate_key: tuple[object, ...] | None = None
    for row in rows_reader.rows:
        row_identity = tuple(row[index] for index in key_indexes)
        if row_identity in rows_by_key:
            duplicate_key = row_identity
            break
        rows_by_key[row_identity] = row
    return rows_by_key, duplicate_key


def _build_records_artifact(
    *,
    table_name: str,
    records: Sequence[ComparisonRecord],
    projection_schema: object,
    comparison_input: ComparisonComputeInput,
    table_ruleset_version: str,
    diagnostics: tuple[DiagnosticRecord, ...],
    records_store: LocalArtifactStore | None,
) -> tuple[ArtifactRef, RecordsArtifact | None]:
    record_columns = tuple(getattr(projection_schema, "selected_columns", ()))
    content = records_parquet_content(records, columns=record_columns)
    manifest = RecordsArtifactManifest(
        table_name=table_name,
        record_count=content.record_count,
        row_diff_detail_policy=comparison_input.comparison_options.row_diff_detail_policy,
        content_digest=content.content_digest,
        content_size_bytes=len(content.content_bytes),
        metadata={
            "comparison_contract_version": comparison_input.comparison_contract_version,
            "projection_contract_version": comparison_input.projection_contract_version,
            "table_ruleset_version": table_ruleset_version,
            "scalar_encoding_version": comparison_input.scalar_encoding_version,
            "projection_schema_digest": getattr(projection_schema, "projection_schema_digest").to_payload(),
            "record_columns": list(record_columns),
            "comparison_options": comparison_input.comparison_options,
        },
        diagnostics=diagnostics,
    )
    artifact_manifest = manifest.to_artifact_manifest()
    manifest_digest = DigestRef.from_payload(artifact_manifest.to_payload())
    logical_ref = artifact_manifest.to_ref(manifest_digest)
    if records_store is None:
        return logical_ref, None
    stored = store_records_artifact(records_store, manifest, records)
    return stored.ref, stored


def _record_sort_key(record: ComparisonRecord) -> tuple[object, ...]:
    kind_priority = {
        ComparisonRecordKind.ROW_ADDED: 0,
        ComparisonRecordKind.ROW_DELETED: 1,
        ComparisonRecordKind.ROW_MODIFIED: 2,
        ComparisonRecordKind.SCHEMA_CHANGE: 3,
        ComparisonRecordKind.TABLE_DEGRADED: 4,
    }[record.record_kind]
    row_identity_key = canonical_json_bytes(record.row_identity or ())
    changed_columns_key = tuple(record.changed_columns or ())
    return kind_priority, row_identity_key, changed_columns_key, canonical_identifier(record.table_name)
