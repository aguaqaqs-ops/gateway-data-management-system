"""C Arrow records and facts against fixed pre-C Python contract behavior."""

from __future__ import annotations

import base64
import json
from contextlib import closing
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_compute._native import (
    _begin_comparison_operation_native,
    _compare_records_native,
    _facts_core_digest_native,
    _validate_records_batches_native,
)

from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore
from gateway_backend.capabilities.comparison.artifacts import (
    RecordsPublicationContext, RecordsPublicationPolicy, _record_to_row,
    _standalone_retained_cap, _write_arrow_parquet, open_records_closure,
    publish_records_closure, publish_records_family_arrow, read_records_artifact,
    restore_records_closure,
)
from gateway_backend.capabilities.comparison import artifacts as records_artifacts
from gateway_backend.capabilities.comparison.contracts import (
    ArtifactScope, DetailedFactsResult, RecordsArtifactFamily, RecordsDetailPolicy,
    SchemaEvolution,
)
from gateway_backend.capabilities.comparison.row_encoding import (
    _summary_payload, _table_digest_payload,
)
from gateway_backend.capabilities.comparison.standard import STANDARD_COMPARISON_ALGORITHM_VERSION
from gateway_backend.capabilities.table_access import NeverCancel
from gateway_backend.capabilities.table_access.kernel import OperationMemoryBudget
from tests.test_comparison_s3_b_differential import (
    _blank_provenance, _bound, _canonical_stream, _plan,
)
from tests.test_comparison_artifacts import _standard_result
from gateway_backend.capabilities.comparison import compare_plan

pytestmark = pytest.mark.unit


class Charge:
    def __init__(self) -> None:
        self.closed = False
        self.retained_bytes: int | None = None

    def shrink_to(self, size: int) -> None:
        self.retained_bytes = size

    def close(self) -> None:
        self.closed = True


def _native_one() -> tuple[object, object, Charge, Charge, DetailedFactsResult]:
    before = _bound("CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); INSERT INTO t VALUES (1, 'before');")
    current = _bound("CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); INSERT INTO t VALUES (1, NULL);")
    plan = _plan(before, current)
    expected = compare_plan(plan)
    assert isinstance(expected, DetailedFactsResult)
    assert expected.facts is not None
    table = expected.facts.tables[0]
    assert plan.tasks[0].policy is not None
    task = plan.tasks[0]
    assert task.before_table is not None and task.current_table is not None
    policy = {
        "mode": "keyed", "selected_columns": list(table.schema_changes.selected_columns),
        "effective_key_before": list(task.policy.effective_key_before),
        "effective_key_current": list(task.policy.effective_key_current),
        "compare_excluded_columns": [], "incompatible_columns": [],
        "emit_add_delete": True, "columns_added": False,
    }
    operation_charge = Charge()
    input_charge = Charge()
    operation = _begin_comparison_operation_native(2 * 1024**3, operation_charge, NeverCancel())
    before_stream = _canonical_stream(task.before_table)
    current_stream = _canonical_stream(task.current_table)
    try:
        handle = _compare_records_native(
            operation, "standard", "t", before_stream, current_stream, json.dumps(policy),
            "FULL_BEFORE_AFTER_VALUES", 2_000_000, 512 * 1024**2, 512 * 1024**2,
            2 * 1024**3,
            input_charge,
        )
    finally:
        before_stream.close()
        current_stream.close()
    return operation, handle, operation_charge, input_charge, expected


def test_native_standard_arrow_and_complete_facts_match_pre_c_source() -> None:
    operation, handle, operation_charge, input_charge, expected = _native_one()
    assert expected.facts is not None
    fact = expected.facts.tables[0]
    reader = handle.record_batches("STANDARD")
    try:
        built_batches = tuple(reader)
        rows = [row for batch in built_batches for row in batch.to_pylist()]
    finally:
        reader.close()
    assert rows == [_record_to_row(
        RecordsArtifactFamily.STANDARD, fact.records[0],
        RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES,
    )]
    old_store = InMemoryArtifactStore()
    old_published = publish_records_closure(expected, old_store)
    assert isinstance(old_published, DetailedFactsResult)
    assert old_published.records_closure is not None
    assert handle.family_summary("STANDARD") == (
        1, old_published.records_closure.records[0].records_content_digest.value
    )
    old_raw = old_store.locate(old_published.records_closure.records[0].records_ref)
    assert _write_arrow_parquet(
        built_batches, built_batches[0].schema,
        RecordsPublicationPolicy(), RecordsPublicationContext(),
    ) == old_raw
    metadata = _table_digest_payload(fact)
    metadata["records"] = []
    raw = json.dumps(metadata)
    assert fact.table_fact_digest is not None
    assert handle.table_fact_digest(raw, 8 * 1024**2) == fact.table_fact_digest.value
    assert _facts_core_digest_native(
        operation, [handle], [raw], STANDARD_COMPARISON_ALGORITHM_VERSION,
        json.dumps(_summary_payload(expected.facts.summary)), 8 * 1024**2,
    ) == expected.facts.facts_core_digest.value
    handle.close()
    operation.close()
    assert input_charge.closed and operation_charge.closed


def test_exported_arrow_buffers_keep_charge_after_handle_and_reader_close() -> None:
    operation, handle, operation_charge, input_charge, _ = _native_one()
    reader = handle.record_batches("STANDARD")
    batch = reader.read_next_batch()
    table = pa.Table.from_batches([batch])
    reader.close()
    handle.close()
    operation.close()
    assert not input_charge.closed and not operation_charge.closed
    assert table.num_rows == 1
    del batch
    assert not input_charge.closed
    del table
    import gc
    gc.collect()
    assert input_charge.closed and operation_charge.closed


@pytest.mark.parametrize("family", ["standard", "ordered", "blank"])
def test_arrow_writer_preserves_fixed_python_parquet_raw_bytes(family: str) -> None:
    path = Path(__file__).resolve().parents[2] / f"fixtures/vectors/comparison/records/{family}-v1.parquet.b64"
    raw = base64.b64decode(path.read_text(encoding="ascii"))
    source = pq.ParquetFile(pa.BufferReader(raw))
    batches = tuple(source.iter_batches(batch_size=1024))
    assert batches
    rebuilt = _write_arrow_parquet(
        batches, source.schema_arrow, RecordsPublicationPolicy(), RecordsPublicationContext()
    )
    assert rebuilt == raw
    reader = pa.RecordBatchReader.from_batches(source.schema_arrow, batches)
    result = _validate_records_batches_native(
        reader, 2_000_000, 2 * 1024**3, NeverCancel()
    )
    assert result[3] == sum(batch.num_rows for batch in batches)


def test_arrow_family_publish_avoids_records_readback() -> None:
    operation, handle, _, _, _ = _native_one()
    operation.seal()
    with pytest.raises(ValueError, match="sealed"):
        handle.metadata_json()

    class NoRecordsReadbackStore(InMemoryArtifactStore):
        records_ref: ArtifactRef | None = None

        def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
            if ref.media_type == "application/vnd.apache.parquet":
                self.records_ref = ref
            return super().put(raw_bytes, ref)

        def locate(self, ref: ArtifactRef) -> bytes:
            if ref == self.records_ref:
                raise AssertionError("new records artifact was read back")
            return super().locate(ref)

    store = NoRecordsReadbackStore()
    entry = publish_records_family_arrow(
        "t", RecordsArtifactFamily.STANDARD, handle, store,
        detail_policy=RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES,
    )
    assert entry.record_count == 1
    handle.close()
    operation.close()


@pytest.mark.parametrize("count", [0, 1, 1023, 1024, 1025])
def test_native_builder_keeps_1024_batch_boundary(count: int) -> None:
    bound = _bound("CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); INSERT INTO t VALUES (1, 'sample');")
    table = bound.table_set.tables[0]
    sample = _canonical_stream(table)
    schema = sample.schema
    sample.close()
    ids = pa.array(range(1, count + 1), type=schema.field("id").type)
    notes = pa.array(["x"] * count, type=schema.field("note").type)
    whole = pa.RecordBatch.from_arrays([ids, notes], schema=schema)
    source_batches = [whole.slice(offset, min(137, count - offset)) for offset in range(0, count, 137)]
    before = pa.RecordBatchReader.from_batches(schema, [])
    current = pa.RecordBatchReader.from_batches(schema, source_batches)
    operation = _begin_comparison_operation_native(2 * 1024**3, Charge(), NeverCancel())
    handle = _compare_records_native(
        operation, "standard", "t", before, current,
        json.dumps({
            "mode": "keyed", "selected_columns": ["id", "note"],
            "effective_key_before": ["id"], "effective_key_current": ["id"],
            "compare_excluded_columns": [], "incompatible_columns": [],
            "emit_add_delete": True, "columns_added": False,
        }),
        "FULL_BEFORE_AFTER_VALUES", 2_000_000, 512 * 1024**2, 512 * 1024**2,
        2 * 1024**3,
        Charge(),
    )
    reader = handle.record_batches("STANDARD")
    try:
        result_batches = tuple(reader)
    finally:
        reader.close()
        handle.close()
        operation.close()
    assert [batch.num_rows for batch in result_batches] == ([1024, 1] if count == 1025 else [count] if count else [])
    assert all(batch.schema.equals(result_batches[0].schema, check_metadata=True) for batch in result_batches)


def test_real_open_read_restore_use_native_arrow_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    source_store = InMemoryArtifactStore()
    published = publish_records_closure(_standard_result(), source_store)
    assert isinstance(published, DetailedFactsResult)
    assert published.facts is not None and published.facts.records_ref is not None
    real_validate = records_artifacts.validate_records_batches
    calls = 0

    def checked_validate(*args: object, **kwargs: object) -> tuple[str, str, str, int, str]:
        nonlocal calls
        calls += 1
        return real_validate(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(records_artifacts, "validate_records_batches", checked_validate)
    closure = open_records_closure(source_store, published.facts.records_ref)
    with closing(read_records_artifact(source_store, closure.records[0])) as stream:
        first = next(stream)
    assert first.to_pylist()[0]["record_kind"] == "ROW_MODIFIED"
    restored = restore_records_closure(
        source_store, InMemoryArtifactStore(), published.facts.records_ref
    )
    assert restored.closure.comparison_digest == closure.comparison_digest
    assert calls >= 4  # open, diagnostic read, restore source, restore destination


def test_standalone_reader_budget_is_m24_not_a_total_i32_limit() -> None:
    gib = 1024**3
    assert _standalone_retained_cap(512 * 1024**2, gib) > 2 * gib
    with pytest.raises(ValueError, match="standalone memory budget"):
        _standalone_retained_cap(512 * 1024**2, 12 * gib)


def test_counts_only_output_budget_excludes_full_sort_blob() -> None:
    bound = _bound("CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL);")
    schema_reader = _canonical_stream(bound.table_set.tables[0])
    schema = schema_reader.schema
    schema_reader.close()
    large_value = "x" * (1024 * 1024)
    current_batch = pa.RecordBatch.from_arrays(
        [
            pa.array([1], type=schema.field("id").type),
            pa.array([large_value], type=schema.field("note").type),
        ],
        schema=schema,
    )
    operation = _begin_comparison_operation_native(2 * 1024**3, Charge(), NeverCancel())
    before = pa.RecordBatchReader.from_batches(schema, [])
    current = pa.RecordBatchReader.from_batches(schema, [current_batch])
    handle = _compare_records_native(
        operation, "standard", "t", before, current,
        json.dumps({
            "mode": "keyed", "selected_columns": ["id", "note"],
            "effective_key_before": ["id"], "effective_key_current": ["id"],
            "compare_excluded_columns": [], "incompatible_columns": [],
            "emit_add_delete": True, "columns_added": False,
        }),
        "COUNTS_ONLY", 2_000_000, 64 * 1024**2, 1024 * 1024,
        2 * 1024**3, Charge(),
    )
    with closing(handle.record_batches("STANDARD")) as stream:
        row = stream.read_next_batch().to_pylist()[0]
    assert row["before_values"] == []
    assert row["current_values"] == []
    handle.close()
    operation.close()


def test_ordered_and_blank_arrow_and_complete_fact_replay_match_frozen_python() -> None:
    before = _bound("""
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (NULL, 2, 'x'), (2, 3, 'b'), (3, 4, 'c');
    """)
    current = _bound("""
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (3, 2, 'c'), (2, 3, 'b'), (NULL, 4, 'x');
    """)
    plan = _plan(before, current, ordered=True)
    expected = compare_plan(plan)
    assert isinstance(expected, DetailedFactsResult) and expected.facts is not None
    fact = expected.facts.tables[0]
    task = plan.tasks[0]
    assert task.policy is not None and task.policy.ordered_policy is not None
    assert task.before_table is not None and task.current_table is not None
    assert task.before_descriptor is not None and task.current_descriptor is not None
    ordered_policy = task.policy.ordered_policy
    changes = fact.schema_changes
    policy = {
        "table_name": task.table_name,
        "policy_version": ordered_policy.policy_version,
        "policy_digest": None if ordered_policy.policy_digest is None else ordered_policy.policy_digest.value,
        "value_columns": list(ordered_policy.value_columns),
        "digest_value_columns": list(ordered_policy.value_columns),
        "compare_excluded_columns": list(task.policy.compare_excluded_columns),
        "emit_add_delete": task.artifact_scope is ArtifactScope.ALL_CHANGES,
        "schema_changed": fact.status.value == "SCHEMA_ONLY_CHANGED",
        "raw_content_changed": task.before_descriptor.raw_content_digest != task.current_descriptor.raw_content_digest,
        "columns_added": changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED,
        "before_blank_provenance": _blank_provenance(task.before_table),
        "current_blank_provenance": _blank_provenance(task.current_table),
        "schema_changes": {
            "before_only_columns": list(changes.before_only_columns),
            "current_only_columns": list(changes.current_only_columns),
            "selected_columns": list(changes.selected_columns),
            "effective_compare_key_before": list(changes.effective_compare_key_before),
            "effective_compare_key_current": list(changes.effective_compare_key_current),
            "effective_compare_key_changed": changes.effective_compare_key_changed,
            "incompatible_columns": list(changes.incompatible_columns),
            "change_source": None if changes.change_source is None else changes.change_source.value,
        },
    }
    operation = _begin_comparison_operation_native(2 * 1024**3, Charge(), NeverCancel())
    before_stream = _canonical_stream(task.before_table)
    current_stream = _canonical_stream(task.current_table)
    try:
        handle = _compare_records_native(
            operation, "ordered", "t", before_stream, current_stream, json.dumps(policy),
            "FULL_BEFORE_AFTER_VALUES", 2_000_000, 512 * 1024**2,
            512 * 1024**2, 2 * 1024**3, Charge(),
        )
    finally:
        before_stream.close()
        current_stream.close()
    families = (
        ("STANDARD", RecordsArtifactFamily.STANDARD, fact.records),
        ("ORDERED", RecordsArtifactFamily.ORDERED,
         () if fact.ordered_extension is None else fact.ordered_extension.records),
        ("BLANK", RecordsArtifactFamily.BLANK,
         () if fact.blank_extension is None else fact.blank_extension.records),
    )
    old_store = InMemoryArtifactStore()
    old_published = publish_records_closure(expected, old_store)
    assert isinstance(old_published, DetailedFactsResult)
    assert old_published.records_closure is not None
    old_entries = {entry.family: entry for entry in old_published.records_closure.records}
    for name, family, records in families:
        with closing(handle.record_batches(name)) as stream:
            built_batches = tuple(stream)
        rows = [row for batch in built_batches for row in batch.to_pylist()]
        assert rows == [
            _record_to_row(family, record, RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES)
            for record in records
        ]
        if records:
            old_entry = old_entries[family]
            assert handle.family_summary(name) == (
                len(records), old_entry.records_content_digest.value
            )
            assert _write_arrow_parquet(
                built_batches, built_batches[0].schema,
                RecordsPublicationPolicy(), RecordsPublicationContext(),
            ) == old_store.locate(old_entry.records_ref)
    metadata = _table_digest_payload(fact)
    metadata["records"] = []
    for extension in ("ordered_extension", "blank_extension"):
        value = metadata.get(extension)
        if isinstance(value, dict):
            value["records"] = []
    raw = json.dumps(metadata)
    assert fact.table_fact_digest is not None
    assert handle.table_fact_digest(raw, 8 * 1024**2) == fact.table_fact_digest.value
    assert _facts_core_digest_native(
        operation, [handle], [raw], STANDARD_COMPARISON_ALGORITHM_VERSION,
        json.dumps(_summary_payload(expected.facts.summary)), 8 * 1024**2,
    ) == expected.facts.facts_core_digest.value
    handle.close()
    operation.close()


def test_phase_seal_returns_native_scratch_to_same_m_before_writer() -> None:
    mib = 1024**2
    memory = OperationMemoryBudget(128 * mib)
    native_charge = memory.reserve(64 * mib)
    input_charge = memory.reserve(8 * mib)
    bound = _bound("CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); INSERT INTO t VALUES (1, 'x');")
    stream = _canonical_stream(bound.table_set.tables[0])
    schema = stream.schema
    operation = _begin_comparison_operation_native(64 * mib, native_charge, NeverCancel())
    handle = _compare_records_native(
        operation, "standard", "t", pa.RecordBatchReader.from_batches(schema, []), stream,
        json.dumps({
            "mode": "keyed", "selected_columns": ["id", "note"],
            "effective_key_before": ["id"], "effective_key_current": ["id"],
            "compare_excluded_columns": [], "incompatible_columns": [],
            "emit_add_delete": True, "columns_added": False,
        }),
        "FULL_BEFORE_AFTER_VALUES", 2_000_000, 16 * mib, 16 * mib,
        8 * mib, input_charge,
    )
    with closing(handle.record_batches("STANDARD")) as reader:
        batch = reader.read_next_batch()
    handle.close()
    retained = operation.seal()
    assert retained < 64 * mib
    assert memory.used_bytes == retained + 8 * mib
    with memory.reserve(50 * mib):
        assert memory.high_water_bytes <= memory.limit_bytes
    del batch
    import gc
    gc.collect()
    assert memory.used_bytes == retained
    assert operation.reconcile_retained() == 0
    assert memory.used_bytes == 0
    operation.close()


def test_facts_core_accepts_metadata_over_one_mib_with_independent_jcs() -> None:
    summary = {"wide_display_names": ["x" * 600 for _ in range(2048)]}
    raw_summary = json.dumps(summary)
    assert len(raw_summary) > 1024**2
    expected = raw_blob_digest(canonicalize_json_value({
        "algorithm_version": STANDARD_COMPARISON_ALGORITHM_VERSION,
        "kind": "comparison-facts-core", "summary": summary, "tables": [],
    }))
    operation = _begin_comparison_operation_native(64 * 1024**2, Charge(), NeverCancel())
    assert _facts_core_digest_native(
        operation, [], [], STANDARD_COMPARISON_ALGORITHM_VERSION,
        raw_summary, 8 * 1024**2,
    ) == expected.value
    operation.close()
