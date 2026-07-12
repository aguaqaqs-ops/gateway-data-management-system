from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ...core.identifiers import canonical_identifier
from ..table_rules import TableRuleDefinition, build_hardcoded_table_rule_registry
from .models import COMPARISON_RULESET_CONTRACT_VERSION, TableRulesetSnapshot, TableRulesetTableRule


@dataclass(frozen=True, slots=True)
class TableRulesetRegistry:
    rulesets: Mapping[str, TableRulesetSnapshot] = field(default_factory=dict)
    default_ruleset_id: str = "default"

    def __post_init__(self) -> None:
        if not isinstance(self.rulesets, Mapping):
            raise TypeError("rulesets must be a mapping")
        normalized_rulesets: dict[str, TableRulesetSnapshot] = {}
        for ruleset_id, snapshot in self.rulesets.items():
            if not isinstance(snapshot, TableRulesetSnapshot):
                raise TypeError("rulesets must contain TableRulesetSnapshot values")
            normalized_rulesets[canonical_identifier(str(ruleset_id))] = snapshot
        object.__setattr__(self, "rulesets", normalized_rulesets)
        object.__setattr__(self, "default_ruleset_id", canonical_identifier(self.default_ruleset_id))
        if self.default_ruleset_id not in self.rulesets:
            raise ValueError("default_ruleset_id must reference a registered ruleset")

    def get(self, ruleset_id: str | None = None) -> TableRulesetSnapshot:
        lookup_id = canonical_identifier(ruleset_id or self.default_ruleset_id)
        try:
            return self.rulesets[lookup_id]
        except KeyError as exc:
            raise KeyError(f"unknown comparison ruleset: {lookup_id}") from exc

    def snapshot(self, ruleset_id: str | None = None) -> TableRulesetSnapshot:
        return self.get(ruleset_id)


def build_hardcoded_table_ruleset_registry() -> TableRulesetRegistry:
    shared_registry = build_hardcoded_table_rule_registry()
    default_ruleset = TableRulesetSnapshot(
        ruleset_id="default",
        ruleset_version="v1",
        ruleset_contract_version=COMPARISON_RULESET_CONTRACT_VERSION,
        table_rules=tuple(
            _table_ruleset_rule_from_definition(rule)
            for rule in shared_registry.table_rule_definitions()
        ),
    )
    return TableRulesetRegistry(rulesets={"default": default_ruleset}, default_ruleset_id="default")


def _table_ruleset_rule_from_definition(rule: TableRuleDefinition) -> TableRulesetTableRule:
    return TableRulesetTableRule(
        table_selector=rule.table_selector,
        static_role=rule.static_role.value,
        compare_key_columns=rule.compare_key_columns,
        ignored_columns=tuple(sorted(rule.ignored_columns)),
        artifact_scope=rule.artifact_scope.value,
        row_diff_policy=rule.row_diff_policy,
    )
