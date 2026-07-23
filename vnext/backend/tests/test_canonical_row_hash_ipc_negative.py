"""WP4 R3 corrupt / truncated / mismatch IPC negative-suite tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest

from gateway_backend.artifacts import (
    ArtifactRef,
    InMemoryArtifactStore,
    RetentionClass,
    build_logical_ref,
)
from gateway_backend.artifacts.serialize import build_manifest
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.canonical_row_hash_artifact import CanonicalRowHashesArtifactManifest
from gateway_backend.canonical_row_hash_ipc import (
    CANONICAL_ROW_HASH_OUTPUT_SCHEMA,
    CanonicalRowHashIpcError,
    _verify_ipc_bytes_match_content_manifest,
    collect_row_hashes_from_ipc,
    content_manifest_from_compute_result,
    open_row_hash_ipc_stream,
    persist_canonical_row_hash_stream,
    reopen_and_verify_canonical_row_hash_artifact,
    table_schema_digest_from_declared_fields,
    write_row_hash_ipc_stream,
)
from gateway_backend.compute import canonical_row_hashes_v1
from gateway_backend.infrastructure.artifact_store import LocalArtifactStore
from gateway_shared_kernel import DigestRef

from ipc_negative_fixtures import (
    HASH_A,
    HASH_B,
    HASH_C,
    HASH_DUPLICATE,
    RANDOM_GARBAGE_SEED,
    append_bytes,
    assert_valid_ipc_opens,
    build_artifact_ref_for_bytes,
    build_compute_fixture,
    build_extra_field_ipc,
    build_field_metadata_ipc,
    build_manual_ipc_bytes,
    build_missing_field_ipc,
    build_nullable_field_ipc,
    build_schema_metadata_ipc,
    build_true_multi_batch_ipc,
    build_unsorted_ipc_bytes,
    build_validity_bitmap_null_slot_ipc,
    build_wrong_field_name_ipc,
    build_wrong_physical_type_ipc,
    concat_streams,
    find_values_buffer_flip_offset,
    flip_byte_at,
    minimal_request_jcs,
    reader_from_hashes,
    reject_ipc_bytes,
    synced_manifest_for_tampered_ipc,
    truncate_at,
)

FIXTURE = build_compute_fixture()
TRUNCATION_FIXTURE = build_true_multi_batch_ipc()


class SpyArtifactStore:
    """Counts put calls while delegating to an in-memory store."""

    def __init__(self) -> None:
        self.put_calls = 0
        self._inner = InMemoryArtifactStore()

    def put(self, raw_bytes: bytes, manifest: Any) -> ArtifactRef:
        self.put_calls += 1
        return self._inner.put(raw_bytes, manifest)

    def locate(self, ref: ArtifactRef) -> bytes:
        return self._inner.locate(ref)

    def verify_manifest(self, manifest: Any) -> None:
        self._inner.verify_manifest(manifest)


class BytesOnlyArtifactStore:
    """Returns fixed bytes without envelope identity checks (reopen envelope tests)."""

    def __init__(self, raw_bytes: bytes) -> None:
        self._raw_bytes = raw_bytes

    def locate(self, ref: ArtifactRef) -> bytes:
        _ = ref
        return self._raw_bytes

    def put(self, raw_bytes: bytes, manifest: Any) -> ArtifactRef:
        raise NotImplementedError

    def verify_manifest(self, manifest: Any) -> None:
        _ = manifest


def _run_compute(
    fields_json: str, data: pa.Table | pa.RecordBatchReader
) -> tuple[pa.RecordBatchReader, bytes]:
    return canonical_row_hashes_v1(minimal_request_jcs(fields_json), data)


# --- Positive controls (E) ---


def test_positive_empty_stream_accepted() -> None:
    reader = pa.RecordBatchReader.from_batches(CANONICAL_ROW_HASH_OUTPUT_SCHEMA, [])
    raw_bytes = write_row_hash_ipc_stream(reader)
    assert_valid_ipc_opens(raw_bytes)


def test_positive_one_batch_accepted() -> None:
    raw_bytes = build_manual_ipc_bytes([HASH_A, HASH_B])
    assert_valid_ipc_opens(raw_bytes)


def test_positive_multi_batch_accepted() -> None:
    assert_valid_ipc_opens(TRUNCATION_FIXTURE.raw_bytes)


def test_true_multi_batch_fixture_offsets_are_exact() -> None:
    buffer_reader = pa.BufferReader(TRUNCATION_FIXTURE.raw_bytes)
    reader = pa.ipc.open_stream(buffer_reader)
    assert buffer_reader.tell() == TRUNCATION_FIXTURE.after_schema_offset
    assert reader.read_next_batch().num_rows == 1
    assert buffer_reader.tell() == TRUNCATION_FIXTURE.after_batch1_offset
    assert reader.read_next_batch().num_rows == 2
    assert buffer_reader.tell() == TRUNCATION_FIXTURE.before_eos_offset
    with pytest.raises(StopIteration):
        reader.read_next_batch()
    assert buffer_reader.tell() == len(TRUNCATION_FIXTURE.raw_bytes)


def test_positive_duplicate_row_hashes_preserved() -> None:
    raw_bytes = build_manual_ipc_bytes([HASH_DUPLICATE, HASH_DUPLICATE, HASH_B])
    assert collect_row_hashes_from_ipc(raw_bytes) == [HASH_DUPLICATE, HASH_DUPLICATE, HASH_B]


def test_positive_sorted_hashes_accepted() -> None:
    raw_bytes = build_manual_ipc_bytes([HASH_A, HASH_B, HASH_C])
    assert_valid_ipc_opens(raw_bytes)


def test_positive_chunking_differs_raw_bytes_same_semantic_digest() -> None:
    hashes = [HASH_A, HASH_B, HASH_C]
    single_bytes = write_row_hash_ipc_stream(reader_from_hashes(hashes))
    batch_a = pa.record_batch(
        [pa.array([HASH_A], type=pa.binary(32))], schema=CANONICAL_ROW_HASH_OUTPUT_SCHEMA
    )
    batch_b = pa.record_batch(
        [pa.array([HASH_B, HASH_C], type=pa.binary(32))],
        schema=CANONICAL_ROW_HASH_OUTPUT_SCHEMA,
    )
    multi_bytes = write_row_hash_ipc_stream(
        pa.RecordBatchReader.from_batches(CANONICAL_ROW_HASH_OUTPUT_SCHEMA, [batch_a, batch_b])
    )
    assert single_bytes != multi_bytes
    digest_a = synced_manifest_for_tampered_ipc(
        single_bytes, fields=FIXTURE.fields, content=FIXTURE.content
    ).raw_content_digest
    digest_b = synced_manifest_for_tampered_ipc(
        multi_bytes, fields=FIXTURE.fields, content=FIXTURE.content
    ).raw_content_digest
    assert digest_a.value == digest_b.value


def test_positive_fixture_family_opens_before_mutations() -> None:
    assert_valid_ipc_opens(FIXTURE.raw_bytes)


# --- Corrupt IPC (A) ---


@pytest.mark.parametrize(
    ("corrupt_bytes", "match_text"),
    [
        pytest.param(b"", "missing end marker", id="empty"),
        pytest.param(b"\x00", "missing end marker", id="length-1"),
        pytest.param(RANDOM_GARBAGE_SEED, "missing end marker", id="random-garbage"),
        pytest.param(
            flip_byte_at(TRUNCATION_FIXTURE.raw_bytes, 0),
            "invalid arrow ipc stream",
            id="flip-header-magic",
        ),
        pytest.param(
            flip_byte_at(TRUNCATION_FIXTURE.raw_bytes, 3),
            "invalid arrow ipc stream",
            id="flip-header-continuation",
        ),
        pytest.param(
            flip_byte_at(TRUNCATION_FIXTURE.raw_bytes, 10),
            "invalid arrow ipc stream",
            id="flip-schema-message",
        ),
        pytest.param(
            flip_byte_at(TRUNCATION_FIXTURE.raw_bytes, TRUNCATION_FIXTURE.after_batch1_offset + 8),
            "invalid arrow ipc stream",
            id="flip-batch2-metadata",
        ),
        pytest.param(
            flip_byte_at(TRUNCATION_FIXTURE.raw_bytes, len(TRUNCATION_FIXTURE.raw_bytes) - 2),
            "missing end marker",
            id="flip-eos",
        ),
        pytest.param(
            append_bytes(TRUNCATION_FIXTURE.raw_bytes, RANDOM_GARBAGE_SEED),
            "missing end marker",
            id="append-garbage",
        ),
        pytest.param(
            concat_streams(
                TRUNCATION_FIXTURE.raw_bytes[: TRUNCATION_FIXTURE.after_batch1_offset],
                TRUNCATION_FIXTURE.raw_bytes,
            ),
            "invalid arrow ipc stream",
            id="concat-second-stream",
        ),
    ],
)
def test_corrupt_ipc_rejected_at_decode(corrupt_bytes: bytes, match_text: str) -> None:
    with pytest.raises(CanonicalRowHashIpcError, match=match_text):
        reject_ipc_bytes(corrupt_bytes)


def test_corrupt_schema_metadata_ipc_rejected() -> None:
    with pytest.raises(CanonicalRowHashIpcError, match="schema does not match"):
        open_row_hash_ipc_stream(build_schema_metadata_ipc())


def test_bit_flip_decodable_ipc_fails_semantic_digest_not_raw_hash() -> None:
    raw_bytes = build_manual_ipc_bytes([HASH_A])
    flip_offset = find_values_buffer_flip_offset(raw_bytes, HASH_A)
    tampered = flip_byte_at(raw_bytes, flip_offset)
    assert_valid_ipc_opens(tampered)
    content = synced_manifest_for_tampered_ipc(
        raw_bytes, fields=FIXTURE.fields, content=FIXTURE.content
    )
    synced = synced_manifest_for_tampered_ipc(
        tampered, fields=FIXTURE.fields, content=FIXTURE.content
    )
    assert synced.raw_content_digest.value != content.raw_content_digest.value
    with pytest.raises(CanonicalRowHashIpcError, match="raw_content_digest mismatch"):
        reopen_and_verify_canonical_row_hash_artifact(
            BytesOnlyArtifactStore(tampered),
            build_artifact_ref_for_bytes(
                tampered,
                logical_ref_suffix="semantic-bit-flip",
                content_digest=synced.raw_content_digest,
            ),
            expected_content=content,
            declared_table_schema_fields=FIXTURE.fields,
        )


# --- Truncated IPC (B) ---


@pytest.mark.parametrize(
    ("length", "match_text", "case_id"),
    [
        (0, "missing end marker", "length-0"),
        (1, "missing end marker", "length-1"),
        (8, "missing end marker", "header-truncated"),
        (32, "missing end marker", "schema-truncated"),
        (
            TRUNCATION_FIXTURE.after_schema_offset - 8,
            "missing end marker",
            "schema-message-truncated",
        ),
        (TRUNCATION_FIXTURE.after_batch1_offset, "missing end marker", "after-batch1-boundary"),
        (
            TRUNCATION_FIXTURE.after_batch1_offset + 16,
            "invalid arrow ipc stream",
            "batch2-metadata-truncated",
        ),
        (TRUNCATION_FIXTURE.before_eos_offset - 8, "missing end marker", "batch2-body-truncated"),
        (len(TRUNCATION_FIXTURE.raw_bytes) - 8, "missing end marker", "eos-removed-full"),
        (len(TRUNCATION_FIXTURE.raw_bytes) - 4, "missing end marker", "eos-half-removed"),
        (TRUNCATION_FIXTURE.before_eos_offset - 1, "missing end marker", "before-eos-byte"),
    ],
)
def test_truncated_ipc_fail_closed(length: int, match_text: str, case_id: str) -> None:
    _ = case_id
    truncated = truncate_at(TRUNCATION_FIXTURE.raw_bytes, length)
    with pytest.raises(CanonicalRowHashIpcError, match=match_text):
        collect_row_hashes_from_ipc(truncated)


def test_truncated_after_batch1_does_not_return_partial_rows() -> None:
    truncated = truncate_at(TRUNCATION_FIXTURE.raw_bytes, TRUNCATION_FIXTURE.after_batch1_offset)
    with pytest.raises(CanonicalRowHashIpcError, match="missing end marker"):
        collect_row_hashes_from_ipc(truncated)


def test_open_row_hash_ipc_stream_rejects_truncated_at_public_boundary() -> None:
    truncated = truncate_at(
        TRUNCATION_FIXTURE.raw_bytes,
        TRUNCATION_FIXTURE.after_batch1_offset + 20,
    )
    with pytest.raises(CanonicalRowHashIpcError, match="missing end marker"):
        open_row_hash_ipc_stream(truncated)


def test_truncated_family_positive_control() -> None:
    assert_valid_ipc_opens(TRUNCATION_FIXTURE.raw_bytes)


# --- Mismatch IPC / identity (C) ---


def test_unsorted_row_hashes_rejected() -> None:
    with pytest.raises(CanonicalRowHashIpcError, match="sorted unsigned lexicographic"):
        _verify_ipc_bytes_match_content_manifest(
            build_unsorted_ipc_bytes(),
            expected_content=FIXTURE.content,
            declared_table_schema_fields=FIXTURE.fields,
        )


def test_schema_field_name_mismatch_rejected() -> None:
    with pytest.raises(CanonicalRowHashIpcError, match="schema does not match"):
        open_row_hash_ipc_stream(build_wrong_field_name_ipc())


def test_schema_missing_field_rejected() -> None:
    with pytest.raises(CanonicalRowHashIpcError, match="schema does not match"):
        open_row_hash_ipc_stream(build_missing_field_ipc())


def test_schema_field_metadata_rejected() -> None:
    with pytest.raises(CanonicalRowHashIpcError, match="schema does not match"):
        open_row_hash_ipc_stream(build_field_metadata_ipc())


def test_schema_physical_type_mismatch_rejected() -> None:
    with pytest.raises(CanonicalRowHashIpcError, match="schema does not match"):
        open_row_hash_ipc_stream(build_wrong_physical_type_ipc())


def test_schema_nullable_mismatch_rejected() -> None:
    with pytest.raises(CanonicalRowHashIpcError, match="schema does not match"):
        open_row_hash_ipc_stream(build_nullable_field_ipc())


def test_null_slot_rejected() -> None:
    with pytest.raises(CanonicalRowHashIpcError, match="must not contain null"):
        collect_row_hashes_from_ipc(build_validity_bitmap_null_slot_ipc())


def test_extra_field_rejected() -> None:
    with pytest.raises(CanonicalRowHashIpcError, match="schema does not match"):
        open_row_hash_ipc_stream(build_extra_field_ipc())


def test_publish_row_count_mismatch_rejects_before_put() -> None:
    output, result_jcs = _run_compute(json.dumps(FIXTURE.fields), pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    tampered = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=content.raw_content_digest,
        table_schema_digest=content.table_schema_digest,
        row_count="999",
    )
    store = SpyArtifactStore()
    with pytest.raises(CanonicalRowHashIpcError, match="row_count mismatch"):
        persist_canonical_row_hash_stream(
            store,
            logical_ref=build_logical_ref("canonical-row-hash", "publish-row-count"),
            reader=output,
            content_manifest=tampered,
            declared_table_schema_fields=FIXTURE.fields,
        )
    assert store.put_calls == 0


def test_publish_table_schema_digest_mismatch_rejects_before_put() -> None:
    output, result_jcs = _run_compute(json.dumps(FIXTURE.fields), pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    tampered = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=content.raw_content_digest,
        table_schema_digest=DigestRef("sha256:" + "f" * 64),
        row_count=content.row_count,
    )
    store = SpyArtifactStore()
    with pytest.raises(CanonicalRowHashIpcError, match="table_schema_digest mismatch"):
        persist_canonical_row_hash_stream(
            store,
            logical_ref=build_logical_ref("canonical-row-hash", "publish-schema"),
            reader=output,
            content_manifest=tampered,
            declared_table_schema_fields=FIXTURE.fields,
        )
    assert store.put_calls == 0


def test_publish_raw_content_digest_mismatch_rejects_before_put() -> None:
    output, result_jcs = _run_compute(json.dumps(FIXTURE.fields), pa.table({"flag": [True, False]}))
    content = content_manifest_from_compute_result(result_jcs)
    tampered = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=DigestRef("sha256:" + "b" * 64),
        table_schema_digest=content.table_schema_digest,
        row_count=content.row_count,
    )
    store = SpyArtifactStore()
    with pytest.raises(CanonicalRowHashIpcError, match="raw_content_digest mismatch"):
        persist_canonical_row_hash_stream(
            store,
            logical_ref=build_logical_ref("canonical-row-hash", "publish-semantic"),
            reader=output,
            content_manifest=tampered,
            declared_table_schema_fields=FIXTURE.fields,
        )
    assert store.put_calls == 0


def test_publish_reject_leaves_local_store_clean(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    output, result_jcs = _run_compute(json.dumps(FIXTURE.fields), pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    tampered = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=content.raw_content_digest,
        table_schema_digest=content.table_schema_digest,
        row_count="999",
    )
    with pytest.raises(CanonicalRowHashIpcError, match="row_count mismatch"):
        persist_canonical_row_hash_stream(
            store,
            logical_ref=build_logical_ref("canonical-row-hash", "publish-clean"),
            reader=output,
            content_manifest=tampered,
            declared_table_schema_fields=FIXTURE.fields,
        )
    artifact_files = [
        path
        for path in (tmp_path / "artifacts").rglob("*")
        if path.is_file() and not path.name.startswith(".")
    ]
    assert artifact_files == []


def test_reopen_raw_content_digest_mismatch_after_raw_integrity() -> None:
    store = InMemoryArtifactStore()
    output, result_jcs = _run_compute(json.dumps(FIXTURE.fields), pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    ref = persist_canonical_row_hash_stream(
        store,
        logical_ref=build_logical_ref("canonical-row-hash", "reopen-semantic"),
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=FIXTURE.fields,
    )
    forged = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=DigestRef("sha256:" + "c" * 64),
        table_schema_digest=content.table_schema_digest,
        row_count=content.row_count,
    )
    with pytest.raises(CanonicalRowHashIpcError, match="raw_content_digest mismatch"):
        reopen_and_verify_canonical_row_hash_artifact(
            store,
            ref,
            expected_content=forged,
            declared_table_schema_fields=FIXTURE.fields,
        )


def test_reopen_envelope_content_digest_mismatch() -> None:
    raw_bytes = build_manual_ipc_bytes([HASH_A])
    content = synced_manifest_for_tampered_ipc(
        raw_bytes, fields=FIXTURE.fields, content=FIXTURE.content
    )
    forged_ref = build_artifact_ref_for_bytes(
        raw_bytes,
        logical_ref_suffix="envelope-digest",
        content_digest=DigestRef("sha256:" + "d" * 64),
    )
    with pytest.raises(CanonicalRowHashIpcError, match="envelope content_digest mismatch"):
        reopen_and_verify_canonical_row_hash_artifact(
            BytesOnlyArtifactStore(raw_bytes),
            forged_ref,
            expected_content=content,
            declared_table_schema_fields=FIXTURE.fields,
        )


def test_reopen_media_type_mismatch() -> None:
    raw_bytes = build_manual_ipc_bytes([HASH_A])
    content = synced_manifest_for_tampered_ipc(
        raw_bytes, fields=FIXTURE.fields, content=FIXTURE.content
    )
    ref = build_artifact_ref_for_bytes(
        raw_bytes,
        logical_ref_suffix="media-type",
        content_digest=content.raw_content_digest,
    )

    class WrongMediaRef:
        media_type = "application/octet-stream"
        size_bytes = ref.size_bytes
        content_digest = ref.content_digest
        logical_ref = ref.logical_ref
        raw_sha256 = ref.raw_sha256

    with pytest.raises(CanonicalRowHashIpcError, match="media_type mismatch"):
        reopen_and_verify_canonical_row_hash_artifact(
            BytesOnlyArtifactStore(raw_bytes),
            WrongMediaRef(),  # type: ignore[arg-type]
            expected_content=content,
            declared_table_schema_fields=FIXTURE.fields,
        )


def test_reopen_declared_schema_mismatch() -> None:
    store = InMemoryArtifactStore()
    output, result_jcs = _run_compute(json.dumps(FIXTURE.fields), pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    ref = persist_canonical_row_hash_stream(
        store,
        logical_ref=build_logical_ref("canonical-row-hash", "declared-schema"),
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=FIXTURE.fields,
    )
    wrong_fields = [{"name": "other", "nullable": True, "semantic_type": {"kind": "boolean"}}]
    with pytest.raises(CanonicalRowHashIpcError, match="table_schema_digest mismatch"):
        reopen_and_verify_canonical_row_hash_artifact(
            store,
            ref,
            expected_content=content,
            declared_table_schema_fields=wrong_fields,
        )


def test_reopen_raw_sha256_mismatch_at_store_layer() -> None:
    store = InMemoryArtifactStore()
    output, result_jcs = _run_compute(json.dumps(FIXTURE.fields), pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    ref = persist_canonical_row_hash_stream(
        store,
        logical_ref=build_logical_ref("canonical-row-hash", "raw-sha256"),
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=FIXTURE.fields,
    )
    forged_ref = replace(ref, raw_sha256=DigestRef("sha256:" + "0" * 64))
    with pytest.raises(ManifestVerificationError, match="stored artifact identity mismatch"):
        reopen_and_verify_canonical_row_hash_artifact(
            store,
            forged_ref,
            expected_content=content,
            declared_table_schema_fields=FIXTURE.fields,
        )


def test_reopen_size_bytes_mismatch_at_capability_layer() -> None:
    raw_bytes = build_manual_ipc_bytes([HASH_A])
    content = synced_manifest_for_tampered_ipc(
        raw_bytes, fields=FIXTURE.fields, content=FIXTURE.content
    )
    ref = build_artifact_ref_for_bytes(
        raw_bytes,
        logical_ref_suffix="size-bytes",
        content_digest=content.raw_content_digest,
    )
    bad_ref = replace(ref, size_bytes=ref.size_bytes + 1)
    with pytest.raises(CanonicalRowHashIpcError, match="located size_bytes mismatch"):
        reopen_and_verify_canonical_row_hash_artifact(
            BytesOnlyArtifactStore(raw_bytes),
            bad_ref,
            expected_content=content,
            declared_table_schema_fields=FIXTURE.fields,
        )


def test_local_store_tamper_after_persist_rejects_reopen(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    output, result_jcs = _run_compute(json.dumps(FIXTURE.fields), pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    ref = persist_canonical_row_hash_stream(
        store,
        logical_ref=build_logical_ref("canonical-row-hash", "tamper-disk"),
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=FIXTURE.fields,
    )
    raw_bytes = store.locate(ref)
    row_hashes = collect_row_hashes_from_ipc(raw_bytes)
    tampered = flip_byte_at(raw_bytes, find_values_buffer_flip_offset(raw_bytes, row_hashes[0]))
    object_path = store.artifact_root
    for path in object_path.rglob("*"):
        if path.is_file() and not path.name.endswith(".manifest.jcs"):
            path.write_bytes(tampered)
            break
    with pytest.raises(ManifestVerificationError, match="stored raw_sha256 mismatch"):
        reopen_and_verify_canonical_row_hash_artifact(
            store,
            ref,
            expected_content=content,
            declared_table_schema_fields=FIXTURE.fields,
        )


def test_local_store_fresh_instance_sidecar_identity_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    store_a = LocalArtifactStore(root)
    output, result_jcs = _run_compute(json.dumps(FIXTURE.fields), pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    ref = persist_canonical_row_hash_stream(
        store_a,
        logical_ref=build_logical_ref("canonical-row-hash", "sidecar-tamper"),
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=FIXTURE.fields,
    )
    raw_bytes = store_a.locate(ref)
    forged_manifest = build_manifest(
        logical_ref=ref.logical_ref,
        raw_bytes=raw_bytes,
        content=CanonicalRowHashesArtifactManifest.create(
            raw_content_digest=DigestRef("sha256:" + "e" * 64),
            table_schema_digest=content.table_schema_digest,
            row_count=content.row_count,
        ),
        retention_class=RetentionClass.OPERATION,
    )
    store_b = LocalArtifactStore(root)
    sidecar = next(root.rglob("*.manifest.jcs"))
    sidecar.write_text(
        __import__(
            "gateway_backend.artifacts.serialize",
            fromlist=["artifact_manifest_to_json"],
        ).artifact_manifest_to_json(forged_manifest),
        encoding="utf-8",
    )
    with pytest.raises(ManifestVerificationError, match="stored artifact identity mismatch"):
        store_b.locate(ref)


def test_same_raw_bytes_different_semantic_identity_isolated() -> None:
    raw_bytes = build_manual_ipc_bytes([HASH_A])
    content_a = synced_manifest_for_tampered_ipc(
        raw_bytes, fields=FIXTURE.fields, content=FIXTURE.content
    )
    content_b = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=DigestRef("sha256:" + "9" * 64),
        table_schema_digest=content_a.table_schema_digest,
        row_count=content_a.row_count,
    )
    assert content_a.raw_content_digest.value != content_b.raw_content_digest.value
    with pytest.raises(CanonicalRowHashIpcError, match="raw_content_digest mismatch"):
        reopen_and_verify_canonical_row_hash_artifact(
            BytesOnlyArtifactStore(raw_bytes),
            build_artifact_ref_for_bytes(
                raw_bytes,
                logical_ref_suffix="semantic-collision",
                content_digest=content_a.raw_content_digest,
            ),
            expected_content=content_b,
            declared_table_schema_fields=FIXTURE.fields,
        )


def test_declared_schema_digest_independent_recompute() -> None:
    fields = FIXTURE.fields
    output, result_jcs = _run_compute(json.dumps(fields), pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    recomputed = table_schema_digest_from_declared_fields(fields)
    assert recomputed.value == content.table_schema_digest.value
