from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
import re

import polars as pl

from ...artifacts.manifest import ArtifactManifest, ArtifactRef
from ...core.digests import DigestRef, canonical_json_bytes
from ...core.diagnostics import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from ..snapshot_materialization.hidden_summary import build_hidden_summary_replay_sql
from ..snapshot_materialization.models import (
    SnapshotMaterializationResult,
    SnapshotTable,
    SnapshotTableDescriptor,
)
from .canonical_storage import select_physical_snapshot_tables
from .models import (
    RepositoryImportArtifact,
    RepositoryImportArtifactBuildStats,
    RepositoryImportArtifactLayout,
    RepositoryImportBundleContent,
    RepositoryImportFileArtifact,
    RepositoryImportTableArtifact,
    RepositoryImportTableManifestPayload,
)
from .versions import (
    REPOSITORY_IMPORT_BUNDLE_CONTENT_SCHEMA_VERSION,
    REPOSITORY_IMPORT_BUNDLE_CONTENT_FILE_NAME,
    REPOSITORY_IMPORT_BUNDLE_MANIFEST_KIND,
    REPOSITORY_IMPORT_CONTRACT_VERSION,
    REPOSITORY_IMPORT_DEFAULT_INSERT_BATCH_SIZE,
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
    REPOSITORY_IMPORT_TABLE_CONTENT_SCHEMA_VERSION,
    REPOSITORY_IMPORT_TABLE_CONTENT_FILE_NAME,
    REPOSITORY_IMPORT_TABLE_MANIFEST_KIND,
    REPOSITORY_IMPORT_TABLES_DIR_NAME,
)


_DEFAULT_EXPORT_FORMATS: tuple[str, ...] = (
    REPOSITORY_IMPORT_ROW_FORMAT_CSV,
    REPOSITORY_IMPORT_ROW_FORMAT_TSV,
    REPOSITORY_IMPORT_ROW_FORMAT_PARQUET,
)
_DEFAULT_ARTIFACT_LAYOUT = RepositoryImportArtifactLayout.TABLE_FILE_SET


@dataclass(frozen=True, slots=True)
class RepositoryImportArtifactBuilder:
    root: Path
    export_formats: tuple[str, ...] = field(default_factory=lambda: _DEFAULT_EXPORT_FORMATS)
    artifact_layout: RepositoryImportArtifactLayout | str = _DEFAULT_ARTIFACT_LAYOUT
    parquet_compression: str | None = None
    insert_batch_size: int = REPOSITORY_IMPORT_DEFAULT_INSERT_BATCH_SIZE

    def __post_init__(self) -> None:
        root = self.root if isinstance(self.root, Path) else Path(self.root)
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "export_formats", _normalize_export_formats(self.export_formats))
        object.__setattr__(self, "artifact_layout", _normalize_artifact_layout(self.artifact_layout))
        if self.parquet_compression is not None and (
            not isinstance(self.parquet_compression, str) or not self.parquet_compression.strip()
        ):
            raise ValueError("parquet_compression must be a non-empty string or None")
        if (
            not isinstance(self.insert_batch_size, int)
            or isinstance(self.insert_batch_size, bool)
            or self.insert_batch_size <= 0
        ):
            raise ValueError("insert_batch_size must be a positive integer")
        self.root.mkdir(parents=True, exist_ok=True)

    def build(
        self,
        result: SnapshotMaterializationResult,
        *,
        requested_tables: Sequence[str] | None = None,
    ) -> RepositoryImportArtifact:
        if result.table_set is None:
            raise ValueError("snapshot materialization result must include table_set")
        if result.summary.snapshot_digest != result.snapshot.snapshot_digest:
            raise ValueError("snapshot digest mismatch between snapshot and summary")
        if result.table_set.snapshot_digest != result.summary.snapshot_digest:
            raise ValueError("snapshot digest mismatch between table_set and summary")

        selected_tables = select_physical_snapshot_tables(
            result,
            requested_tables=requested_tables,
        )
        build_dir = self._build_dir(result.summary.snapshot_digest, selected_tables)
        build_dir.mkdir(parents=True, exist_ok=True)

        if self.artifact_layout is RepositoryImportArtifactLayout.REPLAY_ONLY_MINIMAL:
            if any(value != REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY for value in self.export_formats):
                raise ValueError(
                    "REPLAY_ONLY_MINIMAL layout only supports SQL_REPLAY export format"
                )
            return self._build_minimal(
                result=result,
                selected_tables=selected_tables,
                build_dir=build_dir,
            )

        table_artifacts: list[RepositoryImportTableArtifact] = []
        table_payloads: list[RepositoryImportTableManifestPayload] = []
        table_replay_texts: list[str] = []
        shared_row_artifacts: dict[str, _SharedRowArtifactBundle] = {}
        shared_row_cache_hits = 0
        shared_row_cache_misses = 0
        rows_parquet_write_count = 0
        rows_parquet_reuse_count = 0

        selected_table_names = [table.descriptor.table_name for table in selected_tables]
        row_export_formats = _row_export_formats(self.export_formats)

        for table in selected_tables:
            (
                table_artifact,
                table_payload,
                table_replay_text,
                reused_rows,
                wrote_parquet,
            ) = self._build_table_artifact(
                build_dir=build_dir,
                table=table,
                snapshot_id=result.summary.snapshot_id,
                snapshot_digest=result.summary.snapshot_digest,
                row_export_formats=row_export_formats,
                shared_row_artifacts=shared_row_artifacts,
            )
            table_artifacts.append(table_artifact)
            table_payloads.append(table_payload)
            table_replay_texts.append(table_replay_text)
            if reused_rows:
                shared_row_cache_hits += 1
                if table_artifact.rows_parquet_file is not None:
                    rows_parquet_reuse_count += 1
            else:
                shared_row_cache_misses += 1
                if wrote_parquet:
                    rows_parquet_write_count += 1

        build_stats = RepositoryImportArtifactBuildStats(
            table_count=len(selected_tables),
            shared_row_cache_entries=len(shared_row_artifacts),
            shared_row_cache_hits=shared_row_cache_hits,
            shared_row_cache_misses=shared_row_cache_misses,
            reused_table_count=shared_row_cache_hits,
            rows_parquet_write_count=rows_parquet_write_count,
            rows_parquet_reuse_count=rows_parquet_reuse_count,
        )

        replay_sql_text = "\n\n".join(
            text.rstrip("\n") for text in table_replay_texts if text
        )
        if replay_sql_text:
            replay_sql_text += "\n"
        replay_sql_file = self._build_text_file(
            root_dir=build_dir,
            relative_path=REPOSITORY_IMPORT_REPLAY_SQL_FILE_NAME,
            role="replay_sql",
            text=replay_sql_text,
            export_format=REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY,
        )

        bundle_content = RepositoryImportBundleContent(
            snapshot_id=result.summary.snapshot_id,
            snapshot_digest=result.summary.snapshot_digest.to_payload(),
            raw_state_digest=result.summary.raw_state_digest.to_payload(),
            row_count_total=sum(table.descriptor.row_count for table in selected_tables),
            table_count=len(selected_tables),
            table_artifacts=tuple(table_payloads),
            replay_sql_file=_file_payload(replay_sql_file),
            requested_tables=tuple(selected_table_names),
            export_formats=row_export_formats + (REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY,),
            diagnostics=tuple(_diagnostic_payloads(result.diagnostics)),
        )
        bundle_content_file = self._build_json_file(
            root_dir=build_dir,
            relative_path=REPOSITORY_IMPORT_BUNDLE_CONTENT_FILE_NAME,
            role="bundle_content",
            payload=bundle_content,
            export_format="JSON",
        )

        bundle_manifest = self._build_manifest(
            artifact_kind=REPOSITORY_IMPORT_BUNDLE_MANIFEST_KIND,
            manifest_path=build_dir / REPOSITORY_IMPORT_MANIFEST_FILE_NAME,
            content_bytes=bundle_content_file.content_bytes,
            metadata={
                "content_schema_version": REPOSITORY_IMPORT_BUNDLE_CONTENT_SCHEMA_VERSION,
                "snapshot_id": result.summary.snapshot_id,
                "snapshot_digest": result.summary.snapshot_digest.to_payload(),
                "raw_state_digest": result.summary.raw_state_digest.to_payload(),
                "row_count_total": bundle_content.row_count_total,
                "table_count": bundle_content.table_count,
                "table_names": selected_table_names,
                "requested_tables": selected_table_names,
                "export_formats": list(bundle_content.export_formats),
                "content_path_relative_path": bundle_content_file.relative_path,
            },
            content_diagnostics=bundle_content.diagnostics,
        )

        return RepositoryImportArtifact(
            snapshot_id=result.summary.snapshot_id,
            snapshot_digest=result.summary.snapshot_digest,
            artifact_contract_version=REPOSITORY_IMPORT_CONTRACT_VERSION,
            manifest=bundle_manifest.manifest,
            manifest_ref=bundle_manifest.manifest_ref,
            manifest_path=bundle_manifest.manifest_path,
            content_path=bundle_content_file.path,
            bundle_dir=build_dir,
            replay_sql_file=replay_sql_file,
            table_artifacts=tuple(table_artifacts),
            reused=False,
            build_stats=build_stats,
            diagnostics=tuple(),
        )

    def _build_table_artifact(
        self,
        *,
        build_dir: Path,
        table: SnapshotTable,
        snapshot_id: str,
        snapshot_digest: DigestRef,
        row_export_formats: tuple[str, ...],
        shared_row_artifacts: dict[str, "_SharedRowArtifactBundle"],
        ) -> tuple[
        RepositoryImportTableArtifact,
        RepositoryImportTableManifestPayload,
        str,
        bool,
        bool,
    ]:
        descriptor = table.descriptor
        table_dir_name = _safe_path_component(descriptor.table_name)
        table_dir = build_dir / REPOSITORY_IMPORT_TABLES_DIR_NAME / table_dir_name
        table_dir.mkdir(parents=True, exist_ok=True)

        ordered_columns = tuple(column.name for column in descriptor.columns)
        shared_row_key = _shared_row_artifact_key(descriptor)
        shared_rows = shared_row_artifacts.get(shared_row_key.hex_digest)
        reused_rows = shared_rows is not None
        wrote_parquet = False
        build_csv = REPOSITORY_IMPORT_ROW_FORMAT_CSV in row_export_formats
        build_tsv = REPOSITORY_IMPORT_ROW_FORMAT_TSV in row_export_formats
        build_parquet = REPOSITORY_IMPORT_ROW_FORMAT_PARQUET in row_export_formats
        rows_csv_file: RepositoryImportFileArtifact | None = None
        rows_tsv_file: RepositoryImportFileArtifact | None = None
        rows_parquet_file: RepositoryImportFileArtifact | None = None
        if shared_rows is None:
            rows = tuple(table.reader.iter_rows())
            if build_csv:
                rows_csv_file = self._build_text_file(
                    root_dir=build_dir,
                    relative_path=f"{REPOSITORY_IMPORT_TABLES_DIR_NAME}/{table_dir_name}/{REPOSITORY_IMPORT_ROWS_CSV_FILE_NAME}",
                    role="rows",
                    text=_render_delimited_rows(rows, delimiter=","),
                    export_format=REPOSITORY_IMPORT_ROW_FORMAT_CSV,
                )
            if build_tsv:
                rows_tsv_file = self._build_text_file(
                    root_dir=build_dir,
                    relative_path=f"{REPOSITORY_IMPORT_TABLES_DIR_NAME}/{table_dir_name}/{REPOSITORY_IMPORT_ROWS_TSV_FILE_NAME}",
                    role="rows",
                    text=_render_delimited_rows(rows, delimiter="\t"),
                    export_format=REPOSITORY_IMPORT_ROW_FORMAT_TSV,
                )
            if build_parquet:
                row_dicts = tuple(
                    {
                        column_name: value
                        for column_name, value in zip(ordered_columns, row, strict=True)
                    }
                    for row in rows
                )
                rows_parquet_file = self._build_parquet_file(
                    root_dir=build_dir,
                    relative_path=f"{REPOSITORY_IMPORT_TABLES_DIR_NAME}/{table_dir_name}/{REPOSITORY_IMPORT_ROWS_PARQUET_FILE_NAME}",
                    rows=row_dicts,
                    columns=ordered_columns,
                )
                wrote_parquet = True
            shared_rows = _SharedRowArtifactBundle(
                rows=rows,
                rows_csv_file=rows_csv_file,
                rows_tsv_file=rows_tsv_file,
                rows_parquet_file=rows_parquet_file,
            )
            shared_row_artifacts[shared_row_key.hex_digest] = shared_rows
        else:
            rows = shared_rows.rows
            rows_csv_file = shared_rows.rows_csv_file
            rows_tsv_file = shared_rows.rows_tsv_file
            rows_parquet_file = shared_rows.rows_parquet_file
        table_replay_text = _render_table_replay_sql(
            table_name=descriptor.table_name,
            raw_create_sql=table.raw_create_sql,
            columns=ordered_columns,
            rows=rows,
            batch_size=self.insert_batch_size,
        )
        table_replay_file = self._build_text_file(
            root_dir=build_dir,
            relative_path=f"{REPOSITORY_IMPORT_TABLES_DIR_NAME}/{table_dir_name}/{REPOSITORY_IMPORT_REPLAY_SQL_FILE_NAME}",
            role="replay_sql",
            text=table_replay_text,
            export_format=REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY,
        )

        schema_file_payload = _schema_file_payload(
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest.to_payload(),
            descriptor=descriptor,
            rows_csv_file=rows_csv_file,
            rows_tsv_file=rows_tsv_file,
            rows_parquet_file=rows_parquet_file,
            replay_sql_file=table_replay_file,
            export_formats=row_export_formats + (REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY,),
        )
        schema_file = self._build_json_file(
            root_dir=build_dir,
            relative_path=f"{REPOSITORY_IMPORT_TABLES_DIR_NAME}/{table_dir_name}/{REPOSITORY_IMPORT_SCHEMA_FILE_NAME}",
            role="schema",
            payload=schema_file_payload,
            export_format="JSON",
        )

        table_payload = RepositoryImportTableManifestPayload(
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest.to_payload(),
            table_name=descriptor.table_name,
            display_table_name=descriptor.display_table_name or descriptor.table_name,
            row_count=descriptor.row_count,
            column_count=len(ordered_columns),
            columns=tuple(_column_payload(column) for column in descriptor.columns),
            compare_key_columns=descriptor.compare_key_columns,
            source_ddl_digest=(
                None
                if descriptor.source_ddl_digest is None
                else descriptor.source_ddl_digest.to_payload()
            ),
            canonical_artifact_ref=descriptor.canonical_artifact_ref,
            previous_canonical_artifact_ref=descriptor.previous_canonical_artifact_ref,
            compare_schema_digest=descriptor.compare_schema_digest.to_payload(),
            raw_content_digest=descriptor.raw_content_digest.to_payload(),
            schema_file=_file_payload(schema_file),
            rows_csv_file=None if rows_csv_file is None else _file_payload(rows_csv_file),
            rows_tsv_file=None if rows_tsv_file is None else _file_payload(rows_tsv_file),
            replay_sql_file=_file_payload(table_replay_file),
            rows_parquet_file=(
                None if rows_parquet_file is None else _file_payload(rows_parquet_file)
            ),
            table_ruleset_version=descriptor.table_ruleset_version,
            scalar_encoding_version=descriptor.scalar_encoding_version,
            row_materialization_profile=descriptor.row_materialization_profile,
            export_formats=row_export_formats + (REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY,),
            diagnostics=tuple(_diagnostic_payloads(descriptor.diagnostics)),
        )
        table_content_file = self._build_json_file(
            root_dir=build_dir,
            relative_path=f"{REPOSITORY_IMPORT_TABLES_DIR_NAME}/{table_dir_name}/{REPOSITORY_IMPORT_TABLE_CONTENT_FILE_NAME}",
            role="table_content",
            payload=table_payload,
            export_format="JSON",
        )

        table_manifest = self._build_manifest(
            artifact_kind=REPOSITORY_IMPORT_TABLE_MANIFEST_KIND,
            manifest_path=table_dir / REPOSITORY_IMPORT_MANIFEST_FILE_NAME,
            content_bytes=table_content_file.content_bytes,
            metadata={
                "content_schema_version": REPOSITORY_IMPORT_TABLE_CONTENT_SCHEMA_VERSION,
                "snapshot_id": snapshot_id,
                "snapshot_digest": snapshot_digest.to_payload(),
                "table_name": descriptor.table_name,
                "display_table_name": descriptor.display_table_name or descriptor.table_name,
                "row_count": descriptor.row_count,
                "column_count": len(ordered_columns),
                "compare_key_columns": list(descriptor.compare_key_columns),
                "source_ddl_digest": (
                    None
                    if descriptor.source_ddl_digest is None
                    else descriptor.source_ddl_digest.to_payload()
                ),
                "canonical_artifact_ref": descriptor.canonical_artifact_ref,
                "previous_canonical_artifact_ref": descriptor.previous_canonical_artifact_ref,
                "compare_schema_digest": descriptor.compare_schema_digest.to_payload(),
                "raw_content_digest": descriptor.raw_content_digest.to_payload(),
                "schema_file_relative_path": schema_file.relative_path,
                "rows_csv_relative_path": (
                    None if rows_csv_file is None else rows_csv_file.relative_path
                ),
                "rows_tsv_relative_path": (
                    None if rows_tsv_file is None else rows_tsv_file.relative_path
                ),
                "rows_parquet_relative_path": (
                    None if rows_parquet_file is None else rows_parquet_file.relative_path
                ),
                "replay_sql_relative_path": table_replay_file.relative_path,
                "export_formats": list(table_payload.export_formats),
                "content_path_relative_path": table_content_file.relative_path,
            },
            content_diagnostics=table_payload.diagnostics,
        )

        table_artifact = RepositoryImportTableArtifact(
            table_name=descriptor.table_name,
            display_table_name=descriptor.display_table_name or descriptor.table_name,
            artifact_contract_version=REPOSITORY_IMPORT_CONTRACT_VERSION,
            manifest=table_manifest.manifest,
            manifest_ref=table_manifest.manifest_ref,
            manifest_path=table_manifest.manifest_path,
            content_path=table_content_file.path,
            table_dir=table_dir,
            schema_file=schema_file,
            rows_csv_file=rows_csv_file,
            rows_tsv_file=rows_tsv_file,
            replay_sql_file=table_replay_file,
            rows_parquet_file=rows_parquet_file,
            reused=reused_rows,
            diagnostics=tuple(),
        )
        return table_artifact, table_payload, table_replay_text, reused_rows, wrote_parquet

    def _build_minimal(
        self,
        *,
        result: SnapshotMaterializationResult,
        selected_tables: Sequence[SnapshotTable],
        build_dir: Path,
    ) -> RepositoryImportArtifact:
        table_artifacts: list[RepositoryImportTableArtifact] = []
        table_payloads: list[dict[str, object]] = []
        table_replay_texts: list[str] = []
        shared_row_artifacts: dict[str, _SharedRowArtifactBundle] = {}
        shared_row_cache_hits = 0
        shared_row_cache_misses = 0

        selected_table_names = [table.descriptor.table_name for table in selected_tables]

        for table in selected_tables:
            table_artifact, table_payload, table_replay_text, reused_rows = self._build_minimal_table_artifact(
                build_dir=build_dir,
                table=table,
                snapshot_id=result.summary.snapshot_id,
                snapshot_digest=result.summary.snapshot_digest,
                shared_row_artifacts=shared_row_artifacts,
            )
            table_artifacts.append(table_artifact)
            table_payloads.append(table_payload)
            table_replay_texts.append(table_replay_text)
            if reused_rows:
                shared_row_cache_hits += 1
            else:
                shared_row_cache_misses += 1

        build_stats = RepositoryImportArtifactBuildStats(
            table_count=len(selected_tables),
            shared_row_cache_entries=len(shared_row_artifacts),
            shared_row_cache_hits=shared_row_cache_hits,
            shared_row_cache_misses=shared_row_cache_misses,
            reused_table_count=shared_row_cache_hits,
            rows_parquet_write_count=0,
            rows_parquet_reuse_count=0,
        )

        replay_sql_text = "\n\n".join(text.rstrip("\n") for text in table_replay_texts if text)
        hidden_summary_replay_sql = build_hidden_summary_replay_sql(result.summary)
        if replay_sql_text:
            replay_sql_text += "\n\n"
        replay_sql_text += hidden_summary_replay_sql.rstrip("\n")
        if replay_sql_text:
            replay_sql_text += "\n"
        replay_sql_file = self._build_text_file(
            root_dir=build_dir,
            relative_path=REPOSITORY_IMPORT_REPLAY_SQL_FILE_NAME,
            role="replay_sql",
            text=replay_sql_text,
            export_format=REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY,
        )

        bundle_content_relative_path = REPOSITORY_IMPORT_BUNDLE_CONTENT_FILE_NAME
        bundle_content_payload = {
            "schema_version": REPOSITORY_IMPORT_BUNDLE_CONTENT_SCHEMA_VERSION,
            "artifact_contract_version": REPOSITORY_IMPORT_CONTRACT_VERSION,
            "artifact_layout": self.artifact_layout.value,
            "snapshot_id": result.summary.snapshot_id,
            "snapshot_digest": result.summary.snapshot_digest.to_payload(),
            "raw_state_digest": result.summary.raw_state_digest.to_payload(),
            "row_count_total": sum(table.descriptor.row_count for table in selected_tables),
            "table_count": len(selected_tables),
            "table_artifacts": tuple(table_payloads),
            "replay_sql_relative_path": replay_sql_file.relative_path,
            "content_path_relative_path": bundle_content_relative_path,
            "table_names": selected_table_names,
            "requested_tables": tuple(selected_table_names),
            "export_formats": (REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY,),
            "diagnostics": tuple(_diagnostic_payloads(result.diagnostics)),
        }
        bundle_content_file = self._build_json_file(
            root_dir=build_dir,
            relative_path=REPOSITORY_IMPORT_BUNDLE_CONTENT_FILE_NAME,
            role="bundle_content",
            payload=bundle_content_payload,
            export_format="JSON",
        )

        bundle_manifest = self._build_manifest(
            artifact_kind=REPOSITORY_IMPORT_BUNDLE_MANIFEST_KIND,
            manifest_path=bundle_content_file.path,
            content_bytes=bundle_content_file.content_bytes,
            metadata=bundle_content_payload,
            content_diagnostics=tuple(_diagnostic_payloads(result.diagnostics)),
            write_file=False,
        )

        return RepositoryImportArtifact(
            snapshot_id=result.summary.snapshot_id,
            snapshot_digest=result.summary.snapshot_digest,
            artifact_contract_version=REPOSITORY_IMPORT_CONTRACT_VERSION,
            manifest=bundle_manifest.manifest,
            manifest_ref=bundle_manifest.manifest_ref,
            manifest_path=bundle_content_file.path,
            content_path=bundle_content_file.path,
            bundle_dir=build_dir,
            replay_sql_file=replay_sql_file,
            table_artifacts=tuple(table_artifacts),
            reused=False,
            build_stats=build_stats,
            diagnostics=tuple(),
        )

    def _build_minimal_table_artifact(
        self,
        *,
        build_dir: Path,
        table: SnapshotTable,
        snapshot_id: str,
        snapshot_digest: DigestRef,
        shared_row_artifacts: dict[str, "_SharedRowArtifactBundle"],
    ) -> tuple[
        RepositoryImportTableArtifact,
        dict[str, object],
        str,
        bool,
    ]:
        descriptor = table.descriptor
        table_dir_name = _safe_path_component(descriptor.table_name)
        table_dir = build_dir / REPOSITORY_IMPORT_TABLES_DIR_NAME / table_dir_name
        table_dir.mkdir(parents=True, exist_ok=True)

        shared_row_key = _shared_row_artifact_key(descriptor)
        shared_rows = shared_row_artifacts.get(shared_row_key.hex_digest)
        reused_rows = shared_rows is not None
        if shared_rows is None:
            rows = tuple(table.reader.iter_rows())
            shared_rows = _SharedRowArtifactBundle(rows=rows)
            shared_row_artifacts[shared_row_key.hex_digest] = shared_rows
        else:
            rows = shared_rows.rows

        table_replay_text = _render_table_replay_sql(
            table_name=descriptor.table_name,
            raw_create_sql=table.raw_create_sql,
            columns=tuple(column.name for column in descriptor.columns),
            rows=rows,
            batch_size=self.insert_batch_size,
        )

        table_content_relative_path = (
            f"{REPOSITORY_IMPORT_TABLES_DIR_NAME}/{table_dir_name}/{REPOSITORY_IMPORT_TABLE_CONTENT_FILE_NAME}"
        )
        table_payload = {
            "schema_version": REPOSITORY_IMPORT_TABLE_CONTENT_SCHEMA_VERSION,
            "artifact_contract_version": REPOSITORY_IMPORT_CONTRACT_VERSION,
            "artifact_layout": self.artifact_layout.value,
            "snapshot_id": snapshot_id,
            "snapshot_digest": snapshot_digest.to_payload(),
            "table_name": descriptor.table_name,
            "display_table_name": descriptor.display_table_name or descriptor.table_name,
            "row_count": descriptor.row_count,
            "column_count": len(descriptor.columns),
            "columns": tuple(_column_payload(column) for column in descriptor.columns),
            "compare_key_columns": tuple(descriptor.compare_key_columns),
            "source_ddl_digest": (
                None
                if descriptor.source_ddl_digest is None
                else descriptor.source_ddl_digest.to_payload()
            ),
            "canonical_artifact_ref": descriptor.canonical_artifact_ref,
            "previous_canonical_artifact_ref": descriptor.previous_canonical_artifact_ref,
            "compare_schema_digest": descriptor.compare_schema_digest.to_payload(),
            "raw_content_digest": descriptor.raw_content_digest.to_payload(),
            "table_ruleset_version": descriptor.table_ruleset_version,
            "scalar_encoding_version": descriptor.scalar_encoding_version,
            "row_materialization_profile": descriptor.row_materialization_profile,
            "export_formats": [REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY],
            "content_path_relative_path": table_content_relative_path,
            "diagnostics": tuple(_diagnostic_payloads(descriptor.diagnostics)),
        }
        table_content_file = self._build_json_file(
            root_dir=build_dir,
            relative_path=table_content_relative_path,
            role="table_content",
            payload=table_payload,
            export_format="JSON",
        )

        table_manifest = self._build_manifest(
            artifact_kind=REPOSITORY_IMPORT_TABLE_MANIFEST_KIND,
            manifest_path=table_content_file.path,
            content_bytes=table_content_file.content_bytes,
            metadata=table_payload,
            content_diagnostics=tuple(_diagnostic_payloads(descriptor.diagnostics)),
            write_file=False,
        )

        table_artifact = RepositoryImportTableArtifact(
            table_name=descriptor.table_name,
            display_table_name=descriptor.display_table_name or descriptor.table_name,
            artifact_contract_version=REPOSITORY_IMPORT_CONTRACT_VERSION,
            manifest=table_manifest.manifest,
            manifest_ref=table_manifest.manifest_ref,
            manifest_path=table_content_file.path,
            content_path=table_content_file.path,
            table_dir=table_dir,
            schema_file=table_content_file,
            rows_csv_file=None,
            rows_tsv_file=None,
            replay_sql_file=None,
            rows_parquet_file=None,
            reused=reused_rows,
            diagnostics=tuple(),
        )
        return table_artifact, table_payload, table_replay_text, reused_rows

    def _build_manifest(
        self,
        *,
        artifact_kind: str,
        manifest_path: Path,
        content_bytes: bytes,
        metadata: dict[str, object],
        content_diagnostics: tuple[Mapping[str, object], ...],
        write_file: bool = True,
    ) -> _WrittenArtifactManifest:
        content_digest = DigestRef.from_bytes(content_bytes)
        manifest = ArtifactManifest(
            artifact_kind=artifact_kind,
            artifact_contract_version=REPOSITORY_IMPORT_CONTRACT_VERSION,
            content_digest=content_digest,
            content_size_bytes=len(content_bytes),
            metadata=metadata,
            diagnostics=tuple(
                DiagnosticRecord.from_payload(diagnostic)
                if not isinstance(diagnostic, DiagnosticRecord)
                else diagnostic
                for diagnostic in content_diagnostics
            ),
            created_at=None,
        )
        manifest_bytes = canonical_json_bytes(manifest.to_payload())
        manifest_digest = DigestRef.from_bytes(manifest_bytes)
        manifest_ref = manifest.to_ref(manifest_digest)
        if write_file:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            _write_bytes(manifest_path, manifest_bytes)
        return _WrittenArtifactManifest(
            manifest=manifest,
            manifest_ref=manifest_ref,
            manifest_path=manifest_path,
        )

    def _build_text_file(
        self,
        *,
        root_dir: Path,
        relative_path: str,
        role: str,
        text: str,
        export_format: str,
    ) -> RepositoryImportFileArtifact:
        path = root_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        content_bytes = text.encode("utf-8")
        _write_bytes(path, content_bytes)
        return RepositoryImportFileArtifact(
            role=role,
            relative_path=relative_path,
            path=path,
            content_digest=DigestRef.from_bytes(content_bytes),
            content_size_bytes=len(content_bytes),
            export_format=export_format,
            binary=False,
        )

    def _build_json_file(
        self,
        *,
        root_dir: Path,
        relative_path: str,
        role: str,
        payload: object,
        export_format: str = "JSON",
    ) -> _JsonArtifactFile:
        path = root_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        content_bytes = canonical_json_bytes(payload)
        _write_bytes(path, content_bytes)
        return _JsonArtifactFile(
            role=role,
            relative_path=relative_path,
            path=path,
            content_bytes=content_bytes,
            content_digest=DigestRef.from_bytes(content_bytes),
            content_size_bytes=len(content_bytes),
            export_format=export_format,
            binary=False,
        )

    def _build_parquet_file(
        self,
        *,
        root_dir: Path,
        relative_path: str,
        rows: tuple[dict[str, object], ...],
        columns: tuple[str, ...],
    ) -> RepositoryImportFileArtifact:
        path = root_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if rows:
            frame = pl.from_dicts(rows, infer_schema_length=None, strict=False).select(columns)
        else:
            frame = pl.DataFrame(schema={column: pl.Null for column in columns})
        if self.parquet_compression is None:
            frame.write_parquet(path)
        else:
            frame.write_parquet(path, compression=self.parquet_compression)
        content_bytes = path.read_bytes()
        return RepositoryImportFileArtifact(
            role="rows",
            relative_path=relative_path,
            path=path,
            content_digest=DigestRef.from_bytes(content_bytes),
            content_size_bytes=len(content_bytes),
            export_format=REPOSITORY_IMPORT_ROW_FORMAT_PARQUET,
            binary=True,
        )

    def _build_dir(
        self,
        snapshot_digest: DigestRef,
        tables: Sequence[SnapshotTable],
    ) -> Path:
        fingerprint = DigestRef.from_payload(
            {
                "snapshot_digest": snapshot_digest.to_payload(),
                "table_names": [table.descriptor.table_name for table in tables],
                "export_formats": list(self.export_formats),
                "artifact_layout": self.artifact_layout.value,
                "insert_batch_size": self.insert_batch_size,
                "parquet_compression": self.parquet_compression,
            }
        )
        return self.root / snapshot_digest.hex_digest / fingerprint.hex_digest


@dataclass(frozen=True, slots=True)
class _WrittenArtifactManifest:
    manifest: ArtifactManifest
    manifest_ref: ArtifactRef
    manifest_path: Path


@dataclass(frozen=True, slots=True)
class _SharedRowArtifactBundle:
    rows: tuple[tuple[object, ...], ...]
    rows_csv_file: RepositoryImportFileArtifact | None = None
    rows_tsv_file: RepositoryImportFileArtifact | None = None
    rows_parquet_file: RepositoryImportFileArtifact | None = None


@dataclass(frozen=True, slots=True)
class _JsonArtifactFile:
    role: str
    relative_path: str
    path: Path
    content_bytes: bytes
    content_digest: DigestRef
    content_size_bytes: int
    export_format: str | None
    binary: bool


def _normalize_export_formats(values: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip().upper()
        if not text:
            raise ValueError("export_formats must not contain empty values")
        if text in seen:
            continue
        if text not in {
            REPOSITORY_IMPORT_ROW_FORMAT_CSV,
            REPOSITORY_IMPORT_ROW_FORMAT_TSV,
            REPOSITORY_IMPORT_ROW_FORMAT_PARQUET,
            REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY,
        }:
            raise ValueError(f"unsupported export format: {text}")
        seen.add(text)
        normalized.append(text)
    if not normalized:
        raise ValueError("export_formats must not be empty")
    return tuple(normalized)


def _normalize_artifact_layout(value: RepositoryImportArtifactLayout | str) -> RepositoryImportArtifactLayout:
    if isinstance(value, RepositoryImportArtifactLayout):
        return value
    return RepositoryImportArtifactLayout(str(value))


def _row_export_formats(export_formats: tuple[str, ...]) -> tuple[str, ...]:
    row_formats = tuple(
        value for value in export_formats if value != REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY
    )
    if REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY not in export_formats:
        return row_formats
    return row_formats


def _select_tables(
    tables: Sequence[SnapshotTable],
    requested_tables: Sequence[str] | None,
) -> tuple[SnapshotTable, ...]:
    table_map = {table.descriptor.table_name: table for table in tables}
    if not requested_tables:
        return tuple(table_map[name] for name in sorted(table_map))
    selected_names: list[str] = []
    seen: set[str] = set()
    for value in requested_tables:
        name = canonical_identifier(value)
        if not name or name in seen:
            continue
        if name not in table_map:
            raise ValueError(f"requested table not found: {value}")
        seen.add(name)
        selected_names.append(name)
    return tuple(table_map[name] for name in sorted(selected_names))


def _shared_row_artifact_key(
    descriptor: SnapshotTableDescriptor,
) -> DigestRef:
    row_layout_digest = descriptor.row_layout_digest
    if row_layout_digest is None:
        raise ValueError("table descriptor must expose a canonical row layout digest")
    return row_layout_digest


def _schema_file_payload(
    *,
    snapshot_id: str,
    snapshot_digest: str,
    descriptor,
    rows_csv_file: RepositoryImportFileArtifact | None,
    rows_tsv_file: RepositoryImportFileArtifact | None,
    rows_parquet_file: RepositoryImportFileArtifact | None,
    replay_sql_file: RepositoryImportFileArtifact,
    export_formats: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema_version": REPOSITORY_IMPORT_SCHEMA_FILE_SCHEMA_VERSION,
        "artifact_contract_version": REPOSITORY_IMPORT_CONTRACT_VERSION,
        "snapshot_id": snapshot_id,
        "snapshot_digest": snapshot_digest,
        "table_name": descriptor.table_name,
        "display_table_name": descriptor.display_table_name or descriptor.table_name,
        "row_count": descriptor.row_count,
        "column_count": len(descriptor.columns),
        "columns": tuple(_column_payload(column) for column in descriptor.columns),
        "compare_key_columns": tuple(descriptor.compare_key_columns),
        "source_ddl_digest": (
            None if descriptor.source_ddl_digest is None else descriptor.source_ddl_digest.to_payload()
        ),
        "canonical_artifact_ref": descriptor.canonical_artifact_ref,
        "previous_canonical_artifact_ref": descriptor.previous_canonical_artifact_ref,
        "compare_schema_digest": descriptor.compare_schema_digest.to_payload(),
        "raw_content_digest": descriptor.raw_content_digest.to_payload(),
        "table_ruleset_version": descriptor.table_ruleset_version,
        "scalar_encoding_version": descriptor.scalar_encoding_version,
        "row_materialization_profile": descriptor.row_materialization_profile,
        "rows_csv_file": None if rows_csv_file is None else _file_payload(rows_csv_file),
        "rows_tsv_file": None if rows_tsv_file is None else _file_payload(rows_tsv_file),
        "rows_parquet_file": (
            None if rows_parquet_file is None else _file_payload(rows_parquet_file)
        ),
        "replay_sql_file": _file_payload(replay_sql_file),
        "export_formats": list(export_formats),
    }


def _render_delimited_rows(
    rows: Sequence[tuple[object, ...]],
    *,
    delimiter: str,
) -> str:
    lines = [_render_delimited_row(row, delimiter=delimiter) for row in rows]
    return "" if not lines else "\n".join(lines) + "\n"


def _render_delimited_row(
    row: Sequence[object],
    *,
    delimiter: str,
) -> str:
    return delimiter.join(_render_delimited_cell(value, delimiter=delimiter) for value in row)


def _render_delimited_cell(value: object, *, delimiter: str) -> str:
    if value is None:
        return REPOSITORY_IMPORT_NULL_TOKEN
    if isinstance(value, bool):
        text = "1" if value else "0"
    elif isinstance(value, int):
        text = str(value)
    elif isinstance(value, Decimal):
        text = format(value, "f")
    elif isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("non-finite float values are not supported")
        text = repr(value)
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)
    if _needs_delimited_quotes(text, delimiter=delimiter):
        return '"' + text.replace('"', '""') + '"'
    return text


def _needs_delimited_quotes(text: str, *, delimiter: str) -> bool:
    return (
        text == REPOSITORY_IMPORT_NULL_TOKEN
        or text == ""
        or delimiter in text
        or "\n" in text
        or "\r" in text
        or '"' in text
        or text[:1].isspace()
        or text[-1:].isspace()
    )


def _render_table_replay_sql(
    *,
    table_name: str,
    raw_create_sql: str,
    columns: tuple[str, ...],
    rows: Sequence[tuple[object, ...]],
    batch_size: int,
) -> str:
    parts = [
        f"DROP TABLE IF EXISTS {_sql_quote_identifier(table_name)};",
        f"{raw_create_sql};",
    ]
    for batch in _batched(rows, batch_size):
        parts.append(
            _render_insert_statement(
                table_name=table_name,
                columns=columns,
                rows=batch,
            )
        )
    if len(parts) == 2:
        return "\n".join(parts) + "\n"
    return "\n".join(parts) + "\n"


def _render_insert_statement(
    *,
    table_name: str,
    columns: tuple[str, ...],
    rows: Sequence[tuple[object, ...]],
) -> str:
    column_list = ", ".join(_sql_quote_identifier(column) for column in columns)
    rendered_rows = ",\n  ".join(
        "(" + ", ".join(_render_sql_literal(value) for value in row) + ")"
        for row in rows
    )
    return (
        f"INSERT INTO {_sql_quote_identifier(table_name)} ({column_list}) VALUES\n"
        f"  {rendered_rows};"
    )


def _render_sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("non-finite float values are not supported")
        return repr(value)
    if isinstance(value, str):
        return "'" + _escape_sql_string(value) + "'"
    return "'" + _escape_sql_string(str(value)) + "'"


def _escape_sql_string(value: str) -> str:
    pieces: list[str] = []
    for ch in value:
        if ch == "\\":
            pieces.append("\\\\")
        elif ch == "'":
            pieces.append("''")
        elif ch == "\0":
            pieces.append("\\0")
        elif ch == "\b":
            pieces.append("\\b")
        elif ch == "\n":
            pieces.append("\\n")
        elif ch == "\r":
            pieces.append("\\r")
        elif ch == "\t":
            pieces.append("\\t")
        elif ch == "\x1a":
            pieces.append("\\Z")
        else:
            pieces.append(ch)
    return "".join(pieces)


def _sql_quote_identifier(identifier: str) -> str:
    parts = identifier.split(".")
    return ".".join("`" + part.replace("`", "``") + "`" for part in parts)


def _batched(
    values: Sequence[tuple[object, ...]],
    batch_size: int,
) -> tuple[tuple[object, ...], ...]:
    batches: list[tuple[object, ...]] = []
    current: list[tuple[object, ...]] = []
    for value in values:
        current.append(value)
        if len(current) >= batch_size:
            batches.append(tuple(current))
            current.clear()
    if current:
        batches.append(tuple(current))
    return tuple(batches)


def _column_payload(column) -> dict[str, object]:
    return {
        "name": column.name,
        "display_name": column.display_name,
        "scalar_type": column.scalar_type,
        "nullable": column.nullable,
    }


def _file_payload(file_artifact: RepositoryImportFileArtifact) -> dict[str, object]:
    return {
        "role": file_artifact.role,
        "relative_path": file_artifact.relative_path,
        "content_digest": file_artifact.content_digest.to_payload(),
        "content_size_bytes": file_artifact.content_size_bytes,
        "export_format": file_artifact.export_format,
        "binary": file_artifact.binary,
    }


def _diagnostic_payloads(
    diagnostics: Sequence[DiagnosticRecord],
) -> tuple[dict[str, object], ...]:
    return tuple(diagnostic.to_payload() for diagnostic in diagnostics)


def _safe_path_component(value: str) -> str:
    text = canonical_identifier(value)
    text = re.sub(r"[\\/]+", "_", text)
    if text in {".", ".."}:
        return text.replace(".", "_")
    return text


def _normalize_export_formats(values: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip().upper()
        if not text:
            raise ValueError("export_formats must not contain empty values")
        if text in seen:
            continue
        if text not in {
            REPOSITORY_IMPORT_ROW_FORMAT_CSV,
            REPOSITORY_IMPORT_ROW_FORMAT_TSV,
            REPOSITORY_IMPORT_ROW_FORMAT_PARQUET,
            REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY,
        }:
            raise ValueError(f"unsupported export format: {text}")
        seen.add(text)
        normalized.append(text)
    if not normalized:
        raise ValueError("export_formats must not be empty")
    return tuple(normalized)


def _write_bytes(path: Path, data: bytes) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_bytes(data)
    tmp_path.replace(path)
