"""Public surface of the Table Rules capability."""

from gateway_backend.capabilities.table_rules.contracts import (
    TABLE_RULESET_VERSION,
    TableCompareKey,
    TableRulesetSnapshot,
)

__all__ = [
    "TABLE_RULESET_VERSION",
    "TableCompareKey",
    "TableRulesetSnapshot",
]
