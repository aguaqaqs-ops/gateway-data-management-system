"""Artifact visibility helpers for upload dual-condition checks."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_store import MutationStore


def artifact_ready_path(layout: DurableLayout, repository_id: UUID, artifact_id: UUID) -> Path:
    key = repository_key(repository_id)
    _staging, ready = layout.repository_artifact_directories(key)
    return ready / artifact_id.hex


def has_published_artifact_file(
    layout: DurableLayout,
    repository_id: UUID,
    artifact_id: UUID,
    *,
    size_bytes: int,
    raw_sha256: str,
) -> bool:
    """Return True when the ready artifact file exists with exact size and SHA-256."""

    ready_path = artifact_ready_path(layout, repository_id, artifact_id)
    if not ready_path.is_file():
        return False
    if ready_path.stat().st_size != size_bytes:
        return False
    hasher = hashlib.sha256()
    with ready_path.open("rb") as handle:
        while True:
            chunk = handle.read(64 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest() == raw_sha256


def is_artifact_visible(
    store: MutationStore,
    layout: DurableLayout,
    repository_id: UUID,
    artifact_id: UUID,
    *,
    size_bytes: int,
    raw_sha256: str,
) -> bool:
    """Artifact is visible only when DB and filesystem evidence both exist."""

    return store.has_succeeded_upload(repository_id, artifact_id) and has_published_artifact_file(
        layout,
        repository_id,
        artifact_id,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
    )
