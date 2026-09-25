"""Shared history-compare local oracle helpers for unit and compose gates."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.comparison import (
    ArtifactScope,
    BoundSnapshotInput,
    ComparisonPlan,
    ComparisonTablePolicy,
    ComparisonTableStatus,
    DetailedFactsResult,
    InputCompleteness,
    PairRole,
    PairViewKind,
    TrustedFlowApplicabilityBinding,
    bind_pair_input,
    compare_plan,
    plan_pair,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    MaterializationStage,
    RepositoryRef,
    RepositoryRefMaterializationRequest,
)
from gateway_backend.capabilities.snapshot_materialization.repository_ref import materialize_repository_ref
from gateway_backend.capabilities.table_access.contracts import NeverCancel, ParserInvocationContext
from gateway_backend.capabilities.table_rules.contracts import TABLE_RULESET_VERSION, TableRulesetSnapshot
from gateway_backend.application.history.compare_jobs import _bound_from_materialization
from tests.support.history_compare_job_harness import REPOSITORY_ID
from tests.support.repository_ref_materialization import FakeRepositoryTableAccessProvider


def materialize_bound_snapshot(
    provider: FakeRepositoryTableAccessProvider,
    *,
    commit_id: str,
    artifact_store: object,
) -> BoundSnapshotInput:
    request = RepositoryRefMaterializationRequest(
        repository_ref=RepositoryRef(repository_id=REPOSITORY_ID, ref=commit_id),
        provider=provider,
        ruleset=TableRulesetSnapshot(table_ruleset_version=TABLE_RULESET_VERSION),
        table_ruleset_version=TABLE_RULESET_VERSION,
        materialization_stage=MaterializationStage.FINAL,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        context=ParserInvocationContext(NeverCancel()),
        artifact_store=artifact_store,
    )
    result = materialize_repository_ref(request)
    assert result.status.value == "COMPLETE"
    return _bound_from_materialization(result)


def oracle_comparison_digest(
    *,
    before_provider: FakeRepositoryTableAccessProvider,
    current_provider: FakeRepositoryTableAccessProvider,
    before_commit: str,
    current_commit: str,
    table_policies: tuple[ComparisonTablePolicy, ...],
    compare_binding_digest: str,
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
    bound = bind_pair_input(
        pair_id="pair-0",
        view_kind=PairViewKind.HISTORY,
        pair_role=PairRole.HISTORY,
        before=before,
        current=current,
        input_completeness=InputCompleteness.FULL,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        trusted_flow_binding=TrustedFlowApplicabilityBinding(
            view_kind=PairViewKind.HISTORY,
            binding_digest=DigestRef(compare_binding_digest),
        ),
        table_policies=table_policies,
    )
    planned = plan_pair(bound)
    assert isinstance(planned, ComparisonPlan)
    compared = compare_plan(planned)
    assert isinstance(compared, DetailedFactsResult) and compared.facts is not None
    return compared.facts.comparison_digest.value


def assert_added_table_only_facts(
    *,
    before_provider: FakeRepositoryTableAccessProvider,
    current_provider: FakeRepositoryTableAccessProvider,
    before_commit: str,
    current_commit: str,
    table_policies: tuple[ComparisonTablePolicy, ...],
    compare_binding_digest: str,
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
    bound = bind_pair_input(
        pair_id="pair-0",
        view_kind=PairViewKind.HISTORY,
        pair_role=PairRole.HISTORY,
        before=before,
        current=current,
        input_completeness=InputCompleteness.FULL,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        trusted_flow_binding=TrustedFlowApplicabilityBinding(
            view_kind=PairViewKind.HISTORY,
            binding_digest=DigestRef(compare_binding_digest),
        ),
        table_policies=table_policies,
    )
    planned = plan_pair(bound)
    assert isinstance(planned, ComparisonPlan)
    compared = compare_plan(planned)
    assert isinstance(compared, DetailedFactsResult) and compared.facts is not None
    facts = compared.facts
    assert len(facts.tables) == 1
    assert facts.tables[0].status is ComparisonTableStatus.ADDED_TABLE
    record_count = sum(len(table.records) for table in facts.tables)
    assert record_count == expected_record_count
