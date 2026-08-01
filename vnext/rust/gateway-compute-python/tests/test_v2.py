"""Python facade tests for canonical_row_hashes_v2."""

from __future__ import annotations

import json

import pyarrow as pa
import pytest

import gateway_compute
from gateway_compute import canonical_row_hashes_v2


def request(fields: list[dict[str, object]], *, boundary_version: int = 2, mapping_version: int = 1) -> bytes:
    return json.dumps(
        {
            "boundary_version": boundary_version,
            "canonical_encoding_version": 1,
            "arrow_mapping_version": mapping_version,
            "declared_fields": fields,
        },
        separators=(",", ":"),
    ).encode()


def test_v2_result_is_minimal_and_deterministic_across_batches() -> None:
    fields = [{"name": "v", "nullable": False, "semantic_type": {"kind": "boolean"}}]
    schema = pa.schema([pa.field("v", pa.bool_(), nullable=False)])
    one_batch = pa.RecordBatch.from_arrays([pa.array([True, False])], schema=schema)
    split = pa.RecordBatchReader.from_batches(
        one_batch.schema,
        [one_batch.slice(0, 1), one_batch.slice(1, 1)],
    )
    first, first_result = canonical_row_hashes_v2(request(fields), one_batch)
    second, second_result = canonical_row_hashes_v2(request(fields), split)

    assert json.loads(first_result) == json.loads(second_result)
    assert first.read_all().to_pylist() == second.read_all().to_pylist()
    assert set(json.loads(first_result)) == {
        "boundary_version",
        "table_schema_digest",
        "row_count",
        "raw_content_digest",
    }


def test_v2_rejects_old_shape_and_unsupported_versions() -> None:
    with pytest.raises(gateway_compute.ComputeRequestError) as old_shape:
        canonical_row_hashes_v2(b'{"request_schema_version":1}', pa.table({}))
    assert old_shape.value.code == "COMPUTE_REQUEST_SCHEMA_INVALID"

    with pytest.raises(gateway_compute.ComputeRequestError) as bad_boundary:
        canonical_row_hashes_v2(request([], boundary_version=1), pa.table({}))
    assert bad_boundary.value.code == "COMPUTE_BOUNDARY_VERSION_UNSUPPORTED"

    with pytest.raises(gateway_compute.ComputeRequestError) as bad_mapping:
        canonical_row_hashes_v2(request([], mapping_version=2), pa.table({}))
    assert bad_mapping.value.code == "COMPUTE_ARROW_MAPPING_VERSION_UNSUPPORTED"


def test_v1_entrypoint_is_not_exposed() -> None:
    assert not hasattr(gateway_compute, "canonical_row_hashes_v1")
    assert not hasattr(gateway_compute, "_canonical_row_hashes_v1_native")
