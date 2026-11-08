"""Canonical IPC publication and context-managed borrowed table readers.

Only verified internal producers write this store. Integrity and bound profile
validation do not turn this API into an external IPC business import validator.
Operation callers own controls and release borrowed batches before handle close.
"""

from __future__ import annotations

import struct
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager, nullcontext
from typing import Any

import pyarrow as pa
from gateway_compute._native import (
    _canonical_comparison_profile_native, _encode_canonical_ipc_native,
    _inspect_canonical_ipc_native,
)
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts.canonical_table_store import (
    CANONICAL_IPC_MEDIA_TYPE,
    CanonicalTableKey,
)
from gateway_backend.artifacts.store import (
    ArtifactBufferStorePort,
    ManifestVerificationError,
)
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    SnapshotTableDescriptor,
    enum_set_labels_for_sql_spelling,
    normalize_sql_type_spelling,
)
from gateway_backend.capabilities.snapshot_materialization.sql_declared_types import (
    try_declared_type_for_sql_spelling,
)
from gateway_backend.capabilities.table_rules.contracts import STORAGE_PROJECTION_VERSION
from gateway_backend.capabilities.table_access.contracts import NeverCancel
from gateway_backend.capabilities.table_access import current_kernel_context, KernelMemoryLimit


def canonical_table_key(repository_id: str, descriptor: SnapshotTableDescriptor) -> CanonicalTableKey:
    if descriptor.raw_content_digest is None:
        raise ValueError("canonical table requires a bound business digest")
    return CanonicalTableKey(
        repository_id, STORAGE_PROJECTION_VERSION, descriptor.business_schema_digest,
        descriptor.row_count, descriptor.raw_content_digest,
    )


def canonical_columns(descriptor: SnapshotTableDescriptor) -> list[dict[str, Any]]:
    """Use the existing declaration owners; export order remains outside IPC."""
    result: list[dict[str, Any]] = []
    for ordinal, column in enumerate(descriptor.columns):
        sql_type = normalize_sql_type_spelling(column.scalar_type or "UNKNOWN")
        declared = try_declared_type_for_sql_spelling(sql_type)
        enum_set = enum_set_labels_for_sql_spelling(sql_type)
        logical = "json" if sql_type == "JSON" else "standard"
        labels = None
        if enum_set is not None:
            logical, values = enum_set
            logical = logical.lower()
            labels = list(values)
            if logical == "set":
                declared = None
        if declared is None and logical != "set":
            raise ValueError("canonical column has no supported declaration")
        result.append({
            "canonical_name": column.name, "display_name": column.display_name,
            "ordinal": ordinal, "sql_type": sql_type, "logical_type": logical,
            "nullable": column.nullable, "labels": labels,
            "declared_type": None if declared is None else {
                "kind": declared.kind.value, "bits": declared.bits,
                "precision": declared.precision, "scale": declared.scale,
                "bit_width": declared.bit_width,
            },
        })
    return result


def canonical_comparison_profile(
    descriptor: SnapshotTableDescriptor, input_schema: pa.Schema, *,
    metadata_budget_bytes: int,
) -> tuple[pa.Schema, tuple[int, ...]]:
    """Ask the canonical mapping owner for a schema-only comparison view."""
    context = current_kernel_context()
    if context is None:
        raise ValueError("canonical comparison profile requires an operation context")
    from gateway_backend.capabilities.snapshot_materialization.arrow import operation_codec_budgets

    budgets = operation_codec_budgets()
    budgets["max_codec_peak_bytes"] = metadata_budget_bytes
    check_canonical_descriptor_budget(descriptor, budgets)
    schema, indices = _canonical_comparison_profile_native(
        canonical_columns(descriptor), input_schema, context.cancel_probe,
        budgets, context.deadline_monotonic,
    )
    return schema, tuple(indices)


def check_canonical_descriptor_budget(descriptor: SnapshotTableDescriptor, budgets: dict[str, int]) -> int:
    if max(len(descriptor.columns), len(descriptor.primary_key_columns)) > budgets["max_columns"]:
        raise MemoryError("canonical descriptor column limit exceeded")
    size = 4096 + len(descriptor.columns) * 4096
    size += (len(descriptor.table_name) + len(descriptor.display_table_name)) * 32
    for name in descriptor.primary_key_columns:
        size += len(name) * 32 + 128
    for column in descriptor.columns:
        size += (len(column.name) + len(column.display_name) + len(column.scalar_type or "")) * 32
        if size > budgets["max_descriptor_bytes"] or size * 8 > budgets["max_codec_peak_bytes"]:
            raise MemoryError("canonical descriptor byte limit exceeded")
    if size > budgets["max_descriptor_bytes"] or size * 8 > budgets["max_codec_peak_bytes"]:
        raise MemoryError("canonical descriptor byte limit exceeded")
    return size


class ArtifactReadHandle:
    """Independent reader lifetime; batches/streams are borrowed within it."""

    def __init__(
        self, store: ArtifactBufferStorePort, ref: ArtifactRef,
        descriptor: SnapshotTableDescriptor, budgets: dict[str, int],
    ) -> None:
        self._stack = ExitStack()
        self._reader: pa.ipc.RecordBatchFileReader | None = None
        self._source: pa.BufferReader | None = None
        self._schema: pa.Schema | None = None
        self._indices: tuple[int, ...] = ()
        self._descriptor = descriptor
        self._closed = False
        self._borrowers: list[pa.RecordBatchReader] = []
        self._context = current_kernel_context()
        try:
            checkpoint = None if self._context is None else self._context.checkpoint
            if self._context is not None:
                self._context.checkpoint()
                mapping_key = ("canonical-mapping", id(self))
                self._stack.enter_context(self._context.memory.reserve(ref.size_bytes, backing=mapping_key))
                metadata = 4096 + len(descriptor.columns) * 4096 + ((descriptor.row_count + 65535) // 65536) * (len(descriptor.columns) * 256 + 4096)
                self._stack.enter_context(self._context.memory.reserve(metadata))
                self._context.resources.callback(self.close)
            buffer = self._stack.enter_context(store.open_buffer(ref, checkpoint=checkpoint))
            if self._context is not None:
                self._context.memory.register_mapping(mapping_key, buffer)
                budgets = {**budgets, "max_codec_peak_bytes": min(budgets["max_codec_peak_bytes"], self._context.memory.available_bytes)}
                self._context.memory.record_stage_admission("canonical-ipc-inspect", budgets["max_codec_peak_bytes"])
            # LargeBinary is only a safe zero-copy buffer bridge to A preflight.
            array = pa.Array.from_buffers(pa.large_binary(), 1, [
                None, pa.py_buffer(struct.pack("<qq", 0, len(buffer))), buffer,
            ])
            bridge = pa.RecordBatchReader.from_batches(
                pa.schema([pa.field("ipc", pa.large_binary())]),
                [pa.record_batch([array], names=["ipc"])],
            )
            try:
                rows = _inspect_canonical_ipc_native(
                    canonical_columns(descriptor), bridge,
                    NeverCancel() if self._context is None else self._context.cancel_probe, budgets,
                    None if self._context is None else self._context.deadline_monotonic,
                )
            finally:
                bridge.close()
            del bridge, array
            if checkpoint is not None:
                checkpoint()
            if rows != descriptor.row_count:
                raise ManifestVerificationError("canonical row count binding mismatch")
            self._source = pa.BufferReader(buffer)
            self._reader = pa.ipc.open_file(self._source)
            self._indices = tuple(
                self._reader.schema.get_field_index(column.name) for column in descriptor.columns
            )
            self._schema = pa.schema(
                [self._reader.schema.field(index) for index in self._indices],
                metadata=self._reader.schema.metadata,
            )
        except BaseException as exc:
            self.close()
            if self._context is not None:
                self._context.checkpoint()
                if isinstance(exc, MemoryError):
                    raise KernelMemoryLimit("canonical reader operation memory reservation exceeded") from exc
            raise

    @property
    def schema(self) -> pa.Schema:
        self._require_open()
        assert self._schema is not None
        return self._schema

    def iter_batches(self) -> Iterator[pa.RecordBatch]:
        self._require_open()
        assert self._reader is not None
        for index in range(self._reader.num_record_batches):
            self._require_open()
            batch = self._reader.get_batch(index)
            batch.validate(full=True)
            if self._context is not None:
                self._context.checkpoint()
            yield batch.select(self._indices)
        if self._context is not None:
            self._context.checkpoint()

    @contextmanager
    def borrow_stream(self) -> Iterator[pa.RecordBatchReader]:
        """Release the C Stream borrower before closing its containing handle."""
        self._require_open()
        stream = pa.RecordBatchReader.from_batches(self.schema, self.iter_batches())
        self._borrowers.append(stream)
        try:
            yield stream
        finally:
            stream.close()
            if stream in self._borrowers:
                self._borrowers.remove(stream)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        resources = ExitStack()
        resources.callback(self._stack.close)
        if self._source is not None:
            resources.callback(self._source.close)
        for stream in self._borrowers:
            resources.callback(stream.close)
        self._borrowers.clear()
        self._reader = None
        self._source = None
        self._schema = None
        self._indices = ()
        resources.close()

    def _require_open(self) -> None:
        if self._closed:
            raise ValueError("canonical artifact reader is closed")

    def __enter__(self) -> ArtifactReadHandle:
        self._require_open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class CanonicalTableStore:
    def __init__(
        self, store: ArtifactBufferStorePort, *, repository_id: str, budgets: dict[str, int],
    ) -> None:
        self._store = store
        self._repository_id = repository_id
        self._budgets = dict(budgets)

    @property
    def repository_id(self) -> str:
        return self._repository_id

    def put(
        self, stream: pa.RecordBatchReader, bound_descriptor: SnapshotTableDescriptor, *,
        before_write: Callable[[CanonicalTableKey, ArtifactRef], None] | None = None,
    ) -> ArtifactRef:
        context = current_kernel_context()
        metadata_size = check_canonical_descriptor_budget(bound_descriptor, self._budgets)
        if context is not None:
            context.memory.retain_metadata(bound_descriptor, metadata_size)
        budgets = self._budgets if context is None else {**self._budgets,
            "max_codec_peak_bytes": min(self._budgets["max_codec_peak_bytes"], context.memory.available_bytes)}
        if context is not None:
            context.checkpoint()
            context.memory.record_stage_admission("canonical-ipc-encode", budgets["max_codec_peak_bytes"])
        check_canonical_descriptor_budget(bound_descriptor, budgets)
        key = canonical_table_key(self._repository_id, bound_descriptor)
        def bound_batches() -> Iterator[pa.RecordBatch]:
            rows = 0
            for batch in stream:
                if context is not None:
                    context.checkpoint()
                rows += batch.num_rows
                if rows > bound_descriptor.row_count:
                    raise ValueError("canonical row count binding mismatch")
                yield batch
            if rows != bound_descriptor.row_count:
                raise ValueError("canonical row count binding mismatch")
            if context is not None:
                context.checkpoint()

        bound_stream = pa.RecordBatchReader.from_batches(stream.schema, bound_batches())
        try:
            raw = _encode_canonical_ipc_native(
                canonical_columns(bound_descriptor), bound_stream,
                NeverCancel() if context is None else context.cancel_probe, budgets,
                None if context is None else context.deadline_monotonic,
            )
        except BaseException as exc:
            if context is not None:
                context.checkpoint()
                if isinstance(exc, MemoryError):
                    raise KernelMemoryLimit("canonical codec operation memory reservation exceeded") from exc
            raise
        finally:
            bound_stream.close()
        reservation = nullcontext() if context is None else context.memory.reserve(len(raw), backing=("python-bytes", id(raw)))
        with reservation:
            if context is not None:
                context.checkpoint()
                context.memory.record_stage_admission("canonical-ipc-publication", len(raw))
            ref = ArtifactRef(key.artifact_id, CANONICAL_IPC_MEDIA_TYPE, len(raw), raw_blob_digest(raw))
            if before_write is not None:
                before_write(key, ref)
            if context is not None:
                context.checkpoint()
            published = self._store.put(raw, ref)
            if context is not None:
                context.checkpoint()
            return published

    def open(self, ref: ArtifactRef, bound_descriptor: SnapshotTableDescriptor) -> ArtifactReadHandle:
        metadata_size = check_canonical_descriptor_budget(bound_descriptor, self._budgets)
        context = current_kernel_context()
        if context is not None:
            context.memory.retain_metadata(bound_descriptor, metadata_size)
        key = canonical_table_key(self._repository_id, bound_descriptor)
        if ref.media_type != CANONICAL_IPC_MEDIA_TYPE or ref.artifact_id != key.artifact_id:
            raise ManifestVerificationError("canonical content identity binding mismatch")
        if ref.size_bytes > self._budgets["max_input_bytes"]:
            raise MemoryError("canonical IPC input byte limit exceeded")
        return ArtifactReadHandle(self._store, ref, bound_descriptor, self._budgets)
