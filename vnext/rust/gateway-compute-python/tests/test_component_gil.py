"""GIL release probes for canonical_row_hashes_v1 (R1 §8.1)."""

from __future__ import annotations

import json
import threading
from typing import Any

import pyarrow as pa

from gateway_compute import canonical_row_hashes_v1


def minimal_request_jcs(fields_json: str) -> bytes:
    payload: dict[str, Any] = {
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


def _large_multi_batch_reader() -> pa.RecordBatchReader:
    fields = '[{"name":"v","nullable":false,"semantic_type":{"kind":"string"}}]'
    schema = pa.schema([pa.field("v", pa.string(), nullable=False)])
    batches = []
    for batch_index in range(8):
        values = [f"batch-{batch_index}-row-{row}" for row in range(256)]
        batches.append(pa.record_batch([pa.array(values, type=pa.string())], schema=schema))
    return pa.RecordBatchReader.from_batches(schema, batches)


def test_concurrent_python_thread_makes_progress_during_compute() -> None:
    stop = threading.Event()
    progress = {"count": 0}

    def gil_probe() -> None:
        while not stop.is_set():
            progress["count"] += 1

    request_jcs = minimal_request_jcs(
        '[{"name":"v","nullable":false,"semantic_type":{"kind":"string"}}]'
    )
    probe = threading.Thread(target=gil_probe, daemon=True)
    probe.start()
    try:
        canonical_row_hashes_v1(request_jcs, _large_multi_batch_reader())
    finally:
        stop.set()
        probe.join(timeout=5.0)

    assert progress["count"] >= 1_000, (
        "expected concurrent Python progress while native compute runs detached"
    )


def test_empty_table_import_export_smoke() -> None:
    """Smoke that facade import/export path completes for an empty table."""
    request_jcs = minimal_request_jcs("[]")
    reader = pa.RecordBatchReader.from_batches(pa.schema([]), [])
    output, result_jcs = canonical_row_hashes_v1(request_jcs, reader)
    assert isinstance(output, pa.RecordBatchReader)
    assert b'"row_count":"0"' in result_jcs
