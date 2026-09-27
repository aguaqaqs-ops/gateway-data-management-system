"""Backend facade for the v1 canonical row-hash capability."""

import pyarrow as pa

from gateway_compute import canonical_row_hashes_v1 as _native


def canonical_row_hashes_v1(
    request_jcs: bytes,
    data: pa.RecordBatch | pa.Table | pa.RecordBatchReader,
) -> tuple[pa.RecordBatchReader, bytes]:
    output_stream, result_jcs = _native(request_jcs, data)
    if not isinstance(output_stream, pa.RecordBatchReader):
        raise TypeError("native compute returned a non-RecordBatchReader value")
    return output_stream, result_jcs
