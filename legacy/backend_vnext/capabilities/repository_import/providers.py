from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ...artifacts.manifest import ArtifactRef
from ...core.digests import DigestRef
from ...core.diagnostics import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from ..snapshot_materialization.models import SnapshotTableDescriptor
from .versions import REPOSITORY_IMPORT_CONTRACT_VERSION


class RepositoryImportProvider(str, Enum):
    AUTO = "AUTO"
    SQL_DUMP_REPLAY = "SQL_DUMP_REPLAY"
    SINGLE_TABLE_CLI_IMPORT = "SINGLE_TABLE_CLI_IMPORT"
    MULTI_TABLE_CLI_IMPORT = "MULTI_TABLE_CLI_IMPORT"
    LOAD_DATA = "LOAD_DATA"
    PARQUET_IMPORT = "PARQUET_IMPORT"
    DOLT_SERVER_BULK_LOAD = "DOLT_SERVER_BULK_LOAD"
    SERVER_SESSION_BULK_LOAD = "SERVER_SESSION_BULK_LOAD"


class RepositoryImportImportMode(str, Enum):
    REPLACE_TABLE = "REPLACE_TABLE"
    UPSERT_TABLE = "UPSERT_TABLE"
    CREATE_ONLY = "CREATE_ONLY"


class RepositoryImportSchemaMode(str, Enum):
    SOURCE_CREATE_SQL = "SOURCE_CREATE_SQL"
    DESCRIPTOR_DDL = "DESCRIPTOR_DDL"
    IMPORT_SCHEMA_FILE = "IMPORT_SCHEMA_FILE"


class RepositoryImportServerMode(str, Enum):
    DISABLED = "DISABLED"
    PER_IMPORT = "PER_IMPORT"
    WARM_SESSION = "WARM_SESSION"


class RepositoryImportCallerPolicy(str, Enum):
    DIRECT_RESPONSE_CALLER = "DIRECT_RESPONSE_CALLER"
    READ_ONLY_CALLER = "READ_ONLY_CALLER"
    WARMUP_CALLER = "WARMUP_CALLER"
    FINALIZE_WRITE_CALLER = "FINALIZE_WRITE_CALLER"

    @property
    def executes_import(self) -> bool:
        return self not in {
            RepositoryImportCallerPolicy.DIRECT_RESPONSE_CALLER,
            RepositoryImportCallerPolicy.READ_ONLY_CALLER,
        }

    @property
    def promotes_target_ref(self) -> bool:
        return self == RepositoryImportCallerPolicy.FINALIZE_WRITE_CALLER


class RepositoryImportStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class RepositoryImportValidationPolicy(str, Enum):
    DISABLED = "DISABLED"
    VERIFY_HIDDEN_SUMMARY_CATALOG = "VERIFY_HIDDEN_SUMMARY_CATALOG"
    VERIFY_SCHEMA_ROW_COUNT_SUMMARY = "VERIFY_SCHEMA_ROW_COUNT_SUMMARY"
    VERIFY_TABLE_DIGESTS = "VERIFY_TABLE_DIGESTS"
    VERIFY_ROW_COUNT_ONLY = "VERIFY_ROW_COUNT_ONLY"


class RepositoryImportValidationResult(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class RepositoryImportFailurePhase(str, Enum):
    PREPARE_FAILED = "PREPARE_FAILED"
    STAGING_FAILED = "STAGING_FAILED"
    IMPORT_FAILED = "IMPORT_FAILED"
    COMMIT_FAILED = "COMMIT_FAILED"
    READBACK_FAILED = "READBACK_FAILED"
    VALIDATION_MISMATCH = "VALIDATION_MISMATCH"
    CLEANUP_FAILED = "CLEANUP_FAILED"
    SERVER_START_FAILED = "SERVER_START_FAILED"
    SERVER_HEALTH_CHECK_FAILED = "SERVER_HEALTH_CHECK_FAILED"
    SERVER_SHUTDOWN_FAILED = "SERVER_SHUTDOWN_FAILED"
    TIMEOUT = "TIMEOUT"
    UNSUPPORTED_PROVIDER = "UNSUPPORTED_PROVIDER"


@dataclass(frozen=True, slots=True)
class RepositoryImportPlanTable:
    table_name: str
    descriptor: SnapshotTableDescriptor
    target_table_name: str | None = None
    import_mode: RepositoryImportImportMode | str = RepositoryImportImportMode.REPLACE_TABLE
    schema_mode: RepositoryImportSchemaMode | str = RepositoryImportSchemaMode.SOURCE_CREATE_SQL
    import_artifact_ref: ArtifactRef | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name.strip():
            raise ValueError("table_name must be a non-empty string")
        if not isinstance(self.descriptor, SnapshotTableDescriptor):
            raise TypeError("descriptor must be a SnapshotTableDescriptor")
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        if self.target_table_name is None:
            object.__setattr__(self, "target_table_name", self.table_name)
        else:
            if not isinstance(self.target_table_name, str) or not self.target_table_name.strip():
                raise ValueError("target_table_name must be a non-empty string or None")
            object.__setattr__(self, "target_table_name", canonical_identifier(self.target_table_name))
        object.__setattr__(self, "import_mode", RepositoryImportImportMode(self.import_mode))
        object.__setattr__(self, "schema_mode", RepositoryImportSchemaMode(self.schema_mode))
        if self.import_artifact_ref is not None and not isinstance(self.import_artifact_ref, ArtifactRef):
            raise TypeError("import_artifact_ref must be an ArtifactRef or None")


@dataclass(frozen=True, slots=True)
class RepositoryImportWorktreeContext:
    run_dir: Path
    repo_dir: Path

    def __post_init__(self) -> None:
        if not isinstance(self.run_dir, Path):
            raise TypeError("run_dir must be a Path")
        if not isinstance(self.repo_dir, Path):
            raise TypeError("repo_dir must be a Path")


@dataclass(frozen=True, slots=True)
class RepositoryImportExecutionContext:
    caller_policy: RepositoryImportCallerPolicy | str = RepositoryImportCallerPolicy.FINALIZE_WRITE_CALLER
    writer_lease_context: object | None = None
    idempotency_key: str | None = None
    worktree_context: RepositoryImportWorktreeContext | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "caller_policy", RepositoryImportCallerPolicy(self.caller_policy))
        if self.idempotency_key is not None and (
            not isinstance(self.idempotency_key, str) or not self.idempotency_key.strip()
        ):
            raise ValueError("idempotency_key must be a non-empty string or None")
        if self.worktree_context is not None and not isinstance(
            self.worktree_context,
            RepositoryImportWorktreeContext,
        ):
            raise TypeError("worktree_context must be a RepositoryImportWorktreeContext or None")


@dataclass(frozen=True, slots=True)
class RepositoryImportPlan:
    repository_id: str
    base_ref_or_commit: str
    target_branch_ref: str
    source_snapshot_id: str
    source_snapshot_digest: DigestRef | str
    table_ruleset_version: str
    import_contract_version: str = REPOSITORY_IMPORT_CONTRACT_VERSION
    provider_preference: RepositoryImportProvider | str = RepositoryImportProvider.AUTO
    benchmark_modes: tuple[str, ...] = field(default_factory=tuple)
    server_mode: RepositoryImportServerMode | str = RepositoryImportServerMode.DISABLED
    tables: tuple[RepositoryImportPlanTable, ...] = field(default_factory=tuple)
    validation_table_names: tuple[str, ...] = field(default_factory=tuple)
    commit_message: str = "backend_vnext repository import"
    validation_policy: RepositoryImportValidationPolicy | str = (
        RepositoryImportValidationPolicy.VERIFY_SCHEMA_ROW_COUNT_SUMMARY
    )

    def __post_init__(self) -> None:
        if not isinstance(self.repository_id, str) or not self.repository_id.strip():
            raise ValueError("repository_id must be a non-empty string")
        if not isinstance(self.base_ref_or_commit, str) or not self.base_ref_or_commit.strip():
            raise ValueError("base_ref_or_commit must be a non-empty string")
        if not isinstance(self.target_branch_ref, str) or not self.target_branch_ref.strip():
            raise ValueError("target_branch_ref must be a non-empty string")
        if not isinstance(self.source_snapshot_id, str) or not self.source_snapshot_id.strip():
            raise ValueError("source_snapshot_id must be a non-empty string")
        if not isinstance(self.table_ruleset_version, str) or not self.table_ruleset_version.strip():
            raise ValueError("table_ruleset_version must be a non-empty string")
        if not isinstance(self.import_contract_version, str) or not self.import_contract_version.strip():
            raise ValueError("import_contract_version must be a non-empty string")
        if not isinstance(self.commit_message, str) or not self.commit_message.strip():
            raise ValueError("commit_message must be a non-empty string")
        object.__setattr__(self, "source_snapshot_digest", DigestRef.parse(str(self.source_snapshot_digest)))
        object.__setattr__(self, "provider_preference", RepositoryImportProvider(self.provider_preference))
        object.__setattr__(self, "server_mode", RepositoryImportServerMode(self.server_mode))
        object.__setattr__(self, "validation_policy", RepositoryImportValidationPolicy(self.validation_policy))
        if not isinstance(self.benchmark_modes, tuple):
            object.__setattr__(self, "benchmark_modes", tuple(self.benchmark_modes))
        if not self.benchmark_modes:
            object.__setattr__(self, "benchmark_modes", tuple())
        normalized_tables = tuple(self.tables)
        if not normalized_tables:
            raise ValueError("tables must contain at least one table")
        for table in normalized_tables:
            if not isinstance(table, RepositoryImportPlanTable):
                raise TypeError("tables must contain RepositoryImportPlanTable values")
        object.__setattr__(self, "tables", normalized_tables)
        normalized_validation_tables: list[str] = []
        seen_validation_tables: set[str] = set()
        table_names = {table.table_name for table in normalized_tables}
        for table_name in self.validation_table_names:
            canonical_table = canonical_identifier(str(table_name))
            if not canonical_table or canonical_table in seen_validation_tables:
                continue
            if canonical_table not in table_names:
                raise ValueError(
                    f"validation_table_names must refer to tables in the plan: {canonical_table}"
                )
            seen_validation_tables.add(canonical_table)
            normalized_validation_tables.append(canonical_table)
        object.__setattr__(self, "validation_table_names", tuple(normalized_validation_tables))

    @property
    def effective_provider(self) -> RepositoryImportProvider:
        if self.provider_preference == RepositoryImportProvider.AUTO:
            return RepositoryImportProvider.SQL_DUMP_REPLAY
        return self.provider_preference

    @property
    def table_names(self) -> tuple[str, ...]:
        return tuple(table.table_name for table in self.tables)

    @property
    def effective_validation_table_names(self) -> tuple[str, ...]:
        if self.validation_policy != RepositoryImportValidationPolicy.VERIFY_TABLE_DIGESTS:
            return tuple()
        if self.validation_table_names:
            return self.validation_table_names
        return self.table_names


@dataclass(frozen=True, slots=True)
class RepositoryImportResult:
    repository_id: str
    target_ref: str
    commit_hash: str | None
    import_provider: RepositoryImportProvider | str
    status: RepositoryImportStatus | str
    validation_result: RepositoryImportValidationResult | str
    imported_table_count: int
    source_snapshot_digest: DigestRef | str
    readback_snapshot_digest: DigestRef | str | None
    provider_contract_version: str = REPOSITORY_IMPORT_CONTRACT_VERSION
    imported_table_names: tuple[str, ...] = field(default_factory=tuple)
    server_mode: RepositoryImportServerMode | str | None = None
    import_artifact_manifest_digest: DigestRef | str | None = None
    staging_artifact_bytes: int | None = None
    parse_duration_ms: int | None = None
    staging_duration_ms: int | None = None
    server_start_ms: int | None = None
    import_duration_ms: int | None = None
    commit_duration_ms: int | None = None
    validation_duration_ms: int | None = None
    cleanup_duration_ms: int | None = None
    total_duration_ms: int | None = None
    rows_per_second: float | None = None
    memory_peak: int | None = None
    dolt_version: str | None = None
    failure_phase: RepositoryImportFailurePhase | str | None = None
    failure_reason: str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    repository_path: Path | None = None
    run_dir: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.repository_id, str) or not self.repository_id.strip():
            raise ValueError("repository_id must be a non-empty string")
        if not isinstance(self.target_ref, str) or not self.target_ref.strip():
            raise ValueError("target_ref must be a non-empty string")
        if not isinstance(self.provider_contract_version, str) or not self.provider_contract_version.strip():
            raise ValueError("provider_contract_version must be a non-empty string")
        object.__setattr__(self, "import_provider", RepositoryImportProvider(self.import_provider))
        object.__setattr__(self, "status", RepositoryImportStatus(self.status))
        object.__setattr__(self, "validation_result", RepositoryImportValidationResult(self.validation_result))
        object.__setattr__(self, "source_snapshot_digest", DigestRef.parse(str(self.source_snapshot_digest)))
        if self.readback_snapshot_digest is not None:
            object.__setattr__(self, "readback_snapshot_digest", DigestRef.parse(str(self.readback_snapshot_digest)))
        if self.import_artifact_manifest_digest is not None:
            object.__setattr__(
                self,
                "import_artifact_manifest_digest",
                DigestRef.parse(str(self.import_artifact_manifest_digest)),
            )
        if self.server_mode is not None:
            object.__setattr__(self, "server_mode", RepositoryImportServerMode(self.server_mode))
        if self.failure_phase is not None:
            object.__setattr__(self, "failure_phase", RepositoryImportFailurePhase(self.failure_phase))
        if not isinstance(self.imported_table_count, int) or isinstance(self.imported_table_count, bool) or self.imported_table_count < 0:
            raise ValueError("imported_table_count must be a non-negative integer")
        if not isinstance(self.imported_table_names, tuple):
            object.__setattr__(self, "imported_table_names", tuple(self.imported_table_names))
        if self.repository_path is not None and not isinstance(self.repository_path, Path):
            raise TypeError("repository_path must be a Path or None")
        if self.run_dir is not None and not isinstance(self.run_dir, Path):
            raise TypeError("run_dir must be a Path or None")
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))
        for field_name in (
            "staging_artifact_bytes",
            "parse_duration_ms",
            "staging_duration_ms",
            "server_start_ms",
            "import_duration_ms",
            "commit_duration_ms",
            "validation_duration_ms",
            "cleanup_duration_ms",
            "total_duration_ms",
            "memory_peak",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer or None")
        if self.rows_per_second is not None and (
            isinstance(self.rows_per_second, bool) or self.rows_per_second < 0
        ):
            raise ValueError("rows_per_second must be non-negative or None")
        if not isinstance(self.failure_reason, str) and self.failure_reason is not None:
            raise TypeError("failure_reason must be a string or None")


def coerce_provider(value: RepositoryImportProvider | str) -> RepositoryImportProvider:
    return RepositoryImportProvider(value)


def coerce_server_mode(value: RepositoryImportServerMode | str) -> RepositoryImportServerMode:
    return RepositoryImportServerMode(value)


def coerce_validation_policy(
    value: RepositoryImportValidationPolicy | str,
) -> RepositoryImportValidationPolicy:
    return RepositoryImportValidationPolicy(value)
