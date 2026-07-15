from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..core.digests import DigestRef
from ..core.diagnostics import DiagnosticRecord
from ..core.versions import ARTIFACT_MANIFEST_SCHEMA_VERSION


def _mapping_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("artifact metadata keys must be strings")
        normalized[key] = value
    return normalized


def _diagnostics_payload(
    diagnostics: tuple[DiagnosticRecord, ...],
) -> list[dict[str, object]]:
    return [diagnostic.to_payload() for diagnostic in diagnostics]


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_kind: str
    artifact_contract_version: str
    manifest_digest: DigestRef
    content_digest: DigestRef

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_kind, str) or not self.artifact_kind:
            raise ValueError("artifact kind must be a non-empty string")
        if not isinstance(self.artifact_contract_version, str) or not self.artifact_contract_version:
            raise ValueError("artifact contract version must be a non-empty string")
        object.__setattr__(self, "manifest_digest", _coerce_digest(self.manifest_digest))
        object.__setattr__(self, "content_digest", _coerce_digest(self.content_digest))

    def to_payload(self) -> dict[str, object]:
        return {
            "artifact_kind": self.artifact_kind,
            "artifact_contract_version": self.artifact_contract_version,
            "manifest_digest": self.manifest_digest.to_payload(),
            "content_digest": self.content_digest.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "ArtifactRef":
        return cls(
            artifact_kind=_required_str(payload, "artifact_kind"),
            artifact_contract_version=_required_str(
                payload,
                "artifact_contract_version",
            ),
            manifest_digest=DigestRef.parse(_required_str(payload, "manifest_digest")),
            content_digest=DigestRef.parse(_required_str(payload, "content_digest")),
        )

    @property
    def storage_key(self) -> str:
        return f"{self.artifact_kind}/{self.manifest_digest.hex_digest}"


@dataclass(frozen=True, slots=True)
class ArtifactManifest:
    artifact_kind: str
    artifact_contract_version: str
    content_digest: DigestRef | str
    content_size_bytes: int
    metadata: Mapping[str, object] = field(default_factory=dict)
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_kind, str) or not self.artifact_kind:
            raise ValueError("artifact kind must be a non-empty string")
        if not isinstance(self.artifact_contract_version, str) or not self.artifact_contract_version:
            raise ValueError("artifact contract version must be a non-empty string")
        if (
            not isinstance(self.content_size_bytes, int)
            or isinstance(self.content_size_bytes, bool)
            or self.content_size_bytes < 0
        ):
            raise ValueError("content size must be a non-negative integer")
        object.__setattr__(self, "content_digest", _coerce_digest(self.content_digest))
        object.__setattr__(self, "metadata", _mapping_payload(self.metadata))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if self.created_at is not None and not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime or None")
        if self.created_at is not None and self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": ARTIFACT_MANIFEST_SCHEMA_VERSION,
            "artifact_kind": self.artifact_kind,
            "artifact_contract_version": self.artifact_contract_version,
            "content_digest": self.content_digest.to_payload(),
            "content_size_bytes": self.content_size_bytes,
            "metadata": _mapping_payload(self.metadata),
            "diagnostics": _diagnostics_payload(self.diagnostics),
            "created_at": (
                None
                if self.created_at is None
                else self.created_at.astimezone(timezone.utc).isoformat()
            ),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "ArtifactManifest":
        schema_version = _required_str(payload, "schema_version")
        if schema_version != ARTIFACT_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported artifact manifest schema version")
        diagnostics_payload = payload.get("diagnostics", [])
        if not isinstance(diagnostics_payload, list):
            raise TypeError("artifact diagnostics payload must be a list")
        created_at_value = payload.get("created_at")
        created_at = (
            None
            if created_at_value is None
            else datetime.fromisoformat(str(created_at_value))
        )
        content_size_value = payload["content_size_bytes"]
        if not isinstance(content_size_value, int) or isinstance(content_size_value, bool):
            raise TypeError("content_size_bytes must be an integer")
        return cls(
            artifact_kind=_required_str(payload, "artifact_kind"),
            artifact_contract_version=_required_str(
                payload,
                "artifact_contract_version",
            ),
            content_digest=DigestRef.parse(_required_str(payload, "content_digest")),
            content_size_bytes=content_size_value,
            metadata=_mapping_payload(_mapping_value(payload, "metadata")),
            diagnostics=tuple(
                DiagnosticRecord.from_payload(item)
                for item in diagnostics_payload
            ),
            created_at=created_at,
        )

    def to_ref(self, manifest_digest: DigestRef) -> ArtifactRef:
        return ArtifactRef(
            artifact_kind=self.artifact_kind,
            artifact_contract_version=self.artifact_contract_version,
            manifest_digest=manifest_digest,
            content_digest=self.content_digest,
        )


def _coerce_digest(value: DigestRef | str) -> DigestRef:
    if isinstance(value, DigestRef):
        return value
    return DigestRef.parse(value)


def _mapping_value(
    payload: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    value = payload.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be a mapping")
    return value


def _required_str(payload: Mapping[str, object], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be a non-empty string")
    return value
