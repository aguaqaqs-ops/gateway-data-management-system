"""History compare job pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.application.checkpoints import load_checkpoint_envelope
from gateway_backend.application.history.contracts import HistoryCompareDiagnosticCode
from gateway_backend.application.history.compare_jobs import (
    HISTORY_COMPARE_ASSEMBLE_HANDLER,
    HISTORY_COMPARE_MATERIALIZE_HANDLER,
    HISTORY_COMPARE_PUBLISH_HANDLER,
    HISTORY_COMPARE_STEP_ASSEMBLE,
    HISTORY_COMPARE_STEP_MATERIALIZE,
    HISTORY_COMPARE_STEP_PUBLISH,
    _bound_from_materialization,
    _table_policies_from_checkpoint,
    history_compare_step_id,
)
from gateway_backend.capabilities.comparison import (
    ArtifactScope,
    BoundSnapshotInput,
    ComparisonPlan,
    ComparisonTablePolicy,
    ComparisonTableStatus,
    DetailedFactsResult,
    InputCompleteness,
    OrderedRecordKind,
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
from gateway_backend.capabilities.table_rules.contracts import TableRulesetSnapshot
from gateway_backend.capabilities.snapshot_materialization.repository_ref import materialize_repository_ref
from gateway_backend.capabilities.table_access.contracts import NeverCancel, ParserInvocationContext
from gateway_backend.capabilities.table_rules.contracts import TABLE_RULESET_VERSION
from gateway_backend.http.errors import ApiError
from gateway_backend.http.orchestration.history_compare import get_compare_result
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.operations import OperationStatus, StepStatus
from tests.support.http_workspace_harness import BASELINE_HEAD
from tests.support.history_compare_job_harness import (
    ORDERED_SYX_TABLE,
    REPOSITORY_ID,
    build_history_compare_harness,
    claim_next_step,
    history_compare_net_cfg_provider,
    history_compare_ordered_provider,
    history_compare_provider,
    insert_history_compare_operation,
    run_claimed_handler,
    run_full_history_compare_job,
    run_through_step,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    RepositoryCatalogTable,
    RepositoryColumn,
)
from tests.support.repository_ref_materialization import (
    FakeRepositoryTableAccessProvider,
    catalog_table,
    hidden_summary_for,
    int_id_column,
    make_catalog,
    text_column,
)
from gateway_backend.operations.contracts import BusinessReference

from tests.support.history_zero_write_tables import capture_business_table_state

ORDERED_SYX_TABLE_EXPECTED_POLICY: dict[str, object] = {
    "table_name": ORDERED_SYX_TABLE,
    "ignored_columns": ["no"],
    "keyless_policy": "DEGRADE_NO_COMPARE_KEY",
    "policy_version": "comparison-table-policy/v1",
    "ordered_policy": {
        "policy_id": "ordered-gid-no-v1",
        "policy_version": "backend-vnext/ordered-diff/v2",
        "order_key": ["no"],
        "row_identity_key": ["gid"],
        "stable_key_candidates": ["gid"],
        "value_columns": [],
        "ignored_columns": ["no"],
        "blank_row_policy": "PSEUDO_BLANK_BY_MISSING_STABLE_KEY",
        "move_policy": "STABLE_KEY_RELATIVE_ORDER_V1",
        "ambiguity_policy": "DEGRADE_ON_AMBIGUITY",
        "tail_change_policy": "INTERVAL_OR_ROW_V1",
        "table_processing_mode_policy": "ORDERED_MODE_V1",
    },
}

NET_CFG_STANDARD_DIFF_EXPECTED_POLICY: dict[str, object] = {
    "table_name": "net_cfg",
    "ignored_columns": ["no"],
    "keyless_policy": "DEGRADE_NO_COMPARE_KEY",
    "policy_version": "comparison-table-policy/v1",
}

F1_POLICY_BINDING_CASES = (
    (
        "move_only",
        {ORDERED_SYX_TABLE: ((1, 1, "a"), (2, 2, "b"))},
        {ORDERED_SYX_TABLE: ((2, 1, "b"), (1, 2, "a"))},
        (OrderedRecordKind.ROW_MOVED, OrderedRecordKind.ROW_MOVED),
        0,
    ),
    (
        "pseudo_blank",
        {ORDERED_SYX_TABLE: ((1, 1, "a"),)},
        {ORDERED_SYX_TABLE: ((1, 1, "a"), (None, 2, "blank"))},
        (),
        0,
    ),
    (
        "keyed_ignored_column",
        {ORDERED_SYX_TABLE: ((1, 1, "a"), (2, 2, "b"))},
        {ORDERED_SYX_TABLE: ((1, 99, "a"), (2, 2, "b"))},
        (OrderedRecordKind.ROW_MOVED, OrderedRecordKind.ROW_MOVED),
        0,
    ),
)

pytestmark = pytest.mark.unit


def test_materialize_deduplicates_identical_commits(tmp_path: Path) -> None:
    harness = build_history_compare_harness(
        tmp_path,
        node_specs=(
            (BASELINE_HEAD.business_baseline_node_id, BASELINE_HEAD.business_baseline_commit_id),
            ("bn-b", BASELINE_HEAD.business_baseline_commit_id),
        ),
    )
    insert_history_compare_operation(harness)
    before_opens = harness.total_open_count()
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    assert harness.total_open_count() - before_opens == 1

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert materialize_step.status is StepStatus.SUCCEEDED
    assert materialize_step.checkpoint_ref is not None
    assert assemble_step.status is StepStatus.PENDING
    envelope = load_checkpoint_envelope(harness.artifact_store, materialize_step.checkpoint_ref)
    sides = envelope.job_state["sides"]
    assert isinstance(sides, dict)
    assert set(sides) == {BASELINE_HEAD.business_baseline_commit_id}
    assert isinstance(envelope.job_state.get("compare_binding_digest"), str)


def test_assemble_resumes_without_rederiving_compare_binding(tmp_path: Path) -> None:
    harness = build_history_compare_harness(tmp_path, idempotency_key="history-compare-resume")
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
    assert materialize_step.checkpoint_ref is not None
    with (
        patch(
            "gateway_backend.application.history.compare_jobs.migrated_table_ruleset_snapshot",
            side_effect=RuntimeError("ruleset must not be re-derived"),
        ),
        patch(
            "gateway_backend.application.history.compare_jobs.resolve_table_rule",
            side_effect=RuntimeError("policy must not be re-derived"),
        ),
    ):
        run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
        run_through_step(harness, HISTORY_COMPARE_PUBLISH_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert operation.status is OperationStatus.SUCCEEDED
    assert assemble_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, assemble_step.checkpoint_ref)
    assemble_state = envelope.job_state["assemble_state"]
    assert isinstance(assemble_state, dict)
    assert assemble_state["bundle_digest"]


def test_primary_key_change_across_commits_degrades_without_failing_job(tmp_path: Path) -> None:
    before_commit = BASELINE_HEAD.business_baseline_commit_id
    current_commit = "commit-b"
    value_col = text_column("value", 1)
    id_table = catalog_table("t", (int_id_column(), value_col), primary_key=("id",))
    code_col = RepositoryColumn(name="code", ordinal=0, scalar_type="INT", nullable=False)
    code_table = catalog_table("t", (code_col, value_col), primary_key=("code",))
    rows = {"t": ((1, "a"),)}

    def _provider(commit_id: str, table: RepositoryCatalogTable) -> FakeRepositoryTableAccessProvider:
        catalog = make_catalog(
            (table,),
            repository_id=REPOSITORY_ID,
            ref=commit_id,
            commit=commit_id,
        )
        hidden = hidden_summary_for(catalog, rows)
        return FakeRepositoryTableAccessProvider(
            catalog=catalog,
            base_catalog=catalog,
            hidden=hidden,
            rows=rows,
            declared_rows=rows,
            current_commit=commit_id,
        )

    providers = {
        before_commit: _provider(before_commit, id_table),
        current_commit: _provider(current_commit, code_table),
    }
    harness = build_history_compare_harness(
        tmp_path,
        custom_providers=providers,
        idempotency_key="history-compare-pk-change",
    )
    run_full_history_compare_job(harness)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        incident = unit_of_work.history_compare.get_integrity_by_operation_id(harness.operation_id)
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
    assert operation.status is OperationStatus.SUCCEEDED
    assert incident is None
    assert materialize_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, materialize_step.checkpoint_ref)
    policies_raw = envelope.job_state["table_policies"]
    assert isinstance(policies_raw, list)
    table_policies = _table_policies_from_checkpoint(policies_raw)
    bound = bind_pair_input(
        pair_id="pair-0",
        view_kind=PairViewKind.HISTORY,
        pair_role=PairRole.HISTORY,
        before=_materialize_bound(
            providers[before_commit],
            commit_id=before_commit,
            artifact_store=harness.artifact_store,
        ),
        current=_materialize_bound(
            providers[current_commit],
            commit_id=current_commit,
            artifact_store=harness.artifact_store,
        ),
        input_completeness=InputCompleteness.FULL,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        trusted_flow_binding=TrustedFlowApplicabilityBinding(
            view_kind=PairViewKind.HISTORY,
            binding_digest=DigestRef(str(envelope.job_state["compare_binding_digest"])),
        ),
        table_policies=table_policies,
    )
    planned = plan_pair(bound)
    assert isinstance(planned, ComparisonPlan)
    compared = compare_plan(planned)
    assert isinstance(compared, DetailedFactsResult) and compared.facts is not None
    assert compared.facts.tables[0].status is ComparisonTableStatus.DEGRADED


def test_two_node_compare_job_succeeds(tmp_path: Path) -> None:
    harness = build_history_compare_harness(tmp_path)
    run_full_history_compare_job(harness)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        publish_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_PUBLISH)
        )
    assert operation.status is OperationStatus.SUCCEEDED
    assert publish_step.status is StepStatus.SUCCEEDED
    assert operation.ready_closure_ref is not None


def test_three_node_compare_job_uses_multi_pair_bundle(tmp_path: Path) -> None:
    import json

    from gateway_backend.artifacts.serialize import artifact_ref_from_dict
    from gateway_backend.capabilities.bundle_assembly import BUNDLE_MANIFEST_MEDIA_TYPE

    node_a = BASELINE_HEAD.business_baseline_node_id
    node_b = "bn-b"
    node_c = "bn-c"
    commit_a = BASELINE_HEAD.business_baseline_commit_id
    commit_b = "commit-b"
    commit_c = "commit-c"
    harness = build_history_compare_harness(
        tmp_path,
        node_specs=(
            (node_a, commit_a),
            (node_b, commit_b),
            (node_c, commit_c),
        ),
        idempotency_key="history-compare-3-node",
    )
    run_full_history_compare_job(harness)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert operation.status is OperationStatus.SUCCEEDED
    assert assemble_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, assemble_step.checkpoint_ref)
    assemble_state = envelope.job_state["assemble_state"]
    assert isinstance(assemble_state, dict)
    pairs = assemble_state["pairs"]
    assert isinstance(pairs, list)
    assert len(pairs) == 2
    assert pairs[0]["pair_id"] == f"{harness.operation_id}-p0"
    assert pairs[1]["pair_id"] == f"{harness.operation_id}-p1"
    assert (pairs[0]["before_commit"], pairs[0]["current_commit"]) == (commit_a, commit_b)
    assert (pairs[1]["before_commit"], pairs[1]["current_commit"]) == (commit_b, commit_c)
    required_refs = assemble_state["required_refs"]
    assert isinstance(required_refs, list)
    manifest_ref = next(
        artifact_ref_from_dict(item)
        for item in required_refs
        if artifact_ref_from_dict(item).media_type == BUNDLE_MANIFEST_MEDIA_TYPE
    )
    manifest = json.loads(harness.artifact_store.locate(manifest_ref).decode("utf-8"))
    assert manifest["bundle_profile"] == "MULTI_PAIR"
    inputs = manifest["inputs"]
    assert [item["display_name"] for item in inputs] == ["node-0", "node-1", "node-2"]
    assert [item["role"] for item in inputs] == [node_a, node_b, node_c]


def test_materialize_records_integrity_failure_for_corrupt_hidden_summary(tmp_path: Path) -> None:
    harness = build_history_compare_harness(
        tmp_path,
        mutate_snapshot_digest_for=frozenset({BASELINE_HEAD.business_baseline_commit_id}),
        idempotency_key="history-compare-integrity",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        incident = unit_of_work.history_compare.get_integrity_by_operation_id(harness.operation_id)
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
    assert operation.status is OperationStatus.FAILED
    assert materialize_step.status is StepStatus.FAILED
    assert incident is not None


def test_ruleset_mismatch_publishes_stable_failed_code(tmp_path: Path) -> None:
    import json

    from gateway_shared_kernel.jcs import canonicalize_json_value

    harness = build_history_compare_harness(tmp_path, idempotency_key="history-compare-ruleset")
    payload = json.loads(harness.job_payload)
    payload["table_ruleset_version"] = "0"
    object.__setattr__(harness, "job_payload", canonicalize_json_value(payload))
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
    assert operation.status is OperationStatus.FAILED
    assert operation.diagnostic is not None
    assert operation.diagnostic.code == HistoryCompareDiagnosticCode.HISTORY_RULESET_VERSION_MISMATCH.value


def test_publish_pins_assemble_checkpoint_and_clears_step_checkpoints(tmp_path: Path) -> None:
    harness = build_history_compare_harness(tmp_path, idempotency_key="history-compare-durable")
    run_full_history_compare_job(harness)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
        publish_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_PUBLISH)
        )
        assert assemble_step.checkpoint_ref is not None
        assemble_ref = assemble_step.checkpoint_ref
        protected = unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-operation",
            owner_id=harness.operation_id,
        )
        step_protected = unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-checkpoint",
            owner_id=materialize_step.step_id,
        )
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-checkpoint",
            owner_id=assemble_step.step_id,
        ) == frozenset()
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-checkpoint",
            owner_id=publish_step.step_id,
        ) == frozenset()
    assert step_protected == frozenset()
    assert assemble_ref.artifact_id in protected
    cast(InMemoryArtifactStore, harness.artifact_store)._artifacts.pop(assemble_ref.artifact_id, None)  # noqa: SLF001

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        acceptance = unit_of_work.history_compare.get_acceptance_by_operation_id(harness.operation_id)
    assert acceptance is not None
    with pytest.raises(ApiError) as exc_info:
        get_compare_result(
            operation=operation,
            acceptance=acceptance,
            unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
                harness.db_path,
                read_only=read_only,
            ),
            artifact_store=harness.artifact_store,
        )
    assert exc_info.value.code == "ARTIFACT_UNAVAILABLE"


def _materialize_bound(
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


def _oracle_comparison_digest(
    *,
    before_provider: FakeRepositoryTableAccessProvider,
    current_provider: FakeRepositoryTableAccessProvider,
    before_commit: str,
    current_commit: str,
    table_policies: tuple[ComparisonTablePolicy, ...],
    compare_binding_digest: str,
    artifact_store: object,
) -> str:
    before = _materialize_bound(before_provider, commit_id=before_commit, artifact_store=artifact_store)
    current = _materialize_bound(current_provider, commit_id=current_commit, artifact_store=artifact_store)
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


@pytest.mark.parametrize(
    ("case_id", "before_rows", "current_rows", "expected_kinds", "expected_modified"),
    F1_POLICY_BINDING_CASES,
)
def test_f1_policy_binding_integration_cases(
    tmp_path: Path,
    case_id: str,
    before_rows: dict[str, tuple[tuple[object, ...], ...]],
    current_rows: dict[str, tuple[tuple[object, ...], ...]],
    expected_kinds: tuple[OrderedRecordKind, ...],
    expected_modified: int,
) -> None:
    before_commit = BASELINE_HEAD.business_baseline_commit_id
    current_commit = "commit-b"
    providers = {
        before_commit: history_compare_ordered_provider(commit_id=before_commit, rows=before_rows),
        current_commit: history_compare_ordered_provider(commit_id=current_commit, rows=current_rows),
    }
    harness = build_history_compare_harness(
        tmp_path,
        node_specs=(
            (BASELINE_HEAD.business_baseline_node_id, before_commit),
            ("bn-b", current_commit),
        ),
        custom_providers=providers,
        idempotency_key=f"history-compare-f1-{case_id}",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
    assert materialize_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, materialize_step.checkpoint_ref)
    policies_raw = envelope.job_state["table_policies"]
    assert isinstance(policies_raw, list)
    assert policies_raw[0] == ORDERED_SYX_TABLE_EXPECTED_POLICY

    run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_PUBLISH_HANDLER)

    table_policies = _table_policies_from_checkpoint(policies_raw)
    oracle_digest = _oracle_comparison_digest(
        before_provider=providers[before_commit],
        current_provider=providers[current_commit],
        before_commit=before_commit,
        current_commit=current_commit,
        table_policies=table_policies,
        compare_binding_digest=str(envelope.job_state["compare_binding_digest"]),
        artifact_store=harness.artifact_store,
    )
    bound = bind_pair_input(
        pair_id="pair-0",
        view_kind=PairViewKind.HISTORY,
        pair_role=PairRole.HISTORY,
        before=_materialize_bound(
            providers[before_commit],
            commit_id=before_commit,
            artifact_store=harness.artifact_store,
        ),
        current=_materialize_bound(
            providers[current_commit],
            commit_id=current_commit,
            artifact_store=harness.artifact_store,
        ),
        input_completeness=InputCompleteness.FULL,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        trusted_flow_binding=TrustedFlowApplicabilityBinding(
            view_kind=PairViewKind.HISTORY,
            binding_digest=DigestRef(str(envelope.job_state["compare_binding_digest"])),
        ),
        table_policies=table_policies,
    )
    planned = plan_pair(bound)
    assert isinstance(planned, ComparisonPlan)
    compared = compare_plan(planned)
    assert isinstance(compared, DetailedFactsResult) and compared.facts is not None
    facts = compared.facts
    kinds: list[OrderedRecordKind] = []
    for table in facts.tables:
        extension = table.ordered_extension
        if extension is not None:
            kinds.extend(record.record_kind for record in extension.records)
    assert kinds == list(expected_kinds)
    modified_count = sum(table.row_modified_count for table in facts.tables)
    assert modified_count == expected_modified

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert assemble_step.checkpoint_ref is not None
    assemble_envelope = load_checkpoint_envelope(harness.artifact_store, assemble_step.checkpoint_ref)
    assemble_state = assemble_envelope.job_state["assemble_state"]
    assert isinstance(assemble_state, dict)
    pair = assemble_state["pairs"][0]
    assert isinstance(pair, dict)
    assert pair["comparison_digest"] == oracle_digest


def test_f1_standard_diff_keyed_ignored_column_net_cfg(tmp_path: Path) -> None:
    table_name = "net_cfg"
    before_commit = BASELINE_HEAD.business_baseline_commit_id
    current_commit = "commit-b"
    before_rows = {table_name: (("b1", 1, 1, "a"),)}
    current_rows = {table_name: (("b1", 1, 99, "a"),)}
    providers = {
        before_commit: history_compare_net_cfg_provider(commit_id=before_commit, rows=before_rows),
        current_commit: history_compare_net_cfg_provider(commit_id=current_commit, rows=current_rows),
    }
    harness = build_history_compare_harness(
        tmp_path,
        node_specs=(
            (BASELINE_HEAD.business_baseline_node_id, before_commit),
            ("bn-netcfg-b", current_commit),
        ),
        custom_providers=providers,
        idempotency_key="history-compare-f1-netcfg",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
    assert materialize_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, materialize_step.checkpoint_ref)
    policies_raw = envelope.job_state["table_policies"]
    assert isinstance(policies_raw, list)
    assert policies_raw[0] == NET_CFG_STANDARD_DIFF_EXPECTED_POLICY

    run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_PUBLISH_HANDLER)

    table_policies = _table_policies_from_checkpoint(policies_raw)
    bound = bind_pair_input(
        pair_id="pair-0",
        view_kind=PairViewKind.HISTORY,
        pair_role=PairRole.HISTORY,
        before=_materialize_bound(
            providers[before_commit],
            commit_id=before_commit,
            artifact_store=harness.artifact_store,
        ),
        current=_materialize_bound(
            providers[current_commit],
            commit_id=current_commit,
            artifact_store=harness.artifact_store,
        ),
        input_completeness=InputCompleteness.FULL,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        trusted_flow_binding=TrustedFlowApplicabilityBinding(
            view_kind=PairViewKind.HISTORY,
            binding_digest=DigestRef(str(envelope.job_state["compare_binding_digest"])),
        ),
        table_policies=table_policies,
    )
    planned = plan_pair(bound)
    assert isinstance(planned, ComparisonPlan)
    compared = compare_plan(planned)
    assert isinstance(compared, DetailedFactsResult) and compared.facts is not None
    facts = compared.facts
    kinds: list[OrderedRecordKind] = []
    for table in facts.tables:
        extension = table.ordered_extension
        if extension is not None:
            kinds.extend(record.record_kind for record in extension.records)
    assert kinds == []
    modified_count = sum(table.row_modified_count for table in facts.tables)
    assert modified_count == 0


def test_job_payload_within_budget_without_table_policies(tmp_path: Path) -> None:
    harness = build_history_compare_harness(tmp_path)
    payload = json.loads(harness.job_payload)
    assert len(harness.job_payload) <= 64 * 1024
    assert "table_policies" not in payload


def test_accept_operation_sets_business_refs_and_protection_owner(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from gateway_backend.application.history.contracts import (
        HistoryCompareAcceptCommand,
        HistoryNodeRef,
        HistoryNodeRefKind,
        PERMISSION_READ_PROJECT_HISTORY,
    )
    from gateway_backend.application.history.compare_jobs import history_compare_job_definitions
    from gateway_backend.application.job_definitions import JobDefinitionRegistry
    from gateway_backend.http.dependencies import OpenAdmissionGate
    from gateway_backend.http.orchestration.history_compare import accept_compare_operation
    from tests.support.workspace_fixtures import make_identity

    harness = build_history_compare_harness(tmp_path, idempotency_key="history-compare-business-refs")
    job_registry = JobDefinitionRegistry.build(history_compare_job_definitions())
    identity = make_identity(permissions=frozenset({PERMISSION_READ_PROJECT_HISTORY}))
    result = accept_compare_operation(
        command=HistoryCompareAcceptCommand(
            context=identity,
            idempotency_key="history-compare-business-refs-accept",
            node_refs=(
                HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, BASELINE_HEAD.business_baseline_node_id),
                HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, "bn-b"),
            ),
        ),
        unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(harness.db_path, read_only=read_only),
        job_registry=job_registry,
        admission_gate=OpenAdmissionGate(),
        table_ruleset_version=str(TABLE_RULESET_VERSION),
        now=datetime(2026, 9, 24, tzinfo=UTC),
    )
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(result.response.operation_id)
        acceptance = unit_of_work.history_compare.get_acceptance_by_operation_id(result.response.operation_id)
    assert acceptance is not None
    assert operation.business_refs == (
        BusinessReference(kind="history_compare", value=acceptance.acceptance_id),
    )


def test_publish_job_does_not_mutate_business_tables(tmp_path: Path) -> None:
    harness = build_history_compare_harness(tmp_path, idempotency_key="history-compare-zero-write")
    before = capture_business_table_state(harness.db_path)
    run_full_history_compare_job(harness)
    after = capture_business_table_state(harness.db_path)
    assert before == after


def test_cancel_before_materialize_leaves_operation_cancelled(tmp_path: Path) -> None:
    harness = build_history_compare_harness(tmp_path, idempotency_key="history-compare-cancel-before")
    insert_history_compare_operation(harness)
    session, control, operation, step = claim_next_step(harness)
    control.request_cancel()
    run_claimed_handler(
        harness,
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        session,
        control,
        operation,
        step,
    )

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        persisted = unit_of_work.operations.get_operation(harness.operation_id)
        incident = unit_of_work.history_compare.get_integrity_by_operation_id(harness.operation_id)
    assert persisted.status is OperationStatus.CANCELLED
    assert persisted.ready_closure_ref is None
    assert incident is None
    # Checkpoint never published on this path; empty protection means no spurious pin only.
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-checkpoint",
            owner_id=step.step_id,
        ) == frozenset()
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-operation",
            owner_id=harness.operation_id,
        ) == frozenset()


def test_cancel_at_assemble_entry_releases_materialize_checkpoint_protection(tmp_path: Path) -> None:
    harness = build_history_compare_harness(
        tmp_path,
        idempotency_key="history-compare-cancel-assemble-entry",
    )
    insert_history_compare_operation(harness)
    materialize_step_id = history_compare_step_id(
        harness.operation_id,
        HISTORY_COMPARE_STEP_MATERIALIZE,
    )
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(materialize_step_id)
        assert materialize_step.checkpoint_ref is not None
        protected = unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-checkpoint",
            owner_id=materialize_step_id,
        )
        assert protected != frozenset()

    session, control, operation, step = claim_next_step(harness)
    assert step.step_name == HISTORY_COMPARE_STEP_ASSEMBLE
    control.request_cancel()
    run_claimed_handler(
        harness,
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        session,
        control,
        operation,
        step,
    )

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        persisted = unit_of_work.operations.get_operation(harness.operation_id)
        assert persisted.status is OperationStatus.CANCELLED
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-checkpoint",
            owner_id=materialize_step_id,
        ) == frozenset()
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-operation",
            owner_id=harness.operation_id,
        ) == frozenset()


def test_confirmed_integrity_incident_published_despite_cancel_signal(tmp_path: Path) -> None:
    from gateway_backend.application.history import compare_jobs as compare_jobs_module

    commit_id = BASELINE_HEAD.business_baseline_commit_id
    rows_a = {"t": ((1,),)}
    rows_b = {"t": ((2,),)}
    harness = build_history_compare_harness(
        tmp_path,
        custom_providers={
            commit_id: history_compare_provider(
                commit_id=commit_id,
                declared_rows=rows_a,
                per_read_rows=(rows_b, rows_b),
            )
        },
        idempotency_key="history-compare-cancel-race",
    )
    insert_history_compare_operation(harness)
    session, control, operation, step = claim_next_step(harness)

    original_materialize = compare_jobs_module._materialize_distinct_commits

    def materialize_with_cancel_signal(payload: object, deps: object) -> object:
        control.request_cancel()
        return original_materialize(payload, deps)  # type: ignore[arg-type]

    with patch.object(
        compare_jobs_module,
        "_materialize_distinct_commits",
        side_effect=materialize_with_cancel_signal,
    ):
        run_claimed_handler(
            harness,
            HISTORY_COMPARE_MATERIALIZE_HANDLER,
            session,
            control,
            operation,
            step,
        )

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        persisted = unit_of_work.operations.get_operation(harness.operation_id)
        incident = unit_of_work.history_compare.get_integrity_by_operation_id(harness.operation_id)
    assert persisted.status is OperationStatus.FAILED
    assert incident is not None
    assert control.cancel_requested is True
    # Integrity path fails before checkpoint publish; empty protection means no spurious pin only.
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-checkpoint",
            owner_id=step.step_id,
        ) == frozenset()
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-operation",
            owner_id=harness.operation_id,
        ) == frozenset()
