"""Table Rules owns comparison views derived from the activated snapshot."""

from __future__ import annotations

from gateway_backend.capabilities.table_rules import (
    ComparisonRole,
    TableArtifactScope,
    comparison_rule_set,
    migrated_table_ruleset_snapshot,
    resolve_comparison_rule_view,
)


def test_comparison_view_projects_runtime_role_keys_and_column_disposition() -> None:
    rules = comparison_rule_set(migrated_table_ruleset_snapshot())

    standard = resolve_comparison_rule_view(rules, "composite_signal_point")
    standard_again = resolve_comparison_rule_view(rules, "composite_signal_point")
    ordered = resolve_comparison_rule_view(rules, "b1_n1_iec104_syx_list")
    browse = resolve_comparison_rule_view(rules, "version_manager")
    snapshot = resolve_comparison_rule_view(rules, "forwardtable_demo")
    skipped = resolve_comparison_rule_view(rules, "device_model_table")

    assert standard is not None
    assert standard.comparison_role is ComparisonRole.STANDARD
    assert standard.artifact_scope is TableArtifactScope.ALL_CHANGES
    assert standard.effective_key_columns == ("source_table", "point_gid")
    assert standard.compare_excluded_columns == ("formula_ast_json", "point_name")
    assert standard_again is not None
    assert standard.comparison_rule_digest == standard_again.comparison_rule_digest

    assert ordered is not None
    assert ordered.comparison_role is ComparisonRole.ORDERED
    assert ordered.artifact_scope is TableArtifactScope.ORDERED_SEMANTIC
    assert ordered.effective_key_columns == ("gid",)
    assert ordered.ordered is not None
    assert ordered.ordered.position_column == "no"
    assert ordered.ordered.row_identity_key == ("gid",)
    assert "no" not in ordered.compare_excluded_columns

    assert browse is not None and browse.comparison_role is ComparisonRole.BROWSE_ONLY
    assert snapshot is not None and snapshot.comparison_role is ComparisonRole.SNAPSHOT_ONLY
    assert skipped is None


def test_comparison_view_resolves_raw_primary_key_from_runtime_descriptor() -> None:
    rules = comparison_rule_set(migrated_table_ruleset_snapshot())
    view = resolve_comparison_rule_view(rules, "fallback_table", primary_key_columns=("ID",))

    assert view is not None
    assert view.comparison_role is ComparisonRole.STANDARD
    assert view.effective_key_columns == ("id",)

