from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..core.digests import DigestRef


@dataclass(frozen=True, slots=True)
class RepositoryTableExportArtifact:
    repository_id: str
    repository_ref: str
    resolved_commit_hash: str
    table_name: str
    export_format: str
    path: Path
    content_digest: DigestRef | str | None = None
    content_size_bytes: int | None = None
    table_root_hash: str | None = None
    reused: bool = False
    diagnostics: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository_id", _require_text(self.repository_id, "repository_id"))
        object.__setattr__(self, "repository_ref", _require_text(self.repository_ref, "repository_ref"))
        object.__setattr__(
            self,
            "resolved_commit_hash",
            _require_text(self.resolved_commit_hash, "resolved_commit_hash"),
        )
        object.__setattr__(self, "table_name", _require_text(self.table_name, "table_name"))
        object.__setattr__(self, "export_format", _require_text(self.export_format, "export_format").upper())
        if not isinstance(self.path, Path):
            raise TypeError("path must be a Path")
        object.__setattr__(
            self,
            "content_digest",
            _coerce_optional_digest_ref(self.content_digest, "content_digest"),
        )
        object.__setattr__(
            self,
            "content_size_bytes",
            _coerce_optional_int(self.content_size_bytes, "content_size_bytes"),
        )
        object.__setattr__(self, "table_root_hash", _normalize_optional_text(self.table_root_hash))
        object.__setattr__(self, "reused", bool(self.reused))
        object.__setattr__(self, "diagnostics", tuple(_require_text(item, "diagnostics item") for item in self.diagnostics))

    def to_payload(self) -> dict[str, object]:
        return {
            "repository_id": self.repository_id,
            "repository_ref": self.repository_ref,
            "resolved_commit_hash": self.resolved_commit_hash,
            "table_name": self.table_name,
            "export_format": self.export_format,
            "path": str(self.path),
            "content_digest": (
                self.content_digest.to_payload() if self.content_digest is not None else None
            ),
            "content_size_bytes": self.content_size_bytes,
            "table_root_hash": self.table_root_hash,
            "reused": self.reused,
            "diagnostics": list(self.diagnostics),
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
        *,
        path: Path | None = None,
    ) -> "RepositoryTableExportArtifact":
        artifact_path = path if path is not None else Path(_require_text(payload["path"], "path"))
        return cls(
            repository_id=_require_text(payload["repository_id"], "repository_id"),
            repository_ref=_require_text(payload["repository_ref"], "repository_ref"),
            resolved_commit_hash=_require_text(payload["resolved_commit_hash"], "resolved_commit_hash"),
            table_name=_require_text(payload["table_name"], "table_name"),
            export_format=_require_text(payload["export_format"], "export_format"),
            path=artifact_path,
            content_digest=_coerce_optional_digest_ref(payload.get("content_digest"), "content_digest"),
            content_size_bytes=_coerce_optional_int(payload.get("content_size_bytes"), "content_size_bytes"),
            table_root_hash=_normalize_optional_text(payload.get("table_root_hash")),
            reused=bool(payload.get("reused", False)),
            diagnostics=tuple(
                _require_text(item, "diagnostics item")
                for item in _coerce_sequence(payload.get("diagnostics"))
            ),
        )

    def manifest_payload(self) -> dict[str, object]:
        payload = self.to_payload()
        payload["path"] = "artifact.bin"
        return payload


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _normalize_optional_text(value: object | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError("optional text fields must be strings or None")
    return value.strip()


def _coerce_optional_digest_ref(
    value: object | None,
    field_name: str,
) -> DigestRef | None:
    if value is None:
        return None
    if isinstance(value, DigestRef):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        return DigestRef.parse(normalized)
    raise TypeError(f"{field_name} must be a DigestRef, string, or None")


def _coerce_optional_int(value: object | None, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer or None")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _coerce_sequence(value: object | None) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)):
        raise TypeError("value must be a sequence, not text")
    if not isinstance(value, tuple):
        value = tuple(value)  # type: ignore[arg-type]
    return value
