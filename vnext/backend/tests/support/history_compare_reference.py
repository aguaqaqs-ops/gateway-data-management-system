"""History comparison checks over the live canonical Arrow path."""

from __future__ import annotations

from contextlib import closing

from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput,
    ComparisonFacts,
    ComparisonPlan,
    ComparisonRequest,
    DetailedFactsResult,
    plan_comparison,
)
from gateway_backend.capabilities.comparison.contracts import OrderedRecordKind
from gateway_backend.capabilities.comparison.production import compare_plan_native
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
from tests.support.repository_ref_materialization import (
    FakeRepositoryTableAccessProvider, _bind_fixture_tables,
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
        repository_ref=RepositoryRef(repository_id=provider.catalog.repository_id, ref=commit_id),
        provider=provider,
        ruleset=ruleset,
        canonical_binding=canonical_binding,
        table_ruleset_version=TABLE_RULESET_VERSION,
        materialization_stage=MaterializationStage.FINAL,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        context=ParserInvocationContext(NeverCancel()),
        artifact_store=artifact_store,
    )
    result = materialize_repository_ref(_bind_fixture_tables(request, provider))
    assert result.status.value == "COMPLETE"
    return _bound_from_materialization(result, canonical_binding=canonical_binding)


def compare_bound_snapshots(
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    *,
    pair_id: str = "pair-0",
) -> ComparisonFacts:
    product = compare_plan_native(_plan_bound_snapshots(before, current, pair_id=pair_id))
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        return product.result.facts
    finally:
        product.close()


def compare_bound_snapshots_and_ordered_kinds(
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    *,
    pair_id: str = "pair-0",
) -> tuple[ComparisonFacts, tuple[OrderedRecordKind, ...]]:
    product = compare_plan_native(_plan_bound_snapshots(before, current, pair_id=pair_id))
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        kinds = []
        for table_name in sorted(product.handles):
            with closing(product.handles[table_name].record_batches("ORDERED")) as reader:
                for batch in reader:
                    kinds.extend(
                        OrderedRecordKind(row["record_kind"])
                        for row in batch.to_pylist()
                    )
        return product.result.facts, tuple(kinds)
    finally:
        product.close()


def local_comparison_digest(
    *,
    before_provider: FakeRepositoryTableAccessProvider,
    current_provider: FakeRepositoryTableAccessProvider,
    before_commit: str,
    current_commit: str,
    artifact_store: object,
) -> str:
    """Check History input binding against a separate local native invocation."""
    before = materialize_bound_snapshot(
        before_provider, commit_id=before_commit, artifact_store=artifact_store,
    )
    current = materialize_bound_snapshot(
        current_provider, commit_id=current_commit, artifact_store=artifact_store,
    )
    return compare_bound_snapshots(before, current).comparison_digest.value


def _plan_bound_snapshots(
    before: BoundSnapshotInput, current: BoundSnapshotInput, *, pair_id: str,
) -> ComparisonPlan:
    plan = plan_comparison(
        ComparisonRequest(
            pair_id=pair_id,
            before=before,
            current=current,
            rule_set=comparison_rule_set(migrated_table_ruleset_snapshot()),
        )
    )
    assert isinstance(plan, ComparisonPlan)
    return plan
