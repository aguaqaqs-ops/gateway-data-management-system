"""Decode the selected client file in physical order using its same-side schema.

This is an inverse of the existing client export representation. Canonical scalar
framing and validation remain in the native comparison encoder.
"""
from __future__ import annotations

import re
import struct
from collections.abc import Iterator
from contextlib import contextmanager

import pyarrow as pa
import pyarrow.compute as pc  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from gateway_shared_kernel import raw_blob_digest
from gateway_backend.artifacts import ArtifactRef, ArtifactStorePort
from gateway_backend.capabilities.snapshot_materialization._parquet import _arrow_field, encode_source_columns
from gateway_backend.capabilities.snapshot_materialization.canonical_store import (
    canonical_comparison_profile, canonical_source_descriptor,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import SnapshotTableDescriptor
from gateway_backend.capabilities.table_access import current_kernel_context
from gateway_backend.capabilities.table_access.contracts import SourceColumnDescriptor

_INTEGER = re.compile(r"(?:0|-[1-9][0-9]*|[1-9][0-9]*)\Z")


def _source_type(column: SourceColumnDescriptor) -> pa.DataType:
    kind = None if column.declared_type is None else column.declared_type.kind.value
    return {"signed-integer": pa.int64(), "unsigned-integer": pa.uint64(),
        "float32": pa.float32(), "float64": pa.float64(), "boolean": pa.bool_(),
        "binary": pa.binary(), "bit": pa.binary()}.get(kind or "", pa.string())


def _decode(array: pa.Array, column: SourceColumnDescriptor, target: pa.DataType) -> pa.Array:
    kind = None if column.declared_type is None else column.declared_type.kind.value
    if column.logical_type.value == "set":
        return pc.binary_join(array, ",")
    if kind in {"signed-integer", "unsigned-integer"}:
        # Accept only the exact decimal spelling emitted by the export owner.
        # Same-side SQL width/range validation remains in native encode_cell.
        values = array.to_pylist()
        if any(value is not None and (type(value) is not str or _INTEGER.fullmatch(value) is None)
               for value in values):
            raise ValueError("client integer representation is invalid")
        return pc.cast(array, target, safe=True)
    if kind in {"float32", "float64"}:
        width, code = (8, ">f") if kind == "float32" else (16, ">d")
        values = []
        for value in array.to_pylist():
            if value is None:
                values.append(None)
                continue
            if type(value) is not str or re.fullmatch(f"[0-9a-f]{{{width}}}", value) is None:
                raise ValueError("client float representation is invalid")
            values.append(struct.unpack(code, bytes.fromhex(value))[0])
        return pa.array(values, type=target)
    return array if array.type == target else pc.cast(array, target, safe=True)


@contextmanager
def final_parquet_batches(
    descriptor: SnapshotTableDescriptor, ref: ArtifactRef, store: ArtifactStorePort,
) -> Iterator[Iterator[pa.RecordBatch]]:
    """Reserve before raw/footer/group decode; yield row groups in file order."""
    context = current_kernel_context()
    if context is None:
        raise RuntimeError("final Parquet scan requires the operation context")
    context.checkpoint()
    metadata_upper = 1024 * 1024 + len(descriptor.columns) * 65536 + sum(
        (len(column.name) + len(column.display_name) + len(column.scalar_type or "")) * 1024
        for column in descriptor.columns)
    with context.memory.reserve(2 * ref.size_bytes + metadata_upper):
        raw = store.locate(ref)
        if len(raw) != ref.size_bytes or raw_blob_digest(raw) != ref.raw_sha256:
            raise ValueError("final Parquet raw identity differs")
        if len(raw) < 12 or raw[:4] != b"PAR1" or raw[-4:] != b"PAR1":
            raise ValueError("invalid final Parquet")
        footer = struct.unpack_from("<I", raw, len(raw) - 8)[0]
        if footer > len(raw) - 12:
            raise ValueError("invalid final Parquet footer")
        with context.memory.reserve(footer * 64):
            with pq.ParquetFile(pa.BufferReader(raw)) as file:
                source = canonical_source_descriptor(descriptor)
                physical = pa.schema([_arrow_field(column) for column in source.columns])
                if (not file.schema_arrow.equals(physical, check_metadata=False)
                        or (file.schema_arrow.metadata or {}).get(b"gateway.sta.enc.v1") != encode_source_columns(source.columns)
                        or file.metadata.num_rows != descriptor.row_count):
                    raise ValueError("final Parquet differs from same-side descriptor")
                decoded_source = pa.schema([pa.field(column.canonical_name, _source_type(column),
                    nullable=column.nullable) for column in source.columns])
                profile, indices = canonical_comparison_profile(descriptor, decoded_source,
                    metadata_budget_bytes=metadata_upper)
                # Decode one row group at a time, but admit the largest up front
                # so the native occurrence state cannot consume its headroom.
                upper = max((sum(file.metadata.row_group(group).column(index).total_uncompressed_size
                    for index in range(file.metadata.num_columns)) * 16
                    + file.metadata.row_group(group).num_rows * (len(source.columns) * 256 + 1024)
                    for group in range(file.num_row_groups)), default=0) + 65536
                with context.memory.reserve(upper):
                    def batches() -> Iterator[pa.RecordBatch]:
                        emitted = 0
                        for group in range(file.num_row_groups):
                            context.checkpoint()
                            for batch in file.iter_batches(batch_size=1024, row_groups=[group], use_threads=False):
                                context.checkpoint()
                                arrays = [_decode(batch.column(index), source.columns[index], profile.field(position).type)
                                    for position, index in enumerate(indices)]
                                output = pa.RecordBatch.from_arrays(arrays, schema=profile)
                                emitted += output.num_rows
                                yield output
                        if emitted != descriptor.row_count:
                            raise ValueError("final Parquet scan row count differs")
                        context.checkpoint()
                    yield batches()
