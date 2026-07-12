from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..table_rules import (
    TableCompareKeyMode,
    TableCompareMode,
    TableRuleRegistry,
    TableStaticRole,
)


class TableRuntimeState(StrEnum):
    EMPTY = "EMPTY"
    NON_EMPTY = "NON_EMPTY"


@dataclass(frozen=True, slots=True)
class TableHandlingDecision:
    table_name: str
    static_role: TableStaticRole
    runtime_state: TableRuntimeState
    compare_mode: TableCompareMode
    compare_key_mode: TableCompareKeyMode | None
    compare_key_columns: tuple[str, ...]
    ignored_columns: frozenset[str]
    enters_comparison: bool
    keep_in_raw_snapshot: bool
    keep_metadata: bool
    include_in_preview: bool
    include_in_diff_summary: bool
    export_base_table_artifact: bool
    export_diff_artifact: bool
    default_display_strategy: str | None


def build_table_handling_decision(
    table_rule_registry: TableRuleRegistry,
    table_name: str,
    *,
    row_count: int,
    has_schema: bool,
    primary_key_columns: tuple[str, ...] = (),
) -> TableHandlingDecision:
    semantic_decision = table_rule_registry.resolve_table_semantics(
        table_name,
        primary_key_columns=primary_key_columns,
    )
    static_role = semantic_decision.static_role
    runtime_state = TableRuntimeState.NON_EMPTY if row_count > 0 else TableRuntimeState.EMPTY
    keep_metadata = static_role != TableStaticRole.SKIP and has_schema
    include_in_preview = (
        runtime_state == TableRuntimeState.NON_EMPTY
        and keep_metadata
        and static_role
        in {
            TableStaticRole.BROWSE_ONLY,
            TableStaticRole.STANDARD_DIFF,
            TableStaticRole.ORDERED_DIFF,
        }
    )
    export_diff_artifact = runtime_state == TableRuntimeState.NON_EMPTY and static_role in {
        TableStaticRole.STANDARD_DIFF,
        TableStaticRole.ORDERED_DIFF,
    }
    return TableHandlingDecision(
        table_name=table_name,
        static_role=static_role,
        runtime_state=runtime_state,
        compare_mode=semantic_decision.compare_mode,
        compare_key_mode=semantic_decision.compare_key_mode,
        compare_key_columns=semantic_decision.compare_key_columns,
        ignored_columns=semantic_decision.ignored_columns,
        enters_comparison=semantic_decision.enters_comparison,
        keep_in_raw_snapshot=static_role != TableStaticRole.SKIP,
        keep_metadata=keep_metadata,
        include_in_preview=include_in_preview,
        include_in_diff_summary=include_in_preview,
        export_base_table_artifact=include_in_preview,
        export_diff_artifact=export_diff_artifact,
        default_display_strategy=(
            "CURRENT_ONLY"
            if static_role == TableStaticRole.BROWSE_ONLY
            else "CURRENT_SLOTTED"
            if static_role == TableStaticRole.ORDERED_DIFF
            else "CURRENT_INLINE"
            if static_role == TableStaticRole.STANDARD_DIFF
            else None
        ),
    )
