"""Public surface of the Table Rules capability."""

from gateway_backend.capabilities.table_rules.contracts import (
    FALLBACK_SELECTOR_VALUE,
    ORDERED_IDENTITY_COLUMN,
    ORDERED_POSITION_COLUMN,
    RULESET_ID,
    RULESET_VERSION,
    STORAGE_PROJECTION_VERSION,
    TABLE_RULESET_CONTRACT_VERSION,
    TABLE_RULESET_VERSION,
    CanonicalKeyPolicy,
    DroppedColumn,
    LegacyRuleDecision,
    OrderedPolicy,
    ResolvedTableRule,
    SelectorPrecedenceClass,
    StorageColumnPolicy,
    StorageRuleView,
    TableArtifactScope,
    TableCompareKey,
    TableCompareKeyMode,
    TableRuleRecord,
    TableRuleSelector,
    TableRuleSelectorKind,
    TableRulesetSnapshot,
    TableStaticRole,
    TableStorageDisposition,
    canonicalize_rule_identifier,
    compute_ruleset_digest,
    legacy_ignored_column_reason,
    table_ruleset_document,
    table_ruleset_from_document,
)
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot


def resolve_table_rule(
    snapshot: TableRulesetSnapshot,
    table_name: str,
    *,
    primary_key_columns: tuple[str, ...] = (),
) -> ResolvedTableRule:
    from gateway_backend.capabilities.table_rules.resolver import (
        resolve_table_rule as resolve_against_snapshot,
    )

    return resolve_against_snapshot(
        snapshot,
        table_name,
        primary_key_columns=primary_key_columns,
    )


__all__ = [
    "FALLBACK_SELECTOR_VALUE",
    "ORDERED_IDENTITY_COLUMN",
    "ORDERED_POSITION_COLUMN",
    "RULESET_ID",
    "RULESET_VERSION",
    "STORAGE_PROJECTION_VERSION",
    "TABLE_RULESET_CONTRACT_VERSION",
    "TABLE_RULESET_VERSION",
    "CanonicalKeyPolicy",
    "DroppedColumn",
    "LegacyRuleDecision",
    "OrderedPolicy",
    "ResolvedTableRule",
    "SelectorPrecedenceClass",
    "StorageColumnPolicy",
    "StorageRuleView",
    "TableArtifactScope",
    "TableCompareKey",
    "TableCompareKeyMode",
    "TableRuleRecord",
    "TableRuleSelector",
    "TableRuleSelectorKind",
    "TableRulesetSnapshot",
    "TableStaticRole",
    "TableStorageDisposition",
    "canonicalize_rule_identifier",
    "compute_ruleset_digest",
    "legacy_ignored_column_reason",
    "migrated_table_ruleset_snapshot",
    "resolve_table_rule",
    "table_ruleset_document",
    "table_ruleset_from_document",
]
