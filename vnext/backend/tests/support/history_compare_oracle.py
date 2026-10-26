"""Shared history-compare local oracle helpers for unit and compose gates."""

from __future__ import annotations

from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput,
    ComparisonFacts,
    ComparisonPlan,
    ComparisonRequest,
    ComparisonTableStatus,
    DetailedFactsResult,
    compare_plan,
    plan_comparison,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    MaterializationStage,
    RepositoryRef,
    RepositoryRefMaterializationRequest,
)
from gateway_backend.capabilities.snapshot_materialization.repository_ref import materialize_repository_ref
from gateway_backend.capabilities.table_access.contracts import NeverCancel, ParserInvocationContext
from gateway_backend.capabilities.table_rules import comparison_rule_set, migrated_table_ruleset_snapshot
from gateway_backend.capabilities.table_rules.contracts import TABLE_RULESET_VERSION
from gateway_backend.application.canonical_metadata.binding import canonical_binding_for_commit
from gateway_backend.application.history.compare_jobs import _bound_from_materialization
from tests.support.history_compare_job_harness import REPOSITORY_ID
from tests.support.repository_ref_materialization import (
    FakeRepositoryTableAccessProvider,
)
from tests.support.canonical_metadata import metadata_for_catalog


def materialize_bound_snapshot(
    provider: FakeRepositoryTableAccessProvider,
    *,
    commit_id: str,
    artifact_store: object,
) -> BoundSnapshotInput:
    ruleset = migrated_table_ruleset_snapshot()
    metadata = metadata_for_catalog(
        provider.catalog,
        rows_by_table={name: tuple(tuple(row) for row in rows) for name, rows in provider.rows.items()},
        ruleset=ruleset,
    )
    canonical_binding = canonical_binding_for_commit(metadata, runtime_ruleset=ruleset)
    request = RepositoryRefMaterializationRequest(
        repository_ref=RepositoryRef(repository_id=REPOSITORY_ID, ref=commit_id),
        provider=provider,
        ruleset=ruleset,
        canonical_binding=canonical_binding,
        table_ruleset_version=TABLE_RULESET_VERSION,
        materialization_stage=MaterializationStage.FINAL,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        context=ParserInvocationContext(NeverCancel()),
        artifact_store=artifact_store,
    )
    result = materialize_repository_ref(request)
    assert result.status.value == "COMPLETE"
    return _bound_from_materialization(result, canonical_binding=canonical_binding)


def compare_bound_snapshots(
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    *,
    pair_id: str = "pair-0",
) -> ComparisonFacts:
    plan = plan_comparison(
        ComparisonRequest(
            pair_id=pair_id,
            before=before,
            current=current,
            rule_set=comparison_rule_set(migrated_table_ruleset_snapshot()),
        )
    )
    assert isinstance(plan, ComparisonPlan)
    result = compare_plan(plan)
    assert isinstance(result, DetailedFactsResult) and result.facts is not None
    return result.facts


def oracle_comparison_digest(
    *,
    before_provider: FakeRepositoryTableAccessProvider,
    current_provider: FakeRepositoryTableAccessProvider,
    before_commit: str,
    current_commit: str,
    artifact_store: object,
) -> str:
    before = materialize_bound_snapshot(
        before_provider,
        commit_id=before_commit,
        artifact_store=artifact_store,
    )
    current = materialize_bound_snapshot(
        current_provider,
        commit_id=current_commit,
        artifact_store=artifact_store,
    )
    return compare_bound_snapshots(before, current).comparison_digest.value


def assert_added_table_only_facts(
    *,
    before_provider: FakeRepositoryTableAccessProvider,
    current_provider: FakeRepositoryTableAccessProvider,
    before_commit: str,
    current_commit: str,
    artifact_store: object,
    expected_record_count: int = 1,
) -> None:
    before = materialize_bound_snapshot(
        before_provider,
        commit_id=before_commit,
        artifact_store=artifact_store,
    )
    current = materialize_bound_snapshot(
        current_provider,
        commit_id=current_commit,
        artifact_store=artifact_store,
    )
    facts = compare_bound_snapshots(before, current)
    assert len(facts.tables) == 1
    assert facts.tables[0].status is ComparisonTableStatus.ADDED_TABLE
    record_count = sum(len(table.records) for table in facts.tables)
    assert record_count == expected_record_count
