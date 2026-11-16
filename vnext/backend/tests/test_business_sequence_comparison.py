"""Business identity remains stable when generated row numbers change."""
from __future__ import annotations

from contextlib import closing

import pytest

from gateway_backend.capabilities.comparison import (
    ComparisonPlan, ComparisonRequest, ComparisonTableStatus, DetailedFactsResult, plan_comparison,
)
from gateway_backend.capabilities.comparison.production import compare_plan_native
from gateway_backend.capabilities.table_rules import comparison_rule_set, migrated_table_ruleset_snapshot
from tests.support.comparison_s3_e_live import canonical_bound


@pytest.mark.parametrize(("table", "columns", "old", "new"), (
    ("device_cfg", "no INT PRIMARY KEY, gid INT, page_no INT, option_name TEXT, value TEXT",
     "(259,7,1,'option','same')", "(1,7,1,'option','same')"),
    ("board_cfg", "no INT PRIMARY KEY, board INT, value TEXT", "(6,1,'same')", "(1,1,'same')"),
    ("rule_61850dev_praser_default_cfg", "id INT PRIMARY KEY, ptype TEXT, point TEXT",
     "(10,NULL,'same'),(11,NULL,'same')", "(1,NULL,'same'),(2,NULL,'same')"),
))
@pytest.mark.parametrize("changed", (False, True))
def test_generated_numbers_do_not_create_business_changes(
    table: str, columns: str, old: str, new: str, changed: bool,
) -> None:
    ddl = f"CREATE TABLE {table} ({columns});"
    plan = plan_comparison(ComparisonRequest(
        pair_id="sequence", before=canonical_bound(ddl + f"INSERT INTO {table} VALUES {old};"),
        current=canonical_bound(ddl + f"INSERT INTO {table} VALUES {new.replace('same', 'changed') if changed else new};"),
        rule_set=comparison_rule_set(migrated_table_ruleset_snapshot()),
    ))
    assert isinstance(plan, ComparisonPlan)
    with closing(compare_plan_native(plan)) as product:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        fact, = product.result.facts.tables
        assert fact.status is (ComparisonTableStatus.MODIFIED if changed else ComparisonTableStatus.UNCHANGED)
        if not changed:
            assert not fact.content_changed
            assert not (fact.row_added_count or fact.row_deleted_count or fact.row_modified_count)
        else:
            assert fact.row_added_count or fact.row_deleted_count or fact.row_modified_count
