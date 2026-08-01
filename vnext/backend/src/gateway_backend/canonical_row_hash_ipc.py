"""Canonical Row Hash Arrow IPC write, owner validation, and ordinary reopen."""

from __future__ import annotations

import json
from collections.abc import Sequence

import pyarrow as pa

from gateway_shared_kernel import (
    DigestKind,
    DigestRef,
    canonicalize_identifier,
    canonicalize_jcs,
    semantic_digest,
    unordered_row_hashes_content_digest,
    unordered_row_hashes_content_digest_from_sorted_row_buffer,
)

from gateway_backend.artifacts import ArtifactRef, ArtifactStorePort, put_with_built_ref
from gateway_backend.canonical_row_hash_artifact import (
    CANONICAL_ROW_HASHES_MEDIA_TYPE,
    CANONICAL_ROW_HASH_BOUNDARY_VERSION,
    CanonicalRowHashesArtifactMetadata,
)

ROW_HASH_FIELD_NAME = "row_hash"
ROW_HASH_BYTE_WIDTH = 32
CANONICAL_ROW_HASH_OUTPUT_SCHEMA = pa.schema(
    [pa.field(ROW_HASH_FIELD_NAME, pa.binary(ROW_HASH_BYTE_WIDTH), nullable=False)]
)
MEDIA_TYPE = CANONICAL_ROW_HASHES_MEDIA_TYPE
IPC_STREAM_EOS_MARKER = b"\x00\x00\x00\x00"
_RESULT_EXPECTED_FIELDS = frozenset(
    {"boundary_version", "table_schema_digest", "row_count", "raw_content_digest"}
)


class CanonicalRowHashIpcError(ValueError):
    """Canonical row-hash IPC write, read, or verification failed."""


_ARROW_PUBLIC_BOUNDARY_ERRORS = (pa.ArrowException, OSError, ValueError)


def write_row_hash_ipc_stream(reader: pa.RecordBatchReader) -> bytes:
    """Serialize a canonical row-hash output stream to Arrow IPC stream bytes."""

    try:
        _assert_reader_schema(reader.schema)
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, CANONICAL_ROW_HASH_OUTPUT_SCHEMA) as writer:
            for batch in reader:
                if not batch.schema.equals(CANONICAL_ROW_HASH_OUTPUT_SCHEMA, check_metadata=True):
                    raise CanonicalRowHashIpcError("batch schema does not match canonical output")
                _assert_batch_has_no_null_row_hashes(batch)
                writer.write_batch(batch)
        return bytes(sink.getvalue().to_pybytes())
    except CanonicalRowHashIpcError:
        raise
    except _ARROW_PUBLIC_BOUNDARY_ERRORS:
        raise CanonicalRowHashIpcError("canonical row-hash ipc write failed") from None


def open_row_hash_ipc_stream(raw_bytes: bytes) -> pa.RecordBatchReader:
    """Open finalized Arrow IPC bytes after parsing the fixed output schema."""

    try:
        schema, batches = _read_validated_ipc_batches(raw_bytes)
        return pa.RecordBatchReader.from_batches(schema, batches)
    except CanonicalRowHashIpcError:
        raise
    except _ARROW_PUBLIC_BOUNDARY_ERRORS:
        raise CanonicalRowHashIpcError("invalid arrow ipc stream") from None


def collect_row_hashes_from_ipc(raw_bytes: bytes) -> list[bytes]:
    """Collect row hashes for owner tests using fixed-schema IPC validation."""

    row_buffer, row_count = _collect_row_hash_buffer_from_ipc(raw_bytes)
    if row_count == 0:
        return []
    view = memoryview(row_buffer)
    return [
        bytes(view[index * ROW_HASH_BYTE_WIDTH : (index + 1) * ROW_HASH_BYTE_WIDTH])
        for index in range(row_count)
    ]


def verify_row_hashes_sorted_unsigned(row_hashes: Sequence[bytes]) -> None:
    """Fail closed when owner-produced row hashes are not sorted."""

    prior: bytes | None = None
    for index, row_hash in enumerate(row_hashes):
        if len(row_hash) != ROW_HASH_BYTE_WIDTH:
            raise CanonicalRowHashIpcError(f"row_hashes[{index}] must be exactly 32 bytes")
        if prior is not None and row_hash < prior:
            raise CanonicalRowHashIpcError("row hashes must be sorted unsigned lexicographic")
        prior = row_hash


def recompute_raw_content_digest(row_hashes: Sequence[bytes]) -> DigestRef:
    return unordered_row_hashes_content_digest(list(row_hashes)).digest_ref


def table_schema_digest_from_declared_fields(fields: Sequence[dict[str, object]]) -> DigestRef:
    """Recompute owner schema identity from declared request fields."""

    projected: list[dict[str, object]] = []
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            raise CanonicalRowHashIpcError(f"declared_fields[{index}] must be an object")
        name = field.get("name")
        nullable = field.get("nullable")
        semantic_type = field.get("semantic_type")
        if type(name) is not str:
            raise CanonicalRowHashIpcError(f"declared_fields[{index}].name must be a string")
        if type(nullable) is not bool:
            raise CanonicalRowHashIpcError(
                f"declared_fields[{index}].nullable must be a boolean"
            )
        if not isinstance(semantic_type, dict):
            raise CanonicalRowHashIpcError(
                f"declared_fields[{index}].semantic_type must be an object"
            )
        projected.append(
            {
                "name": canonicalize_identifier(name),
                "nullable": nullable,
                "semantic_type": semantic_type,
            }
        )
    projected.sort(key=lambda item: str(item["name"]))
    payload_bytes = json.dumps({"fields": projected}, separators=(",", ":")).encode("utf-8")
    canonical_payload = canonicalize_jcs(payload_bytes)
    return semantic_digest(DigestKind.TABLE_SCHEMA, canonical_payload).digest_ref


def content_manifest_from_compute_result(result_jcs: bytes) -> CanonicalRowHashesArtifactMetadata:
    canonical = canonicalize_jcs(result_jcs)
    payload = json.loads(canonical)
    if not isinstance(payload, dict):
        raise CanonicalRowHashIpcError("compute result must be a JSON object")
    if set(payload) != _RESULT_EXPECTED_FIELDS:
        raise CanonicalRowHashIpcError("compute result fields do not match v1 schema")
    boundary_version = payload["boundary_version"]
    if type(boundary_version) is not int or boundary_version != CANONICAL_ROW_HASH_BOUNDARY_VERSION:
        raise CanonicalRowHashIpcError("boundary_version must be 1")
    if type(payload["table_schema_digest"]) is not str:
        raise CanonicalRowHashIpcError("table_schema_digest must be a string")
    if type(payload["raw_content_digest"]) is not str:
        raise CanonicalRowHashIpcError("raw_content_digest must be a string")
    if type(payload["row_count"]) is not str:
        raise CanonicalRowHashIpcError("row_count must be a string")
    return CanonicalRowHashesArtifactMetadata.create(
        raw_content_digest=DigestRef(payload["raw_content_digest"]),
        table_schema_digest=DigestRef(payload["table_schema_digest"]),
        row_count=payload["row_count"],
    )


def persist_canonical_row_hash_stream(
    store: ArtifactStorePort,
    *,
    artifact_id: str,
    reader: pa.RecordBatchReader,
    content_manifest: CanonicalRowHashesArtifactMetadata,
    declared_fields: Sequence[dict[str, object]],
) -> ArtifactRef:
    raw_bytes = write_row_hash_ipc_stream(reader)
    _verify_ipc_bytes_match_content_manifest(
        raw_bytes,
        expected_content=content_manifest,
        declared_fields=declared_fields,
    )
    return put_with_built_ref(
        store,
        raw_bytes,
        artifact_id=artifact_id,
        media_type=MEDIA_TYPE,
    )


def reopen_and_verify_canonical_row_hash_artifact(
    store: ArtifactStorePort,
    ref: ArtifactRef,
) -> None:
    """Ordinary reopen verifies raw integrity, Arrow parsing, and fixed schema only."""

    if ref.media_type != MEDIA_TYPE:
        raise CanonicalRowHashIpcError("artifact media_type mismatch")
    raw_bytes = store.locate(ref)
    try:
        _read_validated_ipc_batches(raw_bytes)
    except CanonicalRowHashIpcError:
        raise
    except _ARROW_PUBLIC_BOUNDARY_ERRORS:
        raise CanonicalRowHashIpcError("invalid arrow ipc stream") from None


def _verify_ipc_bytes_match_content_manifest(
    raw_bytes: bytes,
    *,
    expected_content: CanonicalRowHashesArtifactMetadata,
    declared_fields: Sequence[dict[str, object]],
) -> None:
    row_buffer, row_count = _collect_row_hash_buffer_from_ipc(raw_bytes)
    _verify_row_buffer_sorted_unsigned(row_buffer, row_count)
    if str(row_count) != expected_content.row_count:
        raise CanonicalRowHashIpcError("row_count mismatch")
    recomputed_content = unordered_row_hashes_content_digest_from_sorted_row_buffer(
        row_buffer, row_count
    ).digest_ref
    if recomputed_content.value != expected_content.raw_content_digest.value:
        raise CanonicalRowHashIpcError("raw_content_digest mismatch")
    recomputed_schema = table_schema_digest_from_declared_fields(declared_fields)
    if recomputed_schema.value != expected_content.table_schema_digest.value:
        raise CanonicalRowHashIpcError("table_schema_digest mismatch")


def _collect_row_hash_buffer_from_ipc(raw_bytes: bytes) -> tuple[bytearray, int]:
    _schema, batches = _read_validated_ipc_batches(raw_bytes)
    row_buffer = bytearray()
    for batch in batches:
        row_buffer.extend(_row_hash_values_buffer_from_batch(batch))
    row_count = len(row_buffer) // ROW_HASH_BYTE_WIDTH
    if len(row_buffer) != row_count * ROW_HASH_BYTE_WIDTH:
        raise CanonicalRowHashIpcError("row_hash buffer length is not an exact multiple of 32")
    return row_buffer, row_count


def _assert_ipc_stream_eos_marker(raw_bytes: bytes) -> None:
    if len(raw_bytes) < len(IPC_STREAM_EOS_MARKER) or not raw_bytes.endswith(IPC_STREAM_EOS_MARKER):
        raise CanonicalRowHashIpcError("arrow ipc stream missing end marker")


def _read_validated_ipc_batches(raw_bytes: bytes) -> tuple[pa.Schema, list[pa.RecordBatch]]:
    _assert_ipc_stream_eos_marker(raw_bytes)
    try:
        buffer_reader = pa.BufferReader(raw_bytes)
        reader = pa.ipc.open_stream(buffer_reader)
        _assert_reader_schema(reader.schema)
        batches: list[pa.RecordBatch] = []
        try:
            while True:
                batch = reader.read_next_batch()
                _row_hash_values_buffer_from_batch(batch)
                batches.append(batch)
        except StopIteration:
            pass
        if buffer_reader.tell() != len(raw_bytes):
            raise CanonicalRowHashIpcError("arrow ipc stream has unconsumed trailing bytes")
        return reader.schema, batches
    except CanonicalRowHashIpcError:
        raise
    except _ARROW_PUBLIC_BOUNDARY_ERRORS:
        raise CanonicalRowHashIpcError("invalid arrow ipc stream") from None


def _verify_row_buffer_sorted_unsigned(buf: bytearray, row_count: int) -> None:
    if row_count == 0:
        return
    view = memoryview(buf)
    prior_start = 0
    prior_end = ROW_HASH_BYTE_WIDTH
    for index in range(1, row_count):
        current_start = index * ROW_HASH_BYTE_WIDTH
        current_end = current_start + ROW_HASH_BYTE_WIDTH
        if _unsigned_slice_less(view[current_start:current_end], view[prior_start:prior_end]):
            raise CanonicalRowHashIpcError("row hashes must be sorted unsigned lexicographic")
        prior_start = current_start
        prior_end = current_end


def _unsigned_slice_less(left: memoryview, right: memoryview) -> bool:
    for left_byte, right_byte in zip(left, right, strict=True):
        if left_byte < right_byte:
            return True
        if left_byte > right_byte:
            return False
    return False


def _assert_reader_schema(schema: pa.Schema) -> None:
    if not schema.equals(CANONICAL_ROW_HASH_OUTPUT_SCHEMA, check_metadata=True):
        raise CanonicalRowHashIpcError("schema does not match canonical row-hash output")


def _assert_batch_has_no_null_row_hashes(batch: pa.RecordBatch) -> None:
    if batch.num_rows == 0:
        return
    if batch.num_columns != 1 or batch.schema.field(0).name != ROW_HASH_FIELD_NAME:
        raise CanonicalRowHashIpcError("unexpected batch schema")
    column = batch.column(0)
    if isinstance(column, pa.ChunkedArray):
        raise CanonicalRowHashIpcError("row_hash column must be a contiguous array")
    validity = column.buffers()[0]
    if validity is not None and column.null_count > 0:
        raise CanonicalRowHashIpcError("row_hash column must not contain null values")


def _row_hash_values_buffer_from_batch(batch: pa.RecordBatch) -> bytes:
    if not batch.schema.equals(CANONICAL_ROW_HASH_OUTPUT_SCHEMA, check_metadata=True):
        raise CanonicalRowHashIpcError("batch schema does not match canonical output")
    _assert_batch_has_no_null_row_hashes(batch)
    column = batch.column(0)
    if not isinstance(column, pa.FixedSizeBinaryArray):
        raise CanonicalRowHashIpcError("row_hash column must be fixed-size binary")
    values = column.buffers()[1]
    expected_size = len(column) * ROW_HASH_BYTE_WIDTH
    if values is None or values.size != expected_size:
        raise CanonicalRowHashIpcError("row_hash values must be exactly 32 bytes")
    return bytes(values)
