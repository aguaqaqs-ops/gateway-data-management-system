"""Backend walking-skeleton tests for canonical row hash compute."""

from __future__ import annotations

import json

import pyarrow as pa

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


def test_backend_empty_table_formal_path() -> None:
    request_jcs = minimal_request_jcs("[]")
    reader = pa.RecordBatchReader.from_batches(pa.schema([]), [])
    output, result_jcs = canonical_row_hashes_v1(request_jcs, reader)
    assert isinstance(output, pa.RecordBatchReader)
    assert b'"row_count":"0"' in result_jcs
    assert output.read_all().num_rows == 0


def test_backend_one_row_boolean_formal_path() -> None:
    fields = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    request_jcs = minimal_request_jcs(fields)
    batch = pa.record_batch([pa.array([True])], names=["flag"])
    output, result_jcs = canonical_row_hashes_v1(request_jcs, batch)
    table = output.read_all()
    assert table.num_rows == 1
    assert b'"row_count":"1"' in result_jcs
