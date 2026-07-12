from __future__ import annotations

from collections.abc import Mapping, Sequence
from time import perf_counter

from ....artifacts import ArtifactRef
from ....core.diagnostics import DiagnosticRecord
from ....formal_upload_benchmark import benchmark_elapsed_ms, log_formal_upload_benchmark_event
from ..models import ComparisonOrderedExtension, ComparisonTableFact, ComparisonTableStatus
from .classifier import OrderedDiffEngine
from .digest import build_ordered_table_digest
from .models import (
    OrderedReplayGuarantee,
    OrderedSemanticKind,
    OrderedTableCompareInput,
    OrderedTableCompareResult,
    OrderedTableProcessingMode,
)
from .policy import OrderedTablePolicy, build_ordered_table_policy, ordered_policy_value
from .records import write_ordered_records


def compare_ordered_table(comparison_input: OrderedTableCompareInput) -> OrderedTableCompareResult:
    if not isinstance(comparison_input, OrderedTableCompareInput):
        raise TypeError("comparison_input must be an OrderedTableCompareInput")

    diagnostics = list(comparison_input.diagnostics)
    projection_schema = comparison_input.projection_schema
    ordered_policy = comparison_input.ordered_policy or _build_default_policy(comparison_input)
    stable_key_field = _stable_key_field(ordered_policy)
    position_field = _position_field(ordered_policy)
    if stable_key_field is None:
        return _degraded_result(
            comparison_input=comparison_input,
            diagnostics=tuple(diagnostics),
            reason="ORDERED_STABLE_KEY_MISSING",
            ordered_policy=ordered_policy,
        )
    if position_field is None:
        return _degraded_result(
            comparison_input=comparison_input,
            diagnostics=tuple(diagnostics),
            reason="ORDERED_POSITION_FIELD_MISSING",
            ordered_policy=ordered_policy,
        )

    before_table = comparison_input.before_table
    current_table = comparison_input.current_table
    read_started_at = perf_counter()
    (
        before_rows,
        before_columns,
        after_rows,
        after_columns,
        ordered_input_source,
    ) = _ordered_rows_and_columns(
        comparison_input=comparison_input,
        stable_key_field=stable_key_field,
        position_field=position_field,
    )
    _log_ordered_phase(
        comparison_input=comparison_input,
        phase_payload={
            "phase": "read_rows",
            "ordered_input_source": ordered_input_source,
            "row_count_before": len(before_rows),
            "row_count_current": len(after_rows),
            "column_count_before": len(before_columns),
            "column_count_current": len(after_columns),
            "duration_ms": benchmark_elapsed_ms(read_started_at),
        },
    )
    if not before_columns and not after_columns:
        return _degraded_result(
            comparison_input=comparison_input,
            diagnostics=tuple(diagnostics),
            reason="READER_MISSING",
            ordered_policy=ordered_policy,
        )
    if not before_columns:
        before_columns = after_columns
    if not after_columns:
        after_columns = before_columns

    diagnostics.append(
        DiagnosticRecord(
            code="comparison.ordered.compare",
            message="ordered provider is active",
            phase="compare",
            severity="INFO",
            details={
                "table_name": comparison_input.table_name,
                "provider": "ORDERED_TABLE_COMPARE",
                "ordered_policy_digest": (
                    ordered_policy.policy_digest.to_payload()
                    if ordered_policy.policy_digest is not None
                    else None
                ),
            },
        )
    )

    engine = OrderedDiffEngine()
    before_prepare_cache_key = _ordered_prepare_cache_key(
        projection=comparison_input.before_projection,
        table=comparison_input.before_table,
        rows=before_rows,
        columns=before_columns,
        side="before",
        stable_key_field=stable_key_field,
        position_field=position_field,
        pseudo_key_start=int(ordered_policy_value(ordered_policy, "pseudo_key_start", 2_000_000_000) or 2_000_000_000),
    )
    current_prepare_cache_key = _ordered_prepare_cache_key(
        projection=comparison_input.current_projection,
        table=comparison_input.current_table,
        rows=after_rows,
        columns=after_columns,
        side="after",
        stable_key_field=stable_key_field,
        position_field=position_field,
        pseudo_key_start=int(ordered_policy_value(ordered_policy, "pseudo_key_start", 2_000_000_000) or 2_000_000_000),
    )
    ordered_result = engine.compare(
        table_name=comparison_input.table_name,
        before_rows=before_rows,
        before_columns=before_columns,
        after_rows=after_rows,
        after_columns=after_columns,
        stable_key_field=stable_key_field,
        position_field=position_field,
        pseudo_key_start=int(ordered_policy_value(ordered_policy, "pseudo_key_start", 2_000_000_000) or 2_000_000_000),
        ordered_policy_digest=ordered_policy.policy_digest,
        diagnostics=tuple(diagnostics),
        prepared_rows_cache=comparison_input.prepared_rows_cache,
        before_prepare_cache_key=before_prepare_cache_key,
        current_prepare_cache_key=current_prepare_cache_key,
    )
    for phase_payload in ordered_result.benchmark_phase_events:
        _log_ordered_phase(
            comparison_input=comparison_input,
            phase_payload=phase_payload,
            planner_mode=ordered_result.planner_mode,
            degrade_reason=ordered_result.degrade_reason,
            ordered_input_source=ordered_input_source,
        )

    before_descriptor = comparison_input.before_descriptor
    current_descriptor = comparison_input.current_descriptor
    row_counts = comparison_input.row_counts or _row_counts(before_table, current_table)
    before_projection_logical_digest = (
        None
        if comparison_input.before_projection is None
        else comparison_input.before_projection.projection_logical_digest
    )
    current_projection_logical_digest = (
        None
        if comparison_input.current_projection is None
        else comparison_input.current_projection.projection_logical_digest
    )
    schema_changes = _schema_changes_payload(
        projection_schema=projection_schema,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
    )

    status = _table_status_for_result(
        comparison_input=comparison_input,
        ordered_result=ordered_result,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        before_projection_logical_digest=before_projection_logical_digest,
        current_projection_logical_digest=current_projection_logical_digest,
    )

    records_ref = None
    records_artifact = None
    records_write_started_at = perf_counter()
    if ordered_result.records and ordered_result.degrade_reason is None:
        records_ref, records_artifact = write_ordered_records(
            table_name=comparison_input.table_name,
            records=ordered_result.records,
            comparison_contract_version=comparison_input.comparison_contract_version,
            projection_contract_version=comparison_input.projection_contract_version,
            table_ruleset_version=comparison_input.table_ruleset_version,
            scalar_encoding_version=comparison_input.scalar_encoding_version,
            row_diff_detail_policy=comparison_input.row_diff_detail_policy,
            ordered_policy_digest=ordered_policy.policy_digest,
            ordered_preprocess_applied=ordered_result.ordered_preprocess_applied,
            replay_guarantee=ordered_result.replay_guarantee.value,
            table_processing_mode=ordered_result.table_processing_mode.value,
            ordered_summary=ordered_result.summary,
            before_ordered_digest=ordered_result.before_ordered_digest,
            current_ordered_digest=ordered_result.current_ordered_digest,
            diagnostics=ordered_result.diagnostics,
            records_store=comparison_input.records_store,
        )
    _log_ordered_phase(
        comparison_input=comparison_input,
        phase_payload={
            "phase": "records_write",
            "records_count": len(ordered_result.records),
            "records_artifact": records_artifact is not None,
            "skipped": not bool(ordered_result.records and ordered_result.degrade_reason is None),
            "duration_ms": benchmark_elapsed_ms(records_write_started_at),
        },
        planner_mode=ordered_result.planner_mode,
        degrade_reason=ordered_result.degrade_reason,
    )

    table_fact = ComparisonTableFact(
        table_name=comparison_input.table_name,
        status=status,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        projection_schema=projection_schema,
        projection_schema_digest=projection_schema.projection_schema_digest if projection_schema is not None else None,
        before_projection_logical_digest=before_projection_logical_digest,
        current_projection_logical_digest=current_projection_logical_digest,
        row_counts=row_counts,
        schema_changes=schema_changes,
        records_ref=records_ref,
        ordered_extension=_build_ordered_extension(
            ordered_policy_digest=ordered_policy.policy_digest,
            ordered_result=ordered_result,
            records_ref=records_ref,
            stable_key_field=stable_key_field,
            position_field=position_field,
        ),
        diagnostics=ordered_result.diagnostics,
    )
    return OrderedTableCompareResult(
        table_fact=table_fact,
        ordered_summary=ordered_result.summary,
        before_ordered_digest=ordered_result.before_ordered_digest,
        current_ordered_digest=ordered_result.current_ordered_digest,
        records=ordered_result.records,
        records_ref=records_ref,
        records_artifact=records_artifact,
        replay_validation=ordered_result.replay_validation,
        replay_guarantee=ordered_result.replay_guarantee,
        table_processing_mode=ordered_result.table_processing_mode,
        ordered_preprocess_applied=ordered_result.ordered_preprocess_applied,
        diagnostics=ordered_result.diagnostics,
        degrade_reason=ordered_result.degrade_reason,
        planner_mode=ordered_result.planner_mode,
        prepared_row_count_before=ordered_result.prepared_row_count_before,
        prepared_row_count_current=ordered_result.prepared_row_count_current,
        ordered_input_source=ordered_input_source,
        benchmark_phase_events=ordered_result.benchmark_phase_events,
    )


def _build_ordered_extension(
    *,
    ordered_policy_digest: DigestRef | str | None,
    ordered_result: OrderedTableCompareResult,
    records_ref: ArtifactRef | None,
    stable_key_field: str,
    position_field: str,
) -> ComparisonOrderedExtension:
    return ComparisonOrderedExtension(
        ordered_policy_digest=ordered_policy_digest,
        before_ordered_digest=ordered_result.before_ordered_digest,
        current_ordered_digest=ordered_result.current_ordered_digest,
        stable_key_field=stable_key_field,
        position_field=position_field,
        ordered_summary=(
            None if ordered_result.summary is None else ordered_result.summary.to_payload()
        ),
        ordered_records_ref=records_ref,
        replay_guarantee=ordered_result.replay_guarantee.value,
        table_processing_mode=ordered_result.table_processing_mode.value,
        ordered_preprocess_applied=ordered_result.ordered_preprocess_applied,
        diagnostics=ordered_result.diagnostics,
    )


def _build_default_policy(comparison_input: OrderedTableCompareInput) -> OrderedTablePolicy:
    projection_schema = comparison_input.projection_schema
    before_columns = tuple(
        column_name for column_name in _descriptor_columns(comparison_input.before_descriptor)
    )
    current_columns = tuple(
        column_name for column_name in _descriptor_columns(comparison_input.current_descriptor)
    )
    selected_columns = (
        tuple(projection_schema.selected_columns)
        if projection_schema is not None
        else tuple(column for column in before_columns if column in current_columns or not current_columns)
    )
    stable_key_candidates = (
        tuple(projection_schema.effective_compare_key)
        if projection_schema is not None and projection_schema.effective_compare_key
        else tuple(_descriptor_compare_key(comparison_input.before_descriptor) or _descriptor_compare_key(comparison_input.current_descriptor))
    )
    row_identity_key = stable_key_candidates[0] if stable_key_candidates else None
    return build_ordered_table_policy(
        table_name=comparison_input.table_name,
        row_identity_key=row_identity_key,
        stable_key_candidates=stable_key_candidates,
        order_key="no",
        ignored_columns=projection_schema.ignored_columns if projection_schema is not None else (),
        value_columns=selected_columns,
        blank_row_policy="PSEUDO_BLANK_BY_MISSING_STABLE_KEY",
        pseudo_key_start=2_000_000_000,
        move_policy="IDENTITY_POSITION_CHANGE",
    )


def _degraded_result(
    *,
    comparison_input: OrderedTableCompareInput,
    diagnostics: tuple[DiagnosticRecord, ...],
    reason: str,
    ordered_policy: OrderedTablePolicy,
) -> OrderedTableCompareResult:
    diagnostics = diagnostics + (
        DiagnosticRecord(
            code="comparison.ordered.degraded",
            message="ordered provider degraded",
            phase="compare",
            severity="WARNING",
            details={
                "table_name": comparison_input.table_name,
                "provider": "ORDERED_TABLE_COMPARE",
                "reason": reason,
                "ordered_policy_digest": (
                    ordered_policy.policy_digest.to_payload()
                    if ordered_policy.policy_digest is not None
                    else None
                ),
            },
        ),
    )
    table_fact = ComparisonTableFact(
        table_name=comparison_input.table_name,
        status=ComparisonTableStatus.DEGRADED,
        before_descriptor=comparison_input.before_descriptor,
        current_descriptor=comparison_input.current_descriptor,
        projection_schema=comparison_input.projection_schema,
        projection_schema_digest=(
            comparison_input.projection_schema.projection_schema_digest
            if comparison_input.projection_schema is not None
            else None
        ),
        row_counts=comparison_input.row_counts,
        schema_changes=_schema_changes_payload(
            projection_schema=comparison_input.projection_schema,
            before_descriptor=comparison_input.before_descriptor,
            current_descriptor=comparison_input.current_descriptor,
        ),
        ordered_extension=ComparisonOrderedExtension(
            ordered_policy_digest=ordered_policy.policy_digest,
            ordered_summary=None,
            ordered_records_ref=None,
            replay_guarantee=OrderedReplayGuarantee.UNSUPPORTED.value,
            table_processing_mode=OrderedTableProcessingMode.DEGRADED.value,
            ordered_preprocess_applied="NONE",
            diagnostics=diagnostics,
        ),
        diagnostics=diagnostics,
    )
    return OrderedTableCompareResult(
        table_fact=table_fact,
        ordered_summary=None,
        records=(),
        records_ref=None,
        records_artifact=None,
        replay_guarantee=OrderedReplayGuarantee.UNSUPPORTED,
        table_processing_mode=OrderedTableProcessingMode.DEGRADED,
        ordered_preprocess_applied="NONE",
        diagnostics=diagnostics,
        degrade_reason=reason,
        benchmark_phase_events=(
            {
                "phase": "degraded_precheck",
                "degrade_reason": reason,
                "duration_ms": 0,
            },
        ),
    )


def _log_ordered_phase(
    *,
    comparison_input: OrderedTableCompareInput,
    phase_payload: Mapping[str, object],
    planner_mode: str | None = None,
    degrade_reason: str | None = None,
    ordered_input_source: str | None = None,
) -> None:
    payload = dict(phase_payload)
    if planner_mode is not None:
        payload.setdefault("planner_mode", planner_mode)
    if degrade_reason is not None:
        payload.setdefault("degrade_reason", degrade_reason)
    if ordered_input_source is not None:
        payload.setdefault("ordered_input_source", ordered_input_source)
    log_formal_upload_benchmark_event(
        "comparison_core.ordered_provider.phase",
        benchmark_run_id=comparison_input.benchmark_run_id,
        table_name=comparison_input.table_name,
        **payload,
    )


def _table_status_for_result(
    *,
    comparison_input: OrderedTableCompareInput,
    ordered_result,
    before_descriptor: Mapping[str, object] | None,
    current_descriptor: Mapping[str, object] | None,
    before_projection_logical_digest,
    current_projection_logical_digest,
) -> ComparisonTableStatus:
    if ordered_result.degrade_reason is not None:
        return ComparisonTableStatus.DEGRADED
    if comparison_input.before_table is None and comparison_input.current_table is not None:
        return ComparisonTableStatus.ADDED_TABLE
    if comparison_input.before_table is not None and comparison_input.current_table is None:
        return ComparisonTableStatus.DELETED_TABLE
    if not ordered_result.records:
        if (
            before_projection_logical_digest is not None
            and current_projection_logical_digest is not None
            and before_projection_logical_digest == current_projection_logical_digest
        ):
            if (
                before_descriptor is not None
                and current_descriptor is not None
                and before_descriptor.get("raw_content_digest") != current_descriptor.get("raw_content_digest")
            ):
                return ComparisonTableStatus.BUSINESS_EQUIVALENT
            return ComparisonTableStatus.UNCHANGED
        return ComparisonTableStatus.UNCHANGED
    return ComparisonTableStatus.MODIFIED


def _schema_changes_payload(
    *,
    projection_schema,
    before_descriptor: Mapping[str, object] | None,
    current_descriptor: Mapping[str, object] | None,
) -> Mapping[str, object]:
    return {
        "before_only_columns": list(getattr(projection_schema, "before_only_columns", ())) if projection_schema is not None else [],
        "current_only_columns": list(getattr(projection_schema, "current_only_columns", ())) if projection_schema is not None else [],
        "selected_columns": list(getattr(projection_schema, "selected_columns", ())) if projection_schema is not None else [],
        "effective_compare_key_before": list(_descriptor_compare_key(before_descriptor)),
        "effective_compare_key_current": list(_descriptor_compare_key(current_descriptor)),
        "effective_compare_key_changed": _descriptor_compare_key(before_descriptor) != _descriptor_compare_key(current_descriptor),
    }


def _descriptor_compare_key(descriptor: Mapping[str, object] | None) -> tuple[str, ...]:
    if descriptor is None:
        return ()
    compare_key_columns = descriptor.get("compare_key_columns")
    if not isinstance(compare_key_columns, Sequence):
        return ()
    return tuple(str(column) for column in compare_key_columns if str(column).strip())


def _descriptor_columns(descriptor: Mapping[str, object] | None) -> tuple[str, ...]:
    if descriptor is None:
        return ()
    columns = descriptor.get("columns")
    if not isinstance(columns, Sequence):
        return ()
    result: list[str] = []
    for column in columns:
        name = getattr(column, "name", None)
        if isinstance(column, Mapping):
            name = column.get("name")
        if isinstance(name, str) and name.strip():
            result.append(name.lower())
    return tuple(result)


def _rows_and_columns(
    table,
) -> tuple[tuple[tuple[object, ...], ...], tuple[str, ...]]:
    if table is None:
        return (), ()
    descriptor = table.descriptor
    columns = tuple(column.name for column in descriptor.columns)
    rows = tuple(tuple(row) for row in table.reader.iter_rows())
    return rows, columns


def _ordered_rows_and_columns(
    *,
    comparison_input: OrderedTableCompareInput,
    stable_key_field: str,
    position_field: str,
) -> tuple[
    tuple[tuple[object, ...], ...],
    tuple[str, ...],
    tuple[tuple[object, ...], ...],
    tuple[str, ...],
    str,
]:
    if _can_use_projection_rows(
        projection=comparison_input.before_projection,
        table_present=comparison_input.before_table is not None,
        stable_key_field=stable_key_field,
        position_field=position_field,
    ) and _can_use_projection_rows(
        projection=comparison_input.current_projection,
        table_present=comparison_input.current_table is not None,
        stable_key_field=stable_key_field,
        position_field=position_field,
    ):
        before_rows, before_columns = _projection_rows_and_columns(comparison_input.before_projection)
        after_rows, after_columns = _projection_rows_and_columns(comparison_input.current_projection)
        return before_rows, before_columns, after_rows, after_columns, "projection"

    before_rows, before_columns = _table_rows_and_columns(comparison_input.before_table)
    after_rows, after_columns = _table_rows_and_columns(comparison_input.current_table)
    return before_rows, before_columns, after_rows, after_columns, "raw_table_fallback"


def _can_use_projection_rows(
    *,
    projection,
    table_present: bool,
    stable_key_field: str,
    position_field: str,
) -> bool:
    if not table_present:
        return True
    if projection is None:
        return False
    columns = {
        str(column).lower()
        for column in getattr(projection.projection_schema, "selected_columns", ())
    }
    return stable_key_field.lower() in columns and position_field.lower() in columns


def _projection_rows_and_columns(
    projection,
) -> tuple[tuple[tuple[object, ...], ...], tuple[str, ...]]:
    if projection is None:
        return (), ()
    columns = tuple(str(column) for column in projection.projection_schema.selected_columns)
    rows = tuple(tuple(row) for row in projection.reader.iter_rows())
    return rows, columns


def _ordered_prepare_cache_key(
    *,
    projection,
    table,
    rows: Sequence[Sequence[object] | Mapping[str, object]],
    columns: Sequence[str],
    side: str,
    stable_key_field: str,
    position_field: str,
    pseudo_key_start: int,
) -> tuple[object, ...] | None:
    if table is None:
        return None
    descriptor = table.descriptor
    if descriptor.fast_row_digest is None:
        return None
    if projection is None:
        return None
    projection_schema = projection.projection_schema
    return (
        "ordered_prepare",
        side,
        descriptor.fast_row_digest.to_payload(),
        tuple(
            (
                column.name,
                column.scalar_type,
                column.nullable,
            )
            for column in descriptor.columns
        ),
        descriptor.row_count,
        descriptor.row_materialization_profile,
        descriptor.scalar_encoding_version,
        tuple(str(column) for column in columns),
        tuple(str(column) for column in getattr(projection_schema, "selected_columns", ())),
        getattr(projection_schema, "projection_contract_version", None),
        getattr(projection_schema, "scalar_encoding_version", None),
        stable_key_field,
        position_field,
        pseudo_key_start,
        len(rows),
    )


def _table_rows_and_columns(
    table,
) -> tuple[tuple[tuple[object, ...], ...], tuple[str, ...]]:
    return _rows_and_columns(table)


def _row_counts(before_table, current_table) -> tuple[int | None, int | None] | None:
    before_count = None if before_table is None else before_table.descriptor.row_count
    current_count = None if current_table is None else current_table.descriptor.row_count
    if before_count is None and current_count is None:
        return None
    return before_count, current_count


def _stable_key_field(ordered_policy: OrderedTablePolicy) -> str | None:
    row_identity_key = ordered_policy.payload.get("row_identity_key")
    if isinstance(row_identity_key, str) and row_identity_key.strip():
        return row_identity_key
    stable_key_candidates = ordered_policy.payload.get("stable_key_candidates")
    if isinstance(stable_key_candidates, Sequence):
        for candidate in stable_key_candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate
    return None


def _position_field(ordered_policy: OrderedTablePolicy) -> str | None:
    order_key = ordered_policy.payload.get("order_key")
    if isinstance(order_key, str) and order_key.strip():
        return order_key
    return None


__all__ = [
    "compare_ordered_table",
]
