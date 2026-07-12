from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ...core.digests import DigestRef
from .models import RiskLevel, RiskScope, _mapping_payload
from .versions import RISK_RULESET_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class RiskRulesetRule:
    rule_id: str
    rule_version: str
    target_scope: RiskScope | str
    severity_policy: RiskLevel | str
    reason_code: str
    message: str
    params: Mapping[str, object] = field(default_factory=dict)
    enabled: bool = True

    def __post_init__(self) -> None:
        for field_name in ("rule_id", "rule_version", "reason_code", "message"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        object.__setattr__(self, "target_scope", RiskScope(self.target_scope))
        object.__setattr__(self, "severity_policy", RiskLevel(self.severity_policy))
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be a bool")
        object.__setattr__(self, "params", _mapping_payload(self.params))

    def to_payload(self) -> dict[str, object]:
        payload = {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "target_scope": self.target_scope.value,
            "severity_policy": self.severity_policy.value,
            "reason_code": self.reason_code,
            "message": self.message,
            "enabled": self.enabled,
        }
        if self.params:
            payload["params"] = _mapping_payload(self.params)
        return payload


@dataclass(frozen=True, slots=True)
class RiskRulesetSnapshot:
    risk_ruleset_id: str
    risk_ruleset_version: str
    risk_model_version: str
    rules: tuple[RiskRulesetRule, ...] = field(default_factory=tuple)
    risk_ruleset_contract_version: str = RISK_RULESET_CONTRACT_VERSION
    risk_ruleset_digest: DigestRef | str | None = None

    def __post_init__(self) -> None:
        for field_name in ("risk_ruleset_id", "risk_ruleset_version", "risk_model_version", "risk_ruleset_contract_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.rules, tuple):
            object.__setattr__(self, "rules", tuple(self.rules))
        normalized_rules: list[RiskRulesetRule] = []
        for rule in self.rules:
            if not isinstance(rule, RiskRulesetRule):
                raise TypeError("rules must contain RiskRulesetRule values")
            normalized_rules.append(rule)
        object.__setattr__(self, "rules", tuple(normalized_rules))
        if self.risk_ruleset_digest is None:
            object.__setattr__(self, "risk_ruleset_digest", DigestRef.from_payload(self.payload_for_digest()))
        else:
            object.__setattr__(self, "risk_ruleset_digest", DigestRef.parse(str(self.risk_ruleset_digest)))

    def payload_for_digest(self) -> dict[str, object]:
        return {
            "risk_ruleset_contract_version": self.risk_ruleset_contract_version,
            "risk_ruleset_id": self.risk_ruleset_id,
            "risk_ruleset_version": self.risk_ruleset_version,
            "risk_model_version": self.risk_model_version,
            "rules": [rule.to_payload() for rule in self.rules],
        }

    def to_payload(self) -> dict[str, object]:
        return {
            **self.payload_for_digest(),
            "risk_ruleset_digest": self.risk_ruleset_digest.to_payload() if self.risk_ruleset_digest is not None else None,
        }

    def rule_by_id(self, rule_id: str) -> RiskRulesetRule | None:
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError("rule_id must be a non-empty string")
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None

