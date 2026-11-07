"""Independent S3 risk replay expectations from the frozen Python control flow.

These cases deliberately feed small contract facts, without invoking either comparison
kernel. The expected counts come from Risk Contract S3 and _engine.emit's existing
limit-before-filter, normal-return, and exception branches.
"""

from __future__ import annotations

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonFacts,
    ComparisonMode,
    ComparisonRecord,
    ComparisonRecordKind,
    ComparisonSummary,
    ComparisonTableFact,
    ComparisonTableStatus,
    PairResultStatus,
)
from gateway_backend.capabilities.risk_evaluation import (
    RiskEvaluationInput,
    RiskEvaluationStatus,
    RiskExecutionPolicy,
    RiskOptions,
    RiskRulesetSnapshot,
    V1_RISK_RULE_SPECS,
    evaluate_risk,
)


def _added_rows(
    name: str,
    count: int,
    *,
    diagnostics: tuple[str, ...] = (),
) -> ComparisonTableFact:
    return ComparisonTableFact(
        table_name=name,
        status=ComparisonTableStatus.MODIFIED,
        row_added_count=count,
        records=tuple(
            ComparisonRecord(
                table_name=name,
                record_kind=ComparisonRecordKind.ROW_ADDED,
                row_identity=DigestRef(f"sha256:{index + 1:064x}"),
            )
            for index in range(count)
        ),
        diagnostics=diagnostics,
    )


def _input(tables: tuple[ComparisonTableFact, ...], *, options: RiskOptions | None = None) -> RiskEvaluationInput:
    facts = ComparisonFacts(
        comparison_digest=raw_blob_digest(b"s3-risk-comparison"),
        facts_core_digest=raw_blob_digest(b"s3-risk-facts"),
        comparison_contract_version="backend-vnext/comparison/v3",
        projection_contract_version="backend-vnext/comparison-projection/v1",
        scalar_encoding_version=1,
        before_snapshot_digest=raw_blob_digest(b"s3-risk-before"),
        current_snapshot_digest=raw_blob_digest(b"s3-risk-current"),
        comparison_mode=ComparisonMode.DETAILED,
        direction="BEFORE_TO_CURRENT",
        summary=ComparisonSummary(
            status=PairResultStatus.CHANGED,
            table_count=len(tables),
            unchanged_table_count=0,
            changed_table_count=len(tables),
            added_table_count=0,
            deleted_table_count=0,
            schema_changed_table_count=sum(
                table.status in {
                    ComparisonTableStatus.SCHEMA_CHANGED,
                    ComparisonTableStatus.SCHEMA_ONLY_CHANGED,
                }
                for table in tables
            ),
            degraded_table_count=0,
            row_added_count=sum(table.row_added_count for table in tables),
            row_deleted_count=0,
            row_modified_count=0,
            suppressed_added_count=0,
            suppressed_deleted_count=0,
            diagnostics_count=sum(len(table.diagnostics) for table in tables),
        ),
        tables=tables,
    )
    return RiskEvaluationInput(
        comparison_facts=facts,
        risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS),
        risk_options=options or RiskOptions(),
    )


def test_table_budget_exception_does_not_consume_pair_count() -> None:
    # A's third Emit raises the table exception. Its one degraded annotation is
    # published, but the outer exception path does not add it to total_annotations.
    # B consumes two of three pair slots; C consumes the final slot and ends.
    source = _input((_added_rows("a", 3), _added_rows("b", 2), _added_rows("c", 1)))
    result = evaluate_risk(
        source,
        artifact_store=InMemoryArtifactStore(),
        execution_policy=RiskExecutionPolicy(max_annotations_per_table=2, max_annotations_per_pair=3),
    )

    assert result.status is RiskEvaluationStatus.DEGRADED
    assert result.risk_report is not None
    assert tuple((table.table_name, table.annotation_count) for table in result.risk_report.tables) == (
        ("a", 1),
        ("b", 2),
        ("c", 1),
    )
    assert result.risk_report.tables[0].diagnostics == ("risk table budget exceeded",)
    assert result.risk_closure is not None


def test_diagnostics_preflight_degraded_does_consume_pair_count() -> None:
    # A normally returns its degraded outcome from the diagnostics preflight.
    # Its count is therefore one: B fills the pair cap and C's next Emit triggers
    # pair degradation, discarding all partial annotations and their closure.
    source = _input(
        (
            _added_rows("a", 3, diagnostics=("first", "second")),
            _added_rows("b", 2),
            _added_rows("c", 1),
        )
    )
    result = evaluate_risk(
        source,
        artifact_store=InMemoryArtifactStore(),
        execution_policy=RiskExecutionPolicy(
            max_annotations_per_table=2,
            max_annotations_per_pair=3,
            max_diagnostics_per_table=1,
        ),
    )

    assert result.status is RiskEvaluationStatus.DEGRADED
    assert result.risk_report is not None
    assert tuple((table.table_name, table.annotation_count) for table in result.risk_report.tables) == (
        ("a", 0),
        ("b", 0),
        ("c", 0),
    )
    assert all(
        table.diagnostics == ("max_annotations_per_pair exceeded",)
        for table in result.risk_report.tables
    )
    assert result.annotation_artifacts == ()
    assert result.risk_closure is None


def test_filtered_emit_after_pair_cap_still_triggers_pair_degradation() -> None:
    # ROW_ADDED is MEDIUM_LOW in the frozen ruleset. The second table's Emit is
    # filtered by include_low_risk=False, but the pair cap is checked first.
    first = ComparisonTableFact(
        table_name="a",
        status=ComparisonTableStatus.SCHEMA_CHANGED,
    )
    second = _added_rows("b", 1)
    result = evaluate_risk(
        _input((first, second), options=RiskOptions(include_low_risk=False)),
        artifact_store=InMemoryArtifactStore(),
        execution_policy=RiskExecutionPolicy(max_annotations_per_pair=1),
    )

    assert result.status is RiskEvaluationStatus.DEGRADED
    assert result.risk_report is not None
    assert tuple(table.annotation_count for table in result.risk_report.tables) == (0, 0)
    assert result.annotation_artifacts == ()
    assert result.risk_closure is None
