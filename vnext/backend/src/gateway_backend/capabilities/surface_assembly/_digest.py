"""Canonical surface digest helpers."""

from __future__ import annotations

from collections.abc import Iterable

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef
from gateway_backend.capabilities.surface_assembly.contracts import ComparisonSurface


def artifact_integrity(ref: ArtifactRef) -> dict[str, object]:
    return {"raw_sha256": ref.raw_sha256.value, "size_bytes": ref.size_bytes}


def surface_digest_payload(surface: ComparisonSurface) -> dict[str, object]:
    """Return the semantic surface payload, excluding runtime identity and raw refs."""

    document = surface.to_document()
    document.pop("surface_digest", None)
    document.pop("surface_id", None)
    document.pop("diagnostics", None)
    document["refs"] = None
    view_document = document["view"]
    if isinstance(view_document, dict):
        view_document.pop("view_id", None)
        view_document.pop("label", None)
        view_document.pop("diagnostics_summary", None)
    summary_document = document["summary"]
    if isinstance(summary_document, dict):
        summary_document["diagnostics_count"] = 0

    table_integrities: list[dict[str, object]] = []
    table_documents: list[dict[str, object]] = []
    for table in surface.tables:
        table_document = table.to_document()
        table_document.pop("diagnostics", None)
        table_document["table_refs"] = None
        table_document["records_refs"] = {
            "records_format": table.records_refs.records_format.value,
        }
        table_document["risk_refs"] = {
            "annotation_count": table.risk_refs.annotation_count,
            "reason_codes": [item.value for item in table.risk_refs.reason_codes],
            "risk_level": None
            if table.risk_refs.risk_level is None
            else table.risk_refs.risk_level.value,
        }
        current_table_integrities = [artifact_integrity(ref) for ref in _table_refs(table)]
        table_document["ordered_extension"] = _without_ordered_refs(table.ordered_extension)
        current_table_integrities.extend(
            artifact_integrity(ref)
            for ref in (
                table.risk_refs.report_ref,
                table.risk_refs.annotation_ref,
                table.risk_refs.annotation_manifest_ref,
                table.diagnostics.diagnostics_ref,
            )
            if ref is not None
        )
        table_document["_artifact_integrities"] = tuple(
            sorted(
                (item["raw_sha256"], item["size_bytes"])
                for item in current_table_integrities
            )
        )
        table_integrities.extend(current_table_integrities)
        table_documents.append(table_document)
    document.pop("tables", None)
    document["_tables"] = table_documents

    root_refs = [
        surface.refs.records_closure_ref,
        surface.refs.risk_report_ref,
        surface.refs.risk_annotation_closure_ref,
        surface.refs.project_identity_assessment_ref,
        surface.refs.diagnostics_ref,
    ]
    root_refs.extend(
        ref
        for projection in surface.projections
        for ref in (
            projection.projection_ref,
            projection.risk_summary_ref,
            projection.diagnostics_ref,
        )
        if ref is not None
    )
    document["_artifact_integrities"] = tuple(
        sorted(
            (item["raw_sha256"], item["size_bytes"])
            for item in (
                [artifact_integrity(ref) for ref in root_refs if ref is not None]
                + table_integrities
            )
        )
    )
    return document


def compute_surface_digest(surface: ComparisonSurface) -> DigestRef:
    return raw_blob_digest(canonicalize_json_value(surface_digest_payload(surface)))


def _table_refs(table: object) -> Iterable[ArtifactRef]:
    table_refs = table.table_refs  # type: ignore[attr-defined]
    records_refs = table.records_refs  # type: ignore[attr-defined]
    refs = [
        ref
        for ref in (
            table_refs.before_table_ref,
            table_refs.current_table_ref,
            table_refs.browse_table_ref,
            records_refs.records_ref,
            records_refs.records_manifest_ref,
        )
        if ref is not None
    ]
    ordered_extension = table.ordered_extension  # type: ignore[attr-defined]
    if ordered_extension is not None:
        refs.extend(
            value
            for key, value in ordered_extension.items()
            if key.endswith("_ref") and isinstance(value, ArtifactRef)
        )
    return tuple(refs)


def _without_ordered_refs(value: dict[str, object] | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        key: item
        for key, item in value.items()
        if key not in {"ordered_records_ref", "ordered_records_manifest_ref"}
    }
