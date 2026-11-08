"""C Arrow records and facts against fixed pre-C Python contract behavior."""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from collections.abc import Iterator
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_compute._native import (
    _begin_comparison_operation_native,
    _compare_records_native,
    _facts_core_digest_native,
    _validate_records_batches_native,
)

from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore
from gateway_backend.capabilities.comparison.artifacts import (
    NativeRecordsHandle, RecordsPublicationContext, RecordsPublicationError, RecordsPublicationPolicy,
    _canonical_records_batch, _decoded_admission, _schema_matches,
    _standalone_read_bound, _standalone_retained_cap,
    _manifest_from_bytes, _schema_for, _validate_parquet_bytes,
    _write_arrow_parquet, open_records_closure,
    publish_records_family_arrow, read_records_artifact,
    restore_records_closure,
)
from gateway_backend.capabilities.comparison import artifacts as records_artifacts
from gateway_backend.capabilities.comparison.native import validate_records_batches as real_validate
from gateway_backend.capabilities.comparison.contracts import (
    ArtifactScope, DetailedFactsResult, RecordsArtifactFamily, RecordsArtifactManifest,
    RecordsDetailPolicy, SchemaEvolution,
)
from gateway_backend.capabilities.comparison.standard import STANDARD_COMPARISON_ALGORITHM_VERSION
from gateway_backend.capabilities.table_access import NeverCancel
from gateway_backend.capabilities.table_access.kernel import OperationMemoryBudget
from tests.support.comparison_s3_c_inputs import (
    blank_provenance as _blank_provenance,
    bound as _bound,
    canonical_stream as _canonical_stream,
    plan as _plan,
)
from tests.support.records_diagnostic import standalone_records_batches
from tests.support.comparison_s3_e_frozen import frozen_case
from tests.support.comparison_s3_e_live import native_product, publish_product

pytestmark = pytest.mark.unit


def _published_standard(store: InMemoryArtifactStore) -> DetailedFactsResult:
    product = native_product(
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);"
        " INSERT INTO t VALUES (1, 'before');",
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);"
        " INSERT INTO t VALUES (1, NULL);",
    )
    try:
        return publish_product(product, store)
    finally:
        product.close()

FROZEN_RECORDS_PARQUET = (
    (RecordsArtifactFamily.STANDARD, "standard-records/v1", 1,
     "sha256:22bfb26abb0aaeb3d279cdae0614d2733bebbd8cdf8021cfa6751c690db561d4"),
    (RecordsArtifactFamily.ORDERED, "ordered-records/v1", 1,
     "sha256:887e686f96583a28c31f82788608ebd10491b80eb98dc9ab2ada7389ec50468b"),
    (RecordsArtifactFamily.BLANK, "blank-records/v1", 2,
     "sha256:5f7d095129a4fdbeba84392206fa857740ecdca6b466f9cc8177d2264bf9c17a"),
)


class Charge:
    def __init__(self) -> None:
        self.closed = False
        self.retained_bytes: int | None = None

    def shrink_to(self, size: int) -> None:
        self.retained_bytes = size

    def close(self) -> None:
        self.closed = True


class NativeTestOperation(Protocol):
    def seal(self) -> int: ...

    def close(self) -> None: ...


class NativeTestHandle(NativeRecordsHandle, Protocol):
    def metadata_json(self) -> str: ...

    def table_fact_digest(self, metadata_json: str, max_jcs_row_bytes: int) -> str: ...

    def close(self) -> None: ...


_STANDARD_FROZEN_NODEID = (
    "tests/test_comparison_s3_c_arrow.py::"
    "test_native_standard_arrow_and_complete_facts_match_pre_c_source"
)
_ORDERED_FROZEN_NODEID = (
    "tests/test_comparison_s3_c_arrow.py::"
    "test_ordered_and_blank_arrow_and_complete_fact_replay_match_frozen_python"
)


def _captured_row_shape(rows: object) -> Any:
    def bytes_shape(value: object) -> dict[str, str]:
        assert isinstance(value, bytes)
        return {"bytes_hex": value.hex()}

    return cast(Any, json.loads(json.dumps(rows, default=bytes_shape)))


def _native_one() -> tuple[NativeTestOperation, NativeTestHandle, Charge, Charge, dict[str, Any]]:
    before = _bound("CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); INSERT INTO t VALUES (1, 'before');")
    current = _bound("CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); INSERT INTO t VALUES (1, NULL);")
    plan = _plan(before, current)
    expected = frozen_case(_STANDARD_FROZEN_NODEID)
    table = expected["table_payload"]
    task = plan.tasks[0]
    assert task.policy is not None
    assert task.before_table is not None and task.current_table is not None
    policy = {
        "mode": "keyed", "selected_columns": table["schema_changes"]["selected"],
        "effective_key_before": list(task.policy.effective_key_before),
        "effective_key_current": list(task.policy.effective_key_current),
        "compare_excluded_columns": [], "incompatible_columns": [],
        "emit_add_delete": True, "columns_added": False,
    }
    operation_charge = Charge()
    input_charge = Charge()
    operation = cast(NativeTestOperation, _begin_comparison_operation_native(
        2 * 1024**3, operation_charge, NeverCancel(),
    ))
    before_stream = _canonical_stream(task.before_table)
    current_stream = _canonical_stream(task.current_table)
    try:
        handle = cast(NativeTestHandle, _compare_records_native(
            operation, "standard", "t", before_stream, current_stream, json.dumps(policy),
            "FULL_BEFORE_AFTER_VALUES", 2_000_000, 512 * 1024**2, 512 * 1024**2,
            2 * 1024**3,
            input_charge,
        ))
    finally:
        before_stream.close()
        current_stream.close()
    return operation, handle, operation_charge, input_charge, expected


def test_native_standard_arrow_and_complete_facts_match_pre_c_source() -> None:
    operation, handle, operation_charge, input_charge, expected = _native_one()
    reader = handle.record_batches("STANDARD")
    try:
        built_batches = tuple(reader)
        rows = [row for batch in built_batches for row in batch.to_pylist()]
    finally:
        reader.close()
    assert _captured_row_shape(rows) == expected["record_rows"]["STANDARD"]
    old_entry = expected["records"][0]
    assert handle.family_summary("STANDARD") == (
        1, old_entry["content_digest"],
    )
    new_raw = _write_arrow_parquet(
        built_batches,
        _schema_for(RecordsArtifactFamily.STANDARD, None,
                    RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES),
        RecordsPublicationPolicy(), RecordsPublicationContext(),
    )
    assert hashlib.sha256(new_raw).hexdigest() == old_entry["raw_sha256"]
    metadata = deepcopy(expected["table_payload"])
    metadata["records"] = []
    raw = json.dumps(metadata)
    assert handle.table_fact_digest(raw, 8 * 1024**2) == expected["tables"][0]["table_fact_digest"]
    assert _facts_core_digest_native(
        operation, [handle], [raw], STANDARD_COMPARISON_ALGORITHM_VERSION,
        json.dumps(expected["summary_payload"]), 8 * 1024**2,
    ) == expected["facts_core_digest"]
    handle.close()
    operation.close()
    # The exported batch buffers still own both charges after their source
    # handle and reader are closed.
    assert not input_charge.closed and not operation_charge.closed
    del built_batches
    import gc
    gc.collect()
    assert input_charge.closed and operation_charge.closed


def test_exported_arrow_buffers_keep_charge_after_handle_and_reader_close() -> None:
    operation, handle, operation_charge, input_charge, _ = _native_one()
    reader = handle.record_batches("STANDARD")
    batch = reader.read_next_batch()
    table = pa.Table.from_batches([batch])
    retained = operation.seal()
    assert operation_charge.retained_bytes == retained
    assert retained > batch.nbytes
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
    schema = _schema_for(
        RecordsArtifactFamily(family.upper()), None,
        RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES,
    )
    with closing(pq.ParquetFile(pa.BufferReader(raw))) as source:
        batches = tuple(
            _canonical_records_batch(batch, schema)
            for batch in source.iter_batches(batch_size=1024)
        )
    assert batches
    rebuilt = _write_arrow_parquet(
        batches, schema, RecordsPublicationPolicy(), RecordsPublicationContext()
    )
    assert rebuilt == raw
    with closing(pa.RecordBatchReader.from_batches(schema, batches)) as reader:
        result = _validate_records_batches_native(
            reader, 2_000_000, 2 * 1024**3, NeverCancel()
        )
    assert result[3] == sum(batch.num_rows for batch in batches)


@pytest.mark.parametrize(("family", "version", "count", "content_digest"), FROZEN_RECORDS_PARQUET)
def test_frozen_python_parquet_vectors_use_real_native_reader(
    family: RecordsArtifactFamily, version: str, count: int, content_digest: str,
) -> None:
    # The same three fixed vectors and independent expected digests formerly
    # exercised the superseded direct Rust Parquet reader.
    path = Path(__file__).resolve().parents[2] / (
        f"fixtures/vectors/comparison/records/{family.value.lower()}-v1.parquet.b64"
    )
    raw = base64.b64decode(path.read_text(encoding="ascii"))
    digest = DigestRef(content_digest)
    manifest = RecordsArtifactManifest(
        table_name="t", family=family, record_format="PARQUET",
        schema_version=version,
        row_diff_detail_policy=RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES,
        record_count=count, content_digest=digest,
    )
    assert _validate_parquet_bytes(raw, manifest, RecordsPublicationPolicy()) == (count, digest)


@pytest.mark.parametrize("shape", ("list_child", "nullable_field", "metadata"))
def test_actual_records_reader_rejects_noncanonical_parquet_shape(shape: str) -> None:
    family, version, count, digest_text = FROZEN_RECORDS_PARQUET[0]
    path = Path(__file__).resolve().parents[2] / (
        "fixtures/vectors/comparison/records/standard-v1.parquet.b64"
    )
    source_raw = base64.b64decode(path.read_text(encoding="ascii"))
    with closing(pq.ParquetFile(pa.BufferReader(source_raw))) as source:
        schema = source.schema_arrow
        batch = next(source.iter_batches(batch_size=1024))
    fields = list(schema)
    if shape == "list_child":
        fields[3] = pa.field(
            "changed_columns", pa.list_(pa.field("rogue", pa.string())), nullable=False
        )
    elif shape == "nullable_field":
        fields[0] = pa.field("table_name", pa.string(), nullable=True)
    metadata = dict(schema.metadata or {})
    if shape == "metadata":
        metadata[b"gateway-vnext.records.family"] = b"UNSUPPORTED"
    malformed = pa.schema(fields, metadata=metadata)
    assert not _schema_matches(
        malformed,
        _schema_for(family, version, RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES),
        parquet_lists=True,
    )
    malformed_batch = pa.RecordBatch.from_arrays(batch.columns, schema=malformed)
    with pytest.raises(RecordsPublicationError, match="batch schema mismatch"):
        _canonical_records_batch(
            malformed_batch,
            _schema_for(family, version, RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES),
        )
    if shape != "list_child":
        sink = pa.BufferOutputStream()
        pq.write_table(
            pa.Table.from_batches([malformed_batch], schema=malformed), sink,
            compression="zstd", use_dictionary=False, row_group_size=1,
        )
        manifest = RecordsArtifactManifest(
            table_name="t", family=family, record_format="PARQUET",
            schema_version=version,
            row_diff_detail_policy=RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES,
            record_count=count, content_digest=DigestRef(digest_text),
        )
        with pytest.raises(RecordsPublicationError, match="schema mismatch"):
            _validate_parquet_bytes(sink.getvalue().to_pybytes(), manifest, RecordsPublicationPolicy())


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
    assert bound.table_set is not None
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
    published = _published_standard(source_store)
    assert isinstance(published, DetailedFactsResult)
    assert published.facts is not None and published.facts.records_ref is not None
    calls = 0

    def checked_validate(*args: object, **kwargs: object) -> tuple[str, str, str, int, str]:
        nonlocal calls
        calls += 1
        return real_validate(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(records_artifacts, "validate_records_batches", checked_validate)
    closure = open_records_closure(source_store, published.facts.records_ref)
    with pytest.raises(RecordsPublicationError, match="diagnostic records reader cannot escape"):
        read_records_artifact(source_store, closure.records[0])
    first = standalone_records_batches(source_store, closure.records[0])[0]
    assert first.schema.equals(
        _schema_for(
            RecordsArtifactFamily.STANDARD, None,
            RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES,
        ),
        check_metadata=True,
    )
    assert first.to_pylist()[0]["record_kind"] == "ROW_MODIFIED"
    restored = restore_records_closure(
        source_store, InMemoryArtifactStore(), published.facts.records_ref
    )
    assert restored.closure.comparison_digest == closure.comparison_digest
    assert calls >= 4  # open, diagnostic read, restore source, restore destination


def test_standalone_reader_budget_is_m24_not_a_total_i32_limit() -> None:
    gib = 1024**3
    assert _standalone_retained_cap(512 * 1024**2, gib) > 2 * gib
    _standalone_read_bound(1024**2, 10 * gib)
    with pytest.raises(ValueError, match="standalone memory budget"):
        _standalone_retained_cap(512 * 1024**2, 12 * gib)


def test_plain_400_mib_cell_is_admitted_before_decode() -> None:
    class Column:
        encodings = ("PLAIN", "RLE")
        num_values = 1

    class Group:
        num_rows = 1
        num_columns = 1
        total_byte_size = 400 * 1024**2

        def column(self, _index: int) -> Column:
            return Column()

    class Metadata:
        num_row_groups = 1

        def row_group(self, _index: int) -> Group:
            return Group()

    class File:
        metadata = Metadata()

    admission = _decoded_admission(
        cast(pq.ParquetFile, File()), RecordsPublicationPolicy()
    )
    _standalone_read_bound(1024**2, admission)
    assert admission < 12 * 1024**3


def test_sparse_nested_nullable_list_slots_are_charged_before_parquet_decode() -> None:
    # Parquet definition levels compress these null elements, while Arrow must
    # still allocate the nested child array and the validator visits each slot.
    schema = _schema_for(
        RecordsArtifactFamily.STANDARD, detail_policy=RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES
    )
    row = {
        "table_name": "t", "record_kind": "ROW_MODIFIED", "row_identity": bytes(32),
        "changed_columns": [],
        "before_values": [{"column_name": "x", "value": {
            "kind": "set", "text": None, "raw_bytes": None, "boolean": None,
            "items": [None] * 100_000, "anomaly_json": None,
        }}],
        "current_values": [], "field_changes": [], "diagnostics": [],
    }
    batch = pa.RecordBatch.from_pylist([row], schema=schema)
    sink = pa.BufferOutputStream()
    pq.write_table(
        pa.Table.from_batches([batch], schema=schema), sink,
        compression="zstd", use_dictionary=False, row_group_size=1,
    )
    with closing(pq.ParquetFile(pa.BufferReader(sink.getvalue()))) as file:
        metadata = file.metadata
        assert metadata is not None
        group = metadata.row_group(0)
        assert group.num_rows == 1
        assert group.total_byte_size < 1024 * 1024
        assert max(group.column(index).num_values for index in range(group.num_columns)) >= 100_000
        with pytest.raises(ValueError, match="decoded batch budget"):
            _decoded_admission(file, RecordsPublicationPolicy(max_decoded_batch_bytes=32 * 1024**2))
        admitted = _decoded_admission(file, RecordsPublicationPolicy())
        assert admitted >= 100_000 * 512
        decoded = next(file.iter_batches(batch_size=1024, row_groups=[0]))
        assert decoded.nbytes < admitted


def test_counts_only_output_budget_excludes_full_sort_blob() -> None:
    bound = _bound("CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL);")
    assert bound.table_set is not None
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


@pytest.mark.parametrize("detail_policy", ("COUNTS_ONLY", "FULL_BEFORE_AFTER_VALUES"))
def test_records_sort_cap_scales_without_changing_projected_rows(detail_policy: str) -> None:
    mib = 1024**2
    bound = _bound("CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL);")
    assert bound.table_set is not None
    with closing(_canonical_stream(bound.table_set.tables[0])) as schema_reader:
        schema = schema_reader.schema
    note = "x" * (128 * 1024)
    current_batch = pa.RecordBatch.from_arrays(
        [pa.array([1], type=schema.field("id").type),
         pa.array([note], type=schema.field("note").type)],
        schema=schema,
    )
    policy = json.dumps({
        "mode": "keyed", "selected_columns": ["id", "note"],
        "effective_key_before": ["id"], "effective_key_current": ["id"],
        "compare_excluded_columns": [], "incompatible_columns": [],
        "emit_add_delete": True, "columns_added": False,
    })

    def compare(sort_cap: int) -> tuple[dict[str, Any] | None, int]:
        memory = OperationMemoryBudget(64 * mib)
        native_charge = memory.reserve(48 * mib)
        input_charge = memory.reserve(mib)
        operation = _begin_comparison_operation_native(48 * mib, native_charge, NeverCancel())
        before = pa.RecordBatchReader.from_batches(schema, [])
        current = pa.RecordBatchReader.from_batches(schema, [current_batch])
        handle: NativeTestHandle | None = None
        row: dict[str, Any] | None = None
        try:
            handle = cast(NativeTestHandle, _compare_records_native(
                operation, "standard", "t", before, current, policy,
                detail_policy, 2_000_000, sort_cap, 4 * mib, 8 * mib, input_charge,
            ))
            with closing(handle.record_batches("STANDARD")) as stream:
                row = cast(dict[str, Any], stream.read_next_batch().to_pylist()[0])
        finally:
            if handle is not None:
                handle.close()
            before.close()
            current.close()
            operation.close()
            import gc
            gc.collect()
            assert memory.used_bytes == 0
        return row, memory.high_water_bytes

    with pytest.raises(MemoryError, match="records sort budget exceeded"):
        compare(256 * 1024)
    row, peak = compare(16 * mib)
    assert peak <= 64 * mib
    assert row is not None and row["record_kind"] == "ROW_ADDED"
    assert row["table_name"] == "t"
    if detail_policy == "COUNTS_ONLY":
        assert row["current_values"] == []
        assert row["changed_columns"] == []
    else:
        assert {item["column_name"] for item in row["current_values"]} == {"id", "note"}


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
    expected = frozen_case(_ORDERED_FROZEN_NODEID)
    fact = expected["table_payload"]
    task = plan.tasks[0]
    assert task.policy is not None and task.policy.ordered_policy is not None
    assert task.before_table is not None and task.current_table is not None
    assert task.before_descriptor is not None and task.current_descriptor is not None
    ordered_policy = task.policy.ordered_policy
    changes = fact["schema_changes"]
    policy = {
        "table_name": task.table_name,
        "policy_version": ordered_policy.policy_version,
        "policy_digest": None if ordered_policy.policy_digest is None else ordered_policy.policy_digest.value,
        "value_columns": list(ordered_policy.value_columns),
        "digest_value_columns": list(ordered_policy.value_columns),
        "compare_excluded_columns": list(task.policy.compare_excluded_columns),
        "emit_add_delete": task.artifact_scope is ArtifactScope.ALL_CHANGES,
        "schema_changed": fact["status"] == "SCHEMA_ONLY_CHANGED",
        "raw_content_changed": task.before_descriptor.raw_content_digest != task.current_descriptor.raw_content_digest,
        "columns_added": changes["schema_evolution"] == SchemaEvolution.COLUMNS_ADDED.value,
        "before_blank_provenance": _blank_provenance(task.before_table),
        "current_blank_provenance": _blank_provenance(task.current_table),
        "schema_changes": {
            "before_only_columns": changes["before_only"],
            "current_only_columns": changes["current_only"],
            "selected_columns": changes["selected"],
            "effective_compare_key_before": changes["key_before"],
            "effective_compare_key_current": changes["key_current"],
            "effective_compare_key_changed": changes["key_changed"],
            "incompatible_columns": changes["incompatible"],
            "change_source": changes["change_source"],
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
    old_entries = {entry["family"]: entry for entry in expected["records"]}
    for name, family in (
        ("STANDARD", RecordsArtifactFamily.STANDARD),
        ("ORDERED", RecordsArtifactFamily.ORDERED),
        ("BLANK", RecordsArtifactFamily.BLANK),
    ):
        with closing(handle.record_batches(name)) as stream:
            built_batches = tuple(stream)
        rows = [row for batch in built_batches for row in batch.to_pylist()]
        assert _captured_row_shape(rows) == expected["record_rows"][name]
        if name in old_entries:
            old_entry = old_entries[name]
            assert handle.family_summary(name) == (
                old_entry["record_count"], old_entry["content_digest"],
            )
            raw_parquet = _write_arrow_parquet(
                built_batches,
                _schema_for(family, None, RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES),
                RecordsPublicationPolicy(), RecordsPublicationContext(),
            )
            assert hashlib.sha256(raw_parquet).hexdigest() == old_entry["raw_sha256"]
    metadata = deepcopy(expected["table_payload"])
    metadata["records"] = []
    for extension in ("ordered_extension", "blank_extension"):
        value = metadata.get(extension)
        if isinstance(value, dict):
            value["records"] = []
    raw = json.dumps(metadata)
    assert handle.table_fact_digest(raw, 8 * 1024**2) == expected["tables"][0]["table_fact_digest"]
    assert _facts_core_digest_native(
        operation, [handle], [raw], STANDARD_COMPARISON_ALGORITHM_VERSION,
        json.dumps(expected["summary_payload"]), 8 * 1024**2,
    ) == expected["facts_core_digest"]
    handle.close()
    operation.close()


def test_phase_seal_returns_native_scratch_to_same_m_before_writer() -> None:
    mib = 1024**2
    memory = OperationMemoryBudget(128 * mib)
    native_charge = memory.reserve(64 * mib)
    input_charge = memory.reserve(8 * mib)
    bound = _bound("CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); INSERT INTO t VALUES (1, 'x');")
    assert bound.table_set is not None
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


@pytest.mark.parametrize("limited", ("input", "output"))
def test_native_budget_failure_releases_input_and_phase_charges(limited: str) -> None:
    mib = 1024**2
    memory = OperationMemoryBudget(128 * mib)
    native_charge = memory.reserve(64 * mib)
    input_charge = memory.reserve(8 * mib)
    bound = _bound("CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); INSERT INTO t VALUES (1, 'x');")
    assert bound.table_set is not None
    current = _canonical_stream(bound.table_set.tables[0])
    schema = current.schema
    operation = _begin_comparison_operation_native(64 * mib, native_charge, NeverCancel())
    try:
        with pytest.raises(MemoryError, match="RESOURCE_LIMIT_EXCEEDED|budget"):
            _compare_records_native(
                operation, "standard", "t", pa.RecordBatchReader.from_batches(schema, []),
                current,
                json.dumps({
                    "mode": "keyed", "selected_columns": ["id", "note"],
                    "effective_key_before": ["id"], "effective_key_current": ["id"],
                    "compare_excluded_columns": [], "incompatible_columns": [],
                    "emit_add_delete": True, "columns_added": False,
                }),
                "FULL_BEFORE_AFTER_VALUES", 2_000_000, 16 * mib,
                1 if limited == "output" else 16 * mib,
                1 if limited == "input" else 8 * mib, input_charge,
            )
    finally:
        current.close()
        operation.close()
    assert memory.used_bytes == 0
    assert memory.high_water_bytes <= memory.limit_bytes


@pytest.mark.parametrize("control", ("cancel", "deadline"))
def test_native_operation_rejects_cancel_or_expired_deadline_and_releases(control: str) -> None:
    memory = OperationMemoryBudget(64 * 1024**2)
    charge = memory.reserve(64 * 1024**2)

    class Probe:
        def is_set(self) -> bool:
            return control == "cancel"

    with pytest.raises((InterruptedError, TimeoutError)):
        _begin_comparison_operation_native(
            64 * 1024**2, charge, Probe(),
            time.monotonic() - 1 if control == "deadline" else None,
        )
    assert memory.used_bytes == 0


@pytest.mark.serial
def test_native_arrow_read_releases_gil_for_cancel_monitor() -> None:
    bound = _bound("CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL);")
    assert bound.table_set is not None
    schema_reader = _canonical_stream(bound.table_set.tables[0])
    schema = schema_reader.schema
    schema_reader.close()
    count = 100_000
    whole = pa.RecordBatch.from_arrays(
        [pa.array(range(1, count + 1), type=schema.field("id").type),
         pa.array(["x"] * count, type=schema.field("note").type)],
        schema=schema,
    )
    batches = [whole.slice(offset, min(1024, count - offset)) for offset in range(0, count, 1024)]

    entered_native_read = threading.Event()
    python_progressed = threading.Event()
    cancelled = threading.Event()

    def lazy_batches() -> Iterator[pa.RecordBatch]:
        for index, batch in enumerate(batches):
            if index == 0:
                entered_native_read.set()
            yield batch

    def cancel_after_actual_read() -> None:
        if entered_native_read.wait(timeout=5):
            python_progressed.set()
            cancelled.set()

    operation = _begin_comparison_operation_native(2 * 1024**3, Charge(), cancelled)
    before = pa.RecordBatchReader.from_batches(schema, [])
    current = pa.RecordBatchReader.from_batches(schema, lazy_batches())
    assert not entered_native_read.is_set()
    watcher = threading.Thread(target=cancel_after_actual_read)
    watcher.start()
    try:
        with pytest.raises(InterruptedError, match="COMPARISON_CANCELLED"):
            _compare_records_native(
                operation, "standard", "t", before, current,
                json.dumps({
                    "mode": "keyed", "selected_columns": ["id", "note"],
                    "effective_key_before": ["id"], "effective_key_current": ["id"],
                    "compare_excluded_columns": [], "incompatible_columns": [],
                    "emit_add_delete": True, "columns_added": False,
                }),
                "COUNTS_ONLY", 2_000_000, 512 * 1024**2,
                512 * 1024**2, 2 * 1024**3, Charge(),
            )
        assert entered_native_read.is_set()
        assert python_progressed.is_set()
    finally:
        cancelled.set()
        watcher.join(timeout=5)
        assert not watcher.is_alive()
        before.close()
        current.close()
        operation.close()


def test_real_native_read_rejects_correct_raw_with_wrong_content_or_schema() -> None:
    store = InMemoryArtifactStore()
    published = _published_standard(store)
    assert isinstance(published, DetailedFactsResult)
    assert published.records_closure is not None
    entry = published.records_closure.records[0]
    raw = store.locate(entry.records_ref)
    manifest = _manifest_from_bytes(store.locate(entry.records_manifest_ref))
    with pytest.raises(records_artifacts.RecordsPublicationError, match="Parquet is corrupt"):
        _validate_parquet_bytes(b"", manifest, RecordsPublicationPolicy())
    with pytest.raises(ValueError, match="content digest mismatch"):
        _validate_parquet_bytes(
            raw, replace(manifest, content_digest=raw_blob_digest(b"other")),
            RecordsPublicationPolicy(),
        )
    with pytest.raises(ValueError, match="schema mismatch"):
        _validate_parquet_bytes(
            raw, replace(
                manifest, family=RecordsArtifactFamily.ORDERED,
                schema_version="ordered-records/v1",
            ), RecordsPublicationPolicy(),
        )

    class FailingReadStore:
        def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
            return store.put(raw_bytes, ref)

        def locate(self, ref: ArtifactRef) -> bytes:
            if ref == entry.records_ref:
                raise OSError("read failed")
            return store.locate(ref)

    assert published.facts is not None and published.facts.records_ref is not None
    with pytest.raises(ValueError, match="locate failed"):
        open_records_closure(FailingReadStore(), published.facts.records_ref)
