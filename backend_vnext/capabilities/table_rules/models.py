from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Pattern

from ...core.identifiers import canonical_identifier


class TableStaticRole(StrEnum):
    SKIP = "SKIP"
    SNAPSHOT_ONLY = "SNAPSHOT_ONLY"
    BROWSE_ONLY = "BROWSE_ONLY"
    STANDARD_DIFF = "STANDARD_DIFF"
    ORDERED_DIFF = "ORDERED_DIFF"


class TableCompareMode(StrEnum):
    NONE = "NONE"
    PRESENCE_ONLY = "PRESENCE_ONLY"
    CONTENT_BASED = "CONTENT_BASED"
    ORDERED_SEMANTIC = "ORDERED_SEMANTIC"


class TableCompareKeyMode(StrEnum):
    RAW_PRIMARY_KEY = "RAW_PRIMARY_KEY"
    EXPLICIT_KEY = "EXPLICIT_KEY"
    ORDERED_STABLE_KEY = "ORDERED_STABLE_KEY"


class TableArtifactScope(StrEnum):
    ALL_CHANGES = "ALL_CHANGES"
    UPDATE_ONLY = "UPDATE_ONLY"
    ORDERED_SEMANTIC = "ORDERED_SEMANTIC"


class TableDiffOp(StrEnum):
    INSERT = "INSERT"
    DELETE = "DELETE"
    UPDATE = "UPDATE"


@dataclass(frozen=True, slots=True)
class TableRuleSource:
    exact_table_names: frozenset[str]
    regex_patterns: tuple[str, ...]
    compiled_regex_patterns: tuple[Pattern[str], ...]

    @classmethod
    def from_sources(
        cls,
        *,
        exact_table_names: Iterable[str] = (),
        regex_patterns: Iterable[str] = (),
    ) -> "TableRuleSource":
        normalized_patterns = tuple(regex_patterns)
        return cls(
            exact_table_names=frozenset(canonical_identifier(name) for name in exact_table_names),
            regex_patterns=normalized_patterns,
            compiled_regex_patterns=tuple(re.compile(pattern, re.IGNORECASE) for pattern in normalized_patterns),
        )

    def matches(self, table_name: str) -> bool:
        normalized_name = canonical_identifier(table_name)
        if normalized_name in self.exact_table_names:
            return True
        return any(pattern.search(table_name) is not None for pattern in self.compiled_regex_patterns)


@dataclass(frozen=True, slots=True)
class TableKeyRule:
    compare_key_mode: TableCompareKeyMode
    compare_key_columns: tuple[str, ...] = ()
    ignored_columns: frozenset[str] = frozenset()
    artifact_scope: TableArtifactScope = TableArtifactScope.ALL_CHANGES
    position_column: str | None = None
    stable_key_candidates: tuple[str, ...] = ()
    pseudo_key_start: int = 2_000_000_000

    def __post_init__(self) -> None:
        if not isinstance(self.compare_key_mode, TableCompareKeyMode):
            raise TypeError("compare_key_mode must be a TableCompareKeyMode")
        object.__setattr__(
            self,
            "compare_key_columns",
            tuple(canonical_identifier(column) for column in self.compare_key_columns),
        )
        object.__setattr__(self, "ignored_columns", frozenset(canonical_identifier(column) for column in self.ignored_columns))
        object.__setattr__(
            self,
            "stable_key_candidates",
            tuple(canonical_identifier(column) for column in self.stable_key_candidates),
        )
        if self.position_column is not None:
            object.__setattr__(self, "position_column", canonical_identifier(self.position_column))
        if not isinstance(self.artifact_scope, TableArtifactScope):
            object.__setattr__(self, "artifact_scope", TableArtifactScope(self.artifact_scope))
        if not isinstance(self.pseudo_key_start, int) or isinstance(self.pseudo_key_start, bool):
            raise TypeError("pseudo_key_start must be an integer")

    @property
    def ordered_table(self) -> bool:
        return self.artifact_scope == TableArtifactScope.ORDERED_SEMANTIC

    @property
    def included_ops(self) -> tuple[TableDiffOp, ...]:
        if self.artifact_scope == TableArtifactScope.UPDATE_ONLY:
            return (TableDiffOp.UPDATE,)
        if self.artifact_scope == TableArtifactScope.ORDERED_SEMANTIC:
            return ()
        return (TableDiffOp.INSERT, TableDiffOp.DELETE, TableDiffOp.UPDATE)

    @property
    def suppressed_ops(self) -> tuple[TableDiffOp, ...]:
        if self.artifact_scope == TableArtifactScope.UPDATE_ONLY:
            return (TableDiffOp.INSERT, TableDiffOp.DELETE)
        return ()


@dataclass(frozen=True, slots=True)
class TableRuleDefinition:
    table_selector: str
    static_role: TableStaticRole
    compare_key_columns: tuple[str, ...] = field(default_factory=tuple)
    ignored_columns: frozenset[str] = frozenset()
    artifact_scope: TableArtifactScope = TableArtifactScope.ALL_CHANGES
    row_diff_policy: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.table_selector, str) or not self.table_selector.strip():
            raise ValueError("table_selector must be a non-empty string")
        if not isinstance(self.static_role, TableStaticRole):
            raise TypeError("static_role must be a TableStaticRole")
        if self.row_diff_policy is not None and (
            not isinstance(self.row_diff_policy, str) or not self.row_diff_policy.strip()
        ):
            raise ValueError("row_diff_policy must be a non-empty string or None")
        if not isinstance(self.artifact_scope, TableArtifactScope):
            object.__setattr__(self, "artifact_scope", TableArtifactScope(self.artifact_scope))
        object.__setattr__(
            self,
            "compare_key_columns",
            tuple(canonical_identifier(column) for column in self.compare_key_columns),
        )
        object.__setattr__(self, "ignored_columns", frozenset(canonical_identifier(column) for column in self.ignored_columns))

