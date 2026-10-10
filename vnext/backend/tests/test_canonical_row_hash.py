"""Backend owner tests for the v1 canonical row-hash boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa

from gateway_backend.capabilities.canonical_row_hash.canonical_row_hash_ipc import collect_row_hashes_from_ipc, write_row_hash_ipc_stream
from gateway_backend.capabilities.canonical_row_hash.compute import canonical_row_hashes_v1

MIXED_SCALAR_GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "golden"
    / "canonical-row-hash"
    / "mixed-scalars"
)


def request_for(fields: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {
            "boundary_version": 1,
            "canonical_encoding_version": 1,
            "arrow_mapping_version": 1,
            "declared_fields": fields,
        },
        separators=(",", ":"),
    ).encode()


def test_backend_v1_result_has_only_owner_fields() -> None:
    fields = [{"name": "v", "nullable": False, "semantic_type": {"kind": "boolean"}}]
    table = pa.Table.from_arrays(
        [pa.array([True])],
        schema=pa.schema([pa.field("v", pa.bool_(), nullable=False)]),
    )
    output, result_jcs = canonical_row_hashes_v1(
        request_for(fields), table
    )

    result = json.loads(result_jcs)
    assert set(result) == {
        "boundary_version",
        "table_schema_digest",
        "row_count",
        "raw_content_digest",
    }
    assert result["boundary_version"] == 1
    assert result["row_count"] == "1"
    assert len(collect_row_hashes_from_ipc(write_row_hash_ipc_stream(output))) == 1


def test_backend_mixed_scalar_golden_direct_owner_path() -> None:
    request = (MIXED_SCALAR_GOLDEN / "request.json").read_bytes()
    expected = json.loads((MIXED_SCALAR_GOLDEN / "expected.json").read_text(encoding="utf-8"))
    table = pa.ipc.open_stream(
        pa.BufferReader((MIXED_SCALAR_GOLDEN / "input.arrow-stream").read_bytes())
    ).read_all()

    output, result_jcs = canonical_row_hashes_v1(request, table)
    result = json.loads(result_jcs)
    assert {
        "row_count": result["row_count"],
        "raw_content_digest": result["raw_content_digest"],
        "table_schema_digest": result["table_schema_digest"],
    } == {
        "row_count": expected["row_count"],
        "raw_content_digest": expected["raw_content_digest"],
        "table_schema_digest": expected["table_schema_digest"],
    }
    row_hashes = collect_row_hashes_from_ipc(write_row_hash_ipc_stream(output))
    assert [item.hex() for item in row_hashes] == expected["sorted_row_hashes_hex"]
