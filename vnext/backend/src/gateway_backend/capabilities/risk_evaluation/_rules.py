"""Frozen v1 rule selection; deliberately no mutable registry or fallback."""

from __future__ import annotations

from gateway_backend.capabilities.risk_evaluation.contracts import (
    RISK_MODEL_VERSION,
    RISK_RULESET_ID,
    RISK_RULESET_VERSION,
    RISK_RULE_VERSION,
    RiskLevel,
    RiskReasonCode,
    RiskRuleId,
    RiskRuleSpec,
    RiskRulesetSnapshot,
    V1_RISK_RULE_SPECS,
)


class InvalidRiskRuleset(ValueError):
    """The injected ruleset is not the complete compatible v1 snapshot."""


def validate_risk_ruleset(snapshot: RiskRulesetSnapshot) -> dict[RiskRuleId, RiskRuleSpec]:
    if snapshot.risk_ruleset_id != RISK_RULESET_ID:
        raise InvalidRiskRuleset("unsupported risk ruleset id")
    if snapshot.risk_ruleset_version != RISK_RULESET_VERSION:
        raise InvalidRiskRuleset("unsupported risk ruleset version")
    if snapshot.risk_model_version != RISK_MODEL_VERSION:
        raise InvalidRiskRuleset("unsupported risk model version")
    expected_by_id = {item.rule_id: item for item in V1_RISK_RULE_SPECS}
    actual_by_id = {item.rule_id: item for item in snapshot.rules}
    if set(actual_by_id) != set(expected_by_id):
        raise InvalidRiskRuleset("risk ruleset must contain the complete v1 rule set")
    for rule_id, expected in expected_by_id.items():
        actual = actual_by_id[rule_id]
        if actual.rule_version != RISK_RULE_VERSION:
            raise InvalidRiskRuleset(f"unsupported rule version for {rule_id.value}")
        if actual.target_scope is not expected.target_scope or actual.reason_code is not expected.reason_code:
            raise InvalidRiskRuleset(f"frozen rule identity mismatch for {rule_id.value}")
    return actual_by_id


def level_for(rule: RiskRuleSpec) -> RiskLevel:
    for reason_code, level in rule.severity_policy.overrides:
        if reason_code is rule.reason_code:
            return level
    return rule.severity_policy.default_level


def reason_for(rule: RiskRuleSpec) -> RiskReasonCode:
    return rule.reason_code
