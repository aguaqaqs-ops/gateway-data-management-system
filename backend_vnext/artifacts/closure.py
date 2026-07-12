from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..core.digests import DigestRef, canonical_json_bytes
from ..core.diagnostics import DiagnosticRecord
from .local_store import LocalArtifactStore, StoredArtifact
from .manifest import ArtifactManifest, ArtifactRef
from .records import RecordsArtifact, restore_records_artifact
from .versions import (
    COMPARISON_RECORDS_CLOSURE_ARTIFACT_KIND,
    COMPARISON_RECORDS_CLOSURE_CONTRACT_VERSION,
    COMPARISON_RECORDS_CLOSURE_SCHEMA_VERSION,
)


@dataclass(frozen=True, slots=True)
class ComparisonRecordsClosureMember:
    table_name: str
    records_ref: ArtifactRef
    record_count: int
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name:
            raise ValueError("table_name must be a non-empty string")
        if not isinstance(self.records_ref, ArtifactRef):
            raise TypeError("records_ref must be an ArtifactRef")
        if (
            not isinstance(self.record_count, int)
            or isinstance(self.record_count, bool)
            or self.record_count < 0
        ):
            raise ValueError("record_count must be a non-negative integer")
        object.__setattr__(self, "metadata", _mapping_payload(self.metadata))

    @property
    def records_manifest_digest(self) -> DigestRef:
        return self.records_ref.manifest_digest

    @property
    def records_content_digest(self) -> DigestRef:
        return self.records_ref.content_digest

    def to_payload(self) -> dict[str, object]:
        return {
            "table_name": self.table_name,
            "records_ref": self.records_ref.to_payload(),
            "records_manifest_digest": self.records_manifest_digest.to_payload(),
            "records_content_digest": self.records_content_digest.to_payload(),
            "record_count": self.record_count,
            "metadata": _mapping_payload(self.metadata),
        }

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object],
    ) -> "ComparisonRecordsClosureMember":
        records_ref = ArtifactRef.from_payload(_mapping_payload(_mapping_value(payload, "records_ref")))
        manifest_digest = _optional_digest(payload.get("records_manifest_digest"))
        if manifest_digest is not None and manifest_digest != records_ref.manifest_digest:
            raise ValueError("records_manifest_digest does not match records_ref")
        content_digest = _optional_digest(payload.get("records_content_digest"))
        if content_digest is not None and content_digest != records_ref.content_digest:
            raise ValueError("records_content_digest does not match records_ref")
        record_count_value = payload["record_count"]
        if not isinstance(record_count_value, int) or isinstance(record_count_value, bool):
            raise TypeError("record_count must be an integer")
        return cls(
            table_name=_required_str(payload, "table_name"),
            records_ref=records_ref,
            record_count=record_count_value,
            metadata=_mapping_payload(_mapping_value(payload, "metadata")),
        )


@dataclass(frozen=True, slots=True)
class ComparisonRecordsClosureManifest:
    comparison_digest: DigestRef | str
    facts_core_digest: DigestRef | str
    records: tuple[ComparisonRecordsClosureMember, ...] = field(default_factory=tuple)
    closure_contract_version: str = COMPARISON_RECORDS_CLOSURE_CONTRACT_VERSION
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "comparison_digest", _coerce_digest(self.comparison_digest))
        object.__setattr__(self, "facts_core_digest", _coerce_digest(self.facts_core_digest))
        if not isinstance(self.closure_contract_version, str) or not self.closure_contract_version:
            raise ValueError("closure_contract_version must be a non-empty string")
        normalized_records: list[ComparisonRecordsClosureMember] = []
        for record in self.records:
            if not isinstance(record, ComparisonRecordsClosureMember):
                raise TypeError("records must contain ComparisonRecordsClosureMember values")
            normalized_records.append(record)
        object.__setattr__(self, "records", tuple(normalized_records))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if self.created_at is not None and not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime or None")
        if self.created_at is not None and self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": COMPARISON_RECORDS_CLOSURE_SCHEMA_VERSION,
            "closure_contract_version": self.closure_contract_version,
            "comparison_digest": self.comparison_digest.to_payload(),
            "facts_core_digest": self.facts_core_digest.to_payload(),
            "records": [record.to_payload() for record in self.records],
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
            "created_at": (
                None
                if self.created_at is None
                else self.created_at.astimezone(timezone.utc).isoformat()
            ),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "ComparisonRecordsClosureManifest":
        schema_version = _required_str(payload, "schema_version")
        if schema_version != COMPARISON_RECORDS_CLOSURE_SCHEMA_VERSION:
            raise ValueError("unsupported comparison records closure schema version")
        records_payload = payload.get("records", [])
        if not isinstance(records_payload, list):
            raise TypeError("records payload must be a list")
        diagnostics_payload = payload.get("diagnostics", [])
        if not isinstance(diagnostics_payload, list):
            raise TypeError("diagnostics payload must be a list")
        created_at_value = payload.get("created_at")
        created_at = (
            None
            if created_at_value is None
            else datetime.fromisoformat(_required_str({"created_at": created_at_value}, "created_at"))
        )
        return cls(
            comparison_digest=DigestRef.parse(_required_str(payload, "comparison_digest")),
            facts_core_digest=DigestRef.parse(_required_str(payload, "facts_core_digest")),
            records=tuple(
                ComparisonRecordsClosureMember.from_payload(item)
                for item in records_payload
            ),
            closure_contract_version=_required_str(
                payload,
                "closure_contract_version",
            ),
            diagnostics=tuple(
                DiagnosticRecord.from_payload(item)
                for item in diagnostics_payload
            ),
            created_at=created_at,
        )

    def to_artifact_manifest(self) -> ArtifactManifest:
        payload = self.to_payload()
        content_bytes = canonical_json_bytes(payload)
        metadata = {
            "comparison_digest": self.comparison_digest.to_payload(),
            "facts_core_digest": self.facts_core_digest.to_payload(),
            "record_count": len(self.records),
            "table_names": [record.table_name for record in self.records],
            "closure_schema_version": COMPARISON_RECORDS_CLOSURE_SCHEMA_VERSION,
        }
        return ArtifactManifest(
            artifact_kind=COMPARISON_RECORDS_CLOSURE_ARTIFACT_KIND,
            artifact_contract_version=self.closure_contract_version,
            content_digest=DigestRef.from_bytes(content_bytes),
            content_size_bytes=len(content_bytes),
            metadata=metadata,
            diagnostics=self.diagnostics,
            created_at=self.created_at,
        )


@dataclass(frozen=True, slots=True)
class ComparisonRecordsClosureArtifact:
    manifest: ComparisonRecordsClosureManifest
    stored: StoredArtifact

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, ComparisonRecordsClosureManifest):
            raise TypeError("manifest must be a ComparisonRecordsClosureManifest")
        if not isinstance(self.stored, StoredArtifact):
            raise TypeError("stored must be a StoredArtifact")
        if self.stored.manifest.artifact_kind != COMPARISON_RECORDS_CLOSURE_ARTIFACT_KIND:
            raise ValueError("stored artifact is not a comparison records closure")
        if self.stored.manifest.artifact_contract_version != self.manifest.closure_contract_version:
            raise ValueError("stored manifest contract version does not match closure")

    @property
    def ref(self) -> ArtifactRef:
        return self.stored.ref

    @property
    def manifest_path(self) -> Path:
        return self.stored.manifest_path

    @property
    def content_path(self) -> Path:
        return self.stored.content_path

    @property
    def artifact_dir(self) -> Path:
        return self.stored.artifact_dir

    @property
    def reused(self) -> bool:
        return self.stored.reused


@dataclass(frozen=True, slots=True)
class ComparisonRecordsClosureRestoreResult:
    closure_artifact: ComparisonRecordsClosureArtifact
    records_artifacts: tuple[RecordsArtifact, ...] = field(default_factory=tuple)


def store_comparison_records_closure(
    store: LocalArtifactStore,
    manifest: ComparisonRecordsClosureManifest,
) -> ComparisonRecordsClosureArtifact:
    content_bytes = canonical_json_bytes(manifest.to_payload())
    stored = store.put_bytes(manifest.to_artifact_manifest(), content_bytes)
    return ComparisonRecordsClosureArtifact(
        manifest=ComparisonRecordsClosureManifest.from_payload(
            _json_loads(stored.content_path.read_bytes())
        ),
        stored=stored,
    )


def read_comparison_records_closure(
    store: LocalArtifactStore,
    ref: ArtifactRef | DigestRef | str,
) -> ComparisonRecordsClosureArtifact:
    stored = store.read(ref)
    if stored.manifest.artifact_kind != COMPARISON_RECORDS_CLOSURE_ARTIFACT_KIND:
        raise ValueError("artifact is not a comparison records closure")
    if stored.manifest.artifact_contract_version != COMPARISON_RECORDS_CLOSURE_CONTRACT_VERSION:
        raise ValueError("unsupported comparison records closure contract version")
    manifest = ComparisonRecordsClosureManifest.from_payload(
        _json_loads(stored.content_path.read_bytes())
    )
    return ComparisonRecordsClosureArtifact(manifest=manifest, stored=stored)


def restore_comparison_records_closure(
    source_store: LocalArtifactStore,
    target_store: LocalArtifactStore,
    ref: ArtifactRef | DigestRef | str,
) -> ComparisonRecordsClosureRestoreResult:
    source_closure = read_comparison_records_closure(source_store, ref)
    restored_records: list[RecordsArtifact] = []
    for member in source_closure.manifest.records:
        restored_records.append(
            restore_records_artifact(source_store, target_store, member.records_ref)
        )
    closure_artifact = store_comparison_records_closure(
        target_store,
        source_closure.manifest,
    )
    return ComparisonRecordsClosureRestoreResult(
        closure_artifact=closure_artifact,
        records_artifacts=tuple(restored_records),
    )


def _json_loads(raw: bytes) -> Mapping[str, object]:
    import json

    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError("artifact payload must be a mapping")
    return _mapping_payload(payload)


def _mapping_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("mapping keys must be strings")
        normalized[key] = value
    return normalized


def _mapping_value(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
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


def _optional_digest(value: object) -> DigestRef | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("digest values must be strings or null")
    return DigestRef.parse(value)


def _coerce_digest(value: DigestRef | str) -> DigestRef:
    if isinstance(value, DigestRef):
        return value
    return DigestRef.parse(value)
