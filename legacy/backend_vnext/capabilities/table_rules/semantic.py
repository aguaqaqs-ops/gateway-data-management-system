from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ...core.identifiers import canonical_identifier
from .models import TableCompareKeyMode, TableCompareMode, TableStaticRole


@dataclass(frozen=True, slots=True)
class TableSemanticDecision:
    table_name: str
    static_role: TableStaticRole
    compare_mode: TableCompareMode
    compare_key_mode: TableCompareKeyMode | None
    compare_key_columns: tuple[str, ...]
    ignored_columns: frozenset[str]
    enters_comparison: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        if not isinstance(self.static_role, TableStaticRole):
            object.__setattr__(self, "static_role", TableStaticRole(self.static_role))
        if not isinstance(self.compare_mode, TableCompareMode):
            object.__setattr__(self, "compare_mode", TableCompareMode(self.compare_mode))
        if self.compare_key_mode is not None and not isinstance(self.compare_key_mode, TableCompareKeyMode):
            object.__setattr__(self, "compare_key_mode", TableCompareKeyMode(self.compare_key_mode))
        object.__setattr__(
            self,
            "compare_key_columns",
            tuple(canonical_identifier(column) for column in self.compare_key_columns),
        )
        object.__setattr__(
            self,
            "ignored_columns",
            frozenset(canonical_identifier(column) for column in self.ignored_columns),
        )
        if not isinstance(self.enters_comparison, bool):
            raise TypeError("enters_comparison must be a bool")

    @property
    def participates_in_comparison(self) -> bool:
        return self.enters_comparison


def compare_mode_for_static_role(static_role: TableStaticRole | str) -> TableCompareMode:
    role = TableStaticRole(static_role)
    if role == TableStaticRole.BROWSE_ONLY:
        return TableCompareMode.PRESENCE_ONLY
    if role == TableStaticRole.STANDARD_DIFF:
        return TableCompareMode.CONTENT_BASED
    if role == TableStaticRole.ORDERED_DIFF:
        return TableCompareMode.ORDERED_SEMANTIC
    return TableCompareMode.NONE


def enters_comparison_for_static_role(static_role: TableStaticRole | str) -> bool:
    role = TableStaticRole(static_role)
    return role in {TableStaticRole.STANDARD_DIFF, TableStaticRole.ORDERED_DIFF}


def build_table_semantic_decision(
    *,
    table_name: str,
    static_role: TableStaticRole | str,
    compare_key_mode: TableCompareKeyMode | str | None = None,
    compare_key_columns: Sequence[str] = (),
    ignored_columns: Iterable[str] = (),
    primary_key_columns: Sequence[str] = (),
) -> TableSemanticDecision:
    role = TableStaticRole(static_role)
    compare_mode = compare_mode_for_static_role(role)
    normalized_compare_key_columns = tuple(
        canonical_identifier(column)
        for column in compare_key_columns
        if canonical_identifier(column)
    )
    normalized_primary_key_columns = tuple(
        canonical_identifier(column)
        for column in primary_key_columns
        if canonical_identifier(column)
    )
    normalized_ignored_columns = frozenset(
        canonical_identifier(column)
        for column in ignored_columns
        if canonical_identifier(column)
    )

    if role in {TableStaticRole.SKIP, TableStaticRole.SNAPSHOT_ONLY, TableStaticRole.BROWSE_ONLY}:
        return TableSemanticDecision(
            table_name=table_name,
            static_role=role,
            compare_mode=compare_mode,
            compare_key_mode=None,
            compare_key_columns=(),
            ignored_columns=normalized_ignored_columns,
            enters_comparison=False,
        )

    resolved_compare_key_columns = normalized_compare_key_columns
    resolved_compare_key_mode: TableCompareKeyMode | None
    if compare_key_mode is None:
        if resolved_compare_key_columns:
            resolved_compare_key_mode = TableCompareKeyMode.EXPLICIT_KEY
        elif normalized_primary_key_columns:
            resolved_compare_key_mode = TableCompareKeyMode.RAW_PRIMARY_KEY
            resolved_compare_key_columns = normalized_primary_key_columns
        else:
            resolved_compare_key_mode = None
    else:
        resolved_compare_key_mode = TableCompareKeyMode(compare_key_mode)
        if not resolved_compare_key_columns and resolved_compare_key_mode == TableCompareKeyMode.RAW_PRIMARY_KEY:
            resolved_compare_key_columns = normalized_primary_key_columns

    if role == TableStaticRole.ORDERED_DIFF and not resolved_compare_key_columns:
        resolved_compare_key_columns = normalized_primary_key_columns

    return TableSemanticDecision(
        table_name=table_name,
        static_role=role,
        compare_mode=compare_mode,
        compare_key_mode=resolved_compare_key_mode,
        compare_key_columns=resolved_compare_key_columns,
        ignored_columns=normalized_ignored_columns,
        enters_comparison=enters_comparison_for_static_role(role),
    )

