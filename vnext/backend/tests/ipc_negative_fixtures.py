"""Deterministic IPC mutation helpers for WP4 R3 negative-suite tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pyarrow as pa

from gateway_backend.artifacts.contracts import (
    CANONICAL_ROW_HASHES_ARTIFACT,
    content_contract_from_spec,
)
from gateway_backend.artifacts.types import AccessMetadata
from gateway_backend.canonical_row_hash_artifact import CanonicalRowHashesArtifactManifest
from gateway_backend.canonical_row_hash_ipc import (
    CANONICAL_ROW_HASH_OUTPUT_SCHEMA,
    collect_row_hashes_from_ipc,
    content_manifest_from_compute_result,
    open_row_hash_ipc_stream,
    write_row_hash_ipc_stream,
)
from gateway_backend.compute import canonical_row_hashes_v1
from gateway_shared_kernel import DigestRef, raw_blob_digest

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gateway_backend.artifacts import ArtifactRef
else:
    from collections.abc import Sequence

# Fixed deterministic row hashes (unsigned lexicographic order).
HASH_A = b"\x00" * 31 + b"\x01"
HASH_B = b"\x00" * 31 + b"\x02"
HASH_C = b"\x00" * 31 + b"\x03"
HASH_DUPLICATE = HASH_A

DEFAULT_FIELDS_JSON = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
RANDOM_GARBAGE_SEED = b"\xde\xad\xbe\xef\xca\xfe\xba\xbe" * 4


@dataclass(frozen=True, slots=True)
class ValidIpcFixture:
    raw_bytes: bytes
    fields: list[dict[str, object]]
    content: CanonicalRowHashesArtifactManifest
    single_batch_len: int
    after_schema_offset: int
    after_batch1_offset: int
    before_eos_offset: int


def minimal_request_jcs(fields_json: str) -> bytes:
    payload = {
        "request_schema_version": 1,
        "contract_binding": {
            "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
            "semantic_version": "1.0.0",
        },
        "canonical_encoding_version": 1,
        "arrow_mapping_schema_version": 1,
        "declared_table_schema": {"fields": json.loads(fields_json)},
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def flip_byte_at(buf: bytes, offset: int) -> bytes:
    view = bytearray(buf)
    view[offset] ^= 0x01
    return bytes(view)


def truncate_at(buf: bytes, length: int) -> bytes:
    return buf[:length]


def append_bytes(buf: bytes, suffix: bytes) -> bytes:
    return buf + suffix


def concat_streams(left: bytes, right: bytes) -> bytes:
    return left + right


def reader_from_hashes(hashes: Sequence[bytes]) -> pa.RecordBatchReader:
    array = pa.array(list(hashes), type=pa.binary(32))
    batch = pa.record_batch([array], schema=CANONICAL_ROW_HASH_OUTPUT_SCHEMA)
    return pa.RecordBatchReader.from_batches(CANONICAL_ROW_HASH_OUTPUT_SCHEMA, [batch])


def build_manual_ipc_bytes(hashes: Sequence[bytes]) -> bytes:
    return write_row_hash_ipc_stream(reader_from_hashes(hashes))


def _two_batch_ipc_offsets(raw_bytes: bytes) -> tuple[int, int, int]:
    """Return schema end, first-batch end, and second-batch end before EOS."""

    buffer_reader = pa.BufferReader(raw_bytes)
    reader = pa.ipc.open_stream(buffer_reader)
    after_schema_offset = buffer_reader.tell()
    first_batch = reader.read_next_batch()
    after_batch1_offset = buffer_reader.tell()
    second_batch = reader.read_next_batch()
    before_eos_offset = buffer_reader.tell()
    if first_batch.num_rows != 1 or second_batch.num_rows != 2:
        raise AssertionError("expected deterministic [1, 2] row batch partition")
    try:
        reader.read_next_batch()
    except StopIteration:
        pass
    else:
        raise AssertionError("expected exactly two IPC record batches")
    if buffer_reader.tell() != len(raw_bytes):
        raise AssertionError("expected EOS to consume the remaining IPC bytes")
    return after_schema_offset, after_batch1_offset, before_eos_offset


def build_true_multi_batch_ipc(fields_json: str = DEFAULT_FIELDS_JSON) -> ValidIpcFixture:
    fields = json.loads(fields_json)
    request_jcs = minimal_request_jcs(fields_json)
    batch_a = pa.record_batch([pa.array([True])], names=["flag"])
    batch_b = pa.record_batch([pa.array([False, False])], names=["flag"])
    multi_output, multi_result = canonical_row_hashes_v1(
        request_jcs,
        pa.RecordBatchReader.from_batches(batch_a.schema, [batch_a, batch_b]),
    )
    all_hashes = collect_row_hashes_from_ipc(write_row_hash_ipc_stream(multi_output))
    hash_batch_a = pa.record_batch(
        [pa.array(all_hashes[0:1], type=pa.binary(32))],
        schema=CANONICAL_ROW_HASH_OUTPUT_SCHEMA,
    )
    hash_batch_b = pa.record_batch(
        [pa.array(all_hashes[1:3], type=pa.binary(32))],
        schema=CANONICAL_ROW_HASH_OUTPUT_SCHEMA,
    )
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, CANONICAL_ROW_HASH_OUTPUT_SCHEMA) as writer:
        writer.write_batch(hash_batch_a)
        writer.write_batch(hash_batch_b)
    raw_bytes = bytes(sink.getvalue().to_pybytes())
    after_schema_offset, after_batch1_offset, before_eos_offset = _two_batch_ipc_offsets(raw_bytes)
    single_bytes = build_manual_ipc_bytes(all_hashes[0:1])
    content = content_manifest_from_compute_result(multi_result)
    return ValidIpcFixture(
        raw_bytes=raw_bytes,
        fields=fields,
        content=content,
        single_batch_len=len(single_bytes),
        after_schema_offset=after_schema_offset,
        after_batch1_offset=after_batch1_offset,
        before_eos_offset=before_eos_offset,
    )


def build_compute_fixture(fields_json: str = DEFAULT_FIELDS_JSON) -> ValidIpcFixture:
    fields = json.loads(fields_json)
    request_jcs = minimal_request_jcs(fields_json)
    batch_a = pa.record_batch([pa.array([True])], names=["flag"])
    batch_b = pa.record_batch([pa.array([False, False])], names=["flag"])
    single_output, single_result = canonical_row_hashes_v1(request_jcs, batch_a)
    single_bytes = write_row_hash_ipc_stream(single_output)
    multi_output, multi_result = canonical_row_hashes_v1(
        request_jcs,
        pa.RecordBatchReader.from_batches(batch_a.schema, [batch_a, batch_b]),
    )
    multi_bytes = write_row_hash_ipc_stream(multi_output)
    content = content_manifest_from_compute_result(multi_result)
    true_multi = build_true_multi_batch_ipc(fields_json)
    return ValidIpcFixture(
        raw_bytes=multi_bytes,
        fields=fields,
        content=content,
        single_batch_len=len(single_bytes),
        after_schema_offset=true_multi.after_schema_offset,
        after_batch1_offset=true_multi.after_batch1_offset,
        before_eos_offset=len(multi_bytes) - 8,
    )


def assert_valid_ipc_opens(raw_bytes: bytes) -> None:
    reopened = open_row_hash_ipc_stream(raw_bytes)
    assert reopened.schema.equals(CANONICAL_ROW_HASH_OUTPUT_SCHEMA, check_metadata=True)
    collect_row_hashes_from_ipc(raw_bytes)


def build_unsorted_ipc_bytes() -> bytes:
    return build_manual_ipc_bytes([HASH_C, HASH_A, HASH_B])


def build_wrong_field_name_ipc() -> bytes:
    schema = pa.schema([pa.field("not_row_hash", pa.binary(32), nullable=False)])
    batch = pa.record_batch([pa.array([HASH_A], type=pa.binary(32))], schema=schema)
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, schema) as writer:
        writer.write_batch(batch)
    return bytes(sink.getvalue().to_pybytes())


def build_wrong_physical_type_ipc() -> bytes:
    schema = pa.schema([pa.field("row_hash", pa.binary(16), nullable=False)])
    batch = pa.record_batch([pa.array([HASH_A[:16]], type=pa.binary(16))], schema=schema)
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, schema) as writer:
        writer.write_batch(batch)
    return bytes(sink.getvalue().to_pybytes())


def build_nullable_field_ipc() -> bytes:
    schema = pa.schema([pa.field("row_hash", pa.binary(32), nullable=True)])
    batch = pa.record_batch([pa.array([HASH_A], type=pa.binary(32))], schema=schema)
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, schema) as writer:
        writer.write_batch(batch)
    return bytes(sink.getvalue().to_pybytes())


def build_schema_metadata_ipc() -> bytes:
    schema = pa.schema(
        [pa.field("row_hash", pa.binary(32), nullable=False)],
        metadata={b"note": b"forbidden"},
    )
    batch = pa.record_batch([pa.array([HASH_A], type=pa.binary(32))], schema=schema)
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, schema) as writer:
        writer.write_batch(batch)
    return bytes(sink.getvalue().to_pybytes())


def build_field_metadata_ipc() -> bytes:
    schema = pa.schema(
        [pa.field("row_hash", pa.binary(32), nullable=False, metadata={b"note": b"forbidden"})]
    )
    batch = pa.record_batch([pa.array([HASH_A], type=pa.binary(32))], schema=schema)
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, schema) as writer:
        writer.write_batch(batch)
    return bytes(sink.getvalue().to_pybytes())


def build_missing_field_ipc() -> bytes:
    schema = pa.schema([])
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, schema):
        pass
    return bytes(sink.getvalue().to_pybytes())


def ipc_region_for_offset(fixture: ValidIpcFixture, offset: int) -> str:
    if offset < 6:
        return "header"
    if offset < fixture.after_schema_offset:
        return "schema-message"
    if offset < fixture.after_batch1_offset:
        return "batch1-metadata-or-body"
    if offset < fixture.before_eos_offset:
        return "batch2-metadata-or-body"
    if offset < len(fixture.raw_bytes):
        return "eos"
    return "trailing"


def build_validity_bitmap_null_slot_ipc() -> bytes:
    """Canonical schema IPC with a forged null validity bitmap slot."""

    validity = pa.py_buffer(b"\x00")
    values = pa.py_buffer(HASH_A)
    array = pa.FixedSizeBinaryArray.from_buffers(pa.binary(32), 1, [validity, values])
    batch = pa.record_batch([array], schema=CANONICAL_ROW_HASH_OUTPUT_SCHEMA)
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, CANONICAL_ROW_HASH_OUTPUT_SCHEMA) as writer:
        writer.write_batch(batch)
    return bytes(sink.getvalue().to_pybytes())


def build_extra_field_ipc() -> bytes:
    schema = pa.schema(
        [
            pa.field("row_hash", pa.binary(32), nullable=False),
            pa.field("extra", pa.int64(), nullable=False),
        ]
    )
    batch = pa.record_batch(
        [pa.array([HASH_A], type=pa.binary(32)), pa.array([1], type=pa.int64())],
        schema=schema,
    )
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, schema) as writer:
        writer.write_batch(batch)
    return bytes(sink.getvalue().to_pybytes())


def find_values_buffer_flip_offset(raw_bytes: bytes, row_hash: bytes = HASH_B) -> int:
    index = raw_bytes.rfind(row_hash)
    if index < 0:
        raise ValueError("row hash marker not found in ipc bytes")
    return index + len(row_hash) - 1


def manifest_for_ipc_bytes(
    raw_bytes: bytes,
    *,
    fields: Sequence[dict[str, object]],
    content: CanonicalRowHashesArtifactManifest,
) -> CanonicalRowHashesArtifactManifest:
    """Build manifest matching IPC bytes (independent row_count from decode)."""
    row_hashes = collect_row_hashes_from_ipc(raw_bytes)
    from gateway_backend.canonical_row_hash_ipc import recompute_raw_content_digest

    return CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=recompute_raw_content_digest(row_hashes),
        table_schema_digest=content.table_schema_digest,
        row_count=str(len(row_hashes)),
    )


def synced_manifest_for_tampered_ipc(
    tampered_bytes: bytes,
    *,
    fields: Sequence[dict[str, object]],
    content: CanonicalRowHashesArtifactManifest,
) -> CanonicalRowHashesArtifactManifest:
    return manifest_for_ipc_bytes(tampered_bytes, fields=fields, content=content)


def raw_identity_for_bytes(raw_bytes: bytes) -> tuple[int, str]:
    return len(raw_bytes), raw_blob_digest(raw_bytes).value


def build_artifact_ref_for_bytes(
    raw_bytes: bytes,
    *,
    logical_ref_suffix: str,
    content_digest: DigestRef,
) -> ArtifactRef:
    from gateway_backend.artifacts import ArtifactRef, RetentionClass, build_logical_ref

    return ArtifactRef(
        artifact_ref_schema_version=1,
        logical_ref=build_logical_ref("canonical-row-hash", logical_ref_suffix),
        media_type=CANONICAL_ROW_HASHES_ARTIFACT.media_type,
        size_bytes=len(raw_bytes),
        raw_sha256=DigestRef(raw_blob_digest(raw_bytes).value),
        content_digest=content_digest,
        content_contract=content_contract_from_spec(CANONICAL_ROW_HASHES_ARTIFACT),
        content_schema_id=CANONICAL_ROW_HASHES_ARTIFACT.content_schema_id,
        retention_class=RetentionClass.OPERATION,
        access_metadata=AccessMetadata(),
    )


def reject_ipc_bytes(raw_bytes: bytes) -> None:
    """Exercise production decode path (open + full stream consumption)."""

    collect_row_hashes_from_ipc(raw_bytes)
