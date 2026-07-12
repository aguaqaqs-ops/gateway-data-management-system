from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..core.digests import DigestRef


def build_registry_entry_key(
    repository_id: str,
    entry_kind: str,
    identity: object,
) -> DigestRef:
    return DigestRef.from_payload(
        {
            "repository_id": _require_text(repository_id, "repository_id"),
            "entry_kind": _require_text(entry_kind, "entry_kind"),
            "identity": identity,
        }
    )


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    entry_id: int
    repository_id: str
    entry_key: DigestRef | str
    entry_kind: str
    namespace: str = ""
    logical_ref: str = ""
    owner: str = ""
    tag: str = ""
    operation_id: str = ""
    status: str = ""
    content_digest: DigestRef | str | None = None
    manifest_digest: DigestRef | str | None = None
    created_at_ms: int = 0
    updated_at_ms: int = 0
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_id", _require_int(self.entry_id, "entry_id"))
        object.__setattr__(
            self,
            "repository_id",
            _require_text(self.repository_id, "repository_id"),
        )
        object.__setattr__(self, "entry_key", _coerce_digest_ref(self.entry_key, "entry_key"))
        object.__setattr__(self, "entry_kind", _require_text(self.entry_kind, "entry_kind"))
        object.__setattr__(self, "namespace", _normalize_optional_text(self.namespace))
        object.__setattr__(self, "logical_ref", _normalize_optional_text(self.logical_ref))
        object.__setattr__(self, "owner", _normalize_optional_text(self.owner))
        object.__setattr__(self, "tag", _normalize_optional_text(self.tag))
        object.__setattr__(self, "operation_id", _normalize_optional_text(self.operation_id))
        object.__setattr__(self, "status", _require_text(self.status, "status"))
        object.__setattr__(
            self,
            "content_digest",
            _coerce_optional_digest_ref(self.content_digest, "content_digest"),
        )
        object.__setattr__(
            self,
            "manifest_digest",
            _coerce_optional_digest_ref(self.manifest_digest, "manifest_digest"),
        )
        object.__setattr__(self, "created_at_ms", _require_int(self.created_at_ms, "created_at_ms"))
        object.__setattr__(self, "updated_at_ms", _require_int(self.updated_at_ms, "updated_at_ms"))
        object.__setattr__(self, "metadata", _normalize_metadata_mapping(self.metadata))

    @property
    def created_at(self) -> datetime:
        return datetime.fromtimestamp(self.created_at_ms / 1000, tz=timezone.utc)

    @property
    def updated_at(self) -> datetime:
        return datetime.fromtimestamp(self.updated_at_ms / 1000, tz=timezone.utc)

    def to_payload(self) -> dict[str, object]:
        return {
            "entry_id": self.entry_id,
            "repository_id": self.repository_id,
            "entry_key": self.entry_key.to_payload(),
            "entry_kind": self.entry_kind,
            "namespace": self.namespace,
            "logical_ref": self.logical_ref,
            "owner": self.owner,
            "tag": self.tag,
            "operation_id": self.operation_id,
            "status": self.status,
            "content_digest": (
                self.content_digest.to_payload() if self.content_digest is not None else None
            ),
            "manifest_digest": (
                self.manifest_digest.to_payload() if self.manifest_digest is not None else None
            ),
            "created_at_ms": self.created_at_ms,
            "updated_at_ms": self.updated_at_ms,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class RegistryEntrySpec:
    entry_kind: str
    status: str
    identity: object | None = None
    entry_key: DigestRef | str | None = None
    namespace: str = ""
    logical_ref: str = ""
    owner: str = ""
    tag: str = ""
    operation_id: str = ""
    content_digest: DigestRef | str | None = None
    manifest_digest: DigestRef | str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_kind", _require_text(self.entry_kind, "entry_kind"))
        object.__setattr__(self, "status", _require_text(self.status, "status"))
        object.__setattr__(self, "entry_key", _coerce_optional_digest_ref(self.entry_key, "entry_key"))
        object.__setattr__(self, "namespace", _normalize_optional_text(self.namespace))
        object.__setattr__(self, "logical_ref", _normalize_optional_text(self.logical_ref))
        object.__setattr__(self, "owner", _normalize_optional_text(self.owner))
        object.__setattr__(self, "tag", _normalize_optional_text(self.tag))
        object.__setattr__(self, "operation_id", _normalize_optional_text(self.operation_id))
        object.__setattr__(
            self,
            "content_digest",
            _coerce_optional_digest_ref(self.content_digest, "content_digest"),
        )
        object.__setattr__(
            self,
            "manifest_digest",
            _coerce_optional_digest_ref(self.manifest_digest, "manifest_digest"),
        )
        object.__setattr__(self, "metadata", _normalize_metadata_mapping(self.metadata))
        if self.entry_key is None and self.identity is None:
            raise ValueError("entry_key or identity must be provided")

    def resolved_entry_key(self, repository_id: str) -> DigestRef:
        if self.entry_key is not None:
            return self.entry_key
        if self.identity is None:
            raise ValueError("entry_key or identity must be provided")
        return build_registry_entry_key(repository_id, self.entry_kind, self.identity)


@dataclass(frozen=True, slots=True)
class RegistryEntryQuery:
    entry_key: DigestRef | str | None = None
    entry_kind: str | None = None
    namespace: str | None = None
    logical_ref: str | None = None
    owner: str | None = None
    tag: str | None = None
    operation_id: str | None = None
    status: str | None = None
    content_digest: DigestRef | str | None = None
    manifest_digest: DigestRef | str | None = None
    created_at_ms_min: int | None = None
    created_at_ms_max: int | None = None
    updated_at_ms_min: int | None = None
    updated_at_ms_max: int | None = None
    limit: int | None = None
    offset: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_key", _coerce_optional_digest_ref(self.entry_key, "entry_key"))
        object.__setattr__(self, "entry_kind", _coerce_query_text(self.entry_kind))
        object.__setattr__(self, "namespace", _coerce_query_text(self.namespace))
        object.__setattr__(self, "logical_ref", _coerce_query_text(self.logical_ref))
        object.__setattr__(self, "owner", _coerce_query_text(self.owner))
        object.__setattr__(self, "tag", _coerce_query_text(self.tag))
        object.__setattr__(self, "operation_id", _coerce_query_text(self.operation_id))
        object.__setattr__(self, "status", _coerce_query_text(self.status))
        object.__setattr__(
            self,
            "content_digest",
            _coerce_optional_digest_ref(self.content_digest, "content_digest"),
        )
        object.__setattr__(
            self,
            "manifest_digest",
            _coerce_optional_digest_ref(self.manifest_digest, "manifest_digest"),
        )
        object.__setattr__(
            self,
            "created_at_ms_min",
            _coerce_optional_int(self.created_at_ms_min, "created_at_ms_min"),
        )
        object.__setattr__(
            self,
            "created_at_ms_max",
            _coerce_optional_int(self.created_at_ms_max, "created_at_ms_max"),
        )
        object.__setattr__(
            self,
            "updated_at_ms_min",
            _coerce_optional_int(self.updated_at_ms_min, "updated_at_ms_min"),
        )
        object.__setattr__(
            self,
            "updated_at_ms_max",
            _coerce_optional_int(self.updated_at_ms_max, "updated_at_ms_max"),
        )
        object.__setattr__(self, "limit", _coerce_optional_int(self.limit, "limit"))
        object.__setattr__(self, "offset", _require_non_negative_int(self.offset, "offset"))


@runtime_checkable
class RepositoryRegistry(Protocol):
    repository_id: str
    sqlite_path: Path

    def get_entry(self, entry_key: DigestRef | str) -> RegistryEntry | None: ...

    def list_entries(
        self,
        query: RegistryEntryQuery | None = None,
    ) -> tuple[RegistryEntry, ...]: ...


@runtime_checkable
class RepositoryRegistryWriter(RepositoryRegistry, Protocol):
    def upsert_entry(
        self,
        spec: RegistryEntrySpec,
        *,
        now_ms: int | None = None,
    ) -> RegistryEntry: ...

    def delete_entry(self, entry_key: DigestRef | str) -> None: ...


WritableRepositoryRegistry = RepositoryRegistryWriter


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


def _coerce_query_text(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("query text fields must be strings or None")
    return value.strip()


def _coerce_digest_ref(value: object, field_name: str) -> DigestRef:
    if isinstance(value, DigestRef):
        return value
    if isinstance(value, str):
        return DigestRef.parse(value.strip())
    raise TypeError(f"{field_name} must be a DigestRef or string")


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


def _normalize_metadata_mapping(
    metadata: Mapping[str, object] | None,
) -> dict[str, object]:
    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping")
    normalized: dict[str, object] = {}
    for key, value in metadata.items():
        if not isinstance(key, str):
            raise TypeError("metadata keys must be strings")
        normalized[key] = value
    return normalized


def _require_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _coerce_optional_int(value: object | None, field_name: str) -> int | None:
    if value is None:
        return None
    return _require_int(value, field_name)


def _require_non_negative_int(value: object, field_name: str) -> int:
    return _require_int(value, field_name)
