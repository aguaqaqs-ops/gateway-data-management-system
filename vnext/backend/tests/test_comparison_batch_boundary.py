"""S1 Arrow batch boundary and provider-port contract tests."""

from __future__ import annotations

import pyarrow as pa

from gateway_backend.capabilities.comparison import (
    ComparisonBatchRequest,
    PythonReferenceBatchProvider,
    RustArrowBatchProvider,
)
from gateway_backend.capabilities.snapshot_materialization.artifact import (
    open_snapshot_table_artifact,
    publish_snapshot_table_artifact,
)
from gateway_backend.capabilities.snapshot_materialization.batch import (
    BatchBoundaryError,
    batch_metadata_from_schema,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    SnapshotTable,
)
from gateway_backend.capabilities.table_access.contracts import NeverCancel, ParserInvocationContext
from tests.support.snapshot_artifact import first_ready_table
from tests.support.snapshot_materialization import materialize_sql, parse_fixture
from gateway_backend.artifacts import InMemoryArtifactStore


def _opened_table() -> SnapshotTable:
    store = InMemoryArtifactStore()
    source = first_ready_table("sql/valid/s2-null-and-types/input.sql")
    result = materialize_sql(
        parse_fixture("sql/valid/s2-null-and-types/input.sql"),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    assert result.snapshot is not None
    artifact = publish_snapshot_table_artifact(
        source,
        snapshot_digest=result.snapshot.snapshot_digest,
        store=store,
        context=ParserInvocationContext(NeverCancel()),
    )
    opened = open_snapshot_table_artifact(store, artifact.manifest_ref)
    assert opened.batch_reader is not None
    return opened


def test_parquet_batch_reader_preserves_metadata_and_reopens_without_rows() -> None:
    table = _opened_table()
    reader = table.batch_reader
    assert reader is not None
    assert reader.metadata().scalar_encoding_version == table.descriptor.scalar_encoding_version
    assert batch_metadata_from_schema(reader.schema()) == reader.metadata()

    batches = tuple(reader.iter_record_batches())
    assert sum(batch.num_rows for batch in batches) == table.descriptor.row_count
    assert all(batch.schema.equals(reader.schema(), check_metadata=False) for batch in batches)

    reopened = reader.reopen()
    assert sum(batch.num_rows for batch in reopened.iter_record_batches()) == table.descriptor.row_count
    reopened.close()
    reader.close()


def test_missing_batch_metadata_fails_closed() -> None:
    with_schema = pa.schema([pa.field("v", pa.int32())])
    try:
        batch_metadata_from_schema(with_schema)
    except BatchBoundaryError as exc:
        assert "batch metadata" in str(exc)
    else:
        raise AssertionError("schema without S1 metadata must fail closed")


def test_python_reference_provider_preserves_arrow_batches() -> None:
    table = _opened_table()
    reader = table.batch_reader
    assert reader is not None
    request = ComparisonBatchRequest(
        table_name=table.descriptor.table_name,
        descriptor=table.descriptor,
        reader=reader,
    )
    result = PythonReferenceBatchProvider().execute(request)
    assert result.provider_id == "python-reference-batch-v1"
    assert result.input_metadata == reader.metadata()
    output = tuple(result.output_stream)
    assert sum(batch.num_rows for batch in output) == table.descriptor.row_count


def test_rust_provider_port_is_coarse_grained_and_injected() -> None:
    table = _opened_table()
    reader = table.batch_reader
    assert reader is not None
    observed: list[int] = []

    def fake_native(
        request_jcs: bytes, stream: pa.RecordBatchReader
    ) -> tuple[pa.RecordBatchReader, bytes]:
        assert request_jcs == b"request"
        batches = tuple(stream)
        observed.append(sum(batch.num_rows for batch in batches))
        return pa.RecordBatchReader.from_batches(stream.schema, batches), b"native-result"

    request = ComparisonBatchRequest(
        table_name=table.descriptor.table_name,
        descriptor=table.descriptor,
        reader=reader,
        request_jcs=b"request",
    )
    result = RustArrowBatchProvider(fake_native).execute(request)
    assert result.provider_id == "rust-arrow-batch-v1"
    assert result.result_jcs == b"native-result"
    assert observed == [table.descriptor.row_count]
    assert sum(batch.num_rows for batch in result.output_stream) == table.descriptor.row_count
