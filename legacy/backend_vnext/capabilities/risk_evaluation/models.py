from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Protocol, TYPE_CHECKING, runtime_checkable

from ...artifacts.manifest import ArtifactRef
from ...core.digests import DigestRef, canonical_json_bytes
from ...core.diagnostics import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from ..comparison.models import (
    ComparisonRecord,
    ComparisonFacts,
    ComparisonOrderedExtension,
    ComparisonRecordsClosure,
    ComparisonTableStatus,
)
from ..comparison.ordered.models import OrderedRecord
from .versions import RISK_CONTRACT_VERSION, RISK_MODEL_VERSION, RISK_REPORT_CONTRACT_VERSION

if TYPE_CHECKING:
    from .artifacts import RiskAnnotationArtifact
    from .ruleset_contract import RiskRulesetSnapshot


class RiskLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM_HIGH = "MEDIUM_HIGH"
    UNKNOWN = "UNKNOWN"
    MEDIUM_LOW = "MEDIUM_LOW"
    LOW = "LOW"


class RiskScope(StrEnum):
    TABLE = "TABLE"
    STANDARD_ROWS = "STANDARD_ROWS"
    ORDERED_TABLE = "ORDERED_TABLE"
    DEGRADED_TABLE = "DEGRADED_TABLE"


class RiskTargetType(StrEnum):
    COMPARISON = "COMPARISON"
    TABLE = "TABLE"
    ROW = "ROW"
    ROW_PAIR = "ROW_PAIR"
    ROW_INTERVAL = "ROW_INTERVAL"


class RiskAnnotationDetailPolicy(StrEnum):
    COUNTS_ONLY = "COUNTS_ONLY"
    TARGETS_ONLY = "TARGETS_ONLY"
    TARGETS_WITH_EVIDENCE = "TARGETS_WITH_EVIDENCE"


def _mapping_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("mapping keys must be strings")
        normalized[key] = value
    return normalized


def _normalized_str_tuple(values: Sequence[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("tuple values must be non-empty strings")
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return tuple(normalized)


def _normalize_digest(value: DigestRef | str) -> DigestRef:
    if isinstance(value, DigestRef):
        return value
    return DigestRef.parse(str(value))


def _payload_value(value: object) -> object:
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        return to_payload()
    return value


@dataclass(frozen=True, slots=True)
class RiskOptions:
    include_low_risk: bool = True
    include_unknown: bool = True
    annotation_detail_policy: RiskAnnotationDetailPolicy | str = RiskAnnotationDetailPolicy.COUNTS_ONLY

    def __post_init__(self) -> None:
        if not isinstance(self.include_low_risk, bool):
            raise TypeError("include_low_risk must be a bool")
        if not isinstance(self.include_unknown, bool):
            raise TypeError("include_unknown must be a bool")
        object.__setattr__(
            self,
            "annotation_detail_policy",
            RiskAnnotationDetailPolicy(self.annotation_detail_policy),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "include_low_risk": self.include_low_risk,
            "include_unknown": self.include_unknown,
            "annotation_detail_policy": self.annotation_detail_policy.value,
        }


@dataclass(frozen=True, slots=True)
class RiskRowChangeStats:
    row_added_count: int | None = None
    row_deleted_count: int | None = None
    row_modified_count: int | None = None
    raw_inserted_count: int | None = None
    raw_deleted_count: int | None = None
    raw_updated_count: int | None = None
    suppressed_inserted_count: int | None = None
    suppressed_deleted_count: int | None = None
    artifact_scope: str | None = None
    suppression_reason: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "row_added_count",
            "row_deleted_count",
            "row_modified_count",
            "raw_inserted_count",
            "raw_deleted_count",
            "raw_updated_count",
            "suppressed_inserted_count",
            "suppressed_deleted_count",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer or None")
        for field_name in ("artifact_scope", "suppression_reason"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-empty string or None")

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "row_added_count": self.row_added_count,
            "row_deleted_count": self.row_deleted_count,
            "row_modified_count": self.row_modified_count,
        }
        for field_name in (
            "raw_inserted_count",
            "raw_deleted_count",
            "raw_updated_count",
            "suppressed_inserted_count",
            "suppressed_deleted_count",
            "artifact_scope",
            "suppression_reason",
        ):
            value = getattr(self, field_name)
            if value is not None:
                payload[field_name] = value
        return payload


@dataclass(frozen=True, slots=True)
class RiskSemanticFacts:
    kind: str
    payload: Mapping[str, object] = field(default_factory=dict)
    semantic_contract_version: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("kind must be a non-empty string")
        if not isinstance(self.semantic_contract_version, str) or not self.semantic_contract_version.strip():
            raise ValueError("semantic_contract_version must be a non-empty string")
        object.__setattr__(self, "payload", _mapping_payload(self.payload))

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "payload": _mapping_payload(self.payload),
            "semantic_contract_version": self.semantic_contract_version,
        }


@dataclass(frozen=True, slots=True)
class RiskTarget:
    target_type: RiskTargetType | str
    table_name: str | None = None
    row_identity: str | None = None
    before_row_identity: str | None = None
    current_row_identity: str | None = None
    changed_columns: tuple[str, ...] = field(default_factory=tuple)
    position: int | None = None
    position_range: tuple[int, int] | None = None
    coverage: str | None = None
    row_side: str | None = None
    entity_key: str | None = None
    before_entity_key: str | None = None
    after_entity_key: str | None = None
    before_position: int | None = None
    after_position: int | None = None
    position_start: int | None = None
    position_end: int | None = None
    row_count: int | None = None
    interval_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_type", RiskTargetType(self.target_type))
        if self.table_name is not None:
            if not isinstance(self.table_name, str) or not self.table_name.strip():
                raise ValueError("table_name must be a non-empty string or None")
            object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        for field_name in (
            "row_identity",
            "before_row_identity",
            "current_row_identity",
            "coverage",
            "row_side",
            "entity_key",
            "before_entity_key",
            "after_entity_key",
            "interval_id",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string or None")
        if not isinstance(self.changed_columns, tuple):
            object.__setattr__(self, "changed_columns", tuple(self.changed_columns))
        object.__setattr__(
            self,
            "changed_columns",
            tuple(canonical_identifier(column) for column in self.changed_columns if canonical_identifier(column)),
        )
        if self.position is not None and (
            not isinstance(self.position, int) or isinstance(self.position, bool) or self.position < 0
        ):
            raise ValueError("position must be a non-negative integer or None")
        for field_name in (
            "before_position",
            "after_position",
            "position_start",
            "position_end",
            "row_count",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer or None")
        if self.position_range is not None:
            if not isinstance(self.position_range, tuple) or len(self.position_range) != 2:
                raise ValueError("position_range must be a pair of integers or None")
            start, end = self.position_range
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
                or start < 0
                or end < start
            ):
                raise ValueError("position_range must contain ordered non-negative integers")
        if (
            self.position_start is not None
            and self.position_end is not None
            and self.position_end < self.position_start
        ):
            raise ValueError("position_end must be greater than or equal to position_start")

    def identity_key(self) -> tuple[object, ...]:
        return (
            self.target_type.value,
            self.table_name,
            self.row_identity,
            self.before_row_identity,
            self.current_row_identity,
            self.changed_columns,
            self.position,
            self.position_range,
            self.coverage,
            self.row_side,
            self.entity_key,
            self.before_entity_key,
            self.after_entity_key,
            self.before_position,
            self.after_position,
            self.position_start,
            self.position_end,
            self.row_count,
            self.interval_id,
        )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "target_type": self.target_type.value,
        }
        if self.table_name is not None:
            payload["table_name"] = self.table_name
        if self.row_identity is not None:
            payload["row_identity"] = self.row_identity
        if self.before_row_identity is not None:
            payload["before_row_identity"] = self.before_row_identity
        if self.current_row_identity is not None:
            payload["current_row_identity"] = self.current_row_identity
        if self.changed_columns:
            payload["changed_columns"] = list(self.changed_columns)
        if self.position is not None:
            payload["position"] = self.position
        if self.position_range is not None:
            payload["position_range"] = list(self.position_range)
        if self.coverage is not None:
            payload["coverage"] = self.coverage
        if self.row_side is not None:
            payload["row_side"] = self.row_side
        if self.entity_key is not None:
            payload["entity_key"] = self.entity_key
        if self.before_entity_key is not None:
            payload["before_entity_key"] = self.before_entity_key
        if self.after_entity_key is not None:
            payload["after_entity_key"] = self.after_entity_key
        if self.before_position is not None:
            payload["before_position"] = self.before_position
        if self.after_position is not None:
            payload["after_position"] = self.after_position
        if self.position_start is not None:
            payload["position_start"] = self.position_start
        if self.position_end is not None:
            payload["position_end"] = self.position_end
        if self.row_count is not None:
            payload["row_count"] = self.row_count
        if self.interval_id is not None:
            payload["interval_id"] = self.interval_id
        return payload


@dataclass(frozen=True, slots=True)
class RiskReason:
    reason_code: str
    message: str
    rule_id: str
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            raise ValueError("reason_code must be a non-empty string")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message must be a non-empty string")
        if not isinstance(self.rule_id, str) or not self.rule_id.strip():
            raise ValueError("rule_id must be a non-empty string")
        object.__setattr__(self, "evidence", _mapping_payload(self.evidence))

    def to_payload(self) -> dict[str, object]:
        payload = {
            "reason_code": self.reason_code,
            "message": self.message,
            "rule_id": self.rule_id,
        }
        if self.evidence:
            payload["evidence"] = _mapping_payload(self.evidence)
        return payload


@dataclass(frozen=True, slots=True)
class RiskAnnotation:
    annotation_id: str
    target: RiskTarget
    risk_level: RiskLevel | str
    reasons: tuple[RiskReason, ...]
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.annotation_id, str):
            raise TypeError("annotation_id must be a string")
        if not isinstance(self.target, RiskTarget):
            raise TypeError("target must be a RiskTarget")
        object.__setattr__(self, "risk_level", RiskLevel(self.risk_level))
        if not isinstance(self.reasons, tuple):
            object.__setattr__(self, "reasons", tuple(self.reasons))
        normalized_reasons: list[RiskReason] = []
        for reason in self.reasons:
            if not isinstance(reason, RiskReason):
                raise TypeError("reasons must contain RiskReason values")
            normalized_reasons.append(reason)
        object.__setattr__(self, "reasons", tuple(normalized_reasons))
        if not isinstance(self.diagnostics, tuple):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))

    @property
    def target_type(self) -> RiskTargetType:
        return self.target.target_type

    def with_annotation_id(self, annotation_id: str) -> "RiskAnnotation":
        return replace(self, annotation_id=annotation_id)

    def identity_key(self) -> tuple[object, ...]:
        return self.target.identity_key()

    def to_payload(self) -> dict[str, object]:
        payload = {
            "annotation_id": self.annotation_id,
            "target_type": self.target_type.value,
            "risk_level": self.risk_level.value,
            "target": self.target.to_payload(),
            "reasons": [reason.to_payload() for reason in self.reasons],
        }
        if self.diagnostics:
            payload["diagnostics"] = [diagnostic.to_payload() for diagnostic in self.diagnostics]
        return payload


@runtime_checkable
class RiskRecordsAccess(Protocol):
    def get_records_closure(
        self,
    ) -> ComparisonRecordsClosure | None:
        ...

    def get_ordered_records(
        self,
        table_name: str,
    ) -> tuple[OrderedRecord, ...] | None:
        ...

    def get_standard_records(
        self,
        table_name: str,
    ) -> tuple[ComparisonRecord, ...] | None:
        ...


@dataclass(frozen=True, slots=True)
class RiskFacts:
    comparison_digest: DigestRef | str
    table_name: str
    table_status: ComparisonTableStatus | str
    risk_scope: RiskScope | str
    schema_changes: Mapping[str, object] | None = None
    row_change_stats: RiskRowChangeStats | None = None
    before_row_count: int | None = None
    after_row_count: int | None = None
    degraded: bool = False
    degraded_reasons: tuple[str, ...] = field(default_factory=tuple)
    records_ref: ComparisonRecordsClosure | None = None
    standard_records: tuple[ComparisonRecord, ...] = field(default_factory=tuple)
    ordered_extension: ComparisonOrderedExtension | None = None
    ordered_records: tuple[OrderedRecord, ...] = field(default_factory=tuple)
    semantic_facts: RiskSemanticFacts | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "comparison_digest", _normalize_digest(self.comparison_digest))
        if not isinstance(self.table_name, str) or not self.table_name.strip():
            raise ValueError("table_name must be a non-empty string")
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        object.__setattr__(self, "table_status", ComparisonTableStatus(self.table_status))
        object.__setattr__(self, "risk_scope", RiskScope(self.risk_scope))
        if self.schema_changes is not None:
            object.__setattr__(self, "schema_changes", _mapping_payload(self.schema_changes))
        if self.row_change_stats is not None and not isinstance(self.row_change_stats, RiskRowChangeStats):
            raise TypeError("row_change_stats must be a RiskRowChangeStats or None")
        for field_name in ("before_row_count", "after_row_count"):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer or None")
        if not isinstance(self.degraded, bool):
            raise TypeError("degraded must be a bool")
        if not isinstance(self.degraded_reasons, tuple):
            object.__setattr__(self, "degraded_reasons", tuple(self.degraded_reasons))
        object.__setattr__(self, "degraded_reasons", _normalized_str_tuple(self.degraded_reasons))
        if self.records_ref is not None and not isinstance(self.records_ref, ComparisonRecordsClosure):
            raise TypeError("records_ref must be a ComparisonRecordsClosure or None")
        if not isinstance(self.standard_records, tuple):
            object.__setattr__(self, "standard_records", tuple(self.standard_records))
        normalized_standard_records: list[ComparisonRecord] = []
        for standard_record in self.standard_records:
            if not isinstance(standard_record, ComparisonRecord):
                raise TypeError("standard_records must contain ComparisonRecord values")
            normalized_standard_records.append(standard_record)
        object.__setattr__(self, "standard_records", tuple(normalized_standard_records))
        if self.ordered_extension is not None and not isinstance(self.ordered_extension, ComparisonOrderedExtension):
            raise TypeError("ordered_extension must be a ComparisonOrderedExtension or None")
        if not isinstance(self.ordered_records, tuple):
            object.__setattr__(self, "ordered_records", tuple(self.ordered_records))
        normalized_ordered_records: list[OrderedRecord] = []
        for ordered_record in self.ordered_records:
            if not isinstance(ordered_record, OrderedRecord):
                raise TypeError("ordered_records must contain OrderedRecord values")
            normalized_ordered_records.append(ordered_record)
        object.__setattr__(self, "ordered_records", tuple(normalized_ordered_records))
        if self.semantic_facts is not None and not isinstance(self.semantic_facts, RiskSemanticFacts):
            raise TypeError("semantic_facts must be a RiskSemanticFacts or None")
        if not isinstance(self.diagnostics, tuple):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "comparison_digest": self.comparison_digest.to_payload(),
            "table_name": self.table_name,
            "table_status": self.table_status.value,
            "risk_scope": self.risk_scope.value,
            "degraded": self.degraded,
            "degraded_reasons": list(self.degraded_reasons),
            "records_ref": _payload_value(self.records_ref),
        }
        if self.schema_changes is not None:
            payload["schema_changes"] = _mapping_payload(self.schema_changes)
        if self.row_change_stats is not None:
            payload["row_change_stats"] = self.row_change_stats.to_payload()
        if self.semantic_facts is not None:
            payload["semantic_facts"] = self.semantic_facts.to_payload()
        if self.diagnostics:
            payload["diagnostics"] = [diagnostic.to_payload() for diagnostic in self.diagnostics]
        return payload


@dataclass(frozen=True, slots=True)
class RiskSummary:
    risk_level: RiskLevel | str
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk_level", RiskLevel(self.risk_level))
        if not isinstance(self.reason_codes, tuple):
            object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "reason_codes", _normalized_str_tuple(self.reason_codes))

    def to_payload(self) -> dict[str, object]:
        return {
            "risk_level": self.risk_level.value,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class RiskTableRisk:
    table_name: str
    risk_level: RiskLevel | str
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    annotation_count: int = 0
    source_table_status: ComparisonTableStatus | str = ComparisonTableStatus.UNCHANGED
    annotation_ref: ArtifactRef | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name.strip():
            raise ValueError("table_name must be a non-empty string")
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        object.__setattr__(self, "risk_level", RiskLevel(self.risk_level))
        object.__setattr__(self, "source_table_status", ComparisonTableStatus(self.source_table_status))
        if not isinstance(self.annotation_count, int) or isinstance(self.annotation_count, bool) or self.annotation_count < 0:
            raise ValueError("annotation_count must be a non-negative integer")
        if not isinstance(self.reason_codes, tuple):
            object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "reason_codes", _normalized_str_tuple(self.reason_codes))
        if self.annotation_ref is not None and not isinstance(self.annotation_ref, ArtifactRef):
            raise TypeError("annotation_ref must be an ArtifactRef or None")
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
            "table_name": self.table_name,
            "risk_level": self.risk_level.value,
            "reason_codes": list(self.reason_codes),
            "annotation_count": self.annotation_count,
            "source_table_status": self.source_table_status.value,
        }
        if self.annotation_ref is not None:
            payload["annotation_manifest_digest"] = self.annotation_ref.manifest_digest.to_payload()
        return payload

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        if self.annotation_ref is not None:
            payload["annotation_ref"] = self.annotation_ref.to_payload()
        if self.diagnostics:
            payload["diagnostics"] = [diagnostic.to_payload() for diagnostic in self.diagnostics]
        return payload


@dataclass(frozen=True, slots=True)
class RiskEvaluationInput:
    comparison_facts: ComparisonFacts
    risk_ruleset: "RiskRulesetSnapshot"
    records_access: RiskRecordsAccess | None = None
    risk_contract_version: str = RISK_CONTRACT_VERSION
    risk_model_version: str = RISK_MODEL_VERSION
    requested_tables: tuple[str, ...] = field(default_factory=tuple)
    risk_options: RiskOptions = field(default_factory=RiskOptions)
    artifact_policy: str = "DEFAULT"
    cache_policy: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.comparison_facts, ComparisonFacts):
            raise TypeError("comparison_facts must be a ComparisonFacts")
        if self.records_access is not None and not isinstance(self.records_access, RiskRecordsAccess):
            raise TypeError("records_access must implement RiskRecordsAccess or be None")
        if not isinstance(self.risk_contract_version, str) or not self.risk_contract_version.strip():
            raise ValueError("risk_contract_version must be a non-empty string")
        if not isinstance(self.risk_model_version, str) or not self.risk_model_version.strip():
            raise ValueError("risk_model_version must be a non-empty string")
        if not isinstance(self.requested_tables, tuple):
            object.__setattr__(self, "requested_tables", tuple(self.requested_tables))
        object.__setattr__(
            self,
            "requested_tables",
            tuple(canonical_identifier(table_name) for table_name in self.requested_tables if canonical_identifier(table_name)),
        )
        if not isinstance(self.risk_options, RiskOptions):
            raise TypeError("risk_options must be a RiskOptions")
        if not isinstance(self.artifact_policy, str) or not self.artifact_policy.strip():
            raise ValueError("artifact_policy must be a non-empty string")
        if self.cache_policy is not None and not isinstance(self.cache_policy, str):
            raise TypeError("cache_policy must be a string or None")
        from .ruleset_contract import RiskRulesetSnapshot

        if not isinstance(self.risk_ruleset, RiskRulesetSnapshot):
            raise TypeError("risk_ruleset must be a RiskRulesetSnapshot")

    def to_payload(self) -> dict[str, object]:
        payload = {
            "comparison_digest": self.comparison_facts.comparison_digest.to_payload(),
            "risk_ruleset": self.risk_ruleset.to_payload(),
            "risk_contract_version": self.risk_contract_version,
            "risk_model_version": self.risk_model_version,
            "requested_tables": list(self.requested_tables),
            "risk_options": self.risk_options.to_payload(),
            "artifact_policy": self.artifact_policy,
            "cache_policy": self.cache_policy,
        }
        return payload


@dataclass(frozen=True, slots=True)
class RiskEvaluation:
    risk_evaluation_digest: DigestRef | str
    risk_contract_version: str
    risk_model_version: str
    risk_ruleset_digest: DigestRef | str
    comparison_digest: DigestRef | str
    summary: RiskSummary
    table_risks: tuple[RiskTableRisk, ...] = field(default_factory=tuple)
    annotation_refs: tuple[ArtifactRef, ...] = field(default_factory=tuple)
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk_evaluation_digest", _normalize_digest(self.risk_evaluation_digest))
        object.__setattr__(self, "risk_ruleset_digest", _normalize_digest(self.risk_ruleset_digest))
        object.__setattr__(self, "comparison_digest", _normalize_digest(self.comparison_digest))
        for field_name in ("risk_contract_version", "risk_model_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.summary, RiskSummary):
            raise TypeError("summary must be a RiskSummary")
        if not isinstance(self.table_risks, tuple):
            object.__setattr__(self, "table_risks", tuple(self.table_risks))
        normalized_table_risks: list[RiskTableRisk] = []
        for table_risk in self.table_risks:
            if not isinstance(table_risk, RiskTableRisk):
                raise TypeError("table_risks must contain RiskTableRisk values")
            normalized_table_risks.append(table_risk)
        object.__setattr__(self, "table_risks", tuple(normalized_table_risks))
        if not isinstance(self.annotation_refs, tuple):
            object.__setattr__(self, "annotation_refs", tuple(self.annotation_refs))
        normalized_annotation_refs: list[ArtifactRef] = []
        for annotation_ref in self.annotation_refs:
            if not isinstance(annotation_ref, ArtifactRef):
                raise TypeError("annotation_refs must contain ArtifactRef values")
            normalized_annotation_refs.append(annotation_ref)
        object.__setattr__(self, "annotation_refs", tuple(normalized_annotation_refs))
        if not isinstance(self.diagnostics, tuple):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))

    def to_report(self) -> "RiskReport":
        return RiskReport(
            risk_report_contract_version=RISK_REPORT_CONTRACT_VERSION,
            risk_evaluation_digest=self.risk_evaluation_digest,
            overall=self.summary,
            tables=self.table_risks,
            annotation_refs=self.annotation_refs,
            diagnostics=self.diagnostics,
        )

    def to_payload(self) -> dict[str, object]:
        payload = {
            "risk_evaluation_digest": self.risk_evaluation_digest.to_payload(),
            "risk_contract_version": self.risk_contract_version,
            "risk_model_version": self.risk_model_version,
            "risk_ruleset_digest": self.risk_ruleset_digest.to_payload(),
            "comparison_digest": self.comparison_digest.to_payload(),
            "summary": self.summary.to_payload(),
            "table_risks": [table_risk.to_payload() for table_risk in self.table_risks],
            "annotation_refs": [annotation_ref.to_payload() for annotation_ref in self.annotation_refs],
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }
        return payload


@dataclass(frozen=True, slots=True)
class RiskReport:
    risk_report_contract_version: str
    risk_evaluation_digest: DigestRef | str
    overall: RiskSummary
    tables: tuple[RiskTableRisk, ...] = field(default_factory=tuple)
    annotation_refs: tuple[ArtifactRef, ...] = field(default_factory=tuple)
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.risk_report_contract_version, str) or not self.risk_report_contract_version.strip():
            raise ValueError("risk_report_contract_version must be a non-empty string")
        object.__setattr__(self, "risk_evaluation_digest", _normalize_digest(self.risk_evaluation_digest))
        if not isinstance(self.overall, RiskSummary):
            raise TypeError("overall must be a RiskSummary")
        if not isinstance(self.tables, tuple):
            object.__setattr__(self, "tables", tuple(self.tables))
        normalized_tables: list[RiskTableRisk] = []
        for table in self.tables:
            if not isinstance(table, RiskTableRisk):
                raise TypeError("tables must contain RiskTableRisk values")
            normalized_tables.append(table)
        object.__setattr__(self, "tables", tuple(normalized_tables))
        if not isinstance(self.annotation_refs, tuple):
            object.__setattr__(self, "annotation_refs", tuple(self.annotation_refs))
        normalized_annotation_refs: list[ArtifactRef] = []
        for annotation_ref in self.annotation_refs:
            if not isinstance(annotation_ref, ArtifactRef):
                raise TypeError("annotation_refs must contain ArtifactRef values")
            normalized_annotation_refs.append(annotation_ref)
        object.__setattr__(self, "annotation_refs", tuple(normalized_annotation_refs))
        if not isinstance(self.diagnostics, tuple):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))

    def to_payload(self) -> dict[str, object]:
        return {
            "risk_report_contract_version": self.risk_report_contract_version,
            "risk_evaluation_digest": self.risk_evaluation_digest.to_payload(),
            "overall": self.overall.to_payload(),
            "tables": [table.to_payload() for table in self.tables],
            "annotation_refs": [annotation_ref.to_payload() for annotation_ref in self.annotation_refs],
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class RiskEvaluationResult:
    risk_evaluation: RiskEvaluation
    risk_report: RiskReport
    annotation_artifacts: tuple["RiskAnnotationArtifact", ...] = field(default_factory=tuple)
    cache_diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.risk_evaluation, RiskEvaluation):
            raise TypeError("risk_evaluation must be a RiskEvaluation")
        if not isinstance(self.risk_report, RiskReport):
            raise TypeError("risk_report must be a RiskReport")
        if not isinstance(self.annotation_artifacts, tuple):
            object.__setattr__(self, "annotation_artifacts", tuple(self.annotation_artifacts))
        if not isinstance(self.cache_diagnostics, tuple):
            object.__setattr__(self, "cache_diagnostics", tuple(self.cache_diagnostics))
        if not isinstance(self.diagnostics, tuple):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        for field_name in ("cache_diagnostics", "diagnostics"):
            normalized: list[DiagnosticRecord] = []
            for diagnostic in getattr(self, field_name):
                if not isinstance(diagnostic, DiagnosticRecord):
                    raise TypeError(f"{field_name} must contain DiagnosticRecord values")
                normalized.append(diagnostic)
            object.__setattr__(self, field_name, tuple(normalized))

    def to_payload(self) -> dict[str, object]:
        return {
            "risk_evaluation": self.risk_evaluation.to_payload(),
            "risk_report": self.risk_report.to_payload(),
            "annotation_artifacts": [artifact.to_payload() for artifact in self.annotation_artifacts],
            "cache_diagnostics": [diagnostic.to_payload() for diagnostic in self.cache_diagnostics],
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }
