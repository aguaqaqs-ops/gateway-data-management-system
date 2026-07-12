from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from ...core.digests import DigestRef
from .artifacts import RiskAnnotationArtifact
from .models import (
    RiskAnnotation,
    RiskLevel,
    RiskOptions,
    RiskReason,
    RiskSummary,
    RiskTableRisk,
)


RISK_LEVEL_WEIGHTS: dict[RiskLevel, int] = {
    RiskLevel.LOW: 10,
    RiskLevel.MEDIUM_LOW: 20,
    RiskLevel.UNKNOWN: 30,
    RiskLevel.MEDIUM_HIGH: 40,
    RiskLevel.HIGH: 50,
}


def highest_risk_level(levels: Iterable[RiskLevel | None]) -> RiskLevel:
    filtered = [level for level in levels if level is not None]
    if not filtered:
        return RiskLevel.LOW
    return max(filtered, key=lambda level: RISK_LEVEL_WEIGHTS[level])


def merge_reason_codes(reason_codes: Iterable[str]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for reason_code in reason_codes:
        if not isinstance(reason_code, str) or not reason_code.strip():
            raise ValueError("reason codes must be non-empty strings")
        if reason_code in seen:
            continue
        seen.add(reason_code)
        merged.append(reason_code)
    return tuple(merged)


def merge_annotations(annotations: Iterable[RiskAnnotation]) -> tuple[RiskAnnotation, ...]:
    by_target: dict[tuple[object, ...], RiskAnnotation] = {}
    for annotation in annotations:
        key = annotation.identity_key()
        existing = by_target.get(key)
        if existing is None:
            by_target[key] = annotation
            continue
        by_target[key] = RiskAnnotation(
            annotation_id=existing.annotation_id,
            target=existing.target,
            risk_level=highest_risk_level((existing.risk_level, annotation.risk_level)),
            reasons=existing.reasons + annotation.reasons,
            diagnostics=existing.diagnostics + annotation.diagnostics,
        )
    return tuple(by_target.values())


def assign_annotation_ids(annotations: Iterable[RiskAnnotation]) -> tuple[RiskAnnotation, ...]:
    ordered = sorted(
        annotations,
        key=lambda annotation: (
            annotation.target.table_name or "",
            annotation.target.target_type.value,
            annotation.target.row_identity or "",
            annotation.target.before_row_identity or "",
            annotation.target.current_row_identity or "",
            annotation.target.position if annotation.target.position is not None else -1,
            annotation.target.position_range or (),
            annotation.target.coverage or "",
            tuple(reason.reason_code for reason in annotation.reasons),
        ),
    )
    return tuple(
        annotation.with_annotation_id(f"risk-{index:06d}")
        for index, annotation in enumerate(ordered, start=1)
    )


def build_summary(annotations: Sequence[RiskAnnotation]) -> RiskSummary:
    risk_level = highest_risk_level(annotation.risk_level for annotation in annotations)
    reason_codes = merge_reason_codes(
        reason.reason_code for annotation in annotations for reason in annotation.reasons
    )
    return RiskSummary(risk_level=risk_level, reason_codes=reason_codes)


def build_table_risks(
    facts: Sequence[object],
    annotations: Sequence[RiskAnnotation],
    annotation_artifacts: Sequence[RiskAnnotationArtifact] = (),
) -> tuple[RiskTableRisk, ...]:
    annotations_by_table: dict[str, list[RiskAnnotation]] = defaultdict(list)
    for annotation in annotations:
        if annotation.target.table_name is None:
            continue
        annotations_by_table[annotation.target.table_name].append(annotation)

    artifact_by_table = {artifact.table_name: artifact for artifact in annotation_artifacts}
    table_risks: list[RiskTableRisk] = []
    for fact in facts:
        table_name = getattr(fact, "table_name", None)
        if not isinstance(table_name, str) or not table_name.strip():
            continue
        table_annotations = tuple(annotations_by_table.get(table_name, ()))
        if not table_annotations:
            continue
        artifact = artifact_by_table.get(table_name)
        table_risks.append(
            RiskTableRisk(
                table_name=table_name,
                risk_level=highest_risk_level(annotation.risk_level for annotation in table_annotations),
                reason_codes=merge_reason_codes(
                    reason.reason_code for annotation in table_annotations for reason in annotation.reasons
                ),
                annotation_count=len(table_annotations),
                source_table_status=getattr(fact, "table_status"),
                annotation_ref=None if artifact is None else artifact.artifact_ref,
                diagnostics=getattr(fact, "diagnostics", ()),
            )
        )
    return tuple(table_risks)


def build_risk_evaluation_digest(
    *,
    comparison_digest: DigestRef | str,
    risk_contract_version: str,
    risk_model_version: str,
    risk_ruleset_digest: DigestRef | str,
    risk_options: RiskOptions,
    summary: RiskSummary,
    table_risks: Sequence[RiskTableRisk],
    annotation_artifacts: Sequence[RiskAnnotationArtifact] = (),
) -> DigestRef:
    return DigestRef.from_payload(
        {
            "comparison_digest": DigestRef.parse(str(comparison_digest)).to_payload(),
            "risk_contract_version": risk_contract_version,
            "risk_model_version": risk_model_version,
            "risk_ruleset_digest": DigestRef.parse(str(risk_ruleset_digest)).to_payload(),
            "risk_options": risk_options.to_payload(),
            "summary": summary.to_payload(),
            "table_risks": [table_risk.payload_for_digest() for table_risk in table_risks],
            "annotation_artifact_manifest_digests": [
                artifact.manifest_digest.to_payload() if artifact.manifest_digest is not None else None
                for artifact in annotation_artifacts
            ],
        }
    )
