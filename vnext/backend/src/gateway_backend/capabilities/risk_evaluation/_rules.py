"""Frozen v1 rule selection; deliberately no mutable registry or fallback."""

from __future__ import annotations

from gateway_backend.capabilities.table_rules import parse_channel_table_name

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
        if (tuple(key for key, _ in actual.params) != tuple(key for key, _ in expected.params)
                or any(value is not True for _, value in actual.params)):
            raise InvalidRiskRuleset(f"invalid frozen rule parameters for {rule_id.value}")
    return actual_by_id


def standard_rule_applicability(
    snapshot: RiskRulesetSnapshot, table_name: str,
) -> tuple[bool, bool, bool, bool]:
    """Resolve standard-row rules for both evaluation and candidate identity."""
    rules = {rule.rule_id: rule for rule in snapshot.rules}
    def has(rule_id: RiskRuleId, prefix: str) -> bool:
        return (f"{prefix}:{table_name}", True) in rules[rule_id].params

    return (
        not has(RiskRuleId.ROW_ADDED, "exclude_table"),
        not has(RiskRuleId.ROW_DELETED, "exclude_table"),
        True,
        has(RiskRuleId.ROW_MODIFIED, "ignore_address_table"),
    )


def ordered_yk_name_applies(snapshot: RiskRulesetSnapshot, table_name: str) -> bool:
    """Resolve the frozen literal selector shared by evaluation and cache keys."""
    rule = next(rule for rule in snapshot.rules if rule.rule_id is RiskRuleId.ORDERED_MIDDLE_YK_INSERT_DELETE)
    return (("channel_table_name", True) in rule.params
            and ("name_contains:yk", True) in rule.params
            and "yk" in table_name and parse_channel_table_name(table_name) is not None)


def level_for(rule: RiskRuleSpec) -> RiskLevel:
    for reason_code, level in rule.severity_policy.overrides:
        if reason_code is rule.reason_code:
            return level
    return rule.severity_policy.default_level


def reason_for(rule: RiskRuleSpec) -> RiskReasonCode:
    return rule.reason_code
