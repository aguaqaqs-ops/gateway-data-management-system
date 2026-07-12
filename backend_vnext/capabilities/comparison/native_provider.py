from __future__ import annotations

from collections.abc import Callable

from ...artifacts import LocalArtifactStore
from ...contracts.versions import ROW_MATERIALIZATION_PROFILE
from ...core.diagnostics import DiagnosticRecord
from ...core.digests import DigestRef
from ...core.identifiers import canonical_identifier
from ...core.row_digests import stable_rows_digest
from ...repository_server import (
    RepositoryNativeDiffRequest,
    RepositoryRef,
    RepositoryTableCatalogTable,
    SessionPairRepositoryNativeDiffAccess,
)
from ..snapshot_materialization.models import SnapshotTable, SnapshotTableColumn, SnapshotTableDescriptor
from ..snapshot_materialization.readers import InMemorySnapshotTableReader
from .models import ComparisonComputeInput, ComparisonInput, RepositoryBackedComparisonContext


def compare_dolt_native_table(
    *,
    comparison_engine: object,
    table_name: str,
    table_rule: object | None,
    selector_kind: str,
    before_descriptor: SnapshotTableDescriptor | None,
    current_descriptor: SnapshotTableDescriptor | None,
    before_table: object | None,
    current_table: object | None,
    compute_input: ComparisonComputeInput,
    table_ruleset_version: str,
    records_store: LocalArtifactStore | None,
    cache_diagnostics: list[DiagnosticRecord],
    self_project_fn: Callable[..., object],
    compare_projected_pair_fn: Callable[..., object],
    compare_single_side_fn: Callable[..., object],
    diagnostics: list[DiagnosticRecord],
    table_schema: object,
    schema_changed: bool,
    schema_only_changed: bool,
    key_changed: bool,
) -> object | None:
    del selector_kind
    if not getattr(table_schema, "effective_compare_key", ()):
        return None
    before_context = compute_input.before.repository_backed_context
    current_context = compute_input.current.repository_backed_context
    if before_context is None or current_context is None:
        _append_dolt_native_fallback_diagnostic(
            diagnostics,
            table_name=table_name,
            reason="DOLT_NATIVE_PAIR_CONTEXT_MISSING",
        )
        return None
    before_reference = _native_repository_ref_for_input(compute_input.before, before_context)
    current_reference = _native_repository_ref_for_input(compute_input.current, current_context)
    if before_reference is None or current_reference is None:
        _append_dolt_native_fallback_diagnostic(
            diagnostics,
            table_name=table_name,
            reason="DOLT_NATIVE_PAIR_CONTEXT_MISSING",
        )
        return None

    before_provider = before_context.repository_table_access_provider
    current_provider = current_context.repository_table_access_provider
    if before_provider is None or current_provider is None:
        _append_dolt_native_fallback_diagnostic(
            diagnostics,
            table_name=table_name,
            reason="DOLT_NATIVE_PAIR_CONTEXT_MISSING",
        )
        return None

    before_session = None
    current_session = None
    try:
        before_session = before_provider.open_ref(before_reference)
        current_session = current_provider.open_ref(current_reference)
        native_result = SessionPairRepositoryNativeDiffAccess().diff_table(
            before_session,
            current_session,
            table_name,
            RepositoryNativeDiffRequest(include_rows=True),
        )
    except Exception as exc:
        _append_dolt_native_fallback_diagnostic(
            diagnostics,
            table_name=table_name,
            reason="DOLT_NATIVE_TABLE_RAW_DIFF_UNAVAILABLE",
            error=str(exc),
        )
        return None
    finally:
        if before_session is not None:
            before_session.close()
        if current_session is not None:
            current_session.close()

    if native_result.status.value == "TABLE_UNSUPPORTED":
        _append_dolt_native_fallback_diagnostic(
            diagnostics,
            table_name=table_name,
            reason="DOLT_NATIVE_TABLE_RAW_DIFF_UNAVAILABLE",
            status=native_result.status.value,
        )
        return None

    native_before_table = _native_snapshot_table(
        catalog_table=native_result.before_table,
        rows=native_result.before_rows,
        table_ruleset_version=table_ruleset_version,
        scalar_encoding_version=compute_input.scalar_encoding_version or "",
    )
    native_current_table = _native_snapshot_table(
        catalog_table=native_result.current_table,
        rows=native_result.current_rows,
        table_ruleset_version=table_ruleset_version,
        scalar_encoding_version=compute_input.scalar_encoding_version or "",
    )

    if native_before_table is None and native_current_table is None:
        _append_dolt_native_fallback_diagnostic(
            diagnostics,
            table_name=table_name,
            reason="DOLT_NATIVE_TABLE_RAW_DIFF_UNAVAILABLE",
        )
        return None
    if native_before_table is not None and before_descriptor is None:
        _append_dolt_native_fallback_diagnostic(
            diagnostics,
            table_name=table_name,
            reason="DOLT_NATIVE_TABLE_CANONICALIZATION_FAILED",
        )
        return None
    if native_current_table is not None and current_descriptor is None:
        _append_dolt_native_fallback_diagnostic(
            diagnostics,
            table_name=table_name,
            reason="DOLT_NATIVE_TABLE_CANONICALIZATION_FAILED",
        )
        return None

    if native_before_table is not None and native_current_table is not None:
        before_projection = self_project_fn(
            table=native_before_table,
            source_snapshot_digest=compute_input.before.snapshot.snapshot_digest,
            projection_schema=table_schema,
            projection_builder=comparison_engine.projection_builder,
            projection_table_cache=comparison_engine.projection_table_cache,
            cache_diagnostics=cache_diagnostics,
        )
        current_projection = self_project_fn(
            table=native_current_table,
            source_snapshot_digest=compute_input.current.snapshot.snapshot_digest,
            projection_schema=table_schema,
            projection_builder=comparison_engine.projection_builder,
            projection_table_cache=comparison_engine.projection_table_cache,
            cache_diagnostics=cache_diagnostics,
        )
        return compare_projected_pair_fn(
            table_name=table_name,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            before_projection=before_projection,
            current_projection=current_projection,
            projection_schema=table_schema,
            comparison_input=compute_input,
            table_ruleset_version=table_ruleset_version,
            records_store=records_store,
            diagnostics=diagnostics,
            table_rule=table_rule,
            schema_only_changed=schema_only_changed,
            schema_changed=schema_changed,
            key_changed=key_changed,
        )

    if native_before_table is not None:
        before_projection = self_project_fn(
            table=native_before_table,
            source_snapshot_digest=compute_input.before.snapshot.snapshot_digest,
            projection_schema=table_schema,
            projection_builder=comparison_engine.projection_builder,
            projection_table_cache=comparison_engine.projection_table_cache,
            cache_diagnostics=cache_diagnostics,
        )
        return compare_single_side_fn(
            table_name=table_name,
            side="before",
            projection=before_projection,
            descriptor=before_descriptor,
            projection_schema=table_schema,
            comparison_input=compute_input,
            table_ruleset_version=table_ruleset_version,
            records_store=records_store,
            diagnostics=diagnostics,
        )

    if native_current_table is not None:
        current_projection = self_project_fn(
            table=native_current_table,
            source_snapshot_digest=compute_input.current.snapshot.snapshot_digest,
            projection_schema=table_schema,
            projection_builder=comparison_engine.projection_builder,
            projection_table_cache=comparison_engine.projection_table_cache,
            cache_diagnostics=cache_diagnostics,
        )
        return compare_single_side_fn(
            table_name=table_name,
            side="current",
            projection=current_projection,
            descriptor=current_descriptor,
            projection_schema=table_schema,
            comparison_input=compute_input,
            table_ruleset_version=table_ruleset_version,
            records_store=records_store,
            diagnostics=diagnostics,
        )

    _append_dolt_native_fallback_diagnostic(
        diagnostics,
        table_name=table_name,
        reason="DOLT_NATIVE_TABLE_CANONICALIZATION_FAILED",
    )
    return None


def _append_dolt_native_fallback_diagnostic(
    diagnostics: list[DiagnosticRecord],
    *,
    table_name: str,
    reason: str,
    error: str | None = None,
    status: str | None = None,
) -> None:
    details: dict[str, object] = {
        "table_name": table_name,
        "reason": reason,
    }
    if error is not None:
        details["error"] = error
    if status is not None:
        details["status"] = status
    diagnostics.append(
        DiagnosticRecord(
            code="comparison.dolt-native.fallback",
            message="dolt native provider fell back to snapshot comparison",
            phase="compare",
            severity="WARNING",
            details=details,
        )
    )


def _native_repository_ref_for_input(
    comparison_input: ComparisonInput,
    context: RepositoryBackedComparisonContext,
) -> RepositoryRef | None:
    repository_id = comparison_input.snapshot.repository_id
    if repository_id is None and context.repository_id:
        repository_id = context.repository_id
    repository_ref = context.resolved_commit_hash
    if repository_id is None or repository_ref is None:
        return None
    if context.repository_id != repository_id:
        return None
    return RepositoryRef(repository_id=repository_id, repository_ref=repository_ref)


def _native_snapshot_table(
    *,
    catalog_table: RepositoryTableCatalogTable | None,
    rows: tuple[tuple[object | None, ...], ...] | None,
    table_ruleset_version: str,
    scalar_encoding_version: str,
) -> SnapshotTable | None:
    if catalog_table is None or rows is None:
        return None
    normalized_rows = tuple(tuple(row) for row in rows)
    descriptor = _native_snapshot_descriptor(
        catalog_table=catalog_table,
        rows=normalized_rows,
        table_ruleset_version=table_ruleset_version,
        scalar_encoding_version=scalar_encoding_version,
    )
    return SnapshotTable(
        descriptor=descriptor,
        reader=InMemorySnapshotTableReader(
            _descriptor=descriptor,
            _rows=normalized_rows,
        ),
        raw_create_sql=_render_repository_table_create_sql(catalog_table),
    )


def _native_snapshot_descriptor(
    *,
    catalog_table: RepositoryTableCatalogTable,
    rows: tuple[tuple[object | None, ...], ...],
    table_ruleset_version: str,
    scalar_encoding_version: str,
) -> SnapshotTableDescriptor:
    snapshot_columns = tuple(
        SnapshotTableColumn(
            name=column.name,
            display_name=column.display_name,
            scalar_type=column.scalar_type,
            nullable=column.nullable,
        )
        for column in catalog_table.columns
    )
    raw_create_sql = _render_repository_table_create_sql(catalog_table)
    source_ddl_digest = DigestRef.from_bytes(raw_create_sql.encode("utf-8"))
    compare_schema_digest = DigestRef.from_payload(
        {
            "table_name": canonical_identifier(catalog_table.table_name),
            "columns": sorted(column.name for column in snapshot_columns),
            "compare_key_columns": sorted(
                canonical_identifier(column_name)
                for column_name in catalog_table.primary_key_columns
            ),
            "table_ruleset_version": table_ruleset_version,
            "scalar_encoding_version": scalar_encoding_version,
            "row_materialization_profile": ROW_MATERIALIZATION_PROFILE,
        }
    )
    raw_content_digest = stable_rows_digest(rows, tuple(column.name for column in snapshot_columns))
    return SnapshotTableDescriptor(
        table_name=canonical_identifier(catalog_table.table_name),
        display_table_name=catalog_table.display_table_name,
        columns=snapshot_columns,
        compare_key_columns=tuple(
            canonical_identifier(column_name) for column_name in catalog_table.primary_key_columns
        ),
        row_count=len(rows),
        source_ddl_digest=source_ddl_digest,
        table_raw_sql_digest=source_ddl_digest,
        base_table_fingerprint=source_ddl_digest,
        compare_schema_digest=compare_schema_digest,
        raw_content_digest=raw_content_digest,
        business_content_digest=raw_content_digest,
        table_ruleset_version=table_ruleset_version,
        row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        scalar_encoding_version=scalar_encoding_version,
    )


def _render_repository_table_create_sql(
    catalog_table: RepositoryTableCatalogTable,
) -> str:
    column_lines: list[str] = []
    for column in catalog_table.columns:
        column_type = column.scalar_type or column.raw_type or "TEXT"
        column_line = f"`{canonical_identifier(column.name)}` {column_type}"
        if column.nullable is False:
            column_line += " NOT NULL"
        elif column.nullable is True:
            column_line += " DEFAULT NULL"
        column_lines.append(column_line)
    if catalog_table.primary_key_columns:
        primary_key_columns = ", ".join(
            f"`{canonical_identifier(column_name)}`"
            for column_name in catalog_table.primary_key_columns
        )
        column_lines.append(f"PRIMARY KEY ({primary_key_columns})")
    return (
        f"CREATE TABLE `{canonical_identifier(catalog_table.table_name)}` (\n  "
        + ",\n  ".join(column_lines)
        + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8"
    )
