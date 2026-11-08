"""Business assertions retained on the live comparison route."""

from __future__ import annotations

import pytest

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.comparison import (
    ComparisonFacts, ComparisonTableStatus, DetailedFactsResult, SchemaEvolution,
)
from gateway_backend.capabilities.risk_evaluation import (
    RiskEvaluationInput, RiskEvaluationStatus, RiskOptions, RiskReasonCode,
    RiskRulesetSnapshot, V1_RISK_RULE_SPECS, evaluate_risk,
)
from tests.support.comparison_s3_e_live import native_product

pytestmark = pytest.mark.unit

_ENUM_SET_CASES = (
    pytest.param("ENUM", "'a','b'", "'A','b'", "'b'", True,
                 SchemaEvolution.INCOMPATIBLE, id="enum-case-with-added-column"),
    pytest.param("SET", "'x','y'", "'x','z'", "'x'", True,
                 SchemaEvolution.INCOMPATIBLE, id="set-rename-with-added-column"),
    pytest.param("ENUM", "'a','b'", "'A','b'", "'b'", False,
                 SchemaEvolution.INCOMPATIBLE, id="enum-case-without-added-column"),
    pytest.param("SET", "'x','y'", "'x','z'", "'x'", False,
                 SchemaEvolution.INCOMPATIBLE, id="set-rename-without-added-column"),
    pytest.param("ENUM", "'a','c'", "'a','b','c'", "'c'", True,
                 SchemaEvolution.COLUMNS_ADDED, id="enum-add-in-middle"),
    pytest.param("SET", "'x','z'", "'x','y','z'", "'x'", True,
                 SchemaEvolution.COLUMNS_ADDED, id="set-add-in-middle"),
)


def _facts(before: str, current: str) -> ComparisonFacts:
    product = native_product(before, current)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        return product.result.facts
    finally:
        product.close()


@pytest.mark.parametrize(
    ("type_name", "old_labels", "new_labels", "value", "add_note", "evolution"),
    _ENUM_SET_CASES,
)
def test_enum_set_label_spelling_changes_schema_and_risk(
    type_name: str, old_labels: str, new_labels: str, value: str,
    add_note: bool, evolution: SchemaEvolution,
) -> None:
    before = (
        f"CREATE TABLE t (id INT PRIMARY KEY, state {type_name}({old_labels}) NULL);"
        f" INSERT INTO t VALUES (1,{value});"
    )
    note = ", note TEXT NULL" if add_note else ""
    note_value = ", 'new'" if add_note else ""
    current = (
        f"CREATE TABLE t (id INT PRIMARY KEY, state {type_name}({new_labels}) NULL{note});"
        f" INSERT INTO t VALUES (1,{value}{note_value});"
    )
    facts = _facts(before, current)
    table, = facts.tables
    assert table.schema_changes.schema_evolution is evolution
    assert table.schema_changes.current_only_columns == (("note",) if add_note else ())
    if evolution is SchemaEvolution.INCOMPATIBLE:
        assert table.status is ComparisonTableStatus.SCHEMA_CHANGED
        assert table.schema_changes.incompatible_columns == ("state",)
    else:
        assert table.status is ComparisonTableStatus.UNCHANGED
        assert table.schema_changes.incompatible_columns == ()
    risk = evaluate_risk(
        RiskEvaluationInput(
            comparison_facts=facts,
            risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS),
            risk_options=RiskOptions(),
        ),
        artifact_store=InMemoryArtifactStore(),
    )
    assert risk.status is RiskEvaluationStatus.READY
    assert risk.risk_report is not None
    if evolution is SchemaEvolution.INCOMPATIBLE:
        assert RiskReasonCode.SCHEMA_CHANGED in risk.risk_report.tables[0].reason_codes
        assert risk.risk_report.tables[0].risk_level.value == "MEDIUM_HIGH"
    else:
        assert risk.risk_report.tables == ()


@pytest.mark.parametrize(
    ("rows", "changed"),
    (
        ("(2,'b','y'),(1,'a','x')", False),
        ("(2,'b','x'),(1,'a','y')", True),
    ),
    ids=("added-column-physical-reorder", "excluded-values-swap-association"),
)
def test_standard_added_column_preserves_shared_row_association(
    rows: str, changed: bool,
) -> None:
    before = (
        "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(8), secret VARCHAR(8));"
        " INSERT INTO t VALUES (1,'a','x'),(2,'b','y');"
    )
    added_rows = rows.replace(")", ",'z')")
    current = (
        "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(8), secret VARCHAR(8),"
        " added VARCHAR(8));"
        f" INSERT INTO t VALUES {added_rows};"
    )
    product = native_product(before, current, compare_excluded_columns=("secret",))
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.schema_changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED
        assert table.status is ComparisonTableStatus.UNCHANGED
        assert table.content_changed is changed
        assert table.row_modified_count == 0
        assert product.handles["t"].family_summary("STANDARD")[0] == 0
    finally:
        product.close()


def test_excluded_value_change_is_visible_without_row_record() -> None:
    schema = "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(8), aux VARCHAR(8));"
    before = schema + " INSERT INTO t VALUES (1,'same','before');"
    current = schema + " INSERT INTO t VALUES (1,'same','current');"
    product = native_product(before, current, compare_excluded_columns=("aux",))
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        table, = product.result.facts.tables
        assert table.status is ComparisonTableStatus.UNCHANGED
        assert table.content_changed
        assert table.row_modified_count == 0
        assert product.handles["t"].family_summary("STANDARD")[0] == 0
    finally:
        product.close()


def test_removed_column_is_distinct_from_incompatible_schema() -> None:
    before = (
        "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(8), note TEXT);"
        " INSERT INTO t VALUES (1,'same','old');"
    )
    current = (
        "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(8));"
        " INSERT INTO t VALUES (1,'same');"
    )
    table, = _facts(before, current).tables
    assert table.status is ComparisonTableStatus.SCHEMA_CHANGED
    assert table.schema_changes.schema_evolution is SchemaEvolution.COLUMNS_REMOVED
    assert table.schema_changes.before_only_columns == ("note",)


def test_comparison_digest_is_repeatable_and_directional() -> None:
    schema = "CREATE TABLE t (id INT PRIMARY KEY);"
    before = schema + " INSERT INTO t VALUES (1);"
    current = schema + " INSERT INTO t VALUES (2);"
    first = _facts(before, current)
    repeat = _facts(before, current)
    reverse = _facts(current, before)
    assert first.comparison_digest == repeat.comparison_digest
    assert first.facts_core_digest == repeat.facts_core_digest
    assert first.comparison_digest != reverse.comparison_digest
    assert first.tables[0].row_added_count == reverse.tables[0].row_deleted_count
    assert first.tables[0].row_deleted_count == reverse.tables[0].row_added_count
