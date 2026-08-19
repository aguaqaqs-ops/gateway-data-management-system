"""Effective compare-key view from an injected TableRulesetSnapshot."""

from __future__ import annotations

from gateway_shared_kernel import canonicalize_identifier

from gateway_backend.capabilities.table_access.contracts import SourceTableDescriptor
from gateway_backend.capabilities.table_rules.contracts import (
    TableCompareKey,
    TableRulesetSnapshot,
)


class CompareKeyError(ValueError):
    """Ruleset compare key references a column that is not in the table."""

    def __init__(self, column: str) -> None:
        super().__init__(f"compare key column {column!r} is not in the table")
        self.column = column


def compare_key_index(ruleset: TableRulesetSnapshot) -> dict[str, TableCompareKey]:
    index: dict[str, TableCompareKey] = {}
    for item in ruleset.compare_keys:
        canonical = canonicalize_identifier(item.canonical_table)
        index[canonical] = item
    return index


def effective_key_columns(
    descriptor: SourceTableDescriptor,
    ruleset_index: dict[str, TableCompareKey],
) -> tuple[str, ...]:
    override = ruleset_index.get(descriptor.canonical_name)
    if override is not None:
        columns = tuple(canonicalize_identifier(name) for name in override.key_columns)
        available = {column.canonical_name for column in descriptor.columns}
        for name in columns:
            if name not in available:
                raise CompareKeyError(name)
        return columns
    return descriptor.primary_key_canonical_names
