from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from ....core.digests import DigestRef, canonical_json_bytes
from ....core.diagnostics import DiagnosticRecord
from ....formal_upload_benchmark import benchmark_elapsed_ms
from .digest import (
    OrderedRowsDigestParts,
    build_ordered_rows_digest,
    build_ordered_rows_digest_from_parts,
    build_ordered_rows_digest_parts,
)
from .models import (
    OrderedEntityKeyKind,
    OrderedPreparedRowsCache,
    OrderedPreparedRowsCacheEntry,
    OrderedPreparedRow,
    OrderedRecord,
    OrderedRecordKind,
    OrderedReplayGuarantee,
    OrderedReplayValidation,
    OrderedSemanticKind,
    OrderedSemanticOp,
    OrderedSummary,
    OrderedTableProcessingMode,
)
from .preparation import OrderedPreparationError, prepare_ordered_rows
from .records import ordered_record_sort_key
from .replay import validate_ordered_replay
from .topology_planner import _OrderedTopologyPlanner, _Prescan, _TopologyCore, PLANNER_MODE_INPUT_INVALID


ORDERED_PREPROCESS_NONE = "NONE"
ORDERED_PREPROCESS_BLANK_GID_FILLED = "BLANK_GID_FILLED"


@dataclass(frozen=True, slots=True)
class _OrderedDiffResult:
    records: tuple[OrderedRecord, ...]
    summary: OrderedSummary
    replay_validation: OrderedReplayValidation
    replay_guarantee: OrderedReplayGuarantee
    table_processing_mode: OrderedTableProcessingMode
    ordered_preprocess_applied: str
    degrade_reason: str | None
    before_ordered_digest: DigestRef | None
    current_ordered_digest: DigestRef | None
    diagnostics: tuple[DiagnosticRecord, ...]
    semantic_ops: tuple[OrderedSemanticOp, ...]
    benchmark_phase_events: tuple[Mapping[str, object], ...] = ()
    planner_mode: str | None = None
    prepared_row_count_before: int | None = None
    prepared_row_count_current: int | None = None

    @property
    def exact(self) -> bool:
        return (
            self.replay_guarantee is OrderedReplayGuarantee.EXACT
            and self.replay_validation.semantic_replay_passed
            and self.replay_validation.artifact_replay_passed
            and self.degrade_reason is None
        )


def _phase_event(phase: str, started_at: float, **fields: object) -> Mapping[str, object]:
    return {
        "phase": phase,
        **{key: value for key, value in fields.items() if value is not None},
        "duration_ms": benchmark_elapsed_ms(started_at),
    }


def _prescan_benchmark_counts(prescan_summary: Mapping[str, object]) -> dict[str, object]:
    return {
        "shared_real_count": prescan_summary.get("shared_real_count"),
        "inserted_real_count": prescan_summary.get("inserted_real_count"),
        "deleted_real_count": prescan_summary.get("deleted_real_count"),
        "content_changed_count": prescan_summary.get("content_changed_count"),
        "position_changed_count": prescan_summary.get("position_changed_count"),
        "old_common_order_equals_new_common_order": prescan_summary.get(
            "old_common_order_equals_new_common_order"
        ),
    }


def _semantic_op_counts_by_kind(
    semantic_ops: Sequence[OrderedSemanticOp],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for op in semantic_ops:
        key = op.semantic_kind.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def _ordered_digest_for_side(
    *,
    table_name: str,
    rows: Sequence[OrderedPreparedRow],
    columns: Sequence[str],
    stable_key_field: str,
    position_field: str,
    ordered_policy_digest: DigestRef | None,
    side: str,
    prepared_rows_cache: OrderedPreparedRowsCache | None,
    prepare_cache_key: tuple[object, ...] | None,
    cache_entry: OrderedPreparedRowsCacheEntry | None,
) -> tuple[DigestRef, bool, bool]:
    digest_parts = None if cache_entry is None else cache_entry.ordered_digest_parts
    if isinstance(digest_parts, OrderedRowsDigestParts):
        return (
            build_ordered_rows_digest_from_parts(
                table_name=table_name,
                digest_parts=digest_parts,
            ),
            True,
            False,
        )

    computed_parts = build_ordered_rows_digest_parts(
        rows=rows,
        columns=columns,
        stable_key_field=stable_key_field,
        position_field=position_field,
        ordered_policy_digest=ordered_policy_digest,
        side=side,
    )
    if prepared_rows_cache is not None:
        prepared_rows_cache.write_ordered_digest_parts(
            key=prepare_cache_key,
            digest_parts=computed_parts,
        )
    return (
        build_ordered_rows_digest_from_parts(
            table_name=table_name,
            digest_parts=computed_parts,
        ),
        False,
        cache_entry is not None,
    )


class OrderedDiffEngine:
    def __init__(
        self,
        *,
        max_backbone_candidates: int = 2048,
        small_core_threshold: int = 512,
        large_core_threshold: int = 5000,
        planner_step_budget: int = 1_000_000,
        planner_time_budget_ms: int = 1000,
    ) -> None:
        self._max_backbone_candidates = max_backbone_candidates
        self._small_core_threshold = small_core_threshold
        self._large_core_threshold = large_core_threshold
        self._planner_step_budget = planner_step_budget
        self._planner_time_budget_ms = planner_time_budget_ms

    def compare(
        self,
        *,
        table_name: str,
        before_rows: Sequence[Sequence[object] | Mapping[str, object]],
        before_columns: Sequence[str],
        after_rows: Sequence[Sequence[object] | Mapping[str, object]],
        after_columns: Sequence[str],
        stable_key_field: str,
        position_field: str,
        pseudo_key_start: int = 2_000_000_000,
        ordered_policy_digest: DigestRef | None = None,
        diagnostics: tuple[DiagnosticRecord, ...] = (),
        prepared_rows_cache: OrderedPreparedRowsCache | None = None,
        before_prepare_cache_key: tuple[object, ...] | None = None,
        current_prepare_cache_key: tuple[object, ...] | None = None,
    ) -> _OrderedDiffResult:
        prepared_before: list[OrderedPreparedRow] = []
        prepared_after: list[OrderedPreparedRow] = []
        diagnostics_list = list(diagnostics)
        phase_events: list[Mapping[str, object]] = []
        phase_started_at = perf_counter()
        before_cache_entry = (
            None
            if prepared_rows_cache is None
            else prepared_rows_cache.lookup(before_prepare_cache_key)
        )
        current_cache_entry = (
            None
            if prepared_rows_cache is None
            else prepared_rows_cache.lookup(current_prepare_cache_key)
        )
        try:
            if before_cache_entry is None:
                prepared_before = list(
                    prepare_ordered_rows(
                        rows=before_rows,
                        columns=before_columns,
                        stable_key_field=stable_key_field,
                        position_field=position_field,
                        pseudo_key_start=pseudo_key_start,
                        side="before",
                    )
                )
                if prepared_rows_cache is not None:
                    prepared_rows_cache.write(
                        key=before_prepare_cache_key,
                        source_table_name=table_name,
                        rows=prepared_before,
                    )
            else:
                prepared_before = list(before_cache_entry.rows)
            if current_cache_entry is None:
                prepared_after = list(
                    prepare_ordered_rows(
                        rows=after_rows,
                        columns=after_columns,
                        stable_key_field=stable_key_field,
                        position_field=position_field,
                        pseudo_key_start=pseudo_key_start,
                        side="after",
                    )
                )
                if prepared_rows_cache is not None:
                    prepared_rows_cache.write(
                        key=current_prepare_cache_key,
                        source_table_name=table_name,
                        rows=prepared_after,
                    )
            else:
                prepared_after = list(current_cache_entry.rows)
        except OrderedPreparationError as exc:
            phase_events.append(
                _phase_event(
                    "prepare_rows",
                    phase_started_at,
                    row_count_before=len(before_rows),
                    row_count_current=len(after_rows),
                    column_count_before=len(before_columns),
                    column_count_current=len(after_columns),
                    prepared_row_count_before=len(prepared_before),
                    prepared_row_count_current=len(prepared_after),
                    prepared_cache_hit_before=before_cache_entry is not None,
                    prepared_cache_hit_current=current_cache_entry is not None,
                    prepared_cache_eligible_before=before_prepare_cache_key is not None,
                    prepared_cache_eligible_current=current_prepare_cache_key is not None,
                    prepared_cache_source_table_before=(
                        None if before_cache_entry is None else before_cache_entry.source_table_name
                    ),
                    prepared_cache_source_table_current=(
                        None if current_cache_entry is None else current_cache_entry.source_table_name
                    ),
                    prepared_cache_saved_row_count=(
                        (0 if before_cache_entry is None else len(before_cache_entry.rows))
                        + (0 if current_cache_entry is None else len(current_cache_entry.rows))
                    ),
                    degrade_reason=exc.reason,
                )
            )
            return self._input_degraded_result(
                stable_key_field=stable_key_field,
                position_field=position_field,
                degrade_reason=exc.reason,
                diagnostics=tuple(diagnostics_list),
                table_name=table_name,
                ordered_policy_digest=ordered_policy_digest,
                before_rows=before_rows,
                before_columns=before_columns,
                after_rows=after_rows,
                after_columns=after_columns,
                pseudo_key_start=pseudo_key_start,
                benchmark_phase_events=tuple(phase_events),
            )
        phase_events.append(
            _phase_event(
                "prepare_rows",
                phase_started_at,
                row_count_before=len(before_rows),
                row_count_current=len(after_rows),
                column_count_before=len(before_columns),
                column_count_current=len(after_columns),
                prepared_row_count_before=len(prepared_before),
                prepared_row_count_current=len(prepared_after),
                prepared_cache_hit_before=before_cache_entry is not None,
                prepared_cache_hit_current=current_cache_entry is not None,
                prepared_cache_eligible_before=before_prepare_cache_key is not None,
                prepared_cache_eligible_current=current_prepare_cache_key is not None,
                prepared_cache_source_table_before=(
                    None if before_cache_entry is None else before_cache_entry.source_table_name
                ),
                prepared_cache_source_table_current=(
                    None if current_cache_entry is None else current_cache_entry.source_table_name
                ),
                prepared_cache_saved_row_count=(
                    (0 if before_cache_entry is None else len(before_cache_entry.rows))
                    + (0 if current_cache_entry is None else len(current_cache_entry.rows))
                ),
            )
        )

        phase_started_at = perf_counter()
        (
            before_ordered_digest,
            before_digest_parts_reused,
            before_digest_recompute_fallback,
        ) = _ordered_digest_for_side(
            table_name=table_name,
            rows=prepared_before,
            columns=before_columns,
            stable_key_field=stable_key_field,
            position_field=position_field,
            ordered_policy_digest=ordered_policy_digest,
            side="before",
            prepared_rows_cache=prepared_rows_cache,
            prepare_cache_key=before_prepare_cache_key,
            cache_entry=before_cache_entry,
        )
        (
            current_ordered_digest,
            current_digest_parts_reused,
            current_digest_recompute_fallback,
        ) = _ordered_digest_for_side(
            table_name=table_name,
            rows=prepared_after,
            columns=after_columns,
            stable_key_field=stable_key_field,
            position_field=position_field,
            ordered_policy_digest=ordered_policy_digest,
            side="current",
            prepared_rows_cache=prepared_rows_cache,
            prepare_cache_key=current_prepare_cache_key,
            cache_entry=current_cache_entry,
        )
        ordered_digest_saved_row_count = (
            (len(prepared_before) if before_digest_parts_reused else 0)
            + (len(prepared_after) if current_digest_parts_reused else 0)
        )
        if prepared_rows_cache is not None:
            if before_digest_parts_reused:
                prepared_rows_cache.ordered_digest_parts_reuse_count += 1
                prepared_rows_cache.ordered_digest_parts_saved_row_count += len(prepared_before)
            if current_digest_parts_reused:
                prepared_rows_cache.ordered_digest_parts_reuse_count += 1
                prepared_rows_cache.ordered_digest_parts_saved_row_count += len(prepared_after)
            if before_digest_recompute_fallback:
                prepared_rows_cache.ordered_digest_parts_fallback_count += 1
            if current_digest_recompute_fallback:
                prepared_rows_cache.ordered_digest_parts_fallback_count += 1
        phase_events.append(
            _phase_event(
                "ordered_digest",
                phase_started_at,
                prepared_row_count_before=len(prepared_before),
                prepared_row_count_current=len(prepared_after),
                column_count_before=len(before_columns),
                column_count_current=len(after_columns),
                ordered_digest_parts_reused_before=before_digest_parts_reused,
                ordered_digest_parts_reused_current=current_digest_parts_reused,
                ordered_digest_wrapper_only_before=before_digest_parts_reused,
                ordered_digest_wrapper_only_current=current_digest_parts_reused,
                ordered_digest_recompute_fallback_before=before_digest_recompute_fallback,
                ordered_digest_recompute_fallback_current=current_digest_recompute_fallback,
                ordered_digest_saved_row_count=ordered_digest_saved_row_count,
            )
        )

        phase_started_at = perf_counter()
        prescan = self._prescan(
            prepared_before=prepared_before,
            prepared_after=prepared_after,
            stable_key_field=stable_key_field,
            position_field=position_field,
        )
        prescan_summary = self._prescan_summary(prescan)
        phase_events.append(
            _phase_event(
                "prescan",
                phase_started_at,
                **_prescan_benchmark_counts(prescan_summary),
            )
        )
        topology_planner = _OrderedTopologyPlanner(
            max_backbone_candidates=self._max_backbone_candidates,
            small_core_threshold=self._small_core_threshold,
            large_core_threshold=self._large_core_threshold,
            planner_step_budget=self._planner_step_budget,
            planner_time_budget_ms=self._planner_time_budget_ms,
        )
        phase_started_at = perf_counter()
        planner_decision = topology_planner.plan(
            prescan=prescan,
            prepared_before=prepared_before,
            prepared_after=prepared_after,
        )
        phase_events.append(
            _phase_event(
                "topology_plan",
                phase_started_at,
                planner_mode=planner_decision.planner_mode,
                degrade_reason=planner_decision.degrade_reason,
                planner_budget=planner_decision.planner_budget,
                planner_diagnostics=planner_decision.planner_diagnostics,
                topology_core_old_count=len(planner_decision.topology_core.old_order),
                topology_core_new_count=len(planner_decision.topology_core.new_order),
                moved_key_count=len(planner_decision.moved_keys),
                backbone_key_count=len(planner_decision.backbone_keys),
            )
        )
        if planner_decision.degrade_reason is not None:
            return self._degraded_result(
                stable_key_field=stable_key_field,
                position_field=position_field,
                degrade_reason=planner_decision.degrade_reason,
                diagnostics=tuple(diagnostics_list),
                table_name=table_name,
                ordered_policy_digest=ordered_policy_digest,
                before_ordered_digest=before_ordered_digest,
                current_ordered_digest=current_ordered_digest,
                semantic_ops=(),
                planner_mode=planner_decision.planner_mode,
                planner_budget=planner_decision.planner_budget,
                planner_diagnostics=planner_decision.planner_diagnostics,
                prescan_summary=prescan_summary,
                topology_core=planner_decision.topology_core,
                benchmark_phase_events=tuple(phase_events),
                prepared_row_count_before=len(prepared_before),
                prepared_row_count_current=len(prepared_after),
            )

        planner_mode = planner_decision.planner_mode
        phase_started_at = perf_counter()
        semantic_ops, blank_interval_synthesis = self._p1_semantic_ops(
            prescan=prescan,
            moved_keys=planner_decision.moved_keys,
            backbone_keys=planner_decision.backbone_keys,
            prepared_before=prepared_before,
            prepared_after=prepared_after,
            stable_key_field=stable_key_field,
            position_field=position_field,
        )
        phase_events.append(
            _phase_event(
                "semantic_ops",
                phase_started_at,
                semantic_op_count=len(semantic_ops),
                semantic_op_counts_by_kind=_semantic_op_counts_by_kind(semantic_ops),
                blank_interval_synthesis_count=len(blank_interval_synthesis),
            )
        )
        phase_started_at = perf_counter()
        replay_validation = validate_ordered_replay(
            before_rows=tuple(row.row for row in prepared_before),
            after_rows=tuple(row.row for row in prepared_after),
            semantic_ops=tuple(semantic_ops),
            position_field=position_field,
        )
        phase_events.append(
            _phase_event(
                "replay_validation",
                phase_started_at,
                semantic_replay_passed=replay_validation.semantic_replay_passed,
                artifact_replay_passed=replay_validation.artifact_replay_passed,
                mismatch_count=replay_validation.mismatch_count,
            )
        )
        exact = (
            replay_validation.semantic_replay_passed
            and replay_validation.artifact_replay_passed
            and not planner_mode == PLANNER_MODE_INPUT_INVALID
        )
        replay_guarantee = (
            OrderedReplayGuarantee.EXACT
            if exact and planner_mode != PLANNER_MODE_INPUT_INVALID
            else OrderedReplayGuarantee.UNSUPPORTED
        )
        degrade_reason = self._degrade_reason(
            planner_mode=planner_mode,
            replay_validation=replay_validation,
            semantic_ops=semantic_ops,
        )
        ordered_preprocess_applied = (
            ORDERED_PREPROCESS_BLANK_GID_FILLED
            if any(row.entity_key_kind == OrderedEntityKeyKind.PSEUDO_BLANK for row in prepared_before + prepared_after)
            else ORDERED_PREPROCESS_NONE
        )
        table_processing_mode = self._table_processing_mode(
            degraded=degrade_reason is not None,
            semantic_ops=tuple(semantic_ops),
            repair_applied=self._repair_applied(
                semantic_ops=semantic_ops,
                base_row_count=len(prepared_before),
                current_row_count=len(prepared_after),
            ),
            base_row_count=len(prepared_before),
            current_row_count=len(prepared_after),
        )
        phase_started_at = perf_counter()
        records = (
            self._records(
                table_name=table_name,
                semantic_ops=tuple(semantic_ops),
                before_rows=tuple(row.row for row in prepared_before),
                after_rows=tuple(row.row for row in prepared_after),
                stable_key_field=stable_key_field,
            )
            if exact and degrade_reason is None
            else ()
        )
        phase_events.append(
            _phase_event(
                "records_build",
                phase_started_at,
                records_count=len(records),
                skipped=not (exact and degrade_reason is None),
                degrade_reason=degrade_reason,
            )
        )
        summary = self._summary(
            semantic_ops=tuple(semantic_ops),
            degraded=degrade_reason is not None,
            exact=exact,
        )
        return _OrderedDiffResult(
            records=records,
            summary=summary,
            replay_validation=replay_validation,
            replay_guarantee=replay_guarantee,
            table_processing_mode=table_processing_mode,
            ordered_preprocess_applied=ordered_preprocess_applied,
            degrade_reason=degrade_reason,
            before_ordered_digest=before_ordered_digest,
            current_ordered_digest=current_ordered_digest,
            diagnostics=tuple(diagnostics_list),
            semantic_ops=tuple(semantic_ops),
            benchmark_phase_events=tuple(phase_events),
            planner_mode=planner_mode,
            prepared_row_count_before=len(prepared_before),
            prepared_row_count_current=len(prepared_after),
        )

    def _input_degraded_result(
        self,
        *,
        stable_key_field: str,
        position_field: str,
        degrade_reason: str,
        diagnostics: tuple[DiagnosticRecord, ...],
        table_name: str,
        ordered_policy_digest: DigestRef | None,
        before_rows: Sequence[Sequence[object] | Mapping[str, object]],
        before_columns: Sequence[str],
        after_rows: Sequence[Sequence[object] | Mapping[str, object]],
        after_columns: Sequence[str],
        pseudo_key_start: int,
        benchmark_phase_events: tuple[Mapping[str, object], ...],
    ) -> _OrderedDiffResult:
        diagnostics = diagnostics + (
            DiagnosticRecord(
                code="comparison.ordered.degraded",
                message="ordered comparison degraded",
                phase="compare",
                severity="WARNING",
                details={
                    "table_name": table_name,
                    "reason": degrade_reason,
                    "stable_key_field": stable_key_field,
                    "position_field": position_field,
                    "ordered_policy_digest": (
                        ordered_policy_digest.to_payload() if ordered_policy_digest is not None else None
                    ),
                },
            ),
        )
        empty_validation = OrderedReplayValidation(
            semantic_replay_passed=False,
            artifact_replay_passed=False,
            mismatch_count=1,
            mismatch_examples=({"reason": degrade_reason},),
        )
        return _OrderedDiffResult(
            records=(),
            summary=OrderedSummary(degraded_count=1),
            replay_validation=empty_validation,
            replay_guarantee=OrderedReplayGuarantee.UNSUPPORTED,
            table_processing_mode=OrderedTableProcessingMode.DEGRADED,
            ordered_preprocess_applied=ORDERED_PREPROCESS_NONE,
            degrade_reason=degrade_reason,
            before_ordered_digest=build_ordered_rows_digest(
                table_name=table_name,
                rows=(),
                columns=before_columns,
                stable_key_field=stable_key_field,
                position_field=position_field,
                ordered_policy_digest=ordered_policy_digest,
                side="before",
            ),
            current_ordered_digest=build_ordered_rows_digest(
                table_name=table_name,
                rows=(),
                columns=after_columns,
                stable_key_field=stable_key_field,
                position_field=position_field,
                ordered_policy_digest=ordered_policy_digest,
                side="current",
            ),
            diagnostics=diagnostics,
            semantic_ops=(),
            benchmark_phase_events=benchmark_phase_events,
            planner_mode=PLANNER_MODE_INPUT_INVALID,
            prepared_row_count_before=0,
            prepared_row_count_current=0,
        )

    def _degraded_result(
        self,
        *,
        stable_key_field: str,
        position_field: str,
        degrade_reason: str,
        diagnostics: tuple[DiagnosticRecord, ...],
        table_name: str,
        ordered_policy_digest: DigestRef | None,
        before_ordered_digest: DigestRef | None,
        current_ordered_digest: DigestRef | None,
        semantic_ops: Sequence[OrderedSemanticOp],
        planner_mode: str,
        planner_budget: dict[str, Any],
        planner_diagnostics: dict[str, Any],
        prescan_summary: dict[str, Any],
        topology_core: _TopologyCore,
        benchmark_phase_events: tuple[Mapping[str, object], ...],
        prepared_row_count_before: int,
        prepared_row_count_current: int,
    ) -> _OrderedDiffResult:
        empty_validation = OrderedReplayValidation(
            semantic_replay_passed=False,
            artifact_replay_passed=False,
            mismatch_count=1,
            mismatch_examples=({"reason": degrade_reason},),
        )
        return _OrderedDiffResult(
            records=(),
            summary=OrderedSummary(degraded_count=1),
            replay_validation=empty_validation,
            replay_guarantee=OrderedReplayGuarantee.UNSUPPORTED,
            table_processing_mode=OrderedTableProcessingMode.DEGRADED,
            ordered_preprocess_applied=ORDERED_PREPROCESS_NONE,
            degrade_reason=degrade_reason,
            before_ordered_digest=before_ordered_digest,
            current_ordered_digest=current_ordered_digest,
            diagnostics=diagnostics + (
                DiagnosticRecord(
                    code="comparison.ordered.degraded",
                    message="ordered comparison degraded",
                    phase="compare",
                    severity="WARNING",
                    details={
                        "table_name": table_name,
                        "reason": degrade_reason,
                        "stable_key_field": stable_key_field,
                        "position_field": position_field,
                        "planner_mode": planner_mode,
                        "planner_budget": planner_budget,
                        "planner_diagnostics": planner_diagnostics,
                        "prescan_summary": prescan_summary,
                        "topology_core_old_order": list(topology_core.old_order),
                        "topology_core_new_order": list(topology_core.new_order),
                    },
                ),
            ),
            semantic_ops=tuple(semantic_ops),
            benchmark_phase_events=benchmark_phase_events,
            planner_mode=planner_mode,
            prepared_row_count_before=prepared_row_count_before,
            prepared_row_count_current=prepared_row_count_current,
        )

    def _summary(
        self,
        *,
        semantic_ops: tuple[OrderedSemanticOp, ...],
        degraded: bool,
        exact: bool,
    ) -> OrderedSummary:
        summary = {
            "row_added_count": 0,
            "row_deleted_count": 0,
            "row_modified_count": 0,
            "row_moved_count": 0,
            "position_changed_count": 0,
            "interval_inserted_count": 0,
            "interval_deleted_count": 0,
            "blank_changed_count": 0,
            "degraded_count": 1 if degraded else 0,
        }
        for op in semantic_ops:
            if op.semantic_kind is OrderedSemanticKind.DATA_INSERT:
                summary["row_added_count"] += 1
            elif op.semantic_kind is OrderedSemanticKind.DATA_DELETE:
                summary["row_deleted_count"] += 1
            elif op.semantic_kind is OrderedSemanticKind.MOVE:
                summary["row_moved_count"] += 1
                summary["position_changed_count"] += 1
            elif op.semantic_kind is OrderedSemanticKind.CONTENT_UPDATE:
                summary["row_modified_count"] += 1
                if op.before_position != op.after_position:
                    summary["position_changed_count"] += 1
            elif op.semantic_kind is OrderedSemanticKind.BLANK_INSERT_INTERVAL:
                summary["interval_inserted_count"] += 1
                summary["blank_changed_count"] += 1
                summary["position_changed_count"] += 1
            elif op.semantic_kind is OrderedSemanticKind.BLANK_DELETE_INTERVAL:
                summary["interval_deleted_count"] += 1
                summary["blank_changed_count"] += 1
                summary["position_changed_count"] += 1
        return OrderedSummary(**summary)

    def _prescan(
        self,
        *,
        prepared_before: list[OrderedPreparedRow],
        prepared_after: list[OrderedPreparedRow],
        stable_key_field: str,
        position_field: str,
    ) -> _Prescan:
        old_real_order = tuple(row.row_key for row in prepared_before if row.entity_key_kind == OrderedEntityKeyKind.REAL_STABLE)
        new_real_order = tuple(row.row_key for row in prepared_after if row.entity_key_kind == OrderedEntityKeyKind.REAL_STABLE)
        shared_real_key_set = set(old_real_order) & set(new_real_order)
        old_common_order = tuple(row_key for row_key in old_real_order if row_key in shared_real_key_set)
        new_common_order = tuple(row_key for row_key in new_real_order if row_key in shared_real_key_set)
        before_by_key = {row.row_key: row for row in prepared_before if row.entity_key_kind == OrderedEntityKeyKind.REAL_STABLE}
        after_by_key = {row.row_key: row for row in prepared_after if row.entity_key_kind == OrderedEntityKeyKind.REAL_STABLE}
        ignored_fields = {stable_key_field.lower(), position_field.lower()}
        content_changed_keys: list[str] = []
        position_changed_keys: list[str] = []
        for row_key in new_common_order:
            before_row = before_by_key[row_key]
            after_row = after_by_key[row_key]
            if before_row.position != after_row.position:
                position_changed_keys.append(row_key)
            if self._changed_columns(
                before_row=before_row.row,
                after_row=after_row.row,
                ignored_fields=ignored_fields,
            ):
                content_changed_keys.append(row_key)
        return _Prescan(
            shared_real_keys=old_common_order,
            inserted_real_keys=tuple(row_key for row_key in new_real_order if row_key not in shared_real_key_set),
            deleted_real_keys=tuple(row_key for row_key in old_real_order if row_key not in shared_real_key_set),
            content_changed_keys=tuple(content_changed_keys),
            position_changed_keys=tuple(position_changed_keys),
            old_real_order=old_real_order,
            new_real_order=new_real_order,
            old_common_order=old_common_order,
            new_common_order=new_common_order,
        )

    def _p1_semantic_ops(
        self,
        *,
        prescan: _Prescan,
        moved_keys: tuple[str, ...],
        backbone_keys: tuple[str, ...],
        prepared_before: list[OrderedPreparedRow],
        prepared_after: list[OrderedPreparedRow],
        stable_key_field: str,
        position_field: str,
    ) -> tuple[list[OrderedSemanticOp], list[dict[str, Any]]]:
        before_by_key = {row.row_key: row for row in prepared_before if row.entity_key_kind == OrderedEntityKeyKind.REAL_STABLE}
        after_by_key = {row.row_key: row for row in prepared_after if row.entity_key_kind == OrderedEntityKeyKind.REAL_STABLE}
        semantic_ops: list[OrderedSemanticOp] = []
        for row_key in prescan.inserted_real_keys:
            row = after_by_key[row_key]
            semantic_ops.append(
                OrderedSemanticOp(
                    semantic_kind=OrderedSemanticKind.DATA_INSERT,
                    row_key=row_key,
                    entity_key_kind=OrderedEntityKeyKind.REAL_STABLE,
                    before_position=None,
                    after_position=row.position,
                    changed_columns=(),
                    payload_before=None,
                    payload_after=dict(row.row),
                    interval_index=None,
                    interval_label=None,
                )
            )
        for row_key in prescan.deleted_real_keys:
            row = before_by_key[row_key]
            semantic_ops.append(
                OrderedSemanticOp(
                    semantic_kind=OrderedSemanticKind.DATA_DELETE,
                    row_key=row_key,
                    entity_key_kind=OrderedEntityKeyKind.REAL_STABLE,
                    before_position=row.position,
                    after_position=None,
                    changed_columns=(),
                    payload_before=dict(row.row),
                    payload_after=None,
                    interval_index=None,
                    interval_label=None,
                )
            )
        for row_key in moved_keys:
            before_row = before_by_key[row_key]
            after_row = after_by_key[row_key]
            semantic_ops.append(
                OrderedSemanticOp(
                    semantic_kind=OrderedSemanticKind.MOVE,
                    row_key=row_key,
                    entity_key_kind=OrderedEntityKeyKind.REAL_STABLE,
                    before_position=before_row.position,
                    after_position=after_row.position,
                    changed_columns=(),
                    payload_before=dict(before_row.row),
                    payload_after=dict(after_row.row),
                    interval_index=None,
                    interval_label=None,
                )
            )
        ignored_fields = {stable_key_field.lower(), position_field.lower()}
        for row_key in prescan.new_common_order:
            before_row = before_by_key[row_key]
            after_row = after_by_key[row_key]
            changed_columns = tuple(
                self._changed_columns(
                    before_row=before_row.row,
                    after_row=after_row.row,
                    ignored_fields=ignored_fields,
                )
            )
            if not changed_columns:
                continue
            semantic_ops.append(
                OrderedSemanticOp(
                    semantic_kind=OrderedSemanticKind.CONTENT_UPDATE,
                    row_key=row_key,
                    entity_key_kind=OrderedEntityKeyKind.REAL_STABLE,
                    before_position=before_row.position,
                    after_position=after_row.position,
                    changed_columns=changed_columns,
                    payload_before=dict(before_row.row),
                    payload_after=dict(after_row.row),
                    interval_index=None,
                    interval_label=None,
                )
            )
        blank_deltas, blank_interval_synthesis = self._blank_interval_delta_ops(
            backbone_keys=backbone_keys,
            prepared_before=prepared_before,
            prepared_after=prepared_after,
        )
        semantic_ops.extend(blank_deltas)
        return semantic_ops, blank_interval_synthesis

    def _blank_interval_delta_ops(
        self,
        *,
        backbone_keys: tuple[str, ...],
        prepared_before: list[OrderedPreparedRow],
        prepared_after: list[OrderedPreparedRow],
    ) -> tuple[list[OrderedSemanticOp], list[dict[str, Any]]]:
        interval_count = len(backbone_keys) + 1
        before_intervals = self._collect_blank_rows_by_interval(
            rows=prepared_before,
            backbone_keys=set(backbone_keys),
            interval_count=interval_count,
        )
        after_intervals = self._collect_blank_rows_by_interval(
            rows=prepared_after,
            backbone_keys=set(backbone_keys),
            interval_count=interval_count,
        )
        ops: list[OrderedSemanticOp] = []
        diagnostics: list[dict[str, Any]] = []
        for interval_index in sorted(set(before_intervals) | set(after_intervals)):
            before_blanks = list(before_intervals.get(interval_index, ()))
            after_blanks = list(after_intervals.get(interval_index, ()))
            before_by_signature = self._rows_by_signature(before_blanks)
            after_by_signature = self._rows_by_signature(after_blanks)
            interval_label = self._interval_label(backbone_keys, interval_index)
            deleted_rows: list[OrderedPreparedRow] = []
            inserted_rows: list[OrderedPreparedRow] = []
            for signature in sorted(set(before_by_signature) | set(after_by_signature), key=lambda item: str(item)):
                before_rows = before_by_signature.get(signature, [])
                after_rows = after_by_signature.get(signature, [])
                matched = min(len(before_rows), len(after_rows))
                if len(before_rows) > matched:
                    deleted_rows.extend(before_rows[matched:])
                if len(after_rows) > matched:
                    inserted_rows.extend(after_rows[matched:])
            deleted_rows.sort(key=lambda row: row.position)
            inserted_rows.sort(key=lambda row: row.position)
            for row in deleted_rows:
                ops.append(
                    OrderedSemanticOp(
                        semantic_kind=OrderedSemanticKind.BLANK_DELETE_INTERVAL,
                        row_key=row.row_key,
                        entity_key_kind=OrderedEntityKeyKind.PSEUDO_BLANK,
                        before_position=row.position,
                        after_position=None,
                        changed_columns=(),
                        payload_before=dict(row.row),
                        payload_after=None,
                        interval_index=interval_index,
                        interval_label=interval_label,
                    )
                )
            for row in inserted_rows:
                ops.append(
                    OrderedSemanticOp(
                        semantic_kind=OrderedSemanticKind.BLANK_INSERT_INTERVAL,
                        row_key=row.row_key,
                        entity_key_kind=OrderedEntityKeyKind.PSEUDO_BLANK,
                        before_position=None,
                        after_position=row.position,
                        changed_columns=(),
                        payload_before=None,
                        payload_after=dict(row.row),
                        interval_index=interval_index,
                        interval_label=interval_label,
                    )
                )
            diagnostics.append(
                {
                    "interval_index": interval_index,
                    "interval_label": interval_label,
                    "before_blank_count": len(before_blanks),
                    "after_blank_count": len(after_blanks),
                    "deleted_blank_count": len(deleted_rows),
                    "inserted_blank_count": len(inserted_rows),
                }
            )
        return ops, diagnostics

    def _replay_current_rows(
        self,
        *,
        before_rows: tuple[dict[str, Any], ...],
        after_row_count: int,
        semantic_ops: tuple[OrderedSemanticOp, ...],
    ) -> list[dict[str, Any]] | None:
        consumed_before_positions: set[int] = set()
        current_rows_by_position: dict[int, dict[str, Any]] = {}
        moves_by_key: dict[str, OrderedSemanticOp] = {}
        updates_by_key: dict[str, OrderedSemanticOp] = {}

        def consume(before_position: int | None) -> bool:
            if before_position is None:
                return True
            if before_position in consumed_before_positions:
                return False
            consumed_before_positions.add(before_position)
            return True

        def place(after_position: int | None, payload: Mapping[str, Any] | None) -> bool:
            if after_position is None or payload is None:
                return False
            if after_position < 1 or after_position > after_row_count:
                return False
            if after_position in current_rows_by_position:
                return False
            current_rows_by_position[after_position] = dict(payload)
            return True

        for op in semantic_ops:
            if op.semantic_kind == OrderedSemanticKind.MOVE:
                moves_by_key[op.row_key] = op
                continue
            if op.semantic_kind == OrderedSemanticKind.CONTENT_UPDATE:
                updates_by_key[op.row_key] = op
                continue
            if op.semantic_kind in {
                OrderedSemanticKind.DATA_INSERT,
                OrderedSemanticKind.BLANK_INSERT_INTERVAL,
            }:
                if not place(op.after_position, op.payload_after):
                    return None
                continue
            if op.semantic_kind in {
                OrderedSemanticKind.DATA_DELETE,
                OrderedSemanticKind.BLANK_DELETE_INTERVAL,
            }:
                if not consume(op.before_position):
                    return None
                continue

        for row_key, move in moves_by_key.items():
            update = updates_by_key.pop(row_key, None)
            if not consume(move.before_position):
                return None
            payload_after = update.payload_after if update is not None else move.payload_after
            if not place(move.after_position, payload_after):
                return None

        for update in updates_by_key.values():
            if not consume(update.before_position):
                return None
            if not place(update.after_position, update.payload_after):
                return None

        slots: list[dict[str, Any] | None] = [None] * after_row_count
        for after_position, payload in current_rows_by_position.items():
            slots[after_position - 1] = payload

        next_open_slot = 0
        for before_position, row in enumerate(before_rows, start=1):
            if before_position in consumed_before_positions:
                continue
            while next_open_slot < after_row_count and slots[next_open_slot] is not None:
                next_open_slot += 1
            if next_open_slot >= after_row_count:
                return None
            slots[next_open_slot] = dict(row)

        if any(slot is None for slot in slots):
            return None
        return [slot for slot in slots if slot is not None]

    def _records(
        self,
        *,
        table_name: str,
        semantic_ops: tuple[OrderedSemanticOp, ...],
        before_rows: tuple[dict[str, Any], ...],
        after_rows: tuple[dict[str, Any], ...],
        stable_key_field: str,
    ) -> tuple[OrderedRecord, ...]:
        topology_before_rank = self._real_rank_by_key(
            rows=before_rows,
            stable_key_field=stable_key_field,
        )
        topology_after_rank = self._real_rank_by_key(
            rows=after_rows,
            stable_key_field=stable_key_field,
        )
        records: list[OrderedRecord] = []
        for index, op in enumerate(self._sorted_semantic_ops(semantic_ops), start=1):
            records.append(
                OrderedRecord(
                    table_name=table_name,
                    record_kind=self._record_kind_for_semantic_kind(op.semantic_kind),
                    semantic_kind=op.semantic_kind,
                    entity_key_kind=op.entity_key_kind,
                    entity_key=op.row_key,
                    before_position=op.before_position,
                    after_position=op.after_position,
                    topology_before_rank=topology_before_rank.get(op.row_key),
                    topology_after_rank=topology_after_rank.get(op.row_key),
                    interval_index=op.interval_index,
                    interval_label=op.interval_label,
                    changed_columns=op.changed_columns if op.semantic_kind == OrderedSemanticKind.CONTENT_UPDATE else (),
                    payload_before=op.payload_before,
                    payload_after=op.payload_after,
                )
            )
        return tuple(records)

    def _degrade_reason(
        self,
        *,
        planner_mode: str,
        replay_validation: OrderedReplayValidation,
        semantic_ops: Sequence[OrderedSemanticOp],
    ) -> str | None:
        if planner_mode == PLANNER_MODE_INPUT_INVALID:
            return "input_invalid"
        if not replay_validation.semantic_replay_passed:
            return "semantic_replay_failed"
        if not replay_validation.artifact_replay_passed:
            return "artifact_replay_failed"
        return None

    @staticmethod
    def _empty_prescan_summary() -> dict[str, Any]:
        return {
            "shared_real_count": 0,
            "inserted_real_count": 0,
            "deleted_real_count": 0,
            "content_changed_count": 0,
            "position_changed_count": 0,
            "old_common_order_equals_new_common_order": True,
            "shared_real_keys": [],
            "inserted_real_keys": [],
            "deleted_real_keys": [],
            "content_changed_keys": [],
            "position_changed_keys": [],
        }

    @staticmethod
    def _prescan_summary(prescan: _Prescan) -> dict[str, Any]:
        return {
            "shared_real_count": len(prescan.shared_real_keys),
            "inserted_real_count": len(prescan.inserted_real_keys),
            "deleted_real_count": len(prescan.deleted_real_keys),
            "content_changed_count": len(prescan.content_changed_keys),
            "position_changed_count": len(prescan.position_changed_keys),
            "old_common_order_equals_new_common_order": prescan.old_common_order == prescan.new_common_order,
            "shared_real_keys": list(prescan.shared_real_keys),
            "inserted_real_keys": list(prescan.inserted_real_keys),
            "deleted_real_keys": list(prescan.deleted_real_keys),
            "content_changed_keys": list(prescan.content_changed_keys),
            "position_changed_keys": list(prescan.position_changed_keys),
        }

    @staticmethod
    def _collect_blank_rows_by_interval(
        *,
        rows: list[OrderedPreparedRow],
        backbone_keys: set[str],
        interval_count: int,
    ) -> dict[int, list[OrderedPreparedRow]]:
        buckets: dict[int, list[OrderedPreparedRow]] = {}
        interval_index = 0
        for row in rows:
            if row.entity_key_kind == OrderedEntityKeyKind.REAL_STABLE and row.row_key in backbone_keys:
                interval_index += 1
                continue
            if row.entity_key_kind == OrderedEntityKeyKind.PSEUDO_BLANK:
                if interval_index >= interval_count:
                    interval_index = interval_count - 1
                buckets.setdefault(interval_index, []).append(row)
        return buckets

    @staticmethod
    def _blank_signature_counts_by_interval(
        *,
        rows: list[OrderedPreparedRow],
        backbone_keys: set[str],
    ) -> dict[int, dict[tuple[tuple[str, Any], ...], int]]:
        buckets: dict[int, dict[tuple[tuple[str, Any], ...], int]] = {}
        interval_index = 0
        for row in rows:
            if row.entity_key_kind == OrderedEntityKeyKind.REAL_STABLE and row.row_key in backbone_keys:
                interval_index += 1
                continue
            if row.entity_key_kind != OrderedEntityKeyKind.PSEUDO_BLANK:
                continue
            signature = row.blank_signature or ()
            counts = buckets.setdefault(interval_index, {})
            counts[signature] = counts.get(signature, 0) + 1
        return buckets

    @staticmethod
    def _rows_by_signature(rows: list[OrderedPreparedRow]) -> dict[tuple[tuple[str, Any], ...], list[OrderedPreparedRow]]:
        grouped: dict[tuple[tuple[str, Any], ...], list[OrderedPreparedRow]] = {}
        for row in rows:
            grouped.setdefault(row.blank_signature or (), []).append(row)
        return grouped

    @staticmethod
    def _interval_label(backbone_keys: tuple[str, ...], interval_index: int) -> str:
        if not backbone_keys:
            return "whole"
        if interval_index <= 0:
            return f"head->{backbone_keys[0]}"
        if interval_index >= len(backbone_keys):
            return f"{backbone_keys[-1]}->tail"
        return f"{backbone_keys[interval_index - 1]}->{backbone_keys[interval_index]}"

    @staticmethod
    def _repair_applied(
        *,
        semantic_ops: Sequence[OrderedSemanticOp],
        base_row_count: int,
        current_row_count: int,
    ) -> bool:
        for op in semantic_ops:
            if op.semantic_kind in {OrderedSemanticKind.DATA_INSERT, OrderedSemanticKind.BLANK_INSERT_INTERVAL}:
                if op.after_position is not None and op.after_position <= base_row_count:
                    return True
            if op.semantic_kind in {OrderedSemanticKind.DATA_DELETE, OrderedSemanticKind.BLANK_DELETE_INTERVAL}:
                if op.before_position is not None and op.before_position <= current_row_count:
                    return True
        return False

    @staticmethod
    def _table_processing_mode(
        *,
        degraded: bool,
        semantic_ops: tuple[OrderedSemanticOp, ...],
        repair_applied: bool,
        base_row_count: int,
        current_row_count: int,
    ) -> OrderedTableProcessingMode:
        if degraded:
            return OrderedTableProcessingMode.DEGRADED
        if any(op.semantic_kind == OrderedSemanticKind.MOVE for op in semantic_ops):
            return OrderedTableProcessingMode.ORDERED_REORDER_COMPLEX
        if OrderedDiffEngine._tail_only(
            semantic_ops=semantic_ops,
            base_row_count=base_row_count,
            current_row_count=current_row_count,
        ):
            return OrderedTableProcessingMode.ORDERED_TAIL_SEGMENT
        if repair_applied:
            return OrderedTableProcessingMode.ORDERED_SHIFT_REPAIRED
        return OrderedTableProcessingMode.ORDERED_LOCAL_PATCH

    @staticmethod
    def _tail_only(
        *,
        semantic_ops: tuple[OrderedSemanticOp, ...],
        base_row_count: int,
        current_row_count: int,
    ) -> bool:
        if not semantic_ops:
            return False
        for op in semantic_ops:
            if op.semantic_kind in {OrderedSemanticKind.CONTENT_UPDATE, OrderedSemanticKind.MOVE}:
                return False
            if op.semantic_kind in {OrderedSemanticKind.DATA_INSERT, OrderedSemanticKind.BLANK_INSERT_INTERVAL}:
                if op.after_position is None or op.after_position <= base_row_count:
                    return False
                continue
            if op.semantic_kind in {OrderedSemanticKind.DATA_DELETE, OrderedSemanticKind.BLANK_DELETE_INTERVAL}:
                if op.before_position is None or op.before_position <= current_row_count:
                    return False
                continue
        return True

    @staticmethod
    def _sorted_semantic_ops(
        semantic_ops: tuple[OrderedSemanticOp, ...],
    ) -> list[OrderedSemanticOp]:
        kind_rank = {
            OrderedSemanticKind.DATA_DELETE: 0,
            OrderedSemanticKind.BLANK_DELETE_INTERVAL: 1,
            OrderedSemanticKind.MOVE: 2,
            OrderedSemanticKind.CONTENT_UPDATE: 3,
            OrderedSemanticKind.DATA_INSERT: 4,
            OrderedSemanticKind.BLANK_INSERT_INTERVAL: 5,
        }
        return sorted(
            semantic_ops,
            key=lambda op: (
                op.after_position if op.after_position is not None else 10**9,
                op.before_position if op.before_position is not None else 10**9,
                kind_rank.get(op.semantic_kind, 99),
                op.row_key,
            ),
        )

    @staticmethod
    def _record_kind_for_semantic_kind(semantic_kind: OrderedSemanticKind | str) -> OrderedRecordKind:
        normalized = OrderedSemanticKind(semantic_kind)
        if normalized is OrderedSemanticKind.DATA_INSERT:
            return OrderedRecordKind.ORDERED_ROW_ADDED
        if normalized is OrderedSemanticKind.DATA_DELETE:
            return OrderedRecordKind.ORDERED_ROW_DELETED
        if normalized is OrderedSemanticKind.MOVE:
            return OrderedRecordKind.ORDERED_ROW_MOVED
        if normalized is OrderedSemanticKind.CONTENT_UPDATE:
            return OrderedRecordKind.ORDERED_ROW_MODIFIED
        if normalized is OrderedSemanticKind.BLANK_INSERT_INTERVAL:
            return OrderedRecordKind.ORDERED_INTERVAL_INSERTED
        return OrderedRecordKind.ORDERED_INTERVAL_DELETED

    @staticmethod
    def _real_rank_by_key(
        *,
        rows: tuple[dict[str, Any], ...],
        stable_key_field: str,
    ) -> dict[str, int]:
        ranks: dict[str, int] = {}
        next_rank = 1
        for row in rows:
            stable_value = OrderedDiffEngine._normalize_int(
                OrderedDiffEngine._lookup_value(row, stable_key_field),
                zero_is_missing=True,
            )
            if stable_value is None:
                continue
            ranks[f"{stable_key_field}={stable_value}"] = next_rank
            next_rank += 1
        return ranks

    @staticmethod
    def _normalize_rows_for_current_slot_space(
        rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        *,
        position_field: str,
    ) -> list[dict[str, Any]]:
        return [
            OrderedDiffEngine._row_with_position(
                row=dict(row),
                position_field=position_field,
                position=row_index,
            )
            for row_index, row in enumerate(rows, start=1)
        ]

    @staticmethod
    def _mismatch_examples(
        replayed: list[dict[str, Any]],
        expected: tuple[dict[str, Any], ...],
    ) -> list[dict[str, Any]]:
        mismatches: list[dict[str, Any]] = []
        for index, (replayed_row, expected_row) in enumerate(zip(replayed, expected, strict=False), start=1):
            if replayed_row != expected_row:
                mismatches.append(
                    {
                        "row_index": index,
                        "replayed": replayed_row,
                        "expected": expected_row,
                    }
                )
        if len(replayed) != len(expected):
            mismatches.append(
                {
                    "row_count_mismatch": True,
                    "replayed_count": len(replayed),
                    "expected_count": len(expected),
                }
            )
        return mismatches

    @staticmethod
    def _changed_columns(
        *,
        before_row: Mapping[str, Any],
        after_row: Mapping[str, Any],
        ignored_fields: set[str],
    ) -> list[str]:
        ordered_columns = list(before_row)
        for column_name in after_row:
            if column_name not in before_row:
                ordered_columns.append(column_name)
        return [
            column_name
            for column_name in ordered_columns
            if column_name.lower() not in ignored_fields and before_row.get(column_name) != after_row.get(column_name)
        ]

    @staticmethod
    def _blank_signature(
        *,
        row: Mapping[str, Any],
        stable_key_field: str,
        position_field: str,
    ) -> tuple[tuple[str, Any], ...]:
        ignored = {stable_key_field.lower(), position_field.lower()}
        return tuple((column, row[column]) for column in row if column.lower() not in ignored)

    @staticmethod
    def _lookup_value(row: Mapping[str, Any], field_name: str) -> Any:
        lowered = {column.lower(): value for column, value in row.items()}
        return lowered.get(field_name.lower())

    @staticmethod
    def _normalize_int(value: Any, *, zero_is_missing: bool = False) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            if zero_is_missing and value == 0:
                return None
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            normalized = int(text)
        except ValueError:
            return None
        if zero_is_missing and normalized == 0:
            return None
        return normalized

    @staticmethod
    def _row_with_position(
        *,
        row: dict[str, Any],
        position_field: str,
        position: int,
    ) -> dict[str, Any]:
        row[position_field] = position
        return row


__all__ = [
    "OrderedDiffEngine",
]
