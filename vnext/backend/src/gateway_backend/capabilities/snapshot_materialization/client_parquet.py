"""Bounded client Parquet exports of canonical Arrow, using the existing cache."""

from __future__ import annotations

from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id

import struct
import hashlib
from contextlib import ExitStack, closing
from collections.abc import Generator
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from gateway_backend.artifacts import ArtifactRef, ArtifactStorePort, ManifestVerificationError
from gateway_backend.artifacts.scratch import current_scratch
from gateway_backend.artifacts.store import ArtifactFileStorePort
from gateway_shared_kernel import DigestRef
from typing import cast

from gateway_backend.artifacts.snapshot_table_export_cache import (
    PARQUET_MEDIA_TYPE, SnapshotTableArtifactCacheKey, SnapshotTableExportCachePort,
)
from gateway_backend.capabilities.snapshot_materialization._parquet import encode_source_columns, _arrow_field
from gateway_backend.capabilities.snapshot_materialization.arrow import ArrowSnapshotTableReader
from gateway_backend.capabilities.snapshot_materialization.artifact import row_layout_digest_of
from gateway_backend.capabilities.snapshot_materialization.canonical_store import canonical_source_descriptor
from gateway_backend.capabilities.snapshot_materialization.batch import schema_with_batch_metadata
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ROW_FORMAT_PARQUET, ROW_FORMAT_CANONICAL_IPC, SnapshotTable, SnapshotTableBatchMetadata, BlankRowProvenance,
    MaterializationStage,
)
from gateway_backend.capabilities.table_access import current_kernel_context, KernelExecutionContext
from gateway_backend.capabilities.table_access.contracts import SourceColumnDescriptor

_MAX_EXPORT_BYTES = 1024**3  # Same bounded output ceiling as the canonical codec.
_LAYOUT = b"gdds.client.row_layout"
_REPOSITORY = b"gdds.client.repository_id"


def lookup_snapshot_table_parquet(
    table: SnapshotTable, *, store: ArtifactStorePort | None, repository_id: str | None,
    export_cache: SnapshotTableExportCachePort | None = None,
) -> ArtifactRef | None:
    """Validate a canonical export using metadata, before any row demand is admitted."""
    if export_cache is None or store is None or not repository_id:
        return None
    descriptor = table.descriptor
    if descriptor.materialization_stage is not MaterializationStage.FINAL or descriptor.raw_content_digest is None:
        return None
    context = current_kernel_context()
    if context is None:
        raise ValueError("client export lookup requires an operation kernel context")
    context.checkpoint()
    upper = 8192 + len(descriptor.columns) * 8192
    upper += sum((len(column.name) + len(column.display_name) + len(column.scalar_type or "")) * 128
                 for column in descriptor.columns)
    try:
        with context.memory.reserve(upper), ExitStack() as borrowed:
            source = canonical_source_descriptor(descriptor)
            key = SnapshotTableArtifactCacheKey(
                row_layout_digest_of(descriptor, source.columns, table.ordered_metadata), repository_id)
            read_session = getattr(store, "read_session", None)
            if callable(read_session):
                borrowed.enter_context(read_session())
            cached = export_cache.lookup_many((key,)).get(key)
            context.checkpoint()
            if cached is None:
                return None
            bindings = {_LAYOUT: key.row_layout_digest.value.encode(), _REPOSITORY: repository_id.encode()}
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
                        footer_reservation = context.memory.reserve(footer_bytes * 64)
                        context.checkpoint()
                        file = pq.ParquetFile(pa.BufferReader(raw))
                        schema = file.schema_arrow
                        if (file.metadata.num_rows != descriptor.row_count
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
                export_cache.discard_if_same(key, cached)
                return None
    except MemoryError:
        # Cache decoding is optional. A miss admits the ordinary row/export
        # demand under the same M; required writer reservations still fail normally.
        context.checkpoint()
        return None


def export_snapshot_table_parquet(
    table: SnapshotTable, *, store: ArtifactStorePort | None, repository_id: str | None,
    export_cache: SnapshotTableExportCachePort | None = None,
) -> ArtifactRef:
    artifact = table.artifact
    if artifact is not None and artifact.manifest.row_format == ROW_FORMAT_PARQUET:
        return artifact.manifest.row_file_refs[0]
    cached = lookup_snapshot_table_parquet(table, store=store,
        repository_id=repository_id, export_cache=export_cache)
    if cached is not None:
        return cached
    reader = table.reader
    if (not repository_id or store is None or not isinstance(reader, ArrowSnapshotTableReader)
            or not (reader.canonical_comparison_verified or reader.canonical_artifact_read_verified
                    or reader.canonical_committed_read_verified)
            or (artifact is not None and (artifact.manifest.row_format != ROW_FORMAT_CANONICAL_IPC
                                         or artifact.manifest.repository_id != repository_id))):
        raise ValueError("client export requires scoped canonical Arrow with verified authority and an artifact store")
    context = current_kernel_context()
    if context is None:
        raise ValueError("client export requires an operation kernel context")
    context.checkpoint()
    source = reader.source_descriptor()
    layout = row_layout_digest_of(table.descriptor, source.columns, table.ordered_metadata)
    if artifact is not None and artifact.row_layout_digest != layout:
        raise ValueError("client export canonical artifact layout differs from its reader")
    key = SnapshotTableArtifactCacheKey(layout, repository_id)
    schema_upper = 8192 + len(source.columns) * 8192
    schema_upper += sum((len(column.canonical_name) + len(column.display_name) + len(column.sql_type)) * 64 for column in source.columns)
    schema_upper += sum(sum(len(label) for label in (column.enum_or_set_labels or ())) * 64 for column in source.columns)
    context.memory.retain_metadata((table, "client-parquet-schema"), schema_upper)
    bindings = {_LAYOUT: key.row_layout_digest.value.encode(), _REPOSITORY: repository_id.encode()}
    metadata = SnapshotTableBatchMetadata() if table.batch_reader is None else table.batch_reader.metadata()
    schema = schema_with_batch_metadata(pa.schema([_arrow_field(column) for column in source.columns],
        metadata={b"gateway.sta.enc.v1": encode_source_columns(source.columns), **bindings}), metadata)
    isolated = reader.reopen()
    with closing(isolated), current_scratch().file(byte_limit=_MAX_EXPORT_BYTES) as (source_file, output), ExitStack() as writer_metadata:
        with isolated.arrow_stream() as stream, pq.ParquetWriter(output, schema, compression="zstd",
                write_statistics=False, use_dictionary=False, store_schema=True) as writer:
            ordered = metadata.blank_provenance is BlankRowProvenance.CANONICAL_PSEUDO_GID
            with closing(_export_batches(stream, context, ordered=ordered)) as parts:
                for chunk in parts:
                    context.checkpoint()
                    upper = chunk.nbytes * 8 + chunk.num_rows * (len(source.columns) * 512 + 1024) + 512 * 1024
                    with context.memory.reserve(upper):
                        positions = [chunk.schema.get_field_index(column.canonical_name) for column in source.columns]
                        if any(position < 0 for position in positions):
                            raise ValueError("client export input is missing a canonical column")
                        arrays = [_export_array(chunk.column(position), column)
                            for position, column in zip(positions, source.columns, strict=True)]
                        converted = pa.RecordBatch.from_arrays(arrays, schema=schema)
                        # Parquet retains per-row-group column metadata until close.
                        writer_metadata.enter_context(context.memory.reserve(len(source.columns) * 1024 + 4096 +
                            sum(len(column.canonical_name) * 8 for column in source.columns)))
                        writer.write_batch(converted)
                        del arrays, converted
                    if output.tell() > _MAX_EXPORT_BYTES:
                        raise MemoryError("client Parquet output exceeds byte budget")
                    del chunk
            context.checkpoint()
        size = output.tell()
        if size > _MAX_EXPORT_BYTES:
            raise MemoryError("client Parquet output exceeds byte budget")
        with context.memory.reserve(128 * 1024):
            output.flush()
            hasher = hashlib.sha256()
            with source_file.open_read() as published_input:
                while block := published_input.read(64 * 1024):
                    context.checkpoint()
                    hasher.update(block)
            ref = ArtifactRef(
                artifact_id=build_artifact_id(ArtifactLocation.EXPORT, "client-parquet", [
                    repository_id, key.parquet_writer_contract_version, key.row_layout_digest.value]),
                media_type=PARQUET_MEDIA_TYPE, size_bytes=size,
                raw_sha256=DigestRef("sha256:" + hasher.hexdigest()),
            )
            cast(ArtifactFileStorePort, store).put_from_path(source_file, ref,
                checkpoint=context.checkpoint, byte_limit=_MAX_EXPORT_BYTES)
        context.checkpoint()

    if export_cache is not None:
        export_cache.store_many(((key, ref),))
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
