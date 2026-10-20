"""Dataset replacement emits table facts and comparison-level risk only."""

from __future__ import annotations

import pytest

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput,
    ComparisonFacts,
    ComparisonMode,
    ComparisonRequest,
    ComparisonTableStatus,
    ComparisonPlan,
    DatasetReplacementResult,
    compare_plan,
    plan_comparison,
)
from gateway_backend.capabilities.risk_evaluation import (
    RiskEvaluationInput,
    RiskEvaluationStatus,
    RiskOptions,
    RiskReasonCode,
    RiskRulesetSnapshot,
    RiskLevel,
    V1_RISK_RULE_SPECS,
    evaluate_risk,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import MaterializationPolicy
from tests.support.snapshot_materialization import materialize_sql
from tests.support.table_rules import comparison_ruleset_for, standard_rule_record

pytestmark = pytest.mark.unit


def _bound(sql: str) -> BoundSnapshotInput:
    result = materialize_sql(sql, policy=MaterializationPolicy.READERS_REQUIRED)
    assert result.snapshot is not None
    assert result.summary is not None
    assert result.table_set is not None
    return BoundSnapshotInput(result.snapshot, result.summary, result.table_set)


def _replacement(
    before_sql: str,
    current_sql: str,
) -> ComparisonFacts:
    request = ComparisonRequest(
        pair_id="replacement-pair",
        before=_bound(before_sql),
        current=_bound(current_sql),
        rule_set=comparison_ruleset_for(standard_rule_record("version_manager")),
        mode=ComparisonMode.DATASET_REPLACEMENT,
    )
    plan = plan_comparison(request)
    assert isinstance(plan, ComparisonPlan)
    result = compare_plan(plan)
    assert isinstance(result, DatasetReplacementResult)
    assert result.facts is not None
    return result.facts


@pytest.mark.parametrize(
    ("before_sql", "current_sql", "expected_status", "added", "deleted"),
    (
        (
            "CREATE TABLE version_manager (id INT NOT NULL PRIMARY KEY, version VARCHAR(8)); "
            "INSERT INTO version_manager VALUES (1, 'a'), (2, 'b');",
            "CREATE TABLE version_manager (id INT NOT NULL PRIMARY KEY, version VARCHAR(8)); "
            "INSERT INTO version_manager VALUES (8, 'z');",
            ComparisonTableStatus.REPLACED,
            1,
            2,
        ),
        (
            "CREATE TABLE version_manager (id INT NOT NULL PRIMARY KEY, version VARCHAR(8)); "
            "INSERT INTO version_manager VALUES (1, 'a'), (2, 'b');",
            "",
            ComparisonTableStatus.DELETED_TABLE,
            0,
            2,
        ),
        (
            "",
            "CREATE TABLE version_manager (id INT NOT NULL PRIMARY KEY, version VARCHAR(8)); "
            "INSERT INTO version_manager VALUES (8, 'z');",
            ComparisonTableStatus.ADDED_TABLE,
            1,
            0,
        ),
    ),
    ids=("replaced", "deleted", "added"),
)
def test_replacement_produces_table_facts_without_row_records(
    before_sql: str,
    current_sql: str,
    expected_status: ComparisonTableStatus,
    added: int,
    deleted: int,
) -> None:
    facts = _replacement(before_sql, current_sql)

    assert facts.comparison_mode is ComparisonMode.DATASET_REPLACEMENT
    assert len(facts.tables) == 1
    table = facts.tables[0]
    assert table.status is expected_status
    assert table.row_added_count == added
    assert table.row_deleted_count == deleted
    assert table.records == ()
    assert facts.records_ref is None


def test_replacement_risk_is_high_at_pair_scope_without_table_annotations() -> None:
    facts = _replacement(
        "CREATE TABLE version_manager (id INT NOT NULL PRIMARY KEY, version VARCHAR(8)); "
        "INSERT INTO version_manager VALUES (1, 'a');",
        "CREATE TABLE version_manager (id INT NOT NULL PRIMARY KEY, version VARCHAR(8)); "
        "INSERT INTO version_manager VALUES (8, 'z');",
    )

    result = evaluate_risk(
        RiskEvaluationInput(
            comparison_facts=facts,
            risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS),
            risk_options=RiskOptions(),
        ),
        artifact_store=InMemoryArtifactStore(),
    )

    assert result.status is RiskEvaluationStatus.READY
    assert result.risk_report is not None
    assert result.risk_report.overall.risk_level is RiskLevel.HIGH
    assert result.risk_report.overall.reason_codes == (
        RiskReasonCode.PROJECT_IDENTITY_MISMATCH,
    )
    assert result.risk_report.overall.table_count == 0
    assert result.risk_report.overall.annotation_count == 0
    assert result.risk_report.tables == ()

