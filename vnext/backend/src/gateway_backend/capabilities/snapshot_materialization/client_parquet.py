"""Bounded client Parquet exports of canonical Arrow, using the existing cache."""

from __future__ import annotations

import struct
import hashlib
import tempfile
from contextlib import ExitStack, closing
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from gateway_backend.artifacts import ArtifactRef, ArtifactStorePort, ManifestVerificationError, put_with_built_ref
from gateway_backend.artifacts.snapshot_table_export_cache import (
    PARQUET_MEDIA_TYPE, SnapshotTableArtifactCacheKey, SnapshotTableExportCachePort,
)
from gateway_backend.capabilities.snapshot_materialization._parquet import encode_source_columns, _arrow_field
from gateway_backend.capabilities.snapshot_materialization.arrow import ArrowSnapshotTableReader
from gateway_backend.capabilities.snapshot_materialization.batch import schema_with_batch_metadata
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ROW_FORMAT_PARQUET, ROW_FORMAT_CANONICAL_IPC, SnapshotTable, SnapshotTableBatchMetadata, BlankRowProvenance,
)
from gateway_backend.capabilities.table_access import current_kernel_context, KernelExecutionContext
from gateway_backend.capabilities.table_access.contracts import SourceColumnDescriptor

_MAX_EXPORT_BYTES = 1024**3  # Same bounded output ceiling as the canonical codec.
_LAYOUT = b"gdds.client.row_layout"
_REPOSITORY = b"gdds.client.repository_id"


def export_snapshot_table_parquet(
    table: SnapshotTable, *, store: ArtifactStorePort | None, repository_id: str | None,
    export_cache: SnapshotTableExportCachePort | None = None,
) -> ArtifactRef:
    artifact = table.artifact
    if artifact is None:
        raise ValueError("client export requires a bound snapshot artifact")
    if artifact.manifest.row_format == ROW_FORMAT_PARQUET:
        return artifact.manifest.row_file_refs[0]
    if (artifact.manifest.row_format != ROW_FORMAT_CANONICAL_IPC or not repository_id
            or artifact.manifest.repository_id != repository_id or store is None
            or not isinstance(table.reader, ArrowSnapshotTableReader)):
        raise ValueError("client export requires scoped canonical Arrow and an artifact store")
    context = current_kernel_context()
    if context is None:
        raise ValueError("client export requires an operation kernel context")
    context.checkpoint()
    key = SnapshotTableArtifactCacheKey(artifact.row_layout_digest, repository_id)
    source = table.reader.source_descriptor()
    schema_upper = 8192 + len(source.columns) * 8192
    schema_upper += sum((len(column.canonical_name) + len(column.display_name) + len(column.sql_type)) * 64 for column in source.columns)
    schema_upper += sum(sum(len(label) for label in (column.enum_or_set_labels or ())) * 64 for column in source.columns)
    context.memory.retain_metadata((table, "client-parquet-schema"), schema_upper)
    bindings = {_LAYOUT: key.row_layout_digest.value.encode(), _REPOSITORY: repository_id.encode()}
    if export_cache is not None:
        try:
            cached = export_cache.lookup_many((key,)).get(key)
        except (InterruptedError, TimeoutError, MemoryError):
            raise
        except Exception:
            cached = None
        if cached is not None:
            try:
                if cached.media_type != PARQUET_MEDIA_TYPE or cached.size_bytes > _MAX_EXPORT_BYTES:
                    raise ValueError("cached client artifact is not bounded Parquet")
                with context.memory.reserve(cached.size_bytes * 2 + 4096 + len(source.columns) * 8192):
                    file = None
                    raw = None
                    schema = None
                    footer_reservation = None
                    try:
                        raw = store.locate(cached)
                        if len(raw) < 12 or raw[:4] != b"PAR1" or raw[-4:] != b"PAR1":
                            raise ValueError("cached client Parquet footer is invalid")
                        footer_bytes = struct.unpack_from("<I", raw, len(raw) - 8)[0]
                        if footer_bytes > len(raw) - 12:
                            raise ValueError("cached client Parquet footer is truncated")
                        # Thrift row-group/column vectors, paths, schema and KV
                        # objects expand independently of compressed data pages.
                        # Reserve against the encoded footer before C++/Python
                        # metadata decoding, using a conservative object envelope.
                        footer_reservation = context.memory.reserve(footer_bytes * 64)
                        file = pq.ParquetFile(pa.BufferReader(raw))
                        schema = file.schema_arrow
                        if (file.metadata.num_rows != table.descriptor.row_count
                                or not schema.equals(pa.schema([_arrow_field(column) for column in source.columns]), check_metadata=False)
                                or any((schema.metadata or {}).get(name) != value for name, value in bindings.items())
                                or (schema.metadata or {}).get(b"gateway.sta.enc.v1") != encode_source_columns(source.columns)):
                            raise ValueError("cached client Parquet layout binding differs")
                    finally:
                        if file is not None:
                            file.close()
                        del file, raw, schema
                        if footer_reservation is not None:
                            footer_reservation.close()
                context.checkpoint()
                return cached
            except (InterruptedError, TimeoutError, MemoryError):
                raise
            except (ValueError, OSError, ManifestVerificationError, pa.ArrowException):
                context.checkpoint()
                try:
                    export_cache.discard_many((key,))
                except (InterruptedError, TimeoutError, MemoryError):
                    raise
                except Exception:
                    pass
    metadata = SnapshotTableBatchMetadata() if table.batch_reader is None else table.batch_reader.metadata()
    schema = schema_with_batch_metadata(pa.schema([_arrow_field(column) for column in source.columns],
        metadata={b"gateway.sta.enc.v1": encode_source_columns(source.columns), **bindings}), metadata)
    isolated = table.reader.reopen()
    with tempfile.TemporaryDirectory(prefix="gateway-client-parquet-") as directory, ExitStack() as writer_metadata:
        path = Path(directory) / "rows.parquet"
        try:
            with isolated.arrow_stream() as stream, pq.ParquetWriter(path, schema, compression="zstd",
                    write_statistics=False, use_dictionary=False, store_schema=True) as writer:
                ordered = metadata.blank_provenance is BlankRowProvenance.CANONICAL_PSEUDO_GID
                with closing(_export_batches(stream, context, ordered=ordered)) as parts:
                    for chunk in parts:
                        context.checkpoint()
                        upper = chunk.nbytes * 8 + chunk.num_rows * (len(source.columns) * 512 + 1024) + 512 * 1024
                        with context.memory.reserve(upper):
                            arrays = [_export_array(chunk.column(i), column) for i, column in enumerate(source.columns)]
                            converted = pa.RecordBatch.from_arrays(arrays, schema=schema)
                            # Parquet retains per-row-group column metadata until close.
                            writer_metadata.enter_context(context.memory.reserve(len(source.columns) * 1024 + 4096 +
                                sum(len(column.canonical_name) * 8 for column in source.columns)))
                            writer.write_batch(converted)
                            del arrays, converted
                        if path.stat().st_size > _MAX_EXPORT_BYTES:
                            raise MemoryError("client Parquet output exceeds byte budget")
                        del chunk
                context.checkpoint()
            size = path.stat().st_size
            if size > _MAX_EXPORT_BYTES:
                raise MemoryError("client Parquet output exceeds byte budget")
            with context.memory.reserve(size * 2 + 128 * 1024):
                raw = path.read_bytes()
                context.checkpoint()
                ref = put_with_built_ref(store, raw, artifact_id="client-parquet-" + hashlib.sha256(
                    f"{repository_id}:{key.parquet_writer_contract_version}:{key.row_layout_digest.value}".encode()).hexdigest(), media_type=PARQUET_MEDIA_TYPE)
                del raw
            context.checkpoint()
        finally:
            isolated.close()
    if export_cache is not None:
        try:
            export_cache.store_many(((key, ref),))
        except (InterruptedError, TimeoutError, MemoryError):
            raise
        except Exception:
            pass
    context.checkpoint()
    return ref


def _export_array(array: pa.Array, column: SourceColumnDescriptor) -> pa.Array:
    kind = None if column.declared_type is None else column.declared_type.kind.value
    if column.logical_type.value == "set":
        split = pc.split_pattern(array, pattern=",")
        return pc.if_else(pc.equal(array, ""), pa.scalar([], type=pa.list_(pa.string())), split)
    if kind in ("float32", "float64"):
        width, code = (4, "<I") if kind == "float32" else (8, "<Q")
        buffer = array.buffers()[1]
        values: list[Any] = [None if not array[i].is_valid else
            format(struct.unpack_from(code, buffer, (array.offset + i) * width)[0], "08x" if width == 4 else "016x")
            for i in range(len(array))]
        return pa.array(values, type=pa.string())
    if kind in ("boolean", "binary", "bit"):
        return array
    return pc.cast(array, pa.string(), safe=True)


def _export_batches(
    stream: pa.RecordBatchReader, context: KernelExecutionContext, *, ordered: bool,
) -> Generator[pa.RecordBatch, None, None]:
    if ordered:
        backing = stream.read_all()
        # Business ordered reads use numeric no; IPC physical numeric gid is
        # independent. Only a bounded 1024-row gather is copied at a time.
        with context.memory.reserve(backing.num_rows * 24 + len(backing.columns) * 4096 + 8192):
            order = pc.sort_indices(backing, sort_keys=[("no", "ascending")])
            for start in range(0, backing.num_rows, 1024):
                context.checkpoint()
                count = min(1024, backing.num_rows - start)
                with context.memory.reserve(backing.nbytes * 2 + count * len(backing.columns) * 64 + 8192):
                    gathered = backing.take(order.slice(start, count))
                    chunk = gathered.to_batches(max_chunksize=1024)[0]
                    yield chunk
                    del chunk, gathered
            del order
        del backing
    else:
        for batch in stream:
            for start in range(0, batch.num_rows, 1024):
                context.checkpoint()
                yield batch.slice(start, min(1024, batch.num_rows - start))
    context.checkpoint()
