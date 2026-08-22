"""Flow-neutral public contracts for deterministic comparison surface assembly."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from gateway_shared_kernel import DigestRef, canonicalize_identifier

from gateway_backend.artifacts import ArtifactRef, artifact_ref_to_dict, assert_no_host_path_identity
from gateway_backend.capabilities.comparison.contracts import (
    ArtifactScope,
    ComparisonFacts,
    ComparisonMode,
    ComparisonRecordsClosure,
    ComparisonSchemaChanges,
    ComparisonTableStatus,
    IdentityStatus,
)
from gateway_backend.capabilities.risk_evaluation.contracts import (
    RiskAnnotationClosure,
    RiskLevel,
    RiskReasonCode,
    RiskReport,
)


SURFACE_CONTRACT_VERSION = "backend-vnext/comparison-surface/v2"
SURFACE_JSON_MEDIA_TYPE = "application/json"
MAX_SURFACE_JSON_BYTES = 16 * 1024 * 1024
MAX_SURFACE_WALL_TIME_SECONDS = 120.0


class SurfaceProfile(StrEnum):
    STANDARD_TABLE_BROWSER = "STANDARD_TABLE_BROWSER"


class SurfaceRefScope(StrEnum):
    OPERATION_RELATIVE = "OPERATION_RELATIVE"
    BUNDLE_RELATIVE = "BUNDLE_RELATIVE"


class SurfaceChangeKind(StrEnum):
    UNCHANGED = "UNCHANGED"
    BUSINESS_EQUIVALENT = "BUSINESS_EQUIVALENT"
    ADDED = "ADDED"
    DELETED = "DELETED"
    UPDATED = "UPDATED"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    REPLACED = "REPLACED"


class SurfaceDisplayStrategy(StrEnum):
    SUMMARY_ONLY = "SUMMARY_ONLY"
    TABLE_BROWSE = "TABLE_BROWSE"
    RECORDS_ONLY = "RECORDS_ONLY"
    CURRENT_WITH_RECORDS = "CURRENT_WITH_RECORDS"
    DEGRADED_NOTICE = "DEGRADED_NOTICE"
    REPLACEMENT_SIDE_BY_SIDE = "REPLACEMENT_SIDE_BY_SIDE"


class SurfaceTableProcessingMode(StrEnum):
    STANDARD = "STANDARD"
    SCHEMA_ONLY = "SCHEMA_ONLY"
    DEGRADED = "DEGRADED"
    DATASET_REPLACEMENT = "DATASET_REPLACEMENT"


class SurfaceReplayGuarantee(StrEnum):
    EXACT = "EXACT"
    SUMMARY_ONLY = "SUMMARY_ONLY"
    UNSUPPORTED = "UNSUPPORTED"


class SurfaceRecordsFormat(StrEnum):
    PARQUET = "PARQUET"
    INLINE_SUMMARY = "INLINE_SUMMARY"


class SurfaceAssemblyStatus(StrEnum):
    READY = "READY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def _require_text(value: object, label: str) -> str:
    if type(value) is not str or value == "":
        raise ValueError(f"{label} must be a non-empty string")
    if "\x00" in value:
        raise ValueError(f"{label} must not contain NUL")
    return value


def _require_identifier(value: object, label: str) -> str:
    text = _require_text(value, label)
    try:
        return canonicalize_identifier(text)
    except Exception as exc:
        raise ValueError(f"{label} must be a canonical identifier") from exc


def _require_non_negative(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _require_digest(value: object, label: str) -> DigestRef:
    if type(value) is not DigestRef:
        raise ValueError(f"{label} must be DigestRef")
    return value


def _require_ref(value: object, label: str) -> ArtifactRef:
    if type(value) is not ArtifactRef:
        raise ValueError(f"{label} must be ArtifactRef")
    assert_no_host_path_identity(value.artifact_id, label=label)
    return value


def _require_optional_ref(value: object, label: str) -> ArtifactRef | None:
    if value is None:
        return None
    return _require_ref(value, label)


def _require_string_tuple(value: object, label: str) -> tuple[str, ...]:
    if type(value) is not tuple or any(type(item) is not str or item == "" for item in value):
        raise ValueError(f"{label} must contain non-empty strings")
    return value


def _require_sorted_unique_strings(value: object, label: str) -> tuple[str, ...]:
    result = _require_string_tuple(value, label)
    if result != tuple(sorted(result)) or len(set(result)) != len(result):
        raise ValueError(f"{label} must use canonical unique order")
    return result


def _optional_digest(value: DigestRef | None) -> str | None:
    return None if value is None else value.value


def _optional_ref(value: ArtifactRef | None) -> dict[str, object] | None:
    return None if value is None else artifact_ref_to_dict(value)


@dataclass(frozen=True, slots=True)
class SurfaceRowChangeStats:
    row_count_before: int | None = None
    row_count_current: int | None = None
    row_added_count: int = 0
    row_deleted_count: int = 0
    row_modified_count: int = 0
    suppressed_added_count: int = 0
    suppressed_deleted_count: int = 0

    def __post_init__(self) -> None:
        for label in (
            "row_count_before",
            "row_count_current",
            "row_added_count",
            "row_deleted_count",
            "row_modified_count",
            "suppressed_added_count",
            "suppressed_deleted_count",
        ):
            value = getattr(self, label)
            if value is not None:
                _require_non_negative(value, label)

    def to_document(self) -> dict[str, object]:
        return {
            "row_added_count": self.row_added_count,
            "row_count_before": self.row_count_before,
            "row_count_current": self.row_count_current,
            "row_deleted_count": self.row_deleted_count,
            "row_modified_count": self.row_modified_count,
            "suppressed_added_count": self.suppressed_added_count,
            "suppressed_deleted_count": self.suppressed_deleted_count,
        }


@dataclass(frozen=True, slots=True)
class SurfaceColumn:
    name: str
    display_name: str
    scalar_type: str | None
    nullable: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_identifier(self.name, "name"))
        _require_text(self.display_name, "display_name")
        if self.scalar_type is not None:
            _require_text(self.scalar_type, "scalar_type")
        if type(self.nullable) is not bool:
            raise ValueError("nullable must be bool")

    def to_document(self) -> dict[str, object]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "nullable": self.nullable,
            "scalar_type": self.scalar_type,
        }


@dataclass(frozen=True, slots=True)
class SurfaceSchemaSummary:
    before_only_columns: tuple[str, ...] = ()
    current_only_columns: tuple[str, ...] = ()
    selected_columns: tuple[str, ...] = ()
    effective_compare_key_before: tuple[str, ...] = ()
    effective_compare_key_current: tuple[str, ...] = ()
    effective_compare_key_changed: bool = False
    incompatible_columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label in (
            "before_only_columns",
            "current_only_columns",
            "selected_columns",
            "effective_compare_key_before",
            "effective_compare_key_current",
            "incompatible_columns",
        ):
            object.__setattr__(self, label, _require_sorted_unique_strings(getattr(self, label), label))
        if type(self.effective_compare_key_changed) is not bool:
            raise ValueError("effective_compare_key_changed must be bool")

    @classmethod
    def from_comparison(cls, value: ComparisonSchemaChanges) -> "SurfaceSchemaSummary":
        if type(value) is not ComparisonSchemaChanges:
            raise TypeError("value must be ComparisonSchemaChanges")
        return cls(
            before_only_columns=value.before_only_columns,
            current_only_columns=value.current_only_columns,
            selected_columns=value.selected_columns,
            effective_compare_key_before=value.effective_compare_key_before,
            effective_compare_key_current=value.effective_compare_key_current,
            effective_compare_key_changed=value.effective_compare_key_changed,
            incompatible_columns=value.incompatible_columns,
        )

    def to_document(self) -> dict[str, object]:
        return {
            "before_only_columns": list(self.before_only_columns),
            "current_only_columns": list(self.current_only_columns),
            "effective_compare_key_before": list(self.effective_compare_key_before),
            "effective_compare_key_changed": self.effective_compare_key_changed,
            "effective_compare_key_current": list(self.effective_compare_key_current),
            "incompatible_columns": list(self.incompatible_columns),
            "selected_columns": list(self.selected_columns),
        }


@dataclass(frozen=True, slots=True)
class SurfaceReplacementSide:
    row_count: int
    columns: tuple[SurfaceColumn, ...]

    def __post_init__(self) -> None:
        _require_non_negative(self.row_count, "row_count")
        if type(self.columns) is not tuple or any(type(item) is not SurfaceColumn for item in self.columns):
            raise ValueError("columns must contain SurfaceColumn")
        names = tuple(item.name for item in self.columns)
        if names != tuple(sorted(names)) or len(set(names)) != len(names):
            raise ValueError("columns must use canonical unique order")

    def to_document(self) -> dict[str, object]:
        return {
            "columns": [item.to_document() for item in self.columns],
            "row_count": self.row_count,
        }


@dataclass(frozen=True, slots=True)
class SurfaceReplacementSummary:
    before: SurfaceReplacementSide | None
    current: SurfaceReplacementSide | None

    def to_document(self) -> dict[str, object]:
        return {
            "before": None if self.before is None else self.before.to_document(),
            "current": None if self.current is None else self.current.to_document(),
        }


@dataclass(frozen=True, slots=True)
class SurfaceTableRefs:
    before_table_ref: ArtifactRef | None = None
    current_table_ref: ArtifactRef | None = None
    browse_table_ref: ArtifactRef | None = None

    def __post_init__(self) -> None:
        for label in ("before_table_ref", "current_table_ref", "browse_table_ref"):
            _require_optional_ref(getattr(self, label), label)

    def to_document(self) -> dict[str, object]:
        return {
            "before_table_ref": _optional_ref(self.before_table_ref),
            "browse_table_ref": _optional_ref(self.browse_table_ref),
            "current_table_ref": _optional_ref(self.current_table_ref),
        }


@dataclass(frozen=True, slots=True)
class SurfaceRecordsRefs:
    records_ref: ArtifactRef | None = None
    records_manifest_ref: ArtifactRef | None = None
    records_format: SurfaceRecordsFormat = SurfaceRecordsFormat.INLINE_SUMMARY

    def __post_init__(self) -> None:
        if type(self.records_format) is not SurfaceRecordsFormat:
            raise ValueError("records_format must be SurfaceRecordsFormat")
        _require_optional_ref(self.records_ref, "records_ref")
        _require_optional_ref(self.records_manifest_ref, "records_manifest_ref")
        if (self.records_ref is None) != (self.records_manifest_ref is None):
            raise ValueError("records_ref and records_manifest_ref must be provided together")
        if self.records_ref is not None and self.records_format is not SurfaceRecordsFormat.PARQUET:
            raise ValueError("published records refs require PARQUET format")

    def to_document(self) -> dict[str, object]:
        return {
            "records_format": self.records_format.value,
            "records_manifest_ref": _optional_ref(self.records_manifest_ref),
            "records_ref": _optional_ref(self.records_ref),
        }


@dataclass(frozen=True, slots=True)
class SurfaceRiskRefs:
    risk_level: RiskLevel | None = None
    reason_codes: tuple[RiskReasonCode, ...] = ()
    annotation_count: int = 0
    report_ref: ArtifactRef | None = None
    annotation_ref: ArtifactRef | None = None
    annotation_manifest_ref: ArtifactRef | None = None

    def __post_init__(self) -> None:
        if self.risk_level is not None and type(self.risk_level) is not RiskLevel:
            raise ValueError("risk_level must be RiskLevel or None")
        if type(self.reason_codes) is not tuple or any(
            type(item) is not RiskReasonCode for item in self.reason_codes
        ):
            raise ValueError("reason_codes must contain RiskReasonCode")
        if self.reason_codes != tuple(sorted(set(self.reason_codes), key=lambda item: item.value)):
            raise ValueError("reason_codes must use canonical unique order")
        _require_non_negative(self.annotation_count, "annotation_count")
        for label in ("report_ref", "annotation_ref", "annotation_manifest_ref"):
            _require_optional_ref(getattr(self, label), label)
        if (self.annotation_ref is None) != (self.annotation_manifest_ref is None):
            raise ValueError("annotation refs must be provided together")
        if self.risk_level is None and self.reason_codes:
            raise ValueError("reason codes require a risk level")

    def to_document(self) -> dict[str, object]:
        return {
            "annotation_count": self.annotation_count,
            "annotation_manifest_ref": _optional_ref(self.annotation_manifest_ref),
            "annotation_ref": _optional_ref(self.annotation_ref),
            "reason_codes": [item.value for item in self.reason_codes],
            "report_ref": _optional_ref(self.report_ref),
            "risk_level": None if self.risk_level is None else self.risk_level.value,
        }


@dataclass(frozen=True, slots=True)
class SurfaceDiagnostics:
    diagnostics_ref: ArtifactRef | None = None
    diagnostics_summary: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_optional_ref(self.diagnostics_ref, "diagnostics_ref")
        if type(self.diagnostics_summary) is not tuple or any(
            type(item) is not str or item == "" for item in self.diagnostics_summary
        ):
            raise ValueError("diagnostics_summary must contain non-empty strings")

    def to_document(self) -> dict[str, object]:
        return {
            "diagnostics_ref": _optional_ref(self.diagnostics_ref),
            "diagnostics_summary": list(self.diagnostics_summary),
        }


@dataclass(frozen=True, slots=True)
class SurfaceDisplay:
    strategy: SurfaceDisplayStrategy
    table_processing_mode: SurfaceTableProcessingMode
    replay_guarantee: SurfaceReplayGuarantee

    def __post_init__(self) -> None:
        if type(self.strategy) is not SurfaceDisplayStrategy:
            raise ValueError("strategy must be SurfaceDisplayStrategy")
        if type(self.table_processing_mode) is not SurfaceTableProcessingMode:
            raise ValueError("table_processing_mode must be SurfaceTableProcessingMode")
        if type(self.replay_guarantee) is not SurfaceReplayGuarantee:
            raise ValueError("replay_guarantee must be SurfaceReplayGuarantee")

    def to_document(self) -> dict[str, object]:
        return {
            "replay_guarantee": self.replay_guarantee.value,
            "strategy": self.strategy.value,
            "table_processing_mode": self.table_processing_mode.value,
        }


@dataclass(frozen=True, slots=True)
class SurfaceCompare:
    artifact_scope: ArtifactScope | None
    compare_key_columns: tuple[str, ...]
    ignored_columns: tuple[str, ...]
    effective_columns: tuple[str, ...]
    projection_schema_digest: DigestRef | None = None
    projection_logical_digest: DigestRef | None = None
    provider: str | None = None

    def __post_init__(self) -> None:
        if self.artifact_scope is not None and type(self.artifact_scope) is not ArtifactScope:
            raise ValueError("artifact_scope must be ArtifactScope or None")
        for label in ("compare_key_columns", "ignored_columns", "effective_columns"):
            object.__setattr__(self, label, _require_sorted_unique_strings(getattr(self, label), label))
        for label in ("projection_schema_digest", "projection_logical_digest"):
            value = getattr(self, label)
            if value is not None:
                _require_digest(value, label)
        if self.provider is not None:
            _require_text(self.provider, "provider")

    def to_document(self) -> dict[str, object]:
        return {
            "artifact_scope": None if self.artifact_scope is None else self.artifact_scope.value,
            "compare_key_columns": list(self.compare_key_columns),
            "effective_columns": list(self.effective_columns),
            "ignored_columns": list(self.ignored_columns),
            "projection_logical_digest": _optional_digest(self.projection_logical_digest),
            "projection_schema_digest": _optional_digest(self.projection_schema_digest),
            "provider": self.provider,
        }


@dataclass(frozen=True, slots=True)
class SurfaceTable:
    table_id: str
    table_name: str
    display_name: str
    table_status: ComparisonTableStatus
    change_kind: SurfaceChangeKind
    row_change_stats: SurfaceRowChangeStats
    schema_summary: SurfaceSchemaSummary | None
    columns: tuple[SurfaceColumn, ...]
    table_refs: SurfaceTableRefs
    records_refs: SurfaceRecordsRefs
    risk_refs: SurfaceRiskRefs
    display: SurfaceDisplay
    compare: SurfaceCompare
    diagnostics: SurfaceDiagnostics
    replacement_summary: SurfaceReplacementSummary | None = None
    ordered_extension: dict[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_id", _require_identifier(self.table_id, "table_id"))
        object.__setattr__(self, "table_name", _require_identifier(self.table_name, "table_name"))
        _require_text(self.display_name, "display_name")
        if self.table_id != self.table_name:
            raise ValueError("table_id must equal table_name in Surface v2")
        if type(self.table_status) is not ComparisonTableStatus:
            raise ValueError("table_status must be ComparisonTableStatus")
        if type(self.change_kind) is not SurfaceChangeKind:
            raise ValueError("change_kind must be SurfaceChangeKind")
        if type(self.row_change_stats) is not SurfaceRowChangeStats:
            raise ValueError("row_change_stats must be SurfaceRowChangeStats")
        if self.schema_summary is not None and type(self.schema_summary) is not SurfaceSchemaSummary:
            raise ValueError("schema_summary must be SurfaceSchemaSummary or None")
        if type(self.columns) is not tuple or any(type(item) is not SurfaceColumn for item in self.columns):
            raise ValueError("columns must contain SurfaceColumn")
        names = tuple(item.name for item in self.columns)
        if names != tuple(sorted(names)) or len(set(names)) != len(names):
            raise ValueError("columns must use canonical unique order")
        if type(self.table_refs) is not SurfaceTableRefs:
            raise ValueError("table_refs must be SurfaceTableRefs")
        if type(self.records_refs) is not SurfaceRecordsRefs:
            raise ValueError("records_refs must be SurfaceRecordsRefs")
        if type(self.risk_refs) is not SurfaceRiskRefs:
            raise ValueError("risk_refs must be SurfaceRiskRefs")
        if type(self.display) is not SurfaceDisplay:
            raise ValueError("display must be SurfaceDisplay")
        if type(self.compare) is not SurfaceCompare:
            raise ValueError("compare must be SurfaceCompare")
        if type(self.diagnostics) is not SurfaceDiagnostics:
            raise ValueError("diagnostics must be SurfaceDiagnostics")
        if self.replacement_summary is not None and type(self.replacement_summary) is not SurfaceReplacementSummary:
            raise ValueError("replacement_summary must be SurfaceReplacementSummary or None")
        if self.ordered_extension is not None:
            assert_no_host_path_identity(self.ordered_extension, label="ordered_extension")

    def to_document(self) -> dict[str, object]:
        ordered_document = None
        if self.ordered_extension is not None:
            ordered_document = {
                key: artifact_ref_to_dict(value) if type(value) is ArtifactRef else value
                for key, value in self.ordered_extension.items()
            }
        return {
            "change_kind": self.change_kind.value,
            "columns": [item.to_document() for item in self.columns],
            "compare": self.compare.to_document(),
            "diagnostics": self.diagnostics.to_document(),
            "display": self.display.to_document(),
            "display_name": self.display_name,
            "ordered_extension": ordered_document,
            "records_refs": self.records_refs.to_document(),
            "replacement_summary": (
                None if self.replacement_summary is None else self.replacement_summary.to_document()
            ),
            "risk_refs": self.risk_refs.to_document(),
            "row_change_stats": self.row_change_stats.to_document(),
            "schema_summary": None if self.schema_summary is None else self.schema_summary.to_document(),
            "table_id": self.table_id,
            "table_name": self.table_name,
            "table_refs": self.table_refs.to_document(),
            "table_status": self.table_status.value,
        }


@dataclass(frozen=True, slots=True)
class SurfaceProjectionRef:
    projection_id: str
    projection_kind: str
    projection_ref: ArtifactRef
    projection_digest: DigestRef
    projection_summary: tuple[tuple[str, str], ...] = ()
    risk_summary_ref: ArtifactRef | None = None
    diagnostics_ref: ArtifactRef | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "projection_id", _require_identifier(self.projection_id, "projection_id"))
        _require_text(self.projection_kind, "projection_kind")
        _require_ref(self.projection_ref, "projection_ref")
        _require_digest(self.projection_digest, "projection_digest")
        if type(self.projection_summary) is not tuple or any(
            type(item) is not tuple or len(item) != 2 or type(item[0]) is not str or type(item[1]) is not str
            for item in self.projection_summary
        ):
            raise ValueError("projection_summary must contain string pairs")
        _require_optional_ref(self.risk_summary_ref, "risk_summary_ref")
        _require_optional_ref(self.diagnostics_ref, "diagnostics_ref")

    def to_document(self) -> dict[str, object]:
        return {
            "diagnostics_ref": _optional_ref(self.diagnostics_ref),
            "projection_digest": self.projection_digest.value,
            "projection_id": self.projection_id,
            "projection_kind": self.projection_kind,
            "projection_ref": artifact_ref_to_dict(self.projection_ref),
            "projection_summary": [{"key": key, "value": value} for key, value in self.projection_summary],
            "risk_summary_ref": _optional_ref(self.risk_summary_ref),
        }


@dataclass(frozen=True, slots=True)
class SurfaceView:
    view_id: str
    label: str | None
    before_role: str
    current_role: str
    table_count: int
    changed_table_count: int
    degraded_table_count: int
    failed_table_count: int
    risk_level: RiskLevel | None
    diagnostics_summary: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "view_id", _require_identifier(self.view_id, "view_id"))
        if self.label is not None:
            _require_text(self.label, "label")
        _require_text(self.before_role, "before_role")
        _require_text(self.current_role, "current_role")
        for label in (
            "table_count",
            "changed_table_count",
            "degraded_table_count",
            "failed_table_count",
        ):
            _require_non_negative(getattr(self, label), label)
        if self.risk_level is not None and type(self.risk_level) is not RiskLevel:
            raise ValueError("risk_level must be RiskLevel or None")
        _require_string_tuple(self.diagnostics_summary, "diagnostics_summary")

    def to_document(self) -> dict[str, object]:
        return {
            "before_role": self.before_role,
            "changed_table_count": self.changed_table_count,
            "current_role": self.current_role,
            "degraded_table_count": self.degraded_table_count,
            "diagnostics_summary": list(self.diagnostics_summary),
            "failed_table_count": self.failed_table_count,
            "label": self.label,
            "risk_level": None if self.risk_level is None else self.risk_level.value,
            "table_count": self.table_count,
            "view_id": self.view_id,
        }


@dataclass(frozen=True, slots=True)
class SurfaceSummary:
    table_count: int
    changed_table_count: int
    degraded_table_count: int
    failed_table_count: int
    row_added_count: int
    row_deleted_count: int
    row_modified_count: int
    diagnostics_count: int

    def __post_init__(self) -> None:
        for label in (
            "table_count",
            "changed_table_count",
            "degraded_table_count",
            "failed_table_count",
            "row_added_count",
            "row_deleted_count",
            "row_modified_count",
            "diagnostics_count",
        ):
            _require_non_negative(getattr(self, label), label)

    def to_document(self) -> dict[str, object]:
        return {
            "changed_table_count": self.changed_table_count,
            "degraded_table_count": self.degraded_table_count,
            "diagnostics_count": self.diagnostics_count,
            "failed_table_count": self.failed_table_count,
            "row_added_count": self.row_added_count,
            "row_deleted_count": self.row_deleted_count,
            "row_modified_count": self.row_modified_count,
            "table_count": self.table_count,
        }


@dataclass(frozen=True, slots=True)
class SurfaceRootRefs:
    records_closure_ref: ArtifactRef | None = None
    risk_report_ref: ArtifactRef | None = None
    risk_annotation_closure_ref: ArtifactRef | None = None
    project_identity_assessment_ref: ArtifactRef | None = None
    diagnostics_ref: ArtifactRef | None = None

    def __post_init__(self) -> None:
        for label in (
            "records_closure_ref",
            "risk_report_ref",
            "risk_annotation_closure_ref",
            "project_identity_assessment_ref",
            "diagnostics_ref",
        ):
            _require_optional_ref(getattr(self, label), label)

    def to_document(self) -> dict[str, object]:
        return {
            "diagnostics_ref": _optional_ref(self.diagnostics_ref),
            "project_identity_assessment_ref": _optional_ref(self.project_identity_assessment_ref),
            "records_closure_ref": _optional_ref(self.records_closure_ref),
            "risk_annotation_closure_ref": _optional_ref(self.risk_annotation_closure_ref),
            "risk_report_ref": _optional_ref(self.risk_report_ref),
        }


@dataclass(frozen=True, slots=True)
class ComparisonSurface:
    surface_contract_version: str
    surface_digest: DigestRef
    surface_id: str
    direction: str
    comparison_digest: DigestRef
    comparison_mode: ComparisonMode
    project_identity_status: IdentityStatus
    project_identity_assessment_digest: DigestRef | None
    requires_submit_confirmation: bool
    risk_evaluation_digest: DigestRef | None
    view: SurfaceView
    tables: tuple[SurfaceTable, ...]
    projections: tuple[SurfaceProjectionRef, ...]
    summary: SurfaceSummary
    refs: SurfaceRootRefs
    diagnostics: SurfaceDiagnostics
    reserved_extensions: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.surface_contract_version != SURFACE_CONTRACT_VERSION:
            raise ValueError("unsupported surface contract version")
        _require_digest(self.surface_digest, "surface_digest")
        object.__setattr__(self, "surface_id", _require_text(self.surface_id, "surface_id"))
        assert_no_host_path_identity(self.surface_id, label="surface_id")
        _require_text(self.direction, "direction")
        _require_digest(self.comparison_digest, "comparison_digest")
        if type(self.comparison_mode) is not ComparisonMode:
            raise ValueError("comparison_mode must be ComparisonMode")
        if type(self.project_identity_status) is not IdentityStatus:
            raise ValueError("project_identity_status must be IdentityStatus")
        if self.project_identity_assessment_digest is not None:
            _require_digest(self.project_identity_assessment_digest, "project_identity_assessment_digest")
        if type(self.requires_submit_confirmation) is not bool:
            raise ValueError("requires_submit_confirmation must be bool")
        if self.risk_evaluation_digest is not None:
            _require_digest(self.risk_evaluation_digest, "risk_evaluation_digest")
        if type(self.view) is not SurfaceView:
            raise ValueError("view must be SurfaceView")
        if type(self.tables) is not tuple or any(type(item) is not SurfaceTable for item in self.tables):
            raise ValueError("tables must contain SurfaceTable")
        table_names = tuple(item.table_name for item in self.tables)
        if table_names != tuple(sorted(table_names)) or len(set(table_names)) != len(table_names):
            raise ValueError("tables must use canonical unique order")
        if type(self.projections) is not tuple or any(
            type(item) is not SurfaceProjectionRef for item in self.projections
        ):
            raise ValueError("projections must contain SurfaceProjectionRef")
        projection_ids = tuple(item.projection_id for item in self.projections)
        if projection_ids != tuple(sorted(projection_ids)) or len(set(projection_ids)) != len(projection_ids):
            raise ValueError("projections must use canonical unique order")
        if type(self.summary) is not SurfaceSummary:
            raise ValueError("summary must be SurfaceSummary")
        if type(self.refs) is not SurfaceRootRefs:
            raise ValueError("refs must be SurfaceRootRefs")
        if type(self.diagnostics) is not SurfaceDiagnostics:
            raise ValueError("diagnostics must be SurfaceDiagnostics")
        if type(self.reserved_extensions) is not tuple or any(
            type(item) is not tuple or len(item) != 2 or type(item[0]) is not str or type(item[1]) is not str
            for item in self.reserved_extensions
        ):
            raise ValueError("reserved_extensions must contain string pairs")

    def to_document(self) -> dict[str, object]:
        return {
            "comparison_digest": self.comparison_digest.value,
            "comparison_mode": self.comparison_mode.value,
            "diagnostics": self.diagnostics.to_document(),
            "direction": self.direction,
            "project_identity_assessment_digest": _optional_digest(
                self.project_identity_assessment_digest
            ),
            "project_identity_status": self.project_identity_status.value,
            "projections": [item.to_document() for item in self.projections],
            "refs": self.refs.to_document(),
            "reserved_extensions": [
                {"key": key, "value": value} for key, value in self.reserved_extensions
            ],
            "requires_submit_confirmation": self.requires_submit_confirmation,
            "risk_evaluation_digest": _optional_digest(self.risk_evaluation_digest),
            "surface_contract_version": self.surface_contract_version,
            "surface_digest": self.surface_digest.value,
            "surface_id": self.surface_id,
            "summary": self.summary.to_document(),
            "tables": [item.to_document() for item in self.tables],
            "view": self.view.to_document(),
        }


@dataclass(frozen=True, slots=True)
class SurfaceArtifactIndexEntry:
    table_name: str
    table_refs: SurfaceTableRefs = SurfaceTableRefs()
    diagnostics_ref: ArtifactRef | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_name", _require_identifier(self.table_name, "table_name"))
        if type(self.table_refs) is not SurfaceTableRefs:
            raise ValueError("table_refs must be SurfaceTableRefs")
        _require_optional_ref(self.diagnostics_ref, "diagnostics_ref")


@dataclass(frozen=True, slots=True)
class SurfaceAssemblyInput:
    comparison_facts: ComparisonFacts
    surface_id: str
    view_id: str
    before_role: str
    current_role: str
    label: str | None = None
    records_closure: ComparisonRecordsClosure | None = None
    risk_report: RiskReport | None = None
    risk_annotation_closure: RiskAnnotationClosure | None = None
    table_artifacts: tuple[SurfaceArtifactIndexEntry, ...] = ()
    project_identity_assessment_ref: ArtifactRef | None = None
    risk_report_ref: ArtifactRef | None = None
    risk_annotation_closure_ref: ArtifactRef | None = None
    diagnostics_ref: ArtifactRef | None = None
    profile: SurfaceProfile = SurfaceProfile.STANDARD_TABLE_BROWSER
    ref_scope: SurfaceRefScope = SurfaceRefScope.OPERATION_RELATIVE
    requires_submit_confirmation: bool = False

    def __post_init__(self) -> None:
        if type(self.comparison_facts) is not ComparisonFacts:
            raise ValueError("comparison_facts must be ComparisonFacts")
        _require_text(self.surface_id, "surface_id")
        assert_no_host_path_identity(self.surface_id, label="surface_id")
        object.__setattr__(self, "view_id", _require_identifier(self.view_id, "view_id"))
        _require_text(self.before_role, "before_role")
        _require_text(self.current_role, "current_role")
        if self.label is not None:
            _require_text(self.label, "label")
        if self.records_closure is not None and type(self.records_closure) is not ComparisonRecordsClosure:
            raise ValueError("records_closure must be ComparisonRecordsClosure or None")
        if self.risk_report is not None and type(self.risk_report) is not RiskReport:
            raise ValueError("risk_report must be RiskReport or None")
        if self.risk_annotation_closure is not None and type(self.risk_annotation_closure) is not RiskAnnotationClosure:
            raise ValueError("risk_annotation_closure must be RiskAnnotationClosure or None")
        if type(self.table_artifacts) is not tuple or any(
            type(item) is not SurfaceArtifactIndexEntry for item in self.table_artifacts
        ):
            raise ValueError("table_artifacts must contain SurfaceArtifactIndexEntry")
        artifact_names = tuple(item.table_name for item in self.table_artifacts)
        if artifact_names != tuple(sorted(artifact_names)) or len(set(artifact_names)) != len(artifact_names):
            raise ValueError("table_artifacts must use canonical unique order")
        for label in (
            "project_identity_assessment_ref",
            "risk_report_ref",
            "risk_annotation_closure_ref",
            "diagnostics_ref",
        ):
            _require_optional_ref(getattr(self, label), label)
        if type(self.profile) is not SurfaceProfile:
            raise ValueError("profile must be SurfaceProfile")
        if type(self.ref_scope) is not SurfaceRefScope:
            raise ValueError("ref_scope must be SurfaceRefScope")
        if type(self.requires_submit_confirmation) is not bool:
            raise ValueError("requires_submit_confirmation must be bool")


@dataclass(frozen=True, slots=True)
class SurfaceAssemblyPolicy:
    max_surface_json_bytes: int = MAX_SURFACE_JSON_BYTES
    max_surface_wall_time_seconds: float = MAX_SURFACE_WALL_TIME_SECONDS

    def __post_init__(self) -> None:
        if type(self.max_surface_json_bytes) is not int or self.max_surface_json_bytes < 1:
            raise ValueError("max_surface_json_bytes must be positive")
        if type(self.max_surface_wall_time_seconds) not in {int, float} or self.max_surface_wall_time_seconds <= 0:
            raise ValueError("max_surface_wall_time_seconds must be positive float")
        object.__setattr__(self, "max_surface_wall_time_seconds", float(self.max_surface_wall_time_seconds))


@dataclass(frozen=True, slots=True)
class SurfaceAssemblyContext:
    checkpoint: Callable[[], None] = lambda: None
    cancel_requested: Callable[[], bool] = lambda: False

    def __post_init__(self) -> None:
        if not callable(self.checkpoint) or not callable(self.cancel_requested):
            raise ValueError("surface execution hooks must be callable")


@dataclass(frozen=True, slots=True)
class SurfaceAssemblyResult:
    status: SurfaceAssemblyStatus
    surface: ComparisonSurface | None = None
    referenced_artifacts: tuple[ArtifactRef, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.status) is not SurfaceAssemblyStatus:
            raise ValueError("status must be SurfaceAssemblyStatus")
        if self.status is SurfaceAssemblyStatus.READY and self.surface is None:
            raise ValueError("READY result requires surface")
        if self.status is not SurfaceAssemblyStatus.READY and self.surface is not None:
            raise ValueError("terminal failure result must not publish surface")
        if type(self.referenced_artifacts) is not tuple or any(
            type(item) is not ArtifactRef for item in self.referenced_artifacts
        ):
            raise ValueError("referenced_artifacts must contain ArtifactRef")
        identities = tuple((item.artifact_id, item.raw_sha256.value) for item in self.referenced_artifacts)
        if identities != tuple(sorted(set(identities))):
            raise ValueError("referenced_artifacts must use canonical unique order")
        _require_string_tuple(self.diagnostics, "diagnostics")


SurfaceInput: TypeAlias = SurfaceAssemblyInput
