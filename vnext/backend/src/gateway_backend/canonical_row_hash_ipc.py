"""Canonical Row Hash Arrow IPC stream writer, reader, and verification."""

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

from gateway_backend.artifacts import (
    ArtifactRef,
    ArtifactStorePort,
    RetentionClass,
    put_with_built_manifest,
)
from gateway_backend.artifacts.contracts import CANONICAL_ROW_HASHES_ARTIFACT
from gateway_backend.canonical_row_hash_artifact import CanonicalRowHashesArtifactManifest

ROW_HASH_FIELD_NAME = "row_hash"
ROW_HASH_BYTE_WIDTH = 32
CANONICAL_ROW_HASH_OUTPUT_SCHEMA = pa.schema(
    [
        pa.field(
            ROW_HASH_FIELD_NAME,
            pa.binary(ROW_HASH_BYTE_WIDTH),
            nullable=False,
        )
    ]
)
MEDIA_TYPE = CANONICAL_ROW_HASHES_ARTIFACT.media_type
IPC_STREAM_EOS_MARKER = b"\x00\x00\x00\x00"
_RESULT_SCHEMA_VERSION = 1
_RESULT_CANONICAL_ENCODING_VERSION = 1
_RESULT_ARROW_MAPPING_SCHEMA_VERSION = 1
_RESULT_EXPECTED_FIELDS = frozenset(
    {
        "result_schema_version",
        "contract_binding",
        "canonical_encoding_version",
        "arrow_mapping_schema_version",
        "table_schema_digest",
        "row_count",
        "raw_content_digest",
        "diagnostics",
    }
)


class CanonicalRowHashIpcError(ValueError):
    """Canonical row-hash IPC write, read, or verification failed."""


def write_row_hash_ipc_stream(reader: pa.RecordBatchReader) -> bytes:
    """Serialize a canonical row-hash output stream to Arrow IPC stream bytes."""

    _assert_reader_schema(reader.schema)
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, CANONICAL_ROW_HASH_OUTPUT_SCHEMA) as writer:
        for batch in reader:
            if not batch.schema.equals(CANONICAL_ROW_HASH_OUTPUT_SCHEMA, check_metadata=True):
                raise CanonicalRowHashIpcError("batch schema does not match canonical output")
            _assert_batch_has_no_null_row_hashes(batch)
            writer.write_batch(batch)
    return bytes(sink.getvalue().to_pybytes())


def open_row_hash_ipc_stream(raw_bytes: bytes) -> pa.RecordBatchReader:
    """Open finalized Arrow IPC stream bytes as a fail-closed RecordBatchReader."""

    schema, batches = _read_validated_ipc_batches(raw_bytes)
    return pa.RecordBatchReader.from_batches(schema, batches)


def collect_row_hashes_from_ipc(raw_bytes: bytes) -> list[bytes]:
    """Collect row hashes using the same fail-closed IPC validation as production verify."""

    row_buffer, row_count = _collect_row_hash_buffer_from_ipc(raw_bytes)
    if row_count == 0:
        return []
    view = memoryview(row_buffer)
    return [
        bytes(view[index * ROW_HASH_BYTE_WIDTH : (index + 1) * ROW_HASH_BYTE_WIDTH])
        for index in range(row_count)
    ]


def verify_row_hashes_sorted_unsigned(row_hashes: Sequence[bytes]) -> None:
    """Fail closed when row hashes are not sorted by unsigned byte order."""

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
    """Recompute table schema digest from declared request schema fields."""

    projected: list[dict[str, object]] = []
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            raise CanonicalRowHashIpcError(
                f"declared_table_schema.fields[{index}] must be an object"
            )
        name = field.get("name")
        nullable = field.get("nullable")
        semantic_type = field.get("semantic_type")
        if type(name) is not str:
            raise CanonicalRowHashIpcError(
                f"declared_table_schema.fields[{index}].name must be a string"
            )
        if type(nullable) is not bool:
            raise CanonicalRowHashIpcError(
                f"declared_table_schema.fields[{index}].nullable must be a boolean"
            )
        if not isinstance(semantic_type, dict):
            raise CanonicalRowHashIpcError(
                f"declared_table_schema.fields[{index}].semantic_type must be an object"
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


def content_manifest_from_compute_result(result_jcs: bytes) -> CanonicalRowHashesArtifactManifest:
    canonical = canonicalize_jcs(result_jcs)
    payload = json.loads(canonical)
    if not isinstance(payload, dict):
        raise CanonicalRowHashIpcError("compute result must be a JSON object")
    if set(payload) != _RESULT_EXPECTED_FIELDS:
        raise CanonicalRowHashIpcError("compute result fields do not match v1 schema")
    result_schema_version = payload["result_schema_version"]
    canonical_encoding_version = payload["canonical_encoding_version"]
    arrow_mapping_schema_version = payload["arrow_mapping_schema_version"]
    if type(result_schema_version) is not int or result_schema_version != _RESULT_SCHEMA_VERSION:
        raise CanonicalRowHashIpcError("result_schema_version must be 1")
    if (
        type(canonical_encoding_version) is not int
        or canonical_encoding_version != _RESULT_CANONICAL_ENCODING_VERSION
    ):
        raise CanonicalRowHashIpcError("canonical_encoding_version must be 1")
    if (
        type(arrow_mapping_schema_version) is not int
        or arrow_mapping_schema_version != _RESULT_ARROW_MAPPING_SCHEMA_VERSION
    ):
        raise CanonicalRowHashIpcError("arrow_mapping_schema_version must be 1")
    contract_binding = payload["contract_binding"]
    if not isinstance(contract_binding, dict):
        raise CanonicalRowHashIpcError("contract_binding must be an object")
    if set(contract_binding) != {"contract_id", "semantic_version"}:
        raise CanonicalRowHashIpcError("contract_binding fields do not match v1 schema")
    if contract_binding["contract_id"] != CANONICAL_ROW_HASHES_ARTIFACT.contract_id:
        raise CanonicalRowHashIpcError("contract_binding.contract_id mismatch")
    if contract_binding["semantic_version"] != CANONICAL_ROW_HASHES_ARTIFACT.semantic_version:
        raise CanonicalRowHashIpcError("contract_binding.semantic_version mismatch")
    diagnostics = payload["diagnostics"]
    if not isinstance(diagnostics, list):
        raise CanonicalRowHashIpcError("diagnostics must be an array")
    for index, item in enumerate(diagnostics):
        if type(item) is not str:
            raise CanonicalRowHashIpcError(f"diagnostics[{index}] must be a string")
    if type(payload["table_schema_digest"]) is not str:
        raise CanonicalRowHashIpcError("table_schema_digest must be a string")
    if type(payload["raw_content_digest"]) is not str:
        raise CanonicalRowHashIpcError("raw_content_digest must be a string")
    if type(payload["row_count"]) is not str:
        raise CanonicalRowHashIpcError("row_count must be a string")
    return CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=DigestRef(payload["raw_content_digest"]),
        table_schema_digest=DigestRef(payload["table_schema_digest"]),
        row_count=payload["row_count"],
    )


def persist_canonical_row_hash_stream(
    store: ArtifactStorePort,
    *,
    logical_ref: str,
    reader: pa.RecordBatchReader,
    content_manifest: CanonicalRowHashesArtifactManifest,
    declared_table_schema_fields: Sequence[dict[str, object]],
    retention_class: RetentionClass = RetentionClass.OPERATION,
) -> ArtifactRef:
    raw_bytes = write_row_hash_ipc_stream(reader)
    _verify_ipc_bytes_match_content_manifest(
        raw_bytes,
        expected_content=content_manifest,
        declared_table_schema_fields=declared_table_schema_fields,
    )
    return put_with_built_manifest(
        store,
        raw_bytes,
        logical_ref=logical_ref,
        content_manifest=content_manifest,
        retention_class=retention_class,
    )


def reopen_and_verify_canonical_row_hash_artifact(
    store: ArtifactStorePort,
    ref: ArtifactRef,
    *,
    expected_content: CanonicalRowHashesArtifactManifest,
    declared_table_schema_fields: Sequence[dict[str, object]],
) -> None:
    """Fail-closed reopen pipeline: raw integrity, schema, sorted hashes, semantic recompute."""

    if ref.media_type != MEDIA_TYPE:
        raise CanonicalRowHashIpcError("artifact media_type mismatch")
    raw_bytes = store.locate(ref)
    if len(raw_bytes) != ref.size_bytes:
        raise CanonicalRowHashIpcError("located size_bytes mismatch")
    _verify_ipc_bytes_match_content_manifest(
        raw_bytes,
        expected_content=expected_content,
        declared_table_schema_fields=declared_table_schema_fields,
    )
    if ref.content_digest.value != expected_content.raw_content_digest.value:
        raise CanonicalRowHashIpcError("envelope content_digest mismatch")


def _verify_ipc_bytes_match_content_manifest(
    raw_bytes: bytes,
    *,
    expected_content: CanonicalRowHashesArtifactManifest,
    declared_table_schema_fields: Sequence[dict[str, object]],
) -> None:
    row_buffer, row_count = _collect_row_hash_buffer_from_ipc(raw_bytes)
    _verify_row_buffer_sorted_unsigned(row_buffer, row_count)
    if str(row_count) != expected_content.row_count:
        raise CanonicalRowHashIpcError("row_count mismatch")
    recomputed_content = unordered_row_hashes_content_digest_from_sorted_row_buffer(
        row_buffer,
        row_count,
    ).digest_ref
    if recomputed_content.value != expected_content.raw_content_digest.value:
        raise CanonicalRowHashIpcError("raw_content_digest mismatch")
    recomputed_schema = table_schema_digest_from_declared_fields(declared_table_schema_fields)
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
    buffer_reader = pa.BufferReader(raw_bytes)
    try:
        reader = pa.ipc.open_stream(buffer_reader)
    except pa.ArrowInvalid, pa.ArrowIOError, OSError, ValueError:
        raise CanonicalRowHashIpcError("invalid arrow ipc stream") from None
    try:
        _assert_reader_schema(reader.schema)
    except CanonicalRowHashIpcError:
        raise
    except Exception:
        raise CanonicalRowHashIpcError("invalid arrow ipc stream") from None
    batches: list[pa.RecordBatch] = []
    try:
        while True:
            batch = reader.read_next_batch()
            _row_hash_values_buffer_from_batch(batch)
            batches.append(batch)
    except StopIteration:
        pass
    except CanonicalRowHashIpcError:
        raise
    except pa.ArrowInvalid, pa.ArrowIOError, OSError, ValueError:
        raise CanonicalRowHashIpcError("invalid arrow ipc stream") from None
    except Exception:
        raise CanonicalRowHashIpcError("invalid arrow ipc stream") from None
    if buffer_reader.tell() != len(raw_bytes):
        raise CanonicalRowHashIpcError("arrow ipc stream has unconsumed trailing bytes")
    return reader.schema, batches


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
        column = column.combine_chunks()
    validity = column.buffers()[0]
    if validity is not None and column.null_count > 0:
        raise CanonicalRowHashIpcError("row_hash column must not contain null values")


def _row_hash_values_buffer_from_batch(batch: pa.RecordBatch) -> bytes:
    if batch.num_rows == 0:
        return b""
    if batch.num_columns != 1 or batch.schema.field(0).name != ROW_HASH_FIELD_NAME:
        raise CanonicalRowHashIpcError("unexpected batch schema")
    column = batch.column(0)
    if isinstance(column, pa.ChunkedArray):
        column = column.combine_chunks()
    if (
        not pa.types.is_fixed_size_binary(column.type)
        or column.type.byte_width != ROW_HASH_BYTE_WIDTH
    ):
        raise CanonicalRowHashIpcError("row_hash column must be fixed_size_binary(32)")
    _assert_batch_has_no_null_row_hashes(batch)
    values_buffer = column.buffers()[1]
    if values_buffer is None:
        raise CanonicalRowHashIpcError("row_hash values buffer missing")
    expected_len = batch.num_rows * ROW_HASH_BYTE_WIDTH
    raw = bytes(values_buffer.to_pybytes())
    if len(raw) != expected_len:
        raise CanonicalRowHashIpcError("row_hash values buffer length mismatch")
    return raw
