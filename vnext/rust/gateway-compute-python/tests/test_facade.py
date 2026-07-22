"""Parity and facade tests for canonical_row_hashes_v1."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pyarrow as pa
import pytest

from gateway_compute import (
    CanonicalValueError,
    ComputeRequestError,
    _as_record_batch_reader,
    canonical_row_hashes_v1,
)

from test_component_support import assert_failure_envelope, empty_reader

OUTPUT_ROW_HASH_SCHEMA = pa.schema(
    [pa.field("row_hash", pa.binary(32), nullable=False)]
)

BOOLEAN_THREE_ROW_RESULT_JCS = (
    b'{"arrow_mapping_schema_version":1,"canonical_encoding_version":1,'
    b'"contract_binding":{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary",'
    b'"semantic_version":"1.0.0"},"diagnostics":[],"raw_content_digest":'
    b'"sha256:07075d8a72807e5c72006cadcf156c84d9e522be83a7e952970d7c405c268c12",'
    b'"result_schema_version":1,"row_count":"3",'
    b'"table_schema_digest":"sha256:d942ff735528a8ec4297b476074e1c2e3fd2289518242b4f96c99a421b02f7d8"}'
)

BOOLEAN_THREE_ROW_HASHES = [
    bytes.fromhex("250d63ec676e9cf17d4b4e91337e781284be60b1aa59d9fc5c37584d85ce71f5"),
    bytes.fromhex("3180b10d6d203c7fbe989745616bc3d2ff5e17e338453acc4983bb0ecf181c0e"),
    bytes.fromhex("a844c9819cb4da2c2d2119ecd9eebe5137d7af12d4e85b5f7366b52dded90542"),
]


def minimal_request_jcs(fields_json: str) -> bytes:
    payload = {
        "request_schema_version": 1,
        "contract_binding": {
            "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
            "semantic_version": "1.0.0",
        },
        "canonical_encoding_version": 1,
        "arrow_mapping_schema_version": 1,
        "declared_table_schema": {"fields": json.loads(fields_json)},
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def read_row_hashes(reader: pa.RecordBatchReader) -> list[bytes]:
    table = reader.read_all()
    column = table.column(0)
    return [column[i].as_py() for i in range(table.num_rows)]


def assert_output_schema(reader: pa.RecordBatchReader) -> None:
    assert reader.schema == OUTPUT_ROW_HASH_SCHEMA


def test_empty_table_succeeds() -> None:
    request_jcs = minimal_request_jcs("[]")
    reader = pa.RecordBatchReader.from_batches(pa.schema([]), [])
    output, result_jcs = canonical_row_hashes_v1(request_jcs, reader)
    assert_output_schema(output)
    assert b'"row_count":"0"' in result_jcs
    assert read_row_hashes(output) == []
    json.loads(result_jcs.decode())


def test_one_row_boolean_succeeds() -> None:
    fields = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    request_jcs = minimal_request_jcs(fields)
    batch = pa.record_batch([pa.array([True, None, False])], names=["flag"])
    output, result_jcs = canonical_row_hashes_v1(request_jcs, batch)
    assert_output_schema(output)
    assert read_row_hashes(output) == BOOLEAN_THREE_ROW_HASHES
    assert result_jcs == BOOLEAN_THREE_ROW_RESULT_JCS
    json.loads(result_jcs.decode())


def test_multi_batch_matches_single_batch() -> None:
    fields = '[{"name":"v","nullable":false,"semantic_type":{"kind":"boolean"}}]'
    request_jcs = minimal_request_jcs(fields)
    schema = pa.schema([pa.field("v", pa.bool_(), nullable=False)])
    single = pa.record_batch([pa.array([True, False], type=pa.bool_())], schema=schema)
    split = pa.RecordBatchReader.from_batches(
        schema,
        [
            pa.record_batch([pa.array([True], type=pa.bool_())], schema=schema),
            pa.record_batch([pa.array([False], type=pa.bool_())], schema=schema),
        ],
    )
    single_output, single_jcs = canonical_row_hashes_v1(request_jcs, single)
    split_output, split_jcs = canonical_row_hashes_v1(request_jcs, split)
    assert_output_schema(single_output)
    assert_output_schema(split_output)
    assert single_jcs == split_jcs


def test_multi_chunk_table_matches_single_batch() -> None:
    fields = '[{"name":"v","nullable":false,"semantic_type":{"kind":"boolean"}}]'
    request_jcs = minimal_request_jcs(fields)
    schema = pa.schema([pa.field("v", pa.bool_(), nullable=False)])
    single = pa.record_batch([pa.array([True, False], type=pa.bool_())], schema=schema)
    chunked_table = pa.Table.from_batches(
        [
            pa.record_batch([pa.array([True], type=pa.bool_())], schema=schema),
            pa.record_batch([pa.array([False], type=pa.bool_())], schema=schema),
        ]
    )
    assert len(chunked_table.to_batches()) == 2
    _, single_jcs = canonical_row_hashes_v1(request_jcs, single)
    table_output, table_jcs = canonical_row_hashes_v1(request_jcs, chunked_table)
    assert_output_schema(table_output)
    assert single_jcs == table_jcs


@pytest.mark.parametrize(
    "data",
    [
        pa.record_batch([pa.array([True])], names=["flag"]),
        pa.Table.from_batches(
            [pa.record_batch([pa.array([True])], names=["flag"])],
        ),
        pa.RecordBatchReader.from_batches(
            pa.schema([pa.field("flag", pa.bool_(), nullable=True)]),
            [pa.record_batch([pa.array([True])], names=["flag"])],
        ),
    ],
)
def test_facade_input_shapes_are_equivalent(
    data: pa.RecordBatch | pa.Table | pa.RecordBatchReader,
) -> None:
    fields = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    request_jcs = minimal_request_jcs(fields)
    output, result_jcs = canonical_row_hashes_v1(request_jcs, data)
    assert_output_schema(output)
    assert _as_record_batch_reader(data).schema == pa.schema(
        [pa.field("flag", pa.bool_(), nullable=True)]
    )
    assert b'"row_count":"1"' in result_jcs


def test_invalid_request_jcs_raises_compute_request_error() -> None:
    with pytest.raises(ComputeRequestError) as exc_info:
        canonical_row_hashes_v1(b"{not-json", empty_reader())
    assert_failure_envelope(
        exc_info.value,
        expected_type=ComputeRequestError,
        expected_code="COMPUTE_REQUEST_SCHEMA_INVALID",
    )


def test_schema_mismatch_raises_compute_request_error() -> None:
    fields = '[{"name":"v","nullable":false,"semantic_type":{"kind":"boolean"}}]'
    request_jcs = minimal_request_jcs(fields)
    batch = pa.record_batch([pa.array([1], type=pa.int8())], names=["v"])
    with pytest.raises(ComputeRequestError) as exc_info:
        canonical_row_hashes_v1(request_jcs, batch)
    assert_failure_envelope(
        exc_info.value,
        expected_type=ComputeRequestError,
        expected_code="ARROW_SCHEMA_MISMATCH",
    )


def test_nan_float_raises_canonical_value_error() -> None:
    fields = '[{"name":"v","nullable":false,"semantic_type":{"kind":"float64"}}]'
    request_jcs = minimal_request_jcs(fields)
    schema = pa.schema([pa.field("v", pa.float64(), nullable=False)])
    batch = pa.record_batch([pa.array([float("nan")], type=pa.float64())], schema=schema)
    with pytest.raises(CanonicalValueError) as exc_info:
        canonical_row_hashes_v1(request_jcs, batch)
    assert_failure_envelope(
        exc_info.value,
        expected_type=CanonicalValueError,
        expected_code="CANONICAL_VALUE_INVALID",
    )


def test_large_utf8_raises_compute_request_error() -> None:
    fields = '[{"name":"s","nullable":false,"semantic_type":{"kind":"string"}}]'
    request_jcs = minimal_request_jcs(fields)
    array = pa.array(["hello"], type=pa.large_utf8())
    batch = pa.record_batch([array], names=["s"])
    with pytest.raises(ComputeRequestError) as exc_info:
        canonical_row_hashes_v1(request_jcs, batch)
    assert_failure_envelope(
        exc_info.value,
        expected_type=ComputeRequestError,
        expected_code="ARROW_TYPE_UNSUPPORTED",
    )


def test_invalid_input_raises_type_error() -> None:
    with pytest.raises(TypeError):
        _as_record_batch_reader([1, 2, 3])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "request_jcs",
    [
        bytearray(minimal_request_jcs("[]")),
        memoryview(minimal_request_jcs("[]")),
        minimal_request_jcs("[]").decode(),
    ],
)
def test_non_bytes_request_jcs_raises_type_error(request_jcs: object) -> None:
    reader = pa.RecordBatchReader.from_batches(pa.schema([]), [])
    with pytest.raises(TypeError, match="request_jcs must be bytes"):
        canonical_row_hashes_v1(request_jcs, reader)  # type: ignore[arg-type]


def test_request_jcs_annotation_is_bytes() -> None:
    from typing import get_type_hints

    hints = get_type_hints(canonical_row_hashes_v1)
    assert hints["request_jcs"] is bytes


def test_generator_input_raises_type_error() -> None:
    fields = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    request_jcs = minimal_request_jcs(fields)
    batch = pa.record_batch([pa.array([True])], names=["flag"])

    def producer() -> Any:
        yield batch

    with pytest.raises(TypeError):
        canonical_row_hashes_v1(request_jcs, producer())  # type: ignore[arg-type]


def test_facade_invokes_native_once_per_table() -> None:
    fields = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    request_jcs = minimal_request_jcs(fields)
    batch = pa.record_batch([pa.array([True])], names=["flag"])
    with patch(
        "gateway_compute._canonical_row_hashes_v1_native",
        wraps=__import__("gateway_compute")._canonical_row_hashes_v1_native,
    ) as native:
        canonical_row_hashes_v1(request_jcs, batch)
        assert native.call_count == 1


def test_serial_execution_is_byte_identical() -> None:
    fields = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    request_jcs = minimal_request_jcs(fields)
    batch = pa.record_batch([pa.array([True])], names=["flag"])
    first_output, first = canonical_row_hashes_v1(request_jcs, batch)
    second_output, second = canonical_row_hashes_v1(request_jcs, batch)
    assert first == second
    assert read_row_hashes(first_output) == read_row_hashes(second_output)
