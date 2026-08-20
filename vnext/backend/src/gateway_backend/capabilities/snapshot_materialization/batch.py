"""Public Arrow batch boundary for immutable snapshot tables."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BATCH_READER_CONTRACT_VERSION,
    BATCH_SCHEMA_METADATA_VERSION,
    SnapshotTableBatchMetadata,
    SnapshotTableBatchReader,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.table_access.contracts import (
    ParserDiagnosticCode,
    TableAccessError,
)

_METADATA_PREFIX = b"gateway-vnext.batch."
_METADATA_KEYS = {
    "batch_schema_metadata_version": _METADATA_PREFIX + b"schema_metadata_version",
    "batch_reader_contract_version": _METADATA_PREFIX + b"reader_contract_version",
    "scalar_encoding_version": _METADATA_PREFIX + b"scalar_encoding_version",
    "projection_contract_version": _METADATA_PREFIX + b"projection_contract_version",
    "ordered_contract_version": _METADATA_PREFIX + b"ordered_contract_version",
    "blank_contract_version": _METADATA_PREFIX + b"blank_contract_version",
    "artifact_contract_version": _METADATA_PREFIX + b"artifact_contract_version",
}


class BatchBoundaryError(ValueError):
    """Stable error for an invalid or closed Arrow batch boundary."""


def schema_with_batch_metadata(
    schema: pa.Schema,
    metadata: SnapshotTableBatchMetadata,
) -> pa.Schema:
    """Return a schema preserving existing metadata and adding S1 versions."""

    existing = dict(schema.metadata or {})
    values = {
        "batch_schema_metadata_version": str(metadata.batch_schema_metadata_version),
        "batch_reader_contract_version": str(metadata.batch_reader_contract_version),
        "scalar_encoding_version": str(metadata.scalar_encoding_version),
        "projection_contract_version": metadata.projection_contract_version,
        "ordered_contract_version": metadata.ordered_contract_version,
        "blank_contract_version": metadata.blank_contract_version,
        "artifact_contract_version": str(metadata.artifact_contract_version),
    }
    existing.update(
        {_METADATA_KEYS[name]: value.encode("utf-8") for name, value in values.items()}
    )
    return schema.with_metadata(existing)


def batch_metadata_from_schema(schema: pa.Schema) -> SnapshotTableBatchMetadata:
    """Decode and validate all required S1 metadata fields."""

    raw = schema.metadata or {}
    missing = [name for name, key in _METADATA_KEYS.items() if key not in raw]
    if missing:
        raise BatchBoundaryError(f"Arrow schema is missing batch metadata: {', '.join(missing)}")

    def integer(name: str) -> int:
        try:
            value = raw[_METADATA_KEYS[name]]
            if not isinstance(value, bytes):
                raise BatchBoundaryError(f"Arrow batch metadata {name} must be bytes")
            return int(value.decode("ascii"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise BatchBoundaryError(f"Arrow batch metadata {name} must be an integer") from exc

    def text(name: str) -> str:
        try:
            raw_value = raw[_METADATA_KEYS[name]]
            if not isinstance(raw_value, bytes):
                raise BatchBoundaryError(f"Arrow batch metadata {name} must be bytes")
            value = raw_value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BatchBoundaryError(f"Arrow batch metadata {name} must be UTF-8") from exc
        if value == "":
            raise BatchBoundaryError(f"Arrow batch metadata {name} must be non-empty")
        return value

    return SnapshotTableBatchMetadata(
        batch_schema_metadata_version=integer("batch_schema_metadata_version"),
        batch_reader_contract_version=integer("batch_reader_contract_version"),
        scalar_encoding_version=integer("scalar_encoding_version"),
        projection_contract_version=text("projection_contract_version"),
        ordered_contract_version=text("ordered_contract_version"),
        blank_contract_version=text("blank_contract_version"),
        artifact_contract_version=integer("artifact_contract_version"),
    )


class InMemorySnapshotTableBatchReader:
    """Small-fixture/reference reader retaining Arrow batches, never row objects."""

    def __init__(
        self,
        descriptor: SnapshotTableDescriptor,
        batches: Iterable[pa.RecordBatch],
        metadata: SnapshotTableBatchMetadata | None = None,
    ) -> None:
        self._descriptor = descriptor
        self._metadata = metadata or SnapshotTableBatchMetadata(
            scalar_encoding_version=descriptor.scalar_encoding_version,
        )
        self._batches = tuple(batches)
        self._schema = schema_with_batch_metadata(
            self._batches[0].schema if self._batches else pa.schema([]), self._metadata
        )
        for batch in self._batches:
            if not batch.schema.equals(self._batches[0].schema, check_metadata=False):
                raise BatchBoundaryError("all batches must share one Arrow schema")
        self._closed = False
        self._consumed = False

    def descriptor(self) -> SnapshotTableDescriptor:
        self._require_open()
        return self._descriptor

    def schema(self) -> pa.Schema:
        self._require_open()
        return self._schema

    def metadata(self) -> SnapshotTableBatchMetadata:
        self._require_open()
        return self._metadata

    def iter_record_batches(self) -> Iterator[pa.RecordBatch]:
        self._require_open()
        if self._consumed:
            raise BatchBoundaryError("batch reader is single-consumer and non-rewind")
        self._consumed = True
        yield from self._batches

    def close(self) -> None:
        self._closed = True

    def reopen(self) -> InMemorySnapshotTableBatchReader:
        return InMemorySnapshotTableBatchReader(self._descriptor, self._batches, self._metadata)

    def _require_open(self) -> None:
        if self._closed:
            raise TableAccessError(ParserDiagnosticCode.READER_CLOSED, "batch reader is closed")


class ParquetSnapshotTableBatchReader:
    """Streaming Parquet reader backed by immutable bytes and Arrow batches."""

    def __init__(
        self,
        descriptor: SnapshotTableDescriptor,
        parquet_bytes: bytes,
        metadata: SnapshotTableBatchMetadata | None = None,
        *,
        batch_size: int = 1024,
    ) -> None:
        if type(parquet_bytes) is not bytes or not parquet_bytes:
            raise ValueError("parquet_bytes must be non-empty bytes")
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        self._descriptor = descriptor
        self._parquet_bytes = parquet_bytes
        self._source = pa.BufferReader(parquet_bytes)
        try:
            self._file = pq.ParquetFile(self._source)
        except (OSError, pa.ArrowException, ValueError) as exc:
            raise BatchBoundaryError("invalid parquet batch source") from exc
        schema = self._file.schema_arrow
        self._metadata = metadata or batch_metadata_from_schema(schema)
        self._schema = schema_with_batch_metadata(schema, self._metadata)
        self._batch_size = batch_size
        self._closed = False
        self._consumed = False

    def descriptor(self) -> SnapshotTableDescriptor:
        self._require_open()
        return self._descriptor

    def schema(self) -> pa.Schema:
        self._require_open()
        return self._schema

    def metadata(self) -> SnapshotTableBatchMetadata:
        self._require_open()
        return self._metadata

    def iter_record_batches(self) -> Iterator[pa.RecordBatch]:
        self._require_open()
        if self._consumed:
            raise BatchBoundaryError("batch reader is single-consumer and non-rewind")
        self._consumed = True
        try:
            yield from pa.RecordBatchReader.from_batches(
                self._schema,
                self._file.iter_batches(batch_size=self._batch_size),
            )
        except (OSError, pa.ArrowException, ValueError) as exc:
            raise BatchBoundaryError("parquet batch iteration failed") from exc

    def close(self) -> None:
        self._closed = True
        self._source.close()

    def reopen(self) -> ParquetSnapshotTableBatchReader:
        return ParquetSnapshotTableBatchReader(
            self._descriptor,
            self._parquet_bytes,
            self._metadata,
            batch_size=self._batch_size,
        )

    def _require_open(self) -> None:
        if self._closed:
            raise TableAccessError(ParserDiagnosticCode.READER_CLOSED, "batch reader is closed")


def assert_public_batch_reader(reader: object) -> SnapshotTableBatchReader:
    """Validate an injected reader at a provider seam without opening rows."""

    if not isinstance(reader, SnapshotTableBatchReader):
        raise TypeError("reader must implement SnapshotTableBatchReader")
    metadata = reader.metadata()
    if metadata.batch_reader_contract_version != BATCH_READER_CONTRACT_VERSION:
        raise BatchBoundaryError("unsupported batch reader contract version")
    if metadata.batch_schema_metadata_version != BATCH_SCHEMA_METADATA_VERSION:
        raise BatchBoundaryError("unsupported batch schema metadata version")
    return reader
