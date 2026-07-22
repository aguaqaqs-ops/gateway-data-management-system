"""Facade-path stream determinism probes (R1 §6.3)."""

from __future__ import annotations

import pyarrow as pa

from gateway_compute import canonical_row_hashes_v1

from test_component_support import (
    OUTPUT_ROW_HASH_SCHEMA,
    assert_row_hashes_sorted_unsigned_lexicographic,
    minimal_request_jcs,
    parse_result_jcs,
    row_hash_column_bytes,
)


def test_duplicate_row_hashes_are_retained() -> None:
    fields = '[{"name":"v","nullable":false,"semantic_type":{"kind":"string"}}]'
    request_jcs = minimal_request_jcs(fields)
    schema = pa.schema([pa.field("v", pa.string(), nullable=False)])
    batch = pa.record_batch([pa.array(["x", "x"], type=pa.string())], schema=schema)
    output, result_jcs = canonical_row_hashes_v1(request_jcs, batch)
    table = output.read_all()
    assert table.schema == OUTPUT_ROW_HASH_SCHEMA
    assert table.num_rows == 2
    hashes = [table.column(0)[i].as_py() for i in range(2)]
    assert hashes[0] == hashes[1]
    assert b'"row_count":"2"' in result_jcs


def test_multi_batch_partition_matches_single_batch_row_hashes() -> None:
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
    single_output, _ = canonical_row_hashes_v1(request_jcs, single)
    split_output, _ = canonical_row_hashes_v1(request_jcs, split)
    assert row_hash_column_bytes(single_output) == row_hash_column_bytes(split_output)


def _multi_batch_reader() -> pa.RecordBatchReader:
    schema = pa.schema([pa.field("v", pa.string(), nullable=False)])
    return pa.RecordBatchReader.from_batches(
        schema,
        [
            pa.record_batch([pa.array(["alpha"], type=pa.string())], schema=schema),
            pa.record_batch(
                [pa.array(["beta", "gamma"], type=pa.string())],
                schema=schema,
            ),
        ],
    )


def test_multi_batch_serial_execution_is_byte_identical() -> None:
    fields = '[{"name":"v","nullable":false,"semantic_type":{"kind":"string"}}]'
    request_jcs = minimal_request_jcs(fields)
    first_output, first_jcs = canonical_row_hashes_v1(request_jcs, _multi_batch_reader())
    second_output, second_jcs = canonical_row_hashes_v1(request_jcs, _multi_batch_reader())
    assert first_jcs == second_jcs
    assert row_hash_column_bytes(first_output) == row_hash_column_bytes(second_output)


def test_serial_execution_result_jcs_is_exact_bytes() -> None:
    fields = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    request_jcs = minimal_request_jcs(fields)
    batch = pa.record_batch([pa.array([True])], names=["flag"])
    _, first = canonical_row_hashes_v1(request_jcs, batch)
    _, second = canonical_row_hashes_v1(request_jcs, batch)
    assert first == second
    assert isinstance(first, bytes)


def test_input_row_permutation_preserves_digests() -> None:
    fields = (
        '[{"name":"a","nullable":false,"semantic_type":{"kind":"signed-integer","bits":32}},'
        '{"name":"b","nullable":false,"semantic_type":{"kind":"signed-integer","bits":32}}]'
    )
    request_jcs = minimal_request_jcs(fields)
    schema = pa.schema(
        [
            pa.field("a", pa.int32(), nullable=False),
            pa.field("b", pa.int32(), nullable=False),
        ]
    )
    batch_a = pa.record_batch(
        [pa.array([1, 2], type=pa.int32()), pa.array([10, 20], type=pa.int32())],
        schema=schema,
    )
    batch_b = pa.record_batch(
        [pa.array([2, 1], type=pa.int32()), pa.array([20, 10], type=pa.int32())],
        schema=schema,
    )
    output_a, result_a = canonical_row_hashes_v1(request_jcs, batch_a)
    output_b, result_b = canonical_row_hashes_v1(request_jcs, batch_b)
    parsed_a = parse_result_jcs(result_a)
    parsed_b = parse_result_jcs(result_b)
    assert result_a == result_b
    assert row_hash_column_bytes(output_a) == row_hash_column_bytes(output_b)
    assert parsed_a["raw_content_digest"] == parsed_b["raw_content_digest"]
    assert parsed_a["table_schema_digest"] == parsed_b["table_schema_digest"]


def test_field_order_permutation_is_invariant() -> None:
    fields = (
        '[{"name":"a","nullable":false,"semantic_type":{"kind":"string"}},'
        '{"name":"b","nullable":false,"semantic_type":{"kind":"string"}}]'
    )
    request_jcs = minimal_request_jcs(fields)
    schema = pa.schema(
        [
            pa.field("a", pa.string(), nullable=False),
            pa.field("b", pa.string(), nullable=False),
        ]
    )
    batch = pa.record_batch(
        [pa.array(["x"], type=pa.string()), pa.array(["y"], type=pa.string())],
        schema=schema,
    )
    permuted = batch.select(["b", "a"])
    output_a, result_a = canonical_row_hashes_v1(request_jcs, batch)
    output_b, result_b = canonical_row_hashes_v1(request_jcs, permuted)
    assert result_a == result_b
    assert row_hash_column_bytes(output_a) == row_hash_column_bytes(output_b)


def test_output_row_hashes_are_sorted_unsigned_lexicographic() -> None:
    fields = '[{"name":"v","nullable":false,"semantic_type":{"kind":"string"}}]'
    request_jcs = minimal_request_jcs(fields)
    schema = pa.schema([pa.field("v", pa.string(), nullable=False)])
    batch = pa.record_batch(
        [pa.array(["gamma", "alpha", "beta"], type=pa.string())],
        schema=schema,
    )
    output, _ = canonical_row_hashes_v1(request_jcs, batch)
    assert_row_hashes_sorted_unsigned_lexicographic(output)


def test_zero_batches_with_declared_schema_succeeds() -> None:
    fields = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    request_jcs = minimal_request_jcs(fields)
    schema = pa.schema([pa.field("flag", pa.bool_(), nullable=True)])
    reader = pa.RecordBatchReader.from_batches(schema, [])
    output, result_jcs = canonical_row_hashes_v1(request_jcs, reader)
    assert output.schema == OUTPUT_ROW_HASH_SCHEMA
    assert output.read_all().num_rows == 0
    parsed = parse_result_jcs(result_jcs)
    assert parsed["row_count"] == "0"
    assert parsed["raw_content_digest"]
    assert parsed["table_schema_digest"]


def test_serial_execution_preserves_digest_fields() -> None:
    fields = '[{"name":"v","nullable":false,"semantic_type":{"kind":"string"}}]'
    request_jcs = minimal_request_jcs(fields)
    schema = pa.schema([pa.field("v", pa.string(), nullable=False)])
    batch = pa.record_batch([pa.array(["alpha", "beta"], type=pa.string())], schema=schema)
    _, first = canonical_row_hashes_v1(request_jcs, batch)
    _, second = canonical_row_hashes_v1(request_jcs, batch)
    first_parsed = parse_result_jcs(first)
    second_parsed = parse_result_jcs(second)
    assert first == second
    assert first_parsed["raw_content_digest"] == second_parsed["raw_content_digest"]
    assert first_parsed["table_schema_digest"] == second_parsed["table_schema_digest"]
