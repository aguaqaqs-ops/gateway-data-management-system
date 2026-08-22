"""Bundle ref validation and Surface ref collection."""

from __future__ import annotations

from collections.abc import Iterable

from gateway_backend.artifacts import ArtifactRef, assert_no_host_path_identity
from gateway_backend.capabilities.surface_assembly.contracts import ComparisonSurface

_RESERVED_REF_PREFIXES = (
    "cache-",
    "cache:",
    "dolt-",
    "dolt:",
    "repository-",
    "repository:",
    "repo-",
    "repo:",
    "preview-",
    "preview:",
    "submit-",
    "submit:",
    "workspace-",
    "workspace:",
    "history-",
    "history:",
    "flow-",
    "flow:",
    "operation-",
    "operation:",
)


def validate_bundle_ref(ref: ArtifactRef, *, label: str = "bundle ref") -> None:
    if type(ref) is not ArtifactRef:
        raise ValueError(f"{label} must be ArtifactRef")
    assert_no_host_path_identity(ref.artifact_id, label=label)
    lowered = ref.artifact_id.casefold()
    if lowered.startswith(_RESERVED_REF_PREFIXES):
        raise ValueError(f"{label} must not use cache, repository or flow-local identity")


def _surface_refs(surface: ComparisonSurface) -> tuple[ArtifactRef, ...]:
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
    for table in surface.tables:
        refs.extend(
            ref
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
        if table.ordered_extension is not None:
            refs.extend(
                value
                for key, value in table.ordered_extension.items()
                if key.endswith("_ref") and isinstance(value, ArtifactRef)
            )
    for projection in surface.projections:
        refs.extend(
            ref
            for ref in (
                projection.projection_ref,
                projection.risk_summary_ref,
                projection.diagnostics_ref,
            )
            if ref is not None
        )
    return tuple(refs)


def collect_surface_refs(surface: ComparisonSurface) -> tuple[ArtifactRef, ...]:
    if type(surface) is not ComparisonSurface:
        raise TypeError("surface must be ComparisonSurface")
    refs = _surface_refs(surface)
    for ref in refs:
        validate_bundle_ref(ref)
    if len(set(refs)) != len(refs):
        # The same opaque ref may intentionally be used by two surface fields, so uniqueness is
        # not a surface invariant. Keep the first occurrence order for deterministic callers.
        return tuple(dict.fromkeys(refs))
    return refs


def validate_bundle_refs(refs: Iterable[ArtifactRef]) -> None:
    for ref in refs:
        validate_bundle_ref(ref)
