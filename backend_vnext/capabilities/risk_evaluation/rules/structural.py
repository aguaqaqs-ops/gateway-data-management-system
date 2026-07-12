from __future__ import annotations

from ..models import RiskAnnotation, RiskLevel, RiskReason, RiskTarget, RiskTargetType, RiskFacts
from ..rule_registry import RiskRulesetSnapshot


def build_structural_annotations(
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
) -> tuple[RiskAnnotation, ...]:
    annotations: list[RiskAnnotation] = []

    if fact.table_status.name == "ADDED_TABLE":
        annotations.append(
            _annotation(
                fact=fact,
                risk_ruleset=risk_ruleset,
                rule_id="TABLE_ADDED",
                reason_code="TABLE_ADDED",
                message="table added",
            )
        )
    elif fact.table_status.name == "DELETED_TABLE":
        annotations.append(
            _annotation(
                fact=fact,
                risk_ruleset=risk_ruleset,
                rule_id="TABLE_DELETED",
                reason_code="TABLE_DELETED",
                message="table deleted",
            )
        )
    elif fact.table_status.name in {"SCHEMA_CHANGED", "SCHEMA_ONLY_CHANGED"}:
        annotations.append(
            _annotation(
                fact=fact,
                risk_ruleset=risk_ruleset,
                rule_id="SCHEMA_CHANGED",
                reason_code="SCHEMA_CHANGED",
                message="table schema changed",
            )
        )

    return tuple(annotations)


def _annotation(
    *,
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
    rule_id: str,
    reason_code: str,
    message: str,
) -> RiskAnnotation:
    rule = risk_ruleset.rule_by_id(rule_id)
    risk_level = rule.severity_policy if rule is not None else RiskLevel.MEDIUM_LOW
    return RiskAnnotation(
        annotation_id="",
        target=RiskTarget(
            target_type=RiskTargetType.TABLE,
            table_name=fact.table_name,
        ),
        risk_level=risk_level,
        reasons=(
            RiskReason(
                reason_code=rule.reason_code if rule is not None else reason_code,
                message=message,
                rule_id=rule_id,
                evidence={
                    "table_status": fact.table_status.value,
                },
            ),
        ),
        diagnostics=fact.diagnostics,
    )

