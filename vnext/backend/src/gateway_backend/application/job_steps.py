"""Shared operation step checkpoint helpers for job handlers."""

from __future__ import annotations

from collections.abc import Mapping

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


def successor_step_id(
    operation_id: str,
    step_name: str,
    suffix_by_step: Mapping[str, str],
) -> str:
    try:
        suffix = suffix_by_step[step_name]
    except KeyError:
        raise ValueError(f"unknown step_name: {step_name}") from None
    return f"{operation_id}-step-{suffix}"


__all__ = ["successor_step_id", "unique_artifact_refs"]
