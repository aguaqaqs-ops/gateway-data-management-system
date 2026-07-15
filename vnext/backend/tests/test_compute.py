import pyarrow as pa

from gateway_backend.compute import double_first_column


def test_arrow_batch_round_trip_preserves_nulls_and_has_digest() -> None:
    batch = pa.record_batch([pa.array([1, None, -3], type=pa.int64())], names=["value"])

    result, reference = double_first_column(batch)

    assert result.schema == batch.schema
    assert result.column(0).to_pylist() == [2, None, -6]
    assert reference.media_type == "application/vnd.apache.arrow.recordbatch"
    assert reference.digest.startswith("sha256:")
