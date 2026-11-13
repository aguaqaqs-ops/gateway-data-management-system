"""Table Rules owns comparison views derived from the activated snapshot."""

from __future__ import annotations

import pytest
from gateway_shared_kernel import DeclaredType, DeclaredTypeKind, RowField, StringScalar, encode_row
from contextlib import closing
from typing import Any

from gateway_backend.capabilities.comparison import (
    ComparisonFacts, ComparisonPlan, ComparisonRequest, ComparisonRecordKind, ComparisonTableStatus,
    DetailedFactsResult, plan_comparison,
)
from gateway_backend.capabilities.comparison.production import compare_plan_native
from tests.support.comparison_s3_e_live import canonical_bound
from tests.support.table_rules import CONFIGURATION_TABLE_NAMES

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




def _configuration_sql(name: str, rows: str, *, key_column: str = "page_no",
                       primary_key: bool = True) -> str:
    sql = (f"CREATE TABLE {name} (id INT{' PRIMARY KEY' if primary_key else ''}, "
           f"{key_column} VARCHAR(8), no VARCHAR(8), value TEXT);")
    return sql + (f"INSERT INTO {name} VALUES {rows};" if rows else "")


def _configuration_compare(
    before_sql: str, current_sql: str, *, records_out: list[dict[str, Any]] | None = None,
) -> ComparisonFacts:
    planned = plan_comparison(ComparisonRequest(
        pair_id="configuration-contract", before=canonical_bound(before_sql),
        current=canonical_bound(current_sql),
        rule_set=comparison_rule_set(migrated_table_ruleset_snapshot()),
    ))
    assert isinstance(planned, ComparisonPlan)
    with closing(compare_plan_native(planned)) as product:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        if records_out is not None:
            for handle in product.handles.values():
                with closing(handle.record_batches("STANDARD")) as reader:
                    records_out.extend(row for batch in reader for row in batch.to_pylist())
        return product.result.facts


@pytest.mark.parametrize("table_name", CONFIGURATION_TABLE_NAMES)
def test_configuration_rows_align_page_and_number_and_emit_all_changes(table_name: str) -> None:
    rules = comparison_rule_set(migrated_table_ruleset_snapshot())
    view = resolve_comparison_rule_view(rules, table_name, primary_key_columns=("id",))
    assert view is not None
    assert view.comparison_role is ComparisonRole.STANDARD
    assert view.effective_key_columns == ("page_no", "no")
    assert view.artifact_scope is TableArtifactScope.ALL_CHANGES
    records: list[dict[str, Any]] = []
    facts = _configuration_compare(
        _configuration_sql(table_name, "(1,'1','1','same'),(2,'2','1','old'),(3,'3','1','gone')"),
        _configuration_sql(table_name, "(1,'1','1','same'),(2,'2','1','new'),(4,'4','1','added')"),
        records_out=records,
    )
    table, = facts.tables
    assert table.status is ComparisonTableStatus.MODIFIED
    assert (table.row_added_count, table.row_deleted_count, table.row_modified_count) == (1, 1, 1)
    assert {record["record_kind"] for record in records} == {
        "ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED",
    }
    modified, = (record for record in records if record["record_kind"] == "ROW_MODIFIED")
    assert modified["changed_columns"] == ["value"]
    key = encode_row([
        RowField("no", DeclaredType(DeclaredTypeKind.STRING), StringScalar("1")),
        RowField("page_no", DeclaredType(DeclaredTypeKind.STRING), StringScalar("2")),
    ])
    assert modified["row_identity"] == key.digest_ref.raw_digest
    assert modified["before_values"][0]["value"]["text"] == "old"
    assert modified["current_values"][0]["value"]["text"] == "new"
    assert (facts.summary.row_added_count, facts.summary.row_deleted_count,
            facts.summary.row_modified_count) == (1, 1, 1)


COMPARISON_KEY_FAULTS = (
    ("duplicate", "(1,'1','1','a'),(2,'1','1','b')", "page_no", "DUPLICATE_EFFECTIVE_KEY:iec104_cfg"),
    ("null-page", "(1,NULL,'1','a')", "page_no", "NULL_EFFECTIVE_KEY:iec104_cfg"),
    ("null-no", "(1,'1',NULL,'a')", "page_no", "NULL_EFFECTIVE_KEY:iec104_cfg"),
    ("empty-page", "(1,'','1','a')", "page_no", "EMPTY_EFFECTIVE_KEY:iec104_cfg"),
    ("empty-no", "(1,'1','','a')", "page_no", "EMPTY_EFFECTIVE_KEY:iec104_cfg"),
    ("missing-column", "(1,'1','1','a')", "other", "EFFECTIVE_KEY_MISSING"),
)


@pytest.mark.parametrize("label,rows,key_column,diagnostic", COMPARISON_KEY_FAULTS,
                         ids=[case[0] for case in COMPARISON_KEY_FAULTS])
@pytest.mark.parametrize("fault_side", ("before", "current"))
def test_invalid_comparison_key_degrades_without_using_ddl_key(
    label: str, rows: str, key_column: str, diagnostic: str | None, fault_side: str,
) -> None:
    good = _configuration_sql("iec104_cfg", "(1,'1','1','changed')")
    bad = _configuration_sql("iec104_cfg", rows, key_column=key_column)
    result = _configuration_compare(bad if fault_side == "before" else good,
                                    good if fault_side == "before" else bad)
    table, = result.tables
    assert table.status is ComparisonTableStatus.DEGRADED
    assert [record.record_kind for record in table.records] == [ComparisonRecordKind.TABLE_DEGRADED]
    if diagnostic is not None:
        assert diagnostic in table.diagnostics
    assert table.row_modified_count == table.row_added_count == table.row_deleted_count == 0


@pytest.mark.parametrize("primary_key", (False, True))
def test_configuration_comparison_works_with_keyless_or_ddl_storage(primary_key: bool) -> None:
    facts = _configuration_compare(
        _configuration_sql("iec104_cfg", "(1,'1','1','old')", primary_key=primary_key),
        _configuration_sql("iec104_cfg", "(1,'1','1','new')", primary_key=primary_key),
    )
    assert facts.tables[0].row_modified_count == 1


@pytest.mark.parametrize("side", ("before", "current", "both"))
def test_configuration_empty_and_single_side_need_no_key_values(side: str) -> None:
    # Missing compare column is harmless when no keyed alignment is needed.
    empty = _configuration_sql("iec104_cfg", "", key_column="other", primary_key=False)
    result = _configuration_compare("" if side == "current" else empty,
                                    "" if side == "before" else empty)
    table, = result.tables
    assert table.status is {
        "before": ComparisonTableStatus.DELETED_TABLE,
        "current": ComparisonTableStatus.ADDED_TABLE,
        "both": ComparisonTableStatus.UNCHANGED,
    }[side]


@pytest.mark.parametrize("table_name,role,key", (
    ("dev104_cfg", ComparisonRole.BROWSE_ONLY, ()),
    ("nbridge_cfg", ComparisonRole.BROWSE_ONLY, ()),
    ("nr103d_cfg", ComparisonRole.BROWSE_ONLY, ()),
    ("nr103ht_cfg", ComparisonRole.BROWSE_ONLY, ()),
    ("sntp_cfg", ComparisonRole.BROWSE_ONLY, ()),
    ("unknown_cfg", ComparisonRole.STANDARD, ("id",)),
    ("x_iec104_cfg", ComparisonRole.STANDARD, ("id",)),
    ("b1_n1_iec104_cfg", ComparisonRole.STANDARD, ("page_no", "no")),
    ("b1_n1_iec104_dev_cfg", ComparisonRole.STANDARD, ("gid",)),
))
def test_configuration_exact_scope_preserves_other_and_prefixed_rules(
    table_name: str, role: ComparisonRole, key: tuple[str, ...],
) -> None:
    view = resolve_comparison_rule_view(comparison_rule_set(migrated_table_ruleset_snapshot()),
                                        table_name, primary_key_columns=("id",))
    assert view is not None
    assert view.comparison_role is role
    assert view.effective_key_columns == key
