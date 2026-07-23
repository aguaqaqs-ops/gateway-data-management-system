"""WP4 R4 PR-NATIVE Arrow mapping coverage on installed wheel path."""

from __future__ import annotations

from decimal import Decimal

import pyarrow as pa
import pytest

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.canonical_row_hash_ipc import collect_row_hashes_from_ipc

from pr_native_support import build_logical_ref_for_case, run_full_chain

pytestmark = pytest.mark.pr_native


@pytest.mark.parametrize(
    ("case_id", "fields", "schema", "arrays"),
    [
        pytest.param(
            "unsigned-24",
            [
                {
                    "name": "v",
                    "nullable": False,
                    "semantic_type": {"kind": "unsigned-integer", "bits": 24},
                }
            ],
            pa.schema([pa.field("v", pa.uint32(), nullable=False)]),
            [pa.array([16_777_215], type=pa.uint32())],
            id="unsigned-integer-24bit",
        ),
        pytest.param(
            "decimal",
            [
                {
                    "name": "v",
                    "nullable": False,
                    "semantic_type": {"kind": "decimal", "precision": 5, "scale": 2},
                }
            ],
            pa.schema([pa.field("v", pa.decimal128(5, 2), nullable=False)]),
            [pa.array([Decimal("123.45")], type=pa.decimal128(5, 2))],
            id="decimal128",
        ),
        pytest.param(
            "binary",
            [{"name": "v", "nullable": False, "semantic_type": {"kind": "binary"}}],
            pa.schema([pa.field("v", pa.binary(), nullable=False)]),
            [pa.array([b"abc"], type=pa.binary())],
            id="binary",
        ),
        pytest.param(
            "float64",
            [{"name": "v", "nullable": False, "semantic_type": {"kind": "float64"}}],
            pa.schema([pa.field("v", pa.float64(), nullable=False)]),
            [pa.array([-0.0], type=pa.float64())],
            id="float64",
        ),
        pytest.param(
            "duration",
            [{"name": "v", "nullable": False, "semantic_type": {"kind": "time-duration"}}],
            pa.schema([pa.field("v", pa.duration("us"), nullable=False)]),
            [pa.array([1_000], type=pa.duration("us"))],
            id="time-duration",
        ),
    ],
)
def test_mapping_kind_full_chain_round_trip(
    case_id: str,
    fields: list[dict[str, object]],
    schema: pa.Schema,
    arrays: list[pa.Array],
) -> None:
    store = InMemoryArtifactStore()
    ref, content, result_jcs = run_full_chain(
        store,
        fields=fields,
        data=pa.record_batch(arrays, schema=schema),
        logical_ref=build_logical_ref_for_case(f"mapping-{case_id}"),
    )
    assert content.row_count == "1"
    assert b'"row_count":"1"' in result_jcs
    reopened_hashes = collect_row_hashes_from_ipc(store.locate(ref))
    assert len(reopened_hashes) == 1
    assert len(reopened_hashes[0]) == 32
