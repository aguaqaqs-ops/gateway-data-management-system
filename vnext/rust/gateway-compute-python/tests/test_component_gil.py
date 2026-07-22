"""Supplementary facade probes for canonical_row_hashes_v1 (R1 §8.1).

Authoritative attached/detached stage evidence lives in Rust
`kernel_component_tests::{gil_controller,gil_probe,gil_00_python_thread}`.
Python tests here cover facade normalization and import/export smoke only.
"""

from __future__ import annotations

import threading
from unittest.mock import patch

import pyarrow as pa

from gateway_compute import canonical_row_hashes_v1

from test_component_support import minimal_request_jcs


def test_facade_input_normalization_is_synchronous_on_calling_thread() -> None:
    """Facade normalization runs on the calling thread before native entry."""
    caller_thread = threading.get_ident()
    native_thread: dict[str, int | None] = {"id": None}

    import gateway_compute

    real_native = gateway_compute._canonical_row_hashes_v1_native

    def patched_native(request_jcs: bytes, reader: pa.RecordBatchReader):
        if native_thread["id"] is None:
            native_thread["id"] = threading.get_ident()
        return real_native(request_jcs, reader)

    request_jcs = minimal_request_jcs("[]")
    table = pa.table({})

    with patch.object(gateway_compute, "_canonical_row_hashes_v1_native", patched_native):
        canonical_row_hashes_v1(request_jcs, table)

    assert native_thread["id"] == caller_thread, (
        "native must be invoked on the same thread that performed facade normalization"
    )


def test_empty_table_import_export_smoke() -> None:
    request_jcs = minimal_request_jcs("[]")
    reader = pa.RecordBatchReader.from_batches(pa.schema([]), [])
    output, result_jcs = canonical_row_hashes_v1(request_jcs, reader)
    assert isinstance(output, pa.RecordBatchReader)
    assert b'"row_count":"0"' in result_jcs
