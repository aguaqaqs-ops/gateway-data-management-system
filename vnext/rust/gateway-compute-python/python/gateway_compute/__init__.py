"""Gateway compute Python facade over the native Arrow C Stream adapter."""

from __future__ import annotations

import pyarrow as pa

from gateway_compute.exceptions import (
    CanonicalValueError,
    ComputeError,
    ComputeRequestError,
    ResourceLimitError,
)
from gateway_compute.gateway_compute import __version__, _canonical_row_hashes_v2_native

__all__ = [
    "CanonicalValueError",
    "ComputeError",
    "ComputeRequestError",
    "ResourceLimitError",
    "__version__",
    "_as_record_batch_reader",
    "canonical_row_hashes_v2",
]


def _as_record_batch_reader(
    data: pa.RecordBatch | pa.Table | pa.RecordBatchReader,
) -> pa.RecordBatchReader:
    if isinstance(data, pa.RecordBatchReader):
        return data
    if isinstance(data, pa.RecordBatch):
        return pa.RecordBatchReader.from_batches(data.schema, [data])
    if isinstance(data, pa.Table):
        return data.to_reader()
    raise TypeError(
        "data must be pyarrow.RecordBatch, pyarrow.Table, or pyarrow.RecordBatchReader"
    )


def canonical_row_hashes_v2(
    request_jcs: bytes,
    data: pa.RecordBatch | pa.Table | pa.RecordBatchReader,
) -> tuple[pa.RecordBatchReader, bytes]:
    if not isinstance(request_jcs, bytes):
        raise TypeError("request_jcs must be bytes")
    reader = _as_record_batch_reader(data)
    output_stream, result_jcs = _canonical_row_hashes_v2_native(request_jcs, reader)
    if not isinstance(output_stream, pa.RecordBatchReader):
        raise TypeError("native compute returned a non-RecordBatchReader value")
    return output_stream, result_jcs
