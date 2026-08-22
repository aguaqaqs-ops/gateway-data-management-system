"""Public Surface v2 contract tests."""

from __future__ import annotations

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts import ArtifactRef
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonMode,
    ComparisonFacts,
    ComparisonSummary,
    ComparisonTableFact,
    ComparisonTableStatus,
    IdentityStatus,
    PairResultStatus,
)
from gateway_backend.capabilities.surface_assembly import (
    SURFACE_CONTRACT_VERSION,
    SurfaceAssemblyInput,
    SurfaceChangeKind,
    SurfaceColumn,
    SurfaceCompare,
    SurfaceDiagnostics,
    SurfaceDisplay,
    SurfaceDisplayStrategy,
    SurfaceReplayGuarantee,
    SurfaceRecordsFormat,
    SurfaceRecordsRefs,
    SurfaceRiskRefs,
    SurfaceRowChangeStats,
    SurfaceTable,
    SurfaceTableProcessingMode,
    SurfaceTableRefs,
)


def _digest(seed: str) -> DigestRef:
    return raw_blob_digest(seed.encode())


def _ref(name: str) -> ArtifactRef:
    raw = name.encode()
    return ArtifactRef(
        artifact_id=name,
        media_type="application/json",
        size_bytes=len(raw),
        raw_sha256=raw_blob_digest(raw),
    )


def _facts() -> ComparisonFacts:
    table = ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.UNCHANGED)
    summary = ComparisonSummary(
        status=PairResultStatus.UNCHANGED,
        table_count=1,
        unchanged_table_count=1,
        changed_table_count=0,
        added_table_count=0,
        deleted_table_count=0,
        schema_changed_table_count=0,
        degraded_table_count=0,
        row_added_count=0,
        row_deleted_count=0,
        row_modified_count=0,
        suppressed_added_count=0,
        suppressed_deleted_count=0,
        diagnostics_count=0,
    )
    return ComparisonFacts(
        comparison_digest=_digest("comparison"),
        facts_core_digest=_digest("facts-core"),
        comparison_contract_version="backend-vnext/comparison/v2",
        projection_contract_version="backend-vnext/comparison-projection/v1",
        scalar_encoding_version=1,
        before_snapshot_digest=_digest("before"),
        current_snapshot_digest=_digest("current"),
        comparison_mode=ComparisonMode.DETAILED,
        project_identity_status=IdentityStatus.NOT_APPLICABLE,
        assessment_digest=None,
        direction="BEFORE_TO_CURRENT",
        summary=summary,
        tables=(table,),
    )


def test_surface_contract_is_v2_and_does_not_inline_rows() -> None:
    table = SurfaceTable(
        table_id="orders",
        table_name="orders",
        display_name="Orders",
        table_status=ComparisonTableStatus.UNCHANGED,
        change_kind=SurfaceChangeKind.UNCHANGED,
        row_change_stats=SurfaceRowChangeStats(),
        schema_summary=None,
        columns=(SurfaceColumn("id", "ID", "INT", False),),
        table_refs=SurfaceTableRefs(),
        records_refs=SurfaceRecordsRefs(records_format=SurfaceRecordsFormat.INLINE_SUMMARY),
        risk_refs=SurfaceRiskRefs(),
        display=SurfaceDisplay(
            SurfaceDisplayStrategy.SUMMARY_ONLY,
            SurfaceTableProcessingMode.STANDARD,
            SurfaceReplayGuarantee.SUMMARY_ONLY,
        ),
        compare=SurfaceCompare(None, (), (), ()),
        diagnostics=SurfaceDiagnostics(),
    )
    assert SURFACE_CONTRACT_VERSION.endswith("/v2")
    document = table.to_document()
    assert "before_values" not in str(document)
    assert "current_values" not in str(document)


def test_surface_input_rejects_host_path_identity() -> None:
    facts = _facts()
    with pytest.raises(ValueError, match="host path"):
        SurfaceAssemblyInput(
            comparison_facts=facts,
            surface_id="/tmp/surface",
            view_id="view",
            before_role="before",
            current_role="current",
        )


def test_surface_table_rejects_mismatched_record_refs() -> None:
    with pytest.raises(ValueError, match="provided together"):
        SurfaceRecordsRefs(records_ref=_ref("records"))
