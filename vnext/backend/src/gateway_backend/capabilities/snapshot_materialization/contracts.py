"""Public contracts owned by the Snapshot Materialization capability.

Owner: Snapshot Materialization capability
Authority: docs/backend-vnext/refactoring/formal/plans/p3-r3-source-materialization-handoff.md

S2 owns SQL Snapshot field tables, result/status pairing, and the
materialize_sql_snapshot entrypoint. S3 owns business composition with
composite_signal_point. S4 owns the RepositoryRef provider protocol and
hidden FINAL summary readback. S5 owns SnapshotTableArtifact Parquet
publish and cache trust validation.
Downstream consumers may import this module only.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts import ArtifactRef
from gateway_backend.capabilities.composite_signal.contracts import CompositeLogicSource
from gateway_backend.capabilities.table_access.contracts import (
    ParseResult,
    ParserInvocationContext,
    SourceRow,
    XmlParseResult,
)
from gateway_backend.capabilities.table_rules.contracts import TableRulesetSnapshot

if TYPE_CHECKING:
    import pyarrow as pa

SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION = 1
DIGEST_CONTRACT_VERSION = 1
SCALAR_ENCODING_VERSION = 1
SUMMARY_CONTRACT_VERSION = 1
SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION = 1
BATCH_READER_CONTRACT_VERSION = 1
BATCH_SCHEMA_METADATA_VERSION = 1
COMPARISON_PROJECTION_CONTRACT_VERSION = "backend-vnext/comparison-projection/v1"
ORDERED_COMPARISON_CONTRACT_VERSION = "backend-vnext/ordered-diff/v2"
BLANK_COMPARISON_CONTRACT_VERSION = "backend-vnext/comparison-blank/v1"
ROW_MATERIALIZATION_PROFILE = "sql-canonical-v1"
ROW_FORMAT_PARQUET = "parquet"
EXPORT_FORMAT_PARQUET = "PARQUET"
ARTIFACT_COMPRESSION_ZSTD = "zstd"
ROW_ORDER_CONTRACT_INSERT = "INSERT_ORDER"
PARQUET_MEDIA_TYPE = "application/vnd.apache.parquet"
MANIFEST_MEDIA_TYPE = "application/json"
GID_REAL_MIN = 1
GID_REAL_MAX = 3_999_999_999
GID_PSEUDO_MIN = 4_000_000_000
GID_PSEUDO_MAX = 4_294_967_295
_MAX_DIAGNOSTICS = 1024
_MAX_DIAGNOSTIC_MESSAGE_BYTES = 4096
_UTF8 = "utf-8"


class SnapshotMaterializationStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class MaterializationStage(StrEnum):
    PROVISIONAL = "PROVISIONAL"
    FINAL = "FINAL"


class CacheTrustLevel(StrEnum):
    PROVISIONAL = "PROVISIONAL"
    CONTENT_VERIFIED = "CONTENT_VERIFIED"
    COMMIT_VALIDATED = "COMMIT_VALIDATED"


class MaterializationPolicy(StrEnum):
    DESCRIPTOR_ONLY = "DESCRIPTOR_ONLY"
    READERS_REQUIRED = "READERS_REQUIRED"
    ARTIFACTS_REQUIRED = "ARTIFACTS_REQUIRED"


class SourceKind(StrEnum):
    SQL_DUMP_SOURCE = "SQL_DUMP_SOURCE"
    IMMUTABLE_REPOSITORY_REF = "IMMUTABLE_REPOSITORY_REF"


class BlankRowProvenance(StrEnum):
    """Trusted provenance used by the ordered comparison consumer.

    ``NONE`` is the default for ordinary tables.  The two non-empty values are supplied by the
    materialization owner; comparison must not infer blank semantics from a gid value alone.
    """

    NONE = "NONE"
    SOURCE_MISSING_STABLE_KEY = "SOURCE_MISSING_STABLE_KEY"
    CANONICAL_PSEUDO_GID = "CANONICAL_PSEUDO_GID"


class DiagnosticSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class CacheLookupPolicy(StrEnum):
    READ_COMMIT_VALIDATED_ONLY = "READ_COMMIT_VALIDATED_ONLY"
    READ_PROVISIONAL_WITH_REVALIDATION = "READ_PROVISIONAL_WITH_REVALIDATION"
    READ_ANY_WITH_REVALIDATION = "READ_ANY_WITH_REVALIDATION"


class ValidationStatusPolicy(StrEnum):
    NO_CACHE_WRITE = "NO_CACHE_WRITE"
    PROVISIONAL_ONLY = "PROVISIONAL_ONLY"
    PROMOTE_AFTER_AUTHORITY_VALIDATION = "PROMOTE_AFTER_AUTHORITY_VALIDATION"


class CacheLookupStatus(StrEnum):
    HIT = "HIT"
    MISS = "MISS"
    REJECTED = "REJECTED"


class MaterializationDiagnosticCode(StrEnum):
    RULESET_VERSION_MISMATCH = "RULESET_VERSION_MISMATCH"
    REQUESTED_TABLE_MISSING = "REQUESTED_TABLE_MISSING"
    ARTIFACT_STORE_REQUIRED = "ARTIFACT_STORE_REQUIRED"
    ARTIFACT_PUBLISH_FAILED = "ARTIFACT_PUBLISH_FAILED"
    ARTIFACT_MANIFEST_CORRUPT = "ARTIFACT_MANIFEST_CORRUPT"
    ARTIFACT_SCHEMA_MISMATCH = "ARTIFACT_SCHEMA_MISMATCH"
    ARTIFACT_DIGEST_MISMATCH = "ARTIFACT_DIGEST_MISMATCH"
    ARTIFACT_TRUNCATED = "ARTIFACT_TRUNCATED"
    CACHE_PROVISIONAL_REQUIRES_REVALIDATION = "CACHE_PROVISIONAL_REQUIRES_REVALIDATION"
    CACHE_TRUST_POLICY_REJECTED = "CACHE_TRUST_POLICY_REJECTED"
    CACHE_PROMOTION_REQUIRES_AUTHORITY = "CACHE_PROMOTION_REQUIRES_AUTHORITY"
    COMPARE_KEY_UNKNOWN_COLUMN = "COMPARE_KEY_UNKNOWN_COLUMN"
    TABLE_READER_UNAVAILABLE = "TABLE_READER_UNAVAILABLE"
    MATERIALIZATION_CANCELLED = "MATERIALIZATION_CANCELLED"
    MATERIALIZATION_TIMEOUT = "MATERIALIZATION_TIMEOUT"
    STREAM_INCOMPLETE = "STREAM_INCOMPLETE"
    DUPLICATE_EFFECTIVE_KEY = "DUPLICATE_EFFECTIVE_KEY"
    XML_DOCUMENT_FAILED = "XML_DOCUMENT_FAILED"
    COMPOSITE_LOGIC_FAILED = "COMPOSITE_LOGIC_FAILED"
    COMPOSITE_CATALOG_UNAVAILABLE = "COMPOSITE_CATALOG_UNAVAILABLE"
    REPOSITORY_REF_NOT_FOUND = "REPOSITORY_REF_NOT_FOUND"
    REPOSITORY_REF_OPEN_TIMEOUT = "REPOSITORY_REF_OPEN_TIMEOUT"
    REPOSITORY_REF_OPEN_FAILED = "REPOSITORY_REF_OPEN_FAILED"
    REPOSITORY_CATALOG_LOAD_FAILED = "REPOSITORY_CATALOG_LOAD_FAILED"
    REPOSITORY_TABLE_NOT_FOUND = "REPOSITORY_TABLE_NOT_FOUND"
    REPOSITORY_TABLE_READER_OPEN_FAILED = "REPOSITORY_TABLE_READER_OPEN_FAILED"
    REPOSITORY_TABLE_READ_FAILED = "REPOSITORY_TABLE_READ_FAILED"
    REPOSITORY_IDENTIFIER_COLLISION = "REPOSITORY_IDENTIFIER_COLLISION"
    REPOSITORY_SNAPSHOT_DIGEST_MISMATCH = "REPOSITORY_SNAPSHOT_DIGEST_MISMATCH"
    REPOSITORY_SESSION_CLOSE_FAILED = "REPOSITORY_SESSION_CLOSE_FAILED"
    REPOSITORY_SCALAR_ENCODING_DIAGNOSTIC = "REPOSITORY_SCALAR_ENCODING_DIAGNOSTIC"
    HIDDEN_SUMMARY_MISSING = "HIDDEN_SUMMARY_MISSING"
    HIDDEN_SUMMARY_CORRUPT = "HIDDEN_SUMMARY_CORRUPT"
    HIDDEN_SUMMARY_VERSION_MISMATCH = "HIDDEN_SUMMARY_VERSION_MISMATCH"
    HIDDEN_SUMMARY_DIGEST_MISMATCH = "HIDDEN_SUMMARY_DIGEST_MISMATCH"
    RESERVED_PSEUDO_GID = "RESERVED_PSEUDO_GID"


class DegradedReason(StrEnum):
    KEYLESS = "KEYLESS"
    DUPLICATE_EFFECTIVE_KEY = "DUPLICATE_EFFECTIVE_KEY"
    TABLE_FAILED = "TABLE_FAILED"


@dataclass(frozen=True, slots=True)
class MaterializationDiagnostic:
    code: MaterializationDiagnosticCode
    severity: DiagnosticSeverity
    message: str
    table: str | None = None
    column: str | None = None

    def __post_init__(self) -> None:
        if type(self.code) is not MaterializationDiagnosticCode:
            raise ValueError("code must be MaterializationDiagnosticCode")
        if type(self.severity) is not DiagnosticSeverity:
            raise ValueError("severity must be DiagnosticSeverity")
        if type(self.message) is not str or self.message == "":
            raise ValueError("message must be a non-empty string")
        if len(self.message.encode(_UTF8)) > _MAX_DIAGNOSTIC_MESSAGE_BYTES:
            raise ValueError("message exceeds max diagnostic bytes")
        if self.table is not None and (type(self.table) is not str or self.table == ""):
            raise ValueError("table must be a non-empty string or None")
        if self.column is not None and (type(self.column) is not str or self.column == ""):
            raise ValueError("column must be a non-empty string or None")


@dataclass(frozen=True, slots=True)
class SnapshotColumnDescriptor:
    name: str
    display_name: str
    nullable: bool
    scalar_type: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "name")
        _require_non_empty(self.display_name, "display_name")
        if type(self.nullable) is not bool:
            raise ValueError("nullable must be bool")
        if self.scalar_type is not None and (
            type(self.scalar_type) is not str or self.scalar_type == ""
        ):
            raise ValueError("scalar_type must be a non-empty string or None")


@dataclass(frozen=True, slots=True)
class SnapshotTableDescriptor:
    table_name: str
    display_table_name: str
    columns: tuple[SnapshotColumnDescriptor, ...]
    primary_key_columns: tuple[str, ...]
    compare_key_columns: tuple[str, ...]
    row_count: int
    materialization_stage: MaterializationStage
    compare_schema_digest: DigestRef
    table_ruleset_version: int
    row_materialization_profile: str
    scalar_encoding_version: int
    fast_row_digest: DigestRef | None = None
    raw_content_digest: DigestRef | None = None
    business_content_digest: DigestRef | None = None
    degraded_reason: DegradedReason | None = None
    diagnostics: tuple[MaterializationDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.table_name, "table_name")
        _require_non_empty(self.display_table_name, "display_table_name")
        if type(self.columns) is not tuple:
            raise ValueError("columns must be a tuple")
        for column in self.columns:
            if type(column) is not SnapshotColumnDescriptor:
                raise ValueError("columns must contain SnapshotColumnDescriptor")
        if type(self.primary_key_columns) is not tuple:
            raise ValueError("primary_key_columns must be a tuple")
        if type(self.compare_key_columns) is not tuple:
            raise ValueError("compare_key_columns must be a tuple")
        _require_non_negative_int(self.row_count, "row_count")
        if type(self.materialization_stage) is not MaterializationStage:
            raise ValueError("materialization_stage must be MaterializationStage")
        if type(self.compare_schema_digest) is not DigestRef:
            raise ValueError("compare_schema_digest must be DigestRef")
        if type(self.table_ruleset_version) is not int or self.table_ruleset_version < 1:
            raise ValueError("table_ruleset_version must be a positive int")
        if self.row_materialization_profile != ROW_MATERIALIZATION_PROFILE:
            raise ValueError("row_materialization_profile must be sql-canonical-v1")
        if self.scalar_encoding_version != SCALAR_ENCODING_VERSION:
            raise ValueError("scalar_encoding_version must be 1")
        if self.fast_row_digest is not None and type(self.fast_row_digest) is not DigestRef:
            raise ValueError("fast_row_digest must be DigestRef or None")
        if self.raw_content_digest is not None and type(self.raw_content_digest) is not DigestRef:
            raise ValueError("raw_content_digest must be DigestRef or None")
        if self.business_content_digest is not None:
            raise ValueError("S2 business_content_digest must be NOT_COMPUTED")
        if self.degraded_reason is not None and type(self.degraded_reason) is not DegradedReason:
            raise ValueError("degraded_reason must be DegradedReason or None")
        _require_diagnostics(self.diagnostics)
        if (
            self.materialization_stage is MaterializationStage.FINAL
            and self.degraded_reason is not DegradedReason.TABLE_FAILED
            and self.raw_content_digest is None
        ):
            raise ValueError("FINAL success table requires raw_content_digest")


@dataclass(frozen=True, slots=True)
class SnapshotSourceContext:
    source_kind: SourceKind
    sql_source_digest: DigestRef | None = None
    composite_logic_source_digest: DigestRef | None = None
    repository_id: str | None = None
    repository_ref: str | None = None
    resolved_commit_hash: str | None = None

    def __post_init__(self) -> None:
        if type(self.source_kind) is not SourceKind:
            raise ValueError("source_kind must be SourceKind")
        if self.composite_logic_source_digest is not None and (
            type(self.composite_logic_source_digest) is not DigestRef
        ):
            raise ValueError("composite_logic_source_digest must be DigestRef or None")
        if self.source_kind is SourceKind.SQL_DUMP_SOURCE:
            if type(self.sql_source_digest) is not DigestRef:
                raise ValueError("SQL_DUMP_SOURCE requires sql_source_digest")
            if (
                self.repository_id is not None
                or self.repository_ref is not None
                or self.resolved_commit_hash is not None
            ):
                raise ValueError("SQL_DUMP_SOURCE forbids repository source fields")
            return
        if self.source_kind is SourceKind.IMMUTABLE_REPOSITORY_REF:
            _require_non_empty(self.repository_id, "repository_id")
            _require_non_empty(self.repository_ref, "repository_ref")
            _require_opaque_id(self.resolved_commit_hash, "resolved_commit_hash")
            if self.sql_source_digest is not None and type(self.sql_source_digest) is not DigestRef:
                raise ValueError("sql_source_digest must be DigestRef or None")
            return
        raise ValueError("unsupported source_kind")


@dataclass(frozen=True, slots=True)
class Snapshot:
    snapshot_id: str
    source_kind: SourceKind
    parser_version: int
    table_ruleset_version: int
    scalar_encoding_version: int
    snapshot_materialization_contract_version: int
    row_materialization_profile: str
    materialization_stage: MaterializationStage
    snapshot_digest: DigestRef
    raw_state_digest: DigestRef
    created_at: str
    source_context: SnapshotSourceContext
    business_state_digest: DigestRef | None = None

    def __post_init__(self) -> None:
        _require_opaque_id(self.snapshot_id, "snapshot_id")
        if type(self.source_kind) is not SourceKind:
            raise ValueError("source_kind must be SourceKind")
        if type(self.parser_version) is not int or self.parser_version < 1:
            raise ValueError("parser_version must be a positive int")
        if type(self.table_ruleset_version) is not int or self.table_ruleset_version < 1:
            raise ValueError("table_ruleset_version must be a positive int")
        if self.scalar_encoding_version != SCALAR_ENCODING_VERSION:
            raise ValueError("scalar_encoding_version must be 1")
        if self.snapshot_materialization_contract_version != (
            SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION
        ):
            raise ValueError("snapshot_materialization_contract_version must be 1")
        if self.row_materialization_profile != ROW_MATERIALIZATION_PROFILE:
            raise ValueError("row_materialization_profile must be sql-canonical-v1")
        if type(self.materialization_stage) is not MaterializationStage:
            raise ValueError("materialization_stage must be MaterializationStage")
        if type(self.snapshot_digest) is not DigestRef:
            raise ValueError("snapshot_digest must be DigestRef")
        if type(self.raw_state_digest) is not DigestRef:
            raise ValueError("raw_state_digest must be DigestRef")
        _require_non_empty(self.created_at, "created_at")
        if type(self.source_context) is not SnapshotSourceContext:
            raise ValueError("source_context must be SnapshotSourceContext")
        if self.business_state_digest is not None:
            raise ValueError("S2 business_state_digest must be NOT_COMPUTED")
        if "/" in self.snapshot_id or "\\" in self.snapshot_id or "\x00" in self.snapshot_id:
            raise ValueError("snapshot_id must not be a path-shaped identity")


@dataclass(frozen=True, slots=True)
class SnapshotSummary:
    snapshot_id: str
    snapshot_digest: DigestRef
    raw_state_digest: DigestRef
    materialization_stage: MaterializationStage
    parser_version: int
    table_ruleset_version: int
    summary_contract_version: int
    table_count: int
    tables: tuple[SnapshotTableDescriptor, ...]
    source_context: SnapshotSourceContext
    diagnostics: tuple[MaterializationDiagnostic, ...]
    row_count_total: int | None = None
    business_state_digest: DigestRef | None = None

    def __post_init__(self) -> None:
        _require_opaque_id(self.snapshot_id, "snapshot_id")
        if type(self.snapshot_digest) is not DigestRef:
            raise ValueError("snapshot_digest must be DigestRef")
        if type(self.raw_state_digest) is not DigestRef:
            raise ValueError("raw_state_digest must be DigestRef")
        if type(self.materialization_stage) is not MaterializationStage:
            raise ValueError("materialization_stage must be MaterializationStage")
        if type(self.parser_version) is not int or self.parser_version < 1:
            raise ValueError("parser_version must be a positive int")
        if type(self.table_ruleset_version) is not int or self.table_ruleset_version < 1:
            raise ValueError("table_ruleset_version must be a positive int")
        if self.summary_contract_version != SUMMARY_CONTRACT_VERSION:
            raise ValueError("summary_contract_version must be 1")
        _require_non_negative_int(self.table_count, "table_count")
        if type(self.tables) is not tuple:
            raise ValueError("tables must be a tuple")
        if len(self.tables) != self.table_count:
            raise ValueError("table_count must equal len(tables)")
        seen: set[str] = set()
        for table in self.tables:
            if type(table) is not SnapshotTableDescriptor:
                raise ValueError("tables must contain SnapshotTableDescriptor")
            if table.table_name in seen:
                raise ValueError("summary tables must not repeat table_name")
            seen.add(table.table_name)
        if type(self.source_context) is not SnapshotSourceContext:
            raise ValueError("source_context must be SnapshotSourceContext")
        _require_diagnostics(self.diagnostics)
        if self.row_count_total is not None:
            _require_non_negative_int(self.row_count_total, "row_count_total")
        if self.business_state_digest is not None:
            raise ValueError("S2 business_state_digest must be NOT_COMPUTED")


@dataclass(frozen=True, slots=True)
class SnapshotColumnValueCounts:
    column_name: str
    counts: tuple[tuple[str | None, int], ...]
    total_row_count: int

    def __post_init__(self) -> None:
        _require_non_empty(self.column_name, "column_name")
        if type(self.counts) is not tuple:
            raise ValueError("counts must be a tuple")
        total = 0
        for item in self.counts:
            if type(item) is not tuple or len(item) != 2:
                raise ValueError("counts must contain (value, count) pairs")
            value, count = item
            if value is not None and type(value) is not str:
                raise ValueError("count value must be a string or None")
            _require_non_negative_int(count, "count")
            total += count
        _require_non_negative_int(self.total_row_count, "total_row_count")
        if total != self.total_row_count:
            raise ValueError("counts must cover total_row_count")


class SnapshotTableReader(Protocol):
    def descriptor(self) -> SnapshotTableDescriptor:
        """Return the frozen snapshot descriptor for this reader."""

    def iter_rows(self) -> Iterator[SourceRow]:
        """Yield positional rows once; non-rewind and single-consumer."""

    def count_column_values(self, column_name: str) -> SnapshotColumnValueCounts:
        """Count every value of one canonical column, including NULL."""

    def close(self) -> None:
        """Idempotent close. Later access raises READER_CLOSED."""

    def reopen(self) -> SnapshotTableReader:
        """Open an independent reader over the same table."""


@dataclass(frozen=True, slots=True)
class SnapshotTableBatchMetadata:
    """Language-neutral versions carried in an Arrow schema."""

    batch_schema_metadata_version: int = BATCH_SCHEMA_METADATA_VERSION
    batch_reader_contract_version: int = BATCH_READER_CONTRACT_VERSION
    scalar_encoding_version: int = SCALAR_ENCODING_VERSION
    projection_contract_version: str = COMPARISON_PROJECTION_CONTRACT_VERSION
    ordered_contract_version: str = ORDERED_COMPARISON_CONTRACT_VERSION
    blank_contract_version: str = BLANK_COMPARISON_CONTRACT_VERSION
    artifact_contract_version: int = SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION
    blank_provenance: BlankRowProvenance = BlankRowProvenance.NONE

    def __post_init__(self) -> None:
        for name in (
            "batch_schema_metadata_version",
            "batch_reader_contract_version",
            "scalar_encoding_version",
            "artifact_contract_version",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in (
            "projection_contract_version",
            "ordered_contract_version",
            "blank_contract_version",
        ):
            value = getattr(self, name)
            if type(value) is not str or value == "":
                raise ValueError(f"{name} must be a non-empty string")
        if self.batch_schema_metadata_version != BATCH_SCHEMA_METADATA_VERSION:
            raise ValueError("batch_schema_metadata_version must be 1")
        if self.batch_reader_contract_version != BATCH_READER_CONTRACT_VERSION:
            raise ValueError("batch_reader_contract_version must be 1")
        if self.scalar_encoding_version != SCALAR_ENCODING_VERSION:
            raise ValueError("scalar_encoding_version must be 1")
        if self.artifact_contract_version != SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION:
            raise ValueError("artifact_contract_version must be 1")
        if type(self.blank_provenance) is not BlankRowProvenance:
            raise ValueError("blank_provenance must be BlankRowProvenance")


@dataclass(frozen=True, slots=True)
class SnapshotTableOrderedMetadata:
    """Materialization-owned blank marker carried with an ordered table."""

    blank_provenance: BlankRowProvenance

    def __post_init__(self) -> None:
        if self.blank_provenance is BlankRowProvenance.NONE:
            raise ValueError("ordered metadata requires non-empty blank provenance")
        if type(self.blank_provenance) is not BlankRowProvenance:
            raise ValueError("blank_provenance must be BlankRowProvenance")


@runtime_checkable
class SnapshotTableBatchReader(Protocol):
    """Public bulk boundary; implementations must not materialize rows as Python objects."""

    def descriptor(self) -> SnapshotTableDescriptor:
        """Return the immutable table descriptor."""

    def schema(self) -> "pa.Schema":
        """Return the Arrow schema for every batch in this reader."""

    def metadata(self) -> SnapshotTableBatchMetadata:
        """Return version metadata carried by the Arrow schema."""

    def iter_record_batches(self) -> Iterator["pa.RecordBatch"]:
        """Yield Arrow RecordBatch values without row-wise conversion."""

    def close(self) -> None:
        """Idempotently close the reader."""

    def reopen(self) -> "SnapshotTableBatchReader":
        """Open an independent reader over the same immutable table."""


@dataclass(frozen=True, slots=True)
class SnapshotTableArtifactManifest:
    artifact_contract_version: int
    snapshot_digest: DigestRef
    table_name: str
    descriptor: SnapshotTableDescriptor
    row_file_refs: tuple[ArtifactRef, ...]
    row_format: str
    compression: str
    row_materialization_profile: str
    artifact_content_digest: DigestRef
    created_at: str
    diagnostics: tuple[MaterializationDiagnostic, ...] = ()
    ordered_metadata: SnapshotTableOrderedMetadata | None = None

    def __post_init__(self) -> None:
        if self.artifact_contract_version != SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION:
            raise ValueError("artifact_contract_version must be 1")
        if type(self.snapshot_digest) is not DigestRef:
            raise ValueError("snapshot_digest must be DigestRef")
        _require_non_empty(self.table_name, "table_name")
        if type(self.descriptor) is not SnapshotTableDescriptor:
            raise ValueError("descriptor must be SnapshotTableDescriptor")
        if self.descriptor.table_name != self.table_name:
            raise ValueError("manifest table_name must match descriptor")
        if type(self.row_file_refs) is not tuple or not self.row_file_refs:
            raise ValueError("row_file_refs must be a non-empty tuple")
        for ref in self.row_file_refs:
            if type(ref) is not ArtifactRef:
                raise ValueError("row_file_refs must contain ArtifactRef")
        if self.row_format != ROW_FORMAT_PARQUET:
            raise ValueError("row_format must be parquet")
        if self.compression != ARTIFACT_COMPRESSION_ZSTD:
            raise ValueError("compression must be zstd")
        if self.row_materialization_profile != ROW_MATERIALIZATION_PROFILE:
            raise ValueError("row_materialization_profile must be sql-canonical-v1")
        if type(self.artifact_content_digest) is not DigestRef:
            raise ValueError("artifact_content_digest must be DigestRef")
        _require_non_empty(self.created_at, "created_at")
        _require_diagnostics(self.diagnostics)
        if self.ordered_metadata is not None and type(self.ordered_metadata) is not SnapshotTableOrderedMetadata:
            raise ValueError("ordered_metadata must be SnapshotTableOrderedMetadata or None")


@dataclass(frozen=True, slots=True)
class SnapshotTableArtifact:
    manifest_ref: ArtifactRef
    manifest: SnapshotTableArtifactManifest
    row_layout_digest: DigestRef

    def __post_init__(self) -> None:
        if type(self.manifest_ref) is not ArtifactRef:
            raise ValueError("manifest_ref must be ArtifactRef")
        if type(self.manifest) is not SnapshotTableArtifactManifest:
            raise ValueError("manifest must be SnapshotTableArtifactManifest")
        if type(self.row_layout_digest) is not DigestRef:
            raise ValueError("row_layout_digest must be DigestRef")


@dataclass(frozen=True, slots=True)
class SnapshotTableArtifactCacheKey:
    row_layout_digest: DigestRef
    repository_id: str | None = None
    scalar_encoding_version: int = SCALAR_ENCODING_VERSION
    snapshot_table_artifact_contract_version: int = SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION
    export_format: str = EXPORT_FORMAT_PARQUET
    sort_or_row_order_contract: str = ROW_ORDER_CONTRACT_INSERT

    def __post_init__(self) -> None:
        if type(self.row_layout_digest) is not DigestRef:
            raise ValueError("row_layout_digest must be DigestRef")
        if self.repository_id is not None:
            _require_opaque_id(self.repository_id, "repository_id")
        if self.scalar_encoding_version != SCALAR_ENCODING_VERSION:
            raise ValueError("scalar_encoding_version must be 1")
        if self.snapshot_table_artifact_contract_version != (
            SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION
        ):
            raise ValueError("snapshot_table_artifact_contract_version must be 1")
        if self.export_format != EXPORT_FORMAT_PARQUET:
            raise ValueError("export_format must be PARQUET")
        if self.sort_or_row_order_contract != ROW_ORDER_CONTRACT_INSERT:
            raise ValueError("sort_or_row_order_contract must be INSERT_ORDER")


@dataclass(frozen=True, slots=True)
class ArtifactSourceBinding:
    snapshot_digest: DigestRef
    descriptor: SnapshotTableDescriptor
    repository_id: str | None = None
    resolved_commit_hash: str | None = None

    def __post_init__(self) -> None:
        if type(self.snapshot_digest) is not DigestRef:
            raise ValueError("snapshot_digest must be DigestRef")
        if type(self.descriptor) is not SnapshotTableDescriptor:
            raise ValueError("descriptor must be SnapshotTableDescriptor")
        if self.repository_id is not None:
            _require_opaque_id(self.repository_id, "repository_id")
        if self.resolved_commit_hash is not None:
            _require_opaque_id(self.resolved_commit_hash, "resolved_commit_hash")


@dataclass(frozen=True, slots=True)
class CacheAuthorityInput:
    repository_id: str
    resolved_commit_hash: str
    snapshot_digest: DigestRef

    def __post_init__(self) -> None:
        _require_opaque_id(self.repository_id, "repository_id")
        _require_opaque_id(self.resolved_commit_hash, "resolved_commit_hash")
        if type(self.snapshot_digest) is not DigestRef:
            raise ValueError("snapshot_digest must be DigestRef")


@dataclass(frozen=True, slots=True)
class CacheRevalidation:
    snapshot_digest: DigestRef
    descriptor: SnapshotTableDescriptor

    def __post_init__(self) -> None:
        if type(self.snapshot_digest) is not DigestRef:
            raise ValueError("snapshot_digest must be DigestRef")
        if type(self.descriptor) is not SnapshotTableDescriptor:
            raise ValueError("descriptor must be SnapshotTableDescriptor")


@dataclass(frozen=True, slots=True)
class SnapshotTableArtifactCacheResult:
    status: CacheLookupStatus
    trust: CacheTrustLevel | None = None
    artifact: SnapshotTableArtifact | None = None
    diagnostics: tuple[MaterializationDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if type(self.status) is not CacheLookupStatus:
            raise ValueError("status must be CacheLookupStatus")
        if self.trust is not None and type(self.trust) is not CacheTrustLevel:
            raise ValueError("trust must be CacheTrustLevel or None")
        if self.artifact is not None and type(self.artifact) is not SnapshotTableArtifact:
            raise ValueError("artifact must be SnapshotTableArtifact or None")
        _require_diagnostics(self.diagnostics)


@dataclass(frozen=True, slots=True)
class SnapshotTable:
    descriptor: SnapshotTableDescriptor
    reader: SnapshotTableReader | None
    diagnostics: tuple[MaterializationDiagnostic, ...] = ()
    artifact: SnapshotTableArtifact | None = None
    batch_reader: SnapshotTableBatchReader | None = None
    ordered_metadata: SnapshotTableOrderedMetadata | None = None

    def __post_init__(self) -> None:
        if type(self.descriptor) is not SnapshotTableDescriptor:
            raise ValueError("descriptor must be SnapshotTableDescriptor")
        _require_diagnostics(self.diagnostics)
        if self.artifact is not None and type(self.artifact) is not SnapshotTableArtifact:
            raise ValueError("artifact must be SnapshotTableArtifact or None")
        if self.batch_reader is not None and not isinstance(self.batch_reader, SnapshotTableBatchReader):
            raise ValueError("batch_reader must implement SnapshotTableBatchReader or be None")
        if self.ordered_metadata is not None and type(self.ordered_metadata) is not SnapshotTableOrderedMetadata:
            raise ValueError("ordered_metadata must be SnapshotTableOrderedMetadata or None")
        if self.descriptor.degraded_reason is DegradedReason.TABLE_FAILED:
            if self.reader is not None:
                raise ValueError("failed table must not publish a reader")
            if self.artifact is not None:
                raise ValueError("failed table must not publish an artifact")
            if self.batch_reader is not None:
                raise ValueError("failed table must not publish a batch reader")
            if self.ordered_metadata is not None:
                raise ValueError("failed table must not publish ordered metadata")
            return
        if self.reader is None:
            return


@dataclass(frozen=True, slots=True)
class SnapshotTableSet:
    snapshot_id: str
    snapshot_digest: DigestRef
    table_ruleset_version: int
    tables: tuple[SnapshotTable, ...]
    diagnostics: tuple[MaterializationDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        _require_opaque_id(self.snapshot_id, "snapshot_id")
        if type(self.snapshot_digest) is not DigestRef:
            raise ValueError("snapshot_digest must be DigestRef")
        if type(self.table_ruleset_version) is not int or self.table_ruleset_version < 1:
            raise ValueError("table_ruleset_version must be a positive int")
        if type(self.tables) is not tuple:
            raise ValueError("tables must be a tuple")
        seen: set[str] = set()
        for table in self.tables:
            if type(table) is not SnapshotTable:
                raise ValueError("tables must contain SnapshotTable")
            if table.descriptor.table_name in seen:
                raise ValueError("table set must not repeat table_name")
            seen.add(table.descriptor.table_name)
        _require_diagnostics(self.diagnostics)


@dataclass(frozen=True, slots=True)
class SqlSnapshotMaterializationRequest:
    parse_result: ParseResult
    sql_source_digest: DigestRef
    ruleset: TableRulesetSnapshot
    table_ruleset_version: int
    materialization_stage: MaterializationStage
    policy: MaterializationPolicy
    context: ParserInvocationContext
    requested_tables: tuple[str, ...] | None = None
    artifact_store: object | None = None

    def __post_init__(self) -> None:
        if type(self.parse_result) is not ParseResult:
            raise ValueError("parse_result must be ParseResult")
        if type(self.sql_source_digest) is not DigestRef:
            raise ValueError("sql_source_digest must be DigestRef")
        if type(self.ruleset) is not TableRulesetSnapshot:
            raise ValueError("ruleset must be TableRulesetSnapshot")
        if type(self.table_ruleset_version) is not int or self.table_ruleset_version < 1:
            raise ValueError("table_ruleset_version must be a positive int")
        if type(self.materialization_stage) is not MaterializationStage:
            raise ValueError("materialization_stage must be MaterializationStage")
        if type(self.policy) is not MaterializationPolicy:
            raise ValueError("policy must be MaterializationPolicy")
        if type(self.context) is not ParserInvocationContext:
            raise ValueError("context must be ParserInvocationContext")
        _require_optional_store(self.artifact_store)
        if self.requested_tables is None:
            return
        if type(self.requested_tables) is not tuple:
            raise ValueError("requested_tables must be a tuple or None")
        seen: set[str] = set()
        for name in self.requested_tables:
            _require_non_empty(name, "requested table")
            if name in seen:
                raise ValueError("requested_tables must not contain duplicates")
            seen.add(name)


@dataclass(frozen=True, slots=True)
class BusinessSnapshotMaterializationRequest:
    sql: SqlSnapshotMaterializationRequest
    logic: CompositeLogicSource
    xml: XmlParseResult | None = None

    def __post_init__(self) -> None:
        if type(self.sql) is not SqlSnapshotMaterializationRequest:
            raise ValueError("sql must be SqlSnapshotMaterializationRequest")
        if type(self.logic) is not CompositeLogicSource:
            raise ValueError("logic must be CompositeLogicSource")
        if self.logic.empty:
            if self.xml is not None:
                raise ValueError("EMPTY source forbids an XML document result")
            return
        if type(self.xml) is not XmlParseResult:
            raise ValueError("non-empty source requires an XML document result")


class RepositoryProviderError(Exception):
    """Stable provider-boundary error mapped into materialization diagnostics."""

    def __init__(
        self,
        code: MaterializationDiagnosticCode,
        message: str,
        *,
        retryable: bool = False,
        table: str | None = None,
    ) -> None:
        if type(code) is not MaterializationDiagnosticCode:
            raise ValueError("code must be MaterializationDiagnosticCode")
        if type(message) is not str or message == "":
            raise ValueError("message must be a non-empty string")
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.table = table


@dataclass(frozen=True, slots=True)
class RepositoryRef:
    repository_id: str
    ref: str

    def __post_init__(self) -> None:
        _require_non_empty(self.repository_id, "repository_id")
        _require_non_empty(self.ref, "ref")
        if "/" in self.repository_id or "\\" in self.repository_id or "\x00" in self.repository_id:
            raise ValueError("repository_id must not be a path-shaped identity")
        if "\\" in self.ref or "\x00" in self.ref:
            raise ValueError("ref must not contain path separators or NUL")


@dataclass(frozen=True, slots=True)
class RepositoryRefTimeoutPolicy:
    open_ref_timeout_ms: int | None = None
    operation_timeout_ms: int | None = None

    def __post_init__(self) -> None:
        _require_optional_non_negative_int(self.open_ref_timeout_ms, "open_ref_timeout_ms")
        _require_optional_non_negative_int(self.operation_timeout_ms, "operation_timeout_ms")


@dataclass(frozen=True, slots=True)
class RepositoryColumn:
    name: str
    ordinal: int
    display_name: str | None = None
    scalar_type: str | None = None
    nullable: bool | None = None
    raw_type: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "name")
        _require_non_negative_int(self.ordinal, "ordinal")
        if self.display_name is not None:
            _require_non_empty(self.display_name, "display_name")
        if self.scalar_type is not None:
            _require_non_empty(self.scalar_type, "scalar_type")
        if self.nullable is not None and type(self.nullable) is not bool:
            raise ValueError("nullable must be bool or None")
        if self.raw_type is not None:
            _require_non_empty(self.raw_type, "raw_type")


@dataclass(frozen=True, slots=True)
class RepositoryCatalogTable:
    table_name: str
    columns: tuple[RepositoryColumn, ...]
    display_table_name: str | None = None
    primary_key_columns: tuple[str, ...] = ()
    row_count: int | None = None
    repository_table_version: str | None = None
    table_root_hash: str | None = None
    schema_facts_digest: DigestRef | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.table_name, "table_name")
        if type(self.columns) is not tuple:
            raise ValueError("columns must be a tuple")
        seen: set[str] = set()
        for index, column in enumerate(self.columns):
            if type(column) is not RepositoryColumn:
                raise ValueError("columns must contain RepositoryColumn")
            if column.ordinal != index:
                raise ValueError("column ordinal must match catalog order")
            if column.name in seen:
                raise ValueError("catalog columns must not repeat name")
            seen.add(column.name)
        if self.display_table_name is not None:
            _require_non_empty(self.display_table_name, "display_table_name")
        if type(self.primary_key_columns) is not tuple:
            raise ValueError("primary_key_columns must be a tuple")
        for name in self.primary_key_columns:
            _require_non_empty(name, "primary_key column")
        if self.row_count is not None:
            _require_non_negative_int(self.row_count, "row_count")
        if self.repository_table_version is not None:
            _require_non_empty(self.repository_table_version, "repository_table_version")
        if self.table_root_hash is not None:
            _require_non_empty(self.table_root_hash, "table_root_hash")
        if self.schema_facts_digest is not None and type(self.schema_facts_digest) is not DigestRef:
            raise ValueError("schema_facts_digest must be DigestRef or None")


@dataclass(frozen=True, slots=True)
class RepositoryTableCatalog:
    repository_id: str
    repository_ref: str
    resolved_commit_hash: str
    repository_server_contract_version: int
    tables: tuple[RepositoryCatalogTable, ...]
    repository_engine_version: str | None = None
    catalog_digest: DigestRef | None = None
    cache_hit: bool = False

    def __post_init__(self) -> None:
        _require_non_empty(self.repository_id, "repository_id")
        _require_non_empty(self.repository_ref, "repository_ref")
        _require_opaque_id(self.resolved_commit_hash, "resolved_commit_hash")
        if (
            type(self.repository_server_contract_version) is not int
            or self.repository_server_contract_version < 1
        ):
            raise ValueError("repository_server_contract_version must be a positive int")
        if type(self.tables) is not tuple:
            raise ValueError("tables must be a tuple")
        seen: set[str] = set()
        for table in self.tables:
            if type(table) is not RepositoryCatalogTable:
                raise ValueError("tables must contain RepositoryCatalogTable")
            if table.table_name in seen:
                raise ValueError("catalog tables must not repeat table_name")
            seen.add(table.table_name)
        if self.repository_engine_version is not None:
            _require_non_empty(self.repository_engine_version, "repository_engine_version")
        if self.catalog_digest is not None and type(self.catalog_digest) is not DigestRef:
            raise ValueError("catalog_digest must be DigestRef or None")
        if type(self.cache_hit) is not bool:
            raise ValueError("cache_hit must be bool")


@dataclass(frozen=True, slots=True)
class HiddenFinalSummary:
    snapshot_id: str
    snapshot_digest: DigestRef
    raw_state_digest: DigestRef
    materialization_stage: MaterializationStage
    parser_version: int
    table_ruleset_version: int
    summary_contract_version: int
    scalar_encoding_version: int
    snapshot_materialization_contract_version: int
    digest_contract_version: int
    tables: tuple[SnapshotTableDescriptor, ...]

    def __post_init__(self) -> None:
        _require_opaque_id(self.snapshot_id, "snapshot_id")
        if type(self.snapshot_digest) is not DigestRef:
            raise ValueError("snapshot_digest must be DigestRef")
        if type(self.raw_state_digest) is not DigestRef:
            raise ValueError("raw_state_digest must be DigestRef")
        if type(self.materialization_stage) is not MaterializationStage:
            raise ValueError("materialization_stage must be MaterializationStage")
        if type(self.parser_version) is not int or self.parser_version < 1:
            raise ValueError("parser_version must be a positive int")
        if type(self.table_ruleset_version) is not int or self.table_ruleset_version < 1:
            raise ValueError("table_ruleset_version must be a positive int")
        if type(self.summary_contract_version) is not int or self.summary_contract_version < 1:
            raise ValueError("summary_contract_version must be a positive int")
        if type(self.scalar_encoding_version) is not int or self.scalar_encoding_version < 1:
            raise ValueError("scalar_encoding_version must be a positive int")
        if (
            type(self.snapshot_materialization_contract_version) is not int
            or self.snapshot_materialization_contract_version < 1
        ):
            raise ValueError("snapshot_materialization_contract_version must be a positive int")
        if type(self.digest_contract_version) is not int or self.digest_contract_version < 1:
            raise ValueError("digest_contract_version must be a positive int")
        if type(self.tables) is not tuple:
            raise ValueError("tables must be a tuple")
        seen: set[str] = set()
        for table in self.tables:
            if type(table) is not SnapshotTableDescriptor:
                raise ValueError("tables must contain SnapshotTableDescriptor")
            if table.table_name in seen:
                raise ValueError("hidden summary tables must not repeat table_name")
            seen.add(table.table_name)


@runtime_checkable
class RepositoryTableReader(Protocol):
    def catalog_table(self) -> RepositoryCatalogTable:
        """Return the catalog table this reader was opened for."""

    def column_order(self) -> tuple[str, ...]:
        """Return catalog column names in tuple order."""

    def stream_rows(self) -> Iterator[tuple[object | None, ...]]:
        """Yield positional tuples; non-rewind."""

    def close(self) -> None:
        """Idempotent close."""


@runtime_checkable
class RepositoryRefSession(Protocol):
    def pinned_commit_hash(self) -> str:
        """Return the immutable commit this session is pinned to."""

    def get_catalog(self) -> RepositoryTableCatalog:
        """Eager-load and memoize the business-table catalog."""

    def read_hidden_summary(self) -> HiddenFinalSummary | None:
        """Return the hidden FINAL summary, or None when missing."""

    def open_table_reader(self, table_name: str) -> RepositoryTableReader:
        """Open a tuple reader for a catalog table."""

    def export_table_artifact(self, table_name: str, export_format: str) -> None:
        """Optional export fast path. S4 returns None / unsupported."""

    def close(self) -> None:
        """Idempotent close of session resources."""


@runtime_checkable
class RepositoryTableAccessProvider(Protocol):
    def open_ref(
        self,
        repository_ref: RepositoryRef,
        timeout_policy: RepositoryRefTimeoutPolicy | None,
    ) -> RepositoryRefSession:
        """Open a read-only session pinned to a resolved commit."""


@dataclass(frozen=True, slots=True)
class RepositoryRefMaterializationRequest:
    repository_ref: RepositoryRef
    provider: RepositoryTableAccessProvider
    ruleset: TableRulesetSnapshot
    table_ruleset_version: int
    materialization_stage: MaterializationStage
    policy: MaterializationPolicy
    context: ParserInvocationContext
    timeout_policy: RepositoryRefTimeoutPolicy | None = None
    requested_tables: tuple[str, ...] | None = None
    digest_contract_version: int = DIGEST_CONTRACT_VERSION
    scalar_encoding_version: int = SCALAR_ENCODING_VERSION
    snapshot_materialization_contract_version: int = SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION
    parser_version: int | None = None
    artifact_store: object | None = None

    def __post_init__(self) -> None:
        if type(self.repository_ref) is not RepositoryRef:
            raise ValueError("repository_ref must be RepositoryRef")
        if not isinstance(self.provider, RepositoryTableAccessProvider):
            raise ValueError("provider must implement RepositoryTableAccessProvider")
        if type(self.ruleset) is not TableRulesetSnapshot:
            raise ValueError("ruleset must be TableRulesetSnapshot")
        if type(self.table_ruleset_version) is not int or self.table_ruleset_version < 1:
            raise ValueError("table_ruleset_version must be a positive int")
        if self.materialization_stage is not MaterializationStage.FINAL:
            raise ValueError("repository ref materialization requires FINAL stage")
        if type(self.policy) is not MaterializationPolicy:
            raise ValueError("policy must be MaterializationPolicy")
        if type(self.context) is not ParserInvocationContext:
            raise ValueError("context must be ParserInvocationContext")
        if self.timeout_policy is not None and type(self.timeout_policy) is not RepositoryRefTimeoutPolicy:
            raise ValueError("timeout_policy must be RepositoryRefTimeoutPolicy or None")
        if self.digest_contract_version != DIGEST_CONTRACT_VERSION:
            raise ValueError("digest_contract_version must be 1")
        if self.scalar_encoding_version != SCALAR_ENCODING_VERSION:
            raise ValueError("scalar_encoding_version must be 1")
        if self.snapshot_materialization_contract_version != (
            SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION
        ):
            raise ValueError("snapshot_materialization_contract_version must be 1")
        if self.parser_version is not None and (
            type(self.parser_version) is not int or self.parser_version < 1
        ):
            raise ValueError("parser_version must be a positive int or None")
        _require_optional_store(self.artifact_store)
        if self.requested_tables is None:
            return
        if type(self.requested_tables) is not tuple:
            raise ValueError("requested_tables must be a tuple or None")
        seen: set[str] = set()
        for name in self.requested_tables:
            _require_non_empty(name, "requested table")
            if name in seen:
                raise ValueError("requested_tables must not contain duplicates")
            seen.add(name)


@dataclass(frozen=True, slots=True)
class SnapshotMaterializationResult:
    status: SnapshotMaterializationStatus
    materialization_stage: MaterializationStage
    cache_trust_level: CacheTrustLevel
    diagnostics: tuple[MaterializationDiagnostic, ...]
    snapshot: Snapshot | None = None
    summary: SnapshotSummary | None = None
    table_set: SnapshotTableSet | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not SnapshotMaterializationStatus:
            raise ValueError("status must be SnapshotMaterializationStatus")
        if type(self.materialization_stage) is not MaterializationStage:
            raise ValueError("materialization_stage must be MaterializationStage")
        if type(self.cache_trust_level) is not CacheTrustLevel:
            raise ValueError("cache_trust_level must be CacheTrustLevel")
        _require_diagnostics(self.diagnostics)
        _require_stage_trust(self.materialization_stage, self.cache_trust_level)
        if self.cache_trust_level is CacheTrustLevel.COMMIT_VALIDATED:
            raise ValueError("R3 must not self-promote to COMMIT_VALIDATED")
        if self.status is SnapshotMaterializationStatus.FAILED:
            if self.snapshot is not None or self.summary is not None or self.table_set is not None:
                raise ValueError("FAILED must not publish Snapshot, Summary, or TableSet")
            if not self.diagnostics:
                raise ValueError("FAILED requires diagnostics")
            return
        if type(self.snapshot) is not Snapshot:
            raise ValueError("COMPLETE/PARTIAL requires Snapshot")
        if type(self.summary) is not SnapshotSummary:
            raise ValueError("COMPLETE/PARTIAL requires SnapshotSummary")
        if self.snapshot.snapshot_id != self.summary.snapshot_id:
            raise ValueError("snapshot_id must match between Snapshot and Summary")
        if self.snapshot.snapshot_digest != self.summary.snapshot_digest:
            raise ValueError("snapshot_digest must match between Snapshot and Summary")
        if self.table_set is not None:
            if type(self.table_set) is not SnapshotTableSet:
                raise ValueError("table_set must be SnapshotTableSet or None")
            if self.table_set.snapshot_id != self.snapshot.snapshot_id:
                raise ValueError("table_set snapshot_id must match Snapshot")
            if self.table_set.snapshot_digest != self.snapshot.snapshot_digest:
                raise ValueError("table_set snapshot_digest must match Snapshot")
        ready = sum(
            1
            for table in self.summary.tables
            if table.degraded_reason is not DegradedReason.TABLE_FAILED
        )
        failed = len(self.summary.tables) - ready
        if self.status is SnapshotMaterializationStatus.COMPLETE:
            if failed != 0:
                raise ValueError("COMPLETE forbids failed tables")
            return
        if ready == 0 or failed == 0:
            raise ValueError("PARTIAL requires a mix of ready and failed tables")


def _require_stage_trust(stage: MaterializationStage, trust: CacheTrustLevel) -> None:
    if stage is MaterializationStage.PROVISIONAL:
        if trust is not CacheTrustLevel.PROVISIONAL:
            raise ValueError("PROVISIONAL stage requires PROVISIONAL trust")
        return
    if trust is not CacheTrustLevel.CONTENT_VERIFIED:
        raise ValueError("FINAL stage requires CONTENT_VERIFIED trust")


def _require_non_empty(value: object, label: str) -> None:
    if type(value) is not str or value == "":
        raise ValueError(f"{label} must be a non-empty string")


def _require_opaque_id(value: object, label: str) -> None:
    _require_non_empty(value, label)
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a non-empty string")
    if value.startswith("/") or "\\" in value or "\x00" in value:
        raise ValueError(f"{label} must not be a path-shaped identity")


def _require_non_negative_int(value: object, label: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative int")


def _require_optional_non_negative_int(value: object, label: str) -> None:
    if value is None:
        return
    _require_non_negative_int(value, label)


def _require_diagnostics(diagnostics: tuple[MaterializationDiagnostic, ...]) -> None:
    if type(diagnostics) is not tuple:
        raise ValueError("diagnostics must be a tuple")
    if len(diagnostics) > _MAX_DIAGNOSTICS:
        raise ValueError("diagnostics exceed max_diagnostics")
    for diagnostic in diagnostics:
        if type(diagnostic) is not MaterializationDiagnostic:
            raise ValueError("diagnostics must contain MaterializationDiagnostic")


def _require_optional_store(value: object) -> None:
    if value is None:
        return
    put = getattr(value, "put", None)
    locate = getattr(value, "locate", None)
    if not callable(put) or not callable(locate):
        raise ValueError("artifact_store must implement ArtifactStorePort")
