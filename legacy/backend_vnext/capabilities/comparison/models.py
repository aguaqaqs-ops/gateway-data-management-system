from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from ...artifacts.manifest import ArtifactRef
from ...artifacts.records import RecordsArtifact
from ...contracts.versions import SCALAR_ENCODING_VERSION
from ...core.diagnostics import DiagnosticRecord
from ...core.digests import DigestRef
from ...core.identifiers import canonical_identifier
from ..snapshot_materialization.models import (
    Snapshot,
    SnapshotSourceContext,
    SnapshotSummary,
    SnapshotTableSet,
)
from ...repository_server.ref_session import RepositoryTableAccessProvider
from .digest import build_projection_schema_digest


COMPARISON_CONTRACT_VERSION = "backend-vnext/comparison/v1"
COMPARISON_PROJECTION_CONTRACT_VERSION = "backend-vnext/comparison-projection/v1"
COMPARISON_RULESET_CONTRACT_VERSION = "backend-vnext/comparison-ruleset/v1"
COMPARISON_RECORDS_CLOSURE_CONTRACT_VERSION = "backend-vnext/comparison-records-closure/v1"
COMPARISON_DEFAULT_DIRECTION = "BEFORE_TO_CURRENT"
ORDERED_DIFF_CONTRACT_VERSION = "backend-vnext/ordered-diff/v2"


def _mapping_payload(payload: Mapping[str, object] | None) -> dict[str, object] | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise TypeError("mapping payload must be a mapping or None")
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("mapping keys must be strings")
        normalized[key] = value
    return normalized


class ComparisonRole(StrEnum):
    BEFORE = "BEFORE"
    CURRENT = "CURRENT"


class ComparisonTableAccessPolicy(StrEnum):
    SUMMARY_ONLY = "SUMMARY_ONLY"
    TABLE_READERS_ON_DEMAND = "TABLE_READERS_ON_DEMAND"
    TABLE_READERS_REQUIRED = "TABLE_READERS_REQUIRED"


class ComparisonRowDiffDetailPolicy(StrEnum):
    COUNTS_ONLY = "COUNTS_ONLY"
    CHANGED_COLUMNS = "CHANGED_COLUMNS"
    FULL_BEFORE_AFTER_VALUES = "FULL_BEFORE_AFTER_VALUES"


class ComparisonTableAliasScope(StrEnum):
    PROVISIONAL_FAST = "PROVISIONAL_FAST"
    CANONICAL = "CANONICAL"


class ComparisonStatus(StrEnum):
    UNCHANGED = "UNCHANGED"
    CHANGED = "CHANGED"
    BUSINESS_EQUIVALENT = "BUSINESS_EQUIVALENT"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class ComparisonTableStatus(StrEnum):
    UNCHANGED = "UNCHANGED"
    BUSINESS_EQUIVALENT = "BUSINESS_EQUIVALENT"
    ADDED_TABLE = "ADDED_TABLE"
    DELETED_TABLE = "DELETED_TABLE"
    MODIFIED = "MODIFIED"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    SCHEMA_ONLY_CHANGED = "SCHEMA_ONLY_CHANGED"
    DEGRADED = "DEGRADED"


class ComparisonRecordKind(StrEnum):
    ROW_ADDED = "ROW_ADDED"
    ROW_DELETED = "ROW_DELETED"
    ROW_MODIFIED = "ROW_MODIFIED"
    SCHEMA_CHANGE = "SCHEMA_CHANGE"
    TABLE_DEGRADED = "TABLE_DEGRADED"


@dataclass(frozen=True, slots=True)
class ComparisonOptions:
    include_unchanged_tables: bool = True
    row_diff_detail_policy: ComparisonRowDiffDetailPolicy | str = ComparisonRowDiffDetailPolicy.COUNTS_ONLY
    max_inline_record_count: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_diff_detail_policy", ComparisonRowDiffDetailPolicy(self.row_diff_detail_policy))
        if self.max_inline_record_count is not None and (
            not isinstance(self.max_inline_record_count, int)
            or isinstance(self.max_inline_record_count, bool)
            or self.max_inline_record_count < 0
        ):
            raise ValueError("max_inline_record_count must be a non-negative integer or None")


@dataclass(frozen=True, slots=True)
class TableRulesetTableRule:
    table_selector: str
    static_role: str = "STANDARD"
    compare_key_columns: tuple[str, ...] = field(default_factory=tuple)
    ignored_columns: tuple[str, ...] = field(default_factory=tuple)
    artifact_scope: str = "TABLE"
    row_diff_policy: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.table_selector, str) or not self.table_selector.strip():
            raise ValueError("table_selector must be a non-empty string")
        if not isinstance(self.static_role, str) or not self.static_role.strip():
            raise ValueError("static_role must be a non-empty string")
        if not isinstance(self.artifact_scope, str) or not self.artifact_scope.strip():
            raise ValueError("artifact_scope must be a non-empty string")
        if self.row_diff_policy is not None and (
            not isinstance(self.row_diff_policy, str) or not self.row_diff_policy.strip()
        ):
            raise ValueError("row_diff_policy must be a non-empty string or None")
        object.__setattr__(self, "compare_key_columns", tuple(canonical_identifier(column) for column in self.compare_key_columns))
        object.__setattr__(self, "ignored_columns", tuple(canonical_identifier(column) for column in self.ignored_columns))

    def to_payload(self) -> dict[str, object]:
        return {
            "table_selector": self.table_selector,
            "static_role": self.static_role,
            "compare_key_columns": list(self.compare_key_columns),
            "ignored_columns": list(self.ignored_columns),
            "artifact_scope": self.artifact_scope,
            "row_diff_policy": self.row_diff_policy,
        }


@dataclass(frozen=True, slots=True)
class TableRulesetSnapshot:
    ruleset_id: str
    ruleset_version: str
    fallback_key_policy: str = "DEGRADE_NO_COMPARE_KEY"
    projection_policy: str = "DEFAULT"
    table_rules: tuple[TableRulesetTableRule, ...] = field(default_factory=tuple)
    ruleset_contract_version: str = COMPARISON_RULESET_CONTRACT_VERSION
    ruleset_digest: DigestRef | str | None = None

    def __post_init__(self) -> None:
        for field_name in ("ruleset_id", "ruleset_version", "fallback_key_policy", "projection_policy", "ruleset_contract_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.table_rules, tuple):
            object.__setattr__(self, "table_rules", tuple(self.table_rules))
        normalized_rules: list[TableRulesetTableRule] = []
        for rule in self.table_rules:
            if not isinstance(rule, TableRulesetTableRule):
                raise TypeError("table_rules must contain TableRulesetTableRule values")
            normalized_rules.append(rule)
        object.__setattr__(self, "table_rules", tuple(normalized_rules))
        if self.ruleset_digest is None:
            object.__setattr__(self, "ruleset_digest", DigestRef.from_payload(self.payload_for_digest()))
        else:
            object.__setattr__(self, "ruleset_digest", DigestRef.parse(str(self.ruleset_digest)))

    def payload_for_digest(self) -> dict[str, object]:
        return {
            "ruleset_id": self.ruleset_id,
            "ruleset_version": self.ruleset_version,
            "fallback_key_policy": self.fallback_key_policy,
            "projection_policy": self.projection_policy,
            "ruleset_contract_version": self.ruleset_contract_version,
            "table_rules": [rule.to_payload() for rule in self.table_rules],
        }

    def to_payload(self) -> dict[str, object]:
        return {
            **self.payload_for_digest(),
            "ruleset_digest": self.ruleset_digest.to_payload() if self.ruleset_digest is not None else None,
        }


@dataclass(frozen=True, slots=True)
class RepositoryBackedComparisonContext:
    repository_id: str
    resolved_commit_hash: str
    repository_server_contract_version: str
    repository_ref: str | None = None
    dolt_version: str | None = None
    repository_table_access_provider: RepositoryTableAccessProvider | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for field_name in (
            "repository_id",
            "resolved_commit_hash",
            "repository_server_contract_version",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.repository_ref is not None and (
            not isinstance(self.repository_ref, str) or not self.repository_ref.strip()
        ):
            raise ValueError("repository_ref must be a non-empty string or None")
        if self.dolt_version is not None and (
            not isinstance(self.dolt_version, str) or not self.dolt_version.strip()
        ):
            raise ValueError("dolt_version must be a non-empty string or None")
        if self.repository_table_access_provider is not None and not isinstance(
            self.repository_table_access_provider,
            RepositoryTableAccessProvider,
        ):
            raise TypeError(
                "repository_table_access_provider must be a RepositoryTableAccessProvider or None"
            )
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))


@dataclass(frozen=True, slots=True)
class ComparisonInput:
    role: ComparisonRole | str
    snapshot: Snapshot
    summary: SnapshotSummary
    table_set_ref: SnapshotTableSet | None = None
    table_access_policy: ComparisonTableAccessPolicy | str = ComparisonTableAccessPolicy.TABLE_READERS_REQUIRED
    source_context: SnapshotSourceContext | None = None
    repository_backed_context: RepositoryBackedComparisonContext | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", ComparisonRole(self.role))
        object.__setattr__(self, "table_access_policy", ComparisonTableAccessPolicy(self.table_access_policy))
        if not isinstance(self.snapshot, Snapshot):
            raise TypeError("snapshot must be a Snapshot")
        if not isinstance(self.summary, SnapshotSummary):
            raise TypeError("summary must be a SnapshotSummary")
        if self.snapshot.snapshot_digest != self.summary.snapshot_digest:
            raise ValueError("snapshot and summary must describe the same digest")
        if self.table_set_ref is not None and not isinstance(self.table_set_ref, SnapshotTableSet):
            raise TypeError("table_set_ref must be a SnapshotTableSet or None")
        if self.source_context is not None and not isinstance(self.source_context, SnapshotSourceContext):
            raise TypeError("source_context must be a SnapshotSourceContext or None")
        if self.repository_backed_context is not None and not isinstance(
            self.repository_backed_context,
            RepositoryBackedComparisonContext,
        ):
            raise TypeError(
                "repository_backed_context must be a RepositoryBackedComparisonContext or None"
            )
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))


@dataclass(frozen=True, slots=True)
class ComparisonTableAlias:
    logical_table_name: str
    canonical_table_name: str
    alias_scope: ComparisonTableAliasScope | str
    pair_id: str | None = None
    input_role: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        logical = canonical_identifier(self.logical_table_name)
        canonical = canonical_identifier(self.canonical_table_name)
        if not logical:
            raise ValueError("logical_table_name must resolve to a non-empty identifier")
        if not canonical:
            raise ValueError("canonical_table_name must resolve to a non-empty identifier")
        if logical == canonical:
            raise ValueError("logical_table_name and canonical_table_name must differ")
        object.__setattr__(self, "logical_table_name", logical)
        object.__setattr__(self, "canonical_table_name", canonical)
        object.__setattr__(self, "alias_scope", ComparisonTableAliasScope(self.alias_scope))
        for field_name in ("pair_id", "input_role", "reason"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-empty string or None")
            if isinstance(value, str):
                object.__setattr__(self, field_name, value.strip())

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "ComparisonTableAlias":
        if not isinstance(payload, Mapping):
            raise TypeError("table alias payload must be a mapping")
        return cls(
            logical_table_name=str(payload.get("logical_table_name") or ""),
            canonical_table_name=str(payload.get("canonical_table_name") or ""),
            alias_scope=str(payload.get("alias_scope") or ""),
            pair_id=_optional_text(payload.get("pair_id")),
            input_role=_optional_text(payload.get("input_role")),
            reason=_optional_text(payload.get("reason")),
        )

    def payload_for_digest(self) -> dict[str, object]:
        return {
            "logical_table_name": self.logical_table_name,
            "canonical_table_name": self.canonical_table_name,
            "alias_scope": self.alias_scope.value,
        }

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        if self.pair_id is not None:
            payload["pair_id"] = self.pair_id
        if self.input_role is not None:
            payload["input_role"] = self.input_role
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("optional text must be a non-empty string or None")
    return value.strip()


@dataclass(frozen=True, slots=True)
class DirectedComparisonInput:
    before: ComparisonInput
    current: ComparisonInput
    comparison_contract_version: str = COMPARISON_CONTRACT_VERSION
    projection_contract_version: str = COMPARISON_PROJECTION_CONTRACT_VERSION
    table_ruleset: TableRulesetSnapshot | None = None
    table_ruleset_version: str | None = None
    scalar_encoding_version: str | None = SCALAR_ENCODING_VERSION
    requested_tables: tuple[str, ...] = field(default_factory=tuple)
    comparison_options: ComparisonOptions = field(default_factory=ComparisonOptions)
    cache_policy: str = "DISABLED"
    cache_lookup_policy: str = "DISABLED"
    validation_status_policy: str = "STRICT"
    artifact_policy: str = "DEFAULT"
    runtime_policy: Mapping[str, object] | None = None
    table_aliases: tuple[ComparisonTableAlias | Mapping[str, object], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for field_name in ("comparison_contract_version", "projection_contract_version", "cache_policy", "cache_lookup_policy", "validation_status_policy", "artifact_policy"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.before, ComparisonInput):
            raise TypeError("before must be a ComparisonInput")
        if not isinstance(self.current, ComparisonInput):
            raise TypeError("current must be a ComparisonInput")
        if self.table_ruleset is not None and not isinstance(self.table_ruleset, TableRulesetSnapshot):
            raise TypeError("table_ruleset must be a TableRulesetSnapshot or None")
        if self.table_ruleset_version is None and self.table_ruleset is not None:
            object.__setattr__(self, "table_ruleset_version", self.table_ruleset.ruleset_version)
        if self.table_ruleset_version is not None and (
            not isinstance(self.table_ruleset_version, str) or not self.table_ruleset_version.strip()
        ):
            raise ValueError("table_ruleset_version must be a non-empty string or None")
        if self.scalar_encoding_version is None:
            object.__setattr__(self, "scalar_encoding_version", SCALAR_ENCODING_VERSION)
        elif not isinstance(self.scalar_encoding_version, str) or not self.scalar_encoding_version.strip():
            raise ValueError("scalar_encoding_version must be a non-empty string or None")
        if not isinstance(self.requested_tables, tuple):
            object.__setattr__(self, "requested_tables", tuple(self.requested_tables))
        object.__setattr__(self, "requested_tables", tuple(canonical_identifier(table_name) for table_name in self.requested_tables if canonical_identifier(table_name)))
        if self.runtime_policy is not None and not isinstance(self.runtime_policy, Mapping):
            raise TypeError("runtime_policy must be a mapping or None")
        if not isinstance(self.table_aliases, tuple):
            object.__setattr__(self, "table_aliases", tuple(self.table_aliases))
        normalized_by_key: dict[tuple[str, str], ComparisonTableAlias] = {}
        for alias in self.table_aliases:
            if isinstance(alias, ComparisonTableAlias):
                normalized = alias
            elif isinstance(alias, Mapping):
                normalized = ComparisonTableAlias.from_payload(alias)
            else:
                raise TypeError("table_aliases must contain ComparisonTableAlias or mapping values")
            key = (normalized.alias_scope.value, normalized.logical_table_name)
            existing = normalized_by_key.get(key)
            if existing is not None:
                if existing.canonical_table_name != normalized.canonical_table_name:
                    raise ValueError("conflicting table alias for scope/logical table")
                continue
            normalized_by_key[key] = normalized
        object.__setattr__(
            self,
            "table_aliases",
            tuple(
                sorted(
                    normalized_by_key.values(),
                    key=lambda item: (
                        item.alias_scope.value,
                        item.logical_table_name,
                        item.canonical_table_name,
                    ),
                )
            ),
        )


ComparisonPlannerInput = DirectedComparisonInput
ComparisonComputeInput = DirectedComparisonInput


@dataclass(frozen=True, slots=True)
class ProjectionSchema:
    table_name: str
    selected_columns: tuple[str, ...]
    ignored_columns: tuple[str, ...] = field(default_factory=tuple)
    before_only_columns: tuple[str, ...] = field(default_factory=tuple)
    current_only_columns: tuple[str, ...] = field(default_factory=tuple)
    effective_compare_key: tuple[str, ...] = field(default_factory=tuple)
    projection_schema_digest: DigestRef | str | None = None
    table_ruleset_version: str = ""
    projection_contract_version: str = COMPARISON_PROJECTION_CONTRACT_VERSION
    scalar_encoding_version: str = SCALAR_ENCODING_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name.strip():
            raise ValueError("table_name must be a non-empty string")
        if not isinstance(self.selected_columns, tuple):
            object.__setattr__(self, "selected_columns", tuple(self.selected_columns))
        if not isinstance(self.ignored_columns, tuple):
            object.__setattr__(self, "ignored_columns", tuple(self.ignored_columns))
        if not isinstance(self.before_only_columns, tuple):
            object.__setattr__(self, "before_only_columns", tuple(self.before_only_columns))
        if not isinstance(self.current_only_columns, tuple):
            object.__setattr__(self, "current_only_columns", tuple(self.current_only_columns))
        if not isinstance(self.effective_compare_key, tuple):
            object.__setattr__(self, "effective_compare_key", tuple(self.effective_compare_key))
        if not isinstance(self.table_ruleset_version, str) or not self.table_ruleset_version.strip():
            raise ValueError("table_ruleset_version must be a non-empty string")
        if not isinstance(self.projection_contract_version, str) or not self.projection_contract_version.strip():
            raise ValueError("projection_contract_version must be a non-empty string")
        if not isinstance(self.scalar_encoding_version, str) or not self.scalar_encoding_version.strip():
            raise ValueError("scalar_encoding_version must be a non-empty string")
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        if not self.table_name:
            raise ValueError("table_name must resolve to a non-empty identifier")
        object.__setattr__(
            self,
            "selected_columns",
            _normalize_identifier_tuple(self.selected_columns, field_name="selected_columns"),
        )
        object.__setattr__(
            self,
            "ignored_columns",
            _normalize_identifier_tuple(self.ignored_columns, field_name="ignored_columns"),
        )
        object.__setattr__(
            self,
            "before_only_columns",
            _normalize_identifier_tuple(self.before_only_columns, field_name="before_only_columns"),
        )
        object.__setattr__(
            self,
            "current_only_columns",
            _normalize_identifier_tuple(self.current_only_columns, field_name="current_only_columns"),
        )
        object.__setattr__(
            self,
            "effective_compare_key",
            _normalize_identifier_tuple(self.effective_compare_key, field_name="effective_compare_key"),
        )
        if self.projection_schema_digest is not None:
            object.__setattr__(self, "projection_schema_digest", DigestRef.parse(str(self.projection_schema_digest)))
        else:
            object.__setattr__(
                self,
                "projection_schema_digest",
                build_projection_schema_digest(
                    table_name=self.table_name,
                    selected_columns=self.selected_columns,
                    ignored_columns=self.ignored_columns,
                    effective_compare_key=self.effective_compare_key,
                    table_ruleset_version=self.table_ruleset_version,
                    projection_contract_version=self.projection_contract_version,
                    scalar_encoding_version=self.scalar_encoding_version,
                ),
            )

    def payload_for_digest(self) -> dict[str, object]:
        return {
            "table_name": self.table_name,
            "selected_columns": sorted(self.selected_columns),
            "ignored_columns": sorted(self.ignored_columns),
            "effective_compare_key": sorted(self.effective_compare_key),
            "table_ruleset_version": self.table_ruleset_version,
            "projection_contract_version": self.projection_contract_version,
            "scalar_encoding_version": self.scalar_encoding_version,
        }


@dataclass(frozen=True, slots=True)
class ProjectionTable:
    source_snapshot_digest: DigestRef | str
    source_table_name: str
    projection_schema: ProjectionSchema
    row_count: int
    source_raw_content_digest: DigestRef | str | None = None
    projection_logical_digest: DigestRef | str | None = None
    reader: object | None = None
    artifact_ref: object | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.source_table_name, str) or not self.source_table_name.strip():
            raise ValueError("source_table_name must be a non-empty string")
        if not isinstance(self.projection_schema, ProjectionSchema):
            raise TypeError("projection_schema must be a ProjectionSchema")
        if not isinstance(self.row_count, int) or isinstance(self.row_count, bool) or self.row_count < 0:
            raise ValueError("row_count must be a non-negative integer")
        object.__setattr__(self, "source_table_name", canonical_identifier(self.source_table_name))
        if not self.source_table_name:
            raise ValueError("source_table_name must resolve to a non-empty identifier")
        object.__setattr__(self, "source_snapshot_digest", DigestRef.parse(str(self.source_snapshot_digest)))
        if self.source_raw_content_digest is not None:
            object.__setattr__(self, "source_raw_content_digest", DigestRef.parse(str(self.source_raw_content_digest)))
        if self.projection_logical_digest is not None:
            object.__setattr__(self, "projection_logical_digest", DigestRef.parse(str(self.projection_logical_digest)))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))


@dataclass(frozen=True, slots=True)
class ComparisonSummary:
    status: ComparisonStatus | str
    table_count: int
    unchanged_table_count: int = 0
    changed_table_count: int = 0
    added_table_count: int = 0
    deleted_table_count: int = 0
    schema_changed_table_count: int = 0
    degraded_table_count: int = 0
    row_added_count: int | None = None
    row_deleted_count: int | None = None
    row_modified_count: int | None = None
    diagnostics_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ComparisonStatus(self.status))
        for field_name in (
            "table_count",
            "unchanged_table_count",
            "changed_table_count",
            "added_table_count",
            "deleted_table_count",
            "schema_changed_table_count",
            "degraded_table_count",
            "diagnostics_count",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        for field_name in ("row_added_count", "row_deleted_count", "row_modified_count"):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer or None")


@dataclass(frozen=True, slots=True)
class ComparisonOrderedExtension:
    ordered_diff_contract_version: str = ORDERED_DIFF_CONTRACT_VERSION
    ordered_policy_digest: DigestRef | str | None = None
    before_ordered_digest: DigestRef | str | None = None
    current_ordered_digest: DigestRef | str | None = None
    stable_key_field: str | None = None
    position_field: str | None = None
    ordered_summary: Mapping[str, object] | None = None
    ordered_records_ref: ArtifactRef | None = None
    ordered_records_manifest_digest: DigestRef | str | None = None
    replay_guarantee: str | None = None
    table_processing_mode: str | None = None
    ordered_preprocess_applied: str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.ordered_diff_contract_version, str) or not self.ordered_diff_contract_version.strip():
            raise ValueError("ordered_diff_contract_version must be a non-empty string")
        for field_name in (
            "ordered_policy_digest",
            "before_ordered_digest",
            "current_ordered_digest",
            "ordered_records_manifest_digest",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, DigestRef.parse(str(value)))
        if self.ordered_summary is not None:
            object.__setattr__(self, "ordered_summary", _mapping_payload(self.ordered_summary))
        if self.ordered_records_ref is not None:
            if not isinstance(self.ordered_records_ref, ArtifactRef):
                raise TypeError("ordered_records_ref must be an ArtifactRef or None")
            ref_manifest_digest = self.ordered_records_ref.manifest_digest
            if self.ordered_records_manifest_digest is None:
                object.__setattr__(self, "ordered_records_manifest_digest", ref_manifest_digest)
            elif DigestRef.parse(str(self.ordered_records_manifest_digest)) != ref_manifest_digest:
                raise ValueError("ordered_records_manifest_digest must match ordered_records_ref.manifest_digest")
        for field_name in (
            "stable_key_field",
            "position_field",
            "replay_guarantee",
            "table_processing_mode",
            "ordered_preprocess_applied",
        ):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))

    def payload_for_digest(self) -> dict[str, object]:
        payload = {
            "ordered_diff_contract_version": self.ordered_diff_contract_version,
        }
        if self.ordered_policy_digest is not None:
            payload["ordered_policy_digest"] = self.ordered_policy_digest.to_payload()
        if self.before_ordered_digest is not None:
            payload["before_ordered_digest"] = self.before_ordered_digest.to_payload()
        if self.current_ordered_digest is not None:
            payload["current_ordered_digest"] = self.current_ordered_digest.to_payload()
        if self.stable_key_field is not None:
            payload["stable_key_field"] = self.stable_key_field
        if self.position_field is not None:
            payload["position_field"] = self.position_field
        if self.ordered_summary is not None:
            payload["ordered_summary"] = _mapping_payload(self.ordered_summary)
        if self.ordered_records_manifest_digest is not None:
            payload["ordered_records_manifest_digest"] = self.ordered_records_manifest_digest.to_payload()
        if self.replay_guarantee is not None:
            payload["replay_guarantee"] = self.replay_guarantee
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
            payload["ordered_records_ref"] = self.ordered_records_ref.to_payload()
        return payload


@dataclass(frozen=True, slots=True)
class ComparisonTableFact:
    table_name: str
    status: ComparisonTableStatus | str
    before_descriptor: Mapping[str, object] | None = None
    current_descriptor: Mapping[str, object] | None = None
    projection_schema: ProjectionSchema | None = None
    projection_schema_digest: DigestRef | str | None = None
    before_projection_logical_digest: DigestRef | str | None = None
    current_projection_logical_digest: DigestRef | str | None = None
    row_counts: tuple[int | None, int | None] | None = None
    row_change_stats: Mapping[str, object] | None = None
    schema_changes: Mapping[str, object] | None = None
    records_ref: object | None = None
    ordered_extension: ComparisonOrderedExtension | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name.strip():
            raise ValueError("table_name must be a non-empty string")
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        object.__setattr__(self, "status", ComparisonTableStatus(self.status))
        if self.projection_schema is not None and not isinstance(self.projection_schema, ProjectionSchema):
            raise TypeError("projection_schema must be a ProjectionSchema or None")
        if self.row_counts is not None and (
            not isinstance(self.row_counts, tuple) or len(self.row_counts) != 2
        ):
            raise ValueError("row_counts must be a pair of before/current counts or None")
        if self.row_change_stats is not None:
            object.__setattr__(self, "row_change_stats", _mapping_payload(self.row_change_stats))
        if self.projection_schema_digest is not None:
            object.__setattr__(self, "projection_schema_digest", DigestRef.parse(str(self.projection_schema_digest)))
        if self.before_projection_logical_digest is not None:
            object.__setattr__(self, "before_projection_logical_digest", DigestRef.parse(str(self.before_projection_logical_digest)))
        if self.current_projection_logical_digest is not None:
            object.__setattr__(self, "current_projection_logical_digest", DigestRef.parse(str(self.current_projection_logical_digest)))
        if self.ordered_extension is not None and not isinstance(self.ordered_extension, ComparisonOrderedExtension):
            raise TypeError("ordered_extension must be a ComparisonOrderedExtension or None")
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))


@dataclass(frozen=True, slots=True)
class ComparisonFacts:
    comparison_digest: DigestRef | str
    comparison_contract_version: str
    projection_contract_version: str
    table_ruleset_version: str
    before_snapshot_digest: DigestRef | str
    current_snapshot_digest: DigestRef | str
    direction: str = COMPARISON_DEFAULT_DIRECTION
    summary: ComparisonSummary | None = None
    tables: tuple[ComparisonTableFact, ...] = field(default_factory=tuple)
    records_ref: ComparisonRecordsClosure | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "comparison_digest", DigestRef.parse(str(self.comparison_digest)))
        object.__setattr__(self, "before_snapshot_digest", DigestRef.parse(str(self.before_snapshot_digest)))
        object.__setattr__(self, "current_snapshot_digest", DigestRef.parse(str(self.current_snapshot_digest)))
        for field_name in ("comparison_contract_version", "projection_contract_version", "table_ruleset_version", "direction"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.summary is not None and not isinstance(self.summary, ComparisonSummary):
            raise TypeError("summary must be a ComparisonSummary or None")
        if not isinstance(self.tables, tuple):
            object.__setattr__(self, "tables", tuple(self.tables))
        normalized_tables: list[ComparisonTableFact] = []
        for table in self.tables:
            if not isinstance(table, ComparisonTableFact):
                raise TypeError("tables must contain ComparisonTableFact values")
            normalized_tables.append(table)
        object.__setattr__(self, "tables", tuple(normalized_tables))
        if self.records_ref is not None and not isinstance(self.records_ref, ComparisonRecordsClosure):
            raise TypeError("records_ref must be a ComparisonRecordsClosure or None")
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))


@dataclass(frozen=True, slots=True)
class ComparisonRecordsClosureMember:
    table_name: str
    records_ref: object
    records_manifest_digest: DigestRef | str
    records_content_digest: DigestRef | str
    record_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name.strip():
            raise ValueError("table_name must be a non-empty string")
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        if not isinstance(self.record_count, int) or isinstance(self.record_count, bool) or self.record_count < 0:
            raise ValueError("record_count must be a non-negative integer")
        object.__setattr__(self, "records_manifest_digest", DigestRef.parse(str(self.records_manifest_digest)))
        object.__setattr__(self, "records_content_digest", DigestRef.parse(str(self.records_content_digest)))


@dataclass(frozen=True, slots=True)
class ComparisonRecordsClosure:
    closure_contract_version: str
    comparison_digest: DigestRef | str
    facts_core_digest: DigestRef | str
    records: tuple[ComparisonRecordsClosureMember, ...] = field(default_factory=tuple)
    closure_manifest_digest: DigestRef | str | None = None

    def __post_init__(self) -> None:
        for field_name in ("closure_contract_version",):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        object.__setattr__(self, "comparison_digest", DigestRef.parse(str(self.comparison_digest)))
        object.__setattr__(self, "facts_core_digest", DigestRef.parse(str(self.facts_core_digest)))
        if not isinstance(self.records, tuple):
            object.__setattr__(self, "records", tuple(self.records))
        normalized_records: list[ComparisonRecordsClosureMember] = []
        for record in self.records:
            if not isinstance(record, ComparisonRecordsClosureMember):
                raise TypeError("records must contain ComparisonRecordsClosureMember values")
            normalized_records.append(record)
        object.__setattr__(self, "records", tuple(normalized_records))
        if self.closure_manifest_digest is not None:
            object.__setattr__(self, "closure_manifest_digest", DigestRef.parse(str(self.closure_manifest_digest)))
        else:
            object.__setattr__(self, "closure_manifest_digest", DigestRef.from_payload(self.payload_for_digest()))

    def payload_for_digest(self) -> dict[str, object]:
        return {
            "closure_contract_version": self.closure_contract_version,
            "comparison_digest": self.comparison_digest.to_payload(),
            "facts_core_digest": self.facts_core_digest.to_payload(),
            "records": [
                {
                    "table_name": member.table_name,
                    "records_manifest_digest": member.records_manifest_digest.to_payload(),
                    "records_content_digest": member.records_content_digest.to_payload(),
                    "record_count": member.record_count,
                }
                for member in self.records
            ],
        }

    def to_payload(self) -> dict[str, object]:
        return {
            **self.payload_for_digest(),
            "closure_manifest_digest": self.closure_manifest_digest.to_payload()
            if self.closure_manifest_digest is not None
            else None,
        }


@dataclass(frozen=True, slots=True)
class ComparisonPlan:
    comparison_digest: DigestRef | str
    summary_early_exit_tables: tuple[str, ...] = field(default_factory=tuple)
    row_compare_tables: tuple[str, ...] = field(default_factory=tuple)
    provider_routes: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "comparison_digest", DigestRef.parse(str(self.comparison_digest)))
        if not isinstance(self.summary_early_exit_tables, tuple):
            object.__setattr__(self, "summary_early_exit_tables", tuple(self.summary_early_exit_tables))
        if not isinstance(self.row_compare_tables, tuple):
            object.__setattr__(self, "row_compare_tables", tuple(self.row_compare_tables))
        if not isinstance(self.provider_routes, tuple):
            object.__setattr__(self, "provider_routes", tuple(self.provider_routes))
        object.__setattr__(
            self,
            "summary_early_exit_tables",
            tuple(canonical_identifier(table_name) for table_name in self.summary_early_exit_tables if canonical_identifier(table_name)),
        )
        object.__setattr__(
            self,
            "row_compare_tables",
            tuple(canonical_identifier(table_name) for table_name in self.row_compare_tables if canonical_identifier(table_name)),
        )
        normalized_provider_routes: list[tuple[str, str]] = []
        for table_name, provider_name in self.provider_routes:
            if not isinstance(table_name, str) or not table_name.strip():
                raise ValueError("provider_routes table_name must be a non-empty string")
            if not isinstance(provider_name, str) or not provider_name.strip():
                raise ValueError("provider_routes provider_name must be a non-empty string")
            normalized_provider_routes.append((canonical_identifier(table_name), provider_name))
        object.__setattr__(self, "provider_routes", tuple(normalized_provider_routes))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))


@dataclass(frozen=True, slots=True)
class ComparisonComputeResult:
    facts: ComparisonFacts
    summary: ComparisonSummary
    plan: ComparisonPlan
    records_artifacts: tuple[RecordsArtifact, ...] = field(default_factory=tuple)
    cache_diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.facts, ComparisonFacts):
            raise TypeError("facts must be a ComparisonFacts")
        if not isinstance(self.summary, ComparisonSummary):
            raise TypeError("summary must be a ComparisonSummary")
        if not isinstance(self.plan, ComparisonPlan):
            raise TypeError("plan must be a ComparisonPlan")
        if not isinstance(self.records_artifacts, tuple):
            object.__setattr__(self, "records_artifacts", tuple(self.records_artifacts))
        normalized_records_artifacts: list[RecordsArtifact] = []
        for records_artifact in self.records_artifacts:
            if not isinstance(records_artifact, RecordsArtifact):
                raise TypeError("records_artifacts must contain RecordsArtifact values")
            normalized_records_artifacts.append(records_artifact)
        object.__setattr__(self, "records_artifacts", tuple(normalized_records_artifacts))
        normalized_cache_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.cache_diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("cache_diagnostics must contain DiagnosticRecord values")
            normalized_cache_diagnostics.append(diagnostic)
        object.__setattr__(self, "cache_diagnostics", tuple(normalized_cache_diagnostics))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))


@dataclass(frozen=True, slots=True)
class ComparisonRecord:
    table_name: str
    record_kind: ComparisonRecordKind | str
    row_identity: tuple[object, ...] | None = None
    changed_columns: tuple[str, ...] | None = None
    before_values: tuple[object, ...] | None = None
    current_values: tuple[object, ...] | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name.strip():
            raise ValueError("table_name must be a non-empty string")
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        object.__setattr__(self, "record_kind", ComparisonRecordKind(self.record_kind))
        if self.row_identity is not None and not isinstance(self.row_identity, tuple):
            object.__setattr__(self, "row_identity", tuple(self.row_identity))
        if self.changed_columns is not None and not isinstance(self.changed_columns, tuple):
            object.__setattr__(self, "changed_columns", tuple(self.changed_columns))
        if self.before_values is not None and not isinstance(self.before_values, tuple):
            object.__setattr__(self, "before_values", tuple(self.before_values))
        if self.current_values is not None and not isinstance(self.current_values, tuple):
            object.__setattr__(self, "current_values", tuple(self.current_values))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))


def _normalize_identifier_tuple(values: Sequence[str], *, field_name: str) -> tuple[str, ...]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must contain non-empty strings")
        normalized_value = canonical_identifier(value)
        if not normalized_value:
            raise ValueError(f"{field_name} must not contain empty identifiers")
        if normalized_value in seen:
            raise ValueError(f"duplicate canonical identifier in {field_name}: {normalized_value}")
        seen.add(normalized_value)
        normalized_values.append(normalized_value)
    return tuple(normalized_values)
