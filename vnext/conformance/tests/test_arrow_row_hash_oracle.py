"""Tests for the shared-kernel Arrow row-hash oracle."""

from __future__ import annotations

from decimal import Decimal

import pyarrow as pa

import pytest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.harness.canonical_row_hashes.mapping_inventory import (
    REQUIRED_CASE_IDS,
    iter_required_cases,
)
from gateway_conformance.owner.arrow_row_hash_oracle import (
    compute_row_hashes_from_ipc,
    compute_table_content_identity,
    multiset_digest_differs_from_deduped,
)
from gateway_shared_kernel import unordered_row_hashes_content_digest


def _ipc_from_table(table: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, table.schema) as writer:
        for batch in table.to_batches():
            writer.write_batch(batch)
    return bytes(sink.getvalue().to_pybytes())


def test_multiset_digest_retains_duplicate_row_hashes() -> None:
    row_hash = b"\x01" * 32
    assert multiset_digest_differs_from_deduped([row_hash, row_hash]) is True
    one = unordered_row_hashes_content_digest([row_hash]).digest_ref.value
    two = unordered_row_hashes_content_digest([row_hash, row_hash]).digest_ref.value
    assert one != two


def test_oracle_row_hashes_sorted_unsigned_for_multiset() -> None:
    schema = pa.schema(
        [
            pa.field("z_label", pa.string(), nullable=True),
            pa.field("a_id", pa.int32(), nullable=False),
            pa.field("m_flag", pa.bool_(), nullable=True),
            pa.field("amount", pa.decimal128(10, 2), nullable=False),
        ]
    )
    table = pa.Table.from_arrays(
        [
            pa.array(["x", "y"], type=pa.string()),
            pa.array([1, 2], type=pa.int32()),
            pa.array([True, False], type=pa.bool_()),
            pa.array([Decimal("1.00"), Decimal("2.00")], type=pa.decimal128(10, 2)),
        ],
        schema=schema,
    )
    fields = [
        {"name": "z_label", "nullable": True, "semantic_type": {"kind": "string"}},
        {
            "name": "a_id",
            "nullable": False,
            "semantic_type": {"kind": "signed-integer", "bits": 32},
        },
        {"name": "m_flag", "nullable": True, "semantic_type": {"kind": "boolean"}},
        {
            "name": "amount",
            "nullable": False,
            "semantic_type": {"kind": "decimal", "precision": 10, "scale": 2},
        },
    ]
    ipc = _ipc_from_table(table)
    hashes = compute_row_hashes_from_ipc(ipc, fields)
    assert len(hashes) == 2
    row_count, digest, sorted_hashes = compute_table_content_identity(ipc, fields)
    assert row_count == "2"
    assert sorted_hashes == sorted(hashes)
    assert digest == compute_table_content_identity(ipc, fields)[1]


def test_oracle_rejects_int64_for_declared_int32() -> None:
    schema = pa.schema([pa.field("a_id", pa.int64(), nullable=False)])
    table = pa.Table.from_arrays([pa.array([1], type=pa.int64())], schema=schema)
    fields = [
        {
            "name": "a_id",
            "nullable": False,
            "semantic_type": {"kind": "signed-integer", "bits": 32},
        },
    ]
    with pytest.raises(ConformanceValidationError, match="physical type mismatch"):
        compute_row_hashes_from_ipc(_ipc_from_table(table), fields)


def test_oracle_rejects_extra_arrow_column() -> None:
    schema = pa.schema(
        [
            pa.field("a_id", pa.int32(), nullable=False),
            pa.field("extra", pa.string(), nullable=True),
        ]
    )
    table = pa.Table.from_arrays(
        [pa.array([1], type=pa.int32()), pa.array(["x"], type=pa.string())],
        schema=schema,
    )
    fields = [
        {
            "name": "a_id",
            "nullable": False,
            "semantic_type": {"kind": "signed-integer", "bits": 32},
        },
    ]
    with pytest.raises(ConformanceValidationError, match="field count mismatch"):
        compute_row_hashes_from_ipc(_ipc_from_table(table), fields)


def test_oracle_rejects_int32_for_declared_int8() -> None:
    schema = pa.schema([pa.field("v", pa.int32(), nullable=False)])
    table = pa.Table.from_arrays([pa.array([1], type=pa.int32())], schema=schema)
    fields = [
        {
            "name": "v",
            "nullable": False,
            "semantic_type": {"kind": "signed-integer", "bits": 8},
        },
    ]
    with pytest.raises(ConformanceValidationError, match="physical type mismatch"):
        compute_row_hashes_from_ipc(_ipc_from_table(table), fields)


def test_oracle_rejects_decimal256_for_precision_10() -> None:
    schema = pa.schema([pa.field("amount", pa.decimal256(10, 2), nullable=False)])
    table = pa.Table.from_arrays(
        [pa.array([Decimal("1.00")], type=pa.decimal256(10, 2))],
        schema=schema,
    )
    fields = [
        {
            "name": "amount",
            "nullable": False,
            "semantic_type": {"kind": "decimal", "precision": 10, "scale": 2},
        },
    ]
    with pytest.raises(ConformanceValidationError, match="physical type mismatch"):
        compute_row_hashes_from_ipc(_ipc_from_table(table), fields)


def test_oracle_rejects_schema_extension_metadata() -> None:
    from gateway_conformance.owner.arrow_mapping import cross_check_stream_schema

    schema = pa.schema(
        [pa.field("a_id", pa.int32(), nullable=False)],
        metadata={b"ARROW:extension:name": b"test"},
    )
    fields = [
        {
            "name": "a_id",
            "nullable": False,
            "semantic_type": {"kind": "signed-integer", "bits": 32},
        },
    ]
    with pytest.raises(ConformanceValidationError, match="extension metadata unsupported"):
        cross_check_stream_schema(fields, schema)


def test_oracle_rejects_trailing_ipc_bytes() -> None:
    from gateway_conformance.owner.arrow_mapping import assert_no_trailing_ipc_bytes

    with pytest.raises(ConformanceValidationError, match="trailing bytes"):
        assert_no_trailing_ipc_bytes(b"abc", 1)


def test_oracle_rejects_zero_byte_trailing_on_valid_stream() -> None:
    schema = pa.schema([pa.field("a_id", pa.int32(), nullable=False)])
    table = pa.Table.from_arrays([pa.array([1], type=pa.int32())], schema=schema)
    fields = [
        {
            "name": "a_id",
            "nullable": False,
            "semantic_type": {"kind": "signed-integer", "bits": 32},
        },
    ]
    ipc = _ipc_from_table(table)
    with pytest.raises(ConformanceValidationError, match="trailing bytes"):
        compute_row_hashes_from_ipc(ipc + b"\x00", fields)
    with pytest.raises(ConformanceValidationError, match="trailing bytes"):
        compute_row_hashes_from_ipc(ipc + b"\x00\x00\x00\x00", fields)
    with pytest.raises(ConformanceValidationError, match="trailing bytes"):
        compute_row_hashes_from_ipc(ipc + b"garbage", fields)


@pytest.mark.parametrize("case_id", sorted(REQUIRED_CASE_IDS))
def test_oracle_inventory_case_positive(case_id: str) -> None:

    case = next(item for item in iter_required_cases() if item.case_id == case_id)
    fields = [dict(item) for item in case.declared_fields]
    hashes = compute_row_hashes_from_ipc(case.ipc_bytes, fields)
    assert len(hashes) == 1
    assert len(hashes[0]) == 32
