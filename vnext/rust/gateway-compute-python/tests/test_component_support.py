"""Shared helpers for native-kernel component tests."""

from __future__ import annotations

import json
from typing import Any, Type

import pyarrow as pa

from gateway_compute import canonical_row_hashes_v1

CONTRACT_BINDING = {
    "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
    "semantic_version": "1.0.0",
}

OUTPUT_ROW_HASH_SCHEMA = pa.schema(
    [pa.field("row_hash", pa.binary(32), nullable=False)]
)

FAILURE_ENVELOPES: dict[str, bytes] = {
    "COMPUTE_REQUEST_SCHEMA_INVALID": (
        b'{"code":"COMPUTE_REQUEST_SCHEMA_INVALID","contract_binding":'
        b'{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary",'
        b'"semantic_version":"1.0.0"},"diagnostics":[],"effect":"NONE",'
        b'"failure_schema_version":1,"retry_class":"NEVER","stage":"request"}'
    ),
    "COMPUTE_CONTRACT_VERSION_UNSUPPORTED": (
        b'{"code":"COMPUTE_CONTRACT_VERSION_UNSUPPORTED","contract_binding":'
        b'{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary",'
        b'"semantic_version":"1.0.0"},"diagnostics":[],"effect":"NONE",'
        b'"failure_schema_version":1,"retry_class":"NEVER","stage":"request"}'
    ),
    "COMPUTE_CANONICAL_VERSION_UNSUPPORTED": (
        b'{"code":"COMPUTE_CANONICAL_VERSION_UNSUPPORTED","contract_binding":'
        b'{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary",'
        b'"semantic_version":"1.0.0"},"diagnostics":[],"effect":"NONE",'
        b'"failure_schema_version":1,"retry_class":"NEVER","stage":"request"}'
    ),
    "COMPUTE_ARROW_MAPPING_VERSION_UNSUPPORTED": (
        b'{"code":"COMPUTE_ARROW_MAPPING_VERSION_UNSUPPORTED","contract_binding":'
        b'{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary",'
        b'"semantic_version":"1.0.0"},"diagnostics":[],"effect":"NONE",'
        b'"failure_schema_version":1,"retry_class":"NEVER","stage":"request"}'
    ),
    "ARROW_SCHEMA_MISMATCH": (
        b'{"code":"ARROW_SCHEMA_MISMATCH","contract_binding":'
        b'{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary",'
        b'"semantic_version":"1.0.0"},"diagnostics":[],"effect":"NONE",'
        b'"failure_schema_version":1,"retry_class":"NEVER","stage":"schema"}'
    ),
    "ARROW_TYPE_UNSUPPORTED": (
        b'{"code":"ARROW_TYPE_UNSUPPORTED","contract_binding":'
        b'{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary",'
        b'"semantic_version":"1.0.0"},"diagnostics":[],"effect":"NONE",'
        b'"failure_schema_version":1,"retry_class":"NEVER","stage":"schema"}'
    ),
    "CANONICAL_VALUE_INVALID": (
        b'{"code":"CANONICAL_VALUE_INVALID","contract_binding":'
        b'{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary",'
        b'"semantic_version":"1.0.0"},"diagnostics":[],"effect":"NONE",'
        b'"failure_schema_version":1,"retry_class":"NEVER","stage":"canonicalize"}'
    ),
}


def minimal_request_jcs(
    fields_json: str,
    *,
    canonical_encoding_version: int = 1,
    arrow_mapping_schema_version: int = 1,
    contract_id: str = CONTRACT_BINDING["contract_id"],
) -> bytes:
    payload: dict[str, Any] = {
        "request_schema_version": 1,
        "contract_binding": {
            "contract_id": contract_id,
            "semantic_version": CONTRACT_BINDING["semantic_version"],
        },
        "canonical_encoding_version": canonical_encoding_version,
        "arrow_mapping_schema_version": arrow_mapping_schema_version,
        "declared_table_schema": {"fields": json.loads(fields_json)},
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def empty_reader() -> pa.RecordBatchReader:
    return pa.RecordBatchReader.from_batches(pa.schema([]), [])


def row_hash_column_bytes(reader: pa.RecordBatchReader) -> bytes:
    table = reader.read_all()
    column = table.column(0)
    return b"".join(column[i].as_py() for i in range(table.num_rows))


def parse_result_jcs(result_jcs: bytes) -> dict[str, Any]:
    return json.loads(result_jcs.decode())


def assert_failure_envelope(
    exc: BaseException,
    *,
    expected_type: Type[BaseException],
    expected_code: str,
) -> None:
    assert isinstance(exc, expected_type), type(exc)
    assert exc.code == expected_code
    assert exc.stage == json.loads(FAILURE_ENVELOPES[expected_code].decode())["stage"]
    envelope = exc.envelope_jcs
    assert envelope, "envelope_jcs must be non-empty"
    assert envelope == FAILURE_ENVELOPES[expected_code]
    golden = json.loads(FAILURE_ENVELOPES[expected_code].decode())
    parsed = json.loads(envelope.decode())
    assert parsed == golden


def assert_row_hashes_sorted_unsigned_lexicographic(reader: pa.RecordBatchReader) -> None:
    hashes = row_hash_column_bytes(reader)
    chunk = 32
    for index in range(0, len(hashes), chunk):
        current = hashes[index : index + chunk]
        next_index = index + chunk
        if next_index < len(hashes):
            nxt = hashes[next_index : next_index + chunk]
            assert current <= nxt, "row hashes must be unsigned lexicographic sorted"
