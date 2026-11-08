"""Bounded Python reference Risk evaluator."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import ExitStack
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from time import perf_counter

from gateway_backend.artifacts import ArtifactStorePort
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonMode,
    ComparisonRecordKind,
    ComparisonRecordsClosure,
    ComparisonTableStatus,
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
    reason_for,
    validate_risk_ruleset,
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
    V1_RISK_RULE_SPECS,
    compute_risk_evaluation_digest,
)
from gateway_shared_kernel import DigestRef
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.capabilities.table_access import (
    KernelExecutionContext, Reservation, current_kernel_context,
)


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


@dataclass(frozen=True, slots=True)
class _RiskEmitEvent:
    rule_id: RiskRuleId
    target: RiskTarget
    evidence: tuple[tuple[str, str | int | bool | None], ...]


@dataclass(frozen=True, slots=True)
class _RiskCheckClosure:
    pass


_CHECK_CLOSURE = _RiskCheckClosure()
_RISK_CACHE_KEY_PROVISIONAL_BYTES = 16 * 1024**2


def _evict_optional_risk_only(cache: object | None) -> bool:
    evict = None if cache is None else getattr(cache, "risk_evict_for_output", None)
    if not callable(evict):
        return False
    evict()
    return True


def _reserve_risk_output(
    operation: KernelExecutionContext, size: int, cache: object | None,
) -> Reservation:
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
) -> tuple[str | None, Reservation | None]:
    """Pay for an optional complete key before its repr can grow."""
    operation = current_kernel_context()
    digest = item.table_fact.table_fact_digest
    ruleset = evaluation_input.risk_ruleset
    if (operation is None or digest is None
            or ruleset.rules != V1_RISK_RULE_SPECS):
        return None, None
    # The v1 rule body and option enum are fixed. Only three diagnostics
    # vectors have caller-controlled length; count their worst-case repr and
    # intermediate copies before allocating any key string.
    upper = 64 * 1024
    for diagnostics in (
        item.table_fact.diagnostics,
        evaluation_input.comparison_facts.diagnostics,
        item.comparison_facts.diagnostics,
    ):
        for diagnostic in diagnostics:
            upper += 4096 + len(diagnostic) * 256
            if upper > _RISK_CACHE_KEY_PROVISIONAL_BYTES:
                return None, None
    try:
        charge = operation.memory.reserve(_RISK_CACHE_KEY_PROVISIONAL_BYTES)
    except MemoryError:
        return None, None
    try:
        key = repr((
            digest.value,
            item.table_fact.diagnostics,
            evaluation_input.comparison_facts.diagnostics,
            item.comparison_facts.diagnostics,
            evaluation_input.risk_ruleset,
            evaluation_input.risk_options,
            policy.policy_version,
        ))
        actual = len(key) * 8 + 512
        if actual > _RISK_CACHE_KEY_PROVISIONAL_BYTES:
            charge.close()
            return None, None
        charge.shrink_to(actual)
        return key, charge
    except BaseException:
        charge.close()
        raise


class _RiskCandidateRecorder:
    """Store complete candidate/control events only for a known later use."""

    def __init__(self, cache: object, task_key: str, risk_key: str) -> None:
        self.cache = cache
        self.task_key = task_key
        self.risk_key = risk_key
        self.events: list[_RiskEmitEvent | _RiskCheckClosure] = []
        self.charges = ExitStack()
        self.enabled = True

    def append(self, event: _RiskEmitEvent | _RiskCheckClosure) -> None:
        if not self.enabled:
            return
        operation = current_kernel_context()
        if operation is None:
            self.close()
            return
        size = 1024
        if isinstance(event, _RiskEmitEvent):
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
        self.events.append(event)

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
        operation = current_kernel_context()
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
                    item, "risk table budget exceeded", rules,
                    evaluation_input.risk_cache_session,
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
            item, "risk diagnostics truncated", rules,
            evaluation_input.risk_cache_session,
        )

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
            recorder.append(_RiskEmitEvent(rule_id, target, evidence))
        rule = rules[rule_id]
        reason_code = reason_for(rule)
        level = level_for(rule)
        if not _include_level(level, evaluation_input):
            return
        operation = current_kernel_context()
        if operation is not None and not prepaid_cached_output:
            size = 2048 + len(item.table_fact.table_name) * 16
            size += sum(len(column) * 16 + 128 for column in target.changed_columns)
            size += sum((len(name) + len(str(value))) * 16 + 128 for name, value in evidence)
            try:
                reservation = operation.memory.reserve(size)
            except MemoryError:
                if recorder is not None:
                    recorder.close()
                if not _evict_optional_risk_only(evaluation_input.risk_cache_session):
                    if recorder is None:
                        raise
                operation.checkpoint()
                reservation = operation.memory.reserve(size)
            charges.enter_context(reservation)
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
    if (cache is not None and task_key is not None and not item.composite_signal
            and item.table_fact.table_fact_digest is not None):
        risk_key, key_charge = _optional_risk_cache_key(item, evaluation_input, policy)
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
                        if isinstance(event, _RiskEmitEvent):
                            upper += 2048 + len(item.table_fact.table_name) * 16
                            upper += sum(len(column) * 16 + 128
                                         for column in event.target.changed_columns)
                            upper += sum((len(name) + len(str(value))) * 16 + 128
                                         for name, value in event.evidence)
                    operation = current_kernel_context()
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
                    if remaining.get(task_key, 0) > 1 and not cache_rejected:
                        recorder = _RiskCandidateRecorder(cache, task_key, risk_key)
                        recorder.charges.enter_context(key_charge)
                        key_charge = None
                        charges.callback(recorder.close)
            finally:
                if key_charge is not None:
                    key_charge.close()
                risk_key = None

    def require_closure() -> None:
        if recorder is not None:
            recorder.append(_CHECK_CLOSURE)
        _require_records_closure(item, evaluation_input)

    if cached_events is not None:
        for index, event in enumerate(cached_events):
            if index % 1024 == 0:
                operation = current_kernel_context()
                if operation is not None:
                    operation.checkpoint()
            if isinstance(event, _RiskCheckClosure):
                require_closure()
            elif isinstance(event, _RiskEmitEvent):
                emit(event.rule_id, event.target, event.evidence)
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
        _emit_row_risks(
            item,
            emit,
            evaluation_input,
            policy,
            require_closure,
        )
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


def _emit_row_risks(
    item: ExtractedRiskFacts,
    emit: _RiskEmitter,
    evaluation_input: RiskEvaluationInput,
    policy: RiskExecutionPolicy,
    require_closure: Callable[[], None],
) -> None:
    table = item.table_fact
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
            emit(rule_id, target)
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
) -> RiskEvaluationResult:
    table_risks: list[RiskTableRisk] = []
    artifacts: list[RiskAnnotationArtifact] = []
    closure_entries: list[RiskAnnotationClosureEntry] = []
    manifest_digests: list[DigestRef] = []
    for outcome in outcomes:
        if not outcome.annotations:
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
        table_risks.append(
            RiskTableRisk(
                table_name=outcome.table_name,
                risk_level=level,
                reason_codes=reason_codes,
                annotation_count=len(outcome.annotations),
                source_table_status=outcome.source_table_status,
                annotation_ref=None if artifact is None else artifact.content_ref,
                diagnostics=outcome.diagnostics
                + (("annotation artifact budget exceeded",) if artifact is None and outcome.allow_artifact and artifact_requested else ()),
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
) -> RiskEvaluationResult:
    operation = current_kernel_context()
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
) -> RiskEvaluationResult:
    degraded_rule = rules[RiskRuleId.KEY_DEGRADED]
    table_risks = tuple(
        RiskTableRisk(
            table_name=item.table_fact.table_name,
            risk_level=level_for(degraded_rule),
            reason_codes=(reason_for(degraded_rule),),
            annotation_count=0,
            source_table_status=item.table_fact.status,
            diagnostics=("max_annotations_per_pair exceeded",),
        )
        for item in extracted
        if has_visible_change(item)
    )
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
    )


def _degraded_table(
    item: ExtractedRiskFacts,
    diagnostic: str,
    rules: Mapping[RiskRuleId, RiskRuleSpec],
    cache: object | None,
) -> _TableOutcome:
    rule = rules[RiskRuleId.KEY_DEGRADED]
    reason_code = reason_for(rule)
    with ExitStack() as charges:
        operation = current_kernel_context()
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
