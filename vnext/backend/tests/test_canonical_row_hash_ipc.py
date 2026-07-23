"""Canonical row-hash IPC writer/reader tests."""

from __future__ import annotations

import json

import pyarrow as pa
import pytest

from gateway_backend.canonical_row_hash_artifact import CanonicalRowHashesArtifactManifest
from gateway_backend.canonical_row_hash_ipc import (
    CANONICAL_ROW_HASH_OUTPUT_SCHEMA,
    CanonicalRowHashIpcError,
    collect_row_hashes_from_ipc,
    content_manifest_from_compute_result,
    open_row_hash_ipc_stream,
    persist_canonical_row_hash_stream,
    table_schema_digest_from_declared_fields,
    verify_row_hashes_sorted_unsigned,
    write_row_hash_ipc_stream,
)
from gateway_backend.artifacts import InMemoryArtifactStore, build_logical_ref
from gateway_backend.compute import canonical_row_hashes_v1


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


def _reader_from_hashes(hashes: list[bytes]) -> pa.RecordBatchReader:
    array = pa.array(hashes, type=pa.binary(32))
    batch = pa.record_batch([array], schema=CANONICAL_ROW_HASH_OUTPUT_SCHEMA)
    return pa.RecordBatchReader.from_batches(CANONICAL_ROW_HASH_OUTPUT_SCHEMA, [batch])


def test_empty_stream_round_trip_preserves_schema() -> None:
    reader = pa.RecordBatchReader.from_batches(CANONICAL_ROW_HASH_OUTPUT_SCHEMA, [])
    raw_bytes = write_row_hash_ipc_stream(reader)
    reopened = open_row_hash_ipc_stream(raw_bytes)
    assert reopened.schema.equals(CANONICAL_ROW_HASH_OUTPUT_SCHEMA, check_metadata=True)
    assert collect_row_hashes_from_ipc(raw_bytes) == []


def test_write_rejects_non_canonical_schema() -> None:
    schema = pa.schema([pa.field("value", pa.int64())])
    reader = pa.RecordBatchReader.from_batches(schema, [])
    with pytest.raises(CanonicalRowHashIpcError, match="schema does not match"):
        write_row_hash_ipc_stream(reader)


def test_write_rejects_schema_metadata() -> None:
    schema = pa.schema(
        [pa.field("row_hash", pa.binary(32), nullable=False)],
        metadata={b"note": b"forbidden"},
    )
    reader = pa.RecordBatchReader.from_batches(schema, [])
    with pytest.raises(CanonicalRowHashIpcError, match="schema does not match"):
        write_row_hash_ipc_stream(reader)


def test_open_rejects_ipc_with_schema_metadata() -> None:
    schema = pa.schema(
        [pa.field("row_hash", pa.binary(32), nullable=False)],
        metadata={b"note": b"forbidden"},
    )
    batch = pa.record_batch([pa.array([b"\x00" * 32], type=pa.binary(32))], schema=schema)
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, schema) as writer:
        writer.write_batch(batch)
    with pytest.raises(CanonicalRowHashIpcError, match="schema does not match"):
        open_row_hash_ipc_stream(bytes(sink.getvalue().to_pybytes()))


def test_write_rejects_null_row_hash_slot() -> None:
    array = pa.array([None], type=pa.binary(32))
    batch = pa.record_batch([array], schema=CANONICAL_ROW_HASH_OUTPUT_SCHEMA)
    reader = pa.RecordBatchReader.from_batches(CANONICAL_ROW_HASH_OUTPUT_SCHEMA, [batch])
    with pytest.raises(CanonicalRowHashIpcError, match="must not contain null"):
        write_row_hash_ipc_stream(reader)


def test_compute_output_can_be_written_and_reopened() -> None:
    fields = [{"name": "flag", "nullable": True, "semantic_type": {"kind": "boolean"}}]
    request_jcs = minimal_request_jcs(json.dumps(fields))
    batch = pa.record_batch([pa.array([True, False])], names=["flag"])
    output, _ = canonical_row_hashes_v1(request_jcs, batch)
    raw_bytes = write_row_hash_ipc_stream(output)
    row_hashes = collect_row_hashes_from_ipc(raw_bytes)
    assert len(row_hashes) == 2
    verify_row_hashes_sorted_unsigned(row_hashes)


def test_multi_batch_reader_round_trip() -> None:
    request_jcs = minimal_request_jcs(
        '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    )
    batch_a = pa.record_batch([pa.array([True])], names=["flag"])
    batch_b = pa.record_batch([pa.array([False])], names=["flag"])
    output_a, _ = canonical_row_hashes_v1(request_jcs, batch_a)
    output_b, _ = canonical_row_hashes_v1(request_jcs, batch_b)
    hashes_a = collect_row_hashes_from_ipc(write_row_hash_ipc_stream(output_a))
    hashes_b = collect_row_hashes_from_ipc(write_row_hash_ipc_stream(output_b))
    hash_batch_a = pa.record_batch(
        [pa.array(hashes_a, type=pa.binary(32))],
        schema=CANONICAL_ROW_HASH_OUTPUT_SCHEMA,
    )
    hash_batch_b = pa.record_batch(
        [pa.array(hashes_b, type=pa.binary(32))],
        schema=CANONICAL_ROW_HASH_OUTPUT_SCHEMA,
    )
    combined = pa.RecordBatchReader.from_batches(
        CANONICAL_ROW_HASH_OUTPUT_SCHEMA,
        [hash_batch_a, hash_batch_b],
    )
    raw_bytes = write_row_hash_ipc_stream(combined)
    assert collect_row_hashes_from_ipc(raw_bytes) == hashes_a + hashes_b


def test_duplicate_row_hashes_preserved() -> None:
    row_hash = b"\x01" * 32
    raw_bytes = write_row_hash_ipc_stream(_reader_from_hashes([row_hash, row_hash]))
    assert collect_row_hashes_from_ipc(raw_bytes) == [row_hash, row_hash]


def test_content_manifest_from_compute_result_rejects_unknown_field() -> None:
    payload = {
        "result_schema_version": 1,
        "contract_binding": {
            "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
            "semantic_version": "1.0.0",
        },
        "canonical_encoding_version": 1,
        "arrow_mapping_schema_version": 1,
        "table_schema_digest": "sha256:" + "0" * 64,
        "row_count": "0",
        "raw_content_digest": "sha256:" + "0" * 64,
        "diagnostics": [],
        "extra": True,
    }
    with pytest.raises(CanonicalRowHashIpcError, match="fields do not match"):
        content_manifest_from_compute_result(json.dumps(payload).encode())


def test_publish_rejects_invalid_manifest_before_ref() -> None:
    fields = [{"name": "flag", "nullable": True, "semantic_type": {"kind": "boolean"}}]
    request_jcs = minimal_request_jcs(json.dumps(fields))
    output, result_jcs = canonical_row_hashes_v1(request_jcs, pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    tampered = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=content.raw_content_digest,
        table_schema_digest=content.table_schema_digest,
        row_count="999",
    )
    store = InMemoryArtifactStore()
    with pytest.raises(CanonicalRowHashIpcError, match="row_count mismatch"):
        persist_canonical_row_hash_stream(
            store,
            logical_ref=build_logical_ref("canonical-row-hash", "bad-publish"),
            reader=output,
            content_manifest=tampered,
            declared_table_schema_fields=fields,
        )


def test_compute_result_rejects_boolean_version_marker() -> None:
    payload = {
        "result_schema_version": True,
        "contract_binding": {
            "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
            "semantic_version": "1.0.0",
        },
        "canonical_encoding_version": 1,
        "arrow_mapping_schema_version": 1,
        "table_schema_digest": "sha256:" + "0" * 64,
        "row_count": "0",
        "raw_content_digest": "sha256:" + "0" * 64,
        "diagnostics": [],
    }
    with pytest.raises(CanonicalRowHashIpcError, match="result_schema_version must be 1"):
        content_manifest_from_compute_result(json.dumps(payload).encode())


def test_declared_schema_rejects_integer_nullable() -> None:
    fields = [{"name": "flag", "nullable": 1, "semantic_type": {"kind": "boolean"}}]
    with pytest.raises(CanonicalRowHashIpcError, match="nullable must be a boolean"):
        table_schema_digest_from_declared_fields(fields)
