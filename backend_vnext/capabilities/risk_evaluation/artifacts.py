from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ...artifacts.manifest import ArtifactRef
from ...core.digests import DigestRef, canonical_json_bytes
from ...core.diagnostics import DiagnosticRecord
from .models import RiskAnnotation, RiskReason, RiskTarget, RiskTargetType
from .versions import RISK_ANNOTATION_ARTIFACT_CONTRACT_VERSION


RISK_ANNOTATION_ARTIFACT_KIND = "risk-annotations"
RISK_ANNOTATION_ARTIFACT_ROOT_NAME = "risk"
RISK_ANNOTATION_ARTIFACT_COLLECTION_NAME = "annotations"
RISK_ANNOTATION_ARTIFACT_MANIFEST_FILENAME = "manifest.json"
RISK_ANNOTATION_ARTIFACT_CONTENT_FILENAME = "content.json"


@dataclass(frozen=True, slots=True)
class StoredRiskAnnotationArtifact:
    artifact: "RiskAnnotationArtifact"
    manifest_path: Path
    content_path: Path
    reused: bool = False

    @property
    def artifact_dir(self) -> Path:
        return self.manifest_path.parent

    @property
    def ref(self) -> ArtifactRef:
        return self.artifact.ref


@dataclass(frozen=True, slots=True)
class RiskAnnotationArtifact:
    table_name: str
    annotations: tuple[RiskAnnotation, ...] = field(default_factory=tuple)
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    annotation_artifact_contract_version: str = RISK_ANNOTATION_ARTIFACT_CONTRACT_VERSION
    created_at: datetime | None = None
    content_digest: DigestRef | str | None = None
    manifest_digest: DigestRef | str | None = None
    artifact_ref: ArtifactRef | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name.strip():
            raise ValueError("table_name must be a non-empty string")
        if not isinstance(self.annotation_artifact_contract_version, str) or not self.annotation_artifact_contract_version.strip():
            raise ValueError("annotation_artifact_contract_version must be a non-empty string")
        if not isinstance(self.annotations, tuple):
            object.__setattr__(self, "annotations", tuple(self.annotations))
        normalized_annotations: list[RiskAnnotation] = []
        for annotation in self.annotations:
            if not isinstance(annotation, RiskAnnotation):
                raise TypeError("annotations must contain RiskAnnotation values")
            normalized_annotations.append(annotation)
        object.__setattr__(self, "annotations", tuple(normalized_annotations))
        if not isinstance(self.diagnostics, tuple):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))
        if self.created_at is not None:
            if not isinstance(self.created_at, datetime):
                raise TypeError("created_at must be a datetime or None")
            if self.created_at.tzinfo is None:
                raise ValueError("created_at must be timezone-aware")
        computed_content_digest = DigestRef.from_bytes(canonical_json_bytes(self.content_payload()))
        if self.content_digest is None:
            object.__setattr__(self, "content_digest", computed_content_digest)
        else:
            content_digest = DigestRef.parse(str(self.content_digest))
            if content_digest != computed_content_digest:
                raise ValueError("content_digest does not match annotation payload")
            object.__setattr__(self, "content_digest", content_digest)
        computed_manifest_digest = DigestRef.from_payload(self.manifest_payload())
        if self.manifest_digest is None:
            object.__setattr__(self, "manifest_digest", computed_manifest_digest)
        else:
            manifest_digest = DigestRef.parse(str(self.manifest_digest))
            if manifest_digest != computed_manifest_digest:
                raise ValueError("manifest_digest does not match annotation manifest payload")
            object.__setattr__(self, "manifest_digest", manifest_digest)
        if self.artifact_ref is None:
            object.__setattr__(
                self,
                "artifact_ref",
                ArtifactRef(
                    artifact_kind=RISK_ANNOTATION_ARTIFACT_KIND,
                    artifact_contract_version=self.annotation_artifact_contract_version,
                    manifest_digest=self.manifest_digest,
                    content_digest=self.content_digest,
                ),
            )
        else:
            if not isinstance(self.artifact_ref, ArtifactRef):
                raise TypeError("artifact_ref must be an ArtifactRef or None")
            if self.artifact_ref.artifact_kind != RISK_ANNOTATION_ARTIFACT_KIND:
                raise ValueError("artifact_ref is not a risk annotation artifact")
            if self.artifact_ref.artifact_contract_version != self.annotation_artifact_contract_version:
                raise ValueError("artifact_ref contract version does not match annotation artifact contract")
            if self.artifact_ref.manifest_digest != self.manifest_digest:
                raise ValueError("artifact_ref manifest digest does not match annotation artifact")
            if self.artifact_ref.content_digest != self.content_digest:
                raise ValueError("artifact_ref content digest does not match annotation artifact")

    @property
    def annotation_count(self) -> int:
        return len(self.annotations)

    @property
    def ref(self) -> ArtifactRef:
        if self.artifact_ref is None:
            raise ValueError("artifact_ref is not set")
        return self.artifact_ref

    def content_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.annotation_artifact_contract_version,
            "table_name": self.table_name,
            "annotations": [annotation.to_payload() for annotation in self.annotations],
        }
        if self.diagnostics:
            payload["diagnostics"] = [diagnostic.to_payload() for diagnostic in self.diagnostics]
        if self.created_at is not None:
            payload["created_at"] = self.created_at.astimezone(timezone.utc).isoformat()
        return payload

    def manifest_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.annotation_artifact_contract_version,
            "artifact_kind": RISK_ANNOTATION_ARTIFACT_KIND,
            "artifact_contract_version": self.annotation_artifact_contract_version,
            "table_name": self.table_name,
            "annotation_count": self.annotation_count,
            "content_digest": self.content_digest.to_payload() if self.content_digest is not None else None,
            "content_size_bytes": len(canonical_json_bytes(self.content_payload())),
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
            "created_at": (
                None
                if self.created_at is None
                else self.created_at.astimezone(timezone.utc).isoformat()
            ),
        }

    def to_payload(self) -> dict[str, object]:
        return {
            **self.content_payload(),
            "manifest_digest": self.manifest_digest.to_payload() if self.manifest_digest is not None else None,
            "artifact_ref": self.artifact_ref.to_payload() if self.artifact_ref is not None else None,
        }

    @classmethod
    def from_payloads(
        cls,
        *,
        content_payload: Mapping[str, object],
        manifest_payload: Mapping[str, object],
    ) -> "RiskAnnotationArtifact":
        content_schema_version = _required_str(content_payload, "schema_version")
        manifest_schema_version = _required_str(manifest_payload, "schema_version")
        if content_schema_version != RISK_ANNOTATION_ARTIFACT_CONTRACT_VERSION:
            raise ValueError("unsupported risk annotation content schema version")
        if manifest_schema_version != RISK_ANNOTATION_ARTIFACT_CONTRACT_VERSION:
            raise ValueError("unsupported risk annotation manifest schema version")

        manifest_artifact_kind = _required_str(manifest_payload, "artifact_kind")
        if manifest_artifact_kind != RISK_ANNOTATION_ARTIFACT_KIND:
            raise ValueError("manifest is not a risk annotation artifact")
        manifest_contract_version = _required_str(manifest_payload, "artifact_contract_version")
        if manifest_contract_version != RISK_ANNOTATION_ARTIFACT_CONTRACT_VERSION:
            raise ValueError("unsupported risk annotation artifact contract version")

        table_name = _required_str(content_payload, "table_name")
        manifest_table_name = _required_str(manifest_payload, "table_name")
        if table_name != manifest_table_name:
            raise ValueError("table_name does not match between content and manifest")

        annotations = tuple(
            _risk_annotation_from_payload(annotation_payload)
            for annotation_payload in _sequence_payload(content_payload.get("annotations"))
        )
        content_diagnostics = tuple(
            DiagnosticRecord.from_payload(diagnostic_payload)
            for diagnostic_payload in _sequence_payload(content_payload.get("diagnostics"))
        )
        manifest_diagnostics = tuple(
            DiagnosticRecord.from_payload(diagnostic_payload)
            for diagnostic_payload in _sequence_payload(manifest_payload.get("diagnostics"))
        )
        if content_diagnostics != manifest_diagnostics:
            raise ValueError("diagnostics do not match between content and manifest")

        content_created_at = _optional_datetime(content_payload.get("created_at"))
        manifest_created_at = _optional_datetime(manifest_payload.get("created_at"))
        if content_created_at != manifest_created_at:
            raise ValueError("created_at does not match between content and manifest")

        annotation_count = _required_int(manifest_payload, "annotation_count")
        if annotation_count != len(annotations):
            raise ValueError("annotation_count does not match annotations payload")

        content_bytes = canonical_json_bytes(_mapping_payload(content_payload))
        content_digest = DigestRef.from_bytes(content_bytes)
        manifest_content_digest = DigestRef.parse(_required_str(manifest_payload, "content_digest"))
        if manifest_content_digest != content_digest:
            raise ValueError("content_digest does not match annotation payload")
        content_size_bytes = _required_int(manifest_payload, "content_size_bytes")
        if content_size_bytes != len(content_bytes):
            raise ValueError("content_size_bytes does not match annotation payload")

        return cls(
            table_name=table_name,
            annotations=annotations,
            diagnostics=content_diagnostics,
            annotation_artifact_contract_version=manifest_contract_version,
            created_at=content_created_at,
            content_digest=content_digest,
            manifest_digest=DigestRef.from_payload(_mapping_payload(manifest_payload)),
        )


def store_risk_annotation_artifact(
    root: Path,
    artifact: RiskAnnotationArtifact,
) -> StoredRiskAnnotationArtifact:
    if not isinstance(root, Path):
        raise TypeError("root must be a Path")
    if not isinstance(artifact, RiskAnnotationArtifact):
        raise TypeError("artifact must be a RiskAnnotationArtifact")

    content_payload = artifact.content_payload()
    manifest_payload = artifact.manifest_payload()
    content_bytes = canonical_json_bytes(content_payload)
    manifest_bytes = canonical_json_bytes(manifest_payload)
    artifact_dir = _risk_annotation_artifact_dir(root, artifact.manifest_digest)
    manifest_path = artifact_dir / RISK_ANNOTATION_ARTIFACT_MANIFEST_FILENAME
    content_path = artifact_dir / RISK_ANNOTATION_ARTIFACT_CONTENT_FILENAME

    if manifest_path.exists() or content_path.exists():
        existing = _read_stored_risk_annotation_artifact(root, artifact.manifest_digest)
        if existing.artifact != artifact:
            raise ValueError("risk annotation artifact already exists with different payload")
        return StoredRiskAnnotationArtifact(
            artifact=existing.artifact,
            manifest_path=existing.manifest_path,
            content_path=existing.content_path,
            reused=True,
        )

    artifact_dir.mkdir(parents=True, exist_ok=True)
    _write_bytes(content_path, content_bytes)
    _write_bytes(manifest_path, manifest_bytes)
    return StoredRiskAnnotationArtifact(
        artifact=artifact,
        manifest_path=manifest_path,
        content_path=content_path,
    )


def read_risk_annotation_artifact(
    root: Path,
    ref: ArtifactRef | DigestRef | str,
) -> StoredRiskAnnotationArtifact:
    manifest_digest = _coerce_manifest_digest(ref)
    stored = _read_stored_risk_annotation_artifact(root, manifest_digest)
    if isinstance(ref, ArtifactRef):
        if ref.artifact_kind != RISK_ANNOTATION_ARTIFACT_KIND:
            raise ValueError("artifact ref is not a risk annotation artifact")
        if stored.ref != ref:
            raise ValueError("artifact ref does not match stored risk annotation artifact")
    return stored


def restore_risk_annotation_artifact(
    source_root: Path,
    target_root: Path,
    ref: ArtifactRef | DigestRef | str,
) -> StoredRiskAnnotationArtifact:
    source_artifact = read_risk_annotation_artifact(source_root, ref)
    return store_risk_annotation_artifact(target_root, source_artifact.artifact)


def _read_stored_risk_annotation_artifact(
    root: Path,
    manifest_digest: DigestRef,
) -> StoredRiskAnnotationArtifact:
    artifact_dir = _risk_annotation_artifact_dir(root, manifest_digest)
    manifest_path = artifact_dir / RISK_ANNOTATION_ARTIFACT_MANIFEST_FILENAME
    content_path = artifact_dir / RISK_ANNOTATION_ARTIFACT_CONTENT_FILENAME
    if not manifest_path.is_file() or not content_path.is_file():
        raise KeyError("risk annotation artifact not found")

    manifest_bytes = manifest_path.read_bytes()
    content_bytes = content_path.read_bytes()
    if DigestRef.from_bytes(manifest_bytes) != manifest_digest:
        raise ValueError("risk annotation manifest digest mismatch")

    manifest_payload = _json_loads(manifest_bytes)
    content_payload = _json_loads(content_bytes)
    artifact = RiskAnnotationArtifact.from_payloads(
        content_payload=content_payload,
        manifest_payload=manifest_payload,
    )
    return StoredRiskAnnotationArtifact(
        artifact=artifact,
        manifest_path=manifest_path,
        content_path=content_path,
    )


def _risk_annotation_artifact_dir(root: Path, manifest_digest: DigestRef) -> Path:
    return (
        root
        / RISK_ANNOTATION_ARTIFACT_ROOT_NAME
        / RISK_ANNOTATION_ARTIFACT_COLLECTION_NAME
        / manifest_digest.hex_digest
    )


def _risk_annotation_from_payload(payload: Mapping[str, object]) -> RiskAnnotation:
    target_payload = _mapping_value(payload, "target")
    target = _risk_target_from_payload(target_payload)
    target_type = RiskTargetType(_required_str(payload, "target_type"))
    if target.target_type is not target_type:
        raise ValueError("target_type does not match target payload")
    return RiskAnnotation(
        annotation_id=_required_str(payload, "annotation_id"),
        target=target,
        risk_level=_required_str(payload, "risk_level"),
        reasons=tuple(
            _risk_reason_from_payload(reason_payload)
            for reason_payload in _sequence_payload(payload.get("reasons"))
        ),
        diagnostics=tuple(
            DiagnosticRecord.from_payload(diagnostic_payload)
            for diagnostic_payload in _sequence_payload(payload.get("diagnostics"))
        ),
    )


def _risk_target_from_payload(payload: Mapping[str, object]) -> RiskTarget:
    return RiskTarget(
        target_type=_required_str(payload, "target_type"),
        table_name=_optional_str(payload.get("table_name")),
        row_identity=_optional_str(payload.get("row_identity")),
        before_row_identity=_optional_str(payload.get("before_row_identity")),
        current_row_identity=_optional_str(payload.get("current_row_identity")),
        changed_columns=_sequence_payload(payload.get("changed_columns")),
        position=_optional_int(payload.get("position")),
        position_range=_optional_position_range(payload.get("position_range")),
        coverage=_optional_str(payload.get("coverage")),
        row_side=_optional_str(payload.get("row_side")),
        entity_key=_optional_str(payload.get("entity_key")),
        before_entity_key=_optional_str(payload.get("before_entity_key")),
        after_entity_key=_optional_str(payload.get("after_entity_key")),
        before_position=_optional_int(payload.get("before_position")),
        after_position=_optional_int(payload.get("after_position")),
        position_start=_optional_int(payload.get("position_start")),
        position_end=_optional_int(payload.get("position_end")),
        row_count=_optional_int(payload.get("row_count")),
        interval_id=_optional_str(payload.get("interval_id")),
    )


def _risk_reason_from_payload(payload: Mapping[str, object]) -> RiskReason:
    return RiskReason(
        reason_code=_required_str(payload, "reason_code"),
        message=_required_str(payload, "message"),
        rule_id=_required_str(payload, "rule_id"),
        evidence=_mapping_value(payload, "evidence"),
    )


def _sequence_payload(value: object | None) -> tuple[object, ...]:
    if value is None:
        return tuple()
    if isinstance(value, (str, bytes, bytearray)):
        raise TypeError("value must be a sequence, not text")
    if isinstance(value, tuple):
        return value
    if isinstance(value, Sequence):
        return tuple(value)
    raise TypeError("value must be a sequence")


def _optional_int(value: object | None) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("value must be an integer or None")
    return value


def _optional_position_range(value: object | None) -> tuple[int, int] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("position_range must be a sequence or None")
    items = tuple(value)
    if len(items) != 2:
        raise ValueError("position_range must contain exactly two integers")
    start, end = items
    if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
        raise TypeError("position_range values must be integers")
    return (start, end)


def _optional_datetime(value: object | None) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("created_at must be a string or None")
    created_at = datetime.fromisoformat(value)
    if created_at.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")
    return created_at


def _write_bytes(path: Path, data: bytes) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_bytes(data)
    tmp_path.replace(path)


def _json_loads(raw: bytes) -> Mapping[str, object]:
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError("artifact payload must be a mapping")
    return _mapping_payload(payload)


def _coerce_manifest_digest(ref: ArtifactRef | DigestRef | str) -> DigestRef:
    if isinstance(ref, ArtifactRef):
        return ref.manifest_digest
    if isinstance(ref, DigestRef):
        return ref
    return DigestRef.parse(ref)


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


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an integer")
    return value


def _optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("value must be a string or None")
    return value
