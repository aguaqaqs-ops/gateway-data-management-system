"""Local ArtifactStore staging conformance for R2–R7 test helpers."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path

import pyarrow as pa
import pytest
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts import ArtifactRef, ManifestVerificationError, artifact_ref_to_dict
from gateway_backend.canonical_row_hash_ipc import (
    content_manifest_from_compute_result,
    persist_canonical_row_hash_stream,
    reopen_and_verify_canonical_row_hash_artifact,
)
from gateway_backend.compute import canonical_row_hashes_v1
from tests.support.artifact_staging import (
    assert_minimal_ref_has_no_host_path,
    durable_root,
    object_and_sidecar_paths,
    open_local_store,
    put_bytes,
    reopen_local_store,
    staging_root,
)

OPAQUE_ARTIFACT_ID = "opaque-staging-0001"
OPAQUE_BYTES = b"payload"

_Mutator = Callable[[Path, str], None]


def _missing_bytes(root: Path, artifact_id: str) -> None:
    target, _sidecar = object_and_sidecar_paths(root, artifact_id)
    target.unlink()


def _missing_sidecar(root: Path, artifact_id: str) -> None:
    _target, sidecar = object_and_sidecar_paths(root, artifact_id)
    sidecar.unlink()


def _corrupt_bytes_size(root: Path, artifact_id: str) -> None:
    target, _sidecar = object_and_sidecar_paths(root, artifact_id)
    target.write_bytes(target.read_bytes() + b"x")


def _corrupt_bytes_digest(root: Path, artifact_id: str) -> None:
    target, _sidecar = object_and_sidecar_paths(root, artifact_id)
    original = target.read_bytes()
    flipped = bytes([original[0] ^ 0xFF]) + original[1:]
    target.write_bytes(flipped)


def _corrupt_sidecar(root: Path, artifact_id: str) -> None:
    _target, sidecar = object_and_sidecar_paths(root, artifact_id)
    sidecar.write_bytes(b"{not-valid-jcs")


STAGING_OBJECT_FAULTS: tuple[tuple[str, _Mutator, str], ...] = (
    ("missing-bytes", _missing_bytes, "artifact bytes are missing"),
    ("missing-sidecar", _missing_sidecar, "unknown artifact_id"),
    ("corrupt-bytes-size", _corrupt_bytes_size, "stored size_bytes mismatch"),
    ("corrupt-bytes-digest", _corrupt_bytes_digest, "stored raw_sha256 mismatch"),
    ("corrupt-sidecar", _corrupt_sidecar, "artifact read failed"),
)


def test_local_store_round_trip_and_reopen_preserves_bytes(tmp_path: Path) -> None:
    root = staging_root(tmp_path)
    store = open_local_store(root)
    ref = put_bytes(store, OPAQUE_BYTES, artifact_id=OPAQUE_ARTIFACT_ID)
    assert_minimal_ref_has_no_host_path(ref)
    assert store.locate(ref) == OPAQUE_BYTES

    reopened = reopen_local_store(root)
    assert reopened.locate(ref) == OPAQUE_BYTES
    assert str(root) not in json.dumps(artifact_ref_to_dict(ref))
    assert "artifact_root" not in artifact_ref_to_dict(ref)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [(mutate, match) for _name, mutate, match in STAGING_OBJECT_FAULTS],
    ids=[name for name, _mutate, _match in STAGING_OBJECT_FAULTS],
)
def test_reopen_rejects_missing_or_corrupt_staging_object(
    tmp_path: Path, mutate: _Mutator, match: str
) -> None:
    root = staging_root(tmp_path)
    store = open_local_store(root)
    ref = put_bytes(store, OPAQUE_BYTES, artifact_id=OPAQUE_ARTIFACT_ID)
    mutate(root, OPAQUE_ARTIFACT_ID)
    reopened = reopen_local_store(root)
    with pytest.raises(ManifestVerificationError, match=match):
        reopened.locate(ref)


def test_sidecar_replace_failure_does_not_publish_locatable_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = staging_root(tmp_path)
    store = open_local_store(root)
    real_replace = os.replace

    def fail_sidecar_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        if str(dst).endswith(".ref.jcs"):
            raise OSError("injected sidecar replace failure")
        real_replace(src, dst)

    monkeypatch.setattr(
        "gateway_backend.infrastructure.artifact_store.local_store.os.replace",
        fail_sidecar_replace,
    )
    ref = ArtifactRef(
        artifact_id=OPAQUE_ARTIFACT_ID,
        media_type="application/octet-stream",
        size_bytes=len(OPAQUE_BYTES),
        raw_sha256=raw_blob_digest(OPAQUE_BYTES),
    )
    with pytest.raises(ManifestVerificationError, match="artifact write failed"):
        store.put(OPAQUE_BYTES, ref)

    reopened = reopen_local_store(root)
    with pytest.raises(ManifestVerificationError, match="unknown artifact_id"):
        reopened.locate(ref)


def test_tmp_path_cleanup_does_not_mutate_durable_integrity_incident(tmp_path: Path) -> None:
    durable = durable_root(tmp_path)
    durable.mkdir()
    incident = durable / "integrity-incident.json"
    original = b'{"status":"MANUAL_RECOVERY_REQUIRED"}'
    incident.write_bytes(original)

    root = staging_root(tmp_path)
    store = open_local_store(root)
    put_bytes(store, OPAQUE_BYTES, artifact_id=OPAQUE_ARTIFACT_ID)
    shutil.rmtree(root)

    assert incident.read_bytes() == original
    assert not root.exists()


def test_raw_transport_digest_is_independent_of_owner_content_digest(tmp_path: Path) -> None:
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
    content = content_manifest_from_compute_result(result_jcs)
    root = staging_root(tmp_path)
    store = open_local_store(root)
    ref = persist_canonical_row_hash_stream(
        store,
        artifact_id="canonical-row-hash-empty",
        reader=output,
        content_manifest=content,
        declared_fields=fields,
    )
    payload = artifact_ref_to_dict(ref)
    assert set(payload) == {"artifact_id", "media_type", "size_bytes", "raw_sha256"}
    assert "raw_content_digest" not in payload
    assert "table_schema_digest" not in payload
    assert "content_schema_id" not in payload
    assert_minimal_ref_has_no_host_path(ref)
    assert str(root) not in json.dumps(payload)
    assert ref.raw_sha256 != content.raw_content_digest
    assert content.table_schema_digest != ref.raw_sha256
    reopen_and_verify_canonical_row_hash_artifact(reopen_local_store(root), ref)
