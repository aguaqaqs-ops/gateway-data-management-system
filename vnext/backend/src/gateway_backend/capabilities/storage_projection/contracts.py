"""Public contracts owned by the Storage Projection capability.

Owner: Storage Projection capability
Authority: docs/backend-vnext/refactoring/formal/plans/p3-r4-s0-entry-and-budget-freeze.md

Field-level CanonicalizationManifest, RepositoryImportArtifactInput, and
canonical publication ports are owned here. Downstream consumers may import
this module only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts import ArtifactRef
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ArtifactSourceBinding,
    SnapshotTableArtifact,
    SnapshotTableReader,
)
from gateway_backend.capabilities.table_rules.contracts import (
    RULESET_ID,
    RULESET_VERSION,
    STORAGE_PROJECTION_VERSION as TABLE_RULES_STORAGE_PROJECTION_VERSION,
    TABLE_RULESET_CONTRACT_VERSION,
    CanonicalKeyPolicy,
    DroppedColumn,
    OrderedPolicy,
    StorageRuleView,
    TableRulesetSnapshot,
    canonicalize_rule_identifier,
)

STORAGE_PROJECTION_VERSION = TABLE_RULES_STORAGE_PROJECTION_VERSION
CANONICALIZATION_MANIFEST_CONTRACT = "3.0.0"
CANONICALIZATION_MANIFEST_MEDIA_TYPE = "application/json"
REPOSITORY_IMPORT_MEDIA_TYPE = "application/vnd.gateway.repository-import.v1+tar+zstd"
PACKAGE_VERSION = 1
_MIB = 1024 * 1024
_KIB = 1024
MAX_MANIFEST_JSON_BYTES = 16 * _MIB
MAX_REPLAY_SQL_BYTES = 200 * _MIB
MAX_DIAGNOSTICS = 1024
MAX_DIAGNOSTIC_MESSAGE_BYTES = 4 * _KIB
_UTF8 = "utf-8"


class ProjectionStatus(StrEnum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class ProjectionDiagnosticSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ProjectionDiagnosticCode(StrEnum):
    UNSUPPORTED_TABLE = "UNSUPPORTED_TABLE"
    KEY_MISSING = "KEY_MISSING"
    KEY_DUPLICATE = "KEY_DUPLICATE"
    KEY_NULL = "KEY_NULL"
    KEY_EMPTY = "KEY_EMPTY"
    ROW_INTEGRITY = "ROW_INTEGRITY"
    DIGEST_MISMATCH = "DIGEST_MISMATCH"
    BINDING_INVALID = "BINDING_INVALID"
    PUBLICATION_FAILED = "PUBLICATION_FAILED"
    PROJECTION_CANCELLED = "PROJECTION_CANCELLED"
    PROJECTION_TIMEOUT = "PROJECTION_TIMEOUT"
    RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"
    RULESET_IDENTITY_MISMATCH = "RULESET_IDENTITY_MISMATCH"
    REQUIRED_TABLE_FAILED = "REQUIRED_TABLE_FAILED"
    RULESET_INVALID = "RULESET_INVALID"


class CancelProbe(Protocol):
    def is_set(self) -> bool:
        """Return True when the caller has requested cooperative cancellation."""


@dataclass(frozen=True, slots=True)
class NeverCancel:
    def is_set(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class ProjectionInvocationContext:
    cancel_requested: CancelProbe
    deadline_monotonic: float | None = None

    def __post_init__(self) -> None:
        if self.deadline_monotonic is not None:
            if type(self.deadline_monotonic) is not float or not math.isfinite(self.deadline_monotonic):
                raise ValueError("deadline_monotonic must be a finite float or None")


@dataclass(frozen=True, slots=True)
class ProjectionDiagnostic:
    code: ProjectionDiagnosticCode
    severity: ProjectionDiagnosticSeverity
    message: str
    table_name: str | None = None

    def __post_init__(self) -> None:
        if type(self.code) is not ProjectionDiagnosticCode:
            raise ValueError("code must be ProjectionDiagnosticCode")
        if type(self.severity) is not ProjectionDiagnosticSeverity:
            raise ValueError("severity must be ProjectionDiagnosticSeverity")
        if type(self.message) is not str or self.message == "":
            raise ValueError("message must be a non-empty string")
        if len(self.message.encode(_UTF8)) > MAX_DIAGNOSTIC_MESSAGE_BYTES:
            raise ValueError("diagnostic message exceeds max_diagnostic_message_bytes")
        if self.table_name is not None:
            object.__setattr__(self, "table_name", canonicalize_rule_identifier(self.table_name))


@dataclass(frozen=True, slots=True)
class ProjectionTableInput:
    canonical_table: str
    reader: SnapshotTableReader
    source_binding: ArtifactSourceBinding
    artifact: SnapshotTableArtifact | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_table", canonicalize_rule_identifier(self.canonical_table))
        if self.reader is None:
            raise ValueError("reader is required")
        if type(self.source_binding) is not ArtifactSourceBinding:
            raise ValueError("source_binding must be ArtifactSourceBinding")
        if type(self.source_binding.snapshot_digest) is not DigestRef:
            raise ValueError("source_binding requires snapshot_digest")
        if self.source_binding.descriptor.table_name != self.canonical_table:
            raise ValueError("source_binding descriptor table_name must match canonical_table")
        if self.artifact is not None:
            if type(self.artifact) is not SnapshotTableArtifact:
                raise ValueError("artifact must be SnapshotTableArtifact or None")
            if self.artifact.manifest.table_name != self.canonical_table:
                raise ValueError("artifact table_name must match canonical_table")
            if self.artifact.manifest.snapshot_digest != self.source_binding.snapshot_digest:
                raise ValueError("artifact snapshot_digest must match source_binding")


@dataclass(frozen=True, slots=True)
class ProjectionRequest:
    ruleset: TableRulesetSnapshot
    storage_projection_version: str
    tables: tuple[ProjectionTableInput, ...]
    context: ProjectionInvocationContext
    requested_tables: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if type(self.ruleset) is not TableRulesetSnapshot:
            raise ValueError("ruleset must be TableRulesetSnapshot")
        if self.storage_projection_version != STORAGE_PROJECTION_VERSION:
            raise ValueError("storage_projection_version must be 1")
        if self.ruleset.storage_projection_version != self.storage_projection_version:
            raise ValueError("ruleset storage_projection_version must match the request")
        if self.ruleset.ruleset_digest is None:
            raise ValueError("projection requires a complete ruleset_digest")
        if (
            self.ruleset.ruleset_id != RULESET_ID
            or self.ruleset.ruleset_version != RULESET_VERSION
            or self.ruleset.contract_version != TABLE_RULESET_CONTRACT_VERSION
        ):
            raise ValueError("ruleset identity does not match the frozen R4 contract")
        if type(self.tables) is not tuple or not self.tables:
            raise ValueError("tables must be a non-empty tuple")
        seen: set[str] = set()
        for item in self.tables:
            if type(item) is not ProjectionTableInput:
                raise ValueError("tables must contain ProjectionTableInput")
            if item.canonical_table in seen:
                raise ValueError("tables must not repeat canonical_table")
            seen.add(item.canonical_table)
        if type(self.context) is not ProjectionInvocationContext:
            raise ValueError("context must be ProjectionInvocationContext")
        if self.requested_tables is not None:
            if type(self.requested_tables) is not tuple or not self.requested_tables:
                raise ValueError("requested_tables must be a non-empty tuple or None")
            canonical_requested = tuple(
                canonicalize_rule_identifier(name) for name in self.requested_tables
            )
            requested_seen: set[str] = set()
            for name in canonical_requested:
                if name in requested_seen:
                    raise ValueError("requested_tables must not contain duplicates")
                requested_seen.add(name)
            object.__setattr__(self, "requested_tables", canonical_requested)


@dataclass(frozen=True, slots=True)
class ProjectionTable:
    canonical_table: str
    storage_view: StorageRuleView
    diagnostics: tuple[ProjectionDiagnostic, ...] = ()
    row_count: int | None = None
    schema_digest: DigestRef | None = None
    content_digest: DigestRef | None = None
    ordering_digest: DigestRef | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_table", canonicalize_rule_identifier(self.canonical_table))
        if type(self.storage_view) is not StorageRuleView:
            raise ValueError("storage_view must be StorageRuleView")
        if self.storage_view.canonical_table != self.canonical_table:
            raise ValueError("storage_view canonical_table must match")
        _require_diagnostics(self.diagnostics)
        if self.row_count is not None:
            if type(self.row_count) is not int or isinstance(self.row_count, bool) or self.row_count < 0:
                raise ValueError("row_count must be a non-negative int or None")
        if self.schema_digest is not None and type(self.schema_digest) is not DigestRef:
            raise ValueError("schema_digest must be DigestRef or None")
        if self.content_digest is not None and type(self.content_digest) is not DigestRef:
            raise ValueError("content_digest must be DigestRef or None")
        if self.ordering_digest is not None and type(self.ordering_digest) is not DigestRef:
            raise ValueError("ordering_digest must be DigestRef or None")


@dataclass(frozen=True, slots=True)
class CanonicalizationManifestTable:
    name: str
    source_row_count: int
    canonical_row_count: int
    canonical_key_policy: CanonicalKeyPolicy
    ordered_policy: OrderedPolicy
    retained_columns: tuple[str, ...]
    structural_columns: tuple[str, ...]
    dropped_columns: tuple[DroppedColumn, ...]
    canonical_key_columns: tuple[str, ...] = ()
    source_schema_digest: DigestRef | None = None
    canonical_schema_digest: DigestRef | None = None
    content_digest: DigestRef | None = None
    ordering_digest: DigestRef | None = None
    gid_real_count: int | None = None
    gid_pseudo_count: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", canonicalize_rule_identifier(self.name))
        _require_non_negative_int(self.source_row_count, "source_row_count")
        _require_non_negative_int(self.canonical_row_count, "canonical_row_count")
        if type(self.canonical_key_policy) is not CanonicalKeyPolicy:
            raise ValueError("canonical_key_policy must be CanonicalKeyPolicy")
        if type(self.ordered_policy) is not OrderedPolicy:
            raise ValueError("ordered_policy must be OrderedPolicy")
        _require_optional_non_negative_int(self.gid_real_count, "gid_real_count")
        _require_optional_non_negative_int(self.gid_pseudo_count, "gid_pseudo_count")
        object.__setattr__(self, "retained_columns", _name_tuple(self.retained_columns, "retained_columns"))
        object.__setattr__(
            self,
            "structural_columns",
            _name_tuple(self.structural_columns, "structural_columns"),
        )
        object.__setattr__(
            self,
            "canonical_key_columns",
            _name_tuple(self.canonical_key_columns, "canonical_key_columns"),
        )
        if type(self.dropped_columns) is not tuple:
            raise ValueError("dropped_columns must be a tuple")
        for item in self.dropped_columns:
            if type(item) is not DroppedColumn:
                raise ValueError("dropped_columns must contain DroppedColumn")
        for digest, label in (
            (self.source_schema_digest, "source_schema_digest"),
            (self.canonical_schema_digest, "canonical_schema_digest"),
            (self.content_digest, "content_digest"),
            (self.ordering_digest, "ordering_digest"),
        ):
            if digest is not None and type(digest) is not DigestRef:
                raise ValueError(f"{label} must be DigestRef or None")


@dataclass(frozen=True, slots=True)
class CanonicalizationManifest:
    contract_version: str
    storage_projection_version: str
    ruleset_id: str
    ruleset_version: str
    ruleset_digest: DigestRef
    source_artifact_digest: DigestRef
    tables: tuple[CanonicalizationManifestTable, ...]
    manifest_digest: DigestRef | None = None

    def __post_init__(self) -> None:
        if self.contract_version != CANONICALIZATION_MANIFEST_CONTRACT:
            raise ValueError("contract_version must be 3.0.0")
        if self.storage_projection_version != STORAGE_PROJECTION_VERSION:
            raise ValueError("storage_projection_version must be 1")
        if self.ruleset_id != RULESET_ID:
            raise ValueError("ruleset_id must be backend-vnext/table-ruleset")
        if self.ruleset_version != RULESET_VERSION:
            raise ValueError("ruleset_version must be v2")
        if type(self.ruleset_digest) is not DigestRef:
            raise ValueError("ruleset_digest must be DigestRef")
        if type(self.source_artifact_digest) is not DigestRef:
            raise ValueError("source_artifact_digest must be DigestRef")
        if type(self.tables) is not tuple:
            raise ValueError("tables must be a tuple")
        seen: set[str] = set()
        for table in self.tables:
            if type(table) is not CanonicalizationManifestTable:
                raise ValueError("tables must contain CanonicalizationManifestTable")
            if table.name in seen:
                raise ValueError("manifest tables must not repeat names")
            seen.add(table.name)
        if self.manifest_digest is not None and type(self.manifest_digest) is not DigestRef:
            raise ValueError("manifest_digest must be DigestRef or None")


@dataclass(frozen=True, slots=True)
class RepositoryImportColumn:
    name: str
    sql_type: str
    nullable: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", canonicalize_rule_identifier(self.name))
        if type(self.sql_type) is not str or self.sql_type == "":
            raise ValueError("sql_type must be a non-empty string")
        if type(self.nullable) is not bool:
            raise ValueError("nullable must be bool")
        if "\x00" in self.sql_type or "\\" in self.sql_type or self.sql_type.startswith("/"):
            raise ValueError("sql_type must not be a filesystem path")


@dataclass(frozen=True, slots=True)
class RepositoryImportTable:
    name: str
    columns: tuple[RepositoryImportColumn, ...]
    primary_key: tuple[str, ...]
    row_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", canonicalize_rule_identifier(self.name))
        if type(self.columns) is not tuple:
            raise ValueError("columns must be a tuple")
        seen: set[str] = set()
        for column in self.columns:
            if type(column) is not RepositoryImportColumn:
                raise ValueError("columns must contain RepositoryImportColumn")
            if column.name in seen:
                raise ValueError("columns must not repeat names")
            seen.add(column.name)
        object.__setattr__(self, "primary_key", _name_tuple(self.primary_key, "primary_key"))
        for key in self.primary_key:
            if key not in seen:
                raise ValueError("primary_key must reference declared columns")
        _require_non_negative_int(self.row_count, "row_count")


@dataclass(frozen=True, slots=True)
class RepositoryImportArtifactInput:
    package_version: int
    canonicalization_manifest_digest: DigestRef
    tables: tuple[RepositoryImportTable, ...]

    def __post_init__(self) -> None:
        if self.package_version != PACKAGE_VERSION:
            raise ValueError("package_version must be 1")
        if type(self.canonicalization_manifest_digest) is not DigestRef:
            raise ValueError("canonicalization_manifest_digest must be DigestRef")
        if type(self.tables) is not tuple:
            raise ValueError("tables must be a tuple")
        seen: set[str] = set()
        for table in self.tables:
            if type(table) is not RepositoryImportTable:
                raise ValueError("tables must contain RepositoryImportTable")
            if table.name in seen:
                raise ValueError("import tables must not repeat names")
            seen.add(table.name)


@dataclass(frozen=True, slots=True)
class ProjectionResult:
    status: ProjectionStatus
    tables: tuple[ProjectionTable, ...]
    diagnostics: tuple[ProjectionDiagnostic, ...] = ()
    manifest: CanonicalizationManifest | None = None
    import_input: RepositoryImportArtifactInput | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not ProjectionStatus:
            raise ValueError("status must be ProjectionStatus")
        if type(self.tables) is not tuple:
            raise ValueError("tables must be a tuple")
        for table in self.tables:
            if type(table) is not ProjectionTable:
                raise ValueError("tables must contain ProjectionTable")
        _require_diagnostics(self.diagnostics)
        if self.status is ProjectionStatus.FAILED:
            if self.manifest is not None or self.import_input is not None:
                raise ValueError("FAILED projection must not publish manifest or import input")
            return
        if type(self.manifest) is not CanonicalizationManifest:
            raise ValueError("COMPLETE projection requires CanonicalizationManifest")
        if type(self.import_input) is not RepositoryImportArtifactInput:
            raise ValueError("COMPLETE projection requires RepositoryImportArtifactInput")
        if self.manifest.manifest_digest is None:
            raise ValueError("COMPLETE projection requires manifest_digest")
        if self.import_input.canonicalization_manifest_digest != self.manifest.manifest_digest:
            raise ValueError("import input must bind the opaque manifest digest")


@dataclass(frozen=True, slots=True)
class WrittenImportPackage:
    payload: bytes
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if type(self.payload) is not bytes:
            raise ValueError("payload must be bytes")
        if type(self.size_bytes) is not int or isinstance(self.size_bytes, bool) or self.size_bytes < 0:
            raise ValueError("size_bytes must be a non-negative int")
        if self.size_bytes != len(self.payload):
            raise ValueError("size_bytes must match payload")
        if type(self.sha256) is not str:
            raise ValueError("sha256 must be a string")
        DigestRef(self.sha256)


@dataclass(frozen=True, slots=True)
class CanonicalPublication:
    manifest_ref: ArtifactRef
    package_ref: ArtifactRef
    manifest_digest: DigestRef

    def __post_init__(self) -> None:
        if type(self.manifest_ref) is not ArtifactRef:
            raise ValueError("manifest_ref must be ArtifactRef")
        if type(self.package_ref) is not ArtifactRef:
            raise ValueError("package_ref must be ArtifactRef")
        if type(self.manifest_digest) is not DigestRef:
            raise ValueError("manifest_digest must be DigestRef")
        if self.manifest_ref.media_type != CANONICALIZATION_MANIFEST_MEDIA_TYPE:
            raise ValueError("manifest_ref media_type mismatch")
        if self.package_ref.media_type != REPOSITORY_IMPORT_MEDIA_TYPE:
            raise ValueError("package_ref media_type mismatch")


@dataclass(frozen=True, slots=True)
class CanonicalPublicationResult:
    status: ProjectionStatus
    publication: CanonicalPublication | None = None
    diagnostics: tuple[ProjectionDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if type(self.status) is not ProjectionStatus:
            raise ValueError("status must be ProjectionStatus")
        _require_diagnostics(self.diagnostics)
        if self.status is ProjectionStatus.FAILED:
            if self.publication is not None:
                raise ValueError("FAILED publication must not include CanonicalPublication")
            return
        if type(self.publication) is not CanonicalPublication:
            raise ValueError("COMPLETE publication requires CanonicalPublication")


def _require_diagnostics(diagnostics: tuple[ProjectionDiagnostic, ...]) -> None:
    if type(diagnostics) is not tuple:
        raise ValueError("diagnostics must be a tuple")
    if len(diagnostics) > MAX_DIAGNOSTICS:
        raise ValueError("diagnostics exceed max_diagnostics")
    for item in diagnostics:
        if type(item) is not ProjectionDiagnostic:
            raise ValueError("diagnostics must contain ProjectionDiagnostic")


def _require_non_negative_int(value: object, label: str) -> None:
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a non-negative int")


def _require_optional_non_negative_int(value: object, label: str) -> None:
    if value is None:
        return
    _require_non_negative_int(value, label)


def _name_tuple(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ValueError(f"{label} must be a tuple")
    canonical = tuple(canonicalize_rule_identifier(item) for item in values)
    seen: set[str] = set()
    for item in canonical:
        if item in seen:
            raise ValueError(f"{label} must not contain duplicates")
        seen.add(item)
    return canonical


__all__ = [
    "CANONICALIZATION_MANIFEST_CONTRACT",
    "CanonicalKeyPolicy",
    "CanonicalizationManifest",
    "CanonicalizationManifestTable",
    "DroppedColumn",
    "OrderedPolicy",
    "RULESET_ID",
    "RULESET_VERSION",
    "STORAGE_PROJECTION_VERSION",
    "StorageRuleView",
    "TableRulesetSnapshot",
]
