from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ...artifacts.manifest import ArtifactManifest, ArtifactRef
from ...core.digests import DigestRef
from ...core.diagnostics import DiagnosticRecord
from ..snapshot_materialization.models import SnapshotMaterializationResult, SnapshotTable
from ...core.identifiers import canonical_identifier
from .versions import (
    REPOSITORY_IMPORT_BUNDLE_CONTENT_FILE_NAME,
    REPOSITORY_IMPORT_BUNDLE_CONTENT_SCHEMA_VERSION,
    REPOSITORY_IMPORT_BUNDLE_MANIFEST_KIND,
    REPOSITORY_IMPORT_CONTRACT_VERSION,
    REPOSITORY_IMPORT_MANIFEST_FILE_NAME,
    REPOSITORY_IMPORT_NULL_TOKEN,
    REPOSITORY_IMPORT_REPLAY_SQL_FILE_NAME,
    REPOSITORY_IMPORT_ROW_FORMAT_CSV,
    REPOSITORY_IMPORT_ROW_FORMAT_PARQUET,
    REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY,
    REPOSITORY_IMPORT_ROW_FORMAT_TSV,
    REPOSITORY_IMPORT_ROWS_CSV_FILE_NAME,
    REPOSITORY_IMPORT_ROWS_PARQUET_FILE_NAME,
    REPOSITORY_IMPORT_ROWS_TSV_FILE_NAME,
    REPOSITORY_IMPORT_SCHEMA_FILE_NAME,
    REPOSITORY_IMPORT_SCHEMA_FILE_SCHEMA_VERSION,
    REPOSITORY_IMPORT_TABLE_CONTENT_FILE_NAME,
    REPOSITORY_IMPORT_TABLE_CONTENT_SCHEMA_VERSION,
    REPOSITORY_IMPORT_TABLE_MANIFEST_KIND,
    REPOSITORY_IMPORT_TABLES_DIR_NAME,
)


class RepositoryImportArtifactLayout(str, Enum):
    TABLE_FILE_SET = "TABLE_FILE_SET"
    REPLAY_ONLY_MINIMAL = "REPLAY_ONLY_MINIMAL"


@dataclass(frozen=True, slots=True)
class RepositoryImportFileArtifact:
    role: str
    relative_path: str
    path: Path
    content_digest: DigestRef | str
    content_size_bytes: int
    export_format: str | None = None
    binary: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.role, str) or not self.role.strip():
            raise ValueError("role must be a non-empty string")
        if not isinstance(self.relative_path, str) or not self.relative_path.strip():
            raise ValueError("relative_path must be a non-empty string")
        if Path(self.relative_path).is_absolute():
            raise ValueError("relative_path must be relative")
        if not isinstance(self.path, Path):
            raise TypeError("path must be a Path")
        if (
            not isinstance(self.content_size_bytes, int)
            or isinstance(self.content_size_bytes, bool)
            or self.content_size_bytes < 0
        ):
            raise ValueError("content_size_bytes must be a non-negative integer")
        object.__setattr__(self, "content_digest", _coerce_digest(self.content_digest))
        if self.export_format is not None:
            object.__setattr__(self, "export_format", self.export_format.upper())


@dataclass(frozen=True, slots=True)
class RepositoryImportTableArtifact:
    table_name: str
    display_table_name: str
    artifact_contract_version: str
    manifest: ArtifactManifest
    manifest_ref: ArtifactRef
    manifest_path: Path
    content_path: Path
    table_dir: Path
    schema_file: RepositoryImportFileArtifact
    rows_csv_file: RepositoryImportFileArtifact | None = None
    rows_tsv_file: RepositoryImportFileArtifact | None = None
    replay_sql_file: RepositoryImportFileArtifact | None = None
    rows_parquet_file: RepositoryImportFileArtifact | None = None
    reused: bool = False
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name.strip():
            raise ValueError("table_name must be a non-empty string")
        if not isinstance(self.display_table_name, str) or not self.display_table_name.strip():
            raise ValueError("display_table_name must be a non-empty string")
        if not isinstance(self.artifact_contract_version, str) or not self.artifact_contract_version:
            raise ValueError("artifact_contract_version must be a non-empty string")
        if not isinstance(self.manifest, ArtifactManifest):
            raise TypeError("manifest must be an ArtifactManifest")
        if not isinstance(self.manifest_ref, ArtifactRef):
            raise TypeError("manifest_ref must be an ArtifactRef")
        for field_name in (
            "manifest_path",
            "content_path",
            "table_dir",
        ):
            if not isinstance(getattr(self, field_name), Path):
                raise TypeError(f"{field_name} must be a Path")
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if self.manifest.artifact_contract_version != self.artifact_contract_version:
            raise ValueError("manifest contract version mismatch")
        if self.manifest.artifact_kind != REPOSITORY_IMPORT_TABLE_MANIFEST_KIND:
            raise ValueError("table manifest kind mismatch")

    @property
    def files(self) -> tuple[RepositoryImportFileArtifact, ...]:
        items = [self.schema_file]
        if self.rows_csv_file is not None:
            items.append(self.rows_csv_file)
        if self.rows_tsv_file is not None:
            items.append(self.rows_tsv_file)
        if self.replay_sql_file is not None:
            items.append(self.replay_sql_file)
        if self.rows_parquet_file is not None:
            items.append(self.rows_parquet_file)
        return tuple(items)


@dataclass(frozen=True, slots=True)
class RepositoryImportArtifactBuildStats:
    table_count: int
    shared_row_cache_entries: int
    shared_row_cache_hits: int
    shared_row_cache_misses: int
    reused_table_count: int
    rows_parquet_write_count: int
    rows_parquet_reuse_count: int

    def __post_init__(self) -> None:
        for field_name in (
            "table_count",
            "shared_row_cache_entries",
            "shared_row_cache_hits",
            "shared_row_cache_misses",
            "reused_table_count",
            "rows_parquet_write_count",
            "rows_parquet_reuse_count",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")

    def to_payload(self) -> dict[str, int]:
        return {
            "table_count": self.table_count,
            "shared_row_cache_entries": self.shared_row_cache_entries,
            "shared_row_cache_hits": self.shared_row_cache_hits,
            "shared_row_cache_misses": self.shared_row_cache_misses,
            "reused_table_count": self.reused_table_count,
            "rows_parquet_write_count": self.rows_parquet_write_count,
            "rows_parquet_reuse_count": self.rows_parquet_reuse_count,
        }


@dataclass(frozen=True, slots=True)
class RepositoryImportArtifact:
    snapshot_id: str
    snapshot_digest: DigestRef | str
    artifact_contract_version: str
    manifest: ArtifactManifest
    manifest_ref: ArtifactRef
    manifest_path: Path
    content_path: Path
    bundle_dir: Path
    replay_sql_file: RepositoryImportFileArtifact
    table_artifacts: tuple[RepositoryImportTableArtifact, ...]
    reused: bool = False
    build_stats: RepositoryImportArtifactBuildStats | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id.strip():
            raise ValueError("snapshot_id must be a non-empty string")
        if not isinstance(self.artifact_contract_version, str) or not self.artifact_contract_version:
            raise ValueError("artifact_contract_version must be a non-empty string")
        if not isinstance(self.manifest, ArtifactManifest):
            raise TypeError("manifest must be an ArtifactManifest")
        if not isinstance(self.manifest_ref, ArtifactRef):
            raise TypeError("manifest_ref must be an ArtifactRef")
        for field_name in (
            "manifest_path",
            "content_path",
            "bundle_dir",
        ):
            if not isinstance(getattr(self, field_name), Path):
                raise TypeError(f"{field_name} must be a Path")
        object.__setattr__(self, "snapshot_digest", _coerce_digest(self.snapshot_digest))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if self.manifest.artifact_contract_version != self.artifact_contract_version:
            raise ValueError("manifest contract version mismatch")
        if self.manifest.artifact_kind != REPOSITORY_IMPORT_BUNDLE_MANIFEST_KIND:
            raise ValueError("bundle manifest kind mismatch")
        if self.build_stats is not None and not isinstance(
            self.build_stats,
            RepositoryImportArtifactBuildStats,
        ):
            raise TypeError("build_stats must be a RepositoryImportArtifactBuildStats or None")

    @property
    def table_count(self) -> int:
        return len(self.table_artifacts)

    @property
    def row_count_total(self) -> int:
        total = 0
        for table_artifact in self.table_artifacts:
            total += int(table_artifact.manifest.metadata["row_count"])
        return total


@dataclass(frozen=True, slots=True)
class RepositoryImportTableManifestPayload:
    snapshot_id: str
    snapshot_digest: str
    table_name: str
    display_table_name: str
    row_count: int
    column_count: int
    columns: tuple[Mapping[str, object], ...]
    compare_key_columns: tuple[str, ...]
    source_ddl_digest: str | None
    compare_schema_digest: str
    raw_content_digest: str
    schema_file: Mapping[str, object]
    rows_csv_file: Mapping[str, object] | None
    rows_tsv_file: Mapping[str, object] | None
    replay_sql_file: Mapping[str, object] | None
    rows_parquet_file: Mapping[str, object] | None
    table_ruleset_version: str
    scalar_encoding_version: str
    row_materialization_profile: str
    export_formats: tuple[str, ...]
    diagnostics: tuple[Mapping[str, object], ...] = field(default_factory=tuple)
    schema_version: str = REPOSITORY_IMPORT_TABLE_CONTENT_SCHEMA_VERSION
    canonical_artifact_ref: str | None = None
    previous_canonical_artifact_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.schema_version, str) or not self.schema_version:
            raise ValueError("schema_version must be a non-empty string")
        if self.schema_version != REPOSITORY_IMPORT_TABLE_CONTENT_SCHEMA_VERSION:
            raise ValueError("table manifest schema version mismatch")
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id.strip():
            raise ValueError("snapshot_id must be a non-empty string")
        if not isinstance(self.snapshot_digest, str) or not self.snapshot_digest.strip():
            raise ValueError("snapshot_digest must be a non-empty string")
        if not isinstance(self.table_name, str) or not self.table_name.strip():
            raise ValueError("table_name must be a non-empty string")
        if not isinstance(self.display_table_name, str) or not self.display_table_name.strip():
            raise ValueError("display_table_name must be a non-empty string")
        if not isinstance(self.row_count, int) or isinstance(self.row_count, bool) or self.row_count < 0:
            raise ValueError("row_count must be a non-negative integer")
        if not isinstance(self.column_count, int) or isinstance(self.column_count, bool) or self.column_count < 0:
            raise ValueError("column_count must be a non-negative integer")
        if not isinstance(self.columns, tuple):
            object.__setattr__(self, "columns", tuple(self.columns))
        if not isinstance(self.compare_key_columns, tuple):
            object.__setattr__(self, "compare_key_columns", tuple(self.compare_key_columns))
        if self.source_ddl_digest is not None and not isinstance(self.source_ddl_digest, str):
            raise TypeError("source_ddl_digest must be a string or None")
        if self.canonical_artifact_ref is not None and (
            not isinstance(self.canonical_artifact_ref, str) or not self.canonical_artifact_ref.strip()
        ):
            raise TypeError("canonical_artifact_ref must be a string or None")
        if self.previous_canonical_artifact_ref is not None and (
            not isinstance(self.previous_canonical_artifact_ref, str)
            or not self.previous_canonical_artifact_ref.strip()
        ):
            raise TypeError("previous_canonical_artifact_ref must be a string or None")
        if not isinstance(self.compare_schema_digest, str) or not self.compare_schema_digest.strip():
            raise ValueError("compare_schema_digest must be a non-empty string")
        if not isinstance(self.raw_content_digest, str) or not self.raw_content_digest.strip():
            raise ValueError("raw_content_digest must be a non-empty string")
        if not isinstance(self.schema_file, Mapping):
            raise TypeError("schema_file must be a mapping")
        if self.rows_csv_file is not None and not isinstance(self.rows_csv_file, Mapping):
            raise TypeError("rows_csv_file must be a mapping")
        if self.rows_tsv_file is not None and not isinstance(self.rows_tsv_file, Mapping):
            raise TypeError("rows_tsv_file must be a mapping")
        if self.replay_sql_file is not None and not isinstance(self.replay_sql_file, Mapping):
            raise TypeError("replay_sql_file must be a mapping or None")
        if self.rows_parquet_file is not None and not isinstance(self.rows_parquet_file, Mapping):
            raise TypeError("rows_parquet_file must be a mapping or None")
        if not isinstance(self.table_ruleset_version, str) or not self.table_ruleset_version:
            raise ValueError("table_ruleset_version must be a non-empty string")
        if not isinstance(self.scalar_encoding_version, str) or not self.scalar_encoding_version:
            raise ValueError("scalar_encoding_version must be a non-empty string")
        if not isinstance(self.row_materialization_profile, str) or not self.row_materialization_profile:
            raise ValueError("row_materialization_profile must be a non-empty string")
        if not isinstance(self.export_formats, tuple):
            object.__setattr__(self, "export_formats", tuple(self.export_formats))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


@dataclass(frozen=True, slots=True)
class RepositoryImportBundleContent:
    snapshot_id: str
    snapshot_digest: str
    raw_state_digest: str
    row_count_total: int
    table_count: int
    table_artifacts: tuple[Mapping[str, object], ...]
    replay_sql_file: Mapping[str, object]
    requested_tables: tuple[str, ...]
    export_formats: tuple[str, ...]
    diagnostics: tuple[Mapping[str, object], ...] = field(default_factory=tuple)
    schema_version: str = REPOSITORY_IMPORT_BUNDLE_CONTENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.schema_version, str) or not self.schema_version:
            raise ValueError("schema_version must be a non-empty string")
        if self.schema_version != REPOSITORY_IMPORT_BUNDLE_CONTENT_SCHEMA_VERSION:
            raise ValueError("bundle content schema version mismatch")
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id.strip():
            raise ValueError("snapshot_id must be a non-empty string")
        if not isinstance(self.snapshot_digest, str) or not self.snapshot_digest.strip():
            raise ValueError("snapshot_digest must be a non-empty string")
        if not isinstance(self.raw_state_digest, str) or not self.raw_state_digest.strip():
            raise ValueError("raw_state_digest must be a non-empty string")
        if not isinstance(self.row_count_total, int) or isinstance(self.row_count_total, bool) or self.row_count_total < 0:
            raise ValueError("row_count_total must be a non-negative integer")
        if not isinstance(self.table_count, int) or isinstance(self.table_count, bool) or self.table_count < 0:
            raise ValueError("table_count must be a non-negative integer")
        if not isinstance(self.table_artifacts, tuple):
            object.__setattr__(self, "table_artifacts", tuple(self.table_artifacts))
        if not isinstance(self.replay_sql_file, Mapping):
            raise TypeError("replay_sql_file must be a mapping")
        if not isinstance(self.requested_tables, tuple):
            object.__setattr__(self, "requested_tables", tuple(self.requested_tables))
        if not isinstance(self.export_formats, tuple):
            object.__setattr__(self, "export_formats", tuple(self.export_formats))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


def _coerce_digest(value: DigestRef | str) -> DigestRef:
    if isinstance(value, DigestRef):
        return value
    return DigestRef.parse(str(value))
