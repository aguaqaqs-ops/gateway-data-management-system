"""Deterministic Surface Assembly behavior tests."""

from __future__ import annotations

from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts import ArtifactRef
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonFacts,
    ComparisonMode,
    ComparisonRecordsClosure,
    ComparisonSchemaChanges,
    ComparisonSummary,
    ComparisonTableFact,
    ComparisonTableStatus,
    PairResultStatus,
    RecordsArtifactFamily,
    RecordsClosureEntry,
    SchemaEvolution,
)
from gateway_backend.capabilities.risk_evaluation.contracts import (
    RISK_CONTRACT_VERSION,
    RiskLevel,
    RiskReasonCode,
    RiskReport,
    RiskSummary,
    RiskTableRisk,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationStage,
    SnapshotColumnDescriptor,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.surface_assembly.contracts import SurfaceTable
from gateway_backend.capabilities.surface_assembly import (
    SURFACE_CONTRACT_VERSION,
    SurfaceArtifactIndexEntry,
    SurfaceAssemblyContext,
    SurfaceAssemblyInput,
    SurfaceAssemblyPolicy,
    SurfaceAssemblyStatus,
    SurfaceChangeKind,
    SurfaceDisplayStrategy,
    SurfaceIdentityAnnotation,
    SurfaceRecordsFormat,
    SurfaceRefScope,
    SurfaceTableProcessingMode,
    SurfaceTableRefs,
    SurfaceTableContentBindings,
    TableContentBinding,
    assemble_surface,
    compute_surface_digest,
    rewrite_surface_refs,
    validate_surface,
)

from tests.support.artifact_ref_faults import UNSUPPORTED_DELIVERY_ARTIFACT_IDS
from tests.support.surface_navigation import NAVIGATION_PROJECTION

_S1B_GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "golden"
    / "surface"
    / "s1b"
    / "table-presentation.json"
)


def _s1b_surface_golden_case(name: str) -> dict[str, object]:
    document = json.loads(_S1B_GOLDEN.read_text(encoding="utf-8"))
    assert document["contract_version"] == SURFACE_CONTRACT_VERSION
    cases = document["cases"]
    assert type(cases) is dict
    case = cases[name]
    assert type(case) is dict
    return cast(dict[str, object], case)


def _s1b_surface_projection(table: SurfaceTable) -> dict[str, object]:
    schema = table.schema_summary
    stats = table.row_change_stats
    refs = table.table_refs
    records = table.records_refs
    return {
        "table_status": table.table_status.value,
        "change_kind": table.change_kind.value,
        "display_strategy": table.display.strategy.value,
        "schema_evolution": None if schema is None else schema.schema_evolution.value,
        "before_only_columns": [] if schema is None else list(schema.before_only_columns),
        "current_only_columns": [] if schema is None else list(schema.current_only_columns),
        "before_table_ref_present": refs.before_table_ref is not None,
        "current_table_ref_present": refs.current_table_ref is not None,
        "row_count_before": stats.row_count_before,
        "row_count_current": stats.row_count_current,
        "row_added_count": stats.row_added_count,
        "row_deleted_count": stats.row_deleted_count,
        "records_ref_present": records.records_ref is not None,
    }


def _assert_s1b_surface_golden(name: str, table: SurfaceTable) -> None:
    expected = _s1b_surface_golden_case(name)
    actual = _s1b_surface_projection(table)
    assert {key: actual[key] for key in expected} == expected


def _digest(seed: str) -> DigestRef:
    return raw_blob_digest(seed.encode())


def _ref(name: str, media_type: str = "application/json") -> ArtifactRef:
    raw = name.encode()
    return ArtifactRef(
        artifact_id=build_artifact_id(ArtifactLocation.EXPORT, "test-fixture", name),
        media_type=media_type,
        size_bytes=len(raw),
        raw_sha256=raw_blob_digest(raw),
    )


def _descriptor(table_name: str, *, row_count: int, side: str) -> SnapshotTableDescriptor:
    return SnapshotTableDescriptor(
        table_name=table_name,
        display_table_name=table_name.title(),
        columns=(
            SnapshotColumnDescriptor("id", "ID", False, "INT"),
            SnapshotColumnDescriptor("name", "Name", True, "VARCHAR"),
        ),
        primary_key_columns=("id",),
        compare_key_columns=("id",),
        row_count=row_count,
        materialization_stage=MaterializationStage.FINAL,
        compare_schema_digest=_digest(f"{side}-schema"),
        table_ruleset_version=1,
        row_materialization_profile="sql-canonical-v1",
        scalar_encoding_version=1,
        raw_content_digest=_digest(f"{side}-content"),
    )


def _facts(
    table: ComparisonTableFact,
    *,
    mode: ComparisonMode = ComparisonMode.DETAILED,
    records_ref: ArtifactRef | None = None,
) -> ComparisonFacts:
    changed = table.content_changed or table.status not in {
        ComparisonTableStatus.UNCHANGED,
        ComparisonTableStatus.BUSINESS_EQUIVALENT,
    }
    summary = ComparisonSummary(
        status=PairResultStatus.CHANGED if changed else PairResultStatus.UNCHANGED,
        table_count=1,
        unchanged_table_count=0 if changed else 1,
        changed_table_count=1 if changed else 0,
        added_table_count=int(table.status is ComparisonTableStatus.ADDED_TABLE),
        deleted_table_count=int(table.status is ComparisonTableStatus.DELETED_TABLE),
        schema_changed_table_count=int(
            table.status
            in {ComparisonTableStatus.SCHEMA_CHANGED, ComparisonTableStatus.SCHEMA_ONLY_CHANGED}
        ),
        degraded_table_count=int(table.status is ComparisonTableStatus.DEGRADED),
        row_added_count=table.row_added_count,
        row_deleted_count=table.row_deleted_count,
        row_modified_count=table.row_modified_count,
        suppressed_added_count=table.suppressed_added_count,
        suppressed_deleted_count=table.suppressed_deleted_count,
        diagnostics_count=len(table.diagnostics),
    )
    return ComparisonFacts(
        comparison_digest=_digest("comparison"),
        facts_core_digest=_digest("facts-core"),
        comparison_contract_version="backend-vnext/comparison/v3",
        projection_contract_version="backend-vnext/comparison-projection/v1",
        scalar_encoding_version=1,
        before_snapshot_digest=_digest("before"),
        current_snapshot_digest=_digest("current"),
        comparison_mode=mode,
        direction="BEFORE_TO_CURRENT",
        summary=summary,
        tables=(table,),
        records_ref=records_ref,
    )


def _content_binding(seed: str) -> TableContentBinding:
    return TableContentBinding(_digest(seed + "business"), _digest(seed + "content"), 3,
        _digest(seed + "source"), _digest(seed + "canonical"), _digest(seed + "rules"), "3")


def _bindings(refs: SurfaceTableRefs) -> SurfaceTableContentBindings:
    return SurfaceTableContentBindings(**{side: None if (ref := getattr(refs, side + "_table_ref")) is None
        else _content_binding(ref.artifact_id) for side in ("before", "current", "browse")})


def _request(
    facts: ComparisonFacts,
    *,
    table_refs: SurfaceTableRefs = SurfaceTableRefs(),
    records_closure: ComparisonRecordsClosure | None = None,
    surface_id: str = "surface-1",
    identity_annotation: SurfaceIdentityAnnotation = SurfaceIdentityAnnotation(),
    keyless_fallback_tables: tuple[str, ...] = (),
) -> SurfaceAssemblyInput:
    return SurfaceAssemblyInput(
        comparison_facts=facts,
        projections=(NAVIGATION_PROJECTION,),
        surface_id=surface_id,
        view_id="view-1",
        before_role="before",
        current_role="current",
        records_closure=records_closure,
        table_artifacts=(SurfaceArtifactIndexEntry("orders", table_refs, table_content_bindings=_bindings(table_refs)),),
        keyless_fallback_tables=keyless_fallback_tables,
        ref_scope=SurfaceRefScope.OPERATION_RELATIVE,
        identity_annotation=identity_annotation,
    )


def _records_closure(facts: ComparisonFacts) -> tuple[ComparisonRecordsClosure, ArtifactRef]:
    records_ref = _ref("records-orders", "application/vnd.apache.parquet")
    manifest_ref = _ref("records-orders-manifest")
    closure_ref = _ref("records-closure")
    entry = RecordsClosureEntry(
        table_name="orders",
        family=RecordsArtifactFamily.STANDARD,
        records_ref=records_ref,
        records_manifest_ref=manifest_ref,
        records_manifest_digest=manifest_ref.raw_sha256,
        records_content_digest=records_ref.raw_sha256,
        record_count=1,
    )
    return (
        ComparisonRecordsClosure(
            comparison_digest=facts.comparison_digest,
            facts_core_digest=facts.facts_core_digest,
            records=(entry,),
            closure_manifest_digest=closure_ref.raw_sha256,
        ),
        closure_ref,
    )


def test_unchanged_table_is_summary_only_without_row_reads() -> None:
    facts = _facts(ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.UNCHANGED))
    result = assemble_surface(_request(facts))

    assert result.status is SurfaceAssemblyStatus.READY
    assert result.surface is not None
    table = result.surface.tables[0]
    assert table.change_kind is SurfaceChangeKind.UNCHANGED
    assert table.display.strategy is SurfaceDisplayStrategy.SUMMARY_ONLY
    assert table.display.table_processing_mode is SurfaceTableProcessingMode.STANDARD
    assert "before_values" not in str(result.surface.to_document())
    validate_surface(result.surface)


def test_table_content_fact_is_visible_and_counts_as_changed() -> None:
    facts = _facts(
        ComparisonTableFact(
            table_name="orders",
            status=ComparisonTableStatus.UNCHANGED,
            content_changed=True,
        )
    )
    result = assemble_surface(_request(facts))

    assert result.status is SurfaceAssemblyStatus.READY
    assert result.surface is not None
    assert result.surface.summary.changed_table_count == 1
    assert result.surface.tables[0].change_kind is SurfaceChangeKind.UPDATED
    assert result.surface.tables[0].content_changed is True
    assert result.surface.tables[0].to_document()["content_changed"] is True


def test_additive_schema_alone_stays_summary_only_and_keeps_added_names_private() -> None:
    facts = _facts(
        ComparisonTableFact(
            table_name="orders",
            status=ComparisonTableStatus.UNCHANGED,
            schema_changes=ComparisonSchemaChanges(
                current_only_columns=("new_value",),
                schema_evolution=SchemaEvolution.COLUMNS_ADDED,
            ),
            content_changed=False,
        )
    )

    result = assemble_surface(_request(facts))

    assert result.status is SurfaceAssemblyStatus.READY
    assert result.surface is not None
    assert result.surface.summary.changed_table_count == 0
    projected = result.surface.tables[0]
    _assert_s1b_surface_golden("added_columns_only", projected)
    assert projected.change_kind is SurfaceChangeKind.UNCHANGED
    assert projected.display.strategy is SurfaceDisplayStrategy.SUMMARY_ONLY
    assert projected.schema_summary is not None
    assert projected.schema_summary.schema_evolution is SchemaEvolution.COLUMNS_ADDED
    assert projected.schema_summary.current_only_columns == ()


def test_added_column_excluded_value_swap_is_summary_only_and_visible_as_updated() -> None:
    facts = _facts(
        ComparisonTableFact(
            table_name="orders",
            status=ComparisonTableStatus.UNCHANGED,
            schema_changes=ComparisonSchemaChanges(
                current_only_columns=("note",),
                schema_evolution=SchemaEvolution.COLUMNS_ADDED,
            ),
            content_changed=True,
        )
    )

    result = assemble_surface(_request(facts))

    assert result.surface is not None
    projected = result.surface.tables[0]
    _assert_s1b_surface_golden("added_column_excluded_values_swapped", projected)
    assert result.surface.summary.changed_table_count == 1
    assert projected.change_kind is SurfaceChangeKind.UPDATED
    assert projected.display.strategy is SurfaceDisplayStrategy.SUMMARY_ONLY
    assert projected.content_changed is True


def test_incompatible_enum_label_change_projects_schema_changed() -> None:
    facts = _facts(
        ComparisonTableFact(
            table_name="orders",
            status=ComparisonTableStatus.SCHEMA_CHANGED,
            schema_changes=ComparisonSchemaChanges(
                incompatible_columns=("state",),
                schema_evolution=SchemaEvolution.INCOMPATIBLE,
            ),
        )
    )

    result = assemble_surface(_request(facts))

    assert result.surface is not None
    projected = result.surface.tables[0]
    _assert_s1b_surface_golden("incompatible_enum_label_change", projected)
    assert projected.change_kind is SurfaceChangeKind.SCHEMA_CHANGED


@pytest.mark.parametrize(
    ("status", "expected_kind"),
    (
        (ComparisonTableStatus.UNCHANGED, SurfaceChangeKind.UNCHANGED),
        (ComparisonTableStatus.BUSINESS_EQUIVALENT, SurfaceChangeKind.BUSINESS_EQUIVALENT),
        (ComparisonTableStatus.ADDED_TABLE, SurfaceChangeKind.ADDED),
        (ComparisonTableStatus.DELETED_TABLE, SurfaceChangeKind.DELETED),
        (ComparisonTableStatus.MODIFIED, SurfaceChangeKind.UPDATED),
        (ComparisonTableStatus.SCHEMA_CHANGED, SurfaceChangeKind.SCHEMA_CHANGED),
        (ComparisonTableStatus.SCHEMA_ONLY_CHANGED, SurfaceChangeKind.SCHEMA_CHANGED),
        (ComparisonTableStatus.DEGRADED, SurfaceChangeKind.DEGRADED),
    ),
)
def test_table_status_projection_is_deterministic(
    status: ComparisonTableStatus, expected_kind: SurfaceChangeKind
) -> None:
    table = ComparisonTableFact(table_name="orders", status=status)
    result = assemble_surface(_request(_facts(table)))
    assert result.status is SurfaceAssemblyStatus.READY
    assert result.surface is not None
    assert result.surface.tables[0].change_kind is expected_kind


@pytest.mark.parametrize(
    ("status", "refs", "expected_strategy"),
    (
        (
            ComparisonTableStatus.ADDED_TABLE,
            SurfaceTableRefs(current_table_ref=_ref("current-orders", "application/vnd.apache.parquet")),
            SurfaceDisplayStrategy.TABLE_BROWSE,
        ),
        (
            ComparisonTableStatus.DELETED_TABLE,
            SurfaceTableRefs(before_table_ref=_ref("before-orders", "application/vnd.apache.parquet")),
            SurfaceDisplayStrategy.TABLE_BROWSE,
        ),
    ),
)
def test_added_and_deleted_tables_are_browsable_without_row_records(
    status: ComparisonTableStatus,
    refs: SurfaceTableRefs,
    expected_strategy: SurfaceDisplayStrategy,
) -> None:
    table = ComparisonTableFact(
        table_name="orders",
        status=status,
        row_count_current=3 if status is ComparisonTableStatus.ADDED_TABLE else None,
        row_count_before=3 if status is ComparisonTableStatus.DELETED_TABLE else None,
    )

    result = assemble_surface(_request(_facts(table), table_refs=refs))

    assert result.status is SurfaceAssemblyStatus.READY
    assert result.surface is not None
    projected = result.surface.tables[0]
    _assert_s1b_surface_golden(
        "whole_table_added"
        if status is ComparisonTableStatus.ADDED_TABLE
        else "whole_table_deleted",
        projected,
    )
    assert projected.display.strategy is expected_strategy
    assert projected.records_refs.records_ref is None


def test_changed_table_requires_records_closure_when_row_targets_exist() -> None:
    facts = _facts(
        ComparisonTableFact(
            table_name="orders",
            status=ComparisonTableStatus.MODIFIED,
            row_modified_count=1,
        )
    )
    result = assemble_surface(_request(facts))
    assert result.status is SurfaceAssemblyStatus.FAILED
    assert result.surface is None
    assert result.diagnostics == ("REQUIRED_RECORDS_CLOSURE_MISSING",)


def test_ordered_unsupported_is_degraded_notice_not_standard_diff() -> None:
    facts = _facts(
        ComparisonTableFact(
            table_name="orders",
            status=ComparisonTableStatus.MODIFIED,
            diagnostics=("ORDERED_DIFF_UNSUPPORTED",),
        )
    )
    result = assemble_surface(_request(facts))

    assert result.status is SurfaceAssemblyStatus.READY
    assert result.surface is not None
    table = result.surface.tables[0]
    assert table.change_kind is SurfaceChangeKind.DEGRADED
    assert table.display.strategy is SurfaceDisplayStrategy.DEGRADED_NOTICE
    assert table.display.table_processing_mode is SurfaceTableProcessingMode.DEGRADED


def test_risk_report_is_projected_without_synthesizing_missing_table_risk() -> None:
    facts = _facts(ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.UNCHANGED))
    empty_summary = RiskSummary(risk_level=None, reason_codes=(), table_count=0, annotation_count=0)
    empty_report = RiskReport(
        risk_report_contract_version=RISK_CONTRACT_VERSION,
        risk_evaluation_digest=_digest("risk-empty"),
        overall=empty_summary,
        tables=(),
    )
    empty_result = assemble_surface(
        SurfaceAssemblyInput(
            comparison_facts=facts,
            projections=(NAVIGATION_PROJECTION,),
            surface_id="surface-empty-risk",
            view_id="view-1",
            before_role="before",
            current_role="current",
            risk_report=empty_report,
        )
    )
    assert empty_result.status is SurfaceAssemblyStatus.READY
    assert empty_result.surface is not None
    assert empty_result.surface.tables[0].risk_refs.risk_level is None

    table_risk = RiskTableRisk(
        table_name="orders",
        risk_level=RiskLevel.UNKNOWN,
        reason_codes=(RiskReasonCode.ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED,),
        annotation_count=0,
        source_table_status=ComparisonTableStatus.UNCHANGED,
    )
    report = RiskReport(
        risk_report_contract_version=RISK_CONTRACT_VERSION,
        risk_evaluation_digest=_digest("risk-table"),
        overall=RiskSummary(
            risk_level=RiskLevel.UNKNOWN,
            reason_codes=(RiskReasonCode.ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED,),
            table_count=1,
            annotation_count=0,
        ),
        tables=(table_risk,),
    )
    result = assemble_surface(
        SurfaceAssemblyInput(
            comparison_facts=facts,
            projections=(NAVIGATION_PROJECTION,),
            surface_id="surface-table-risk",
            view_id="view-1",
            before_role="before",
            current_role="current",
            risk_report=report,
        )
    )
    assert result.status is SurfaceAssemblyStatus.READY
    assert result.surface is not None
    assert result.surface.tables[0].risk_refs.risk_level is RiskLevel.UNKNOWN


def test_records_closure_is_published_without_changing_semantic_digest() -> None:
    facts = _facts(
        ComparisonTableFact(
            table_name="orders",
            status=ComparisonTableStatus.MODIFIED,
            row_modified_count=1,
        )
    )
    closure, closure_ref = _records_closure(facts)
    facts = replace(facts, records_ref=closure_ref)
    request = _request(facts, records_closure=closure)
    result = assemble_surface(request)

    assert result.status is SurfaceAssemblyStatus.READY
    assert result.surface is not None
    assert result.surface.tables[0].records_refs.records_format is SurfaceRecordsFormat.PARQUET
    assert result.surface.tables[0].display.strategy is SurfaceDisplayStrategy.RECORDS_ONLY
    assert result.surface.refs.records_closure_ref == closure_ref
    validate_surface(result.surface)


def test_replacement_uses_independent_side_browse_and_no_records() -> None:
    table = ComparisonTableFact(
        table_name="orders",
        status=ComparisonTableStatus.MODIFIED,
        before_descriptor=_descriptor("orders", row_count=2, side="before"),
        current_descriptor=_descriptor("orders", row_count=3, side="current"),
        row_added_count=3,
        row_deleted_count=2,
    )
    facts = _facts(
        table,
        mode=ComparisonMode.DATASET_REPLACEMENT,
    )
    result = assemble_surface(
        _request(
            facts,
            table_refs=SurfaceTableRefs(
                before_table_ref=_ref("before-orders", "application/vnd.apache.parquet"),
                current_table_ref=_ref("current-orders", "application/vnd.apache.parquet"),
            ),
            identity_annotation=SurfaceIdentityAnnotation(
                status="DIFFERENT_PROJECT",
                assessment_digest=_digest("assessment"),
            ),
        )
    )

    assert result.status is SurfaceAssemblyStatus.READY
    assert result.surface is not None
    table_result = result.surface.tables[0]
    assert table_result.change_kind is SurfaceChangeKind.REPLACED
    assert table_result.display.strategy is SurfaceDisplayStrategy.REPLACEMENT_SIDE_BY_SIDE
    assert table_result.display.table_processing_mode is SurfaceTableProcessingMode.DATASET_REPLACEMENT
    assert table_result.records_refs.records_ref is None
    assert table_result.replacement_summary is not None
    assert table_result.replacement_summary.before is not None
    assert table_result.replacement_summary.current is not None

    swapped_refs = replace(
        table_result.table_refs,
        before_table_ref=table_result.table_refs.current_table_ref,
        current_table_ref=table_result.table_refs.before_table_ref,
    )
    swapped_surface = replace(
        result.surface,
        tables=(replace(table_result, table_refs=swapped_refs),),
    )
    assert compute_surface_digest(swapped_surface) == result.surface.surface_digest
    swapped_bindings = replace(table_result.table_content_bindings,
        before=table_result.table_content_bindings.current, current=table_result.table_content_bindings.before)
    rebound = replace(result.surface, tables=(replace(table_result, table_refs=swapped_refs,
        table_content_bindings=swapped_bindings),))
    assert compute_surface_digest(rebound) != result.surface.surface_digest


def test_input_order_and_ref_rewrite_do_not_change_surface_digest() -> None:
    table = ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.UNCHANGED)
    facts = _facts(table)
    first = assemble_surface(_request(facts, surface_id="surface-a"))
    second = assemble_surface(_request(facts, surface_id="surface-b"))
    assert first.surface is not None and second.surface is not None
    assert first.surface.surface_digest == second.surface.surface_digest
    assert compute_surface_digest(first.surface) == first.surface.surface_digest

    old_ref = _ref("current-orders", "application/vnd.apache.parquet")
    new_ref = replace(old_ref, artifact_id="a1:durable:9e1660768076ad9eb6982ad5106b06ff209eb2cafb8ddaa08254acbbacf27eef")
    with_ref = assemble_surface(
        _request(
            facts,
            table_refs=SurfaceTableRefs(current_table_ref=old_ref),
        )
    )
    assert with_ref.surface is not None
    rewritten = rewrite_surface_refs(with_ref.surface, {old_ref: new_ref})
    assert rewritten.surface_digest == with_ref.surface.surface_digest
    assert rewritten.tables[0].table_refs.current_table_ref == new_ref
    validate_surface(rewritten)


def test_keyless_fallback_hint_is_read_only_surface_diagnostic() -> None:
    facts = _facts(
        ComparisonTableFact(
            table_name="orders",
            status=ComparisonTableStatus.UNCHANGED,
        )
    )

    result = assemble_surface(
        _request(facts, keyless_fallback_tables=("orders",))
    )

    assert result.surface is not None
    table = result.surface.tables[0]
    assert table.table_status is ComparisonTableStatus.UNCHANGED
    assert "KEYLESS_FALLBACK" in table.diagnostics.diagnostics_summary
    assert result.surface.summary.changed_table_count == 0


@pytest.mark.parametrize("artifact_id", UNSUPPORTED_DELIVERY_ARTIFACT_IDS)
def test_unsupported_delivery_ref_fails_before_ready(artifact_id: str) -> None:
    facts = _facts(ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.UNCHANGED))
    ref = _ref("delivery-member")
    request = _request(facts, table_refs=SurfaceTableRefs(current_table_ref=ref))
    # Corrupt the typed ref only after the request is valid: exercise assembly's
    # fail-closed boundary rather than a constructor rejecting the fixture first.
    object.__setattr__(ref, "artifact_id", artifact_id)
    result = assemble_surface(request)
    assert result.status is SurfaceAssemblyStatus.FAILED
    assert result.surface is None


def test_cancellation_and_json_budget_never_publish_partial_surface() -> None:
    facts = _facts(ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.UNCHANGED))
    cancelled = assemble_surface(
        _request(facts),
        context=SurfaceAssemblyContext(cancel_requested=lambda: True),
    )
    assert cancelled.status is SurfaceAssemblyStatus.CANCELLED
    assert cancelled.surface is None

    over_budget = assemble_surface(
        _request(facts),
        policy=SurfaceAssemblyPolicy(max_surface_json_bytes=1),
    )
    assert over_budget.status is SurfaceAssemblyStatus.FAILED
    assert over_budget.surface is None


def test_surface_physical_rows_and_locator_are_outside_semantic_digest() -> None:
    facts = _facts(ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.UNCHANGED))
    rows = _ref("rows-first", "application/vnd.apache.parquet")
    result = assemble_surface(_request(facts, table_refs=SurfaceTableRefs(current_table_ref=rows)))
    assert result.surface is not None
    original = result.surface
    table = original.tables[0]
    reordered = _ref("rows-reordered", "application/vnd.apache.parquet")
    locator = _ref("row-locator", "application/vnd.apache.parquet")
    changed = replace(table, table_refs=replace(table.table_refs, current_table_ref=reordered),
                      row_locator_ref=locator)
    rebound = replace(original, tables=(changed,))
    assert compute_surface_digest(rebound) == original.surface_digest
    rewritten_locator = replace(locator, artifact_id=build_artifact_id(ArtifactLocation.EXPORT, "test-fixture", "locator-bundle"))
    rewritten = rewrite_surface_refs(rebound, {locator: rewritten_locator})
    assert rewritten.tables[0].row_locator_ref == rewritten_locator
    assert compute_surface_digest(rewritten) == original.surface_digest
    from gateway_backend.capabilities.bundle_assembly._refs import collect_surface_refs
    assert rewritten_locator in collect_surface_refs(rewritten)
    binding = changed.table_content_bindings.current
    assert binding is not None
    different_content = replace(changed, table_content_bindings=replace(changed.table_content_bindings,
        current=replace(binding, raw_content_digest=_digest("different-content"))))
    assert compute_surface_digest(replace(original, tables=(different_content,))) != original.surface_digest


def test_table_bindings_reject_missing_or_incompatible_ref_content() -> None:
    rows = _ref("shared-rows", "application/vnd.apache.parquet")
    with pytest.raises(ValueError, match="nullability"):
        SurfaceArtifactIndexEntry("orders", SurfaceTableRefs(current_table_ref=rows))
    with pytest.raises(ValueError, match="incompatible"):
        SurfaceArtifactIndexEntry("orders", SurfaceTableRefs(before_table_ref=rows, current_table_ref=rows),
            table_content_bindings=SurfaceTableContentBindings(_content_binding("old"), _content_binding("new")))


def test_surface_uses_frozen_comments_and_preserves_before_only_columns() -> None:
    from gateway_backend.capabilities.table_presentation.metadata import (
        ColumnPresentation, PresentationMetadata, TablePresentation,
    )
    old = _descriptor("orders", row_count=1, side="before")
    current = replace(_descriptor("orders", row_count=1, side="current"), columns=(old.columns[0],))
    table = ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.SCHEMA_ONLY_CHANGED,
        before_descriptor=old, current_descriptor=current)
    request = replace(_request(_facts(table)),
        before_presentation=PresentationMetadata((TablePresentation("orders", "旧表", (
            ColumnPresentation("id", "旧编号"), ColumnPresentation("name", "旧名称"))),)),
        current_presentation=PresentationMetadata((TablePresentation("orders", "新表", (
            ColumnPresentation("id", "新编号"),)),)))
    result = assemble_surface(request)
    assert result.surface is not None
    projected = result.surface.tables[0]
    assert projected.display_name == "新表"
    assert [(c.name, c.display_name, c.present_in, c.pinned, c.display_order) for c in projected.columns] == [
        ("id", "新编号", "BOTH", False, 0), ("name", "旧名称", "BEFORE", True, 1)]
    replacement = assemble_surface(replace(request, comparison_facts=replace(request.comparison_facts,
        comparison_mode=ComparisonMode.DATASET_REPLACEMENT)))
    assert replacement.surface is not None
    sides = replacement.surface.tables[0].replacement_summary
    assert sides is not None and sides.before is not None and sides.current is not None
    assert (sides.before.display_name, sides.current.display_name) == ("旧表", "新表")
    assert {c.present_in for c in sides.before.columns} == {"BEFORE"}
    assert {c.present_in for c in sides.current.columns} == {"CURRENT"}


@pytest.mark.parametrize(("message", "code"), (
    ("DUPLICATE_EFFECTIVE_KEY:orders", "DUPLICATE_EFFECTIVE_KEY"),
    ("TableAccessError", "COMPARISON_INTERNAL_ERROR"),
    ("ArrowInvalid", "COMPARISON_INTERNAL_ERROR"),
    ("arbitrary error text", "COMPARISON_INTERNAL_ERROR"),
    ("KEYLESS_FALLBACK", "KEYLESS_FALLBACK"),
))
def test_surface_diagnostics_publish_only_stable_codes(message: str, code: str) -> None:
    facts = _facts(ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.UNCHANGED,
        diagnostics=(message,)))
    result = assemble_surface(_request(facts))
    assert result.surface is not None
    assert result.surface.tables[0].diagnostics.diagnostics_summary == (code,)


@pytest.mark.parametrize("fault", ("missing", "wrong-id", "wrong-kind", "duplicate-kind", "risk-summary"))
def test_ready_surface_requires_exactly_one_current_navigation_projection(fault: str) -> None:
    request = _request(_facts(ComparisonTableFact("orders", ComparisonTableStatus.UNCHANGED)))
    projections = {
        "missing": (),
        "wrong-id": (replace(NAVIGATION_PROJECTION, projection_id="wrong"),),
        "wrong-kind": (replace(NAVIGATION_PROJECTION, projection_kind="wrong"),),
        "duplicate-kind": (NAVIGATION_PROJECTION, replace(NAVIGATION_PROJECTION, projection_id="second")),
        "risk-summary": (replace(NAVIGATION_PROJECTION, risk_summary_ref=_ref("risk-summary")),),
    }[fault]
    result = assemble_surface(replace(request, projections=projections))
    assert result.status is SurfaceAssemblyStatus.FAILED and result.surface is None
