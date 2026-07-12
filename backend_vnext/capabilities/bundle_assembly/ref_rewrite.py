from __future__ import annotations

from dataclasses import replace

from ..surface_assembly.models import (
    ComparisonSurface,
    SurfaceOrderedExtension,
    SurfaceProjectionRef,
    SurfaceRecordsRefs,
    SurfaceRefs,
    SurfaceRiskRefs,
    SurfaceTable,
    SurfaceTableRefs,
)


def rewrite_surface_for_bundle(surface: ComparisonSurface, pair_id: str) -> ComparisonSurface:
    pair_prefix = f"pairs/{pair_id}"
    rewritten_tables = tuple(_rewrite_table(table, pair_prefix) for table in surface.tables)
    rewritten_projections = tuple(
        _rewrite_projection(projection, pair_prefix)
        for projection in surface.projections
    )
    rewritten_refs = _rewrite_surface_refs(surface.refs, pair_prefix)
    rewritten_surface = replace(
        surface,
        surface_id=surface.surface_id,
        refs=rewritten_refs,
        tables=rewritten_tables,
        projections=rewritten_projections,
    )
    return rewritten_surface


def _rewrite_surface_refs(refs: SurfaceRefs, pair_prefix: str) -> SurfaceRefs:
    return replace(
        refs,
        surface_ref=f"{pair_prefix}/{refs.surface_ref}",
        records_closure_ref=_prefix_ref(pair_prefix, refs.records_closure_ref),
        risk_report_ref=_prefix_ref(pair_prefix, refs.risk_report_ref),
        risk_annotation_closure_ref=_prefix_ref(pair_prefix, refs.risk_annotation_closure_ref),
        diagnostics_refs=tuple(_prefix_ref(pair_prefix, ref) for ref in refs.diagnostics_refs),
    )


def _rewrite_table(table: SurfaceTable, pair_prefix: str) -> SurfaceTable:
    rewritten_table_refs = replace(
        table.table_refs,
        before_table_ref=_prefix_ref(pair_prefix, table.table_refs.before_table_ref),
        current_table_ref=_prefix_ref(pair_prefix, table.table_refs.current_table_ref),
        browse_table_ref=_prefix_ref(pair_prefix, table.table_refs.browse_table_ref),
    )
    rewritten_records_refs = replace(
        table.records_refs,
        records_ref=_prefix_ref(pair_prefix, table.records_refs.records_ref),
        records_manifest_ref=_prefix_ref(pair_prefix, table.records_refs.records_manifest_ref),
    )
    rewritten_risk_refs = replace(
        table.risk_refs,
        report_ref=_prefix_ref(pair_prefix, table.risk_refs.report_ref),
        annotation_ref=_prefix_ref(pair_prefix, table.risk_refs.annotation_ref),
        annotation_manifest_ref=_prefix_ref(pair_prefix, table.risk_refs.annotation_manifest_ref),
    )
    rewritten_ordered_extension = table.ordered_extension
    if rewritten_ordered_extension is not None:
        rewritten_ordered_extension = replace(
            rewritten_ordered_extension,
            ordered_records_ref=_prefix_ref(pair_prefix, rewritten_ordered_extension.ordered_records_ref),
            ordered_records_manifest_ref=_prefix_ref(
                pair_prefix,
                rewritten_ordered_extension.ordered_records_manifest_ref,
            ),
        )
    return replace(
        table,
        table_refs=rewritten_table_refs,
        records_refs=rewritten_records_refs,
        risk_refs=rewritten_risk_refs,
        ordered_extension=rewritten_ordered_extension,
    )


def _rewrite_projection(projection: SurfaceProjectionRef, pair_prefix: str) -> SurfaceProjectionRef:
    return replace(
        projection,
        projection_ref=_prefix_ref(pair_prefix, projection.projection_ref),
        risk_summary_ref=_prefix_ref(pair_prefix, projection.risk_summary_ref),
        diagnostics_ref=_prefix_ref(pair_prefix, projection.diagnostics_ref),
    )


def _prefix_ref(prefix: str, ref: str | None) -> str | None:
    if ref is None:
        return None
    if ref.startswith(f"{prefix}/"):
        return ref
    return f"{prefix}/{ref}"
