"""R2–R7 test-only local ArtifactStore staging.

Owns tmp_path layout, reopen (fresh store), known object/sidecar paths, and
minimal-ref host-path assertions. Does not own capability content schema,
production retention, or cleanup policy.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from gateway_backend.artifacts import (
    ArtifactRef,
    artifact_ref_to_dict,
    assert_no_host_path_identity,
    put_with_built_ref,
)
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore

_MINIMAL_REF_FIELDS = frozenset({"artifact_id", "media_type", "size_bytes", "raw_sha256"})
_FORBIDDEN_IDENTITY_KEYS = frozenset(
    {
        "path",
        "host_path",
        "filesystem_path",
        "artifact_root",
        "file_path",
        "absolute_path",
        "provider_path",
        "temporary_root",
    }
)


def staging_root(tmp_path: Path) -> Path:
    return tmp_path / "artifact-staging"


def durable_root(tmp_path: Path) -> Path:
    return tmp_path / "durable"


def open_local_store(root: Path) -> LocalArtifactStore:
    return LocalArtifactStore(root)


def reopen_local_store(root: Path) -> LocalArtifactStore:
    """Ordinary reopen: new process-local cache, same on-disk root."""

    return LocalArtifactStore(root)


def object_and_sidecar_paths(root: Path, artifact_id: str) -> tuple[Path, Path]:
    digest = hashlib.sha256(artifact_id.encode("utf-8")).hexdigest()
    target = root / digest[0:2] / digest[2:4] / digest
    sidecar = target.with_suffix(target.suffix + ".ref.jcs")
    return target, sidecar


def put_bytes(
    store: LocalArtifactStore,
    raw_bytes: bytes,
    *,
    artifact_id: str,
    media_type: str = "application/octet-stream",
) -> ArtifactRef:
    return put_with_built_ref(
        store,
        raw_bytes,
        artifact_id=artifact_id,
        media_type=media_type,
    )


def assert_minimal_ref_has_no_host_path(ref: ArtifactRef) -> None:
    payload = artifact_ref_to_dict(ref)
    if set(payload) != _MINIMAL_REF_FIELDS:
        raise AssertionError(f"ArtifactRef fields {set(payload)!r} are not the minimal envelope")
    overlap = _FORBIDDEN_IDENTITY_KEYS.intersection(payload)
    if overlap:
        raise AssertionError(f"ArtifactRef contains host-path keys {sorted(overlap)!r}")
    assert_no_host_path_identity(payload)
