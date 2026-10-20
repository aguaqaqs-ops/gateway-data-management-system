"""Bounded Python reference Risk evaluator."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from gateway_backend.artifacts import ArtifactStorePort
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonMode,
    ComparisonRecordKind,
    ComparisonRecordsClosure,
    ComparisonTableStatus,
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
    try:
        rules = validate_risk_ruleset(evaluation_input.risk_ruleset)
        if evaluation_input.comparison_facts.comparison_mode is ComparisonMode.DATASET_REPLACEMENT:
            return _publish_result(
                evaluation_input,
                [],
                artifact_store,
                execution_policy,
                degraded=False,
            )
        source_tables = evaluation_input.comparison_facts.tables
        if len(source_tables) > execution_policy.max_risk_tables_per_pair:
            raise _PairFailure("max_risk_tables_per_pair exceeded")
        _check_pair(context, pair_started, execution_policy)
        extracted = extract_risk_facts(
            evaluation_input.comparison_facts,
            evaluation_input.requested_tables,
        )
        outcomes: list[_TableOutcome] = []
        total_annotations = 0
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
                total_annotations += len(outcome.annotations)
            except _TableBudgetExceeded:
                outcomes.append(_degraded_table(item, "risk table budget exceeded", rules))
            except _PairAnnotationBudgetExceeded:
                return _build_pair_degraded_without_annotations(
                    evaluation_input,
                    extracted,
                    rules,
                    execution_policy,
                )
        # Publication is the terminal commit boundary; cancellation is observed before it,
        # and a result that has crossed the boundary is never converted back to CANCELLED.
        _check_pair(context, pair_started, execution_policy)
        result = _publish_result(
            evaluation_input,
            outcomes,
            artifact_store,
            execution_policy,
            any(item.degraded for item in outcomes),
        )
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
    table_started = context.clock()
    annotations: list[RiskAnnotation] = []

    if (
        len(item.comparison_facts.diagnostics) > policy.max_diagnostics_per_table
        or len(canonicalize_json_value(list(item.comparison_facts.diagnostics)))
        > policy.max_diagnostics_bytes_per_table
    ):
        return _degraded_table(item, "risk diagnostics truncated", rules)

    def emit(
        rule_id: RiskRuleId,
        target: RiskTarget,
        evidence: tuple[tuple[str, str | int | bool | None], ...] = (),
    ) -> None:
        if len(annotations) >= min(policy.max_annotations_per_table, annotation_limit):
            if len(annotations) >= annotation_limit:
                raise _PairAnnotationBudgetExceeded
            raise _TableBudgetExceeded
        rule = rules[rule_id]
        reason_code = reason_for(rule)
        level = level_for(rule)
        if not _include_level(level, evaluation_input):
            return
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

    table_target = RiskTarget(target_type=RiskTargetType.TABLE, table_name=item.table_fact.table_name)
    if item.composite_signal:
        emit(
            RiskRuleId.COMPOSITE_SIGNAL_POINT,
            table_target,
            _counts_evidence(item),
        )
    else:
        if item.table_fact.status is ComparisonTableStatus.ADDED_TABLE:
            emit(RiskRuleId.TABLE_ADDED, table_target)
        if item.table_fact.status is ComparisonTableStatus.DELETED_TABLE:
            emit(RiskRuleId.TABLE_DELETED, table_target)
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
    return _TableOutcome(
        table_name=item.table_fact.table_name,
        source_table_status=item.table_fact.status,
        annotations=tuple(annotations),
        allow_artifact=not item.comparison_facts.degraded,
    )


def _emit_row_risks(
    item: ExtractedRiskFacts,
    emit: _RiskEmitter,
    evaluation_input: RiskEvaluationInput,
    policy: RiskExecutionPolicy,
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
            _require_records_closure(item, evaluation_input)
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
            try:
                artifact = publish_annotation_artifact(
                    artifact_store,
                    table_name=outcome.table_name,
                    annotations=outcome.annotations,
                    max_bytes=policy.max_annotation_artifact_bytes_per_table,
                )
            except RiskArtifactError as exc:
                if "exceeds table byte budget" not in str(exc):
                    raise
                degraded = True
                artifact = None
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
        reason_codes = (reason_for(pair_rule),)
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
    evaluation_digest = compute_risk_evaluation_digest(
        comparison_digest=evaluation_input.comparison_facts.comparison_digest,
        risk_contract_version=evaluation_input.risk_contract_version,
        risk_model_version=evaluation_input.risk_model_version,
        risk_ruleset_digest=ruleset_digest,
        risk_options=evaluation_input.risk_options,
        table_risks=table_risks,
        annotation_manifest_digests=manifest_refs,
    )
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
    if len(canonicalize_json_value(evaluation.to_document())) > policy.max_risk_evaluation_json_bytes:
        raise _PairFailure("risk evaluation JSON budget exceeded")
    if len(canonicalize_json_value(report.to_document())) > policy.max_risk_report_json_bytes:
        raise _PairFailure("risk report JSON budget exceeded")
    closure = None
    if closure_entries and artifact_store is not None:
        closure = publish_annotation_closure(
            artifact_store,
            comparison_digest=evaluation_input.comparison_facts.comparison_digest,
            risk_evaluation_digest=evaluation_digest,
            entries=closure_entries,
        )
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
) -> _TableOutcome:
    rule = rules[RiskRuleId.KEY_DEGRADED]
    reason_code = reason_for(rule)
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
        changes.before_only_columns
        or changes.current_only_columns
        or changes.incompatible_columns
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
