"""Replacement-period B differential against the fixed 4d5 Python algorithms.

E removes this file and the native _s3_compare_probe once the production route
uses Arrow builders. The source pins fail closed if a later stage changes the
Python reference, so this test cannot compare a new route with itself.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from gateway_compute._native import _encode_canonical_ipc_native, _s3_compare_probe
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.capabilities.comparison import (
    ArtifactScope, BoundSnapshotInput, ComparisonPlan, ComparisonRequest,
    ComparisonStorageFacts, ComparisonTableFact, DetailedFactsResult, TableComparisonTask,
    SchemaEvolution, compare_plan, plan_comparison,
)
from gateway_backend.capabilities.comparison import standard as old_standard
from gateway_backend.capabilities.comparison.row_encoding import _can_table_early_exit, _encode_cell
from gateway_backend.capabilities.snapshot_materialization.canonical_store import canonical_columns
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BlankRowProvenance, MaterializationPolicy, SnapshotTable,
)
from gateway_backend.capabilities.table_access import NeverCancel
from gateway_backend.capabilities.table_rules.contracts import CanonicalKeyPolicy, OrderedPolicy, StorageRuleView
from tests.support.snapshot_materialization import materialize_sql
from tests.support.table_rules import comparison_ruleset_for, fallback_record, ordered_record, standard_rule_record

pytestmark = pytest.mark.unit

_REFERENCE_SOURCES = {
    "standard.py": "3ff92146caac590ac989b3fa08ed1200ac410c2ccb9bd9c8a95f15f73422acf4",
    "ordered.py": "049ff089f20e8bbc1e72090d54d2ae88ea15ef84e324819241a07e2d68bd160f",
    "row_encoding.py": "41fae5ad009edbcc1c947c0266182b99c924cc728db21ad9942770236e7b397e",
}
_SOURCE_DIR = Path(__file__).resolve().parents[1] / "src/gateway_backend/capabilities/comparison"
_CODEC_BUDGETS = {
    "max_columns": 2048, "max_input_batches": 4096, "max_rows": 10_000_000,
    "max_descriptor_bytes": 16 * 1024**2, "max_input_bytes": 1024**3,
    "max_output_bytes": 1024**3, "max_codec_peak_bytes": 24 * 1024**3,
}


def _fixed_reference() -> None:
    assert compare_plan is old_standard.compare_plan
    for name, digest in _REFERENCE_SOURCES.items():
        assert hashlib.sha256((_SOURCE_DIR / name).read_bytes()).hexdigest() == digest


def _bound(sql: str) -> BoundSnapshotInput:
    materialized = materialize_sql(sql, policy=MaterializationPolicy.READERS_REQUIRED)
    assert materialized.snapshot is not None
    assert materialized.summary is not None
    assert materialized.table_set is not None
    return BoundSnapshotInput(
        materialized.snapshot, materialized.summary, materialized.table_set,
    )


def _fallback_bound(sql: str) -> BoundSnapshotInput:
    bound = _bound(sql)
    descriptor = bound.summary.tables[0]
    facts = ComparisonStorageFacts(
        storage_rule_view=StorageRuleView(
            canonical_table=descriptor.table_name,
            canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS,
            ordered_policy=OrderedPolicy.NONE,
            retained_columns=tuple(column.name for column in descriptor.columns),
            canonical_key_columns=descriptor.primary_key_columns,
        ),
        source_schema_digest=raw_blob_digest(b"s3-b-fixed-keyless-source"),
    )
    return replace(bound, storage_facts=(facts,))


def _plan(
    before: BoundSnapshotInput, current: BoundSnapshotInput, *, ordered: bool = False,
    keyless: bool = False, excluded: tuple[str, ...] = (),
) -> ComparisonPlan:
    record = (
        ordered_record(r"^t$", compare_excluded_columns=excluded) if ordered else
        fallback_record() if keyless else standard_rule_record("t")
    )
    plan = plan_comparison(ComparisonRequest(
        pair_id="s3-b-frozen-differential",
        before=before, current=current,
        rule_set=comparison_ruleset_for(record),
    ))
    assert isinstance(plan, ComparisonPlan)
    return plan


def _fact(plan: ComparisonPlan) -> ComparisonTableFact:
    result = compare_plan(plan)
    assert isinstance(result, DetailedFactsResult)
    assert result.facts is not None
    assert len(result.facts.tables) == 1
    return result.facts.tables[0]


def _canonical_stream(table: SnapshotTable) -> pa.RecordBatchReader:
    assert table.reader is not None
    if callable(getattr(table.reader, "arrow_stream", None)):
        isolated = table.reader.reopen()
        try:
            with isolated.arrow_stream() as source:
                raw = _encode_canonical_ipc_native(
                    canonical_columns(table.descriptor), source, NeverCancel(), _CODEC_BUDGETS,
                )
        finally:
            isolated.close()
    else:
        assert table.batch_reader is not None
        isolated_batches = table.batch_reader.reopen()
        try:
            source = pa.RecordBatchReader.from_batches(
                isolated_batches.schema(), isolated_batches.iter_record_batches(),
            )
            try:
                raw = _encode_canonical_ipc_native(
                    canonical_columns(table.descriptor), source, NeverCancel(), _CODEC_BUDGETS,
                )
            finally:
                source.close()
        finally:
            isolated_batches.close()
    encoded = pa.ipc.open_file(pa.BufferReader(raw))
    batches = [encoded.get_batch(index) for index in range(encoded.num_record_batches)]
    schema = encoded.schema
    return pa.RecordBatchReader.from_batches(schema, batches)


def _blank_provenance(table: SnapshotTable) -> str:
    assert table.ordered_metadata is not None
    value = table.ordered_metadata.blank_provenance
    if value is BlankRowProvenance.SOURCE_MISSING_STABLE_KEY:
        return "source"
    if value is BlankRowProvenance.CANONICAL_PSEUDO_GID:
        return "canonical"
    raise AssertionError("ordered comparison has no trusted blank provenance")


def _probe_task(
    task: TableComparisonTask, fact: ComparisonTableFact, *, ordered: bool,
) -> dict[str, Any]:
    assert task.before_table is not None
    assert task.current_table is not None
    assert task.before_descriptor is not None
    assert task.current_descriptor is not None
    assert task.policy is not None
    policy: dict[str, Any] = {
        "selected_columns": list(fact.schema_changes.selected_columns),
        "effective_key_before": list(task.policy.effective_key_before),
        "effective_key_current": list(task.policy.effective_key_current),
        "compare_excluded_columns": list(task.policy.compare_excluded_columns),
        "incompatible_columns": list(fact.schema_changes.incompatible_columns),
        "emit_add_delete": task.artifact_scope is ArtifactScope.ALL_CHANGES,
        "columns_added": fact.schema_changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED,
        "mode": "keyed" if task.policy.effective_key_before else "keyless",
    }
    if ordered:
        ordered_policy = task.policy.ordered_policy
        assert ordered_policy is not None
        policy.update({
            "table_name": task.table_name,
            "policy_version": ordered_policy.policy_version,
            "policy_digest": None if ordered_policy.policy_digest is None else ordered_policy.policy_digest.value,
            "value_columns": list(ordered_policy.value_columns),
            "digest_value_columns": list(ordered_policy.value_columns),
            "schema_changed": fact.status.value == "SCHEMA_ONLY_CHANGED",
            "raw_content_changed": (
                task.before_descriptor.raw_content_digest != task.current_descriptor.raw_content_digest
            ),
            "before_blank_provenance": _blank_provenance(task.before_table),
            "current_blank_provenance": _blank_provenance(task.current_table),
            "schema_changes": {
                "before_only_columns": list(fact.schema_changes.before_only_columns),
                "current_only_columns": list(fact.schema_changes.current_only_columns),
                "selected_columns": list(fact.schema_changes.selected_columns),
                "effective_compare_key_before": list(fact.schema_changes.effective_compare_key_before),
                "effective_compare_key_current": list(fact.schema_changes.effective_compare_key_current),
                "effective_compare_key_changed": fact.schema_changes.effective_compare_key_changed,
                "incompatible_columns": list(fact.schema_changes.incompatible_columns),
                "change_source": None if fact.schema_changes.change_source is None else fact.schema_changes.change_source.value,
            },
        })
        policy["unchanged"] = _can_table_early_exit(
            task.before_descriptor, task.current_descriptor, task.policy,
        )
    before_stream = _canonical_stream(task.before_table)
    current_stream = _canonical_stream(task.current_table)
    try:
        output = _s3_compare_probe(
            "ordered" if ordered else "standard",
            before_stream, current_stream, json.dumps(policy),
        )
    finally:
        before_stream.close()
        current_stream.close()
    parsed = json.loads(output)
    assert isinstance(parsed, dict)
    return parsed


def _probe(plan: ComparisonPlan, fact: ComparisonTableFact, *, ordered: bool) -> dict[str, Any]:
    assert len(plan.tasks) == 1
    return _probe_task(plan.tasks[0], fact, ordered=ordered)


def _identity(value: object) -> str | None:
    return None if value is None else value.value  # type: ignore[attr-defined]


def _frames(values: tuple[tuple[str, object], ...], descriptor: object) -> list[dict[str, str]]:
    columns = {column.name: column for column in descriptor.columns}  # type: ignore[attr-defined]
    return [
        {"column": name, "frame_hex": _encode_cell(columns[name], value).hex()}
        for name, value in values
    ]


def _expected_standard(record: object, before: object, current: object) -> dict[str, object]:
    return {
        "kind": record.record_kind.value,  # type: ignore[attr-defined]
        "row_identity": _identity(record.row_identity),  # type: ignore[attr-defined]
        "changed_columns": list(record.changed_columns),  # type: ignore[attr-defined]
        "diagnostics": list(record.diagnostics),  # type: ignore[attr-defined]
        "before_frames": _frames(record.before_values, before),  # type: ignore[attr-defined]
        "current_frames": _frames(record.current_values, current),  # type: ignore[attr-defined]
    }


def _project_record(record: dict[str, object]) -> dict[str, object]:
    return {
        key: record[key] for key in (
            "kind", "row_identity", "changed_columns", "diagnostics",
            "before_frames", "current_frames",
        )
    }


@pytest.mark.parametrize(
    ("before_sql", "current_sql", "keyless"),
    (
        (
            "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(8));"
            " INSERT INTO t VALUES (1,'a'),(2,'b');",
            "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(8));"
            " INSERT INTO t VALUES (1,'z'),(3,'c');",
            False,
        ),
        (
            "CREATE TABLE t (name VARCHAR(8));"
            " INSERT INTO t VALUES ('a'),('same'),('same');",
            "CREATE TABLE t (name VARCHAR(8));"
            " INSERT INTO t VALUES ('a'),('same'),('other');",
            True,
        ),
    ),
    ids=("keyed-full-values", "keyless-multiset"),
)
def test_standard_probe_matches_fixed_python(
    before_sql: str, current_sql: str, keyless: bool,
) -> None:
    _fixed_reference()
    bound = _fallback_bound if keyless else _bound
    plan = _plan(bound(before_sql), bound(current_sql), keyless=keyless)
    fact = _fact(plan)
    assert len(plan.tasks) == 1
    actual = _probe(plan, fact, ordered=False)
    assert (
        actual["row_added_count"], actual["row_deleted_count"], actual["row_modified_count"],
    ) == (
        fact.row_added_count, fact.row_deleted_count, fact.row_modified_count,
    )
    assert actual["suppressed_added_count"] == fact.suppressed_added_count
    assert actual["suppressed_deleted_count"] == fact.suppressed_deleted_count
    records = [_project_record(actual["records"][index]) for index in actual["facts_order"]]
    expected = [
        _expected_standard(item, plan.tasks[0].before_descriptor, plan.tasks[0].current_descriptor)
        for item in fact.records
    ]
    assert records == expected


def test_ordered_probe_matches_fixed_python_records_and_digests() -> None:
    _fixed_reference()
    before = _bound(
        "CREATE TABLE t (gid BIGINT, no BIGINT, name VARCHAR(8));"
        " INSERT INTO t VALUES (1,1,'a'),(2,2,'b'),(NULL,3,NULL),(3,4,'c');"
    )
    current = _bound(
        "CREATE TABLE t (gid BIGINT, no BIGINT, name VARCHAR(8));"
        " INSERT INTO t VALUES (2,1,'b'),(1,2,'z'),(NULL,3,NULL),(3,4,'c');"
    )
    plan = _plan(before, current, ordered=True)
    fact = _fact(plan)
    assert fact.ordered_extension is not None
    assert fact.blank_extension is not None
    actual = _probe(plan, fact, ordered=True)
    assert actual["status"] == fact.status.value
    assert (
        actual["row_added_count"], actual["row_deleted_count"], actual["row_modified_count"],
    ) == (
        fact.row_added_count, fact.row_deleted_count, fact.row_modified_count,
    )
    ordered = fact.ordered_extension
    blank = fact.blank_extension
    assert actual["before_ordered_digest"] == _identity(ordered.before_ordered_digest)
    assert actual["current_ordered_digest"] == _identity(ordered.current_ordered_digest)
    assert actual["before_occupancy_digest"] == _identity(blank.before_occupancy_digest)
    assert actual["current_occupancy_digest"] == _identity(blank.current_occupancy_digest)
    before_descriptor = plan.tasks[0].before_descriptor
    current_descriptor = plan.tasks[0].current_descriptor
    standard_records = [
        _project_record(actual["standard_records"][index])
        for index in actual["standard_facts_order"]
    ]
    assert standard_records == [
        _expected_standard(item, before_descriptor, current_descriptor)
        for item in fact.records
    ]
    ordered_records = [
        actual["ordered_records"][index] for index in actual["ordered_facts_order"]
    ]
    assert [
        (
            item["kind"], item["semantic_kind"], item["entity_key_kind"],
            item["row_identity"], item["before_position"], item["current_position"],
            item["changed_columns"], item["before_frames"], item["current_frames"],
        )
        for item in ordered_records
    ] == [
        (
            item.record_kind.value, item.semantic_kind.value, item.entity_key_kind.value,
            _identity(item.row_identity), item.before_position, item.current_position,
            list(item.changed_columns),
            _frames(item.before_values, before_descriptor),
            _frames(item.current_values, current_descriptor),
        )
        for item in ordered.records
    ]
    assert [
        (
            item["kind"], item["entity_key_kind"], item["interval"]["interval_digest"],
            item["before_occupancy"], item["current_occupancy"],
        )
        for item in actual["blank_records"]
    ] == [
        (
            item.record_kind.value, item.entity_key_kind.value,
            _identity(item.interval.interval_digest),
            item.before_occupancy, item.current_occupancy,
        )
        for item in blank.records
    ]


@pytest.mark.parametrize(
    ("current_rows", "changed"),
    (
        ("(2,2,'b','y'),(1,1,'a','x')", False),
        ("(2,2,'b','x'),(1,1,'a','y')", True),
    ),
    ids=("added-column-and-physical-reorder", "excluded-values-swap-association"),
)
def test_ordered_columns_added_uses_full_shared_row_multiset(
    current_rows: str, changed: bool,
) -> None:
    _fixed_reference()
    before = _bound(
        "CREATE TABLE t (gid BIGINT, no BIGINT, name VARCHAR(8), secret VARCHAR(8));"
        " INSERT INTO t VALUES (1,1,'a','x'),(2,2,'b','y');"
    )
    rows_with_added = current_rows.replace(")", ",'z')")
    current = _bound(
        "CREATE TABLE t (gid BIGINT, no BIGINT, name VARCHAR(8), secret VARCHAR(8),"
        " added VARCHAR(8));"
        f" INSERT INTO t VALUES {rows_with_added};"
    )
    plan = _plan(before, current, ordered=True, excluded=("secret",))
    fact = _fact(plan)
    assert fact.schema_changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED
    assert fact.status.value == "UNCHANGED"
    assert fact.content_changed is changed
    actual = _probe(plan, fact, ordered=True)
    assert actual["content_changed"] is changed
    assert actual["standard_records"] == []
    assert actual["ordered_records"] == []
