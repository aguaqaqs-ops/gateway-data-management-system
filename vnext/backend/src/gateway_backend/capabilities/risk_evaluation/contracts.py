"""Public, flow-neutral contracts owned by the Risk capability."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import Callable, Protocol, TypeAlias, runtime_checkable

from gateway_shared_kernel import DigestRef, canonicalize_identifier, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef, artifact_ref_to_dict, assert_no_host_path_identity
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonFacts,
    ComparisonRecordsClosure,
    ComparisonSchemaChanges,
    ComparisonTableStatus,
    OrderedRecord,
)


RISK_CONTRACT_VERSION = "backend-vnext/risk/v1"
RISK_RULESET_CONTRACT_VERSION = "backend-vnext/risk-ruleset/v1"
RISK_MODEL_VERSION = "backend-vnext/risk-model/v2"
RISK_ANNOTATION_CONTRACT_VERSION = "backend-vnext/risk-annotations/v1"
RISK_ANNOTATION_MEDIA_TYPE = "application/vnd.gateway.risk-annotations+json"
RISK_ANNOTATION_MANIFEST_MEDIA_TYPE = (
    "application/vnd.gateway.risk-annotations.manifest+json"
)
RISK_ANNOTATION_CLOSURE_MEDIA_TYPE = (
    "application/vnd.gateway.risk-annotations.closure+json"
)
RISK_CACHE_POLICY_VERSION = "backend-vnext/risk-cache/v1"
RISK_EXECUTION_POLICY_VERSION = "backend-vnext/risk-execution/v1"
RISK_RULESET_ID = "backend-vnext/comparison-risk"
RISK_RULESET_VERSION = "v2"
RISK_RULE_VERSION = "v2"


RiskOptionValue: TypeAlias = str | int | bool | None
RiskOptionsPairs: TypeAlias = tuple[tuple[str, RiskOptionValue], ...]


def _require_string(value: object, label: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{label} must be a string")
    return value


def _require_non_empty_string(value: object, label: str) -> str:
    result = _require_string(value, label)
    if result == "":
        raise ValueError(f"{label} must be a non-empty string")
    return result


def _require_option_value(value: object, label: str) -> RiskOptionValue:
    if value is None or type(value) in {str, int, bool}:
        return value  # type: ignore[return-value]
    raise ValueError(f"{label} must be a string, integer, boolean or null")


def _validate_option_pairs(value: RiskOptionsPairs, label: str) -> None:
    if type(value) is not tuple:
        raise ValueError(f"{label} must be a tuple")
    previous: str | None = None
    seen: set[str] = set()
    for item in value:
        if type(item) is not tuple or len(item) != 2:
            raise ValueError(f"{label} must contain key/value pairs")
        key, item_value = item
        _require_non_empty_string(key, f"{label}.key")
        if previous is not None and key <= previous:
            raise ValueError(f"{label} must use canonical key order")
        if key in seen:
            raise ValueError(f"{label} must not repeat keys")
        _require_option_value(item_value, f"{label}.{key}")
        previous = key
        seen.add(key)


class RiskLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM_HIGH = "MEDIUM_HIGH"
    UNKNOWN = "UNKNOWN"
    MEDIUM_LOW = "MEDIUM_LOW"
    LOW = "LOW"


class RiskTargetType(StrEnum):
    COMPARISON = "COMPARISON"
    TABLE = "TABLE"
    ROW = "ROW"
    ROW_PAIR = "ROW_PAIR"
    ROW_INTERVAL = "ROW_INTERVAL"


class RiskScope(StrEnum):
    PAIR = "PAIR"
    TABLE = "TABLE"
    STANDARD_ROWS = "STANDARD_ROWS"
    ORDERED_TABLE = "ORDERED_TABLE"
    DEGRADED_TABLE = "DEGRADED_TABLE"


class AnnotationDetailPolicy(StrEnum):
    COUNTS_ONLY = "COUNTS_ONLY"
    TARGETS_ONLY = "TARGETS_ONLY"
    TARGETS_WITH_EVIDENCE = "TARGETS_WITH_EVIDENCE"


class RiskEvaluationStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RiskRuleId(StrEnum):
    PROJECT_IDENTITY_MISMATCH = "PROJECT_IDENTITY_MISMATCH"
    TABLE_ADDED = "TABLE_ADDED"
    TABLE_DELETED = "TABLE_DELETED"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    ROW_ADDED = "ROW_ADDED"
    ROW_DELETED = "ROW_DELETED"
    ROW_MODIFIED = "ROW_MODIFIED"
    KEY_DEGRADED = "KEY_DEGRADED"
    ORDERED_DIFF_UNSUPPORTED = "ORDERED_DIFF_UNSUPPORTED"
    COMPARISON_FAILED = "COMPARISON_FAILED"
    COMPOSITE_SIGNAL_POINT = "COMPOSITE_SIGNAL_POINT"
    UNKNOWN_CHANGE_TARGET = "UNKNOWN_CHANGE_TARGET"


class RiskReasonCode(StrEnum):
    PROJECT_IDENTITY_MISMATCH = "PROJECT_IDENTITY_MISMATCH"
    TABLE_ADDED = "TABLE_ADDED"
    TABLE_DELETED = "TABLE_DELETED"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    ROW_ADDED = "ROW_ADDED"
    ROW_DELETED = "ROW_DELETED"
    ROW_MODIFIED = "ROW_MODIFIED"
    KEY_DEGRADED = "KEY_DEGRADED"
    ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED = "ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED"
    COMPARISON_FAILED = "COMPARISON_FAILED"
    COMPOSITE_SIGNAL_CHANGE_REVIEW_REQUIRED = "COMPOSITE_SIGNAL_CHANGE_REVIEW_REQUIRED"
    UNKNOWN_CHANGE_TARGET = "UNKNOWN_CHANGE_TARGET"


@runtime_checkable
class RiskCancellationProbe(Protocol):
    def is_set(self) -> bool:
        ...


@dataclass(frozen=True, slots=True)
class RiskExecutionContext:
    """Non-semantic cancellation/deadline context supplied by the caller."""

    cancel_requested: RiskCancellationProbe | None = None
    deadline_monotonic: float | None = None
    clock: Callable[[], float] = monotonic

    def __post_init__(self) -> None:
        if self.cancel_requested is not None and not isinstance(self.cancel_requested, RiskCancellationProbe):
            raise ValueError("cancel_requested must implement RiskCancellationProbe")
        if self.deadline_monotonic is not None and type(self.deadline_monotonic) is not float:
            raise ValueError("deadline_monotonic must be float or None")
        if not callable(self.clock):
            raise ValueError("clock must be callable")

    def cancellation_requested(self) -> bool:
        return self.cancel_requested is not None and self.cancel_requested.is_set()

    def deadline_expired(self) -> bool:
        return self.deadline_monotonic is not None and self.clock() >= self.deadline_monotonic


@dataclass(frozen=True, slots=True)
class RiskExecutionPolicy:
    """S0-frozen bounded execution policy; policy identity is not semantic risk identity."""

    policy_version: str = RISK_EXECUTION_POLICY_VERSION
    max_risk_tables_per_pair: int = 4_096
    max_annotations_per_table: int = 2_000_000
    max_annotations_per_pair: int = 4_000_000
    max_annotation_artifact_bytes_per_table: int = 512 * 1024 * 1024
    max_risk_evaluation_json_bytes: int = 16 * 1024 * 1024
    max_risk_report_json_bytes: int = 16 * 1024 * 1024
    max_diagnostics_per_table: int = 4_096
    max_diagnostics_bytes_per_table: int = 4 * 1024 * 1024
    max_risk_table_wall_time_seconds: float = 120.0
    max_risk_pair_wall_time_seconds: float = 900.0
    max_pair_concurrency: int = 8
    cancellation_observation_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.policy_version != RISK_EXECUTION_POLICY_VERSION:
            raise ValueError("unsupported risk execution policy version")
        for label in (
            "max_risk_tables_per_pair",
            "max_annotations_per_table",
            "max_annotations_per_pair",
            "max_annotation_artifact_bytes_per_table",
            "max_risk_evaluation_json_bytes",
            "max_risk_report_json_bytes",
            "max_diagnostics_per_table",
            "max_diagnostics_bytes_per_table",
            "max_pair_concurrency",
        ):
            value = getattr(self, label)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{label} must be a positive int")
        for label in (
            "max_risk_table_wall_time_seconds",
            "max_risk_pair_wall_time_seconds",
            "cancellation_observation_seconds",
        ):
            value = getattr(self, label)
            if type(value) is not float or value <= 0:
                raise ValueError(f"{label} must be a positive float")

    def to_document(self) -> dict[str, object]:
        return {
            "cancellation_observation_seconds": self.cancellation_observation_seconds,
            "max_annotation_artifact_bytes_per_table": self.max_annotation_artifact_bytes_per_table,
            "max_annotations_per_pair": self.max_annotations_per_pair,
            "max_annotations_per_table": self.max_annotations_per_table,
            "max_diagnostics_bytes_per_table": self.max_diagnostics_bytes_per_table,
            "max_diagnostics_per_table": self.max_diagnostics_per_table,
            "max_pair_concurrency": self.max_pair_concurrency,
            "max_risk_evaluation_json_bytes": self.max_risk_evaluation_json_bytes,
            "max_risk_pair_wall_time_seconds": self.max_risk_pair_wall_time_seconds,
            "max_risk_table_wall_time_seconds": self.max_risk_table_wall_time_seconds,
            "max_risk_tables_per_pair": self.max_risk_tables_per_pair,
            "max_risk_report_json_bytes": self.max_risk_report_json_bytes,
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True, slots=True)
class RiskOptions:
    include_low_risk: bool = True
    include_unknown: bool = True
    annotation_detail_policy: AnnotationDetailPolicy = AnnotationDetailPolicy.TARGETS_ONLY

    def __post_init__(self) -> None:
        if type(self.include_low_risk) is not bool:
            raise ValueError("include_low_risk must be bool")
        if type(self.include_unknown) is not bool:
            raise ValueError("include_unknown must be bool")
        if type(self.annotation_detail_policy) is not AnnotationDetailPolicy:
            raise ValueError("annotation_detail_policy must be AnnotationDetailPolicy")

    def to_document(self) -> dict[str, object]:
        return {
            "annotation_detail_policy": self.annotation_detail_policy.value,
            "include_low_risk": self.include_low_risk,
            "include_unknown": self.include_unknown,
        }


@dataclass(frozen=True, slots=True)
class RiskArtifactPolicy:
    """Caller-selected artifact policy; publication is outside S1."""

    policy_version: str = RISK_ANNOTATION_CONTRACT_VERSION
    options: RiskOptionsPairs = ()

    def __post_init__(self) -> None:
        _require_non_empty_string(self.policy_version, "policy_version")
        _validate_option_pairs(self.options, "options")

    def to_document(self) -> dict[str, object]:
        return {
            "options": [[key, value] for key, value in self.options],
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True, slots=True)
class RiskCachePolicy:
    """Future cache policy seam with no cache implementation in S1."""

    policy_version: str = RISK_CACHE_POLICY_VERSION
    options: RiskOptionsPairs = ()

    def __post_init__(self) -> None:
        _require_non_empty_string(self.policy_version, "policy_version")
        _validate_option_pairs(self.options, "options")

    def to_document(self) -> dict[str, object]:
        return {
            "options": [[key, value] for key, value in self.options],
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True, slots=True)
class RiskSeverityPolicy:
    default_level: RiskLevel
    overrides: tuple[tuple[RiskReasonCode, RiskLevel], ...] = ()

    def __post_init__(self) -> None:
        if type(self.default_level) is not RiskLevel:
            raise ValueError("default_level must be RiskLevel")
        if type(self.overrides) is not tuple:
            raise ValueError("overrides must be a tuple")
        previous: str | None = None
        seen: set[str] = set()
        for item in self.overrides:
            if type(item) is not tuple or len(item) != 2:
                raise ValueError("overrides must contain reason-code/level pairs")
            reason_code, level = item
            if type(reason_code) is not RiskReasonCode:
                raise ValueError("severity override reason code must be RiskReasonCode")
            if type(level) is not RiskLevel:
                raise ValueError("severity override level must be RiskLevel")
            if reason_code.value in seen:
                raise ValueError("severity overrides must not repeat reason codes")
            if previous is not None and reason_code.value <= previous:
                raise ValueError("severity overrides must use canonical reason-code order")
            seen.add(reason_code.value)
            previous = reason_code.value

    def to_document(self) -> dict[str, object]:
        return {
            "default_level": self.default_level.value,
            "overrides": [[reason.value, level.value] for reason, level in self.overrides],
        }


@dataclass(frozen=True, slots=True)
class RiskRuleSpec:
    rule_id: RiskRuleId
    rule_version: str
    target_scope: RiskScope
    reason_code: RiskReasonCode
    severity_policy: RiskSeverityPolicy
    params: RiskOptionsPairs = ()

    def __post_init__(self) -> None:
        if type(self.rule_id) is not RiskRuleId:
            raise ValueError("rule_id must be RiskRuleId")
        _require_non_empty_string(self.rule_version, "rule_version")
        if type(self.target_scope) is not RiskScope:
            raise ValueError("target_scope must be RiskScope")
        if type(self.reason_code) is not RiskReasonCode:
            raise ValueError("reason_code must be RiskReasonCode")
        if type(self.severity_policy) is not RiskSeverityPolicy:
            raise ValueError("severity_policy must be RiskSeverityPolicy")
        _validate_option_pairs(self.params, "params")

    def to_document(self) -> dict[str, object]:
        return {
            "params": [[key, value] for key, value in self.params],
            "reason_code": self.reason_code.value,
            "rule_id": self.rule_id.value,
            "rule_version": self.rule_version,
            "severity_policy": self.severity_policy.to_document(),
            "target_scope": self.target_scope.value,
        }


@dataclass(frozen=True, slots=True)
class RiskRulesetSnapshot:
    """Immutable ruleset selected by the caller; no mutable registry is consulted."""

    risk_ruleset_id: str = RISK_RULESET_ID
    risk_ruleset_version: str = RISK_RULESET_VERSION
    risk_model_version: str = RISK_MODEL_VERSION
    rules: tuple[RiskRuleSpec, ...] = ()
    risk_ruleset_digest: DigestRef | None = None
    contract_version: str = RISK_RULESET_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for label in ("risk_ruleset_id", "risk_ruleset_version", "risk_model_version"):
            _require_non_empty_string(getattr(self, label), label)
        if self.contract_version != RISK_RULESET_CONTRACT_VERSION:
            raise ValueError("unsupported risk ruleset contract version")
        if type(self.rules) is not tuple:
            raise ValueError("rules must be a tuple")
        previous: str | None = None
        seen: set[str] = set()
        for rule in self.rules:
            if type(rule) is not RiskRuleSpec:
                raise ValueError("rules must contain RiskRuleSpec")
            if rule.rule_id.value in seen:
                raise ValueError("rules must not repeat rule_id")
            if previous is not None and rule.rule_id.value <= previous:
                raise ValueError("rules must use canonical rule_id order")
            seen.add(rule.rule_id.value)
            previous = rule.rule_id.value
        if self.risk_ruleset_digest is not None and type(self.risk_ruleset_digest) is not DigestRef:
            raise ValueError("risk_ruleset_digest must be DigestRef or None")
        expected = compute_risk_ruleset_digest(risk_ruleset_document(self))
        if self.risk_ruleset_digest is None:
            object.__setattr__(self, "risk_ruleset_digest", expected)
        elif self.risk_ruleset_digest != expected:
            raise ValueError("risk_ruleset_digest does not match the canonical document")


_RULESET_DOCUMENT_KEYS = frozenset(
    {"contract_version", "risk_model_version", "risk_ruleset_id", "risk_ruleset_version", "rules"}
)
_RULE_DOCUMENT_KEYS = frozenset(
    {"params", "reason_code", "rule_id", "rule_version", "severity_policy", "target_scope"}
)
_SEVERITY_DOCUMENT_KEYS = frozenset({"default_level", "overrides"})


def risk_ruleset_document(snapshot: RiskRulesetSnapshot) -> dict[str, object]:
    if type(snapshot) is not RiskRulesetSnapshot:
        raise ValueError("snapshot must be RiskRulesetSnapshot")
    return {
        "contract_version": snapshot.contract_version,
        "risk_model_version": snapshot.risk_model_version,
        "risk_ruleset_id": snapshot.risk_ruleset_id,
        "risk_ruleset_version": snapshot.risk_ruleset_version,
        "rules": [rule.to_document() for rule in snapshot.rules],
    }


def compute_risk_ruleset_digest(document: Mapping[str, object]) -> DigestRef:
    if type(document) is not dict:
        raise ValueError("risk ruleset document must be a dict")
    _reject_unknown_keys(document, _RULESET_DOCUMENT_KEYS, "risk ruleset document")
    return raw_blob_digest(canonicalize_json_value(dict(document)))


def risk_ruleset_from_document(document: Mapping[str, object]) -> RiskRulesetSnapshot:
    if type(document) is not dict:
        raise ValueError("risk ruleset document must be a dict")
    _reject_unknown_keys(document, _RULESET_DOCUMENT_KEYS, "risk ruleset document")
    rules_payload = document.get("rules")
    if type(rules_payload) is not list:
        raise ValueError("rules must be a list")
    rules = tuple(_rule_from_document(item) for item in rules_payload)
    return RiskRulesetSnapshot(
        contract_version=_require_string(document.get("contract_version"), "contract_version"),
        risk_model_version=_require_string(document.get("risk_model_version"), "risk_model_version"),
        risk_ruleset_id=_require_string(document.get("risk_ruleset_id"), "risk_ruleset_id"),
        risk_ruleset_version=_require_string(document.get("risk_ruleset_version"), "risk_ruleset_version"),
        rules=rules,
        risk_ruleset_digest=compute_risk_ruleset_digest(document),
    )


def _rule_from_document(payload: object) -> RiskRuleSpec:
    if type(payload) is not dict:
        raise ValueError("risk rule must be an object")
    _reject_unknown_keys(payload, _RULE_DOCUMENT_KEYS, "risk rule")
    severity_payload = payload.get("severity_policy")
    if type(severity_payload) is not dict:
        raise ValueError("severity_policy must be an object")
    _reject_unknown_keys(severity_payload, _SEVERITY_DOCUMENT_KEYS, "severity policy")
    overrides_payload = severity_payload.get("overrides")
    if type(overrides_payload) is not list:
        raise ValueError("severity_policy.overrides must be a list")
    overrides: list[tuple[RiskReasonCode, RiskLevel]] = []
    for item in overrides_payload:
        if type(item) is not list or len(item) != 2:
            raise ValueError("severity overrides must contain two-item lists")
        overrides.append(
            (
                RiskReasonCode(_require_string(item[0], "override.reason_code")),
                RiskLevel(_require_string(item[1], "override.level")),
            )
        )
    return RiskRuleSpec(
        rule_id=RiskRuleId(_require_string(payload.get("rule_id"), "rule_id")),
        rule_version=_require_string(payload.get("rule_version"), "rule_version"),
        target_scope=RiskScope(_require_string(payload.get("target_scope"), "target_scope")),
        reason_code=RiskReasonCode(_require_string(payload.get("reason_code"), "reason_code")),
        severity_policy=RiskSeverityPolicy(
            default_level=RiskLevel(_require_string(severity_payload.get("default_level"), "default_level")),
            overrides=tuple(overrides),
        ),
        params=_pairs_from_document(payload.get("params"), "params"),
    )


@runtime_checkable
class RiskRecordsAccess(Protocol):
    """Read-only R5 records closure protocol consumed by future risk rules."""

    def get_records_closure(self) -> ComparisonRecordsClosure:
        ...

    def get_ordered_records(self, table_name: str) -> tuple[OrderedRecord, ...]:
        ...


@dataclass(frozen=True, slots=True)
class RiskRowChangeStats:
    row_added_count: int | None = None
    row_deleted_count: int | None = None
    row_modified_count: int | None = None

    def __post_init__(self) -> None:
        for label in ("row_added_count", "row_deleted_count", "row_modified_count"):
            value = getattr(self, label)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{label} must be a non-negative int or None")

    def to_document(self) -> dict[str, object]:
        return {
            "row_added_count": self.row_added_count,
            "row_deleted_count": self.row_deleted_count,
            "row_modified_count": self.row_modified_count,
        }


@dataclass(frozen=True, slots=True)
class RiskFacts:
    comparison_digest: DigestRef
    table_name: str
    table_status: ComparisonTableStatus
    risk_scope: RiskScope
    schema_changes: ComparisonSchemaChanges | None = None
    row_change_stats: RiskRowChangeStats | None = None
    degraded: bool = False
    degraded_reasons: tuple[str, ...] = ()
    records_ref: ArtifactRef | None = None
    semantic_facts: RiskOptionsPairs | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.comparison_digest) is not DigestRef:
            raise ValueError("comparison_digest must be DigestRef")
        object.__setattr__(self, "table_name", _require_canonical_name(self.table_name, "table_name"))
        if type(self.table_status) is not ComparisonTableStatus:
            raise ValueError("table_status must be ComparisonTableStatus")
        if type(self.risk_scope) is not RiskScope:
            raise ValueError("risk_scope must be RiskScope")
        if self.schema_changes is not None and type(self.schema_changes) is not ComparisonSchemaChanges:
            raise ValueError("schema_changes must be ComparisonSchemaChanges or None")
        if self.row_change_stats is not None and type(self.row_change_stats) is not RiskRowChangeStats:
            raise ValueError("row_change_stats must be RiskRowChangeStats or None")
        if type(self.degraded) is not bool:
            raise ValueError("degraded must be bool")
        _require_string_tuple(self.degraded_reasons, "degraded_reasons")
        if self.records_ref is not None and type(self.records_ref) is not ArtifactRef:
            raise ValueError("records_ref must be ArtifactRef or None")
        if self.semantic_facts is not None:
            _validate_option_pairs(self.semantic_facts, "semantic_facts")
        _require_string_tuple(self.diagnostics, "diagnostics")

    def to_document(self) -> dict[str, object]:
        return {
            "comparison_digest": self.comparison_digest.value,
            "degraded": self.degraded,
            "degraded_reasons": list(self.degraded_reasons),
            "diagnostics": list(self.diagnostics),
            "records_ref": None if self.records_ref is None else artifact_ref_to_dict(self.records_ref),
            "risk_scope": self.risk_scope.value,
            "row_change_stats": None if self.row_change_stats is None else self.row_change_stats.to_document(),
            "schema_changes": None if self.schema_changes is None else _schema_changes_document(self.schema_changes),
            "semantic_facts": None if self.semantic_facts is None else _pairs_document(self.semantic_facts),
            "table_name": self.table_name,
            "table_status": self.table_status.value,
        }


@dataclass(frozen=True, slots=True)
class RiskTarget:
    target_type: RiskTargetType
    table_name: str | None = None
    row_identity: DigestRef | None = None
    before_row_identity: DigestRef | None = None
    current_row_identity: DigestRef | None = None
    changed_columns: tuple[str, ...] = ()
    position: int | None = None
    position_range: tuple[int, int] | None = None
    coverage: str | None = None

    def __post_init__(self) -> None:
        if type(self.target_type) is not RiskTargetType:
            raise ValueError("target_type must be RiskTargetType")
        if self.table_name is not None:
            object.__setattr__(self, "table_name", _require_canonical_name(self.table_name, "table_name"))
        for label in ("row_identity", "before_row_identity", "current_row_identity"):
            value = getattr(self, label)
            if value is not None and type(value) is not DigestRef:
                raise ValueError(f"{label} must be DigestRef or None")
        object.__setattr__(self, "changed_columns", _canonical_columns(self.changed_columns, "changed_columns"))
        if self.position is not None and (type(self.position) is not int or self.position < 1):
            raise ValueError("position must be a positive int or None")
        if self.position_range is not None:
            if type(self.position_range) is not tuple or len(self.position_range) != 2:
                raise ValueError("position_range must be a two-item tuple or None")
            start, end = self.position_range
            if type(start) is not int or type(end) is not int or start < 1 or end < start:
                raise ValueError("position_range must contain an ordered positive range")
        if self.coverage is not None:
            _require_non_empty_string(self.coverage, "coverage")

    def to_document(self) -> dict[str, object]:
        return {
            "before_row_identity": _optional_digest(self.before_row_identity),
            "changed_columns": list(self.changed_columns),
            "coverage": self.coverage,
            "current_row_identity": _optional_digest(self.current_row_identity),
            "position": self.position,
            "position_range": None if self.position_range is None else list(self.position_range),
            "row_identity": _optional_digest(self.row_identity),
            "table_name": self.table_name,
            "target_type": self.target_type.value,
        }


@dataclass(frozen=True, slots=True)
class RiskReason:
    reason_code: RiskReasonCode
    message: str
    rule_id: RiskRuleId
    evidence: RiskOptionsPairs = ()

    def __post_init__(self) -> None:
        if type(self.reason_code) is not RiskReasonCode:
            raise ValueError("reason_code must be RiskReasonCode")
        _require_non_empty_string(self.message, "message")
        if type(self.rule_id) is not RiskRuleId:
            raise ValueError("rule_id must be RiskRuleId")
        _validate_option_pairs(self.evidence, "evidence")
        assert_no_host_path_identity(dict(self.evidence), label="risk evidence")

    def to_document(self) -> dict[str, object]:
        return {
            "evidence": _pairs_document(self.evidence),
            "message": self.message,
            "reason_code": self.reason_code.value,
            "rule_id": self.rule_id.value,
        }


@dataclass(frozen=True, slots=True)
class RiskAnnotation:
    annotation_id: str
    risk_level: RiskLevel
    target: RiskTarget
    reasons: tuple[RiskReason, ...]
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty_string(self.annotation_id, "annotation_id")
        assert_no_host_path_identity(self.annotation_id, label="annotation_id")
        if type(self.risk_level) is not RiskLevel:
            raise ValueError("risk_level must be RiskLevel")
        if type(self.target) is not RiskTarget:
            raise ValueError("target must be RiskTarget")
        if type(self.reasons) is not tuple or not self.reasons or any(
            type(item) is not RiskReason for item in self.reasons
        ):
            raise ValueError("reasons must contain at least one RiskReason")
        _require_string_tuple(self.diagnostics, "diagnostics")

    def to_document(self) -> dict[str, object]:
        return {
            "annotation_id": self.annotation_id,
            "diagnostics": list(self.diagnostics),
            "reasons": [reason.to_document() for reason in self.reasons],
            "risk_level": self.risk_level.value,
            "target": self.target.to_document(),
        }


@dataclass(frozen=True, slots=True)
class RiskAnnotationArtifact:
    """One immutable canonical JSON annotation payload and its manifest."""

    table_name: str
    content_ref: ArtifactRef
    manifest_ref: ArtifactRef
    content_digest: DigestRef
    manifest_digest: DigestRef
    annotation_count: int
    contract_version: str = RISK_ANNOTATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_name", _require_canonical_name(self.table_name, "table_name"))
        for label in ("content_ref", "manifest_ref"):
            if type(getattr(self, label)) is not ArtifactRef:
                raise ValueError(f"{label} must be ArtifactRef")
        for label in ("content_digest", "manifest_digest"):
            if type(getattr(self, label)) is not DigestRef:
                raise ValueError(f"{label} must be DigestRef")
        if type(self.annotation_count) is not int or self.annotation_count < 0:
            raise ValueError("annotation_count must be a non-negative int")
        if self.contract_version != RISK_ANNOTATION_CONTRACT_VERSION:
            raise ValueError("unsupported risk annotation contract version")

    def to_document(self) -> dict[str, object]:
        return {
            "annotation_count": self.annotation_count,
            "content_digest": self.content_digest.value,
            "content_ref": artifact_ref_to_dict(self.content_ref),
            "contract_version": self.contract_version,
            "manifest_digest": self.manifest_digest.value,
            "manifest_ref": artifact_ref_to_dict(self.manifest_ref),
            "table_name": self.table_name,
        }


@dataclass(frozen=True, slots=True)
class RiskAnnotationClosureEntry:
    """A successful annotation artifact or an explicit degraded no-record entry."""

    table_name: str
    annotation_count: int
    artifact: RiskAnnotationArtifact | None = None
    no_record_reason_codes: tuple[RiskReasonCode, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_name", _require_canonical_name(self.table_name, "table_name"))
        if type(self.annotation_count) is not int or self.annotation_count < 0:
            raise ValueError("annotation_count must be a non-negative int")
        if self.artifact is not None:
            if type(self.artifact) is not RiskAnnotationArtifact:
                raise ValueError("artifact must be RiskAnnotationArtifact or None")
            if self.artifact.table_name != self.table_name:
                raise ValueError("artifact table_name must match closure entry")
            if self.artifact.annotation_count != self.annotation_count:
                raise ValueError("artifact annotation_count must match closure entry")
            if self.no_record_reason_codes:
                raise ValueError("artifact entry must not carry no-record reasons")
        elif not self.no_record_reason_codes:
            raise ValueError("no-record entry requires at least one reason code")
        _require_reason_codes(self.no_record_reason_codes, "no_record_reason_codes")

    def to_document(self) -> dict[str, object]:
        return {
            "annotation_count": self.annotation_count,
            "artifact": None if self.artifact is None else self.artifact.to_document(),
            "no_record_reason_codes": [item.value for item in self.no_record_reason_codes],
            "table_name": self.table_name,
        }


@dataclass(frozen=True, slots=True)
class RiskAnnotationClosure:
    """Immutable logical closure over all published risk annotation artifacts."""

    comparison_digest: DigestRef
    risk_evaluation_digest: DigestRef
    entries: tuple[RiskAnnotationClosureEntry, ...]
    closure_ref: ArtifactRef
    closure_manifest_digest: DigestRef
    contract_version: str = RISK_ANNOTATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for label in ("comparison_digest", "risk_evaluation_digest", "closure_manifest_digest"):
            if type(getattr(self, label)) is not DigestRef:
                raise ValueError(f"{label} must be DigestRef")
        if type(self.entries) is not tuple or any(
            type(item) is not RiskAnnotationClosureEntry for item in self.entries
        ):
            raise ValueError("entries must contain RiskAnnotationClosureEntry")
        names = tuple(item.table_name for item in self.entries)
        if names != tuple(sorted(names)) or len(set(names)) != len(names):
            raise ValueError("closure entries must use canonical unique table order")
        if type(self.closure_ref) is not ArtifactRef:
            raise ValueError("closure_ref must be ArtifactRef")
        if self.contract_version != RISK_ANNOTATION_CONTRACT_VERSION:
            raise ValueError("unsupported risk annotation contract version")

    def to_document(self) -> dict[str, object]:
        return {
            "closure_manifest_digest": self.closure_manifest_digest.value,
            "closure_ref": artifact_ref_to_dict(self.closure_ref),
            "comparison_digest": self.comparison_digest.value,
            "contract_version": self.contract_version,
            "entries": [item.to_document() for item in self.entries],
            "risk_evaluation_digest": self.risk_evaluation_digest.value,
        }


def validate_risk_annotation_documents(
    content_bytes: bytes,
    manifest_bytes: bytes,
    *,
    table_name: str,
    annotation_count: int,
    content_digest: DigestRef,
) -> None:
    """Validate canonical Risk annotation content and manifest documents."""

    try:
        content = json.loads(content_bytes)
        manifest = json.loads(manifest_bytes)
    except (TypeError, ValueError) as exc:
        raise ValueError("risk annotation artifact is not JSON") from exc
    if type(content) is not dict or type(manifest) is not dict:
        raise ValueError("risk annotation artifact must contain JSON objects")
    if canonicalize_json_value(content) != content_bytes:
        raise ValueError("risk annotation content is not canonical JSON")
    if canonicalize_json_value(manifest) != manifest_bytes:
        raise ValueError("risk annotation manifest is not canonical JSON")
    annotations = content.get("annotations")
    if (
        set(content) != {"annotations", "contract_version", "table_name"}
        or content.get("contract_version") != RISK_ANNOTATION_CONTRACT_VERSION
        or content.get("table_name") != table_name
        or type(annotations) is not list
        or len(annotations) != annotation_count
    ):
        raise ValueError("risk annotation content payload mismatch")
    try:
        parsed = tuple(_risk_annotation_from_document(payload) for payload in annotations)
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError("risk annotation record payload mismatch") from exc
    annotation_ids = tuple(item.annotation_id for item in parsed)
    if annotation_ids != tuple(sorted(annotation_ids)) or len(set(annotation_ids)) != len(
        annotation_ids
    ):
        raise ValueError("risk annotation records must use canonical unique order")
    expected_manifest = {
        "annotation_count": annotation_count,
        "content_digest": content_digest.value,
        "contract_version": RISK_ANNOTATION_CONTRACT_VERSION,
        "record_format": "CANONICAL_JSON",
        "table_name": table_name,
    }
    if manifest != expected_manifest:
        raise ValueError("risk annotation manifest payload mismatch")


def _risk_annotation_from_document(payload: object) -> RiskAnnotation:
    if type(payload) is not dict:
        raise ValueError("annotation must be an object")
    if set(payload) != {"annotation_id", "diagnostics", "reasons", "risk_level", "target"}:
        raise ValueError("annotation fields mismatch")
    target_payload = payload["target"]
    if type(target_payload) is not dict:
        raise ValueError("annotation target must be an object")
    target_keys = {
        "before_row_identity",
        "changed_columns",
        "coverage",
        "current_row_identity",
        "position",
        "position_range",
        "row_identity",
        "table_name",
        "target_type",
    }
    if set(target_payload) != target_keys:
        raise ValueError("annotation target fields mismatch")
    changed_columns_payload = target_payload["changed_columns"]
    if type(changed_columns_payload) is not list:
        raise ValueError("annotation changed_columns must be a list")
    position_range_payload = target_payload["position_range"]
    if position_range_payload is not None and type(position_range_payload) is not list:
        raise ValueError("annotation position_range must be a list or null")
    reasons_payload = payload["reasons"]
    if type(reasons_payload) is not list:
        raise ValueError("annotation reasons must be a list")
    diagnostics_payload = payload["diagnostics"]
    if type(diagnostics_payload) is not list:
        raise ValueError("annotation diagnostics must be a list")
    reasons: list[RiskReason] = []
    for reason_payload in reasons_payload:
        if type(reason_payload) is not dict or set(reason_payload) != {
            "evidence",
            "message",
            "reason_code",
            "rule_id",
        }:
            raise ValueError("annotation reason fields mismatch")
        evidence_payload = reason_payload["evidence"]
        if type(evidence_payload) is not list:
            raise ValueError("annotation evidence must be a list")
        evidence: list[tuple[str, object]] = []
        for pair in evidence_payload:
            if type(pair) is not list or len(pair) != 2 or type(pair[0]) is not str:
                raise ValueError("annotation evidence pair mismatch")
            evidence.append((pair[0], pair[1]))
        reasons.append(
            RiskReason(
                reason_code=RiskReasonCode(reason_payload["reason_code"]),
                message=reason_payload["message"],
                rule_id=RiskRuleId(reason_payload["rule_id"]),
                evidence=tuple(evidence),  # type: ignore[arg-type]
            )
        )
    return RiskAnnotation(
        annotation_id=payload["annotation_id"],
        risk_level=RiskLevel(payload["risk_level"]),
        target=RiskTarget(
            target_type=RiskTargetType(str(target_payload["target_type"])),
            table_name=target_payload["table_name"],
            row_identity=(
                None
                if target_payload["row_identity"] is None
                else DigestRef(target_payload["row_identity"])
            ),
            before_row_identity=(
                None
                if target_payload["before_row_identity"] is None
                else DigestRef(target_payload["before_row_identity"])
            ),
            current_row_identity=(
                None
                if target_payload["current_row_identity"] is None
                else DigestRef(target_payload["current_row_identity"])
            ),
            changed_columns=tuple(changed_columns_payload),
            position=target_payload["position"],
            position_range=(
                None
                if position_range_payload is None
                else tuple(position_range_payload)
            ),
            coverage=target_payload["coverage"],
        ),
        reasons=tuple(reasons),
        diagnostics=tuple(diagnostics_payload),
    )


@dataclass(frozen=True, slots=True)
class RiskTableRisk:
    table_name: str
    risk_level: RiskLevel
    reason_codes: tuple[RiskReasonCode, ...]
    annotation_count: int
    source_table_status: ComparisonTableStatus
    annotation_ref: ArtifactRef | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_name", _require_canonical_name(self.table_name, "table_name"))
        if type(self.risk_level) is not RiskLevel:
            raise ValueError("risk_level must be RiskLevel")
        _require_reason_codes(self.reason_codes, "reason_codes", require_one=True)
        if type(self.annotation_count) is not int or self.annotation_count < 0:
            raise ValueError("annotation_count must be a non-negative int")
        if type(self.source_table_status) is not ComparisonTableStatus:
            raise ValueError("source_table_status must be ComparisonTableStatus")
        if self.annotation_ref is not None and type(self.annotation_ref) is not ArtifactRef:
            raise ValueError("annotation_ref must be ArtifactRef or None")
        _require_string_tuple(self.diagnostics, "diagnostics")

    def to_document(self) -> dict[str, object]:
        return {
            "annotation_count": self.annotation_count,
            "annotation_ref": None if self.annotation_ref is None else artifact_ref_to_dict(self.annotation_ref),
            "diagnostics": list(self.diagnostics),
            "reason_codes": [item.value for item in self.reason_codes],
            "risk_level": self.risk_level.value,
            "source_table_status": self.source_table_status.value,
            "table_name": self.table_name,
        }


@dataclass(frozen=True, slots=True)
class RiskSummary:
    risk_level: RiskLevel | None
    reason_codes: tuple[RiskReasonCode, ...]
    table_count: int
    annotation_count: int

    def __post_init__(self) -> None:
        if self.risk_level is not None and type(self.risk_level) is not RiskLevel:
            raise ValueError("risk_level must be RiskLevel or None")
        _require_reason_codes(self.reason_codes, "reason_codes")
        for label in ("table_count", "annotation_count"):
            value = getattr(self, label)
            if type(value) is not int or value < 0:
                raise ValueError(f"{label} must be a non-negative int")
        if self.risk_level is None and self.reason_codes:
            raise ValueError("no overall risk level must not carry reason codes")

    def to_document(self) -> dict[str, object]:
        return {
            "annotation_count": self.annotation_count,
            "reason_codes": [item.value for item in self.reason_codes],
            "risk_level": None if self.risk_level is None else self.risk_level.value,
            "table_count": self.table_count,
        }


@dataclass(frozen=True, slots=True)
class RiskEvaluation:
    risk_evaluation_digest: DigestRef
    risk_contract_version: str
    risk_model_version: str
    risk_ruleset_digest: DigestRef
    comparison_digest: DigestRef
    summary: RiskSummary
    table_risks: tuple[RiskTableRisk, ...]
    annotation_refs: tuple[ArtifactRef, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label in ("risk_evaluation_digest", "risk_ruleset_digest", "comparison_digest"):
            if type(getattr(self, label)) is not DigestRef:
                raise ValueError(f"{label} must be DigestRef")
        if self.risk_contract_version != RISK_CONTRACT_VERSION:
            raise ValueError("unsupported risk contract version")
        _require_non_empty_string(self.risk_model_version, "risk_model_version")
        if type(self.summary) is not RiskSummary:
            raise ValueError("summary must be RiskSummary")
        _validate_table_risks(self.table_risks)
        _validate_artifact_refs(self.annotation_refs, "annotation_refs")
        _require_string_tuple(self.diagnostics, "diagnostics")

    def to_document(self) -> dict[str, object]:
        return {
            "annotation_refs": [artifact_ref_to_dict(item) for item in self.annotation_refs],
            "comparison_digest": self.comparison_digest.value,
            "diagnostics": list(self.diagnostics),
            "risk_contract_version": self.risk_contract_version,
            "risk_evaluation_digest": self.risk_evaluation_digest.value,
            "risk_model_version": self.risk_model_version,
            "risk_ruleset_digest": self.risk_ruleset_digest.value,
            "summary": self.summary.to_document(),
            "table_risks": [item.to_document() for item in self.table_risks],
        }


@dataclass(frozen=True, slots=True)
class RiskReport:
    risk_report_contract_version: str
    risk_evaluation_digest: DigestRef
    overall: RiskSummary
    tables: tuple[RiskTableRisk, ...]
    annotation_refs: tuple[ArtifactRef, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.risk_report_contract_version != RISK_CONTRACT_VERSION:
            raise ValueError("unsupported risk report contract version")
        if type(self.risk_evaluation_digest) is not DigestRef:
            raise ValueError("risk_evaluation_digest must be DigestRef")
        if type(self.overall) is not RiskSummary:
            raise ValueError("overall must be RiskSummary")
        _validate_table_risks(self.tables)
        _validate_artifact_refs(self.annotation_refs, "annotation_refs")
        _require_string_tuple(self.diagnostics, "diagnostics")

    def to_document(self) -> dict[str, object]:
        return {
            "annotation_refs": [artifact_ref_to_dict(item) for item in self.annotation_refs],
            "diagnostics": list(self.diagnostics),
            "overall": self.overall.to_document(),
            "risk_evaluation_digest": self.risk_evaluation_digest.value,
            "risk_report_contract_version": self.risk_report_contract_version,
            "tables": [item.to_document() for item in self.tables],
        }


@dataclass(frozen=True, slots=True)
class RiskEvaluationResult:
    """Terminal flow-neutral result of one bounded risk evaluation."""

    status: RiskEvaluationStatus
    risk_evaluation: RiskEvaluation | None = None
    risk_report: RiskReport | None = None
    annotation_artifacts: tuple[RiskAnnotationArtifact, ...] = ()
    risk_closure: RiskAnnotationClosure | None = None
    cache_diagnostics: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.status) is not RiskEvaluationStatus:
            raise ValueError("status must be RiskEvaluationStatus")
        if type(self.annotation_artifacts) is not tuple or any(
            type(item) is not RiskAnnotationArtifact for item in self.annotation_artifacts
        ):
            raise ValueError("annotation_artifacts must contain RiskAnnotationArtifact")
        artifact_names = tuple(item.table_name for item in self.annotation_artifacts)
        if artifact_names != tuple(sorted(artifact_names)) or len(set(artifact_names)) != len(artifact_names):
            raise ValueError("annotation_artifacts must use canonical unique table order")
        _require_string_tuple(self.cache_diagnostics, "cache_diagnostics")
        _require_string_tuple(self.diagnostics, "diagnostics")
        if self.status in {RiskEvaluationStatus.FAILED, RiskEvaluationStatus.CANCELLED}:
            if any(
                value is not None
                for value in (self.risk_evaluation, self.risk_report, self.risk_closure)
            ) or self.annotation_artifacts:
                raise ValueError("failed/cancelled result must not expose risk outputs")
        elif self.risk_evaluation is None or self.risk_report is None:
            raise ValueError("ready/degraded result requires risk evaluation and report")
        if self.risk_evaluation is not None and self.risk_report is not None:
            if self.risk_report.risk_evaluation_digest != self.risk_evaluation.risk_evaluation_digest:
                raise ValueError("risk report must bind to risk evaluation digest")
        if self.risk_closure is not None:
            if self.risk_evaluation is None:
                raise ValueError("risk closure requires risk evaluation")
            if self.risk_closure.risk_evaluation_digest != self.risk_evaluation.risk_evaluation_digest:
                raise ValueError("risk closure must bind to risk evaluation digest")

    def to_document(self) -> dict[str, object]:
        return {
            "annotation_artifacts": [item.to_document() for item in self.annotation_artifacts],
            "cache_diagnostics": list(self.cache_diagnostics),
            "diagnostics": list(self.diagnostics),
            "risk_closure": None if self.risk_closure is None else self.risk_closure.to_document(),
            "risk_evaluation": None if self.risk_evaluation is None else self.risk_evaluation.to_document(),
            "risk_report": None if self.risk_report is None else self.risk_report.to_document(),
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class RiskEvaluationInput:
    comparison_facts: ComparisonFacts
    risk_ruleset: RiskRulesetSnapshot
    risk_contract_version: str = RISK_CONTRACT_VERSION
    risk_model_version: str = RISK_MODEL_VERSION
    records_access: RiskRecordsAccess | None = None
    requested_tables: tuple[str, ...] | None = None
    risk_options: RiskOptions = RiskOptions()
    artifact_policy: RiskArtifactPolicy = RiskArtifactPolicy()
    cache_policy: RiskCachePolicy | None = None

    def __post_init__(self) -> None:
        if type(self.comparison_facts) is not ComparisonFacts:
            raise ValueError("comparison_facts must be ComparisonFacts")
        if type(self.risk_ruleset) is not RiskRulesetSnapshot:
            raise ValueError("risk_ruleset must be RiskRulesetSnapshot")
        if self.risk_contract_version != RISK_CONTRACT_VERSION:
            raise ValueError("unsupported risk contract version")
        if self.risk_model_version != self.risk_ruleset.risk_model_version:
            raise ValueError("risk_model_version must match risk ruleset")
        if self.records_access is not None and not isinstance(self.records_access, RiskRecordsAccess):
            raise ValueError("records_access must implement RiskRecordsAccess")
        if self.requested_tables is not None:
            object.__setattr__(self, "requested_tables", _canonical_names(self.requested_tables, "requested_tables"))
        if type(self.risk_options) is not RiskOptions:
            raise ValueError("risk_options must be RiskOptions")
        if type(self.artifact_policy) is not RiskArtifactPolicy:
            raise ValueError("artifact_policy must be RiskArtifactPolicy")
        if self.cache_policy is not None and type(self.cache_policy) is not RiskCachePolicy:
            raise ValueError("cache_policy must be RiskCachePolicy or None")

    def to_document(self) -> dict[str, object]:
        return {
            "artifact_policy": self.artifact_policy.to_document(),
            "comparison_facts_digest": self.comparison_facts.comparison_digest.value,
            "risk_contract_version": self.risk_contract_version,
            "risk_model_version": self.risk_model_version,
            "risk_options": self.risk_options.to_document(),
            "risk_ruleset_digest": _optional_digest(self.risk_ruleset.risk_ruleset_digest),
            "requested_tables": None if self.requested_tables is None else list(self.requested_tables),
        }


def risk_table_digest_payload(
    table_risk: RiskTableRisk,
    annotation_manifest_digests: Sequence[DigestRef] = (),
) -> dict[str, object]:
    if type(table_risk) is not RiskTableRisk:
        raise ValueError("table_risk must be RiskTableRisk")
    _validate_digest_sequence(annotation_manifest_digests, "annotation_manifest_digests")
    return {
        "annotation_manifest_digests": sorted(item.value for item in annotation_manifest_digests),
        "annotation_count": table_risk.annotation_count,
        "kind": "risk-table",
        "reason_codes": [item.value for item in table_risk.reason_codes],
        "risk_level": table_risk.risk_level.value,
        "source_table_status": table_risk.source_table_status.value,
        "table_name": table_risk.table_name,
    }


def compute_risk_table_digest(
    table_risk: RiskTableRisk,
    annotation_manifest_digests: Sequence[DigestRef] = (),
) -> DigestRef:
    return raw_blob_digest(canonicalize_json_value(risk_table_digest_payload(table_risk, annotation_manifest_digests)))


def risk_evaluation_digest_payload(
    *,
    comparison_digest: DigestRef,
    risk_contract_version: str,
    risk_model_version: str,
    risk_ruleset_digest: DigestRef,
    risk_options: RiskOptions,
    table_risks: Sequence[RiskTableRisk],
    annotation_manifest_digests: Sequence[DigestRef] = (),
) -> dict[str, object]:
    if type(comparison_digest) is not DigestRef:
        raise ValueError("comparison_digest must be DigestRef")
    if risk_contract_version != RISK_CONTRACT_VERSION:
        raise ValueError("unsupported risk contract version")
    _require_non_empty_string(risk_model_version, "risk_model_version")
    if type(risk_ruleset_digest) is not DigestRef:
        raise ValueError("risk_ruleset_digest must be DigestRef")
    if type(risk_options) is not RiskOptions:
        raise ValueError("risk_options must be RiskOptions")
    _validate_digest_sequence(annotation_manifest_digests, "annotation_manifest_digests")
    table_risks_tuple = tuple(table_risks)
    _validate_table_risks(table_risks_tuple)
    table_payloads = [
        risk_table_digest_payload(table_risk)
        for table_risk in sorted(table_risks_tuple, key=lambda item: item.table_name)
    ]
    return {
        "annotation_manifest_digests": sorted(item.value for item in annotation_manifest_digests),
        "comparison_digest": comparison_digest.value,
        "kind": "risk-evaluation",
        "risk_contract_version": risk_contract_version,
        "risk_model_version": risk_model_version,
        "risk_options": risk_options.to_document(),
        "risk_ruleset_digest": risk_ruleset_digest.value,
        "table_risk_digests": [
            raw_blob_digest(canonicalize_json_value(payload)).value for payload in table_payloads
        ],
    }


def compute_risk_evaluation_digest(
    *,
    comparison_digest: DigestRef,
    risk_contract_version: str,
    risk_model_version: str,
    risk_ruleset_digest: DigestRef,
    risk_options: RiskOptions,
    table_risks: Sequence[RiskTableRisk],
    annotation_manifest_digests: Sequence[DigestRef] = (),
) -> DigestRef:
    return raw_blob_digest(
        canonicalize_json_value(
            risk_evaluation_digest_payload(
                comparison_digest=comparison_digest,
                risk_contract_version=risk_contract_version,
                risk_model_version=risk_model_version,
                risk_ruleset_digest=risk_ruleset_digest,
                risk_options=risk_options,
                table_risks=table_risks,
                annotation_manifest_digests=annotation_manifest_digests,
            )
        )
    )


def risk_report_digest_payload(report: RiskReport) -> dict[str, object]:
    """Return the ref/diagnostic-free semantic payload for a risk report."""

    if type(report) is not RiskReport:
        raise ValueError("report must be RiskReport")
    table_payloads = [
        risk_table_digest_payload(item)
        for item in sorted(report.tables, key=lambda item: item.table_name)
    ]
    return {
        "kind": "risk-report",
        "overall": report.overall.to_document(),
        "risk_evaluation_digest": report.risk_evaluation_digest.value,
        "risk_report_contract_version": report.risk_report_contract_version,
        "table_risk_digests": [
            raw_blob_digest(canonicalize_json_value(payload)).value for payload in table_payloads
        ],
    }


def compute_risk_report_digest(report: RiskReport) -> DigestRef:
    return raw_blob_digest(canonicalize_json_value(risk_report_digest_payload(report)))


def _schema_changes_document(changes: ComparisonSchemaChanges) -> dict[str, object]:
    return {
        "before_only_columns": list(changes.before_only_columns),
        "current_only_columns": list(changes.current_only_columns),
        "effective_compare_key_before": list(changes.effective_compare_key_before),
        "effective_compare_key_changed": changes.effective_compare_key_changed,
        "effective_compare_key_current": list(changes.effective_compare_key_current),
        "incompatible_columns": list(changes.incompatible_columns),
        "selected_columns": list(changes.selected_columns),
    }


def _pairs_document(pairs: RiskOptionsPairs) -> list[list[RiskOptionValue]]:
    return [[key, value] for key, value in pairs]


def _pairs_from_document(value: object, label: str) -> RiskOptionsPairs:
    if type(value) is not list:
        raise ValueError(f"{label} must be a list")
    pairs: list[tuple[str, RiskOptionValue]] = []
    for item in value:
        if type(item) is not list or len(item) != 2:
            raise ValueError(f"{label} must contain two-item lists")
        pairs.append(
            (
                _require_string(item[0], f"{label}.key"),
                _require_option_value(item[1], f"{label}.value"),
            )
        )
    result = tuple(pairs)
    _validate_option_pairs(result, label)
    return result


def _require_canonical_name(value: object, label: str) -> str:
    result = _require_non_empty_string(value, label)
    if canonicalize_identifier(result) != result:
        raise ValueError(f"{label} must be canonical")
    return result


def _canonical_names(value: tuple[str, ...], label: str) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise ValueError(f"{label} must be a tuple")
    names = tuple(_require_canonical_name(item, label) for item in value)
    if names != tuple(sorted(names)):
        raise ValueError(f"{label} must use canonical order")
    if len(set(names)) != len(names):
        raise ValueError(f"{label} must not repeat names")
    return names


def _canonical_columns(value: tuple[str, ...], label: str) -> tuple[str, ...]:
    return _canonical_names(value, label)


def _require_string_tuple(value: tuple[str, ...], label: str) -> None:
    if type(value) is not tuple or any(type(item) is not str or item == "" for item in value):
        raise ValueError(f"{label} must contain non-empty strings")


def _require_reason_codes(
    value: tuple[RiskReasonCode, ...], label: str, *, require_one: bool = False
) -> None:
    if type(value) is not tuple:
        raise ValueError(f"{label} must be a tuple")
    if require_one and not value:
        raise ValueError(f"{label} must be a non-empty tuple")
    values: list[str] = []
    for item in value:
        if type(item) is not RiskReasonCode:
            raise ValueError(f"{label} must contain RiskReasonCode")
        values.append(item.value)
    if values != sorted(values) or len(set(values)) != len(values):
        raise ValueError(f"{label} must use canonical unique order")


def _validate_table_risks(value: tuple[RiskTableRisk, ...]) -> None:
    if type(value) is not tuple or any(type(item) is not RiskTableRisk for item in value):
        raise ValueError("table risks must contain RiskTableRisk")
    names = tuple(item.table_name for item in value)
    if names != tuple(sorted(names)) or len(set(names)) != len(names):
        raise ValueError("table risks must use canonical unique table order")


def _validate_artifact_refs(value: tuple[ArtifactRef, ...], label: str) -> None:
    if type(value) is not tuple or any(type(item) is not ArtifactRef for item in value):
        raise ValueError(f"{label} must contain ArtifactRef")


def _validate_digest_sequence(value: Sequence[DigestRef], label: str) -> None:
    if any(type(item) is not DigestRef for item in value):
        raise ValueError(f"{label} must contain DigestRef")


def _optional_digest(value: DigestRef | None) -> str | None:
    return None if value is None else value.value


def _reject_unknown_keys(payload: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {', '.join(sorted(unknown))}")


def _default_rule(
    rule_id: RiskRuleId,
    target_scope: RiskScope,
    reason_code: RiskReasonCode,
    level: RiskLevel,
) -> RiskRuleSpec:
    return RiskRuleSpec(
        rule_id=rule_id,
        rule_version=RISK_RULE_VERSION,
        target_scope=target_scope,
        reason_code=reason_code,
        severity_policy=RiskSeverityPolicy(default_level=level),
    )


V1_RISK_RULE_SPECS: tuple[RiskRuleSpec, ...] = tuple(
    sorted(
        (
            _default_rule(
                RiskRuleId.PROJECT_IDENTITY_MISMATCH,
                RiskScope.PAIR,
                RiskReasonCode.PROJECT_IDENTITY_MISMATCH,
                RiskLevel.HIGH,
            ),
            _default_rule(RiskRuleId.TABLE_ADDED, RiskScope.TABLE, RiskReasonCode.TABLE_ADDED, RiskLevel.MEDIUM_LOW),
            _default_rule(RiskRuleId.TABLE_DELETED, RiskScope.TABLE, RiskReasonCode.TABLE_DELETED, RiskLevel.MEDIUM_HIGH),
            _default_rule(RiskRuleId.SCHEMA_CHANGED, RiskScope.TABLE, RiskReasonCode.SCHEMA_CHANGED, RiskLevel.MEDIUM_HIGH),
            _default_rule(RiskRuleId.ROW_ADDED, RiskScope.STANDARD_ROWS, RiskReasonCode.ROW_ADDED, RiskLevel.MEDIUM_LOW),
            _default_rule(RiskRuleId.ROW_DELETED, RiskScope.STANDARD_ROWS, RiskReasonCode.ROW_DELETED, RiskLevel.MEDIUM_LOW),
            _default_rule(RiskRuleId.ROW_MODIFIED, RiskScope.STANDARD_ROWS, RiskReasonCode.ROW_MODIFIED, RiskLevel.MEDIUM_HIGH),
            _default_rule(RiskRuleId.KEY_DEGRADED, RiskScope.DEGRADED_TABLE, RiskReasonCode.KEY_DEGRADED, RiskLevel.UNKNOWN),
            _default_rule(
                RiskRuleId.ORDERED_DIFF_UNSUPPORTED,
                RiskScope.DEGRADED_TABLE,
                RiskReasonCode.ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED,
                RiskLevel.UNKNOWN,
            ),
            _default_rule(RiskRuleId.COMPARISON_FAILED, RiskScope.TABLE, RiskReasonCode.COMPARISON_FAILED, RiskLevel.HIGH),
            _default_rule(
                RiskRuleId.COMPOSITE_SIGNAL_POINT,
                RiskScope.TABLE,
                RiskReasonCode.COMPOSITE_SIGNAL_CHANGE_REVIEW_REQUIRED,
                RiskLevel.UNKNOWN,
            ),
            _default_rule(
                RiskRuleId.UNKNOWN_CHANGE_TARGET,
                RiskScope.TABLE,
                RiskReasonCode.UNKNOWN_CHANGE_TARGET,
                RiskLevel.UNKNOWN,
            ),
        ),
        key=lambda item: item.rule_id.value,
    )
)
