"""Canonical surface digest helpers."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef
from gateway_backend.capabilities.surface_assembly.contracts import ComparisonSurface


def artifact_integrity(ref: ArtifactRef) -> dict[str, object]:
    return {"raw_sha256": ref.raw_sha256.value, "size_bytes": ref.size_bytes}


def _optional_artifact_integrity(ref: ArtifactRef | None) -> dict[str, object] | None:
    return None if ref is None else artifact_integrity(ref)


def surface_digest_payload(surface: ComparisonSurface) -> dict[str, object]:
    """Return the semantic surface payload, excluding runtime identity and raw refs."""

    document = surface.to_document()
    document.pop("surface_digest", None)
    document.pop("surface_id", None)
    document.pop("diagnostics", None)
    document["refs"] = {
        "project_identity_assessment": _optional_artifact_integrity(
            surface.refs.project_identity_assessment_ref
        ),
        "records_closure": _optional_artifact_integrity(
            surface.refs.records_closure_ref
        ),
        "risk_annotation_closure": _optional_artifact_integrity(
            surface.refs.risk_annotation_closure_ref
        ),
        "risk_report": _optional_artifact_integrity(surface.refs.risk_report_ref),
    }
    view_document = document["view"]
    if isinstance(view_document, dict):
        view_document.pop("view_id", None)
        view_document.pop("label", None)
        view_document.pop("diagnostics_summary", None)
    summary_document = document["summary"]
    if isinstance(summary_document, dict):
        summary_document["diagnostics_count"] = 0

    table_documents: list[dict[str, object]] = []
    for table in surface.tables:
        table_document = table.to_document()
        table_document.pop("diagnostics", None)
        table_document["table_refs"] = {
            "before_table": _optional_artifact_integrity(
                table.table_refs.before_table_ref
            ),
            "browse_table": _optional_artifact_integrity(
                table.table_refs.browse_table_ref
            ),
            "current_table": _optional_artifact_integrity(
                table.table_refs.current_table_ref
            ),
        }
        table_document["records_refs"] = {
            "records_format": table.records_refs.records_format.value,
            "records": _optional_artifact_integrity(table.records_refs.records_ref),
            "records_manifest": _optional_artifact_integrity(
                table.records_refs.records_manifest_ref
            ),
        }
        table_document["risk_refs"] = {
            "annotation_count": table.risk_refs.annotation_count,
            "annotation": _optional_artifact_integrity(
                table.risk_refs.annotation_ref
            ),
            "annotation_manifest": _optional_artifact_integrity(
                table.risk_refs.annotation_manifest_ref
            ),
            "reason_codes": [item.value for item in table.risk_refs.reason_codes],
            "report": _optional_artifact_integrity(table.risk_refs.report_ref),
            "risk_level": None
            if table.risk_refs.risk_level is None
            else table.risk_refs.risk_level.value,
        }
        table_document["ordered_extension"] = _ordered_digest_payload(
            table.ordered_extension
        )
        table_documents.append(table_document)
    document.pop("tables", None)
    document["_tables"] = table_documents

    document["projections"] = [
        {
            **projection.to_document(),
            "diagnostics_ref": None,
            "projection_ref": artifact_integrity(projection.projection_ref),
            "risk_summary_ref": _optional_artifact_integrity(
                projection.risk_summary_ref
            ),
        }
        for projection in surface.projections
    ]
    return document


def compute_surface_digest(surface: ComparisonSurface) -> DigestRef:
    return raw_blob_digest(canonicalize_json_value(surface_digest_payload(surface)))


def _ordered_digest_payload(
    value: dict[str, object] | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        key: artifact_integrity(item)
        if key.endswith("_ref") and isinstance(item, ArtifactRef)
        else item
        for key, item in value.items()
    }
