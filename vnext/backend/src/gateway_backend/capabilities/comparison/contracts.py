"""Public contracts owned by the Comparison capability.

S1 owns the language-neutral batch/provider port. S2-S5 add pair, facts and records semantics without
changing this coarse-grained Arrow boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, ClassVar, Protocol, TypeAlias, runtime_checkable

import pyarrow as pa
from gateway_shared_kernel import DigestRef, canonicalize_identifier, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BATCH_READER_CONTRACT_VERSION,
    BATCH_SCHEMA_METADATA_VERSION,
    Snapshot,
    SnapshotSummary,
    SnapshotTable,
    SnapshotTableBatchMetadata,
    SnapshotTableBatchReader,
    SnapshotTableDescriptor,
    SnapshotTableSet,
)

COMPARISON_BATCH_PORT_VERSION = 1
COMPARISON_CONTRACT_VERSION = "backend-vnext/comparison/v2"
PROJECT_IDENTITY_ASSESSMENT_SCHEMA_VERSION = "project-identity-assessment/v1"
PROJECT_IDENTITY_RULE_VERSION = "version-manager-overlap/v1"
RECORDS_ARTIFACT_CONTRACT_VERSION = "backend-vnext/comparison-records/v1"
RECORDS_CLOSURE_CONTRACT_VERSION = "backend-vnext/comparison-records-closure/v1"
RECORDS_PARQUET_FORMAT = "PARQUET"
STANDARD_RECORDS_SCHEMA_VERSION = "standard-records/v1"
ORDERED_RECORDS_SCHEMA_VERSION = "ordered-records/v1"
BLANK_RECORDS_SCHEMA_VERSION = "blank-records/v1"


class PairViewKind(StrEnum):
    """Flow-neutral view context supplied by the trusted orchestrator."""

    PAIR_COMPARISON = "PAIR_COMPARISON"
    INITIAL_SNAPSHOT = "INITIAL_SNAPSHOT"
    HISTORY = "HISTORY"
    ARCHIVE_REPLAY = "ARCHIVE_REPLAY"


class PairRole(StrEnum):
    """The directed pair role within a formal upload or replay flow."""

    INITIAL_SNAPSHOT = "INITIAL_SNAPSHOT"
    BASELINE_TO_INITIAL = "BASELINE_TO_INITIAL"
    INITIAL_TO_MODIFIED = "INITIAL_TO_MODIFIED"
    HISTORY = "HISTORY"
    ARCHIVE_REPLAY = "ARCHIVE_REPLAY"


class InputCompleteness(StrEnum):
    FULL = "FULL"
    MODIFIED_ONLY = "MODIFIED_ONLY"


class ComparisonMode(StrEnum):
    DETAILED = "DETAILED"
    DATASET_REPLACEMENT = "DATASET_REPLACEMENT"


class ArtifactScope(StrEnum):
    ALL_CHANGES = "ALL_CHANGES"
    UPDATE_ONLY = "UPDATE_ONLY"


class KeylessPolicy(StrEnum):
    """Explicit fallback semantics when no effective compare key is available."""

    DEGRADE_NO_COMPARE_KEY = "DEGRADE_NO_COMPARE_KEY"
    FULL_ROW_DIGEST_SET_DIFF = "FULL_ROW_DIGEST_SET_DIFF"


class ComparisonRecordKind(StrEnum):
    ROW_ADDED = "ROW_ADDED"
    ROW_DELETED = "ROW_DELETED"
    ROW_MODIFIED = "ROW_MODIFIED"
    SCHEMA_CHANGE = "SCHEMA_CHANGE"
    TABLE_DEGRADED = "TABLE_DEGRADED"


class RecordsArtifactFamily(StrEnum):
    STANDARD = "STANDARD"
    ORDERED = "ORDERED"
    BLANK = "BLANK"


class RecordsDetailPolicy(StrEnum):
    COUNTS_ONLY = "COUNTS_ONLY"
    CHANGED_COLUMNS = "CHANGED_COLUMNS"
    FULL_BEFORE_AFTER_VALUES = "FULL_BEFORE_AFTER_VALUES"


class ComparisonTableStatus(StrEnum):
    UNCHANGED = "UNCHANGED"
    BUSINESS_EQUIVALENT = "BUSINESS_EQUIVALENT"
    ADDED_TABLE = "ADDED_TABLE"
    DELETED_TABLE = "DELETED_TABLE"
    MODIFIED = "MODIFIED"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    SCHEMA_ONLY_CHANGED = "SCHEMA_ONLY_CHANGED"
    DEGRADED = "DEGRADED"


class IdentityApplicability(StrEnum):
    REQUIRED = "REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class IdentityStatus(StrEnum):
    SAME_PROJECT = "SAME_PROJECT"
    DIFFERENT_PROJECT = "DIFFERENT_PROJECT"
    UNVERIFIABLE = "UNVERIFIABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ContinuationAction(StrEnum):
    ALLOW_DETAILED_ON_UNVERIFIABLE = "ALLOW_DETAILED_ON_UNVERIFIABLE"


class BaselineReconstructionStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class PairResultKind(StrEnum):
    INITIAL_SNAPSHOT = "INITIAL_SNAPSHOT"
    DETAILED_FACTS = "DETAILED_FACTS"
    DATASET_REPLACEMENT = "DATASET_REPLACEMENT"
    IDENTITY_GATE_BLOCKED = "IDENTITY_GATE_BLOCKED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class PairResultStatus(StrEnum):
    UNCHANGED = "UNCHANGED"
    BUSINESS_EQUIVALENT = "BUSINESS_EQUIVALENT"
    CHANGED = "CHANGED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


ORDERED_DIFF_CONTRACT_VERSION = "backend-vnext/ordered-diff/v2"
BLANK_COMPARISON_CONTRACT_VERSION = "backend-vnext/comparison-blank/v1"
GID_REAL_MIN = 1
GID_REAL_MAX = 3_999_999_999
GID_PSEUDO_MIN = 4_000_000_000
GID_PSEUDO_MAX = 4_294_967_295


class BlankRowPolicy(StrEnum):
    PSEUDO_BLANK_BY_MISSING_STABLE_KEY = "PSEUDO_BLANK_BY_MISSING_STABLE_KEY"


class OrderedStatus(StrEnum):
    UNCHANGED = "ORDERED_UNCHANGED"
    CHANGED = "ORDERED_CHANGED"
    BUSINESS_EQUIVALENT = "ORDERED_BUSINESS_EQUIVALENT"
    DEGRADED = "ORDERED_DEGRADED"


class OrderedRecordKind(StrEnum):
    ROW_ADDED = "ORDERED_ROW_ADDED"
    ROW_DELETED = "ORDERED_ROW_DELETED"
    ROW_MODIFIED = "ORDERED_ROW_MODIFIED"
    ROW_MOVED = "ORDERED_ROW_MOVED"
    TABLE_DEGRADED = "ORDERED_TABLE_DEGRADED"


class OrderedSemanticKind(StrEnum):
    DATA_INSERT = "DATA_INSERT"
    DATA_DELETE = "DATA_DELETE"
    MOVE = "MOVE"
    CONTENT_UPDATE = "CONTENT_UPDATE"


class OrderedEntityKeyKind(StrEnum):
    REAL_STABLE = "REAL_STABLE"
    PSEUDO_BLANK = "PSEUDO_BLANK"


class ReplayGuarantee(StrEnum):
    EXACT = "EXACT"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"


class OrderedTableProcessingMode(StrEnum):
    TAIL_SEGMENT = "ORDERED_TAIL_SEGMENT"
    LOCAL_PATCH = "ORDERED_LOCAL_PATCH"
    SHIFT_REPAIRED = "ORDERED_SHIFT_REPAIRED"
    REORDER_COMPLEX = "ORDERED_REORDER_COMPLEX"
    DEGRADED = "DEGRADED"


class BlankRecordKind(StrEnum):
    DELETE_INTERVAL = "BLANK_DELETE_INTERVAL"
    INSERT_INTERVAL = "BLANK_INSERT_INTERVAL"


class BlankSemanticKind(StrEnum):
    DELETE_INTERVAL = "BLANK_DELETE_INTERVAL"
    INSERT_INTERVAL = "BLANK_INSERT_INTERVAL"


@dataclass(frozen=True, slots=True)
class RecordsArtifactManifest:
    """Small, ref-independent metadata for one table/family Parquet artifact."""

    table_name: str
    family: RecordsArtifactFamily
    record_format: str
    schema_version: str
    row_diff_detail_policy: RecordsDetailPolicy
    record_count: int
    content_digest: DigestRef
    contract_version: str = RECORDS_ARTIFACT_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_name", _require_canonical_table_name(self.table_name))
        if type(self.family) is not RecordsArtifactFamily:
            raise ValueError("family must be RecordsArtifactFamily")
        if self.record_format != RECORDS_PARQUET_FORMAT:
            raise ValueError("record_format must be PARQUET")
        expected_schema_version = {
            RecordsArtifactFamily.STANDARD: STANDARD_RECORDS_SCHEMA_VERSION,
            RecordsArtifactFamily.ORDERED: ORDERED_RECORDS_SCHEMA_VERSION,
            RecordsArtifactFamily.BLANK: BLANK_RECORDS_SCHEMA_VERSION,
        }[self.family]
        if self.schema_version != expected_schema_version:
            raise ValueError("schema_version does not match records family")
        if type(self.schema_version) is not str or self.schema_version == "":
            raise ValueError("schema_version must be a non-empty string")
        if type(self.row_diff_detail_policy) is not RecordsDetailPolicy:
            raise ValueError("row_diff_detail_policy must be RecordsDetailPolicy")
        if type(self.record_count) is not int or self.record_count < 0:
            raise ValueError("record_count must be a non-negative integer")
        if type(self.content_digest) is not DigestRef:
            raise ValueError("content_digest must be DigestRef")
        if self.contract_version != RECORDS_ARTIFACT_CONTRACT_VERSION:
            raise ValueError("unsupported records artifact contract version")


@dataclass(frozen=True, slots=True)
class RecordsClosureEntry:
    table_name: str
    family: RecordsArtifactFamily
    records_ref: ArtifactRef
    records_manifest_ref: ArtifactRef
    records_manifest_digest: DigestRef
    records_content_digest: DigestRef
    record_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_name", _require_canonical_table_name(self.table_name))
        if type(self.family) is not RecordsArtifactFamily:
            raise ValueError("family must be RecordsArtifactFamily")
        if type(self.records_ref) is not ArtifactRef:
            raise ValueError("records_ref must be ArtifactRef")
        if type(self.records_manifest_ref) is not ArtifactRef:
            raise ValueError("records_manifest_ref must be ArtifactRef")
        for label in ("records_manifest_digest", "records_content_digest"):
            if type(getattr(self, label)) is not DigestRef:
                raise ValueError(f"{label} must be DigestRef")
        if type(self.record_count) is not int or self.record_count < 0:
            raise ValueError("record_count must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class ComparisonRecordsClosure:
    """Immutable pair-level closure over all published table/family artifacts."""

    comparison_digest: DigestRef
    facts_core_digest: DigestRef
    records: tuple[RecordsClosureEntry, ...]
    closure_manifest_digest: DigestRef
    closure_contract_version: str = RECORDS_CLOSURE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for label in (
            "comparison_digest",
            "facts_core_digest",
            "closure_manifest_digest",
        ):
            if type(getattr(self, label)) is not DigestRef:
                raise ValueError(f"{label} must be DigestRef")
        if type(self.records) is not tuple or any(
            type(item) is not RecordsClosureEntry for item in self.records
        ):
            raise ValueError("records must contain RecordsClosureEntry")
        keys = tuple((item.table_name, item.family.value) for item in self.records)
        if keys != tuple(sorted(keys)):
            raise ValueError("records must use canonical table/family order")
        if len(set(keys)) != len(keys):
            raise ValueError("records must not repeat table/family pairs")
        if self.closure_contract_version != RECORDS_CLOSURE_CONTRACT_VERSION:
            raise ValueError("unsupported records closure contract version")

    @property
    def closure_digest(self) -> DigestRef:
        """Compatibility name for consumers of the original S5 marker protocol."""

        return self.closure_manifest_digest


@runtime_checkable
class ProjectIdentityAssessment(Protocol):
    """Read-only consumer port for the separately owned identity capability.

    R5 validates the binding fields below but never computes the assessment or exposes its
    original identity entries.
    """

    @property
    def schema_version(self) -> str: ...

    @property
    def rule_version(self) -> str: ...

    @property
    def before_snapshot_digest(self) -> DigestRef: ...

    @property
    def current_snapshot_digest(self) -> DigestRef: ...

    @property
    def status(self) -> IdentityStatus: ...

    @property
    def comparable_columns(self) -> tuple[str, ...]: ...

    @property
    def before_row_count(self) -> int: ...

    @property
    def current_row_count(self) -> int: ...

    @property
    def before_distinct_entry_count(self) -> int: ...

    @property
    def current_distinct_entry_count(self) -> int: ...

    @property
    def matched_entry_count(self) -> int: ...

    @property
    def before_entry_set_digest(self) -> DigestRef | None: ...

    @property
    def current_entry_set_digest(self) -> DigestRef | None: ...

    @property
    def assessment_digest(self) -> DigestRef: ...

    @property
    def diagnostics(self) -> tuple[object, ...]: ...

    @property
    def requires_continuation_confirmation(self) -> bool: ...

    @property
    def requires_submit_confirmation(self) -> bool: ...


ComparisonOptionValue: TypeAlias = str | int | bool | None
ContractVersionValue: TypeAlias = str | int
ComparisonOptions: TypeAlias = tuple[tuple[str, ComparisonOptionValue], ...]
ContractVersions: TypeAlias = tuple[tuple[str, ContractVersionValue], ...]

DEFAULT_CONTRACT_VERSIONS: ContractVersions = (
    ("comparison_contract_version", COMPARISON_CONTRACT_VERSION),
)


@dataclass(frozen=True, slots=True)
class OrderedTablePolicy:
    """Explicit ordered semantics supplied by the trusted table-rules owner."""

    policy_id: str = "ordered-gid-no-v1"
    policy_version: str = ORDERED_DIFF_CONTRACT_VERSION
    order_key: tuple[str, ...] = ("no",)
    row_identity_key: tuple[str, ...] | None = ("gid",)
    stable_key_candidates: tuple[str, ...] = ("gid",)
    value_columns: tuple[str, ...] = ()
    ignored_columns: tuple[str, ...] = ("no",)
    blank_row_policy: BlankRowPolicy = BlankRowPolicy.PSEUDO_BLANK_BY_MISSING_STABLE_KEY
    move_policy: str = "STABLE_KEY_RELATIVE_ORDER_V1"
    ambiguity_policy: str = "DEGRADE_ON_AMBIGUITY"
    tail_change_policy: str = "INTERVAL_OR_ROW_V1"
    table_processing_mode_policy: str = "ORDERED_MODE_V1"
    policy_digest: DigestRef | None = None

    def __post_init__(self) -> None:
        for label in (
            "policy_id",
            "policy_version",
            "move_policy",
            "ambiguity_policy",
            "tail_change_policy",
            "table_processing_mode_policy",
        ):
            value = getattr(self, label)
            if type(value) is not str or value == "":
                raise ValueError(f"{label} must be a non-empty string")
        if type(self.blank_row_policy) is not BlankRowPolicy:
            raise ValueError("blank_row_policy must be BlankRowPolicy")
        for label in (
            "order_key",
            "stable_key_candidates",
            "value_columns",
            "ignored_columns",
        ):
            value = getattr(self, label)
            if type(value) is not tuple:
                raise ValueError(f"{label} must be a tuple")
            canonical = tuple(_require_canonical_column_name(item) for item in value)
            if len(set(canonical)) != len(canonical):
                raise ValueError(f"{label} must not repeat names")
            object.__setattr__(self, label, canonical)
        if not self.order_key:
            raise ValueError("order_key must not be empty")
        if self.row_identity_key is not None:
            if type(self.row_identity_key) is not tuple or not self.row_identity_key:
                raise ValueError("row_identity_key must be a non-empty tuple or None")
            canonical_identity = tuple(
                _require_canonical_column_name(item) for item in self.row_identity_key
            )
            if len(set(canonical_identity)) != len(canonical_identity):
                raise ValueError("row_identity_key must not repeat names")
            object.__setattr__(self, "row_identity_key", canonical_identity)
        if self.policy_digest is not None and type(self.policy_digest) is not DigestRef:
            raise ValueError("policy_digest must be DigestRef or None")
        if self.policy_digest is None:
            payload = {
                "kind": "ordered-table-policy",
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
                "order_key": list(self.order_key),
                "row_identity_key": (
                    None if self.row_identity_key is None else list(self.row_identity_key)
                ),
                "stable_key_candidates": list(self.stable_key_candidates),
                "value_columns": list(self.value_columns),
                "ignored_columns": list(self.ignored_columns),
                "blank_row_policy": self.blank_row_policy.value,
                "move_policy": self.move_policy,
                "ambiguity_policy": self.ambiguity_policy,
                "tail_change_policy": self.tail_change_policy,
                "table_processing_mode_policy": self.table_processing_mode_policy,
            }
            object.__setattr__(
                self,
                "policy_digest",
                raw_blob_digest(canonicalize_json_value(payload)),
            )


@dataclass(frozen=True, slots=True)
class OrderedInterval:
    before_start: int | None = None
    before_end: int | None = None
    current_start: int | None = None
    current_end: int | None = None
    row_count: int = 0
    interval_digest: DigestRef | None = None

    def __post_init__(self) -> None:
        for label in ("before_start", "before_end", "current_start", "current_end"):
            value = getattr(self, label)
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError(f"{label} must be a positive int or None")
        if type(self.row_count) is not int or self.row_count < 0:
            raise ValueError("row_count must be a non-negative int")
        if self.interval_digest is not None and type(self.interval_digest) is not DigestRef:
            raise ValueError("interval_digest must be DigestRef or None")


def _validate_ordered_values(value: object, label: str) -> None:
    if type(value) is not tuple:
        raise ValueError(f"{label} must be a tuple")
    for item in value:
        if type(item) is not tuple or len(item) != 2:
            raise ValueError(f"{label} must contain name/value pairs")
        _require_canonical_column_name(item[0])


@dataclass(frozen=True, slots=True)
class OrderedRecord:
    table_name: str
    record_kind: OrderedRecordKind
    semantic_kind: OrderedSemanticKind
    entity_key_kind: OrderedEntityKeyKind = OrderedEntityKeyKind.REAL_STABLE
    row_identity: DigestRef | None = None
    before_position: int | None = None
    current_position: int | None = None
    before_values: tuple[tuple[str, object], ...] = ()
    current_values: tuple[tuple[str, object], ...] = ()
    changed_columns: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_name", _require_canonical_table_name(self.table_name))
        if type(self.record_kind) is not OrderedRecordKind:
            raise ValueError("record_kind must be OrderedRecordKind")
        if type(self.semantic_kind) is not OrderedSemanticKind:
            raise ValueError("semantic_kind must be OrderedSemanticKind")
        if type(self.entity_key_kind) is not OrderedEntityKeyKind:
            raise ValueError("entity_key_kind must be OrderedEntityKeyKind")
        if self.row_identity is not None and type(self.row_identity) is not DigestRef:
            raise ValueError("row_identity must be DigestRef or None")
        for label in ("before_position", "current_position"):
            value = getattr(self, label)
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError(f"{label} must be a positive int or None")
        _validate_ordered_values(self.before_values, "before_values")
        _validate_ordered_values(self.current_values, "current_values")
        canonical_columns = tuple(_require_canonical_column_name(item) for item in self.changed_columns)
        if len(set(canonical_columns)) != len(canonical_columns):
            raise ValueError("changed_columns must not repeat names")
        object.__setattr__(self, "changed_columns", canonical_columns)
        if self.record_kind is not OrderedRecordKind.TABLE_DEGRADED and self.row_identity is None:
            raise ValueError("ordered row records require row_identity")
        if self.entity_key_kind is OrderedEntityKeyKind.PSEUDO_BLANK:
            raise ValueError("blank rows use BlankRecord, not OrderedRecord")
        _require_diagnostic_strings(self.diagnostics)


@dataclass(frozen=True, slots=True)
class BlankRecord:
    table_name: str
    record_kind: BlankRecordKind
    semantic_kind: BlankSemanticKind
    interval: OrderedInterval
    entity_key_kind: OrderedEntityKeyKind = OrderedEntityKeyKind.PSEUDO_BLANK
    before_occupancy: int = 0
    current_occupancy: int = 0
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_name", _require_canonical_table_name(self.table_name))
        if type(self.record_kind) is not BlankRecordKind:
            raise ValueError("record_kind must be BlankRecordKind")
        if type(self.semantic_kind) is not BlankSemanticKind:
            raise ValueError("semantic_kind must be BlankSemanticKind")
        if type(self.interval) is not OrderedInterval:
            raise ValueError("interval must be OrderedInterval")
        if self.entity_key_kind is not OrderedEntityKeyKind.PSEUDO_BLANK:
            raise ValueError("blank records must use PSEUDO_BLANK entity key kind")
        for label in ("before_occupancy", "current_occupancy"):
            value = getattr(self, label)
            if type(value) is not int or value < 0:
                raise ValueError(f"{label} must be a non-negative int")
        _require_diagnostic_strings(self.diagnostics)


@dataclass(frozen=True, slots=True)
class OrderedSummary:
    row_added_count: int = 0
    row_deleted_count: int = 0
    row_modified_count: int = 0
    row_moved_count: int = 0
    position_changed_count: int = 0
    degraded_count: int = 0

    def __post_init__(self) -> None:
        _require_non_negative_int_fields(self, (
            "row_added_count",
            "row_deleted_count",
            "row_modified_count",
            "row_moved_count",
            "position_changed_count",
            "degraded_count",
        ))


@dataclass(frozen=True, slots=True)
class BlankSummary:
    interval_inserted_count: int = 0
    interval_deleted_count: int = 0
    blank_changed_count: int = 0
    degraded_count: int = 0

    def __post_init__(self) -> None:
        _require_non_negative_int_fields(self, (
            "interval_inserted_count",
            "interval_deleted_count",
            "blank_changed_count",
            "degraded_count",
        ))


@dataclass(frozen=True, slots=True)
class OrderedExtension:
    status: OrderedStatus
    ordered_summary: OrderedSummary
    records: tuple[OrderedRecord, ...] = ()
    before_ordered_digest: DigestRef | None = None
    current_ordered_digest: DigestRef | None = None
    replay_guarantee: ReplayGuarantee = ReplayGuarantee.EXACT
    table_processing_mode: OrderedTableProcessingMode | None = None
    diagnostics: tuple[str, ...] = ()
    contract_version: str = ORDERED_DIFF_CONTRACT_VERSION
    policy_digest: DigestRef | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not OrderedStatus:
            raise ValueError("status must be OrderedStatus")
        if type(self.ordered_summary) is not OrderedSummary:
            raise ValueError("ordered_summary must be OrderedSummary")
        if type(self.records) is not tuple or any(type(item) is not OrderedRecord for item in self.records):
            raise ValueError("records must contain OrderedRecord")
        for label in ("before_ordered_digest", "current_ordered_digest", "policy_digest"):
            value = getattr(self, label)
            if value is not None and type(value) is not DigestRef:
                raise ValueError(f"{label} must be DigestRef or None")
        if type(self.replay_guarantee) is not ReplayGuarantee:
            raise ValueError("replay_guarantee must be ReplayGuarantee")
        if self.table_processing_mode is not None and type(self.table_processing_mode) is not OrderedTableProcessingMode:
            raise ValueError("table_processing_mode must be OrderedTableProcessingMode or None")
        _require_diagnostic_strings(self.diagnostics)
        if type(self.contract_version) is not str or self.contract_version == "":
            raise ValueError("contract_version must be a non-empty string")


@dataclass(frozen=True, slots=True)
class BlankExtension:
    status: OrderedStatus
    blank_summary: BlankSummary
    records: tuple[BlankRecord, ...] = ()
    before_occupancy_digest: DigestRef | None = None
    current_occupancy_digest: DigestRef | None = None
    replay_guarantee: ReplayGuarantee = ReplayGuarantee.EXACT
    diagnostics: tuple[str, ...] = ()
    contract_version: str = BLANK_COMPARISON_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if type(self.status) is not OrderedStatus:
            raise ValueError("status must be OrderedStatus")
        if type(self.blank_summary) is not BlankSummary:
            raise ValueError("blank_summary must be BlankSummary")
        if type(self.records) is not tuple or any(type(item) is not BlankRecord for item in self.records):
            raise ValueError("records must contain BlankRecord")
        for label in ("before_occupancy_digest", "current_occupancy_digest"):
            value = getattr(self, label)
            if value is not None and type(value) is not DigestRef:
                raise ValueError(f"{label} must be DigestRef or None")
        if type(self.replay_guarantee) is not ReplayGuarantee:
            raise ValueError("replay_guarantee must be ReplayGuarantee")
        _require_diagnostic_strings(self.diagnostics)
        if type(self.contract_version) is not str or self.contract_version == "":
            raise ValueError("contract_version must be a non-empty string")


@dataclass(frozen=True, slots=True)
class ComparisonTablePolicy:
    """Immutable per-table projection and keyless policy supplied by an upstream owner."""

    table_name: str
    ignored_columns: tuple[str, ...] = ()
    keyless_policy: KeylessPolicy = KeylessPolicy.DEGRADE_NO_COMPARE_KEY
    policy_version: str = "comparison-table-policy/v1"
    ordered_policy: OrderedTablePolicy | None = None

    def __post_init__(self) -> None:
        canonical_name = _require_canonical_table_name(self.table_name)
        object.__setattr__(self, "table_name", canonical_name)
        if type(self.ignored_columns) is not tuple:
            raise ValueError("ignored_columns must be a tuple")
        canonical_columns = tuple(
            _require_canonical_column_name(column) for column in self.ignored_columns
        )
        if len(set(canonical_columns)) != len(canonical_columns):
            raise ValueError("ignored_columns must not repeat names")
        object.__setattr__(self, "ignored_columns", canonical_columns)
        if type(self.keyless_policy) is not KeylessPolicy:
            raise ValueError("keyless_policy must be KeylessPolicy")
        if type(self.policy_version) is not str or self.policy_version == "":
            raise ValueError("policy_version must be a non-empty string")
        if self.ordered_policy is not None and type(self.ordered_policy) is not OrderedTablePolicy:
            raise ValueError("ordered_policy must be OrderedTablePolicy or None")


@dataclass(frozen=True, slots=True)
class ComparisonSchemaChanges:
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
            value = getattr(self, label)
            if type(value) is not tuple:
                raise ValueError(f"{label} must be a tuple")
            canonical = tuple(_require_canonical_column_name(item) for item in value)
            if len(set(canonical)) != len(canonical):
                raise ValueError(f"{label} must not repeat names")
            object.__setattr__(self, label, canonical)
        if type(self.effective_compare_key_changed) is not bool:
            raise ValueError("effective_compare_key_changed must be bool")


@dataclass(frozen=True, slots=True)
class FieldChange:
    table_name: str
    row_identity: DigestRef
    column_name: str
    before_value: object
    current_value: object
    change_kind: str = "UPDATE"

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_name", _require_canonical_table_name(self.table_name))
        if type(self.row_identity) is not DigestRef:
            raise ValueError("row_identity must be DigestRef")
        object.__setattr__(self, "column_name", _require_canonical_column_name(self.column_name))
        if self.change_kind != "UPDATE":
            raise ValueError("FieldChange change_kind must be UPDATE")


@dataclass(frozen=True, slots=True)
class ComparisonRecord:
    table_name: str
    record_kind: ComparisonRecordKind
    row_identity: DigestRef | None = None
    changed_columns: tuple[str, ...] = ()
    before_values: tuple[tuple[str, object], ...] = ()
    current_values: tuple[tuple[str, object], ...] = ()
    field_changes: tuple[FieldChange, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_name", _require_canonical_table_name(self.table_name))
        if type(self.record_kind) is not ComparisonRecordKind:
            raise ValueError("record_kind must be ComparisonRecordKind")
        if self.row_identity is not None and type(self.row_identity) is not DigestRef:
            raise ValueError("row_identity must be DigestRef or None")
        if type(self.changed_columns) is not tuple:
            raise ValueError("changed_columns must be a tuple")
        canonical_columns = tuple(
            _require_canonical_column_name(item) for item in self.changed_columns
        )
        if len(set(canonical_columns)) != len(canonical_columns):
            raise ValueError("changed_columns must not repeat names")
        object.__setattr__(self, "changed_columns", canonical_columns)
        for label in ("before_values", "current_values"):
            values = getattr(self, label)
            if type(values) is not tuple:
                raise ValueError(f"{label} must be a tuple")
            for item in values:
                if type(item) is not tuple or len(item) != 2:
                    raise ValueError(f"{label} must contain name/value pairs")
                _require_canonical_column_name(item[0])
        if type(self.field_changes) is not tuple or any(
            type(item) is not FieldChange for item in self.field_changes
        ):
            raise ValueError("field_changes must contain FieldChange")
        if any(item.table_name != self.table_name for item in self.field_changes):
            raise ValueError("field_changes table name must match record")
        if self.record_kind in {
            ComparisonRecordKind.ROW_ADDED,
            ComparisonRecordKind.ROW_DELETED,
            ComparisonRecordKind.ROW_MODIFIED,
        } and self.row_identity is None:
            raise ValueError("row records require row_identity")
        if self.record_kind is not ComparisonRecordKind.ROW_MODIFIED and self.field_changes:
            raise ValueError("only ROW_MODIFIED records may contain field_changes")
        _require_diagnostic_strings(self.diagnostics)


@dataclass(frozen=True, slots=True)
class ComparisonTableFact:
    table_name: str
    status: ComparisonTableStatus
    before_descriptor: SnapshotTableDescriptor | None = None
    current_descriptor: SnapshotTableDescriptor | None = None
    schema_changes: ComparisonSchemaChanges = ComparisonSchemaChanges()
    row_count_before: int | None = None
    row_count_current: int | None = None
    row_added_count: int = 0
    row_deleted_count: int = 0
    row_modified_count: int = 0
    suppressed_added_count: int = 0
    suppressed_deleted_count: int = 0
    records: tuple[ComparisonRecord, ...] = ()
    diagnostics: tuple[str, ...] = ()
    table_fact_digest: DigestRef | None = None
    ordered_extension: OrderedExtension | None = None
    blank_extension: BlankExtension | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_name", _require_canonical_table_name(self.table_name))
        if type(self.status) is not ComparisonTableStatus:
            raise ValueError("status must be ComparisonTableStatus")
        for label in (
            "before_descriptor",
            "current_descriptor",
        ):
            descriptor = getattr(self, label)
            if descriptor is not None and type(descriptor) is not SnapshotTableDescriptor:
                raise ValueError(f"{label} must be SnapshotTableDescriptor or None")
        if type(self.schema_changes) is not ComparisonSchemaChanges:
            raise ValueError("schema_changes must be ComparisonSchemaChanges")
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
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{label} must be a non-negative int or None")
        if type(self.records) is not tuple or any(
            type(item) is not ComparisonRecord for item in self.records
        ):
            raise ValueError("records must contain ComparisonRecord")
        _require_diagnostic_strings(self.diagnostics)
        if self.table_fact_digest is not None and type(self.table_fact_digest) is not DigestRef:
            raise ValueError("table_fact_digest must be DigestRef or None")
        if self.ordered_extension is not None and type(self.ordered_extension) is not OrderedExtension:
            raise ValueError("ordered_extension must be OrderedExtension or None")
        if self.blank_extension is not None and type(self.blank_extension) is not BlankExtension:
            raise ValueError("blank_extension must be BlankExtension or None")


@dataclass(frozen=True, slots=True)
class ComparisonSummary:
    status: PairResultStatus
    table_count: int
    unchanged_table_count: int
    changed_table_count: int
    added_table_count: int
    deleted_table_count: int
    schema_changed_table_count: int
    degraded_table_count: int
    row_added_count: int
    row_deleted_count: int
    row_modified_count: int
    suppressed_added_count: int
    suppressed_deleted_count: int
    diagnostics_count: int

    def __post_init__(self) -> None:
        if type(self.status) is not PairResultStatus:
            raise ValueError("status must be PairResultStatus")
        for label in (
            "table_count",
            "unchanged_table_count",
            "changed_table_count",
            "added_table_count",
            "deleted_table_count",
            "schema_changed_table_count",
            "degraded_table_count",
            "row_added_count",
            "row_deleted_count",
            "row_modified_count",
            "suppressed_added_count",
            "suppressed_deleted_count",
            "diagnostics_count",
        ):
            value = getattr(self, label)
            if type(value) is not int or value < 0:
                raise ValueError(f"{label} must be a non-negative int")


@dataclass(frozen=True, slots=True)
class ComparisonFacts:
    comparison_digest: DigestRef
    facts_core_digest: DigestRef
    comparison_contract_version: str
    projection_contract_version: str
    scalar_encoding_version: int
    before_snapshot_digest: DigestRef
    current_snapshot_digest: DigestRef
    comparison_mode: ComparisonMode
    project_identity_status: IdentityStatus
    assessment_digest: DigestRef | None
    direction: str
    summary: ComparisonSummary
    tables: tuple[ComparisonTableFact, ...]
    diagnostics: tuple[str, ...] = ()
    records_ref: ArtifactRef | None = None

    def __post_init__(self) -> None:
        for label in (
            "comparison_digest",
            "facts_core_digest",
            "before_snapshot_digest",
            "current_snapshot_digest",
        ):
            if type(getattr(self, label)) is not DigestRef:
                raise ValueError(f"{label} must be DigestRef")
        for label in ("comparison_contract_version", "projection_contract_version", "direction"):
            value = getattr(self, label)
            if type(value) is not str or value == "":
                raise ValueError(f"{label} must be a non-empty string")
        if type(self.scalar_encoding_version) is not int or self.scalar_encoding_version < 1:
            raise ValueError("scalar_encoding_version must be a positive int")
        if type(self.comparison_mode) is not ComparisonMode:
            raise ValueError("comparison_mode must be ComparisonMode")
        if type(self.project_identity_status) is not IdentityStatus:
            raise ValueError("project_identity_status must be IdentityStatus")
        if self.assessment_digest is not None and type(self.assessment_digest) is not DigestRef:
            raise ValueError("assessment_digest must be DigestRef or None")
        if self.project_identity_status is IdentityStatus.NOT_APPLICABLE:
            if self.assessment_digest is not None:
                raise ValueError("NOT_APPLICABLE facts must not carry assessment_digest")
        elif self.assessment_digest is None:
            raise ValueError("applicable facts require assessment_digest")
        if type(self.summary) is not ComparisonSummary:
            raise ValueError("summary must be ComparisonSummary")
        if type(self.tables) is not tuple or any(
            type(item) is not ComparisonTableFact for item in self.tables
        ):
            raise ValueError("tables must contain ComparisonTableFact")
        table_names = tuple(item.table_name for item in self.tables)
        if len(set(table_names)) != len(table_names):
            raise ValueError("tables must not repeat table names")
        if table_names != tuple(sorted(table_names)):
            raise ValueError("tables must use canonical table order")
        if self.direction != "BEFORE_TO_CURRENT":
            raise ValueError("direction must be BEFORE_TO_CURRENT")
        if self.records_ref is not None and type(self.records_ref) is not ArtifactRef:
            raise ValueError("records_ref must be ArtifactRef or None")
        _require_diagnostic_strings(self.diagnostics)


@dataclass(frozen=True, slots=True)
class BoundSnapshotInput:
    """Immutable snapshot metadata plus an optional public reader/artifact closure."""

    snapshot: Snapshot
    summary: SnapshotSummary
    table_set: SnapshotTableSet | None = None

    def __post_init__(self) -> None:
        if type(self.snapshot) is not Snapshot:
            raise ValueError("snapshot must be Snapshot")
        if type(self.summary) is not SnapshotSummary:
            raise ValueError("summary must be SnapshotSummary")
        if self.snapshot.snapshot_id != self.summary.snapshot_id:
            raise ValueError("snapshot_id must match between snapshot and summary")
        if self.snapshot.snapshot_digest != self.summary.snapshot_digest:
            raise ValueError("snapshot_digest must match between snapshot and summary")
        if self.table_set is not None:
            if type(self.table_set) is not SnapshotTableSet:
                raise ValueError("table_set must be SnapshotTableSet or None")
            if self.table_set.snapshot_id != self.snapshot.snapshot_id:
                raise ValueError("table_set snapshot_id must match snapshot")
            if self.table_set.snapshot_digest != self.snapshot.snapshot_digest:
                raise ValueError("table_set snapshot_digest must match snapshot")

            summary_tables = _canonical_table_map(self.summary.tables)
            table_set_tables = _canonical_table_map(
                tuple(table.descriptor for table in self.table_set.tables)
            )
            for table_name, descriptor in table_set_tables.items():
                if table_name not in summary_tables:
                    raise ValueError("table_set contains a table absent from summary")
                if descriptor != summary_tables[table_name]:
                    raise ValueError("table_set descriptor must match summary descriptor")


@dataclass(frozen=True, slots=True)
class BaselineReconstructionResult:
    """Pinned baseline result supplied by an upstream flow/reconstruction owner."""

    status: BaselineReconstructionStatus
    baseline: BoundSnapshotInput | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.status) is not BaselineReconstructionStatus:
            raise ValueError("status must be BaselineReconstructionStatus")
        _require_diagnostic_strings(self.diagnostics)
        if self.status is BaselineReconstructionStatus.AVAILABLE:
            if type(self.baseline) is not BoundSnapshotInput:
                raise ValueError("AVAILABLE baseline reconstruction requires baseline")
            return
        if self.baseline is not None:
            raise ValueError("UNAVAILABLE baseline reconstruction forbids baseline")
        if not self.diagnostics:
            raise ValueError("UNAVAILABLE baseline reconstruction requires diagnostics")


@dataclass(frozen=True, slots=True)
class TrustedFlowApplicabilityBinding:
    """Opaque flow binding used for history/archive NOT_APPLICABLE contexts.

    The trusted orchestrator is responsible for producing and authorizing this value. R5 only
    validates its context and digest shape; actor/session authorization is deliberately absent.
    """

    view_kind: PairViewKind
    binding_digest: DigestRef

    def __post_init__(self) -> None:
        if self.view_kind not in {PairViewKind.HISTORY, PairViewKind.ARCHIVE_REPLAY}:
            raise ValueError("flow applicability binding requires history or archive view")
        if type(self.binding_digest) is not DigestRef:
            raise ValueError("binding_digest must be DigestRef")


@dataclass(frozen=True, slots=True)
class UnverifiableContinuationBinding:
    """Revalidated, actor-free continuation binding for an UNVERIFIABLE assessment."""

    action: ContinuationAction
    pair_id: str
    before_snapshot_digest: DigestRef
    current_snapshot_digest: DigestRef
    assessment_digest: DigestRef
    assessment_set_digest: DigestRef | None = None
    policy_version: str = ""

    def __post_init__(self) -> None:
        if self.action is not ContinuationAction.ALLOW_DETAILED_ON_UNVERIFIABLE:
            raise ValueError("unsupported continuation action")
        _require_opaque_id(self.pair_id, "pair_id")
        if type(self.before_snapshot_digest) is not DigestRef:
            raise ValueError("before_snapshot_digest must be DigestRef")
        if type(self.current_snapshot_digest) is not DigestRef:
            raise ValueError("current_snapshot_digest must be DigestRef")
        if type(self.assessment_digest) is not DigestRef:
            raise ValueError("assessment_digest must be DigestRef")
        if self.assessment_set_digest is not None and type(self.assessment_set_digest) is not DigestRef:
            raise ValueError("assessment_set_digest must be DigestRef or None")
        if type(self.policy_version) is not str or self.policy_version == "":
            raise ValueError("policy_version must be a non-empty string")


@dataclass(frozen=True, slots=True)
class PairExecutionInput:
    """Flow-neutral, already-bound pair input consumed by the R5 planner."""

    pair_id: str
    view_kind: PairViewKind
    pair_role: PairRole
    before: BoundSnapshotInput | None
    current: BoundSnapshotInput
    input_completeness: InputCompleteness
    comparison_mode: ComparisonMode | None
    artifact_scope: ArtifactScope | None
    identity_applicability: IdentityApplicability
    identity_assessment: ProjectIdentityAssessment | None = None
    continuation_binding: UnverifiableContinuationBinding | None = None
    comparison_options: ComparisonOptions = ()
    contract_versions: ContractVersions = DEFAULT_CONTRACT_VERSIONS
    trusted_flow_binding: TrustedFlowApplicabilityBinding | None = None
    table_policies: tuple[ComparisonTablePolicy, ...] = ()

    def __post_init__(self) -> None:
        _require_opaque_id(self.pair_id, "pair_id")
        if type(self.view_kind) is not PairViewKind:
            raise ValueError("view_kind must be PairViewKind")
        if type(self.pair_role) is not PairRole:
            raise ValueError("pair_role must be PairRole")
        if self.before is not None and type(self.before) is not BoundSnapshotInput:
            raise ValueError("before must be BoundSnapshotInput or None")
        if type(self.current) is not BoundSnapshotInput:
            raise ValueError("current must be BoundSnapshotInput")
        if type(self.input_completeness) is not InputCompleteness:
            raise ValueError("input_completeness must be InputCompleteness")
        if self.comparison_mode is not None and type(self.comparison_mode) is not ComparisonMode:
            raise ValueError("comparison_mode must be ComparisonMode or None")
        if self.artifact_scope is not None and type(self.artifact_scope) is not ArtifactScope:
            raise ValueError("artifact_scope must be ArtifactScope or None")
        if type(self.identity_applicability) is not IdentityApplicability:
            raise ValueError("identity_applicability must be IdentityApplicability")
        if self.identity_assessment is not None and not isinstance(
            self.identity_assessment, ProjectIdentityAssessment
        ):
            raise ValueError("identity_assessment must implement ProjectIdentityAssessment")
        if self.continuation_binding is not None and type(
            self.continuation_binding
        ) is not UnverifiableContinuationBinding:
            raise ValueError("continuation_binding must be UnverifiableContinuationBinding or None")
        _validate_options(self.comparison_options, "comparison_options")
        _validate_contract_versions(self.contract_versions)
        if type(self.table_policies) is not tuple or any(
            type(item) is not ComparisonTablePolicy for item in self.table_policies
        ):
            raise ValueError("table_policies must contain ComparisonTablePolicy")
        policy_names = [item.table_name for item in self.table_policies]
        if len(set(policy_names)) != len(policy_names):
            raise ValueError("table_policies must not repeat table names")
        if self.trusted_flow_binding is not None and type(
            self.trusted_flow_binding
        ) is not TrustedFlowApplicabilityBinding:
            raise ValueError("trusted_flow_binding must be TrustedFlowApplicabilityBinding or None")

        if self.view_kind is PairViewKind.INITIAL_SNAPSHOT:
            if self.pair_role is not PairRole.INITIAL_SNAPSHOT:
                raise ValueError("initial snapshot requires INITIAL_SNAPSHOT pair role")
            if self.before is not None:
                raise ValueError("initial snapshot forbids before")
            if self.comparison_mode is not None or self.artifact_scope is not None:
                raise ValueError("initial snapshot forbids comparison mode and artifact scope")
            if self.identity_applicability is not IdentityApplicability.NOT_APPLICABLE:
                raise ValueError("initial snapshot identity applicability must be NOT_APPLICABLE")
            if self.identity_assessment is not None or self.continuation_binding is not None:
                raise ValueError("initial snapshot forbids identity assessment and continuation")
            if self.trusted_flow_binding is not None:
                raise ValueError("initial snapshot forbids trusted flow binding")
            return

        if self.before is None:
            raise ValueError("comparison input requires before")
        if self.view_kind is PairViewKind.PAIR_COMPARISON:
            if self.pair_role not in {PairRole.BASELINE_TO_INITIAL, PairRole.INITIAL_TO_MODIFIED}:
                raise ValueError("pair comparison requires a formal upload pair role")
            if self.identity_applicability is not IdentityApplicability.REQUIRED:
                raise ValueError("pair comparison identity applicability must be REQUIRED")
            if self.identity_assessment is None:
                raise ValueError("pair comparison requires identity assessment")
            if self.comparison_mode is None or self.artifact_scope is None:
                raise ValueError("pair comparison requires mode and artifact scope")
            assessment_status = getattr(self.identity_assessment, "status", None)
            if type(assessment_status) is not IdentityStatus:
                raise ValueError("identity assessment status must be IdentityStatus")
            expected_mode = (
                ComparisonMode.DATASET_REPLACEMENT
                if assessment_status is IdentityStatus.DIFFERENT_PROJECT
                else ComparisonMode.DETAILED
            )
            if self.comparison_mode is not expected_mode:
                raise ValueError("comparison_mode must be derived from identity assessment")
            if self.trusted_flow_binding is not None:
                raise ValueError("pair comparison forbids trusted flow binding")
            if self.input_completeness is InputCompleteness.MODIFIED_ONLY and self.pair_role is not PairRole.INITIAL_TO_MODIFIED:
                raise ValueError("MODIFIED_ONLY requires INITIAL_TO_MODIFIED role")
            return

        expected_role = (
            PairRole.HISTORY if self.view_kind is PairViewKind.HISTORY else PairRole.ARCHIVE_REPLAY
        )
        if self.pair_role is not expected_role:
            raise ValueError("replay view requires matching pair role")
        if self.input_completeness is not InputCompleteness.FULL:
            raise ValueError("history and archive replay require FULL input")
        if self.comparison_mode is not ComparisonMode.DETAILED or self.artifact_scope is None:
            raise ValueError("history and archive replay require DETAILED mode and artifact scope")
        if self.identity_applicability is not IdentityApplicability.NOT_APPLICABLE:
            raise ValueError("history and archive identity applicability must be NOT_APPLICABLE")
        if self.identity_assessment is not None or self.continuation_binding is not None:
            raise ValueError("history and archive replay forbid identity assessment and continuation")
        if self.trusted_flow_binding is None or self.trusted_flow_binding.view_kind is not self.view_kind:
            raise ValueError("history and archive replay require matching trusted flow binding")


@dataclass(frozen=True, slots=True)
class TableComparisonTask:
    """One table pair; readers remain unopened until a later comparison stage."""

    table_name: str
    before_descriptor: SnapshotTableDescriptor | None
    current_descriptor: SnapshotTableDescriptor | None
    before_table: SnapshotTable | None
    current_table: SnapshotTable | None
    artifact_scope: ArtifactScope
    policy: ComparisonTablePolicy | None = None

    def __post_init__(self) -> None:
        canonical_name = _require_canonical_table_name(self.table_name)
        if self.before_descriptor is None and self.before_table is not None:
            raise ValueError("before_table requires before_descriptor")
        if self.current_descriptor is None and self.current_table is not None:
            raise ValueError("current_table requires current_descriptor")
        if self.before_descriptor is not None:
            if type(self.before_descriptor) is not SnapshotTableDescriptor:
                raise ValueError("before_descriptor must be SnapshotTableDescriptor or None")
            if canonicalize_identifier(self.before_descriptor.table_name) != canonical_name:
                raise ValueError("before descriptor table name must match task")
        if self.current_descriptor is not None:
            if type(self.current_descriptor) is not SnapshotTableDescriptor:
                raise ValueError("current_descriptor must be SnapshotTableDescriptor or None")
            if canonicalize_identifier(self.current_descriptor.table_name) != canonical_name:
                raise ValueError("current descriptor table name must match task")
        if self.before_table is not None:
            if type(self.before_table) is not SnapshotTable:
                raise ValueError("before_table must be SnapshotTable or None")
            if self.before_table.descriptor != self.before_descriptor:
                raise ValueError("before_table descriptor must match before_descriptor")
        if self.current_table is not None:
            if type(self.current_table) is not SnapshotTable:
                raise ValueError("current_table must be SnapshotTable or None")
            if self.current_table.descriptor != self.current_descriptor:
                raise ValueError("current_table descriptor must match current_descriptor")
        if type(self.artifact_scope) is not ArtifactScope:
            raise ValueError("artifact_scope must be ArtifactScope")
        if self.policy is None:
            object.__setattr__(
                self,
                "policy",
                ComparisonTablePolicy(table_name=canonical_name),
            )
        elif type(self.policy) is not ComparisonTablePolicy:
            raise ValueError("policy must be ComparisonTablePolicy or None")
        elif self.policy.table_name != canonical_name:
            raise ValueError("policy table name must match task")


@dataclass(frozen=True, slots=True)
class ComparisonPlan:
    """Detailed comparison plan produced without opening any table reader."""

    pair_id: str
    view_kind: PairViewKind
    pair_role: PairRole
    before: BoundSnapshotInput
    current: BoundSnapshotInput
    comparison_mode: ComparisonMode
    artifact_scope: ArtifactScope
    identity_status: IdentityStatus
    assessment_digest: DigestRef | None
    tasks: tuple[TableComparisonTask, ...]
    diagnostics: tuple[str, ...] = ()
    comparison_options: ComparisonOptions = ()
    contract_versions: ContractVersions = DEFAULT_CONTRACT_VERSIONS

    def __post_init__(self) -> None:
        _require_opaque_id(self.pair_id, "pair_id")
        if self.view_kind not in {PairViewKind.PAIR_COMPARISON, PairViewKind.HISTORY, PairViewKind.ARCHIVE_REPLAY}:
            raise ValueError("comparison plan requires a pair or replay view")
        if type(self.pair_role) is not PairRole:
            raise ValueError("pair_role must be PairRole")
        if type(self.before) is not BoundSnapshotInput or type(self.current) is not BoundSnapshotInput:
            raise ValueError("comparison plan requires bound before and current")
        if self.comparison_mode is not ComparisonMode.DETAILED:
            raise ValueError("comparison plan only represents DETAILED execution")
        if type(self.artifact_scope) is not ArtifactScope:
            raise ValueError("artifact_scope must be ArtifactScope")
        if type(self.identity_status) is not IdentityStatus:
            raise ValueError("identity_status must be IdentityStatus")
        if self.assessment_digest is not None and type(self.assessment_digest) is not DigestRef:
            raise ValueError("assessment_digest must be DigestRef or None")
        if type(self.tasks) is not tuple:
            raise ValueError("tasks must be a tuple")
        seen: set[str] = set()
        for task in self.tasks:
            if type(task) is not TableComparisonTask:
                raise ValueError("tasks must contain TableComparisonTask")
            if task.table_name in seen:
                raise ValueError("tasks must not repeat table_name")
            seen.add(task.table_name)
        _require_diagnostic_strings(self.diagnostics)
        _validate_options(self.comparison_options, "comparison_options")
        _validate_contract_versions(self.contract_versions)


@dataclass(frozen=True, slots=True)
class PairExecutionResultBase:
    """Common immutable result envelope for the S2/S3/S5 result union."""

    pair_id: str
    status: PairResultStatus
    facts: ComparisonFacts | None = None
    records_closure: ComparisonRecordsClosure | None = None
    diagnostics: tuple[str, ...] = ()
    kind: ClassVar[PairResultKind]

    def __post_init__(self) -> None:
        _require_opaque_id(self.pair_id, "pair_id")
        if type(self.status) is not PairResultStatus:
            raise ValueError("status must be PairResultStatus")
        _require_diagnostic_strings(self.diagnostics)


@dataclass(frozen=True, slots=True)
class InitialSnapshotResult(PairExecutionResultBase):
    kind: ClassVar[PairResultKind] = PairResultKind.INITIAL_SNAPSHOT

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.status is not PairResultStatus.NOT_APPLICABLE:
            raise ValueError("initial snapshot result status must be NOT_APPLICABLE")
        if self.facts is not None or self.records_closure is not None:
            raise ValueError("initial snapshot result forbids facts and records closure")


@dataclass(frozen=True, slots=True)
class DetailedFactsResult(PairExecutionResultBase):
    kind: ClassVar[PairResultKind] = PairResultKind.DETAILED_FACTS

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.status not in {
            PairResultStatus.UNCHANGED,
            PairResultStatus.BUSINESS_EQUIVALENT,
            PairResultStatus.CHANGED,
            PairResultStatus.DEGRADED,
        }:
            raise ValueError("detailed facts result has an invalid status")
        if self.facts is None:
            raise ValueError("detailed facts result requires facts")


@dataclass(frozen=True, slots=True)
class DatasetReplacementResult(PairExecutionResultBase):
    kind: ClassVar[PairResultKind] = PairResultKind.DATASET_REPLACEMENT

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.status is not PairResultStatus.CHANGED:
            raise ValueError("dataset replacement result status must be CHANGED")
        if self.facts is not None and self.facts.records_ref is not None:
            raise ValueError("dataset replacement forbids records_ref")
        if self.records_closure is not None:
            raise ValueError("dataset replacement forbids records closure")


@dataclass(frozen=True, slots=True)
class IdentityGateBlockedResult(PairExecutionResultBase):
    kind: ClassVar[PairResultKind] = PairResultKind.IDENTITY_GATE_BLOCKED

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.status is not PairResultStatus.DEGRADED:
            raise ValueError("identity gate result status must be DEGRADED")
        if not self.diagnostics:
            raise ValueError("identity gate result requires diagnostics")
        if self.facts is not None or self.records_closure is not None:
            raise ValueError("identity gate result forbids facts and records closure")


@dataclass(frozen=True, slots=True)
class CancelledResult(PairExecutionResultBase):
    kind: ClassVar[PairResultKind] = PairResultKind.CANCELLED

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.status is not PairResultStatus.CANCELLED:
            raise ValueError("cancelled result status must be CANCELLED")
        if not self.diagnostics:
            raise ValueError("cancelled result requires diagnostics")
        if self.facts is not None or self.records_closure is not None:
            raise ValueError("cancelled result forbids facts and records closure")


@dataclass(frozen=True, slots=True)
class FailedResult(PairExecutionResultBase):
    kind: ClassVar[PairResultKind] = PairResultKind.FAILED

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.status is not PairResultStatus.FAILED:
            raise ValueError("failed result status must be FAILED")
        if not self.diagnostics:
            raise ValueError("failed result requires diagnostics")
        if self.facts is not None or self.records_closure is not None:
            raise ValueError("failed result forbids facts and records closure")


PairExecutionResult: TypeAlias = (
    InitialSnapshotResult
    | DetailedFactsResult
    | DatasetReplacementResult
    | IdentityGateBlockedResult
    | CancelledResult
    | FailedResult
)


def _require_non_negative_int_fields(value: object, labels: tuple[str, ...]) -> None:
    for label in labels:
        item = getattr(value, label)
        if type(item) is not int or item < 0:
            raise ValueError(f"{label} must be a non-negative int")


def _canonical_table_map(
    descriptors: tuple[SnapshotTableDescriptor, ...],
) -> dict[str, SnapshotTableDescriptor]:
    result: dict[str, SnapshotTableDescriptor] = {}
    for descriptor in descriptors:
        canonical_name = _require_canonical_table_name(descriptor.table_name)
        if canonical_name in result:
            raise ValueError("table names must be unique after canonicalization")
        result[canonical_name] = descriptor
    return result


def _require_canonical_table_name(value: object) -> str:
    if type(value) is not str or value == "":
        raise ValueError("table_name must be a non-empty string")
    try:
        return canonicalize_identifier(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("table_name must be a canonical identifier") from exc


def _require_canonical_column_name(value: object) -> str:
    if type(value) is not str or value == "":
        raise ValueError("column_name must be a non-empty string")
    try:
        return canonicalize_identifier(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("column_name must be a canonical identifier") from exc


def _require_opaque_id(value: object, label: str) -> None:
    if type(value) is not str or value == "":
        raise ValueError(f"{label} must be a non-empty string")
    if value.startswith("/") or "\\" in value or "\x00" in value:
        raise ValueError(f"{label} must not be a path-shaped identity")


def _require_diagnostic_strings(value: object) -> None:
    if type(value) is not tuple:
        raise ValueError("diagnostics must be a tuple")
    for item in value:
        if type(item) is not str or item == "":
            raise ValueError("diagnostics must contain non-empty strings")


def _validate_options(value: object, label: str) -> None:
    if type(value) is not tuple:
        raise ValueError(f"{label} must be a tuple")
    seen: set[str] = set()
    for item in value:
        if type(item) is not tuple or len(item) != 2:
            raise ValueError(f"{label} must contain key/value pairs")
        key, option = item
        if type(key) is not str or key == "":
            raise ValueError(f"{label} keys must be non-empty strings")
        if key in seen:
            raise ValueError(f"{label} must not repeat keys")
        seen.add(key)
        if option is not None and type(option) not in {str, int, bool}:
            raise ValueError(f"{label} values must be scalar JSON values")


def _validate_contract_versions(value: object) -> None:
    if type(value) is not tuple or not value:
        raise ValueError("contract_versions must be a non-empty tuple")
    seen: set[str] = set()
    for item in value:
        if type(item) is not tuple or len(item) != 2:
            raise ValueError("contract_versions must contain key/value pairs")
        key, version = item
        if type(key) is not str or key == "":
            raise ValueError("contract version keys must be non-empty strings")
        if key in seen:
            raise ValueError("contract_versions must not repeat keys")
        seen.add(key)
        if type(version) not in {str, int} or version == "":
            raise ValueError("contract version values must be non-empty strings or positive ints")


@dataclass(frozen=True, slots=True)
class ComparisonBatchRequest:
    """Provider-neutral request; the request bytes are opaque to the port."""

    table_name: str
    descriptor: SnapshotTableDescriptor
    reader: SnapshotTableBatchReader
    request_jcs: bytes = b""

    def __post_init__(self) -> None:
        if type(self.table_name) is not str or self.table_name == "":
            raise ValueError("table_name must be a non-empty string")
        if self.descriptor.table_name != self.table_name:
            raise ValueError("table_name must match descriptor")
        if not isinstance(self.reader, SnapshotTableBatchReader):
            raise ValueError("reader must implement SnapshotTableBatchReader")
        if type(self.request_jcs) is not bytes:
            raise ValueError("request_jcs must be bytes")


@dataclass(frozen=True, slots=True)
class ComparisonBatchResult:
    """Coarse provider output; semantic facts are owned by later R5 stages."""

    provider_id: str
    output_stream: pa.RecordBatchReader
    result_jcs: bytes
    input_metadata: SnapshotTableBatchMetadata

    def __post_init__(self) -> None:
        if type(self.provider_id) is not str or self.provider_id == "":
            raise ValueError("provider_id must be a non-empty string")
        if not isinstance(self.output_stream, pa.RecordBatchReader):
            raise ValueError("output_stream must be pyarrow.RecordBatchReader")
        if type(self.result_jcs) is not bytes:
            raise ValueError("result_jcs must be bytes")
        if type(self.input_metadata) is not SnapshotTableBatchMetadata:
            raise ValueError("input_metadata must be SnapshotTableBatchMetadata")


@runtime_checkable
class ComparisonBatchProvider(Protocol):
    """Provider port shared by Python reference and Rust native implementations."""

    @property
    def provider_id(self) -> str:
        """Stable diagnostic identifier; it is not a semantic digest input."""

    def execute(self, request: ComparisonBatchRequest) -> ComparisonBatchResult:
        """Consume one Arrow stream and return one coarse-grained Arrow stream."""


NativeBatchCompute = Callable[
    [bytes, pa.RecordBatch | pa.Table | pa.RecordBatchReader],
    tuple[pa.RecordBatchReader, bytes],
]


def validate_batch_reader(reader: object) -> SnapshotTableBatchReader:
    """Validate an injected reader at the provider seam without opening rows."""

    if not isinstance(reader, SnapshotTableBatchReader):
        raise TypeError("reader must implement SnapshotTableBatchReader")
    metadata = reader.metadata()
    if metadata.batch_reader_contract_version != BATCH_READER_CONTRACT_VERSION:
        raise ValueError("unsupported batch reader contract version")
    if metadata.batch_schema_metadata_version != BATCH_SCHEMA_METADATA_VERSION:
        raise ValueError("unsupported batch schema metadata version")
    return reader
