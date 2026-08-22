"""Surface ref validation and immutable ref rewriting."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from gateway_backend.artifacts import ArtifactRef, assert_no_host_path_identity
from gateway_backend.capabilities.surface_assembly.contracts import (
    ComparisonSurface,
    SurfaceDiagnostics,
    SurfaceRiskRefs,
    SurfaceTable,
    SurfaceTableRefs,
)


_RESERVED_REF_PREFIXES = (
    "cache-",
    "cache:",
    "dolt-",
    "dolt:",
    "repository-",
    "repository:",
    "preview-",
    "preview:",
    "submit-",
    "submit:",
    "workspace-",
    "workspace:",
    "history-",
    "history:",
)


def validate_surface_ref(ref: ArtifactRef, *, label: str = "surface ref") -> None:
    if type(ref) is not ArtifactRef:
        raise ValueError(f"{label} must be ArtifactRef")
    assert_no_host_path_identity(ref.artifact_id, label=label)
    lowered = ref.artifact_id.casefold()
    if lowered.startswith(_RESERVED_REF_PREFIXES):
        raise ValueError(f"{label} must not use cache, repository or flow-local identity")


def rewrite_surface_refs(
    surface: ComparisonSurface,
    replacements: Mapping[ArtifactRef, ArtifactRef],
) -> ComparisonSurface:
    if type(surface) is not ComparisonSurface:
        raise TypeError("surface must be ComparisonSurface")
    if not isinstance(replacements, Mapping):
        raise TypeError("replacements must be a mapping")
    for old, new in replacements.items():
        validate_surface_ref(old, label="replacement source")
        validate_surface_ref(new, label="replacement target")

    def rewrite(ref: ArtifactRef | None) -> ArtifactRef | None:
        return None if ref is None else replacements.get(ref, ref)

    def rewrite_required(ref: ArtifactRef) -> ArtifactRef:
        value = rewrite(ref)
        assert value is not None
        return value

    def rewrite_table_refs(refs: SurfaceTableRefs) -> SurfaceTableRefs:
        return replace(
            refs,
            before_table_ref=rewrite(refs.before_table_ref),
            current_table_ref=rewrite(refs.current_table_ref),
            browse_table_ref=rewrite(refs.browse_table_ref),
        )

    def rewrite_risk_refs(refs: SurfaceRiskRefs) -> SurfaceRiskRefs:
        return replace(
            refs,
            report_ref=rewrite(refs.report_ref),
            annotation_ref=rewrite(refs.annotation_ref),
            annotation_manifest_ref=rewrite(refs.annotation_manifest_ref),
        )

    def rewrite_diagnostics(value: SurfaceDiagnostics) -> SurfaceDiagnostics:
        return replace(value, diagnostics_ref=rewrite(value.diagnostics_ref))

    def rewrite_table(table: SurfaceTable) -> SurfaceTable:
        ordered = table.ordered_extension
        if ordered is not None:
            ordered = {
                **ordered,
                "ordered_records_ref": rewrite(
                    cast(ArtifactRef | None, ordered.get("ordered_records_ref"))
                ),
                "ordered_records_manifest_ref": rewrite(
                    cast(ArtifactRef | None, ordered.get("ordered_records_manifest_ref"))
                ),
            }
            ordered = {
                key: value
                for key, value in ordered.items()
                if value is not None or key not in {"ordered_records_ref", "ordered_records_manifest_ref"}
            }
        return replace(
            table,
            table_refs=rewrite_table_refs(table.table_refs),
            records_refs=replace(
                table.records_refs,
                records_ref=rewrite(table.records_refs.records_ref),
                records_manifest_ref=rewrite(table.records_refs.records_manifest_ref),
            ),
            risk_refs=rewrite_risk_refs(table.risk_refs),
            diagnostics=rewrite_diagnostics(table.diagnostics),
            ordered_extension=ordered,
        )

    rewritten = replace(
        surface,
        tables=tuple(rewrite_table(item) for item in surface.tables),
        projections=tuple(
            replace(
                item,
                projection_ref=rewrite_required(item.projection_ref),
                risk_summary_ref=rewrite(item.risk_summary_ref),
                diagnostics_ref=rewrite(item.diagnostics_ref),
            )
            for item in surface.projections
        ),
        refs=replace(
            surface.refs,
            records_closure_ref=rewrite(surface.refs.records_closure_ref),
            risk_report_ref=rewrite(surface.refs.risk_report_ref),
            risk_annotation_closure_ref=rewrite(surface.refs.risk_annotation_closure_ref),
            project_identity_assessment_ref=rewrite(surface.refs.project_identity_assessment_ref),
            diagnostics_ref=rewrite(surface.refs.diagnostics_ref),
        ),
    )
    validate_surface_refs(rewritten)
    return rewritten


def validate_surface_refs(surface: ComparisonSurface) -> None:
    refs: list[ArtifactRef] = []
    refs.extend(
        ref
        for ref in (
            surface.refs.records_closure_ref,
            surface.refs.risk_report_ref,
            surface.refs.risk_annotation_closure_ref,
            surface.refs.project_identity_assessment_ref,
            surface.refs.diagnostics_ref,
        )
        if ref is not None
    )
    refs.extend(
        ref
        for table in surface.tables
        for ref in (
            table.table_refs.before_table_ref,
            table.table_refs.current_table_ref,
            table.table_refs.browse_table_ref,
            table.records_refs.records_ref,
            table.records_refs.records_manifest_ref,
            table.risk_refs.report_ref,
            table.risk_refs.annotation_ref,
            table.risk_refs.annotation_manifest_ref,
            table.diagnostics.diagnostics_ref,
        )
        if ref is not None
    )
    refs.extend(
        ref
        for projection in surface.projections
        for ref in (
            projection.projection_ref,
            projection.risk_summary_ref,
            projection.diagnostics_ref,
        )
        if ref is not None
    )
    for ref in refs:
        validate_surface_ref(ref)
    for table in surface.tables:
        if table.ordered_extension is not None:
            for key in ("ordered_records_ref", "ordered_records_manifest_ref"):
                ordered_value = table.ordered_extension.get(key)
                if ordered_value is not None:
                    validate_surface_ref(cast(ArtifactRef, ordered_value), label=key)
