from __future__ import annotations

from dataclasses import dataclass

from ...core.diagnostics import DiagnosticRecord
from ..comparison.models import ComparisonStatus
from .aggregation import (
    assign_annotation_ids,
    build_risk_evaluation_digest,
    build_summary,
    build_table_risks,
    merge_annotations,
)
from .artifacts import RiskAnnotationArtifact
from .facts_extractor import extract_risk_facts
from .models import (
    RiskAnnotation,
    RiskEvaluation,
    RiskEvaluationInput,
    RiskEvaluationResult,
    RiskLevel,
    RiskOptions,
    RiskReason,
    RiskTarget,
    RiskTargetType,
)
from .rules.degraded import build_degraded_annotations
from .rules.ordered import build_ordered_annotations
from .rules.ordered_placeholder import build_ordered_placeholder_annotations
from .rules.standard_basic import build_standard_annotations
from .rules.structural import build_structural_annotations


@dataclass(frozen=True, slots=True)
class RiskEngine:
    def evaluate(self, risk_input: RiskEvaluationInput) -> RiskEvaluationResult:
        if not isinstance(risk_input, RiskEvaluationInput):
            raise TypeError("risk_input must be a RiskEvaluationInput")

        facts = extract_risk_facts(
            risk_input.comparison_facts,
            requested_tables=risk_input.requested_tables,
            records_access=risk_input.records_access,
        )

        annotations: list[RiskAnnotation] = []
        for fact in facts:
            annotations.extend(build_structural_annotations(fact, risk_input.risk_ruleset))
            annotations.extend(build_standard_annotations(fact, risk_input.risk_ruleset))
            annotations.extend(build_ordered_annotations(fact, risk_input.risk_ruleset))
            annotations.extend(build_ordered_placeholder_annotations(fact, risk_input.risk_ruleset))
            annotations.extend(build_degraded_annotations(fact, risk_input.risk_ruleset))

        annotations.extend(
            _comparison_failed_annotation(
                comparison_status=_comparison_status(risk_input),
                diagnostics=risk_input.comparison_facts.diagnostics,
            )
        )

        merged_annotations = merge_annotations(annotations)
        filtered_annotations = tuple(
            annotation
            for annotation in merged_annotations
            if _annotation_allowed(annotation, risk_input.risk_options)
        )
        assigned_annotations = assign_annotation_ids(filtered_annotations)

        table_artifacts = tuple(
            RiskAnnotationArtifact(
                table_name=table_name,
                annotations=tuple(annotation for annotation in assigned_annotations if annotation.target.table_name == table_name),
                diagnostics=_fact_diagnostics(facts, table_name),
            )
            for table_name in sorted(
                {
                    annotation.target.table_name
                    for annotation in assigned_annotations
                    if annotation.target.table_name is not None
                }
            )
        )

        table_risks = build_table_risks(
            facts=facts,
            annotations=assigned_annotations,
            annotation_artifacts=table_artifacts,
        )
        summary = build_summary(assigned_annotations)
        evaluation_digest = build_risk_evaluation_digest(
            comparison_digest=risk_input.comparison_facts.comparison_digest,
            risk_contract_version=risk_input.risk_contract_version,
            risk_model_version=risk_input.risk_model_version,
            risk_ruleset_digest=risk_input.risk_ruleset.risk_ruleset_digest,
            risk_options=risk_input.risk_options,
            summary=summary,
            table_risks=table_risks,
            annotation_artifacts=table_artifacts,
        )
        annotation_refs = tuple(artifact.artifact_ref for artifact in table_artifacts if artifact.artifact_ref is not None)
        evaluation = RiskEvaluation(
            risk_evaluation_digest=evaluation_digest,
            risk_contract_version=risk_input.risk_contract_version,
            risk_model_version=risk_input.risk_model_version,
            risk_ruleset_digest=risk_input.risk_ruleset.risk_ruleset_digest,
            comparison_digest=risk_input.comparison_facts.comparison_digest,
            summary=summary,
            table_risks=table_risks,
            annotation_refs=annotation_refs,
            diagnostics=risk_input.comparison_facts.diagnostics,
        )
        report = evaluation.to_report()
        return RiskEvaluationResult(
            risk_evaluation=evaluation,
            risk_report=report,
            annotation_artifacts=table_artifacts,
            cache_diagnostics=tuple(),
            diagnostics=risk_input.comparison_facts.diagnostics,
        )


def evaluate(risk_input: RiskEvaluationInput, *, engine: RiskEngine | None = None) -> RiskEvaluationResult:
    return (engine or RiskEngine()).evaluate(risk_input)


def _comparison_status(risk_input: RiskEvaluationInput) -> ComparisonStatus | None:
    summary = risk_input.comparison_facts.summary
    if summary is None:
        return None
    return summary.status


def _comparison_failed_annotation(
    *,
    comparison_status: ComparisonStatus | None,
    diagnostics: tuple[DiagnosticRecord, ...],
) -> tuple[RiskAnnotation, ...]:
    if comparison_status is not ComparisonStatus.FAILED:
        return ()
    return (
        RiskAnnotation(
            annotation_id="",
            target=RiskTarget(
                target_type=RiskTargetType.COMPARISON,
            ),
            risk_level=RiskLevel.HIGH,
            reasons=(
                RiskReason(
                    reason_code="COMPARISON_FAILED",
                    message="comparison summary indicates failure",
                    rule_id="COMPARISON_FAILED",
                    evidence={
                        "diagnostic_count": len(diagnostics),
                    },
                ),
            ),
            diagnostics=diagnostics,
        ),
    )


def _annotation_allowed(annotation: RiskAnnotation, risk_options: RiskOptions) -> bool:
    if annotation.risk_level is RiskLevel.LOW and not risk_options.include_low_risk:
        return False
    if annotation.risk_level is RiskLevel.UNKNOWN and not risk_options.include_unknown:
        return False
    return True


def _fact_diagnostics(facts: tuple[object, ...], table_name: str) -> tuple[DiagnosticRecord, ...]:
    for fact in facts:
        if getattr(fact, "table_name", None) == table_name:
            diagnostics = getattr(fact, "diagnostics", ())
            return diagnostics if isinstance(diagnostics, tuple) else tuple(diagnostics)
    return ()
