"""Local/in-memory artifact store ordinary reopen tests."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pytest

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts import (
    ArtifactRef,
    InMemoryArtifactStore,
    artifact_ref_to_dict,
    build_artifact_id,
    put_with_built_ref,
)
from gateway_backend.artifacts.nominal_refs import (
    NominalArtifactRefError,
    assert_backend_ref_not_repository_ref,
    assert_repository_ref_not_backend_ref,
    backend_artifact_ref_from_store_ref,
    repository_artifact_ref_from_upload_response,
    store_ref_from_backend_artifact_ref,
)
from gateway_backend.domain.submission.models import BackendArtifactRef, RepositoryArtifactRef
from gateway_backend.capabilities.canonical_row_hash import CanonicalRowHashesArtifactMetadata
from gateway_backend.canonical_row_hash_ipc import (
    CANONICAL_ROW_HASH_OUTPUT_SCHEMA,
    CanonicalRowHashIpcError,
    content_manifest_from_compute_result,
    persist_canonical_row_hash_stream,
    reopen_and_verify_canonical_row_hash_artifact,
    write_row_hash_ipc_stream,
)
from gateway_backend.compute import canonical_row_hashes_v1
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore


def _empty_content() -> tuple[
    pa.RecordBatchReader,
    CanonicalRowHashesArtifactMetadata,
    list[dict[str, object]],
]:
    fields: list[dict[str, object]] = []
    output, result_jcs = canonical_row_hashes_v1(
        json.dumps(
            {
                "boundary_version": 1,
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


_STORE_REF = ArtifactRef(
    artifact_id="backend-package-1",
    media_type="application/vnd.gateway.repository-import.v1+tar+zstd",
    size_bytes=12,
    raw_sha256=DigestRef("sha256:" + "aa" * 32),
)


def test_backend_and_repository_refs_are_distinct_nominal_types() -> None:
    backend = backend_artifact_ref_from_store_ref(_STORE_REF)
    repository = repository_artifact_ref_from_upload_response(
        artifact_id="repo-artifact-uuid",
        media_type=_STORE_REF.media_type,
        size_bytes=_STORE_REF.size_bytes,
        raw_sha256=_STORE_REF.raw_sha256.value,
    )
    assert type(backend) is BackendArtifactRef
    assert type(repository) is RepositoryArtifactRef
    assert backend.artifact_id != repository.artifact_id


def test_store_ref_round_trip_preserves_backend_identity() -> None:
    backend = backend_artifact_ref_from_store_ref(_STORE_REF)
    roundtrip = store_ref_from_backend_artifact_ref(backend)
    assert roundtrip == _STORE_REF


NOMINAL_REF_CROSS_TYPE_FAULTS: tuple[tuple[str, object, str], ...] = (
    (
        "repository-ref-used-as-backend",
        RepositoryArtifactRef(
            artifact_id="repo-1",
            media_type="application/octet-stream",
            size_bytes=1,
            raw_sha256="sha256:" + "cc" * 32,
        ),
        "backend",
    ),
    (
        "backend-ref-used-as-repository",
        BackendArtifactRef(
            artifact_id="backend-1",
            media_type="application/octet-stream",
            size_bytes=1,
            raw_sha256="sha256:" + "bb" * 32,
        ),
        "repository",
    ),
)


@pytest.mark.parametrize(("case_id", "ref", "expected_kind"), NOMINAL_REF_CROSS_TYPE_FAULTS)
def test_nominal_ref_cross_type_substitution_is_rejected(
    case_id: str,
    ref: object,
    expected_kind: str,
) -> None:
    if expected_kind == "backend":
        with pytest.raises(NominalArtifactRefError):
            assert_backend_ref_not_repository_ref(ref)
        return
    with pytest.raises(NominalArtifactRefError):
        assert_repository_ref_not_backend_ref(ref)


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
