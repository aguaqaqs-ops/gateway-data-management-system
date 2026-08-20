"""Provider-port implementations for the S1 Arrow batch boundary."""

from __future__ import annotations

import pyarrow as pa
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.comparison.contracts import (
    COMPARISON_BATCH_PORT_VERSION,
    ComparisonBatchRequest,
    ComparisonBatchResult,
    NativeBatchCompute,
    validate_batch_reader,
)


class PythonReferenceBatchProvider:
    """Small-fixture reference provider; it retains batches but never converts rows to Python lists."""

    provider_id = "python-reference-batch-v1"

    def execute(self, request: ComparisonBatchRequest) -> ComparisonBatchResult:
        reader = validate_batch_reader(request.reader.reopen())
        batches = tuple(reader.iter_record_batches())
        reader.close()
        output = pa.RecordBatchReader.from_batches(request.reader.schema(), batches)
        result_jcs = canonicalize_json_value(
            {
                "batch_port_version": COMPARISON_BATCH_PORT_VERSION,
                "row_count": sum(batch.num_rows for batch in batches),
            }
        )
        return ComparisonBatchResult(
            provider_id=self.provider_id,
            output_stream=output,
            result_jcs=result_jcs,
            input_metadata=request.reader.metadata(),
        )


class RustArrowBatchProvider:
    """Coarse PyO3 adapter around an injected native callable.

    The callable receives a single Arrow stream and returns a single Arrow stream. Injecting it keeps
    the comparison capability independent from the backend compute facade and makes provider failures
    explicit rather than silently falling back to Python.
    """

    provider_id = "rust-arrow-batch-v1"

    def __init__(self, native_compute: NativeBatchCompute) -> None:
        if not callable(native_compute):
            raise TypeError("native_compute must be callable")
        self._native_compute = native_compute

    def execute(self, request: ComparisonBatchRequest) -> ComparisonBatchResult:
        reader = validate_batch_reader(request.reader.reopen())
        input_stream = pa.RecordBatchReader.from_batches(
            reader.schema(), reader.iter_record_batches()
        )
        try:
            output_stream, result_jcs = self._native_compute(request.request_jcs, input_stream)
        finally:
            reader.close()
        return ComparisonBatchResult(
            provider_id=self.provider_id,
            output_stream=output_stream,
            result_jcs=result_jcs,
            input_metadata=request.reader.metadata(),
        )


def collect_batches(reader: pa.RecordBatchReader) -> tuple[pa.RecordBatch, ...]:
    """Test/reference helper that collects batches, never row objects."""

    return tuple(reader)
