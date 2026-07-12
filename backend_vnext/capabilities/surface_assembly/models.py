from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum

from ...artifacts.manifest import ArtifactRef
from ...core.digests import DigestRef
from ...core.diagnostics import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from ..comparison.models import ComparisonFacts, ComparisonRecordsClosure, ComparisonRole, ComparisonTableFact, ComparisonTableStatus
from ..business_projection.models import BusinessProjectionResult
from ..risk_evaluation.models import RiskLevel, RiskReport, RiskTableRisk
from .digest import build_surface_digest
from .ref_validation import ensure_logical_relative_ref, ensure_logical_relative_refs, ensure_surface_options
from .versions import (
    SURFACE_CONTRACT_VERSION,
    SURFACE_ORDERED_EXTENSION_CONTRACT_VERSION,
    SURFACE_PROFILE_STANDARD_TABLE_BROWSER,
    SURFACE_REF_SCOPE_BUNDLE_RELATIVE,
    SURFACE_REF_SCOPE_OPERATION_RELATIVE,
)


def _mapping_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("mapping keys must be strings")
        normalized[key] = value
    return normalized


def _optional_digest(value: DigestRef | str | None) -> DigestRef | None:
    if value is None:
        return None
    if isinstance(value, DigestRef):
        return value
    return DigestRef.parse(value)


def _normalize_str_tuple(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, tuple):
        values = tuple(values)
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise ValueError("tuple values must be non-empty strings")
        normalized.append(value)
    return tuple(normalized)


class SurfaceProfile(StrEnum):
    STANDARD_TABLE_BROWSER = SURFACE_PROFILE_STANDARD_TABLE_BROWSER


class SurfaceRefScope(StrEnum):
    OPERATION_RELATIVE = SURFACE_REF_SCOPE_OPERATION_RELATIVE
    BUNDLE_RELATIVE = SURFACE_REF_SCOPE_BUNDLE_RELATIVE


class SurfaceChangeKind(StrEnum):
    UNCHANGED = "UNCHANGED"
    BUSINESS_EQUIVALENT = "BUSINESS_EQUIVALENT"
    ADDED = "ADDED"
    DELETED = "DELETED"
    UPDATED = "UPDATED"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class SurfaceDisplayStrategy(StrEnum):
    SUMMARY_ONLY = "SUMMARY_ONLY"
    TABLE_BROWSE = "TABLE_BROWSE"
    RECORDS_ONLY = "RECORDS_ONLY"
    CURRENT_WITH_RECORDS = "CURRENT_WITH_RECORDS"
    DEGRADED_NOTICE = "DEGRADED_NOTICE"


class SurfaceTableProcessingMode(StrEnum):
    STANDARD = "STANDARD"
    SCHEMA_ONLY = "SCHEMA_ONLY"
    DEGRADED = "DEGRADED"


class SurfaceReplayGuarantee(StrEnum):
    EXACT = "EXACT"
    SUMMARY_ONLY = "SUMMARY_ONLY"
    UNSUPPORTED = "UNSUPPORTED"


class SurfaceRecordsFormat(StrEnum):
    PARQUET = "PARQUET"
    INLINE_SUMMARY = "INLINE_SUMMARY"


class SurfaceHiddenTableReason(StrEnum):
    EMPTY_UNCHANGED_TABLE = "EMPTY_UNCHANGED_TABLE"


class SurfaceProjectionKind(StrEnum):
    FORWARD_CHANNELS = "FORWARD_CHANNELS"
    SECONDARY_DEVICES = "SECONDARY_DEVICES"
    COMMUNICATION_PROTOCOLS = "COMMUNICATION_PROTOCOLS"
    GLOBAL_PARAMETERS = "GLOBAL_PARAMETERS"
    UNPARSED_TABLES = "UNPARSED_TABLES"


@dataclass(frozen=True, slots=True)
class SurfaceView:
    view_id: str
    label: str | None = None
    before_role: ComparisonRole | str = ComparisonRole.BEFORE
    current_role: ComparisonRole | str = ComparisonRole.CURRENT
    display_before_role: str | None = None
    display_current_role: str | None = None
    table_count: int = 0
    changed_table_count: int = 0
    degraded_table_count: int = 0
    risk_level: RiskLevel | str | None = None
    diagnostics_summary: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.view_id, str) or not self.view_id:
            raise ValueError("view_id must be a non-empty string")
        object.__setattr__(self, "before_role", ComparisonRole(self.before_role))
        object.__setattr__(self, "current_role", ComparisonRole(self.current_role))
        if self.display_before_role is not None:
            if not isinstance(self.display_before_role, str) or not self.display_before_role:
                raise ValueError("display_before_role must be a non-empty string or None")
        if self.display_current_role is not None:
            if not isinstance(self.display_current_role, str) or not self.display_current_role:
                raise ValueError("display_current_role must be a non-empty string or None")
        for field_name in ("table_count", "changed_table_count", "degraded_table_count"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.risk_level is not None:
            object.__setattr__(self, "risk_level", RiskLevel(self.risk_level))
        if self.diagnostics_summary is not None:
            object.__setattr__(self, "diagnostics_summary", _mapping_payload(self.diagnostics_summary))

    def payload_for_digest(self) -> dict[str, object]:
        payload = {
            "before_role": self.before_role.value,
            "current_role": self.current_role.value,
            "table_count": self.table_count,
            "changed_table_count": self.changed_table_count,
            "degraded_table_count": self.degraded_table_count,
        }
        if self.risk_level is not None:
            payload["risk_level"] = self.risk_level.value
        return payload

    def to_payload(self) -> dict[str, object]:
        payload = {
            "view_id": self.view_id,
            "before_role": self.before_role.value,
            "current_role": self.current_role.value,
            "table_count": self.table_count,
            "changed_table_count": self.changed_table_count,
            "degraded_table_count": self.degraded_table_count,
        }
        if self.label is not None:
            payload["label"] = self.label
        if self.display_before_role is not None:
            payload["display_before_role"] = self.display_before_role
        if self.display_current_role is not None:
            payload["display_current_role"] = self.display_current_role
        if self.risk_level is not None:
            payload["risk_level"] = self.risk_level.value
        if self.diagnostics_summary is not None:
            payload["diagnostics_summary"] = _mapping_payload(self.diagnostics_summary)
        return payload


@dataclass(frozen=True, slots=True)
class SurfaceSummary:
    table_count: int
    visible_table_count: int | None = None
    hidden_table_count: int = 0
    hidden_table_counts_by_reason: Mapping[str, object] = field(default_factory=dict)
    changed_table_count: int = 0
    degraded_table_count: int = 0
    risk_level: RiskLevel | str | None = None
    diagnostics_count: int = 0

    def __post_init__(self) -> None:
        if self.visible_table_count is None:
            object.__setattr__(self, "visible_table_count", self.table_count - self.hidden_table_count)
        for field_name in (
            "table_count",
            "visible_table_count",
            "hidden_table_count",
            "changed_table_count",
            "degraded_table_count",
            "diagnostics_count",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.visible_table_count + self.hidden_table_count != self.table_count:
            raise ValueError("visible_table_count + hidden_table_count must equal table_count")
        object.__setattr__(self, "hidden_table_counts_by_reason", _mapping_payload(self.hidden_table_counts_by_reason))
        hidden_reason_total = 0
        for reason, count in self.hidden_table_counts_by_reason.items():
            SurfaceHiddenTableReason(reason)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError("hidden table reason counts must be non-negative integers")
            hidden_reason_total += count
        if hidden_reason_total != self.hidden_table_count:
            raise ValueError("hidden table reason counts must sum to hidden_table_count")
        if self.risk_level is not None:
            object.__setattr__(self, "risk_level", RiskLevel(self.risk_level))

    def payload_for_digest(self) -> dict[str, object]:
        payload = {
            "table_count": self.table_count,
            "visible_table_count": self.visible_table_count,
            "changed_table_count": self.changed_table_count,
            "degraded_table_count": self.degraded_table_count,
            "diagnostics_count": self.diagnostics_count,
        }
        if self.risk_level is not None:
            payload["risk_level"] = self.risk_level.value
        return payload

    def to_payload(self) -> dict[str, object]:
        return self.payload_for_digest()


@dataclass(frozen=True, slots=True)
class SurfaceTableRefs:
    before_table_ref: str | None = None
    current_table_ref: str | None = None
    browse_table_ref: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("before_table_ref", "current_table_ref", "browse_table_ref"):
            value = getattr(self, field_name)
            if value is not None:
                ensure_logical_relative_ref(value, field_name)

    def payload_for_digest(self) -> dict[str, object]:
        return {}

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.before_table_ref is not None:
            payload["before_table_ref"] = self.before_table_ref
        if self.current_table_ref is not None:
            payload["current_table_ref"] = self.current_table_ref
        if self.browse_table_ref is not None:
            payload["browse_table_ref"] = self.browse_table_ref
        return payload


@dataclass(frozen=True, slots=True)
class SurfaceRecordsRefs:
    records_ref: str | None = None
    records_manifest_ref: str | None = None
    records_format: SurfaceRecordsFormat | str = SurfaceRecordsFormat.PARQUET
    records_manifest_digest: DigestRef | str | None = None
    records_content_digest: DigestRef | str | None = None

    def __post_init__(self) -> None:
        if self.records_ref is not None:
            ensure_logical_relative_ref(self.records_ref, "records_ref")
        if self.records_manifest_ref is not None:
            ensure_logical_relative_ref(self.records_manifest_ref, "records_manifest_ref")
        object.__setattr__(self, "records_format", SurfaceRecordsFormat(self.records_format))
        if self.records_manifest_digest is not None:
            object.__setattr__(self, "records_manifest_digest", _optional_digest(self.records_manifest_digest))
        if self.records_content_digest is not None:
            object.__setattr__(self, "records_content_digest", _optional_digest(self.records_content_digest))

    def payload_for_digest(self) -> dict[str, object]:
        payload: dict[str, object] = {"records_format": self.records_format.value}
        if self.records_manifest_digest is not None:
            payload["records_manifest_digest"] = self.records_manifest_digest.to_payload()
        if self.records_content_digest is not None:
            payload["records_content_digest"] = self.records_content_digest.to_payload()
        return payload

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        if self.records_ref is not None:
            payload["records_ref"] = self.records_ref
        if self.records_manifest_ref is not None:
            payload["records_manifest_ref"] = self.records_manifest_ref
        return payload


@dataclass(frozen=True, slots=True)
class SurfaceRiskRefs:
    report_ref: str | None = None
    annotation_ref: str | None = None
    annotation_manifest_ref: str | None = None
    report_digest: DigestRef | str | None = None
    annotation_manifest_digest: DigestRef | str | None = None
    annotation_content_digest: DigestRef | str | None = None

    def __post_init__(self) -> None:
        for field_name in ("report_ref", "annotation_ref", "annotation_manifest_ref"):
            value = getattr(self, field_name)
            if value is not None:
                ensure_logical_relative_ref(value, field_name)
        if self.report_digest is not None:
            object.__setattr__(self, "report_digest", _optional_digest(self.report_digest))
        if self.annotation_manifest_digest is not None:
            object.__setattr__(self, "annotation_manifest_digest", _optional_digest(self.annotation_manifest_digest))
        if self.annotation_content_digest is not None:
            object.__setattr__(self, "annotation_content_digest", _optional_digest(self.annotation_content_digest))

    def payload_for_digest(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.report_digest is not None:
            payload["report_digest"] = self.report_digest.to_payload()
        if self.annotation_manifest_digest is not None:
            payload["annotation_manifest_digest"] = self.annotation_manifest_digest.to_payload()
        if self.annotation_content_digest is not None:
            payload["annotation_content_digest"] = self.annotation_content_digest.to_payload()
        return payload

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        if self.report_ref is not None:
            payload["report_ref"] = self.report_ref
        if self.annotation_ref is not None:
            payload["annotation_ref"] = self.annotation_ref
        if self.annotation_manifest_ref is not None:
            payload["annotation_manifest_ref"] = self.annotation_manifest_ref
        return payload


@dataclass(frozen=True, slots=True)
class SurfaceDiagnosticsRefs:
    diagnostics_ref: str | None = None
    diagnostics_summary: Mapping[str, object] | None = None
    diagnostics_manifest_digest: DigestRef | str | None = None

    def __post_init__(self) -> None:
        if self.diagnostics_ref is not None:
            ensure_logical_relative_ref(self.diagnostics_ref, "diagnostics_ref")
        if self.diagnostics_summary is not None:
            object.__setattr__(self, "diagnostics_summary", _mapping_payload(self.diagnostics_summary))
        if self.diagnostics_manifest_digest is not None:
            object.__setattr__(self, "diagnostics_manifest_digest", _optional_digest(self.diagnostics_manifest_digest))

    def payload_for_digest(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.diagnostics_summary is not None:
            payload["diagnostics_summary"] = _mapping_payload(self.diagnostics_summary)
        if self.diagnostics_manifest_digest is not None:
            payload["diagnostics_manifest_digest"] = self.diagnostics_manifest_digest.to_payload()
        return payload

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        if self.diagnostics_ref is not None:
            payload["diagnostics_ref"] = self.diagnostics_ref
        return payload


@dataclass(frozen=True, slots=True)
class SurfaceDisplay:
    strategy: SurfaceDisplayStrategy | str = SurfaceDisplayStrategy.SUMMARY_ONLY
    table_processing_mode: SurfaceTableProcessingMode | str = SurfaceTableProcessingMode.STANDARD
    replay_guarantee: SurfaceReplayGuarantee | str = SurfaceReplayGuarantee.SUMMARY_ONLY

    def __post_init__(self) -> None:
        object.__setattr__(self, "strategy", SurfaceDisplayStrategy(self.strategy))
        object.__setattr__(self, "table_processing_mode", SurfaceTableProcessingMode(self.table_processing_mode))
        object.__setattr__(self, "replay_guarantee", SurfaceReplayGuarantee(self.replay_guarantee))

    def payload_for_digest(self) -> dict[str, object]:
        return {
            "strategy": self.strategy.value,
            "table_processing_mode": self.table_processing_mode.value,
            "replay_guarantee": self.replay_guarantee.value,
        }

    def to_payload(self) -> dict[str, object]:
        return self.payload_for_digest()


@dataclass(frozen=True, slots=True)
class SurfaceCompare:
    artifact_scope: str = "TABLE"
    compare_key_columns: tuple[str, ...] = field(default_factory=tuple)
    ignored_columns: tuple[str, ...] = field(default_factory=tuple)
    effective_columns: tuple[str, ...] = field(default_factory=tuple)
    projection_schema_digest: DigestRef | str | None = None
    projection_logical_digest: DigestRef | str | None = None
    provider: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_scope, str) or not self.artifact_scope:
            raise ValueError("artifact_scope must be a non-empty string")
        object.__setattr__(self, "compare_key_columns", _normalize_str_tuple(self.compare_key_columns))
        object.__setattr__(self, "ignored_columns", _normalize_str_tuple(self.ignored_columns))
        object.__setattr__(self, "effective_columns", _normalize_str_tuple(self.effective_columns))
        if self.projection_schema_digest is not None:
            object.__setattr__(self, "projection_schema_digest", _optional_digest(self.projection_schema_digest))
        if self.projection_logical_digest is not None:
            object.__setattr__(self, "projection_logical_digest", _optional_digest(self.projection_logical_digest))
        if self.provider is not None and not isinstance(self.provider, str):
            raise TypeError("provider must be a string or None")

    def payload_for_digest(self) -> dict[str, object]:
        payload = {
            "artifact_scope": self.artifact_scope,
            "compare_key_columns": list(self.compare_key_columns),
            "ignored_columns": list(self.ignored_columns),
            "effective_columns": list(self.effective_columns),
        }
        if self.projection_schema_digest is not None:
            payload["projection_schema_digest"] = self.projection_schema_digest.to_payload()
        if self.projection_logical_digest is not None:
            payload["projection_logical_digest"] = self.projection_logical_digest.to_payload()
        if self.provider is not None:
            payload["provider"] = self.provider
        return payload

    def to_payload(self) -> dict[str, object]:
        return self.payload_for_digest()


@dataclass(frozen=True, slots=True)
class SurfaceOrderedExtension:
    ordered_contract_version: str = SURFACE_ORDERED_EXTENSION_CONTRACT_VERSION
    ordered_summary: Mapping[str, object] | None = None
    ordered_records_ref: str | None = None
    ordered_records_manifest_ref: str | None = None
    stable_key_field: str | None = None
    position_field: str | None = None
    ordered_display_mode: str | None = None
    table_processing_mode: str | None = None
    ordered_preprocess_applied: str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.ordered_contract_version, str) or not self.ordered_contract_version:
            raise ValueError("ordered_contract_version must be a non-empty string")
        if self.ordered_summary is not None:
            object.__setattr__(self, "ordered_summary", _mapping_payload(self.ordered_summary))
        for field_name in ("ordered_records_ref", "ordered_records_manifest_ref"):
            value = getattr(self, field_name)
            if value is not None:
                ensure_logical_relative_ref(value, field_name)
        for field_name in ("stable_key_field", "position_field"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        if self.ordered_display_mode is not None and not isinstance(self.ordered_display_mode, str):
            raise TypeError("ordered_display_mode must be a string or None")
        if self.table_processing_mode is not None and not isinstance(self.table_processing_mode, str):
            raise TypeError("table_processing_mode must be a string or None")
        if self.ordered_preprocess_applied is not None and (
            not isinstance(self.ordered_preprocess_applied, str)
            or not self.ordered_preprocess_applied.strip()
        ):
            raise TypeError("ordered_preprocess_applied must be a non-empty string or None")
        if not isinstance(self.diagnostics, tuple):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))

    def payload_for_digest(self) -> dict[str, object]:
        payload = {
            "ordered_contract_version": self.ordered_contract_version,
        }
        if self.ordered_summary is not None:
            payload["ordered_summary"] = _mapping_payload(self.ordered_summary)
        if self.stable_key_field is not None:
            payload["stable_key_field"] = self.stable_key_field
        if self.position_field is not None:
            payload["position_field"] = self.position_field
        if self.ordered_display_mode is not None:
            payload["ordered_display_mode"] = self.ordered_display_mode
        if self.table_processing_mode is not None:
            payload["table_processing_mode"] = self.table_processing_mode
        if self.ordered_preprocess_applied is not None:
            payload["ordered_preprocess_applied"] = self.ordered_preprocess_applied
        if self.diagnostics:
            payload["diagnostics"] = [diagnostic.to_payload() for diagnostic in self.diagnostics]
        return payload

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        if self.ordered_records_ref is not None:
            payload["ordered_records_ref"] = self.ordered_records_ref
        if self.ordered_records_manifest_ref is not None:
            payload["ordered_records_manifest_ref"] = self.ordered_records_manifest_ref
        return payload


@dataclass(frozen=True, slots=True)
class SurfaceProjectionRef:
    projection_id: str
    projection_kind: SurfaceProjectionKind | str
    projection_ref: str
    projection_digest: DigestRef | str
    projection_summary: Mapping[str, object] = field(default_factory=dict)
    risk_summary_ref: str | None = None
    diagnostics_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.projection_id, str) or not self.projection_id:
            raise ValueError("projection_id must be a non-empty string")
        object.__setattr__(self, "projection_kind", SurfaceProjectionKind(self.projection_kind))
        ensure_logical_relative_ref(self.projection_ref, "projection_ref")
        object.__setattr__(self, "projection_digest", _optional_digest(self.projection_digest))
        object.__setattr__(self, "projection_summary", _mapping_payload(self.projection_summary))
        for field_name in ("risk_summary_ref", "diagnostics_ref"):
            value = getattr(self, field_name)
            if value is not None:
                ensure_logical_relative_ref(value, field_name)

    def payload_for_digest(self) -> dict[str, object]:
        return {
            "projection_id": self.projection_id,
            "projection_kind": self.projection_kind.value,
            "projection_digest": self.projection_digest.to_payload(),
            "projection_summary": _mapping_payload(self.projection_summary),
        }

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        payload["projection_ref"] = self.projection_ref
        if self.risk_summary_ref is not None:
            payload["risk_summary_ref"] = self.risk_summary_ref
        if self.diagnostics_ref is not None:
            payload["diagnostics_ref"] = self.diagnostics_ref
        return payload


@dataclass(frozen=True, slots=True)
class SurfaceTable:
    table_name: str
    table_id: str | None = None
    display_name: str | None = None
    table_status: ComparisonTableStatus | str = ComparisonTableStatus.UNCHANGED
    change_kind: SurfaceChangeKind | str = SurfaceChangeKind.UNCHANGED
    row_count: int | None = None
    row_change_stats: Mapping[str, object] | None = None
    schema_summary: Mapping[str, object] | None = None
    columns: tuple[str, ...] = field(default_factory=tuple)
    table_refs: SurfaceTableRefs = field(default_factory=SurfaceTableRefs)
    records_refs: SurfaceRecordsRefs = field(default_factory=SurfaceRecordsRefs)
    risk_refs: SurfaceRiskRefs = field(default_factory=SurfaceRiskRefs)
    display: SurfaceDisplay = field(default_factory=SurfaceDisplay)
    compare: SurfaceCompare = field(default_factory=SurfaceCompare)
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    ordered_extension: SurfaceOrderedExtension | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name:
            raise ValueError("table_name must be a non-empty string")
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        if self.table_id is None:
            object.__setattr__(self, "table_id", self.table_name)
        elif not isinstance(self.table_id, str) or not self.table_id:
            raise ValueError("table_id must be a non-empty string or None")
        else:
            object.__setattr__(self, "table_id", canonical_identifier(self.table_id))
        object.__setattr__(self, "table_status", ComparisonTableStatus(self.table_status))
        object.__setattr__(self, "change_kind", SurfaceChangeKind(self.change_kind))
        if self.row_count is not None and (
            not isinstance(self.row_count, int) or isinstance(self.row_count, bool) or self.row_count < 0
        ):
            raise ValueError("row_count must be a non-negative integer or None")
        if self.row_change_stats is not None:
            object.__setattr__(self, "row_change_stats", _mapping_payload(self.row_change_stats))
        if self.schema_summary is not None:
            object.__setattr__(self, "schema_summary", _mapping_payload(self.schema_summary))
        object.__setattr__(self, "columns", _normalize_str_tuple(self.columns))
        if not isinstance(self.table_refs, SurfaceTableRefs):
            raise TypeError("table_refs must be a SurfaceTableRefs")
        if not isinstance(self.records_refs, SurfaceRecordsRefs):
            raise TypeError("records_refs must be a SurfaceRecordsRefs")
        if not isinstance(self.risk_refs, SurfaceRiskRefs):
            raise TypeError("risk_refs must be a SurfaceRiskRefs")
        if not isinstance(self.display, SurfaceDisplay):
            raise TypeError("display must be a SurfaceDisplay")
        if not isinstance(self.compare, SurfaceCompare):
            raise TypeError("compare must be a SurfaceCompare")
        if not isinstance(self.diagnostics, tuple):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))
        if self.ordered_extension is not None and not isinstance(self.ordered_extension, SurfaceOrderedExtension):
            raise TypeError("ordered_extension must be a SurfaceOrderedExtension or None")

    def payload_for_digest(self) -> dict[str, object]:
        payload = {
            "table_name": self.table_name,
            "table_id": self.table_id,
            "table_status": self.table_status.value,
            "change_kind": self.change_kind.value,
            "row_count": self.row_count,
            "columns": list(self.columns),
            "display": self.display.payload_for_digest(),
            "compare": self.compare.payload_for_digest(),
        }
        if self.row_change_stats is not None:
            payload["row_change_stats"] = _mapping_payload(self.row_change_stats)
        if self.schema_summary is not None:
            payload["schema_summary"] = _mapping_payload(self.schema_summary)
        if self.diagnostics:
            payload["diagnostics"] = [diagnostic.to_payload() for diagnostic in self.diagnostics]
        if self.ordered_extension is not None:
            payload["ordered_extension"] = self.ordered_extension.payload_for_digest()
        return payload

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        if self.display_name is not None:
            payload["display_name"] = self.display_name
        payload["table_refs"] = self.table_refs.to_payload()
        payload["records_refs"] = self.records_refs.to_payload()
        payload["risk_refs"] = self.risk_refs.to_payload()
        if self.ordered_extension is not None:
            payload["ordered_extension"] = self.ordered_extension.to_payload()
        return payload


@dataclass(frozen=True, slots=True)
class SurfaceHiddenTable:
    table_name: str
    reason: SurfaceHiddenTableReason | str
    table_id: str | None = None
    display_name: str | None = None
    table_status: ComparisonTableStatus | str = ComparisonTableStatus.UNCHANGED
    row_count: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name:
            raise ValueError("table_name must be a non-empty string")
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        if self.table_id is None:
            object.__setattr__(self, "table_id", self.table_name)
        elif not isinstance(self.table_id, str) or not self.table_id:
            raise ValueError("table_id must be a non-empty string or None")
        else:
            object.__setattr__(self, "table_id", canonical_identifier(self.table_id))
        object.__setattr__(self, "reason", SurfaceHiddenTableReason(self.reason))
        object.__setattr__(self, "table_status", ComparisonTableStatus(self.table_status))
        if self.row_count is not None and (
            not isinstance(self.row_count, int) or isinstance(self.row_count, bool) or self.row_count < 0
        ):
            raise ValueError("row_count must be a non-negative integer or None")
        if self.display_name is not None and not isinstance(self.display_name, str):
            raise TypeError("display_name must be a string or None")

    def payload_for_digest(self) -> dict[str, object]:
        return {
            "table_name": self.table_name,
            "table_id": self.table_id,
            "reason": self.reason.value,
            "table_status": self.table_status.value,
            "row_count": self.row_count,
        }

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        if self.display_name is not None:
            payload["display_name"] = self.display_name
        return payload


@dataclass(frozen=True, slots=True)
class SurfaceRefs:
    surface_ref: str
    records_closure_ref: str | None = None
    records_closure_manifest_digest: DigestRef | str | None = None
    risk_report_ref: str | None = None
    risk_report_digest: DigestRef | str | None = None
    risk_annotation_closure_ref: str | None = None
    risk_annotation_closure_manifest_digest: DigestRef | str | None = None
    diagnostics_refs: tuple[str, ...] = field(default_factory=tuple)
    diagnostics_manifest_digests: tuple[DigestRef | str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        ensure_logical_relative_ref(self.surface_ref, "surface_ref")
        for field_name in ("records_closure_ref", "risk_report_ref", "risk_annotation_closure_ref"):
            value = getattr(self, field_name)
            if value is not None:
                ensure_logical_relative_ref(value, field_name)
        object.__setattr__(self, "diagnostics_refs", _normalize_str_tuple(self.diagnostics_refs))
        for ref in self.diagnostics_refs:
            ensure_logical_relative_ref(ref, "diagnostics_ref")
        object.__setattr__(self, "diagnostics_manifest_digests", tuple(_optional_digest(value) for value in self.diagnostics_manifest_digests))
        if self.records_closure_manifest_digest is not None:
            object.__setattr__(self, "records_closure_manifest_digest", _optional_digest(self.records_closure_manifest_digest))
        if self.risk_report_digest is not None:
            object.__setattr__(self, "risk_report_digest", _optional_digest(self.risk_report_digest))
        if self.risk_annotation_closure_manifest_digest is not None:
            object.__setattr__(self, "risk_annotation_closure_manifest_digest", _optional_digest(self.risk_annotation_closure_manifest_digest))

    def payload_for_digest(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.records_closure_manifest_digest is not None:
            payload["records_closure_manifest_digest"] = self.records_closure_manifest_digest.to_payload()
        if self.risk_report_digest is not None:
            payload["risk_report_digest"] = self.risk_report_digest.to_payload()
        if self.risk_annotation_closure_manifest_digest is not None:
            payload["risk_annotation_closure_manifest_digest"] = self.risk_annotation_closure_manifest_digest.to_payload()
        if self.diagnostics_manifest_digests:
            payload["diagnostics_manifest_digests"] = [digest.to_payload() for digest in self.diagnostics_manifest_digests]
        return payload

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        payload["surface_ref"] = self.surface_ref
        if self.records_closure_ref is not None:
            payload["records_closure_ref"] = self.records_closure_ref
        if self.risk_report_ref is not None:
            payload["risk_report_ref"] = self.risk_report_ref
        if self.risk_annotation_closure_ref is not None:
            payload["risk_annotation_closure_ref"] = self.risk_annotation_closure_ref
        if self.diagnostics_refs:
            payload["diagnostics_refs"] = list(self.diagnostics_refs)
        return payload


@dataclass(frozen=True, slots=True)
class ComparisonSurface:
    surface_contract_version: str = SURFACE_CONTRACT_VERSION
    surface_digest: DigestRef | str | None = None
    surface_id: str = ""
    direction: str = ""
    comparison_digest: DigestRef | str = ""
    risk_evaluation_digest: DigestRef | str | None = None
    surface_profile: SurfaceProfile | str = SurfaceProfile.STANDARD_TABLE_BROWSER
    surface_options: Mapping[str, object] = field(default_factory=dict)
    view: SurfaceView = field(default_factory=lambda: SurfaceView(view_id="default"))
    tables: tuple[SurfaceTable, ...] = field(default_factory=tuple)
    hidden_tables: tuple[SurfaceHiddenTable, ...] = field(default_factory=tuple)
    projections: tuple[SurfaceProjectionRef, ...] = field(default_factory=tuple)
    summary: SurfaceSummary = field(default_factory=lambda: SurfaceSummary(table_count=0))
    refs: SurfaceRefs = field(default_factory=lambda: SurfaceRefs(surface_ref="comparison-surface.json"))
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    reserved_extensions: tuple[Mapping[str, object], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.surface_contract_version, str) or not self.surface_contract_version:
            raise ValueError("surface_contract_version must be a non-empty string")
        if not isinstance(self.surface_id, str) or not self.surface_id:
            raise ValueError("surface_id must be a non-empty string")
        if not isinstance(self.direction, str) or not self.direction:
            raise ValueError("direction must be a non-empty string")
        object.__setattr__(self, "comparison_digest", _optional_digest(self.comparison_digest))
        if self.comparison_digest is None:
            raise ValueError("comparison_digest must be set")
        if self.risk_evaluation_digest is not None:
            object.__setattr__(self, "risk_evaluation_digest", _optional_digest(self.risk_evaluation_digest))
        object.__setattr__(self, "surface_profile", SurfaceProfile(self.surface_profile))
        if self.surface_profile is not SurfaceProfile.STANDARD_TABLE_BROWSER:
            raise ValueError("only STANDARD_TABLE_BROWSER is supported in the first surface version")
        if self.surface_options is None:
            object.__setattr__(self, "surface_options", {})
        else:
            if not isinstance(self.surface_options, Mapping):
                raise TypeError("surface_options must be a mapping")
            object.__setattr__(self, "surface_options", _mapping_payload(self.surface_options))
        if not isinstance(self.view, SurfaceView):
            raise TypeError("view must be a SurfaceView")
        if not isinstance(self.tables, tuple):
            object.__setattr__(self, "tables", tuple(self.tables))
        normalized_tables: list[SurfaceTable] = []
        for table in self.tables:
            if not isinstance(table, SurfaceTable):
                raise TypeError("tables must contain SurfaceTable values")
            normalized_tables.append(table)
        object.__setattr__(self, "tables", tuple(normalized_tables))
        if not isinstance(self.hidden_tables, tuple):
            object.__setattr__(self, "hidden_tables", tuple(self.hidden_tables))
        normalized_hidden_tables: list[SurfaceHiddenTable] = []
        for table in self.hidden_tables:
            if not isinstance(table, SurfaceHiddenTable):
                raise TypeError("hidden_tables must contain SurfaceHiddenTable values")
            normalized_hidden_tables.append(table)
        object.__setattr__(self, "hidden_tables", tuple(normalized_hidden_tables))
        if not isinstance(self.projections, tuple):
            object.__setattr__(self, "projections", tuple(self.projections))
        normalized_projections: list[SurfaceProjectionRef] = []
        for projection in self.projections:
            if not isinstance(projection, SurfaceProjectionRef):
                raise TypeError("projections must contain SurfaceProjectionRef values")
            normalized_projections.append(projection)
        object.__setattr__(self, "projections", tuple(normalized_projections))
        if not isinstance(self.summary, SurfaceSummary):
            raise TypeError("summary must be a SurfaceSummary")
        if not isinstance(self.refs, SurfaceRefs):
            raise TypeError("refs must be a SurfaceRefs")
        if not isinstance(self.diagnostics, tuple):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))
        if not isinstance(self.reserved_extensions, tuple):
            object.__setattr__(self, "reserved_extensions", tuple(self.reserved_extensions))
        normalized_extensions: list[Mapping[str, object]] = []
        for extension in self.reserved_extensions:
            if not isinstance(extension, Mapping):
                raise TypeError("reserved_extensions must contain mappings")
            normalized_extensions.append(_mapping_payload(extension))
        object.__setattr__(self, "reserved_extensions", tuple(normalized_extensions))
        if self.surface_digest is None:
            object.__setattr__(self, "surface_digest", build_surface_digest(self))
        else:
            object.__setattr__(self, "surface_digest", _optional_digest(self.surface_digest))

    def payload_for_digest(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "surface_contract_version": self.surface_contract_version,
            "comparison_digest": self.comparison_digest.to_payload(),
            "surface_profile": self.surface_profile.value,
            "surface_options": _mapping_payload(self.surface_options),
            "view": self.view.payload_for_digest(),
            "summary": self.summary.payload_for_digest(),
            "tables": [table.payload_for_digest() for table in self.tables],
            "projections": [projection.payload_for_digest() for projection in self.projections],
            "refs": self.refs.payload_for_digest(),
        }
        if self.risk_evaluation_digest is not None:
            payload["risk_evaluation_digest"] = self.risk_evaluation_digest.to_payload()
        if self.diagnostics:
            payload["diagnostics"] = [diagnostic.to_payload() for diagnostic in self.diagnostics]
        if self.reserved_extensions:
            payload["reserved_extensions"] = [dict(extension) for extension in self.reserved_extensions]
        return payload

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        payload.pop("surface_profile", None)
        payload.pop("surface_options", None)
        payload["surface_digest"] = self.surface_digest.to_payload() if self.surface_digest is not None else None
        payload["surface_id"] = self.surface_id
        payload["direction"] = self.direction
        payload["view"] = self.view.to_payload()
        payload["summary"] = self.summary.to_payload()
        payload["refs"] = self.refs.to_payload()
        payload["tables"] = [table.to_payload() for table in self.tables]
        payload["projections"] = [projection.to_payload() for projection in self.projections]
        if self.diagnostics:
            payload["diagnostics"] = [diagnostic.to_payload() for diagnostic in self.diagnostics]
        if self.reserved_extensions:
            payload["reserved_extensions"] = [dict(extension) for extension in self.reserved_extensions]
        return payload


@dataclass(frozen=True, slots=True)
class ComparisonSurfaceAssemblyInput:
    comparison_facts: ComparisonFacts
    records_closure: ComparisonRecordsClosure | None = None
    risk_report: RiskReport | None = None
    business_projection_result: BusinessProjectionResult | None = None
    risk_annotation_closure: tuple[ArtifactRef, ...] = field(default_factory=tuple)
    diagnostics_refs: tuple[str, ...] = field(default_factory=tuple)
    surface_contract_version: str = SURFACE_CONTRACT_VERSION
    surface_profile: SurfaceProfile | str = SurfaceProfile.STANDARD_TABLE_BROWSER
    surface_options: Mapping[str, object] = field(default_factory=dict)
    ref_scope: SurfaceRefScope | str = SurfaceRefScope.OPERATION_RELATIVE

    def __post_init__(self) -> None:
        if not isinstance(self.comparison_facts, ComparisonFacts):
            raise TypeError("comparison_facts must be a ComparisonFacts")
        if self.records_closure is None and self.comparison_facts.records_ref is not None:
            object.__setattr__(self, "records_closure", self.comparison_facts.records_ref)
        if self.records_closure is not None and not isinstance(self.records_closure, ComparisonRecordsClosure):
            raise TypeError("records_closure must be a ComparisonRecordsClosure or None")
        if self.risk_report is not None and not isinstance(self.risk_report, RiskReport):
            raise TypeError("risk_report must be a RiskReport or None")
        if self.business_projection_result is not None and not isinstance(self.business_projection_result, BusinessProjectionResult):
            raise TypeError("business_projection_result must be a BusinessProjectionResult or None")
        if not isinstance(self.surface_contract_version, str) or not self.surface_contract_version:
            raise ValueError("surface_contract_version must be a non-empty string")
        object.__setattr__(self, "surface_profile", SurfaceProfile(self.surface_profile))
        object.__setattr__(self, "ref_scope", SurfaceRefScope(self.ref_scope))
        if self.surface_profile is not SurfaceProfile.STANDARD_TABLE_BROWSER:
            raise ValueError("only STANDARD_TABLE_BROWSER is supported in the first surface version")
        object.__setattr__(self, "risk_annotation_closure", tuple(self.risk_annotation_closure))
        for ref in self.risk_annotation_closure:
            if not isinstance(ref, ArtifactRef):
                raise TypeError("risk_annotation_closure must contain ArtifactRef values")
        object.__setattr__(self, "diagnostics_refs", _normalize_str_tuple(self.diagnostics_refs))
        ensure_logical_relative_refs(self.diagnostics_refs, "diagnostics_ref")
        if self.surface_options is None:
            object.__setattr__(self, "surface_options", {})
        else:
            if not isinstance(self.surface_options, Mapping):
                raise TypeError("surface_options must be a mapping")
            normalized = _mapping_payload(self.surface_options)
            ensure_surface_options(normalized)
            object.__setattr__(self, "surface_options", normalized)


@dataclass(frozen=True, slots=True)
class ComparisonSurfaceAssemblyResult:
    comparison_surface: ComparisonSurface
    surface_digest: DigestRef
    referenced_artifacts: tuple[ArtifactRef, ...] = field(default_factory=tuple)
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.comparison_surface, ComparisonSurface):
            raise TypeError("comparison_surface must be a ComparisonSurface")
        if not isinstance(self.surface_digest, DigestRef):
            object.__setattr__(self, "surface_digest", _optional_digest(self.surface_digest))
        if not isinstance(self.referenced_artifacts, tuple):
            object.__setattr__(self, "referenced_artifacts", tuple(self.referenced_artifacts))
        normalized_artifacts: list[ArtifactRef] = []
        for artifact_ref in self.referenced_artifacts:
            if not isinstance(artifact_ref, ArtifactRef):
                raise TypeError("referenced_artifacts must contain ArtifactRef values")
            normalized_artifacts.append(artifact_ref)
        object.__setattr__(self, "referenced_artifacts", tuple(normalized_artifacts))
        if not isinstance(self.diagnostics, tuple):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))
