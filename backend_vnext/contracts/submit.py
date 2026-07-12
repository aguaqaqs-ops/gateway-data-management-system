from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

from ..artifacts import ArtifactRef
from ..core.digests import DigestRef
from .versions import SQL_PARSER_VERSION, TABLE_RULESET_VERSION


PREVIEW_INPUT_BINDING_CONTRACT_VERSION = "backend-vnext/preview-input-binding/v1"
SUBMIT_SOURCE_PACKAGE_CONTRACT_VERSION = "backend-vnext/submit-source-package/v1"
SUBMIT_ACCEPTED_CONTRACT_VERSION = "backend-vnext/submit-accepted/v1"
SUBMIT_SOURCE_KIND = "SUBMIT_FULL"


def _mapping_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("mapping keys must be strings")
        normalized[key] = _payload_value(value)
    return normalized


def _payload_value(value: object) -> object:
    if value is None:
        return None
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        return _payload_value(to_payload())
    if isinstance(value, Mapping):
        return _mapping_payload(value)
    if isinstance(value, tuple):
        return [_payload_value(item) for item in value]
    if isinstance(value, list):
        return [_payload_value(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("datetime values must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()
    return value


def _required_str(payload: Mapping[str, object], field_name: str) -> str:
    value = payload[field_name]
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string")
    return value


def _optional_str(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string or None")
    return value


def _required_positive_int(payload: Mapping[str, object], field_name: str) -> int:
    value = payload[field_name]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TypeError(f"{field_name} must be a non-negative integer")
    return value


def _optional_datetime(value: object, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be an ISO 8601 string or None")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed


def _optional_digest(value: DigestRef | str | None) -> DigestRef | None:
    if value is None:
        return None
    if isinstance(value, DigestRef):
        return value
    return DigestRef.parse(str(value))


def _required_artifact_ref(payload: Mapping[str, object], field_name: str) -> ArtifactRef:
    value = payload[field_name]
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return ArtifactRef.from_payload(value)


@dataclass(frozen=True, slots=True)
class PreviewInputBindingEntry:
    entry_name: str
    content_digest: DigestRef | str
    normalized_path: str | None = None
    entry_kind: str = "FILE"

    def __post_init__(self) -> None:
        if not isinstance(self.entry_name, str) or not self.entry_name:
            raise ValueError("entry_name must be a non-empty string")
        object.__setattr__(self, "content_digest", _optional_digest(self.content_digest))
        if self.normalized_path is not None and (
            not isinstance(self.normalized_path, str) or not self.normalized_path
        ):
            raise ValueError("normalized_path must be a non-empty string or None")
        if not isinstance(self.entry_kind, str) or not self.entry_kind:
            raise ValueError("entry_kind must be a non-empty string")

    def to_payload(self) -> dict[str, object]:
        return {
            "entry_name": self.entry_name,
            "content_digest": self.content_digest.to_payload(),
            "normalized_path": self.normalized_path,
            "entry_kind": self.entry_kind,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "PreviewInputBindingEntry":
        return cls(
            entry_name=_required_str(payload, "entry_name"),
            content_digest=_required_str(payload, "content_digest"),
            normalized_path=_optional_str(
                payload.get("normalized_path"),
                field_name="normalized_path",
            ),
            entry_kind=_required_str(payload, "entry_kind"),
        )


def _required_entries_manifest_payload(
    entries: Sequence[PreviewInputBindingEntry],
    *,
    binding_contract_version: str,
) -> dict[str, object]:
    return {
        "binding_contract_version": binding_contract_version,
        "entries": [entry.to_payload() for entry in entries],
    }


@dataclass(frozen=True, slots=True)
class PreviewInputBinding:
    binding_id: str
    workspace_id: str
    upload_generation: str
    preview_source_digest: DigestRef | str
    required_entries: tuple[PreviewInputBindingEntry, ...] = field(default_factory=tuple)
    parser_version: str = SQL_PARSER_VERSION
    table_ruleset_version: str = TABLE_RULESET_VERSION
    before_snapshot_digest: DigestRef | str | None = None
    current_snapshot_digest: DigestRef | str | None = None
    comparison_digest: DigestRef | str | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    binding_contract_version: str = PREVIEW_INPUT_BINDING_CONTRACT_VERSION
    required_entries_manifest_digest: DigestRef | str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.binding_id, str) or not self.binding_id:
            raise ValueError("binding_id must be a non-empty string")
        if not isinstance(self.workspace_id, str) or not self.workspace_id:
            raise ValueError("workspace_id must be a non-empty string")
        if not isinstance(self.upload_generation, str) or not self.upload_generation:
            raise ValueError("upload_generation must be a non-empty string")
        object.__setattr__(self, "preview_source_digest", _optional_digest(self.preview_source_digest))
        if not self.required_entries:
            raise ValueError("required_entries must contain at least one entry")
        if not isinstance(self.required_entries, tuple):
            object.__setattr__(self, "required_entries", tuple(self.required_entries))
        normalized_entries: list[PreviewInputBindingEntry] = []
        seen_entry_names: set[str] = set()
        for entry in self.required_entries:
            if not isinstance(entry, PreviewInputBindingEntry):
                raise TypeError("required_entries must contain PreviewInputBindingEntry values")
            if entry.entry_name in seen_entry_names:
                raise ValueError(f"duplicate required entry name: {entry.entry_name}")
            seen_entry_names.add(entry.entry_name)
            normalized_entries.append(entry)
        normalized_entries.sort(
            key=lambda item: (
                item.entry_name,
                item.normalized_path or "",
                item.entry_kind,
                item.content_digest.hex_digest,
            )
        )
        object.__setattr__(self, "required_entries", tuple(normalized_entries))
        for field_name in ("parser_version", "table_ruleset_version", "binding_contract_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        object.__setattr__(self, "before_snapshot_digest", _optional_digest(self.before_snapshot_digest))
        object.__setattr__(self, "current_snapshot_digest", _optional_digest(self.current_snapshot_digest))
        object.__setattr__(self, "comparison_digest", _optional_digest(self.comparison_digest))
        if not isinstance(self.generated_at, datetime):
            raise TypeError("generated_at must be a datetime")
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        computed_required_entries_manifest_digest = DigestRef.from_payload(
            _required_entries_manifest_payload(
                self.required_entries,
                binding_contract_version=self.binding_contract_version,
            )
        )
        if self.required_entries_manifest_digest is None:
            object.__setattr__(
                self,
                "required_entries_manifest_digest",
                computed_required_entries_manifest_digest,
            )
        else:
            object.__setattr__(
                self,
                "required_entries_manifest_digest",
                _optional_digest(self.required_entries_manifest_digest),
            )
            if self.required_entries_manifest_digest != computed_required_entries_manifest_digest:
                raise ValueError("required_entries_manifest_digest does not match required entries")

    def to_payload(self) -> dict[str, object]:
        return {
            "binding_id": self.binding_id,
            "workspace_id": self.workspace_id,
            "upload_generation": self.upload_generation,
            "preview_source_digest": self.preview_source_digest.to_payload(),
            "required_entries": [entry.to_payload() for entry in self.required_entries],
            "parser_version": self.parser_version,
            "table_ruleset_version": self.table_ruleset_version,
            "before_snapshot_digest": self.before_snapshot_digest.to_payload()
            if self.before_snapshot_digest is not None
            else None,
            "current_snapshot_digest": self.current_snapshot_digest.to_payload()
            if self.current_snapshot_digest is not None
            else None,
            "comparison_digest": self.comparison_digest.to_payload()
            if self.comparison_digest is not None
            else None,
            "generated_at": self.generated_at.astimezone(timezone.utc).isoformat(),
            "binding_contract_version": self.binding_contract_version,
            "required_entries_manifest_digest": self.required_entries_manifest_digest.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "PreviewInputBinding":
        required_entries_payload = payload.get("required_entries", [])
        if required_entries_payload is None:
            required_entries_payload = []
        if not isinstance(required_entries_payload, list):
            raise TypeError("required_entries payload must be a list")
        generated_at_value = payload.get("generated_at")
        if generated_at_value is None:
            generated_at = datetime.now(timezone.utc)
        else:
            generated_at = _optional_datetime(generated_at_value, field_name="generated_at")
            if generated_at is None:
                generated_at = datetime.now(timezone.utc)
        return cls(
            binding_id=_required_str(payload, "binding_id"),
            workspace_id=_required_str(payload, "workspace_id"),
            upload_generation=_required_str(payload, "upload_generation"),
            preview_source_digest=_required_str(payload, "preview_source_digest"),
            required_entries=tuple(
                PreviewInputBindingEntry.from_payload(item)
                for item in required_entries_payload
            ),
            parser_version=_required_str(payload, "parser_version"),
            table_ruleset_version=_required_str(payload, "table_ruleset_version"),
            before_snapshot_digest=_required_str(payload, "before_snapshot_digest"),
            current_snapshot_digest=_required_str(payload, "current_snapshot_digest"),
            comparison_digest=_required_str(payload, "comparison_digest"),
            generated_at=generated_at,
            binding_contract_version=_required_str(
                payload,
                "binding_contract_version",
            ),
            required_entries_manifest_digest=_optional_digest(
                payload.get("required_entries_manifest_digest"),
            ),
        )


@dataclass(frozen=True, slots=True)
class SubmitSourcePackage:
    source_package_id: str
    source_kind: str = SUBMIT_SOURCE_KIND
    package_kind: str = "DIRECTORY"
    source_package_digest: DigestRef | str | None = None
    package_manifest_digest: DigestRef | str | None = None
    required_entries_manifest_digest: DigestRef | str | None = None
    parser_version: str = SQL_PARSER_VERSION
    table_ruleset_version: str = TABLE_RULESET_VERSION
    artifact_ref: ArtifactRef | None = None
    size_bytes: int = 0
    created_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    retention_policy: str = "DEFAULT"
    diagnostics_ref: str | None = None
    submit_source_package_contract_version: str = SUBMIT_SOURCE_PACKAGE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.source_package_id, str) or not self.source_package_id:
            raise ValueError("source_package_id must be a non-empty string")
        if self.source_kind != SUBMIT_SOURCE_KIND:
            raise ValueError("source_kind must be SUBMIT_FULL")
        if not isinstance(self.package_kind, str) or not self.package_kind:
            raise ValueError("package_kind must be a non-empty string")
        object.__setattr__(self, "source_package_digest", _optional_digest(self.source_package_digest))
        object.__setattr__(self, "package_manifest_digest", _optional_digest(self.package_manifest_digest))
        object.__setattr__(
            self,
            "required_entries_manifest_digest",
            _optional_digest(self.required_entries_manifest_digest),
        )
        for field_name in ("parser_version", "table_ruleset_version", "submit_source_package_contract_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.artifact_ref is not None and not isinstance(self.artifact_ref, ArtifactRef):
            raise TypeError("artifact_ref must be an ArtifactRef or None")
        if (
            not isinstance(self.size_bytes, int)
            or isinstance(self.size_bytes, bool)
            or self.size_bytes < 0
        ):
            raise ValueError("size_bytes must be a non-negative integer")
        if self.created_by is not None and (not isinstance(self.created_by, str) or not self.created_by):
            raise ValueError("created_by must be a non-empty string or None")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.expires_at is not None:
            if not isinstance(self.expires_at, datetime):
                raise TypeError("expires_at must be a datetime or None")
            if self.expires_at.tzinfo is None:
                raise ValueError("expires_at must be timezone-aware")
        if not isinstance(self.retention_policy, str) or not self.retention_policy:
            raise ValueError("retention_policy must be a non-empty string")
        if self.diagnostics_ref is not None and (not isinstance(self.diagnostics_ref, str) or not self.diagnostics_ref):
            raise ValueError("diagnostics_ref must be a non-empty string or None")
        if self.artifact_ref is None:
            raise ValueError("artifact_ref must be provided for SubmitSourcePackage")
        if self.source_package_digest is None:
            raise ValueError("source_package_digest must be provided")
        if self.package_manifest_digest is None:
            raise ValueError("package_manifest_digest must be provided")
        if self.required_entries_manifest_digest is None:
            raise ValueError("required_entries_manifest_digest must be provided")

    def to_payload(self) -> dict[str, object]:
        return {
            "source_package_id": self.source_package_id,
            "source_kind": self.source_kind,
            "package_kind": self.package_kind,
            "source_package_digest": self.source_package_digest.to_payload(),
            "package_manifest_digest": self.package_manifest_digest.to_payload(),
            "required_entries_manifest_digest": self.required_entries_manifest_digest.to_payload(),
            "parser_version": self.parser_version,
            "table_ruleset_version": self.table_ruleset_version,
            "artifact_ref": self.artifact_ref.to_payload(),
            "size_bytes": self.size_bytes,
            "created_by": self.created_by,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "expires_at": (
                None
                if self.expires_at is None
                else self.expires_at.astimezone(timezone.utc).isoformat()
            ),
            "retention_policy": self.retention_policy,
            "diagnostics_ref": self.diagnostics_ref,
            "submit_source_package_contract_version": self.submit_source_package_contract_version,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "SubmitSourcePackage":
        return cls(
            source_package_id=_required_str(payload, "source_package_id"),
            source_kind=_required_str(payload, "source_kind"),
            package_kind=_required_str(payload, "package_kind"),
            source_package_digest=_required_str(payload, "source_package_digest"),
            package_manifest_digest=_required_str(payload, "package_manifest_digest"),
            required_entries_manifest_digest=_required_str(
                payload,
                "required_entries_manifest_digest",
            ),
            parser_version=_required_str(payload, "parser_version"),
            table_ruleset_version=_required_str(payload, "table_ruleset_version"),
            artifact_ref=_required_artifact_ref(payload, "artifact_ref"),
            size_bytes=_required_positive_int(payload, "size_bytes"),
            created_by=_optional_str(payload.get("created_by"), field_name="created_by"),
            created_at=_optional_datetime(payload.get("created_at"), field_name="created_at")
            or datetime.now(timezone.utc),
            expires_at=_optional_datetime(payload.get("expires_at"), field_name="expires_at"),
            retention_policy=_required_str(payload, "retention_policy"),
            diagnostics_ref=_optional_str(
                payload.get("diagnostics_ref"),
                field_name="diagnostics_ref",
            ),
            submit_source_package_contract_version=_required_str(
                payload,
                "submit_source_package_contract_version",
            ),
        )


class SubmitOperationStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    FINALIZING = "FINALIZING"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class SubmitAccepted:
    operation_id: str
    submission_id: str
    status: SubmitOperationStatus | str = SubmitOperationStatus.ACCEPTED
    source_package_id: str | None = None
    binding_id: str | None = None
    accepted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    submit_source_package_digest: DigestRef | str | None = None
    required_entries_manifest_digest: DigestRef | str | None = None
    parser_version: str = SQL_PARSER_VERSION
    table_ruleset_version: str = TABLE_RULESET_VERSION
    preview_source_digest: DigestRef | str | None = None
    submit_accepted_contract_version: str = SUBMIT_ACCEPTED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, str) or not self.operation_id:
            raise ValueError("operation_id must be a non-empty string")
        if not isinstance(self.submission_id, str) or not self.submission_id:
            raise ValueError("submission_id must be a non-empty string")
        object.__setattr__(self, "status", SubmitOperationStatus(self.status))
        if not isinstance(self.source_package_id, str) or not self.source_package_id:
            raise ValueError("source_package_id must be a non-empty string")
        if not isinstance(self.binding_id, str) or not self.binding_id:
            raise ValueError("binding_id must be a non-empty string")
        if not isinstance(self.accepted_at, datetime):
            raise TypeError("accepted_at must be a datetime")
        if self.accepted_at.tzinfo is None:
            raise ValueError("accepted_at must be timezone-aware")
        object.__setattr__(self, "submit_source_package_digest", _optional_digest(self.submit_source_package_digest))
        object.__setattr__(self, "required_entries_manifest_digest", _optional_digest(self.required_entries_manifest_digest))
        object.__setattr__(self, "preview_source_digest", _optional_digest(self.preview_source_digest))
        for field_name in (
            "parser_version",
            "table_ruleset_version",
            "submit_accepted_contract_version",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.submit_source_package_digest is None:
            raise ValueError("submit_source_package_digest must be provided")
        if self.required_entries_manifest_digest is None:
            raise ValueError("required_entries_manifest_digest must be provided")

    def to_payload(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "submission_id": self.submission_id,
            "status": self.status.value,
            "source_package_id": self.source_package_id,
            "binding_id": self.binding_id,
            "accepted_at": self.accepted_at.astimezone(timezone.utc).isoformat(),
            "submit_source_package_digest": self.submit_source_package_digest.to_payload(),
            "required_entries_manifest_digest": self.required_entries_manifest_digest.to_payload(),
            "parser_version": self.parser_version,
            "table_ruleset_version": self.table_ruleset_version,
            "preview_source_digest": (
                None
                if self.preview_source_digest is None
                else self.preview_source_digest.to_payload()
            ),
            "submit_accepted_contract_version": self.submit_accepted_contract_version,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "SubmitAccepted":
        accepted_at_value = payload.get("accepted_at")
        accepted_at = (
            _optional_datetime(accepted_at_value, field_name="accepted_at")
            if accepted_at_value is not None
            else datetime.now(timezone.utc)
        )
        if accepted_at is None:
            accepted_at = datetime.now(timezone.utc)
        return cls(
            operation_id=_required_str(payload, "operation_id"),
            submission_id=_required_str(payload, "submission_id"),
            status=_required_str(payload, "status"),
            source_package_id=_required_str(payload, "source_package_id"),
            binding_id=_required_str(payload, "binding_id"),
            accepted_at=accepted_at,
            submit_source_package_digest=_required_str(
                payload,
                "submit_source_package_digest",
            ),
            required_entries_manifest_digest=_required_str(
                payload,
                "required_entries_manifest_digest",
            ),
            parser_version=_required_str(payload, "parser_version"),
            table_ruleset_version=_required_str(payload, "table_ruleset_version"),
            preview_source_digest=_optional_digest(payload.get("preview_source_digest")),
            submit_accepted_contract_version=_required_str(
                payload,
                "submit_accepted_contract_version",
            ),
        )


def validate_submit_source_package_binding(
    submit_source_package: SubmitSourcePackage,
    preview_input_binding: PreviewInputBinding,
) -> None:
    if not isinstance(submit_source_package, SubmitSourcePackage):
        raise TypeError("submit_source_package must be a SubmitSourcePackage")
    if not isinstance(preview_input_binding, PreviewInputBinding):
        raise TypeError("preview_input_binding must be a PreviewInputBinding")
    if submit_source_package.source_kind != SUBMIT_SOURCE_KIND:
        raise ValueError("submit source package must be a SUBMIT_FULL package")
    if submit_source_package.required_entries_manifest_digest != preview_input_binding.required_entries_manifest_digest:
        raise ValueError("required entries digest mismatch between submit source package and preview binding")
    if submit_source_package.parser_version != preview_input_binding.parser_version:
        raise ValueError("parser_version mismatch between submit source package and preview binding")
    if submit_source_package.table_ruleset_version != preview_input_binding.table_ruleset_version:
        raise ValueError("table_ruleset_version mismatch between submit source package and preview binding")
