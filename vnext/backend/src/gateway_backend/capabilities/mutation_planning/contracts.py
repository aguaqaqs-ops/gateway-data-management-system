"""Public contracts owned by the Mutation Planning capability.

Owner: Mutation Planning capability
Authority: docs/backend-vnext/refactoring/formal/contracts/storage-mutation-and-change-set.md
Downstream consumers may import this module only.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import Callable, Protocol, TypeAlias, runtime_checkable

from gateway_shared_kernel import DigestRef, canonicalize_identifier, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef
from gateway_backend.capabilities.storage_projection.contracts import (
    CanonicalKeyPolicy,
    CanonicalizationManifest,
    CanonicalizationManifestTable,
    MAX_REPLAY_SQL_BYTES as _STORAGE_PROJECTION_MAX_REPLAY_SQL_BYTES,
    StorageRuleView,
)

MUTATION_CONTRACT_VERSION = "backend-vnext/storage-mutation/v1"
CHANGE_SET_ARTIFACT_CONTRACT_VERSION = "backend-vnext/change-set-artifact/v1"
CHANGE_SET_MANIFEST_CONTRACT_VERSION = "backend-vnext/change-set-manifest/v1"
THRESHOLD_POLICY_VERSION = "backend-vnext/mutation-threshold/v1"
RENDERER_CAPABILITY_CONTRACT_VERSION = "backend-vnext/mutation-renderer-capability/v1"
CANONICAL_ENCODING_VERSION = 1
DEFAULT_MUTATION_POLICY = "REBUILD_ALWAYS"
MAX_PATCH_CHANGED_ROWS = 1_000
MAX_PATCH_CHANGE_RATIO = "0.05"
_MIB = 1024 * 1024
MAX_CHANGE_SET_JSON_BYTES = 16 * _MIB
MAX_REPLAY_SQL_BYTES = _STORAGE_PROJECTION_MAX_REPLAY_SQL_BYTES
CHANGE_SET_MANIFEST_MEDIA_TYPE = "application/vnd.gateway.change-set-manifest+json"
CHANGE_SET_CLOSURE_MEDIA_TYPE = "application/vnd.gateway.change-set-closure+json"

CanonicalCellValue: TypeAlias = dict[str, object]


class MutationPolicy(StrEnum):
    REBUILD_ALWAYS = "REBUILD_ALWAYS"
    ADAPTIVE_PATCH = "ADAPTIVE_PATCH"


class TableMutationKind(StrEnum):
    REBUILD_TABLE = "REBUILD_TABLE"
    PATCH_DML = "PATCH_DML"
    NOOP = "NOOP"


class RowMutationOperation(StrEnum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


_OPERATION_ORDER = {
    RowMutationOperation.DELETE: 0,
    RowMutationOperation.UPDATE: 1,
    RowMutationOperation.INSERT: 2,
}


class MutationPlanStatus(StrEnum):
    READY = "READY"
    NOOP = "NOOP"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    FAILED = "FAILED"


class MutationFailureCode(StrEnum):
    FAILED = "FAILED"
    TARGET_CAPABILITY_UNSUPPORTED = "TARGET_CAPABILITY_UNSUPPORTED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    DRIFT_DETECTED = "DRIFT_DETECTED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    RESOURCE_EXCEEDED = "RESOURCE_EXCEEDED"


class MutationTargetKind(StrEnum):
    CANONICAL_REPOSITORY_REPLAY = "CANONICAL_REPOSITORY_REPLAY"
    EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"


_ALLOWED_CELL_VALUE_KINDS = frozenset(
    {
        "null",
        "boolean",
        "signed-integer",
        "unsigned-integer",
        "decimal",
        "float32",
        "float64",
        "string",
        "binary",
        "bit",
        "date",
        "datetime",
        "timestamp",
        "time-duration",
        "source-literal-anomaly",
    }
)

_NULL_CELL_KEYS = frozenset({"kind"})
_BOOLEAN_CELL_KEYS = frozenset({"kind", "value"})
_DECIMAL_CELL_KEYS = frozenset({"kind", "decimal"})
_FLOAT_CELL_KEYS = frozenset({"kind", "bits_hex"})
_STRING_CELL_KEYS = frozenset({"kind", "text"})
_BINARY_CELL_KEYS = frozenset({"kind", "bytes_base64url"})
_ANOMALY_CELL_KEYS = frozenset({"kind", "envelope"})

_MANIFEST_DOCUMENT_KEYS = frozenset(
    {
        "artifact_contract_version",
        "base_repository_ref_digest",
        "canonical_encoding_version",
        "change_set_digest",
        "manifest_contract_version",
        "mutation_contract_version",
        "mutation_policy",
        "renderer_capability",
        "source_identity_digest",
        "storage_projection_digest",
        "table_ruleset_digest",
        "table_summaries",
        "target_identity",
        "threshold_policy",
    }
)

_CLOSURE_DOCUMENT_KEYS = frozenset({"manifest", "mutations"})
_MUTATION_DOCUMENT_KEYS = frozenset(
    {
        "after_image",
        "before_row_digest",
        "canonical_storage_key",
        "canonical_table",
        "operation",
    }
)
_THRESHOLD_POLICY_KEYS = frozenset(
    {
        "max_patch_change_ratio",
        "max_patch_changed_rows",
        "policy_version",
    }
)
_RENDERER_CAPABILITY_KEYS = frozenset(
    {
        "capability_contract_version",
        "capability_digest",
        "capability_version",
        "target_kind",
    }
)


@runtime_checkable
class MutationCancellationProbe(Protocol):
    def is_set(self) -> bool:
        ...


@dataclass(frozen=True, slots=True)
class MutationExecutionContext:
    """Non-semantic cancellation/deadline context supplied by the caller."""

    cancel_requested: MutationCancellationProbe | None = None
    deadline_monotonic: float | None = None
    clock: Callable[[], float] = monotonic

    def __post_init__(self) -> None:
        if self.cancel_requested is not None and not isinstance(
            self.cancel_requested, MutationCancellationProbe
        ):
            raise ValueError("cancel_requested must implement MutationCancellationProbe")
        if self.deadline_monotonic is not None:
            if type(self.deadline_monotonic) is not float or not math.isfinite(
                self.deadline_monotonic
            ):
                raise ValueError("deadline_monotonic must be a finite float or None")
        if not callable(self.clock):
            raise ValueError("clock must be callable")

    def cancellation_requested(self) -> bool:
        return self.cancel_requested is not None and self.cancel_requested.is_set()

    def deadline_expired(self) -> bool:
        return self.deadline_monotonic is not None and self.clock() >= self.deadline_monotonic


@dataclass(frozen=True, slots=True)
class MutationThresholdPolicy:
    policy_version: str = THRESHOLD_POLICY_VERSION
    max_patch_changed_rows: int = MAX_PATCH_CHANGED_ROWS
    max_patch_change_ratio: str = MAX_PATCH_CHANGE_RATIO

    def __post_init__(self) -> None:
        if self.policy_version != THRESHOLD_POLICY_VERSION:
            raise ValueError("unsupported threshold policy version")
        if (
            type(self.max_patch_changed_rows) is not int
            or isinstance(self.max_patch_changed_rows, bool)
            or self.max_patch_changed_rows <= 0
        ):
            raise ValueError("max_patch_changed_rows must be a positive int")
        if type(self.max_patch_change_ratio) is not str or self.max_patch_change_ratio == "":
            raise ValueError("max_patch_change_ratio must be a non-empty string")
        if self.max_patch_change_ratio != MAX_PATCH_CHANGE_RATIO:
            raise ValueError("max_patch_change_ratio must match the frozen S0 value")

    def to_document(self) -> dict[str, object]:
        return {
            "max_patch_change_ratio": self.max_patch_change_ratio,
            "max_patch_changed_rows": self.max_patch_changed_rows,
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True, slots=True)
class RendererCapabilityDeclaration:
    target_kind: MutationTargetKind
    capability_version: str
    capability_digest: DigestRef
    capability_contract_version: str = RENDERER_CAPABILITY_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if type(self.target_kind) is not MutationTargetKind:
            raise ValueError("target_kind must be MutationTargetKind")
        if type(self.capability_version) is not str or self.capability_version == "":
            raise ValueError("capability_version must be a non-empty string")
        if type(self.capability_digest) is not DigestRef:
            raise ValueError("capability_digest must be DigestRef")
        if self.capability_contract_version != RENDERER_CAPABILITY_CONTRACT_VERSION:
            raise ValueError("unsupported renderer capability contract version")

    def to_document(self) -> dict[str, object]:
        return {
            "capability_contract_version": self.capability_contract_version,
            "capability_digest": self.capability_digest.value,
            "capability_version": self.capability_version,
            "target_kind": self.target_kind.value,
        }


@dataclass(frozen=True, slots=True)
class MutationSourceIdentity:
    source_identity_digest: DigestRef

    def __post_init__(self) -> None:
        if type(self.source_identity_digest) is not DigestRef:
            raise ValueError("source_identity_digest must be DigestRef")


@dataclass(frozen=True, slots=True)
class MutationRepositoryBase:
    base_repository_ref_digest: DigestRef

    def __post_init__(self) -> None:
        if type(self.base_repository_ref_digest) is not DigestRef:
            raise ValueError("base_repository_ref_digest must be DigestRef")


@dataclass(frozen=True, slots=True)
class MutationProjectionBinding:
    before_storage_projection_digest: DigestRef
    after_storage_projection_digest: DigestRef
    before_manifest_digest: DigestRef
    after_manifest_digest: DigestRef
    table_ruleset_digest: DigestRef

    def __post_init__(self) -> None:
        for label in (
            "before_storage_projection_digest",
            "after_storage_projection_digest",
            "before_manifest_digest",
            "after_manifest_digest",
            "table_ruleset_digest",
        ):
            if type(getattr(self, label)) is not DigestRef:
                raise ValueError(f"{label} must be DigestRef")


@dataclass(frozen=True, slots=True)
class MutationPlanningInput:
    mutation_policy: MutationPolicy
    projection_binding: MutationProjectionBinding
    repository_base: MutationRepositoryBase
    source_identity: MutationSourceIdentity
    renderer_capability: RendererCapabilityDeclaration
    threshold_policy: MutationThresholdPolicy = MutationThresholdPolicy()
    context: MutationExecutionContext | None = None
    mutation_contract_version: str = MUTATION_CONTRACT_VERSION
    canonical_encoding_version: int = CANONICAL_ENCODING_VERSION

    def __post_init__(self) -> None:
        if type(self.mutation_policy) is not MutationPolicy:
            raise ValueError("mutation_policy must be MutationPolicy")
        if type(self.projection_binding) is not MutationProjectionBinding:
            raise ValueError("projection_binding must be MutationProjectionBinding")
        if type(self.repository_base) is not MutationRepositoryBase:
            raise ValueError("repository_base must be MutationRepositoryBase")
        if type(self.source_identity) is not MutationSourceIdentity:
            raise ValueError("source_identity must be MutationSourceIdentity")
        if type(self.renderer_capability) is not RendererCapabilityDeclaration:
            raise ValueError("renderer_capability must be RendererCapabilityDeclaration")
        if type(self.threshold_policy) is not MutationThresholdPolicy:
            raise ValueError("threshold_policy must be MutationThresholdPolicy")
        if self.context is not None and type(self.context) is not MutationExecutionContext:
            raise ValueError("context must be MutationExecutionContext or None")
        if self.mutation_contract_version != MUTATION_CONTRACT_VERSION:
            raise ValueError("unsupported mutation contract version")
        if self.canonical_encoding_version != CANONICAL_ENCODING_VERSION:
            raise ValueError("canonical_encoding_version must be 1")


@dataclass(frozen=True, slots=True)
class TableMutationSummary:
    canonical_table: str
    operation: TableMutationKind
    changed_row_count: int
    before_row_count: int
    after_row_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "canonical_table", canonicalize_identifier(self.canonical_table)
        )
        if type(self.operation) is not TableMutationKind:
            raise ValueError("operation must be TableMutationKind")
        for label in ("changed_row_count", "before_row_count", "after_row_count"):
            value = getattr(self, label)
            if type(value) is not int or isinstance(value, bool) or value < 0:
                raise ValueError(f"{label} must be a non-negative int")

    def to_document(self) -> dict[str, object]:
        return {
            "after_row_count": self.after_row_count,
            "before_row_count": self.before_row_count,
            "canonical_table": self.canonical_table,
            "changed_row_count": self.changed_row_count,
            "operation": self.operation.value,
        }


@dataclass(frozen=True, slots=True)
class StorageMutationPlan:
    mutation_plan_identity_digest: DigestRef
    plan_status: MutationPlanStatus
    table_summaries: tuple[TableMutationSummary, ...]
    planning_input: MutationPlanningInput
    requires_confirmation: bool = False
    confirmation_reason: str | None = None
    failure_code: MutationFailureCode | None = None

    def __post_init__(self) -> None:
        if type(self.mutation_plan_identity_digest) is not DigestRef:
            raise ValueError("mutation_plan_identity_digest must be DigestRef")
        if type(self.plan_status) is not MutationPlanStatus:
            raise ValueError("plan_status must be MutationPlanStatus")
        _validate_table_summaries(self.table_summaries)
        if type(self.planning_input) is not MutationPlanningInput:
            raise ValueError("planning_input must be MutationPlanningInput")
        if type(self.requires_confirmation) is not bool:
            raise ValueError("requires_confirmation must be bool")
        if self.confirmation_reason is not None:
            if type(self.confirmation_reason) is not str or self.confirmation_reason == "":
                raise ValueError("confirmation_reason must be a non-empty string or None")
        if self.failure_code is not None and type(self.failure_code) is not MutationFailureCode:
            raise ValueError("failure_code must be MutationFailureCode or None")
        expected_identity = compute_mutation_plan_identity_digest(self.planning_input)
        if self.mutation_plan_identity_digest != expected_identity:
            raise ValueError("mutation_plan_identity_digest does not match planning input")
        if self.plan_status is MutationPlanStatus.FAILED:
            if self.failure_code is None:
                raise ValueError("FAILED plan requires failure_code")
            return
        if self.plan_status is MutationPlanStatus.CONFIRMATION_REQUIRED:
            if not self.requires_confirmation:
                raise ValueError("CONFIRMATION_REQUIRED plan must set requires_confirmation")
            if self.confirmation_reason is None:
                raise ValueError("CONFIRMATION_REQUIRED plan requires confirmation_reason")
            if self.failure_code is not MutationFailureCode.CONFIRMATION_REQUIRED:
                raise ValueError("CONFIRMATION_REQUIRED plan must use CONFIRMATION_REQUIRED code")
            return
        if self.failure_code is not None:
            raise ValueError("non-failed plan must not carry failure_code")
        if self.plan_status is MutationPlanStatus.NOOP:
            if self.table_summaries:
                raise ValueError("NOOP plan must not carry table summaries")
            if self.requires_confirmation:
                raise ValueError("NOOP plan must not require confirmation")


@dataclass(frozen=True, slots=True)
class CanonicalStorageKey:
    columns: tuple[tuple[str, CanonicalCellValue], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "columns", _canonicalize_cell_columns(self.columns, "key"))

    def to_document(self) -> list[dict[str, object]]:
        return [
            {"column": column, "value": dict(value)} for column, value in self.columns
        ]


@dataclass(frozen=True, slots=True)
class PersistedRowImage:
    columns: tuple[tuple[str, CanonicalCellValue], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "columns", _canonicalize_cell_columns(self.columns, "row"))

    def to_document(self) -> list[dict[str, object]]:
        return [
            {"column": column, "value": dict(value)} for column, value in self.columns
        ]


@dataclass(frozen=True, slots=True)
class ChangeSetMutation:
    canonical_table: str
    operation: RowMutationOperation
    canonical_storage_key: CanonicalStorageKey
    before_row_digest: DigestRef | None = None
    after_image: PersistedRowImage | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "canonical_table", canonicalize_identifier(self.canonical_table)
        )
        if type(self.operation) is not RowMutationOperation:
            raise ValueError("operation must be RowMutationOperation")
        if type(self.canonical_storage_key) is not CanonicalStorageKey:
            raise ValueError("canonical_storage_key must be CanonicalStorageKey")
        if self.operation is RowMutationOperation.INSERT:
            if self.before_row_digest is not None:
                raise ValueError("INSERT must not carry before_row_digest")
            if type(self.after_image) is not PersistedRowImage:
                raise ValueError("INSERT requires after_image")
            return
        if self.operation is RowMutationOperation.UPDATE:
            if type(self.before_row_digest) is not DigestRef:
                raise ValueError("UPDATE requires before_row_digest")
            if type(self.after_image) is not PersistedRowImage:
                raise ValueError("UPDATE requires after_image")
            return
        if self.before_row_digest is None:
            raise ValueError("DELETE requires before_row_digest")
        if self.after_image is not None:
            raise ValueError("DELETE must not carry after_image")

    def to_document(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "canonical_storage_key": self.canonical_storage_key.to_document(),
            "canonical_table": self.canonical_table,
            "operation": self.operation.value,
        }
        if self.before_row_digest is not None:
            payload["before_row_digest"] = self.before_row_digest.value
        if self.after_image is not None:
            payload["after_image"] = self.after_image.to_document()
        return payload


@dataclass(frozen=True, slots=True)
class ChangeSetManifest:
    manifest_contract_version: str
    artifact_contract_version: str
    mutation_contract_version: str
    canonical_encoding_version: int
    source_identity_digest: DigestRef
    base_repository_ref_digest: DigestRef
    target_identity: RendererCapabilityDeclaration
    storage_projection_digest: MutationProjectionBinding
    table_ruleset_digest: DigestRef
    mutation_policy: MutationPolicy
    threshold_policy: MutationThresholdPolicy
    table_summaries: tuple[TableMutationSummary, ...]
    change_set_digest: DigestRef
    renderer_capability: RendererCapabilityDeclaration

    def __post_init__(self) -> None:
        if self.manifest_contract_version != CHANGE_SET_MANIFEST_CONTRACT_VERSION:
            raise ValueError("unsupported change-set manifest contract version")
        if self.artifact_contract_version != CHANGE_SET_ARTIFACT_CONTRACT_VERSION:
            raise ValueError("unsupported change-set artifact contract version")
        if self.mutation_contract_version != MUTATION_CONTRACT_VERSION:
            raise ValueError("unsupported mutation contract version")
        if self.canonical_encoding_version != CANONICAL_ENCODING_VERSION:
            raise ValueError("canonical_encoding_version must be 1")
        for label in ("source_identity_digest", "base_repository_ref_digest", "table_ruleset_digest"):
            if type(getattr(self, label)) is not DigestRef:
                raise ValueError(f"{label} must be DigestRef")
        if type(self.target_identity) is not RendererCapabilityDeclaration:
            raise ValueError("target_identity must be RendererCapabilityDeclaration")
        if type(self.storage_projection_digest) is not MutationProjectionBinding:
            raise ValueError("storage_projection_digest must be MutationProjectionBinding")
        if type(self.mutation_policy) is not MutationPolicy:
            raise ValueError("mutation_policy must be MutationPolicy")
        if type(self.threshold_policy) is not MutationThresholdPolicy:
            raise ValueError("threshold_policy must be MutationThresholdPolicy")
        _validate_table_summaries(self.table_summaries)
        if type(self.change_set_digest) is not DigestRef:
            raise ValueError("change_set_digest must be DigestRef")
        if type(self.renderer_capability) is not RendererCapabilityDeclaration:
            raise ValueError("renderer_capability must be RendererCapabilityDeclaration")
        if self.target_identity != self.renderer_capability:
            raise ValueError("target_identity must match renderer_capability")

    def to_document(self) -> dict[str, object]:
        return {
            "artifact_contract_version": self.artifact_contract_version,
            "base_repository_ref_digest": self.base_repository_ref_digest.value,
            "canonical_encoding_version": self.canonical_encoding_version,
            "change_set_digest": self.change_set_digest.value,
            "manifest_contract_version": self.manifest_contract_version,
            "mutation_contract_version": self.mutation_contract_version,
            "mutation_policy": self.mutation_policy.value,
            "renderer_capability": self.renderer_capability.to_document(),
            "source_identity_digest": self.source_identity_digest.value,
            "storage_projection_digest": _projection_binding_document(
                self.storage_projection_digest
            ),
            "table_ruleset_digest": self.table_ruleset_digest.value,
            "table_summaries": [item.to_document() for item in self.table_summaries],
            "target_identity": self.target_identity.to_document(),
            "threshold_policy": self.threshold_policy.to_document(),
        }


@dataclass(frozen=True, slots=True)
class ChangeSetArtifact:
    manifest: ChangeSetManifest
    mutations: tuple[ChangeSetMutation, ...]

    def __post_init__(self) -> None:
        if type(self.manifest) is not ChangeSetManifest:
            raise ValueError("manifest must be ChangeSetManifest")
        if type(self.mutations) is not tuple:
            raise ValueError("mutations must be a tuple")
        for item in self.mutations:
            if type(item) is not ChangeSetMutation:
                raise ValueError("mutations must contain ChangeSetMutation")
        validate_change_set_ordering(self.mutations)
        expected_digest = compute_change_set_digest(self.mutations)
        if self.manifest.change_set_digest != expected_digest:
            raise ValueError("manifest change_set_digest does not match mutations")


@dataclass(frozen=True, slots=True)
class ChangeSetClosure:
    manifest: ChangeSetManifest
    mutations: tuple[ChangeSetMutation, ...]
    closure_digest: DigestRef | None = None

    def __post_init__(self) -> None:
        artifact = ChangeSetArtifact(manifest=self.manifest, mutations=self.mutations)
        object.__setattr__(self, "manifest", artifact.manifest)
        expected_closure = compute_change_set_closure_digest(artifact)
        if self.closure_digest is None:
            object.__setattr__(self, "closure_digest", expected_closure)
        elif self.closure_digest != expected_closure:
            raise ValueError("closure_digest does not match canonical closure document")


@dataclass(frozen=True, slots=True)
class MutationKeyedRow:
    key: CanonicalStorageKey
    image: PersistedRowImage
    row_digest: DigestRef

    def __post_init__(self) -> None:
        if type(self.key) is not CanonicalStorageKey:
            raise ValueError("key must be CanonicalStorageKey")
        if type(self.image) is not PersistedRowImage:
            raise ValueError("image must be PersistedRowImage")
        if type(self.row_digest) is not DigestRef:
            raise ValueError("row_digest must be DigestRef")


@dataclass(frozen=True, slots=True)
class MutationTableSnapshot:
    manifest_table: CanonicalizationManifestTable
    storage_view: StorageRuleView
    rows: tuple[MutationKeyedRow, ...] = ()

    def __post_init__(self) -> None:
        if type(self.manifest_table) is not CanonicalizationManifestTable:
            raise ValueError("manifest_table must be CanonicalizationManifestTable")
        if type(self.storage_view) is not StorageRuleView:
            raise ValueError("storage_view must be StorageRuleView")
        if self.manifest_table.name != self.storage_view.canonical_table:
            raise ValueError("manifest_table name must match storage_view canonical_table")
        if type(self.rows) is not tuple:
            raise ValueError("rows must be a tuple")
        keyless = (
            self.storage_view.canonical_key_policy
            in {
                CanonicalKeyPolicy.EXPLICIT_KEYLESS,
                CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS,
            }
            and not self.storage_view.canonical_key_columns
        )
        previous_sort_key: tuple[bytes, str] | None = None
        seen: set[bytes] = set()
        for item in self.rows:
            if type(item) is not MutationKeyedRow:
                raise ValueError("rows must contain MutationKeyedRow")
            key_bytes = canonicalize_json_value(item.key.to_document())
            sort_key = (key_bytes, item.row_digest.value if keyless else "")
            if not keyless and key_bytes in seen:
                raise ValueError("rows must not repeat canonical storage keys")
            if previous_sort_key is not None and sort_key < previous_sort_key:
                raise ValueError("rows must use canonical key order")
            previous_sort_key = sort_key
            seen.add(key_bytes)


@dataclass(frozen=True, slots=True)
class MutationPlanningRequest:
    planning_input: MutationPlanningInput
    before_manifest: CanonicalizationManifest
    after_manifest: CanonicalizationManifest
    before_tables: tuple[MutationTableSnapshot, ...] = ()
    after_tables: tuple[MutationTableSnapshot, ...] = ()
    destructive_confirmation_granted: bool = False

    def __post_init__(self) -> None:
        if type(self.planning_input) is not MutationPlanningInput:
            raise ValueError("planning_input must be MutationPlanningInput")
        if type(self.before_manifest) is not CanonicalizationManifest:
            raise ValueError("before_manifest must be CanonicalizationManifest")
        if type(self.after_manifest) is not CanonicalizationManifest:
            raise ValueError("after_manifest must be CanonicalizationManifest")
        binding = self.planning_input.projection_binding
        if self.before_manifest.manifest_digest != binding.before_manifest_digest:
            raise ValueError("before_manifest digest must match projection binding")
        if self.after_manifest.manifest_digest != binding.after_manifest_digest:
            raise ValueError("after_manifest digest must match projection binding")
        if type(self.destructive_confirmation_granted) is not bool:
            raise ValueError("destructive_confirmation_granted must be bool")
        _validate_table_snapshots(self.before_tables, "before_tables")
        _validate_table_snapshots(self.after_tables, "after_tables")


@dataclass(frozen=True, slots=True)
class PublishedChangeSetClosure:
    closure_ref: ArtifactRef
    closure_digest: DigestRef

    def __post_init__(self) -> None:
        if type(self.closure_ref) is not ArtifactRef:
            raise ValueError("closure_ref must be ArtifactRef")
        if type(self.closure_digest) is not DigestRef:
            raise ValueError("closure_digest must be DigestRef")


@dataclass(frozen=True, slots=True)
class MutationPlanningResult:
    status: MutationPlanStatus
    plan: StorageMutationPlan | None = None
    change_set_closure: ChangeSetClosure | None = None
    failure_code: MutationFailureCode | None = None
    published_closure: PublishedChangeSetClosure | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not MutationPlanStatus:
            raise ValueError("status must be MutationPlanStatus")
        if self.plan is not None and type(self.plan) is not StorageMutationPlan:
            raise ValueError("plan must be StorageMutationPlan or None")
        if self.change_set_closure is not None and type(self.change_set_closure) is not ChangeSetClosure:
            raise ValueError("change_set_closure must be ChangeSetClosure or None")
        if self.failure_code is not None and type(self.failure_code) is not MutationFailureCode:
            raise ValueError("failure_code must be MutationFailureCode or None")
        if self.published_closure is not None and type(self.published_closure) is not PublishedChangeSetClosure:
            raise ValueError("published_closure must be PublishedChangeSetClosure or None")
        if self.status is not MutationPlanStatus.READY and self.published_closure is not None:
            raise ValueError("non-READY result must not publish closure refs")
        if self.status is MutationPlanStatus.FAILED:
            if self.failure_code is None:
                raise ValueError("FAILED result requires failure_code")
            if self.change_set_closure is not None:
                raise ValueError("FAILED result must not publish change_set_closure")
            return
        if self.status is MutationPlanStatus.CONFIRMATION_REQUIRED:
            if self.change_set_closure is not None:
                raise ValueError("CONFIRMATION_REQUIRED result must not publish change_set_closure")
            if self.plan is None:
                raise ValueError("CONFIRMATION_REQUIRED result requires diagnostic plan")
            return
        if self.status is MutationPlanStatus.NOOP:
            if self.change_set_closure is not None:
                raise ValueError("NOOP result must not publish change_set_closure")
            if self.plan is None or self.plan.plan_status is not MutationPlanStatus.NOOP:
                raise ValueError("NOOP result requires NOOP plan")
            return
        if self.status is MutationPlanStatus.READY:
            if self.plan is None or self.plan.plan_status is not MutationPlanStatus.READY:
                raise ValueError("READY result requires READY plan")
            if self.change_set_closure is None:
                raise ValueError("READY result requires change_set_closure")
            if self.failure_code is not None:
                raise ValueError("READY result must not carry failure_code")


def _validate_table_snapshots(
    value: tuple[MutationTableSnapshot, ...],
    label: str,
) -> None:
    if type(value) is not tuple:
        raise ValueError(f"{label} must be a tuple")
    previous: str | None = None
    seen: set[str] = set()
    for item in value:
        if type(item) is not MutationTableSnapshot:
            raise ValueError(f"{label} must contain MutationTableSnapshot")
        name = item.manifest_table.name
        if name in seen:
            raise ValueError(f"{label} must not repeat table names")
        if previous is not None and name <= previous:
            raise ValueError(f"{label} must use canonical table order")
        previous = name
        seen.add(name)


def mutation_plan_identity_payload(planning_input: MutationPlanningInput) -> dict[str, object]:
    if type(planning_input) is not MutationPlanningInput:
        raise ValueError("planning_input must be MutationPlanningInput")
    binding = planning_input.projection_binding
    return {
        "base_repository_ref_digest": planning_input.repository_base.base_repository_ref_digest.value,
        "canonical_encoding_version": planning_input.canonical_encoding_version,
        "mutation_contract_version": planning_input.mutation_contract_version,
        "mutation_policy": planning_input.mutation_policy.value,
        "renderer_capability": planning_input.renderer_capability.to_document(),
        "source_identity_digest": planning_input.source_identity.source_identity_digest.value,
        "storage_projection_digest": _projection_binding_document(binding),
        "threshold_policy": planning_input.threshold_policy.to_document(),
    }


def compute_mutation_plan_identity_digest(planning_input: MutationPlanningInput) -> DigestRef:
    return raw_blob_digest(canonicalize_json_value(mutation_plan_identity_payload(planning_input)))


def change_set_mutations_payload(
    mutations: Sequence[ChangeSetMutation],
) -> list[dict[str, object]]:
    return [item.to_document() for item in mutations]


def compute_change_set_digest(mutations: Sequence[ChangeSetMutation]) -> DigestRef:
    if any(type(item) is not ChangeSetMutation for item in mutations):
        raise ValueError("mutations must contain ChangeSetMutation")
    validate_change_set_ordering(tuple(mutations))
    return raw_blob_digest(
        canonicalize_json_value({"mutations": change_set_mutations_payload(mutations)})
    )


def change_set_closure_document(artifact: ChangeSetArtifact) -> dict[str, object]:
    if type(artifact) is not ChangeSetArtifact:
        raise ValueError("artifact must be ChangeSetArtifact")
    return {
        "manifest": artifact.manifest.to_document(),
        "mutations": change_set_mutations_payload(artifact.mutations),
    }


def compute_change_set_closure_digest(artifact: ChangeSetArtifact) -> DigestRef:
    return raw_blob_digest(canonicalize_json_value(change_set_closure_document(artifact)))


def validate_change_set_ordering(mutations: Sequence[ChangeSetMutation]) -> None:
    if type(mutations) is not tuple:
        raise ValueError("mutations must be a tuple")
    previous_table: str | None = None
    current_table: str | None = None
    previous_phase = -1
    previous_key_bytes: bytes | None = None
    for mutation in mutations:
        if type(mutation) is not ChangeSetMutation:
            raise ValueError("mutations must contain ChangeSetMutation")
        table = mutation.canonical_table
        if current_table != table:
            if previous_table is not None and table < previous_table:
                raise ValueError("mutations must use canonical table order")
            current_table = table
            previous_table = table
            previous_phase = -1
            previous_key_bytes = None
        phase = _OPERATION_ORDER[mutation.operation]
        key_bytes = canonicalize_json_value(mutation.canonical_storage_key.to_document())
        if phase < previous_phase:
            raise ValueError("mutations must follow DELETE -> UPDATE -> INSERT within each table")
        if phase == previous_phase and previous_key_bytes is not None and key_bytes < previous_key_bytes:
            raise ValueError("mutations must use canonical key order within each phase")
        previous_phase = phase
        previous_key_bytes = key_bytes


def validate_canonical_cell_value(value: object, label: str) -> CanonicalCellValue:
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    kind = value.get("kind")
    if type(kind) is not str or kind not in _ALLOWED_CELL_VALUE_KINDS:
        raise ValueError(f"{label}.kind is unsupported")
    if kind == "null":
        _reject_unknown_keys(value, _NULL_CELL_KEYS, label)
        return {"kind": "null"}
    if kind == "boolean":
        _reject_unknown_keys(value, _BOOLEAN_CELL_KEYS, label)
        if type(value.get("value")) is not bool:
            raise ValueError(f"{label}.value must be bool")
        return {"kind": "boolean", "value": value["value"]}
    if kind in {"signed-integer", "unsigned-integer", "decimal"}:
        _reject_unknown_keys(value, _DECIMAL_CELL_KEYS, label)
        decimal_value = value.get("decimal")
        if type(decimal_value) is not str or decimal_value == "":
            raise ValueError(f"{label}.decimal must be a non-empty string")
        return {"kind": kind, "decimal": decimal_value}
    if kind in {"float32", "float64"}:
        _reject_unknown_keys(value, _FLOAT_CELL_KEYS, label)
        bits_hex = value.get("bits_hex")
        if type(bits_hex) is not str or bits_hex == "":
            raise ValueError(f"{label}.bits_hex must be a non-empty string")
        return {"kind": kind, "bits_hex": bits_hex}
    if kind == "string":
        _reject_unknown_keys(value, _STRING_CELL_KEYS, label)
        text = value.get("text")
        if type(text) is not str:
            raise ValueError(f"{label}.text must be a string")
        return {"kind": "string", "text": text}
    if kind in {"binary", "bit"}:
        _reject_unknown_keys(value, _BINARY_CELL_KEYS, label)
        encoded = value.get("bytes_base64url")
        if type(encoded) is not str or encoded == "":
            raise ValueError(f"{label}.bytes_base64url must be a non-empty string")
        return {"kind": kind, "bytes_base64url": encoded}
    if kind in {"date", "datetime", "timestamp", "time-duration"}:
        _reject_unknown_keys(value, _STRING_CELL_KEYS, label)
        text = value.get("text")
        if type(text) is not str or text == "":
            raise ValueError(f"{label}.text must be a non-empty string")
        return {"kind": kind, "text": text}
    _reject_unknown_keys(value, _ANOMALY_CELL_KEYS, label)
    envelope = value.get("envelope")
    if type(envelope) is not dict:
        raise ValueError(f"{label}.envelope must be an object")
    return {"kind": "source-literal-anomaly", "envelope": dict(envelope)}


def change_set_manifest_from_document(document: Mapping[str, object]) -> ChangeSetManifest:
    if type(document) is not dict:
        raise ValueError("change-set manifest document must be a dict")
    _reject_unknown_keys(document, _MANIFEST_DOCUMENT_KEYS, "change-set manifest document")
    summaries_payload = document.get("table_summaries")
    if type(summaries_payload) is not list:
        raise ValueError("table_summaries must be a list")
    summaries = tuple(_table_summary_from_document(item) for item in summaries_payload)
    renderer_payload = document.get("renderer_capability")
    if type(renderer_payload) is not dict:
        raise ValueError("renderer_capability must be an object")
    renderer = _renderer_capability_from_document(renderer_payload)
    target_payload = document.get("target_identity")
    if type(target_payload) is not dict:
        raise ValueError("target_identity must be an object")
    target = _renderer_capability_from_document(target_payload)
    if target != renderer:
        raise ValueError("target_identity must match renderer_capability")
    projection_payload = document.get("storage_projection_digest")
    if type(projection_payload) is not dict:
        raise ValueError("storage_projection_digest must be an object")
    threshold_payload = document.get("threshold_policy")
    if type(threshold_payload) is not dict:
        raise ValueError("threshold_policy must be an object")
    return ChangeSetManifest(
        manifest_contract_version=_require_string(
            document.get("manifest_contract_version"), "manifest_contract_version"
        ),
        artifact_contract_version=_require_string(
            document.get("artifact_contract_version"), "artifact_contract_version"
        ),
        mutation_contract_version=_require_string(
            document.get("mutation_contract_version"), "mutation_contract_version"
        ),
        canonical_encoding_version=_require_int(document.get("canonical_encoding_version")),
        source_identity_digest=DigestRef(
            _require_string(document.get("source_identity_digest"), "source_identity_digest")
        ),
        base_repository_ref_digest=DigestRef(
            _require_string(document.get("base_repository_ref_digest"), "base_repository_ref_digest")
        ),
        target_identity=target,
        storage_projection_digest=_projection_binding_from_document(projection_payload),
        table_ruleset_digest=DigestRef(
            _require_string(document.get("table_ruleset_digest"), "table_ruleset_digest")
        ),
        mutation_policy=MutationPolicy(_require_string(document.get("mutation_policy"), "mutation_policy")),
        threshold_policy=_threshold_policy_from_document(threshold_payload),
        table_summaries=summaries,
        change_set_digest=DigestRef(
            _require_string(document.get("change_set_digest"), "change_set_digest")
        ),
        renderer_capability=renderer,
    )


def change_set_closure_from_document(document: Mapping[str, object]) -> ChangeSetClosure:
    if type(document) is not dict:
        raise ValueError("change-set closure document must be a dict")
    _reject_unknown_keys(document, _CLOSURE_DOCUMENT_KEYS, "change-set closure document")
    manifest_payload = document.get("manifest")
    if type(manifest_payload) is not dict:
        raise ValueError("manifest must be an object")
    mutations_payload = document.get("mutations")
    if type(mutations_payload) is not list:
        raise ValueError("mutations must be a list")
    manifest = change_set_manifest_from_document(manifest_payload)
    mutations = tuple(_mutation_from_document(item) for item in mutations_payload)
    return ChangeSetClosure(manifest=manifest, mutations=mutations)


def _canonicalize_cell_columns(
    columns: tuple[tuple[str, CanonicalCellValue], ...],
    label: str,
) -> tuple[tuple[str, CanonicalCellValue], ...]:
    if type(columns) is not tuple or (not columns and label != "key"):
        raise ValueError(f"{label} must be a non-empty tuple")
    normalized: list[tuple[str, CanonicalCellValue]] = []
    previous: str | None = None
    seen: set[str] = set()
    for item in columns:
        if type(item) is not tuple or len(item) != 2:
            raise ValueError(f"{label} must contain column/value pairs")
        column, value = item
        canonical_column = canonicalize_identifier(_require_string(column, "column"))
        if canonical_column in seen:
            raise ValueError(f"{label} must not repeat columns")
        if previous is not None and canonical_column <= previous:
            raise ValueError(f"{label} must use canonical column order")
        normalized.append((canonical_column, validate_canonical_cell_value(value, f"{label}.{column}")))
        previous = canonical_column
        seen.add(canonical_column)
    return tuple(normalized)


def _validate_table_summaries(value: tuple[TableMutationSummary, ...]) -> None:
    if type(value) is not tuple:
        raise ValueError("table_summaries must be a tuple")
    previous: str | None = None
    seen: set[str] = set()
    for item in value:
        if type(item) is not TableMutationSummary:
            raise ValueError("table_summaries must contain TableMutationSummary")
        if item.canonical_table in seen:
            raise ValueError("table_summaries must not repeat canonical_table")
        if previous is not None and item.canonical_table <= previous:
            raise ValueError("table_summaries must use canonical table order")
        previous = item.canonical_table
        seen.add(item.canonical_table)


def _projection_binding_document(binding: MutationProjectionBinding) -> dict[str, object]:
    return {
        "after_manifest_digest": binding.after_manifest_digest.value,
        "after_storage_projection_digest": binding.after_storage_projection_digest.value,
        "before_manifest_digest": binding.before_manifest_digest.value,
        "before_storage_projection_digest": binding.before_storage_projection_digest.value,
        "table_ruleset_digest": binding.table_ruleset_digest.value,
    }


_PROJECTION_BINDING_KEYS = frozenset(
    {
        "after_manifest_digest",
        "after_storage_projection_digest",
        "before_manifest_digest",
        "before_storage_projection_digest",
        "table_ruleset_digest",
    }
)


def _projection_binding_from_document(document: Mapping[str, object]) -> MutationProjectionBinding:
    _reject_unknown_keys(document, _PROJECTION_BINDING_KEYS, "storage projection binding")
    return MutationProjectionBinding(
        before_storage_projection_digest=DigestRef(
            _require_string(
                document.get("before_storage_projection_digest"),
                "before_storage_projection_digest",
            )
        ),
        after_storage_projection_digest=DigestRef(
            _require_string(
                document.get("after_storage_projection_digest"),
                "after_storage_projection_digest",
            )
        ),
        before_manifest_digest=DigestRef(
            _require_string(document.get("before_manifest_digest"), "before_manifest_digest")
        ),
        after_manifest_digest=DigestRef(
            _require_string(document.get("after_manifest_digest"), "after_manifest_digest")
        ),
        table_ruleset_digest=DigestRef(
            _require_string(document.get("table_ruleset_digest"), "table_ruleset_digest")
        ),
    )


def _threshold_policy_from_document(document: Mapping[str, object]) -> MutationThresholdPolicy:
    _reject_unknown_keys(document, _THRESHOLD_POLICY_KEYS, "threshold policy")
    return MutationThresholdPolicy(
        policy_version=_require_string(document.get("policy_version"), "policy_version"),
        max_patch_changed_rows=_require_int(document.get("max_patch_changed_rows")),
        max_patch_change_ratio=_require_string(
            document.get("max_patch_change_ratio"), "max_patch_change_ratio"
        ),
    )


def _renderer_capability_from_document(
    document: Mapping[str, object],
) -> RendererCapabilityDeclaration:
    _reject_unknown_keys(document, _RENDERER_CAPABILITY_KEYS, "renderer capability")
    return RendererCapabilityDeclaration(
        target_kind=MutationTargetKind(_require_string(document.get("target_kind"), "target_kind")),
        capability_version=_require_string(
            document.get("capability_version"), "capability_version"
        ),
        capability_digest=DigestRef(
            _require_string(document.get("capability_digest"), "capability_digest")
        ),
        capability_contract_version=_require_string(
            document.get("capability_contract_version"), "capability_contract_version"
        ),
    )


def _table_summary_from_document(payload: object) -> TableMutationSummary:
    if type(payload) is not dict:
        raise ValueError("table summary must be an object")
    return TableMutationSummary(
        canonical_table=_require_string(payload.get("canonical_table"), "canonical_table"),
        operation=TableMutationKind(_require_string(payload.get("operation"), "operation")),
        changed_row_count=_require_int(payload.get("changed_row_count")),
        before_row_count=_require_int(payload.get("before_row_count")),
        after_row_count=_require_int(payload.get("after_row_count")),
    )


def _mutation_from_document(payload: object) -> ChangeSetMutation:
    if type(payload) is not dict:
        raise ValueError("change-set mutation must be an object")
    _reject_unknown_keys(payload, _MUTATION_DOCUMENT_KEYS, "change-set mutation")
    key_payload = payload.get("canonical_storage_key")
    if type(key_payload) is not list:
        raise ValueError("canonical_storage_key must be a list")
    key_columns = tuple(
        _cell_column_from_document(item, "canonical_storage_key.value") for item in key_payload
    )
    before_payload = payload.get("before_row_digest")
    before_digest = None if before_payload is None else DigestRef(
        _require_string(before_payload, "before_row_digest")
    )
    after_payload = payload.get("after_image")
    after_image = None
    if after_payload is not None:
        if type(after_payload) is not list:
            raise ValueError("after_image must be a list")
        after_image = PersistedRowImage(
            columns=tuple(
                _cell_column_from_document(item, "after_image.value") for item in after_payload
            )
        )
    return ChangeSetMutation(
        canonical_table=_require_string(payload.get("canonical_table"), "canonical_table"),
        operation=RowMutationOperation(_require_string(payload.get("operation"), "operation")),
        canonical_storage_key=CanonicalStorageKey(columns=key_columns),
        before_row_digest=before_digest,
        after_image=after_image,
    )


def _cell_column_from_document(
    payload: object,
    value_label: str,
) -> tuple[str, CanonicalCellValue]:
    if type(payload) is not dict:
        raise ValueError("cell column must be an object")
    return (
        _require_string(payload.get("column"), "column"),
        validate_canonical_cell_value(payload.get("value"), value_label),
    )


def _require_string(value: object, label: str) -> str:
    if type(value) is not str or value == "":
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _require_int(value: object) -> int:
    if type(value) is not int or isinstance(value, bool):
        raise ValueError("expected int")
    return value


def _reject_unknown_keys(payload: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {', '.join(sorted(unknown))}")
