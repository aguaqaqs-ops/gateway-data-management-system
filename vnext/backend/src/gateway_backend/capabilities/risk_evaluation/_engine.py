"""Bounded Python reference Risk evaluator."""

from __future__ import annotations

from gateway_backend.statistics.metrics import timed

from collections.abc import Callable, Mapping
from contextlib import ExitStack, closing
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from time import perf_counter

from gateway_backend.artifacts import ArtifactStorePort
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonMode,
    ComparisonRecordKind,
    ComparisonRecordsClosure,
    ComparisonTableStatus,
    OrderedRecordKind,
    ReplayGuarantee,
    SchemaEvolution,
)
from gateway_backend.capabilities.risk_evaluation._artifacts import (
    RiskArtifactError,
    publish_annotation_artifact,
    publish_annotation_closure,
)
from gateway_backend.capabilities.risk_evaluation._facts import (
    ExtractedRiskFacts,
    extract_risk_facts,
    has_visible_change,
    record_kind_name,
)
from gateway_backend.capabilities.risk_evaluation._rules import (
    InvalidRiskRuleset,
    level_for,
    ordered_yk_name_applies,
    reason_for,
    standard_rule_applicability,
    validate_risk_ruleset,
)
from gateway_backend.capabilities.risk_evaluation.candidates import (
    CHECK_RECORDS_CLOSURE,
    RiskCandidateEvent,
    RiskCheckRecordsClosure,
    RiskEmitEvent,
    optional_candidate_input,
)
from gateway_backend.capabilities.risk_evaluation.contracts import (
    AnnotationDetailPolicy,
    RiskAnnotation,
    RiskAnnotationArtifact,
    RiskAnnotationClosureEntry,
    RiskEvaluation,
    RiskEvaluationInput,
    RiskEvaluationResult,
    RiskEvaluationStatus,
    RiskExecutionContext,
    RiskOperationPort,
    RiskReservationPort,
    RiskExecutionPolicy,
    RiskLevel,
    RiskReason,
    RiskReasonCode,
    RiskReport,
    RiskRuleId,
    RiskRuleSpec,
    RiskSummary,
    RiskTableRisk,
    RiskTarget,
    RiskTargetType,
    compute_risk_evaluation_digest,
)
from gateway_shared_kernel import DigestRef
from gateway_shared_kernel.jcs import canonicalize_json_value


_LEVEL_RANK: dict[RiskLevel, int] = {
    RiskLevel.HIGH: 5,
    RiskLevel.MEDIUM_HIGH: 4,
    RiskLevel.UNKNOWN: 3,
    RiskLevel.MEDIUM_LOW: 2,
    RiskLevel.LOW: 1,
}


def _record_timing(evaluation_input: RiskEvaluationInput, key: str, started: float) -> None:
    metrics = evaluation_input.record_view_metrics
    if metrics is not None:
        metrics[key] = metrics.get(key, 0.0) + perf_counter() - started


_MESSAGES: dict[RiskReasonCode, str] = {
    RiskReasonCode.PROJECT_IDENTITY_MISMATCH: "project identity differs; dataset replacement requires review",
    RiskReasonCode.TABLE_ADDED: "table added",
    RiskReasonCode.TABLE_DELETED: "table deleted",
    RiskReasonCode.SCHEMA_CHANGED: "schema changed",
    RiskReasonCode.ROW_ADDED: "row added",
    RiskReasonCode.ROW_DELETED: "row deleted",
    RiskReasonCode.ROW_MODIFIED: "row modified",
    RiskReasonCode.STANDARD_NAME_UPDATE: "row name or description changed",
    RiskReasonCode.ORDERED_MOVE: "ordered row moved",
    RiskReasonCode.ORDERED_REPLACEMENT: "ordered row replaced at the same position",
    RiskReasonCode.ORDERED_MIDDLE_INSERT_DELETE: "ordered row inserted or deleted in the middle",
    RiskReasonCode.ORDERED_TAIL_INSERT_DELETE: "ordered row inserted or deleted at the end",
    RiskReasonCode.ORDERED_NAME_UPDATE: "ordered row name or description changed",
    RiskReasonCode.ORDERED_CONTENT_UPDATE: "ordered row content changed",
    RiskReasonCode.ORDERED_RISK_UNKNOWN: "ordered change requires review",
    RiskReasonCode.ORDERED_MIDDLE_BLANK_INTERVAL: "blank interval changed in the middle of the table",
    RiskReasonCode.ORDERED_TAIL_BLANK_INTERVAL: "blank interval changed at the end of the table",
    RiskReasonCode.KEY_DEGRADED: "comparison key degraded; review required",
    RiskReasonCode.ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED: "ordered diff unsupported; review required",
    RiskReasonCode.COMPARISON_FAILED: "comparison failed",
    RiskReasonCode.COMPOSITE_SIGNAL_CHANGE_REVIEW_REQUIRED: "composite signal change; review required",
    RiskReasonCode.UNKNOWN_CHANGE_TARGET: "unknown change target; review required",
}


class _PairFailure(Exception):
    pass


class _PairCancelled(Exception):
    pass


class _TableBudgetExceeded(Exception):
    pass


class _PairAnnotationBudgetExceeded(Exception):
    pass


_RiskEmitter = Callable[..., None]


@dataclass(frozen=True, slots=True)
class _TableOutcome:
    table_name: str
    source_table_status: ComparisonTableStatus
    annotations: tuple[RiskAnnotation, ...]
    degraded: bool = False
    allow_artifact: bool = True
    diagnostics: tuple[str, ...] = ()
    charges: ExitStack = field(default_factory=ExitStack, repr=False, compare=False)


def _evict_optional_risk_only(cache: object | None) -> bool:
    evict = None if cache is None else getattr(cache, "risk_evict_for_output", None)
    if not callable(evict):
        return False
    evict()
    return True


def _reserve_risk_output(
    operation: RiskOperationPort, size: int, cache: object | None,
) -> RiskReservationPort:
    try:
        return operation.memory.reserve(size)
    except MemoryError:
        if not _evict_optional_risk_only(cache):
            raise
        operation.checkpoint()
        return operation.memory.reserve(size)


def _optional_risk_cache_key(
    item: ExtractedRiskFacts,
    evaluation_input: RiskEvaluationInput,
    policy: RiskExecutionPolicy,
    operation: RiskOperationPort | None,
    task_key: str,
) -> tuple[str | None, RiskReservationPort | None]:
    """The current Comparison task identifies neutral facts and record content."""
    candidate, charge = optional_candidate_input(
        item, evaluation_input, policy, task_key, operation,
    )
    if candidate is None or charge is None:
        return None, None
    try:
        key = candidate.task_digest()
        assert operation is not None
        operation.checkpoint()
        charge.shrink_to(2048)
        return key, charge
    except BaseException:
        charge.close()
        raise


class _RiskCandidateRecorder:
    """Store complete neutral events only; the session decides retention uses."""

    def __init__(
        self, cache: object, task_key: str, risk_key: str,
        operation: RiskOperationPort | None,
    ) -> None:
        self.cache = cache
        self.task_key = task_key
        self.risk_key = risk_key
        self.operation = operation
        self.events: list[RiskCandidateEvent] = []
        self.charges = ExitStack()
        self.enabled = True

    def append(self, event: RiskCandidateEvent) -> None:
        if not self.enabled:
            return
        operation = self.operation
        if operation is None:
            self.close()
            return
        size = 1024
        if isinstance(event, RiskEmitEvent):
            size += len(event.target.table_name or "") * 16
            size += sum(len(column) * 16 + 128 for column in event.target.changed_columns)
            size += sum((len(name) + len(str(value))) * 16 + 128
                        for name, value in event.evidence)
        try:
            self.charges.enter_context(operation.memory.reserve(size))
        except MemoryError:
            # Cache retention is optional. Continue the current lazy rule
            # evaluation with no new business resource failure.
            self.close()
            return
        self.events.append(event.neutral() if isinstance(event, RiskEmitEvent) else event)

    def finish(self) -> None:
        if self.enabled:
            store = getattr(self.cache, "risk_store")
            transferred = self.charges.pop_all()
            try:
                stored = store(self.task_key, self.risk_key, tuple(self.events), transferred)
            except BaseException:
                transferred.close()
                raise
            if not stored:
                transferred.close()
        self.enabled = False
        self.events.clear()
        self.risk_key = ""

    def close(self) -> None:
        self.enabled = False
        self.events.clear()
        self.risk_key = ""
        self.charges.close()


@timed("risk")
def evaluate_risk(
    evaluation_input: RiskEvaluationInput,
    *,
    artifact_store: ArtifactStorePort | None = None,
    execution_policy: RiskExecutionPolicy = RiskExecutionPolicy(),
    execution_context: RiskExecutionContext | None = None,
) -> RiskEvaluationResult:
    """Evaluate one immutable R5 facts object under an injected frozen ruleset."""

    context = execution_context or RiskExecutionContext()
    pair_started = context.clock()
    pair_charges = ExitStack()
    try:
        operation = context.operation
        if operation is not None:
            table_count = min(
                len(evaluation_input.comparison_facts.tables),
                execution_policy.max_risk_tables_per_pair,
            )
            operation.resources.enter_context(_reserve_risk_output(operation,
                16 * 1024**2 + table_count * 8192,
                evaluation_input.risk_cache_session,
            ))
        rules_started = perf_counter()
        rules = validate_risk_ruleset(evaluation_input.risk_ruleset)
        _record_timing(evaluation_input, "ruleset_validation_seconds", rules_started)
        if evaluation_input.comparison_facts.comparison_mode is ComparisonMode.DATASET_REPLACEMENT:
            publication_started = perf_counter()
            result = _publish_result(
                evaluation_input,
                [],
                artifact_store,
                execution_policy,
                degraded=False,
                context=context,
            )
            _record_timing(evaluation_input, "publication_seconds", publication_started)
            return result
        source_tables = evaluation_input.comparison_facts.tables
        if len(source_tables) > execution_policy.max_risk_tables_per_pair:
            raise _PairFailure("max_risk_tables_per_pair exceeded")
        _check_pair(context, pair_started, execution_policy)
        extraction_started = perf_counter()
        extracted = extract_risk_facts(
            evaluation_input.comparison_facts,
            evaluation_input.requested_tables,
            evaluation_input.record_views,
            evaluation_input.record_view_metrics,
            context.operation,
        )
        _record_timing(evaluation_input, "fact_extraction_seconds", extraction_started)
        outcomes: list[_TableOutcome] = []
        total_annotations = 0
        rules_started = perf_counter()
        for item in extracted:
            _check_pair(context, pair_started, execution_policy)
            try:
                outcome = _evaluate_table(
                    item,
                    rules,
                    evaluation_input,
                    execution_policy,
                    context,
                    pair_started,
                    annotation_limit=execution_policy.max_annotations_per_pair - total_annotations,
                )
                outcomes.append(outcome)
                pair_charges.enter_context(outcome.charges)
                total_annotations += len(outcome.annotations)
            except _TableBudgetExceeded:
                degraded = _degraded_table(
                    item, "RISK_TABLE_BUDGET_EXCEEDED", rules,
                    evaluation_input.risk_cache_session,
                    context.operation,
                )
                outcomes.append(degraded)
                pair_charges.enter_context(degraded.charges)
            except _PairAnnotationBudgetExceeded:
                _record_timing(evaluation_input, "rules_evaluation_seconds", rules_started)
                return _build_pair_degraded_without_annotations(
                    evaluation_input,
                    extracted,
                    rules,
                    execution_policy,
                    context,
                )
        _record_timing(evaluation_input, "rules_evaluation_seconds", rules_started)
        # A cached replay tuple is only needed while its table is being
        # evaluated. Once every table has returned, the current pair's last
        # known use can release its Risk-only owner before publication/Surface.
        cache = evaluation_input.risk_cache_session
        retire = None if cache is None else getattr(cache, "risk_retire_last_uses", None)
        if callable(retire) and evaluation_input.risk_task_keys is not None:
            retire(evaluation_input.risk_task_keys)
        # Publication is the terminal commit boundary; cancellation is observed before it,
        # and a result that has crossed the boundary is never converted back to CANCELLED.
        _check_pair(context, pair_started, execution_policy)
        publication_started = perf_counter()
        result = _publish_result(
            evaluation_input,
            outcomes,
            artifact_store,
            execution_policy,
            any(item.degraded for item in outcomes),
            context,
        )
        _record_timing(evaluation_input, "publication_seconds", publication_started)
        return result
    except _PairCancelled as exc:
        return RiskEvaluationResult(
            status=RiskEvaluationStatus.CANCELLED,
            diagnostics=(str(exc),),
        )
    except (InvalidRiskRuleset, _PairFailure, RiskArtifactError, ValueError) as exc:
        return RiskEvaluationResult(
            status=RiskEvaluationStatus.FAILED,
            diagnostics=(str(exc),),
        )
    finally:
        # RiskEvaluationResult contains only summaries and artifact refs. It
        # never retains the annotation objects after publication.
        pair_charges.close()


def _evaluate_table(
    item: ExtractedRiskFacts,
    rules: Mapping[RiskRuleId, RiskRuleSpec],
    evaluation_input: RiskEvaluationInput,
    policy: RiskExecutionPolicy,
    context: RiskExecutionContext,
    pair_started: float,
    *,
    annotation_limit: int,
) -> _TableOutcome:
    with ExitStack() as charges:
        outcome = _evaluate_table_impl(
            item, rules, evaluation_input, policy, context, pair_started,
            annotation_limit=annotation_limit, charges=charges,
        )
        charges.enter_context(outcome.charges)
        return replace(outcome, charges=charges.pop_all())


def _evaluate_table_impl(
    item: ExtractedRiskFacts,
    rules: Mapping[RiskRuleId, RiskRuleSpec],
    evaluation_input: RiskEvaluationInput,
    policy: RiskExecutionPolicy,
    context: RiskExecutionContext,
    pair_started: float,
    *,
    annotation_limit: int,
    charges: ExitStack,
) -> _TableOutcome:
    # Empty-baseline imports retain comparison diagnostics but carry no risk marks.
    # Publish a complete empty outcome for each table so navigation stays exact.
    if evaluation_input.risk_options.empty_baseline:
        return _TableOutcome(item.table_fact.table_name, item.table_fact.status, ())

    table_started = context.clock()
    annotations: list[RiskAnnotation] = []
    cached_events: tuple[object, ...] | None = None
    prepaid_cached_output = False

    if (
        len(item.comparison_facts.diagnostics) > policy.max_diagnostics_per_table
        or len(canonicalize_json_value(list(item.comparison_facts.diagnostics)))
        > policy.max_diagnostics_bytes_per_table
    ):
        return _degraded_table(
            item, "RISK_DIAGNOSTICS_TRUNCATED", rules,
            evaluation_input.risk_cache_session,
            context.operation,
        )

    def reserve_required(size: int) -> RiskReservationPort:
        operation = context.operation
        assert operation is not None
        try:
            return operation.memory.reserve(size)
        except MemoryError:
            if recorder is not None:
                recorder.close()
            if not _evict_optional_risk_only(evaluation_input.risk_cache_session) and recorder is None:
                raise
            operation.checkpoint()
            return operation.memory.reserve(size)

    def emit(
        rule_id: RiskRuleId,
        target: RiskTarget,
        evidence: tuple[tuple[str, str | int | bool | None], ...] = (),
    ) -> None:
        if len(annotations) >= min(policy.max_annotations_per_table, annotation_limit):
            if len(annotations) >= annotation_limit:
                raise _PairAnnotationBudgetExceeded
            raise _TableBudgetExceeded
        if recorder is not None:
            recorder.append(RiskEmitEvent(rule_id, target, evidence))
        rule = rules[rule_id]
        reason_code = reason_for(rule)
        level = level_for(rule)
        if not _include_level(level, evaluation_input):
            return
        operation = context.operation
        if operation is not None and not prepaid_cached_output:
            size = 2048 + len(item.table_fact.table_name) * 16
            size += sum(len(column) * 16 + 128 for column in target.changed_columns)
            size += sum((len(name) + len(str(value))) * 16 + 128 for name, value in evidence)
            charges.enter_context(reserve_required(size))
        annotations.append(
            RiskAnnotation(
                annotation_id=f"{item.table_fact.table_name}:{len(annotations):08d}",
                risk_level=level,
                target=target,
                reasons=(
                    RiskReason(
                        reason_code=reason_code,
                        message=_MESSAGES[reason_code],
                        rule_id=rule_id,
                        evidence=evidence,
                    ),
                ),
            )
        )
        _check_table(context, table_started, pair_started, policy)

    if not has_visible_change(item):
        return _TableOutcome(item.table_fact.table_name, item.table_fact.status, ())

    recorder: _RiskCandidateRecorder | None = None
    cache_rejected = False
    cache = evaluation_input.risk_cache_session
    task_keys = evaluation_input.risk_task_keys
    task_key = None if task_keys is None else task_keys.get(item.table_fact.table_name)
    if cache is not None and task_key is not None and not item.composite_signal:
        risk_key, key_charge = _optional_risk_cache_key(
            item, evaluation_input, policy, context.operation, task_key,
        )
        if risk_key is not None and key_charge is not None:
            try:
                lookup = getattr(cache, "risk_lookup")
                cached_events = lookup(task_key, risk_key)
                if cached_events is not None:
                    # A cached candidate is optional. Admit the maximum annotation
                    # materialization it can cause before replay. If retention would
                    # crowd out this necessary output, release it and execute rules.
                    upper = 0
                    for event in cached_events:
                        if isinstance(event, RiskEmitEvent):
                            upper += 2048 + len(item.table_fact.table_name) * 16
                            upper += sum(len(column) * 16 + 128
                                         for column in event.target.changed_columns)
                            upper += sum((len(name) + len(str(value))) * 16 + 128
                                         for name, value in event.evidence)
                    operation = context.operation
                    if operation is not None:
                        try:
                            charges.enter_context(operation.memory.reserve(upper))
                            prepaid_cached_output = True
                        except MemoryError:
                            cached_events = None
                            if not _evict_optional_risk_only(cache):
                                evict = getattr(cache, "risk_evict")
                                evict(task_key, risk_key)
                            cache_rejected = True
                if cached_events is None:
                    remaining = getattr(cache, "remaining_uses")
                    if (remaining.get(task_key, 0) > 1 or getattr(cache, "persistent_retention", False)) and not cache_rejected:
                        recorder = _RiskCandidateRecorder(
                            cache, task_key, risk_key, context.operation,
                        )
                        recorder.charges.enter_context(key_charge)
                        key_charge = None
                        charges.callback(recorder.close)
            finally:
                if key_charge is not None:
                    key_charge.close()
                risk_key = None

    def require_closure() -> None:
        if recorder is not None:
            recorder.append(CHECK_RECORDS_CLOSURE)
        _require_records_closure(item, evaluation_input)

    if cached_events is not None:
        for index, event in enumerate(cached_events):
            if index % 1024 == 0:
                operation = context.operation
                if operation is not None:
                    operation.checkpoint()
            if isinstance(event, RiskCheckRecordsClosure):
                require_closure()
            elif isinstance(event, RiskEmitEvent):
                emit(event.rule_id, event.bind_target(item.table_fact.table_name), event.evidence)
            else:
                raise _PairFailure("risk candidate cache contains an invalid event")
        return _TableOutcome(
            table_name=item.table_fact.table_name,
            source_table_status=item.table_fact.status,
            annotations=tuple(annotations),
            allow_artifact=not item.comparison_facts.degraded,
        )

    table_target = RiskTarget(target_type=RiskTargetType.TABLE, table_name=item.table_fact.table_name)
    if item.composite_signal:
        emit(
            RiskRuleId.COMPOSITE_SIGNAL_POINT,
            table_target,
            _counts_evidence(item),
        )
    else:
        if item.table_fact.status is ComparisonTableStatus.ADDED_TABLE:
            emit(
                RiskRuleId.TABLE_ADDED,
                table_target,
                (("row_count", item.table_fact.row_count_current),),
            )
        if item.table_fact.status is ComparisonTableStatus.DELETED_TABLE:
            emit(
                RiskRuleId.TABLE_DELETED,
                table_target,
                (("row_count", item.table_fact.row_count_before),),
            )
        if item.table_fact.status in {
            ComparisonTableStatus.SCHEMA_CHANGED,
            ComparisonTableStatus.SCHEMA_ONLY_CHANGED,
        } or _has_schema_changes(item):
            emit(RiskRuleId.SCHEMA_CHANGED, table_target)
        if item.comparison_failed:
            emit(RiskRuleId.COMPARISON_FAILED, table_target)
        if item.comparison_facts.degraded:
            emit(RiskRuleId.KEY_DEGRADED, table_target, _counts_evidence(item))
        if item.ordered_unsupported:
            emit(RiskRuleId.ORDERED_DIFF_UNSUPPORTED, table_target)
        if item.uncovered_targets:
            emit(
                RiskRuleId.UNKNOWN_CHANGE_TARGET,
                table_target,
                (("target", item.uncovered_targets[0]),),
            )
        ordered_counts: dict[RiskRuleId, int] = {}

        def emit_ordered(rule_id: RiskRuleId, target: RiskTarget,
                         evidence: tuple[tuple[str, str | int | bool | None], ...] = ()) -> None:
            if (evaluation_input.risk_options.annotation_detail_policy is AnnotationDetailPolicy.COUNTS_ONLY
                    and target.target_type is not RiskTargetType.TABLE):
                count = next((value for key, value in evidence if key == "count"), 1)
                assert isinstance(count, int)
                ordered_counts[rule_id] = ordered_counts.get(rule_id, 0) + count
            else:
                emit(rule_id, target, evidence)

        ordered = item.table_fact.ordered_extension
        if ordered is not None and not item.ordered_unsupported:
            if ordered.replay_guarantee is not ReplayGuarantee.EXACT:
                emit(RiskRuleId.ORDERED_RISK_UNKNOWN, table_target)
            else:
                _emit_ordered_moves(item, emit_ordered, evaluation_input, context, reserve_required)
                _emit_ordered_rows(item, emit_ordered, evaluation_input, context, reserve_required)
                summary = ordered.ordered_summary
                blank = item.table_fact.blank_extension
                if blank is not None and blank.replay_guarantee is not ReplayGuarantee.EXACT:
                    emit(RiskRuleId.ORDERED_RISK_UNKNOWN, table_target)
                else:
                    _emit_blank_intervals(item, emit_ordered, evaluation_input, context, reserve_required)
                if (summary.position_changed_count and not (summary.row_added_count or summary.row_deleted_count
                        or summary.row_moved_count or (blank is not None and blank.blank_summary.blank_changed_count))):
                    emit(RiskRuleId.ORDERED_RISK_UNKNOWN, table_target)
        elif ordered is None:
            if item.table_fact.blank_extension is not None and item.table_fact.blank_extension.blank_summary.blank_changed_count:
                raise _PairFailure("blank comparison lacks ordered extension")
            _emit_row_risks(item, emit, evaluation_input, policy, require_closure)
        for rule_id, count in ordered_counts.items():
            emit(rule_id, RiskTarget(target_type=RiskTargetType.TABLE,
                 table_name=item.table_fact.table_name, coverage="ROW_COUNTS"), (("count", count),))
        for record in item.records:
            if record.record_kind in {
                ComparisonRecordKind.SCHEMA_CHANGE,
                ComparisonRecordKind.TABLE_DEGRADED,
            }:
                continue
            if record_kind_name(record) is None:
                emit(
                    RiskRuleId.UNKNOWN_CHANGE_TARGET,
                    table_target,
                    (("target", record.record_kind.value),),
                )
    outcome = _TableOutcome(
        table_name=item.table_fact.table_name,
        source_table_status=item.table_fact.status,
        annotations=tuple(annotations),
        allow_artifact=not item.comparison_facts.degraded,
    )
    if recorder is not None:
        recorder.finish()
    return outcome


def _emit_ordered_moves(
    item: ExtractedRiskFacts,
    emit: _RiskEmitter,
    evaluation_input: RiskEvaluationInput,
    context: RiskExecutionContext,
    reserve_required: Callable[[int], RiskReservationPort],
) -> None:
    extension = item.table_fact.ordered_extension
    if extension is None or extension.ordered_summary.row_moved_count == 0:
        return
    expected = extension.ordered_summary.row_moved_count
    count = 0

    def emit_move(identity: DigestRef | None, position: int | None) -> None:
        nonlocal count
        if identity is None:
            raise _PairFailure("ordered move missing row identity")
        emit(RiskRuleId.ORDERED_MOVE, RiskTarget(
            target_type=RiskTargetType.ROW, table_name=item.table_fact.table_name,
            row_identity=identity, position=position,
        ))
        count += 1

    views = evaluation_input.ordered_record_views
    handle = None if views is None else views.get(item.table_fact.table_name)
    if handle is not None:
        reader = getattr(handle, "risk_record_batches")("ORDERED")
        with closing(reader):
            for batch in reader:
                if context.operation is not None:
                    context.operation.checkpoint()
                scratch = (nullcontext() if context.operation is None else reserve_required(8192 + batch.nbytes * 16 + batch.num_rows * 512))
                with scratch:
                    kinds = batch.column(batch.schema.get_field_index("record_kind")).to_pylist()
                    identities = batch.column(batch.schema.get_field_index("row_identity")).to_pylist()
                    positions = batch.column(batch.schema.get_field_index("current_position")).to_pylist()
                    for kind, identity, position in zip(kinds, identities, positions, strict=True):
                        if kind == OrderedRecordKind.ROW_MOVED.value:
                            emit_move(None if identity is None else DigestRef("sha256:" + identity.hex()), position)
    else:
        records = extension.records
        if not records and evaluation_input.records_access is not None:
            records = evaluation_input.records_access.get_ordered_records(item.table_fact.table_name)
        for record in records:
            if record.record_kind is OrderedRecordKind.ROW_MOVED:
                emit_move(record.row_identity, record.current_position)
    if count != expected:
        emit(RiskRuleId.ORDERED_RISK_UNKNOWN, RiskTarget(
            target_type=RiskTargetType.TABLE, table_name=item.table_fact.table_name))


def _emit_ordered_rows(
    item: ExtractedRiskFacts,
    emit: _RiskEmitter,
    evaluation_input: RiskEvaluationInput,
    context: RiskExecutionContext,
    reserve_required: Callable[[int], RiskReservationPort],
) -> None:
    extension = item.table_fact.ordered_extension
    if extension is None:
        return
    summary = extension.ordered_summary
    if not (summary.row_added_count or summary.row_deleted_count or summary.row_modified_count):
        return
    name = item.table_fact.table_name
    counts = {"ORDERED_ROW_ADDED": 0, "ORDERED_ROW_DELETED": 0, "ORDERED_ROW_MODIFIED": 0}
    added: dict[int, tuple[DigestRef, DigestRef | None, int | None]] = {}
    deleted: dict[int, DigestRef] = {}

    def consume(kind: str, identity: DigestRef | None, before: int | None,
                current: int | None, columns: tuple[str, ...],
                replacement_identity: DigestRef | None, replacement_position: int | None) -> None:
        if kind not in counts:
            return
        counts[kind] += 1
        if identity is None:
            raise _PairFailure("ordered row missing identity")
        if kind == "ORDERED_ROW_MODIFIED":
            rule = (RiskRuleId.ORDERED_NAME_UPDATE if columns and set(columns) <= {"name", "description"}
                    else RiskRuleId.ORDERED_CONTENT_UPDATE if columns
                    else RiskRuleId.ORDERED_RISK_UNKNOWN)
            emit(rule, RiskTarget(target_type=RiskTargetType.ROW, table_name=name,
                 row_identity=identity, position=current, changed_columns=columns))
            return
        position = current if kind == "ORDERED_ROW_ADDED" else before
        if position is None or position < 1:
            raise _PairFailure("ordered row missing position")
        if kind == "ORDERED_ROW_ADDED":
            if position in added or ((replacement_identity is None) != (replacement_position is None)):
                raise _PairFailure("invalid ordered replacement evidence")
            added[position] = (identity, replacement_identity, replacement_position)
        else:
            if position in deleted:
                raise _PairFailure("duplicate ordered row position")
            deleted[position] = identity

    with ExitStack() as charges:
        if context.operation is not None:
            charges.enter_context(reserve_required(4096 + (summary.row_added_count + summary.row_deleted_count) * 512))
        views = evaluation_input.ordered_record_views
        handle = None if views is None else views.get(name)
        if handle is not None:
            reader = getattr(handle, "risk_record_batches")("ORDERED")
            with closing(reader):
                for batch in reader:
                    if context.operation is not None:
                        context.operation.checkpoint()
                    scratch = (nullcontext() if context.operation is None else reserve_required(8192 + batch.nbytes * 16 + batch.num_rows * 512))
                    with scratch:
                        names = ("record_kind", "row_identity", "before_position", "current_position",
                                 "changed_columns", "replacement_before_identity", "replacement_before_position")
                        values = [batch.column(batch.schema.get_field_index(key)).to_pylist() for key in names]
                        for kind, identity, before, current, columns, partner, partner_position in zip(*values, strict=True):
                            consume(kind, None if identity is None else DigestRef("sha256:" + identity.hex()),
                                    before, current, tuple(columns or ()),
                                    None if partner is None else DigestRef("sha256:" + partner.hex()), partner_position)
        else:
            records = extension.records
            if not records and evaluation_input.records_access is not None:
                records = evaluation_input.records_access.get_ordered_records(name)
            for record in records:
                partner = record.replacement_before
                consume(record.record_kind.value, record.row_identity, record.before_position,
                        record.current_position, record.changed_columns,
                        None if partner is None else partner[0], None if partner is None else partner[1])
        if (counts["ORDERED_ROW_ADDED"] != summary.row_added_count
                or counts["ORDERED_ROW_DELETED"] != summary.row_deleted_count
                or counts["ORDERED_ROW_MODIFIED"] != summary.row_modified_count):
            emit(RiskRuleId.ORDERED_RISK_UNKNOWN, RiskTarget(target_type=RiskTargetType.TABLE, table_name=name))
        for position, (current_identity, partner_identity, partner_position) in sorted(added.items()):
            if partner_identity is None:
                continue
            if partner_position is None or deleted.get(partner_position) != partner_identity:
                raise _PairFailure("ordered replacement partner does not match deleted row")
            emit(RiskRuleId.ORDERED_REPLACEMENT, RiskTarget(
                target_type=RiskTargetType.ROW_PAIR, table_name=name, position=position,
                before_row_identity=partner_identity, current_row_identity=current_identity))
            deleted.pop(partner_position)
            added.pop(position)
        blank = item.table_fact.blank_extension
        fallback_positions = (added.keys() & deleted.keys()) if (
            blank is None or blank.blank_summary.blank_changed_count == 0) else ()
        for position in sorted(fallback_positions):
            emit(RiskRuleId.ORDERED_REPLACEMENT, RiskTarget(
                target_type=RiskTargetType.ROW_PAIR, table_name=name, position=position,
                before_row_identity=deleted.pop(position), current_row_identity=added.pop(position)[0]))
        maxima_map = evaluation_input.ordered_tail_bounds
        maxima = None if maxima_map is None else maxima_map.get(name)
        for rows, side in (({position: value[0] for position, value in added.items()}, "current"),
                           (deleted, "before")):
            opposite_max = None if maxima is None else (maxima.before_max_position if side == "current" else maxima.current_max_position)
            for position, identity in sorted(rows.items()):
                if maxima is None:
                    rule = RiskRuleId.ORDERED_RISK_UNKNOWN
                elif opposite_max is None or position > opposite_max:
                    rule = RiskRuleId.ORDERED_TAIL_INSERT_DELETE
                else:
                    rule = RiskRuleId.ORDERED_MIDDLE_INSERT_DELETE
                    if ordered_yk_name_applies(evaluation_input.risk_ruleset, name):
                        rule = RiskRuleId.ORDERED_MIDDLE_YK_INSERT_DELETE
                emit(rule, RiskTarget(target_type=RiskTargetType.ROW, table_name=name,
                     row_identity=identity, position=position), (("side", side.upper()),))


def _emit_blank_intervals(
    item: ExtractedRiskFacts,
    emit: _RiskEmitter,
    evaluation_input: RiskEvaluationInput,
    context: RiskExecutionContext,
    reserve_required: Callable[[int], RiskReservationPort],
) -> None:
    extension = item.table_fact.blank_extension
    if extension is None or not extension.blank_summary.blank_changed_count:
        return
    maxima_map = evaluation_input.ordered_tail_bounds
    maxima = None if maxima_map is None else maxima_map.get(item.table_fact.table_name)
    if maxima is None or not maxima.complete:
        emit(RiskRuleId.ORDERED_RISK_UNKNOWN, RiskTarget(
            target_type=RiskTargetType.TABLE, table_name=item.table_fact.table_name))
        return
    inserted = deleted = 0

    def emit_interval(kind: str, interval: Mapping[str, object]) -> None:
        nonlocal inserted, deleted
        if kind == "BLANK_INSERT_INTERVAL":
            side, maximum, last = "current", maxima.current_max_position, maxima.current_last_retained_position
            inserted += 1
        elif kind == "BLANK_DELETE_INTERVAL":
            side, maximum, last = "before", maxima.before_max_position, maxima.before_last_retained_position
            deleted += 1
        else:
            raise _PairFailure("unexpected blank interval record")
        start, end, count = interval.get(f"{side}_start"), interval.get(f"{side}_end"), interval.get("row_count")
        if (type(start) is not int or type(end) is not int or type(count) is not int
                or start < 1 or end < start or count < 1 or maximum is None or end > maximum):
            raise _PairFailure("invalid blank interval position")
        rule = (RiskRuleId.ORDERED_TAIL_BLANK_INTERVAL if last is None or last < start
                else RiskRuleId.ORDERED_MIDDLE_BLANK_INTERVAL)
        if rule is RiskRuleId.ORDERED_MIDDLE_BLANK_INTERVAL and ordered_yk_name_applies(evaluation_input.risk_ruleset, item.table_fact.table_name):
            rule = RiskRuleId.ORDERED_MIDDLE_YK_BLANK_INTERVAL
        emit(rule, RiskTarget(target_type=RiskTargetType.ROW_INTERVAL,
             table_name=item.table_fact.table_name, position_range=(start, end)),
             (("count", count), ("side", side.upper())))

    views = evaluation_input.ordered_record_views
    handle = None if views is None else views.get(item.table_fact.table_name)
    if handle is not None:
        reader = getattr(handle, "risk_record_batches")("BLANK")
        with closing(reader):
            for batch in reader:
                if context.operation is not None:
                    context.operation.checkpoint()
                scratch = (nullcontext() if context.operation is None else reserve_required(8192 + batch.nbytes * 16 + batch.num_rows * 512))
                with scratch:
                    kinds = batch.column(batch.schema.get_field_index("record_kind")).to_pylist()
                    names = ("before_start", "before_end", "current_start", "current_end", "row_count")
                    values = [batch.column(batch.schema.get_field_index(key)).to_pylist() for key in names]
                    for kind, row in zip(kinds, zip(*values, strict=True), strict=True):
                        emit_interval(kind, dict(zip(names, row, strict=True)))
    else:
        for record in extension.records:
            interval = record.interval
            emit_interval(record.record_kind.value, {
                "before_start": interval.before_start, "before_end": interval.before_end,
                "current_start": interval.current_start, "current_end": interval.current_end,
                "row_count": interval.row_count,
            })
    if (inserted != extension.blank_summary.interval_inserted_count
            or deleted != extension.blank_summary.interval_deleted_count):
        emit(RiskRuleId.ORDERED_RISK_UNKNOWN, RiskTarget(
            target_type=RiskTargetType.TABLE, table_name=item.table_fact.table_name))


def _emit_row_risks(
    item: ExtractedRiskFacts,
    emit: _RiskEmitter,
    evaluation_input: RiskEvaluationInput,
    policy: RiskExecutionPolicy,
    require_closure: Callable[[], None],
) -> None:
    table = item.table_fact
    emit_added, emit_deleted, name_low = standard_rule_applicability(
        evaluation_input.risk_ruleset, table.table_name,
    )
    counts = {
        ComparisonRecordKind.ROW_ADDED: table.row_added_count,
        ComparisonRecordKind.ROW_DELETED: table.row_deleted_count,
        ComparisonRecordKind.ROW_MODIFIED: table.row_modified_count,
    }
    suppressed_counts = {
        ComparisonRecordKind.ROW_ADDED: table.suppressed_added_count,
        ComparisonRecordKind.ROW_DELETED: table.suppressed_deleted_count,
        ComparisonRecordKind.ROW_MODIFIED: 0,
    }
    for record_kind, count in counts.items():
        if count <= 0:
            continue
        if ((record_kind is ComparisonRecordKind.ROW_ADDED and not emit_added)
                or (record_kind is ComparisonRecordKind.ROW_DELETED and not emit_deleted)):
            continue
        rule_id = {
            ComparisonRecordKind.ROW_ADDED: RiskRuleId.ROW_ADDED,
            ComparisonRecordKind.ROW_DELETED: RiskRuleId.ROW_DELETED,
            ComparisonRecordKind.ROW_MODIFIED: RiskRuleId.ROW_MODIFIED,
        }[record_kind]
        if evaluation_input.risk_options.annotation_detail_policy is AnnotationDetailPolicy.COUNTS_ONLY:
            emit(rule_id, RiskTarget(target_type=RiskTargetType.TABLE, table_name=table.table_name, coverage="ROW_COUNTS"), (("count", count),))
            continue
        matching_count = 0
        for record in item.records:
            if record.record_kind is not record_kind:
                continue
            matching_count += 1
            target = RiskTarget(
                target_type=RiskTargetType.ROW,
                table_name=table.table_name,
                row_identity=record.row_identity,
                changed_columns=record.changed_columns,
            )
            actual_rule = (RiskRuleId.STANDARD_NAME_UPDATE
                if record_kind is ComparisonRecordKind.ROW_MODIFIED
                and name_low and bool(record.changed_columns)
                and set(record.changed_columns) <= {"name", "description"} else rule_id)
            emit(actual_rule, target)
        if not matching_count:
            if suppressed_counts[record_kind] == count:
                emit(
                    rule_id,
                    RiskTarget(
                        target_type=RiskTargetType.TABLE,
                        table_name=table.table_name,
                        coverage="ROW_RECORDS_SUPPRESSED",
                    ),
                    (("count", count),),
                )
                continue
            require_closure()
            emit(rule_id, RiskTarget(target_type=RiskTargetType.TABLE, table_name=table.table_name, coverage="ROW_RECORDS_UNAVAILABLE"), (("count", count),))
        if matching_count < count:
            emit(
                rule_id,
                RiskTarget(target_type=RiskTargetType.TABLE, table_name=table.table_name, coverage="ROW_RECORDS_SUPPRESSED"),
                (("count", count - matching_count),),
            )
def _require_records_closure(item: ExtractedRiskFacts, evaluation_input: RiskEvaluationInput) -> None:
    access = evaluation_input.records_access
    if access is None:
        raise _PairFailure("records closure is required for requested row annotation detail")
    try:
        closure = access.get_records_closure()
    except Exception as exc:
        raise _PairFailure("records closure could not be opened") from exc
    if not isinstance(closure, ComparisonRecordsClosure):
        raise _PairFailure("records closure has an invalid type")
    if closure.comparison_digest != evaluation_input.comparison_facts.comparison_digest:
        raise _PairFailure("records closure comparison digest mismatch")
    if closure.facts_core_digest != evaluation_input.comparison_facts.facts_core_digest:
        raise _PairFailure("records closure facts digest mismatch")
    if not any(entry.table_name == item.table_fact.table_name for entry in closure.records):
        raise _PairFailure("records closure is missing the requested table")


def _publish_result(
    evaluation_input: RiskEvaluationInput,
    outcomes: list[_TableOutcome],
    artifact_store: ArtifactStorePort | None,
    policy: RiskExecutionPolicy,
    degraded: bool,
    context: RiskExecutionContext,
) -> RiskEvaluationResult:
    table_risks: list[RiskTableRisk] = []
    artifacts: list[RiskAnnotationArtifact] = []
    closure_entries: list[RiskAnnotationClosureEntry] = []
    manifest_digests: list[DigestRef] = []
    for outcome in outcomes:
        if not outcome.annotations:
            if context.attribution_observer is not None:
                context.attribution_observer(outcome.table_name, (), not outcome.degraded)
            continue
        level = max((item.risk_level for item in outcome.annotations), key=lambda value: _LEVEL_RANK[value])
        reason_codes = tuple(
            sorted(
                {reason.reason_code for annotation in outcome.annotations for reason in annotation.reasons},
                key=lambda value: value.value,
            )
        )
        artifact: RiskAnnotationArtifact | None = None
        if outcome.allow_artifact and evaluation_input.risk_options.annotation_detail_policy is not AnnotationDetailPolicy.COUNTS_ONLY:
            if artifact_store is None:
                raise _PairFailure("artifact store is required for annotation details")
            artifact_started = perf_counter()
            try:
                artifact = publish_annotation_artifact(
                    artifact_store,
                    table_name=outcome.table_name,
                    annotations=outcome.annotations,
                    max_bytes=policy.max_annotation_artifact_bytes_per_table,
                    on_memory_pressure=lambda: _evict_optional_risk_only(
                        evaluation_input.risk_cache_session,
                    ),
                    operation=context.operation,
                )
            except RiskArtifactError as exc:
                if "exceeds table byte budget" not in str(exc):
                    raise
                degraded = True
                artifact = None
            finally:
                _record_timing(evaluation_input, "artifact_publication_seconds", artifact_started)
            if artifact is not None:
                artifacts.append(artifact)
                manifest_digests.append(artifact.manifest_digest)
        artifact_requested = evaluation_input.risk_options.annotation_detail_policy is not AnnotationDetailPolicy.COUNTS_ONLY
        if context.attribution_observer is not None:
            context.attribution_observer(
                outcome.table_name, outcome.annotations,
                not outcome.degraded and not (
                    artifact_requested and outcome.allow_artifact and artifact is None
                ),
            )
        table_risks.append(
            RiskTableRisk(
                table_name=outcome.table_name,
                risk_level=level,
                reason_codes=reason_codes,
                annotation_count=len(outcome.annotations),
                source_table_status=outcome.source_table_status,
                annotation_ref=None if artifact is None else artifact.content_ref,
                diagnostics=outcome.diagnostics
                + (("RISK_ANNOTATION_ARTIFACT_BUDGET_EXCEEDED",) if artifact is None and outcome.allow_artifact and artifact_requested else ()),
            )
        )
        if artifact_requested:
            closure_entries.append(
                RiskAnnotationClosureEntry(
                    table_name=outcome.table_name,
                    annotation_count=len(outcome.annotations),
                    artifact=artifact,
                    no_record_reason_codes=() if artifact is not None else reason_codes,
                )
            )
    return _finish_result(
        evaluation_input,
        tuple(table_risks),
        tuple(artifacts),
        tuple(closure_entries),
        tuple(manifest_digests),
        artifact_store,
        policy,
        degraded,
        context,
    )


def _finish_result(
    evaluation_input: RiskEvaluationInput,
    table_risks: tuple[RiskTableRisk, ...],
    artifacts: tuple[RiskAnnotationArtifact, ...],
    closure_entries: tuple[RiskAnnotationClosureEntry, ...],
    manifest_digests: tuple[DigestRef, ...],
    artifact_store: ArtifactStorePort | None,
    policy: RiskExecutionPolicy,
    degraded: bool,
    context: RiskExecutionContext,
) -> RiskEvaluationResult:
    operation = context.operation
    publication = (nullcontext() if operation is None else _reserve_risk_output(
        operation,
        8 * (policy.max_risk_evaluation_json_bytes
             + policy.max_risk_report_json_bytes)
        + len(table_risks) * 8192,
        evaluation_input.risk_cache_session,
    ))
    with publication:
        return _finish_result_admitted(
            evaluation_input, table_risks, artifacts, closure_entries,
            manifest_digests, artifact_store, policy, degraded,
        )


def _finish_result_admitted(
    evaluation_input: RiskEvaluationInput,
    table_risks: tuple[RiskTableRisk, ...],
    artifacts: tuple[RiskAnnotationArtifact, ...],
    closure_entries: tuple[RiskAnnotationClosureEntry, ...],
    manifest_digests: tuple[DigestRef, ...],
    artifact_store: ArtifactStorePort | None,
    policy: RiskExecutionPolicy,
    degraded: bool,
) -> RiskEvaluationResult:
    levels = tuple(item.risk_level for item in table_risks)
    is_replacement = (
        evaluation_input.comparison_facts.comparison_mode is ComparisonMode.DATASET_REPLACEMENT
    )
    if is_replacement:
        pair_rule = next(
            item
            for item in evaluation_input.risk_ruleset.rules
            if item.rule_id is RiskRuleId.PROJECT_IDENTITY_MISMATCH
        )
        reason_codes: tuple[RiskReasonCode, ...] = (reason_for(pair_rule),)
        summary = RiskSummary(
            risk_level=level_for(pair_rule),
            reason_codes=reason_codes,
            table_count=0,
            annotation_count=0,
        )
    else:
        reason_codes = tuple(
            sorted({code for item in table_risks for code in item.reason_codes}, key=lambda value: value.value)
        )
        summary = RiskSummary(
            risk_level=None if not levels else max(levels, key=lambda value: _LEVEL_RANK[value]),
            reason_codes=reason_codes,
            table_count=len(table_risks),
            annotation_count=sum(item.annotation_count for item in table_risks),
        )
    ruleset_digest = evaluation_input.risk_ruleset.risk_ruleset_digest
    if ruleset_digest is None:
        raise _PairFailure("risk ruleset digest is missing")
    manifest_refs = tuple(item for item in manifest_digests)
    digest_started = perf_counter()
    evaluation_digest = compute_risk_evaluation_digest(
        comparison_digest=evaluation_input.comparison_facts.comparison_digest,
        risk_contract_version=evaluation_input.risk_contract_version,
        risk_model_version=evaluation_input.risk_model_version,
        risk_ruleset_digest=ruleset_digest,
        risk_options=evaluation_input.risk_options,
        table_risks=table_risks,
        annotation_manifest_digests=manifest_refs,
    )
    _record_timing(evaluation_input, "digest_jcs_seconds", digest_started)
    annotation_refs = tuple(item.annotation_ref for item in table_risks if item.annotation_ref is not None)
    evaluation = RiskEvaluation(
        risk_evaluation_digest=evaluation_digest,
        risk_contract_version=evaluation_input.risk_contract_version,
        risk_model_version=evaluation_input.risk_model_version,
        risk_ruleset_digest=ruleset_digest,
        comparison_digest=evaluation_input.comparison_facts.comparison_digest,
        summary=summary,
        table_risks=table_risks,
        annotation_refs=annotation_refs,
    )
    report = RiskReport(
        risk_report_contract_version=evaluation_input.risk_contract_version,
        risk_evaluation_digest=evaluation_digest,
        overall=summary,
        tables=table_risks,
        annotation_refs=annotation_refs,
    )
    report_jcs_started = perf_counter()
    evaluation_size = len(canonicalize_json_value(evaluation.to_document()))
    _record_timing(evaluation_input, "report_jcs_seconds", report_jcs_started)
    if evaluation_size > policy.max_risk_evaluation_json_bytes:
        raise _PairFailure("risk evaluation JSON budget exceeded")
    report_jcs_started = perf_counter()
    report_size = len(canonicalize_json_value(report.to_document()))
    _record_timing(evaluation_input, "report_jcs_seconds", report_jcs_started)
    if report_size > policy.max_risk_report_json_bytes:
        raise _PairFailure("risk report JSON budget exceeded")
    closure = None
    if closure_entries and artifact_store is not None:
        artifact_started = perf_counter()
        closure = publish_annotation_closure(
            artifact_store,
            comparison_digest=evaluation_input.comparison_facts.comparison_digest,
            risk_evaluation_digest=evaluation_digest,
            entries=closure_entries,
        )
        _record_timing(evaluation_input, "artifact_publication_seconds", artifact_started)
    return RiskEvaluationResult(
        status=RiskEvaluationStatus.DEGRADED if degraded else RiskEvaluationStatus.READY,
        risk_evaluation=evaluation,
        risk_report=report,
        annotation_artifacts=artifacts,
        risk_closure=closure,
    )


def _build_pair_degraded_without_annotations(
    evaluation_input: RiskEvaluationInput,
    extracted: tuple[ExtractedRiskFacts, ...],
    rules: Mapping[RiskRuleId, RiskRuleSpec],
    policy: RiskExecutionPolicy,
    context: RiskExecutionContext,
) -> RiskEvaluationResult:
    degraded_rule = rules[RiskRuleId.KEY_DEGRADED]
    table_risks = tuple(
        RiskTableRisk(
            table_name=item.table_fact.table_name,
            risk_level=level_for(degraded_rule),
            reason_codes=(reason_for(degraded_rule),),
            annotation_count=0,
            source_table_status=item.table_fact.status,
            diagnostics=("RISK_ANNOTATION_LIMIT_EXCEEDED",),
        )
        for item in extracted
        if has_visible_change(item)
    )
    if context.attribution_observer is not None:
        for item in extracted:
            if has_visible_change(item):
                # The pair-cap owner has just established a TABLE degradation,
                # rather than an unknown collection of partial row annotations.
                # Expose that actual typed outcome transiently; the published
                # payload above deliberately keeps annotation_count=0.
                outcome = _degraded_table(item, "RISK_ANNOTATION_LIMIT_EXCEEDED", rules,
                    evaluation_input.risk_cache_session, context.operation)
                with outcome.charges:
                    context.attribution_observer(item.table_fact.table_name, outcome.annotations, False)
            else:
                context.attribution_observer(item.table_fact.table_name, (), False)
    # Discard every partial annotation and preserve an explicit degraded table-level risk for
    # each visible change. This keeps the pair-level failure observable downstream without
    # publishing a partial annotation closure.
    return _finish_result(
        evaluation_input,
        table_risks,
        (),
        (),
        (),
        None,
        policy,
        True,
        context,
    )


def _degraded_table(
    item: ExtractedRiskFacts,
    diagnostic: str,
    rules: Mapping[RiskRuleId, RiskRuleSpec],
    cache: object | None,
    operation: RiskOperationPort | None,
) -> _TableOutcome:
    rule = rules[RiskRuleId.KEY_DEGRADED]
    reason_code = reason_for(rule)
    with ExitStack() as charges:
        if operation is not None:
            charges.enter_context(_reserve_risk_output(
                operation,
                4096 + (len(item.table_fact.table_name) + len(diagnostic)) * 32,
                cache,
            ))
        annotation = RiskAnnotation(
            annotation_id=f"{item.table_fact.table_name}:degraded",
            risk_level=level_for(rule),
            target=RiskTarget(target_type=RiskTargetType.TABLE, table_name=item.table_fact.table_name),
            reasons=(
                RiskReason(
                    reason_code=reason_code,
                    message=_MESSAGES[reason_code],
                    rule_id=RiskRuleId.KEY_DEGRADED,
                    evidence=(("diagnostic", diagnostic),),
                ),
            ),
        )
        return _TableOutcome(
            table_name=item.table_fact.table_name,
            source_table_status=item.table_fact.status,
            annotations=(annotation,),
            degraded=True,
            allow_artifact=False,
            diagnostics=(diagnostic,),
            charges=charges.pop_all(),
        )


def _include_level(level: RiskLevel, evaluation_input: RiskEvaluationInput) -> bool:
    if level is RiskLevel.UNKNOWN and not evaluation_input.risk_options.include_unknown:
        return False
    if level in {RiskLevel.LOW, RiskLevel.MEDIUM_LOW} and not evaluation_input.risk_options.include_low_risk:
        return False
    return True


def _counts_evidence(item: ExtractedRiskFacts) -> tuple[tuple[str, str | int | bool | None], ...]:
    table = item.table_fact
    return (
        ("row_added_count", table.row_added_count),
        ("row_deleted_count", table.row_deleted_count),
        ("row_modified_count", table.row_modified_count),
    )


def _has_schema_changes(item: ExtractedRiskFacts) -> bool:
    changes = item.table_fact.schema_changes
    return bool(
        changes.schema_evolution in {SchemaEvolution.COLUMNS_REMOVED, SchemaEvolution.INCOMPATIBLE}
        or changes.effective_compare_key_changed
    )


def _check_table(
    context: RiskExecutionContext,
    table_started: float,
    pair_started: float,
    policy: RiskExecutionPolicy,
) -> None:
    _check_pair(context, pair_started, policy)
    if context.clock() - table_started >= policy.max_risk_table_wall_time_seconds:
        raise _TableBudgetExceeded


def _check_pair(context: RiskExecutionContext, pair_started: float, policy: RiskExecutionPolicy) -> None:
    if context.cancellation_requested():
        raise _PairCancelled("risk evaluation cancelled")
    if context.deadline_expired():
        raise _PairCancelled("risk evaluation deadline exceeded")
    if context.clock() - pair_started >= policy.max_risk_pair_wall_time_seconds:
        raise _PairCancelled("max_risk_pair_wall_time_seconds exceeded")
