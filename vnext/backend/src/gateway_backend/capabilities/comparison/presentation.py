"""One conservative business projection; original comparison facts stay immutable."""
from __future__ import annotations

from dataclasses import replace

from gateway_backend.capabilities.comparison.contracts import (
    ComparisonFacts, ComparisonSchemaChanges, ComparisonTableFact, ComparisonTableStatus,
    OrderedStatus,
)

_SCHEMA_DIAGNOSTICS = frozenset({"BEFORE_ONLY_COLUMNS", "CURRENT_ONLY_COLUMNS", "BUSINESS_SCHEMA_CHANGED"})


def structure_change_is_audit_only(table: ComparisonTableFact) -> bool:
    changes = table.schema_changes
    if (table.before_descriptor is None or table.current_descriptor is None
            or table.row_count_before is None or table.row_count_before != table.row_count_current
            or table.status not in {ComparisonTableStatus.UNCHANGED,
                ComparisonTableStatus.SCHEMA_CHANGED, ComparisonTableStatus.SCHEMA_ONLY_CHANGED}
            or not (changes.before_only_columns or changes.current_only_columns)
            or changes.incompatible_columns or changes.effective_compare_key_changed
            or changes.effective_compare_key_before != changes.effective_compare_key_current
            or any(diagnostic not in _SCHEMA_DIAGNOSTICS for diagnostic in table.diagnostics)
            or table.content_changed
            or any((table.row_added_count, table.row_deleted_count, table.row_modified_count,
                    table.suppressed_added_count, table.suppressed_deleted_count))):
        return False
    if table.row_count_before == 0:
        if table.shared_value_equality != "BOUND_EMPTY_DESCRIPTORS":
            return False
    elif (table.shared_value_equality != "NATIVE_SHARED_VALUES"
            or not changes.effective_compare_key_before or not changes.selected_columns):
        return False
    ordered, blank = table.ordered_extension, table.blank_extension
    if ordered is not None and (ordered.status is not OrderedStatus.UNCHANGED
            or any((
                ordered.ordered_summary.row_added_count, ordered.ordered_summary.row_deleted_count,
                ordered.ordered_summary.row_modified_count, ordered.ordered_summary.row_moved_count,
                ordered.ordered_summary.position_changed_count, ordered.ordered_summary.degraded_count))):
        return False
    if blank is not None and (blank.status is not OrderedStatus.UNCHANGED
            or any((blank.blank_summary.interval_inserted_count, blank.blank_summary.interval_deleted_count,
                    blank.blank_summary.blank_changed_count, blank.blank_summary.degraded_count))):
        return False
    return True


def visible_table_fact(table: ComparisonTableFact) -> ComparisonTableFact:
    if not structure_change_is_audit_only(table):
        return table
    return replace(table, status=ComparisonTableStatus.UNCHANGED, content_changed=False,
        schema_changes=ComparisonSchemaChanges(), records=(), diagnostics=())


def visible_comparison_facts(facts: ComparisonFacts) -> ComparisonFacts:
    tables = tuple(visible_table_fact(table) for table in facts.tables)
    return replace(facts, tables=tables,
        diagnostics=tuple(diagnostic for table in tables for diagnostic in table.diagnostics))
