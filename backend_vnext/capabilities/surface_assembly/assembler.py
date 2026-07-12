from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from ...artifacts.manifest import ArtifactRef
from ...core.digests import DigestRef
from ...core.diagnostics import DiagnosticRecord, ErrorRecord
from ...core.identifiers import canonical_identifier
from ..comparison.models import ComparisonFacts, ComparisonRecordsClosure, ComparisonTableFact, ComparisonTableStatus
from ..risk_evaluation.models import RiskLevel, RiskReport, RiskTableRisk
from .digest import build_surface_digest
from .models import (
    ComparisonSurface,
    ComparisonSurfaceAssemblyInput,
    ComparisonSurfaceAssemblyResult,
    SurfaceChangeKind,
    SurfaceCompare,
    SurfaceDisplay,
    SurfaceDisplayStrategy,
    SurfaceDiagnosticsRefs,
    SurfaceOrderedExtension,
    SurfaceProjectionRef,
    SurfaceRecordsFormat,
    SurfaceRecordsRefs,
    SurfaceRefScope,
    SurfaceRefs,
    SurfaceReplayGuarantee,
    SurfaceRiskRefs,
    SurfaceSummary,
    SurfaceTable,
    SurfaceTableProcessingMode,
    SurfaceTableRefs,
    SurfaceView,
)
from .ref_validation import ensure_logical_relative_ref
from .versions import SURFACE_CONTRACT_VERSION, SURFACE_PROFILE_STANDARD_TABLE_BROWSER


class SurfaceAssembler:
    def assemble(self, request: ComparisonSurfaceAssemblyInput) -> ComparisonSurfaceAssemblyResult:
        diagnostics: list[DiagnosticRecord] = []
        records_closure = request.records_closure
        if records_closure is None and request.comparison_facts.records_ref is not None:
            records_closure = request.comparison_facts.records_ref

        if request.comparison_facts.summary is None:
            raise ValueError("comparison_facts.summary is required for surface assembly")

        tables: list[SurfaceTable] = []
        referenced_artifacts: list[ArtifactRef] = []
        risk_report = request.risk_report
        risk_annotation_closure = request.risk_annotation_closure
        risk_report_digest = None
        if risk_report is not None:
            risk_report_digest = _build_risk_report_digest(risk_report)
            referenced_artifacts.extend(risk_report.annotation_refs)
        if risk_annotation_closure:
            referenced_artifacts.extend(risk_annotation_closure)

        records_closure_manifest_digest = None
        if records_closure is not None:
            records_closure_manifest_digest = records_closure.closure_manifest_digest
            referenced_artifacts.extend(member.records_ref for member in records_closure.records)
        projections = _projection_refs_for_result(request.business_projection_result)
        surface_options = dict(request.surface_options)
        view_id = _surface_view_id(request.comparison_facts)
        view_label = None
        surface_id = _surface_id(request.comparison_facts)

        for fact in request.comparison_facts.tables:
            table = _build_surface_table(
                fact=fact,
                comparison_facts=request.comparison_facts,
                records_closure=records_closure,
                risk_report=risk_report,
                records_closure_manifest_digest=records_closure_manifest_digest,
                risk_report_digest=risk_report_digest,
            )
            if _should_filter_empty_unchanged_table(table):
                continue
            tables.append(table)

        surface_view = SurfaceView(
            view_id=view_id,
            label=view_label,
            before_role="BEFORE",
            current_role="CURRENT",
            table_count=len(tables),
            changed_table_count=sum(1 for table in tables if table.change_kind not in {SurfaceChangeKind.UNCHANGED, SurfaceChangeKind.BUSINESS_EQUIVALENT}),
            degraded_table_count=sum(1 for table in tables if table.change_kind in {SurfaceChangeKind.DEGRADED, SurfaceChangeKind.FAILED}),
            risk_level=_risk_level_from_report(risk_report),
        )
        surface_summary = SurfaceSummary(
            table_count=len(tables),
            visible_table_count=len(tables),
            changed_table_count=surface_view.changed_table_count,
            degraded_table_count=surface_view.degraded_table_count,
            risk_level=surface_view.risk_level,
            diagnostics_count=(
                len(request.comparison_facts.diagnostics)
                + len(diagnostics)
                + (0 if request.business_projection_result is None else len(request.business_projection_result.diagnostics))
            ),
        )

        surface_refs = SurfaceRefs(
            surface_ref="comparison-surface.json",
            records_closure_ref=("comparison/records-closure.json" if records_closure is not None else None),
            records_closure_manifest_digest=records_closure_manifest_digest,
            risk_report_ref=("risk/risk-report.json" if risk_report is not None else None),
            risk_report_digest=risk_report_digest,
            risk_annotation_closure_ref=(
                "risk/risk-annotation-closure.json" if risk_annotation_closure else None
            ),
            risk_annotation_closure_manifest_digest=(
                DigestRef.from_payload([artifact_ref.to_payload() for artifact_ref in risk_annotation_closure])
                if risk_annotation_closure
                else None
            ),
            diagnostics_refs=tuple(request.diagnostics_refs),
            diagnostics_manifest_digests=(),
        )

        surface = ComparisonSurface(
            surface_contract_version=request.surface_contract_version,
            surface_id=surface_id,
            direction=request.comparison_facts.direction,
            comparison_digest=request.comparison_facts.comparison_digest,
            risk_evaluation_digest=(
                None if risk_report is None else risk_report.risk_evaluation_digest
            ),
            surface_profile=request.surface_profile,
            surface_options=surface_options,
            view=surface_view,
            tables=tuple(tables),
            hidden_tables=(),
            projections=projections,
            summary=surface_summary,
            refs=surface_refs,
            diagnostics=(
                tuple(request.comparison_facts.diagnostics)
                + tuple(diagnostics)
                + (() if request.business_projection_result is None else request.business_projection_result.diagnostics)
            ),
        )
        surface_digest = build_surface_digest(surface)
        surface = replace(surface, surface_digest=surface_digest)
        return ComparisonSurfaceAssemblyResult(
            comparison_surface=surface,
            surface_digest=surface_digest,
            referenced_artifacts=_dedupe_artifacts(referenced_artifacts),
            diagnostics=tuple(diagnostics),
        )


def _projection_refs_for_result(result) -> tuple[SurfaceProjectionRef, ...]:
    if result is None:
        return ()
    diagnostics_ref = "projections/diagnostics.json" if result.diagnostics else None
    projections: list[SurfaceProjectionRef] = []
    for projection in result.projections:
        summary = projection.payload.get("summary")
        projection_summary = dict(summary) if isinstance(summary, Mapping) else {}
        projections.append(
            SurfaceProjectionRef(
                projection_id=projection.projection_id,
                projection_kind=projection.projection_kind.value,
                projection_ref=f"projections/{projection.projection_id}.json",
                projection_digest=projection.projection_digest,
                projection_summary=projection_summary,
                diagnostics_ref=diagnostics_ref,
            )
        )
    return tuple(projections)


def _build_surface_table(
    *,
    fact: ComparisonTableFact,
    comparison_facts: ComparisonFacts,
    records_closure: ComparisonRecordsClosure | None,
    risk_report: RiskReport | None,
    records_closure_manifest_digest: DigestRef | None,
    risk_report_digest: DigestRef | None,
) -> SurfaceTable:
    records_ref = fact.records_ref
    records_prefix, records_suffix, records_manifest_suffix = _records_artifact_layout_for_fact(fact)
    table_records_ref = None
    records_manifest_ref = None
    records_manifest_digest = None
    records_content_digest = None
    if records_ref is not None and hasattr(records_ref, "manifest_digest"):
        table_records_ref = f"{records_prefix}/{fact.table_name}{records_suffix}"
        records_manifest_ref = f"{records_prefix}/{fact.table_name}{records_manifest_suffix}"
        records_manifest_digest = getattr(records_ref, "manifest_digest", None)
        records_content_digest = getattr(records_ref, "content_digest", None)

    risk_refs = SurfaceRiskRefs()
    table_risk = _risk_table_for_name(risk_report, fact.table_name)
    if table_risk is not None:
        risk_refs = SurfaceRiskRefs(
            report_ref="risk/risk-report.json",
            annotation_ref=f"risk/annotations/{fact.table_name}.json",
            annotation_manifest_ref=f"risk/annotations/{fact.table_name}.manifest.json",
            report_digest=risk_report_digest,
            annotation_manifest_digest=(
                table_risk.annotation_ref.manifest_digest if table_risk.annotation_ref is not None else None
            ),
            annotation_content_digest=(
                table_risk.annotation_ref.content_digest if table_risk.annotation_ref is not None else None
            ),
        )

    # Surface assembly does not own snapshot row artifacts.  The publishing flow
    # binds these refs only after it has materialized real bundle-local content.
    table_refs = SurfaceTableRefs()
    compare = SurfaceCompare(
        artifact_scope=_artifact_scope_for_fact(fact),
        compare_key_columns=_compare_key_columns_for_fact(fact),
        ignored_columns=_ignored_columns_for_fact(fact),
        effective_columns=_effective_columns_for_fact(fact),
        projection_schema_digest=fact.projection_schema_digest,
        projection_logical_digest=(
            fact.current_projection_logical_digest or fact.before_projection_logical_digest
        ),
        provider=_provider_for_fact(fact),
    )
    display = SurfaceDisplay(
        strategy=_display_strategy_for_fact(fact),
        table_processing_mode=_table_processing_mode_for_fact(fact),
        replay_guarantee=_replay_guarantee_for_fact(fact, records_ref is not None),
    )
    ordered_extension = _ordered_extension_for_fact(
        fact=fact,
        records_prefix=records_prefix,
        records_suffix=records_suffix,
        records_manifest_suffix=records_manifest_suffix,
    )
    return SurfaceTable(
        table_name=fact.table_name,
        display_name=_display_name_for_fact(fact),
        table_status=fact.status,
        change_kind=_change_kind_for_fact(fact),
        row_count=_row_count_for_fact(fact),
        row_change_stats=_row_change_stats_for_fact(fact),
        schema_summary=_schema_summary_for_fact(fact),
        columns=_effective_columns_for_fact(fact),
        table_refs=table_refs,
        records_refs=SurfaceRecordsRefs(
            records_ref=table_records_ref,
            records_manifest_ref=records_manifest_ref,
            records_format=(
                SurfaceRecordsFormat.PARQUET
                if table_records_ref is not None
                else SurfaceRecordsFormat.INLINE_SUMMARY
            ),
            records_manifest_digest=records_manifest_digest,
            records_content_digest=records_content_digest,
        ),
        risk_refs=risk_refs,
        display=display,
        compare=compare,
        diagnostics=fact.diagnostics,
        ordered_extension=ordered_extension,
    )


def _should_filter_empty_unchanged_table(table: SurfaceTable) -> bool:
    if table.table_status is not ComparisonTableStatus.UNCHANGED:
        return False
    if table.change_kind is not SurfaceChangeKind.UNCHANGED:
        return False
    if table.row_count != 0:
        return False
    if table.records_refs.records_ref is not None or table.records_refs.records_manifest_ref is not None:
        return False
    return True


def _change_kind_for_fact(fact: ComparisonTableFact) -> SurfaceChangeKind:
    status = fact.status
    if status is ComparisonTableStatus.UNCHANGED:
        return SurfaceChangeKind.UNCHANGED
    if status is ComparisonTableStatus.BUSINESS_EQUIVALENT:
        return SurfaceChangeKind.BUSINESS_EQUIVALENT
    if status is ComparisonTableStatus.ADDED_TABLE:
        return SurfaceChangeKind.ADDED
    if status is ComparisonTableStatus.DELETED_TABLE:
        return SurfaceChangeKind.DELETED
    if status is ComparisonTableStatus.MODIFIED:
        return SurfaceChangeKind.UPDATED
    if status in {ComparisonTableStatus.SCHEMA_CHANGED, ComparisonTableStatus.SCHEMA_ONLY_CHANGED}:
        return SurfaceChangeKind.SCHEMA_CHANGED
    if status is ComparisonTableStatus.DEGRADED:
        return SurfaceChangeKind.DEGRADED
    return SurfaceChangeKind.FAILED


def _table_processing_mode_for_fact(fact: ComparisonTableFact) -> SurfaceTableProcessingMode:
    if _is_ordered_unsupported(fact):
        return SurfaceTableProcessingMode.DEGRADED
    if fact.status in {ComparisonTableStatus.DEGRADED}:
        return SurfaceTableProcessingMode.DEGRADED
    if fact.status in {ComparisonTableStatus.SCHEMA_CHANGED, ComparisonTableStatus.SCHEMA_ONLY_CHANGED}:
        return SurfaceTableProcessingMode.SCHEMA_ONLY
    return SurfaceTableProcessingMode.STANDARD


def _display_strategy_for_fact(fact: ComparisonTableFact) -> SurfaceDisplayStrategy:
    if _is_ordered_unsupported(fact) or fact.status in {ComparisonTableStatus.DEGRADED}:
        return SurfaceDisplayStrategy.DEGRADED_NOTICE
    if _provider_for_fact(fact) == "BROWSE_ONLY":
        return SurfaceDisplayStrategy.TABLE_BROWSE
    if fact.status in {ComparisonTableStatus.UNCHANGED, ComparisonTableStatus.BUSINESS_EQUIVALENT}:
        return SurfaceDisplayStrategy.SUMMARY_ONLY
    if fact.status is ComparisonTableStatus.ADDED_TABLE:
        return SurfaceDisplayStrategy.TABLE_BROWSE
    if fact.status is ComparisonTableStatus.DELETED_TABLE:
        return SurfaceDisplayStrategy.RECORDS_ONLY if fact.records_ref is not None else SurfaceDisplayStrategy.SUMMARY_ONLY
    if fact.status is ComparisonTableStatus.MODIFIED:
        return SurfaceDisplayStrategy.CURRENT_WITH_RECORDS if fact.records_ref is not None else SurfaceDisplayStrategy.SUMMARY_ONLY
    if fact.status in {ComparisonTableStatus.SCHEMA_CHANGED, ComparisonTableStatus.SCHEMA_ONLY_CHANGED}:
        return SurfaceDisplayStrategy.RECORDS_ONLY if fact.records_ref is not None else SurfaceDisplayStrategy.DEGRADED_NOTICE
    return SurfaceDisplayStrategy.DEGRADED_NOTICE


def _replay_guarantee_for_fact(fact: ComparisonTableFact, has_records: bool) -> SurfaceReplayGuarantee:
    if fact.status is ComparisonTableStatus.DEGRADED:
        return SurfaceReplayGuarantee.UNSUPPORTED
    if has_records:
        return SurfaceReplayGuarantee.EXACT
    return SurfaceReplayGuarantee.SUMMARY_ONLY


def _change_kind_status_counts(fact: ComparisonTableFact) -> Mapping[str, object]:
    if fact.row_counts is None:
        return {}
    before_count, current_count = fact.row_counts
    payload: dict[str, object] = {}
    if before_count is not None:
        payload["before_row_count"] = before_count
    if current_count is not None:
        payload["current_row_count"] = current_count
    return payload


def _row_change_stats_for_fact(fact: ComparisonTableFact) -> Mapping[str, object] | None:
    if fact.row_change_stats is not None:
        return dict(fact.row_change_stats)
    if fact.row_counts is None:
        return None
    before_count, current_count = fact.row_counts
    if fact.status is ComparisonTableStatus.ADDED_TABLE and current_count is not None:
        return {"row_added_count": current_count}
    if fact.status is ComparisonTableStatus.DELETED_TABLE and before_count is not None:
        return {"row_deleted_count": before_count}
    return None


def _schema_summary_for_fact(fact: ComparisonTableFact) -> Mapping[str, object] | None:
    if fact.schema_changes is not None:
        return dict(fact.schema_changes)
    if fact.projection_schema is None:
        return None
    return {
        "table_name": fact.projection_schema.table_name,
        "selected_columns": list(fact.projection_schema.selected_columns),
        "ignored_columns": list(fact.projection_schema.ignored_columns),
        "compare_key_columns": list(fact.projection_schema.effective_compare_key),
    }


def _effective_columns_for_fact(fact: ComparisonTableFact) -> tuple[str, ...]:
    if fact.projection_schema is None:
        return ()
    return tuple(fact.projection_schema.selected_columns)


def _compare_key_columns_for_fact(fact: ComparisonTableFact) -> tuple[str, ...]:
    if fact.projection_schema is None:
        return ()
    return tuple(fact.projection_schema.effective_compare_key)


def _ignored_columns_for_fact(fact: ComparisonTableFact) -> tuple[str, ...]:
    if fact.projection_schema is None:
        return ()
    return tuple(fact.projection_schema.ignored_columns)


def _artifact_scope_for_fact(fact: ComparisonTableFact) -> str:
    if fact.projection_schema is None:
        return "TABLE"
    return "TABLE"


def _provider_for_fact(fact: ComparisonTableFact) -> str | None:
    for diagnostic in fact.diagnostics:
        provider = diagnostic.details.get("provider")
        if isinstance(provider, str):
            return provider
    return None


def _display_name_for_fact(fact: ComparisonTableFact) -> str:
    if fact.current_descriptor is not None:
        display_name = fact.current_descriptor.get("display_table_name")
        if isinstance(display_name, str) and display_name:
            return display_name
    if fact.before_descriptor is not None:
        display_name = fact.before_descriptor.get("display_table_name")
        if isinstance(display_name, str) and display_name:
            return display_name
    return fact.table_name


def _row_count_for_fact(fact: ComparisonTableFact) -> int | None:
    if fact.row_counts is None:
        return None
    before_count, current_count = fact.row_counts
    if current_count is not None:
        return current_count
    return before_count


def _risk_table_for_name(risk_report: RiskReport | None, table_name: str) -> RiskTableRisk | None:
    if risk_report is None:
        return None
    for table_risk in risk_report.tables:
        if canonical_identifier(table_risk.table_name) == canonical_identifier(table_name):
            return table_risk
    return None


def _risk_level_from_report(risk_report: RiskReport | None) -> RiskLevel | None:
    if risk_report is None:
        return None
    return risk_report.overall.risk_level


def _is_ordered_unsupported(fact: ComparisonTableFact) -> bool:
    if fact.ordered_extension is not None:
        return False
    if fact.status is not ComparisonTableStatus.DEGRADED:
        return False
    for diagnostic in fact.diagnostics:
        if diagnostic.details.get("reason") == "ORDERED_PROVIDER_MISSING":
            return True
    return False


def _ordered_extension_for_fact(
    *,
    fact: ComparisonTableFact,
    records_prefix: str,
    records_suffix: str,
    records_manifest_suffix: str,
) -> SurfaceOrderedExtension | None:
    ordered_extension = fact.ordered_extension
    if ordered_extension is not None:
        ordered_records_ref = None
        ordered_records_manifest_ref = None
        if ordered_extension.ordered_records_ref is not None:
            ordered_records_ref = f"{records_prefix}/{fact.table_name}{records_suffix}"
            ordered_records_manifest_ref = f"{records_prefix}/{fact.table_name}{records_manifest_suffix}"
        return SurfaceOrderedExtension(
            ordered_contract_version=ordered_extension.ordered_diff_contract_version,
            ordered_summary=ordered_extension.ordered_summary,
            ordered_records_ref=ordered_records_ref,
            ordered_records_manifest_ref=ordered_records_manifest_ref,
            stable_key_field=ordered_extension.stable_key_field,
            position_field=ordered_extension.position_field,
            ordered_display_mode=None,
            table_processing_mode=ordered_extension.table_processing_mode,
            ordered_preprocess_applied=ordered_extension.ordered_preprocess_applied,
            diagnostics=ordered_extension.diagnostics,
        )
    if _is_ordered_unsupported(fact):
        return SurfaceOrderedExtension(
            ordered_summary=None,
            ordered_records_ref=None,
            ordered_records_manifest_ref=None,
            ordered_display_mode=None,
            table_processing_mode="DEGRADED",
            ordered_preprocess_applied="NONE",
            diagnostics=fact.diagnostics,
        )
    return None


def _records_artifact_layout_for_fact(fact: ComparisonTableFact) -> tuple[str, str, str]:
    if fact.ordered_extension is not None:
        return (
            "comparison/ordered-records",
            ".ordered.records.parquet",
            ".ordered.records.manifest.json",
        )
    return (
        "comparison/records",
        ".records.parquet",
        ".records.manifest.json",
    )


def _surface_view_id(comparison_facts: ComparisonFacts) -> str:
    return comparison_facts.direction.lower()


def _surface_id(comparison_facts: ComparisonFacts) -> str:
    return f"surface-{comparison_facts.comparison_digest.hex_digest[:12]}"


def _build_risk_report_digest(risk_report: RiskReport) -> DigestRef:
    payload = {
        "risk_report_contract_version": risk_report.risk_report_contract_version,
        "risk_evaluation_digest": risk_report.risk_evaluation_digest.to_payload(),
        "overall": risk_report.overall.to_payload(),
        "tables": [table.payload_for_digest() for table in risk_report.tables],
        "annotation_manifest_digests": [
            annotation_ref.manifest_digest.to_payload() for annotation_ref in risk_report.annotation_refs
        ],
        "diagnostics": [diagnostic.to_payload() for diagnostic in risk_report.diagnostics],
    }
    return DigestRef.from_payload(payload)


def _dedupe_artifacts(artifacts: list[ArtifactRef]) -> tuple[ArtifactRef, ...]:
    seen: set[str] = set()
    deduped: list[ArtifactRef] = []
    for artifact_ref in artifacts:
        if not isinstance(artifact_ref, ArtifactRef):
            continue
        key = artifact_ref.storage_key
        if key in seen:
            continue
        seen.add(key)
        deduped.append(artifact_ref)
    return tuple(deduped)


__all__ = [
    "ComparisonSurface",
    "ComparisonSurfaceAssemblyInput",
    "ComparisonSurfaceAssemblyResult",
    "SurfaceChangeKind",
    "SurfaceCompare",
    "SurfaceDisplay",
    "SurfaceDisplayStrategy",
    "SurfaceDiagnosticsRefs",
    "SurfaceOrderedExtension",
    "SurfaceProfile",
    "SurfaceRecordsFormat",
    "SurfaceRecordsRefs",
    "SurfaceRefScope",
    "SurfaceRefs",
    "SurfaceReplayGuarantee",
    "SurfaceRiskRefs",
    "SurfaceSummary",
    "SurfaceTable",
    "SurfaceTableProcessingMode",
    "SurfaceTableRefs",
    "SurfaceView",
]
