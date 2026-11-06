"""Canonical IPC publication and context-managed borrowed table readers.

Only verified internal producers write this store. Integrity and bound profile
validation do not turn this API into an external IPC business import validator.
Operation callers own controls and release borrowed batches before handle close.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

import pyarrow as pa
from gateway_compute._native import _encode_canonical_ipc_native, _inspect_canonical_ipc_native

from gateway_backend.artifacts.canonical_table_store import (
    CANONICAL_IPC_MEDIA_TYPE,
    CanonicalTableKey,
)
from gateway_backend.artifacts.store import (
    ArtifactBufferStorePort,
    ManifestVerificationError,
    put_with_built_ref,
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
from gateway_backend.capabilities.storage_projection.contracts import STORAGE_PROJECTION_VERSION
from gateway_backend.capabilities.table_access.contracts import NeverCancel


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


def _check_descriptor_budget(descriptor: SnapshotTableDescriptor, budgets: dict[str, int]) -> None:
    if len(descriptor.columns) > budgets["max_columns"]:
        raise MemoryError("canonical descriptor column limit exceeded")
    size = 4096 + len(descriptor.columns) * 4096
    size += (len(descriptor.table_name) + len(descriptor.display_table_name)) * 32
    for column in descriptor.columns:
        size += (len(column.name) + len(column.display_name) + len(column.scalar_type or "")) * 32
        if size > budgets["max_descriptor_bytes"] or size * 8 > budgets["max_codec_peak_bytes"]:
            raise MemoryError("canonical descriptor byte limit exceeded")


class ArtifactReadHandle:
    """Independent reader lifetime; batches/streams are borrowed within it."""

    def __init__(
        self, store: ArtifactBufferStorePort, ref: ArtifactRef,
        descriptor: SnapshotTableDescriptor, budgets: dict[str, int],
    ) -> None:
        self._stack = ExitStack()
        self._reader: pa.ipc.RecordBatchFileReader | None = None
        self._source: pa.BufferReader | None = None
        self._descriptor = descriptor
        self._closed = False
        self._borrowers: list[pa.RecordBatchReader] = []
        try:
            buffer = self._stack.enter_context(store.open_buffer(ref))
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
                    canonical_columns(descriptor), bridge, NeverCancel(), budgets,
                )
            finally:
                bridge.close()
            del bridge, array
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
        except BaseException:
            self.close()
            raise

    @property
    def schema(self) -> pa.Schema:
        self._require_open()
        return self._schema

    def iter_batches(self) -> Iterator[pa.RecordBatch]:
        self._require_open()
        assert self._reader is not None
        for index in range(self._reader.num_record_batches):
            self._require_open()
            batch = self._reader.get_batch(index)
            batch.validate(full=True)
            yield batch.select(self._indices)

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
        for stream in self._borrowers:
            stream.close()
        self._borrowers.clear()
        self._reader = None
        if self._source is not None:
            self._source.close()
            self._source = None
        self._stack.close()

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

    def put(self, stream: pa.RecordBatchReader, bound_descriptor: SnapshotTableDescriptor) -> ArtifactRef:
        _check_descriptor_budget(bound_descriptor, self._budgets)
        key = canonical_table_key(self._repository_id, bound_descriptor)
        def bound_batches() -> Iterator[pa.RecordBatch]:
            rows = 0
            for batch in stream:
                rows += batch.num_rows
                if rows > bound_descriptor.row_count:
                    raise ValueError("canonical row count binding mismatch")
                yield batch
            if rows != bound_descriptor.row_count:
                raise ValueError("canonical row count binding mismatch")

        bound_stream = pa.RecordBatchReader.from_batches(stream.schema, bound_batches())
        try:
            raw = _encode_canonical_ipc_native(
                canonical_columns(bound_descriptor), bound_stream, NeverCancel(), self._budgets,
            )
        finally:
            bound_stream.close()
        return put_with_built_ref(
            self._store, raw, artifact_id=key.artifact_id, media_type=CANONICAL_IPC_MEDIA_TYPE,
        )

    def open(self, ref: ArtifactRef, bound_descriptor: SnapshotTableDescriptor) -> ArtifactReadHandle:
        _check_descriptor_budget(bound_descriptor, self._budgets)
        key = canonical_table_key(self._repository_id, bound_descriptor)
        if ref.media_type != CANONICAL_IPC_MEDIA_TYPE or ref.artifact_id != key.artifact_id:
            raise ManifestVerificationError("canonical content identity binding mismatch")
        if ref.size_bytes > self._budgets["max_input_bytes"]:
            raise MemoryError("canonical IPC input byte limit exceeded")
        return ArtifactReadHandle(self._store, ref, bound_descriptor, self._budgets)
