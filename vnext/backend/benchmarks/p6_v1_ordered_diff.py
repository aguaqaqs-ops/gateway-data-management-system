"""Prepare, verify, and measure the Phase 6 V1 ordered-comparison prototype.

The module is benchmark/test tooling only. Arrow IPC inputs, expected comparison
normal forms, and logs are sensitive scratch data and must stay outside Git in a
0700 directory; files are written with mode 0600. Printed summaries omit cell
values and row identities.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import struct
import sys
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.ipc as pa_ipc
from gateway_shared_kernel import (
    BooleanScalar,
    DecimalScalar,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    UnsignedIntegerScalar,
    raw_blob_digest,
)
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts.store import InMemoryArtifactStore, put_with_built_ref
from gateway_backend.application import preview_jobs
from gateway_backend.capabilities.comparison import (
    ArtifactScope,
    BoundSnapshotInput,
    ComparisonRequest,
    ComparisonSchemaChanges,
    ComparisonTableFact,
    ComparisonPlan,
    plan_comparison,
)
from gateway_backend.capabilities.comparison import ordered as ordered_reference
from gateway_backend.capabilities.comparison import row_encoding as comparison_encoding
from gateway_backend.capabilities.comparison.contracts import (
    BlankRowPolicy,
    OrderedTablePolicy,
    TableComparisonTask,
    _ComparisonTablePolicy,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BlankRowProvenance,
    MaterializationStage,
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    SnapshotColumnDescriptor,
    SnapshotTable,
    SnapshotTableDescriptor,
    SnapshotTableOrderedMetadata,
)
from gateway_backend.domain.workspace.models import SourceArtifactBinding
from gateway_backend.operations.contracts import OperationDiagnosticSide
from gateway_backend.capabilities.table_rules import (
    comparison_rule_set,
    migrated_table_ruleset_snapshot,
)

OCF_MAGIC = b"GDMSOCF1"
OCF_FORMAT = "gateway.comparison.ordered-canonical"
OCF_VERSION = 1


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _write_private(path: Path, data: bytes) -> None:
    _private_dir(path.parent)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
    path.chmod(0o600)


def _write_json(path: Path, value: object) -> None:
    _write_private(path, canonicalize_json_value(value))


def _ocf(value: object) -> bytes:
    payload = canonicalize_json_value(value)
    if len(payload) > 0xFFFF_FFFF:
        raise ValueError("ordered canonical form exceeds u32 length")
    return OCF_MAGIC + struct.pack(">I", len(payload)) + payload


def _read_ocf(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw[:8] != OCF_MAGIC or len(raw) < 12:
        raise ValueError(f"{path.name}: not an ordered canonical form")
    (length,) = struct.unpack_from(">I", raw, 8)
    if len(raw) != 12 + length:
        raise ValueError(f"{path.name}: invalid ordered canonical form length")
    value = json.loads(raw[12:])
    if type(value) is not dict or value.get("format") != OCF_FORMAT or value.get("version") != OCF_VERSION:
        raise ValueError(f"{path.name}: unsupported ordered canonical form")
    return value


def _digest_value(value: object | None) -> str | None:
    return None if value is None else str(getattr(value, "value", value))


def _schema_changes(value: ComparisonSchemaChanges) -> dict[str, object]:
    return {
        "before_only_columns": list(value.before_only_columns),
        "current_only_columns": list(value.current_only_columns),
        "selected_columns": list(value.selected_columns),
        "effective_compare_key_before": list(value.effective_compare_key_before),
        "effective_compare_key_current": list(value.effective_compare_key_current),
        "effective_compare_key_changed": value.effective_compare_key_changed,
        "incompatible_columns": list(value.incompatible_columns),
        "change_source": None if value.change_source is None else value.change_source.value,
    }


def _scalar_value(column: SnapshotColumnDescriptor, value: object) -> dict[str, object]:
    frame = comparison_encoding._encode_cell(column, value)
    return {
        "column": column.name,
        "type_marker": frame[0],
        "frame_hex": frame.hex(),
    }


def _value_pairs(
    values: tuple[tuple[str, object], ...],
    descriptors: dict[str, SnapshotColumnDescriptor],
) -> list[dict[str, object]]:
    return [_scalar_value(descriptors[name], value) for name, value in values]


def _normal_form(
    fact: ComparisonTableFact,
    task: TableComparisonTask,
    *,
    format_name: str = OCF_FORMAT,
) -> dict[str, object]:
    before_columns = (
        {} if task.before_descriptor is None else {column.name: column for column in task.before_descriptor.columns}
    )
    current_columns = (
        {} if task.current_descriptor is None else {column.name: column for column in task.current_descriptor.columns}
    )
    records = []
    for record in fact.records:
        field_changes = [
            {
                "table_name": item.table_name,
                "row_identity": item.row_identity.value,
                "column": item.column_name,
                "before": _scalar_value(before_columns[item.column_name], item.before_value),
                "current": _scalar_value(current_columns[item.column_name], item.current_value),
                "change_kind": item.change_kind,
            }
            for item in record.field_changes
        ]
        records.append(
            {
                "table_name": record.table_name,
                "record_kind": record.record_kind.value,
                "row_identity": None if record.row_identity is None else record.row_identity.value,
                "changed_columns": list(record.changed_columns),
                "before_values": _value_pairs(record.before_values, before_columns),
                "current_values": _value_pairs(record.current_values, current_columns),
                "field_changes": field_changes,
                "diagnostics": list(record.diagnostics),
            }
        )

    ordered_extension = fact.ordered_extension
    blank_extension = fact.blank_extension
    if ordered_extension is None or blank_extension is None:
        raise ValueError(f"{task.table_name}: ordered task did not produce both extensions")
    ordered_records = [
        {
            "table_name": record.table_name,
            "record_kind": record.record_kind.value,
            "semantic_kind": record.semantic_kind.value,
            "entity_key_kind": record.entity_key_kind.value,
            "row_identity": None if record.row_identity is None else record.row_identity.value,
            "before_position": record.before_position,
            "current_position": record.current_position,
            "changed_columns": list(record.changed_columns),
            "before_values": _value_pairs(record.before_values, before_columns),
            "current_values": _value_pairs(record.current_values, current_columns),
            "diagnostics": list(record.diagnostics),
        }
        for record in ordered_extension.records
    ]
    blank_records = [
        {
            "table_name": record.table_name,
            "record_kind": record.record_kind.value,
            "semantic_kind": record.semantic_kind.value,
            "entity_key_kind": record.entity_key_kind.value,
            "interval": {
                "before_start": record.interval.before_start,
                "before_end": record.interval.before_end,
                "current_start": record.interval.current_start,
                "current_end": record.interval.current_end,
                "row_count": record.interval.row_count,
                "interval_digest": _digest_value(record.interval.interval_digest),
            },
            "before_occupancy": record.before_occupancy,
            "current_occupancy": record.current_occupancy,
            "diagnostics": list(record.diagnostics),
        }
        for record in blank_extension.records
    ]
    return {
        "format": format_name,
        "version": OCF_VERSION,
        "table_name": fact.table_name,
        "status": fact.status.value,
        "row_count_before": fact.row_count_before,
        "row_count_current": fact.row_count_current,
        "row_added_count": fact.row_added_count,
        "row_deleted_count": fact.row_deleted_count,
        "row_modified_count": fact.row_modified_count,
        "suppressed_added_count": fact.suppressed_added_count,
        "suppressed_deleted_count": fact.suppressed_deleted_count,
        "content_changed": fact.content_changed,
        "schema_changes": _schema_changes(fact.schema_changes),
        "diagnostics": list(fact.diagnostics),
        "records": records,
        "ordered_extension": {
            "contract_version": ordered_extension.contract_version,
            "status": ordered_extension.status.value,
            "summary": {
                "row_added_count": ordered_extension.ordered_summary.row_added_count,
                "row_deleted_count": ordered_extension.ordered_summary.row_deleted_count,
                "row_modified_count": ordered_extension.ordered_summary.row_modified_count,
                "row_moved_count": ordered_extension.ordered_summary.row_moved_count,
                "position_changed_count": ordered_extension.ordered_summary.position_changed_count,
                "degraded_count": ordered_extension.ordered_summary.degraded_count,
            },
            "before_ordered_digest": _digest_value(ordered_extension.before_ordered_digest),
            "current_ordered_digest": _digest_value(ordered_extension.current_ordered_digest),
            "replay_guarantee": ordered_extension.replay_guarantee.value,
            "table_processing_mode": (
                None
                if ordered_extension.table_processing_mode is None
                else ordered_extension.table_processing_mode.value
            ),
            "policy_digest": _digest_value(ordered_extension.policy_digest),
            "diagnostics": list(ordered_extension.diagnostics),
            "records": ordered_records,
        },
        "blank_extension": {
            "contract_version": blank_extension.contract_version,
            "status": blank_extension.status.value,
            "summary": {
                "interval_inserted_count": blank_extension.blank_summary.interval_inserted_count,
                "interval_deleted_count": blank_extension.blank_summary.interval_deleted_count,
                "blank_changed_count": blank_extension.blank_summary.blank_changed_count,
                "degraded_count": blank_extension.blank_summary.degraded_count,
            },
            "before_occupancy_digest": _digest_value(blank_extension.before_occupancy_digest),
            "current_occupancy_digest": _digest_value(blank_extension.current_occupancy_digest),
            "replay_guarantee": blank_extension.replay_guarantee.value,
            "diagnostics": list(blank_extension.diagnostics),
            "records": blank_records,
        },
    }


def _field_scalar_type(field: pa.Field, descriptor: SnapshotColumnDescriptor) -> pa.Field:
    metadata = dict(field.metadata or {})
    if descriptor.scalar_type is not None:
        metadata[b"gdms.scalar_type"] = descriptor.scalar_type.encode("utf-8")
    return field.with_metadata(metadata)


def _arrow_type(column: SnapshotColumnDescriptor) -> pa.DataType:
    spelling = (column.scalar_type or "").strip().lower()
    if spelling.startswith(("tinyint", "smallint", "mediumint", "int", "integer", "bigint")):
        return pa.uint64() if "unsigned" in spelling or "zerofill" in spelling else pa.int64()
    if spelling.startswith(("decimal", "numeric")):
        arguments = spelling.partition("(")[2].partition(")")[0].split(",")
        precision = int(arguments[0]) if arguments and arguments[0].strip() else 10
        scale = int(arguments[1]) if len(arguments) > 1 and arguments[1].strip() else 0
        return pa.decimal128(precision, scale)
    if spelling.startswith(("bool", "boolean")):
        return pa.bool_()
    if spelling.startswith("float"):
        return pa.float32()
    if spelling.startswith(("double", "real")):
        return pa.float64()
    if spelling.startswith(("binary", "varbinary", "tinyblob", "blob", "mediumblob", "longblob", "bit")):
        return pa.binary()
    if spelling.startswith("set("):
        return pa.list_(pa.string())
    return pa.string()


def _python_cell(cell: object) -> object:
    if isinstance(cell, NullScalar):
        return None
    if isinstance(cell, (SignedIntegerScalar, UnsignedIntegerScalar)):
        return int(cell.decimal)
    if isinstance(cell, DecimalScalar):
        from decimal import Decimal

        return Decimal(cell.decimal)
    if isinstance(cell, BooleanScalar):
        return cell.value
    if isinstance(cell, StringScalar):
        return cell.text
    if isinstance(cell, Float32Scalar):
        return struct.unpack(">f", bytes.fromhex(cell.bits_hex))[0]
    if isinstance(cell, Float64Scalar):
        return struct.unpack(">d", bytes.fromhex(cell.bits_hex))[0]
    if isinstance(cell, (bytes, bytearray)):
        return bytes(cell)
    if type(cell).__name__ == "SqlSetValue":
        return list(getattr(cell, "members"))
    text = getattr(cell, "text", None)
    if isinstance(text, str):
        return text
    raw_bytes = getattr(cell, "raw_bytes", None)
    if isinstance(raw_bytes, bytes):
        return raw_bytes
    raise TypeError(f"unsupported benchmark scalar {type(cell).__name__}")


def _fallback_batches(table: SnapshotTable) -> tuple[pa.Schema, list[pa.RecordBatch]]:
    if table.reader is None:
        raise ValueError(f"{table.descriptor.table_name}: reference row reader is unavailable")
    descriptor = table.descriptor
    rows = list(table.reader.reopen().iter_rows())
    fields = [
        _field_scalar_type(
            pa.field(column.name, _arrow_type(column), nullable=column.nullable),
            column,
        )
        for column in descriptor.columns
    ]
    schema = pa.schema(fields)
    arrays = [
        pa.array([_python_cell(row[index]) for row in rows], type=field.type)
        for index, field in enumerate(fields)
    ]
    return schema, [pa.RecordBatch.from_arrays(arrays, schema=schema)]


def _export_side(table: SnapshotTable | None, path: Path) -> None:
    if table is None:
        return
    if table.batch_reader is not None:
        reader = table.batch_reader.reopen()
        original_schema = reader.schema()
        descriptors = {column.name: column for column in table.descriptor.columns}
        schema = pa.schema(
            [_field_scalar_type(field, descriptors[field.name]) for field in original_schema],
            metadata=original_schema.metadata,
        )
        batches = [
            pa.RecordBatch.from_arrays(batch.columns, schema=schema)
            for batch in reader.iter_record_batches()
        ]
        reader.close()
    else:
        schema, batches = _fallback_batches(table)
    _private_dir(path.parent)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as sink:
        with pa_ipc.new_file(sink, schema, options=pa_ipc.IpcWriteOptions(compression=None)) as writer:
            for batch in batches:
                writer.write_batch(batch)
    path.chmod(0o600)


def _normal_provenance(table: SnapshotTable | None) -> str:
    if table is None:
        return BlankRowProvenance.SOURCE_MISSING_STABLE_KEY.value
    if table.ordered_metadata is None:
        return "MISSING"
    return table.ordered_metadata.blank_provenance.value


def _input_case(
    case_id: str,
    corpus: str,
    task: TableComparisonTask,
    fact: ComparisonTableFact,
    root: Path,
    *,
    measure_python: bool = False,
    runs: int = 3,
) -> tuple[dict[str, object], dict[str, object] | None]:
    before_relative = None if task.before_table is None else f"ipc/{case_id}.before.arrow"
    current_relative = None if task.current_table is None else f"ipc/{case_id}.current.arrow"
    if task.before_table is not None:
        assert before_relative is not None
        _export_side(task.before_table, root / before_relative)
    if task.current_table is not None:
        assert current_relative is not None
        _export_side(task.current_table, root / current_relative)
    expected_relative = f"expected/{case_id}.ocf"
    _write_private(root / expected_relative, _ocf(_normal_form(fact, task)))
    policy = task.policy
    if policy is None or policy.ordered_policy is None:
        raise ValueError(f"{task.table_name}: task has no ordered policy")
    ordered_policy = policy.ordered_policy
    schema_changes = fact.schema_changes
    raw_content_changed = False
    if task.before_descriptor is not None and task.current_descriptor is not None:
        raw_content_changed = (
            task.before_descriptor.raw_content_digest != task.current_descriptor.raw_content_digest
        )
    candidate_value_columns = ordered_policy.value_columns or tuple(
        column
        for column in schema_changes.selected_columns
        if column not in set(ordered_policy.order_key)
        and column not in set(ordered_policy.row_identity_key or ())
    )
    excluded = set(policy.compare_excluded_columns)
    value_columns = [column for column in candidate_value_columns if column not in excluded]
    schema_changed = (
        task.before_descriptor is not None
        and task.current_descriptor is not None
        and task.before_descriptor.business_schema_digest != task.current_descriptor.business_schema_digest
    )
    case = {
        "case_id": case_id,
        "corpus": corpus,
        "table_name": task.table_name,
        "before_ipc": before_relative,
        "current_ipc": current_relative,
        "expected_ocf": expected_relative,
        "policy": {
            "policy_version": ordered_policy.policy_version,
            "policy_digest": _digest_value(ordered_policy.policy_digest),
            "value_columns": value_columns,
            "digest_value_columns": list(candidate_value_columns),
            "compare_excluded_columns": sorted(excluded),
            "include_add_delete_records": task.artifact_scope is ArtifactScope.ALL_CHANGES,
            "schema_changed": schema_changed,
            "raw_content_changed": raw_content_changed,
            "schema_changes": _schema_changes(schema_changes),
            "before_blank_provenance": _normal_provenance(task.before_table),
            "current_blank_provenance": _normal_provenance(task.current_table),
            "max_rows": 2_000_000,
        },
    }
    python_metrics = None
    if measure_python:
        timings: list[float] = []
        latest: ComparisonTableFact | None = None
        for index in range(runs + 1):
            started = time.perf_counter()
            latest = ordered_reference.compare_ordered_task(task)
            elapsed = time.perf_counter() - started
            if index:
                timings.append(elapsed)
        if latest is None:
            raise RuntimeError("Python benchmark did not produce a fact")
        python_metrics = {
            "case_id": case_id,
            "table_name": task.table_name,
            "before_rows": fact.row_count_before,
            "current_rows": fact.row_count_current,
            "python_median_seconds": statistics.median(timings),
            "python_min_seconds": min(timings),
            "python_max_seconds": max(timings),
            "standard_record_count": len(fact.records),
            "ordered_record_count": len(fact.ordered_extension.records if fact.ordered_extension else ()),
            "blank_record_count": len(fact.blank_extension.records if fact.blank_extension else ()),
        }
    return case, python_metrics


def _materialize_package(package_bytes: bytes, store: InMemoryArtifactStore) -> BoundSnapshotInput:
    ref = put_with_built_ref(
        store,
        package_bytes,
        artifact_id=f"p6-v1-{uuid.uuid4().hex}",
        media_type="application/gzip",
    )
    binding = SourceArtifactBinding(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        raw_sha256=ref.raw_sha256.value,
    )
    bound, _, _ = preview_jobs._materialize_uploaded_side(
        binding,
        store,
        migrated_table_ruleset_snapshot(),
        side=OperationDiagnosticSide.MODIFIED,
    )
    return bound


def _close_bound(bound: BoundSnapshotInput) -> None:
    if bound.table_set is None:
        return
    for table in bound.table_set.tables:
        for reader in (table.reader, table.batch_reader):
            if reader is not None:
                reader.close()


def _changed(task: TableComparisonTask) -> bool:
    before = task.before_descriptor
    current = task.current_descriptor
    if before is None or current is None or task.policy is None:
        return True
    return not comparison_encoding._can_table_early_exit(before, current, task.policy)


def _real_pairs(outdir: Path, tiers: list[str], packages_dir: Path, runs: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    cases: list[dict[str, object]] = []
    python_metrics: list[dict[str, object]] = []
    package_names = {
        "t1": "rd-t1-a",
        "t2": "rd-t2-b",
        "t3": "rd-t3-c",
        "t4": "rd-t4-d",
    }
    ruleset = migrated_table_ruleset_snapshot()
    rules = comparison_rule_set(ruleset)
    for tier in tiers:
        package_stem = package_names[tier]
        store = InMemoryArtifactStore()
        before = _materialize_package((packages_dir / f"{package_stem}-v1.tar.gz").read_bytes(), store)
        current = _materialize_package((packages_dir / f"{package_stem}-v2.tar.gz").read_bytes(), store)
        plan = plan_comparison(ComparisonRequest(pair_id=f"p6-v1-{tier}", before=before, current=current, rule_set=rules))
        if not isinstance(plan, ComparisonPlan):
            raise RuntimeError(f"{tier}: comparison planning failed")
        changed_ordered = [
            task for task in plan.tasks
            if task.policy is not None and task.policy.ordered_policy is not None and _changed(task)
        ]
        if tier == "t4" and changed_ordered:
            group_timings: list[float] = []
            for iteration in range(runs + 1):
                started = time.perf_counter()
                facts = [ordered_reference.compare_ordered_task(task) for task in changed_ordered]
                elapsed = time.perf_counter() - started
                del facts
                if iteration:
                    group_timings.append(elapsed)
            python_metrics.append(
                {
                    "scope": "t4-changed-ordered-set",
                    "table_count": len(changed_ordered),
                    "python_median_seconds": statistics.median(group_timings),
                    "python_min_seconds": min(group_timings),
                    "python_max_seconds": max(group_timings),
                }
            )
            python_metrics.append(
                {
                    "scope": "t4-changed-ordered-set-memory",
                    **_comparison_peak_rss(changed_ordered),
                }
            )
        for index, task in enumerate(changed_ordered):
            fact = ordered_reference.compare_ordered_task(task)
            case_id = f"{tier}-{index:04d}"
            case, metric = _input_case(
                case_id,
                "real",
                task,
                fact,
                outdir,
                measure_python=tier == "t4",
                runs=runs,
            )
            cases.append(case)
            if metric is not None:
                python_metrics.append(metric)
        _close_bound(before)
        _close_bound(current)
    return cases, python_metrics


def _reference_plan(before_sql: str, current_sql: str, case_id: str) -> tuple[ComparisonPlan, list[TableComparisonTask]]:
    from tests.test_comparison_ordered import _bound

    before = _bound(before_sql)
    current = _bound(current_sql)
    plan = plan_comparison(
        ComparisonRequest(
            pair_id=case_id,
            before=before,
            current=current,
            rule_set=comparison_rule_set(migrated_table_ruleset_snapshot()),
        )
    )
    if not isinstance(plan, ComparisonPlan):
        raise RuntimeError(f"{case_id}: ordered fixture planning failed")
    return plan, [
        task for task in plan.tasks
        if task.policy is not None and task.policy.ordered_policy is not None
    ]


def _synthetic_sql(rows: list[tuple[int | None, str]], *, table: str = "t") -> str:
    literals = [
        f"({('NULL' if gid is None else gid)}, {index}, '{value}')"
        for index, (gid, value) in enumerate(rows, start=1)
    ]
    body = ", ".join(literals) if literals else "(NULL, 1, 'empty')"
    return (
        f"CREATE TABLE {table} (gid BIGINT NULL, no INT NULL, value VARCHAR(32) NULL);\n"
        f"INSERT INTO {table} VALUES {body};"
    )


def _random_rows(rng: random.Random, size: int) -> list[tuple[int | None, str]]:
    rows: list[tuple[int | None, str]] = []
    for gid in range(1, size + 1):
        if rng.random() < 0.18:
            rows.append((None, f"blank-{rng.randrange(1000)}"))
        else:
            rows.append((gid, f"value-{rng.randrange(1000)}"))
    return rows


def _mutate_rows(rng: random.Random, rows: list[tuple[int | None, str]]) -> list[tuple[int | None, str]]:
    result = rows.copy()
    operations = ["insert", "delete", "move", "modify", "blank"]
    for _ in range(rng.randint(1, 5)):
        operation = rng.choice(operations)
        if operation == "insert":
            existing = {gid for gid, _ in result if gid is not None}
            candidate = max(existing, default=100) + rng.randint(1, 50)
            result.insert(rng.randrange(len(result) + 1), (candidate, f"insert-{rng.randrange(1000)}"))
        elif operation == "delete" and result:
            result.pop(rng.randrange(len(result)))
        elif operation == "move" and len(result) > 1:
            item = result.pop(rng.randrange(len(result)))
            result.insert(rng.randrange(len(result) + 1), item)
        elif operation == "modify" and result:
            index = rng.randrange(len(result))
            gid, _ = result[index]
            result[index] = (gid, f"changed-{rng.randrange(1000)}")
        elif operation == "blank" and result:
            index = rng.randrange(len(result))
            result[index] = (None, f"blank-change-{rng.randrange(1000)}")
    if not any(gid is not None for gid, _ in result):
        result.append((1_000_000 + rng.randrange(10000), "stable-seed"))
    return result


def _build_synthetic_and_random(outdir: Path, random_samples: int, seed: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    backend_root = str(Path(__file__).resolve().parents[1])
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)
    from tests.test_comparison_ordered import BACKBONE_OUTCOMES, _plan

    cases: list[dict[str, object]] = []
    names = [
        "real-row-removed-between-blank-segments",
        "real-row-inserted-inside-blank-segment",
        "real-row-moved-with-blank-rows-untouched",
        "real-row-appended-after-blank-segment",
        "first-of-six-real-rows-moved-to-end",
        "blank-row-inserted-above-five-real-rows",
        "blank-row-inserted-inside-segment",
        "blank-row-deleted-inside-segment",
        "blank-and-real-rows-changed-together",
        "blank-row-appended-at-tail",
        "blank-row-deleted-at-tail",
        "blank-notation-and-payload-ignored",
        "tie-keeps-earlier-before-row",
        "tie-among-three-longest-runs",
        "content-only-update",
        "content-update-with-tail-insert",
        "tail-replacement-without-shift",
        "absolute-renumber-only",
        "two-row-swap",
        "in-place-replacement",
    ]
    for index, parameters in enumerate(BACKBONE_OUTCOMES):
        before_sql, current_sql, _ = parameters.values
        plan = _plan(before_sql, current_sql)
        task = next(item for item in plan.tasks if item.policy is not None and item.policy.ordered_policy is not None)
        fact = ordered_reference.compare_ordered_task(task)
        case, _ = _input_case(f"synthetic-{index:03d}", "synthetic", task, fact, outdir)
        case["case_label"] = names[index] if index < len(names) else f"reference-case-{index}"
        cases.append(case)

    blank_pairs = (
        (
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a'),(NULL,2,'x'),(NULL,3,'y'),(2,4,'b');",
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a'),(NULL,2,'changed'),(NULL,3,'other'),(2,4,'b');",
        ),
        (
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a'),(NULL,2,'x'),(NULL,3,'y'),(2,100,'b');",
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a'),(NULL,2,'changed'),(2,4,'b');",
        ),
        (
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a'),(NULL,2,'x'),(2,4,'b');",
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a'),(NULL,2,'x'),(NULL,3,'y'),(2,100,'b');",
        ),
        (
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a'),(NULL,2,'x'),(2,3,'b');",
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a'),(2,2,'b'),(NULL,3,'x');",
        ),
        (
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a');",
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a'),(2,2,'b');",
        ),
        (
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a'),(2,2,'b');",
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a');",
        ),
    )
    for index, (before_sql, current_sql) in enumerate(blank_pairs):
        plan = _plan(before_sql, current_sql)
        task = next(item for item in plan.tasks if item.policy is not None and item.policy.ordered_policy is not None)
        fact = ordered_reference.compare_ordered_task(task)
        case, _ = _input_case(f"blank-contract-{index:03d}", "synthetic", task, fact, outdir)
        case["case_label"] = f"blank-contract-{index}"
        cases.append(case)

    integrity_pairs = (
        (
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a'),(2,1,'b');",
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a');",
            "duplicate-position",
        ),
        (
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a'),(1,2,'b');",
            "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a');",
            "duplicate-gid",
        ),
    )
    for index, (before_sql, current_sql, label) in enumerate(integrity_pairs):
        plan = _plan(before_sql, current_sql)
        task = next(item for item in plan.tasks if item.policy is not None and item.policy.ordered_policy is not None)
        fact = ordered_reference.compare_ordered_task(task)
        case, _ = _input_case(f"ordered-integrity-{index:03d}", "synthetic", task, fact, outdir)
        case["case_label"] = label
        cases.append(case)

    schema_plan = _plan(
        "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a');",
        "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL, added VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a','new');",
    )
    schema_task = next(
        item for item in schema_plan.tasks
        if item.policy is not None and item.policy.ordered_policy is not None
    )
    schema_fact = ordered_reference.compare_ordered_task(schema_task)
    schema_case, _ = _input_case(
        "ordered-schema-added-column-only", "synthetic", schema_task, schema_fact, outdir
    )
    schema_case["case_label"] = "added-column-only"
    cases.append(schema_case)

    missing_plan = _plan(
        "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a');",
        "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL); INSERT INTO t VALUES (1,1,'a');",
    )
    missing_task = next(item for item in missing_plan.tasks if item.policy is not None and item.policy.ordered_policy is not None)
    if missing_task.before_table is None:
        raise RuntimeError("missing-provenance fixture has no before table")
    missing_table = replace(missing_task.before_table, ordered_metadata=None)
    missing_task = replace(missing_task, before_table=missing_table)
    missing_fact = ordered_reference.compare_ordered_task(missing_task)
    missing_case, _ = _input_case("ordered-integrity-missing-provenance", "synthetic", missing_task, missing_fact, outdir)
    missing_case["case_label"] = "missing-provenance"
    cases.append(missing_case)

    rng = random.Random(seed)
    random_cases: list[dict[str, object]] = []
    for index in range(random_samples):
        before_rows = _random_rows(rng, rng.randint(4, 18))
        current_rows = _mutate_rows(rng, before_rows)
        before_sql = _synthetic_sql(before_rows)
        current_sql = _synthetic_sql(current_rows)
        plan = _plan(before_sql, current_sql)
        task = next(item for item in plan.tasks if item.policy is not None and item.policy.ordered_policy is not None)
        fact = ordered_reference.compare_ordered_task(task)
        case, _ = _input_case(f"random-{index:04d}", "random", task, fact, outdir)
        case["seed"] = seed
        random_cases.append(case)
    return cases, random_cases


def _scale_rows(count: int, *, reverse: bool) -> list[tuple[object, ...]]:
    gids = range(count, 0, -1) if reverse else range(1, count + 1)
    rows = []
    for position, gid in enumerate(gids, start=1):
        rows.append((UnsignedIntegerScalar(str(gid)), SignedIntegerScalar(str(position)), StringScalar("x")))
    return rows


class _SyntheticReader:
    def __init__(self, descriptor: SnapshotTableDescriptor, rows: tuple[tuple[object, ...], ...]) -> None:
        self._descriptor = descriptor
        self._rows = rows

    def descriptor(self) -> SnapshotTableDescriptor:
        return self._descriptor

    def iter_rows(self):
        return iter(self._rows)

    def count_column_values(self, column_name: str):
        raise RuntimeError(f"unexpected count request for {column_name}")

    def close(self) -> None:
        return None

    def reopen(self) -> _SyntheticReader:
        return _SyntheticReader(self._descriptor, self._rows)


def _synthetic_scale_task(count: int) -> tuple[TableComparisonTask, pa.RecordBatch, pa.RecordBatch]:
    name = f"b1_n1_p6v1_scale_{count}"
    columns = (
        SnapshotColumnDescriptor("gid", "gid", False, "INT UNSIGNED"),
        SnapshotColumnDescriptor("no", "no", False, "INT"),
        SnapshotColumnDescriptor("value", "value", False, "VARCHAR(8)"),
    )
    digest = raw_blob_digest(f"scale-{count}".encode())

    def descriptor() -> SnapshotTableDescriptor:
        return SnapshotTableDescriptor(
            table_name=name,
            display_table_name=name,
            columns=columns,
            primary_key_columns=("gid",),
            compare_key_columns=("gid",),
            row_count=count,
            materialization_stage=MaterializationStage.FINAL,
            compare_schema_digest=digest,
            table_ruleset_version=1,
            row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
            scalar_encoding_version=SCALAR_ENCODING_VERSION,
            raw_content_digest=digest,
        )

    before_descriptor = descriptor()
    current_descriptor = descriptor()
    before_rows = tuple(_scale_rows(count, reverse=False))
    current_rows = tuple(_scale_rows(count, reverse=True))
    before_reader = _SyntheticReader(before_descriptor, before_rows)
    current_reader = _SyntheticReader(current_descriptor, current_rows)
    ordered_metadata = SnapshotTableOrderedMetadata(BlankRowProvenance.SOURCE_MISSING_STABLE_KEY)
    before_table = SnapshotTable(before_descriptor, before_reader, ordered_metadata=ordered_metadata)
    current_table = SnapshotTable(current_descriptor, current_reader, ordered_metadata=ordered_metadata)
    policy = _ComparisonTablePolicy(
        table_name=name,
        ordered_policy=OrderedTablePolicy(
            policy_id="ordered-runtime-v1",
            policy_version="iec104-gid-no-v1",
            order_key=("no",),
            row_identity_key=("gid",),
            stable_key_candidates=("gid",),
            blank_row_policy=BlankRowPolicy.PSEUDO_BLANK_BY_MISSING_STABLE_KEY,
            value_columns=("value",),
        ),
        effective_key_before=("gid",),
        effective_key_current=("gid",),
    )
    task = TableComparisonTask(
        table_name=name,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        before_table=before_table,
        current_table=current_table,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        policy=policy,
    )
    before_batch = pa.RecordBatch.from_arrays(
        [pa.array(range(1, count + 1), type=pa.uint64()), pa.array(range(1, count + 1), type=pa.int64()), pa.array(["x"] * count)],
        names=["gid", "no", "value"],
    )
    current_batch = pa.RecordBatch.from_arrays(
        [pa.array(range(count, 0, -1), type=pa.uint64()), pa.array(range(1, count + 1), type=pa.int64()), pa.array(["x"] * count)],
        names=["gid", "no", "value"],
    )
    return task, before_batch, current_batch


def _export_scale_cases(outdir: Path, sizes: list[int], runs: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    cases = []
    metrics = []
    for count in sizes:
        task, before_batch, current_batch = _synthetic_scale_task(count)
        # The scale fixture uses the same table reader as the Python oracle and a
        # value-equivalent Arrow batch as the Rust input.
        fact = ordered_reference.compare_ordered_task(task)
        ordered_fact = fact.ordered_extension
        case_id = f"scale-{count}"
        before_relative = f"ipc/{case_id}.before.arrow"
        current_relative = f"ipc/{case_id}.current.arrow"
        _export_batch(before_batch, task.before_descriptor, outdir / before_relative)
        _export_batch(current_batch, task.current_descriptor, outdir / current_relative)
        expected_relative = f"expected/{case_id}.ocf"
        _write_private(outdir / expected_relative, _ocf(_normal_form(fact, task)))
        case = {
            "case_id": case_id,
            "corpus": "scale",
            "table_name": task.table_name,
            "before_ipc": before_relative,
            "current_ipc": current_relative,
            "expected_ocf": expected_relative,
            "policy": {
                "policy_version": "iec104-gid-no-v1",
                "policy_digest": (
                    None
                    if ordered_fact is None
                    else _digest_value(ordered_fact.policy_digest)
                ),
                "value_columns": ["value"],
                "digest_value_columns": ["value"],
                "compare_excluded_columns": [],
                "include_add_delete_records": True,
                "schema_changed": False,
                "raw_content_changed": True,
                "schema_changes": _schema_changes(fact.schema_changes),
                "before_blank_provenance": BlankRowProvenance.SOURCE_MISSING_STABLE_KEY.value,
                "current_blank_provenance": BlankRowProvenance.SOURCE_MISSING_STABLE_KEY.value,
                "max_rows": 2_000_000,
            },
        }
        cases.append(case)
        timings = []
        for iteration in range(runs + 1):
            started = time.perf_counter()
            ordered_reference.compare_ordered_task(task)
            elapsed = time.perf_counter() - started
            if iteration:
                timings.append(elapsed)
        metrics.append(
            {
                "case_id": case_id,
                "table_name": task.table_name,
                "rows": count,
                "python_median_seconds": statistics.median(timings),
                "python_min_seconds": min(timings),
                "python_max_seconds": max(timings),
                "moved_rows": fact.ordered_extension.ordered_summary.row_moved_count if fact.ordered_extension else 0,
            }
        )
        del task, before_batch, current_batch, fact
    return cases, metrics


def _export_batch(batch: pa.RecordBatch, descriptor: SnapshotTableDescriptor | None, path: Path) -> None:
    if descriptor is None:
        raise ValueError("synthetic scale table is missing its descriptor")
    columns = {column.name: column for column in descriptor.columns}
    schema = pa.schema(
        [_field_scalar_type(field, columns[field.name]) for field in batch.schema],
        metadata=batch.schema.metadata,
    )
    _private_dir(path.parent)
    descriptor_fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor_fd, "wb") as sink:
        with pa_ipc.new_file(sink, schema, options=pa_ipc.IpcWriteOptions(compression=None)) as writer:
            writer.write_batch(pa.RecordBatch.from_arrays(batch.columns, schema=schema))
    path.chmod(0o600)


def prepare(args: argparse.Namespace) -> int:
    outdir = Path(args.outdir).resolve()
    _private_dir(outdir)
    manifests: dict[str, list[dict[str, object]]] = {}
    python_metrics: list[dict[str, object]] = []
    if args.tiers:
        real_cases, python_metrics = _real_pairs(outdir, args.tiers, Path(args.packages_dir), args.runs)
        manifests["real"] = real_cases
    if args.synthetic or args.random_samples:
        synthetic_cases, random_cases = _build_synthetic_and_random(outdir, args.random_samples, args.seed)
        if args.synthetic:
            manifests["synthetic"] = synthetic_cases
        if args.random_samples:
            manifests["random"] = random_cases
    if args.scale_sizes:
        scale_cases, scale_metrics = _export_scale_cases(outdir, args.scale_sizes, args.runs)
        manifests["scale"] = scale_cases
        python_metrics.extend(scale_metrics)
    for corpus, cases in manifests.items():
        _write_json(outdir / f"{corpus}.manifest.json", {"format": "gateway.comparison.ordered-inputs", "version": 1, "cases": cases})
    _write_json(
        outdir / "python-measurements.json",
        {
            "measurement": "comparison kernel only; materialization, IPC, and normal-form encoding excluded",
            "warmups": 1,
            "runs": args.runs,
            "python_peak_rss_kib": _peak_rss_kib(),
            "cases": python_metrics,
        },
    )
    summary = {
        "outdir": str(outdir),
        "manifests": {name: len(cases) for name, cases in manifests.items()},
        "real_tables": sorted(
            (case["corpus"], case["table_name"], case["case_id"])
            for cases in manifests.values() for case in cases if case["corpus"] == "real"
        ),
        "random_seed": args.seed,
        "random_samples": args.random_samples,
        "scale_rows": args.scale_sizes,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


def _peak_rss_kib() -> int | None:
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value if sys.platform == "darwin" else value
    except (ImportError, OSError, ValueError):
        return None


def _current_rss_kib() -> int | None:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _comparison_peak_rss(tasks: list[TableComparisonTask]) -> dict[str, object]:
    baseline = _current_rss_kib()
    peak = baseline or 0
    stopped = threading.Event()

    def sample() -> None:
        nonlocal peak
        while not stopped.wait(0.005):
            rss = _current_rss_kib()
            if rss is not None:
                peak = max(peak, rss)

    monitor = threading.Thread(target=sample, name="p6-v1-rss-sampler", daemon=True)
    monitor.start()
    try:
        facts = [ordered_reference.compare_ordered_task(task) for task in tasks]
    finally:
        stopped.set()
        monitor.join()
    end_rss = _current_rss_kib()
    if end_rss is not None:
        peak = max(peak, end_rss)
    return {
        "baseline_rss_kib": baseline,
        "peak_rss_kib": peak or None,
        "comparison_rss_delta_kib": None if baseline is None else max(peak - baseline, 0),
        "comparison_tables": len(facts),
        "process_high_water_rss_kib": _peak_rss_kib(),
    }


def audit(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve()
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    entries = []
    differences = 0
    for case in manifest["cases"]:
        expected_path = root / case["expected_ocf"]
        actual_path = root / args.actual_dir / f"{case['case_id']}.rust.ocf"
        expected = expected_path.read_bytes()
        actual = actual_path.read_bytes() if actual_path.exists() else b""
        same = expected == actual
        differences += int(not same)
        reference = _read_ocf(expected_path)
        table = {
            "case_id": case["case_id"],
            "corpus": case["corpus"],
            "table_name": case["table_name"],
            "same": same,
            "before_rows": reference["row_count_before"],
            "current_rows": reference["row_count_current"],
            "row_added_count": reference["row_added_count"],
            "row_deleted_count": reference["row_deleted_count"],
            "row_modified_count": reference["row_modified_count"],
            "standard_record_count": len(reference["records"]),
            "ordered_record_count": len(reference["ordered_extension"]["records"]),
            "blank_record_count": len(reference["blank_extension"]["records"]),
            "ordered_digest_before": reference["ordered_extension"]["before_ordered_digest"],
            "ordered_digest_current": reference["ordered_extension"]["current_ordered_digest"],
            "type_markers": _type_markers(reference),
            "sample_positions": _sample_positions(reference),
        }
        entries.append(table)
    output = {
        "manifest": manifest_path.name,
        "case_count": len(entries),
        "difference_count": differences,
        "record_count": sum(item["standard_record_count"] + item["ordered_record_count"] + item["blank_record_count"] for item in entries),
        "rows_before": sum(item["before_rows"] or 0 for item in entries),
        "rows_current": sum(item["current_rows"] or 0 for item in entries),
        "tables": entries,
    }
    if args.out:
        _write_json(Path(args.out).resolve(), output)
    print(json.dumps({key: value for key, value in output.items() if key != "tables"}, sort_keys=True))
    return 0 if differences == 0 else 1


def _type_markers(value: dict[str, Any]) -> list[int]:
    markers: set[int] = set()

    def visit(item: object) -> None:
        if isinstance(item, dict):
            if type(item.get("type_marker")) is int:
                markers.add(item["type_marker"])
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return sorted(markers)


def _sample_positions(value: dict[str, Any]) -> list[int]:
    positions: list[int] = []
    for record in value["ordered_extension"]["records"]:
        for key in ("before_position", "current_position"):
            position = record[key]
            if position is not None:
                positions.append(position)
                if len(positions) >= 16:
                    return positions
    for record in value["blank_extension"]["records"]:
        interval = record["interval"]
        for key in ("before_start", "before_end", "current_start", "current_end"):
            position = interval[key]
            if position is not None:
                positions.append(position)
                if len(positions) >= 16:
                    return positions
    return positions


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--outdir", required=True)
    prepare_parser.add_argument("--packages-dir", default="/home/dev/gateway-real-dumps/packages")
    prepare_parser.add_argument("--tiers", nargs="*", choices=("t1", "t2", "t3", "t4"), default=[])
    prepare_parser.add_argument("--synthetic", action="store_true")
    prepare_parser.add_argument("--random-samples", type=int, default=0)
    prepare_parser.add_argument("--seed", type=int, default=20261025)
    prepare_parser.add_argument("--scale-sizes", type=lambda value: [int(item) for item in value.split(",")], default=[])
    prepare_parser.add_argument("--runs", type=int, default=3)
    prepare_parser.set_defaults(handler=prepare)
    audit_parser = commands.add_parser("audit")
    audit_parser.add_argument("--manifest", required=True)
    audit_parser.add_argument("--actual-dir", default="actual")
    audit_parser.add_argument("--out")
    audit_parser.set_defaults(handler=audit)
    return parser


def main() -> int:
    args = make_parser().parse_args()
    if getattr(args, "random_samples", 0) < 0:
        raise SystemExit("--random-samples must be non-negative")
    if getattr(args, "runs", 1) < 1:
        raise SystemExit("--runs must be positive")
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
