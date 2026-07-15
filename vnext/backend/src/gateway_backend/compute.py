import pyarrow as pa

from gateway_backend.artifacts import ArtifactRef, artifact_ref


def double_first_column(batch: pa.RecordBatch) -> tuple[pa.RecordBatch, ArtifactRef]:
    """Run the fixed-width numeric walking-skeleton kernel and identify its result."""
    import gateway_compute

    result = gateway_compute.double_first_column(batch)
    if not isinstance(result, pa.RecordBatch):
        raise TypeError("native compute returned a non-RecordBatch value")
    return result, artifact_ref(
        result.serialize().to_pybytes(), "application/vnd.apache.arrow.recordbatch"
    )
