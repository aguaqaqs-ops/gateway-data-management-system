"""Minimal Backend artifact identity and integrity rules."""

from __future__ import annotations

import re
from dataclasses import dataclass

from gateway_shared_kernel import DigestRef

IJSON_MAX_SAFE_INTEGER = (2**53) - 1
_ARTIFACT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
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
_WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")
_TRAVERSAL_SEGMENT_PATTERN = re.compile(r"(^|[\\/])\.\.?($|[\\/])")


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Backend-local opaque location identity plus raw transport integrity."""

    artifact_id: str
    media_type: str
    size_bytes: int
    raw_sha256: DigestRef

    def __post_init__(self) -> None:
        validate_artifact_id(self.artifact_id)
        if type(self.media_type) is not str or not self.media_type:
            raise ValueError("media_type must be a non-empty string")
        if type(self.size_bytes) is not int:
            raise ValueError("size_bytes must be an integer")
        if self.size_bytes < 0 or self.size_bytes > IJSON_MAX_SAFE_INTEGER:
            raise ValueError("size_bytes must be a non-negative I-JSON safe integer")
        if type(self.raw_sha256) is not DigestRef:
            raise ValueError("raw_sha256 must be DigestRef")

    @property
    def integrity_identity(self) -> tuple[int, str]:
        return (self.size_bytes, self.raw_sha256.value)


def validate_artifact_id(artifact_id: str) -> None:
    if type(artifact_id) is not str or not _ARTIFACT_ID_PATTERN.fullmatch(artifact_id):
        raise ValueError("artifact_id must be a bounded opaque string")
    assert_no_host_path_identity(artifact_id, label="artifact_id")


def assert_no_host_path_identity(payload: object, *, label: str = "artifact identity") -> None:
    """Reject path-shaped keys and values from persisted or wire identity."""

    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in _FORBIDDEN_IDENTITY_KEYS:
                raise ValueError(f"{label} must not contain forbidden key {key!r}")
            assert_no_host_path_identity(value, label=f"{label}.{key}")
        return
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            assert_no_host_path_identity(item, label=f"{label}[{index}]")
        return
    if not isinstance(payload, str):
        return
    lowered = payload.casefold()
    if (
        "\x00" in payload
        or "\\" in payload
        or payload.startswith("/")
        or payload.startswith("//")
        or lowered.startswith("file:")
        or _WINDOWS_DRIVE_PATTERN.match(payload)
        or _TRAVERSAL_SEGMENT_PATTERN.search(payload)
    ):
        raise ValueError(f"{label} must not contain host path value")
