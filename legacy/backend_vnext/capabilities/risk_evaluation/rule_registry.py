from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ...core.identifiers import canonical_identifier
from .models import RiskScope
from .ruleset_contract import RiskRulesetRule, RiskRulesetSnapshot
from .versions import RISK_MODEL_VERSION


@dataclass(frozen=True, slots=True)
class RiskRuleRegistry:
    rulesets: Mapping[str, RiskRulesetSnapshot] = field(default_factory=dict)
    default_ruleset_id: str = "default"

    def __post_init__(self) -> None:
        if not isinstance(self.rulesets, Mapping):
            raise TypeError("rulesets must be a mapping")
        normalized_rulesets: dict[str, RiskRulesetSnapshot] = {}
        for ruleset_id, snapshot in self.rulesets.items():
            if not isinstance(snapshot, RiskRulesetSnapshot):
                raise TypeError("rulesets must contain RiskRulesetSnapshot values")
            normalized_rulesets[canonical_identifier(str(ruleset_id))] = snapshot
        object.__setattr__(self, "rulesets", normalized_rulesets)
        object.__setattr__(self, "default_ruleset_id", canonical_identifier(self.default_ruleset_id))
        if self.default_ruleset_id not in self.rulesets:
            raise ValueError("default_ruleset_id must reference a registered ruleset")

    def get(self, ruleset_id: str | None = None) -> RiskRulesetSnapshot:
        lookup_id = canonical_identifier(ruleset_id or self.default_ruleset_id)
        try:
            return self.rulesets[lookup_id]
        except KeyError as exc:
            raise KeyError(f"unknown risk ruleset: {lookup_id}") from exc

    def snapshot(self, ruleset_id: str | None = None) -> RiskRulesetSnapshot:
        return self.get(ruleset_id)

    def export_model(self) -> dict[str, object]:
        return {
            "default_ruleset_id": self.default_ruleset_id,
            "rulesets": {
                ruleset_id: snapshot.to_payload()
                for ruleset_id, snapshot in sorted(self.rulesets.items())
            },
        }


def select_rules(snapshot: RiskRulesetSnapshot, risk_scope: RiskScope | str) -> tuple[RiskRulesetRule, ...]:
    normalized_scope = RiskScope(risk_scope)
    return tuple(
        rule
        for rule in snapshot.rules
        if rule.enabled and rule.target_scope is normalized_scope
    )


def build_hardcoded_risk_ruleset_registry() -> RiskRuleRegistry:
    default_ruleset = RiskRulesetSnapshot(
        risk_ruleset_id="default",
        risk_ruleset_version="v1",
        risk_model_version=RISK_MODEL_VERSION,
        rules=(
            RiskRulesetRule(
                rule_id="TABLE_ADDED",
                rule_version="v1",
                target_scope=RiskScope.TABLE,
                severity_policy="MEDIUM_LOW",
                reason_code="TABLE_ADDED",
                message="table added",
            ),
            RiskRulesetRule(
                rule_id="TABLE_DELETED",
                rule_version="v1",
                target_scope=RiskScope.TABLE,
                severity_policy="MEDIUM_HIGH",
                reason_code="TABLE_DELETED",
                message="table deleted",
            ),
            RiskRulesetRule(
                rule_id="SCHEMA_CHANGED",
                rule_version="v1",
                target_scope=RiskScope.TABLE,
                severity_policy="MEDIUM_HIGH",
                reason_code="SCHEMA_CHANGED",
                message="table schema changed",
            ),
            RiskRulesetRule(
                rule_id="STANDARD_INSERT",
                rule_version="v1",
                target_scope=RiskScope.STANDARD_ROWS,
                severity_policy="MEDIUM_LOW",
                reason_code="STANDARD_INSERT",
                message="standard row inserted",
            ),
            RiskRulesetRule(
                rule_id="STANDARD_DELETE",
                rule_version="v1",
                target_scope=RiskScope.STANDARD_ROWS,
                severity_policy="MEDIUM_LOW",
                reason_code="STANDARD_DELETE",
                message="standard row deleted",
            ),
            RiskRulesetRule(
                rule_id="STANDARD_UPDATE",
                rule_version="v1",
                target_scope=RiskScope.STANDARD_ROWS,
                severity_policy="MEDIUM_HIGH",
                reason_code="STANDARD_UPDATE",
                message="standard row updated",
            ),
            RiskRulesetRule(
                rule_id="DEVICE_POINT_NAME_UPDATE",
                rule_version="v1",
                target_scope=RiskScope.STANDARD_ROWS,
                severity_policy="LOW",
                reason_code="DEVICE_POINT_NAME_UPDATE",
                message="device point name changed",
            ),
            RiskRulesetRule(
                rule_id="DEVICE_POINT_CONTENT_UPDATE",
                rule_version="v1",
                target_scope=RiskScope.STANDARD_ROWS,
                severity_policy="MEDIUM_HIGH",
                reason_code="DEVICE_POINT_CONTENT_UPDATE",
                message="device point content changed",
            ),
            RiskRulesetRule(
                rule_id="ROW_ADDED",
                rule_version="v1",
                target_scope=RiskScope.STANDARD_ROWS,
                severity_policy="MEDIUM_LOW",
                reason_code="ROW_ADDED",
                message="rows added",
            ),
            RiskRulesetRule(
                rule_id="ROW_DELETED",
                rule_version="v1",
                target_scope=RiskScope.STANDARD_ROWS,
                severity_policy="MEDIUM_LOW",
                reason_code="ROW_DELETED",
                message="rows deleted",
            ),
            RiskRulesetRule(
                rule_id="ROW_MODIFIED",
                rule_version="v1",
                target_scope=RiskScope.STANDARD_ROWS,
                severity_policy="MEDIUM_HIGH",
                reason_code="ROW_MODIFIED",
                message="rows modified",
            ),
            RiskRulesetRule(
                rule_id="KEY_DEGRADED",
                rule_version="v1",
                target_scope=RiskScope.DEGRADED_TABLE,
                severity_policy="UNKNOWN",
                reason_code="KEY_DEGRADED",
                message="key comparison degraded",
            ),
            RiskRulesetRule(
                rule_id="ORDERED_REPLACEMENT",
                rule_version="v1",
                target_scope=RiskScope.ORDERED_TABLE,
                severity_policy="MEDIUM_LOW",
                reason_code="ORDERED_REPLACEMENT",
                message="ordered row delete and insert share the same position",
            ),
            RiskRulesetRule(
                rule_id="ORDERED_MOVE",
                rule_version="v1",
                target_scope=RiskScope.ORDERED_TABLE,
                severity_policy="MEDIUM_HIGH",
                reason_code="ORDERED_MOVE",
                message="ordered row position changed",
            ),
            RiskRulesetRule(
                rule_id="ORDERED_MIDDLE_INSERT_DELETE",
                rule_version="v1",
                target_scope=RiskScope.ORDERED_TABLE,
                severity_policy="MEDIUM_HIGH",
                reason_code="ORDERED_MIDDLE_INSERT_DELETE",
                message="ordered middle structural change",
            ),
            RiskRulesetRule(
                rule_id="ORDERED_MIDDLE_BLANK_INTERVAL",
                rule_version="v1",
                target_scope=RiskScope.ORDERED_TABLE,
                severity_policy="MEDIUM_HIGH",
                reason_code="ORDERED_MIDDLE_BLANK_INTERVAL",
                message="ordered middle blank interval change",
            ),
            RiskRulesetRule(
                rule_id="ORDERED_TAIL_INSERT_DELETE",
                rule_version="v1",
                target_scope=RiskScope.ORDERED_TABLE,
                severity_policy="LOW",
                reason_code="ORDERED_TAIL_INSERT_DELETE",
                message="ordered tail structural change",
            ),
            RiskRulesetRule(
                rule_id="ORDERED_TAIL_BLANK_INTERVAL",
                rule_version="v1",
                target_scope=RiskScope.ORDERED_TABLE,
                severity_policy="LOW",
                reason_code="ORDERED_TAIL_BLANK_INTERVAL",
                message="ordered tail blank interval change",
            ),
            RiskRulesetRule(
                rule_id="ORDERED_NAME_UPDATE",
                rule_version="v1",
                target_scope=RiskScope.ORDERED_TABLE,
                severity_policy="LOW",
                reason_code="ORDERED_NAME_UPDATE",
                message="ordered name field changed",
            ),
            RiskRulesetRule(
                rule_id="ORDERED_CONTENT_UPDATE",
                rule_version="v1",
                target_scope=RiskScope.ORDERED_TABLE,
                severity_policy="MEDIUM_LOW",
                reason_code="ORDERED_CONTENT_UPDATE",
                message="ordered content field changed",
            ),
            RiskRulesetRule(
                rule_id="ORDERED_RISK_UNKNOWN",
                rule_version="v1",
                target_scope=RiskScope.ORDERED_TABLE,
                severity_policy="UNKNOWN",
                reason_code="ORDERED_RISK_UNKNOWN",
                message="ordered diff target is not classified",
            ),
            RiskRulesetRule(
                rule_id="ORDERED_DIFF_UNSUPPORTED",
                rule_version="v1",
                target_scope=RiskScope.DEGRADED_TABLE,
                severity_policy="UNKNOWN",
                reason_code="ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED",
                message="ordered comparison provider is not available",
            ),
            RiskRulesetRule(
                rule_id="COMPARISON_FAILED",
                rule_version="v1",
                target_scope=RiskScope.TABLE,
                severity_policy="HIGH",
                reason_code="COMPARISON_FAILED",
                message="comparison failed",
            ),
        ),
    )
    return RiskRuleRegistry(rulesets={"default": default_ruleset}, default_ruleset_id="default")
