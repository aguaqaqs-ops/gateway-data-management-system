from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import multiprocessing
import os
from pathlib import Path
from time import perf_counter

from ...artifacts.manifest import ArtifactRef
from ...core.digests import DigestRef
from ...core.diagnostics import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from ...core.row_digests import stable_snapshot_rows_digest
from ...core.scalar_encoding import normalize_snapshot_rows
from ...formal_upload_benchmark import (
    benchmark_elapsed_ms,
    formal_upload_benchmark_enabled,
    log_formal_upload_benchmark_event,
)
from ..comparison.digest import (
    build_projection_logical_digest_parts,
    build_projection_schema_digest,
)
from ..table_rules import TableRuleRegistry, TableStaticRole, default_table_rule_registry
from .models import (
    ROW_MATERIALIZATION_PROFILE,
    PROJECTION_DIGEST_POLICY_DISABLED,
    PROJECTION_DIGEST_POLICY_FINAL_ONLY,
    PROJECTION_DIGEST_POLICY_PROVISIONAL_AND_FINAL,
    SNAPSHOT_DIGEST_CONTRACT_VERSION,
    SCALAR_ENCODING_VERSION,
    SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
    SNAPSHOT_SUMMARY_SCHEMA_VERSION,
    SQL_PARSER_VERSION,
    SnapshotMaterializationStage,
    SnapshotProjectionDigest,
    SnapshotProjectionDigestAuthority,
    TABLE_RULESET_VERSION,
    Snapshot,
    SnapshotMaterializationInput,
    SnapshotMaterializationResult,
    SnapshotSourceContext,
    SnapshotSummary,
    SnapshotTable,
    SnapshotTableDescriptor,
    SnapshotTableSet,
    assign_canonical_artifact_refs,
)
from .rules import TableHandlingDecision, build_table_handling_decision
from .readers import InMemorySnapshotTableReader, LazySnapshotTableReader
from .sql_source import (
    DEFAULT_SQL_STREAM_CHUNK_SIZE_BYTES,
    SqlDumpSource,
    resolve_sql_dump_source,
)
from .sql_parser import (
    ParsedSqlDump,
    ParsedTableBundle,
    ParsedTableDefinition,
    parse_mysql_dump,
    parse_mysql_dump_chunks,
)
from .source_package import (
    SourceDocumentRef,
    SourcePackage,
    get_source_package,
    resolve_required_sql_document,
)
from .versions import SQL_DUMP_SOURCE_CONTRACT_VERSION

COMPARISON_PROJECTION_CONTRACT_VERSION = "backend-vnext/comparison-projection/v1"

@dataclass(frozen=True, slots=True)
class SqlDumpParseContext:
    parser_version: str = SQL_PARSER_VERSION
    parser_input_contract_version: str = SQL_DUMP_SOURCE_CONTRACT_VERSION
    scalar_encoding_version: str = SCALAR_ENCODING_VERSION
    requested_tables: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for field_name in (
            "parser_version",
            "parser_input_contract_version",
            "scalar_encoding_version",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        normalized_requested_tables: list[str] = []
        seen: set[str] = set()
        for table_name in self.requested_tables:
            canonical_name = canonical_identifier(table_name)
            if not canonical_name or canonical_name in seen:
                continue
            seen.add(canonical_name)
            normalized_requested_tables.append(canonical_name)
        object.__setattr__(self, "requested_tables", tuple(normalized_requested_tables))


@dataclass(frozen=True, slots=True)
class SqlDumpParseSummary:
    table_count: int
    row_count_total: int
    ignored_statement_count: int
    dropped_table_count: int
    unsupported_statement_count: int
    parse_skipped_insert_table_count: int = 0
    parse_skipped_insert_statement_count: int = 0
    parse_skipped_insert_row_count: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "table_count",
            "row_count_total",
            "ignored_statement_count",
            "dropped_table_count",
            "unsupported_statement_count",
            "parse_skipped_insert_table_count",
            "parse_skipped_insert_statement_count",
            "parse_skipped_insert_row_count",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class SqlDumpParseResult:
    sql_dump_source: SqlDumpSource
    parsed_dump: ParsedSqlDump
    parse_summary: SqlDumpParseSummary
    parser_diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.sql_dump_source, SqlDumpSource):
            raise TypeError("sql_dump_source must be a SqlDumpSource")
        if not isinstance(self.parsed_dump, ParsedSqlDump):
            raise TypeError("parsed_dump must be a ParsedSqlDump")
        if not isinstance(self.parse_summary, SqlDumpParseSummary):
            raise TypeError("parse_summary must be a SqlDumpParseSummary")
        object.__setattr__(self, "parser_diagnostics", tuple(self.parser_diagnostics))
        for diagnostic in self.parser_diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("parser_diagnostics must contain DiagnosticRecord values")

    @property
    def tables(self) -> dict[str, ParsedTableBundle]:
        return self.parsed_dump.tables

    @property
    def table_count(self) -> int:
        return self.parse_summary.table_count

    @property
    def row_count_total(self) -> int:
        return self.parse_summary.row_count_total


@dataclass(frozen=True, slots=True)
class _TableMaterializationTiming:
    descriptor_build_duration_ms: int = 0
    reader_build_duration_ms: int = 0
    row_finalize_duration_ms: int | None = None
    row_digest_duration_ms: int | None = None
    descriptor_finalize_duration_ms: int | None = None
    projection_digest_duration_ms: int = 0
    projection_digest_count: int = 0
    projection_digest_row_count: int = 0
    projection_digest_enabled: bool = False
    projection_digest_policy: str = PROJECTION_DIGEST_POLICY_DISABLED
    total_duration_ms: int = 0

    def to_payload(self) -> dict[str, object]:
        return {
            "descriptor_build_duration_ms": self.descriptor_build_duration_ms,
            "reader_build_duration_ms": self.reader_build_duration_ms,
            "row_finalize_duration_ms": self.row_finalize_duration_ms,
            "row_digest_duration_ms": self.row_digest_duration_ms,
            "descriptor_finalize_duration_ms": self.descriptor_finalize_duration_ms,
            "projection_digest_duration_ms": self.projection_digest_duration_ms,
            "projection_digest_count": self.projection_digest_count,
            "projection_digest_row_count": self.projection_digest_row_count,
            "projection_digest_enabled": self.projection_digest_enabled,
            "projection_digest_policy": self.projection_digest_policy,
            "total_duration_ms": self.total_duration_ms,
        }


@dataclass(frozen=True, slots=True)
class _TableMaterializationProfile:
    table_name: str
    parsed_row_count: int
    column_count: int
    insert_statement_count: int
    primary_key_column_count: int
    parse_skipped_insert_statement_count: int
    parse_skipped_row_count: int
    rule_decision_duration_ms: int | None
    static_role: str | None
    runtime_state: str | None
    compare_mode: str | None
    keep_in_raw_snapshot: bool | None
    enters_comparison: bool | None
    include_in_preview: bool | None
    include_in_diff_summary: bool | None
    export_base_table_artifact: bool | None
    export_diff_artifact: bool | None
    finalize_canonical_digests: bool
    materialized: bool = False
    skip_reason: str | None = None
    error_type: str | None = None
    timing: _TableMaterializationTiming | None = None
    total_duration_ms: int = 0

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "table_name": self.table_name,
            "parsed_row_count": self.parsed_row_count,
            "column_count": self.column_count,
            "insert_statement_count": self.insert_statement_count,
            "primary_key_column_count": self.primary_key_column_count,
            "parse_skipped_insert_statement_count": self.parse_skipped_insert_statement_count,
            "parse_skipped_row_count": self.parse_skipped_row_count,
            "parse_rows_skipped": self.parse_skipped_row_count > 0,
            "rule_decision_duration_ms": self.rule_decision_duration_ms,
            "static_role": self.static_role,
            "runtime_state": self.runtime_state,
            "compare_mode": self.compare_mode,
            "keep_in_raw_snapshot": self.keep_in_raw_snapshot,
            "enters_comparison": self.enters_comparison,
            "include_in_preview": self.include_in_preview,
            "include_in_diff_summary": self.include_in_diff_summary,
            "export_base_table_artifact": self.export_base_table_artifact,
            "export_diff_artifact": self.export_diff_artifact,
            "finalize_canonical_digests": self.finalize_canonical_digests,
            "materialized": self.materialized,
            "skip_reason": self.skip_reason,
            "error_type": self.error_type,
            "total_duration_ms": self.total_duration_ms,
        }
        if self.timing is not None:
            payload.update(self.timing.to_payload())
        return payload


@dataclass(frozen=True, slots=True)
class _TableMaterializationContext:
    table_ruleset_version: str
    scalar_encoding_version: str
    row_materialization_profile: str
    projection_digest_policy: str


@dataclass(frozen=True, slots=True)
class _TableMaterializationWorkItem:
    table_name: str
    bundle: ParsedTableBundle
    decision: TableHandlingDecision
    decision_duration_ms: int


@dataclass(frozen=True, slots=True)
class _TableMaterializationOutcome:
    table_name: str
    descriptor: SnapshotTableDescriptor | None
    table: SnapshotTable | None
    timing: _TableMaterializationTiming | None
    decision: TableHandlingDecision
    decision_duration_ms: int
    error_type: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _TableMaterializationBatchResult:
    outcomes: tuple[_TableMaterializationOutcome, ...]
    duration_ms: int


def _projection_digest_enabled_for_policy(
    *,
    projection_digest_policy: str,
    finalize_canonical_digests: bool,
) -> bool:
    if projection_digest_policy == PROJECTION_DIGEST_POLICY_DISABLED:
        return False
    if projection_digest_policy == PROJECTION_DIGEST_POLICY_FINAL_ONLY:
        return finalize_canonical_digests
    if projection_digest_policy == PROJECTION_DIGEST_POLICY_PROVISIONAL_AND_FINAL:
        return True
    return False


def parse_sql_dump_source(
    sql_dump_source: SqlDumpSource | SourceDocumentRef | SourcePackageStagingResult | SourcePackage | ArtifactRef | Path | str | bytes | bytearray | memoryview,
    parser_context: SqlDumpParseContext | SnapshotMaterializationInput | None = None,
) -> SqlDumpParseResult:
    context = _coerce_parse_context(parser_context)
    resolved_source = _coerce_sql_dump_source(
        sql_dump_source,
        parser_input_contract_version=context.parser_input_contract_version,
    )
    skip_hook = _parse_skip_hook(parser_context)
    if resolved_source.file_backed:
        parsed = parse_mysql_dump_chunks(
            resolved_source.iter_text_chunks(
                chunk_size_bytes=DEFAULT_SQL_STREAM_CHUNK_SIZE_BYTES,
            ),
            should_skip_insert_rows=skip_hook,
        )
    else:
        if resolved_source.source_text is None:
            raise ValueError("resolved SQL source has no source_text")
        parsed = parse_mysql_dump(
            resolved_source.source_text,
            should_skip_insert_rows=skip_hook,
        )
    table_count = len(parsed.tables)
    row_count_total = sum(bundle.row_count for bundle in parsed.tables.values())
    diagnostics: list[DiagnosticRecord] = []
    if parsed.unsupported_statements:
        diagnostics.append(
            DiagnosticRecord(
                code="snapshot.sql-parse.unsupported-statements",
                message="unsupported SQL statements were skipped during parsing",
                phase="parse",
                severity="WARNING",
                details={
                    "count": len(parsed.unsupported_statements),
                    "sample": list(parsed.unsupported_statements[:3]),
                },
            )
        )
    return SqlDumpParseResult(
        sql_dump_source=resolved_source,
        parsed_dump=parsed,
        parse_summary=SqlDumpParseSummary(
            table_count=table_count,
            row_count_total=row_count_total,
            ignored_statement_count=parsed.ignored_statement_count,
            dropped_table_count=parsed.dropped_table_count,
            unsupported_statement_count=len(parsed.unsupported_statements),
            parse_skipped_insert_table_count=parsed.parse_skipped_insert_table_count,
            parse_skipped_insert_statement_count=parsed.parse_skipped_insert_statement_count,
            parse_skipped_insert_row_count=parsed.parse_skipped_insert_row_count,
        ),
        parser_diagnostics=tuple(diagnostics),
    )


def _log_sql_source_open(
    resolved_source: SqlDumpSource,
    *,
    benchmark_run_id: str | None,
    requested_table_count: int,
) -> None:
    started_at = perf_counter()
    source_path = resolved_source.source_path
    if source_path is not None and not source_path.is_file():
        raise FileNotFoundError(str(source_path))
    log_formal_upload_benchmark_event(
        "snapshot_materialize.sql_source_open",
        benchmark_run_id=benchmark_run_id,
        requested_table_count=requested_table_count,
        streaming=resolved_source.file_backed,
        file_backed=resolved_source.source_path is not None,
        has_source_text=resolved_source.source_text is not None,
        source_size_bytes=resolved_source.source_size_bytes,
        chunk_size_bytes=DEFAULT_SQL_STREAM_CHUNK_SIZE_BYTES if resolved_source.file_backed else None,
        duration_ms=benchmark_elapsed_ms(started_at),
    )


def materialize_sql_dump_source(
    sql_dump_source: SqlDumpSource | SourceDocumentRef | SourcePackageStagingResult | SourcePackage | ArtifactRef | Path | str | bytes | bytearray | memoryview,
    materialization_context: SnapshotMaterializationInput | None = None,
    *,
    benchmark_run_id: str | None = None,
) -> SnapshotMaterializationResult:
    total_started_at = perf_counter()
    context_started_at = perf_counter()
    context = materialization_context or SnapshotMaterializationInput(
        sql_dump_source=resolve_sql_dump_source(sql_dump_source),
        source_kind="SQL_DUMP_SOURCE",
    )
    log_formal_upload_benchmark_event(
        "snapshot_materialize.context",
        benchmark_run_id=benchmark_run_id,
        requested_table_count=len(context.requested_tables),
        finalize_canonical_digests=True,
        projection_digest_policy=context.projection_digest_policy,
        duration_ms=benchmark_elapsed_ms(context_started_at),
    )
    resolve_started_at = perf_counter()
    resolved_source = _resolve_sql_dump_source_from_materialization_input(context)
    log_formal_upload_benchmark_event(
        "snapshot_materialize.resolve_sql_source",
        benchmark_run_id=benchmark_run_id,
        requested_table_count=len(context.requested_tables),
        source_size_bytes=resolved_source.source_size_bytes,
        duration_ms=benchmark_elapsed_ms(resolve_started_at),
    )
    _log_sql_source_open(
        resolved_source,
        benchmark_run_id=benchmark_run_id,
        requested_table_count=len(context.requested_tables),
    )
    parse_started_at = perf_counter()
    parse_result = parse_sql_dump_source(
        resolved_source,
        context,
    )
    log_formal_upload_benchmark_event(
        "snapshot_materialize.parse_sql",
        benchmark_run_id=benchmark_run_id,
        requested_table_count=len(context.requested_tables),
        table_count=parse_result.parse_summary.table_count,
        row_count_total=parse_result.parse_summary.row_count_total,
        ignored_statement_count=parse_result.parse_summary.ignored_statement_count,
        unsupported_statement_count=parse_result.parse_summary.unsupported_statement_count,
        parse_skipped_insert_table_count=parse_result.parse_summary.parse_skipped_insert_table_count,
        parse_skipped_insert_statement_count=parse_result.parse_summary.parse_skipped_insert_statement_count,
        parse_skipped_insert_row_count=parse_result.parse_summary.parse_skipped_insert_row_count,
        largest_parse_skipped_tables=_largest_parse_skipped_tables(parse_result.parsed_dump),
        streaming=resolved_source.file_backed,
        chunk_size_bytes=DEFAULT_SQL_STREAM_CHUNK_SIZE_BYTES if resolved_source.file_backed else None,
        source_size_bytes=resolved_source.source_size_bytes,
        **parse_result.parsed_dump.metrics.to_payload(),
        duration_ms=benchmark_elapsed_ms(parse_started_at),
    )
    result = _materialize_parsed_dump(
        materialization_input=context,
        sql_dump_source=resolved_source,
        parsed=parse_result.parsed_dump,
        parser_diagnostics=parse_result.parser_diagnostics,
        finalize_canonical_digests=True,
        benchmark_run_id=benchmark_run_id,
    )
    log_formal_upload_benchmark_event(
        "snapshot_materialize.total",
        benchmark_run_id=benchmark_run_id,
        requested_table_count=len(context.requested_tables),
        table_count=result.summary.table_count,
        row_count_total=result.summary.row_count_total,
        finalize_canonical_digests=True,
        projection_digest_policy=context.projection_digest_policy,
        duration_ms=benchmark_elapsed_ms(total_started_at),
    )
    return result


def materialize_sql_dump_source_preview(
    sql_dump_source: SqlDumpSource | SourceDocumentRef | SourcePackageStagingResult | SourcePackage | ArtifactRef | Path | str | bytes | bytearray | memoryview,
    materialization_context: SnapshotMaterializationInput | None = None,
    *,
    benchmark_run_id: str | None = None,
) -> SnapshotMaterializationResult:
    total_started_at = perf_counter()
    context_started_at = perf_counter()
    context = materialization_context or SnapshotMaterializationInput(
        sql_dump_source=resolve_sql_dump_source(sql_dump_source),
        source_kind="SQL_DUMP_SOURCE",
    )
    log_formal_upload_benchmark_event(
        "snapshot_materialize.context",
        benchmark_run_id=benchmark_run_id,
        requested_table_count=len(context.requested_tables),
        finalize_canonical_digests=False,
        projection_digest_policy=context.projection_digest_policy,
        duration_ms=benchmark_elapsed_ms(context_started_at),
    )
    resolve_started_at = perf_counter()
    resolved_source = _resolve_sql_dump_source_from_materialization_input(context)
    log_formal_upload_benchmark_event(
        "snapshot_materialize.resolve_sql_source",
        benchmark_run_id=benchmark_run_id,
        requested_table_count=len(context.requested_tables),
        source_size_bytes=resolved_source.source_size_bytes,
        duration_ms=benchmark_elapsed_ms(resolve_started_at),
    )
    _log_sql_source_open(
        resolved_source,
        benchmark_run_id=benchmark_run_id,
        requested_table_count=len(context.requested_tables),
    )
    parse_started_at = perf_counter()
    parse_result = parse_sql_dump_source(
        resolved_source,
        context,
    )
    log_formal_upload_benchmark_event(
        "snapshot_materialize.parse_sql",
        benchmark_run_id=benchmark_run_id,
        requested_table_count=len(context.requested_tables),
        table_count=parse_result.parse_summary.table_count,
        row_count_total=parse_result.parse_summary.row_count_total,
        ignored_statement_count=parse_result.parse_summary.ignored_statement_count,
        unsupported_statement_count=parse_result.parse_summary.unsupported_statement_count,
        finalize_canonical_digests=False,
        parse_skipped_insert_table_count=parse_result.parse_summary.parse_skipped_insert_table_count,
        parse_skipped_insert_statement_count=parse_result.parse_summary.parse_skipped_insert_statement_count,
        parse_skipped_insert_row_count=parse_result.parse_summary.parse_skipped_insert_row_count,
        largest_parse_skipped_tables=_largest_parse_skipped_tables(parse_result.parsed_dump),
        streaming=resolved_source.file_backed,
        chunk_size_bytes=DEFAULT_SQL_STREAM_CHUNK_SIZE_BYTES if resolved_source.file_backed else None,
        source_size_bytes=resolved_source.source_size_bytes,
        **parse_result.parsed_dump.metrics.to_payload(),
        duration_ms=benchmark_elapsed_ms(parse_started_at),
    )
    result = _materialize_parsed_dump(
        materialization_input=context,
        sql_dump_source=resolved_source,
        parsed=parse_result.parsed_dump,
        parser_diagnostics=parse_result.parser_diagnostics,
        finalize_canonical_digests=False,
        benchmark_run_id=benchmark_run_id,
    )
    log_formal_upload_benchmark_event(
        "snapshot_materialize.total",
        benchmark_run_id=benchmark_run_id,
        requested_table_count=len(context.requested_tables),
        table_count=result.summary.table_count,
        row_count_total=result.summary.row_count_total,
        finalize_canonical_digests=False,
        projection_digest_policy=context.projection_digest_policy,
        duration_ms=benchmark_elapsed_ms(total_started_at),
    )
    return result


def materialize_sql_snapshot(
    materialization_input: SnapshotMaterializationInput,
) -> SnapshotMaterializationResult:
    resolved_source = _resolve_sql_dump_source_from_materialization_input(materialization_input)
    return materialize_sql_dump_source(resolved_source, materialization_input)


def materialize_sql_snapshot_preview(
    materialization_input: SnapshotMaterializationInput,
) -> SnapshotMaterializationResult:
    resolved_source = _resolve_sql_dump_source_from_materialization_input(materialization_input)
    return materialize_sql_dump_source_preview(resolved_source, materialization_input)


def materialize_sql_source(
    *,
    source_sql: str,
    source_path: Path | None = None,
    source_kind: str = "SQL_DUMP_SOURCE",
    requested_tables: Sequence[str] = (),
    parser_version: str | None = None,
    table_ruleset_version: str | None = None,
    scalar_encoding_version: str | None = None,
    snapshot_materialization_contract_version: str | None = None,
    summary_contract_version: str | None = None,
    row_materialization_profile: str | None = None,
    materialization_policy: str = "READERS_REQUIRED",
    projection_digest_policy: str = PROJECTION_DIGEST_POLICY_DISABLED,
    table_rule_registry: TableRuleRegistry | None = None,
) -> SnapshotMaterializationResult:
    effective_table_rule_registry = table_rule_registry or default_table_rule_registry()
    return materialize_sql_snapshot(
        SnapshotMaterializationInput(
            source_path=source_path,
            source_sql=source_sql,
            source_kind=source_kind,
            digest_contract_version=SNAPSHOT_DIGEST_CONTRACT_VERSION,
            parser_version=parser_version or SQL_PARSER_VERSION,
            parser_input_contract_version=SQL_DUMP_SOURCE_CONTRACT_VERSION,
            table_ruleset_version=(
                table_ruleset_version or effective_table_rule_registry.table_ruleset_version
            ),
            scalar_encoding_version=scalar_encoding_version or SCALAR_ENCODING_VERSION,
            snapshot_materialization_contract_version=(
                snapshot_materialization_contract_version
                or SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION
            ),
            summary_contract_version=summary_contract_version
            or SNAPSHOT_SUMMARY_SCHEMA_VERSION,
            row_materialization_profile=row_materialization_profile or ROW_MATERIALIZATION_PROFILE,
            requested_tables=tuple(requested_tables),
            materialization_policy=materialization_policy,
            projection_digest_policy=projection_digest_policy,
            table_rule_registry=effective_table_rule_registry,
        )
    )


def materialize_sql_source_preview(
    *,
    source_sql: str,
    source_path: Path | None = None,
    source_kind: str = "SQL_DUMP_SOURCE",
    requested_tables: Sequence[str] = (),
    parser_version: str | None = None,
    table_ruleset_version: str | None = None,
    scalar_encoding_version: str | None = None,
    snapshot_materialization_contract_version: str | None = None,
    summary_contract_version: str | None = None,
    row_materialization_profile: str | None = None,
    materialization_policy: str = "READERS_REQUIRED",
    projection_digest_policy: str = PROJECTION_DIGEST_POLICY_DISABLED,
    table_rule_registry: TableRuleRegistry | None = None,
) -> SnapshotMaterializationResult:
    effective_table_rule_registry = table_rule_registry or default_table_rule_registry()
    return materialize_sql_snapshot_preview(
        SnapshotMaterializationInput(
            source_path=source_path,
            source_sql=source_sql,
            source_kind=source_kind,
            digest_contract_version=SNAPSHOT_DIGEST_CONTRACT_VERSION,
            parser_version=parser_version or SQL_PARSER_VERSION,
            parser_input_contract_version=SQL_DUMP_SOURCE_CONTRACT_VERSION,
            table_ruleset_version=(
                table_ruleset_version or effective_table_rule_registry.table_ruleset_version
            ),
            scalar_encoding_version=scalar_encoding_version or SCALAR_ENCODING_VERSION,
            snapshot_materialization_contract_version=(
                snapshot_materialization_contract_version
                or SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION
            ),
            summary_contract_version=summary_contract_version
            or SNAPSHOT_SUMMARY_SCHEMA_VERSION,
            row_materialization_profile=row_materialization_profile or ROW_MATERIALIZATION_PROFILE,
            requested_tables=tuple(requested_tables),
            materialization_policy=materialization_policy,
            projection_digest_policy=projection_digest_policy,
            table_rule_registry=effective_table_rule_registry,
        )
    )


def materialize_sql_file(
    source_path: Path,
    *,
    source_kind: str = "SQL_DUMP_SOURCE",
    requested_tables: Sequence[str] = (),
    table_ruleset_version: str | None = None,
    materialization_policy: str = "READERS_REQUIRED",
    projection_digest_policy: str = PROJECTION_DIGEST_POLICY_DISABLED,
    table_rule_registry: TableRuleRegistry | None = None,
) -> SnapshotMaterializationResult:
    effective_table_rule_registry = table_rule_registry or default_table_rule_registry()
    return materialize_sql_snapshot(
        SnapshotMaterializationInput(
            source_path=source_path,
            source_kind=source_kind,
            digest_contract_version=SNAPSHOT_DIGEST_CONTRACT_VERSION,
            table_ruleset_version=(
                table_ruleset_version or effective_table_rule_registry.table_ruleset_version
            ),
            requested_tables=tuple(requested_tables),
            materialization_policy=materialization_policy,
            projection_digest_policy=projection_digest_policy,
            table_rule_registry=effective_table_rule_registry,
        )
    )


def materialize_sql_file_preview(
    source_path: Path,
    *,
    source_kind: str = "SQL_DUMP_SOURCE",
    requested_tables: Sequence[str] = (),
    table_ruleset_version: str | None = None,
    materialization_policy: str = "READERS_REQUIRED",
    projection_digest_policy: str = PROJECTION_DIGEST_POLICY_DISABLED,
    table_rule_registry: TableRuleRegistry | None = None,
) -> SnapshotMaterializationResult:
    effective_table_rule_registry = table_rule_registry or default_table_rule_registry()
    return materialize_sql_snapshot_preview(
        SnapshotMaterializationInput(
            source_path=source_path,
            source_kind=source_kind,
            digest_contract_version=SNAPSHOT_DIGEST_CONTRACT_VERSION,
            table_ruleset_version=(
                table_ruleset_version or effective_table_rule_registry.table_ruleset_version
            ),
            requested_tables=tuple(requested_tables),
            materialization_policy=materialization_policy,
            projection_digest_policy=projection_digest_policy,
            table_rule_registry=effective_table_rule_registry,
        )
    )


def finalize_snapshot_materialization(
    materialization_result: SnapshotMaterializationResult,
) -> SnapshotMaterializationResult:
    if materialization_result.snapshot.materialization_stage == SnapshotMaterializationStage.FINAL.value:
        return materialization_result
    if materialization_result.table_set is None:
        raise ValueError("provisional snapshot materialization requires a table_set")
    if materialization_result.materialization_input is None:
        raise ValueError("provisional snapshot materialization requires materialization_input")
    if materialization_result.snapshot.source_digest is None:
        raise ValueError("provisional snapshot materialization requires source_digest")

    materialization_input = materialization_result.materialization_input
    finalized_tables: dict[str, SnapshotTable] = {}
    finalized_descriptors: list[SnapshotTableDescriptor] = []
    for table_name in sorted(materialization_result.table_set.tables):
        table = materialization_result.table_set.tables[table_name]
        raw_rows = tuple(table.reader.iter_rows())
        rows = normalize_snapshot_rows(raw_rows, table.descriptor.columns)
        raw_content_digest = stable_snapshot_rows_digest(
            raw_rows,
            table.descriptor.columns,
        )
        final_descriptor = replace(
            table.descriptor,
            materialization_stage=SnapshotMaterializationStage.FINAL.value,
            raw_content_digest=raw_content_digest,
            business_content_digest=raw_content_digest,
        )
        final_reader = replace(
            table.reader,
            _descriptor=final_descriptor,
            _rows=rows,
            _content_digest=raw_content_digest,
        )
        final_table = replace(table, descriptor=final_descriptor, reader=final_reader)
        finalized_tables[table_name] = final_table
        finalized_descriptors.append(final_descriptor)

    finalized_descriptors = list(
        assign_canonical_artifact_refs(
            sorted(finalized_descriptors, key=lambda descriptor: descriptor.table_name),
            previous_summary=materialization_input.previous_summary,
        )
    )
    finalized_descriptor_map = {
        descriptor.table_name: descriptor for descriptor in finalized_descriptors
    }
    finalized_tables = {
        table_name: replace(
            table,
            descriptor=finalized_descriptor_map[table_name],
            reader=replace(table.reader, _descriptor=finalized_descriptor_map[table_name]),
        )
        for table_name, table in finalized_tables.items()
    }
    row_count_total = sum(descriptor.row_count for descriptor in finalized_descriptors)
    raw_state_digest = DigestRef.from_payload(
        {
            "materialization_stage": SnapshotMaterializationStage.FINAL.value,
            "table_count": len(finalized_descriptors),
            "row_count_total": row_count_total,
            "tables": [
                {
                    "table_name": descriptor.table_name,
                    "row_count": descriptor.row_count,
                    "raw_content_digest": descriptor.materialization_digest.to_payload(),
                }
                for descriptor in finalized_descriptors
            ],
        }
    )
    snapshot_digest = DigestRef.from_payload(
        {
            "digest_contract_version": materialization_input.digest_contract_version,
            "materialization_stage": SnapshotMaterializationStage.FINAL.value,
            "source_kind": materialization_input.source_kind,
            "source_digest": materialization_result.snapshot.source_digest.to_payload(),
            "parser_version": materialization_input.parser_version,
            "table_ruleset_version": materialization_input.table_ruleset_version,
            "scalar_encoding_version": materialization_input.scalar_encoding_version,
            "snapshot_materialization_contract_version": materialization_input.snapshot_materialization_contract_version,
            "row_materialization_profile": materialization_input.row_materialization_profile,
            "requested_tables": sorted(materialization_input.requested_tables),
            "tables": [
                {
                    "table_name": descriptor.table_name,
                    "compare_schema_digest": descriptor.compare_schema_digest.to_payload(),
                    "raw_content_digest": descriptor.materialization_digest.to_payload(),
                    "row_count": descriptor.row_count,
                }
                for descriptor in finalized_descriptors
            ],
        }
    )
    snapshot_id = f"snapshot:{snapshot_digest.hex_digest}"
    source_context = (
        materialization_result.summary.source_context
        or materialization_result.snapshot.source_context
        or SnapshotSourceContext(
            source_kind=materialization_input.source_kind,
            source_digest=materialization_result.snapshot.source_digest,
        )
    )
    summary = replace(
        materialization_result.summary,
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        raw_state_digest=raw_state_digest,
        business_state_digest=raw_state_digest,
        materialization_stage=SnapshotMaterializationStage.FINAL.value,
        table_count=len(finalized_descriptors),
        row_count_total=row_count_total,
        tables=tuple(finalized_descriptors),
        source_context=source_context,
    )
    snapshot = replace(
        materialization_result.snapshot,
        snapshot_id=snapshot_id,
        materialization_stage=SnapshotMaterializationStage.FINAL.value,
        snapshot_digest=snapshot_digest,
        raw_state_digest=raw_state_digest,
        business_state_digest=raw_state_digest,
        summary=summary,
        source_digest=materialization_result.snapshot.source_digest,
        source_context=source_context,
    )
    table_set = replace(
        materialization_result.table_set,
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        tables=finalized_tables,
    )
    return replace(
        materialization_result,
        snapshot=snapshot,
        summary=summary,
        table_set=table_set,
    )


def resolve_snapshot_table_set(
    snapshot_ref_or_result: SnapshotMaterializationResult | Snapshot | SnapshotTableSet,
    policy: str = "READERS_REQUIRED",
    *,
    table_rule_registry: TableRuleRegistry | None = None,
) -> SnapshotTableSet:
    if isinstance(snapshot_ref_or_result, SnapshotTableSet):
        return snapshot_ref_or_result
    if isinstance(snapshot_ref_or_result, SnapshotMaterializationResult):
        if snapshot_ref_or_result.table_set is not None:
            return snapshot_ref_or_result.table_set
        snapshot = snapshot_ref_or_result.snapshot
    elif isinstance(snapshot_ref_or_result, Snapshot):
        snapshot = snapshot_ref_or_result
    else:
        raise TypeError("snapshot_ref_or_result must be a Snapshot, SnapshotMaterializationResult or SnapshotTableSet")
    if snapshot.summary is None:
        raise ValueError("snapshot summary is required to resolve a table set")
    source_document_ref = _snapshot_source_document_ref(snapshot)
    if source_document_ref is None:
        raise ValueError("snapshot does not carry a source document reference")
    sql_dump_source = resolve_sql_dump_source(
        source_document_ref,
        parser_input_contract_version=snapshot.parser_version,
    )
    requested_tables = tuple(table.table_name for table in snapshot.summary.tables)
    rematerialized = materialize_sql_dump_source(
        sql_dump_source,
        SnapshotMaterializationInput(
            sql_dump_source=sql_dump_source,
            source_kind=snapshot.source_kind,
            digest_contract_version=SNAPSHOT_DIGEST_CONTRACT_VERSION,
            parser_version=snapshot.parser_version,
            parser_input_contract_version=sql_dump_source.parser_input_contract_version,
            table_ruleset_version=snapshot.table_ruleset_version,
            scalar_encoding_version=snapshot.scalar_encoding_version,
            snapshot_materialization_contract_version=snapshot.snapshot_materialization_contract_version,
            row_materialization_profile=snapshot.row_materialization_profile,
            requested_tables=requested_tables,
            materialization_policy=policy,
            cache_policy="READ_ONLY" if policy != "DISABLED" else "DISABLED",
            table_rule_registry=table_rule_registry or default_table_rule_registry(),
        ),
    )
    if rematerialized.table_set is None:
        raise ValueError("table set resolution failed")
    return rematerialized.table_set


def _coerce_parse_context(
    parser_context: SqlDumpParseContext | SnapshotMaterializationInput | None,
) -> SqlDumpParseContext:
    if parser_context is None:
        return SqlDumpParseContext()
    if isinstance(parser_context, SqlDumpParseContext):
        return parser_context
    if isinstance(parser_context, SnapshotMaterializationInput):
        return SqlDumpParseContext(
            parser_version=parser_context.parser_version,
            parser_input_contract_version=parser_context.parser_input_contract_version,
            scalar_encoding_version=parser_context.scalar_encoding_version,
            requested_tables=parser_context.requested_tables,
        )
    raise TypeError("parser_context must be a SqlDumpParseContext, SnapshotMaterializationInput or None")


def _coerce_sql_dump_source(
    sql_dump_source: SqlDumpSource | SourceDocumentRef | SourcePackageStagingResult | SourcePackage | ArtifactRef | Path | str | bytes | bytearray | memoryview,
    *,
    parser_input_contract_version: str,
) -> SqlDumpSource:
    if isinstance(sql_dump_source, SqlDumpSource):
        return sql_dump_source
    return resolve_sql_dump_source(
        sql_dump_source,
        parser_input_contract_version=parser_input_contract_version,
    )


def _parse_skip_hook(
    parser_context: SqlDumpParseContext | SnapshotMaterializationInput | None,
):
    if not isinstance(parser_context, SnapshotMaterializationInput):
        return None
    table_rule_registry = _resolve_table_rule_registry(parser_context)
    requested_tables = set(parser_context.requested_tables)

    def should_skip(definition: ParsedTableDefinition) -> bool:
        if requested_tables and definition.table_name not in requested_tables:
            return True
        if definition.table_name == "version_manager":
            return False
        decision = table_rule_registry.resolve_table_semantics(
            definition.table_name,
            primary_key_columns=definition.primary_key_columns,
        )
        return decision.static_role is TableStaticRole.SKIP

    return should_skip


def _largest_parse_skipped_tables(
    parsed: ParsedSqlDump,
    *,
    limit: int = 10,
) -> list[dict[str, object]]:
    return [
        {
            "table_name": table_name,
            "parse_skipped_row_count": bundle.parse_skipped_row_count,
            "parse_skipped_insert_statement_count": bundle.parse_skipped_insert_statement_count,
        }
        for table_name, bundle in sorted(
            parsed.tables.items(),
            key=lambda item: item[1].parse_skipped_row_count,
            reverse=True,
        )
        if bundle.parse_skipped_row_count > 0
    ][:limit]


def _resolve_sql_dump_source_from_materialization_input(
    materialization_input: SnapshotMaterializationInput,
) -> SqlDumpSource:
    if materialization_input.sql_dump_source is not None:
        return _coerce_sql_dump_source(
            materialization_input.sql_dump_source,
            parser_input_contract_version=materialization_input.parser_input_contract_version,
        )
    if materialization_input.source_path is not None:
        return _coerce_sql_dump_source(
            materialization_input.source_path,
            parser_input_contract_version=materialization_input.parser_input_contract_version,
        )
    if materialization_input.source_sql is not None:
        return _coerce_sql_dump_source(
            materialization_input.source_sql,
            parser_input_contract_version=materialization_input.parser_input_contract_version,
        )
    raise ValueError("materialization input does not carry a SQL dump source")


def _resolve_table_rule_registry(
    materialization_input: SnapshotMaterializationInput,
) -> TableRuleRegistry:
    if materialization_input.table_rule_registry is not None:
        return materialization_input.table_rule_registry
    return default_table_rule_registry()


def _snapshot_source_document_ref(snapshot: Snapshot) -> SourceDocumentRef | None:
    if snapshot.source_context is not None and snapshot.source_context.source_document_ref is not None:
        source_document_ref = snapshot.source_context.source_document_ref
        if isinstance(source_document_ref, SourceDocumentRef):
            return source_document_ref
    if snapshot.source_package_id is None:
        return None
    try:
        return resolve_required_sql_document(snapshot.source_package_id)
    except Exception:
        return None


def _source_package_digest_for_source_dump(sql_dump_source: SqlDumpSource) -> DigestRef | None:
    try:
        source_package = get_source_package(sql_dump_source.source_document_ref.source_package_id)
    except Exception:
        return None
    return source_package.source_package_digest


def _source_context_for_sql_dump_source(
    sql_dump_source: SqlDumpSource,
    *,
    source_kind: str,
) -> SnapshotSourceContext:
    source_package_digest = _source_package_digest_for_source_dump(sql_dump_source)
    return SnapshotSourceContext(
        source_kind=source_kind,
        source_digest=sql_dump_source.sql_source_digest,
        source_package_digest=source_package_digest,
        sql_source_digest=sql_dump_source.sql_source_digest,
        source_document_ref=sql_dump_source.source_document_ref,
    )


def _materialize_work_items(
    work_items: Sequence[_TableMaterializationWorkItem],
    *,
    materialization_input: SnapshotMaterializationInput,
    finalize_canonical_digests: bool,
) -> tuple[tuple[_TableMaterializationOutcome, ...], dict[str, object]]:
    if not work_items:
        return tuple(), _parallel_stats(
            parallel_enabled=False,
            worker_count=0,
            lane_row_counts=(),
        )
    worker_count = _final_materialization_worker_count() if finalize_canonical_digests else 1
    min_rows = _parallel_min_rows()
    total_rows = sum(item.bundle.row_count for item in work_items)
    if (
        not finalize_canonical_digests
        or worker_count < 2
        or len(work_items) < 2
        or total_rows < min_rows
    ):
        return (
            _materialize_work_items_sequential(
                work_items,
                materialization_context=_table_materialization_context(materialization_input),
                finalize_canonical_digests=finalize_canonical_digests,
            ),
            _parallel_stats(
                parallel_enabled=False,
                worker_count=1,
                lane_row_counts=(total_rows,),
            ),
        )

    lanes = _build_materialization_lanes(work_items)
    if len(lanes) < 2 or any(not lane for lane in lanes):
        return (
            _materialize_work_items_sequential(
                work_items,
                materialization_context=_table_materialization_context(materialization_input),
                finalize_canonical_digests=finalize_canonical_digests,
            ),
            _parallel_stats(
                parallel_enabled=False,
                worker_count=1,
                lane_row_counts=(total_rows,),
            ),
        )

    dispatch_started_at = perf_counter()
    context = _table_materialization_context(materialization_input)
    with ProcessPoolExecutor(
        max_workers=2,
        mp_context=multiprocessing.get_context("spawn"),
    ) as executor:
        futures = [
            executor.submit(
                _materialize_table_batch,
                tuple(lane),
                context,
                finalize_canonical_digests,
            )
            for lane in lanes
        ]
        dispatch_duration_ms = benchmark_elapsed_ms(dispatch_started_at)
        merge_started_at = perf_counter()
        batch_results = tuple(future.result() for future in futures)
        merge_duration_ms = benchmark_elapsed_ms(merge_started_at)

    outcomes: list[_TableMaterializationOutcome] = []
    for batch_result in batch_results:
        outcomes.extend(batch_result.outcomes)
    lane_row_counts = tuple(sum(item.bundle.row_count for item in lane) for lane in lanes)
    return (
        tuple(outcomes),
        _parallel_stats(
            parallel_enabled=True,
            worker_count=2,
            lane_row_counts=lane_row_counts,
            parallel_dispatch_ms=dispatch_duration_ms,
            parallel_worker_compute_ms=max(
                (batch_result.duration_ms for batch_result in batch_results),
                default=0,
            ),
            parallel_merge_ms=merge_duration_ms,
        ),
    )


def _materialize_work_items_sequential(
    work_items: Sequence[_TableMaterializationWorkItem],
    *,
    materialization_context: _TableMaterializationContext,
    finalize_canonical_digests: bool,
) -> tuple[_TableMaterializationOutcome, ...]:
    return _materialize_table_batch(
        tuple(work_items),
        materialization_context,
        finalize_canonical_digests,
    ).outcomes


def _materialize_table_batch(
    work_items: tuple[_TableMaterializationWorkItem, ...],
    materialization_context: _TableMaterializationContext,
    finalize_canonical_digests: bool,
) -> _TableMaterializationBatchResult:
    started_at = perf_counter()
    outcomes: list[_TableMaterializationOutcome] = []
    for item in work_items:
        try:
            descriptor, table, timing = _materialize_table(
                item.bundle,
                materialization_input=materialization_context,
                decision=item.decision,
                finalize_canonical_digests=finalize_canonical_digests,
            )
            outcomes.append(
                _TableMaterializationOutcome(
                    table_name=item.table_name,
                    descriptor=descriptor,
                    table=table,
                    timing=timing,
                    decision=item.decision,
                    decision_duration_ms=item.decision_duration_ms,
                )
            )
        except Exception as exc:  # noqa: BLE001
            outcomes.append(
                _TableMaterializationOutcome(
                    table_name=item.table_name,
                    descriptor=None,
                    table=None,
                    timing=None,
                    decision=item.decision,
                    decision_duration_ms=item.decision_duration_ms,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )
    return _TableMaterializationBatchResult(
        outcomes=tuple(outcomes),
        duration_ms=benchmark_elapsed_ms(started_at),
    )


def _build_materialization_lanes(
    work_items: Sequence[_TableMaterializationWorkItem],
) -> tuple[tuple[_TableMaterializationWorkItem, ...], tuple[_TableMaterializationWorkItem, ...]]:
    heavy_tables = _configured_heavy_tables()
    heavy_rank = {table_name: index for index, table_name in enumerate(heavy_tables)}
    sorted_items = sorted(
        work_items,
        key=lambda item: (
            0 if item.table_name in heavy_rank else 1,
            heavy_rank.get(item.table_name, 0),
            -item.bundle.row_count,
            item.table_name,
        ),
    )
    lanes: list[list[_TableMaterializationWorkItem]] = [[], []]
    lane_row_counts = [0, 0]
    for item in sorted_items:
        lane_index = 0 if lane_row_counts[0] <= lane_row_counts[1] else 1
        lanes[lane_index].append(item)
        lane_row_counts[lane_index] += item.bundle.row_count
    return tuple(lanes[0]), tuple(lanes[1])


def _table_materialization_context(
    materialization_input: SnapshotMaterializationInput,
) -> _TableMaterializationContext:
    return _TableMaterializationContext(
        table_ruleset_version=materialization_input.table_ruleset_version,
        scalar_encoding_version=materialization_input.scalar_encoding_version,
        row_materialization_profile=materialization_input.row_materialization_profile,
        projection_digest_policy=materialization_input.projection_digest_policy,
    )


def _final_materialization_worker_count() -> int:
    value = os.getenv("BACKEND_VNEXT_SNAPSHOT_MATERIALIZE_FINAL_WORKERS", "2").strip()
    try:
        parsed = int(value)
    except ValueError:
        return 2
    return 2 if parsed >= 2 else 1


def _parallel_min_rows() -> int:
    value = os.getenv("BACKEND_VNEXT_SNAPSHOT_MATERIALIZE_PARALLEL_MIN_ROWS", "5000").strip()
    try:
        parsed = int(value)
    except ValueError:
        return 5000
    return max(0, parsed)


def _configured_heavy_tables() -> tuple[str, ...]:
    raw_value = os.getenv("BACKEND_VNEXT_SNAPSHOT_MATERIALIZE_HEAVY_TABLES", "")
    configured: list[str] = []
    seen: set[str] = set()
    for item in raw_value.split(","):
        table_name = canonical_identifier(item)
        if not table_name or table_name in seen:
            continue
        seen.add(table_name)
        configured.append(table_name)
    return tuple(configured)


def _parallel_stats(
    *,
    parallel_enabled: bool,
    worker_count: int,
    lane_row_counts: Sequence[int],
    parallel_dispatch_ms: int = 0,
    parallel_worker_compute_ms: int = 0,
    parallel_merge_ms: int = 0,
) -> dict[str, object]:
    return {
        "parallel_enabled": parallel_enabled,
        "worker_count": worker_count,
        "lane_count": len(tuple(lane_row_counts)),
        "lane_row_counts": tuple(lane_row_counts),
        "parallel_dispatch_ms": parallel_dispatch_ms,
        "parallel_worker_compute_ms": parallel_worker_compute_ms,
        "parallel_merge_ms": parallel_merge_ms,
    }


def _materialize_parsed_dump(
    *,
    materialization_input: SnapshotMaterializationInput,
    sql_dump_source: SqlDumpSource,
    parsed: ParsedSqlDump,
    parser_diagnostics: tuple[DiagnosticRecord, ...] = (),
    finalize_canonical_digests: bool = True,
    benchmark_run_id: str | None = None,
) -> SnapshotMaterializationResult:
    requested_tables = set(materialization_input.requested_tables)
    table_rule_registry = _resolve_table_rule_registry(materialization_input)
    table_diagnostics: list[DiagnosticRecord] = list(parser_diagnostics)
    tables: dict[str, SnapshotTable] = {}
    descriptors: list[SnapshotTableDescriptor] = []
    skipped_tables: list[str] = []
    rule_skipped_tables: list[dict[str, object]] = []
    table_profiles: list[_TableMaterializationProfile] = []
    profile_enabled = formal_upload_benchmark_enabled()

    table_loop_started_at = perf_counter()
    table_materialize_duration_ms = 0
    table_rows_finalized = 0
    rule_skipped_row_count = 0
    work_items: list[_TableMaterializationWorkItem] = []
    for table_name in sorted(parsed.tables):
        per_table_started_at = perf_counter()
        if requested_tables and table_name not in requested_tables:
            if profile_enabled:
                bundle = parsed.tables[table_name]
                table_profiles.append(
                    _build_table_materialization_profile(
                        bundle=bundle,
                        decision=None,
                        finalize_canonical_digests=finalize_canonical_digests,
                        rule_decision_duration_ms=None,
                        materialized=False,
                        skip_reason="REQUESTED_TABLE_FILTER",
                        timing=None,
                        total_duration_ms=benchmark_elapsed_ms(per_table_started_at),
                    )
                )
            continue
        bundle = parsed.tables[table_name]
        decision_started_at = perf_counter()
        decision = build_table_handling_decision(
            table_rule_registry,
            table_name,
            row_count=bundle.row_count,
            has_schema=True,
            primary_key_columns=bundle.definition.primary_key_columns,
        )
        decision_duration_ms = benchmark_elapsed_ms(decision_started_at)
        if not decision.keep_in_raw_snapshot:
            rule_skipped_row_count += bundle.row_count
            rule_skipped_tables.append(
                {
                    "table_name": table_name,
                    "static_role": decision.static_role.value,
                    "runtime_state": decision.runtime_state.value,
                    "compare_mode": decision.compare_mode.value,
                }
            )
            if profile_enabled:
                table_profiles.append(
                    _build_table_materialization_profile(
                        bundle=bundle,
                        decision=decision,
                        finalize_canonical_digests=finalize_canonical_digests,
                        rule_decision_duration_ms=decision_duration_ms,
                        materialized=False,
                        skip_reason="TABLE_RULE_SKIP",
                        timing=None,
                        total_duration_ms=benchmark_elapsed_ms(per_table_started_at),
                    )
            )
            continue
        work_items.append(
            _TableMaterializationWorkItem(
                table_name=table_name,
                bundle=bundle,
                decision=decision,
                decision_duration_ms=decision_duration_ms,
            )
        )

    materialize_started_at = perf_counter()
    materialization_outcomes, parallel_stats = _materialize_work_items(
        work_items,
        materialization_input=materialization_input,
        finalize_canonical_digests=finalize_canonical_digests,
    )
    materialize_duration_ms = benchmark_elapsed_ms(materialize_started_at)
    descriptor_build_duration_ms = 0
    reader_build_duration_ms = 0
    row_finalize_duration_ms = 0
    row_digest_duration_ms = 0
    descriptor_finalize_duration_ms = 0
    projection_digest_duration_ms = 0
    projection_digest_table_count = 0
    projection_digest_count = 0
    projection_digest_row_count = 0
    for outcome in sorted(materialization_outcomes, key=lambda item: item.table_name):
        bundle = parsed.tables[outcome.table_name]
        if outcome.descriptor is None or outcome.table is None or outcome.timing is None:
            skipped_tables.append(outcome.table_name)
            if profile_enabled:
                table_profiles.append(
                    _build_table_materialization_profile(
                        bundle=bundle,
                        decision=outcome.decision,
                        finalize_canonical_digests=finalize_canonical_digests,
                        rule_decision_duration_ms=outcome.decision_duration_ms,
                        materialized=False,
                        skip_reason="MATERIALIZATION_ERROR",
                        error_type=outcome.error_type,
                        timing=None,
                        total_duration_ms=outcome.decision_duration_ms,
                    )
                )
            table_diagnostics.append(
                DiagnosticRecord(
                    code="snapshot.materialization.table-skipped",
                    message="table could not be materialized and was skipped",
                    phase="materialization",
                    severity="WARNING",
                    details={
                        "table_name": outcome.table_name,
                        "error_type": outcome.error_type,
                        "error": outcome.error,
                    },
                )
            )
            continue
        table_materialize_duration_ms += outcome.timing.total_duration_ms
        descriptor_build_duration_ms += outcome.timing.descriptor_build_duration_ms
        reader_build_duration_ms += outcome.timing.reader_build_duration_ms
        row_finalize_duration_ms += outcome.timing.row_finalize_duration_ms or 0
        row_digest_duration_ms += outcome.timing.row_digest_duration_ms or 0
        descriptor_finalize_duration_ms += outcome.timing.descriptor_finalize_duration_ms or 0
        projection_digest_duration_ms += outcome.timing.projection_digest_duration_ms
        projection_digest_count += outcome.timing.projection_digest_count
        projection_digest_row_count += outcome.timing.projection_digest_row_count
        if outcome.timing.projection_digest_count:
            projection_digest_table_count += 1
        table_rows_finalized += outcome.descriptor.row_count
        if profile_enabled:
            table_profiles.append(
                _build_table_materialization_profile(
                    bundle=bundle,
                    decision=outcome.decision,
                    finalize_canonical_digests=finalize_canonical_digests,
                    rule_decision_duration_ms=outcome.decision_duration_ms,
                    materialized=True,
                    skip_reason=None,
                    timing=outcome.timing,
                    total_duration_ms=outcome.decision_duration_ms + outcome.timing.total_duration_ms,
                )
            )
        tables[outcome.descriptor.table_name] = outcome.table
        descriptors.append(outcome.descriptor)
    log_formal_upload_benchmark_event(
        "snapshot_materialize.table_loop",
        benchmark_run_id=benchmark_run_id,
        requested_table_count=len(requested_tables),
        parsed_table_count=len(parsed.tables),
        materialized_table_count=len(descriptors),
        skipped_table_count=len(skipped_tables),
        rule_skipped_table_count=len(rule_skipped_tables),
        row_count_total=table_rows_finalized,
        table_materialize_duration_ms=table_materialize_duration_ms,
        descriptor_build_duration_ms=descriptor_build_duration_ms,
        reader_build_duration_ms=reader_build_duration_ms,
        row_finalize_duration_ms=row_finalize_duration_ms,
        row_digest_duration_ms=row_digest_duration_ms,
        descriptor_finalize_duration_ms=descriptor_finalize_duration_ms,
        projection_digest_duration_ms=projection_digest_duration_ms,
        projection_digest_table_count=projection_digest_table_count,
        projection_digest_count=projection_digest_count,
        projection_digest_row_count=projection_digest_row_count,
        projection_digest_enabled=materialization_input.projection_digest_policy
        != PROJECTION_DIGEST_POLICY_DISABLED,
        projection_digest_policy=materialization_input.projection_digest_policy,
        materialized_row_count=table_rows_finalized,
        rule_skipped_row_count=rule_skipped_row_count,
        parse_skipped_insert_table_count=parsed.parse_skipped_insert_table_count,
        parse_skipped_insert_statement_count=parsed.parse_skipped_insert_statement_count,
        parse_skipped_insert_row_count=parsed.parse_skipped_insert_row_count,
        largest_parse_skipped_tables=_largest_parse_skipped_tables(parsed),
        profile_event_count=len(table_profiles),
        top_slow_tables=_top_slow_table_profiles(table_profiles),
        largest_rule_skipped_tables=_largest_rule_skipped_table_profiles(table_profiles),
        finalize_canonical_digests=finalize_canonical_digests,
        materialize_duration_ms=materialize_duration_ms,
        parallel_enabled=parallel_stats["parallel_enabled"],
        worker_count=parallel_stats["worker_count"],
        lane_count=parallel_stats["lane_count"],
        lane_row_counts=parallel_stats["lane_row_counts"],
        parallel_dispatch_ms=parallel_stats["parallel_dispatch_ms"],
        parallel_worker_compute_ms=parallel_stats["parallel_worker_compute_ms"],
        parallel_merge_ms=parallel_stats["parallel_merge_ms"],
        duration_ms=benchmark_elapsed_ms(table_loop_started_at),
    )
    if projection_digest_count:
        log_formal_upload_benchmark_event(
            "snapshot_materialize.projection_digest_build",
            benchmark_run_id=benchmark_run_id,
            requested_table_count=len(requested_tables),
            projection_digest_table_count=projection_digest_table_count,
            projection_digest_count=projection_digest_count,
            projection_digest_row_count=projection_digest_row_count,
            projection_digest_duration_ms=projection_digest_duration_ms,
            projection_digest_policy=materialization_input.projection_digest_policy,
            top_slow_tables=_top_slow_projection_digest_profiles(table_profiles),
            finalize_canonical_digests=finalize_canonical_digests,
            duration_ms=projection_digest_duration_ms,
        )
    _log_table_materialization_profiles(
        benchmark_run_id=benchmark_run_id,
        profiles=table_profiles,
        requested_table_count=len(requested_tables),
        parsed_table_count=len(parsed.tables),
        materialized_table_count=len(descriptors),
        skipped_table_count=len(skipped_tables),
        rule_skipped_table_count=len(rule_skipped_tables),
        materialized_row_count=table_rows_finalized,
        rule_skipped_row_count=rule_skipped_row_count,
        parse_skipped_insert_table_count=parsed.parse_skipped_insert_table_count,
        parse_skipped_insert_statement_count=parsed.parse_skipped_insert_statement_count,
        parse_skipped_insert_row_count=parsed.parse_skipped_insert_row_count,
        largest_parse_skipped_tables=_largest_parse_skipped_tables(parsed),
        finalize_canonical_digests=finalize_canonical_digests,
        projection_digest_duration_ms=projection_digest_duration_ms,
        projection_digest_table_count=projection_digest_table_count,
        projection_digest_count=projection_digest_count,
        projection_digest_row_count=projection_digest_row_count,
        projection_digest_policy=materialization_input.projection_digest_policy,
        duration_ms=benchmark_elapsed_ms(table_loop_started_at),
    )

    if rule_skipped_tables:
        table_diagnostics.append(
            DiagnosticRecord(
                code="snapshot.materialization.table-skipped-by-rule",
                message="table was excluded by the active table rules",
                phase="materialization",
                severity="WARNING",
                details={
                    "count": len(rule_skipped_tables),
                    "tables": rule_skipped_tables,
                },
            )
        )

    missing_requested_tables = sorted(requested_tables - set(tables))
    if missing_requested_tables:
        table_diagnostics.append(
            DiagnosticRecord(
                code="snapshot.materialization.requested-table-missing",
                message="requested table(s) were not found in the SQL source",
                phase="materialization",
                severity="WARNING",
                details={"tables": missing_requested_tables},
            )
        )

    if parsed.unsupported_statements:
        table_diagnostics.append(
            DiagnosticRecord(
                code="snapshot.materialization.unsupported-statements",
                message="unsupported SQL statements were skipped",
                phase="materialization",
                severity="WARNING",
                details={
                    "count": len(parsed.unsupported_statements),
                    "sample": list(parsed.unsupported_statements[:3]),
                },
            )
        )

    digest_started_at = perf_counter()
    source_context = _source_context_for_sql_dump_source(
        sql_dump_source,
        source_kind=materialization_input.source_kind,
    )
    materialization_stage = (
        SnapshotMaterializationStage.FINAL
        if finalize_canonical_digests
        else SnapshotMaterializationStage.PROVISIONAL
    )
    descriptors = sorted(descriptors, key=lambda descriptor: descriptor.table_name)
    if materialization_stage == SnapshotMaterializationStage.FINAL:
        descriptors = list(
            assign_canonical_artifact_refs(
                descriptors,
                previous_summary=materialization_input.previous_summary,
            )
        )
    row_count_total = sum(descriptor.row_count for descriptor in descriptors)
    raw_state_digest = DigestRef.from_payload(
        {
            "materialization_stage": materialization_stage.value,
            "table_count": len(descriptors),
            "row_count_total": row_count_total,
            "tables": [
                {
                    "table_name": descriptor.table_name,
                    "row_count": descriptor.row_count,
                    "raw_content_digest": descriptor.materialization_digest.to_payload(),
                }
                for descriptor in descriptors
            ],
        }
    )
    snapshot_digest = DigestRef.from_payload(
        {
            "materialization_stage": materialization_stage.value,
            "source_kind": materialization_input.source_kind,
            "source_digest": sql_dump_source.sql_source_digest.to_payload(),
            "parser_version": materialization_input.parser_version,
            "table_ruleset_version": materialization_input.table_ruleset_version,
            "scalar_encoding_version": materialization_input.scalar_encoding_version,
            "row_materialization_profile": materialization_input.row_materialization_profile,
            "requested_tables": sorted(requested_tables),
            "tables": [
                {
                    "table_name": descriptor.table_name,
                    "compare_schema_digest": descriptor.compare_schema_digest.to_payload(),
                    "raw_content_digest": descriptor.materialization_digest.to_payload(),
                    "row_count": descriptor.row_count,
                }
                for descriptor in descriptors
            ],
        }
    )
    snapshot_id = f"snapshot:{snapshot_digest.hex_digest}"
    log_formal_upload_benchmark_event(
        "snapshot_materialize.digest_build",
        benchmark_run_id=benchmark_run_id,
        table_count=len(descriptors),
        row_count_total=row_count_total,
        finalize_canonical_digests=finalize_canonical_digests,
        duration_ms=benchmark_elapsed_ms(digest_started_at),
    )
    config_time_started_at = perf_counter()
    configuration_generated_at = _extract_configuration_generated_at(parsed)
    log_formal_upload_benchmark_event(
        "snapshot_materialize.configuration_generated_at",
        benchmark_run_id=benchmark_run_id,
        found=configuration_generated_at is not None,
        duration_ms=benchmark_elapsed_ms(config_time_started_at),
    )
    summary_started_at = perf_counter()
    summary = SnapshotSummary(
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        raw_state_digest=raw_state_digest,
        business_state_digest=raw_state_digest,
        materialization_stage=materialization_stage.value,
        parser_version=materialization_input.parser_version,
        table_ruleset_version=materialization_input.table_ruleset_version,
        summary_contract_version=materialization_input.summary_contract_version,
        table_count=len(descriptors),
        row_count_total=row_count_total,
        configuration_generated_at=configuration_generated_at,
        tables=tuple(descriptors),
        missing_or_unsupported_tables=tuple(sorted(set(missing_requested_tables) | set(skipped_tables))),
        source_context=source_context,
        diagnostics=tuple(table_diagnostics),
    )
    snapshot = Snapshot(
        snapshot_id=snapshot_id,
        source_kind=materialization_input.source_kind,
        source_package_id=sql_dump_source.source_document_ref.source_package_id,
        parser_version=materialization_input.parser_version,
        table_ruleset_version=materialization_input.table_ruleset_version,
        scalar_encoding_version=materialization_input.scalar_encoding_version,
        snapshot_materialization_contract_version=materialization_input.snapshot_materialization_contract_version,
        row_materialization_profile=materialization_input.row_materialization_profile,
        materialization_stage=materialization_stage.value,
        snapshot_digest=snapshot_digest,
        raw_state_digest=raw_state_digest,
        business_state_digest=raw_state_digest,
        summary=summary,
        source_digest=sql_dump_source.sql_source_digest,
        source_context=source_context,
        created_at=datetime.now(timezone.utc),
        diagnostics=tuple(table_diagnostics),
    )
    table_set = SnapshotTableSet(
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        table_ruleset_version=materialization_input.table_ruleset_version,
        tables=tables,
        resolution_plan=f"sql_dump:{materialization_input.materialization_policy}",
        diagnostics=tuple(table_diagnostics),
    )
    log_formal_upload_benchmark_event(
        "snapshot_materialize.summary_objects",
        benchmark_run_id=benchmark_run_id,
        table_count=len(descriptors),
        row_count_total=row_count_total,
        finalize_canonical_digests=finalize_canonical_digests,
        duration_ms=benchmark_elapsed_ms(summary_started_at),
    )
    return SnapshotMaterializationResult(
        snapshot=snapshot,
        summary=summary,
        table_set=table_set,
        materialization_input=materialization_input,
        cache_diagnostics=(),
        diagnostics=tuple(table_diagnostics),
    )


def _extract_configuration_generated_at(parsed: ParsedSqlDump) -> datetime | None:
    version_manager = parsed.tables.get("version_manager")
    if version_manager is None:
        return None

    saved_time_index = None
    for index, column in enumerate(version_manager.definition.columns):
        if column.name == "saved_time":
            saved_time_index = index
            break
    if saved_time_index is None:
        return None

    latest: datetime | None = None
    for row in version_manager.rows:
        if saved_time_index >= len(row):
            continue
        parsed_value = _parse_configuration_generated_at(row[saved_time_index])
        if parsed_value is not None:
            latest = parsed_value
    return latest


def _parse_configuration_generated_at(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _build_table_materialization_profile(
    *,
    bundle: ParsedTableBundle,
    decision: TableHandlingDecision | None,
    finalize_canonical_digests: bool,
    rule_decision_duration_ms: int | None,
    materialized: bool,
    skip_reason: str | None,
    timing: _TableMaterializationTiming | None,
    total_duration_ms: int,
    error_type: str | None = None,
) -> _TableMaterializationProfile:
    definition = bundle.definition
    return _TableMaterializationProfile(
        table_name=definition.table_name,
        parsed_row_count=bundle.row_count,
        column_count=len(definition.columns),
        insert_statement_count=len(bundle.insert_statements),
        primary_key_column_count=len(definition.primary_key_columns),
        parse_skipped_insert_statement_count=bundle.parse_skipped_insert_statement_count,
        parse_skipped_row_count=bundle.parse_skipped_row_count,
        rule_decision_duration_ms=rule_decision_duration_ms,
        static_role=None if decision is None else decision.static_role.value,
        runtime_state=None if decision is None else decision.runtime_state.value,
        compare_mode=None if decision is None else decision.compare_mode.value,
        keep_in_raw_snapshot=None if decision is None else decision.keep_in_raw_snapshot,
        enters_comparison=None if decision is None else decision.enters_comparison,
        include_in_preview=None if decision is None else decision.include_in_preview,
        include_in_diff_summary=None if decision is None else decision.include_in_diff_summary,
        export_base_table_artifact=None if decision is None else decision.export_base_table_artifact,
        export_diff_artifact=None if decision is None else decision.export_diff_artifact,
        finalize_canonical_digests=finalize_canonical_digests,
        materialized=materialized,
        skip_reason=skip_reason,
        error_type=error_type,
        timing=timing,
        total_duration_ms=total_duration_ms,
    )


def _top_slow_table_profiles(
    profiles: Sequence[_TableMaterializationProfile],
    *,
    limit: int = 10,
) -> list[dict[str, object]]:
    return [
        {
            "table_name": profile.table_name,
            "duration_ms": profile.total_duration_ms,
            "parsed_row_count": profile.parsed_row_count,
            "static_role": profile.static_role,
            "projection_digest_duration_ms": (
                0
                if profile.timing is None
                else profile.timing.projection_digest_duration_ms
            ),
            "projection_digest_count": (
                0 if profile.timing is None else profile.timing.projection_digest_count
            ),
        }
        for profile in sorted(
            (profile for profile in profiles if profile.materialized),
            key=lambda item: item.total_duration_ms,
            reverse=True,
        )[:limit]
    ]


def _top_slow_projection_digest_profiles(
    profiles: Sequence[_TableMaterializationProfile],
    *,
    limit: int = 10,
) -> list[dict[str, object]]:
    return [
        {
            "table_name": profile.table_name,
            "duration_ms": profile.timing.projection_digest_duration_ms,
            "parsed_row_count": profile.parsed_row_count,
            "static_role": profile.static_role,
        }
        for profile in sorted(
            (
                profile
                for profile in profiles
                if profile.materialized
                and profile.timing is not None
                and profile.timing.projection_digest_count
            ),
            key=lambda item: item.timing.projection_digest_duration_ms if item.timing else 0,
            reverse=True,
        )[:limit]
    ]


def _largest_rule_skipped_table_profiles(
    profiles: Sequence[_TableMaterializationProfile],
    *,
    limit: int = 10,
) -> list[dict[str, object]]:
    return [
        {
            "table_name": profile.table_name,
            "parsed_row_count": profile.parsed_row_count,
            "static_role": profile.static_role,
            "duration_ms": profile.total_duration_ms,
        }
        for profile in sorted(
            (
                profile
                for profile in profiles
                if profile.skip_reason == "TABLE_RULE_SKIP"
            ),
            key=lambda item: item.parsed_row_count,
            reverse=True,
        )[:limit]
    ]


def _log_table_materialization_profiles(
    *,
    benchmark_run_id: str | None,
    profiles: Sequence[_TableMaterializationProfile],
    requested_table_count: int,
    parsed_table_count: int,
    materialized_table_count: int,
    skipped_table_count: int,
    rule_skipped_table_count: int,
    materialized_row_count: int,
    rule_skipped_row_count: int,
    parse_skipped_insert_table_count: int,
    parse_skipped_insert_statement_count: int,
    parse_skipped_insert_row_count: int,
    largest_parse_skipped_tables: Sequence[Mapping[str, object]],
    finalize_canonical_digests: bool,
    projection_digest_duration_ms: int,
    projection_digest_table_count: int,
    projection_digest_count: int,
    projection_digest_row_count: int,
    projection_digest_policy: str,
    duration_ms: int,
) -> None:
    if not profiles:
        return
    log_formal_upload_benchmark_event(
        "snapshot_materialize.table_loop_profile_summary",
        benchmark_run_id=benchmark_run_id,
        requested_table_count=requested_table_count,
        parsed_table_count=parsed_table_count,
        materialized_table_count=materialized_table_count,
        skipped_table_count=skipped_table_count,
        rule_skipped_table_count=rule_skipped_table_count,
        materialized_row_count=materialized_row_count,
        rule_skipped_row_count=rule_skipped_row_count,
        parse_skipped_insert_table_count=parse_skipped_insert_table_count,
        parse_skipped_insert_statement_count=parse_skipped_insert_statement_count,
        parse_skipped_insert_row_count=parse_skipped_insert_row_count,
        largest_parse_skipped_tables=list(largest_parse_skipped_tables),
        profile_event_count=len(profiles),
        top_slow_tables=_top_slow_table_profiles(profiles),
        largest_rule_skipped_tables=_largest_rule_skipped_table_profiles(profiles),
        finalize_canonical_digests=finalize_canonical_digests,
        projection_digest_duration_ms=projection_digest_duration_ms,
        projection_digest_table_count=projection_digest_table_count,
        projection_digest_count=projection_digest_count,
        projection_digest_row_count=projection_digest_row_count,
        projection_digest_enabled=projection_digest_policy
        != PROJECTION_DIGEST_POLICY_DISABLED,
        projection_digest_policy=projection_digest_policy,
        duration_ms=duration_ms,
    )
    for profile in profiles:
        log_formal_upload_benchmark_event(
            "snapshot_materialize.table_profile",
            benchmark_run_id=benchmark_run_id,
            **profile.to_payload(),
        )


def _materialize_table(
    bundle: ParsedTableBundle,
    *,
    materialization_input: SnapshotMaterializationInput | _TableMaterializationContext,
    decision: TableHandlingDecision,
    finalize_canonical_digests: bool,
) -> tuple[SnapshotTableDescriptor, SnapshotTable, _TableMaterializationTiming]:
    total_started_at = perf_counter()
    definition = bundle.definition
    compare_key_columns = decision.compare_key_columns
    descriptor_started_at = perf_counter()
    compare_schema_digest = DigestRef.from_payload(
        {
            "table_name": definition.table_name,
            "columns": sorted(column.name for column in definition.columns),
            "compare_key_columns": sorted(
                canonical_identifier(column_name) for column_name in compare_key_columns
            ),
            "table_ruleset_version": materialization_input.table_ruleset_version,
            "scalar_encoding_version": materialization_input.scalar_encoding_version,
            "row_materialization_profile": materialization_input.row_materialization_profile,
        }
    )
    source_ddl_digest = DigestRef.from_bytes(definition.raw_create_sql.encode("utf-8"))
    descriptor = SnapshotTableDescriptor(
        table_name=definition.table_name,
        display_table_name=definition.display_table_name,
        table_role=decision.static_role.value,
        columns=definition.columns,
        compare_key_columns=compare_key_columns,
        row_count=bundle.row_count,
        materialization_stage=SnapshotMaterializationStage.PROVISIONAL.value,
        source_ddl_digest=source_ddl_digest,
        table_raw_sql_digest=bundle.raw_sql_digest,
        fast_row_digest=bundle.fast_row_digest,
        base_table_fingerprint=bundle.raw_sql_digest,
        compare_schema_digest=compare_schema_digest,
        raw_content_digest=None,
        business_content_digest=None,
        table_ruleset_version=materialization_input.table_ruleset_version,
        row_materialization_profile=materialization_input.row_materialization_profile,
        scalar_encoding_version=materialization_input.scalar_encoding_version,
    )
    descriptor_build_duration_ms = benchmark_elapsed_ms(descriptor_started_at)
    reader_started_at = perf_counter()
    reader = LazySnapshotTableReader(
        _descriptor=descriptor,
        _definition=definition,
        _insert_statements=bundle.insert_statements,
    )
    reader_build_duration_ms = benchmark_elapsed_ms(reader_started_at)
    row_finalize_duration_ms: int | None = None
    row_digest_duration_ms: int | None = None
    descriptor_finalize_duration_ms: int | None = None
    projection_digest_duration_ms = 0
    projection_digest_count = 0
    projection_digest_row_count = 0
    projection_digest_enabled = _projection_digest_enabled_for_policy(
        projection_digest_policy=materialization_input.projection_digest_policy,
        finalize_canonical_digests=finalize_canonical_digests,
    )
    if finalize_canonical_digests:
        row_finalize_started_at = perf_counter()
        rows = reader.rows
        row_finalize_duration_ms = benchmark_elapsed_ms(row_finalize_started_at)
        row_digest_started_at = perf_counter()
        raw_content_digest = stable_snapshot_rows_digest(rows, definition.columns)
        row_digest_duration_ms = benchmark_elapsed_ms(row_digest_started_at)
        descriptor_finalize_started_at = perf_counter()
        descriptor = replace(
            descriptor,
            materialization_stage=SnapshotMaterializationStage.FINAL.value,
            raw_content_digest=raw_content_digest,
            business_content_digest=raw_content_digest,
        )
        reader = replace(reader, _descriptor=descriptor, _rows=rows, _content_digest=raw_content_digest)
        descriptor_finalize_duration_ms = benchmark_elapsed_ms(descriptor_finalize_started_at)
    projection_digests: tuple[SnapshotProjectionDigest, ...] = ()
    if projection_digest_enabled:
        projection_digest_started_at = perf_counter()
        projection_digests = _projection_digests_for_materialized_table(
            rows=rows if finalize_canonical_digests else reader.iter_rows(),
            columns=definition.columns,
            table_name=definition.table_name,
            decision=decision,
            table_ruleset_version=materialization_input.table_ruleset_version,
            scalar_encoding_version=materialization_input.scalar_encoding_version,
            digest_authority=(
                SnapshotProjectionDigestAuthority.FINAL
                if finalize_canonical_digests
                else SnapshotProjectionDigestAuthority.PROVISIONAL_FAST
            ),
        )
        projection_digest_duration_ms = benchmark_elapsed_ms(projection_digest_started_at)
        projection_digest_count = len(projection_digests)
        if projection_digests:
            projection_digest_row_count = bundle.row_count
    if projection_digests:
        descriptor = replace(descriptor, projection_digests=projection_digests)
        reader = replace(reader, _descriptor=descriptor)
    table = SnapshotTable(
        descriptor=descriptor,
        reader=reader,
        raw_create_sql=definition.raw_create_sql,
    )
    return (
        descriptor,
        table,
        _TableMaterializationTiming(
            descriptor_build_duration_ms=descriptor_build_duration_ms,
            reader_build_duration_ms=reader_build_duration_ms,
            row_finalize_duration_ms=row_finalize_duration_ms,
            row_digest_duration_ms=row_digest_duration_ms,
            descriptor_finalize_duration_ms=descriptor_finalize_duration_ms,
            projection_digest_duration_ms=projection_digest_duration_ms,
            projection_digest_count=projection_digest_count,
            projection_digest_row_count=projection_digest_row_count,
            projection_digest_enabled=projection_digest_enabled,
            projection_digest_policy=materialization_input.projection_digest_policy,
            total_duration_ms=benchmark_elapsed_ms(total_started_at),
        ),
    )


def _projection_digests_for_materialized_table(
    *,
    rows: Iterable[Sequence[object]],
    columns: Sequence[object],
    table_name: str,
    decision: TableHandlingDecision,
    table_ruleset_version: str,
    scalar_encoding_version: str,
    digest_authority: SnapshotProjectionDigestAuthority,
) -> tuple[SnapshotProjectionDigest, ...]:
    if decision.static_role is not TableStaticRole.STANDARD_DIFF:
        return ()
    if not decision.compare_key_columns:
        return ()
    ignored_columns = frozenset(canonical_identifier(column) for column in decision.ignored_columns)
    selected_column_names = tuple(
        column_name
        for column_name in sorted(canonical_identifier(getattr(column, "name", "")) for column in columns)
        if column_name and column_name not in ignored_columns
    )
    if not selected_column_names:
        return ()
    if not set(decision.compare_key_columns).issubset(set(selected_column_names)):
        return ()
    selected_columns_by_name = {
        canonical_identifier(getattr(column, "name", "")): column
        for column in columns
    }
    selected_columns = tuple(selected_columns_by_name[column_name] for column_name in selected_column_names)
    source_indexes = {
        canonical_identifier(getattr(column, "name", "")): index
        for index, column in enumerate(columns)
    }
    selected_indexes = tuple(source_indexes[column_name] for column_name in selected_column_names)
    projected_rows = tuple(tuple(row[index] for index in selected_indexes) for row in rows)
    projection_schema_digest = build_projection_schema_digest(
        table_name=table_name,
        selected_columns=selected_column_names,
        ignored_columns=tuple(sorted(ignored_columns)),
        effective_compare_key=decision.compare_key_columns,
        table_ruleset_version=table_ruleset_version,
        projection_contract_version=COMPARISON_PROJECTION_CONTRACT_VERSION,
        scalar_encoding_version=scalar_encoding_version,
    )
    digest_parts = build_projection_logical_digest_parts(
        rows=projected_rows,
        columns=selected_columns,
        projection_schema_digest=projection_schema_digest,
        row_identity_columns=decision.compare_key_columns,
        scalar_encoding_version=scalar_encoding_version,
    )
    return (
        SnapshotProjectionDigest(
            projection_schema_digest=projection_schema_digest,
            selected_columns=selected_column_names,
            ignored_columns=tuple(sorted(ignored_columns)),
            effective_compare_key=decision.compare_key_columns,
            row_identity_columns=decision.compare_key_columns,
            row_identity_digest=digest_parts.row_identity_digest,
            projected_row_value_digest=digest_parts.projected_row_value_digest,
            projection_logical_digest=digest_parts.projection_logical_digest,
            table_ruleset_version=table_ruleset_version,
            projection_contract_version=COMPARISON_PROJECTION_CONTRACT_VERSION,
            scalar_encoding_version=scalar_encoding_version,
            digest_authority=digest_authority,
        ),
    )
