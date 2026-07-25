"""Closed mapping-case inventory for all 15 canonical semantic kinds."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pyarrow as pa

from gateway_shared_kernel import DeclaredTypeKind

_ANOMALY_ENVELOPE = (
    b'{"declared_type":{"kind":"date"},"raw_base64url":"YmFk",'
    b'"raw_encoding":"utf8","reason":"owner-reason"}'
)


def _ipc_from_batches(schema: pa.Schema, arrays: list[pa.Array]) -> bytes:
    table = pa.Table.from_arrays(arrays, schema=schema)
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, schema) as writer:
        for batch in table.to_batches():
            writer.write_batch(batch)
    return bytes(sink.getvalue().to_pybytes())


@dataclass(frozen=True, slots=True)
class MappingCase:
    case_id: str
    primary_kind: str
    declared_fields: tuple[dict[str, Any], ...]
    ipc_bytes: bytes


def _case(
    case_id: str,
    primary_kind: str,
    fields: list[dict[str, Any]],
    schema: pa.Schema,
    arrays: list[pa.Array],
) -> MappingCase:
    return MappingCase(
        case_id=case_id,
        primary_kind=primary_kind,
        declared_fields=tuple(fields),
        ipc_bytes=_ipc_from_batches(schema, arrays),
    )


def _build_cases() -> tuple[MappingCase, ...]:
    return (
        _case(
            "mapping-null",
            DeclaredTypeKind.NULL.value,
            [{"name": "v", "nullable": True, "semantic_type": {"kind": "null"}}],
            pa.schema([pa.field("v", pa.null(), nullable=True)]),
            [pa.array([None], type=pa.null())],
        ),
        _case(
            "mapping-boolean",
            DeclaredTypeKind.BOOLEAN.value,
            [{"name": "v", "nullable": False, "semantic_type": {"kind": "boolean"}}],
            pa.schema([pa.field("v", pa.bool_(), nullable=False)]),
            [pa.array([True], type=pa.bool_())],
        ),
        _case(
            "mapping-signed-integer-32",
            DeclaredTypeKind.SIGNED_INTEGER.value,
            [
                {
                    "name": "v",
                    "nullable": False,
                    "semantic_type": {"kind": "signed-integer", "bits": 32},
                }
            ],
            pa.schema([pa.field("v", pa.int32(), nullable=False)]),
            [pa.array([-42], type=pa.int32())],
        ),
        _case(
            "mapping-unsigned-integer-32",
            DeclaredTypeKind.UNSIGNED_INTEGER.value,
            [
                {
                    "name": "v",
                    "nullable": False,
                    "semantic_type": {"kind": "unsigned-integer", "bits": 32},
                }
            ],
            pa.schema([pa.field("v", pa.uint32(), nullable=False)]),
            [pa.array([42], type=pa.uint32())],
        ),
        _case(
            "mapping-decimal",
            DeclaredTypeKind.DECIMAL.value,
            [
                {
                    "name": "v",
                    "nullable": False,
                    "semantic_type": {"kind": "decimal", "precision": 5, "scale": 2},
                }
            ],
            pa.schema([pa.field("v", pa.decimal128(5, 2), nullable=False)]),
            [pa.array([Decimal("123.45")], type=pa.decimal128(5, 2))],
        ),
        _case(
            "mapping-float32",
            DeclaredTypeKind.FLOAT32.value,
            [{"name": "v", "nullable": False, "semantic_type": {"kind": "float32"}}],
            pa.schema([pa.field("v", pa.float32(), nullable=False)]),
            [pa.array([-0.0], type=pa.float32())],
        ),
        _case(
            "mapping-float64",
            DeclaredTypeKind.FLOAT64.value,
            [{"name": "v", "nullable": False, "semantic_type": {"kind": "float64"}}],
            pa.schema([pa.field("v", pa.float64(), nullable=False)]),
            [pa.array([-0.0], type=pa.float64())],
        ),
        _case(
            "mapping-string",
            DeclaredTypeKind.STRING.value,
            [{"name": "v", "nullable": False, "semantic_type": {"kind": "string"}}],
            pa.schema([pa.field("v", pa.string(), nullable=False)]),
            [pa.array(["alpha"], type=pa.string())],
        ),
        _case(
            "mapping-binary",
            DeclaredTypeKind.BINARY.value,
            [{"name": "v", "nullable": False, "semantic_type": {"kind": "binary"}}],
            pa.schema([pa.field("v", pa.binary(), nullable=False)]),
            [pa.array([b"abc"], type=pa.binary())],
        ),
        _case(
            "mapping-bit-8",
            DeclaredTypeKind.BIT.value,
            [
                {
                    "name": "v",
                    "nullable": False,
                    "semantic_type": {"kind": "bit", "bit_width": 8},
                }
            ],
            pa.schema([pa.field("v", pa.binary(), nullable=False)]),
            [pa.array([bytes([0xAB])], type=pa.binary())],
        ),
        _case(
            "mapping-date",
            DeclaredTypeKind.DATE.value,
            [{"name": "v", "nullable": False, "semantic_type": {"kind": "date"}}],
            pa.schema([pa.field("v", pa.date32(), nullable=False)]),
            [pa.array([0], type=pa.date32())],
        ),
        _case(
            "mapping-datetime",
            DeclaredTypeKind.DATETIME.value,
            [{"name": "v", "nullable": False, "semantic_type": {"kind": "datetime"}}],
            pa.schema([pa.field("v", pa.timestamp("us"), nullable=False)]),
            [pa.array([0], type=pa.timestamp("us"))],
        ),
        _case(
            "mapping-timestamp",
            DeclaredTypeKind.TIMESTAMP.value,
            [{"name": "v", "nullable": False, "semantic_type": {"kind": "timestamp"}}],
            pa.schema([pa.field("v", pa.timestamp("us", tz="UTC"), nullable=False)]),
            [pa.array([0], type=pa.timestamp("us", tz="UTC"))],
        ),
        _case(
            "mapping-time-duration",
            DeclaredTypeKind.TIME_DURATION.value,
            [{"name": "v", "nullable": False, "semantic_type": {"kind": "time-duration"}}],
            pa.schema([pa.field("v", pa.duration("us"), nullable=False)]),
            [pa.array([1_000], type=pa.duration("us"))],
        ),
        _case(
            "mapping-anomaly",
            DeclaredTypeKind.SOURCE_LITERAL_ANOMALY.value,
            [
                {
                    "name": "v",
                    "nullable": False,
                    "semantic_type": {"kind": "source-literal-anomaly"},
                }
            ],
            pa.schema([pa.field("v", pa.binary(), nullable=False)]),
            [pa.array([_ANOMALY_ENVELOPE], type=pa.binary())],
        ),
        _case(
            "mapping-boolean-null-slot",
            DeclaredTypeKind.BOOLEAN.value,
            [{"name": "v", "nullable": True, "semantic_type": {"kind": "boolean"}}],
            pa.schema([pa.field("v", pa.bool_(), nullable=True)]),
            [pa.array([None], type=pa.bool_())],
        ),
        _case(
            "mapping-string-null-slot",
            DeclaredTypeKind.STRING.value,
            [{"name": "v", "nullable": True, "semantic_type": {"kind": "string"}}],
            pa.schema([pa.field("v", pa.string(), nullable=True)]),
            [pa.array([None], type=pa.string())],
        ),
        _case(
            "mapping-signed-integer-null-slot",
            DeclaredTypeKind.SIGNED_INTEGER.value,
            [
                {
                    "name": "v",
                    "nullable": True,
                    "semantic_type": {"kind": "signed-integer", "bits": 32},
                }
            ],
            pa.schema([pa.field("v", pa.int32(), nullable=True)]),
            [pa.array([None], type=pa.int32())],
        ),
        _case(
            "mapping-decimal-null-slot",
            DeclaredTypeKind.DECIMAL.value,
            [
                {
                    "name": "v",
                    "nullable": True,
                    "semantic_type": {"kind": "decimal", "precision": 5, "scale": 2},
                }
            ],
            pa.schema([pa.field("v", pa.decimal128(5, 2), nullable=True)]),
            [pa.array([None], type=pa.decimal128(5, 2))],
        ),
        _case(
            "mapping-float64-null-slot",
            DeclaredTypeKind.FLOAT64.value,
            [{"name": "v", "nullable": True, "semantic_type": {"kind": "float64"}}],
            pa.schema([pa.field("v", pa.float64(), nullable=True)]),
            [pa.array([None], type=pa.float64())],
        ),
        _case(
            "mapping-unsigned-integer-24-max",
            DeclaredTypeKind.UNSIGNED_INTEGER.value,
            [
                {
                    "name": "v",
                    "nullable": False,
                    "semantic_type": {"kind": "unsigned-integer", "bits": 24},
                }
            ],
            pa.schema([pa.field("v", pa.uint32(), nullable=False)]),
            [pa.array([16_777_215], type=pa.uint32())],
        ),
        _case(
            "mapping-signed-integer-24-max",
            DeclaredTypeKind.SIGNED_INTEGER.value,
            [
                {
                    "name": "v",
                    "nullable": False,
                    "semantic_type": {"kind": "signed-integer", "bits": 24},
                }
            ],
            pa.schema([pa.field("v", pa.int32(), nullable=False)]),
            [pa.array([8_388_607], type=pa.int32())],
        ),
    )


_MAPPING_CASES: tuple[MappingCase, ...] = _build_cases()

REQUIRED_CASE_IDS: frozenset[str] = frozenset(case.case_id for case in _MAPPING_CASES)


def iter_required_cases() -> tuple[MappingCase, ...]:
    return _MAPPING_CASES


def kinds_covered_by(cases: Sequence[MappingCase]) -> frozenset[str]:
    return frozenset(case.primary_kind for case in cases)
