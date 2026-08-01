"""Minimal BackendArtifactRef and ordinary reopen tests."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pytest
from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts import (
    ArtifactRef,
    InMemoryArtifactStore,
    artifact_ref_from_json,
    artifact_ref_to_dict,
    artifact_ref_to_json,
    build_artifact_id,
    put_with_built_ref,
)
from gateway_backend.canonical_row_hash_artifact import CanonicalRowHashesArtifactMetadata
from gateway_backend.canonical_row_hash_ipc import (
    CANONICAL_ROW_HASH_OUTPUT_SCHEMA,
    CanonicalRowHashIpcError,
    content_manifest_from_compute_result,
    persist_canonical_row_hash_stream,
    reopen_and_verify_canonical_row_hash_artifact,
    write_row_hash_ipc_stream,
)
from gateway_backend.compute import canonical_row_hashes_v2
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore


def test_backend_ref_is_exactly_minimal_and_round_trips() -> None:
    ref = ArtifactRef(
        artifact_id="canonical-row-hash-example-0001",
        media_type="application/vnd.apache.arrow.stream",
        size_bytes=3,
        raw_sha256=DigestRef("sha256:" + "a" * 64),
    )
    assert set(artifact_ref_to_dict(ref)) == {
        "artifact_id",
        "media_type",
        "size_bytes",
        "raw_sha256",
    }
    assert artifact_ref_from_json(artifact_ref_to_json(ref)) == ref

    payload = json.loads(artifact_ref_to_json(ref))
    payload["content_digest"] = "sha256:" + "b" * 64
    with pytest.raises(ValueError, match="unknown fields"):
        artifact_ref_from_json(json.dumps(payload))


def test_backend_ref_rejects_host_path() -> None:
    with pytest.raises(ValueError, match="bounded opaque"):
        ArtifactRef(
            artifact_id="/tmp/secret.arrow",
            media_type="application/vnd.apache.arrow.stream",
            size_bytes=0,
            raw_sha256=DigestRef("sha256:" + "0" * 64),
        )


def _empty_content() -> tuple[
    pa.RecordBatchReader,
    CanonicalRowHashesArtifactMetadata,
    list[dict[str, object]],
]:
    fields: list[dict[str, object]] = []
    output, result_jcs = canonical_row_hashes_v2(
        json.dumps(
            {
                "boundary_version": 2,
                "canonical_encoding_version": 1,
                "arrow_mapping_version": 1,
                "declared_fields": fields,
            },
            separators=(",", ":"),
        ).encode(),
        pa.table({}),
    )
    return output, content_manifest_from_compute_result(result_jcs), fields


def test_publish_and_ordinary_reopen_local_artifact(tmp_path: Path) -> None:
    output, content, fields = _empty_content()
    store = LocalArtifactStore(tmp_path)
    ref = persist_canonical_row_hash_stream(
        store,
        artifact_id=build_artifact_id("canonical-row-hash", "empty"),
        reader=output,
        content_manifest=content,
        declared_fields=fields,
    )
    assert artifact_ref_to_dict(ref) == {
        "artifact_id": "canonical-row-hash-empty",
        "media_type": "application/vnd.apache.arrow.stream",
        "size_bytes": ref.size_bytes,
        "raw_sha256": ref.raw_sha256.value,
    }
    reopen_and_verify_canonical_row_hash_artifact(store, ref)


@pytest.mark.parametrize("variant", ["truncated", "corrupt", "schema"])
def test_ordinary_reopen_rejects_invalid_arrow_or_integrity(tmp_path: Path, variant: str) -> None:
    store = LocalArtifactStore(tmp_path)
    if variant == "schema":
        bad_schema = pa.schema([pa.field("wrong", pa.int32(), nullable=False)])
        bad_reader = pa.RecordBatchReader.from_batches(
            bad_schema,
            [pa.RecordBatch.from_arrays([pa.array([1])], schema=bad_schema)],
        )
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, bad_schema) as writer:
            writer.write_batch(bad_reader.read_next_batch())
        raw = sink.getvalue().to_pybytes()
    else:
        good = write_row_hash_ipc_stream(
            pa.RecordBatchReader.from_batches(CANONICAL_ROW_HASH_OUTPUT_SCHEMA, [])
        )
        raw = good[:-4] if variant == "truncated" else good[:-4] + b"x\x00\x00\x00"
    ref = put_with_built_ref(
        store,
        raw,
        artifact_id=f"bad-{variant}",
        media_type="application/vnd.apache.arrow.stream",
    )
    with pytest.raises((CanonicalRowHashIpcError, ValueError)):
        reopen_and_verify_canonical_row_hash_artifact(store, ref)


def test_reopen_does_not_require_semantic_manifest() -> None:
    raw = write_row_hash_ipc_stream(
        pa.RecordBatchReader.from_batches(CANONICAL_ROW_HASH_OUTPUT_SCHEMA, [])
    )
    store = InMemoryArtifactStore()
    ref = put_with_built_ref(
        store,
        raw,
        artifact_id="reopen-without-content-manifest",
        media_type="application/vnd.apache.arrow.stream",
    )
    reopen_and_verify_canonical_row_hash_artifact(store, ref)
