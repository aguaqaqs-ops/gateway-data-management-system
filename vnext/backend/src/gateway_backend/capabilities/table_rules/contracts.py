"""Public contracts owned by the Table Rules capability.

Owner: Table Rules capability
Authority: docs/backend-vnext/refactoring/formal/plans/p3-r3-s0-entry-and-budget-freeze.md

This module owns the immutable TableRulesetSnapshot injection surface used by
source materialization. Full comparison/storage rule matrix remains P3-R4.
Downstream consumers may import this module only.
"""

from __future__ import annotations

from dataclasses import dataclass

TABLE_RULESET_VERSION = 1


@dataclass(frozen=True, slots=True)
class TableCompareKey:
    canonical_table: str
    key_columns: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.canonical_table) is not str or self.canonical_table == "":
            raise ValueError("canonical_table must be a non-empty string")
        if type(self.key_columns) is not tuple:
            raise ValueError("key_columns must be a tuple")
        if not self.key_columns:
            raise ValueError("key_columns must not be empty")
        seen: set[str] = set()
        for column in self.key_columns:
            if type(column) is not str or column == "":
                raise ValueError("key_columns must contain non-empty strings")
            if column in seen:
                raise ValueError("key_columns must not contain duplicates")
            seen.add(column)


@dataclass(frozen=True, slots=True)
class TableRulesetSnapshot:
    """Immutable ruleset view injected into materialization. No hidden global."""

    table_ruleset_version: int
    compare_keys: tuple[TableCompareKey, ...] = ()

    def __post_init__(self) -> None:
        if type(self.table_ruleset_version) is not int or self.table_ruleset_version < 1:
            raise ValueError("table_ruleset_version must be a positive int")
        if type(self.compare_keys) is not tuple:
            raise ValueError("compare_keys must be a tuple")
        seen: set[str] = set()
        for item in self.compare_keys:
            if type(item) is not TableCompareKey:
                raise ValueError("compare_keys must contain TableCompareKey")
            if item.canonical_table in seen:
                raise ValueError("compare_keys must not repeat canonical_table")
            seen.add(item.canonical_table)
