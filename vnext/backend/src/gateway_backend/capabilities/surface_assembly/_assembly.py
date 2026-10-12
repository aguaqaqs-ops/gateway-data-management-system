"""Deterministic, bounded comparison surface assembly."""

from __future__ import annotations

from collections.abc import Iterable
from time import monotonic

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef, ArtifactStorePort
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonFacts,
    ComparisonMode,
    ComparisonRecordsClosure,
    ComparisonTableFact,
    ComparisonTableStatus,
    RecordsArtifactFamily,
)
from gateway_backend.capabilities.risk_evaluation.contracts import (
    RISK_ANNOTATION_MANIFEST_MEDIA_TYPE,
    RISK_ANNOTATION_MEDIA_TYPE,
    RiskAnnotationClosure,
    RiskAnnotationClosureEntry,
    RiskReport,
    RiskTableRisk,
    validate_risk_annotation_documents,
)
from gateway_backend.capabilities.surface_assembly._digest import compute_surface_digest
from gateway_backend.capabilities.surface_assembly._refs import validate_surface_refs
from gateway_backend.capabilities.surface_assembly.contracts import (
    ComparisonSurface,
    SurfaceArtifactIndexEntry,
    SurfaceAssemblyContext,
    SurfaceAssemblyInput,
    SurfaceAssemblyPolicy,
    SurfaceAssemblyResult,
    SurfaceAssemblyStatus,
    SurfaceChangeKind,
    SurfaceColumn,
    SurfaceCompare,
    SurfaceDiagnostics,
    SurfaceDisplay,
    SurfaceDisplayStrategy,
    SurfaceRecordsFormat,
    SurfaceRecordsRefs,
    SurfaceReplayGuarantee,
    SurfaceReplacementSide,
    SurfaceReplacementSummary,
    SurfaceRiskRefs,
    SurfaceRowChangeStats,
    SurfaceRootRefs,
    SurfaceSchemaSummary,
    SurfaceSummary,
    SurfaceTable,
    SurfaceTableProcessingMode,
    SurfaceTableRefs,
    SurfaceView,
    SURFACE_CONTRACT_VERSION,
)


def assemble_surface(
    request: SurfaceAssemblyInput,
    *,
    policy: SurfaceAssemblyPolicy | None = None,
    context: SurfaceAssemblyContext | None = None,
) -> SurfaceAssemblyResult:
    """Assemble one immutable Surface without reading row payloads."""

    if type(request) is not SurfaceAssemblyInput:
        raise TypeError("request must be SurfaceAssemblyInput")
    limits = policy or SurfaceAssemblyPolicy()
    control = context or SurfaceAssemblyContext()
    started = monotonic()

    def checkpoint() -> None:
        control.checkpoint()
        if control.cancel_requested():
            raise _Cancelled
        if monotonic() - started > limits.max_surface_wall_time_seconds:
            raise _AssemblyError("SURFACE_WALL_TIME_EXCEEDED")

    try:
        checkpoint()
        facts = request.comparison_facts
        if facts.summary.status.value in {"FAILED", "CANCELLED"}:
            raise _AssemblyError(f"COMPARISON_{facts.summary.status.value}")
        if facts.comparison_mode is ComparisonMode.DATASET_REPLACEMENT and facts.records_ref is not None:
            raise _AssemblyError("REPLACEMENT_MUST_NOT_CARRY_RECORDS_REF")
        _validate_records_closure(facts, request.records_closure)
        risk_by_name, risk_entry_by_name = _validate_risk_inputs(
            facts, request.risk_report, request.risk_annotation_closure
        )
        artifact_by_name = {item.table_name: item for item in request.table_artifacts}
        tables: list[SurfaceTable] = []
        for table in facts.tables:
            checkpoint()
            tables.append(
                _project_table(
                    facts,
                    table,
                    artifact_by_name.get(table.table_name),
                    request.records_closure,
                    risk_by_name.get(table.table_name),
                    risk_entry_by_name.get(table.table_name),
                    request.risk_report_ref,
                    keyless_fallback=table.table_name in request.keyless_fallback_tables,
                )
            )
        checkpoint()
        table_tuple = tuple(tables)
        root_diagnostics = _stable_messages(facts.diagnostics)
        if request.risk_report is not None:
            root_diagnostics = _stable_messages(
                (*root_diagnostics, *request.risk_report.diagnostics)
            )
        changed_count = sum(
            item.change_kind
            not in {SurfaceChangeKind.UNCHANGED, SurfaceChangeKind.BUSINESS_EQUIVALENT}
            or item.content_changed
            for item in table_tuple
        )
        degraded_count = sum(item.change_kind is SurfaceChangeKind.DEGRADED for item in table_tuple)
        summary = SurfaceSummary(
            table_count=len(table_tuple),
            changed_table_count=changed_count,
            degraded_table_count=degraded_count,
            failed_table_count=0,
            row_added_count=facts.summary.row_added_count,
            row_deleted_count=facts.summary.row_deleted_count,
            row_modified_count=facts.summary.row_modified_count,
            diagnostics_count=len(root_diagnostics)
            + sum(len(item.diagnostics.diagnostics_summary) for item in table_tuple),
        )
        view = SurfaceView(
            view_id=request.view_id,
            label=request.label,
            before_role=request.before_role,
            current_role=request.current_role,
            table_count=summary.table_count,
            changed_table_count=summary.changed_table_count,
            degraded_table_count=summary.degraded_table_count,
            failed_table_count=summary.failed_table_count,
            risk_level=None if request.risk_report is None else request.risk_report.overall.risk_level,
            diagnostics_summary=root_diagnostics,
        )
        surface = ComparisonSurface(
            surface_contract_version=SURFACE_CONTRACT_VERSION,
            surface_digest=DigestRef("sha256:" + "00" * 32),
            surface_id=request.surface_id,
            direction=facts.direction,
            comparison_digest=facts.comparison_digest,
            comparison_mode=facts.comparison_mode,
            project_identity_status=request.identity_annotation.status,
            project_identity_assessment_digest=request.identity_annotation.assessment_digest,
            requires_submit_confirmation=request.requires_submit_confirmation,
            risk_evaluation_digest=(
                None if request.risk_report is None else request.risk_report.risk_evaluation_digest
            ),
            view=view,
            tables=table_tuple,
            projections=(),
            summary=summary,
            refs=SurfaceRootRefs(
                records_closure_ref=facts.records_ref,
                risk_report_ref=request.risk_report_ref,
                risk_annotation_closure_ref=request.risk_annotation_closure_ref,
                project_identity_assessment_ref=request.identity_annotation.assessment_ref,
                diagnostics_ref=request.diagnostics_ref,
            ),
            diagnostics=SurfaceDiagnostics(
                diagnostics_ref=request.diagnostics_ref,
                diagnostics_summary=root_diagnostics,
            ),
        )
        digest = compute_surface_digest(surface)
        surface = _replace_surface_digest(surface, digest)
        validate_surface_refs(surface)
        encoded = canonicalize_json_value(surface.to_document())
        if len(encoded) > limits.max_surface_json_bytes:
            raise _AssemblyError("SURFACE_JSON_BUDGET_EXCEEDED")
        checkpoint()
        return SurfaceAssemblyResult(
            status=SurfaceAssemblyStatus.READY,
            surface=surface,
            referenced_artifacts=_referenced_artifacts(surface),
            diagnostics=root_diagnostics,
        )
    except _Cancelled:
        return SurfaceAssemblyResult(
            status=SurfaceAssemblyStatus.CANCELLED,
            diagnostics=("SURFACE_ASSEMBLY_CANCELLED",),
        )
    except Exception as exc:
        return SurfaceAssemblyResult(
            status=SurfaceAssemblyStatus.FAILED,
            diagnostics=(str(exc) or type(exc).__name__,),
        )


def validate_surface(surface: ComparisonSurface) -> None:
    if type(surface) is not ComparisonSurface:
        raise TypeError("surface must be ComparisonSurface")
    validate_surface_refs(surface)
    expected = compute_surface_digest(surface)
    if expected != surface.surface_digest:
        raise ValueError("surface digest mismatch")


def validate_surface_artifacts(
    surface: ComparisonSurface,
    store: ArtifactStorePort,
) -> None:
    """Validate Surface-owned typed artifacts before Bundle publication."""

    validate_surface(surface)
    for table in surface.tables:
        content_ref = table.risk_refs.annotation_ref
        manifest_ref = table.risk_refs.annotation_manifest_ref
        if content_ref is None or manifest_ref is None:
            continue
        if content_ref.media_type != RISK_ANNOTATION_MEDIA_TYPE:
            raise ValueError("risk annotation content media type mismatch")
        if manifest_ref.media_type != RISK_ANNOTATION_MANIFEST_MEDIA_TYPE:
            raise ValueError("risk annotation manifest media type mismatch")
        content_bytes = store.locate(content_ref)
        manifest_bytes = store.locate(manifest_ref)
        if (
            len(content_bytes) != content_ref.size_bytes
            or raw_blob_digest(content_bytes) != content_ref.raw_sha256
        ):
            raise ValueError("risk annotation content integrity mismatch")
        if (
            len(manifest_bytes) != manifest_ref.size_bytes
            or raw_blob_digest(manifest_bytes) != manifest_ref.raw_sha256
        ):
            raise ValueError("risk annotation manifest integrity mismatch")
        validate_risk_annotation_documents(
            content_bytes,
            manifest_bytes,
            table_name=table.table_name,
            annotation_count=table.risk_refs.annotation_count,
            content_digest=content_ref.raw_sha256,
        )


class _AssemblyError(ValueError):
    pass


class _Cancelled(Exception):
    pass


def _replace_surface_digest(surface: ComparisonSurface, digest: DigestRef) -> ComparisonSurface:
    from dataclasses import replace

    return replace(surface, surface_digest=digest)


def _validate_records_closure(
    facts: ComparisonFacts, closure: ComparisonRecordsClosure | None
) -> None:
    if facts.comparison_mode is ComparisonMode.DATASET_REPLACEMENT:
        if closure is not None:
            raise _AssemblyError("REPLACEMENT_MUST_NOT_CARRY_RECORDS_CLOSURE")
        return
    if closure is None:
        if any(_requires_records(table) for table in facts.tables):
            raise _AssemblyError("REQUIRED_RECORDS_CLOSURE_MISSING")
        return
    if closure.comparison_digest != facts.comparison_digest:
        raise _AssemblyError("RECORDS_COMPARISON_DIGEST_MISMATCH")
    if closure.facts_core_digest != facts.facts_core_digest:
        raise _AssemblyError("RECORDS_FACTS_CORE_DIGEST_MISMATCH")
    if facts.records_ref is None:
        raise _AssemblyError("RECORDS_CLOSURE_UNBOUND")
    fact_names = {item.table_name for item in facts.tables}
    if any(item.table_name not in fact_names for item in closure.records):
        raise _AssemblyError("RECORDS_CLOSURE_UNKNOWN_TABLE")


def _validate_risk_inputs(
    facts: ComparisonFacts,
    report: RiskReport | None,
    closure: RiskAnnotationClosure | None,
) -> tuple[dict[str, RiskTableRisk], dict[str, RiskAnnotationClosureEntry]]:
    if report is None and closure is not None:
        raise _AssemblyError("RISK_CLOSURE_WITHOUT_REPORT")
    if report is None:
        return {}, {}
    if closure is None and any(item.annotation_ref is not None for item in report.tables):
        raise _AssemblyError("RISK_ANNOTATION_CLOSURE_MISSING")
    if closure is not None:
        if closure.comparison_digest != facts.comparison_digest:
            raise _AssemblyError("RISK_CLOSURE_COMPARISON_DIGEST_MISMATCH")
        if closure.risk_evaluation_digest != report.risk_evaluation_digest:
            raise _AssemblyError("RISK_CLOSURE_EVALUATION_DIGEST_MISMATCH")
    risk_by_name = {item.table_name: item for item in report.tables}
    if len(risk_by_name) != len(report.tables):
        raise _AssemblyError("RISK_REPORT_DUPLICATE_TABLE")
    fact_names = {item.table_name for item in facts.tables}
    if any(name not in fact_names for name in risk_by_name):
        raise _AssemblyError("RISK_REPORT_UNKNOWN_TABLE")
    entries = {} if closure is None else {item.table_name: item for item in closure.entries}
    if closure is not None and len(entries) != len(closure.entries):
        raise _AssemblyError("RISK_CLOSURE_DUPLICATE_TABLE")
    for name, risk in risk_by_name.items():
        entry = entries.get(name)
        if risk.annotation_ref is not None:
            if entry is None or entry.artifact is None:
                raise _AssemblyError(f"RISK_ANNOTATION_ENTRY_MISSING:{name}")
            if entry.artifact.content_ref != risk.annotation_ref:
                raise _AssemblyError(f"RISK_ANNOTATION_REF_MISMATCH:{name}")
    return risk_by_name, entries


def _requires_records(table: ComparisonTableFact) -> bool:
    if table.status in {ComparisonTableStatus.ADDED_TABLE, ComparisonTableStatus.DELETED_TABLE}:
        return False
    return (
        table.row_added_count > 0
        or table.row_deleted_count > 0
        or table.row_modified_count > 0
    )


def _project_table(
    facts: ComparisonFacts,
    table: ComparisonTableFact,
    artifact_entry: SurfaceArtifactIndexEntry | None,
    records_closure: ComparisonRecordsClosure | None,
    risk: object | None,
    risk_entry: object | None,
    risk_report_ref: ArtifactRef | None,
    *,
    keyless_fallback: bool = False,
) -> SurfaceTable:
    table_refs = SurfaceTableRefs() if artifact_entry is None else artifact_entry.table_refs
    records = _records_refs(table, records_closure)
    ordered = _ordered_extension(table, records_closure)
    ordered_unsupported = _ordered_unsupported(table)
    replacement = facts.comparison_mode is ComparisonMode.DATASET_REPLACEMENT
    change_kind, strategy, processing, replay = _display_projection(
        table, table_refs, records, replacement, ordered_unsupported
    )
    if table.content_changed and change_kind is SurfaceChangeKind.UNCHANGED:
        change_kind = SurfaceChangeKind.UPDATED
    if ordered_unsupported:
        change_kind = SurfaceChangeKind.DEGRADED
    display_name = _display_name(table)
    before_descriptor = table.before_descriptor
    current_descriptor = table.current_descriptor
    schema = None
    if table.schema_changes != type(table.schema_changes)():
        schema = SurfaceSchemaSummary.from_comparison(table.schema_changes)
    columns = _columns(current_descriptor or before_descriptor)
    replacement_summary = None
    if replacement:
        replacement_summary = SurfaceReplacementSummary(
            before=_replacement_side(before_descriptor),
            current=_replacement_side(current_descriptor),
        )
        schema = None
        records = SurfaceRecordsRefs()
    risk_refs = _risk_refs(risk, risk_entry, risk_report_ref)
    messages = list(table.diagnostics)
    if risk is not None:
        messages.extend(risk.diagnostics)  # type: ignore[attr-defined]
    if ordered_unsupported:
        messages.append("ORDERED_DIFF_UNSUPPORTED")
    if keyless_fallback:
        messages.append("KEYLESS_FALLBACK")
    diagnostics = SurfaceDiagnostics(
        diagnostics_ref=None if artifact_entry is None else artifact_entry.diagnostics_ref,
        diagnostics_summary=_stable_messages(messages),
    )
    compare_key = _compare_key(current_descriptor or before_descriptor)
    effective = () if replacement else (
        table.schema_changes.selected_columns
        or tuple(item.name for item in columns)
    )
    compare = SurfaceCompare(
        artifact_scope=None,
        compare_key_columns=compare_key,
        ignored_columns=(),
        effective_columns=effective,
    )
    return SurfaceTable(
        table_id=table.table_name,
        table_name=table.table_name,
        display_name=display_name,
        table_status=table.status,
        change_kind=change_kind,
        row_change_stats=SurfaceRowChangeStats(
            row_count_before=table.row_count_before,
            row_count_current=table.row_count_current,
            row_added_count=table.row_added_count,
            row_deleted_count=table.row_deleted_count,
            row_modified_count=table.row_modified_count,
            suppressed_added_count=table.suppressed_added_count,
            suppressed_deleted_count=table.suppressed_deleted_count,
        ),
        schema_summary=schema,
        columns=columns,
        table_refs=table_refs,
        records_refs=records,
        risk_refs=risk_refs,
        display=SurfaceDisplay(strategy, processing, replay),
        compare=compare,
        diagnostics=diagnostics,
        content_changed=table.content_changed,
        replacement_summary=replacement_summary,
        ordered_extension=ordered,
    )


def _display_projection(
    table: ComparisonTableFact,
    refs: SurfaceTableRefs,
    records: SurfaceRecordsRefs,
    replacement: bool,
    ordered_unsupported: bool,
) -> tuple[SurfaceChangeKind, SurfaceDisplayStrategy, SurfaceTableProcessingMode, SurfaceReplayGuarantee]:
    if replacement:
        if table.before_descriptor is not None and table.current_descriptor is not None:
            kind = SurfaceChangeKind.REPLACED
        elif table.current_descriptor is not None:
            kind = SurfaceChangeKind.ADDED
        else:
            kind = SurfaceChangeKind.DELETED
        return kind, SurfaceDisplayStrategy.REPLACEMENT_SIDE_BY_SIDE, SurfaceTableProcessingMode.DATASET_REPLACEMENT, SurfaceReplayGuarantee.EXACT
    if ordered_unsupported:
        return SurfaceChangeKind.DEGRADED, SurfaceDisplayStrategy.DEGRADED_NOTICE, SurfaceTableProcessingMode.DEGRADED, SurfaceReplayGuarantee.UNSUPPORTED
    mapping = {
        ComparisonTableStatus.UNCHANGED: (SurfaceChangeKind.UNCHANGED, SurfaceDisplayStrategy.SUMMARY_ONLY),
        ComparisonTableStatus.BUSINESS_EQUIVALENT: (SurfaceChangeKind.BUSINESS_EQUIVALENT, SurfaceDisplayStrategy.SUMMARY_ONLY),
        ComparisonTableStatus.ADDED_TABLE: (SurfaceChangeKind.ADDED, SurfaceDisplayStrategy.TABLE_BROWSE if refs.current_table_ref else SurfaceDisplayStrategy.SUMMARY_ONLY),
        ComparisonTableStatus.DELETED_TABLE: (SurfaceChangeKind.DELETED, SurfaceDisplayStrategy.RECORDS_ONLY if records.records_ref else SurfaceDisplayStrategy.SUMMARY_ONLY),
        ComparisonTableStatus.MODIFIED: (SurfaceChangeKind.UPDATED, SurfaceDisplayStrategy.CURRENT_WITH_RECORDS if refs.current_table_ref and records.records_ref else SurfaceDisplayStrategy.TABLE_BROWSE if refs.current_table_ref else SurfaceDisplayStrategy.RECORDS_ONLY if records.records_ref else SurfaceDisplayStrategy.SUMMARY_ONLY),
        ComparisonTableStatus.SCHEMA_CHANGED: (SurfaceChangeKind.SCHEMA_CHANGED, SurfaceDisplayStrategy.RECORDS_ONLY if records.records_ref else SurfaceDisplayStrategy.DEGRADED_NOTICE),
        ComparisonTableStatus.SCHEMA_ONLY_CHANGED: (SurfaceChangeKind.SCHEMA_CHANGED, SurfaceDisplayStrategy.RECORDS_ONLY if records.records_ref else SurfaceDisplayStrategy.DEGRADED_NOTICE),
        ComparisonTableStatus.DEGRADED: (SurfaceChangeKind.DEGRADED, SurfaceDisplayStrategy.DEGRADED_NOTICE),
    }
    kind, strategy = mapping[table.status]
    processing = SurfaceTableProcessingMode.DEGRADED if kind is SurfaceChangeKind.DEGRADED else SurfaceTableProcessingMode.SCHEMA_ONLY if kind is SurfaceChangeKind.SCHEMA_CHANGED else SurfaceTableProcessingMode.STANDARD
    replay = SurfaceReplayGuarantee.EXACT if refs.current_table_ref or refs.before_table_ref or records.records_ref else SurfaceReplayGuarantee.SUMMARY_ONLY
    return kind, strategy, processing, replay


def _records_refs(table: ComparisonTableFact, closure: ComparisonRecordsClosure | None) -> SurfaceRecordsRefs:
    if closure is None:
        return SurfaceRecordsRefs()
    candidates = [item for item in closure.records if item.table_name == table.table_name]
    standard = next((item for item in candidates if item.family is RecordsArtifactFamily.STANDARD), None)
    if standard is None:
        return SurfaceRecordsRefs()
    return SurfaceRecordsRefs(
        records_ref=standard.records_ref,
        records_manifest_ref=standard.records_manifest_ref,
        records_format=SurfaceRecordsFormat.PARQUET,
    )


def _ordered_extension(table: ComparisonTableFact, closure: ComparisonRecordsClosure | None) -> dict[str, object] | None:
    extension = table.ordered_extension
    if extension is None:
        return None
    ordered_entry = None
    if closure is not None:
        ordered_entry = next(
            (item for item in closure.records if item.table_name == table.table_name and item.family is RecordsArtifactFamily.ORDERED),
            None,
        )
    summary = extension.ordered_summary
    value: dict[str, object] = {
        "contract_version": extension.contract_version,
        "current_ordered_digest": None if extension.current_ordered_digest is None else extension.current_ordered_digest.value,
        "diagnostics": list(extension.diagnostics),
        "ordered_summary": {
            "degraded_count": summary.degraded_count,
            "position_changed_count": summary.position_changed_count,
            "row_added_count": summary.row_added_count,
            "row_deleted_count": summary.row_deleted_count,
            "row_modified_count": summary.row_modified_count,
            "row_moved_count": summary.row_moved_count,
        },
        "replay_guarantee": extension.replay_guarantee.value,
        "status": extension.status.value,
    }
    if extension.before_ordered_digest is not None:
        value["before_ordered_digest"] = extension.before_ordered_digest.value
    if extension.policy_digest is not None:
        value["policy_digest"] = extension.policy_digest.value
    if extension.table_processing_mode is not None:
        value["table_processing_mode"] = extension.table_processing_mode.value
    if ordered_entry is not None:
        value["ordered_records_ref"] = ordered_entry.records_ref
        value["ordered_records_manifest_ref"] = ordered_entry.records_manifest_ref
    return value


def _ordered_unsupported(table: ComparisonTableFact) -> bool:
    extension = table.ordered_extension
    if extension is not None and extension.status.value == "ORDERED_DEGRADED":
        return True
    return any("ORDERED_DIFF_UNSUPPORTED" in item for item in table.diagnostics)


def _risk_refs(
    risk: object | None,
    entry: object | None,
    report_ref: ArtifactRef | None,
) -> SurfaceRiskRefs:
    if risk is None:
        return SurfaceRiskRefs()
    annotation_ref = None
    manifest_ref = None
    if entry is not None and entry.artifact is not None:  # type: ignore[attr-defined]
        annotation_ref = entry.artifact.content_ref  # type: ignore[attr-defined]
        manifest_ref = entry.artifact.manifest_ref  # type: ignore[attr-defined]
    return SurfaceRiskRefs(
        risk_level=risk.risk_level,  # type: ignore[attr-defined]
        reason_codes=tuple(sorted(risk.reason_codes, key=lambda item: item.value)),  # type: ignore[attr-defined]
        annotation_count=risk.annotation_count,  # type: ignore[attr-defined]
        report_ref=report_ref,
        annotation_ref=annotation_ref,
        annotation_manifest_ref=manifest_ref,
    )


def _display_name(table: ComparisonTableFact) -> str:
    descriptor = table.current_descriptor or table.before_descriptor
    return table.table_name if descriptor is None else descriptor.display_table_name


def _columns(descriptor: object | None) -> tuple[SurfaceColumn, ...]:
    if descriptor is None:
        return ()
    return tuple(
        SurfaceColumn(
            name=item.name,
            display_name=item.display_name,
            scalar_type=item.scalar_type,
            nullable=item.nullable,
        )
        for item in sorted(descriptor.columns, key=lambda value: value.name)  # type: ignore[attr-defined]
    )


def _replacement_side(descriptor: object | None) -> SurfaceReplacementSide | None:
    if descriptor is None:
        return None
    return SurfaceReplacementSide(
        row_count=descriptor.row_count,  # type: ignore[attr-defined]
        columns=_columns(descriptor),
    )


def _compare_key(descriptor: object | None) -> tuple[str, ...]:
    if descriptor is None:
        return ()
    return tuple(sorted(descriptor.compare_key_columns))  # type: ignore[attr-defined]


def _stable_messages(messages: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(item for item in messages if item)))


def _referenced_artifacts(surface: ComparisonSurface) -> tuple[ArtifactRef, ...]:
    refs: dict[tuple[str, str], ArtifactRef] = {}
    for table in surface.tables:
        values: list[ArtifactRef | None] = [
            table.table_refs.before_table_ref,
            table.table_refs.current_table_ref,
            table.table_refs.browse_table_ref,
            table.records_refs.records_ref,
            table.records_refs.records_manifest_ref,
            table.risk_refs.report_ref,
            table.risk_refs.annotation_ref,
            table.risk_refs.annotation_manifest_ref,
            table.diagnostics.diagnostics_ref,
        ]
        if table.ordered_extension is not None:
            values.extend(
                item
                for key, item in table.ordered_extension.items()
                if key.endswith("_ref") and isinstance(item, ArtifactRef)
            )
        for ref in values:
            if ref is not None:
                refs[(ref.artifact_id, ref.raw_sha256.value)] = ref
    values = [
        surface.refs.records_closure_ref,
        surface.refs.risk_report_ref,
        surface.refs.risk_annotation_closure_ref,
        surface.refs.project_identity_assessment_ref,
        surface.refs.diagnostics_ref,
    ]
    for projection in surface.projections:
        values.extend((projection.projection_ref, projection.risk_summary_ref, projection.diagnostics_ref))
    for ref in values:
        if ref is not None:
            refs[(ref.artifact_id, ref.raw_sha256.value)] = ref
    return tuple(refs[key] for key in sorted(refs))
