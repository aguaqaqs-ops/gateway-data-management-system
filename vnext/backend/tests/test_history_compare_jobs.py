"""History compare job pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
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
    history_compare_step_id,
)
from gateway_backend.capabilities.comparison import (
    OrderedRecordKind,
    ComparisonTableStatus,
)
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
from tests.support.table_rules import _runtime_comparison_ruleset_digest
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    RepositoryCatalogTable,
    RepositoryColumn,
)
from tests.support.repository_ref_materialization import (
    FakeRepositoryTableAccessProvider,
    catalog_table,
    int_id_column,
    make_catalog,
    text_column,
)
from gateway_backend.operations.contracts import BusinessReference

from tests.support.history_compare_oracle import (
    compare_bound_snapshots,
    materialize_bound_snapshot,
    oracle_comparison_digest,
)
from tests.support.history_zero_write_tables import capture_business_table_state

F1_POLICY_BINDING_CASES = (
    (
        "move_only",
        {ORDERED_SYX_TABLE: ((1, 1, "a"), (2, 2, "b"))},
        {ORDERED_SYX_TABLE: ((2, 1, "b"), (1, 2, "a"))},
        (OrderedRecordKind.ROW_MOVED,),
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
        (OrderedRecordKind.ROW_MOVED,),
        0,
    ),
)

RULESET_MISMATCH_STEPS = (
    ("materialize_inputs", HISTORY_COMPARE_MATERIALIZE_HANDLER, ()),
    (
        "assemble_comparison",
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        (HISTORY_COMPARE_MATERIALIZE_HANDLER,),
    ),
    (
        "publish_result",
        HISTORY_COMPARE_PUBLISH_HANDLER,
        (HISTORY_COMPARE_MATERIALIZE_HANDLER, HISTORY_COMPARE_ASSEMBLE_HANDLER),
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
    assert "compare_binding_digest" not in envelope.job_state


def test_assemble_resumes_from_materialized_sides_with_runtime_ruleset(tmp_path: Path) -> None:
    harness = build_history_compare_harness(tmp_path, idempotency_key="history-compare-resume")
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
    assert materialize_step.checkpoint_ref is not None
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
        return FakeRepositoryTableAccessProvider(
            catalog=catalog,
            base_catalog=catalog,
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
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
    assert operation.status is OperationStatus.SUCCEEDED
    assert materialize_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, materialize_step.checkpoint_ref)
    assert "table_policies" not in envelope.job_state
    facts = compare_bound_snapshots(
        materialize_bound_snapshot(
            providers[before_commit],
            commit_id=before_commit,
            artifact_store=harness.artifact_store,
        ),
        materialize_bound_snapshot(
            providers[current_commit],
            commit_id=current_commit,
            artifact_store=harness.artifact_store,
        ),
    )
    assert facts.tables[0].status is ComparisonTableStatus.DEGRADED


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


def test_repository_row_count_mismatch_fails_history_compare(tmp_path: Path) -> None:
    commit_id = BASELINE_HEAD.business_baseline_commit_id
    provider = history_compare_provider(
        commit_id=commit_id,
        row_count=2,
        declared_rows={"t": ((1,),)},
    )
    harness = build_history_compare_harness(
        tmp_path,
        custom_providers={
            commit_id: provider,
            "commit-b": history_compare_provider(commit_id="commit-b"),
        },
        idempotency_key="history-compare-row-count-mismatch",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
    assert operation.status is OperationStatus.FAILED
    assert materialize_step.status is StepStatus.FAILED
    assert operation.diagnostic is not None
    assert operation.diagnostic.code == "REPOSITORY_ROW_COUNT_MISMATCH"


def test_ruleset_mismatch_publishes_stable_failed_code(tmp_path: Path) -> None:
    import json

    from gateway_shared_kernel.jcs import canonicalize_json_value

    harness = build_history_compare_harness(tmp_path, idempotency_key="history-compare-ruleset")
    payload = json.loads(harness.job_payload)
    payload["comparison_ruleset_digest"] = "sha256:old-ruleset"
    object.__setattr__(harness, "job_payload", canonicalize_json_value(payload))
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
    assert operation.status is OperationStatus.FAILED
    assert operation.diagnostic is not None
    assert operation.diagnostic.code == HistoryCompareDiagnosticCode.HISTORY_RULESET_VERSION_MISMATCH.value


@pytest.mark.parametrize(
    ("step_name", "handler_identity", "prior_handlers"),
    RULESET_MISMATCH_STEPS,
    ids=("materialize", "assemble", "publish"),
)
def test_history_compare_rejects_runtime_ruleset_change_before_each_step(
    tmp_path: Path,
    step_name: str,
    handler_identity: str,
    prior_handlers: tuple[str, ...],
) -> None:
    harness = build_history_compare_harness(tmp_path, idempotency_key=f"ruleset-drift-{step_name}")
    insert_history_compare_operation(harness)
    for prior_handler in prior_handlers:
        run_through_step(harness, prior_handler)

    with patch(
        "gateway_backend.application.history.compare_jobs.comparison_rule_set",
        return_value=SimpleNamespace(ruleset_digest=DigestRef("sha256:" + "cd" * 32)),
    ):
        run_through_step(harness, handler_identity)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        failed_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, step_name)
        )
    assert operation.status is OperationStatus.FAILED
    assert operation.diagnostic is not None
    assert operation.diagnostic.code == HistoryCompareDiagnosticCode.HISTORY_RULESET_VERSION_MISMATCH.value
    assert failed_step.status is StepStatus.FAILED


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
    assert "table_policies" not in envelope.job_state

    run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_PUBLISH_HANDLER)

    oracle_digest = oracle_comparison_digest(
        before_provider=providers[before_commit],
        current_provider=providers[current_commit],
        before_commit=before_commit,
        current_commit=current_commit,
        artifact_store=harness.artifact_store,
    )
    facts = compare_bound_snapshots(
        materialize_bound_snapshot(
            providers[before_commit],
            commit_id=before_commit,
            artifact_store=harness.artifact_store,
        ),
        materialize_bound_snapshot(
            providers[current_commit],
            commit_id=current_commit,
            artifact_store=harness.artifact_store,
        ),
    )
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


def test_history_compares_canonical_net_cfg_without_dropped_column(tmp_path: Path) -> None:
    table_name = "net_cfg"
    before_commit = BASELINE_HEAD.business_baseline_commit_id
    current_commit = "commit-b"
    before_rows = {table_name: (("b1", 1, "a"),)}
    current_rows = {table_name: (("b1", 1, "a"),)}
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
    assert "table_policies" not in envelope.job_state

    run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_PUBLISH_HANDLER)

    facts = compare_bound_snapshots(
        materialize_bound_snapshot(
            providers[before_commit],
            commit_id=before_commit,
            artifact_store=harness.artifact_store,
        ),
        materialize_bound_snapshot(
            providers[current_commit],
            commit_id=current_commit,
            artifact_store=harness.artifact_store,
        ),
    )
    kinds: list[OrderedRecordKind] = []
    for table in facts.tables:
        extension = table.ordered_extension
        if extension is not None:
            kinds.extend(record.record_kind for record in extension.records)
    assert kinds == []
    modified_count = sum(table.row_modified_count for table in facts.tables)
    assert modified_count == 0
    assert facts.tables[0].status is ComparisonTableStatus.UNCHANGED


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
        comparison_ruleset_digest=_runtime_comparison_ruleset_digest(),
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
    assert persisted.status is OperationStatus.CANCELLED
    assert persisted.ready_closure_ref is None
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
