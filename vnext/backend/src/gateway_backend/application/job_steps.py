"""Shared operation step checkpoint helpers for job handlers."""

from __future__ import annotations

from gateway_backend.artifacts.types import ArtifactRef


def unique_artifact_refs(refs: tuple[ArtifactRef, ...]) -> tuple[ArtifactRef, ...]:
    seen: set[str] = set()
    unique: list[ArtifactRef] = []
    for ref in refs:
        if ref.artifact_id in seen:
            continue
        seen.add(ref.artifact_id)
        unique.append(ref)
    return tuple(unique)
