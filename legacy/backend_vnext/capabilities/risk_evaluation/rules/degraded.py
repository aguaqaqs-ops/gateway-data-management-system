from __future__ import annotations

from ..models import RiskAnnotation, RiskFacts, RiskLevel, RiskReason, RiskTarget, RiskTargetType
from ..rule_registry import RiskRulesetSnapshot


def build_degraded_annotations(
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
) -> tuple[RiskAnnotation, ...]:
    if not fact.degraded:
        return ()
    if fact.ordered_extension is not None:
        return ()
    if any(reason.startswith("ORDERED_") for reason in fact.degraded_reasons):
        return ()

    rule = risk_ruleset.rule_by_id("KEY_DEGRADED")
    risk_level = rule.severity_policy if rule is not None else RiskLevel.UNKNOWN
    return (
        RiskAnnotation(
            annotation_id="",
            target=RiskTarget(
                target_type=RiskTargetType.TABLE,
                table_name=fact.table_name,
            ),
            risk_level=risk_level,
            reasons=(
                RiskReason(
                    reason_code=rule.reason_code if rule is not None else "KEY_DEGRADED",
                    message="table comparison degraded",
                    rule_id="KEY_DEGRADED",
                    evidence={
                        "degraded_reasons": list(fact.degraded_reasons),
                    },
                ),
            ),
            diagnostics=fact.diagnostics,
        ),
    )
