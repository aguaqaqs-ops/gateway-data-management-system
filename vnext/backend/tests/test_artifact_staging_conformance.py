"""Local ArtifactStore staging conformance for R2–R7 test helpers."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts import ArtifactRef, ManifestVerificationError, artifact_ref_to_dict
from tests.support.artifact_staging import (
    assert_minimal_ref_has_no_host_path,
    object_and_sidecar_paths,
    open_local_store,
    put_bytes,
    reopen_local_store,
    staging_root,
)

OPAQUE_ARTIFACT_ID = "a1:durable:ed1d7f23199e656e49e5f449a67569e16e2c6eb4fd0f95181252da3bba2ffe46"
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
    ("missing-bytes", _missing_bytes, "artifact is not available"),
    ("missing-sidecar", _missing_sidecar, "incomplete stored artifact directory"),
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


def test_directory_publication_failure_does_not_publish_locatable_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = staging_root(tmp_path)
    store = open_local_store(root)
    def fail_publication(source: Path, target: Path) -> None:
        raise OSError("injected directory publication failure")

    monkeypatch.setattr(
        "gateway_backend.infrastructure.artifact_store.local_store.rename_noreplace", fail_publication,
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
    with pytest.raises(ManifestVerificationError, match="artifact ref is not available"):
        reopened.locate(ref)
