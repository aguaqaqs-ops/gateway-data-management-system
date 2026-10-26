"""Candidate-key census for projected keyless tables in the eight real dumps.

This read-only benchmark stores only table, column, rule, and count metadata in
its output. Source cell values stay in process memory and are reduced to
fingerprints before cross-dataset comparisons.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gateway_shared_kernel import DigestRef, NullScalar, raw_blob_digest

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.composite_signal.contracts import (
    empty_composite_logic_source,
    present_composite_logic_source,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BusinessSnapshotMaterializationRequest,
    SnapshotTable,
)
from gateway_backend.capabilities.snapshot_materialization.compose import materialize_business_snapshot
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParserInvocationContext,
    SqlParseRequest,
    SqlSourceInput,
    SourceCell,
)
from gateway_backend.capabilities.table_access.sql import parse_sql
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    SelectorPrecedenceClass,
    TableStaticRole,
    canonicalize_rule_identifier,
)
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.capabilities.table_rules.resolver import resolve_table_rule
from gateway_backend.capabilities.storage_projection import project_canonical_table_set
from gateway_backend.capabilities.storage_projection.contracts import (
    CanonicalizationManifestTable,
    ProjectionStatus,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import SnapshotTableDescriptor
from gateway_backend.capabilities.source_package_staging.contracts import (
    PackageKind,
    SourcePackageInput,
    StagingInvocationContext,
    StagingTransport,
)
from gateway_backend.capabilities.source_package_staging.staging import stage_source_package
from gateway_backend.capabilities.table_access.contracts import XmlParseRequest, XmlSourceInput
from gateway_backend.capabilities.table_access.xml import parse_xml

from benchmarks.real_dump_census import _sql_snapshot_request


_ZERO_DIGEST = DigestRef("sha256:" + "00" * 32)
_PACKAGE_IDS = (
    "rd-t1-a-v1",
    "rd-t1-a-v2",
    "rd-t2-b-v1",
    "rd-t2-b-v2",
    "rd-t3-c-v1",
    "rd-t3-c-v2",
    "rd-t4-d-v1",
    "rd-t4-d-v2",
)
_DC29_KNOWN_TABLES = frozenset(
    {
        "cnt_manage_cfg",
        "comm_user_data",
        "dev104_cfg",
        "forwardtable_yc1",
        "forwardtable_yc2",
        "forwardtable_yk1",
        "forwardtable_yt1",
        "forwardtable_yx1",
        "forwardtable_yx2",
        "forwardtbl_lst_cs",
        "forwardtbl_lst_dz",
        "forwardtbl_lst_qt",
        "forwardtbl_lst_yc",
        "forwardtbl_lst_yk",
        "forwardtbl_lst_ym",
        "forwardtbl_lst_yt",
        "forwardtbl_lst_yx",
        "iec101_cfg",
        "iec104_cfg",
        "iec104gw_cfg",
        "iec61850c_cfg",
        "jdxx_cfg",
        "mms_rp_cdc_index",
        "nbridge_cfg",
        "nr103d_cfg",
        "nr103ht_cfg",
        "out_time_cfg",
        "project",
        "sc_cfg",
        "scada_cfg",
        "sg_manage_cfg",
        "sntp_cfg",
        "vqc_cfg",
        "wave_cfg",
        "wf_cfg",
    }
)
_PACKAGE_PAIRS = (
    ("rd-t1-a-v1", "rd-t1-a-v2"),
    ("rd-t2-b-v1", "rd-t2-b-v2"),
    ("rd-t3-c-v1", "rd-t3-c-v2"),
    ("rd-t4-d-v1", "rd-t4-d-v2"),
)
_FLOAT_SQL_TYPES = frozenset({"FLOAT", "DOUBLE", "REAL"})


class CensusRefusal(RuntimeError):
    """A production staging, materialization, or projection path was incomplete."""


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    package_path: Path


@dataclass(frozen=True)
class TableMetadata:
    dataset_id: str
    table_name: str
    row_count: int
    columns: tuple[str, ...]
    float_columns: tuple[str, ...]
    rule_category: str
    canonical_key_columns: tuple[str, ...]

    @property
    def keyless(self) -> bool:
        return not self.canonical_key_columns


@dataclass(frozen=True)
class DatasetRows:
    row_hashes: tuple[bytes, ...]
    column_hashes: dict[str, tuple[bytes | None, ...]]

    @property
    def row_count(self) -> int:
        return len(self.row_hashes)

    @property
    def duplicate_extra_rows(self) -> int:
        return sum(count - 1 for count in Counter(self.row_hashes).values() if count > 1)


def _expected_specs(packages_dir: Path) -> tuple[DatasetSpec, ...]:
    specs = tuple(
        DatasetSpec(dataset_id, packages_dir / f"{dataset_id}.tar.gz")
        for dataset_id in _PACKAGE_IDS
    )
    missing = [str(spec.package_path.name) for spec in specs if not spec.package_path.is_file()]
    if missing:
        raise CensusRefusal(f"required dataset packages are missing: {', '.join(missing)}")
    return specs


def _failure_codes(items: Iterable[Any]) -> str:
    codes = sorted({str(item.code.value) for item in items})
    return ",".join(codes) if codes else "NO_DIAGNOSTIC_CODE"


def _parse_package(package_path: Path) -> tuple[bytes, bytes | None, InMemoryArtifactStore]:
    package_bytes = package_path.read_bytes()
    store = InMemoryArtifactStore()
    staged = stage_source_package(
        SourcePackageInput(
            package_kind=PackageKind.TAR_GZ,
            transport=StagingTransport.IDENTITY,
            context=StagingInvocationContext(NeverCancel()),
            payload=package_bytes,
        ),
        store,
    )
    if staged.status.value != "COMPLETE" or staged.required_sql_document_ref is None:
        raise CensusRefusal(
            f"{package_path.name}: source staging refused or incomplete "
            f"({_failure_codes(staged.diagnostics)})"
        )
    sql_bytes = store.locate(staged.required_sql_document_ref.artifact_ref)
    xml_bytes: bytes | None = None
    if staged.optional_xml_document_ref is not None:
        xml_bytes = store.locate(staged.optional_xml_document_ref.artifact_ref)
    return sql_bytes, xml_bytes, store


def _parse_xml(xml_bytes: bytes | None, dataset_id: str) -> Any:
    if xml_bytes is None:
        return None
    result = parse_xml(
        XmlParseRequest(
            source=XmlSourceInput(
                document_content_digest=_ZERO_DIGEST,
                xml_source_digest=raw_blob_digest(xml_bytes),
                parser_input_contract_version=1,
                encoding="utf-8",
                source_size_bytes=len(xml_bytes),
            ),
            xml_utf8=xml_bytes,
            context=ParserInvocationContext(NeverCancel()),
        )
    )
    if result.status.value != "COMPLETE":
        raise CensusRefusal(f"{dataset_id}: XML parsing incomplete ({_failure_codes(result.diagnostics)})")
    return result


def _rule_category(
    descriptor: SnapshotTableDescriptor,
    manifest_table: CanonicalizationManifestTable,
) -> str:
    ruleset = migrated_table_ruleset_snapshot()
    resolved = resolve_table_rule(
        ruleset,
        descriptor.table_name,
        primary_key_columns=descriptor.primary_key_columns,
    )
    if resolved.record.static_role is TableStaticRole.SNAPSHOT_ONLY:
        return "SNAPSHOT_ONLY"
    if resolved.record.static_role is TableStaticRole.BROWSE_ONLY:
        return "BROWSE_ONLY"
    if resolved.record.precedence_class is SelectorPrecedenceClass.STANDARD_RAW_PK_FALLBACK:
        return "RAW_PK_FALLBACK"
    if manifest_table.canonical_key_policy is CanonicalKeyPolicy.EXPLICIT_KEYLESS:
        return "EXPLICIT_KEYLESS"
    raise CensusRefusal(
        f"{descriptor.table_name}: empty canonical key is outside the requested rule categories"
    )


def _float_column_names(table: SnapshotTable) -> tuple[str, ...]:
    names: list[str] = []
    for column in table.descriptor.columns:
        sql_type = (column.scalar_type or "").strip().upper()
        base_type = re.sub(r"\([^)]*\)", "", sql_type).split()
        if base_type and base_type[0] in _FLOAT_SQL_TYPES:
            names.append(canonicalize_rule_identifier(column.name))
    return tuple(sorted(names))


def _materialize_project(
    spec: DatasetSpec,
) -> tuple[dict[str, TableMetadata], tuple[SnapshotTable, ...]]:
    sql_bytes, xml_bytes, store = _parse_package(spec.package_path)
    parse_context = ParserInvocationContext(NeverCancel())
    parse_result = parse_sql(
        SqlParseRequest(
            source=SqlSourceInput(
                document_content_digest=_ZERO_DIGEST,
                sql_source_digest=raw_blob_digest(sql_bytes),
                parser_input_contract_version=1,
                encoding="utf-8",
                source_size_bytes=len(sql_bytes),
            ),
            sql_utf8=sql_bytes,
            context=parse_context,
        )
    )
    if parse_result.status.value != "COMPLETE":
        raise CensusRefusal(
            f"{spec.dataset_id}: SQL parsing incomplete ({_failure_codes(parse_result.diagnostics)})"
        )

    ruleset = migrated_table_ruleset_snapshot()
    xml_result = _parse_xml(xml_bytes, spec.dataset_id)
    logic_source = (
        empty_composite_logic_source()
        if xml_bytes is None
        else present_composite_logic_source(xml_bytes)
    )
    sql_request = _sql_snapshot_request(
        {"parse_result": parse_result, "context": parse_context},
        sql_bytes=sql_bytes,
        ruleset=ruleset,
        artifact_store=store,
        diagnostic_mode=True,
    )
    business = materialize_business_snapshot(
        BusinessSnapshotMaterializationRequest(
            sql=sql_request,
            logic=logic_source,
            xml=xml_result,
        )
    )
    if (
        business.status.value != "COMPLETE"
        or business.snapshot is None
        or business.table_set is None
    ):
        if business.table_set is not None:
            _close_readers(business.table_set.tables)
        raise CensusRefusal(
            f"{spec.dataset_id}: business materialization incomplete "
            f"({_failure_codes(business.diagnostics)})"
        )

    raw_table_set = business.table_set
    projection = project_canonical_table_set(raw_table_set, ruleset)
    _close_readers(raw_table_set.tables)
    if projection.status is not ProjectionStatus.COMPLETE or projection.manifest is None:
        raise CensusRefusal(
            f"{spec.dataset_id}: canonical projection incomplete "
            f"({ _failure_codes(projection.diagnostics) })"
        )

    source_by_name = {table.descriptor.table_name: table.descriptor for table in raw_table_set.tables}
    projected_by_name = {table.descriptor.table_name: table for table in projection.tables}
    manifest_by_name = {table.name: table for table in projection.manifest.tables}
    if set(projected_by_name) != set(manifest_by_name):
        _close_readers(projection.tables)
        raise CensusRefusal(f"{spec.dataset_id}: projection table and manifest sets differ")

    metadata: dict[str, TableMetadata] = {}
    try:
        for table_name, manifest_table in manifest_by_name.items():
            projected_table = projected_by_name[table_name]
            source_descriptor = source_by_name.get(table_name)
            if source_descriptor is None:
                raise CensusRefusal(f"{spec.dataset_id}: projected table lacks source descriptor")
            if projected_table.reader is None:
                raise CensusRefusal(f"{spec.dataset_id}/{table_name}: projected reader unavailable")
            columns = tuple(
                canonicalize_rule_identifier(column.name)
                for column in projected_table.descriptor.columns
            )
            if len(columns) != len(set(columns)):
                raise CensusRefusal(f"{spec.dataset_id}/{table_name}: projected columns are not unique")
            metadata[table_name] = TableMetadata(
                dataset_id=spec.dataset_id,
                table_name=table_name,
                row_count=manifest_table.canonical_row_count,
                columns=columns,
                float_columns=_float_column_names(projected_table),
                rule_category=(
                    _rule_category(source_descriptor, manifest_table)
                    if not manifest_table.canonical_key_columns
                    else _category_for_keyed_table(source_descriptor)
                ),
                canonical_key_columns=manifest_table.canonical_key_columns,
            )
    except Exception:
        _close_readers(projection.tables)
        raise
    return metadata, projection.tables


def _category_for_keyed_table(descriptor: SnapshotTableDescriptor) -> str:
    ruleset = migrated_table_ruleset_snapshot()
    resolved = resolve_table_rule(
        ruleset,
        descriptor.table_name,
        primary_key_columns=descriptor.primary_key_columns,
    )
    if resolved.record.static_role is TableStaticRole.SNAPSHOT_ONLY:
        return "SNAPSHOT_ONLY"
    if resolved.record.static_role is TableStaticRole.BROWSE_ONLY:
        return "BROWSE_ONLY"
    if resolved.record.precedence_class is SelectorPrecedenceClass.STANDARD_RAW_PK_FALLBACK:
        return "RAW_PK_FALLBACK"
    if resolved.record.canonical_key_policy is CanonicalKeyPolicy.EXPLICIT_KEYLESS:
        return "EXPLICIT_KEYLESS"
    return resolved.record.precedence_class.value


def _close_readers(tables: Sequence[SnapshotTable]) -> None:
    for table in tables:
        if table.reader is not None:
            try:
                table.reader.close()
            except Exception:
                continue


def _cell_fingerprint(cell: SourceCell) -> bytes | None:
    if isinstance(cell, NullScalar):
        return None
    return hashlib.sha256(repr(cell).encode("utf-8")).digest()


def _row_fingerprint(
    schema: tuple[tuple[str, str | None], ...], row: tuple[SourceCell, ...]
) -> bytes:
    return hashlib.sha256(repr((schema, row)).encode("utf-8")).digest()


def _scan_dataset_rows(
    spec: DatasetSpec,
    target_metadata: dict[str, TableMetadata],
    common_columns: dict[str, tuple[str, ...]],
) -> dict[str, DatasetRows]:
    metadata, projected_tables = _materialize_project(spec)
    try:
        projected_by_name = {table.descriptor.table_name: table for table in projected_tables}
        scanned: dict[str, DatasetRows] = {}
        for table_name, expected in target_metadata.items():
            current = metadata.get(table_name)
            if current is None:
                continue
            if current != expected:
                raise CensusRefusal(
                    f"{spec.dataset_id}/{table_name}: metadata changed between census passes"
                )
            table = projected_by_name.get(table_name)
            if table is None or table.reader is None:
                raise CensusRefusal(f"{spec.dataset_id}/{table_name}: projected reader unavailable")
            columns = tuple(canonicalize_rule_identifier(col.name) for col in table.descriptor.columns)
            schema = tuple(
                (canonicalize_rule_identifier(column.name), column.scalar_type)
                for column in table.descriptor.columns
            )
            indexes = {column: index for index, column in enumerate(columns)}
            wanted = common_columns[table_name]
            try:
                wanted_indexes = {column: indexes[column] for column in wanted}
            except KeyError as exc:
                raise CensusRefusal(
                    f"{spec.dataset_id}/{table_name}: common projected column is missing"
                ) from exc
            column_hash_lists: dict[str, list[bytes | None]] = {column: [] for column in wanted}
            row_hashes: list[bytes] = []
            for row in table.reader.iter_rows():
                if len(row) != len(columns):
                    raise CensusRefusal(f"{spec.dataset_id}/{table_name}: projected row width mismatch")
                row_hashes.append(_row_fingerprint(schema, row))
                for column, index in wanted_indexes.items():
                    column_hash_lists[column].append(_cell_fingerprint(row[index]))
            if len(row_hashes) != expected.row_count:
                raise CensusRefusal(
                    f"{spec.dataset_id}/{table_name}: projected row count differs from manifest"
                )
            scanned[table_name] = DatasetRows(
                row_hashes=tuple(row_hashes),
                column_hashes={
                    column: tuple(values) for column, values in column_hash_lists.items()
                },
            )
        return scanned
    finally:
        _close_readers(projected_tables)


def _candidate_status(combo: tuple[str, ...], rows: DatasetRows | None) -> str:
    if rows is None or rows.row_count == 0:
        return "NO_ROWS"
    columns = tuple(rows.column_hashes[column] for column in combo)
    seen: set[tuple[bytes, ...]] = set()
    for values in zip(*columns, strict=True):
        if any(value is None for value in values):
            return "NULL"
        key = tuple(value for value in values if value is not None)
        if key in seen:
            return "DUPLICATE"
        seen.add(key)
    return "UNIQUE"


def _key_fingerprints(combo: tuple[str, ...], rows: DatasetRows | None) -> tuple[bytes, ...]:
    if rows is None:
        return ()
    columns = tuple(rows.column_hashes[column] for column in combo)
    output: list[bytes] = []
    for values in zip(*columns, strict=True):
        if any(value is None for value in values):
            raise CensusRefusal("candidate key unexpectedly contains NULL")
        key_bytes = b"".join(value for value in values if value is not None)
        output.append(hashlib.sha256(key_bytes).digest())
    return tuple(output)


def _keyed_row_map(combo: tuple[str, ...], rows: DatasetRows | None) -> tuple[dict[bytes, bytes], int, int]:
    if rows is None:
        return {}, 0, 0
    key_hashes = _key_fingerprints(combo, rows)
    grouped: dict[bytes, list[bytes]] = {}
    for key_hash, row_hash in zip(key_hashes, rows.row_hashes, strict=True):
        grouped.setdefault(key_hash, []).append(row_hash)
    duplicate_extra_rows = sum(len(values) - 1 for values in grouped.values() if len(values) > 1)
    conflicting_groups = sum(
        1 for values in grouped.values() if len(values) > 1 and len(set(values)) > 1
    )
    return {key: values[0] for key, values in grouped.items()}, duplicate_extra_rows, conflicting_groups


def _counter(rows: DatasetRows | None) -> Counter[bytes]:
    return Counter() if rows is None else Counter(rows.row_hashes)


def _row_multiset_changes(before: DatasetRows | None, after: DatasetRows | None) -> tuple[int, int]:
    before_counts = _counter(before)
    after_counts = _counter(after)
    return sum((after_counts - before_counts).values()), sum((before_counts - after_counts).values())


def _key_changes(
    combo: tuple[str, ...], before: DatasetRows | None, after: DatasetRows | None
) -> dict[str, int]:
    before_map, before_dupes, before_conflicts = _keyed_row_map(combo, before)
    after_map, after_dupes, after_conflicts = _keyed_row_map(combo, after)
    shared = before_map.keys() & after_map.keys()
    return {
        "insert": len(after_map.keys() - before_map.keys()),
        "delete": len(before_map.keys() - after_map.keys()),
        "update": sum(before_map[key] != after_map[key] for key in shared),
        "v1_duplicate_extra_rows": before_dupes,
        "v1_conflicting_key_groups": before_conflicts,
        "v2_duplicate_extra_rows": after_dupes,
        "v2_conflicting_key_groups": after_conflicts,
    }


def _discover_candidates(
    table_name: str,
    all_metadata: dict[str, dict[str, TableMetadata]],
    row_data: dict[str, dict[str, DatasetRows]],
    dataset_ids: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[str, ...]]:
    appearances = [all_metadata[dataset_id][table_name] for dataset_id in dataset_ids if table_name in all_metadata[dataset_id]]
    common = set(appearances[0].columns)
    for metadata in appearances[1:]:
        common.intersection_update(metadata.columns)
    common_columns = tuple(sorted(common))
    local_minimal: dict[str, set[tuple[str, ...]]] = {dataset_id: set() for dataset_id in dataset_ids}
    global_minimal: list[tuple[str, ...]] = []
    partial: dict[tuple[str, ...], dict[str, str]] = {}
    null_columns: dict[str, set[str]] = {}
    for dataset_id in dataset_ids:
        rows = row_data[dataset_id].get(table_name)
        null_columns[dataset_id] = (
            set()
            if rows is None
            else {
                column
                for column, values in rows.column_hashes.items()
                if any(value is None for value in values)
            }
        )
    total_rows = sum(item.row_count for item in appearances)

    for size in range(1, min(3, len(common_columns)) + 1):
        for combo in itertools.combinations(common_columns, size):
            if any(set(candidate).issubset(combo) for candidate in global_minimal):
                continue
            statuses: dict[str, str] = {}
            for dataset_id in dataset_ids:
                if table_name not in all_metadata[dataset_id]:
                    continue
                rows = row_data[dataset_id].get(table_name)
                if rows is None or rows.row_count == 0:
                    status = "NO_ROWS"
                elif set(combo) & null_columns[dataset_id]:
                    status = "NULL"
                elif any(set(previous).issubset(combo) for previous in local_minimal[dataset_id]):
                    status = "UNIQUE"
                else:
                    status = _candidate_status(combo, rows)
                statuses[dataset_id] = status
            globally_unique = total_rows > 0 and all(
                status in {"UNIQUE", "NO_ROWS"} for status in statuses.values()
            )
            locally_minimal_in: list[str] = []
            for dataset_id, status in statuses.items():
                if status != "UNIQUE":
                    continue
                if not any(set(previous).issubset(combo) for previous in local_minimal[dataset_id]):
                    locally_minimal_in.append(dataset_id)
                    local_minimal[dataset_id].add(combo)
            if globally_unique:
                global_minimal.append(combo)
            elif locally_minimal_in:
                partial[combo] = statuses

    float_names = {
        column
        for metadata in appearances
        for column in metadata.float_columns
        if column in common_columns
    }
    candidate_items: list[dict[str, Any]] = []
    for combo in global_minimal:
        included_floats = sorted(set(combo) & float_names)
        candidate_items.append(
            {
                "columns": list(combo),
                "includes_float": bool(included_floats),
                "float_columns": included_floats,
            }
        )

    partial_items: list[dict[str, Any]] = []
    for combo, statuses in sorted(partial.items(), key=lambda item: (len(item[0]), item[0])):
        included_floats = sorted(set(combo) & float_names)
        partial_items.append(
            {
                "columns": list(combo),
                "includes_float": bool(included_floats),
                "float_columns": included_floats,
                "unique_in_datasets": sorted(
                    dataset_id for dataset_id, status in statuses.items() if status == "UNIQUE"
                ),
                "status_by_dataset": statuses,
            }
        )
    return candidate_items, partial_items, common_columns


def _serialize_table(
    table_name: str,
    all_metadata: dict[str, dict[str, TableMetadata]],
    row_data: dict[str, dict[str, DatasetRows]],
    dataset_ids: tuple[str, ...],
) -> dict[str, Any]:
    appearance_metadata = [
        all_metadata[dataset_id][table_name]
        for dataset_id in dataset_ids
        if table_name in all_metadata[dataset_id]
    ]
    is_new = table_name not in _DC29_KNOWN_TABLES
    candidates, partial_candidates, common_columns = _discover_candidates(
        table_name, all_metadata, row_data, dataset_ids
    )
    appearances = []
    for metadata in appearance_metadata:
        rows = row_data[metadata.dataset_id].get(table_name)
        duplicates = 0 if rows is None else rows.duplicate_extra_rows
        appearances.append(
            {
                "dataset_id": metadata.dataset_id,
                "row_count": metadata.row_count,
                "column_count": len(metadata.columns),
                "columns": list(metadata.columns),
                "rule_category": metadata.rule_category,
                "canonical_key_columns": list(metadata.canonical_key_columns),
                "keyless": metadata.keyless,
                "exact_duplicate_extra_rows": duplicates,
            }
        )

    version_changes: list[dict[str, Any]] = []
    for v1_id, v2_id in _PACKAGE_PAIRS:
        before = row_data[v1_id].get(table_name)
        after = row_data[v2_id].get(table_name)
        added, removed = _row_multiset_changes(before, after)
        key_changes = []
        for candidate in candidates:
            combo = tuple(candidate["columns"])
            changes = _key_changes(combo, before, after)
            key_changes.append({"columns": list(combo), **changes})
        version_changes.append(
            {
                "v1_dataset_id": v1_id,
                "v2_dataset_id": v2_id,
                "row_multiset_insert": added,
                "row_multiset_delete": removed,
                "candidate_key_changes": key_changes,
            }
        )

    return {
        "table_name": table_name,
        "dc29_status": "NEW_TABLE" if is_new else "DC29_KNOWN_TABLE",
        "datasets": appearances,
        "common_candidate_columns": list(common_columns),
        "candidate_keys": candidates,
        "partial_candidate_keys": partial_candidates,
        "version_changes": version_changes,
    }


def _build_report(specs: tuple[DatasetSpec, ...]) -> dict[str, Any]:
    dataset_ids = tuple(spec.dataset_id for spec in specs)
    all_metadata: dict[str, dict[str, TableMetadata]] = {}
    keyless_names: set[str] = set()
    for spec in specs:
        print(f"metadata {spec.dataset_id}", flush=True)
        metadata, projected_tables = _materialize_project(spec)
        try:
            all_metadata[spec.dataset_id] = metadata
            keyless_names.update(table_name for table_name, item in metadata.items() if item.keyless)
        finally:
            _close_readers(projected_tables)

    target_metadata = {
        table_name: {
            dataset_id: all_metadata[dataset_id][table_name]
            for dataset_id in dataset_ids
            if table_name in all_metadata[dataset_id]
        }
        for table_name in keyless_names
    }
    common_columns: dict[str, tuple[str, ...]] = {}
    for table_name, metadata_by_dataset in target_metadata.items():
        columns = set(next(iter(metadata_by_dataset.values())).columns)
        for item in metadata_by_dataset.values():
            columns.intersection_update(item.columns)
        common_columns[table_name] = tuple(sorted(columns))

    row_data: dict[str, dict[str, DatasetRows]] = {dataset_id: {} for dataset_id in dataset_ids}
    for spec in specs:
        print(f"fingerprints {spec.dataset_id}", flush=True)
        per_dataset_targets = {
            table_name: metadata_by_dataset[spec.dataset_id]
            for table_name, metadata_by_dataset in target_metadata.items()
            if spec.dataset_id in metadata_by_dataset
        }
        scanned_rows = _scan_dataset_rows(spec, per_dataset_targets, common_columns)
        row_data[spec.dataset_id].update(scanned_rows)

    tables = [
        _serialize_table(table_name, all_metadata, row_data, dataset_ids)
        for table_name in sorted(keyless_names)
    ]
    single = [item["table_name"] for item in tables if len(item["candidate_keys"]) == 1]
    multiple = [item["table_name"] for item in tables if len(item["candidate_keys"]) > 1]
    none = [item["table_name"] for item in tables if not item["candidate_keys"]]
    with_duplicates = [
        item["table_name"]
        for item in tables
        if any(dataset["exact_duplicate_extra_rows"] for dataset in item["datasets"])
    ]
    new_names = [item["table_name"] for item in tables if item["dc29_status"] == "NEW_TABLE"]
    return {
        "schema": "gateway-vnext.real-dump-keyless-candidate-census/v1",
        "datasets": list(dataset_ids),
        "tables": tables,
        "summary": {
            "table_count": len(tables),
            "exactly_one_candidate_key": {"count": len(single), "tables": single},
            "multiple_candidate_keys": {"count": len(multiple), "tables": multiple},
            "no_candidate_key": {"count": len(none), "tables": none},
            "tables_with_exact_duplicate_rows": {
                "count": len(with_duplicates),
                "tables": with_duplicates,
            },
            "new_table_names_vs_dc29": {"count": len(new_names), "tables": new_names},
        },
    }


def _write_private(path: Path, content: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 真实数据 keyless 表候选键普查",
        "",
        "## 方法",
        "",
        "- 输入为调试节点上的 t1–t4 v1、v2 共 8 个 SourcePackage；不写回数据包。",
        "- 每份数据通过现有 staging、SQL/XML 解析、READERS_REQUIRED 业务物化与 `project_canonical_table_set`；仅以规范投影 manifest 中 `canonical_key_columns` 为空的表作为纳入条件。",
        "- 行数、列数与候选键均取自规范投影后的表。被规则丢弃的列已不参与候选键。规则类别取当前规则解析结果。",
        "- 候选键为所有出现数据集中共同存在的列中，均无 NULL 且唯一的最小列组合，最多 3 列。空表不提供唯一性证据；至少一个数据集有行才报告候选键。浮点列参与项单独标记。",
        "- 完全相同行按规范投影后的列名、类型和值指纹计数，报告每组保留一行后多出的行数。新增/删除按整行多重集合差计数；候选键变化按唯一键的插入、删除和整行变化计数。",
        "- 工具做两遍同一物化与投影：第一遍收集每数据集的投影 schema 与规则，第二遍只对纳入表统计指纹。业务单元格值只在进程内处理，不写入 JSON、日志或报告。",
        "- 表名不在 DC29 §12 已知 35 表清单时标记为“本次新表”。结果不包含任何业务单元格值；无候选键结论不代表建议新增规则。",
        "",
        "## 汇总",
        "",
        f"共纳入 **{report['summary']['table_count']}** 个表名（在至少一个数据集中 canonical key 为空）。",
        "",
        "| 分组 | 表数 | 表名 |",
        "| --- | ---: | --- |",
    ]
    summary = report["summary"]
    for label, key in (
        ("恰有一个全局最小候选键", "exactly_one_candidate_key"),
        ("有多个全局最小候选键", "multiple_candidate_keys"),
        ("无全局候选键", "no_candidate_key"),
        ("至少一份数据有完全重复行", "tables_with_exact_duplicate_rows"),
        ("DC29 清单之外的新表", "new_table_names_vs_dc29"),
    ):
        entry = summary[key]
        names = "、".join(entry["tables"]) if entry["tables"] else "—"
        lines.append(f"| {label} | {entry['count']} | {names} |")

    lines.extend(["", "## 逐表统计", ""])
    for item in report["tables"]:
        table_name = item["table_name"]
        novelty = "（本次新表）" if item["dc29_status"] == "NEW_TABLE" else ""
        lines.extend([f"### `{table_name}`{novelty}", ""])
        lines.extend(
            [
                "| 数据集 | 行数 | 列数 | 命中规则类别 | 规范键列 | 完全相同重复多余行数 |",
                "| --- | ---: | ---: | --- | --- | ---: |",
            ]
        )
        for dataset in item["datasets"]:
            key_columns = ", ".join(dataset["canonical_key_columns"]) or "keyless"
            lines.append(
                f"| {dataset['dataset_id']} | {dataset['row_count']} | {dataset['column_count']} | "
                f"{dataset['rule_category']} | {key_columns} | {dataset['exact_duplicate_extra_rows']} |"
            )
        lines.extend(["", "**各数据集规范投影列**："])
        for dataset in item["datasets"]:
            column_names = "、".join(dataset["columns"]) or "无列"
            lines.append(f"- {dataset['dataset_id']}：{column_names}")
        if item["candidate_keys"]:
            lines.append("**全局最小候选键**：")
            for candidate in item["candidate_keys"]:
                label = "（含浮点列：" + "、".join(candidate["float_columns"]) + "）" if candidate["includes_float"] else ""
                lines.append(f"- `({', '.join(candidate['columns'])})`{label}")
        else:
            lines.append("**全局最小候选键**：无（最多 3 列的组合中，没有在全部出现数据集均非空且唯一的组合）。")
        if item["partial_candidate_keys"]:
            lines.extend(["", "**仅在部分数据集唯一的最小组合（需业务判断）**："])
            for candidate in item["partial_candidate_keys"]:
                unique = "、".join(candidate["unique_in_datasets"])
                statuses = "；".join(
                    f"{dataset_id}={status}"
                    for dataset_id, status in candidate["status_by_dataset"].items()
                )
                label = "，含浮点列 " + "、".join(candidate["float_columns"]) if candidate["includes_float"] else ""
                lines.append(f"- `({', '.join(candidate['columns'])})`：唯一于 {unique}；{statuses}{label}")
        lines.extend(
            [
                "",
                "| v1→v2 | 整行新增 | 整行删除 | 候选键列 | INSERT | DELETE | UPDATE | v1 键重复多余行/冲突组 | v2 键重复多余行/冲突组 |",
                "| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for change in item["version_changes"]:
            if change["candidate_key_changes"]:
                for key_change in change["candidate_key_changes"]:
                    lines.append(
                        f"| {change['v1_dataset_id']}→{change['v2_dataset_id']} | "
                        f"{change['row_multiset_insert']} | {change['row_multiset_delete']} | "
                        f"({', '.join(key_change['columns'])}) | {key_change['insert']} | "
                        f"{key_change['delete']} | {key_change['update']} | "
                        f"{key_change['v1_duplicate_extra_rows']}/{key_change['v1_conflicting_key_groups']} | "
                        f"{key_change['v2_duplicate_extra_rows']}/{key_change['v2_conflicting_key_groups']} |"
                    )
            else:
                lines.append(
                    f"| {change['v1_dataset_id']}→{change['v2_dataset_id']} | "
                    f"{change['row_multiset_insert']} | {change['row_multiset_delete']} | — | — | — | — | — | — |"
                )
        lines.append("")

    lines.extend(["## 需要业务判断的观察", ""])
    partial_count = sum(len(item["partial_candidate_keys"]) for item in report["tables"])
    lines.append(f"- 共记录 {partial_count} 个仅在部分数据集唯一的最小列组合；具体唯一/重复/NULL 状态见逐表表格。")
    new_names = summary["new_table_names_vs_dc29"]["tables"]
    lines.append(
        "- DC29 已知清单以外的表名：" + ("、".join(new_names) if new_names else "无。")
    )
    float_keys = [
        f"{item['table_name']}({', '.join(candidate['columns'])})"
        for item in report["tables"]
        for candidate in item["candidate_keys"]
        if candidate["includes_float"]
    ]
    lines.append(
        "- 含浮点列的全局候选键：" + ("；".join(float_keys) if float_keys else "无。")
    )
    lines.extend(["", "本报告仅提供测量事实，不判断哪些表应补为显式键规则。", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Census candidate keys in projected keyless real-dump tables.")
    parser.add_argument("--packages-dir", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        specs = _expected_specs(args.packages_dir)
        report = _build_report(specs)
        _write_private(args.json_output, json.dumps(report, indent=2, sort_keys=True) + "\n")
        _write_private(args.markdown_output, _render_markdown(report))
    except CensusRefusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "dataset_count": len(specs),
                "keyless_table_count": report["summary"]["table_count"],
                "json_output_mode": "0600",
                "markdown_output_mode": "0600",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
